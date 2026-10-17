from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QLabel, QVBoxLayout, QWidget


class RemotePanel(QWidget):
    def __init__(self, url, compact=False, parent=None):
        super().__init__(parent)
        self._compact = compact
        self.qr = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        qr_size = 112 if compact else 150
        self.qr.setFixedSize(qr_size, qr_size)
        self.qr.setStyleSheet("background:white; padding:6px; border-radius:6px;")
        title = QLabel("Phone remote"); title.setObjectName("h2"); title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.address = QLabel(url.rstrip('/') if compact else f"Scan to browse and queue songs:\n{url}")
        self.address.setWordWrap(True)
        self.address.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status = QLabel("Queued: 0 · Devices: 0"); self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if compact:
            self.setFixedWidth(160)
            title.hide()
            self.status.hide()
            self.address.setStyleSheet("font-size:12px;font-weight:700;color:#ffffff;background:transparent;")
            shadow = QGraphicsDropShadowEffect(self.address)
            shadow.setBlurRadius(8)
            shadow.setColor(QColor(0, 0, 0, 220))
            shadow.setOffset(0, 1)
            self.address.setGraphicsEffect(shadow)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4) if compact else lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4 if compact else 6)
        lay.addWidget(title); lay.addWidget(self.qr, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addWidget(self.address, 0, Qt.AlignmentFlag.AlignHCenter); lay.addWidget(self.status)
        self._make_qr(url)

    def set_status(self, queued, devices):
        self.status.setText(f"Queued: {queued} · Devices: {devices}")

    def _make_qr(self, text):
        try:
            import qrcode
            matrix = qrcode.QRCode(box_size=5, border=4)
            matrix.add_data(text); matrix.make(fit=True)
            cells = matrix.get_matrix()
            scale = 5
            image = QImage(len(cells) * scale, len(cells) * scale, QImage.Format.Format_RGB32)
            image.fill(QColor("white"))
            painter = QPainter(image); painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QColor("black"))
            for y, row in enumerate(cells):
                for x, dark in enumerate(row):
                    if dark: painter.drawRect(x * scale, y * scale, scale, scale)
            painter.end()
            size = self.qr.width() - 12
            self.qr.setPixmap(QPixmap.fromImage(image).scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                                               Qt.TransformationMode.FastTransformation))
        except Exception:
            self.qr.setText("QR unavailable")
