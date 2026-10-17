from __future__ import annotations
import os
from PySide6.QtWidgets import (QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QMessageBox, QPushButton, QVBoxLayout, QWidget)


class AudioSettingsView(QWidget):
    def __init__(self, db, settings, ctl, parent=None):
        super().__init__(parent)
        self.settings, self.ctl = settings, ctl
        title = QLabel("Audio Settings"); title.setObjectName("h1")
        self.dev = QComboBox(); self.dev.setMinimumWidth(380)
        self.current = QLabel(); self.current.setObjectName("muted")
        apply_b, test_b, refresh_b = QPushButton("Use this device"), QPushButton("Test output (440 Hz tone)"), QPushButton("Refresh")
        r = QHBoxLayout(); r.addWidget(self.dev, 1); r.addWidget(refresh_b); r.addWidget(apply_b)
        box = QGroupBox("Output device"); bl = QVBoxLayout(box); bl.addLayout(r); bl.addWidget(self.current); bl.addWidget(test_b)

        self.ff, self.fs = QLineEdit(settings.get("ffmpeg_path")), QLineEdit(settings.get("fluidsynth_dll_dir"))
        self.ff.setPlaceholderText("Leave empty to use ffmpeg from PATH"); self.fs.setPlaceholderText("Folder containing libfluidsynth-3.dll (optional)")
        ffb, fsb = QPushButton("Browse…"), QPushButton("Browse…")
        paths = QGroupBox("Native dependencies"); pl = QVBoxLayout(paths)
        for lab, edit, btn in (("FFmpeg executable:", self.ff, ffb), ("FluidSynth DLL folder (restart required):", self.fs, fsb)):
            pl.addWidget(QLabel(lab)); row = QHBoxLayout(); row.addWidget(edit, 1); row.addWidget(btn); pl.addLayout(row)
        self.check = QLabel(); pl.addWidget(self.check)
        check_b = QPushButton("Save && check"); pl.addWidget(check_b)

        lay = QVBoxLayout(self); lay.addWidget(title); lay.addWidget(box); lay.addWidget(paths); lay.addStretch(1)
        refresh_b.clicked.connect(self.refresh_devices); apply_b.clicked.connect(self._apply); test_b.clicked.connect(self._test)
        ffb.clicked.connect(lambda: self._browse(self.ff, False)); fsb.clicked.connect(lambda: self._browse(self.fs, True))
        check_b.clicked.connect(self._check)
        self.refresh_devices()

    def refresh_devices(self):
        self.dev.clear(); self.dev.addItem("System default", None)
        try:
            import sounddevice as sd
            for i, d in enumerate(sd.query_devices()):
                if d["max_output_channels"] > 0:
                    self.dev.addItem(f"{d['name']}  (#{i})", i)
        except Exception as e:
            self.dev.addItem(f"Devices unavailable: {e}", None)
        saved = self.settings.get("audio_device")
        for i in range(self.dev.count()):
            if self.dev.itemData(i) == saved: self.dev.setCurrentIndex(i)
        self.current.setText(f"Currently using: {self.ctl.device_name()}")

    def _apply(self):
        if self.ctl.set_output_device(self.dev.currentData()):
            self.current.setText(f"Currently using: {self.ctl.device_name()}")

    def _test(self):
        if self.ctl.state == "playing":
            QMessageBox.information(self, "Test output", "Stop playback first."); return
        self.ctl.stop(); self.ctl.engine.test_tone(1.0)

    def _browse(self, edit, folder):
        p = QFileDialog.getExistingDirectory(self, "Select folder") if folder else QFileDialog.getOpenFileName(self, "Select ffmpeg", "", "Executables (*.exe);;All (*)")[0]
        if p: edit.setText(p)

    def _check(self):
        self.settings.set("ffmpeg_path", self.ff.text().strip()); self.settings.set("fluidsynth_dll_dir", self.fs.text().strip())
        from app.audio.audio_decoder import find_ffmpeg, DecodeError
        try: ff = f"FFmpeg OK: {find_ffmpeg(self.ff.text().strip() or None)}"
        except DecodeError as e: ff = f"FFmpeg: {e}"
        self.check.setText(ff + "\nFluidSynth is verified the first time a MIDI file is played.")


class AppSettingsView(QWidget):
    def __init__(self, db, settings, ctl, parent=None):
        super().__init__(parent)
        self.db, self.settings, self.ctl = db, settings, ctl
        self.w = None
        title = QLabel("Application Settings"); title.setObjectName("h1")
        self.folders = QListWidget()
        self.add_b = QPushButton("Add library folder…")
        self.rm_b = QPushButton("Remove folder")
        self.scan_b = QPushButton("Rescan library")
        row = QHBoxLayout()
        for b in (self.add_b, self.rm_b, self.scan_b): row.addWidget(b)
        box = QGroupBox("Library folders (removing a folder never deletes files)"); bl = QVBoxLayout(box); bl.addWidget(self.folders); bl.addLayout(row)
        self.video_folder = QLineEdit(settings.get("karaoke_video_folder"))
        self.video_folder.setPlaceholderText("Optional folder containing karaoke background videos")
        video_browse = QPushButton("Browse")
        video_save = QPushButton("Save")
        video_row = QHBoxLayout(); video_row.addWidget(self.video_folder, 1); video_row.addWidget(video_browse); video_row.addWidget(video_save)
        video_box = QGroupBox("Karaoke background videos")
        video_layout = QVBoxLayout(video_box)
        video_layout.addWidget(QLabel("Folder containing karaoke background videos."))
        video_layout.addLayout(video_row)
        self.info = QLabel(f"Database: schema v{db.version}"); self.info.setObjectName("muted")
        lay = QVBoxLayout(self); lay.addWidget(title); lay.addWidget(box, 1); lay.addWidget(video_box); lay.addWidget(self.info)
        self.add_b.clicked.connect(self._add); self.rm_b.clicked.connect(self._rm); self.scan_b.clicked.connect(self._rescan)
        video_browse.clicked.connect(self._browse_video_folder); video_save.clicked.connect(self._save_video_folder)
        self.refresh()

    def refresh(self):
        self.folders.clear(); self.folders.addItems(self.db.library_folders())

    def _add(self):
        p = QFileDialog.getExistingDirectory(self, "Add library folder")
        if p:
            self.db.add_library_folder(p); self.refresh(); self._run("folder", [p])

    def _rm(self):
        it = self.folders.currentItem()
        if it: self.db.remove_library_folder(it.text()); self.refresh()

    def _rescan(self):
        self._run("rescan", [])

    def _browse_video_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Select karaoke background video folder", self.video_folder.text())
        if path:
            self.video_folder.setText(path)

    def _save_video_folder(self):
        path = self.video_folder.text().strip()
        if path and not os.path.isdir(path):
            QMessageBox.warning(self, "Background videos", "That folder does not exist.")
            return
        self.settings.set("karaoke_video_folder", path)
        self.info.setText("Karaoke background video folder saved.")

    def _run(self, mode, paths):
        from app.services.scan_worker import ScanWorker
        if self.w and self.w.isRunning():
            self.info.setText("A scan is already running…")
            return
        self._set_buttons_enabled(False)
        self.w = ScanWorker(self.db, mode, paths, self)
        self.w.progress.connect(lambda n, p: self.info.setText(f"Scanning… {n}: {os.path.basename(p)}"))
        self.w.finished_scan.connect(self._scan_done)
        self.w.failed.connect(lambda e: (self._set_buttons_enabled(True), QMessageBox.warning(self, "Scan failed", e)))
        self.info.setText("Scanning…")
        self.w.start()

    def _set_buttons_enabled(self, enabled: bool):
        for b in (self.add_b, self.rm_b, self.scan_b):
            b.setEnabled(enabled)

    def _scan_done(self, res):
        self._set_buttons_enabled(True)
        self.info.setText(res.summary())
        self.ctl.library_changed.emit()
        if res.errors:
            box = QMessageBox(QMessageBox.Icon.Warning, "Some files had problems",
                              f"{len(res.errors)} file(s) could not be imported or read. They are listed below.", parent=self)
            box.setDetailedText("\n".join(f"{p}\n    → {m}" for p, m in res.errors))
            box.exec()
