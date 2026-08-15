"""User-level Windows autostart via a shortcut in the Startup folder
(spec section 12). No admin privileges required.

History: this originally used a plain HKCU\\...\\Run key. A real user hit
a case where the app silently failed to launch at logon despite a
correct, present Run-key entry (see PROJECT_STATE.md "Windows Startup
Reliability Fix") -- Run keys are known to be occasionally skipped under
Windows Fast Startup / early-logon timing races. Task Scheduler
("onlogon" trigger) was tried next as the standard more-reliable
alternative, but `schtasks /create` was denied in this environment even
for a trivial task, without elevation -- which this app must never
require. The Startup folder
(`%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup`) is the
third well-established non-elevated mechanism: Windows Explorer launches
everything in it once per interactive logon, and it doesn't share the Run
key's specific failure mode.

Task Manager can always terminate the app -- this is ordinary, safe,
user-level persistence only.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SHORTCUT_NAME = "DSAAccountability.lnk"

# Legacy artifacts from earlier versions of this app, cleaned up on every
# enable/disable so there's never a stale duplicate entry left behind.
_LEGACY_RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
_LEGACY_RUN_VALUE_NAME = "DSAAccountability"
_LEGACY_TASK_NAME = "DSAAccountability"


def _startup_folder() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA environment variable not set (unexpected on Windows)")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _shortcut_path() -> Path:
    return _startup_folder() / SHORTCUT_NAME


def _target_exe_and_args() -> tuple[Path, str]:
    # No --minimized: the overlay must be visible and on top the instant
    # the app launches at logon, not tucked away in the tray. See
    # PROJECT_STATE.md "Startup Reliability Fix" -- this was a real
    # regression where autostart silently launched hidden.
    exe = Path(sys.executable)
    if exe.name.lower().startswith("dsaaccountability"):
        return exe, ""
    # dev mode: launch via the venv python + main.py
    main_py = Path(__file__).resolve().parent.parent / "main.py"
    return exe, f'"{main_py}"'


def _remove_legacy_entries() -> None:
    try:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _LEGACY_RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, _LEGACY_RUN_VALUE_NAME)
        except OSError:
            pass
    except ImportError:
        pass

    try:
        subprocess.run(
            ["schtasks", "/delete", "/tn", _LEGACY_TASK_NAME, "/f"],
            capture_output=True, text=True, shell=False,
        )
    except OSError:
        pass


def enable_startup() -> None:
    _remove_legacy_entries()
    target_exe, args = _target_exe_and_args()
    shortcut_path = _shortcut_path()
    shortcut_path.parent.mkdir(parents=True, exist_ok=True)

    # WScript.Shell's CreateShortcut is the standard, dependency-free way
    # to create a real .lnk file on Windows (no pywin32 required). Values
    # are all internally-computed paths (sys.executable / this file's own
    # location), never user-supplied, so building this small script is safe.
    script = (
        f'$WshShell = New-Object -ComObject WScript.Shell; '
        f'$Shortcut = $WshShell.CreateShortcut("{shortcut_path}"); '
        f'$Shortcut.TargetPath = "{target_exe}"; '
        f'$Shortcut.Arguments = \'{args}\'; '
        f'$Shortcut.WorkingDirectory = "{target_exe.parent}"; '
        f'$Shortcut.Save()'
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, shell=False,
    )
    if result.returncode != 0 or not shortcut_path.exists():
        raise RuntimeError(f"Could not create startup shortcut: {result.stderr or result.stdout}")


def disable_startup() -> None:
    _remove_legacy_entries()
    _shortcut_path().unlink(missing_ok=True)


def is_startup_enabled() -> bool:
    return _shortcut_path().exists()
