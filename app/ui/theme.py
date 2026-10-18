ACCENT = "#7c4dff"
STYLE = """
* { font-family: "Segoe UI", "Inter", sans-serif; font-size: 13px; }
QWidget { background: #14151a; color: #e6e6ea; }
QMainWindow, QStackedWidget, QSplitter { background: #14151a; }
QListWidget#sidebar { background: #0e0f13; border: none; padding: 8px 0; outline: 0; }
QListWidget#sidebar::item { padding: 11px 18px; border-radius: 8px; margin: 2px 8px; }
QListWidget#sidebar::item:selected { background: #2a2350; color: #ffffff; }
QListWidget#sidebar::item:hover:!selected { background: #1d1e26; }
QPushButton { background: #262833; border: 1px solid #343747; border-radius: 8px; padding: 7px 14px; }
QPushButton:hover { background: #30334a; } QPushButton:pressed { background: #3a3e5c; }
QPushButton:disabled { color: #666; } QPushButton:checked { background: #5b3fd1; border-color: #7c4dff; }
QPushButton#primary { background: #7c4dff; border: none; font-weight: 600; min-width: 44px; }
QPushButton#primary:hover { background: #8f66ff; }
QPushButton#karaoke_btn {
  background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7c4dff, stop:0.5 #9c27b0, stop:1 #e91e63);
  color: #ffffff;
  border: 1px solid #f06292;
  border-radius: 8px;
  font-weight: 700;
  font-size: 13px;
  padding: 7px 16px;
}
QPushButton#karaoke_btn:hover {
  background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #9168ff, stop:0.5 #ba68c8, stop:1 #f06292);
  border: 1px solid #ffffff;
}
QPushButton#karaoke_btn:pressed {
  background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #651fff, stop:0.5 #7b1fa2, stop:1 #c2185b);
}
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox { background: #1d1e26; border: 1px solid #343747; border-radius: 8px; padding: 6px 10px; }
QLineEdit:focus, QComboBox:focus { border-color: #7c4dff; }
QComboBox QAbstractItemView { background: #1d1e26; selection-background-color: #3a2f78; }
QTableView, QListWidget { background: #181920; border: 1px solid #2a2c38; border-radius: 8px; gridline-color: transparent;
  selection-background-color: #3a2f78; alternate-background-color: #1b1c24; outline: 0; }
QHeaderView::section { background: #1d1e26; color: #aab; border: none; padding: 7px; font-weight: 600; }
QSlider::groove:horizontal { height: 6px; background: #2c2e3b; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #7c4dff; border-radius: 3px; }
QSlider::handle:horizontal { background: #fff; width: 14px; margin: -5px 0; border-radius: 7px; }
QSlider::groove:vertical { width: 6px; background: #2c2e3b; border-radius: 3px; }
QSlider::sub-page:vertical { background: #2c2e3b; } QSlider::add-page:vertical { background: #7c4dff; border-radius: 3px; }
QSlider::handle:vertical { background: #fff; height: 14px; margin: 0 -5px; border-radius: 7px; }
QTabWidget::pane { border: 1px solid #2a2c38; border-radius: 8px; }
QTabBar::tab { padding: 8px 16px; background: transparent; } QTabBar::tab:selected { color: #fff; border-bottom: 2px solid #7c4dff; }
QGroupBox { border: 1px solid #2a2c38; border-radius: 10px; margin-top: 14px; padding: 12px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; color: #aab; }
QLabel#h1 { font-size: 22px; font-weight: 700; } QLabel#muted { color: #8a8da0; }
QFrame#nowplaying { background: #0e0f13; border-top: 1px solid #2a2c38; }
QScrollArea { border: none; } QStatusBar { background: #0e0f13; color: #8a8da0; }
QToolTip { background: #262833; color: #fff; border: 1px solid #7c4dff; }
"""
