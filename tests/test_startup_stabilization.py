"""Production stabilization pass (2026-08-12): first-run persistence must
be a one-time concept fully decoupled from runtime health, and autostart
must never spawn a second competing process. See
docs/PRODUCTION_STABILIZATION_2026-08-12.md for the real production bugs
these guard against.
"""
from __future__ import annotations

from app.services import pairing_service, single_instance


def _first_run_needed(conn) -> bool:
    """Mirrors main.py's exact gating condition."""
    return conn.execute(
        "SELECT value FROM settings WHERE key = 'first_run_complete'"
    ).fetchone() is None


def test_first_run_needed_on_brand_new_install(seeded_conn):
    assert _first_run_needed(seeded_conn) is True


def test_first_run_not_needed_once_marked_complete_regardless_of_health(seeded_conn):
    """Case B-E of the production-stabilization test matrix: once
    first_run_complete is set, NOTHING about runtime health (GitHub
    down, Chrome disconnected, Java missing, etc.) may cause the wizard
    to reappear -- the gating condition in main.py checks only this one
    flag, never re-derives it from run_checks()'s live health output."""
    seeded_conn.execute(
        "INSERT INTO settings (key, value) VALUES ('first_run_complete', '1')"
    )
    seeded_conn.commit()
    # Deliberately leave every other integration setting/table completely
    # unhealthy/absent (no dsa135_repo_path, no auto_push_enabled, no
    # startup registration) -- none of that may resurrect the wizard.
    assert _first_run_needed(seeded_conn) is False


def _isolate_repo(conn, tmp_path):
    """run_checks() resolves the DSA-135 repo path as part of its normal
    checklist -- under the final production repair pass's structural
    guard (runtime_env.is_test_environment()), that now hard-fails unless
    a test explicitly isolates it first, exactly like any other caller."""
    from app.services import pipeline_service
    pipeline_service.set_dsa135_repo(conn, tmp_path / "DSA-135")


def test_first_run_wizard_check_generates_token_before_evaluating_it(seeded_conn, tmp_path):
    """Regression test for the exact contradictory-state bug: 'Token not
    generated' rendered while a real token was displayed two widgets
    below it in the same dialog, because the checklist evaluated token
    presence before the token was created. Mirrors FirstRunWizard.__init__'s
    corrected order: create-or-fetch the token BEFORE calling run_checks()."""
    from app.ui.first_run_wizard import run_checks

    _isolate_repo(seeded_conn, tmp_path)
    assert seeded_conn.execute(
        "SELECT 1 FROM settings WHERE key = 'pairing_token'"
    ).fetchone() is None

    # Correct order (what FirstRunWizard.__init__ now does):
    token = pairing_service.get_or_create_token(seeded_conn)
    checks = dict((label, (ok, detail)) for label, ok, detail in run_checks(seeded_conn))

    assert token
    ok, detail = checks["Chrome extension"]
    assert ok is True
    assert "not generated" not in detail.lower()


def test_first_run_wizard_check_would_be_contradictory_in_wrong_order(seeded_conn, tmp_path):
    """Proves the bug existed: evaluating the checklist BEFORE creating
    the token (the old order) reports 'Token not generated' on a
    genuinely first-ever run, even though a token is about to be shown
    to the user moments later."""
    from app.ui.first_run_wizard import run_checks

    _isolate_repo(seeded_conn, tmp_path)
    checks = dict((label, (ok, detail)) for label, ok, detail in run_checks(seeded_conn))
    ok, detail = checks["Chrome extension"]
    assert ok is False
    assert "not generated" in detail.lower()


# --- single-instance protection ------------------------------------------------

def test_single_instance_lock_blocks_second_acquire():
    # A unique per-test mutex name avoids colliding with a real running
    # instance of the app on the developer's machine, or with other test
    # runs -- Windows named mutexes are system-global, not per-process.
    import uuid
    name = f"Global\\DSAAccountability_test_{uuid.uuid4().hex}"
    first = single_instance.acquire(name)
    assert first is True
    second = single_instance.acquire(name)
    assert second is False
