from __future__ import annotations

DEFAULTS = {
    "volume": 0.8, "shuffle": False, "repeat": "off", "tempo": 1.0,
    "soundfont": None, "synth_gain": 0.65, "reverb_level": 0.4, "chorus_level": 1.5,
    "bass_punch": 0.75, "drum_boost": True,
    "eq": {"gains": [0.0] * 10, "bass": 0.0, "treble": 0.0, "balance": 0.0, "bass_punch": 0.75, "preset": "Flat"},
    "audio_device": None, "sample_rate": 44100,
    "ffmpeg_path": "", "fluidsynth_dll_dir": "",
    "karaoke_font_size": 54, "karaoke_bg": "#000000", "karaoke_video_folder": "",
    "geometry": None, "library_sort": "title", "library_desc": False,
    "lyrics_highlight_color": "#5fb7ff",
    "lyrics_highlight_offset": 0.15,
}


class Settings:
    def __init__(self, db):
        self.db = db
        self._listeners: list = []

    def add_listener(self, callback):
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback):
        if callback in self._listeners:
            self._listeners.remove(callback)

    def get(self, key, default=None):
        if default is None:
            default = DEFAULTS.get(key)
        return self.db.get_setting(key, default)

    def set(self, key, value):
        self.db.set_setting(key, value)
        for cb in list(self._listeners):
            try:
                cb(key, value)
            except Exception:
                pass

