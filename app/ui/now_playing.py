from __future__ import annotations
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (QDoubleSpinBox, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QPushButton, QSlider, QVBoxLayout, QWidget, QAbstractItemView)
from app.utils.format import fmt_time


class NowPlayingBar(QFrame):
    karaoke_requested = Signal()

    def __init__(self, ctl, parent=None):
        super().__init__(parent)
        self.setObjectName("nowplaying")
        self.ctl = ctl
        self._dragging = False
        self.title = QLabel("Nothing playing"); self.title.setStyleSheet("font-size:15px;font-weight:600;")
        self.sub = QLabel(""); self.sub.setObjectName("muted")
        info = QVBoxLayout(); info.addWidget(self.title); info.addWidget(self.sub)
        infow = QWidget(); infow.setLayout(info); infow.setMinimumWidth(180)

        self.prev_b = QPushButton("⏮"); self.play_b = QPushButton("▶"); self.stop_b = QPushButton("⏹"); self.next_b = QPushButton("⏭")
        self.play_b.setObjectName("primary")
        for b, tip in ((self.prev_b, "Previous"), (self.play_b, "Play / Pause"), (self.stop_b, "Stop"), (self.next_b, "Next")):
            b.setToolTip(tip); b.setMinimumHeight(36)
        self.shuffle_b = QPushButton("Shuffle"); self.shuffle_b.setCheckable(True)
        self.shuffle_b.setChecked(ctl.queue.shuffle)
        self.repeat_b = QPushButton(); self._set_repeat_text()
        self.tempo = QDoubleSpinBox(); self.tempo.setRange(0.5, 1.5); self.tempo.setSingleStep(0.05)
        self.tempo.setPrefix("Tempo ×"); self.tempo.setValue(ctl.tempo)
        self.karaoke_b = QPushButton("🎤 Karaoke")
        self.vol = QSlider(Qt.Orientation.Horizontal); self.vol.setRange(0, 150)
        self.vol.setValue(int(ctl.engine.eq.volume * 100)); self.vol.setFixedWidth(110)
        self.vol_lbl = QLabel(f"{self.vol.value()}%"); self.vol_lbl.setFixedWidth(40)

        buttons = QHBoxLayout()
        for w in (self.prev_b, self.play_b, self.stop_b, self.next_b, self.shuffle_b, self.repeat_b, self.tempo, self.karaoke_b):
            buttons.addWidget(w)
        buttons.addStretch(1)
        buttons.addWidget(QLabel("🔊")); buttons.addWidget(self.vol); buttons.addWidget(self.vol_lbl)

        self.pos = QSlider(Qt.Orientation.Horizontal); self.pos.setRange(0, 1000)
        self.t_cur, self.t_tot = QLabel("00:00"), QLabel("--:--")
        prog = QHBoxLayout(); prog.addWidget(self.t_cur); prog.addWidget(self.pos, 1); prog.addWidget(self.t_tot)

        right = QVBoxLayout(); right.addLayout(buttons); right.addLayout(prog)
        lay = QHBoxLayout(self); lay.addWidget(infow); lay.addLayout(right, 1)

        self.prev_b.clicked.connect(ctl.previous); self.next_b.clicked.connect(ctl.next)
        self.play_b.clicked.connect(ctl.toggle_play_pause); self.stop_b.clicked.connect(ctl.stop)
        self.shuffle_b.toggled.connect(ctl.set_shuffle)
        self.repeat_b.clicked.connect(self._cycle_repeat)
        self.tempo.valueChanged.connect(ctl.set_tempo)
        self.karaoke_b.clicked.connect(self.karaoke_requested)
        self.vol.valueChanged.connect(self._vol)
        self.pos.sliderPressed.connect(lambda: setattr(self, "_dragging", True))
        self.pos.sliderReleased.connect(self._seek)
        ctl.song_changed.connect(self._song); ctl.state_changed.connect(self._state)
        ctl.position_changed.connect(self._position)

    def _vol(self, v):
        self.vol_lbl.setText(f"{v}%"); self.ctl.set_volume(v / 100)

    def _set_repeat_text(self):
        self.repeat_b.setText({"off": "Repeat: Off", "all": "Repeat: All", "one": "Repeat: One"}[self.ctl.queue.repeat])

    def _cycle_repeat(self):
        nxt = {"off": "all", "all": "one", "one": "off"}[self.ctl.queue.repeat]
        self.ctl.set_repeat(nxt); self._set_repeat_text()

    def _seek(self):
        self._dragging = False
        dur = self.ctl.engine.duration
        if dur > 0:
            self.ctl.seek(self.pos.value() / 1000 * dur)

    def _song(self, song):
        if not song:
            self.title.setText("Nothing playing"); self.sub.setText(""); return
        self.title.setText(song["title"] or song["filename"])
        self.sub.setText(" · ".join(x for x in (song.get("artist"), song.get("format")) if x))
        self.tempo.setEnabled(song["format"] in ("MID", "MIDI", "KAR"))
        self.tempo.setToolTip("Tempo changes (pitch unchanged) are available for MIDI/KAR files." )

    def _state(self, s):
        self.play_b.setText("⏸" if s == "playing" else "▶")
        if s == "loading":
            self.sub.setText("Decoding audio…")

    def _position(self, pos, dur):
        self.t_cur.setText(fmt_time(pos)); self.t_tot.setText(fmt_time(dur))
        if not self._dragging and dur > 0:
            self.pos.setValue(int(min(1.0, pos / dur) * 1000))


class QueuePanel(QWidget):
    def __init__(self, ctl, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.clear_b = QPushButton("Clear queue"); self.rm_b = QPushButton("Remove selected")
        row = QHBoxLayout(); row.addWidget(self.rm_b); row.addWidget(self.clear_b)
        lay = QVBoxLayout(self); lay.addWidget(self.list); lay.addLayout(row)
        self.list.itemDoubleClicked.connect(lambda it: ctl.play_now(it.data(Qt.ItemDataRole.UserRole)))
        self.list.model().rowsMoved.connect(lambda *a: QTimer.singleShot(0, self._moved))
        self.rm_b.clicked.connect(self._remove); self.clear_b.clicked.connect(ctl.clear_queue)
        self._refreshing = False
        ctl.queue_changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        # Do NOT block the model's signals here: the view relies on them to
        # display the rows, which is why the queue used to appear empty.
        self._refreshing = True
        try:
            self.list.clear()
            cur = self.ctl.queue.current_uid
            waiting = {it.uid: n for n, it in enumerate(self.ctl.queue.upcoming(), 1)}
            for it in self.ctl.queue.items:
                s = it.song
                name = (s.get("title") or s.get("filename") or "") + (f" — {s['artist']}" if s.get("artist") else "")
                if it.uid == cur:
                    prefix = "▶  "
                elif it.uid in waiting:
                    prefix = f"{waiting[it.uid]}.  "
                else:
                    prefix = "✓  "
                li = QListWidgetItem(prefix + name); li.setData(Qt.ItemDataRole.UserRole, it.uid)
                if it.uid == cur:
                    f = li.font(); f.setBold(True); li.setFont(f)
                elif it.uid not in waiting:
                    li.setForeground(Qt.GlobalColor.gray)
                self.list.addItem(li)
        finally:
            self._refreshing = False

    def _moved(self):
        if self._refreshing:
            return
        uids = [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())]
        try:
            self.ctl.reorder_queue(uids)
        except ValueError:
            pass
        self.refresh()

    def _remove(self):
        for it in self.list.selectedItems():
            self.ctl.queue.remove(it.data(Qt.ItemDataRole.UserRole))
        self.ctl.queue_changed.emit()
