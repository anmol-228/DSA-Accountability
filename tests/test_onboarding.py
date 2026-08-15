import datetime as dt

from app.services import curriculum_service, onboarding_service, schedule_service


def test_first_run_configures_an_arbitrary_repo_and_start_date(conn, tmp_path):
    repo = tmp_path / "my-learning-journal"
    result = onboarding_service.configure_first_run(
        conn,
        start_date=dt.date(2027, 1, 1),
        learner_repo=repo,
        auto_push=False,
        startup_enabled=False,
        manage_startup=False,
    )
    curriculum_service.seed_curriculum(conn)

    settings = {
        row["key"]: row["value"]
        for row in conn.execute("SELECT key, value FROM settings")
    }
    assert settings["first_run_complete"] == "1"
    assert settings["schedule_start_date"] == "2027-01-01"
    assert settings["schedule_version"] == "start-2027-01-01-v1"
    assert settings["dsa135_repo_path"] == str(repo)
    assert settings["auto_push_enabled"] == "0"
    assert "pairing_token" in settings
    assert (repo / ".git").exists()
    assert result["target_end_date"] == dt.date(2027, 5, 15)
    assert conn.execute(
        "SELECT original_due_date FROM curriculum_days WHERE day_number = 135"
    ).fetchone()["original_due_date"] == "2027-05-15"


def test_existing_installation_infers_its_day_one_without_rescheduling(conn):
    schedule_service.set_start_date(conn, dt.date(2026, 8, 15))
    curriculum_service.seed_curriculum(conn)
    before = [
        row[0]
        for row in conn.execute(
            "SELECT original_due_date FROM curriculum_days ORDER BY day_number"
        )
    ]
    conn.execute("DELETE FROM settings WHERE key = 'schedule_start_date'")
    conn.execute(
        "UPDATE settings SET value = '2026-08-15-v1' WHERE key = 'schedule_version'"
    )
    conn.commit()

    inferred = schedule_service.ensure_existing_installation_setting(conn)
    after = [
        row[0]
        for row in conn.execute(
            "SELECT original_due_date FROM curriculum_days ORDER BY day_number"
        )
    ]
    assert inferred == dt.date(2026, 8, 15)
    assert before == after


def test_first_run_without_github_remote_is_valid_local_git(conn, tmp_path):
    repo = tmp_path / "local-only"
    result = onboarding_service.configure_first_run(
        conn,
        start_date="2027-06-15",
        learner_repo=repo,
        remote_url="",
        auto_push=True,
        manage_startup=False,
    )
    assert result["remote_configured"] is False
    assert (repo / ".git").exists()
