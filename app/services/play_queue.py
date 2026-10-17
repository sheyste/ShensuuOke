"""Playback queue with shuffle / repeat. Pure Python (no Qt) so it is fully testable."""
from __future__ import annotations
import itertools
import random
from dataclasses import dataclass


@dataclass
class QueueItem:
    uid: int
    song: dict


class PlayQueue:
    def __init__(self, rng=None):
        self.items: list[QueueItem] = []
        self.current_uid: int | None = None
        self.shuffle = False
        self.repeat = "off"           # off | all | one
        self._uids = itertools.count(1)
        self._played: set[int] = set()
        self._hint: int | None = None  # index to resume from if the current item was removed
        self._rng = rng or random.Random()

    def _index(self, uid):
        for i, it in enumerate(self.items):
            if it.uid == uid:
                return i
        return -1

    def current(self):
        i = self._index(self.current_uid)
        return self.items[i] if i >= 0 else None

    def add(self, songs, play_next=False):
        new = [QueueItem(next(self._uids), s) for s in songs]
        if play_next and self.current_uid is not None and self._index(self.current_uid) >= 0:
            at = self._index(self.current_uid) + 1
            self.items[at:at] = new
        else:
            self.items.extend(new)
        return new

    def set_items(self, songs, start_index=0):
        self.items = [QueueItem(next(self._uids), s) for s in songs]
        self._played.clear()
        self._hint = None
        self.current_uid = None
        if self.items:
            self.jump(self.items[max(0, min(start_index, len(self.items) - 1))].uid)
        return self.current()

    def jump(self, uid):
        if self._index(uid) < 0:
            return None
        self.current_uid = uid
        self._played.add(uid)
        self._hint = None
        return self.current()

    def remove(self, uid):
        i = self._index(uid)
        if i < 0:
            return
        del self.items[i]
        self._played.discard(uid)
        if uid == self.current_uid:
            self.current_uid = None
            self._hint = i
        elif self._hint is not None and i < self._hint:
            self._hint -= 1

    def clear(self):
        self.items.clear(); self._played.clear(); self.current_uid = None; self._hint = None

    def upcoming(self):
        """Items still waiting to be played (excludes the current and already-played ones)."""
        if self.shuffle:
            return [it for it in self.items if it.uid not in self._played and it.uid != self.current_uid]
        i = self._index(self.current_uid)
        if i >= 0:
            return self.items[i + 1:]
        start = self._hint if self._hint is not None else (0 if not self._played else len(self.items))
        return self.items[start:]

    def move(self, uid, delta):
        """Swap an upcoming item with its upcoming neighbour (delta -1 = up, +1 = down)."""
        waiting = [it.uid for it in self.upcoming()]
        if uid not in waiting:
            return False
        j = waiting.index(uid) + delta
        if not 0 <= j < len(waiting):
            return False
        a, b = self._index(uid), self._index(waiting[j])
        self.items[a], self.items[b] = self.items[b], self.items[a]
        return True

    def move_next(self, uid):
        """Move an item so it plays right after the current song."""
        i = self._index(uid)
        if i < 0 or uid == self.current_uid:
            return False
        item = self.items.pop(i)
        if self._hint is not None and i < self._hint:
            self._hint -= 1
        cur = self._index(self.current_uid)
        if cur >= 0:
            at = cur + 1
        else:
            waiting = self.upcoming()
            at = self._index(waiting[0].uid) if waiting else len(self.items)
        self.items.insert(at, item)
        self._played.discard(uid)
        if self.current_uid is None and self._hint is not None:
            self._hint = at
        return True

    def reorder(self, uids):
        by_uid = {it.uid: it for it in self.items}
        if set(uids) != set(by_uid) or len(uids) != len(by_uid):
            raise ValueError("reorder() needs exactly the current queue uids")
        self.items = [by_uid[u] for u in uids]

    def advance(self, auto=False):
        """Next item to play, or None at the end. auto=True means a song finished by itself."""
        if not self.items:
            return None
        if auto and self.repeat == "one" and self.current():
            return self.current()
        if self.current_uid is None:           # current was removed (or nothing played yet)
            i = self._hint if self._hint is not None else 0
            if i < len(self.items) and not self.shuffle:
                return self.jump(self.items[i].uid)
        if self.shuffle:
            pool = [it for it in self.items if it.uid not in self._played]
            if not pool:
                if self.repeat != "all":
                    return None
                self._played = {self.current_uid} if self.current_uid else set()
                pool = [it for it in self.items if it.uid not in self._played] or list(self.items)
            return self.jump(self._rng.choice(pool).uid)
        i = self._index(self.current_uid)
        nxt = i + 1
        if nxt >= len(self.items):
            if self.repeat != "all":
                return None
            nxt = 0
        return self.jump(self.items[nxt].uid)

    def previous(self):
        i = self._index(self.current_uid)
        if i <= 0:
            return self.jump(self.items[0].uid) if self.items else None
        return self.jump(self.items[i - 1].uid)
