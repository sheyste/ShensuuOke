"""Generate a small test KAR file (C major scale with lyrics) to verify real playback.
Usage: python tools/make_sample_midi.py sample.kar
"""
import sys
import mido

out = sys.argv[1] if len(sys.argv) > 1 else "sample.kar"
m = mido.MidiFile(ticks_per_beat=480)
words = mido.MidiTrack(); music = mido.MidiTrack(); m.tracks += [words, music]
words.append(mido.MetaMessage("text", text="@KMIDI KARAOKE FILE", time=0))
words.append(mido.MetaMessage("text", text="@TSample Scale", time=0))
words.append(mido.MetaMessage("text", text="@TTest Artist", time=0))
music.append(mido.Message("program_change", program=0, time=0))
music.append(mido.Message("program_change", channel=1, program=33, time=0))
syll = ["Do ", "Re ", "Mi ", "Fa ", "/Sol ", "La ", "Ti ", "Do"]
for i, (note, s) in enumerate(zip([60, 62, 64, 65, 67, 69, 71, 72], syll)):
    words.append(mido.MetaMessage("text", text=s, time=0 if i == 0 else 480))
    music.append(mido.Message("note_on", note=note, velocity=90, time=0))
    music.append(mido.Message("note_off", note=note, velocity=0, time=420))
    music.append(mido.Message("note_on", channel=1, note=note - 24, velocity=80, time=60))
    music.append(mido.Message("note_off", channel=1, note=note - 24, velocity=0, time=0))
m.save(out)
print("wrote", out)
