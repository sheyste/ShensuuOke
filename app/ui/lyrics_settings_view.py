from __future__ import annotations
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QColorDialog, QFrame, QGroupBox, QHBoxLayout,
                               QLabel, QPushButton, QSlider, QVBoxLayout, QWidget)
from app.ui.lyrics_view import LyricsView
from app.utils.lyrics import LyricEvent

PRESET_COLORS = [
    ("Sky Blue (Default)", "#5fb7ff"),
    ("Neon Cyan", "#00e5ff"),
    ("Emerald Green", "#00e676"),
    ("KTV Gold", "#ffd54f"),
    ("Radiant Orange", "#ff9100"),
    ("Neon Pink", "#ff4081"),
    ("Vivid Violet", "#b388ff"),
    ("Ruby Red", "#ff5252"),
]


class LyricsSettingsView(QWidget):
    def __init__(self, db, settings, ctl, parent=None):
        super().__init__(parent)
        self.db, self.settings, self.ctl = db, settings, ctl

        current_color = self.settings.get("lyrics_highlight_color") or "#5fb7ff"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 28)
        lay.setSpacing(18)

        # 1. Header
        title = QLabel("Lyrics Settings")
        title.setObjectName("h1")
        subtitle = QLabel("Customize the appearance, highlight colors, and timing of karaoke lyrics.")
        subtitle.setStyleSheet("color: #aab; font-size: 14px; margin-bottom: 4px;")
        lay.addWidget(title)
        lay.addWidget(subtitle)

        # 2. Highlight Color Box
        color_box = QGroupBox("Lyrics Highlight Color")
        color_layout = QVBoxLayout(color_box)
        color_layout.setSpacing(14)

        desc = QLabel("Select the color used to smoothly sweep and highlight lyrics as they are sung:")
        desc.setStyleSheet("color: #cfd8dc; font-size: 13px;")
        color_layout.addWidget(desc)

        # Presets Row
        presets_layout = QHBoxLayout()
        presets_layout.setSpacing(10)
        self._preset_buttons = []

        for name, hex_val in PRESET_COLORS:
            btn = QPushButton(name)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: #1e202c;
                    color: #ffffff;
                    border: 2px solid #2e3244;
                    border-radius: 8px;
                    padding: 8px 14px;
                    font-weight: 600;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    border-color: {hex_val};
                    background: #26293a;
                }}
            """)
            btn.clicked.connect(lambda _, c=hex_val: self._apply_color(c))
            presets_layout.addWidget(btn)
            self._preset_buttons.append((btn, hex_val))

        presets_layout.addStretch(1)
        color_layout.addLayout(presets_layout)

        # Custom picker row
        custom_row = QHBoxLayout()
        custom_row.setSpacing(12)

        self.swatch = QFrame()
        self.swatch.setFixedSize(36, 36)
        self.swatch.setStyleSheet(f"background: {current_color}; border-radius: 6px; border: 2px solid #ffffff;")

        self.hex_label = QLabel(current_color.upper())
        self.hex_label.setStyleSheet("font-family: monospace; font-size: 15px; font-weight: bold; color: #ffffff;")

        custom_btn = QPushButton("🎨 Pick Custom Color…")
        custom_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        custom_btn.setStyleSheet("""
            QPushButton {
                background: #7c4dff;
                color: #ffffff;
                font-weight: bold;
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background: #651fff;
            }
        """)
        custom_btn.clicked.connect(self._pick_custom_color)

        reset_btn = QPushButton("↺ Reset to Default")
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setStyleSheet("""
            QPushButton {
                background: #2b2e3e;
                color: #cfd8dc;
                border: 1px solid #3d4257;
                border-radius: 8px;
                padding: 8px 14px;
            }
            QPushButton:hover {
                background: #363a4e;
                color: #ffffff;
            }
        """)
        reset_btn.clicked.connect(lambda: self._apply_color("#5fb7ff"))

        custom_row.addWidget(self.swatch)
        custom_row.addWidget(self.hex_label)
        custom_row.addWidget(custom_btn)
        custom_row.addWidget(reset_btn)
        custom_row.addStretch(1)
        color_layout.addLayout(custom_row)

        lay.addWidget(color_box)

        # 3. Karaoke Font Size Box
        font_box = QGroupBox("Karaoke Screen Font Size")
        font_layout = QHBoxLayout(font_box)
        font_layout.setSpacing(14)

        cur_font_size = int(self.settings.get("karaoke_font_size") or 54)
        self.font_slider = QSlider(Qt.Orientation.Horizontal)
        self.font_slider.setRange(24, 96)
        self.font_slider.setValue(cur_font_size)
        self.font_slider.setFixedWidth(300)

        self.font_val_label = QLabel(f"{cur_font_size} px")
        self.font_val_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #7c4dff;")

        self.font_slider.valueChanged.connect(self._on_font_size_changed)

        font_layout.addWidget(QLabel("Default font size:"))
        font_layout.addWidget(self.font_slider)
        font_layout.addWidget(self.font_val_label)
        font_layout.addStretch(1)

        lay.addWidget(font_box)

        # 4. Highlight Timing Advance Box
        timing_box = QGroupBox("Highlight Timing Advance")
        timing_layout = QHBoxLayout(timing_box)
        timing_layout.setSpacing(14)

        cur_offset_ms = int(round(float(self.settings.get("lyrics_highlight_offset") or 0.15) * 1000))
        self.timing_slider = QSlider(Qt.Orientation.Horizontal)
        self.timing_slider.setRange(0, 500)
        self.timing_slider.setSingleStep(25)
        self.timing_slider.setValue(cur_offset_ms)
        self.timing_slider.setFixedWidth(300)

        self.timing_val_label = QLabel(f"+{cur_offset_ms} ms")
        self.timing_val_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #7c4dff;")

        self.timing_slider.valueChanged.connect(self._on_timing_changed)

        reset_timing_btn = QPushButton("↺ Reset")
        reset_timing_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_timing_btn.setStyleSheet("""
            QPushButton {
                background: #2b2e3e;
                color: #cfd8dc;
                border: 1px solid #3d4257;
                border-radius: 8px;
                padding: 6px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #363a4e;
                color: #ffffff;
            }
        """)
        reset_timing_btn.clicked.connect(self._reset_timing)

        timing_layout.addWidget(QLabel("Advance lead time:"))
        timing_layout.addWidget(self.timing_slider)
        timing_layout.addWidget(self.timing_val_label)
        timing_layout.addWidget(reset_timing_btn)
        timing_desc = QLabel("(Starts highlight slightly before the note so you can anticipate lyrics)")
        timing_desc.setStyleSheet("color: #aab; font-size: 12px;")
        timing_layout.addWidget(timing_desc)
        timing_layout.addStretch(1)

        lay.addWidget(timing_box)

        # 5. Live Interactive Preview Box
        preview_box = QGroupBox("Live Karaoke Preview")
        preview_layout = QVBoxLayout(preview_box)
        preview_layout.setContentsMargins(16, 16, 16, 16)

        preview_container = QFrame()
        preview_container.setFixedHeight(180)
        preview_container.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #12141c, stop:1 #1c1f2e);
                border: 1px solid #2e3248;
                border-radius: 10px;
            }
        """)
        pc_layout = QVBoxLayout(preview_container)
        pc_layout.setContentsMargins(0, 0, 0, 0)

        self.preview_lyrics = LyricsView(font_size=32, parent=preview_container, settings=settings)
        pc_layout.addWidget(self.preview_lyrics)
        preview_layout.addWidget(preview_container)

        lay.addWidget(preview_box, 1)

        # Setup sample lyrics in preview
        sample_events = [
            LyricEvent(0.5, "Shen"),
            LyricEvent(1.1, "suu"),
            LyricEvent(1.6, "Oke "),
            LyricEvent(2.2, "Ka"),
            LyricEvent(2.7, "ra"),
            LyricEvent(3.1, "o"),
            LyricEvent(3.5, "ke!"),
            LyricEvent(4.5, "Sing ", new_line=True),
            LyricEvent(5.1, "with "),
            LyricEvent(5.7, "smooth "),
            LyricEvent(6.3, "high"),
            LyricEvent(6.9, "light!"),
        ]
        self.preview_lyrics.set_lyrics(sample_events)
        self.preview_lyrics.set_state("playing")

        self._preview_time = 0.0
        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(20)  # 50 FPS
        self._preview_timer.timeout.connect(self._tick_preview)

        self._update_ui_state(current_color)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._preview_timer.isActive():
            self._preview_timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        if self._preview_timer.isActive():
            self._preview_timer.stop()

    def _tick_preview(self):
        self._preview_time += 0.02
        if self._preview_time > 8.0:
            self._preview_time = 0.0
        self.preview_lyrics.set_position(self._preview_time)

    def _apply_color(self, hex_val: str):
        hex_clean = hex_val.strip()
        self.settings.set("lyrics_highlight_color", hex_clean)
        self.preview_lyrics.set_highlight_color(hex_clean)
        self._update_ui_state(hex_clean)

    def _update_ui_state(self, hex_val: str):
        self.swatch.setStyleSheet(f"background: {hex_val}; border-radius: 6px; border: 2px solid #ffffff;")
        self.hex_label.setText(hex_val.upper())
        for btn, h in self._preset_buttons:
            if h.lower() == hex_val.lower():
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: #2a2e42;
                        color: #ffffff;
                        border: 2px solid {h};
                        border-radius: 8px;
                        padding: 8px 14px;
                        font-weight: bold;
                        font-size: 12px;
                    }}
                """)
            else:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: #1e202c;
                        color: #ffffff;
                        border: 2px solid #2e3244;
                        border-radius: 8px;
                        padding: 8px 14px;
                        font-weight: 600;
                        font-size: 12px;
                    }}
                    QPushButton:hover {{
                        border-color: {h};
                        background: #26293a;
                    }}
                """)

    def _pick_custom_color(self):
        cur = QColor(self.settings.get("lyrics_highlight_color") or "#5fb7ff")
        chosen = QColorDialog.getColor(cur, self, "Select Lyrics Highlight Color")
        if chosen.isValid():
            self._apply_color(chosen.name())

    def _on_font_size_changed(self, val):
        self.font_val_label.setText(f"{val} px")
        self.settings.set("karaoke_font_size", val)

    def _on_timing_changed(self, val):
        self.timing_val_label.setText(f"+{val} ms")
        offset_sec = round(val / 1000.0, 3)
        self.settings.set("lyrics_highlight_offset", offset_sec)
        self.preview_lyrics.highlight_offset = offset_sec

    def _reset_timing(self):
        self.timing_slider.setValue(150)
        self._on_timing_changed(150)



