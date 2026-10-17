import mido, numpy as np, pytest
from app.audio.midi_engine import load_midi, MidiSource, MidiLoadError

def make_kar(path):
    m = mido.MidiFile(ticks_per_beat=480); t = mido.MidiTrack(); m.tracks.append(t)
    t.append(mido.MetaMessage("text", text="@KMIDI KARAOKE FILE", time=0))
    t.append(mido.MetaMessage("text", text="@TMy Song", time=0))
    t.append(mido.Message("program_change", program=5, time=0))
    t.append(mido.Message("note_on", note=60, velocity=90, time=0))
    t.append(mido.MetaMessage("text", text="Hel", time=0))
    t.append(mido.MetaMessage("text", text="lo\r", time=480))
    t.append(mido.Message("note_off", note=60, time=0))
    t.append(mido.MetaMessage("text", text="/World", time=480))
    m.save(path)

class FakeSynth:
    def __init__(self): self.sent = []; self.cleared = 0
    def send(self, msg): self.sent.append(msg)
    def render(self, n): return np.zeros((n, 2), np.float32)
    def all_sounds_off(self): self.cleared += 1

def test_load_kar(tmp_path):
    p = tmp_path / "a.kar"; make_kar(str(p)); s = load_midi(str(p))
    assert s.title == "My Song" and s.has_lyrics
    assert [l.text for l in s.lyrics] == ["Hel", "lo", "World"]
    assert s.lyrics[2].new_line and abs(s.lyrics[1].time - 0.5) < 1e-6
    assert s.programs[0] == 5

def test_bad_file(tmp_path):
    p = tmp_path / "bad.mid"; p.write_bytes(b"nope")
    with pytest.raises(MidiLoadError): load_midi(str(p))

def test_sequencer_timing_and_speed(tmp_path):
    p = tmp_path / "a.mid"; make_kar(str(p)); s = load_midi(str(p))
    src = MidiSource(s, FakeSynth(), 44100)
    src.read(22050 - 1); assert not any(m.type == "note_off" for m in src.synth.sent)
    src.read(2); assert any(m.type == "note_off" for m in src.synth.sent)
    fast = MidiSource(s, FakeSynth(), 44100); fast.set_speed(2.0)
    fast.read(11025 + 2); assert any(m.type == "note_off" for m in fast.synth.sent)

def test_seek_and_finish(tmp_path):
    p = tmp_path / "a.mid"; make_kar(str(p)); s = load_midi(str(p))
    src = MidiSource(s, FakeSynth(), 44100); src.seek(0.75)
    assert src.synth.cleared == 1 and all(m.type != "note_on" for m in src.synth.sent)
    done = False
    for _ in range(200):
        _, done = src.read(1024)
        if done: break
    assert done
