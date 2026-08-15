"""Writes accepted Java solutions to their deterministic path in DSA-135,
never silently destroying a prior version of a file (spec section 21)."""
from __future__ import annotations

import re
from pathlib import Path

from app import config
from app.services import runtime_env


def _pascal_case(title: str) -> str:
    words = re.split(r"[^A-Za-z0-9]+", title)
    return "".join(w[:1].upper() + w[1:] for w in words if w)


def week_for_day(day_number: int) -> int:
    return ((day_number - 1) // 7) + 1


def leetcode_file_path(repo_root: Path, day_number: int, leetcode_number: int, title: str) -> Path:
    week = week_for_day(day_number)
    file_name = f"LC{leetcode_number:04d}_{_pascal_case(title)}.java"
    return repo_root / f"Week-{week:02d}" / f"Day-{day_number:03d}" / "leetcode" / file_name


def exercise_file_path(repo_root: Path, day_number: int, canonical_filename: str) -> Path:
    """`canonical_filename` must be the task's explicit `tasks.canonical_filename`
    value (see curriculum/build_schedule.py EXERCISE_FILENAMES) — never
    re-derived from the display title, which can disagree (e.g. "Maximum
    of 3" naive-PascalCased is "MaximumOf3", not the correct "MaximumOfThree")."""
    week = week_for_day(day_number)
    return repo_root / f"Week-{week:02d}" / f"Day-{day_number:03d}" / "exercises" / f"{canonical_filename}.java"


def notes_file_path(repo_root: Path, day_number: int) -> Path:
    week = week_for_day(day_number)
    return repo_root / f"Week-{week:02d}" / f"Day-{day_number:03d}" / "notes.md"


def write_exercise_skeleton_if_missing(target_path: Path, class_name: str) -> bool:
    """Creates a starter skeleton at target_path if — and only if — no
    file exists there yet. Never overwrites existing learner work (spec
    section 6: skeletons only, never pre-solved; never destroy real
    progress). Returns True if a skeleton was written."""
    runtime_env.assert_file_write_allowed(target_path, "write exercise skeleton")
    if target_path.exists():
        return False
    target_path.parent.mkdir(parents=True, exist_ok=True)
    skeleton = (
        f"public class {class_name} {{\n"
        f"    public static void main(String[] args) {{\n"
        f"        // Write your solution here.\n"
        f"    }}\n"
        f"}}\n"
    )
    target_path.write_text(skeleton, encoding="utf-8")
    return True


def write_solution(target_path: Path, code: str) -> tuple[Path, Path | None]:
    """Writes `code` to target_path. If target_path already exists with
    DIFFERENT content, the previous content is preserved as a timestamped
    backup alongside it before being overwritten. Returns
    (written_path, backup_path_or_None)."""
    runtime_env.assert_file_write_allowed(target_path, "write captured solution")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = None

    if target_path.exists():
        existing = target_path.read_text(encoding="utf-8")
        if existing != code:
            stamp = config.now_local().strftime("%Y%m%d-%H%M%S")
            backup_path = target_path.with_name(f"{target_path.stem}.prev-{stamp}{target_path.suffix}")
            backup_path.write_text(existing, encoding="utf-8")
        else:
            return target_path, None  # identical content, nothing to do

    target_path.write_text(code, encoding="utf-8")
    return target_path, backup_path
