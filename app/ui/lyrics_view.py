import html
import os
from pathlib import Path
import sys
import time
from PySide6.QtCore import QRectF, QTimer, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget
from app.utils.lyrics import build_lines, locate

HIGHLIGHT, DONE, UPCOMING = "#5fb7ff", "#ffffff", "#ffffff"


def _get_countdown_pixmaps() -> dict[int, QPixmap]:
    roots = []
    if getattr(sys, "_MEIPASS", None):
        roots.append(Path(sys._MEIPASS) / "app" / "resources" / "countdown")
    roots.append(Path(__file__).resolve().parent.parent / "resources" / "countdown")
    pixmaps = {}
    for num in (4, 3, 2, 1):
        for root in roots:
            p = root / f"{num}.png"
            if p.is_file():
                pix = QPixmap(str(p))
                if not pix.isNull():
                    pixmaps[num] = pix
                    break
    return pixmaps


class _KaraokeLabel(QLabel):
    def __init__(self, owner: LyricsView):
        super().__init__()
        self.owner = owner
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, event):
        self.owner._paint_lyrics(self)


class LyricsView(QWidget):
    """High-performance vector karaoke display with cached pixmap rendering."""
    def __init__(self, font_size=24, parent=None, bottom_margin=0, settings=None, ctl=None):
        super().__init__(parent)
        self.font_size = font_size
        self._bottom_margin = bottom_margin
        self.settings = settings
        self.ctl = ctl
        self.song_title: str = ""
        self.song_artist: str = ""
        self.song_number: int | str | None = None
        self._countdown_pixmaps: dict[int, QPixmap] = _get_countdown_pixmaps()
        self.highlight_color = (settings.get("lyrics_highlight_color") if settings else None) or HIGHLIGHT
        self.highlight_offset = float(settings.get("lyrics_highlight_offset") if settings else 0.15)
        if settings and hasattr(settings, "add_listener"):
            settings.add_listener(self._on_setting_changed)

        self.lines: list = []
        self._key = None
        self._message = "Select a song"
        self._current_pos = 0.0
        self._last_tick_time = time.perf_counter()
        self._is_playing = False
        self._playback_speed = 1.0
        self._line_cache: dict = {}

        self.label = _KaraokeLabel(self)
        self.label.setText(self._message)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, bottom_margin)
        lay.addWidget(self.label)

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(16)  # ~60 FPS smooth interpolation
        self._anim_timer.timeout.connect(self._on_anim_tick)

        if ctl:
            ctl.state_changed.connect(self.set_state)
            ctl.song_changed.connect(self._on_ctl_song_changed)
            if hasattr(ctl, "tempo"):
                self._playback_speed = float(getattr(ctl, "tempo", 1.0) or 1.0)
            if hasattr(ctl, "current") and ctl.current:
                self._on_ctl_song_changed(ctl.current)

    def set_song_info(self, title: str = "", artist: str = "", song_number: int | str | None = None):
        self.song_title = title or ""
        self.song_artist = artist or ""
        self.song_number = song_number
        self.label.update()

    def _on_ctl_song_changed(self, song: dict | None):
        if song and isinstance(song, dict):
            num = song.get("song_number")
            if not num and self.ctl and hasattr(self.ctl, "db") and song.get("id"):
                try:
                    num = self.ctl.db.get_song_number(song["id"])
                except Exception:
                    num = None
            self.set_song_info(
                song.get("title") or song.get("filename") or "",
                song.get("artist") or "",
                num
            )
        else:
            self.set_song_info("", "", None)

    def _on_setting_changed(self, key, value):
        if key == "lyrics_highlight_color" and value:
            self.set_highlight_color(value)
        elif key == "lyrics_highlight_offset" and value is not None:
            try:
                self.highlight_offset = float(value)
                self.label.update()
            except (ValueError, TypeError):
                pass

    def set_highlight_color(self, color: str):
        if self.highlight_color != color:
            self.highlight_color = color
            self._line_cache.clear()
            self.label.update()

    def set_state(self, state: str):
        self._is_playing = (state == "playing")
        if self._is_playing and self.lines and self.isVisible():
            self._last_tick_time = time.perf_counter()
            if not self._anim_timer.isActive():
                self._anim_timer.start()
        else:
            if self._anim_timer.isActive():
                self._anim_timer.stop()
            self.label.update()

    def showEvent(self, event):
        super().showEvent(event)
        if self._is_playing and self.lines and not self._anim_timer.isActive():
            self._last_tick_time = time.perf_counter()
            self._anim_timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        if self._anim_timer.isActive():
            self._anim_timer.stop()

    def _on_anim_tick(self):
        if not self.isVisible():
            self._anim_timer.stop()
            return
        if self._is_playing and self.lines:
            now = time.perf_counter()
            dt = now - self._last_tick_time
            if 0 < dt < 0.25:
                self._current_pos += dt * self._playback_speed
            self._last_tick_time = now
            self.label.update()

    def set_font_size(self, n):
        new_size = max(12, min(160, n))
        if self.font_size != new_size:
            self.font_size = new_size
            self._line_cache.clear()
            self.label.update()

    def set_lyrics(self, events, message=None):
        self.lines = build_lines(events or [])
        self._message = "No lyrics available." if message is None else message
        self._key = None
        self._current_pos = 0.0
        self._last_tick_time = time.perf_counter()
        self._line_cache.clear()

        if not self.lines:
            if not self._message:
                self.label.setText("")
            else:
                self.label.setText(self._message)
            if self._anim_timer.isActive():
                self._anim_timer.stop()
        else:
            self.label.setText("")
            if self._is_playing and self.isVisible() and not self._anim_timer.isActive():
                self._anim_timer.start()
        self.label.update()

    def set_position(self, t: float):
        self._current_pos = max(0.0, t)
        self._last_tick_time = time.perf_counter()
        if self._is_playing and self.lines and self.isVisible() and not self._anim_timer.isActive():
            self._anim_timer.start()
        self.label.update()

    def _render(self, li=-1, si=-1):
        self._key = (li, si)
        self.label.update()

    def _get_line_render(self, line, line_idx: int, label: QWidget) -> dict:
        dpr = label.devicePixelRatio() if hasattr(label, "devicePixelRatio") else 1.0
        cache_key = (id(line), self.font_size, self.highlight_color, round(dpr, 2))
        cached = self._line_cache.get(cache_key)
        if cached is not None:
            return cached

        font = QFont(self.font().family(), self.font_size, QFont.Weight.Bold)
        metrics = QFontMetrics(font)
        full_text = "".join(e.text for e in line)
        total_w = float(metrics.horizontalAdvance(full_text))

        syl_data = []
        cum_w = 0.0
        n = len(line)
        for i, e in enumerate(line):
            sw = float(metrics.horizontalAdvance(e.text))
            s_start = e.time
            if i < n - 1:
                next_t = line[i + 1].time
                gap = max(0.01, next_t - s_start)
                sing_dur = min(gap, max(0.35, len(e.text) * 0.25)) if gap > 1.8 else gap
            else:
                if line_idx + 1 < len(self.lines):
                    gap = max(0.05, self.lines[line_idx + 1][0].time - s_start)
                    # Finish the fill slightly before the next line takes over,
                    # so the last word sweeps smoothly instead of snapping full.
                    sing_dur = min(gap * 0.92, max(0.4, len(e.text) * 0.35))
                else:
                    sing_dur = max(0.4, len(e.text) * 0.35)
            s_end = s_start + max(0.05, sing_dur)
            syl_data.append((cum_w, sw, s_start, s_end))
            cum_w += sw

        pad_x = 12
        pad_y = 12
        pix_w = max(1, int(total_w + pad_x * 2 + 8))
        pix_h = max(1, int(metrics.height() + metrics.descent() + pad_y * 2 + 8))
        ascent = metrics.ascent() + pad_y

        outline_width = max(2.5, self.font_size / 14)
        outline_pen = QPen(QColor(0, 0, 0, 225), outline_width,
                           Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)

        # 1. Base pixmap (pure white)
        img_base = QImage(int(pix_w * dpr), int(pix_h * dpr), QImage.Format.Format_ARGB32_Premultiplied)
        img_base.setDevicePixelRatio(dpr)
        img_base.fill(Qt.GlobalColor.transparent)
        pb = QPainter(img_base)
        pb.setRenderHint(QPainter.RenderHint.Antialiasing)
        pb.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        path = QPainterPath()
        path.addText(pad_x, ascent, font, full_text)

        shadow = QPainterPath()
        shadow.addText(pad_x + 2, ascent + 2.5, font, full_text)
        pb.fillPath(shadow, QBrush(QColor(0, 0, 0, 160)))

        pb.strokePath(path, outline_pen)
        pb.fillPath(path, QBrush(QColor(255, 255, 255)))
        pb.end()

        # 2. Highlight pixmap
        img_hl = QImage(int(pix_w * dpr), int(pix_h * dpr), QImage.Format.Format_ARGB32_Premultiplied)
        img_hl.setDevicePixelRatio(dpr)
        img_hl.fill(Qt.GlobalColor.transparent)
        ph = QPainter(img_hl)
        ph.setRenderHint(QPainter.RenderHint.Antialiasing)
        ph.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        ph.fillPath(shadow, QBrush(QColor(0, 0, 0, 160)))
        ph.strokePath(path, outline_pen)
        ph.fillPath(path, QBrush(QColor(self.highlight_color)))
        ph.end()

        result = {
            "pix_base": QPixmap.fromImage(img_base),
            "pix_hl": QPixmap.fromImage(img_hl),
            "total_w": total_w,
            "pix_w": pix_w,
            "pix_h": pix_h,
            "pad_x": pad_x,
            "pad_y": pad_y,
            "ascent": ascent,
            "syl_data": syl_data,
            "line_h": metrics.height() * 1.35,
            "font_ascent": metrics.ascent(),
        }
        if len(self._line_cache) > 40:
            self._line_cache.clear()
        self._line_cache[cache_key] = result
        return result

    def _calculate_line_progress(self, line_or_info, t: float, metrics: QFontMetrics | None = None, line_idx: int = 0) -> float:
        if isinstance(line_or_info, dict):
            total_w = line_or_info["total_w"]
            syl_data = line_or_info["syl_data"]
        else:
            line = line_or_info
            if not line:
                return 0.0
            full_text = "".join(e.text for e in line)
            m = metrics or QFontMetrics(QFont(self.font().family(), self.font_size, QFont.Weight.Bold))
            total_w = float(m.horizontalAdvance(full_text))
            if t < line[0].time:
                return 0.0
            syl_data = []
            cum_w = 0.0
            n = len(line)
            for i, e in enumerate(line):
                sw = float(m.horizontalAdvance(e.text))
                s_start = e.time
                if i < n - 1:
                    gap = max(0.01, line[i + 1].time - s_start)
                    sing_dur = min(gap, max(0.35, len(e.text) * 0.25)) if gap > 1.8 else gap
                else:
                    sing_dur = max(0.4, len(e.text) * 0.35)
                s_end = s_start + sing_dur
                syl_data.append((cum_w, sw, s_start, s_end))
                cum_w += sw

        if not syl_data or t < syl_data[0][2]:
            return 0.0

        n = len(syl_data)
        for i in range(n):
            sx, sw, s_start, s_end = syl_data[i]
            if t < s_start:
                return sx
            elif s_start <= t < s_end:
                fraction = (t - s_start) / max(0.01, s_end - s_start)
                return sx + min(1.0, max(0.0, fraction)) * sw
            elif i < n - 1 and t < syl_data[i + 1][2]:
                return sx + sw
        return total_w

    def _paint_lyrics(self, label: QWidget):
        painter = QPainter(label)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        w = label.width()
        h = label.height()
        if w <= 0 or h <= 0:
            painter.end()
            return

        if not self.lines:
            msg = label.text() if label.text() is not None else self._message
            if not msg:
                painter.end()
                return
            msg_font = QFont(self.font().family(), max(16, self.font_size // 2), QFont.Weight.DemiBold)
            painter.setFont(msg_font)
            metrics = QFontMetrics(msg_font)
            msg_w = metrics.horizontalAdvance(msg)
            x = (w - msg_w) / 2.0
            y = (h + metrics.ascent() - metrics.descent()) / 2.0
            path = QPainterPath()
            path.addText(x, y, msg_font, msg)
            painter.strokePath(path, QPen(QColor(0, 0, 0, 200), 3))
            painter.fillPath(path, QBrush(QColor(255, 255, 255, 220)))
            painter.end()
            return

        t = max(0.0, self._current_pos + self.highlight_offset)
        li, si = locate(self.lines, t)
        t_first = self.lines[0][0].time if self.lines and self.lines[0] else 0.0

        font = QFont(self.font().family(), self.font_size, QFont.Weight.Bold)
        metrics = QFontMetrics(font)
        line_h = metrics.height() * 1.35

        if self._bottom_margin > 0:
            base_bottom = h - self._bottom_margin
            slot_y = [
                base_bottom - 2 * line_h + metrics.ascent(),
                base_bottom - line_h + metrics.ascent()
            ]
        else:
            start_y = (h - 2 * line_h) / 2.0
            slot_y = [
                start_y + metrics.ascent(),
                start_y + line_h + metrics.ascent()
            ]

        # 1. Before singing begins (li < 0):
        # Show Title & Artist intro card if not yet in the countdown window
        if li < 0:
            countdown_start = max(0.0, t_first - 4.0)
            if t < countdown_start:
                fade_window = 0.5
                alpha = 1.0
                if countdown_start > fade_window and t >= countdown_start - fade_window:
                    alpha = max(0.0, (countdown_start - t) / fade_window)
                self._draw_title_intro_card(painter, w, h, alpha)
                painter.end()
                return

        if li < 0:
            slot_lines = [0 if len(self.lines) > 0 else None,
                          1 if len(self.lines) > 1 else None]
            active_slot = -1
        else:
            top_idx = li if li % 2 == 0 else li + 1
            bottom_idx = li + 1 if li % 2 == 0 else li
            slot_lines = [
                top_idx if top_idx < len(self.lines) else None,
                bottom_idx if bottom_idx < len(self.lines) else None
            ]
            active_slot = 0 if li % 2 == 0 else 1

        for slot_idx in (0, 1):
            line_idx = slot_lines[slot_idx]
            if line_idx is None or line_idx >= len(self.lines):
                continue
            line_events = self.lines[line_idx]
            line_info = self._get_line_render(line_events, line_idx, label)
            is_active = (slot_idx == active_slot and line_idx == li)

            if is_active:
                progress_x = self._calculate_line_progress(line_info, t)
            elif li > line_idx:
                progress_x = line_info["total_w"]
            else:
                progress_x = 0.0

            baseline_y = slot_y[slot_idx]
            self._draw_karaoke_line(painter, line_info, progress_x, baseline_y, w, is_active)

        # 2. Draw Countdown just above the lyrics of the song:
        top_text_y = slot_y[0] - metrics.ascent()
        if li < 0 and t_first - 4.0 <= t < t_first:
            self._draw_countdown(painter, w, top_text_y, t_first - t)
        elif li >= 0 and li + 1 < len(self.lines):
            next_start = self.lines[li + 1][0].time
            cur_info = self._get_line_render(self.lines[li], li, label)
            cur_end = cur_info["syl_data"][-1][3] if cur_info.get("syl_data") else self.lines[li][-1].time
            if next_start - cur_end >= 5.5 and next_start - 4.0 <= t < next_start:
                self._draw_countdown(painter, w, top_text_y, next_start - t)

        painter.end()

    def _draw_karaoke_line(self, painter: QPainter, line_info: dict, progress_x: float,
                           baseline_y: float, widget_w: int, is_active: bool):
        total_w = line_info["total_w"]
        pix_base = line_info["pix_base"]
        pix_hl = line_info["pix_hl"]
        pad_x = line_info["pad_x"]
        ascent = line_info["ascent"]
        pix_h = line_info["pix_h"]

        x = (widget_w - total_w) / 2.0
        draw_x = x - pad_x
        draw_y = baseline_y - ascent

        margin = 40.0
        avail_w = max(100.0, float(widget_w) - margin * 2)
        scale = min(1.0, avail_w / max(1.0, total_w))

        if scale < 1.0:
            painter.save()
            pivot_x = widget_w / 2.0
            painter.translate(pivot_x, baseline_y)
            painter.scale(scale, scale)
            painter.translate(-pivot_x, -baseline_y)

        # 1. Blit base line (pure solid white)
        painter.drawPixmap(int(round(draw_x)), int(round(draw_y)), pix_base)

        # 2. Blit highlight line clipped to progress_x
        if is_active and progress_x > 0.0:
            clip_w = progress_x + pad_x
            painter.save()
            painter.setClipRect(QRectF(draw_x, draw_y, clip_w, pix_h), Qt.ClipOperation.IntersectClip)
            painter.drawPixmap(int(round(draw_x)), int(round(draw_y)), pix_hl)
            painter.restore()

        if scale < 1.0:
            painter.restore()

    def _draw_title_intro_card(self, painter: QPainter, w: int, h: int, alpha: float = 1.0):
        if not self.song_title and not self.song_artist:
            return
        painter.save()
        painter.setOpacity(max(0.0, min(1.0, alpha)))

        display_number = ""
        if self.song_number:
            raw_num = str(self.song_number).strip()
            display_number = raw_num if raw_num.startswith(("#", "No.")) else f"#{raw_num}"

        display_title = self.song_title or "Unknown Title"
        # If display_title happens to start with the song number prefix, strip it for clean display
        if display_number and display_title.startswith(display_number):
            display_title = display_title[len(display_number):].lstrip(" -–—")
        elif display_title.startswith("#"):
            import re
            m = re.match(r"^(#\d+)\s*[-–—]\s*(.*)$", display_title)
            if m:
                if not display_number:
                    display_number = m.group(1)
                display_title = m.group(2)
        display_artist = self.song_artist or ""

        number_pt = max(18, min(38, int(self.font_size * 0.95)))
        title_pt = max(24, min(54, int(self.font_size * 1.30)))
        artist_pt = max(16, min(34, int(self.font_size * 0.80)))

        number_font = QFont(self.font().family(), number_pt, QFont.Weight.Bold)
        title_font = QFont(self.font().family(), title_pt, QFont.Weight.Bold)
        artist_font = QFont(self.font().family(), artist_pt, QFont.Weight.DemiBold)

        number_m = QFontMetrics(number_font)
        title_m = QFontMetrics(title_font)
        artist_m = QFontMetrics(artist_font)

        max_text_w = float(max(100, w - 80))
        if display_number and number_m.horizontalAdvance(display_number) > max_text_w:
            display_number = number_m.elidedText(display_number, Qt.TextElideMode.ElideRight, int(max_text_w))
        if title_m.horizontalAdvance(display_title) > max_text_w:
            display_title = title_m.elidedText(display_title, Qt.TextElideMode.ElideRight, int(max_text_w))
        if display_artist and artist_m.horizontalAdvance(display_artist) > max_text_w:
            display_artist = artist_m.elidedText(display_artist, Qt.TextElideMode.ElideRight, int(max_text_w))

        has_num = bool(display_number)
        has_art = bool(display_artist)
        spacing = 14.0
        total_text_h = (
            (number_m.height() + spacing if has_num else 0.0)
            + title_m.height()
            + (spacing + artist_m.height() if has_art else 0.0)
        )

        start_y = (h - total_text_h) / 2.0
        if self._bottom_margin > 0:
            start_y = max(20.0, start_y - self._bottom_margin / 2.0)

        cur_y = start_y

        # 1. Draw Song Number (above title)
        if has_num:
            num_w = float(number_m.horizontalAdvance(display_number))
            num_x = (w - num_w) / 2.0
            num_y = cur_y + number_m.ascent()
            n_path = QPainterPath()
            n_path.addText(num_x, num_y, number_font, display_number)
            n_shadow = QPainterPath()
            n_shadow.addText(num_x + 2.0, num_y + 2.5, number_font, display_number)
            painter.fillPath(n_shadow, QBrush(QColor(0, 0, 0, 200)))
            painter.strokePath(n_path, QPen(QColor(0, 0, 0, 230), 3.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.fillPath(n_path, QBrush(QColor(255, 255, 255)))
            cur_y += number_m.height() + spacing

        # 2. Draw Title (pure white with strong dark shadow and outline)
        title_w = float(title_m.horizontalAdvance(display_title))
        title_x = (w - title_w) / 2.0
        title_y = cur_y + title_m.ascent()
        t_path = QPainterPath()
        t_path.addText(title_x, title_y, title_font, display_title)
        t_shadow = QPainterPath()
        t_shadow.addText(title_x + 2.5, title_y + 3.0, title_font, display_title)
        painter.fillPath(t_shadow, QBrush(QColor(0, 0, 0, 210)))
        painter.strokePath(t_path, QPen(QColor(0, 0, 0, 240), 3.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.fillPath(t_path, QBrush(QColor(255, 255, 255)))
        cur_y += title_m.height() + spacing

        # 3. Draw Artist (pure white with strong dark shadow and outline)
        if has_art:
            art_w = float(artist_m.horizontalAdvance(display_artist))
            art_x = (w - art_w) / 2.0
            art_y = cur_y + artist_m.ascent()
            a_path = QPainterPath()
            a_path.addText(art_x, art_y, artist_font, display_artist)
            a_shadow = QPainterPath()
            a_shadow.addText(art_x + 2.0, art_y + 2.5, artist_font, display_artist)
            painter.fillPath(a_shadow, QBrush(QColor(0, 0, 0, 200)))
            painter.strokePath(a_path, QPen(QColor(0, 0, 0, 230), 3.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.fillPath(a_path, QBrush(QColor(255, 255, 255)))

        painter.restore()

    def _draw_countdown(self, painter: QPainter, w: int, top_lyric_y: float, seconds_left: float):
        if seconds_left <= 0.0 or seconds_left > 4.0:
            return
        active_num = max(1, min(4, int(seconds_left) + 1))
        if seconds_left >= 3.99:
            active_num = 4

        base_badge_size = min(54.0, max(36.0, self.font_size * 1.30))
        gap = 12.0
        total_w = 4 * base_badge_size + 3 * gap
        if total_w > w - 40:
            scale_fit = (w - 40) / total_w
            base_badge_size *= scale_fit
            gap *= scale_fit
            total_w = 4 * base_badge_size + 3 * gap

        start_x = (float(w) - total_w) / 2.0
        countdown_y = top_lyric_y - base_badge_size - 14.0
        if countdown_y < 8.0:
            countdown_y = 8.0

        sub_sec = seconds_left - (active_num - 1)

        for i, num in enumerate((4, 3, 2, 1)):
            pix = self._countdown_pixmaps.get(num)
            if not pix or pix.isNull():
                continue

            cx = start_x + i * (base_badge_size + gap) + base_badge_size / 2.0
            cy = countdown_y + base_badge_size / 2.0

            if num == active_num:
                pop = max(0.0, sub_sec - 0.65) / 0.35
                scale = 1.05 + 0.15 * pop
                opacity = 1.0

                glow_size = base_badge_size * scale + 10.0
                glow_rect = QRectF(cx - glow_size / 2.0, cy - glow_size / 2.0, glow_size, glow_size)
                g_path = QPainterPath()
                g_path.addRoundedRect(glow_rect, 12, 12)
                painter.save()
                painter.setOpacity(0.35)
                painter.fillPath(g_path, QBrush(QColor(255, 255, 255)))
                painter.restore()
            elif num > active_num:
                scale = 0.95
                opacity = 0.45
            else:
                scale = 0.90
                opacity = 0.22

            draw_size = base_badge_size * scale
            target_rect = QRectF(cx - draw_size / 2.0, cy - draw_size / 2.0, draw_size, draw_size)

            painter.save()
            painter.setOpacity(opacity)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(target_rect.toRect(), pix)
            painter.restore()
