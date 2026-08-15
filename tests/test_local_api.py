import json
import time
import urllib.error
import urllib.request

import pytest

from app import database
from app.services import curriculum_service, pairing_service


@pytest.fixture()
def api_server(tmp_path, monkeypatch):
    from app import config
    from app.services import pipeline_service
    db_path = tmp_path / "api_test.sqlite"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    database.run_migrations(db_path)
    conn = database.get_connection(db_path)
    curriculum_service.seed_curriculum(conn)
    token = pairing_service.get_or_create_token(conn)
    # Isolated repo path for every test in this file, up front -- a test
    # that POSTs a real Accepted payload with code (e.g.
    # test_session_start_then_accepted_via_real_http_is_fresh) would
    # otherwise have local_server.py resolve _get_dsa135_repo() with no
    # setting configured, which is now a hard ProductionDataAccessError
    # under pytest rather than a silent fallback (see runtime_env.py) --
    # this real incident wrote actual files/commits into the real
    # a real learner repo during development. Isolating it here
    # once means no individual test in this file has to remember to.
    pipeline_service.set_dsa135_repo(conn, tmp_path / "DSA-135-test")
    conn.close()

    from app.api.local_server import LocalAPIServer
    server = LocalAPIServer(host="127.0.0.1")
    server.start()
    time.sleep(0.2)
    yield server, token
    server.stop()


def _get(server, path, token=None):
    req = urllib.request.Request(f"http://{server.host}:{server.port}{path}")
    if token:
        req.add_header("X-DSA-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _post(server, path, body, token=None):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(f"http://{server.host}:{server.port}{path}", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-DSA-Token", token)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_health_no_token_required(api_server):
    server, _token = api_server
    status, body = _get(server, "/api/health")
    assert status == 200
    assert body["status"] == "ok"


def test_status_requires_token(api_server):
    server, _token = api_server
    status, body = _get(server, "/api/status")
    assert status == 401


def test_status_with_valid_token(api_server):
    server, token = api_server
    status, body = _get(server, "/api/status", token=token)
    assert status == 200
    assert body["active_day"] == 1


def test_invalid_token_rejected(api_server):
    server, _token = api_server
    status, body = _get(server, "/api/status", token="wrong-token")
    assert status == 401


def test_current_curriculum_endpoint(api_server):
    server, token = api_server
    status, body = _get(server, "/api/curriculum/current", token=token)
    assert status == 200
    assert body["day"] == 1
    # Day 1 is java_foundation with exercises only, no leetcode tasks
    assert body["pending_leetcode_tasks"] == []


def test_current_curriculum_day3_has_leetcode_tasks(api_server, tmp_path):
    from app import config
    server, token = api_server
    conn = database.get_connection(config.DB_PATH)
    from app.services import progression_service as prog
    for day in (1, 2):
        rows = conn.execute("SELECT id FROM tasks WHERE day_number = ? AND required = 1", (day,)).fetchall()
        for r in rows:
            prog.complete_task(conn, r["id"])
    conn.close()
    status, body = _get(server, "/api/curriculum/current", token=token)
    assert body["day"] == 3
    assert len(body["pending_leetcode_tasks"]) == 2
    assert {t["leetcode_number"] for t in body["pending_leetcode_tasks"]} == {1480, 1672}


# --- /api/session/start real HTTP contract -----------------------------------
# These exercise the ACTUAL request the real Chrome extension sends (see
# chrome-extension/content-script.js::notifyPageOpened and
# service-worker.js::forwardSessionStart: POST {"slug": "..."}), through the
# real HTTP layer -- not leetcode_service.start_session() called directly.
# This is exactly the layer the pre-existing test_leetcode_service.py tests
# bypassed, which is how the real slug/leetcode_number body-key mismatch went
# undetected. Day 3 is used because Day 1/2 have no leetcode tasks.

def _advance_to_day3(server):
    from app import config
    conn = database.get_connection(config.DB_PATH)
    from app.services import progression_service as prog
    for day in (1, 2):
        rows = conn.execute("SELECT id FROM tasks WHERE day_number = ? AND required = 1", (day,)).fetchall()
        for r in rows:
            prog.complete_task(conn, r["id"])
    conn.close()


def test_session_start_requires_token(api_server):
    server, _token = api_server
    status, body = _post(server, "/api/session/start", {"slug": "running-sum-of-1d-array"})
    assert status == 401


def test_session_start_real_extension_payload_matches_scheduled_task(api_server):
    """The exact real payload shape the extension sends -- only `slug`,
    never `leetcode_number` -- must match today's scheduled task and
    create a real problem_sessions row."""
    server, token = api_server
    _advance_to_day3(server)

    status, body = _post(server, "/api/session/start", {"slug": "running-sum-of-1d-array"}, token=token)
    assert status == 200
    assert body["matched"] is True
    assert body["session_id"] is not None

    from app import config
    conn = database.get_connection(config.DB_PATH)
    row = conn.execute(
        "SELECT * FROM problem_sessions WHERE id = ?", (body["session_id"],)
    ).fetchone()
    conn.close()
    assert row is not None
    assert row["ended_at"] is None


def test_session_start_unrelated_slug_not_matched(api_server):
    server, token = api_server
    _advance_to_day3(server)
    status, body = _post(server, "/api/session/start", {"slug": "median-of-two-sorted-arrays"}, token=token)
    assert status == 200
    assert body["matched"] is False


def test_session_start_future_day_slug_not_matched(api_server):
    """A problem scheduled for a later, still-locked day must not be
    matchable just because its slug is known to the curriculum."""
    server, token = api_server
    # Still on day 1 -- day 3's problems are not yet the active day's tasks.
    status, body = _post(server, "/api/session/start", {"slug": "running-sum-of-1d-array"}, token=token)
    assert status == 200
    assert body["matched"] is False


def test_session_start_duplicate_page_open_reuses_session(api_server):
    """Repeated PROBLEM_PAGE_OPENED notifications (SPA re-render, refocus)
    must not spawn a new problem_sessions row each time."""
    server, token = api_server
    _advance_to_day3(server)

    _, first = _post(server, "/api/session/start", {"slug": "running-sum-of-1d-array"}, token=token)
    _, second = _post(server, "/api/session/start", {"slug": "running-sum-of-1d-array"}, token=token)
    assert first["session_id"] == second["session_id"]

    from app import config
    conn = database.get_connection(config.DB_PATH)
    count = conn.execute(
        "SELECT COUNT(*) c FROM problem_sessions WHERE id = ?", (first["session_id"],)
    ).fetchone()["c"]
    conn.close()
    assert count == 1


def test_session_start_then_accepted_via_real_http_is_fresh(api_server):
    """The full real round trip through the actual HTTP routes (not
    leetcode_service called directly): session-start creates a session,
    then a same-slug Java Accepted event with a later timestamp must be
    verified fresh -- this is the exact path that was broken in
    production (see docs/PRODUCTION_STABILIZATION_2026-08-12.md)."""
    server, token = api_server
    _advance_to_day3(server)

    status, start_body = _post(server, "/api/session/start", {"slug": "running-sum-of-1d-array"}, token=token)
    assert start_body["matched"] is True

    import datetime as dt
    accepted_payload = {
        "slug": "running-sum-of-1d-array",
        "language": "java",
        "code": "class Solution { public int[] runningSum(int[] nums) { return nums; } }",
        "code_capture_method": "monaco_global",
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": "fresh_submission",
    }
    status, accepted_body = _post(server, "/api/leetcode/accepted", accepted_payload, token=token)
    assert status == 200
    assert accepted_body["status"] == "ok"
    assert accepted_body["code_captured"] is True
