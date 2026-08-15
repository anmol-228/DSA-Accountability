"""Compiles and runs standalone learner Java exercises in isolated,
timeout-protected child processes. Learner code is NEVER executed inside
the DSA Accountability Python process itself (spec section 42) — a hung
or crashing beginner program must never freeze the tracker.

.class files are written to a build directory outside the Git-tracked
learner repo (spec section 13), never scattered into DSA-135.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app import config

BUILD_ROOT = config.DATA_DIR / "build-temp"
DEFAULT_RUN_TIMEOUT_SECONDS = 5.0
COMPILE_TIMEOUT_SECONDS = 20.0

_LINE_ERROR_RE = re.compile(r".*\.java:(\d+): error: (.+)")


def find_javac() -> str | None:
    return shutil.which("javac")


def find_java() -> str | None:
    return shutil.which("java")


@dataclass
class CompileResult:
    success: bool
    class_name: str
    build_dir: Path
    raw_stderr: str = ""
    summary: str = ""


@dataclass
class RunResult:
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool

    @property
    def ok(self) -> bool:
        return not self.timed_out and self.returncode == 0


def _strip_comments(source: str) -> str:
    """Not a full Java tokenizer -- doesn't need to be. Only gates a UI
    completion status (spec section 12), never actual compilation."""
    no_block = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    no_line = re.sub(r"//.*", "", no_block)
    return no_line


def is_skeleton_or_empty(source: str) -> bool:
    """True if, after stripping comments, the source has zero statement-
    terminating semicolons anywhere -- i.e. every method body (main()
    included) is still empty, exactly matching the untouched starter
    skeleton. Deliberately lenient the other direction: any real
    statement at all is accepted, per spec section 12's "do not rely
    only on file size" guidance."""
    stripped = _strip_comments(source)
    if not stripped.strip():
        return True
    return stripped.count(";") == 0


def _summarize_javac_errors(stderr: str, max_lines: int = 3) -> str:
    lines = []
    for raw_line in stderr.splitlines():
        m = _LINE_ERROR_RE.match(raw_line)
        if m:
            lines.append(f"Line {m.group(1)}: {m.group(2).strip()}")
        if len(lines) >= max_lines:
            break
    if not lines:
        for raw_line in stderr.splitlines():
            if raw_line.strip():
                lines = [raw_line.strip()]
                break
    return "\n".join(lines) if lines else "Compilation failed."


def compile_java(source_path: Path, class_name: str) -> CompileResult:
    build_dir = BUILD_ROOT / class_name
    build_dir.mkdir(parents=True, exist_ok=True)
    for stale in build_dir.glob("*.class"):
        stale.unlink(missing_ok=True)

    javac = find_javac()
    if javac is None:
        return CompileResult(
            False, class_name, build_dir, raw_stderr="javac not found on PATH",
            summary="Java compiler (javac) not found. Is a JDK installed and on PATH?",
        )

    try:
        proc = subprocess.run(
            [javac, "-d", str(build_dir), str(source_path)],
            capture_output=True, text=True, timeout=COMPILE_TIMEOUT_SECONDS, shell=False,
        )
    except subprocess.TimeoutExpired:
        return CompileResult(False, class_name, build_dir, raw_stderr="javac timed out",
                              summary="Compilation timed out.")

    if proc.returncode != 0:
        return CompileResult(False, class_name, build_dir, raw_stderr=proc.stderr,
                              summary=_summarize_javac_errors(proc.stderr))
    return CompileResult(True, class_name, build_dir)


def run_java_class(class_name: str, build_dir: Path, stdin_text: str = "",
                    timeout: float = DEFAULT_RUN_TIMEOUT_SECONDS) -> RunResult:
    """Runs the compiled class as an isolated child process with
    controlled stdin, captured stdout/stderr, and a hard timeout. On
    timeout, subprocess.run has already killed the child before raising —
    a hung learner program can never freeze the tracker."""
    java = find_java()
    if java is None:
        return RunResult(None, "", "java not found on PATH", timed_out=False)
    try:
        proc = subprocess.run(
            [java, "-cp", str(build_dir), class_name],
            input=stdin_text, capture_output=True, text=True, timeout=timeout, shell=False,
        )
    except subprocess.TimeoutExpired:
        return RunResult(None, "", "", timed_out=True)
    return RunResult(proc.returncode, proc.stdout, proc.stderr, timed_out=False)
