"""Render a real token-free overlay screenshot from a disposable fresh DB."""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    output = project_root / "docs" / "images" / "main-widget.png"
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="dsa-public-screenshot-") as temp:
        print("Preparing disposable UI state...", flush=True)
        root = Path(temp)
        db_path = root / "runtime" / "data" / "progress.test.sqlite"
        repo = root / "Learner-Journey"
        os.environ.update(
            {
                "DSA_ACCOUNTABILITY_ENV": "TEST",
                "DSA_ACCOUNTABILITY_TEST_ROOT": str(root),
                "DSA_ACCOUNTABILITY_TEST_DB": str(db_path),
                "DSA_ACCOUNTABILITY_TEST_REPO": str(repo),
                "DSA_ACCOUNTABILITY_PRODUCTION_DB": str(root / "protected" / "db.sqlite"),
                "DSA_ACCOUNTABILITY_PRODUCTION_REPO": str(root / "protected" / "repo"),
                "LOCALAPPDATA": str(root / "runtime"),
            }
        )
        sys.path.insert(0, str(project_root))

        from PySide6.QtCore import QSettings  # noqa: PLC0415
        from PySide6.QtWidgets import QApplication  # noqa: PLC0415
        from app import config, database  # noqa: PLC0415
        from app.services import curriculum_service, onboarding_service  # noqa: PLC0415
        from app.ui.main_window import OverlayWindow  # noqa: PLC0415
        from app.ui.theme import build_qss, get_palette  # noqa: PLC0415

        config.DATA_DIR = db_path.parent
        config.BACKUPS_DIR = root / "runtime" / "backups"
        config.LOGS_DIR = root / "runtime" / "logs"
        config.DB_PATH = db_path
        config.TEST_DB_PATH = db_path
        config.DEFAULT_DSA135_REPO = repo

        database.run_migrations(db_path)
        conn = database.get_connection(db_path)
        onboarding_service.configure_first_run(
            conn,
            start_date=date(2027, 1, 1),
            learner_repo=repo,
            remote_url="",
            auto_push=False,
            manage_startup=False,
        )
        curriculum_service.seed_curriculum(conn)
        conn.close()

        print("Rendering overlay...", flush=True)
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(root / "qsettings"))
        app = QApplication([])
        app.setStyleSheet(build_qss(get_palette()))
        window = OverlayWindow()
        window.show()
        app.processEvents()
        print("Capturing image...", flush=True)
        if not window.grab().save(str(output), "PNG"):
            raise RuntimeError("Qt could not save the screenshot")
        window.hide()
        window.deleteLater()
        app.processEvents()
        app.quit()
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
