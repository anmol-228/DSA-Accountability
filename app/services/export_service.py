"""Progress export to JSON / CSV / Markdown (spec section 54)."""
from __future__ import annotations

import csv
import io
import json
import sqlite3
from pathlib import Path

from app.services import progression_service as prog, streak_service


def _collect(conn: sqlite3.Connection) -> dict:
    status = prog.get_status(conn)
    days = [dict(r) for r in conn.execute("SELECT * FROM curriculum_days ORDER BY day_number")]
    problems_solved = [dict(r) for r in conn.execute(
        "SELECT DISTINCT p.leetcode_number, p.title, p.topic FROM leetcode_events e "
        "JOIN problems p ON p.leetcode_number = e.problem_number "
        "WHERE e.is_fresh = 1 AND e.language = 'java'"
    )]
    reflections = [dict(r) for r in conn.execute("SELECT * FROM reflections ORDER BY created_at")]
    commits = [dict(r) for r in conn.execute("SELECT * FROM git_commits ORDER BY created_at")]
    return {
        "active_day": status.active_day,
        "post_plan_mode": status.post_plan_mode,
        "completed_days": status.completed_days,
        "schedule_delay_days": status.schedule_delay_days,
        "original_target_end": status.original_target_end.isoformat(),
        "projected_finish": status.projected_finish.isoformat(),
        "activity_streak": streak_service.current_activity_streak(conn),
        "best_activity_streak": streak_service.best_activity_streak(conn),
        "on_schedule_streak": streak_service.on_schedule_streak(conn),
        "curriculum_days": days,
        "unique_problems_solved": problems_solved,
        "reflections": reflections,
        "git_commits": commits,
    }


def export_json(conn: sqlite3.Connection, out_path: Path) -> Path:
    data = _collect(conn)
    out_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return out_path


def export_csv(conn: sqlite3.Connection, out_path: Path) -> Path:
    data = _collect(conn)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["day_number", "title", "topic", "original_due_date", "completed", "completed_at"])
    for d in data["curriculum_days"]:
        writer.writerow([d["day_number"], d["title"], d["topic"], d["original_due_date"],
                          d["completed"], d["completed_at"]])
    out_path.write_text(buf.getvalue(), encoding="utf-8")
    return out_path


def export_markdown(conn: sqlite3.Connection, out_path: Path) -> Path:
    data = _collect(conn)
    lines = [
        "# DSA Accountability Progress Export",
        "",
        f"- Active day: {data['active_day']} / 135" if not data["post_plan_mode"] else "- POST-PLAN MODE (135/135 complete)",
        f"- Completed days: {data['completed_days']} / 135",
        f"- Schedule delay: {data['schedule_delay_days']} day(s)",
        f"- Original target end: {data['original_target_end']}",
        f"- Projected finish: {data['projected_finish']}",
        f"- Activity streak: {data['activity_streak']} (best {data['best_activity_streak']})",
        f"- On-schedule streak: {data['on_schedule_streak']}",
        "",
        "## Unique Problems Solved (Java, fresh Accepted)",
        "",
    ]
    for p in data["unique_problems_solved"]:
        lines.append(f"- LC {p['leetcode_number']} — {p['title']} ({p.get('topic') or 'n/a'})")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
