from __future__ import annotations
import os
from PySide6.QtCore import QByteArray, QTimer, QUrl, Qt
from PySide6.QtWidgets import (QFrame, QGroupBox, QHBoxLayout, QLabel, QListWidget, QMainWindow, QMessageBox,
                               QPushButton, QScrollArea, QSplitter, QStackedWidget, QTabWidget, QVBoxLayout, QWidget)
from PySide6.QtGui import QDesktopServices, QIcon, QKeySequence, QPixmap, QShortcut
from app.services.update_checker import UpdateCheckWorker
from app.ui.equalizer_view import EqualizerView
from app.ui.karaoke_window import KaraokeWindow
from app.ui.lyrics_view import LyricsView
from app.ui.remote_panel import RemotePanel
from app.ui.now_playing import NowPlayingBar, QueuePanel
from app.services.remote_server import RemoteServer
from PySide6.QtCore import QObject, Signal
from app.ui.settings_view import AppSettingsView, AudioSettingsView
from app.ui.lyrics_settings_view import LyricsSettingsView
from app.ui.song_library import LibraryView
from app.ui.soundfont_manager import SoundFontManager
from app.version import __version__


class HomePage(QWidget):
    def __init__(self, db, ctl, go, open_karaoke=None, on_check_update=None):
        super().__init__()
        self.db, self.ctl, self.go, self.open_karaoke = db, ctl, go, open_karaoke
        self.on_check_update = on_check_update

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(28, 24, 28, 28)
        lay.setSpacing(18)

        # 1. Header / Hero section with Logo
        brand_row = QHBoxLayout()
        brand_row.setSpacing(16)

        logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "icons", "logo.png")
        if os.path.exists(logo_path):
            logo_lbl = QLabel()
            pix = QPixmap(logo_path).scaled(68, 68, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_lbl.setPixmap(pix)
            logo_lbl.setFixedSize(68, 68)
            brand_row.addWidget(logo_lbl)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title = QLabel(f"ShensuuOke <span style='font-size: 15px; font-weight: 600; color: #7c4dff;'>v{__version__}</span>")
        title.setObjectName("h1")
        title.setStyleSheet("font-size: 28px; font-weight: 800; color: #ffffff;")

        subtitle = QLabel("High-Performance Desktop Karaoke & MIDI Synthesizer System")
        subtitle.setStyleSheet("color: #aab; font-size: 14px; font-weight: 500;")

        self.stats = QLabel()
        self.stats.setObjectName("muted")
        self.stats.setStyleSheet("color: #7c4dff; font-size: 13px; font-weight: 600;")

        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        title_box.addWidget(self.stats)
        brand_row.addLayout(title_box)
        brand_row.addStretch(1)

        if on_check_update:
            self.update_btn = QPushButton("🔄 Check for Updates")
            self.update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.update_btn.setStyleSheet("padding: 7px 16px; font-weight: 600; border-radius: 8px;")
            self.update_btn.clicked.connect(on_check_update)
            brand_row.addWidget(self.update_btn, 0, Qt.AlignmentFlag.AlignVCenter)

        lay.addLayout(brand_row)

        # 2. Quick Navigation Buttons
        actions_box = QHBoxLayout()
        actions_box.setSpacing(10)

        if open_karaoke:
            karaoke_btn = QPushButton("🎤 Karaoke Screen")
            karaoke_btn.setObjectName("karaoke_btn")
            karaoke_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            karaoke_btn.clicked.connect(open_karaoke)
            actions_box.addWidget(karaoke_btn)

        lib_btn = QPushButton("🎵 Song Library")
        lib_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        lib_btn.clicked.connect(lambda: go(1))
        actions_box.addWidget(lib_btn)

        sf_btn = QPushButton("🎹 SoundFont Manager")
        sf_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sf_btn.clicked.connect(lambda: go(3))
        actions_box.addWidget(sf_btn)

        app_settings_btn = QPushButton("📁 Application Settings")
        app_settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        app_settings_btn.clicked.connect(lambda: go(6))
        actions_box.addWidget(app_settings_btn)

        audio_settings_btn = QPushButton("🔊 Audio Settings")
        audio_settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        audio_settings_btn.clicked.connect(lambda: go(5))
        actions_box.addWidget(audio_settings_btn)

        lyrics_settings_btn = QPushButton("✨ Lyrics Settings")
        lyrics_settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        lyrics_settings_btn.clicked.connect(lambda: go(7))
        actions_box.addWidget(lyrics_settings_btn)

        actions_box.addStretch(1)
        lay.addLayout(actions_box)

        # 3. Getting Started Guide
        guide_group = QGroupBox("Getting Started")
        guide_layout = QVBoxLayout(guide_group)
        guide_layout.setContentsMargins(16, 18, 16, 16)
        guide_layout.setSpacing(12)

        steps = [
            ("1. SoundFont Setup",
             "Navigate to <b>SoundFont Manager</b> and load or activate a SoundFont file (<code>.sf2</code>). This enables rich real-time instrument rendering for MIDI and KAR karaoke tracks."),
            ("2. Manage Library Folders",
             "Head over to <b>Application Settings</b> to configure your song directories. The engine automatically indexes and watches all supported formats (MIDI, KAR, MP3, FLAC, CDG, Video)."),
            ("3. Browse & Queue Songs",
             "Explore and search your library in the <b>Song Library</b> view. Double-click any song to play immediately, or add songs to the live playback queue."),
            ("4. Sing with Karaoke Screen & Remote",
             "Switch to <b>Karaoke Screen</b> (press <code>F11</code> for full screen) to enjoy synchronized lyric coloring and background videos. Guests can scan the on-screen QR code with their smartphones to browse, search, and queue songs remotely!"),
        ]

        for step_title, step_desc in steps:
            step_box = QVBoxLayout()
            step_box.setSpacing(2)
            t_lbl = QLabel(f"<span style='color: #7c4dff; font-weight: bold;'>{step_title}</span>")
            d_lbl = QLabel(f"<span style='color: #d1d5db; line-height: 140%;'>{step_desc}</span>")
            d_lbl.setWordWrap(True)
            step_box.addWidget(t_lbl)
            step_box.addWidget(d_lbl)
            guide_layout.addLayout(step_box)

        lay.addWidget(guide_group)

        # 4. Developer & Credits Section
        credits_group = QGroupBox("Credits & Copyright Attributions")
        credits_layout = QVBoxLayout(credits_group)
        credits_layout.setContentsMargins(16, 18, 16, 16)
        credits_layout.setSpacing(14)

        dev_html = (
            "<div style='margin-bottom: 4px;'>"
            f"<span style='font-size: 15px; font-weight: bold; color: #ffffff;'>ShensuuOke v{__version__}</span><br/>"
            "<span style='font-size: 14px; font-weight: 600; color: #7c4dff;'>Shensuu</span> "
            "<span style='color: #9ca3af;'>— Lead Developer & Creator of ShensuuOke</span>"
            "</div>"
        )
        dev_lbl = QLabel(dev_html)
        dev_lbl.setWordWrap(True)
        credits_layout.addWidget(dev_lbl)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("color: #2a2c38; background-color: #2a2c38; height: 1px; border: none;")
        credits_layout.addWidget(line)

        tools_title = QLabel("<span style='font-size: 14px; font-weight: bold; color: #ffffff;'>Tools & Engine Credits</span>")
        credits_layout.addWidget(tools_title)

        tool_credits = [
            ("FluidSynth",
             "Real-time SoundFont 2 (SF2) software synthesizer engine used for high-fidelity MIDI instrument rendering.",
             "Copyright © Peter Hanappe and the FluidSynth Development Team. Licensed under GNU LGPL v2.1+."),
            ("FFmpeg",
             "Comprehensive multimedia processing framework used for universal audio decoding and karaoke background video playback.",
             "Copyright © FFmpeg Authors / Fabrice Bellard et al. Licensed under GNU LGPL / GPL."),
            ("PySide6 / Qt",
             "Cross-platform graphical user interface application framework.",
             "Copyright © The Qt Company Ltd. and contributors. Licensed under GNU LGPL v3."),
            ("Mido & Python-RtMidi",
             "MIDI stream parsing, timing dispatch, and KAR lyric sequencing engine.",
             "Copyright © Ole Martin Bjørndalen and contributors. Licensed under MIT License.")
        ]

        for name, desc, copy in tool_credits:
            c_box = QVBoxLayout()
            c_box.setSpacing(2)
            header_lbl = QLabel(f"<b style='color: #ffffff;'>{name}</b> — <span style='color: #aab;'>{desc}</span>")
            header_lbl.setWordWrap(True)
            copy_lbl = QLabel(f"<span style='color: #71717a; font-size: 12px;'>{copy}</span>")
            copy_lbl.setWordWrap(True)
            c_box.addWidget(header_lbl)
            c_box.addWidget(copy_lbl)
            credits_layout.addLayout(c_box)

        lay.addWidget(credits_group)
        lay.addStretch(1)

        outer_lay = QVBoxLayout(self)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.addWidget(scroll)
        scroll.setWidget(content)

        ctl.library_changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        count = self.db.count_songs()
        folders = len(self.db.library_folders())
        folder_text = f" across {folders} folder{'s' if folders != 1 else ''}" if folders else ""
        self.stats.setText(f"📁 {count} song{'s' if count != 1 else ''} indexed{folder_text}")


class _RemoteBridge(QObject):
    queue_requested = Signal(object)
    control_requested = Signal(str)
    queue_action_requested = Signal(str, int)


class MainWindow(QMainWindow):
    NAV = ["Home", "Song Library", "Recently Played", "SoundFont Manager", "Equalizer",
           "Audio Settings", "Application Settings", "Lyrics Settings"]

    def __init__(self, db, settings, ctl):
        super().__init__()
        self.db, self.settings, self.ctl = db, settings, ctl
        self.db.clear_recently_played()
        self.setWindowTitle(f"ShensuuOke v{__version__}"); self.resize(1280, 800); self.setMinimumSize(900, 600)
        logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "icons", "logo.png")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))
        self.side = QListWidget(); self.side.setObjectName("sidebar"); self.side.setFixedWidth(210)
        self.side.addItems(self.NAV)
        self.stack = QStackedWidget()
        self.home_page = HomePage(db, ctl, self.side.setCurrentRow, open_karaoke=self._open_karaoke,
                                  on_check_update=self._check_updates_manual)
        self.pages = [self.home_page,
                      LibraryView(db, settings, ctl, "library"),
                      LibraryView(db, settings, ctl, "recent"), SoundFontManager(db, settings, ctl),
                      EqualizerView(db, settings, ctl), AudioSettingsView(db, settings, ctl),
                      AppSettingsView(db, settings, ctl), LyricsSettingsView(db, settings, ctl)]
        for p in self.pages: self.stack.addWidget(p)

        self.queue_panel = QueuePanel(ctl); self.lyrics = LyricsView(22, settings=settings, ctl=ctl)
        self.lyrics.set_lyrics([], "Nothing playing.")
        self.remote_bridge = _RemoteBridge(self)
        self.remote_bridge.queue_requested.connect(self._queue_from_remote)
        self.remote_bridge.control_requested.connect(self._control_from_remote)
        self.remote_bridge.queue_action_requested.connect(self.ctl.queue_action)
        self.remote = RemoteServer(db, self.remote_bridge.queue_requested.emit,
                                   queue_count_callback=lambda: len(self.ctl.queue.upcoming()),
                                   control_callback=self.remote_bridge.control_requested.emit,
                                   queue_snapshot_callback=self._queue_snapshot,
                                   queue_action_callback=self.remote_bridge.queue_action_requested.emit,
                                   status_callback=lambda: {
                                       "state": self.ctl.state,
                                       "title": ((self.ctl.current or {}).get("title") or
                                                 (self.ctl.current or {}).get("filename") or "")})
        try:
            self.remote.start()
            self.remote_panel = RemotePanel(self.remote.url)
            lyrics_page = QWidget(); lyrics_layout = QVBoxLayout(lyrics_page)
            lyrics_layout.setContentsMargins(0, 0, 0, 0)
            lyrics_layout.addWidget(self.remote_panel); lyrics_layout.addWidget(self.lyrics, 1)
        except OSError:
            self.remote = None
            self.remote_panel = None
            lyrics_page = self.lyrics
        self.remote_timer = QTimer(self)
        self.remote_timer.timeout.connect(self._refresh_remote_status)
        self.remote_timer.start(2000)
        self.right = QTabWidget(); self.right.addTab(lyrics_page, "Lyrics"); self.right.addTab(self.queue_panel, "Queue")
        self.right.setMinimumWidth(280)
        split = QSplitter(); split.addWidget(self.stack); split.addWidget(self.right); split.setStretchFactor(0, 1)
        split.setSizes([900, 340]); split.setCollapsible(0, False)

        self.now = NowPlayingBar(ctl)
        body = QWidget(); bl = QHBoxLayout(body); bl.setContentsMargins(0, 0, 0, 0); bl.setSpacing(0)
        bl.addWidget(self.side); bl.addWidget(split, 1)
        root = QWidget(); rl = QVBoxLayout(root); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(0)
        rl.addWidget(body, 1); rl.addWidget(self.now)
        self.workspace = root

        self.karaoke = KaraokeWindow(self.ctl, self.settings, self.remote, parent=self)
        self.karaoke.settings_requested.connect(self._show_settings)

        self.window_stack = QStackedWidget()
        self.window_stack.addWidget(self.karaoke)
        self.window_stack.addWidget(self.workspace)
        self.setCentralWidget(self.window_stack)

        self.f11_shortcut = QShortcut(QKeySequence(Qt.Key.Key_F11), self)
        self.f11_shortcut.activated.connect(self._toggle_karaoke_fullscreen)

        self.f1_shortcut = QShortcut(QKeySequence(Qt.Key.Key_F1), self)
        self.f1_shortcut.activated.connect(self._on_f1_pressed)

        self.side.currentRowChanged.connect(self._nav)
        self.side.setCurrentRow(1)
        self.now.karaoke_requested.connect(self._open_karaoke)
        ctl.lyrics_changed.connect(self.lyrics.set_lyrics)
        ctl.position_changed.connect(lambda p, d: self.lyrics.set_position(p))
        ctl.error.connect(self._error)
        ctl.state_changed.connect(lambda s: self.statusBar().showMessage({"playing": "Playing", "paused": "Paused", "stopped": "Stopped", "loading": "Loading…"}[s], 4000))
        g = settings.get("geometry")
        if g: self.restoreGeometry(QByteArray.fromBase64(g.encode()))

        # Default to karaoke view on startup
        self._open_karaoke_default()

        # Check for updates in background on startup
        self._startup_update_worker = None
        QTimer.singleShot(3000, self._check_startup_updates)

    def _check_startup_updates(self):
        self._startup_update_worker = UpdateCheckWorker(repo="sheyste/ShensuuOke", parent=self)
        self._startup_update_worker.finished_check.connect(self._on_startup_update_finished)
        self._startup_update_worker.start()

    def _on_startup_update_finished(self, res: dict):
        # On startup, only prompt if there is actually an update; don't bother the user if up to date or network error
        if res.get("has_update"):
            self._on_manual_update_finished(res)

    def _check_updates_manual(self):
        if hasattr(self, "_manual_update_worker") and self._manual_update_worker and self._manual_update_worker.isRunning():
            return
        if hasattr(self.home_page, "update_btn"):
            self.home_page.update_btn.setEnabled(False)
            self.home_page.update_btn.setText("Checking…")
        self.statusBar().showMessage("Checking GitHub for updates…", 4000)
        self._manual_update_worker = UpdateCheckWorker(repo="sheyste/ShensuuOke", parent=self)
        self._manual_update_worker.finished_check.connect(self._on_manual_update_finished)
        self._manual_update_worker.start()

    def _on_manual_update_finished(self, res: dict):
        if hasattr(self.home_page, "update_btn"):
            self.home_page.update_btn.setEnabled(True)
            self.home_page.update_btn.setText("🔄 Check for Updates")

        if res.get("error"):
            self.statusBar().showMessage(f"Update check failed: {res['error']}", 6000)
            QMessageBox.warning(self, "Update Check", f"Could not check for updates:\n{res['error']}")
            return

        if res.get("has_update"):
            latest = res.get("latest_version")
            curr = res.get("current_version")
            url = res.get("download_url") or res.get("release_url")
            body = res.get("body", "")
            
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Information)
            box.setWindowTitle("ShensuuOke Update Available")
            box.setText(f"<h3>A new release of ShensuuOke is available!</h3>"
                        f"<b>Latest Version:</b> v{latest}<br/>"
                        f"<b>Current Version:</b> v{curr}<br/>")
            if body:
                box.setDetailedText(body)
            dl_btn = box.addButton("Download Update", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() == dl_btn and url:
                QDesktopServices.openUrl(QUrl(url))
        else:
            QMessageBox.information(
                self,
                "Up to Date",
                f"<h3>ShensuuOke is up to date!</h3>"
                f"You are running the latest version: <b>v{__version__}</b>"
            )

    def _nav(self, row):
        self.stack.setCurrentIndex(row)
        w = self.pages[row]
        for m in ("refresh", "reload"):
            if hasattr(w, m): getattr(w, m)(); break

    def _queue_from_remote(self, song):
        self.ctl.enqueue([song])
        self.statusBar().showMessage(f"Queued from phone: {song['title'] or song['filename']}", 5000)

    def _control_from_remote(self, action):
        if action == "next":
            self.ctl.next()
        elif action == "pause":
            self.ctl.toggle_play_pause()

    def _queue_snapshot(self):
        """Called from the HTTP thread: only reads a copy of the queue."""
        def row(it):
            s = it.song
            return {"uid": it.uid, "title": s.get("title") or s.get("filename") or "",
                    "artist": s.get("artist") or ""}
        q = self.ctl.queue
        cur = q.current()
        return {"current": row(cur) if cur else None, "upcoming": [row(it) for it in list(q.upcoming())]}

    def _refresh_remote_status(self):
        if not self.remote:
            return
        queued = len(self.ctl.queue.upcoming())
        devices = self.remote.connected_devices()
        if self.remote_panel:
            self.remote_panel.set_status(queued, devices)
        if self.karaoke:
            self.karaoke.set_remote_status(queued, devices)

    def _open_karaoke(self):
        self.statusBar().hide()
        self.window_stack.setCurrentWidget(self.karaoke)
        self.karaoke.open_fullscreen()

    def _open_karaoke_default(self):
        self.statusBar().hide()
        self.window_stack.setCurrentWidget(self.karaoke)
        self.karaoke.open_windowed()

    def _toggle_karaoke_fullscreen(self):
        if self.window_stack.currentWidget() == self.karaoke:
            self.karaoke.toggle_fullscreen()
        else:
            self._open_karaoke()

    def show_karaoke_startup(self):
        """Show the karaoke view first, while keeping this interface available."""
        self._open_karaoke_default()

    def _on_f1_pressed(self):
        if self.window_stack.currentWidget() == self.karaoke:
            self._show_settings()
        else:
            self._open_karaoke()

    def _show_settings(self):
        if self.isFullScreen():
            self.showNormal()
            self.showMaximized()
        self.window_stack.setCurrentWidget(self.workspace)
        self.statusBar().show()

    def _error(self, msg):
        self.statusBar().showMessage(msg.splitlines()[0], 8000)
        QMessageBox.warning(self, "ShensuuOke", msg)

    def closeEvent(self, e):
        self.settings.set("geometry", bytes(self.saveGeometry().toBase64()).decode())
        if self.remote: self.remote.stop()
        self.ctl.shutdown(); self.db.close()
        super().closeEvent(e)
