"""SQLite connection management and versioned migrations."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from app import config
from app.services import runtime_env


class MigrationError(RuntimeError):
    """Raised when a migration script fails partway through.

    The pre-migration backup (backup_path, if one was taken) is left
    completely untouched by this failure -- run_migrations never wipes or
    silently recreates the database on error. The caller is expected to
    show a clear recovery message pointing at the backup rather than
    letting a bare traceback look like data loss.
    """

    def __init__(self, version: int, backup_path: Path | None, original: Exception):
        self.version = version
        self.backup_path = backup_path
        self.original = original
        detail = f" A pre-migration backup is available at: {backup_path}" if backup_path else ""
        super().__init__(f"Migration {version} failed: {original}.{detail}")


def _resolve_db_path(db_path: Path | None) -> Path:
    if db_path is not None:
        return Path(db_path)
    if runtime_env.is_test_environment():
        # `config.DB_PATH` may be narrowed further by a per-test fixture (for
        # example, a real HTTP server test). The session fixture guarantees it
        # remains under the pytest temp root and provides the required marker.
        return runtime_env.get_test_db_path(config.DB_PATH)
    return config.DB_PATH


def _migration_files() -> list[Path]:
    return sorted(config.MIGRATIONS_DIR.glob("*.sql"))


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = _resolve_db_path(db_path)
    runtime_env.assert_database_access_allowed(path, config.PRODUCTION_DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _applied_versions(conn: sqlite3.Connection) -> set[int]:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    return {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}


def backup_db(db_path: Path | None = None, label: str = "pre-migration") -> Path | None:
    """WAL-safe snapshot via SQLite's own online backup API.

    A plain file copy (the previous implementation) can capture a torn or
    inconsistent snapshot if another connection is mid-write while running
    in WAL mode -- the .sqlite-wal file's uncommitted pages wouldn't be
    reflected correctly in a byte-for-byte copy of just the main file.
    sqlite3.Connection.backup() uses SQLite's Online Backup API, which
    takes a consistent, complete snapshot regardless of WAL state and
    without requiring the source to be closed.
    """
    path = _resolve_db_path(db_path)
    runtime_env.assert_database_access_allowed(path, config.PRODUCTION_DB_PATH)
    if not path.exists():
        return None
    config.BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = config.now_local().strftime("%Y%m%d-%H%M%S")
    dest = config.BACKUPS_DIR / f"progress-{stamp}-{label}.sqlite"

    src = sqlite3.connect(str(path))
    try:
        dst = sqlite3.connect(str(dest))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()

    _rotate_backups()
    return dest


def _rotate_backups(keep: int = 30) -> None:
    backups = sorted(config.BACKUPS_DIR.glob("progress-*.sqlite"), key=lambda p: p.stat().st_mtime)
    while len(backups) > keep:
        oldest = backups.pop(0)
        oldest.unlink(missing_ok=True)


def run_migrations(db_path: Path | None = None) -> list[int]:
    """Apply any pending .sql migrations in order. Returns applied version numbers.

    On failure, raises MigrationError rather than letting a bare exception
    propagate -- the pre-migration backup taken below is always preserved
    untouched, and the failure never triggers a DB wipe/recreate anywhere
    in this function. The caller (app startup) is expected to show the
    user a clear message pointing at the backup rather than crashing
    silently or losing progress.
    """
    path = _resolve_db_path(db_path)
    backup_path = backup_db(path, label="pre-migration") if path.exists() else None

    conn = get_connection(path)
    applied: list[int] = []
    try:
        existing = _applied_versions(conn)
        for f in _migration_files():
            version = int(f.name.split("_")[0])
            if version in existing:
                continue
            sql = f.read_text(encoding="utf-8")
            try:
                # conn.executescript() cannot be wrapped for atomic
                # rollback -- per the sqlite3 docs it implicitly commits
                # any pending transaction before running, so a manual
                # BEGIN before it would just get committed away, and a
                # failure partway through the script can leave earlier
                # statements already durably applied. Executing each
                # statement individually inside one real transaction lets
                # SQLite's transactional DDL support actually roll back a
                # partial failure. Safe for these migration files (plain
                # CREATE TABLE/ALTER TABLE/CREATE INDEX statements, no
                # semicolons embedded in string literals or triggers).
                conn.execute("BEGIN")
                for statement in _split_sql_statements(sql):
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (version, config.now_local().isoformat()),
                )
                conn.commit()
            except Exception as exc:
                conn.rollback()
                raise MigrationError(version, backup_path, exc) from exc
            applied.append(version)
    finally:
        conn.close()
    return applied


def _split_sql_statements(sql: str) -> list[str]:
    return [s.strip() for s in sql.split(";") if s.strip()]


def init_db(db_path: Path | None = None) -> Path:
    path = _resolve_db_path(db_path)
    run_migrations(path)
    return path
