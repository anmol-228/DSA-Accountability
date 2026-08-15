"""Loads curriculum/schedule.json and seeds it into the database (idempotent)."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from app import config
from app.services import runtime_env, schedule_service


def load_schedule() -> dict:
    return json.loads(config.SCHEDULE_JSON.read_text(encoding="utf-8"))


def _get_or_create_problem(conn: sqlite3.Connection, leetcode_number: int, title: str) -> int:
    row = conn.execute(
        "SELECT id FROM problems WHERE leetcode_number = ?", (leetcode_number,)
    ).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO problems (leetcode_number, title, slug, url) VALUES (?, ?, ?, ?)",
        (leetcode_number, title, _slugify(title), f"https://leetcode.com/problems/{_slugify(title)}/"),
    )
    assert cur.lastrowid is not None
    return cur.lastrowid


def _slugify(title: str) -> str:
    out = []
    for ch in title.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in " -_":
            out.append("-")
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def is_seeded(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT COUNT(*) AS c FROM curriculum_days").fetchone()
    return row["c"] >= config.TOTAL_CURRICULUM_DAYS


def seed_curriculum(conn: sqlite3.Connection, force: bool = False) -> None:
    """Idempotent: seeds all 135 curriculum days + tasks + problems if not already present."""
    runtime_env.assert_connection_access_allowed(conn, config.PRODUCTION_DB_PATH, "seed curriculum")
    if is_seeded(conn) and not force:
        return

    schedule = load_schedule()
    now = config.now_local().isoformat()

    for day_data in schedule["days"]:
        day_no = day_data["day"]
        due = schedule_service.due_date(conn, day_no).isoformat()
        conn.execute(
            """INSERT INTO curriculum_days (day_number, title, topic, original_due_date, is_oa_day, is_mock_day, unlocked_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(day_number) DO UPDATE SET
                 title=excluded.title, topic=excluded.topic, original_due_date=excluded.original_due_date,
                 is_oa_day=excluded.is_oa_day, is_mock_day=excluded.is_mock_day""",
            (day_no, day_data["title"], day_data["topic"], due,
             int(day_data.get("is_oa", False)), int(day_data.get("is_mock", False)),
             now if day_no == 1 else None),
        )

        # clear existing generated=0 (curriculum-defined) tasks for this day before re-inserting,
        # so re-running the seeder (force=True) doesn't duplicate rows.
        conn.execute("DELETE FROM tasks WHERE day_number = ? AND generated = 0", (day_no,))

        for item in day_data["items"]:
            _insert_task_for_item(conn, day_no, item)

    conn.commit()


def _insert_task_for_item(conn: sqlite3.Connection, day_no: int, item: dict[str, Any]) -> None:
    kind = item["kind"]

    if kind == "learn_group":
        for bullet in item["bullets"]:
            conn.execute(
                "INSERT INTO tasks (day_number, task_type, title, required) VALUES (?, 'learn', ?, 1)",
                (day_no, bullet),
            )
    elif kind == "exercise":
        conn.execute(
            "INSERT INTO tasks (day_number, task_type, title, required, canonical_filename) "
            "VALUES (?, 'exercise', ?, 1, ?)",
            (day_no, item["title"], item.get("filename")),
        )
    elif kind == "leetcode":
        pid = _get_or_create_problem(conn, item["leetcode_number"], item["title"])
        desc = item.get("note")
        conn.execute(
            "INSERT INTO tasks (day_number, task_type, title, description, problem_id, required) "
            "VALUES (?, 'leetcode', ?, ?, ?, 1)",
            (day_no, f"LC {item['leetcode_number']} - {item['title']}", desc, pid),
        )
    elif kind == "revision":
        pid = _get_or_create_problem(conn, item["leetcode_number"], item["title"])
        conn.execute(
            "INSERT INTO tasks (day_number, task_type, title, problem_id, required) "
            "VALUES (?, 'revision', ?, ?, 1)",
            (day_no, f"Revision - LC {item['leetcode_number']} {item['title']}", pid),
        )
    elif kind == "concept":
        bullets = "; ".join(item.get("bullets", []))
        conn.execute(
            "INSERT INTO tasks (day_number, task_type, title, description, required) "
            "VALUES (?, 'concept', ?, ?, 1)",
            (day_no, item["title"], bullets),
        )
    elif kind == "repair":
        conn.execute(
            "INSERT INTO tasks (day_number, task_type, title, description, required) "
            "VALUES (?, 'repair', ?, ?, 1)",
            (day_no, item["title"], item.get("note", "")),
        )
    elif kind == "oa":
        desc = json.dumps({"minutes": item["minutes"], "note": item.get("note")})
        task_id = conn.execute(
            "INSERT INTO tasks (day_number, task_type, title, description, required) "
            "VALUES (?, 'oa', ?, ?, 1)",
            (day_no, item["title"], desc),
        ).lastrowid
        for p in item["problems"]:
            pid = _get_or_create_problem(conn, p["leetcode_number"], p["title"])
            conn.execute(
                "INSERT OR IGNORE INTO task_problem_links (task_id, problem_id) VALUES (?, ?)",
                (task_id, pid),
            )
    elif kind == "mock":
        desc = json.dumps({"note": item.get("note")})
        task_id = conn.execute(
            "INSERT INTO tasks (day_number, task_type, title, description, required) "
            "VALUES (?, 'mock', ?, ?, 1)",
            (day_no, item["title"], desc),
        ).lastrowid
        for entry in item["items"]:
            p = entry.get("problem")
            if p:
                pid = _get_or_create_problem(conn, p["leetcode_number"], p["title"])
                conn.execute(
                    "INSERT OR IGNORE INTO task_problem_links (task_id, problem_id) VALUES (?, ?)",
                    (task_id, pid),
                )
    else:
        raise ValueError(f"Unknown curriculum item kind: {kind}")


def backfill_canonical_filenames(conn: sqlite3.Connection) -> int:
    """Fills in tasks.canonical_filename for exercise tasks that predate the
    column (e.g. an already-seeded install from before this feature). Only
    ever touches rows where the value is currently NULL — never overwrites
    real data or completion state. Safe to call on every startup; a no-op
    once every row has a value. Returns the number of rows updated."""
    runtime_env.assert_connection_access_allowed(conn, config.PRODUCTION_DB_PATH, "backfill curriculum filenames")
    schedule = load_schedule()
    updated = 0
    for day_data in schedule["days"]:
        for item in day_data["items"]:
            if item.get("kind") != "exercise":
                continue
            cur = conn.execute(
                "UPDATE tasks SET canonical_filename = ? "
                "WHERE day_number = ? AND task_type = 'exercise' AND title = ? "
                "AND canonical_filename IS NULL",
                (item["filename"], day_data["day"], item["title"]),
            )
            updated += cur.rowcount
    if updated:
        conn.commit()
    return updated


def get_day(conn: sqlite3.Connection, day_number: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM curriculum_days WHERE day_number = ?", (day_number,)
    ).fetchone()


def get_tasks_for_day(conn: sqlite3.Connection, day_number: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM tasks WHERE day_number = ? ORDER BY id", (day_number,)
    ).fetchall()
