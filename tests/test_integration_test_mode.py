"""Live LeetCode integration test mode (production stabilization pass,
section 9-13): must exercise the real session-start / Accepted / freshness
pipeline for an explicitly armed, non-curriculum problem WITHOUT ever
touching curriculum progress, and must commit/push (if configured) through
a disposable branch that's fully cleaned up afterward, never disturbing the
repo's original branch or working tree state.
"""
from __future__ import annotations

import datetime as dt
import subprocess

from app.services import (
    git_service,
    integration_test_service,
    leetcode_service,
    pipeline_service,
    progression_service as prog,
)


def _init_bare_remote(tmp_path):
    remote_path = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote_path)], check=True, capture_output=True)
    return remote_path


def _init_repo_with_remote(tmp_path):
    repo_root = tmp_path / "DSA-135"
    git_service.ensure_repo(repo_root)
    (repo_root / "README.md").write_text("# DSA-135\n", encoding="utf-8")
    git_service.safe_commit(repo_root, [repo_root / "README.md"], "initial commit")
    remote_path = _init_bare_remote(tmp_path)
    git_service.add_remote(repo_root, str(remote_path))
    git_service.push(repo_root, branch="main")
    return repo_root


# --- arming + session-start isolation -----------------------------------------

def test_session_start_creates_session_for_armed_test_slug_not_in_curriculum(seeded_conn):
    integration_test_service.start(seeded_conn, "reverse-integer", 7, "Reverse Integer")
    assert integration_test_service.is_active_for_slug(seeded_conn, "reverse-integer") is True

    problem_id = integration_test_service.get_or_create_test_problem(seeded_conn, 7, "reverse-integer", "Reverse Integer")
    session_id = leetcode_service.start_or_reuse_session(seeded_conn, problem_id, None, None, "solve")
    integration_test_service.record_session(seeded_conn, session_id)

    row = seeded_conn.execute("SELECT * FROM problem_sessions WHERE id = ?", (session_id,)).fetchone()
    assert row is not None
    assert row["ended_at"] is None


def test_unarmed_slug_never_gets_a_test_mode_session(seeded_conn):
    assert integration_test_service.is_active_for_slug(seeded_conn, "reverse-integer") is False


def test_stop_clears_armed_state(seeded_conn):
    integration_test_service.start(seeded_conn, "reverse-integer", 7, "Reverse Integer")
    integration_test_service.stop(seeded_conn)
    assert integration_test_service.status(seeded_conn)["active"] is False


def test_managed_integration_repo_is_a_disposable_clone_and_stop_removes_it(seeded_conn, tmp_path):
    source_repo = _init_repo_with_remote(tmp_path)
    source_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(source_repo), capture_output=True, text=True, check=True,
    ).stdout.strip()
    isolated = integration_test_service.start(
        seeded_conn, "reverse-integer", 7, "Reverse Integer", source_repo=source_repo,
    )
    assert isolated is not None
    assert isolated != source_repo
    assert (isolated / ".git").exists()
    assert git_service.is_working_tree_clean(source_repo)

    integration_test_service.stop(seeded_conn)
    assert not isolated.exists()
    assert git_service.is_working_tree_clean(source_repo)
    current_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(source_repo), capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert current_head == source_head


def test_startup_cleanup_disarms_leftover_mode(seeded_conn):
    integration_test_service.start(seeded_conn, "reverse-integer", 7, "Reverse Integer")
    assert integration_test_service.clear_on_startup(seeded_conn) is True
    assert integration_test_service.status(seeded_conn)["active"] is False
    assert integration_test_service.clear_on_startup(seeded_conn) is False


# --- Accepted event isolation: never touches curriculum -----------------------

def test_test_mode_accepted_event_does_not_touch_curriculum_progress(seeded_conn):
    conn = seeded_conn
    before_active_day = prog.get_active_day(conn)
    before_completed = conn.execute("SELECT COUNT(*) c FROM curriculum_days WHERE completed = 1").fetchone()["c"]
    before_streak = conn.execute("SELECT COUNT(*) c FROM daily_activity WHERE meaningful_activity = 1").fetchone()["c"]
    before_revisions = conn.execute("SELECT COUNT(*) c FROM revision_schedule").fetchone()["c"]

    integration_test_service.start(conn, "reverse-integer", 7, "Reverse Integer")
    problem_id = integration_test_service.get_or_create_test_problem(conn, 7, "reverse-integer", "Reverse Integer")
    session_id = leetcode_service.start_or_reuse_session(conn, problem_id, None, None, "solve")
    integration_test_service.record_session(conn, session_id)

    payload = {
        "slug": "reverse-integer", "language": "java", "code": "class Solution {}",
        "code_capture_method": "monaco_global",
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": "fresh_submission",
    }
    result = leetcode_service.handle_accepted_event(conn, payload)
    assert result.status == "ok"
    assert integration_test_service.is_active_session(conn, result.session_id) is True

    after_active_day = prog.get_active_day(conn)
    after_completed = conn.execute("SELECT COUNT(*) c FROM curriculum_days WHERE completed = 1").fetchone()["c"]
    after_streak = conn.execute("SELECT COUNT(*) c FROM daily_activity WHERE meaningful_activity = 1").fetchone()["c"]
    after_revisions = conn.execute("SELECT COUNT(*) c FROM revision_schedule").fetchone()["c"]

    assert after_active_day == before_active_day
    assert after_completed == before_completed
    assert after_streak == before_streak
    assert after_revisions == before_revisions


# --- finalize_integration_test: isolated branch, real push, real cleanup ------

def test_finalize_integration_test_uses_disposable_branch_and_restores_main(seeded_conn, tmp_path):
    conn = seeded_conn
    repo_root = _init_repo_with_remote(tmp_path)
    pipeline_service.set_dsa135_repo(conn, repo_root)

    integration_test_service.start(conn, "reverse-integer", 7, "Reverse Integer")
    problem_id = integration_test_service.get_or_create_test_problem(conn, 7, "reverse-integer", "Reverse Integer")
    session_id = leetcode_service.start_or_reuse_session(conn, problem_id, None, None, "solve")
    integration_test_service.record_session(conn, session_id)

    payload = {
        "slug": "reverse-integer", "language": "java", "code": "class Solution { int x; }",
        "code_capture_method": "monaco_global",
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": "fresh_submission",
    }
    accepted = leetcode_service.handle_accepted_event(conn, payload)
    assert accepted.status == "ok"

    # Mirror what local_server._handle_accepted does for a test-mode event:
    # write the code into the isolated archive path and record it.
    from app.services import code_sync_service
    target = integration_test_service.test_archive_path(repo_root, "LC0007_ReverseInteger.java")
    written_path, _ = code_sync_service.write_solution(target, payload["code"])
    conn.execute(
        "INSERT INTO code_sync_events (leetcode_event_id, file_path, status, created_at) "
        "VALUES (?, ?, 'captured', ?)",
        (accepted.event_id, str(written_path), "2026-08-12T00:00:00+05:30"),
    )
    conn.commit()

    assert git_service.current_branch(repo_root) == "main"
    result = pipeline_service.finalize_integration_test(conn, accepted.event_id, "real test note", repo_root)

    assert result["committed"] is True
    assert result["pushed"] is True
    assert result["remote_branch_verified"] is True  # confirmed present on the remote right after push
    assert result["returned_to_branch"] == "main"
    assert result["working_tree_clean_after"] is True
    assert git_service.current_branch(repo_root) == "main"
    assert git_service.is_working_tree_clean(repo_root) is True

    # The disposable branch must not still exist locally or on the remote.
    branches = subprocess.run(["git", "branch"], cwd=str(repo_root), capture_output=True, text=True).stdout
    assert result["branch"] not in branches
    assert git_service.remote_branch_exists(repo_root, result["branch"]) is False
    assert integration_test_service.status(conn)["active"] is False

    # Real curriculum files under Week-*/Day-*/ were never touched.
    curriculum_dirs = list(repo_root.glob("Week-*"))
    assert curriculum_dirs == []


def test_finalize_integration_test_aborts_if_working_tree_dirty(seeded_conn, tmp_path):
    conn = seeded_conn
    repo_root = _init_repo_with_remote(tmp_path)
    pipeline_service.set_dsa135_repo(conn, repo_root)
    (repo_root / "uncommitted.txt").write_text("dirty", encoding="utf-8")  # untracked, dirty tree

    integration_test_service.start(conn, "reverse-integer", 7, "Reverse Integer")
    problem_id = integration_test_service.get_or_create_test_problem(conn, 7, "reverse-integer", "Reverse Integer")
    session_id = leetcode_service.start_or_reuse_session(conn, problem_id, None, None, "solve")
    integration_test_service.record_session(conn, session_id)
    payload = {
        "slug": "reverse-integer", "language": "java", "code": "class Solution {}",
        "code_capture_method": "monaco_global",
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(), "source": "fresh_submission",
    }
    accepted = leetcode_service.handle_accepted_event(conn, payload)
    from app.services import code_sync_service
    target = integration_test_service.test_archive_path(repo_root, "x.java")
    written_path, _ = code_sync_service.write_solution(target, payload["code"])
    conn.execute(
        "INSERT INTO code_sync_events (leetcode_event_id, file_path, status, created_at) VALUES (?, ?, 'captured', ?)",
        (accepted.event_id, str(written_path), "2026-08-12T00:00:00+05:30"),
    )
    conn.commit()

    result = pipeline_service.finalize_integration_test(conn, accepted.event_id, "note", repo_root)
    assert result["committed"] is False
    assert "not clean" in result["reason"]
    assert git_service.current_branch(repo_root) == "main"  # never even attempted to branch
    assert integration_test_service.status(conn)["active"] is False
