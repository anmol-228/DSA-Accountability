"""Runtime environment model (final production repair pass).

A real incident this session proved that "helpful" fallback logic in
production code (recovering a genuinely-missing repo-path setting by
probing config.DEFAULT_DSA135_REPO) is dangerous when the same code runs
under pytest: an isolated test's fresh, unconfigured DB has no
dsa135_repo_path setting either, and a fallback can resolve to a real learner
repository, writing test commits and files into it. Individual tests
remembering to call set_dsa135_repo() is
not a structural fix -- the next new test can make the same mistake.

This module makes the distinction explicit and machine-checkable, so
production-data fallback can be made structurally impossible during tests
rather than merely discouraged by convention.
"""
from __future__ import annotations

import enum
import os
import sqlite3
import sys
from pathlib import Path


class ProductionDataAccessError(RuntimeError):
    """Raised when code running in a TEST environment would otherwise
    silently fall back to a real, non-isolated production resource (the
    real DSA-135 repo, the real production DB, the real pairing token).
    Tests must explicitly configure an isolated resource; this exception
    exists so that failing to do so is loud and immediate, not a silent
    write into real user data.
    """


class RuntimeEnvironment(str, enum.Enum):
    """Explicit execution contexts with different safety boundaries."""

    PRODUCTION = "PRODUCTION"
    DEVELOPMENT = "DEVELOPMENT"
    TEST = "TEST"
    LIVE_INTEGRATION_TEST = "LIVE_INTEGRATION_TEST"


ENVIRONMENT_VARIABLE = "DSA_ACCOUNTABILITY_ENV"
TEST_ROOT_VARIABLE = "DSA_ACCOUNTABILITY_TEST_ROOT"
TEST_DB_VARIABLE = "DSA_ACCOUNTABILITY_TEST_DB"
TEST_REPO_VARIABLE = "DSA_ACCOUNTABILITY_TEST_REPO"
PRODUCTION_DB_VARIABLE = "DSA_ACCOUNTABILITY_PRODUCTION_DB"
PRODUCTION_REPO_VARIABLE = "DSA_ACCOUNTABILITY_PRODUCTION_REPO"


def _running_under_pytest() -> bool:
    # PYTEST_CURRENT_TEST covers fixture setup/test/teardown. `pytest` in
    # sys.modules additionally covers collection and session-fixture startup,
    # before PYTEST_CURRENT_TEST is installed.
    return "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules


def current_environment() -> RuntimeEnvironment:
    """Return the formal runtime context.

    Pytest always wins over an environment-variable override. This prevents a
    test command from opting itself into PRODUCTION accidentally or maliciously.
    """
    if _running_under_pytest():
        return RuntimeEnvironment.TEST

    explicit = os.environ.get(ENVIRONMENT_VARIABLE, "").strip().upper()
    if explicit:
        try:
            return RuntimeEnvironment(explicit)
        except ValueError as exc:
            allowed = ", ".join(e.value for e in RuntimeEnvironment)
            raise RuntimeError(
                f"Invalid {ENVIRONMENT_VARIABLE}={explicit!r}; expected one of {allowed}"
            ) from exc

    return RuntimeEnvironment.PRODUCTION if bool(getattr(sys, "frozen", False)) else RuntimeEnvironment.DEVELOPMENT


def is_test_environment() -> bool:
    """True when running under pytest.

    Detected structurally via PYTEST_CURRENT_TEST, which pytest sets in
    the environment for the duration of every single test automatically
    -- no test file has to opt in, so a newly-written test gets this
    protection for free, unlike the previous approach where safety
    depended on every test author remembering to call
    pipeline_service.set_dsa135_repo() with an isolated path first.
    """
    return current_environment() is RuntimeEnvironment.TEST


def _canonical(path: Path | str) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _same_or_within(path: Path | str, root: Path | str) -> bool:
    candidate = _canonical(path)
    protected = _canonical(root)
    try:
        return os.path.commonpath([candidate, protected]) == protected
    except ValueError:  # different Windows drives
        return False


def production_db_path(default: Path | str) -> Path:
    return Path(os.environ.get(PRODUCTION_DB_VARIABLE, os.fspath(default)))


def production_repo_paths() -> tuple[Path, ...]:
    # Protect the generic default on every machine. Installations that use a
    # different learner repo can add it through the private environment
    # variable used by their local test command; public source never embeds a
    # person's drive or username.
    paths = [Path.home() / "DSA-135"]
    configured = os.environ.get(PRODUCTION_REPO_VARIABLE, "").strip()
    if configured:
        paths.append(Path(configured))
    return tuple(paths)


def assert_database_access_allowed(path: Path | str, production_path: Path | str) -> None:
    if not is_test_environment():
        return
    protected = production_db_path(production_path)
    if _canonical(path) == _canonical(protected):
        raise ProductionDataAccessError(
            f"TEST attempted to access production SQLite database {protected}. "
            "Tests must use the isolated database supplied by tests/conftest.py."
        )


def connection_database_paths(conn: sqlite3.Connection) -> tuple[Path, ...]:
    return tuple(Path(row[2]) for row in conn.execute("PRAGMA database_list") if row[2])


def assert_connection_access_allowed(
    conn: sqlite3.Connection, production_path: Path | str, operation: str
) -> None:
    if not is_test_environment():
        return
    protected = production_db_path(production_path)
    for path in connection_database_paths(conn):
        if _canonical(path) == _canonical(protected):
            raise ProductionDataAccessError(
                f"TEST attempted production database operation {operation!r} on {protected}."
            )


def assert_repo_access_allowed(repo_path: Path | str, operation: str) -> None:
    if not is_test_environment():
        return
    for protected in production_repo_paths():
        if _same_or_within(repo_path, protected):
            raise ProductionDataAccessError(
                f"TEST attempted learner-repository operation {operation!r} at {repo_path}; "
                f"protected production root is {protected}."
            )


def assert_file_write_allowed(path: Path | str, operation: str) -> None:
    assert_repo_access_allowed(path, operation)


def get_test_repo_path() -> Path:
    value = os.environ.get(TEST_REPO_VARIABLE, "").strip()
    if not value:
        raise ProductionDataAccessError(
            f"TEST has no isolated learner repo. {TEST_REPO_VARIABLE} must be set by the global test fixture."
        )
    path = Path(value)
    assert_repo_access_allowed(path, "resolve isolated test repo")
    return path


def get_test_db_path(candidate: Path | str | None = None) -> Path:
    value = os.environ.get(TEST_DB_VARIABLE, "").strip()
    if not value:
        raise ProductionDataAccessError(
            f"TEST requested the default database before {TEST_DB_VARIABLE} was configured. "
            "Use an explicit temporary path or the global tests/conftest.py fixture."
        )
    path = Path(candidate) if candidate is not None else Path(value)
    root_value = os.environ.get(TEST_ROOT_VARIABLE, "").strip()
    if not root_value or not _same_or_within(path, Path(root_value)):
        raise ProductionDataAccessError(
            f"TEST database path {path} is outside the isolated test root {root_value or '<unset>'}."
        )
    return path
