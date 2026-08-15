"""Application constants and portable runtime paths.

The 135-day curriculum is fixed, but its calendar anchor is per-user state in
SQLite. No date or learner-repository path in this module identifies a
particular installation.
"""
from __future__ import annotations

import datetime as _dt
import os
import sys
from pathlib import Path

# --- Curriculum shape -----------------------------------------------------------
TOTAL_CURRICULUM_DAYS = 135


def now_local() -> _dt.datetime:
    """Timezone-aware current time using the Windows user's local timezone."""
    return _dt.datetime.now().astimezone()


def local_timezone() -> _dt.tzinfo:
    return now_local().tzinfo or _dt.timezone.utc


def today_local() -> _dt.date:
    return now_local().date()


# --- Paths -----------------------------------------------------------------------
# APP_ROOT is where source lives in dev mode. When PyInstaller freezes the
# app, bundled read-only resources (curriculum JSON, migrations) are
# extracted to sys._MEIPASS instead, and writable data must NOT go there
# (that directory is a throwaway temp extraction, wiped between runs).
IS_FROZEN = bool(getattr(sys, "frozen", False))
APP_ROOT = Path(__file__).resolve().parent.parent
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", str(APP_ROOT))) if IS_FROZEN else APP_ROOT
PRODUCTION_DATA_ROOT = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "DSAAccountability"
PRODUCTION_DB_PATH = PRODUCTION_DATA_ROOT / "data" / "progress.sqlite"
DEVELOPMENT_DATA_ROOT = (
    Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
    / "DSAAccountability-Development"
)

if IS_FROZEN:
    _user_data_root = PRODUCTION_DATA_ROOT
else:
    # Keep dev DBs, logs, backups, and compiler output outside the source
    # checkout so stale runtime artifacts cannot masquerade as production.
    _user_data_root = DEVELOPMENT_DATA_ROOT

# A friendly suggestion only. First run lets every user choose any folder.
DEFAULT_DSA135_REPO = Path.home() / "DSA-135"

DATA_DIR = _user_data_root / "data"
BACKUPS_DIR = _user_data_root / "backups"
LOGS_DIR = _user_data_root / "logs"
DB_PATH = DATA_DIR / "progress.sqlite"
TEST_DB_PATH = DATA_DIR / "progress.test.sqlite"
CURRICULUM_DIR = RESOURCE_ROOT / "curriculum"
SCHEDULE_JSON = CURRICULUM_DIR / "schedule.json"
FALLBACK_PROBLEMS_JSON = CURRICULUM_DIR / "fallback_free_problems.json"
MIGRATIONS_DIR = RESOURCE_ROOT / "app" / "migrations"

# --- Local API ---------------------------------------------------------------------
LOCAL_API_HOST = "127.0.0.1"
LOCAL_API_DEFAULT_PORT = 8765
LOCAL_API_PORT_RANGE = range(8765, 8785)  # tried in order on conflict

# --- Reminders ---------------------------------------------------------------------
DEFAULT_REMINDER_TIMES = ["10:00", "16:00", "20:00"]

# --- Revision spacing (days) --------------------------------------------------------
REVISION_INTERVALS_DEFAULT = [2, 7, 21, 45]
REVISION_INTERVALS_RED = [1, 3, 7, 21, 45]
MAX_GENERATED_REVISIONS_PER_DAY = 2

# --- Recovery ------------------------------------------------------------------------
RECOVERY_MODE_THRESHOLD_DAYS = 2
