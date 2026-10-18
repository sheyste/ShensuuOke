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
SOUNDFONT_URL = ""


def _roots(app_data: Path) -> list[Path]:
    roots = []
    if getattr(sys, "_MEIPASS", None):
        roots.append(Path(sys._MEIPASS))
    roots.extend((Path(__file__).resolve().parents[2], app_data))
    return roots


def _unpack_bundled_runtime(app_data: Path) -> None:
    """Automatically reconstruct and unpack git-friendly compressed archives if binaries are not yet unpacked."""
    import io
    for root in _roots(app_data):
        # 1. Unpack ffmpeg.exe if ffmpeg.zip exists
        ff_dir = root / "runtime" / "ffmpeg"
        ff_exe = ff_dir / "ffmpeg.exe"
        ff_zip = ff_dir / "ffmpeg.zip"
        if not ff_exe.is_file() and ff_zip.is_file():
            try:
                with zipfile.ZipFile(ff_zip) as z:
                    z.extractall(ff_dir)
            except Exception as e:
                print(f"Notice: Failed to extract {ff_zip}: {e}", file=sys.stderr)

        # 2. Unpack DreamSam SoundFont if split git parts exist
        sf_dir = root / "runtime" / "soundfonts"
        sf_file = sf_dir / "DreamSam 8202 (SPHE).sf2"
        p1 = sf_dir / "DreamSam.zip.part1"
        p2 = sf_dir / "DreamSam.zip.part2"
        if not sf_file.is_file() and p1.is_file() and p2.is_file():
            try:
                with p1.open("rb") as f1, p2.open("rb") as f2:
                    combined = f1.read() + f2.read()
                with zipfile.ZipFile(io.BytesIO(combined)) as z:
                    z.extractall(sf_dir)
            except Exception as e:
                print(f"Notice: Failed to unpack {sf_file}: {e}", file=sys.stderr)


def _ffmpeg_path(app_data: Path) -> Path | None:
    _unpack_bundled_runtime(app_data)
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
    _unpack_bundled_runtime(app_data)
    for root in _roots(app_data):
        path = root / "runtime" / "soundfonts" / "DreamSam 8202 (SPHE).sf2"
        if path.is_file() and path.stat().st_size > 100000:
            return path
    for root in _roots(app_data):
        sf_dir = root / "runtime" / "soundfonts"
        if sf_dir.is_dir():
            for sf in sf_dir.glob("*.sf2"):
                if sf.is_file() and sf.stat().st_size > 100000:
                    return sf
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
        if soundfont is None and SOUNDFONT_URL:
            downloads.mkdir(parents=True, exist_ok=True)
            soundfont = runtime / "soundfonts" / "DreamSam 8202 (SPHE).sf2"
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
