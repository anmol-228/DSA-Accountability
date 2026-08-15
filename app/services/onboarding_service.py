"""Transactional first-run configuration used by the setup UI and tests."""
from __future__ import annotations

import datetime as dt
import os
import sqlite3
from pathlib import Path

from app.services import (
    git_service,
    pairing_service,
    pipeline_service,
    schedule_service,
    startup_service,
)


def configure_first_run(
    conn: sqlite3.Connection,
    *,
    start_date: dt.date | str,
    learner_repo: Path | str,
    remote_url: str = "",
    auto_push: bool = True,
    startup_enabled: bool = False,
    manage_startup: bool = True,
) -> dict:
    raw_repo = os.fspath(learner_repo).strip()
    if not raw_repo:
        raise ValueError("Choose a learner repository folder.")
    repo = Path(raw_repo).expanduser()

    start = schedule_service.parse_start_date(start_date)
    git_service.ensure_repo(repo)
    pipeline_service.set_dsa135_repo(conn, repo)

    remote = remote_url.strip()
    if remote:
        git_service.add_remote(repo, remote)

    schedule_service.set_start_date(conn, start)
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('auto_push_enabled', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        ("1" if auto_push else "0",),
    )
    pairing_service.get_or_create_token(conn)
    conn.execute(
        "INSERT INTO settings (key, value) VALUES ('first_run_complete', '1') "
        "ON CONFLICT(key) DO UPDATE SET value = '1'"
    )
    conn.commit()

    if manage_startup:
        if startup_enabled:
            startup_service.enable_startup()
        else:
            startup_service.disable_startup()

    return {
        "start_date": start,
        "target_end_date": schedule_service.target_end_date(conn),
        "learner_repo": repo,
        "remote_configured": bool(remote),
        "auto_push": auto_push,
        "startup_enabled": startup_enabled,
    }
