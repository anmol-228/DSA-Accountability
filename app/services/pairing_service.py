"""Random pairing token for the localhost API (spec section 32).
The Chrome extension must present this token on every request via the
X-DSA-Token header. Requests without a valid token are rejected."""
from __future__ import annotations

import secrets
import sqlite3

from app import config
from app.services import runtime_env

SETTING_KEY = "pairing_token"


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
    conn.commit()
    return token


def is_valid(conn: sqlite3.Connection, presented_token: str | None) -> bool:
    if not presented_token:
        return False
    return secrets.compare_digest(presented_token, get_or_create_token(conn))
