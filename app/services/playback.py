"""Qt-facing playback controller: ties queue, engine, synth, database and settings together."""
from __future__ import annotations
import os
from PySide6.QtCore import QObject, QThread, QTimer, Signal

from app.audio.audio_engine import AudioEngine
from app.audio.audio_decoder import FileSource, decode_file
from app.audio.fluidsynth_backend import FluidSynthBackend, SynthError
from app.audio.midi_engine import MidiSource, MidiLoadError, load_midi
from app.library.metadata import kind_of
from app.services.play_queue import PlayQueue


class _DecodeWorker(QThread):
    done = Signal(int, object, str)    # token, FileSource | None, error

    def __init__(self, token, path, sr, ffmpeg, parent=None):
        super().__init__(parent)
        self.token, self.path, self.sr, self.ffmpeg = token, path, sr, ffmpeg

    def run(self):
        try:
            self.done.emit(self.token, FileSource(decode_file(self.path, self.sr, self.ffmpeg or None), self.sr), "")
        except Exception as e:
            self.done.emit(self.token, None, str(e))


class PlaybackController(QObject):
    song_changed = Signal(object)          # song dict | None
    state_changed = Signal(str)            # playing | paused | stopped | loading
    position_changed = Signal(float, float)
    lyrics_changed = Signal(object, str)   # list[LyricEvent], message when empty
    queue_changed = Signal()
    library_changed = Signal()
    error = Signal(str)
    _finished = Signal()
    _engine_error = Signal(str)

    def __init__(self, db, settings, parent=None):
        super().__init__(parent)
        self.db, self.settings = db, settings
        self.engine = AudioEngine(settings.get("sample_rate"), device=settings.get("audio_device"))
        self.engine.on_finished = self._finished.emit      # emitted from audio-side thread -> queued
        self.engine.on_error = self._engine_error.emit
        self._finished.connect(self._on_finished)
        self._engine_error.connect(self._on_engine_error)
        self.queue = PlayQueue()
        self.queue.shuffle = bool(settings.get("shuffle"))
        self.queue.repeat = settings.get("repeat")
        self.synth: FluidSynthBackend | None = None
        self.current: dict | None = None
        self.current_lyrics = []
        self.current_lyrics_message = "Nothing playing."
        self.state = "stopped"
        self.tempo = float(settings.get("tempo"))
        self._token = 0
        self._worker = None
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._tick)
        eq = settings.get("eq")
        self.engine.eq.set_gains(eq["gains"])
        self.engine.eq.set_tone(eq["bass"], eq["treble"])
        self.engine.eq.set_balance(eq["balance"])
        self.engine.eq.set_volume(float(settings.get("volume")))

    # ---- audio device / synth ---------------------------------------
    def start_audio(self) -> bool:
        try:
            self.engine.start()
            return True
        except Exception as e:
            self.error.emit(str(e))
            return False

    def set_output_device(self, device):
        self.engine.device = device
        self.settings.set("audio_device", device)
        return self.start_audio()

    def device_name(self) -> str:
        try:
            import sounddevice as sd
            idx = self.engine.device if self.engine.device is not None else sd.default.device[1]
            return sd.query_devices(idx)["name"]
        except Exception:
            return "Unknown"

    def ensure_synth(self) -> FluidSynthBackend:
        if self.synth is None:
            self.synth = FluidSynthBackend(self.engine.sr, self.settings.get("synth_gain"),
                                           self.settings.get("fluidsynth_dll_dir") or None)
            self.apply_synth_fx()
        if self.synth.soundfont_path is None:
            path = self.settings.get("soundfont")
            if not (path and os.path.isfile(path)):
                d = self.db.default_soundfont()
                path = d["path"] if d else None
            if not (path and os.path.isfile(path)):
                try:
                    from app.services.runtime_bootstrap import _soundfont_path
                    from pathlib import Path
                    sp = _soundfont_path(Path("."))
                    if sp and sp.is_file():
                        path = str(sp)
                except Exception:
                    pass
            if path and os.path.isfile(path):
                try:
                    self.set_soundfont(path)
                except SynthError as e:
                    self.error.emit(str(e))
        if self.synth.soundfont_path is None:
            raise SynthError("No SoundFont is loaded. Open the SoundFont Manager, add an .sf2 file and press 'Use selected'.")
        return self.synth

    def set_soundfont(self, path: str):
        """Switch the SoundFont used by the synth (takes effect immediately, even mid-song)."""
        synth = self.synth or self.ensure_synth_no_font()
        synth.load_soundfont(path)
        self.settings.set("soundfont", path)

    def ensure_synth_no_font(self):
        if self.synth is None:
            self.synth = FluidSynthBackend(self.engine.sr, self.settings.get("synth_gain"),
                                           self.settings.get("fluidsynth_dll_dir") or None)
            self.apply_synth_fx()
        return self.synth

    def apply_synth_fx(self):
        if self.synth is None:
            return
        try:
            self.synth.set_gain(self.settings.get("synth_gain"))
            self.synth.set_reverb(level=self.settings.get("reverb_level"))
            self.synth.set_chorus(level=self.settings.get("chorus_level"))
        except Exception as e:
            self.error.emit(f"Could not apply reverb/chorus (pyfluidsynth too old?): {e}")

    # ---- transport ---------------------------------------------------
    def _set_state(self, s):
        self.state = s
        self.state_changed.emit(s)

    def _discard_failed_current(self):
        """Prevent a broken item from being retried by the transport queue."""
        if self.queue.current_uid is not None:
            self.queue.remove(self.queue.current_uid)
        self.current = None
        self.queue_changed.emit()

    def play_song(self, song: dict) -> bool:
        self._token += 1
        self.engine.pause()
        path = song["path"]
        if not os.path.isfile(path):
            self.db.set_missing(song["id"], True)
            self._discard_failed_current()
            self.library_changed.emit()
            self.error.emit(f"File is missing and was skipped:\n{path}")
            return False
        kind = kind_of(path)
        try:
            if kind == "midi":
                synth = self.ensure_synth()
                try:
                    synth.all_sounds_off()
                except Exception:
                    pass
                ms = load_midi(path)
                # Folder imports intentionally defer MIDI parsing. Cache the
                # details discovered during playback for the library view.
                st = os.stat(path)
                metadata = {
                    "filename": os.path.basename(path),
                    "title": ms.title or song.get("title") or os.path.splitext(os.path.basename(path))[0],
                    "artist": ms.artist or song.get("artist") or "",
                    "format": os.path.splitext(path)[1].lstrip(".").upper(),
                    "duration": ms.duration,
                    "size": st.st_size,
                    "mtime": st.st_mtime,
                    "fingerprint": song.get("fingerprint"),
                    "has_lyrics": 1 if ms.has_lyrics else 0,
                    "error": None,
                }
                self.db.upsert_song(path, metadata)
                song.update(metadata)
                msg = "" if ms.has_lyrics else "This MIDI file contains no lyrics."
                self._start(song, MidiSource(ms, synth, self.engine.sr), ms.lyrics, msg)
                return True
            if kind in ("audio", "video"):
                self.current = song
                self.song_changed.emit(song)
                self.lyrics_changed.emit([], "Lyrics are only available for MIDI/KAR files.")
                self._set_state("loading")
                self._worker = _DecodeWorker(self._token, path, self.engine.sr,
                                             self.settings.get("ffmpeg_path"), self)
                self._worker.done.connect(self._on_decoded)
                self._worker.start()
                return True
            self._discard_failed_current()
            self.error.emit(f"Unsupported file type: {path}")
        except (SynthError, MidiLoadError) as e:
            self._discard_failed_current()
            self.error.emit(str(e))
        except Exception as e:
            self._discard_failed_current()
            self.error.emit(f"Playback failed: {e}")
        self._set_state("stopped")
        return False

    def _on_decoded(self, token, source, err):
        if token != self._token:
            return                        # user already moved on
        if source is None:
            self._discard_failed_current()
            self.error.emit(err)
            self._set_state("stopped")
            return
        self._start(self.current, source, [], "Lyrics are only available for MIDI/KAR files.", announce=False)

    def _start(self, song, source, lyrics, msg, announce=True):
        self.engine.load(source)
        self.engine.set_speed(self.tempo)
        self.current = song
        self.current_lyrics = lyrics or []
        self.current_lyrics_message = msg
        self.engine.play()
        self.db.record_play(song["id"])
        if announce:
            self.song_changed.emit(song)
            self.lyrics_changed.emit(lyrics, msg)
        self._set_state("playing")
        self._timer.start()
        self.library_changed.emit()
        self.queue_changed.emit()

    def toggle_play_pause(self):
        if self.state == "playing":
            self.engine.pause(); self._set_state("paused")
        elif self.state == "paused":
            self.engine.play(); self._set_state("playing")
        elif self.state == "stopped":
            item = self.queue.current() or self.queue.advance()
            if item:
                self.play_song(item.song)
                self.queue_changed.emit()

    def stop(self):
        self._token += 1
        self.engine.stop()
        self._timer.stop()
        self._set_state("stopped")
        self.position_changed.emit(0.0, self.engine.duration)

    def seek(self, seconds):
        self.engine.seek(seconds)
        self._tick()

    def next(self):
        self._advance(auto=False)

    def previous(self):
        if self.engine.position > 3.0 and self.state in ("playing", "paused"):
            self.seek(0.0); return
        item = self.queue.previous()
        if item:
            self.play_song(item.song); self.queue_changed.emit()

    def _advance(self, auto):
        for _ in range(max(1, len(self.queue.items))):      # skip missing/broken files
            item = self.queue.advance(auto=auto)
            if item is None:
                if auto:
                    self.stop()
                return
            if self.play_song(item.song):
                self.queue_changed.emit()
                return

    def _on_finished(self):
        if self.queue.repeat == "one" and self.queue.current():
            self.engine.seek(0.0); self.engine.play(); self._set_state("playing")
            self.db.record_play(self.current["id"]); self.library_changed.emit()
            return
        self._advance(auto=True)

    def _on_engine_error(self, msg):
        self._set_state("paused")
        self.error.emit(f"Audio engine error: {msg}")

    def _tick(self):
        self.position_changed.emit(self.engine.position, self.engine.duration)

    # ---- queue / settings helpers -----------------------------------
    def play_songs(self, songs, start_index=0):
        self.queue.set_items(songs, start_index)
        item = self.queue.current()
        if item and not self.play_song(item.song):
            self._advance(auto=True)
        self.queue_changed.emit()

    def play_uid(self, uid):
        item = self.queue.jump(uid)
        if item:
            self.play_song(item.song); self.queue_changed.emit()

    def enqueue(self, songs, play_next=False):
        added = self.queue.add(songs, play_next)
        if added and self.state == "stopped":
            item = self.queue.jump(added[0].uid)
            if item:
                self.play_song(item.song)
        self.queue_changed.emit()

    def reorder_queue(self, uids):          # silent: the view already shows this order
        self.queue.reorder(uids)

    def remove_from_queue(self, uid):
        self.queue.remove(uid)
        self.queue_changed.emit()

    def move_in_queue(self, uid, delta):
        if self.queue.move(uid, delta):
            self.queue_changed.emit()

    def play_next_in_queue(self, uid):
        if self.queue.move_next(uid):
            self.queue_changed.emit()

    def play_now(self, uid):
        """Play a queued song immediately without skipping the songs before it."""
        if uid != self.queue.current_uid:
            self.queue.move_next(uid)
        self.play_uid(uid)

    def queue_action(self, action, uid):
        if action == "play":
            self.play_now(uid)
        elif action == "remove":
            self.remove_from_queue(uid)
        elif action == "up":
            self.move_in_queue(uid, -1)
        elif action == "down":
            self.move_in_queue(uid, 1)
        elif action == "next":
            self.play_next_in_queue(uid)

    def clear_queue(self):
        self.queue.clear(); self.queue_changed.emit()

    def toggle_favorite(self, song):
        self.db.set_favorite(song["id"], not song["favorite"])
        song["favorite"] = int(not song["favorite"])
        self.library_changed.emit()

    def set_volume(self, v):
        self.engine.eq.set_volume(v); self.settings.set("volume", v)

    def set_tempo(self, t):
        self.tempo = t; self.engine.set_speed(t); self.settings.set("tempo", t)

    def set_shuffle(self, on):
        self.queue.shuffle = on; self.settings.set("shuffle", on)

    def set_repeat(self, mode):
        self.queue.repeat = mode; self.settings.set("repeat", mode)

    def supports_tempo(self):
        return bool(getattr(self.engine._source, "supports_speed", False))

    def shutdown(self):
        self._token += 1
        self._timer.stop()
        self.engine.close()
        if self._worker and self._worker.isRunning():
            self._worker.wait(3000)
        if self.synth:
            self.synth.close()
