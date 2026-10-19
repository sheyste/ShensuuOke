from __future__ import annotations
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel,
                               QMessageBox, QPushButton, QSlider, QVBoxLayout, QWidget)
from app.audio.equalizer import BAND_FREQS, BUILTIN_PRESETS
from app.library.database import DatabaseError


def _label(f): return f"{f // 1000}k" if f >= 1000 else str(f)


class EqualizerView(QWidget):
    def __init__(self, db, settings, ctl, parent=None):
        super().__init__(parent)
        self.db, self.settings, self.eq = db, settings, ctl.engine.eq
        self._loading = False
        self._save = QTimer(self); self._save.setSingleShot(True); self._save.setInterval(500); self._save.timeout.connect(self._persist)

        title = QLabel("Equalizer"); title.setObjectName("h1")
        self.preset = QComboBox(); self.save_b = QPushButton("Save as…"); self.ren_b = QPushButton("Rename"); self.del_b = QPushButton("Delete")
        self.reset_b = QPushButton("Reset"); self.mute = QCheckBox("Mute")
        top = QHBoxLayout()
        for w in (QLabel("Preset:"), self.preset, self.save_b, self.ren_b, self.del_b): top.addWidget(w)
        top.addStretch(1); top.addWidget(self.mute); top.addWidget(self.reset_b)

        bands = QGridLayout(); self.band_sliders, self.band_labels = [], []
        for i, f in enumerate(BAND_FREQS):
            s = QSlider(Qt.Orientation.Vertical); s.setRange(-120, 120); s.setMinimumHeight(200)
            lab = QLabel("0.0 dB"); lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            s.valueChanged.connect(lambda v, i=i: self._band(i, v))
            bands.addWidget(s, 0, i, Qt.AlignmentFlag.AlignHCenter); bands.addWidget(lab, 1, i)
            bands.addWidget(QLabel(_label(f) + " Hz"), 2, i, Qt.AlignmentFlag.AlignHCenter)
            self.band_sliders.append(s); self.band_labels.append(lab)
        bands_box = QGroupBox("10-band graphic equalizer (−12 … +12 dB)"); bands_box.setLayout(bands)

        def hslider(lo, hi): 
            s = QSlider(Qt.Orientation.Horizontal); s.setRange(lo, hi); return s
        self.bass_punch = hslider(0, 100)
        self.bass, self.treble = hslider(-120, 120), hslider(-120, 120)
        self.balance, self.volume = hslider(-100, 100), hslider(0, 150)
        self.vals = {k: QLabel() for k in ("bass_punch", "bass", "treble", "balance", "volume")}
        tone = QGridLayout()
        for r, (name, s, key) in enumerate((("Bass Drum Punch", self.bass_punch, "bass_punch"),
                                            ("Bass", self.bass, "bass"), ("Treble", self.treble, "treble"),
                                            ("Balance L↔R", self.balance, "balance"), ("Master volume", self.volume, "volume"))):
            tone.addWidget(QLabel(name), r, 0); tone.addWidget(s, r, 1); tone.addWidget(self.vals[key], r, 2)
        tone_box = QGroupBox("Tone, balance, volume & punch"); tone_box.setLayout(tone)

        lay = QVBoxLayout(self); lay.addWidget(title); lay.addLayout(top); lay.addWidget(bands_box, 1); lay.addWidget(tone_box)

        self.bass_punch.valueChanged.connect(self._punch)
        self.bass.valueChanged.connect(lambda v: self._tone("bass", v)); self.treble.valueChanged.connect(lambda v: self._tone("treble", v))
        self.balance.valueChanged.connect(self._balance); self.volume.valueChanged.connect(self._volume)
        self.mute.toggled.connect(self.eq.set_muted)
        self.reset_b.clicked.connect(self._reset)
        self.preset.activated.connect(self._apply_preset)
        self.save_b.clicked.connect(self._save_as); self.ren_b.clicked.connect(self._rename); self.del_b.clicked.connect(self._delete)
        ctl.song_changed.connect(lambda _: None)
        self._refresh_presets(self.settings.get("eq").get("preset", "Flat"))
        self._sync_from_eq()

    # ---- UI <-> DSP --------------------------------------------------
    def _sync_from_eq(self):
        self._loading = True
        for i, g in enumerate(self.eq.gains):
            self.band_sliders[i].setValue(round(g * 10)); self.band_labels[i].setText(f"{g:+.1f} dB")
        self.bass_punch.setValue(round(getattr(self.eq, "bass_punch", 0.75) * 100))
        self.bass.setValue(round(self.eq.bass_db * 10)); self.treble.setValue(round(self.eq.treble_db * 10))
        self.balance.setValue(round(self.eq.balance * 100)); self.volume.setValue(round(self.eq.volume * 100))
        self.mute.setChecked(self.eq.muted)
        self._loading = False
        self._tone_labels()

    def _tone_labels(self):
        p = self.bass_punch.value()
        self.vals["bass_punch"].setText("Off" if p == 0 else f"{p}% (Punchy)")
        self.vals["bass"].setText(f"{self.bass.value() / 10:+.1f} dB"); self.vals["treble"].setText(f"{self.treble.value() / 10:+.1f} dB")
        b = self.balance.value(); self.vals["balance"].setText("Center" if b == 0 else f"{'R' if b > 0 else 'L'} {abs(b)}%")
        self.vals["volume"].setText(f"{self.volume.value()}%")

    def _punch(self, v):
        self._tone_labels()
        if not self._loading:
            p = v / 100.0
            self.eq.set_bass_punch(p)
            self.settings.set("bass_punch", p)
            if hasattr(self, "ctl") and getattr(self.ctl, "synth", None):
                self.ctl.synth.set_bass_punch(p)
            self._changed()

    def _band(self, i, v):
        self.band_labels[i].setText(f"{v / 10:+.1f} dB")
        if not self._loading:
            self.eq.set_band(i, v / 10); self._changed()

    def _tone(self, which, v):
        self._tone_labels()
        if not self._loading:
            self.eq.set_tone(**{f"{which}_db": v / 10}); self._changed()

    def _balance(self, v):
        self._tone_labels()
        if not self._loading: self.eq.set_balance(v / 100); self._changed()

    def _volume(self, v):
        self._tone_labels()
        if not self._loading: self.eq.set_volume(v / 100); self.settings.set("volume", v / 100)

    def _changed(self):
        self._save.start()

    def _persist(self):
        self.settings.set("eq", {"gains": self.eq.gains, "bass": self.eq.bass_db, "treble": self.eq.treble_db,
                                 "balance": self.eq.balance, "bass_punch": getattr(self.eq, "bass_punch", 0.75),
                                 "preset": self.preset.currentText()})
        self.settings.set("bass_punch", getattr(self.eq, "bass_punch", 0.75))

    # ---- presets -----------------------------------------------------
    def _all_presets(self):
        p = {n: {"gains": g, "bass": 0.0, "treble": 0.0} for n, g in BUILTIN_PRESETS.items()}
        p.update(self.db.list_eq_presets())
        return p

    def _refresh_presets(self, select=None):
        self.preset.blockSignals(True); self.preset.clear()
        for n in BUILTIN_PRESETS: self.preset.addItem(n)
        for n in self.db.list_eq_presets(): self.preset.addItem(n + "  (custom)", n)
        idx = self.preset.findText(select) if select else 0
        for i in range(self.preset.count()):
            if (self.preset.itemData(i) or self.preset.itemText(i)) == select: idx = i
        self.preset.setCurrentIndex(max(0, idx)); self.preset.blockSignals(False)

    def _current_name(self):
        return self.preset.currentData() or self.preset.currentText()

    def _is_custom(self):
        return self.preset.currentData() is not None

    def _apply_preset(self):
        p = self._all_presets().get(self._current_name())
        if p:
            self.eq.set_gains(p["gains"]); self.eq.set_tone(p["bass"], p["treble"]); self._sync_from_eq(); self._persist()

    def _save_as(self):
        name, ok = QInputDialog.getText(self, "Save preset", "Preset name:")
        if ok:
            try:
                self.db.save_eq_preset(name, self.eq.gains, self.eq.bass_db, self.eq.treble_db)
                self._refresh_presets(name.strip()); self._persist()
            except DatabaseError as e: QMessageBox.warning(self, "Preset", str(e))

    def _rename(self):
        if not self._is_custom():
            QMessageBox.information(self, "Preset", "Built-in presets cannot be renamed."); return
        old = self._current_name()
        name, ok = QInputDialog.getText(self, "Rename preset", "New name:", text=old)
        if ok:
            try: self.db.rename_eq_preset(old, name); self._refresh_presets(name.strip())
            except DatabaseError as e: QMessageBox.warning(self, "Preset", str(e))

    def _delete(self):
        if not self._is_custom():
            QMessageBox.information(self, "Preset", "Built-in presets cannot be deleted."); return
        self.db.delete_eq_preset(self._current_name()); self._refresh_presets("Flat")

    def _reset(self):
        self.eq.reset()
        self.eq.set_bass_punch(0.75)
        self.settings.set("bass_punch", 0.75)
        if hasattr(self, "ctl") and getattr(self.ctl, "synth", None):
            self.ctl.synth.set_bass_punch(0.75)
        self.settings.set("volume", self.eq.volume)
        self._refresh_presets("Flat")
        self._sync_from_eq()
        self._persist()
