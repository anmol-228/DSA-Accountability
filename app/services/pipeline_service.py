"""Orchestrates the end-to-end pipeline: Accepted code -> local file ->
reflection -> local Git commit -> GitHub push -> task/day completion
(spec sections 17-27). This is the single place that wires together
code_sync, git, github_sync, progression, revision, and streak services so
the UI layer stays thin.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from app import config
from app.services import (
    code_sync_service,
    docs_sync_service,
    git_service,
    github_sync_service,
    integration_test_service,
    progression_service as prog,
    revision_service,
    runtime_env,
    streak_service,
)


def get_dsa135_repo(conn: sqlite3.Connection) -> Path:
    """Single source of truth for the learner repo path (every other
    consumer -- local_server.py, first_run_wizard.py, settings_dialog.py --
    must call this rather than re-deriving the path independently; a
    duplicate lookup in local_server.py used to disagree silently).

    Resolution order:
      1. the persisted `dsa135_repo_path` setting, if one exists at all --
         trusted unconditionally once explicitly set, even if the target
         isn't a git repo *yet* (ensure_repo() is what turns a freshly
         configured, not-yet-initialized directory into one; this
         resolver must never second-guess a deliberately configured path
         just because nothing has been committed there yet);
      2. only when NO setting has ever been persisted: config.DEFAULT_
         DSA135_REPO, if that's already a valid git repo -- and if so,
         persist it so future lookups skip straight to (1);
      3. only when NO setting has ever been persisted and (2) didn't
         match: the sibling dev-checkout convention (APP_ROOT.parent /
         "DSA-135"). Note this only helps in dev mode -- when frozen,
         config.APP_ROOT resolves inside the PyInstaller extraction
         folder, not the real source checkout, so this candidate is a
         no-op for a packaged build. It's kept because it's harmless and
         correctly self-heals a dev-mode install; it is NOT a fix for the
         frozen case on its own.

      The real production case this whole resolver exists for -- a
      packaged build whose frozen-mode default (Path.home()/"DSA-135")
      was a stray, non-git folder while the actual configured/pushed repo
      lived elsewhere with no setting ever persisted -- was repaired the
      same way a user would via Settings -> "Save repo path": by
      explicitly persisting the confirmed-correct path once (see
      docs/PRODUCTION_STABILIZATION_2026-08-12.md). This resolver's job
      going forward is simply to never lose or second-guess that
      persisted setting again, and to self-heal automatically for the
      narrower cases (1)/(2) actually cover.

      Never auto-inits a *new* repo here -- only adopts one that's
      already valid, and only persists a path once it's been confirmed
      to actually be a git repo.
    """
    row = conn.execute("SELECT value FROM settings WHERE key = 'dsa135_repo_path'").fetchone()
    if row and row["value"]:
        resolved = Path(row["value"])
        runtime_env.assert_repo_access_allowed(resolved, "resolve configured learner repo")
        return resolved

    if runtime_env.is_test_environment():
        # Structural guard (final production repair pass): a real incident
        # this session proved that falling through to config.DEFAULT_
        # DSA135_REPO here could resolve to a real learner repo in dev/pytest
        # context, silently writing test data into user work.
        # Rather than trust every test to remember set_dsa135_repo(), make
        # the unconfigured case fail loudly under pytest instead of
        # guessing. See app/services/runtime_env.py and
        # docs/PRODUCTION_STABILIZATION_2026-08-12.md's contamination
        # incident writeup.
        return runtime_env.get_test_repo_path()

    if git_service.is_repo(config.DEFAULT_DSA135_REPO):
        set_dsa135_repo(conn, config.DEFAULT_DSA135_REPO)
        return config.DEFAULT_DSA135_REPO

    sibling = config.APP_ROOT.parent / "DSA-135"
    if sibling != config.DEFAULT_DSA135_REPO and git_service.is_repo(sibling):
        set_dsa135_repo(conn, sibling)
        return sibling

    return config.DEFAULT_DSA135_REPO


def set_dsa135_repo(conn: sqlite3.Connection, path: Path) -> None:
    runtime_env.assert_repo_access_allowed(path, "configure learner repo")
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('dsa135_repo_path', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (str(path),),
    )
    conn.commit()


def _commit_message(task_row: sqlite3.Row, problem_row: sqlite3.Row | None) -> str:
    day = task_row["day_number"]
    if task_row["task_type"] == "revision" and problem_row:
        return f"dsa(review): revisit LC{problem_row['leetcode_number']} {problem_row['title']}"
    if task_row["task_type"] == "leetcode" and problem_row:
        return f"dsa(day-{day:03d}): solve LC{problem_row['leetcode_number']} {problem_row['title']}"
    if task_row["task_type"] == "exercise":
        return f"dsa(day-{day:03d}): complete Java exercise — {task_row['title']}"
    return f"dsa(day-{day:03d}): complete {task_row['task_type']} — {task_row['title']}"


def _push_committed_work(conn: sqlite3.Connection, commit_id: int, repo_root: Path) -> str:
    """Push when enabled/configured; otherwise keep the successful local commit."""
    if not github_sync_service.auto_push_enabled(conn):
        return "disabled"
    if not git_service.has_remote(repo_root):
        return "local_only"
    queue_id = github_sync_service.enqueue_push(conn, commit_id)
    pushed = github_sync_service.attempt_push(conn, queue_id, repo_root)
    return "pushed" if pushed else "queued"


def finalize_leetcode_task(
    conn: sqlite3.Connection,
    task_id: int,
    code: str,
    reflection: dict,
    repo_root: Path | None = None,
) -> dict:
    """Full pipeline for a leetcode/revision task: writes the solution file,
    records the reflection, commits locally, attempts a GitHub push, marks
    the task complete (which may complete the day and unlock the next),
    schedules the next spaced revision, and records meaningful activity.

    `reflection` must contain: pattern, time_complexity, space_complexity,
    explanation, assistance_level, confidence.
    """
    repo_root = repo_root or get_dsa135_repo(conn)
    task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if task is None:
        raise ValueError(f"No task {task_id}")
    if task["task_type"] not in ("leetcode", "revision"):
        raise ValueError(f"finalize_leetcode_task called on task_type={task['task_type']}")

    problem = conn.execute("SELECT * FROM problems WHERE id = ?", (task["problem_id"],)).fetchone()
    now = config.now_local().isoformat()

    git_service.ensure_repo(repo_root)
    target_path = code_sync_service.leetcode_file_path(
        repo_root, task["day_number"], problem["leetcode_number"], problem["title"]
    )
    written_path, backup_path = code_sync_service.write_solution(target_path, code)

    notes_path = code_sync_service.notes_file_path(repo_root, task["day_number"])
    _append_problem_notes(notes_path, task, problem, reflection)

    conn.execute(
        "INSERT INTO reflections (task_id, problem_id, pattern, time_complexity, space_complexity, "
        "explanation, assistance_level, confidence, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (task_id, problem["id"], reflection.get("pattern"), reflection.get("time_complexity"),
         reflection.get("space_complexity"), reflection["explanation"], reflection["assistance_level"],
         reflection["confidence"], now),
    )
    conn.execute(
        "INSERT INTO confidence_history (problem_id, confidence, source, created_at) VALUES (?, ?, ?, ?)",
        (problem["id"], reflection["confidence"], task["task_type"], now),
    )
    conn.execute(
        "INSERT INTO attempts (problem_id, task_id, day_number, language, result, assistance_level, created_at) "
        "VALUES (?, ?, ?, 'java', 'accepted', ?, ?)",
        (problem["id"], task_id, task["day_number"], reflection["assistance_level"], now),
    )
    conn.commit()

    commit_files = [written_path, notes_path]
    message = _commit_message(task, problem)
    commit_result = git_service.safe_commit(repo_root, commit_files, message)

    result: dict = {"commit": commit_result.success, "commit_error": commit_result.error,
                     "backup_created": str(backup_path) if backup_path else None,
                     "push": "not_attempted"}

    if commit_result.success:
        cur = conn.execute(
            "INSERT INTO git_commits (repo_path, commit_hash, message, files_json, task_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(repo_root), commit_result.commit_hash, message,
             __import__("json").dumps([str(f) for f in commit_files]), task_id, now),
        )
        commit_id = cur.lastrowid
        conn.commit()

        result["push"] = _push_committed_work(conn, commit_id, repo_root)

        day_completed = prog.complete_task(conn, task_id)
        result["day_completed"] = day_completed

        if task["task_type"] == "revision":
            row = conn.execute(
                "SELECT id FROM revision_schedule WHERE task_id = ? AND status = 'required_today'",
                (task_id,),
            ).fetchone()
            if row:
                revision_service.complete_revision(conn, row["id"], reflection["confidence"])
        else:
            revision_service.schedule_revision(conn, problem["id"], reflection["confidence"])

        streak_service.record_meaningful_activity(conn)
        result["docs_sync"] = docs_sync_service.sync_and_commit(conn, repo_root)

    return result


def finalize_simple_task(conn: sqlite3.Connection, task_id: int, note: str | None = None,
                          code: str | None = None, repo_root: Path | None = None) -> dict:
    """For exercise / concept / repair / oa / mock tasks: optional code file
    + optional note, local commit if there's anything to commit, then
    completes the task (and possibly the day)."""
    repo_root = repo_root or get_dsa135_repo(conn)
    task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if task is None:
        raise ValueError(f"No task {task_id}")

    now = config.now_local().isoformat()
    commit_files: list[Path] = []

    if code and task["task_type"] == "exercise":
        git_service.ensure_repo(repo_root)
        target_path = code_sync_service.exercise_file_path(
            repo_root, task["day_number"], task["canonical_filename"]
        )
        written_path, _backup = code_sync_service.write_solution(target_path, code)
        commit_files.append(written_path)

    if note:
        notes_path = code_sync_service.notes_file_path(repo_root, task["day_number"])
        notes_path.parent.mkdir(parents=True, exist_ok=True)
        with notes_path.open("a", encoding="utf-8") as f:
            f.write(f"\n## {task['title']} ({now})\n{note}\n")
        commit_files.append(notes_path)

    result: dict = {"commit": False, "push": "not_attempted"}
    if commit_files:
        message = _commit_message(task, None)
        commit_result = git_service.safe_commit(repo_root, commit_files, message)
        result["commit"] = commit_result.success
        result["commit_error"] = commit_result.error
        if commit_result.success:
            cur = conn.execute(
                "INSERT INTO git_commits (repo_path, commit_hash, message, files_json, task_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (str(repo_root), commit_result.commit_hash, message,
                 __import__("json").dumps([str(f) for f in commit_files]), task_id, now),
            )
            commit_id = cur.lastrowid
            conn.commit()
            result["push"] = _push_committed_work(conn, commit_id, repo_root)

    day_completed = prog.complete_task(conn, task_id)
    result["day_completed"] = day_completed
    streak_service.record_meaningful_activity(conn)
    if commit_files:
        result["docs_sync"] = docs_sync_service.sync_and_commit(conn, repo_root)
    return result


def finalize_exercise_task(conn: sqlite3.Connection, task_id: int, note: str,
                            repo_root: Path | None = None) -> dict:
    """Finalizes a standalone Java exercise written in VS Code (spec:
    "the DSA Accountability app must not be a code editor"). The source
    file must already exist on disk at its canonical path, already pass
    compilation and functional tests (the caller — ExerciseTaskDialog —
    is responsible for gating on that via build_service before ever
    calling this). This function only archives what's already there: it
    never writes or rewrites the learner's source."""
    repo_root = repo_root or get_dsa135_repo(conn)
    task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if task is None:
        raise ValueError(f"No task {task_id}")
    if task["task_type"] != "exercise":
        raise ValueError(f"finalize_exercise_task called on task_type={task['task_type']}")
    if not task["canonical_filename"]:
        raise ValueError(f"Task {task_id} has no canonical_filename set")

    git_service.ensure_repo(repo_root)
    target_path = code_sync_service.exercise_file_path(
        repo_root, task["day_number"], task["canonical_filename"]
    )
    if not target_path.exists():
        raise FileNotFoundError(f"Expected source file not found: {target_path}")

    now = config.now_local().isoformat()
    commit_files = [target_path]

    notes_path = code_sync_service.notes_file_path(repo_root, task["day_number"])
    notes_path.parent.mkdir(parents=True, exist_ok=True)
    with notes_path.open("a", encoding="utf-8") as f:
        f.write(
            f"\n## {task['title']}\n\n"
            f"What I learned:\n{note}\n\n"
            f"Completed: {now}\n\n"
            f"Validation: Passed (compiled, functional tests green)\n"
        )
    commit_files.append(notes_path)

    message = _commit_message(task, None)
    commit_result = git_service.safe_commit(repo_root, commit_files, message)

    result: dict = {"commit": commit_result.success, "commit_error": commit_result.error,
                     "push": "not_attempted", "day_completed": False}

    if commit_result.success:
        # Completion is gated on a successful LOCAL commit (matching
        # finalize_leetcode_task) -- "safe local Git commit" is one of the
        # spec's own completion criteria for a local exercise, not merely
        # a side effect. A GitHub push failure, on the other hand, never
        # blocks completion (network is best-effort + queued/retried).
        cur = conn.execute(
            "INSERT INTO git_commits (repo_path, commit_hash, message, files_json, task_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(repo_root), commit_result.commit_hash, message,
             __import__("json").dumps([str(f) for f in commit_files]), task_id, now),
        )
        commit_id = cur.lastrowid
        conn.commit()
        assert commit_id is not None

        result["push"] = _push_committed_work(conn, commit_id, repo_root)

        result["day_completed"] = prog.complete_task(conn, task_id)
        streak_service.record_meaningful_activity(conn)
        result["docs_sync"] = docs_sync_service.sync_and_commit(conn, repo_root)

    return result


def finalize_integration_test(conn: sqlite3.Connection, event_id: int, note: str,
                              repo_root: Path | None = None, push: bool = True) -> dict:
    """Finalize once and always disarm/clean managed integration-test state."""
    managed_row = conn.execute(
        "SELECT value FROM settings WHERE key = 'integration_test_repo_path'"
    ).fetchone()
    managed_repo = Path(managed_row["value"]) if managed_row and managed_row["value"] else None
    try:
        result = _finalize_integration_test_impl(conn, event_id, note, repo_root, push)
    finally:
        integration_test_service.stop(conn)
    if managed_repo is not None:
        result["isolated_repo_removed"] = not managed_repo.exists()
    return result


def _finalize_integration_test_impl(conn: sqlite3.Connection, event_id: int, note: str,
                                     repo_root: Path | None = None, push: bool = True) -> dict:
    """Commits the isolated .integration-test archive produced by a live
    LeetCode integration-test Accepted event (production stabilization
    pass, section 9-13) to a disposable temporary branch, optionally
    pushes and verifies it against the real DSA-135 remote, then cleans
    up completely -- never touching curriculum tasks/days, streaks,
    revisions, or readiness metrics, and never leaving the real repo on
    any branch but the one it started on.

    Aborts (rather than risk mixing test-branch operations with real
    uncommitted work) if the working tree isn't clean beforehand.
    """
    repo_root = repo_root or integration_test_service.repo_path(conn)
    row = conn.execute(
        "SELECT * FROM code_sync_events WHERE leetcode_event_id = ? AND status = 'captured' "
        "ORDER BY id DESC LIMIT 1",
        (event_id,),
    ).fetchone()
    if row is None or not row["file_path"]:
        return {"committed": False, "pushed": False, "reason": "no captured integration-test file for this event"}

    written_path = Path(row["file_path"])
    notes_path = integration_test_service.test_notes_path(repo_root)
    notes_path.parent.mkdir(parents=True, exist_ok=True)
    with notes_path.open("a", encoding="utf-8") as f:
        f.write(
            f"\n# Integration test — {config.now_local().isoformat()}\n\n"
            f"NOT curriculum progress. Verifies the real Chrome extension -> desktop -> "
            f"Git/GitHub pipeline only.\n\n{note}\n"
        )

    if not git_service.is_repo(repo_root):
        return {"committed": False, "pushed": False, "reason": "DSA-135 repo not initialized"}
    # The test archive itself was just written to disk (untracked) and is
    # exactly what's about to be committed -- only reject on OTHER dirty
    # state, which would indicate real uncommitted work that must not be
    # touched by this operation.
    if not git_service.is_working_tree_clean_except(repo_root, integration_test_service.TEST_ARCHIVE_DIRNAME):
        return {"committed": False, "pushed": False,
                 "reason": "working tree not clean outside .integration-test/ -- aborted rather than "
                           "risk mixing in real uncommitted work"}

    original_branch = git_service.current_branch(repo_root)
    branch_name = f"integration-test-live-leetcode-{config.now_local().strftime('%Y%m%d-%H%M%S')}"

    created, err = git_service.create_and_checkout_branch(repo_root, branch_name, base=original_branch)
    if not created:
        return {"committed": False, "pushed": False, "reason": f"could not create test branch: {err}"}

    commit_result = git_service.safe_commit(
        repo_root, [written_path, notes_path],
        f"integration-test: verify live LeetCode pipeline (not curriculum progress)",
    )
    result = {"committed": commit_result.success, "pushed": False, "branch": branch_name,
               "commit_hash": commit_result.commit_hash, "error": commit_result.error}

    if commit_result.success and push and git_service.has_remote(repo_root):
        pushed, push_err = git_service.push(repo_root, branch=branch_name)
        result["pushed"] = pushed
        if not pushed:
            result["push_error"] = push_err
        else:
            result["remote_branch_verified"] = git_service.remote_branch_exists(repo_root, branch_name)
            git_service.delete_remote_branch(repo_root, branch_name)

    # Always return to the original branch and remove the local disposable
    # branch, regardless of commit/push outcome above.
    git_service.checkout(repo_root, original_branch)
    git_service.delete_local_branch(repo_root, branch_name)
    result["returned_to_branch"] = git_service.current_branch(repo_root)
    result["working_tree_clean_after"] = git_service.is_working_tree_clean(repo_root)
    return result


def _append_problem_notes(notes_path: Path, task: sqlite3.Row, problem: sqlite3.Row, reflection: dict) -> None:
    notes_path.parent.mkdir(parents=True, exist_ok=True)
    entry = (
        f"\n# LC {problem['leetcode_number']} — {problem['title']}\n\n"
        f"Curriculum Day: {task['day_number']}\n"
        f"Solved Date: {config.today_local().isoformat()}\n\n"
        f"## Pattern\n{reflection.get('pattern') or '(not specified)'}\n\n"
        f"## My Approach\n{reflection['explanation']}\n\n"
        f"## Complexity\nTime: {reflection.get('time_complexity') or '?'}\n"
        f"Space: {reflection.get('space_complexity') or '?'}\n\n"
        f"## Assistance\n{reflection['assistance_level']}\n\n"
        f"## Confidence\n{reflection['confidence'].upper()}\n"
    )
    with notes_path.open("a", encoding="utf-8") as f:
        f.write(entry)
