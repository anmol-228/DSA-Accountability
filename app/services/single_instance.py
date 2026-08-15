"""Single-instance protection (production stabilization pass, section 32).

Autostart + a manual launch (or a stray leftover process from testing)
could otherwise run two DSAAccountability.exe processes at once, which
would bind different localhost API ports, hold two independent SQLite
connections, duplicate the startup reminder, and confuse Chrome's paired
port discovery. Uses a Windows named mutex -- the standard, dependency-free,
non-admin way to detect "is another copy of me already running" -- which
the OS automatically releases if the owning process dies or crashes, so
there's no stale-lock-file cleanup to get wrong.

No-ops safely on non-Windows platforms (there is no other target for this
app, but tests run under whatever platform CI uses).
"""
from __future__ import annotations

import sys

_MUTEX_NAME = "Global\\DSAAccountability_SingleInstance_Mutex"
_WINDOW_TITLE = "DSA Accountability"
_ERROR_ALREADY_EXISTS = 183

_mutex_handle = None  # kept alive for the process lifetime; module-level so it's never GC'd


def acquire(mutex_name: str = _MUTEX_NAME) -> bool:
    """Returns True if this process now owns the single-instance lock
    (i.e. no other copy is running). Returns False if another instance
    already holds it. Idempotent-safe to call more than once; only the
    first call's handle is retained.

    `mutex_name` defaults to the real production lock name; tests pass a
    unique per-test name so they don't collide with a real running
    instance of the app on the same machine (a genuine Windows named
    mutex is system-global, not per-process) or with each other.
    """
    global _mutex_handle
    if sys.platform != "win32":
        return True
    import ctypes

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.CreateMutexW(None, False, mutex_name)
    # ctypes.get_last_error() only reflects the real Win32 last-error code
    # when the DLL was loaded with use_last_error=True (ctypes.windll does
    # not do this by default) -- call GetLastError() directly instead.
    already_running = kernel32.GetLastError() == _ERROR_ALREADY_EXISTS
    if not already_running:
        _mutex_handle = handle  # keep referenced so the OS doesn't reclaim it early
    return not already_running


def bring_existing_instance_forward() -> bool:
    """Best-effort: finds the other instance's overlay window (by its
    explicit title, see OverlayWindow.setWindowTitle) and raises it.
    Returns True if a window was found and a foreground request was sent.
    Never raises -- this is a courtesy, not a requirement; failing to
    find the window still means this (second) process should simply exit."""
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found = []

    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if buf.value == _WINDOW_TITLE:
            found.append(hwnd)
            return False
        return True

    try:
        user32.EnumWindows(EnumWindowsProc(_callback), 0)
    except Exception:  # noqa: BLE001 - purely a courtesy action
        return False

    if not found:
        return False
    hwnd = found[0]
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    return True
