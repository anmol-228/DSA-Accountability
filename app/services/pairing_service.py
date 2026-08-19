"""Random pairing token for the localhost API (spec section 32).
The Chrome extension must present this token on every request via the
X-DSA-Token header. Requests without a valid token are rejected.

Token invariant (pairing-token lifecycle audit -- see
PAIRING_TOKEN_LIFECYCLE_AUDIT.md): exactly two legitimate write paths.
get_or_create_token() creates one only when none exists and otherwise always
returns the existing value unchanged; regenerate_token() is the only path
that overwrites, and its sole caller (SettingsDialog._regenerate_token) is
gated behind an explicit confirmation dialog defaulting to Cancel. No other
startup/migration/seeding path may call regenerate_token(). Both paths now
log a fingerprint-only audit_log row so a future change is provable from the
database itself -- the raw token is never written to audit_log, logs, or
anywhere outside the settings table itself."""
from __future__ import annotations

import hashlib
import secrets
import sqlite3

from app import config
from app.services import runtime_env

SETTING_KEY = "pairing_token"


def _fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:8]


def _log_token_event(conn: sqlite3.Connection, action: str, token: str) -> None:
    conn.execute(
        "INSERT INTO audit_log (ts, actor, action, details) VALUES (?, 'system', ?, ?)",
        (config.now_local().isoformat(), action, f"pairing_token_fingerprint={_fingerprint(token)}"),
    )


def get_or_create_token(conn: sqlite3.Connection) -> str:
    runtime_env.assert_connection_access_allowed(conn, config.PRODUCTION_DB_PATH, "read/create pairing token")
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (SETTING_KEY,)).fetchone()
    if row and row["value"]:
        return row["value"]
    token = secrets.token_urlsafe(24)
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (SETTING_KEY, token),
    )
    _log_token_event(conn, "pairing_token_created", token)
    conn.commit()
    return token


def regenerate_token(conn: sqlite3.Connection) -> str:
    runtime_env.assert_connection_access_allowed(conn, config.PRODUCTION_DB_PATH, "regenerate pairing token")
    token = secrets.token_urlsafe(24)
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (SETTING_KEY, token),
    )
    _log_token_event(conn, "pairing_token_regenerated", token)
    conn.commit()
    return token


def is_valid(conn: sqlite3.Connection, presented_token: str | None) -> bool:
    if not presented_token:
        return False
    return secrets.compare_digest(presented_token, get_or_create_token(conn))
