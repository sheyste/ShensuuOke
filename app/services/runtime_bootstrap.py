"""Provision the native media runtimes used by the player.

The Windows build carries these files when they are available.  A source run
or an older build can also install them automatically into the user's app
data directory, so playback never depends on a separate system installer.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path


FFMPEG_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
FLUIDSYNTH_URL = (
    "https://github.com/FluidSynth/fluidsynth/releases/download/v2.6.1/"
    "fluidsynth-v2.6.1-win10-x64-cpp11.zip"
)
SOUNDFONT_URL = "https://raw.githubusercontent.com/craffel/pretty-midi/main/pretty_midi/TimGM6mb.sf2"


def _roots(app_data: Path) -> list[Path]:
    roots = []
    if getattr(sys, "_MEIPASS", None):
        roots.append(Path(sys._MEIPASS))
    roots.extend((Path(__file__).resolve().parents[2], app_data))
    return roots


def _ffmpeg_path(app_data: Path) -> Path | None:
    for root in _roots(app_data):
        path = root / "runtime" / "ffmpeg" / "ffmpeg.exe"
        if path.is_file():
            return path
    return None


def _fluidsynth_dir(app_data: Path) -> Path | None:
    for root in _roots(app_data):
        path = root / "runtime" / "fluidsynth"
        if path.is_dir() and any(path.glob("*.dll")):
            return path
    return None


def _soundfont_path(app_data: Path) -> Path | None:
    for root in _roots(app_data):
        path = root / "runtime" / "soundfonts" / "TimGM6mb.sf2"
        if path.is_file() and path.stat().st_size > 100000:
            return path
    return None


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "KaraokePlayer/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response, destination.open("wb") as out:
        shutil.copyfileobj(response, out)


def _safe_extract(zip_path: Path, destination: Path, wanted_suffix: str) -> list[Path]:
    extracted = []
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            name = member.filename.replace("\\", "/")
            if member.is_dir() or not name.lower().endswith(wanted_suffix):
                continue
            target = destination / Path(name).name
            with archive.open(member) as source, target.open("wb") as out:
                shutil.copyfileobj(source, out)
            extracted.append(target)
    return extracted


def ensure_native_runtime(app_data_dir: str | os.PathLike[str]) -> tuple[str | None, str | None, str | None, str | None]:
    """Return ``(ffmpeg, fluidsynth_dll_dir, soundfont, error)`` after setup."""
    if sys.platform != "win32":
        return None, None, None, None

    app_data = Path(app_data_dir)
    runtime = app_data / "runtime"
    downloads = runtime / "downloads"
    errors = []
    ffmpeg = _ffmpeg_path(app_data)
    fluidsynth = _fluidsynth_dir(app_data)
    soundfont = _soundfont_path(app_data)

    try:
        if ffmpeg is None:
            downloads.mkdir(parents=True, exist_ok=True)
            archive = downloads / "ffmpeg.zip"
            _download(FFMPEG_URL, archive)
            files = _safe_extract(archive, runtime / "ffmpeg", "ffmpeg.exe")
            ffmpeg = files[0] if files else None
    except Exception as exc:
        errors.append(f"FFmpeg: {exc}")

    try:
        if fluidsynth is None:
            downloads.mkdir(parents=True, exist_ok=True)
            archive = downloads / "fluidsynth.zip"
            _download(FLUIDSYNTH_URL, archive)
            files = _safe_extract(archive, runtime / "fluidsynth", ".dll")
            fluidsynth = (runtime / "fluidsynth") if files else None
    except Exception as exc:
        errors.append(f"FluidSynth: {exc}")

    try:
        if soundfont is None:
            downloads.mkdir(parents=True, exist_ok=True)
            soundfont = runtime / "soundfonts" / "TimGM6mb.sf2"
            soundfont.parent.mkdir(parents=True, exist_ok=True)
            _download(SOUNDFONT_URL, soundfont)
            if soundfont.stat().st_size <= 100000:
                soundfont = None
                raise RuntimeError("downloaded SoundFont is incomplete")
    except Exception as exc:
        soundfont = None
        errors.append(f"SoundFont: {exc}")

    # Keep the app-data copy discoverable by the existing audio backends.
    if ffmpeg:
        os.environ["FFMPEG_PATH"] = str(ffmpeg)
    if fluidsynth:
        os.environ["FLUIDSYNTH_DLL_DIR"] = str(fluidsynth)
    return (str(ffmpeg) if ffmpeg else None,
            str(fluidsynth) if fluidsynth else None,
            str(soundfont) if soundfont else None,
            "; ".join(errors) if errors else None)
