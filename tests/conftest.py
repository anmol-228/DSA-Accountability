import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import sqlite3

from app import config, database
from app.services import runtime_env

@pytest.fixture(scope="session", autouse=True)
def _isolated_runtime(tmp_path_factory):
    """Globally isolate every default without opening production resources.

    Every test gets a temporary data root, DB, logs/backups, and learner-repo
    default without relying on individual test authors. The fixture never reads,
    fingerprints, migrates, or writes a real installation.
    """
    root = tmp_path_factory.mktemp("dsa-accountability-runtime")
    data_dir = root / "data"
    backups_dir = root / "backups"
    logs_dir = root / "logs"
    repo_dir = root / "DSA-135-test"
    for path in (data_dir, backups_dir, logs_dir, repo_dir):
        path.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "progress.test.sqlite"

    patcher = pytest.MonkeyPatch()
    patcher.setenv(runtime_env.ENVIRONMENT_VARIABLE, runtime_env.RuntimeEnvironment.TEST.value)
    # All pytest tmp_path fixtures for this session are siblings under the same
    # base directory. Protect that whole pytest-owned base so per-test DB
    # monkeypatches remain valid while repo/workspace paths remain forbidden.
    patcher.setenv(runtime_env.TEST_ROOT_VARIABLE, str(root.parent))
    patcher.setenv(runtime_env.TEST_DB_VARIABLE, str(db_path))
    patcher.setenv(runtime_env.TEST_REPO_VARIABLE, str(repo_dir))
    patcher.setenv(runtime_env.PRODUCTION_DB_VARIABLE, str(config.PRODUCTION_DB_PATH))
    patcher.setattr(config, "DATA_DIR", data_dir)
    patcher.setattr(config, "BACKUPS_DIR", backups_dir)
    patcher.setattr(config, "LOGS_DIR", logs_dir)
    patcher.setattr(config, "DB_PATH", db_path)
    patcher.setattr(config, "TEST_DB_PATH", db_path)
    patcher.setattr(config, "DEFAULT_DSA135_REPO", repo_dir)

    yield
    patcher.undo()


@pytest.fixture()
def conn(tmp_path) -> sqlite3.Connection:
    db_path = tmp_path / "test.sqlite"
    database.run_migrations(db_path)
    c = database.get_connection(db_path)
    yield c
    c.close()


@pytest.fixture()
def seeded_conn(conn) -> sqlite3.Connection:
    import datetime as dt
    from app.services import curriculum_service, schedule_service
    schedule_service.set_start_date(conn, dt.date(2026, 8, 15))
    curriculum_service.seed_curriculum(conn)
    return conn
