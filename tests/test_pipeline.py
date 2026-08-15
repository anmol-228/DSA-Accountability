from pathlib import Path

from app.services import pipeline_service, progression_service as prog


SAMPLE_JAVA = """class Solution {
    public int[] twoSum(int[] nums, int target) {
        return new int[]{0, 1};
    }
}
"""


def test_finalize_leetcode_task_writes_file_commits_and_completes_task(seeded_conn, tmp_path):
    conn = seeded_conn
    repo_root = tmp_path / "DSA-135"
    pipeline_service.set_dsa135_repo(conn, repo_root)

    task = conn.execute(
        "SELECT t.* FROM tasks t JOIN problems p ON t.problem_id = p.id "
        "WHERE t.day_number = 8 AND p.leetcode_number = 1"
    ).fetchone()
    assert task is not None

    reflection = {
        "pattern": "Hashing",
        "time_complexity": "O(n)",
        "space_complexity": "O(n)",
        "explanation": "I used a hashmap to store seen values and their indices.",
        "assistance_level": "independent",
        "confidence": "green",
    }

    result = pipeline_service.finalize_leetcode_task(conn, task["id"], SAMPLE_JAVA, reflection, repo_root)

    assert result["commit"] is True
    # GitHub is optional: without a remote the successful local commit remains
    # valid and no permanently failing queue item is created.
    assert result["push"] == "local_only"

    written = repo_root / "Week-02" / "Day-008" / "leetcode" / "LC0001_TwoSum.java"
    assert written.exists()
    assert written.read_text(encoding="utf-8") == SAMPLE_JAVA

    notes = repo_root / "Week-02" / "Day-008" / "notes.md"
    assert notes.exists()
    assert "Two Sum" in notes.read_text(encoding="utf-8")

    updated_task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task["id"],)).fetchone()
    assert updated_task["completed"] == 1

    # A local commit row exists; no push queue row is created without a remote.
    commit_row = conn.execute("SELECT * FROM git_commits WHERE task_id = ?", (task["id"],)).fetchone()
    assert commit_row is not None
    assert commit_row["commit_hash"] is not None

    queue_row = conn.execute(
        "SELECT * FROM github_push_queue WHERE commit_id = ?", (commit_row["id"],)
    ).fetchone()
    assert queue_row is None

    # revision schedule should have been created for future spaced review
    rev = conn.execute("SELECT * FROM revision_schedule WHERE problem_id = ?", (task["problem_id"],)).fetchall()
    assert len(rev) == 4  # D+2, D+7, D+21, D+45


def test_finalize_leetcode_task_never_uses_add_dot(seeded_conn, tmp_path, monkeypatch):
    """Regression guard: safe_commit must never stage unrelated files. We
    drop an unrelated dirty file in the repo and confirm it's NOT staged."""
    conn = seeded_conn
    repo_root = tmp_path / "DSA-135"
    pipeline_service.set_dsa135_repo(conn, repo_root)
    repo_root.mkdir(parents=True)

    from app.services import git_service
    git_service.ensure_repo(repo_root)
    unrelated = repo_root / "unrelated_scratch.txt"
    unrelated.write_text("do not commit me", encoding="utf-8")

    task = conn.execute(
        "SELECT t.* FROM tasks t JOIN problems p ON t.problem_id = p.id "
        "WHERE t.day_number = 8 AND p.leetcode_number = 121"
    ).fetchone()
    reflection = {
        "pattern": "One pass", "time_complexity": "O(n)", "space_complexity": "O(1)",
        "explanation": "Track min price seen so far.", "assistance_level": "independent",
        "confidence": "yellow",
    }
    pipeline_service.finalize_leetcode_task(conn, task["id"], SAMPLE_JAVA, reflection, repo_root)

    status_result = git_service._run(["status", "--porcelain"], cwd=repo_root)
    # unrelated_scratch.txt must still show as untracked ('??'), never staged/committed
    assert "?? unrelated_scratch.txt" in status_result.stdout


def test_finalize_simple_task_exercise(seeded_conn, tmp_path):
    conn = seeded_conn
    repo_root = tmp_path / "DSA-135"
    pipeline_service.set_dsa135_repo(conn, repo_root)

    task = conn.execute(
        "SELECT * FROM tasks WHERE day_number = 1 AND task_type = 'exercise' AND title = 'Even/Odd'"
    ).fetchone()
    assert task is not None

    code = "public class EvenOdd { public static void main(String[] a) { } }"
    result = pipeline_service.finalize_simple_task(conn, task["id"], note="Learned if/else parity check.", code=code)
    assert result["commit"] is True

    written = repo_root / "Week-01" / "Day-001" / "exercises" / "EvenOdd.java"
    assert written.exists()

    updated = conn.execute("SELECT * FROM tasks WHERE id = ?", (task["id"],)).fetchone()
    assert updated["completed"] == 1
