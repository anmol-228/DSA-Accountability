"""Regression coverage for docs_sync_service -- the mechanism that keeps
DSA-135's PROGRESS.md/COMPLETED.md permanently in sync with the real
database, and the consistency checker that proves it. Covers the exact
failure mode reported in production: GitHub docs showing stale completion
state (a specific exercise "not started") after the real app, DB, and git
history all agreed it was done.
"""
from __future__ import annotations

import datetime as dt

from app.services import curriculum_service, docs_sync_service, git_service, pipeline_service
from app.services import progression_service as prog, schedule_service


def _complete_all_required(conn, day_number):
    rows = conn.execute(
        "SELECT id FROM tasks WHERE day_number = ? AND required = 1", (day_number,)
    ).fetchall()
    for r in rows:
        prog.complete_task(conn, r["id"])


# --- pure rendering: reflects live DB state, no git involved -----------------

def test_fresh_install_progress_md_shows_day1_active_zero_done(seeded_conn):
    md = docs_sync_service.render_progress_md(seeded_conn)
    assert "Day 01 / 135 — active, 0 / 12 tasks so far." in md
    assert "| Active curriculum day | 1 / 135 |" in md
    assert "| Days fully complete | 0 / 135 |" in md


def test_mid_day_single_task_completion_reflected_exactly(seeded_conn):
    """Regression for the generic 'mid-day task' case: completing ONE of
    several required tasks must move the count without marking the day (or
    any exercise not yet done) complete."""
    task = seeded_conn.execute(
        "SELECT id, title FROM tasks WHERE day_number = 1 AND required = 1 LIMIT 1"
    ).fetchone()
    prog.complete_task(seeded_conn, task["id"])

    md = docs_sync_service.render_progress_md(seeded_conn)
    assert "Day 01 / 135 — active, 1 / 12 tasks so far." in md
    assert "| Days fully complete | 0 / 135 |" in md

    completed_md = docs_sync_service.render_completed_md(seeded_conn)
    assert f"✅ {task['title']}" in completed_md
    assert "Day 1 — Java Fundamentals I — ✅ COMPLETE" not in completed_md


def test_exact_leap_year_regression(seeded_conn):
    """The exact reported scenario: three of Day 1's four exercises plus all
    eight learn items complete, Leap Year still outstanding -- Day 1 must
    show as active/incomplete and Leap Year must show as not done."""
    rows = seeded_conn.execute(
        "SELECT id, title FROM tasks WHERE day_number = 1 AND required = 1"
    ).fetchall()
    leap_year = next(r for r in rows if r["title"] == "Leap Year")
    for r in rows:
        if r["id"] != leap_year["id"]:
            prog.complete_task(seeded_conn, r["id"])

    completed_md = docs_sync_service.render_completed_md(seeded_conn)
    assert "Day 1 — Java Fundamentals I — active, 11 / 12 tasks" in completed_md
    assert "⬜ Leap Year" in completed_md
    assert "✅ Leap Year" not in completed_md

    # Now finish it for real -- Day 1 must flip to complete and Day 2 activate,
    # in the SAME render call, with no stale leftover state from before.
    prog.complete_task(seeded_conn, leap_year["id"])
    completed_md = docs_sync_service.render_completed_md(seeded_conn)
    assert "Day 1 — Java Fundamentals I — ✅ COMPLETE" in completed_md
    assert "✅ Leap Year" in completed_md
    assert "Day 2" in completed_md  # newly active day now listed too


def test_generic_final_task_of_any_day_completes_that_day_only(seeded_conn):
    """Same invariant as the Leap Year case, generalized to an arbitrary
    day -- proves this isn't a hardcoded Day-1 special case."""
    _complete_all_required(seeded_conn, 1)
    rows = seeded_conn.execute(
        "SELECT id FROM tasks WHERE day_number = 2 AND required = 1"
    ).fetchall()
    for r in rows[:-1]:
        prog.complete_task(seeded_conn, r["id"])
    md = docs_sync_service.render_progress_md(seeded_conn)
    assert "| Days fully complete | 1 / 135 |" in md
    assert f"Day 02 / 135 — active, {len(rows) - 1} / {len(rows)} tasks so far." in md

    prog.complete_task(seeded_conn, rows[-1]["id"])
    md = docs_sync_service.render_progress_md(seeded_conn)
    assert "| Days fully complete | 2 / 135 |" in md
    assert "Day 03 / 135 — active, 0 /" in md


def test_date_anchor_cross_surface_regression(seeded_conn):
    """The exact reported Dec-27-vs-Dec-28 scenario: PROGRESS.md's target
    finish must come from the SAME schedule_service.target_end_date() the
    UI uses, so re-anchoring the schedule can never leave the doc and the
    UI disagreeing."""
    schedule_service.set_start_date(seeded_conn, dt.date(2026, 8, 16))
    curriculum_service.seed_curriculum(seeded_conn)
    md = docs_sync_service.render_progress_md(seeded_conn)
    assert "| Target finish (locked) | 2026-12-28 |" in md
    assert schedule_service.target_end_date(seeded_conn) == dt.date(2026, 12, 28)


# --- full pipeline: real git repo, real commit, real idempotency -------------

def test_finalize_exercise_task_syncs_and_commits_docs(seeded_conn, tmp_path):
    repo_root = tmp_path / "learner_repo"
    pipeline_service.set_dsa135_repo(seeded_conn, repo_root)
    task = seeded_conn.execute(
        "SELECT * FROM tasks WHERE day_number = 1 AND task_type = 'exercise' "
        "AND canonical_filename = 'LeapYear'"
    ).fetchone()
    from app.services import code_sync_service
    target = code_sync_service.exercise_file_path(repo_root, 1, "LeapYear")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("public class LeapYear {}\n", encoding="utf-8")

    result = pipeline_service.finalize_exercise_task(seeded_conn, task["id"], "learned the century rule")
    assert result["commit"] is True
    assert result["docs_sync"]["changed"] is True
    assert result["docs_sync"]["commit"] is True

    progress_path = repo_root / "PROGRESS.md"
    completed_path = repo_root / "COMPLETED.md"
    assert progress_path.exists()
    assert completed_path.exists()
    assert "✅ Leap Year" in completed_path.read_text(encoding="utf-8")

    # Docs must have landed in their OWN commit, not silently merged into the
    # exercise commit (which would make push/rollback semantics ambiguous).
    log = git_service._run(["log", "--format=%s"], cwd=repo_root)
    subjects = log.stdout.strip().splitlines()
    assert any("docs: sync PROGRESS.md/COMPLETED.md" in s for s in subjects)
    assert any("Leap Year" in s for s in subjects)


def test_docs_sync_is_idempotent_no_duplicate_commit_when_nothing_changed(seeded_conn, tmp_path):
    repo_root = tmp_path / "learner_repo"
    pipeline_service.set_dsa135_repo(seeded_conn, repo_root)
    git_service.ensure_repo(repo_root)

    first = docs_sync_service.sync_and_commit(seeded_conn, repo_root)
    assert first["changed"] is True
    assert first["commit"] is True

    second = docs_sync_service.sync_and_commit(seeded_conn, repo_root)
    assert second == {"changed": False}

    log = git_service._run(["log", "--format=%s"], cwd=repo_root)
    subjects = log.stdout.strip().splitlines()
    assert len(subjects) == 1  # no duplicate commit from the no-op retry


def test_check_docs_in_sync_passes_after_sync_and_fails_on_manual_drift(seeded_conn, tmp_path):
    """The consistency checker itself: clean after a real sync, and it must
    actually detect drift rather than trivially passing."""
    repo_root = tmp_path / "learner_repo"
    pipeline_service.set_dsa135_repo(seeded_conn, repo_root)
    git_service.ensure_repo(repo_root)

    docs_sync_service.sync_and_commit(seeded_conn, repo_root)
    assert docs_sync_service.check_docs_in_sync(seeded_conn, repo_root) == []

    # Simulate exactly what was observed in production: DB moves forward,
    # docs don't (hand-edited / never regenerated).
    _complete_all_required(seeded_conn, 1)
    problems = docs_sync_service.check_docs_in_sync(seeded_conn, repo_root)
    assert any("PROGRESS.md" in p for p in problems)
    assert any("COMPLETED.md" in p for p in problems)

    # And re-syncing must clear it back to a clean pass.
    docs_sync_service.sync_and_commit(seeded_conn, repo_root)
    assert docs_sync_service.check_docs_in_sync(seeded_conn, repo_root) == []
