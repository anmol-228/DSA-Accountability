"""Rolling local database backups (spec section 53)."""
from __future__ import annotations

from pathlib import Path

from app import config, database


def backup_now(label: str = "manual") -> Path | None:
    return database.backup_db(config.DB_PATH, label=label)


def list_backups() -> list[Path]:
    return sorted(config.BACKUPS_DIR.glob("progress-*.sqlite"), reverse=True)
