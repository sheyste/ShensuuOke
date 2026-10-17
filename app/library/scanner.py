"""Folder scanning, duplicate fingerprinting, relocation and missing-file detection."""
from __future__ import annotations
import hashlib
import os
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
    return {s["id"] for s in db.list_songs() if s["missing"]}


def refresh_missing(db, result=None) -> int:
    """Flag songs whose files vanished; clear the flag for files that came back."""
    n = 0
    for s in db.list_songs():
        exists = os.path.isfile(s["path"])
        if exists and s["missing"]:
            db.set_missing(s["id"], False)
        elif not exists and not s["missing"]:
            db.set_missing(s["id"], True)
            n += 1
    return n


def scan_folder(db, folder, reader=read_metadata, progress=None, cancel=None, remember=True,
                result=None, lazy=False) -> ScanResult:
    if not os.path.isdir(folder):
        raise ScanError(f"Folder not found: {folder}")
    own = result is None
    result = result or ScanResult()
    before = _missing_ids(db)
    refresh_missing(db)              # so files moved elsewhere can be matched back to their rows
    count = 0
    for root, dirs, files in os.walk(folder):
        dirs.sort()
        for name in sorted(files):
            if os.path.splitext(name)[1].lower() not in SUPPORTED_EXT:
                continue
            if cancel and cancel():
                result.cancelled = True
                return result
            path = os.path.join(root, name)
            _process(db, path, reader, result, lazy=lazy)
            count += 1
            if progress:
                progress(count, path)
    if remember:
        db.add_library_folder(folder)
    refresh_missing(db)
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


def rescan_library(db, reader=read_metadata, progress=None, cancel=None) -> ScanResult:
    result = ScanResult()
    before = _missing_ids(db)
    for folder in db.library_folders():
        if os.path.isdir(folder):
            scan_folder(db, folder, reader, progress, cancel, remember=False, result=result)
        else:
            result.errors.append((folder, "Library folder is unavailable (drive disconnected or folder moved)."))
        if result.cancelled:
            return result
    refresh_missing(db)
    result.newly_missing = len(_missing_ids(db) - before)
    result.duplicate_groups = len(db.find_duplicates())
    return result
