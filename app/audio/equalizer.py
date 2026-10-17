"""Shared real-time DSP chain: 10-band EQ, bass/treble, balance, volume, mute, soft limiter.

Every audio source (synthesized MIDI or decoded files) passes through this one object,
so the EQ affects actual output. Filters are RBJ biquads run with scipy.signal.sosfilt,
carrying filter state (zi) between blocks so block-wise output equals one-shot output.
"""
from __future__ import annotations
import threading
import numpy as np
from scipy.signal import sosfilt

BAND_FREQS = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
GAIN_MIN, GAIN_MAX = -12.0, 12.0
BASS_FREQ, TREBLE_FREQ = 100.0, 8000.0

BUILTIN_PRESETS = {
    "Flat":       [0] * 10,
    "Pop":        [-1, 1, 3, 4, 3, 0, -1, -1, 1, 2],
    "Rock":       [4, 3, 2, 0, -1, -1, 1, 3, 4, 4],
    "Jazz":       [3, 2, 1, 2, -2, -2, 0, 1, 2, 3],
    "Vocal":      [-3, -2, -1, 1, 3, 4, 4, 2, 0, -1],
    "Bass Boost": [8, 7, 5, 3, 1, 0, 0, 0, 0, 0],
}


def _peaking(f, gain_db, fs, q=1.41):
    A = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * f / fs
    al = np.sin(w0) / (2 * q)
    c = np.cos(w0)
    b = [1 + al * A, -2 * c, 1 - al * A]
    a = [1 + al / A, -2 * c, 1 - al / A]
    return b, a


def _shelf(f, gain_db, fs, high):
    A = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * f / fs
    c = np.cos(w0)
    al = np.sin(w0) / 2 * np.sqrt(2.0)  # shelf slope S=1
    r = 2 * np.sqrt(A) * al
    if not high:
        b = [A * ((A + 1) - (A - 1) * c + r), 2 * A * ((A - 1) - (A + 1) * c), A * ((A + 1) - (A - 1) * c - r)]
        a = [(A + 1) + (A - 1) * c + r, -2 * ((A - 1) + (A + 1) * c), (A + 1) + (A - 1) * c - r]
    else:
        b = [A * ((A + 1) + (A - 1) * c + r), -2 * A * ((A - 1) + (A + 1) * c), A * ((A + 1) + (A - 1) * c - r)]
        a = [(A + 1) - (A - 1) * c + r, 2 * ((A - 1) - (A + 1) * c), (A + 1) - (A - 1) * c - r]
    return b, a


def _row(b, a):
    return [b[0] / a[0], b[1] / a[0], b[2] / a[0], 1.0, a[1] / a[0], a[2] / a[0]]


class Equalizer:
    def __init__(self, sample_rate: int = 44100, channels: int = 2):
        self.fs = sample_rate
        self.channels = channels
        self._lock = threading.Lock()
        self.reset()

    # ---- parameters -------------------------------------------------
    def reset(self):
        with self._lock:
            self.gains = [0.0] * len(BAND_FREQS)
            self.bass_db = 0.0
            self.treble_db = 0.0
            self.volume = 1.0
            self.balance = 0.0   # -1 (left only) .. +1 (right only)
            self.muted = False
            self._rebuild()

    def set_band(self, index: int, db: float):
        with self._lock:
            self.gains[index] = float(np.clip(db, GAIN_MIN, GAIN_MAX))
            self._rebuild()

    def set_gains(self, gains):
        if len(gains) != len(BAND_FREQS):
            raise ValueError(f"expected {len(BAND_FREQS)} gains")
        with self._lock:
            self.gains = [float(np.clip(g, GAIN_MIN, GAIN_MAX)) for g in gains]
            self._rebuild()

    def set_tone(self, bass_db=None, treble_db=None):
        with self._lock:
            if bass_db is not None:
                self.bass_db = float(np.clip(bass_db, GAIN_MIN, GAIN_MAX))
            if treble_db is not None:
                self.treble_db = float(np.clip(treble_db, GAIN_MIN, GAIN_MAX))
            self._rebuild()

    def set_volume(self, v: float):
        self.volume = float(np.clip(v, 0.0, 1.5))

    def set_balance(self, b: float):
        self.balance = float(np.clip(b, -1.0, 1.0))

    def set_muted(self, m: bool):
        self.muted = bool(m)

    def _rebuild(self):
        rows = [_row(*_peaking(f, g, self.fs)) for f, g in zip(BAND_FREQS, self.gains)]
        rows.append(_row(*_shelf(BASS_FREQ, self.bass_db, self.fs, high=False)))
        rows.append(_row(*_shelf(TREBLE_FREQ, self.treble_db, self.fs, high=True)))
        self._sos = np.array(rows, dtype=np.float64)
        if not hasattr(self, "_zi") or self._zi.shape[0] != len(rows):
            self._zi = np.zeros((len(rows), self.channels, 2))

    # ---- processing (called from the audio thread) ------------------
    def process(self, x: np.ndarray) -> np.ndarray:
        """x: float32 array (frames, channels). Returns a new float32 array."""
        if self.muted:
            return np.zeros_like(x, dtype=np.float32)
        with self._lock:
            sos, zi = self._sos, self._zi
            y, self._zi = sosfilt(sos, x.astype(np.float64), axis=0, zi=zi)
        if self.channels == 2:
            y[:, 0] *= min(1.0, 1.0 - self.balance)
            y[:, 1] *= min(1.0, 1.0 + self.balance)
        y *= self.volume
        return self._soft_limit(y).astype(np.float32)

    @staticmethod
    def _soft_limit(y, knee=0.8):
        ay = np.abs(y)
        m = ay > knee
        if m.any():
            y[m] = np.sign(y[m]) * (knee + (1 - knee) * np.tanh((ay[m] - knee) / (1 - knee)))
        return y
