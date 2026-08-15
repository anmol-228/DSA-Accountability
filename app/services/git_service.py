"""Safe Git operations scoped to the DSA-135 solutions repo.

Safety rules (spec section 23 / 72):
- Never `git add .` / `git add -A`.
- Stage only the specific files belonging to the completed task.
- Never force-push, reset, or rewrite history here.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.services import runtime_env


class GitError(RuntimeError):
    pass


@dataclass
class CommitResult:
    success: bool
    commit_hash: str | None
    message: str
    error: str | None = None


def _run(args: list[str], cwd: Path, timeout: int = 30) -> subprocess.CompletedProcess:
    runtime_env.assert_repo_access_allowed(cwd, f"git {' '.join(args[:2])}")
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=timeout
    )


def is_repo(repo_path: Path) -> bool:
    runtime_env.assert_repo_access_allowed(repo_path, "inspect git repository")
    return (repo_path / ".git").exists()


def ensure_repo(repo_path: Path) -> bool:
    """Initializes a git repo at repo_path if one doesn't already exist.
    Returns True if a new repo was created."""
    runtime_env.assert_repo_access_allowed(repo_path, "initialize git repository")
    repo_path.mkdir(parents=True, exist_ok=True)
    if is_repo(repo_path):
        return False
    result = _run(["init", "-b", "main"], cwd=repo_path)
    if result.returncode != 0:
        raise GitError(f"git init failed: {result.stderr}")
    return True


def has_remote(repo_path: Path, remote: str = "origin") -> bool:
    result = _run(["remote"], cwd=repo_path)
    return remote in result.stdout.split()


def add_remote(repo_path: Path, url: str, remote: str = "origin") -> None:
    if has_remote(repo_path, remote):
        _run(["remote", "set-url", remote, url], cwd=repo_path)
    else:
        _run(["remote", "add", remote, url], cwd=repo_path)


def remote_url(repo_path: Path, remote: str = "origin") -> str | None:
    result = _run(["remote", "get-url", remote], cwd=repo_path)
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None


def clone_repo(remote_url: str, target_path: Path) -> None:
    """Clone into a new explicit target without touching any existing repo."""
    runtime_env.assert_repo_access_allowed(target_path, "clone integration repository")
    if target_path.exists():
        raise GitError(f"refusing to clone over existing path: {target_path}")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    result = _run(["clone", "--origin", "origin", remote_url, str(target_path)], cwd=target_path.parent, timeout=120)
    if result.returncode != 0:
        raise GitError(f"git clone failed: {(result.stderr or result.stdout).strip()}")


def current_branch(repo_path: Path) -> str:
    result = _run(["branch", "--show-current"], cwd=repo_path)
    return result.stdout.strip() or "main"


def safe_commit(repo_path: Path, files: list[Path], message: str) -> CommitResult:
    """Stages ONLY the given files (relative or absolute, must exist under
    repo_path) and commits them. Never touches unrelated working-tree state."""
    if not files:
        return CommitResult(success=False, commit_hash=None, message=message, error="no files given")

    rel_files: list[str] = []
    for f in files:
        f = Path(f)
        try:
            rel = f.relative_to(repo_path)
        except ValueError:
            return CommitResult(success=False, commit_hash=None, message=message,
                                 error=f"file {f} is outside repo {repo_path}")
        rel_files.append(str(rel))

    add_result = _run(["add", "--", *rel_files], cwd=repo_path)
    if add_result.returncode != 0:
        return CommitResult(success=False, commit_hash=None, message=message, error=add_result.stderr)

    diff_check = _run(["diff", "--cached", "--quiet"], cwd=repo_path)
    if diff_check.returncode == 0:
        return CommitResult(success=False, commit_hash=None, message=message,
                             error="nothing to commit (no changes in staged files)")

    commit_result = _run(["commit", "-m", message], cwd=repo_path)
    if commit_result.returncode != 0:
        return CommitResult(success=False, commit_hash=None, message=message, error=commit_result.stderr)

    hash_result = _run(["rev-parse", "HEAD"], cwd=repo_path)
    commit_hash = hash_result.stdout.strip() if hash_result.returncode == 0 else None
    return CommitResult(success=True, commit_hash=commit_hash, message=message)


def push(repo_path: Path, remote: str = "origin", branch: str | None = None) -> tuple[bool, str | None]:
    branch = branch or current_branch(repo_path)
    result = _run(["push", remote, branch], cwd=repo_path, timeout=60)
    if result.returncode == 0:
        return True, None
    return False, (result.stderr or result.stdout).strip()


def is_working_tree_clean(repo_path: Path) -> bool:
    result = _run(["status", "--porcelain"], cwd=repo_path)
    return result.returncode == 0 and result.stdout.strip() == ""


def is_working_tree_clean_except(repo_path: Path, exclude_dir: str) -> bool:
    """Like is_working_tree_clean, but ignores changes confined to
    `exclude_dir` (relative to repo_path). Used before starting an
    integration-test commit: the test archive itself was just written to
    disk (untracked/modified) and is exactly what's about to be
    committed, so it must not itself count as "dirty" -- but anything
    outside that directory still must be clean, or the operation aborts
    rather than risk mixing in real uncommitted work."""
    result = _run(["status", "--porcelain", "--", ".", f":!{exclude_dir}"], cwd=repo_path)
    return result.returncode == 0 and result.stdout.strip() == ""


def create_and_checkout_branch(repo_path: Path, branch_name: str, base: str = "main") -> tuple[bool, str | None]:
    result = _run(["checkout", "-b", branch_name, base], cwd=repo_path)
    if result.returncode == 0:
        return True, None
    return False, (result.stderr or result.stdout).strip()


def checkout(repo_path: Path, branch_name: str) -> tuple[bool, str | None]:
    result = _run(["checkout", branch_name], cwd=repo_path)
    if result.returncode == 0:
        return True, None
    return False, (result.stderr or result.stdout).strip()


def delete_local_branch(repo_path: Path, branch_name: str) -> tuple[bool, str | None]:
    """Never -D-forces a branch that hasn't been pushed/merged silently
    lost -- callers of this in this codebase only ever delete a
    just-pushed disposable integration-test branch."""
    result = _run(["branch", "-D", branch_name], cwd=repo_path)
    if result.returncode == 0:
        return True, None
    return False, (result.stderr or result.stdout).strip()


def delete_remote_branch(repo_path: Path, branch_name: str, remote: str = "origin") -> tuple[bool, str | None]:
    result = _run(["push", remote, "--delete", branch_name], cwd=repo_path, timeout=60)
    if result.returncode == 0:
        return True, None
    return False, (result.stderr or result.stdout).strip()


def remote_branch_exists(repo_path: Path, branch_name: str, remote: str = "origin") -> bool:
    result = _run(["ls-remote", "--heads", remote, branch_name], cwd=repo_path, timeout=30)
    return result.returncode == 0 and branch_name in result.stdout
