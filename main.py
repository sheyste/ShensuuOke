"""Karaoke Player entry point. Run: python main.py"""
import os
import sys
import traceback


def main() -> int:
    from PySide6.QtCore import QStandardPaths
    from PySide6.QtWidgets import QApplication, QMessageBox
    from app.library.database import Database, DatabaseError
    from app.services.playback import PlaybackController
    from app.services.runtime_bootstrap import ensure_native_runtime
    from app.services.settings import Settings
    from app.ui.main_window import MainWindow
    from app.ui.theme import STYLE

    app = QApplication(sys.argv)
    app.setApplicationName("ShensuuOke"); app.setOrganizationName("ShensuuOke")
    app.setStyleSheet(STYLE)

    icon_path = os.path.join(os.path.dirname(__file__), "app", "resources", "icons", "logo.png")
    if os.path.exists(icon_path):
        from PySide6.QtGui import QIcon
        app.setWindowIcon(QIcon(icon_path))

    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Shensuu.ShensuuOke.App")
        except Exception:
            pass

    def hook(et, ev, tb):
        traceback.print_exception(et, ev, tb)
        QMessageBox.critical(None, "Unexpected error", f"{et.__name__}: {ev}")
    sys.excepthook = hook

    docs_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    app_docs_dir = os.path.join(docs_dir, "ShensuuOke")
    data_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    try:
        os.makedirs(app_docs_dir, exist_ok=True)
        target_db = os.path.join(app_docs_dir, "library.db")
        if not os.path.exists(target_db):
            # Check for existing database from prior install and migrate seamlessly
            prior_appdata_db = os.path.join(data_dir, "library.db")
            old_data_dir = os.path.join(os.path.dirname(data_dir), "KaraokePlayer")
            old_db = os.path.join(old_data_dir, "library.db")
            for candidate in (prior_appdata_db, old_db):
                if os.path.exists(candidate):
                    import shutil
                    try:
                        shutil.copyfile(candidate, target_db)
                        break
                    except OSError:
                        pass
        db = Database(target_db)
        db.clear_recently_played()
    except (DatabaseError, OSError) as e:
        QMessageBox.critical(None, "Database error", str(e)); return 1

    # Native playback dependencies are provisioned automatically on Windows.
    # Failure is non-fatal so the library can still open and explain the issue.
    _, _, soundfont_path, runtime_error = ensure_native_runtime(data_dir)
    if runtime_error:
        print(f"Native runtime setup warning: {runtime_error}", file=sys.stderr)
    # Clean up missing soundfonts from database and ensure default soundfont is valid
    for sf in db.list_soundfonts():
        if not os.path.isfile(sf["path"]):
            db.remove_soundfont(sf["id"])

    cur_sf = db.default_soundfont()
    if soundfont_path and (not cur_sf or not os.path.isfile(cur_sf.get("path", ""))):
        soundfont_id = db.add_soundfont(soundfont_path)
        db.set_default_soundfont(soundfont_id)

    settings = Settings(db)
    ctl = PlaybackController(db, settings)
    win = MainWindow(db, settings, ctl)
    win.showMaximized()
    ctl.start_audio()          # reports a clear error if no output device can be opened
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
