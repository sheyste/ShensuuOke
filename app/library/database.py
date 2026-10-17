"""SQLite persistence with versioned migrations (PRAGMA user_version)."""
from __future__ import annotations
import json
import os
import sqlite3
import threading
import time


class DatabaseError(RuntimeError):
    pass


# Append new scripts to the END of this list; never edit an released one.
MIGRATIONS = [
    """
    CREATE TABLE songs (
        id INTEGER PRIMARY KEY,
        path TEXT NOT NULL UNIQUE,
        filename TEXT NOT NULL,
        title TEXT, artist TEXT, format TEXT,
        duration REAL, size INTEGER, mtime REAL, fingerprint TEXT,
        has_lyrics INTEGER NOT NULL DEFAULT 0,
        favorite INTEGER NOT NULL DEFAULT 0,
        play_count INTEGER NOT NULL DEFAULT 0,
        last_played REAL,
        added_at REAL NOT NULL,
        missing INTEGER NOT NULL DEFAULT 0,
        error TEXT
    );
    CREATE INDEX idx_songs_fp ON songs(fingerprint);
    CREATE TABLE playlists (
        id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, created_at REAL NOT NULL);
    CREATE TABLE playlist_songs (
        id INTEGER PRIMARY KEY,
        playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
        song_id INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
        position INTEGER NOT NULL);
    CREATE INDEX idx_pls ON playlist_songs(playlist_id, position);
    CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE eq_presets (
        name TEXT PRIMARY KEY, gains TEXT NOT NULL, bass REAL NOT NULL DEFAULT 0, treble REAL NOT NULL DEFAULT 0);
    CREATE TABLE soundfonts (
        id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE, name TEXT NOT NULL, is_default INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE library_folders (path TEXT PRIMARY KEY);
    """,
]

SORT_COLUMNS = {"title": "s.title COLLATE NOCASE", "artist": "s.artist COLLATE NOCASE",
                "duration": "s.duration", "format": "s.format", "added_at": "s.added_at",
                "play_count": "s.play_count", "last_played": "s.last_played"}
SONG_FIELDS = ("filename", "title", "artist", "format", "duration", "size", "mtime",
               "fingerprint", "has_lyrics", "error")


class Database:
    def __init__(self, path: str = ":memory:"):
        try:
            if path != ":memory:":
                os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            self._conn = sqlite3.connect(path, check_same_thread=False)
        except (sqlite3.Error, OSError) as e:
            raise DatabaseError(f"Cannot open database '{path}': {e}") from e
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    # ---- infrastructure ---------------------------------------------
    @property
    def version(self) -> int:
        return self._conn.execute("PRAGMA user_version").fetchone()[0]

    def _migrate(self):
        with self._lock:
            v = self.version
            if v > len(MIGRATIONS):
                raise DatabaseError(f"Database schema v{v} is newer than this application supports "
                                    f"(v{len(MIGRATIONS)}). Please update the application.")
            for i in range(v, len(MIGRATIONS)):
                try:
                    self._conn.executescript(f"BEGIN;{MIGRATIONS[i]}PRAGMA user_version={i + 1};COMMIT;")
                except sqlite3.Error as e:
                    self._conn.rollback()
                    raise DatabaseError(f"Migration to v{i + 1} failed: {e}") from e

    def close(self):
        with self._lock:
            self._conn.close()

    def _all(self, sql, params=()):
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def _one(self, sql, params=()):
        rows = self._all(sql, params)
        return rows[0] if rows else None

    def _run(self, sql, params=()):
        with self._lock, self._conn:
            return self._conn.execute(sql, params)

    # ---- songs -------------------------------------------------------
    def get_song(self, song_id):
        return self._one("SELECT * FROM songs WHERE id=?", (song_id,))

    def get_song_by_path(self, path):
        return self._one("SELECT * FROM songs WHERE path=?", (path,))

    def upsert_song(self, path: str, info: dict) -> tuple[int, bool]:
        vals = [info.get(f) for f in SONG_FIELDS]
        with self._lock, self._conn:
            row = self._conn.execute("SELECT id FROM songs WHERE path=?", (path,)).fetchone()
            if row:
                sets = ",".join(f"{f}=?" for f in SONG_FIELDS)
                self._conn.execute(f"UPDATE songs SET {sets}, missing=0 WHERE id=?", vals + [row["id"]])
                return row["id"], False
            cols = ",".join(SONG_FIELDS)
            cur = self._conn.execute(
                f"INSERT INTO songs(path,{cols},added_at) VALUES(?,{','.join('?' * len(SONG_FIELDS))},?)",
                [path] + vals + [time.time()])
            return cur.lastrowid, True

    def find_missing_by_fingerprint(self, fp):
        if not fp:
            return None
        return self._one("SELECT * FROM songs WHERE fingerprint=? AND missing=1 LIMIT 1", (fp,))

    def relocate_song(self, song_id, new_path, info):
        """A missing song reappeared at another path: keep its favorites/play counts."""
        vals = [info.get(f) for f in SONG_FIELDS]
        sets = ",".join(f"{f}=?" for f in SONG_FIELDS)
        self._run(f"UPDATE songs SET path=?, {sets}, missing=0 WHERE id=?", [new_path] + vals + [song_id])

    def list_songs(self, search="", sort="title", descending=False, favorites_only=False,
                   recent_only=False, limit=None, offset=None):
        where, params = [], []
        if search.strip():
            for term in search.split():
                like = f"%{term.replace('%', '').replace('_', ' ')}%"
                where.append("(s.title LIKE ? OR s.artist LIKE ? OR s.filename LIKE ? "
                             "OR s.format LIKE ? OR s.path LIKE ?)")
                params += [like] * 5
        if favorites_only:
            where.append("s.favorite=1")
        if recent_only:
            where.append("s.last_played IS NOT NULL")
        direction = "DESC" if descending else "ASC"
        if recent_only:
            order = "s.last_played DESC"
        elif sort == "added_at":
            order = f"s.added_at {direction}, s.id {direction}"
        else:
            order = f"{SORT_COLUMNS.get(sort, SORT_COLUMNS['title'])} {direction}, s.id ASC"
        sql = ("WITH numbered AS ("
               "SELECT s.*, ROW_NUMBER() OVER (ORDER BY s.title COLLATE NOCASE, s.id ASC) AS song_number "
               "FROM songs s) "
               "SELECT s.* FROM numbered s" +
               (" WHERE " + " AND ".join(where) if where else "") +
               f" ORDER BY {order}")
        if limit:
            sql += f" LIMIT {int(limit)}"
            if offset:
                sql += f" OFFSET {int(offset)}"
        return self._all(sql, params)

    def count_songs(self):
        return self._one("SELECT COUNT(*) AS n FROM songs")["n"]

    def get_song_by_number(self, number: int):
        """Find a song by its stable karaoke song number (1-based title order)."""
        if number < 1:
            return None
        sql = ("WITH numbered AS ("
               "SELECT s.*, ROW_NUMBER() OVER (ORDER BY s.title COLLATE NOCASE, s.id ASC) AS song_number "
               "FROM songs s) "
               "SELECT * FROM numbered WHERE song_number=? LIMIT 1")
        return self._one(sql, (int(number),))

    def list_remote_songs(self, search="", limit=30, offset=0, shuffle=True, seed=None):
        """Paginated library rows with stable karaoke numbers.

        The number is assigned over the complete title-sorted library before
        search filtering, so a phone search never renumbers the songs.
        When browsing without a search query, results are shuffled so they are
        not presented in sequential number order.
        """
        where, params = [], []
        if search.strip():
            for term in search.split():
                like = f"%{term.replace('%', '').replace('_', ' ')}%"
                where.append("(s.title LIKE ? OR s.artist LIKE ? OR s.filename LIKE ? "
                             "OR s.format LIKE ? OR s.path LIKE ?)")
                params += [like] * 5
        s_val = int(seed) if seed is not None else 1013904223
        mult = (s_val * 1103515245 + 12345) & 0x7FFFFFFF
        if mult % 2 == 0:
            mult += 1
        quad = (s_val % 997 + 13)
        order_clause = (
            f"((s.song_number * {mult} + s.song_number * s.song_number * {quad} + {s_val}) % 2147483647)"
            if (shuffle and not search.strip())
            else "s.song_number"
        )
        sql = ("WITH numbered AS ("
               "SELECT s.*, ROW_NUMBER() OVER (ORDER BY s.title COLLATE NOCASE, s.id ASC) AS song_number "
               "FROM songs s) "
               "SELECT * FROM numbered s" +
               (" WHERE " + " AND ".join(where) if where else "") +
               f" ORDER BY {order_clause} LIMIT ? OFFSET ?")
        return self._all(sql, params + [int(limit), max(0, int(offset))])

    def set_favorite(self, song_id, value: bool):
        self._run("UPDATE songs SET favorite=? WHERE id=?", (1 if value else 0, song_id))

    def record_play(self, song_id):
        self._run("UPDATE songs SET play_count=play_count+1, last_played=? WHERE id=?", (time.time(), song_id))

    def set_missing(self, song_id, missing: bool):
        self._run("UPDATE songs SET missing=? WHERE id=?", (1 if missing else 0, song_id))

    def remove_songs(self, song_ids):
        """Removes library rows only. Never touches files on disk."""
        with self._lock, self._conn:
            self._conn.executemany("DELETE FROM songs WHERE id=?", [(i,) for i in song_ids])

    def find_duplicates(self):
        """Groups of songs with identical content fingerprints."""
        groups = {}
        for r in self._all("SELECT * FROM songs WHERE fingerprint IN (SELECT fingerprint FROM songs "
                           "WHERE fingerprint IS NOT NULL GROUP BY fingerprint HAVING COUNT(*)>1) "
                           "ORDER BY fingerprint, id"):
            groups.setdefault(r["fingerprint"], []).append(r)
        return list(groups.values())

    # ---- library folders --------------------------------------------
    def add_library_folder(self, path):
        self._run("INSERT OR IGNORE INTO library_folders(path) VALUES(?)", (path,))

    def remove_library_folder(self, path):
        self._run("DELETE FROM library_folders WHERE path=?", (path,))

    def library_folders(self):
        return [r["path"] for r in self._all("SELECT path FROM library_folders ORDER BY path")]

    # ---- playlists ---------------------------------------------------
    def create_playlist(self, name: str) -> int:
        name = name.strip()
        if not name:
            raise DatabaseError("Playlist name cannot be empty.")
        try:
            return self._run("INSERT INTO playlists(name,created_at) VALUES(?,?)", (name, time.time())).lastrowid
        except sqlite3.IntegrityError:
            raise DatabaseError(f"A playlist named '{name}' already exists.") from None

    def rename_playlist(self, pid, name):
        name = name.strip()
        if not name:
            raise DatabaseError("Playlist name cannot be empty.")
        try:
            self._run("UPDATE playlists SET name=? WHERE id=?", (name, pid))
        except sqlite3.IntegrityError:
            raise DatabaseError(f"A playlist named '{name}' already exists.") from None

    def delete_playlist(self, pid):
        self._run("DELETE FROM playlists WHERE id=?", (pid,))

    def list_playlists(self):
        return self._all("SELECT p.*, (SELECT COUNT(*) FROM playlist_songs ps WHERE ps.playlist_id=p.id) AS count "
                         "FROM playlists p ORDER BY p.name COLLATE NOCASE")

    def playlist_add(self, pid, song_ids):
        with self._lock, self._conn:
            pos = self._conn.execute("SELECT COALESCE(MAX(position),-1) FROM playlist_songs WHERE playlist_id=?",
                                     (pid,)).fetchone()[0]
            for sid in song_ids:
                pos += 1
                self._conn.execute("INSERT INTO playlist_songs(playlist_id,song_id,position) VALUES(?,?,?)",
                                   (pid, sid, pos))

    def playlist_songs(self, pid):
        sql = ("WITH numbered AS ("
               "SELECT s.*, ROW_NUMBER() OVER (ORDER BY s.title COLLATE NOCASE, s.id ASC) AS song_number "
               "FROM songs s) "
               "SELECT s.*, ps.id AS entry_id, ps.position AS position FROM playlist_songs ps "
               "JOIN numbered s ON s.id=ps.song_id WHERE ps.playlist_id=? ORDER BY ps.position")
        return self._all(sql, (pid,))

    def playlist_remove(self, pid, entry_ids):
        with self._lock, self._conn:
            self._conn.executemany("DELETE FROM playlist_songs WHERE id=? AND playlist_id=?",
                                   [(e, pid) for e in entry_ids])
        self._renumber(pid)

    def playlist_move(self, pid, entry_id, new_index):
        ids = [r["entry_id"] for r in self.playlist_songs(pid)]
        if entry_id not in ids:
            return
        ids.remove(entry_id)
        ids.insert(max(0, min(new_index, len(ids))), entry_id)
        self._renumber(pid, ids)

    def _renumber(self, pid, ordered=None):
        ordered = ordered or [r["entry_id"] for r in self.playlist_songs(pid)]
        with self._lock, self._conn:
            self._conn.executemany("UPDATE playlist_songs SET position=? WHERE id=?",
                                   [(i, e) for i, e in enumerate(ordered)])

    # ---- settings / presets / soundfonts -----------------------------
    def get_setting(self, key, default=None):
        row = self._one("SELECT value FROM settings WHERE key=?", (key,))
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except ValueError:
            return default

    def set_setting(self, key, value):
        self._run("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                  (key, json.dumps(value)))

    def save_eq_preset(self, name, gains, bass=0.0, treble=0.0):
        if not name.strip():
            raise DatabaseError("Preset name cannot be empty.")
        self._run("INSERT OR REPLACE INTO eq_presets(name,gains,bass,treble) VALUES(?,?,?,?)",
                  (name.strip(), json.dumps(list(gains)), bass, treble))

    def list_eq_presets(self):
        return {r["name"]: {"gains": json.loads(r["gains"]), "bass": r["bass"], "treble": r["treble"]}
                for r in self._all("SELECT * FROM eq_presets ORDER BY name COLLATE NOCASE")}

    def rename_eq_preset(self, old, new):
        new = new.strip()
        if not new:
            raise DatabaseError("Preset name cannot be empty.")
        if new != old and self._one("SELECT 1 FROM eq_presets WHERE name=?", (new,)):
            raise DatabaseError(f"A preset named '{new}' already exists.")
        self._run("UPDATE eq_presets SET name=? WHERE name=?", (new, old))

    def delete_eq_preset(self, name):
        self._run("DELETE FROM eq_presets WHERE name=?", (name,))

    def add_soundfont(self, path):
        existing = self._one("SELECT id FROM soundfonts WHERE path=?", (path,))
        if existing:
            return existing["id"]
        first = not self._one("SELECT 1 FROM soundfonts")
        return self._run("INSERT INTO soundfonts(path,name,is_default) VALUES(?,?,?)",
                         (path, os.path.basename(path), 1 if first else 0)).lastrowid

    def list_soundfonts(self):
        return self._all("SELECT * FROM soundfonts ORDER BY name COLLATE NOCASE")

    def remove_soundfont(self, sf_id):
        self._run("DELETE FROM soundfonts WHERE id=?", (sf_id,))   # file stays on disk

    def set_default_soundfont(self, sf_id):
        with self._lock, self._conn:
            self._conn.execute("UPDATE soundfonts SET is_default=0")
            self._conn.execute("UPDATE soundfonts SET is_default=1 WHERE id=?", (sf_id,))

    def default_soundfont(self):
        return self._one("SELECT * FROM soundfonts WHERE is_default=1")
