"""Asynchronous Video Optimizer & Cache Service for ShensuuOke.

Prevents GUI freezes when changing songs or background videos by:
1. Maintaining in-memory resolution of video formats and transcoded cache files.
2. Checking disk caches BEFORE invoking any subprocess.
3. Performing all heavy FFmpeg probing and transcoding in background threads.
4. Caching directory scanning to avoid repetitive disk I/O on every song change.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
import re
import subprocess
import tempfile
from typing import Dict, List, Optional, Set, Tuple
from app.audio.audio_decoder import find_ffmpeg

_SUPPORTED_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm"}
_MEMORY_CACHE: Dict[str, str] = {}
_FOLDER_CACHE: Dict[str, Tuple[float, List[str]]] = {}
_PENDING_TRANSCODES: Set[str] = set()
_EXECUTOR: Optional[ThreadPoolExecutor] = None


def _get_executor() -> ThreadPoolExecutor:
    global _EXECUTOR
    if _EXECUTOR is None:
        _EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="VideoOpt")
    return _EXECUTOR


def _get_cache_dir() -> str:
    cache_dir = os.path.join(tempfile.gettempdir(), "shensuuoke_video_cache")
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def _make_stat_key(src_path: str) -> Tuple[str, str]:
    """Return (mem_key, cache_key_hash)."""
    try:
        stat = os.stat(src_path)
        raw_key = f"{os.path.abspath(src_path)}:{stat.st_mtime}:{stat.st_size}"
        cache_hash = hashlib.sha256(raw_key.encode()).hexdigest()[:16]
        return raw_key, cache_hash
    except Exception:
        raw_key = os.path.abspath(src_path)
        cache_hash = hashlib.sha256(raw_key.encode()).hexdigest()[:16]
        return raw_key, cache_hash


def get_cached_folder_videos(folder: str) -> List[str]:
    """Return list of video file paths in folder, cached by directory mtime to avoid repeated disk scans."""
    if not folder or not os.path.isdir(folder):
        return []
    try:
        mtime = os.path.getmtime(folder)
    except Exception:
        mtime = 0.0

    cached = _FOLDER_CACHE.get(folder)
    if cached and cached[0] == mtime:
        return cached[1]

    try:
        files = [
            os.path.join(folder, name)
            for name in sorted(os.listdir(folder))
            if os.path.splitext(name)[1].lower() in _SUPPORTED_EXTENSIONS
            and os.path.isfile(os.path.join(folder, name))
        ]
        _FOLDER_CACHE[folder] = (mtime, files)
        return files
    except Exception:
        return []


def _transcode_video(ffmpeg_bin: str, src_path: str, dst_path: str, cache_hash: str):
    """Run FFmpeg transcode in background thread."""
    try:
        tmp_path = dst_path + ".tmp.mp4"
        cmd = [
            ffmpeg_bin, "-v", "error", "-y", "-i", src_path,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-pix_fmt", "yuv420p", "-c:a", "copy", tmp_path
        ]
        res = subprocess.run(
            cmd,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=120
        )
        if res.returncode == 0 and os.path.isfile(tmp_path):
            os.replace(tmp_path, dst_path)
            raw_key, _ = _make_stat_key(src_path)
            _MEMORY_CACHE[raw_key] = dst_path
    except Exception:
        pass
    finally:
        _PENDING_TRANSCODES.discard(cache_hash)


def get_playable_video_fast(src_path: str, auto_transcode_async: bool = True) -> str:
    """Return a video path compatible with QtMultimedia with zero UI freeze.

    1. Checks in-memory cache.
    2. Checks disk cache for pre-transcoded files before any FFmpeg probe.
    3. If not cached, probes codec; if transcoding is needed, queues it in background
       and returns the original or cached version without stalling the caller.
    """
    if not src_path or not os.path.isfile(src_path):
        return src_path

    raw_key, cache_hash = _make_stat_key(src_path)

    # 1. Fast in-memory cache hit
    if raw_key in _MEMORY_CACHE:
        return _MEMORY_CACHE[raw_key]

    # 2. Fast disk cache check (existing transcoded file)
    cache_dir = _get_cache_dir()
    dst_path = os.path.join(cache_dir, f"{cache_hash}.mp4")
    if os.path.isfile(dst_path) and os.path.getsize(dst_path) > 0:
        _MEMORY_CACHE[raw_key] = dst_path
        return dst_path

    # 3. Probe codec using bundled FFmpeg
    try:
        ffmpeg_bin = find_ffmpeg()
    except Exception:
        _MEMORY_CACHE[raw_key] = src_path
        return src_path

    try:
        probe = subprocess.run(
            [ffmpeg_bin, "-i", src_path],
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            timeout=3
        )
        m = re.search(r"Stream #\d+:\d+.*?: Video: ([^,\s]+)", probe.stderr)
        codec = (m.group(1).lower() if m else "")
        if codec in ("h264", "avc1", "vp8", "vp9", "mjpeg"):
            _MEMORY_CACHE[raw_key] = src_path
            return src_path

        # Codec requires transcoding (e.g. AV1 or exotic stream)
        if auto_transcode_async and cache_hash not in _PENDING_TRANSCODES:
            _PENDING_TRANSCODES.add(cache_hash)
            _get_executor().submit(_transcode_video, ffmpeg_bin, src_path, dst_path, cache_hash)

        # In the meantime, if a transcoded file isn't ready yet, return original
        return src_path
    except Exception:
        _MEMORY_CACHE[raw_key] = src_path
        return src_path


def is_video_ready(src_path: str) -> bool:
    """Check if video is already verified or transcoded without blocking."""
    raw_key, cache_hash = _make_stat_key(src_path)
    if raw_key in _MEMORY_CACHE:
        return True
    cache_dir = _get_cache_dir()
    dst_path = os.path.join(cache_dir, f"{cache_hash}.mp4")
    return os.path.isfile(dst_path) and os.path.getsize(dst_path) > 0


def prewarm_background_folder(folder: str):
    """Scan and pre-probe/transcode background videos in background thread."""
    if not folder or not os.path.isdir(folder):
        return

    def _worker():
        files = get_cached_folder_videos(folder)
        for f in files:
            try:
                get_playable_video_fast(f, auto_transcode_async=True)
            except Exception:
                pass

    _get_executor().submit(_worker)
