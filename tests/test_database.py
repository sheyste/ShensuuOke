import os, sqlite3, pytest
from app.library.database import Database, DatabaseError, MIGRATIONS

def info(title, artist="", fmt="MID", fp=None, dur=60.0):
    return dict(filename=title + ".mid", title=title, artist=artist, format=fmt, duration=dur,
                size=1, mtime=1.0, fingerprint=fp, has_lyrics=0, error=None)

def test_fresh_db_is_at_latest_version():
    assert Database().version == len(MIGRATIONS)

def test_reopen_persists_and_does_not_remigrate(tmp_path):
    p = str(tmp_path / "k.db"); d = Database(p); d.upsert_song("/a.mid", info("A")); d.close()
    d2 = Database(p); assert d2.count_songs() == 1 and d2.version == len(MIGRATIONS)

def test_newer_schema_is_refused(tmp_path):
    p = str(tmp_path / "k.db"); Database(p).close()
    c = sqlite3.connect(p); c.execute("PRAGMA user_version=99"); c.commit(); c.close()
    with pytest.raises(DatabaseError): Database(p)

def test_upsert_search_sort():
    d = Database()
    d.upsert_song("/x/b.mid", info("Bravo", "Zed", dur=10)); d.upsert_song("/x/a.kar", info("alpha", "Yan", "KAR", dur=30))
    assert [s["title"] for s in d.list_songs(sort="title")] == ["alpha", "Bravo"]
    assert [s["title"] for s in d.list_songs(sort="duration", descending=True)] == ["alpha", "Bravo"]
    assert [s["title"] for s in d.list_songs(search="yan")] == ["alpha"]
    assert [s["title"] for s in d.list_songs(search="kar")] == ["alpha"]
    assert [s["title"] for s in d.list_songs(search="/x/b")] == ["Bravo"]
    _, created = d.upsert_song("/x/b.mid", info("Bravo2")); assert not created and d.count_songs() == 2

def test_favorites_recent_and_counts():
    d = Database(); a, _ = d.upsert_song("/a.mid", info("A")); b, _ = d.upsert_song("/b.mid", info("B"))
    d.set_favorite(a, True); assert [s["id"] for s in d.list_songs(favorites_only=True)] == [a]
    assert d.list_songs(recent_only=True) == []
    d.record_play(a); d.record_play(b); d.record_play(b)
    assert d.get_song(b)["play_count"] == 2
    assert [s["id"] for s in d.list_songs(recent_only=True)][0] == b
    d.clear_recently_played()
    assert d.list_songs(recent_only=True) == []
    assert d.get_song(b)["play_count"] == 2

def test_remove_song_keeps_file(tmp_path):
    f = tmp_path / "s.mid"; f.write_bytes(b"x"); d = Database()
    sid, _ = d.upsert_song(str(f), info("S")); d.remove_songs([sid])
    assert d.count_songs() == 0 and f.exists()

def test_duplicates():
    d = Database(); d.upsert_song("/a.mid", info("A", fp="F1")); d.upsert_song("/b.mid", info("B", fp="F1"))
    d.upsert_song("/c.mid", info("C", fp="F2")); g = d.find_duplicates()
    assert len(g) == 1 and {s["path"] for s in g[0]} == {"/a.mid", "/b.mid"}

def test_settings_roundtrip_and_presets_and_soundfonts():
    d = Database(); d.set_setting("k", {"a": [1, 2]}); assert d.get_setting("k") == {"a": [1, 2]}
    assert d.get_setting("nope", 5) == 5
    d.save_eq_preset("Mine", [1] * 10, 2, 3); assert d.list_eq_presets()["Mine"]["bass"] == 2
    d.rename_eq_preset("Mine", "Mine2"); assert "Mine2" in d.list_eq_presets()
    d.delete_eq_preset("Mine2"); assert d.list_eq_presets() == {}
    a = d.add_soundfont("/sf/a.sf2"); b = d.add_soundfont("/sf/b.sf2")
    assert d.default_soundfont()["id"] == a and d.add_soundfont("/sf/a.sf2") == a
    d.set_default_soundfont(b); assert d.default_soundfont()["id"] == b
    d.remove_soundfont(b); assert len(d.list_soundfonts()) == 1


def test_stable_song_numbering():
    d = Database()
    d.upsert_song("/c.mid", info("Cherry", "Artist C", dur=10))
    d.upsert_song("/a.mid", info("Apple", "Artist A", dur=30))
    d.upsert_song("/b.mid", info("Banana", "Artist B", dur=20))

    # All songs ordered by title have stable numbers 1, 2, 3
    all_songs = d.list_songs(sort="title")
    assert [(s["song_number"], s["title"]) for s in all_songs] == [(1, "Apple"), (2, "Banana"), (3, "Cherry")]

    # Searching for Cherry retains its original number (3), not reset to 1
    cherry_search = d.list_songs(search="Cherry")
    assert len(cherry_search) == 1
    assert cherry_search[0]["song_number"] == 3
    assert cherry_search[0]["title"] == "Cherry"

    # Searching for Banana retains its original number (2)
    banana_search = d.list_songs(search="Banana")
    assert len(banana_search) == 1
    assert banana_search[0]["song_number"] == 2

    # Sorting by duration descending does not renumber Cherry
    dur_sorted = d.list_songs(sort="duration", descending=True)
    assert [(s["song_number"], s["title"]) for s in dur_sorted] == [(1, "Apple"), (2, "Banana"), (3, "Cherry")]

    # get_song_by_number lookup
    assert d.get_song_by_number(1)["title"] == "Apple"
    assert d.get_song_by_number(2)["title"] == "Banana"
    assert d.get_song_by_number(3)["title"] == "Cherry"
    assert d.get_song_by_number(0) is None
    assert d.get_song_by_number(4) is None


def test_missing_songs_excluded_and_purged():
    d = Database()
    s1, _ = d.upsert_song("/a.mid", info("Song A"))
    s2, _ = d.upsert_song("/b.mid", info("Song B"))
    s3, _ = d.upsert_song("/c.mid", info("Song C"))

    assert len(d.list_songs()) == 3
    assert d.count_songs() == 3

    # Mark Song B as missing
    d.set_missing(s2, True)

    # By default, list_songs and count_songs exclude missing songs
    songs = d.list_songs()
    assert len(songs) == 2
    assert [s["title"] for s in songs] == ["Song A", "Song C"]
    assert d.count_songs() == 2

    # Include missing flag allows retrieving all
    assert len(d.list_songs(include_missing=True)) == 3
    assert d.count_songs(include_missing=True) == 3

    # Stable numbering excludes missing songs
    assert [(s["song_number"], s["title"]) for s in songs] == [(1, "Song A"), (2, "Song C")]
    assert d.get_song_by_number(2)["title"] == "Song C"

    # Purge permanently deletes missing songs
    purged = d.purge_missing_songs()
    assert purged == 1
    assert len(d.list_songs(include_missing=True)) == 2
    assert d.get_song(s2) is None


def test_get_song_number_and_get_song_includes_number():
    d = Database()
    s_c, _ = d.upsert_song("/c.mid", info("Cherry"))
    s_a, _ = d.upsert_song("/a.mid", info("Apple"))
    s_b, _ = d.upsert_song("/b.mid", info("Banana"))

    # Alphabetical order: Apple is 1, Banana is 2, Cherry is 3
    assert d.get_song_number(s_a) == 1
    assert d.get_song_number(s_b) == 2
    assert d.get_song_number(s_c) == 3

    # get_song also includes song_number
    assert d.get_song(s_a)["song_number"] == 1
    assert d.get_song(s_b)["song_number"] == 2
    assert d.get_song(s_c)["song_number"] == 3

