"""Splash screen for ShensuuOke startup."""
from __future__ import annotations
import os
import time
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel,
    QProgressBar, QSplashScreen, QVBoxLayout
)
from app.version import __version__


def get_rounded_logo(logo_path: str, size: int = 64, radius: int = 14) -> QPixmap:
    src = QPixmap(logo_path).scaled(
        size, size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation
    )
    dest = QPixmap(size, size)
    dest.fill(Qt.GlobalColor.transparent)
    painter = QPainter(dest)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size, size, radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, src)
    painter.setClipping(False)
    painter.setPen(QPen(QColor(255, 255, 255, 45), 1.5))
    painter.drawRoundedRect(0.75, 0.75, size - 1.5, size - 1.5, radius, radius)
    painter.end()
    return dest


class SplashScreen(QSplashScreen):
    """Modern dark-themed splash screen shown while initializing engines, database, and UI."""

    def __init__(self, parent=None):
        pixmap = QPixmap(520, 290)
        pixmap.fill(Qt.GlobalColor.transparent)
        super().__init__(pixmap, Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._start_time = time.time()

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("splash_card")
        card.setStyleSheet("""
            QFrame#splash_card {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #181924, stop:0.5 #12131b, stop:1 #0c0d12);
                border: 1px solid #7c4dff55;
                border-radius: 16px;
            }
        """)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 26, 28, 20)
        card_layout.setSpacing(14)

        # Header: Logo & Branding
        header_row = QHBoxLayout()
        header_row.setSpacing(18)

        logo_lbl = QLabel()
        logo_path = os.path.join(os.path.dirname(__file__), "..", "resources", "icons", "logo.png")
        if os.path.exists(logo_path):
            logo_pix = get_rounded_logo(logo_path, size=64, radius=13)
            logo_lbl.setPixmap(logo_pix)
        else:
            logo_lbl.setText("🎤")
            logo_lbl.setStyleSheet("font-size: 44px;")
        header_row.addWidget(logo_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

        brand_col = QVBoxLayout()
        brand_col.setSpacing(3)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title_lbl = QLabel("ShensuuOke")
        title_lbl.setStyleSheet("font-size: 26px; font-weight: 800; color: #ffffff; letter-spacing: 0.5px;")
        title_row.addWidget(title_lbl)

        ver_badge = QLabel(f"v{__version__}")
        ver_badge.setStyleSheet("""
            background: #28214b;
            color: #c4b5fd;
            border: 1px solid #7c4dff77;
            border-radius: 6px;
            padding: 2px 7px;
            font-size: 11px;
            font-weight: 700;
        """)
        title_row.addWidget(ver_badge)
        title_row.addStretch(1)
        brand_col.addLayout(title_row)

        subtitle_lbl = QLabel("Modern Desktop Karaoke Experience")
        subtitle_lbl.setStyleSheet("font-size: 12px; color: #9ca3af; font-weight: 500;")
        brand_col.addWidget(subtitle_lbl)

        header_row.addLayout(brand_col, 1)
        card_layout.addLayout(header_row)

        # Feature pills
        pills_row = QHBoxLayout()
        pills_row.setSpacing(8)
        for icon_text in ["✨ Video Backgrounds", "⚡ Real-time Lyrics", "📱 Smartphone Remote"]:
            pill = QLabel(icon_text)
            pill.setStyleSheet("""
                background: #1b1c27;
                color: #a1a1aa;
                border: 1px solid #2e303e;
                border-radius: 10px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 500;
            """)
            pills_row.addWidget(pill)
        pills_row.addStretch(1)
        card_layout.addLayout(pills_row)

        card_layout.addStretch(1)

        # Status and Progress
        status_box = QVBoxLayout()
        status_box.setSpacing(6)

        status_header = QHBoxLayout()
        self.status_lbl = QLabel("Starting ShensuuOke…")
        self.status_lbl.setStyleSheet("font-size: 12px; color: #e5e7eb; font-weight: 600;")
        status_header.addWidget(self.status_lbl)

        self.percent_lbl = QLabel("10%")
        self.percent_lbl.setStyleSheet("font-size: 11px; color: #c084fc; font-weight: 700;")
        status_header.addWidget(self.percent_lbl)
        status_box.addLayout(status_header)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(5)
        self.progress.setRange(0, 100)
        self.progress.setValue(10)
        self.progress.setStyleSheet("""
            QProgressBar {
                background: #20222d;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7c4dff, stop:0.5 #a855f7, stop:1 #ec4899);
                border-radius: 2px;
            }
        """)
        status_box.addWidget(self.progress)
        card_layout.addLayout(status_box)

        # Footer row
        footer_row = QHBoxLayout()
        copy_lbl = QLabel("© 2026 ShensuuOke")
        copy_lbl.setStyleSheet("font-size: 10px; color: #6b7280;")
        footer_row.addWidget(copy_lbl)
        footer_row.addStretch(1)

        sys_lbl = QLabel("Powered by FluidSynth & BASS Engine")
        sys_lbl.setStyleSheet("font-size: 10px; color: #6b7280;")
        footer_row.addWidget(sys_lbl)
        card_layout.addLayout(footer_row)

        root_layout.addWidget(card)

    def set_message(self, message: str, percent: int | None = None):
        """Update the displayed status message and optional progress bar percentage."""
        self.status_lbl.setText(message)
        if percent is not None:
            self.progress.setValue(percent)
            self.percent_lbl.setText(f"{percent}%")
        QApplication.processEvents()

    def finish_splash(self, main_win, min_duration: float = 1.0):
        """Ensure splash displays gracefully for min_duration seconds before finishing."""
        elapsed = time.time() - self._start_time
        remaining = max(0.0, min_duration - elapsed)
        self.set_message("Ready!", 100)
        if remaining > 0:
            QTimer.singleShot(int(remaining * 1000), lambda: self._do_finish(main_win))
        else:
            self._do_finish(main_win)

    def _do_finish(self, main_win):
        self.finish(main_win)
        self.deleteLater()
