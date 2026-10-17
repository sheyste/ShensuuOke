import pytest
from app.library.database import Database, DatabaseError
from tests.test_database import info

def setup():
    d = Database(); ids = [d.upsert_song(f"/{n}.mid", info(n))[0] for n in "abc"]
    return d, ids

def test_playlist_crud_and_order():
    d, ids = setup(); p = d.create_playlist("Fav")
    with pytest.raises(DatabaseError): d.create_playlist("Fav")
    with pytest.raises(DatabaseError): d.create_playlist("  ")
    d.playlist_add(p, ids); d.playlist_add(p, [ids[0]])
    assert [s["title"] for s in d.playlist_songs(p)] == ["a", "b", "c", "a"]
    assert d.list_playlists()[0]["count"] == 4
    d.rename_playlist(p, "Best"); assert d.list_playlists()[0]["name"] == "Best"

def test_move_and_remove_entries():
    d, ids = setup(); p = d.create_playlist("P"); d.playlist_add(p, ids)
    rows = d.playlist_songs(p); d.playlist_move(p, rows[2]["entry_id"], 0)
    assert [s["title"] for s in d.playlist_songs(p)] == ["c", "a", "b"]
    d.playlist_remove(p, [d.playlist_songs(p)[1]["entry_id"]])
    after = d.playlist_songs(p); assert [s["title"] for s in after] == ["c", "b"]
    assert [s["position"] for s in after] == [0, 1]

def test_deleting_playlist_or_song_cleans_entries():
    d, ids = setup(); p = d.create_playlist("P"); d.playlist_add(p, ids)
    d.remove_songs([ids[0]]); assert len(d.playlist_songs(p)) == 2
    d.delete_playlist(p); assert d.list_playlists() == [] and d.count_songs() == 2
