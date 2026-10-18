from app.utils.lyrics import LyricEvent
from app.utils.lyrics import build_lines, locate

def ev(t, s, nl=False): return LyricEvent(t, s, nl)

def test_lines_and_locate():
    evs = [ev(1, "Hel"), ev(2, "lo "), ev(3, "World", True), ev(4, "!")]
    lines = build_lines(evs); assert [len(l) for l in lines] == [2, 2]
    assert locate(lines, 0.5) == (-1, -1) and locate(lines, 1.5) == (0, 0)
    assert locate(lines, 3.0) == (1, 0) and locate(lines, 99) == (1, 1)

def test_long_line_without_markers_is_wrapped():
    evs = [ev(i, "word ") for i in range(30)]; assert len(build_lines(evs)) > 2


def test_smooth_lyrics_progress():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFont, QFontMetrics
    from app.ui.lyrics_view import LyricsView

    app = QApplication.instance() or QApplication([])
    view = LyricsView(font_size=24)
    line = [ev(1.0, "Twinkle "), ev(2.0, "twinkle "), ev(3.0, "star")]
    view.set_lyrics(line)

    font = QFont("Arial", 24, QFont.Weight.Bold)
    metrics = QFontMetrics(font)
    p0 = view._calculate_line_progress(line, 0.5, metrics, 0)
    p1 = view._calculate_line_progress(line, 1.5, metrics, 0)
    p2 = view._calculate_line_progress(line, 2.5, metrics, 0)
    p3 = view._calculate_line_progress(line, 4.0, metrics, 0)

    assert p0 == 0.0
    assert 0.0 < p1 < p2 < p3


def test_lyrics_settings_and_color_propagation():
    from PySide6.QtWidgets import QApplication
    from app.library.database import Database
    from app.services.settings import Settings
    from app.services.playback import PlaybackController
    from app.ui.lyrics_settings_view import LyricsSettingsView
    from app.ui.lyrics_view import LyricsView

    app = QApplication.instance() or QApplication([])
    db = Database()
    settings = Settings(db)
    ctl = PlaybackController(db, settings)

    view = LyricsView(font_size=24, settings=settings)
    assert view.highlight_color == "#5fb7ff"

    settings_view = LyricsSettingsView(db, settings, ctl)
    settings_view._apply_color("#ff4081")

    assert settings.get("lyrics_highlight_color") == "#ff4081"
    assert view.highlight_color == "#ff4081"

    assert view.highlight_offset == 0.15
    settings_view._on_timing_changed(200)
    assert settings.get("lyrics_highlight_offset") == 0.2
    assert view.highlight_offset == 0.2
    settings_view._reset_timing()
    assert settings.get("lyrics_highlight_offset") == 0.15
    assert view.highlight_offset == 0.15
    assert settings_view.timing_slider.value() == 150

