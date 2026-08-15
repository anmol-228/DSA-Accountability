"""Live LeetCode integration test mode (production stabilization pass,
section 9-13).

Exercises the REAL Chrome extension -> localhost API -> fresh-Accepted ->
code-capture -> Git -> GitHub pipeline end-to-end, for diagnostic purposes,
WITHOUT touching curriculum progress. This exists because Day 1 (the only
currently-active curriculum day) has no LeetCode task at all -- there is no
legitimate scheduled Day-1 LeetCode problem to test the browser path
against, and the pipeline must never be "tested" by faking real curriculum
completion.

Guarantees enforced by this module + its call sites in local_server.py:
  - never marks any curriculum task complete
  - never advances curriculum_days.completed / the active day
  - never schedules a real spaced revision
  - never records a streak / meaningful-activity event
  - never changes topic-readiness metrics
  - never writes under a real curriculum Week-*/Day-*/ folder
  - never counts toward the unique-solved-curriculum-problems count
  - commits, if any, land in an ISOLATED temporary git repository that
    shares the real DSA-135 remote only for the duration of a single
    disposable branch push+verify+cleanup -- the real learner working
    tree/branch is never opened or touched by this module at all.

Session/dedup/freshness/language anti-gaming logic is NOT weakened or
bypassed for test mode -- a test-mode Accepted event goes through the exact
same leetcode_service.handle_accepted_event() as a real one.
"""
from __future__ import annotations

import datetime as dt
import os
import shutil
import sqlite3
import stat
import tempfile
from pathlib import Path

from app import config
from app.services import git_service, runtime_env

_ACTIVE_KEY = "integration_test_active"
_SLUG_KEY = "integration_test_slug"
_LEETCODE_NUMBER_KEY = "integration_test_leetcode_number"
_TITLE_KEY = "integration_test_title"
_SESSION_ID_KEY = "integration_test_session_id"
_EXPIRES_AT_KEY = "integration_test_expires_at"
_REPO_PATH_KEY = "integration_test_repo_path"

_KEYS = (
    _ACTIVE_KEY, _SLUG_KEY, _LEETCODE_NUMBER_KEY, _TITLE_KEY, _SESSION_ID_KEY,
    _EXPIRES_AT_KEY, _REPO_PATH_KEY,
)

TEST_ARCHIVE_DIRNAME = ".integration-test"


def _integration_root() -> Path:
    return config.DATA_DIR.parent / "integration-tests"


def _is_managed_repo_path(path: Path) -> bool:
    try:
        return path.resolve().is_relative_to(_integration_root().resolve())
    except (OSError, ValueError):
        return False


def _remove_managed_repo(path: Path | None) -> bool:
    if path is None or not path.exists():
        return False
    if not _is_managed_repo_path(path):
        raise RuntimeError(f"refusing to delete non-managed integration path: {path}")
    def _clear_readonly_and_retry(function, failing_path, _exc_info):
        os.chmod(failing_path, stat.S_IWRITE)
        function(failing_path)

    # Git object files are commonly read-only on Windows; clear that bit only
    # inside the already-validated app-managed integration root.
    shutil.rmtree(path, onexc=_clear_readonly_and_retry)
    return True


def prepare_isolated_repo(source_repo: Path) -> Path:
    """Clone the learner repo's remote into an app-managed disposable path."""
    url = git_service.remote_url(source_repo)
    if not url:
        raise RuntimeError(f"source learner repo has no origin remote: {source_repo}")
    root = _integration_root()
    root.mkdir(parents=True, exist_ok=True)
    placeholder = Path(tempfile.mkdtemp(prefix="live-leetcode-", dir=root))
    placeholder.rmdir()  # clone_repo requires a non-existent explicit target
    try:
        git_service.clone_repo(url, placeholder)
        return placeholder
    except Exception:
        _remove_managed_repo(placeholder)
        raise


def start(
    conn: sqlite3.Connection, slug: str, leetcode_number: int, title: str,
    source_repo: Path | None = None,
) -> Path | None:
    """Arms test mode for exactly one problem (matched by slug, the same
    key the real extension sends). Clears any prior test-mode state first
    -- idempotent, safe to call again to restart against a different
    problem."""
    stop(conn)
    isolated_repo = prepare_isolated_repo(source_repo) if source_repo is not None else None
    expires_at = (config.now_local() + dt.timedelta(hours=2)).isoformat()
    conn.execute("INSERT INTO settings (key, value) VALUES (?, '1')", (_ACTIVE_KEY,))
    conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (_SLUG_KEY, slug))
    conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (_LEETCODE_NUMBER_KEY, str(leetcode_number)))
    conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (_TITLE_KEY, title))
    conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (_EXPIRES_AT_KEY, expires_at))
    if isolated_repo is not None:
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (_REPO_PATH_KEY, str(isolated_repo)))
    conn.commit()
    return isolated_repo


def stop(conn: sqlite3.Connection) -> None:
    repo_row = conn.execute("SELECT value FROM settings WHERE key = ?", (_REPO_PATH_KEY,)).fetchone()
    managed_repo = Path(repo_row["value"]) if repo_row and repo_row["value"] else None
    _remove_managed_repo(managed_repo)
    for key in _KEYS:
        conn.execute("DELETE FROM settings WHERE key = ?", (key,))
    conn.commit()


def clear_on_startup(conn: sqlite3.Connection) -> bool:
    present = conn.execute(
        "SELECT 1 FROM settings WHERE key LIKE 'integration_test_%' LIMIT 1"
    ).fetchone() is not None
    if present:
        stop(conn)
    return present


def status(conn: sqlite3.Connection) -> dict:
    def _get(key):
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    result = {
        "active": _get(_ACTIVE_KEY) == "1",
        "slug": _get(_SLUG_KEY),
        "leetcode_number": int(_get(_LEETCODE_NUMBER_KEY)) if _get(_LEETCODE_NUMBER_KEY) else None,
        "title": _get(_TITLE_KEY),
        "session_id": int(_get(_SESSION_ID_KEY)) if _get(_SESSION_ID_KEY) else None,
        "expires_at": _get(_EXPIRES_AT_KEY),
        "repo_path": _get(_REPO_PATH_KEY),
    }
    if result["active"] and result["expires_at"]:
        expires = dt.datetime.fromisoformat(result["expires_at"])
        if config.now_local() >= expires:
            stop(conn)
            return {
                "active": False, "slug": None, "leetcode_number": None,
                "title": None, "session_id": None, "expires_at": None, "repo_path": None,
            }
    return result


def repo_path(conn: sqlite3.Connection) -> Path:
    value = status(conn).get("repo_path")
    if not value:
        raise RuntimeError("live integration test has no managed disposable repository")
    path = Path(value)
    if not _is_managed_repo_path(path) and not runtime_env.is_test_environment():
        raise RuntimeError(f"integration repository is outside the managed root: {path}")
    return path


def is_active_for_slug(conn: sqlite3.Connection, slug: str) -> bool:
    s = status(conn)
    return bool(s["active"] and s["slug"] == slug)


def is_active_session(conn: sqlite3.Connection, session_id: int | None) -> bool:
    if session_id is None:
        return False
    s = status(conn)
    return bool(s["active"] and s["session_id"] == session_id)


def record_session(conn: sqlite3.Connection, session_id: int) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (_SESSION_ID_KEY, str(session_id)),
    )
    conn.commit()


def get_or_create_test_problem(conn: sqlite3.Connection, leetcode_number: int, slug: str, title: str) -> int:
    """A problem_sessions row requires a real problems.id. Reuses an
    existing row for this leetcode_number if the curriculum already
    created one (harmless -- the test path never touches task/day
    completion regardless of which problem row it points at); otherwise
    creates a minimal one. Never used for curriculum linkage."""
    row = conn.execute("SELECT id FROM problems WHERE leetcode_number = ?", (leetcode_number,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO problems (leetcode_number, title, slug, url) VALUES (?, ?, ?, ?)",
        (leetcode_number, title, slug, f"https://leetcode.com/problems/{slug}/"),
    )
    conn.commit()
    assert cur.lastrowid is not None
    return cur.lastrowid


def test_archive_path(repo_root: Path, filename: str) -> Path:
    if not runtime_env.is_test_environment() and not _is_managed_repo_path(repo_root):
        raise RuntimeError(f"refusing integration-test archive under non-managed repo: {repo_root}")
    d = repo_root / TEST_ARCHIVE_DIRNAME / "leetcode"
    d.mkdir(parents=True, exist_ok=True)
    return d / filename


def test_notes_path(repo_root: Path) -> Path:
    if not runtime_env.is_test_environment() and not _is_managed_repo_path(repo_root):
        raise RuntimeError(f"refusing integration-test notes under non-managed repo: {repo_root}")
    return repo_root / TEST_ARCHIVE_DIRNAME / "notes.md"
