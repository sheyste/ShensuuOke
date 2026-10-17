"""FFmpeg-based decoding of audio/video files into float32 stereo PCM held in memory."""
from __future__ import annotations
import os
import shutil
import subprocess
import sys
from pathlib import Path
import numpy as np


class DecodeError(RuntimeError):
    pass


def find_ffmpeg(configured: str | None = None) -> str:
    roots = []
    if getattr(sys, "_MEIPASS", None):
        roots.append(Path(sys._MEIPASS))
    roots.append(Path(__file__).resolve().parents[2])
    bundled = [root / "runtime" / "ffmpeg" / "ffmpeg.exe" for root in roots]
    for cand in (configured, *bundled, os.environ.get("FFMPEG_PATH"), shutil.which("ffmpeg")):
        if cand and os.path.isfile(cand):
            return str(cand)
        if cand and shutil.which(cand):
            return shutil.which(cand)
    raise DecodeError("FFmpeg not found. Add ffmpeg.exe to the bundled runtime\\ffmpeg folder, "
                      "install it on PATH, or set its path in Audio Settings.")


def decode_file(path: str, sample_rate: int = 44100, ffmpeg: str | None = None) -> np.ndarray:
    if not os.path.isfile(path):
        raise DecodeError(f"File not found: {path}")
    exe = find_ffmpeg(ffmpeg)
    cmd = [exe, "-v", "error", "-i", path, "-vn", "-f", "f32le", "-acodec", "pcm_f32le",
           "-ac", "2", "-ar", str(sample_rate), "-"]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    p = subprocess.run(cmd, capture_output=True, creationflags=flags)
    if p.returncode != 0 or not p.stdout:
        raise DecodeError(f"FFmpeg could not decode '{os.path.basename(path)}': "
                          f"{p.stderr.decode(errors='replace').strip() or 'no audio stream'}")
    return np.frombuffer(p.stdout, dtype=np.float32).reshape(-1, 2).copy()


class FileSource:
    """Audio source over fully-decoded PCM. Seeking is exact; tempo change is not supported yet."""
    supports_speed = False

    def __init__(self, samples: np.ndarray, sample_rate: int = 44100):
        self.samples, self.sr, self._i = samples, sample_rate, 0

    @property
    def duration(self): return len(self.samples) / self.sr
    @property
    def position(self): return self._i / self.sr

    def set_speed(self, s: float): pass

    def seek(self, seconds: float):
        self._i = int(max(0.0, min(seconds, self.duration)) * self.sr)

    def read(self, frames: int):
        chunk = self.samples[self._i:self._i + frames]
        self._i += len(chunk)
        if len(chunk) < frames:
            chunk = np.vstack([chunk, np.zeros((frames - len(chunk), 2), np.float32)])
        return chunk, self._i >= len(self.samples)
