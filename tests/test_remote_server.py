import json
import urllib.request
import pytest
from app.library.database import Database
from app.services.remote_server import RemoteServer
from tests.test_database import info


@pytest.fixture
def test_remote():
    db = Database()
    db.upsert_song("/a.mid", info("Apple", "Artist A"))
    db.upsert_song("/b.mid", info("Banana", "Artist B"))
    db.upsert_song("/c.mid", info("Cherry", "Artist C"))

    queued = []
    server = RemoteServer(db, lambda s: queued.append(s), host="127.0.0.1", port=0)
    server.start()
    port = server.port

    yield db, server, f"http://127.0.0.1:{port}", queued
    server.stop()


def test_remote_songs_api_stable_numbering(test_remote):
    db, server, base_url, queued = test_remote

    # All songs list - shuffled by default so not in sequential number order
    req = urllib.request.urlopen(f"{base_url}/api/songs")
    data = json.loads(req.read().decode("utf-8"))
    assert set(s["number"] for s in data["songs"]) == {1, 2, 3}
    assert [s["number"] for s in data["songs"]] != [1, 2, 3]

    # Explicitly un-shuffled with shuffle=0
    req0 = urllib.request.urlopen(f"{base_url}/api/songs?shuffle=0")
    data0 = json.loads(req0.read().decode("utf-8"))
    assert [s["number"] for s in data0["songs"]] == [1, 2, 3]
    assert [s["title"] for s in data0["songs"]] == ["Apple", "Banana", "Cherry"]

    # Search for Cherry: should retain number 3, not reset to 1
    req = urllib.request.urlopen(f"{base_url}/api/songs?q=Cherry")
    data = json.loads(req.read().decode("utf-8"))
    assert len(data["songs"]) == 1
    assert data["songs"][0]["title"] == "Cherry"
    assert data["songs"][0]["number"] == 3


def test_remote_button_design_swap(test_remote):
    db, server, base_url, queued = test_remote
    html = urllib.request.urlopen(f"{base_url}/").read().decode("utf-8")
    assert '<button class="alt" id="pause">Play</button><button id="next">Next</button>' in html
    q_html = urllib.request.urlopen(f"{base_url}/queue").read().decode("utf-8")
    assert '<button class="alt" id="pause">Play</button><button id="next">Next</button>' in q_html


def test_remote_song_info_preview(test_remote):
    db, server, base_url, queued = test_remote
    data = json.loads(urllib.request.urlopen(f"{base_url}/api/song-info/2").read())
    assert data == {"ok": True, "title": "Banana", "artist": "Artist B"}
    assert json.loads(urllib.request.urlopen(f"{base_url}/api/song-info/99").read()) == {"ok": False}
    assert queued == []                       # a lookup must never queue anything


def test_remote_queue_by_song_number(test_remote):
    db, server, base_url, queued = test_remote

    # Queue song #3 (Cherry)
    req = urllib.request.Request(f"{base_url}/api/song-number/3", data=b"", method="POST")
    resp = urllib.request.urlopen(req)
    data = json.loads(resp.read().decode("utf-8"))
    assert data["ok"] is True
    assert len(queued) == 1
    assert queued[0]["title"] == "Cherry"

    # Queue invalid song number 999
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        req = urllib.request.Request(f"{base_url}/api/song-number/999", data=b"", method="POST")
        urllib.request.urlopen(req)
    assert exc_info.value.code == 404


def test_remote_songs_page_fixed_search_bar(test_remote):
    db, server, base_url, queued = test_remote

    req = urllib.request.urlopen(f"{base_url}/songs")
    html = req.read().decode("utf-8")

    # Search bar should be enclosed in a sticky container and overflow-x:clip used so it stays fixed on scroll
    assert "overflow-x:clip" in html
    assert ".sticky{position:sticky;top:0" in html
    assert '<div class="sticky"><input class="search"' in html


def test_remote_queue_endpoints():
    actions = []
    snapshot = {"current": {"uid": 1, "title": "A", "artist": ""},
                "upcoming": [{"uid": 2, "title": "B", "artist": ""}]}
    server = RemoteServer(Database(), lambda s: None, host="127.0.0.1", port=0,
                          queue_snapshot_callback=lambda: snapshot,
                          queue_action_callback=lambda a, u: actions.append((a, u)))
    server.start()
    base = f"http://127.0.0.1:{server.port}"
    try:
        assert json.loads(urllib.request.urlopen(f"{base}/api/queue").read()) == snapshot
        for act in ("up", "down", "play", "remove"):
            req = urllib.request.Request(f"{base}/api/queue-action/{act}/2", data=b"", method="POST")
            assert json.loads(urllib.request.urlopen(req).read())["ok"] is True
        assert actions == [("up", 2), ("down", 2), ("play", 2), ("remove", 2)]
        with pytest.raises(urllib.error.HTTPError):
            req = urllib.request.Request(f"{base}/api/queue-action/explode/2", data=b"", method="POST")
            urllib.request.urlopen(req)
        html = urllib.request.urlopen(f"{base}/queue").read().decode("utf-8")
        assert 'id="queueNav" href="/queue"' in html
    finally:
        server.stop()


def test_remote_confirmation_modal(test_remote):
    db, server, base_url, queued = test_remote
    # Check page includes modal markup and methods
    html = urllib.request.urlopen(base_url).read().decode("utf-8")
    assert ".modal-overlay" in html
    assert "showModal" in html
    assert "Added to Queue!" in html

    # Queue by song number returns title and artist
    req = urllib.request.Request(f"{base_url}/api/song-number/2", data=b"", method="POST")
    resp = json.loads(urllib.request.urlopen(req).read().decode("utf-8"))
    assert resp["ok"] is True
    assert resp["title"] == "Banana"
    assert resp["artist"] == "Artist B"

    # Queue by id returns title and artist
    song_id = queued[-1]["id"]
    req = urllib.request.Request(f"{base_url}/api/queue/{song_id}", data=b"", method="POST")
    resp = json.loads(urllib.request.urlopen(req).read().decode("utf-8"))
    assert resp["ok"] is True
    assert resp["title"] == "Banana"

    # Check showConfirm and confirmations for song queue, play, remove
    assert "showConfirm" in html
    assert "Add to Queue?" in html
    assert "Play this song now?" in html
    assert "Remove from queue?" in html


def test_remote_reshuffle_with_seeds(test_remote):
    db, server, base_url, _ = test_remote
    # Add more songs to clearly distinguish permutations
    for i in range(4, 25):
        db.upsert_song(f"/{i}.mid", info(f"Song {i:02d}", f"Artist {i}"))

    req1 = urllib.request.urlopen(f"{base_url}/api/songs?seed=12345&limit=25")
    data1 = json.loads(req1.read().decode("utf-8"))["songs"]
    nums1 = [s["number"] for s in data1]

    req2 = urllib.request.urlopen(f"{base_url}/api/songs?seed=987654&limit=25")
    data2 = json.loads(req2.read().decode("utf-8"))["songs"]
    nums2 = [s["number"] for s in data2]

    assert len(nums1) == 24
    assert len(nums2) == 24
    assert set(nums1) == set(range(1, 25))
    assert set(nums2) == set(range(1, 25))
    assert nums1 != nums2  # different seeds produce different shuffled orders!


def test_remote_logo_route(test_remote):
    db, server, base_url, _ = test_remote
    req = urllib.request.urlopen(f"{base_url}/logo.png")
    assert req.status == 200
    assert req.headers.get("Content-Type") == "image/png"
    assert len(req.read()) > 0

