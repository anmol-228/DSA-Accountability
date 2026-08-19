"""Regenerates DSA-135's top-level progress docs (PROGRESS.md, COMPLETED.md)
deterministically from live database state, and commits them in the same
step as the triggering task's own commit.

These two files are the only "current state" surfaces the app does not
otherwise keep live: the desktop UI, the local API, and the export feature
all re-query the database on every read, so they can never drift. A
markdown file committed to a separate repo has no such guarantee unless
something regenerates it -- prior to this module, nothing did, so these
files could only ever be as fresh as the last person who remembered to
hand-edit them. Calling sync_and_commit() after every real completion
closes that gap structurally rather than relying on memory.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from app.services import git_service, progression_service as prog, schedule_service


def _all_days(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT day_number, title, original_due_date, completed, completed_at "
        "FROM curriculum_days ORDER BY day_number"
    ).fetchall()


def _tasks_for_day(conn: sqlite3.Connection, day_number: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT title, task_type, completed FROM tasks "
        "WHERE day_number = ? AND required = 1 ORDER BY id",
        (day_number,),
    ).fetchall()


def render_progress_md(conn: sqlite3.Connection) -> str:
    status = prog.get_status(conn)
    days = _all_days(conn)

    lines = [
        "# Progress",
        "",
        f"Last updated: {status.today.isoformat()}",
        "",
        "This file is generated automatically by the DSA Accountability app",
        "after every completed task -- it cannot fall out of sync with the",
        "app's own database, which remains the authoritative source. See",
        "[COMPLETED.md](COMPLETED.md) for the verified per-exercise breakdown.",
        "",
        "## Current status",
        "",
    ]
    if status.active_day is None:
        lines.append("**All 135 / 135 days complete.**")
    else:
        active_tasks = _tasks_for_day(conn, status.active_day)
        done_today = sum(1 for t in active_tasks if t["completed"])
        lines.append(
            f"**Day {status.active_day:02d} / 135 — active, "
            f"{done_today} / {len(active_tasks)} tasks so far.**"
        )
    lines += [
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Active curriculum day | {status.active_day if status.active_day else '—'} / 135 |",
        f"| Days fully complete | {status.completed_days} / 135 |",
        f"| Schedule delay | {status.schedule_delay_days}d |",
        f"| Target finish (locked) | {schedule_service.target_end_date(conn).isoformat()} |",
        "",
        "## All days",
        "",
        "| Day | Title | Status | Completed |",
        "|---:|---|---|---|",
    ]
    for d in days:
        state = "✅ complete" if d["completed"] else (
            "🟢 active" if d["day_number"] == status.active_day else "⬜ locked"
        )
        completed_at = (d["completed_at"] or "")[:10]
        lines.append(f"| {d['day_number']} | {d['title']} | {state} | {completed_at} |")
    lines.append("")
    return "\n".join(lines)


def render_completed_md(conn: sqlite3.Connection) -> str:
    status = prog.get_status(conn)
    days = _all_days(conn)

    lines = [
        "# Completed Work",
        "",
        "Generated automatically from the DSA Accountability app's own",
        "database -- reflects real completed tasks only, never assumed from",
        "a commit message or file location. Local exercises are only marked",
        "complete after they compile and pass the app's own functional-test",
        "suite; LeetCode problems only after a fresh, genuine Accepted",
        "submission. Nothing here is filled in by AI on the learner's behalf.",
        "",
    ]
    relevant = [d for d in days if d["completed"] or d["day_number"] == status.active_day]
    for d in relevant:
        tasks = _tasks_for_day(conn, d["day_number"])
        if d["completed"]:
            lines.append(f"## Day {d['day_number']} — {d['title']} — ✅ COMPLETE")
        else:
            done = sum(1 for t in tasks if t["completed"])
            lines.append(f"## Day {d['day_number']} — {d['title']} — active, {done} / {len(tasks)} tasks")
        lines.append("")
        for t in tasks:
            mark = "✅" if t["completed"] else "⬜"
            lines.append(f"{mark} {t['title']} ({t['task_type']})")
        lines.append("")
    lines += [
        "---",
        "",
        "Legend: ✅ verified completed · 🟢 active · ⬜ not started",
    ]
    return "\n".join(lines)


def sync_and_commit(conn: sqlite3.Connection, repo_root: Path) -> dict:
    """Writes PROGRESS.md/COMPLETED.md if their content differs from what
    the database says right now, and commits only the files that changed.
    A no-op (no commit) when the docs already match -- this makes it safe
    to call after every single task completion."""
    if not git_service.is_repo(repo_root):
        return {"changed": False, "reason": "not a git repository"}

    progress_path = repo_root / "PROGRESS.md"
    completed_path = repo_root / "COMPLETED.md"
    new_progress = render_progress_md(conn)
    new_completed = render_completed_md(conn)

    changed_files: list[Path] = []
    if not progress_path.exists() or progress_path.read_text(encoding="utf-8") != new_progress:
        progress_path.write_text(new_progress, encoding="utf-8")
        changed_files.append(progress_path)
    if not completed_path.exists() or completed_path.read_text(encoding="utf-8") != new_completed:
        completed_path.write_text(new_completed, encoding="utf-8")
        changed_files.append(completed_path)

    if not changed_files:
        return {"changed": False}

    commit_result = git_service.safe_commit(
        repo_root, changed_files, "docs: sync PROGRESS.md/COMPLETED.md with real completion state"
    )
    return {"changed": True, "commit": commit_result.success, "commit_error": commit_result.error}


def check_docs_in_sync(conn: sqlite3.Connection, repo_root: Path) -> list[str]:
    """Read-only consistency check: returns a list of mismatch descriptions
    (empty if PROGRESS.md/COMPLETED.md on disk exactly match what the
    database says right now). Used by the regression suite so drift between
    the DB and these docs fails a normal test run instead of going unnoticed."""
    problems: list[str] = []
    progress_path = repo_root / "PROGRESS.md"
    completed_path = repo_root / "COMPLETED.md"

    if not progress_path.exists():
        problems.append("PROGRESS.md does not exist")
    elif progress_path.read_text(encoding="utf-8") != render_progress_md(conn):
        problems.append("PROGRESS.md content does not match current database state")

    if not completed_path.exists():
        problems.append("COMPLETED.md does not exist")
    elif completed_path.read_text(encoding="utf-8") != render_completed_md(conn):
        problems.append("COMPLETED.md content does not match current database state")

    return problems
