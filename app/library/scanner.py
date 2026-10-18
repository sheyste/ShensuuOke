"""Folder scanning, duplicate fingerprinting, relocation and missing-file detection."""
from __future__ import annotations
import hashlib
import os
import time
from dataclasses import dataclass, field
from .metadata import SUPPORTED_EXT, index_metadata, read_metadata


class ScanError(RuntimeError):
    pass


@dataclass
class ScanResult:
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    relocated: int = 0
    newly_missing: int = 0
    duplicate_groups: int = 0
    cancelled: bool = False
    errors: list = field(default_factory=list)   # (path, message)

    def summary(self) -> str:
        return (f"Added {self.added}, updated {self.updated}, unchanged {self.unchanged}, "
                f"moved {self.relocated}, missing {self.newly_missing}, errors {len(self.errors)}, "
                f"duplicate groups {self.duplicate_groups}")


def fingerprint(path: str) -> str | None:
    """Size + SHA1 of first and last 64 KiB: cheap and stable for duplicate detection."""
    try:
        size = os.path.getsize(path)
        h = hashlib.sha1(str(size).encode())
        with open(path, "rb") as f:
            h.update(f.read(65536))
            if size > 131072:
                f.seek(-65536, os.SEEK_END)
                h.update(f.read(65536))
        return h.hexdigest()
    except OSError:
        return None


def _iter_supported_files(folder: str, supported_ext: set):
    """Recursively yield (path, name, stat_result) for all supported files using os.scandir."""
    stack = [folder]
    while stack:
        curr = stack.pop()
        try:
            with os.scandir(curr) as it:
                entries = list(it)
        except OSError:
            continue
        dirs, files = [], []
        for e in entries:
            try:
                if e.is_dir(follow_symlinks=False):
                    dirs.append(e)
                elif e.is_file(follow_symlinks=False):
                    ext = os.path.splitext(e.name)[1].lower()
                    if ext in supported_ext:
                        files.append(e)
            except OSError:
                continue
        files.sort(key=lambda e: e.name.lower())
        for e in files:
            try:
                st = e.stat(follow_symlinks=False)
                yield e.path, e.name, st
            except OSError:
                yield e.path, e.name, None
        dirs.sort(key=lambda e: e.name.lower())
        for d in reversed(dirs):
            stack.append(d.path)


def _process(db, path, reader, result, lazy=False):
    try:
        st = os.stat(path)
    except OSError as e:
        result.errors.append((path, f"Cannot access file: {e}"))
        return
    existing = db.get_song_by_path(path)
    if (existing and existing["size"] == st.st_size and existing["mtime"] is not None
            and abs(existing["mtime"] - st.st_mtime) < 1e-3 and not existing["missing"]):
        result.unchanged += 1
        return
    info = index_metadata(path) if lazy else reader(path)
    info.update(size=st.st_size, mtime=st.st_mtime,
                fingerprint=None if lazy else fingerprint(path))
    if existing is None:
        moved = db.find_missing_by_fingerprint(info["fingerprint"])
        if moved:
            db.relocate_song(moved["id"], path, info)
            result.relocated += 1
            return
    _, created = db.upsert_song(path, info)
    result.added += created
    result.updated += (not created)
    if info.get("error"):
        result.errors.append((path, info["error"]))


def _missing_ids(db) -> set:
    if hasattr(db, "list_songs_paths_and_missing"):
        return {s["id"] for s in db.list_songs_paths_and_missing() if s["missing"]}
    return {s["id"] for s in db.list_songs() if s["missing"]}


def refresh_missing(db, result=None) -> int:
    """Flag songs whose files vanished; clear the flag for files that came back."""
    songs = db.list_songs_paths_and_missing() if hasattr(db, "list_songs_paths_and_missing") else db.list_songs()
    to_mark_missing = []
    to_unmark_missing = []
    for s in songs:
        exists = os.path.isfile(s["path"])
        if exists and s["missing"]:
            to_unmark_missing.append(s["id"])
        elif not exists and not s["missing"]:
            to_mark_missing.append(s["id"])

    if hasattr(db, "set_missing_many"):
        if to_mark_missing:
            db.set_missing_many(to_mark_missing, True)
        if to_unmark_missing:
            db.set_missing_many(to_unmark_missing, False)
    else:
        for sid in to_mark_missing:
            db.set_missing(sid, True)
        for sid in to_unmark_missing:
            db.set_missing(sid, False)
    return len(to_mark_missing)


def scan_folder(db, folder, reader=read_metadata, progress=None, cancel=None, remember=True,
                result=None, lazy=None) -> ScanResult:
    if not os.path.isdir(folder):
        raise ScanError(f"Folder not found: {folder}")
    if lazy is None:
        lazy = (reader is read_metadata)
    own = result is None
    result = result or ScanResult()
    before = _missing_ids(db)

    # Pre-fetch existing songs for this folder into memory
    if hasattr(db, "get_path_map"):
        existing_map = db.get_path_map(folder)
    else:
        all_s = db.list_songs() if hasattr(db, "list_songs") else []
        existing_map = {s["path"]: dict(s) for s in all_s}

    norm_existing = {os.path.normcase(os.path.abspath(p)): s for p, s in existing_map.items()}

    if not lazy:
        # If not lazy, files might have moved; mark files missing before scan so fingerprint matches them
        missing_before = [s["id"] for p, s in existing_map.items() if not os.path.exists(p) and not s["missing"]]
        if missing_before:
            if hasattr(db, "set_missing_many"):
                db.set_missing_many(missing_before, True)
            else:
                for sid in missing_before:
                    db.set_missing(sid, True)
            for s in existing_map.values():
                if s["id"] in missing_before:
                    s["missing"] = 1

    to_insert = []
    to_update = []
    found_norm_paths = set()
    BATCH_SIZE = 1000
    count = 0
    last_progress_time = 0.0
    last_path = ""

    def flush_batch():
        nonlocal to_insert, to_update
        if not to_insert and not to_update:
            return
        if hasattr(db, "save_songs_batch"):
            ins, upd = db.save_songs_batch(to_insert, to_update)
            result.added += ins
            result.updated += upd
        else:
            for p, info in to_insert:
                _, created = db.upsert_song(p, info)
                result.added += created
                result.updated += (not created)
            for sid, info in to_update:
                path = info.get("path") or ""
                db.upsert_song(path, info)
                result.updated += 1
        to_insert.clear()
        to_update.clear()

    for path, name, st in _iter_supported_files(folder, SUPPORTED_EXT):
        if cancel and cancel():
            result.cancelled = True
            flush_batch()
            return result

        if st is None:
            result.errors.append((path, "Cannot access file."))
            continue

        last_path = path
        norm_p = os.path.normcase(os.path.abspath(path))
        found_norm_paths.add(norm_p)
        count += 1

        existing = existing_map.get(path)
        if existing is None:
            existing = norm_existing.get(norm_p)

        if (existing and existing["size"] == st.st_size and existing["mtime"] is not None
                and abs(existing["mtime"] - st.st_mtime) < 1e-3 and not existing["missing"]):
            result.unchanged += 1
        else:
            try:
                info = index_metadata(path) if lazy else reader(path)
            except Exception as e:
                result.errors.append((path, f"Error reading metadata: {e}"))
                continue
            info.update(size=st.st_size, mtime=st.st_mtime,
                        fingerprint=None if lazy else fingerprint(path))
            if existing is None:
                moved = db.find_missing_by_fingerprint(info["fingerprint"]) if not lazy else None
                if moved:
                    db.relocate_song(moved["id"], path, info)
                    result.relocated += 1
                    norm_existing[norm_p] = dict(moved, missing=0)
                    continue
                to_insert.append((path, info))
                norm_existing[norm_p] = {"id": None, "missing": 0}
            else:
                to_update.append((existing["id"], info))

            if info.get("error"):
                result.errors.append((path, info["error"]))

            if len(to_insert) + len(to_update) >= BATCH_SIZE:
                flush_batch()

        now = time.monotonic()
        if progress and (count <= 5 or count % 50 == 0 or (now - last_progress_time) >= 0.04):
            progress(count, path)
            last_progress_time = now

    flush_batch()

    if progress and count > 0 and last_path:
        progress(count, last_path)

    newly_missing_ids = []
    recovered_ids = []
    for p, s in existing_map.items():
        np = os.path.normcase(os.path.abspath(p))
        if np not in found_norm_paths:
            if not s["missing"]:
                newly_missing_ids.append(s["id"])
        else:
            if s["missing"]:
                recovered_ids.append(s["id"])

    if newly_missing_ids:
        if hasattr(db, "set_missing_many"):
            db.set_missing_many(newly_missing_ids, True)
        else:
            for sid in newly_missing_ids:
                db.set_missing(sid, True)

    if recovered_ids:
        if hasattr(db, "set_missing_many"):
            db.set_missing_many(recovered_ids, False)
        else:
            for sid in recovered_ids:
                db.set_missing(sid, False)

    if remember:
        db.add_library_folder(folder)

    if own:
        result.newly_missing = len(_missing_ids(db) - before)
    result.duplicate_groups = len(db.find_duplicates())
    return result


def import_files(db, paths, reader=read_metadata, progress=None, cancel=None) -> ScanResult:
    result = ScanResult()
    for i, path in enumerate(paths, 1):
        if cancel and cancel():
            result.cancelled = True
            break
        if os.path.splitext(path)[1].lower() not in SUPPORTED_EXT:
            result.errors.append((path, "Unsupported file type."))
            continue
        _process(db, path, reader, result)
        if progress:
            progress(i, path)
    result.duplicate_groups = len(db.find_duplicates())
    return result


def rescan_library(db, reader=read_metadata, progress=None, cancel=None, lazy=None) -> ScanResult:
    if lazy is None:
        lazy = (reader is read_metadata)
    result = ScanResult()
    before = _missing_ids(db)
    for folder in db.library_folders():
        if os.path.isdir(folder):
            scan_folder(db, folder, reader=reader, progress=progress, cancel=cancel, remember=False, result=result, lazy=lazy)
        else:
            result.errors.append((folder, "Library folder is unavailable (drive disconnected or folder moved)."))
            if hasattr(db, "get_path_map"):
                folder_songs = db.get_path_map(folder)
                missing_ids = [s["id"] for s in folder_songs.values() if not s["missing"]]
                if missing_ids:
                    if hasattr(db, "set_missing_many"):
                        db.set_missing_many(missing_ids, True)
                    else:
                        for sid in missing_ids:
                            db.set_missing(sid, True)
        if result.cancelled:
            return result
    refresh_missing(db, result)
    result.newly_missing = len(_missing_ids(db) - before)
    result.duplicate_groups = len(db.find_duplicates())
    return result
