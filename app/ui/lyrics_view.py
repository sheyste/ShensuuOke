from __future__ import annotations
import html
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QLabel, QVBoxLayout, QWidget
from app.utils.lyrics import build_lines, locate

HIGHLIGHT, DONE, UPCOMING = "#5fb7ff", "#ffffff", "#ffffff"


class LyricsView(QWidget):
    """Traditional karaoke display: the current line and the next line."""
    def __init__(self, font_size=24, parent=None, bottom_margin=0):
        super().__init__(parent)
        self.font_size = font_size
        self._bottom_margin = bottom_margin
        self.lines: list = []
        self._key = None
        self._message = "Select a song"
        self.label = QLabel(self._message)
        alignment = (Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter
                     if bottom_margin else Qt.AlignmentFlag.AlignCenter)
        self.label.setAlignment(alignment)
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.TextFormat.RichText)
        self.label.setStyleSheet("background: transparent;")
        outline = QGraphicsDropShadowEffect(self.label)
        outline.setBlurRadius(50)
        outline.setColor(QColor("#000000"))
        outline.setOffset(0, 0)
        self.label.setGraphicsEffect(outline)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, bottom_margin)
        lay.addWidget(self.label)
        self._render(-1, -1)

    def set_font_size(self, n):
        self.font_size = max(12, min(160, n))
        key = self._key or (-1, -1)
        self._render(*key)

    def set_lyrics(self, events, message=""):
        self.lines = build_lines(events or [])
        self._message = message or "No lyrics available."
        self._key = None
        self._render(-1, -1)

    def set_position(self, t: float):
        li, si = locate(self.lines, t)
        if (li, si) != self._key:
            self._render(li, si)

    def _line_html(self, line, sung_upto, size, dim=False):
        out = []
        for i, e in enumerate(line):
            color = UPCOMING if dim else (HIGHLIGHT if i <= sung_upto else DONE)
            out.append(f'<span style="color:{color};font-weight:700;">{html.escape(e.text)}</span>')
        return f'<div style="font-size:{size}px;font-weight:700;">{"".join(out)}</div>'

    def _render(self, li, si):
        self._key = (li, si)
        if not self.lines:
            self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.label.setText(f'<div style="font-size:{max(20, self.font_size // 2)}px;font-weight:600;color:{UPCOMING};">'
                               f'{html.escape(self._message)}</div>')
            return
        alignment = (Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter
                     if self._bottom_margin else Qt.AlignmentFlag.AlignCenter)
        self.label.setAlignment(alignment)
        s = self.font_size
        parts = []
        if li < 0:   # intro: show the first two lines dimmed
            parts = [self._line_html(l, -1, s, dim=True)
                     for i, l in enumerate(self.lines[:2])]
        else:
            # Keep two fixed screen positions. Even-numbered lines use the
            # top slot and odd-numbered lines use the bottom slot; finishing
            # one line replaces only that slot, so the other line never moves.
            top = li if li % 2 == 0 else li + 1
            bottom = li + 1 if li % 2 == 0 else li
            if top < len(self.lines):
                parts.append(self._line_html(self.lines[top], si if li == top else -1,
                                             s, dim=li != top))
            if bottom < len(self.lines):
                parts.append(self._line_html(self.lines[bottom], si if li == bottom else -1,
                                             s, dim=li != bottom))
        self.label.setText("<br>".join(parts))
