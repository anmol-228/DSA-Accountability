"""Create and validate a disposable new-user instance without production access."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument("--repo-name", default="My-DSA-Journey")
    args = parser.parse_args()

    root = args.root.resolve()
    if root.exists() and any(root.iterdir()):
        raise RuntimeError(f"Refusing non-empty simulation root: {root}")
    root.mkdir(parents=True, exist_ok=True)

    data_root = root / "runtime"
    db_path = data_root / "data" / "progress.test.sqlite"
    repo_path = root / args.repo_name
    protected = root / "must-not-touch"
    os.environ.update(
        {
            "DSA_ACCOUNTABILITY_ENV": "TEST",
            "DSA_ACCOUNTABILITY_TEST_ROOT": str(root),
            "DSA_ACCOUNTABILITY_TEST_DB": str(db_path),
            "DSA_ACCOUNTABILITY_TEST_REPO": str(repo_path),
            "DSA_ACCOUNTABILITY_PRODUCTION_DB": str(protected / "progress.sqlite"),
            "DSA_ACCOUNTABILITY_PRODUCTION_REPO": str(protected / "learner"),
            "LOCALAPPDATA": str(data_root),
            "QT_QPA_PLATFORM": "offscreen",
        }
    )

    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root))
    from app import config, database  # noqa: PLC0415
    from app.services import curriculum_service, onboarding_service, progression_service  # noqa: PLC0415

    config.DATA_DIR = db_path.parent
    config.BACKUPS_DIR = data_root / "backups"
    config.LOGS_DIR = data_root / "logs"
    config.DB_PATH = db_path
    config.TEST_DB_PATH = db_path
    config.DEFAULT_DSA135_REPO = repo_path

    database.run_migrations(db_path)
    conn = database.get_connection(db_path)
    try:
        onboarding_service.configure_first_run(
            conn,
            start_date=args.start_date,
            learner_repo=repo_path,
            remote_url="",
            auto_push=False,
            startup_enabled=False,
            manage_startup=False,
        )
        curriculum_service.seed_curriculum(conn)
        curriculum_service.backfill_canonical_filenames(conn)
        progression_service.reschedule_original_dates(conn)

        first = conn.execute(
            "SELECT original_due_date FROM curriculum_days WHERE day_number=1"
        ).fetchone()[0]
        last = conn.execute(
            "SELECT original_due_date FROM curriculum_days WHERE day_number=135"
        ).fetchone()[0]
        counts = {
            "days": conn.execute("SELECT COUNT(*) FROM curriculum_days").fetchone()[0],
            "completed_days": conn.execute(
                "SELECT COUNT(*) FROM curriculum_days WHERE completed=1"
            ).fetchone()[0],
            "completed_tasks": conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE completed=1"
            ).fetchone()[0],
        }
        token_present = conn.execute(
            "SELECT 1 FROM settings WHERE key='pairing_token'"
        ).fetchone() is not None
        first_run = conn.execute(
            "SELECT value FROM settings WHERE key='first_run_complete'"
        ).fetchone()[0]
    finally:
        conn.close()

    expected_last = args.start_date + timedelta(days=134)
    assert counts == {"days": 135, "completed_days": 0, "completed_tasks": 0}
    assert first == args.start_date.isoformat()
    assert last == expected_last.isoformat()
    assert token_present and first_run == "1"
    assert (repo_path / ".git").is_dir()
    assert not protected.exists()

    print(
        json.dumps(
            {
                "result": "PASS",
                "start_date": first,
                "target_date": last,
                "curriculum_days": 135,
                "completed_days": 0,
                "completed_tasks": 0,
                "token_created": True,
                "repo_name": repo_path.name,
                "local_git": True,
                "github_remote": False,
                "protected_resources_touched": False,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
