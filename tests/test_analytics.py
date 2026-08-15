from app.services import analytics_service, pipeline_service


SAMPLE = "class Solution { public int[] twoSum(int[] n, int t) { return new int[]{0,1}; } }"


def test_topic_readiness_zero_before_any_work(seeded_conn):
    scores = analytics_service.topic_readiness(seeded_conn)
    assert scores["arrays"] == 0.0


def test_topic_readiness_increases_after_independent_green_solve(seeded_conn, tmp_path):
    conn = seeded_conn
    pipeline_service.set_dsa135_repo(conn, tmp_path / "DSA-135")
    task = conn.execute(
        "SELECT t.* FROM tasks t JOIN problems p ON t.problem_id = p.id "
        "WHERE t.day_number = 8 AND p.leetcode_number = 1"
    ).fetchone()
    reflection = {
        "pattern": "Hashing", "time_complexity": "O(n)", "space_complexity": "O(n)",
        "explanation": "Used a hashmap for one-pass lookup.",
        "assistance_level": "independent", "confidence": "green",
    }
    pipeline_service.finalize_leetcode_task(conn, task["id"], SAMPLE, reflection)
    scores = analytics_service.topic_readiness(conn)
    assert scores["arrays"] > 0.0
