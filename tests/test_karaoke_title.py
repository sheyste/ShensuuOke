import pytest
from app.library.database import Database
from app.services.settings import Settings
from app.services.playback import PlaybackController
from app.ui.karaoke_window import KaraokeWindow
from PySide6.QtWidgets import QApplication

def info(title, artist="", fmt="MID"):
    return dict(filename=title + ".mid", title=title, artist=artist, format=fmt,
                duration=60.0, size=1, mtime=1.0, fingerprint=None, has_lyrics=0, error=None)

def test_karaoke_song_number_before_title():
    app = QApplication.instance() or QApplication([])
    d = Database()
    s = Settings(d)
    ctl = PlaybackController(d, s)

    # Insert songs
    s_b, _ = d.upsert_song("/b.mid", info("Banana Song", "Artist B"))
    s_a, _ = d.upsert_song("/a.mid", info("Apple Song", "Artist A"))

    kw = KaraokeWindow(ctl, s)

    song_a = d.get_song(s_a)
    song_b = d.get_song(s_b)

    # In title order: Apple is 1, Banana is 2
    title_a = kw._format_song_title(song_a)
    title_b = kw._format_song_title(song_b)

    assert title_a == "#1 - Apple Song — Artist A"
    assert title_b == "#2 - Banana Song — Artist B"

    # When song has no song_number in dict yet, it resolves it automatically from DB
    raw_song = dict(id=s_a, title="Apple Song", filename="Apple Song.mid")
    assert kw._format_song_title(raw_song) == "#1 - Apple Song"
