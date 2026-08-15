"""Fresh-Accepted verification, Java-only enforcement, and Premium fallback.

Historical Accepted status is never enough (spec section 29): a submission
only counts toward completing today's task if it happened during an open
problem_session that was started for that task/problem.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import sqlite3
from dataclasses import dataclass

from app import config
from app.services import curriculum_service, integration_test_service, progression_service

MAX_SESSION_AGE = _dt.timedelta(hours=6)
MAX_FUTURE_CLOCK_SKEW = _dt.timedelta(minutes=5)


def compute_event_hash(slug: str, timestamp: str, source: str) -> str:
    raw = f"{slug}|{timestamp}|{source}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def start_session(conn: sqlite3.Connection, problem_id: int, task_id: int | None,
                   day_number: int | None, session_type: str = "solve") -> int:
    now = config.now_local().isoformat()
    cur = conn.execute(
        "INSERT INTO problem_sessions (problem_id, task_id, day_number, session_type, started_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (problem_id, task_id, day_number, session_type, now),
    )
    conn.commit()
    assert cur.lastrowid is not None
    return cur.lastrowid


def end_session(conn: sqlite3.Connection, session_id: int) -> None:
    now = config.now_local().isoformat()
    conn.execute("UPDATE problem_sessions SET ended_at = ? WHERE id = ?", (now, session_id))
    conn.commit()


def start_or_reuse_session(conn: sqlite3.Connection, problem_id: int, task_id: int | None,
                            day_number: int | None, session_type: str = "solve") -> int:
    """Idempotent session start for the real HTTP session-start contract.

    A single problem page view can trigger PROBLEM_PAGE_OPENED more than
    once (SPA re-render, refocus, duplicate content-script injection) --
    each call must not spawn a brand-new problem_sessions row, or a
    genuinely fresh Accepted event's freshness check would still pass
    (any open session before it counts), but the DB would accumulate
    session spam. Reuses the most recent still-open session for this
    problem if one exists; only creates a new row otherwise.
    """
    existing = conn.execute(
        "SELECT id FROM problem_sessions WHERE problem_id = ? AND task_id IS ? "
        "AND day_number IS ? AND session_type = ? AND ended_at IS NULL "
        "ORDER BY started_at DESC LIMIT 1",
        (problem_id, task_id, day_number, session_type),
    ).fetchone()
    if existing is not None:
        return existing["id"]
    return start_session(conn, problem_id, task_id, day_number, session_type)


def _open_session_for_problem(conn: sqlite3.Connection, problem_id: int, before_ts: str) -> sqlite3.Row | None:
    """Most recent still-open session for this problem that started at or
    before `before_ts`.

    Deliberately compares parsed, timezone-aware datetimes rather than raw
    ISO strings. Session.started_at is written with config.now_local()
    (the user's local timezone), while a real browser Accepted/session-start
    timestamp is JS `Date.toISOString()` (UTC, "Z"/"+00:00") -- lexicographic
    string comparison across two different UTC offsets is unsound (e.g.
    "16:30:00+05:30" sorts as GREATER than "11:05:00+00:00" even though the
    former is the earlier instant, 11:00 UTC), which could wrongly reject a
    genuinely fresh session as stale depending on time of day. Confirmed by
    a real HTTP round-trip test using an actual UTC timestamp.
    """
    before_dt = _dt.datetime.fromisoformat(before_ts)
    if before_dt.tzinfo is None:
        before_dt = before_dt.replace(tzinfo=config.local_timezone())

    candidates = conn.execute(
        "SELECT * FROM problem_sessions WHERE problem_id = ? AND ended_at IS NULL "
        "ORDER BY started_at DESC",
        (problem_id,),
    ).fetchall()
    for row in candidates:
        started_dt = _dt.datetime.fromisoformat(row["started_at"])
        if started_dt.tzinfo is None:
            started_dt = started_dt.replace(tzinfo=config.local_timezone())
        age = before_dt - started_dt
        if _dt.timedelta(0) <= age <= MAX_SESSION_AGE:
            return row
    return None


@dataclass
class AcceptedResult:
    status: str  # 'ok' | 'duplicate' | 'stale' | 'wrong_language' | 'unknown_problem'
    event_id: int | None = None
    session_id: int | None = None
    problem_id: int | None = None
    task_id: int | None = None
    day_number: int | None = None
    message: str = ""


def handle_accepted_event(conn: sqlite3.Connection, payload: dict) -> AcceptedResult:
    slug = payload["slug"]
    problem_number = payload.get("problem_number")
    language = (payload.get("language") or "").lower()
    timestamp = payload.get("timestamp") or config.now_local().isoformat()
    source = payload.get("source", "fresh_submission")

    event_hash = compute_event_hash(slug, timestamp, source)
    existing = conn.execute(
        "SELECT id FROM leetcode_events WHERE event_hash = ?", (event_hash,)
    ).fetchone()
    if existing:
        return AcceptedResult(status="duplicate", event_id=existing["id"],
                               message="Duplicate Accepted event ignored.")

    problem_row = None
    if problem_number is not None:
        problem_row = conn.execute(
            "SELECT * FROM problems WHERE leetcode_number = ?", (problem_number,)
        ).fetchone()
    if problem_row is None:
        problem_row = conn.execute("SELECT * FROM problems WHERE slug = ?", (slug,)).fetchone()

    now = config.now_local().isoformat()
    if problem_row is None:
        cur = conn.execute(
            "INSERT INTO leetcode_events (slug, problem_number, language, event_type, event_ts, "
            "source, event_hash, raw_payload, is_fresh, created_at) "
            "VALUES (?, ?, ?, 'accepted', ?, ?, ?, ?, 0, ?)",
            (slug, problem_number, language, timestamp, source, event_hash, json.dumps(payload), now),
        )
        conn.commit()
        return AcceptedResult(status="unknown_problem", event_id=cur.lastrowid,
                               message=f"No curriculum problem matches slug '{slug}'.")

    session = _open_session_for_problem(conn, problem_row["id"], timestamp)
    event_dt = _dt.datetime.fromisoformat(timestamp)
    if event_dt.tzinfo is None:
        event_dt = event_dt.replace(tzinfo=config.local_timezone())
    now_dt = config.now_local()
    source_is_fresh = source == "fresh_submission"
    clock_is_sane = event_dt <= now_dt + MAX_FUTURE_CLOCK_SKEW
    session_is_authorized = False
    if session is not None:
        if integration_test_service.is_active_session(conn, session["id"]):
            session_is_authorized = True
        elif session["task_id"] is not None and session["day_number"] is not None:
            active_day = progression_service.get_active_day(conn)
            task = conn.execute(
                "SELECT required, completed, day_number, problem_id FROM tasks WHERE id = ?",
                (session["task_id"],),
            ).fetchone()
            session_is_authorized = bool(
                task and task["required"] and not task["completed"]
                and task["day_number"] == active_day == session["day_number"]
                and task["problem_id"] == problem_row["id"]
            )
    is_fresh = bool(session and source_is_fresh and clock_is_sane and session_is_authorized)

    cur = conn.execute(
        "INSERT INTO leetcode_events (slug, problem_number, language, event_type, event_ts, "
        "source, session_id, event_hash, raw_payload, is_fresh, created_at) "
        "VALUES (?, ?, ?, 'accepted', ?, ?, ?, ?, ?, ?, ?)",
        (slug, problem_row["leetcode_number"], language, timestamp, source,
         session["id"] if session else None, event_hash, json.dumps(payload), int(is_fresh), now),
    )
    conn.commit()
    event_id = cur.lastrowid

    if not is_fresh:
        return AcceptedResult(status="stale", event_id=event_id, problem_id=problem_row["id"],
                               message="Accepted found, but no active session was started for this "
                                       "problem today — historical Accepted does not count.")

    if language != "java":
        return AcceptedResult(status="wrong_language", event_id=event_id, session_id=session["id"],
                               problem_id=problem_row["id"],
                               message=f"Accepted, but this curriculum requires Java (submitted: {language or 'unknown'}).")

    end_session(conn, session["id"])
    return AcceptedResult(status="ok", event_id=event_id, session_id=session["id"],
                           problem_id=problem_row["id"], task_id=session["task_id"],
                           day_number=session["day_number"], message="Fresh Java Accepted verified.")


# --- Premium fallback ---------------------------------------------------------

def load_fallback_catalog() -> dict:
    return json.loads(config.FALLBACK_PROBLEMS_JSON.read_text(encoding="utf-8"))


def apply_premium_fallback(conn: sqlite3.Connection, task_id: int, topic: str) -> dict | None:
    """Replaces a task's problem with a free same-topic replacement. Never
    penalizes the user; always audit-logged (spec section 33)."""
    catalog = load_fallback_catalog()
    candidates = catalog.get(topic, [])
    task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if task is None:
        return None

    used_numbers = {
        r["leetcode_number"] for r in conn.execute(
            "SELECT p.leetcode_number FROM tasks t JOIN problems p ON t.problem_id = p.id "
            "WHERE t.day_number = ?", (task["day_number"],)
        ).fetchall()
    }
    replacement = next((c for c in candidates if c["leetcode_number"] not in used_numbers), None)
    if replacement is None:
        return None

    new_problem_id = curriculum_service._get_or_create_problem(
        conn, replacement["leetcode_number"], replacement["title"]
    )
    now = config.now_local().isoformat()
    # Task title is display text derived from the problem at seed time
    # (curriculum_service._insert_task_for_item uses the same "LC N - Title"
    # format) — it must be updated here too, or the UI would keep showing
    # the original (now premium-blocked) problem's name forever even
    # though problem_id already points at the free replacement.
    new_title = f"LC {replacement['leetcode_number']} - {replacement['title']}"
    conn.execute(
        "UPDATE tasks SET original_problem_id = COALESCE(original_problem_id, problem_id), "
        "problem_id = ?, title = ?, premium_blocked_note = ? WHERE id = ?",
        (new_problem_id, new_title, f"Original problem became Premium-only; replaced {now}.", task_id),
    )
    conn.execute(
        "INSERT INTO audit_log (ts, actor, action, details) VALUES (?, 'system', 'premium_fallback', ?)",
        (now, json.dumps({"task_id": task_id, "replacement": replacement})),
    )
    conn.commit()
    return replacement
