import pytest
from PySide6.QtWidgets import QApplication
from app.library.database import Database
from app.services.settings import Settings
from app.ui.song_library import LibraryView, SongTableModel


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


class DummyCtl:
    def __init__(self):
        from PySide6.QtCore import QObject, Signal
        class _Signals(QObject):
            library_changed = Signal()
            song_changed = Signal(object)
        self._s = _Signals()
        self.library_changed = self._s.library_changed
        self.song_changed = self._s.song_changed
        self.queue = None


def make_info(title, artist=""):
    return dict(filename=title + ".mp3", title=title, artist=artist, format="MP3", duration=180.0,
                size=1024, mtime=1.0, fingerprint=None, has_lyrics=0, error=None)


def test_lazy_loading_and_fetch_more(qapp, tmp_path):
    db_file = tmp_path / "test.db"
    db = Database(str(db_file))

    # Insert 250 songs
    for i in range(1, 251):
        artist = "Queen" if i % 2 == 0 else "Beatles"
        db.upsert_song(f"/music/song_{i:03d}.mp3", make_info(f"Track {i:03d}", artist))

    assert db.count_songs() == 250
    assert db.count_songs(search="Queen") == 125

    settings = Settings(db)
    ctl = DummyCtl()

    view = LibraryView(db, settings, ctl, mode="library")
    view.resize(800, 600)

    # Initially before reload / show
    assert len(view.model.rows) == 0 or len(view.model.rows) == 100
    view.reload()

    # Initial page should only load PAGE_SIZE (100) items
    assert len(view.model.rows) == 100
    assert view.model.canFetchMore() is True
    assert "Showing 100 of 250 songs" in view.status.text()

    # Load next page
    view.load_more()
    assert len(view.model.rows) == 200
    assert view.model.canFetchMore() is True
    assert "Showing 200 of 250 songs" in view.status.text()

    # Load third page (remaining 50)
    view.load_more()
    assert len(view.model.rows) == 250
    assert view.model.canFetchMore() is False
    assert view.status.text() == "250 songs"

    # Search filter with lazy load
    view.search.setText("Queen")
    view.reload()
    assert len(view.model.rows) == 100
    assert view.model.canFetchMore() is True
    assert "Showing 100 of 125 songs" in view.status.text()

    view.load_more()
    assert len(view.model.rows) == 125
    assert view.model.canFetchMore() is False
    assert view.status.text() == "125 songs"
