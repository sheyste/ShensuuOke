"""FluidSynth wrapper used as an *offline renderer*.

We never start FluidSynth's own audio driver. Instead we pull samples with get_samples()
so the output can flow through the shared Equalizer and the single output stream.
"""
from __future__ import annotations
import os
from pathlib import Path
import sys
import threading
import numpy as np


class SynthError(RuntimeError):
    pass


def _import_fluidsynth(dll_dir: str | None):
    if sys.platform == "win32":
        roots = []
        if getattr(sys, "_MEIPASS", None):
            roots.append(Path(sys._MEIPASS))
        roots.append(Path(__file__).resolve().parents[2])
        bundled = [root / "runtime" / "fluidsynth" for root in roots]
        dirs = [dll_dir, os.environ.get("FLUIDSYNTH_DLL_DIR"), *bundled, *roots]
        for d in filter(None, dirs):
            d = str(d)
            if os.path.isdir(d):
                os.add_dll_directory(d)                                   # for the DLL's own dependencies
                os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")   # ctypes.find_library uses PATH
    try:
        import fluidsynth  # pyfluidsynth
        return fluidsynth
    except Exception as e:  # ImportError or missing native lib
        raise SynthError(
            "FluidSynth could not be loaded. Add its DLLs to the bundled "
            "runtime\\fluidsynth folder, or set a DLL folder in Audio Settings. "
            f"Details: {e}") from e


class FluidSynthBackend:
    def __init__(self, sample_rate: int = 44100, gain: float = 0.65, dll_dir: str | None = None,
                 bass_punch: float = 0.75, drum_boost: bool = True):
        fs = _import_fluidsynth(dll_dir)
        self.sample_rate = sample_rate
        self._lock = threading.RLock()
        self._synth = fs.Synth(gain=gain, samplerate=float(sample_rate))
        try:
            self._synth.setting("synth.polyphony", 256)
        except Exception:
            pass
        self.gain = gain
        self.bass_punch = float(np.clip(bass_punch, 0.0, 1.0))
        self.drum_boost = bool(drum_boost)
        self.soundfont_path: str | None = None
        self._sfid: int | None = None
        self.channel_scale = [1.0] * 16     # per-channel volume multiplier (applied to CC7)
        self.channel_muted = [False] * 16
        self._last_cc7 = [100] * 16
        self._programs: dict[int, int] = {}

    # ---- soundfonts --------------------------------------------------
    def load_soundfont(self, path: str) -> None:
        """Load a SoundFont and make it active. On failure the previous one stays active."""
        if not os.path.isfile(path):
            raise SynthError(f"SoundFont not found: {path}")
        if not path.lower().endswith(".sf2"):
            raise SynthError("Only .sf2 SoundFonts are supported.")
        with self._lock:
            new_id = self._synth.sfload(path, update_midi_preset=1)
            if new_id is None or new_id < 0:
                raise SynthError(f"FluidSynth rejected the SoundFont (invalid or incompatible): {path}")
            old = self._sfid
            self._sfid, self.soundfont_path = new_id, path
            if old is not None:
                self._synth.sfunload(old, update_midi_preset=1)
            self.all_sounds_off()

    # ---- settings ----------------------------------------------------
    def set_bass_punch(self, punch: float, drum_boost: bool | None = None):
        with self._lock:
            self.bass_punch = float(np.clip(punch, 0.0, 1.0))
            if drum_boost is not None:
                self.drum_boost = bool(drum_boost)

    def set_gain(self, gain: float):
        with self._lock:
            self.gain = float(np.clip(gain, 0.0, 5.0))
            try:
                self._synth.setting("synth.gain", self.gain)
            except Exception:
                pass

    def set_reverb(self, room=0.2, damp=0.0, width=0.5, level=0.9):
        with self._lock:
            self._synth.set_reverb(room, damp, width, level)

    def set_chorus(self, nr=3, level=2.0, speed=0.3, depth=8.0, type_=0):
        with self._lock:
            self._synth.set_chorus(nr, level, speed, depth, type_)

    def set_channel_volume(self, ch: int, scale: float):
        with self._lock:
            if 0 <= ch < 16:
                self.channel_scale[ch] = float(np.clip(scale, 0.0, 1.0))
                self._apply_cc7(ch)

    def set_channel_muted(self, ch: int, muted: bool):
        with self._lock:
            if 0 <= ch < 16:
                self.channel_muted[ch] = muted
                if muted:
                    try:
                        self._synth.all_notes_off(ch)
                    except Exception:
                        pass

    def _apply_cc7(self, ch):
        if 0 <= ch < 16:
            try:
                self._synth.cc(ch, 7, int(np.clip(self._last_cc7[ch] * self.channel_scale[ch], 0, 127)))
            except Exception:
                pass

    # ---- events ------------------------------------------------------
    def send(self, msg) -> None:
        """Dispatch a mido channel message."""
        t = getattr(msg, "type", "")
        with self._lock:
            try:
                raw_ch = getattr(msg, "channel", 0)
                if not isinstance(raw_ch, int) or raw_ch < 0:
                    raw_ch = 0
                ch = raw_ch % 16

                if t == "note_on":
                    if self.channel_muted[ch]:
                        return
                    note = int(getattr(msg, "note", 60))
                    velocity = int(getattr(msg, "velocity", 64))
                    if 0 <= note <= 127:
                        if velocity <= 0:
                            self._synth.noteoff(ch, note)
                        else:
                            if self.drum_boost and self.bass_punch > 0.01:
                                if ch == 9:
                                    # Channel 10 (drums): 35 Acoustic Bass Drum, 36 Bass Drum 1 (Kick)
                                    if note in (35, 36):
                                        factor = 1.0 + 0.35 * self.bass_punch
                                        base_add = int(25 * self.bass_punch)
                                        velocity = min(127, max(1, int(velocity * factor + base_add)))
                                    elif note in (38, 40):  # Snare punch
                                        factor = 1.0 + 0.15 * self.bass_punch
                                        base_add = int(10 * self.bass_punch)
                                        velocity = min(127, max(1, int(velocity * factor + base_add)))
                                else:
                                    # Non-drum channel: check if bass instrument (GM 32..39)
                                    prog = self._programs.get(ch)
                                    if prog is not None and 32 <= prog <= 39:
                                        factor = 1.0 + 0.20 * self.bass_punch
                                        base_add = int(12 * self.bass_punch)
                                        velocity = min(127, max(1, int(velocity * factor + base_add)))
                            self._synth.noteon(ch, note, min(127, max(1, velocity)))
                elif t == "note_off":
                    note = int(getattr(msg, "note", 60))
                    if 0 <= note <= 127:
                        self._synth.noteoff(ch, note)
                elif t == "control_change":
                    ctrl = int(getattr(msg, "control", 0))
                    val = int(getattr(msg, "value", 0))
                    val = max(0, min(127, val))
                    if ctrl == 7:
                        self._last_cc7[ch] = val
                        self._apply_cc7(ch)
                    elif 0 <= ctrl <= 127:
                        self._synth.cc(ch, ctrl, val)
                elif t == "program_change":
                    prog = int(getattr(msg, "program", 0))
                    if 0 <= prog <= 127:
                        self._programs[ch] = prog
                        self._synth.program_change(ch, prog)
                elif t == "pitchwheel":
                    pitch = int(getattr(msg, "pitch", 0))
                    self._synth.pitch_bend(ch, pitch)
                elif t in ("aftertouch", "channel_pressure"):
                    val = int(getattr(msg, "value", 0))
                    val = max(0, min(127, val))
                    if hasattr(self._synth, "channel_pressure"):
                        self._synth.channel_pressure(ch, val)
                elif t == "polytouch":
                    note = int(getattr(msg, "note", 60))
                    val = int(getattr(msg, "value", 0))
                    if hasattr(self._synth, "key_pressure"):
                        self._synth.key_pressure(ch, note, val)
            except Exception:
                pass

    def all_sounds_off(self):
        with self._lock:
            for ch in range(16):
                try:
                    self._synth.all_sounds_off(ch)
                    self._synth.cc(ch, 121, 0)  # reset all controllers
                except Exception:
                    pass

    def render(self, frames: int) -> np.ndarray:
        """Return float32 stereo (frames, 2)."""
        if frames <= 0:
            return np.zeros((0, 2), dtype=np.float32)
        with self._lock:
            try:
                raw = self._synth.get_samples(frames)
            except Exception:
                return np.zeros((frames, 2), dtype=np.float32)
        try:
            arr = (np.asarray(raw, dtype=np.float32).reshape(-1, 2)) / 32768.0
            if arr.shape[0] != frames:
                res = np.zeros((frames, 2), dtype=np.float32)
                m = min(arr.shape[0], frames)
                res[:m] = arr[:m]
                return res
            return arr
        except Exception:
            return np.zeros((frames, 2), dtype=np.float32)

    def close(self):
        with self._lock:
            try:
                self._synth.delete()
            except Exception:
                pass
