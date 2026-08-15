"""GitHub push + durable retry queue.

Push failures caused by network/GitHub outages must never erase local
progress. A local Git commit (see git_service.safe_commit) is what counts
as "complete" for curriculum gating; the push is attempted immediately and,
on failure, queued for retry rather than blocking anything (spec 26-27).
"""
from __future__ import annotations

import datetime as _dt
import os
import sqlite3
from pathlib import Path

from app import config
from app.services import git_service

# Errors that mean "config is broken", not "try again later" — these should
# surface prominently in Settings rather than silently retry forever.
_CONFIG_ERROR_MARKERS = (
    "not a git repository",
    "does not appear to be a git repository",
    "repository not found",
    "could not read from remote repository",
    "no configured push destination",
    "remote-hung-up",
)

# Errors that look transient/network related and should stay queued.
_NETWORK_ERROR_MARKERS = (
    "could not resolve host",
    "connection timed out",
    "failed to connect",
    "network is unreachable",
    "temporary failure in name resolution",
    "the remote end hung up unexpectedly",
    "ssl_error",
    "timed out",
)


def auto_push_enabled(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT value FROM settings WHERE key = 'auto_push_enabled'"
    ).fetchone()
    return row is None or row["value"] == "1"


def enqueue_push(conn: sqlite3.Connection, commit_id: int) -> int:
    now = config.now_local().isoformat()
    cur = conn.execute(
        "INSERT INTO github_push_queue (commit_id, status, attempts, created_at) "
        "VALUES (?, 'pending', 0, ?)",
        (commit_id, now),
    )
    conn.commit()
    assert cur.lastrowid is not None
    return cur.lastrowid


def _classify_error(err: str) -> str:
    low = err.lower()
    if any(m in low for m in _CONFIG_ERROR_MARKERS):
        return "failed_config"
    return "pending"  # treat everything else (incl. network) as retry-later


def attempt_push(conn: sqlite3.Connection, queue_id: int, repo_path: Path) -> bool:
    row = conn.execute(
        "SELECT q.*, c.repo_path as commit_repo_path FROM github_push_queue q "
        "JOIN git_commits c ON q.commit_id = c.id WHERE q.id = ?",
        (queue_id,),
    ).fetchone()
    if row is None or row["status"] == "pushed":
        return row is not None and row["status"] == "pushed"

    now = config.now_local().isoformat()
    recorded_repo = Path(row["commit_repo_path"])
    if os.path.normcase(os.path.abspath(recorded_repo)) != os.path.normcase(os.path.abspath(repo_path)):
        error = f"queue repo mismatch: recorded={recorded_repo} requested={repo_path}"
        conn.execute(
            "UPDATE github_push_queue SET status='failed_config', attempts=attempts+1, "
            "last_attempt_at=?, last_error=? WHERE id=?",
            (now, error, queue_id),
        )
        conn.commit()
        return False
    success, error = git_service.push(repo_path)
    if success:
        conn.execute(
            "UPDATE github_push_queue SET status='pushed', attempts=attempts+1, last_attempt_at=? WHERE id=?",
            (now, queue_id),
        )
        conn.commit()
        return True

    status = _classify_error(error or "")
    conn.execute(
        "UPDATE github_push_queue SET status=?, attempts=attempts+1, last_attempt_at=?, last_error=? WHERE id=?",
        (status, now, error, queue_id),
    )
    conn.commit()
    return False


def process_queue(conn: sqlite3.Connection, repo_path: Path) -> dict:
    """Attempts every pending push once. Returns a summary dict.
    Never pushes to a different repo than the one recorded for the commit."""
    pending = conn.execute(
        "SELECT id FROM github_push_queue WHERE status = 'pending' ORDER BY id"
    ).fetchall()
    pushed, still_pending = 0, 0
    for row in pending:
        if attempt_push(conn, row["id"], repo_path):
            pushed += 1
        else:
            still_pending += 1
    return {"pushed": pushed, "still_pending": still_pending, "total": len(pending)}


def queue_status(conn: sqlite3.Connection) -> dict:
    rows = conn.execute("SELECT status, COUNT(*) c FROM github_push_queue GROUP BY status").fetchall()
    return {r["status"]: r["c"] for r in rows}


# --- automatic retry drain ----------------------------------------------------
# process_queue() above always existed but nothing ever called it after the
# one immediate attempt made right after enqueue_push() -- a push that failed
# with a retryable error stayed "pending" forever with no automatic recovery.
# This adds a capped-backoff drain safe to call repeatedly (startup, and on a
# periodic timer) without hammering GitHub on every call.

_BACKOFF_SECONDS_BY_ATTEMPTS = {1: 60, 2: 5 * 60, 3: 15 * 60}
_BACKOFF_CAP_SECONDS = 30 * 60


def _due_for_retry(row: sqlite3.Row, now) -> bool:
    if row["last_attempt_at"] is None:
        return True
    last = _dt.datetime.fromisoformat(row["last_attempt_at"])
    wait_seconds = _BACKOFF_SECONDS_BY_ATTEMPTS.get(row["attempts"], _BACKOFF_CAP_SECONDS)
    return (now - last).total_seconds() >= wait_seconds


def drain_due_pushes(conn: sqlite3.Connection, repo_path: Path) -> dict:
    """Retries only the pending rows whose backoff window has elapsed
    (attempt 1 ~60s after the last try, attempt 2 ~5min, attempt 3
    ~15min, then capped at 30min) -- safe to call on every startup and on
    a short periodic timer without spamming GitHub. Never pushes to a
    different repo than the one recorded for the commit (delegates to
    attempt_push/git_service.push exactly like process_queue). Retrying
    never creates a new commit -- it only re-runs `git push` for the
    already-committed hash recorded on git_commits.
    """
    pending = conn.execute(
        "SELECT * FROM github_push_queue WHERE status = 'pending' ORDER BY id"
    ).fetchall()
    if not auto_push_enabled(conn):
        return {"pushed": 0, "still_pending": len(pending), "skipped": len(pending), "total": len(pending)}
    now = config.now_local()
    pushed, still_pending, skipped = 0, 0, 0
    for row in pending:
        if not _due_for_retry(row, now):
            skipped += 1
            continue
        if attempt_push(conn, row["id"], repo_path):
            pushed += 1
        else:
            still_pending += 1
    return {"pushed": pushed, "still_pending": still_pending, "skipped": skipped, "total": len(pending)}
