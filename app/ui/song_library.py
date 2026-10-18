from __future__ import annotations
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QTimer, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMenu, QMessageBox, QPushButton, QTableView, QVBoxLayout, QWidget)
from app.utils.format import fmt_time

SORTS = [("Title", "title"), ("Artist", "artist"), ("Duration", "duration"), ("Format", "format"), ("Recently added", "added_at")]
COL_SORT = {2: "title", 3: "artist", 4: "format", 5: "duration"}


class SongTableModel(QAbstractTableModel):
    HEADERS = ["#", "★", "Title", "Artist", "Format", "Duration", "Location", "Status"]

    def __init__(self):
        super().__init__()
        self.rows: list[dict] = []
        self.playing_id = None

    def set_rows(self, rows):
        self.beginResetModel(); self.rows = rows; self.endResetModel()

    def rowCount(self, parent=QModelIndex()): return 0 if parent.isValid() else len(self.rows)
    def columnCount(self, parent=QModelIndex()): return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.HEADERS[section]

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        r, c = self.rows[index.row()], index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if c == 0: return r.get("song_number", index.row() + 1)
            if c == 1: return "★" if r["favorite"] else ""
            if c == 2: return r["title"] or r["filename"]
            if c == 3: return r["artist"] or ""
            if c == 4: return r["format"] or ""
            if c == 5: return fmt_time(r["duration"])
            if c == 6: return r["path"]
            if c == 7:
                if r["missing"]: return "Missing"
                if r["error"]: return "Unreadable"
                if r["id"] == self.playing_id: return "▶ Playing"
                return "♪ Lyrics" if r["has_lyrics"] else ""
        elif role == Qt.ItemDataRole.ToolTipRole:
            return r["error"] or ("File not found on disk" if r["missing"] else r["path"])
        elif role == Qt.ItemDataRole.ForegroundRole and (r["missing"] or r["error"]):
            return QBrush(QColor("#e57373"))
        elif role == Qt.ItemDataRole.ForegroundRole and c == 1:
            return QBrush(QColor("#ffd54f"))
        elif role == Qt.ItemDataRole.TextAlignmentRole and c in (0, 1, 5):
            return int(Qt.AlignmentFlag.AlignCenter)


class LibraryView(QWidget):
    """mode: library | recent | favorites | playlist"""
    def __init__(self, db, settings, ctl, mode="library", parent=None):
        super().__init__(parent)
        self.db, self.settings, self.ctl, self.mode = db, settings, ctl, mode
        self.playlist_id = None
        self.sort = settings.get("library_sort"); self.desc = bool(settings.get("library_desc"))

        self.search = QLineEdit(); self.search.setPlaceholderText("Search title, artist, filename, format or path…")
        self.search.setClearButtonEnabled(True)
        self.sort_box = QComboBox()
        for label, key in SORTS:
            self.sort_box.addItem(label, key)
        self.sort_box.setCurrentIndex(max(0, [k for _, k in SORTS].index(self.sort) if self.sort in dict((k, 1) for _, k in SORTS) else 0))
        self.order_b = QPushButton("↓" if self.desc else "↑"); self.order_b.setFixedWidth(36)
        top = QHBoxLayout(); top.addWidget(self.search, 1); top.addWidget(QLabel("Sort:")); top.addWidget(self.sort_box); top.addWidget(self.order_b)

        self.up_b = QPushButton("Move up"); self.down_b = QPushButton("Move down")
        self.clear_recent_b = QPushButton("Clear list")
        self.status = QLabel(""); self.status.setObjectName("muted")
        bar = QHBoxLayout()
        for w in (self.up_b, self.down_b, self.clear_recent_b):
            bar.addWidget(w)
        bar.addStretch(1); bar.addWidget(self.status)
        if mode != "playlist":
            self.up_b.hide(); self.down_b.hide()
        if mode != "recent":
            self.clear_recent_b.hide()

        self.model = SongTableModel()
        self.table = QTableView(); self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True); self.table.verticalHeader().hide(); self.table.setShowGrid(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        h = self.table.horizontalHeader(); h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h.setStretchLastSection(False)
        for i, w in enumerate((42, 36, 260, 180, 70, 80, 360, 90)):
            self.table.setColumnWidth(i, w)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        lay = QVBoxLayout(self); lay.addLayout(top); lay.addLayout(bar); lay.addWidget(self.table, 1)

        self._debounce = QTimer(self); self._debounce.setSingleShot(True); self._debounce.setInterval(250)
        self._debounce.timeout.connect(self.reload)
        self.search.textChanged.connect(lambda _: self._debounce.start())
        self.sort_box.currentIndexChanged.connect(self._sort_changed)
        self.order_b.clicked.connect(self._toggle_order)
        h.sectionClicked.connect(self._header_clicked)
        self.table.doubleClicked.connect(self._double_click)
        self.table.customContextMenuRequested.connect(self._menu)
        self.up_b.clicked.connect(lambda: self._move(-1)); self.down_b.clicked.connect(lambda: self._move(1))
        self.clear_recent_b.clicked.connect(self._clear_recent)
        ctl.library_changed.connect(self.reload)
        ctl.song_changed.connect(self._playing_changed)
        self.reload()

    def _clear_recent(self):
        self.db.clear_recently_played()
        self.reload()

    # ---- data --------------------------------------------------------
    def set_playlist(self, pid):
        self.playlist_id = pid; self.reload()

    def reload(self):
        if self.mode == "playlist":
            rows = self.db.playlist_songs(self.playlist_id) if self.playlist_id else []
            q = self.search.text().lower().strip()
            if q:
                rows = [r for r in rows if q in " ".join(str(r.get(k) or "") for k in ("title", "artist", "filename", "format", "path")).lower()]
        else:
            rows = self.db.list_songs(self.search.text(), self.sort, self.desc,
                                      favorites_only=self.mode == "favorites", recent_only=self.mode == "recent")
        self.model.set_rows(rows)
        self.status.setText(f"{len(rows)} song{'s' if len(rows) != 1 else ''}")

    def _playing_changed(self, song):
        self.model.playing_id = song["id"] if song else None
        self.model.layoutChanged.emit()

    def _sort_changed(self):
        self.sort = self.sort_box.currentData(); self.settings.set("library_sort", self.sort); self.reload()

    def _toggle_order(self):
        self.desc = not self.desc; self.order_b.setText("↓" if self.desc else "↑")
        self.settings.set("library_desc", self.desc); self.reload()

    def _header_clicked(self, col):
        key = COL_SORT.get(col)
        if not key or self.mode in ("recent", "playlist"):
            return
        if key == self.sort:
            self._toggle_order()
        else:
            self.sort_box.setCurrentIndex(self.sort_box.findData(key))

    def _selected(self):
        return [self.model.rows[i.row()] for i in self.table.selectionModel().selectedRows()]

    # ---- actions -----------------------------------------------------
    def _double_click(self, index):
        self.ctl.play_songs([self.model.rows[index.row()]], 0)

    def _menu(self, pos):
        sel = self._selected()
        if not sel:
            return
        m = QMenu(self)
        m.addAction("Play", lambda: self.ctl.play_songs([sel[0]], 0))
        m.addAction("Add to queue", lambda: self.ctl.enqueue(sel))
        m.addAction("Play next", lambda: self.ctl.enqueue(sel, play_next=True))
        m.addAction("Remove from favorites" if sel[0]["favorite"] else "Add to favorites", lambda: self._fav(sel))
        sub = m.addMenu("Add to playlist")
        for p in self.db.list_playlists():
            sub.addAction(p["name"], lambda pid=p["id"]: self._to_playlist(pid, sel))
        if not self.db.list_playlists():
            sub.addAction("(no playlists yet)").setEnabled(False)
        if self.mode == "playlist":
            m.addAction("Remove from playlist", lambda: self._rm_playlist(sel))
        m.addSeparator()
        m.addAction("Remove from library (keeps file)", lambda: self._remove(sel))
        m.exec(self.table.viewport().mapToGlobal(pos))

    def _fav(self, sel):
        value = not sel[0]["favorite"]
        for s in sel:
            self.db.set_favorite(s["id"], value)
        self.ctl.library_changed.emit()

    def _to_playlist(self, pid, sel):
        self.db.playlist_add(pid, [s["id"] for s in sel]); self.ctl.library_changed.emit()

    def _rm_playlist(self, sel):
        self.db.playlist_remove(self.playlist_id, [s["entry_id"] for s in sel]); self.reload()

    def _move(self, delta):
        sel = self._selected()
        if len(sel) != 1:
            return
        idx = self.model.rows.index(sel[0])
        self.db.playlist_move(self.playlist_id, sel[0]["entry_id"], idx + delta)
        self.reload(); self.table.selectRow(max(0, min(idx + delta, len(self.model.rows) - 1)))

    def _remove(self, sel):
        if QMessageBox.question(self, "Remove from library",
                                f"Remove {len(sel)} song(s) from the library?\nThe files on disk will NOT be deleted.") \
                == QMessageBox.StandardButton.Yes:
            self.db.remove_songs([s["id"] for s in sel]); self.ctl.library_changed.emit()
