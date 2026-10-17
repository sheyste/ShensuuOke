"""Single output stream: source -> Equalizer -> device. GUI-independent."""
from __future__ import annotations
import threading
from typing import Callable
import numpy as np
from .equalizer import Equalizer


class AudioEngine:
    def __init__(self, sample_rate: int = 44100, device=None, block: int = 1024):
        self.sr, self.device, self.block = sample_rate, device, block
        self.eq = Equalizer(sample_rate)
        self.on_finished: Callable[[], None] | None = None
        self.on_error: Callable[[str], None] | None = None
        self._source = None
        self._playing = False
        self._finished_flag = False
        self._stream = None
        self._swap = threading.Lock()

    # ---- lifecycle ---------------------------------------------------
    def start(self):
        import sounddevice as sd
        self.stop_stream()
        try:
            self._stream = sd.OutputStream(samplerate=self.sr, channels=2, dtype="float32",
                                           blocksize=self.block, device=self.device,
                                           callback=self._callback, latency="low")
            self._stream.start()
        except Exception as e:
            self._stream = None
            raise RuntimeError(f"Cannot open audio output device: {e}") from e

    def stop_stream(self):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None

    def close(self):
        self._playing = False
        self.stop_stream()
        self._source = None

    # ---- transport ---------------------------------------------------
    def load(self, source):
        with self._swap:
            self._playing = False
            self._finished_flag = False
            self._source = source

    def play(self): self._playing = self._source is not None
    def pause(self): self._playing = False

    def stop(self):
        self._playing = False
        with self._swap:
            if self._source is not None:
                self._source.seek(0.0)
                self._finished_flag = False

    def seek(self, seconds: float):
        with self._swap:
            if self._source is not None:
                self._source.seek(seconds)
                self._finished_flag = False

    @property
    def is_playing(self): return self._playing
    @property
    def position(self): return self._source.position if self._source else 0.0
    @property
    def duration(self): return self._source.duration if self._source else 0.0

    def set_speed(self, s: float):
        if self._source is not None and getattr(self._source, "supports_speed", False):
            self._source.set_speed(s)

    # ---- audio thread ------------------------------------------------
    def _callback(self, outdata, frames, time_info, status):
        src = self._source
        if src is None or not self._playing:
            outdata.fill(0)
            return
        try:
            if not self._swap.acquire(blocking=False):
                outdata.fill(0)
                return
            try:
                data, done = src.read(frames)
            finally:
                self._swap.release()
            outdata[:] = self.eq.process(data)
        except Exception as e:  # never raise inside the callback
            outdata.fill(0)
            self._playing = False
            if self.on_error:
                threading.Thread(target=self.on_error, args=(str(e),), daemon=True).start()
            return
        if done and not self._finished_flag:
            self._finished_flag = True
            self._playing = False
            if self.on_finished:
                threading.Thread(target=self.on_finished, daemon=True).start()

    def test_tone(self, seconds: float = 1.0):
        """Play a 440 Hz tone through the full chain (EQ/volume included)."""
        from .audio_decoder import FileSource
        t = np.arange(int(self.sr * seconds)) / self.sr
        tone = (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        self.load(FileSource(np.column_stack([tone, tone]), self.sr))
        self._finished_flag = True      # a test tone must not trigger queue advance
        self.play()
