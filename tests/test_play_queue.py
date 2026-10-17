import random
from app.services.play_queue import PlayQueue

def songs(n): return [{"id": i} for i in range(n)]
def ids(q): return [i.song["id"] for i in q.items]

def test_linear_advance_and_end():
    q = PlayQueue(); q.set_items(songs(3))
    assert [q.advance().song["id"], q.advance().song["id"]] == [1, 2] and q.advance() is None

def test_repeat_all_and_one():
    q = PlayQueue(); q.set_items(songs(2), 1); q.repeat = "all"
    assert q.advance().song["id"] == 0
    q.repeat = "one"; assert q.advance(auto=True).song["id"] == 0 and q.advance(auto=False).song["id"] == 1

def test_shuffle_plays_everything_once_then_stops():
    q = PlayQueue(random.Random(1)); q.shuffle = True; q.set_items(songs(5))
    seen = [q.current().song["id"]]
    while (n := q.advance()): seen.append(n.song["id"])
    assert sorted(seen) == [0, 1, 2, 3, 4]
    q.repeat = "all"; assert q.advance() is not None

def test_add_remove_reorder_during_playback():
    q = PlayQueue(); q.set_items(songs(3)); cur = q.current()
    q.add([{"id": 9}], play_next=True); assert ids(q) == [0, 9, 1, 2]
    q.reorder([it.uid for it in reversed(q.items)]); assert ids(q) == [2, 1, 9, 0]
    assert q.current().uid == cur.uid                       # current follows its uid
    q.remove(q.items[0].uid); assert ids(q) == [1, 9, 0]

def test_removing_current_resumes_at_same_slot():
    q = PlayQueue(); q.set_items(songs(4), 1); q.remove(q.current().uid)
    assert q.current() is None and q.advance().song["id"] == 2

def test_previous_and_empty():
    q = PlayQueue(); assert q.advance() is None and q.previous() is None
    q.set_items(songs(3), 2); assert q.previous().song["id"] == 1 and q.previous().song["id"] == 0
    assert q.previous().song["id"] == 0

def up(q): return [i.song["id"] for i in q.upcoming()]

def test_upcoming_shrinks_as_songs_play():
    q = PlayQueue(); q.set_items(songs(4))
    assert up(q) == [1, 2, 3]
    q.advance(); assert up(q) == [2, 3]
    q.advance(); q.advance(); assert up(q) == []

def test_move_only_within_upcoming():
    q = PlayQueue(); q.set_items(songs(4))           # current = 0
    first = q.upcoming()[0].uid
    assert not q.move(first, -1)                      # cannot jump above the current song
    assert q.move(first, 1) and up(q) == [2, 1, 3]
    assert not q.move(q.current().uid, 1)

def test_move_next_puts_song_after_current():
    q = PlayQueue(); q.set_items(songs(4))
    q.move_next(q.items[3].uid)
    assert ids(q) == [0, 3, 1, 2] and up(q) == [3, 1, 2]
