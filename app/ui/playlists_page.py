from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QInputDialog, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
                               QSplitter, QVBoxLayout, QWidget)
from app.library.database import DatabaseError
from app.ui.song_library import LibraryView


class PlaylistsPage(QWidget):
    def __init__(self, db, settings, ctl, parent=None):
        super().__init__(parent)
        self.db, self.ctl = db, ctl
        self.list = QListWidget()
        new_b, ren_b, del_b = QPushButton("New"), QPushButton("Rename"), QPushButton("Delete")
        row = QHBoxLayout()
        for b in (new_b, ren_b, del_b): row.addWidget(b)
        left = QWidget(); ll = QVBoxLayout(left); ll.setContentsMargins(0, 0, 0, 0); ll.addWidget(self.list); ll.addLayout(row)
        self.songs = LibraryView(db, settings, ctl, mode="playlist")
        split = QSplitter(); split.addWidget(left); split.addWidget(self.songs); split.setStretchFactor(1, 1)
        split.setSizes([240, 760])
        QVBoxLayout(self).addWidget(split)
        new_b.clicked.connect(self._new); ren_b.clicked.connect(self._rename); del_b.clicked.connect(self._delete)
        self.list.currentItemChanged.connect(lambda cur, _: self.songs.set_playlist(cur.data(Qt.ItemDataRole.UserRole) if cur else None))
        ctl.library_changed.connect(self._refresh_counts)
        self.refresh()

    def refresh(self, select=None):
        cur = select or (self.list.currentItem().data(Qt.ItemDataRole.UserRole) if self.list.currentItem() else None)
        self.list.blockSignals(True); self.list.clear()
        target = None
        for p in self.db.list_playlists():
            it = QListWidgetItem(f"{p['name']}  ({p['count']})"); it.setData(Qt.ItemDataRole.UserRole, p["id"])
            it.setData(Qt.ItemDataRole.UserRole + 1, p["name"])
            self.list.addItem(it)
            if p["id"] == cur: target = it
        self.list.blockSignals(False)
        if target: self.list.setCurrentItem(target)
        elif self.list.count(): self.list.setCurrentRow(0)
        else: self.songs.set_playlist(None)

    def _refresh_counts(self):
        self.refresh()

    def _new(self):
        name, ok = QInputDialog.getText(self, "New playlist", "Name:")
        if ok:
            try: self.refresh(self.db.create_playlist(name))
            except DatabaseError as e: QMessageBox.warning(self, "Playlist", str(e))

    def _rename(self):
        it = self.list.currentItem()
        if not it: return
        name, ok = QInputDialog.getText(self, "Rename playlist", "Name:", text=it.data(Qt.ItemDataRole.UserRole + 1))
        if ok:
            try: self.db.rename_playlist(it.data(Qt.ItemDataRole.UserRole), name); self.refresh()
            except DatabaseError as e: QMessageBox.warning(self, "Playlist", str(e))

    def _delete(self):
        it = self.list.currentItem()
        if it and QMessageBox.question(self, "Delete playlist", "Delete this playlist? Songs stay in your library.") \
                == QMessageBox.StandardButton.Yes:
            self.db.delete_playlist(it.data(Qt.ItemDataRole.UserRole)); self.refresh()
