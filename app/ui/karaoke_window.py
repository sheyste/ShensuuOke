from __future__ import annotations
import os
from PySide6.QtCore import QEvent, QTimer, QUrl, QSizeF, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QGraphicsDropShadowEffect, QGraphicsScene, QGraphicsView,
                               QHBoxLayout, QLabel, QPushButton, QStackedLayout,
                               QVBoxLayout, QWidget)
from app.ui.lyrics_view import LyricsView
from app.ui.remote_panel import RemotePanel

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
except ImportError:  # Multimedia is optional; color backgrounds still work.
    QAudioOutput = QMediaPlayer = QGraphicsVideoItem = None


class _BackgroundVideoView(QGraphicsView):
    def __init__(self, on_resize, parent=None):
        super().__init__(parent)
        self._on_resize = on_resize

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._on_resize:
            self._on_resize()


class KaraokeWindow(QWidget):
    """Full-screen singing view. F11 toggles full screen, Esc leaves it, Space pauses."""
    settings_requested = Signal()

    def __init__(self, ctl, settings, remote=None, parent=None):
        super().__init__(parent)
        self.ctl, self.settings, self.remote = ctl, settings, remote
        self._queued_count = len(ctl.queue.upcoming()) if hasattr(ctl, "queue") else 0
        self._devices_count = remote.connected_devices() if remote and hasattr(remote, "connected_devices") else 0
        self.setWindowTitle("ShensuuOke - Karaoke")
        logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "icons", "logo.png")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))
        self.resize(1280, 760)
        self.setMinimumSize(760, 480)
        self.setMouseTracking(True)
        self.video = None
        self.video_view = None
        self.video_player = None
        self.video_audio = None
        self._video_index = -1
        self._is_song_video = False
        if QGraphicsVideoItem is not None:
            self.video_view = _BackgroundVideoView(self._resize_video, self)
            self.video_view.setFrameStyle(0)
            self.video_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.video_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.video_view.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self.video_view.setStyleSheet("background: transparent; border: 0;")
            scene = QGraphicsScene(self.video_view)
            self.video = QGraphicsVideoItem()
            self.video.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatioByExpanding)
            self.video.nativeSizeChanged.connect(lambda _: self._resize_video())
            scene.addItem(self.video)
            self.video_view.setScene(scene)
            self.video_audio = QAudioOutput(self)
            self.video_audio.setVolume(0.0)
            self.video_player = QMediaPlayer(self)
            self.video_player.setAudioOutput(self.video_audio)
            self.video_player.setVideoOutput(self.video)
            self.video_player.mediaStatusChanged.connect(self._video_status)

        self.title = QLabel("")
        self.title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.title.setStyleSheet("font-size:22px;font-weight:700;color:#ffffff;background:transparent;")

        self.next_song_lbl = QLabel("Up next: —")
        self.next_song_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.next_song_lbl.setStyleSheet("font-size:14px;font-weight:500;color:#ffffff;background:transparent;")

        self.queue_status_lbl = QLabel(f"Queued: {self._queued_count} · Devices: {self._devices_count}")
        self.queue_status_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.queue_status_lbl.setStyleSheet("font-size:13px;font-weight:600;color:#75c7ff;background:transparent;")

        for w in (self.title, self.next_song_lbl, self.queue_status_lbl):
            shadow = QGraphicsDropShadowEffect(w)
            shadow.setBlurRadius(8)
            shadow.setColor(QColor(0, 0, 0, 220))
            shadow.setOffset(0, 1)
            w.setGraphicsEffect(shadow)

        info_box = QWidget()
        info_box.setStyleSheet("background:transparent;")
        info_lay = QVBoxLayout(info_box)
        info_lay.setContentsMargins(0, 0, 0, 0)
        info_lay.setSpacing(3)
        info_lay.addWidget(self.title)
        info_lay.addWidget(self.next_song_lbl)
        info_lay.addWidget(self.queue_status_lbl)
        info_lay.addStretch(1)

        heading = QWidget()
        heading.setStyleSheet("background:transparent;")
        heading_row = QHBoxLayout(heading)
        heading_row.setContentsMargins(14, 8, 14, 0)
        heading_row.addWidget(info_box, 1, Qt.AlignmentFlag.AlignTop)
        heading_row.addStretch(1)
        self.remote_panel = RemotePanel(remote.url, compact=True) if remote else None
        if self.remote_panel:
            heading_row.addWidget(self.remote_panel, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)

        self.lyrics = LyricsView(settings.get("karaoke_font_size"), bottom_margin=48, settings=settings, ctl=ctl)
        self.controls = QWidget(self)
        self.controls.setStyleSheet("background:transparent;")
        self.controls.setFixedHeight(56)
        row = QHBoxLayout(self.controls)
        row.setContentsMargins(0, 0, 0, 8)
        btns = {"⏮": ctl.previous, "⏯": ctl.toggle_play_pause, "⏭": ctl.next, "A−": lambda: self._size(-6),
                "A+": lambda: self._size(6), "Background…": self._bg, "Full screen (F11)": self.toggle_fullscreen, "Settings": self.settings_requested.emit}
        btns.pop(next((key for key in btns if key.startswith("Background")), ""), None)
        row.addStretch(1)
        self.btn_font_dec = None
        self.btn_font_inc = None
        for t, fn in btns.items():
            b = QPushButton(t); b.clicked.connect(fn); b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            if t == "A−":
                self.btn_font_dec = b
            elif t == "A+":
                self.btn_font_inc = b
            row.addWidget(b)
        row.addStretch(1)
        overlay = QWidget(self)
        self.overlay = overlay
        overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        overlay.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(overlay)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(heading, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self.lyrics, 1)
        lay.addWidget(self.controls, 0, Qt.AlignmentFlag.AlignBottom)
        stack = QStackedLayout(self)
        stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        if self.video_view:
            stack.addWidget(self.video_view)
        stack.addWidget(overlay)
        overlay.raise_()
        self._apply_bg(settings.get("karaoke_bg"))
        self._refresh_background_video()
        ctl.song_changed.connect(self._on_song_changed)
        ctl.queue_changed.connect(self._on_queue_changed)
        ctl.state_changed.connect(self._on_state_changed)
        ctl.lyrics_changed.connect(self._on_lyrics_changed)
        ctl.position_changed.connect(self._update_lyrics)
        self._sync_display()

    def _apply_bg(self, color):
        self.setStyleSheet(f"QWidget#kw {{ background:{color}; color:#fff; }} "
                           "QPushButton { background:#262833; border:1px solid #343747; border-radius:8px; padding:7px 14px; } "
                           "QPushButton:hover { background:#30334a; }")
        self.setObjectName("kw")

    def _is_video_song(self, song: dict | None) -> bool:
        if not song:
            return False
        path = song.get("path") or ""
        ext = os.path.splitext(path)[1].lower()
        if ext in (".mp4", ".mkv", ".avi", ".mov", ".webm"):
            return True
        fmt = (song.get("format") or "").upper()
        return fmt in ("MP4", "MKV", "AVI", "MOV", "WEBM", "VIDEO")

    def _play_song_video(self, song: dict):
        if not self.video_player or not self.video:
            return
        path = song.get("path")
        if not path or not os.path.isfile(path):
            self.video_player.stop()
            self.video_view.hide()
            return
        self._is_song_video = True
        self.lyrics.setVisible(True)
        self.lyrics.set_lyrics([], "")
        if self.btn_font_dec:
            self.btn_font_dec.setVisible(False)
        if self.btn_font_inc:
            self.btn_font_inc.setVisible(False)
        self.video.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self.video_view.show()
        self._resize_video()
        url = QUrl.fromLocalFile(path)
        if self.video_player.source() != url:
            self.video_player.setSource(url)
        self.video_player.setPosition(0)
        if self.ctl.state == "playing":
            self.video_player.play()
        else:
            self.video_player.pause()
        self.overlay.raise_()

    def _video_status(self, status):
        if not self.video_player:
            return
        if status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            self._resize_video()
            QTimer.singleShot(60, self._resize_video)
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            if not self._is_song_video:
                self.video_player.setPosition(0)
                self.video_player.play()
            else:
                self.video_player.pause()

    def _update_lyrics(self, position, _duration):
        if not self._is_song_video:
            self.lyrics.set_position(position)
        elif self.video_player and self.ctl.state == "playing":
            target_ms = int(position * 1000)
            cur_ms = self.video_player.position()
            if abs(cur_ms - target_ms) > 250:
                self.video_player.setPosition(target_ms)
            if self.video_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                self.video_player.play()

    def _format_song_title(self, song):
        if not song:
            return ""
        title = song.get("title") or song.get("filename") or ""
        artist = song.get("artist") or ""
        full = f"{title} — {artist}" if (artist and artist.strip() and artist.lower() not in title.lower()) else title
        num = song.get("song_number")
        if not num and hasattr(self.ctl, "db") and song.get("id"):
            num = self.ctl.db.get_song_number(song["id"])
            if num:
                song["song_number"] = num
        if num:
            return f"#{num} - {full}"
        return full

    def _update_next_song(self):
        upcoming = self.ctl.queue.upcoming() if hasattr(self.ctl, "queue") else []
        if upcoming:
            nxt = upcoming[0].song
            nxt_text = self._format_song_title(nxt)
            self.next_song_lbl.setText(f"Up next: {nxt_text}" if nxt_text else "Up next: —")
        else:
            self.next_song_lbl.setText("Up next: —")

    def _update_queue_status(self):
        self._queued_count = len(self.ctl.queue.upcoming()) if hasattr(self.ctl, "queue") else 0
        if self.remote and hasattr(self.remote, "connected_devices"):
            try:
                self._devices_count = self.remote.connected_devices()
            except Exception:
                pass
        self.queue_status_lbl.setText(f"Queued: {self._queued_count} · Devices: {self._devices_count}")
        if self.remote_panel:
            self.remote_panel.set_status(self._queued_count, self._devices_count)

    def _sync_display(self):
        upcoming = self.ctl.queue.upcoming() if hasattr(self.ctl, "queue") else []
        is_active = self.ctl.state in ("playing", "paused", "loading")
        if self.ctl.current and is_active:
            self.title.setText(self._format_song_title(self.ctl.current))
            if self._is_video_song(self.ctl.current):
                self._is_song_video = True
                self.lyrics.setVisible(True)
                self.lyrics.set_lyrics([], "")
                if self.btn_font_dec:
                    self.btn_font_dec.setVisible(False)
                if self.btn_font_inc:
                    self.btn_font_inc.setVisible(False)
            else:
                self._is_song_video = False
                self.lyrics.setVisible(True)
                if self.btn_font_dec:
                    self.btn_font_dec.setVisible(True)
                if self.btn_font_inc:
                    self.btn_font_inc.setVisible(True)
                if self.video:
                    self.video.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatioByExpanding)
                self.lyrics.set_lyrics(self.ctl.current_lyrics, self.ctl.current_lyrics_message)
                self.lyrics.set_position(self.ctl.engine.position)
        else:
            if not upcoming or self.ctl.state == "stopped":
                self.title.setText("")
                self._is_song_video = False
                self.lyrics.setVisible(True)
                if self.btn_font_dec:
                    self.btn_font_dec.setVisible(True)
                if self.btn_font_inc:
                    self.btn_font_inc.setVisible(True)
                if self.video:
                    self.video.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatioByExpanding)
                self.lyrics.set_lyrics([], "Select a song")
        self._update_next_song()
        self._update_queue_status()

    def _on_state_changed(self, state):
        if state == "stopped":
            self._sync_display()
            if self.video_player:
                self.video_player.stop()
                if self._is_song_video:
                    self.video_view.hide()
                    self._is_song_video = False
                    self.lyrics.setVisible(True)
                    if self.btn_font_dec:
                        self.btn_font_dec.setVisible(True)
                    if self.btn_font_inc:
                        self.btn_font_inc.setVisible(True)
                    if self.video:
                        self.video.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatioByExpanding)
            self.controls.setVisible(True)
        elif state == "paused":
            if self.video_player:
                self.video_player.pause()
            self.controls.setVisible(True)
        elif state == "playing":
            if self.video_player:
                if self._is_song_video:
                    if self.video_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                        self.video_player.play()
                elif self.video_player.source().isValid():
                    if self.video_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
                        self.video_player.play()
        elif state == "loading":
            if self.video_player and self._is_song_video:
                self.video_player.pause()
                self.video_player.setPosition(0)
            self.controls.setVisible(True)
        self._update_queue_status()

    def _on_queue_changed(self):
        self._sync_display()

    def _on_song_changed(self, song):
        if song:
            self.title.setText(self._format_song_title(song))
            self._update_next_song()
            self._update_queue_status()
            if self._is_video_song(song):
                self._play_song_video(song)
            else:
                self._is_song_video = False
                self.lyrics.setVisible(True)
                if self.btn_font_dec:
                    self.btn_font_dec.setVisible(True)
                if self.btn_font_inc:
                    self.btn_font_inc.setVisible(True)
                if self.video:
                    self.video.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatioByExpanding)
                self._refresh_background_video(advance=True)
        else:
            self._sync_display()

    def _on_lyrics_changed(self, lyrics, msg):
        if self._is_song_video:
            return
        upcoming = self.ctl.queue.upcoming() if hasattr(self.ctl, "queue") else []
        is_active = self.ctl.state in ("playing", "paused", "loading")
        if not is_active and (not upcoming or self.ctl.state == "stopped"):
            self.lyrics.set_lyrics([], "Select a song")
        else:
            self.lyrics.set_lyrics(lyrics, msg)

    def set_remote_status(self, queued, devices):
        self._queued_count = queued
        self._devices_count = devices
        self.queue_status_lbl.setText(f"Queued: {queued} · Devices: {devices}")
        if self.remote_panel:
            self.remote_panel.set_status(queued, devices)

    def _bg(self):
        # Kept as a harmless compatibility target for older saved layouts;
        # the background control is no longer displayed.
        pass

    def _resize_video(self):
        if not self.video_view or not self.video:
            return
        vp = self.video_view.viewport()
        vp_w = vp.width() if vp else self.video_view.width()
        vp_h = vp.height() if vp else self.video_view.height()
        width = max(1, vp_w, self.video_view.width(), self.width())
        height = max(1, vp_h, self.video_view.height(), self.height())
        if self.video_view.scene():
            self.video_view.scene().setSceneRect(0, 0, width, height)
        self.video_view.setSceneRect(0, 0, width, height)
        self.video.setPos(0, 0)
        self.video.setSize(QSizeF(width, height))

    def _refresh_background_video(self, advance=False):
        if not self.video_player or self._is_song_video:
            return
        folder = self.settings.get("karaoke_video_folder") or ""
        extensions = {".mp4", ".mkv", ".avi", ".mov", ".webm"}
        files = []
        if os.path.isdir(folder):
            files = [os.path.join(folder, name) for name in sorted(os.listdir(folder))
                     if os.path.splitext(name)[1].lower() in extensions
                     and os.path.isfile(os.path.join(folder, name))]
        if files:
            if advance or self._video_index < 0:
                self._video_index = (self._video_index + 1) % len(files)
            else:
                self._video_index %= len(files)
            if self.video:
                self.video.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatioByExpanding)
            self.video_view.show()
            self._resize_video()
            self.video_player.setSource(QUrl.fromLocalFile(files[self._video_index]))
            self.video_player.play()
            self.overlay.raise_()
        else:
            self.video_player.stop()
            self.video_view.hide()

    def _size(self, d):
        self.lyrics.set_font_size(self.lyrics.font_size + d); self.settings.set("karaoke_font_size", self.lyrics.font_size)

    def toggle_fullscreen(self):
        w = self.window()
        w.showNormal() if w.isFullScreen() else w.showFullScreen()
        self.controls.setVisible(True)
        self._resize_video()
        QTimer.singleShot(60, self._resize_video)
        QTimer.singleShot(200, self._resize_video)

    def open_fullscreen(self):
        w = self.window()
        w.showFullScreen()
        self.show()
        self.controls.setVisible(True)
        self._sync_display()
        if not self._is_song_video:
            self._refresh_background_video()
        self._resize_video()
        QTimer.singleShot(60, self._resize_video)
        QTimer.singleShot(200, self._resize_video)

    def open_windowed(self):
        w = self.window()
        if w.isFullScreen():
            w.showNormal()
        self.show()
        self.controls.setVisible(True)
        self._sync_display()
        if not self._is_song_video:
            self._refresh_background_video()
        self._resize_video()
        QTimer.singleShot(60, self._resize_video)
        QTimer.singleShot(200, self._resize_video)

    def showEvent(self, event):
        super().showEvent(event)
        self._resize_video()
        QTimer.singleShot(0, self._resize_video)
        QTimer.singleShot(60, self._resize_video)
        QTimer.singleShot(200, self._resize_video)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._resize_video()
            QTimer.singleShot(60, self._resize_video)
            QTimer.singleShot(200, self._resize_video)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_video()
        QTimer.singleShot(0, self._resize_video)

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key.Key_F11: self.toggle_fullscreen()
        elif k == Qt.Key.Key_Escape:
            w = self.window()
            if w.isFullScreen():
                w.showNormal()
            else:
                self.settings_requested.emit()
        elif k == Qt.Key.Key_Space: self.ctl.toggle_play_pause()
        elif k in (Qt.Key.Key_Plus, Qt.Key.Key_Equal): self._size(6)
        elif k == Qt.Key.Key_Minus: self._size(-6)
        else: super().keyPressEvent(e)
