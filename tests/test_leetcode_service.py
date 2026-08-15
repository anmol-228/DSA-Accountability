import datetime as dt

from app import config
from app.services import integration_test_service, leetcode_service


def _problem_id(conn, leetcode_number):
    return conn.execute(
        "SELECT id FROM problems WHERE leetcode_number = ?", (leetcode_number,)
    ).fetchone()["id"]


def _start_authorized_integration_session(conn, leetcode_number=1, slug="two-sum", title="Two Sum"):
    pid = _problem_id(conn, leetcode_number)
    integration_test_service.start(conn, slug, leetcode_number, title)
    session_id = leetcode_service.start_session(conn, pid, None, None)
    integration_test_service.record_session(conn, session_id)
    return session_id


def test_stale_accepted_without_open_session_does_not_count(seeded_conn):
    conn = seeded_conn
    payload = {
        "slug": "two-sum", "problem_number": 1, "language": "java",
        "timestamp": config.now_local().isoformat(), "source": "fresh_submission",
    }
    result = leetcode_service.handle_accepted_event(conn, payload)
    assert result.status == "stale"


def test_fresh_accepted_with_open_session_counts(seeded_conn):
    conn = seeded_conn
    session_id = _start_authorized_integration_session(conn)
    payload = {
        "slug": "two-sum", "problem_number": 1, "language": "java",
        "timestamp": config.now_local().isoformat(), "source": "fresh_submission",
    }
    result = leetcode_service.handle_accepted_event(conn, payload)
    assert result.status == "ok"
    ended = conn.execute("SELECT ended_at FROM problem_sessions WHERE id=?", (session_id,)).fetchone()
    assert ended["ended_at"] is not None


def test_session_started_after_accepted_event_does_not_count(seeded_conn):
    """A session must be started BEFORE the accepted timestamp to count as
    fresh — an old/historical Accepted must not be retroactively validated
    by starting a session afterward."""
    conn = seeded_conn
    old_ts = (config.now_local() - dt.timedelta(hours=2)).isoformat()
    payload = {
        "slug": "two-sum", "problem_number": 1, "language": "java",
        "timestamp": old_ts, "source": "fresh_submission",
    }
    # session starts now (after the old accepted timestamp)
    _start_authorized_integration_session(conn)
    result = leetcode_service.handle_accepted_event(conn, payload)
    assert result.status == "stale"


def test_wrong_language_flagged_even_when_fresh(seeded_conn):
    conn = seeded_conn
    _start_authorized_integration_session(conn)
    payload = {
        "slug": "two-sum", "problem_number": 1, "language": "python3",
        "timestamp": config.now_local().isoformat(), "source": "fresh_submission",
    }
    result = leetcode_service.handle_accepted_event(conn, payload)
    assert result.status == "wrong_language"


def test_duplicate_event_ignored(seeded_conn):
    conn = seeded_conn
    _start_authorized_integration_session(conn)
    ts = config.now_local().isoformat()
    payload = {
        "slug": "two-sum", "problem_number": 1, "language": "java",
        "timestamp": ts, "source": "fresh_submission",
    }
    first = leetcode_service.handle_accepted_event(conn, payload)
    second = leetcode_service.handle_accepted_event(conn, payload)
    assert first.status == "ok"
    assert second.status == "duplicate"
    assert second.event_id == first.event_id


def test_unknown_problem_slug(seeded_conn):
    conn = seeded_conn
    payload = {
        "slug": "some-problem-not-in-curriculum", "problem_number": 999999,
        "language": "java", "timestamp": config.now_local().isoformat(), "source": "fresh_submission",
    }
    result = leetcode_service.handle_accepted_event(conn, payload)
    assert result.status == "unknown_problem"


def test_session_end_stops_it_counting_as_open(seeded_conn):
    conn = seeded_conn
    session_id = _start_authorized_integration_session(conn)
    leetcode_service.end_session(conn, session_id)
    payload = {
        "slug": "two-sum", "problem_number": 1, "language": "java",
        "timestamp": config.now_local().isoformat(), "source": "fresh_submission",
    }
    result = leetcode_service.handle_accepted_event(conn, payload)
    assert result.status == "stale"


def test_session_older_than_six_hours_is_stale(seeded_conn):
    conn = seeded_conn
    session_id = _start_authorized_integration_session(conn)
    conn.execute(
        "UPDATE problem_sessions SET started_at=? WHERE id=?",
        ((config.now_local() - dt.timedelta(hours=7)).isoformat(), session_id),
    )
    conn.commit()
    payload = {
        "slug": "two-sum", "problem_number": 1, "language": "java",
        "timestamp": config.now_local().isoformat(), "source": "fresh_submission",
    }
    assert leetcode_service.handle_accepted_event(conn, payload).status == "stale"


def test_non_fresh_source_cannot_count_even_with_open_session(seeded_conn):
    conn = seeded_conn
    _start_authorized_integration_session(conn)
    payload = {
        "slug": "two-sum", "problem_number": 1, "language": "java",
        "timestamp": config.now_local().isoformat(), "source": "historical_status",
    }
    assert leetcode_service.handle_accepted_event(conn, payload).status == "stale"


def test_future_timestamp_outside_clock_skew_cannot_count(seeded_conn):
    conn = seeded_conn
    _start_authorized_integration_session(conn)
    payload = {
        "slug": "two-sum", "problem_number": 1, "language": "java",
        "timestamp": (config.now_local() + dt.timedelta(minutes=6)).isoformat(),
        "source": "fresh_submission",
    }
    assert leetcode_service.handle_accepted_event(conn, payload).status == "stale"
