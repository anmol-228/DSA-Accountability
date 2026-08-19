"""Pairing token invariant tests (pairing-token lifecycle audit -- see
PAIRING_TOKEN_LIFECYCLE_AUDIT.md). The core guarantee: once a token exists,
nothing except an explicit regenerate_token() call may ever change it -- not
a repeated get_or_create_token() call, not a migration, not a reseed, not a
simulated app-update/rebuild cycle.
"""
from __future__ import annotations

from app.services import curriculum_service, pairing_service


def test_get_or_create_is_stable_across_thousands_of_calls(conn):
    first = pairing_service.get_or_create_token(conn)
    for _ in range(2000):
        assert pairing_service.get_or_create_token(conn) == first


def test_get_or_create_never_overwrites_across_a_full_reseed_cycle(conn):
    """Simulates a real app-update/rebuild: migration already applied (the
    `conn` fixture runs all migrations), then a full curriculum reseed --
    exactly what every real startup does. Token must be byte-identical
    before and after."""
    token = pairing_service.get_or_create_token(conn)

    curriculum_service.seed_curriculum(conn)

    assert pairing_service.get_or_create_token(conn) == token
    # And again, simulating a second "restart" after the first reseed.
    curriculum_service.seed_curriculum(conn)
    assert pairing_service.get_or_create_token(conn) == token


def test_only_explicit_regenerate_changes_the_token(conn):
    first = pairing_service.get_or_create_token(conn)
    for _ in range(50):
        assert pairing_service.get_or_create_token(conn) == first

    second = pairing_service.regenerate_token(conn)
    assert second != first
    for _ in range(50):
        assert pairing_service.get_or_create_token(conn) == second


def test_token_creation_is_logged_with_fingerprint_only_never_raw(conn):
    import hashlib
    token = pairing_service.get_or_create_token(conn)
    row = conn.execute(
        "SELECT details FROM audit_log WHERE action = 'pairing_token_created' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row is not None
    expected_fp = hashlib.sha256(token.encode()).hexdigest()[:8]
    assert expected_fp in row["details"]
    assert token not in row["details"]  # raw token must never be written to audit_log


def test_regenerate_is_logged_distinctly_from_create(conn):
    pairing_service.get_or_create_token(conn)
    pairing_service.regenerate_token(conn)
    actions = [
        r["action"] for r in conn.execute(
            "SELECT action FROM audit_log WHERE action LIKE 'pairing_token_%' ORDER BY id"
        )
    ]
    assert actions == ["pairing_token_created", "pairing_token_regenerated"]
