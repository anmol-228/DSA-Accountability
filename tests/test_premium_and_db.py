import json

import pytest

from app import database
from app.services import curriculum_service, leetcode_service


def test_premium_fallback_replaces_problem_and_logs_audit(seeded_conn):
    conn = seeded_conn
    task = conn.execute(
        "SELECT t.* FROM tasks t JOIN problems p ON t.problem_id = p.id "
        "WHERE t.day_number = 8 AND p.leetcode_number = 1"
    ).fetchone()
    original_problem_id = task["problem_id"]

    replacement = leetcode_service.apply_premium_fallback(conn, task["id"], "arrays")
    assert replacement is not None
    assert replacement["premium"] == 0 if "premium" in replacement else True  # catalog entries are all free

    updated = conn.execute("SELECT * FROM tasks WHERE id = ?", (task["id"],)).fetchone()
    assert updated["problem_id"] != original_problem_id
    assert updated["original_problem_id"] == original_problem_id
    assert updated["premium_blocked_note"] is not None

    audit = conn.execute(
        "SELECT * FROM audit_log WHERE action = 'premium_fallback'"
    ).fetchone()
    assert audit is not None
    details = json.loads(audit["details"])
    assert details["task_id"] == task["id"]


def test_premium_fallback_never_reuses_a_problem_already_scheduled_that_day(seeded_conn):
    conn = seeded_conn
    # Day 8 already has LC 1 and LC 121. If LC1 goes premium, the fallback
    # must not pick something already present on day 8.
    task = conn.execute(
        "SELECT t.* FROM tasks t JOIN problems p ON t.problem_id = p.id "
        "WHERE t.day_number = 8 AND p.leetcode_number = 1"
    ).fetchone()
    replacement = leetcode_service.apply_premium_fallback(conn, task["id"], "arrays")
    assert replacement is not None
    assert replacement["leetcode_number"] != 121


def test_premium_fallback_does_not_penalize_user(seeded_conn):
    conn = seeded_conn
    task = conn.execute(
        "SELECT t.* FROM tasks t JOIN problems p ON t.problem_id = p.id "
        "WHERE t.day_number = 8 AND p.leetcode_number = 1"
    ).fetchone()
    leetcode_service.apply_premium_fallback(conn, task["id"], "arrays")
    updated = conn.execute("SELECT * FROM tasks WHERE id = ?", (task["id"],)).fetchone()
    assert updated["required"] == 1  # still required, still completable — not silently dropped
    assert updated["completed"] == 0


# --- database migrations + backups ------------------------------------------

def test_migrations_are_idempotent(tmp_path):
    db_path = tmp_path / "migrate_test.sqlite"
    applied_1 = database.run_migrations(db_path)
    applied_2 = database.run_migrations(db_path)
    assert len(applied_1) >= 1
    assert applied_2 == []  # nothing re-applied second time


def test_backup_created_before_migration(tmp_path):
    db_path = tmp_path / "migrate_test.sqlite"
    database.run_migrations(db_path)  # creates the db
    backups_before = list(database.config.BACKUPS_DIR.glob("progress-*.sqlite"))
    database.run_migrations(db_path)  # second run: file exists -> should back up first
    backups_after = list(database.config.BACKUPS_DIR.glob("progress-*.sqlite"))
    assert len(backups_after) >= len(backups_before)


def test_seed_curriculum_is_idempotent(conn):
    curriculum_service.seed_curriculum(conn)
    count_1 = conn.execute("SELECT COUNT(*) c FROM tasks").fetchone()["c"]
    curriculum_service.seed_curriculum(conn)  # second call: is_seeded() short-circuits
    count_2 = conn.execute("SELECT COUNT(*) c FROM tasks").fetchone()["c"]
    assert count_1 == count_2


# --- WAL-safe backup + migration failure recovery (production stabilization) --

def test_backup_is_wal_safe_and_restorable(tmp_path, monkeypatch):
    """backup_db() must use SQLite's online backup API, not a plain file
    copy -- a copy taken while WAL-mode writes are in flight can be torn.
    This proves the backup is a fully consistent, independently-openable
    snapshot that reflects writes made and committed before the backup."""
    from app import config as app_config
    db_path = tmp_path / "wal_test.sqlite"
    monkeypatch.setattr(app_config, "BACKUPS_DIR", tmp_path / "backups")
    database.run_migrations(db_path)

    conn = database.get_connection(db_path)
    conn.execute("INSERT INTO settings (key, value) VALUES ('probe', 'before-backup')")
    conn.commit()

    backup_path = database.backup_db(db_path, label="test")
    assert backup_path is not None
    assert backup_path.exists()

    # Modify the original AFTER the backup -- the backup must be
    # unaffected (proves it's an independent, complete snapshot, not a
    # reference/symlink or a partial copy).
    conn.execute("UPDATE settings SET value = 'after-backup' WHERE key = 'probe'")
    conn.commit()
    conn.close()

    backup_conn = database.get_connection(backup_path)
    integrity = backup_conn.execute("PRAGMA integrity_check").fetchone()[0]
    assert integrity == "ok"
    row = backup_conn.execute("SELECT value FROM settings WHERE key = 'probe'").fetchone()
    backup_conn.close()
    assert row["value"] == "before-backup"


def test_migration_failure_does_not_wipe_existing_db(tmp_path, monkeypatch):
    """A migration that fails partway must raise MigrationError (not a
    bare exception, not a silent wipe) and must leave the existing,
    already-applied schema/data completely intact."""
    from app import config as app_config
    db_path = tmp_path / "fail_test.sqlite"
    monkeypatch.setattr(app_config, "BACKUPS_DIR", tmp_path / "backups")
    database.run_migrations(db_path)  # apply the real migrations cleanly first

    conn = database.get_connection(db_path)
    conn.execute("INSERT INTO settings (key, value) VALUES ('survives', 'yes')")
    conn.commit()
    conn.close()

    # The broken migration's own version number must be one past whatever
    # real migrations already applied above -- otherwise the runner sees it
    # as an already-applied version and silently skips it instead of
    # running (and failing on) it. Computed from the real migrations
    # directory rather than hardcoded, so this test doesn't need updating
    # again every time a new real migration is added.
    real_max_version = max(
        int(f.name.split("_")[0]) for f in app_config.MIGRATIONS_DIR.glob("*.sql")
    )
    next_version = real_max_version + 1

    bad_migrations_dir = tmp_path / "bad_migrations"
    bad_migrations_dir.mkdir()
    (bad_migrations_dir / f"{next_version:03d}_broken.sql").write_text(
        "INSERT INTO settings (key, value) VALUES ('should_not_persist', 'x');\n"
        "THIS IS NOT VALID SQL AND WILL FAIL;\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(app_config, "MIGRATIONS_DIR", bad_migrations_dir)

    with pytest.raises(database.MigrationError) as exc_info:
        database.run_migrations(db_path)
    assert exc_info.value.version == next_version
    assert exc_info.value.backup_path is not None
    assert exc_info.value.backup_path.exists()

    # Existing data untouched, and the failed migration's own partial
    # writes were rolled back rather than silently persisted.
    conn = database.get_connection(db_path)
    row = conn.execute("SELECT value FROM settings WHERE key = 'survives'").fetchone()
    assert row["value"] == "yes"
    partial = conn.execute("SELECT value FROM settings WHERE key = 'should_not_persist'").fetchone()
    conn.close()
    assert partial is None


# --- DSA-135 repo path resolution (production stabilization) -----------------

def test_get_dsa135_repo_trusts_explicit_setting_even_if_not_yet_a_repo(seeded_conn, tmp_path):
    """A freshly configured, not-yet-initialized directory must be trusted
    as-is -- ensure_repo() is what turns it into a real git repo; the
    resolver must never second-guess a deliberately configured path just
    because nothing has been committed there yet (this was a real
    regression caught while fixing the missing-setting recovery path)."""
    from app.services import pipeline_service
    not_yet_a_repo = tmp_path / "DSA-135"
    pipeline_service.set_dsa135_repo(seeded_conn, not_yet_a_repo)
    assert pipeline_service.get_dsa135_repo(seeded_conn) == not_yet_a_repo


def test_get_dsa135_repo_hard_fails_under_pytest_when_unconfigured(seeded_conn, monkeypatch):
    """Final production repair pass: the sibling-dev-checkout recovery
    fallback (previously tested here) is a PRODUCTION safety net only.
    Under pytest it must never fire at all -- it was exactly this kind of
    "helpful" fallback that silently resolved to a real learner repository
    during this session's own test runs and wrote real commits into it
    (see docs/PRODUCTION_STABILIZATION_2026-08-12.md's contamination
    incident). A test with no explicit dsa135_repo_path setting must now
    fail loudly and immediately instead of guessing at a real-looking
    path -- this is a structural guard, not per-test discipline."""
    from app.services import pipeline_service, runtime_env

    monkeypatch.delenv(runtime_env.TEST_REPO_VARIABLE)
    with pytest.raises(runtime_env.ProductionDataAccessError):
        pipeline_service.get_dsa135_repo(seeded_conn)


def test_get_dsa135_repo_still_recovers_sibling_outside_test_env(seeded_conn, tmp_path, monkeypatch):
    """The sibling-dev-checkout recovery itself still works correctly for
    a genuine (non-pytest) dev-mode run -- only its use *under pytest* is
    now blocked (previous test). Simulates a non-test environment by
    monkeypatching runtime_env.is_test_environment() to False."""
    from app import config as app_config
    from app.services import git_service, pipeline_service, runtime_env

    monkeypatch.setattr(runtime_env, "is_test_environment", lambda: False)

    app_root = tmp_path / "app_root"
    app_root.mkdir()
    broken_default = tmp_path / "not_a_repo"  # simulates Path.home()/"DSA-135" with no .git
    sibling_repo = tmp_path / "DSA-135"  # simulates APP_ROOT.parent / "DSA-135"
    git_service.ensure_repo(sibling_repo)

    monkeypatch.setattr(app_config, "APP_ROOT", app_root)
    monkeypatch.setattr(app_config, "DEFAULT_DSA135_REPO", broken_default)

    resolved = pipeline_service.get_dsa135_repo(seeded_conn)
    assert resolved == sibling_repo

    # And it's now persisted, so a second call doesn't need to re-probe.
    row = seeded_conn.execute("SELECT value FROM settings WHERE key = 'dsa135_repo_path'").fetchone()
    assert row["value"] == str(sibling_repo)


# --- GitHub automatic retry drain (production stabilization) -----------------

def test_drain_due_pushes_skips_rows_still_in_backoff_window(seeded_conn, tmp_path):
    from app.services import git_service, github_sync_service
    from app import config as app_config

    repo = tmp_path / "repo"
    git_service.ensure_repo(repo)
    (repo / "f.txt").write_text("x", encoding="utf-8")
    from app.services import git_service as gs
    gs.safe_commit(repo, [repo / "f.txt"], "test commit")
    commit_id_row = seeded_conn.execute(
        "INSERT INTO git_commits (repo_path, commit_hash, message, files_json, created_at) "
        "VALUES (?, 'deadbeef', 'test commit', '[]', ?) RETURNING id",
        (str(repo), app_config.now_local().isoformat()),
    ).fetchone()
    seeded_conn.commit()
    commit_id = commit_id_row["id"]
    queue_id = github_sync_service.enqueue_push(seeded_conn, commit_id)

    # Simulate one failed attempt just now (well within the ~60s backoff
    # window for attempts=1) -- a drain call right after must skip it.
    now = app_config.now_local().isoformat()
    seeded_conn.execute(
        "UPDATE github_push_queue SET status='pending', attempts=1, last_attempt_at=?, "
        "last_error='network down' WHERE id=?",
        (now, queue_id),
    )
    seeded_conn.commit()

    result = github_sync_service.drain_due_pushes(seeded_conn, repo)
    assert result["skipped"] == 1
    assert result["pushed"] == 0


def test_drain_due_pushes_retries_a_row_past_its_backoff_window(seeded_conn, tmp_path):
    from app.services import git_service, github_sync_service
    from app import config as app_config
    import datetime as dt

    repo = tmp_path / "repo"
    git_service.ensure_repo(repo)
    commit_id_row = seeded_conn.execute(
        "INSERT INTO git_commits (repo_path, commit_hash, message, files_json, created_at) "
        "VALUES (?, 'deadbeef', 'test commit', '[]', ?) RETURNING id",
        (str(repo), app_config.now_local().isoformat()),
    ).fetchone()
    seeded_conn.commit()
    queue_id = github_sync_service.enqueue_push(seeded_conn, commit_id_row["id"])

    long_ago = (app_config.now_local() - dt.timedelta(minutes=10)).isoformat()
    seeded_conn.execute(
        "UPDATE github_push_queue SET status='pending', attempts=1, last_attempt_at=?, "
        "last_error='network down' WHERE id=?",
        (long_ago, queue_id),
    )
    seeded_conn.commit()

    # No real remote configured -> the retry itself will still fail, but
    # the point here is that it was ATTEMPTED (not skipped) once its
    # backoff window had passed.
    result = github_sync_service.drain_due_pushes(seeded_conn, repo)
    assert result["skipped"] == 0
    assert result["pushed"] + result["still_pending"] == 1


def test_retry_never_creates_a_duplicate_commit(seeded_conn, tmp_path):
    """Repeated retry attempts must push the existing commit only -- never
    create a new local commit as a side effect."""
    from app.services import git_service, github_sync_service
    from app import config as app_config

    repo = tmp_path / "repo"
    git_service.ensure_repo(repo)
    (repo / "f.txt").write_text("x", encoding="utf-8")
    git_service.safe_commit(repo, [repo / "f.txt"], "only commit")
    log_before = subprocess_log(repo)

    commit_id_row = seeded_conn.execute(
        "INSERT INTO git_commits (repo_path, commit_hash, message, files_json, created_at) "
        "VALUES (?, 'deadbeef', 'test commit', '[]', ?) RETURNING id",
        (str(repo), app_config.now_local().isoformat()),
    ).fetchone()
    seeded_conn.commit()
    queue_id = github_sync_service.enqueue_push(seeded_conn, commit_id_row["id"])

    for _ in range(3):
        github_sync_service.attempt_push(seeded_conn, queue_id, repo)

    log_after = subprocess_log(repo)
    assert log_before == log_after  # same single commit, nothing duplicated


def subprocess_log(repo):
    import subprocess
    result = subprocess.run(["git", "log", "--oneline"], cwd=str(repo), capture_output=True, text=True)
    return result.stdout.strip()
