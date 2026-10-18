import os, pytest
from app.library.database import Database
from app.library import scanner
from app.library.metadata import read_metadata, kind_of

def fake_reader(path):
    return dict(filename=os.path.basename(path), title=os.path.basename(path), artist="", format="MID",
                duration=1.0, has_lyrics=0, error="boom" if "bad" in path else None)

def make(tmp_path):
    (tmp_path / "sub").mkdir()
    for rel, data in {"a.mid": b"AAAA", "sub/b.kar": b"BBBB", "sub/copy.mid": b"AAAA",
                      "notes.txt": b"zzz", "bad.mp3": b"junk"}.items():
        (tmp_path / rel).write_bytes(data)

def test_recursive_scan_duplicates_errors(tmp_path):
    make(tmp_path); d = Database()
    r = scanner.scan_folder(d, str(tmp_path), reader=fake_reader)
    assert r.added == 4 and d.count_songs() == 4          # .txt ignored
    assert r.duplicate_groups == 1
    assert [p for p, _ in r.errors] == [str(tmp_path / "bad.mp3")]
    assert d.library_folders() == [str(tmp_path)]
    assert d.get_song_by_path(str(tmp_path / "bad.mp3"))["error"] == "boom"

def test_rescan_unchanged_new_missing_and_moved(tmp_path):
    make(tmp_path); d = Database(); scanner.scan_folder(d, str(tmp_path), reader=fake_reader)
    sid = d.get_song_by_path(str(tmp_path / "sub/b.kar"))["id"]; d.set_favorite(sid, True)
    (tmp_path / "new.mid").write_bytes(b"NEW")
    os.rename(tmp_path / "sub/b.kar", tmp_path / "moved.kar")      # same content, new path
    os.remove(tmp_path / "a.mid")
    r = scanner.rescan_library(d, reader=fake_reader)
    assert r.added == 1 and r.relocated == 1 and r.newly_missing == 1
    moved = d.get_song(sid); assert moved["path"].endswith("moved.kar") and moved["favorite"] == 1
    assert d.get_song_by_path(str(tmp_path / "a.mid"))["missing"] == 1
    r2 = scanner.rescan_library(d, reader=fake_reader); assert r2.added == 0 and r2.newly_missing == 0

def test_missing_file_recovers(tmp_path):
    make(tmp_path); d = Database(); scanner.scan_folder(d, str(tmp_path), reader=fake_reader)
    p = tmp_path / "a.mid"; data = p.read_bytes(); p.unlink(); scanner.refresh_missing(d)
    assert d.get_song_by_path(str(p))["missing"] == 1
    p.write_bytes(data); scanner.refresh_missing(d); assert d.get_song_by_path(str(p))["missing"] == 0

def test_import_files_and_unsupported(tmp_path):
    make(tmp_path); d = Database()
    r = scanner.import_files(d, [str(tmp_path / "a.mid"), str(tmp_path / "notes.txt")], reader=fake_reader)
    assert r.added == 1 and r.errors == [(str(tmp_path / "notes.txt"), "Unsupported file type.")]

def test_bad_folder_and_cancel(tmp_path):
    d = Database()
    with pytest.raises(scanner.ScanError): scanner.scan_folder(d, str(tmp_path / "nope"))
    make(tmp_path); r = scanner.scan_folder(d, str(tmp_path), reader=fake_reader, cancel=lambda: True)
    assert r.cancelled and d.count_songs() == 0

def test_metadata_fallbacks(tmp_path):
    p = tmp_path / "The Band - Great_Song.mp3"; p.write_bytes(b"not audio")
    m = read_metadata(str(p))
    assert m["title"] == "Great Song" and m["artist"] == "The Band" and m["format"] == "MP3"
    assert kind_of("x.KAR") == "midi" and kind_of("x.flac") == "audio" and kind_of("x.mkv") == "video" and kind_of("x.txt") is None
    try: import mutagen
    except ImportError: return
    assert m["error"]    # corrupt audio is reported, not hidden

def test_midi_metadata(tmp_path):
    pytest.importorskip("mido")
    from tests.test_midi_engine import make_kar
    p = tmp_path / "a.kar"; make_kar(str(p)); m = read_metadata(str(p))
    assert m["title"] == "My Song" and m["has_lyrics"] == 1 and m["duration"] > 0


def test_app_settings_view_scan_progress(tmp_path):
    from PySide6.QtWidgets import QApplication
    from app.services.settings import Settings
    from app.services.playback import PlaybackController
    from app.ui.settings_view import AppSettingsView
    app = QApplication.instance() or QApplication([])
    d = Database()
    s = Settings(d)
    c = PlaybackController(d, s)
    view = AppSettingsView(d, s, c)

    view.add_b.setEnabled(True)
    view._run("folder", [str(tmp_path)])
    view.w.progress.emit(1, str(tmp_path / "song.mp3"))
    assert "Scanning… 1: song.mp3" in view.info.text()
    assert not view.scan_b.isEnabled()

    class DummyResult:
        errors = []
        def summary(self):
            return "Added 1 song"

    view._scan_done(DummyResult())
    assert view.info.text() == "Added 1 song"
    assert view.scan_b.isEnabled()
    view.w.wait()


def test_app_settings_view_add_folder(tmp_path):
    from PySide6.QtWidgets import QApplication
    from app.services.settings import Settings
    from app.services.playback import PlaybackController
    from app.ui.settings_view import AppSettingsView
    app = QApplication.instance() or QApplication([])
    d = Database()
    s = Settings(d)
    c = PlaybackController(d, s)
    view = AppSettingsView(d, s, c)

    # Adding via folder input
    view.folder_input.setText(str(tmp_path))
    view._add_from_input()
    assert str(tmp_path) in d.library_folders()
    if view.w:
        view.w.wait()

    # Adding duplicate
    view._add_folder_path(str(tmp_path))
    assert "Folder already in library" in view.info.text()


def test_rescan_updates_song_libraries_and_removes_missing(tmp_path):
    make(tmp_path)
    d = Database()
    scanner.scan_folder(d, str(tmp_path), reader=fake_reader)
    initial_songs = d.list_songs()
    assert len(initial_songs) == 4
    assert d.count_songs() == 4

    # Delete one song from disk
    os.remove(tmp_path / "a.mid")

    # Rescan library
    r = scanner.rescan_library(d, reader=fake_reader)
    assert r.newly_missing == 1

    # Songs listed in song libraries immediately exclude the missing song
    updated_songs = d.list_songs()
    assert len(updated_songs) == 3
    assert d.count_songs() == 3
    assert not any(s["path"].endswith("a.mid") for s in updated_songs)

    # Purge permanently cleans them
    purged = d.purge_missing_songs()
    assert purged == 1
    assert len(d.list_songs(include_missing=True)) == 3

