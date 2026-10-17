from __future__ import annotations

DEFAULTS = {
    "volume": 0.8, "shuffle": False, "repeat": "off", "tempo": 1.0,
    "soundfont": None, "synth_gain": 0.5, "reverb_level": 0.4, "chorus_level": 1.5,
    "eq": {"gains": [0.0] * 10, "bass": 0.0, "treble": 0.0, "balance": 0.0, "preset": "Flat"},
    "audio_device": None, "sample_rate": 44100,
    "ffmpeg_path": "", "fluidsynth_dll_dir": "",
    "karaoke_font_size": 54, "karaoke_bg": "#000000", "karaoke_video_folder": "",
    "geometry": None, "library_sort": "title", "library_desc": False,
}


class Settings:
    def __init__(self, db):
        self.db = db

    def get(self, key):
        default = DEFAULTS.get(key)
        return self.db.get_setting(key, default)

    def set(self, key, value):
        self.db.set_setting(key, value)
