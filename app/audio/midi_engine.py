"""MIDI/KAR parsing and a sample-accurate event sequencer driven by the audio callback."""
from __future__ import annotations
import math
from dataclasses import dataclass, field
import numpy as np
import mido
from app.utils.lyrics import LyricEvent


class MidiLoadError(RuntimeError):
    pass


@dataclass
class MidiSong:
    path: str
    events: list = field(default_factory=list)   # (seconds, mido.Message), time-sorted
    lyrics: list = field(default_factory=list)   # list[LyricEvent]
    duration: float = 0.0
    title: str = ""
    artist: str = ""
    channels: set = field(default_factory=set)
    programs: dict = field(default_factory=dict)  # channel -> first program number

    @property
    def has_lyrics(self) -> bool:
        return bool(self.lyrics)


def _clean_syllable(text: str):
    nl = False
    if text[:1] in ("/", "\\"):
        nl, text = True, text[1:]
    if text.endswith(("\r", "\n")):
        return text.rstrip("\r\n"), nl, True
    return text, nl, False


def load_midi(path: str) -> MidiSong:
    try:
        mid = mido.MidiFile(path, clip=True)
    except Exception as e:
        raise MidiLoadError(f"Cannot read MIDI file '{path}': {e}") from e
    if mid.type == 2:
        raise MidiLoadError("Type-2 (multi-sequence) MIDI files are not supported.")
    song = MidiSong(path=path)
    tpb, tempo, t = max(1, getattr(mid, "ticks_per_beat", 480)), 500000, 0.0
    lyric_meta, text_meta = [], []
    try:
        merged = mido.merge_tracks(mid.tracks)
    except Exception:
        merged = []
        for trk in getattr(mid, "tracks", []):
            merged.extend(trk)
    for msg in merged:
        try:
            msg_time = max(0, getattr(msg, "time", 0))
            t += mido.tick2second(msg_time, tpb, max(1, tempo))
            if msg.type == "set_tempo":
                tempo = max(1, getattr(msg, "tempo", 500000))
            elif msg.is_meta:
                # Only text-bearing meta messages have a ``text`` attribute.
                # Real-world MIDI files often contain other meta messages mixed
                # into the same stream; those must not abort playback.
                text = getattr(msg, "text", None)
                if msg.type == "lyrics" and isinstance(text, str):
                    lyric_meta.append((t, text))
                elif msg.type == "text" and isinstance(text, str):
                    text_meta.append((t, text))
                elif msg.type == "track_name" and isinstance(text, str) and not song.title and text.strip():
                    song.title = text.strip()
            else:
                song.events.append((t, msg))
                if hasattr(msg, "channel"):
                    song.channels.add(msg.channel % 16)
                if msg.type == "program_change" and hasattr(msg, "program"):
                    song.programs.setdefault(getattr(msg, "channel", 0) % 16, msg.program)
        except Exception:
            continue
    song.duration = t
    # KAR files: '@T' lines carry title, other '@' lines are headers; syllables are text events.
    headers = [tx[2:].strip() for _, tx in text_meta if tx.startswith("@T")]
    if headers:                      # KAR convention: 1st @T = title, 2nd = artist
        song.title = headers[0] or song.title
        if len(headers) > 1:
            song.artist = headers[1]
    source = lyric_meta or [(tt, tx) for tt, tx in text_meta if not tx.startswith("@")]
    pending_nl = False
    for tt, tx in source:
        if not tx:
            continue
        text, nl, ends_line = _clean_syllable(tx)
        song.lyrics.append(LyricEvent(tt, text, new_line=nl or pending_nl))
        pending_nl = ends_line
    return song


class MidiSource:
    """Audio source: renders the synth in sub-blocks split at event boundaries."""
    TAIL = 2.0  # seconds of release/reverb tail after the last event
    supports_speed = True

    def __init__(self, song: MidiSong, synth, sample_rate: int = 44100):
        self.song, self.synth, self.sr = song, synth, sample_rate
        self.speed = 1.0
        self.pos = 0.0        # song-time seconds
        self._i = 0

    @property
    def duration(self): return self.song.duration
    @property
    def position(self): return self.pos

    def set_speed(self, s: float):
        self.speed = max(0.25, min(2.0, s))   # tempo scaling only: pitch unchanged

    def seek(self, seconds: float):
        seconds = max(0.0, min(seconds, self.song.duration))
        try:
            self.synth.all_sounds_off()
        except Exception:
            pass
        self._i = 0
        ev = self.song.events
        while self._i < len(ev) and ev[self._i][0] <= seconds:
            m = ev[self._i][1]
            if getattr(m, "type", "") in ("program_change", "control_change", "pitchwheel"):
                try:
                    self.synth.send(m)       # restore channel state, skip notes
                except Exception:
                    pass
            self._i += 1
        self.pos = seconds

    def read(self, frames: int):
        out = np.zeros((frames, 2), dtype=np.float32)
        ev, done, dt = self.song.events, 0, self.speed / self.sr
        while done < frames:
            while self._i < len(ev) and ev[self._i][0] <= self.pos + 1e-9:
                try:
                    self.synth.send(ev[self._i][1])
                except Exception:
                    pass
                self._i += 1
            n = frames - done
            if self._i < len(ev):
                n = min(n, max(1, math.ceil((ev[self._i][0] - self.pos) / dt - 1e-6)))   # tolerance avoids float overshoot
            if n > 0:
                try:
                    out[done:done + n] = self.synth.render(n)
                except Exception:
                    pass
                self.pos += n * dt
                done += n
            else:
                break
            if self._i >= len(ev) and self.pos >= self.song.duration + self.TAIL:
                break
        return out, self.pos >= self.song.duration + self.TAIL
