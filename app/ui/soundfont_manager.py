from __future__ import annotations
import os
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget)
from app.audio.fluidsynth_backend import SynthError


class SoundFontManager(QWidget):
    def __init__(self, db, settings, ctl, parent=None):
        super().__init__(parent)
        self.db, self.settings, self.ctl = db, settings, ctl
        title = QLabel("SoundFont Manager"); title.setObjectName("h1")
        self.active = QLabel(); self.active.setObjectName("muted")
        self.list = QListWidget()
        add_b, rm_b, use_b, def_b = QPushButton("Add .sf2…"), QPushButton("Remove from list"), QPushButton("Use selected"), QPushButton("Set as default")
        use_b.setObjectName("primary")
        row = QHBoxLayout()
        for b in (add_b, rm_b, def_b, use_b): row.addWidget(b)

        self.gain, self.reverb, self.chorus = QSlider(Qt.Orientation.Horizontal), QSlider(Qt.Orientation.Horizontal), QSlider(Qt.Orientation.Horizontal)
        self.bass_punch = QSlider(Qt.Orientation.Horizontal)
        self.gain.setRange(0, 200); self.reverb.setRange(0, 100); self.chorus.setRange(0, 100)
        self.bass_punch.setRange(0, 100)
        self.gain.setValue(int(settings.get("synth_gain") * 100)); self.reverb.setValue(int(settings.get("reverb_level") * 100))
        self.chorus.setValue(int(settings.get("chorus_level") * 10))
        self.bass_punch.setValue(int(settings.get("bass_punch", 0.75) * 100))
        self.kick_boost_cb = QCheckBox("Kick Drum Dynamic Velocity Boost (triggers punchy hit layer)")
        self.kick_boost_cb.setChecked(bool(settings.get("drum_boost", True)))

        self.gl, self.rl, self.cl, self.pl = QLabel(), QLabel(), QLabel(), QLabel()
        fx = QGridLayout()
        for r, (n, s, l) in enumerate((("Synth gain", self.gain, self.gl),
                                       ("Reverb level", self.reverb, self.rl),
                                       ("Chorus level", self.chorus, self.cl),
                                       ("Bass Drum Punch", self.bass_punch, self.pl))):
            fx.addWidget(QLabel(n), r, 0); fx.addWidget(s, r, 1); fx.addWidget(l, r, 2)
        fx.addWidget(self.kick_boost_cb, 4, 0, 1, 3)
        reset_b = QPushButton("Reset synthesizer settings"); fx.addWidget(reset_b, 5, 0, 1, 3)
        fx_box = QGroupBox("Synthesizer & Drum Dynamics"); fx_box.setLayout(fx)

        self.ch_sliders, self.ch_mutes = [], []
        grid = QGridLayout()
        for ch in range(16):
            lab = QLabel(f"Ch {ch + 1}" + (" (drums)" if ch == 9 else ""))
            s = QSlider(Qt.Orientation.Horizontal); s.setRange(0, 100); s.setValue(100)
            m = QCheckBox("Mute")
            s.valueChanged.connect(lambda v, ch=ch: self._ch_vol(ch, v)); m.toggled.connect(lambda on, ch=ch: self._ch_mute(ch, on))
            grid.addWidget(lab, ch, 0); grid.addWidget(s, ch, 1); grid.addWidget(m, ch, 2)
            self.ch_sliders.append(s); self.ch_mutes.append(m)
        inner = QWidget(); inner.setLayout(grid); scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(inner)
        scroll.setMinimumHeight(160)
        ch_box = QGroupBox("Channel mixer (requires a loaded SoundFont)"); QVBoxLayout(ch_box).addWidget(scroll)

        lay = QVBoxLayout(self)
        for w in (title, self.active, self.list): lay.addWidget(w)
        lay.addLayout(row); lay.addWidget(fx_box); lay.addWidget(ch_box, 1)

        add_b.clicked.connect(self._add); rm_b.clicked.connect(self._remove); use_b.clicked.connect(self._use)
        def_b.clicked.connect(self._default); self.list.itemDoubleClicked.connect(lambda _: self._use())
        self.gain.valueChanged.connect(self._fx); self.reverb.valueChanged.connect(self._fx); self.chorus.valueChanged.connect(self._fx)
        self.bass_punch.valueChanged.connect(self._fx); self.kick_boost_cb.toggled.connect(self._fx)
        reset_b.clicked.connect(self._reset)
        self._labels(); self.refresh()

    def refresh(self):
        self.list.clear()
        cur = self.settings.get("soundfont")
        for sf in self.db.list_soundfonts():
            ok = os.path.isfile(sf["path"])
            tags = (" [ACTIVE]" if sf["path"] == cur else "") + (" [default]" if sf["is_default"] else "") + ("" if ok else " [FILE MISSING]")
            it = QListWidgetItem(f"{sf['name']}{tags}\n{sf['path']}"); it.setData(Qt.ItemDataRole.UserRole, sf)
            if not ok: it.setForeground(QBrush(QColor("#e57373")))
            self.list.addItem(it)
        name = os.path.basename(self.ctl.synth.soundfont_path) if self.ctl.synth and self.ctl.synth.soundfont_path else "none loaded"
        self.active.setText(f"Active SoundFont: {name}")

    def _sel(self):
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _add(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Add SoundFont", "", "SoundFonts (*.sf2)")
        for p in paths:
            self.db.add_soundfont(p)
        self.refresh()

    def _remove(self):
        sf = self._sel()
        if sf:
            self.db.remove_soundfont(sf["id"]); self.refresh()     # the .sf2 file itself is never deleted

    def _default(self):
        sf = self._sel()
        if sf: self.db.set_default_soundfont(sf["id"]); self.refresh()

    def _use(self):
        sf = self._sel()
        if not sf: return
        try:
            self.ctl.set_soundfont(sf["path"])
        except SynthError as e:
            QMessageBox.warning(self, "SoundFont could not be loaded", f"{e}\n\nThe previously active SoundFont (if any) is still in use.")
        self.refresh()

    def _labels(self):
        self.gl.setText(f"{self.gain.value() / 100:.2f}"); self.rl.setText(f"{self.reverb.value()}%"); self.cl.setText(f"{self.chorus.value() / 10:.1f}")
        p = self.bass_punch.value()
        self.pl.setText("Off" if p == 0 else f"{p}% (Punchy)")

    def _fx(self):
        self._labels()
        self.settings.set("synth_gain", self.gain.value() / 100); self.settings.set("reverb_level", self.reverb.value() / 100)
        self.settings.set("chorus_level", self.chorus.value() / 10)
        punch = self.bass_punch.value() / 100.0
        self.settings.set("bass_punch", punch)
        self.settings.set("drum_boost", self.kick_boost_cb.isChecked())
        if hasattr(self.ctl, "engine") and hasattr(self.ctl.engine, "eq"):
            self.ctl.engine.eq.set_bass_punch(punch)
        self.ctl.apply_synth_fx()

    def _reset(self):
        self.gain.setValue(65); self.reverb.setValue(40); self.chorus.setValue(15)
        self.bass_punch.setValue(75)
        self.kick_boost_cb.setChecked(True)
        for s, m in zip(self.ch_sliders, self.ch_mutes): s.setValue(100); m.setChecked(False)
        self._fx()

    def _ch_vol(self, ch, v):
        if self.ctl.synth: self.ctl.synth.set_channel_volume(ch, v / 100)

    def _ch_mute(self, ch, on):
        if self.ctl.synth: self.ctl.synth.set_channel_muted(ch, on)
