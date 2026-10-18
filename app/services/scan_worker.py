from PySide6.QtCore import QThread, Signal
from app.library import scanner


class ScanWorker(QThread):
    """Runs import/scan/rescan off the GUI thread."""
    progress = Signal(int, str)
    finished_scan = Signal(object)   # ScanResult
    failed = Signal(str)

    def __init__(self, db, mode: str, paths=None, parent=None):
        super().__init__(parent)
        self.db, self.mode, self.paths = db, mode, paths or []
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        cb = lambda n, p: self.progress.emit(n, p)
        stop = lambda: self._cancel
        try:
            if self.mode == "files":
                res = scanner.import_files(self.db, self.paths, progress=cb, cancel=stop)
            elif self.mode == "folder":
                # Folder import only indexes paths and cheap file metadata.
                # MIDI parsing is deferred until the user plays a song.
                res = scanner.scan_folder(self.db, self.paths[0], progress=cb, cancel=stop,
                                          lazy=True)
            else:
                res = scanner.rescan_library(self.db, progress=cb, cancel=stop, lazy=True)
            self.finished_scan.emit(res)
        except Exception as e:
            self.failed.emit(str(e))
