"""Detects and launches VS Code. DSA Accountability is never a code editor
(spec: "the app must not replace VS Code") — this module's only job is to
robustly find the real VS Code install and hand it a file to open, via a
safe argument-list subprocess call (never shell=True / string interpolation).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

_CACHED_EXE: str | None | object = "_unset"  # sentinel so a genuine None (not found) is cached too


def _candidate_install_paths() -> list[Path]:
    import os
    candidates = []
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(Path(local_appdata) / "Programs" / "Microsoft VS Code" / "Code.exe")
    program_files = os.environ.get("ProgramFiles")
    if program_files:
        candidates.append(Path(program_files) / "Microsoft VS Code" / "Code.exe")
    program_files_x86 = os.environ.get("ProgramFiles(x86)")
    if program_files_x86:
        candidates.append(Path(program_files_x86) / "Microsoft VS Code" / "Code.exe")
    return candidates


def _registry_app_path() -> str | None:
    """Windows 'App Paths' registry entries let any correctly-installed app
    register its own exe location for exactly this kind of lookup."""
    try:
        import winreg
    except ImportError:
        return None  # not on Windows
    key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Code.exe"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, key_path) as key:
                value, _ = winreg.QueryValueEx(key, None)
                if value and Path(value).exists():
                    return value
        except OSError:
            continue
    return None


def find_vscode_executable(use_cache: bool = True) -> str | None:
    """Returns a path/command usable to launch VS Code, or None if not
    found by any means. Checked in order: `code`/`code.cmd` on PATH (the
    CLI shim, present when "Add to PATH" was selected at install), the
    Windows App Paths registry entry, then common install directories."""
    global _CACHED_EXE
    if use_cache and _CACHED_EXE != "_unset":
        return _CACHED_EXE  # type: ignore[return-value]

    for cli_name in ("code", "code.cmd"):
        found = shutil.which(cli_name)
        if found:
            _CACHED_EXE = found
            return found

    registry_path = _registry_app_path()
    if registry_path:
        _CACHED_EXE = registry_path
        return registry_path

    for candidate in _candidate_install_paths():
        if candidate.exists():
            _CACHED_EXE = str(candidate)
            return str(candidate)

    _CACHED_EXE = None
    return None


def is_available() -> bool:
    return find_vscode_executable() is not None


def open_file_in_vscode(file_path: Path, workspace_root: Path | None = None) -> tuple[bool, str]:
    """Opens `file_path` in VS Code, focused (`-g` = goto). If
    `workspace_root` is given, opens/reuses that folder as the workspace
    rather than spawning an unrelated single-file window — so repeatedly
    opening different exercises reuses one DSA-135 VS Code window instead
    of piling up unrelated windows."""
    exe = find_vscode_executable()
    if exe is None:
        return False, "VS Code was not found on this machine. Install it from https://code.visualstudio.com/."

    args = [exe]
    if workspace_root is not None:
        args.append(str(workspace_root))
    args += ["-g", str(file_path)]

    try:
        subprocess.Popen(args, shell=False)
    except OSError as exc:
        return False, f"Could not launch VS Code: {exc}"
    return True, f"Opened {file_path.name} in VS Code."


def open_folder_in_vscode(folder_path: Path) -> tuple[bool, str]:
    exe = find_vscode_executable()
    if exe is None:
        return False, "VS Code was not found on this machine."
    try:
        subprocess.Popen([exe, str(folder_path)], shell=False)
    except OSError as exc:
        return False, f"Could not launch VS Code: {exc}"
    return True, f"Opened {folder_path} in VS Code."
