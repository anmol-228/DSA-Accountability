import os
from pathlib import Path

import pytest

from app import config, database
from app.services import code_sync_service, git_service, pipeline_service, runtime_env


def test_pytest_forces_formal_test_environment(monkeypatch):
    monkeypatch.setenv(runtime_env.ENVIRONMENT_VARIABLE, "PRODUCTION")
    assert runtime_env.current_environment() is runtime_env.RuntimeEnvironment.TEST


def test_development_runtime_state_is_outside_source_checkout():
    assert config.DEVELOPMENT_DATA_ROOT != config.APP_ROOT
    assert not config.DEVELOPMENT_DATA_ROOT.is_relative_to(config.APP_ROOT)


def test_global_defaults_are_inside_isolated_test_root():
    root = Path(os.environ[runtime_env.TEST_ROOT_VARIABLE])
    assert config.DB_PATH.is_relative_to(root)
    assert config.DATA_DIR.is_relative_to(root)
    assert config.BACKUPS_DIR.is_relative_to(root)
    assert config.LOGS_DIR.is_relative_to(root)
    assert config.DEFAULT_DSA135_REPO.is_relative_to(root)


def test_default_database_connection_uses_temporary_database():
    conn = database.get_connection()
    try:
        path = Path(conn.execute("PRAGMA database_list").fetchone()[2])
        assert path == config.DB_PATH
        assert path != config.PRODUCTION_DB_PATH
    finally:
        conn.close()


def test_production_database_access_is_rejected_before_open():
    with pytest.raises(runtime_env.ProductionDataAccessError):
        database.get_connection(config.PRODUCTION_DB_PATH)
    with pytest.raises(runtime_env.ProductionDataAccessError):
        database.backup_db(config.PRODUCTION_DB_PATH, label="must-not-exist")


def test_production_repo_cannot_be_configured_or_resolved(seeded_conn, tmp_path, monkeypatch):
    production_repo = tmp_path / "protected-user-repo"
    monkeypatch.setenv(runtime_env.PRODUCTION_REPO_VARIABLE, str(production_repo))
    with pytest.raises(runtime_env.ProductionDataAccessError):
        pipeline_service.set_dsa135_repo(seeded_conn, production_repo)

    seeded_conn.execute(
        "INSERT INTO settings (key, value) VALUES ('dsa135_repo_path', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(production_repo),),
    )
    seeded_conn.commit()
    with pytest.raises(runtime_env.ProductionDataAccessError):
        pipeline_service.get_dsa135_repo(seeded_conn)


def test_production_repo_git_and_file_writes_are_rejected(tmp_path, monkeypatch):
    production_repo = tmp_path / "protected-user-repo"
    monkeypatch.setenv(runtime_env.PRODUCTION_REPO_VARIABLE, str(production_repo))
    with pytest.raises(runtime_env.ProductionDataAccessError):
        git_service.is_repo(production_repo)
    with pytest.raises(runtime_env.ProductionDataAccessError):
        git_service.ensure_repo(production_repo)
    with pytest.raises(runtime_env.ProductionDataAccessError):
        code_sync_service.write_solution(production_repo / "should-never-exist.java", "class X {}")


def test_missing_global_test_db_fails_loudly(monkeypatch):
    monkeypatch.delenv(runtime_env.TEST_DB_VARIABLE)
    with pytest.raises(runtime_env.ProductionDataAccessError):
        database.get_connection()


def test_missing_global_test_repo_fails_loudly(seeded_conn, monkeypatch):
    monkeypatch.delenv(runtime_env.TEST_REPO_VARIABLE)
    with pytest.raises(runtime_env.ProductionDataAccessError):
        pipeline_service.get_dsa135_repo(seeded_conn)
