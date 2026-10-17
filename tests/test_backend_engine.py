import sys, threading, types, numpy as np, pytest
from types import SimpleNamespace as NS
from app.audio.audio_decoder import FileSource, DecodeError, decode_file
from app.audio.audio_engine import AudioEngine


class FakeSynth:
    _next = 0
    def __init__(self, gain=0.2, samplerate=44100.0):
        self.calls, self.fonts = [], {}
    def sfload(self, path, update_midi_preset=0):
        if path.endswith("bad.sf2"): return -1
        FakeSynth._next += 1; self.fonts[FakeSynth._next] = path; return FakeSynth._next
    def sfunload(self, sfid, update_midi_preset=0): self.calls.append(("unload", sfid)); self.fonts.pop(sfid)
    def noteon(self, ch, k, v): self.calls.append(("on", ch, k, v))
    def noteoff(self, ch, k): self.calls.append(("off", ch, k))
    def cc(self, ch, c, v): self.calls.append(("cc", ch, c, v))
    def all_notes_off(self, ch): self.calls.append(("alloff", ch))
    def all_sounds_off(self, ch): pass
    def program_change(self, ch, p): self.calls.append(("pc", ch, p))
    def pitch_bend(self, ch, v): pass
    def channel_pressure(self, ch, v): pass
    def setting(self, k, v): self.calls.append(("setting", k, v))
    def get_samples(self, n): return np.full(n * 2, 16384, dtype=np.int16)
    def delete(self): self.calls.append(("delete",))




def backend():
    sys.modules["fluidsynth"] = types.SimpleNamespace(Synth=FakeSynth)
    from app.audio.fluidsynth_backend import FluidSynthBackend
    return FluidSynthBackend(44100, 0.5)


def test_soundfont_load_switch_and_failures(tmp_path):
    from app.audio.fluidsynth_backend import SynthError
    a, b, bad = (tmp_path / n for n in ("a.sf2", "b.sf2", "bad.sf2"))
    for f in (a, b, bad): f.write_bytes(b"x")
    be = backend()
    be.load_soundfont(str(a)); first = be._sfid
    be.load_soundfont(str(b))                                        # switch: old font unloaded, new active
    assert be.soundfont_path == str(b) and ("unload", first) in be._synth.calls
    with pytest.raises(SynthError): be.load_soundfont(str(bad))      # rejected by FluidSynth
    assert be.soundfont_path == str(b)                               # previous font still active
    with pytest.raises(SynthError): be.load_soundfont(str(tmp_path / "missing.sf2"))
    (tmp_path / "x.txt").write_bytes(b"x")
    with pytest.raises(SynthError): be.load_soundfont(str(tmp_path / "x.txt"))

def test_events_channel_mute_volume_and_render():
    be = backend()
    be.send(NS(type="note_on", channel=0, note=60, velocity=90)); be.send(NS(type="note_on", channel=0, note=60, velocity=0))
    assert ("on", 0, 60, 90) in be._synth.calls and ("off", 0, 60) in be._synth.calls
    be.set_channel_muted(1, True); n = len(be._synth.calls)
    be.send(NS(type="note_on", channel=1, note=50, velocity=90)); assert ("alloff", 1) in be._synth.calls
    assert not any(c[0] == "on" and c[1] == 1 for c in be._synth.calls)
    be.send(NS(type="control_change", channel=2, control=7, value=100)); be.set_channel_volume(2, 0.5)
    assert ("cc", 2, 7, 50) in be._synth.calls
    out = be.render(8); assert out.shape == (8, 2) and out.dtype == np.float32 and abs(out[0, 0] - 0.5) < 1e-6
    be.close(); assert ("delete",) in be._synth.calls

def test_missing_native_library_gives_clear_error():
    from app.audio.fluidsynth_backend import FluidSynthBackend, SynthError
    monkeypatch_target = sys.modules.pop("fluidsynth", None)
    sys.modules["fluidsynth"] = None            # makes `import fluidsynth` raise ImportError
    try:
        with pytest.raises(SynthError): FluidSynthBackend()
    finally:
        sys.modules.pop("fluidsynth", None)
        if monkeypatch_target: sys.modules["fluidsynth"] = monkeypatch_target

def _out(n=256): return np.zeros((n, 2), np.float32)

def test_engine_silence_when_paused_then_plays_and_finishes():
    eng = AudioEngine(44100); done = threading.Event(); eng.on_finished = done.set
    samples = np.full((300, 2), 0.1, np.float32); eng.load(FileSource(samples, 44100))
    o = _out(); eng._callback(o, 256, None, None); assert not o.any()            # not playing yet
    eng.play(); eng._callback(o, 256, None, None); assert o.any() and not done.is_set()
    eng._callback(o, 256, None, None); assert done.wait(2) and not eng.is_playing   # source exhausted
    assert abs(eng.position - 300 / 44100) < 1e-9

def test_engine_applies_eq_to_output():
    eng = AudioEngine(44100); t = np.arange(44100) / 44100
    s = (0.05 * np.sin(2 * np.pi * 1000 * t)).astype(np.float32); eng.load(FileSource(np.column_stack([s, s]), 44100))
    eng.eq.set_band(5, 12); eng.play(); o = _out(44100); eng._callback(o, 44100, None, None)
    assert np.sqrt(np.mean(o[22050:] ** 2)) > 3.5 * np.sqrt(np.mean(s[22050:] ** 2))

def test_engine_error_in_source_is_contained():
    class Boom:
        supports_speed = False; duration = 1; position = 0
        def read(self, n): raise RuntimeError("decoder died")
        def seek(self, s): pass
    eng = AudioEngine(44100); got = threading.Event(); eng.on_error = lambda m: got.set()
    eng.load(Boom()); eng.play(); o = np.ones((64, 2), np.float32); eng._callback(o, 64, None, None)
    assert not o.any() and got.wait(2) and not eng.is_playing

def test_engine_seek_stop_close_and_file_source():
    eng = AudioEngine(100); eng.load(FileSource(np.ones((500, 2), np.float32), 100))
    eng.seek(2.0); assert eng.position == 2.0; eng.stop(); assert eng.position == 0.0
    eng.seek(99); assert eng.position == 5.0
    eng.close(); assert eng.position == 0.0 and eng.duration == 0.0

def test_decoder_errors(tmp_path):
    with pytest.raises(DecodeError): decode_file(str(tmp_path / "nope.mp3"))
    f = tmp_path / "x.mp3"; f.write_bytes(b"junk")
    with pytest.raises(DecodeError): decode_file(str(f), ffmpeg="definitely-not-ffmpeg")
