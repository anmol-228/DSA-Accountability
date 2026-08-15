# Troubleshooting

## App does not launch or the overlay is missing

1. Check Task Manager for one `DSAAccountability.exe` process.
2. Use the tray icon's Show/Hide action.
3. Check `%LOCALAPPDATA%\DSAAccountability\logs\app.log`.
4. If a monitor change left the overlay off-screen, reset its saved position
   under the app's `HKCU\Software` settings only after preserving current data.
5. Do not delete the SQLite database as a launch diagnostic.

## Java or javac is unavailable

Run `scripts\check-prerequisites.ps1`. Install a full JDK 17+ (not only a JRE),
add its `bin` directory to `PATH`, reopen the app/PowerShell, and verify
`java -version` plus `javac -version`.

## VS Code does not open

VS Code is optional but recommended. Verify `code --version` in a new
PowerShell. You can still open the canonical `.java` file manually; do not edit
a differently named copy and expect the app to finalize it.

## Desktop unreachable in Chrome

1. Confirm the desktop app is running.
2. Reload the unpacked extension and refresh the LeetCode tab.
3. The app tries loopback ports 8765–8784; the extension discovers the current
   authenticated port automatically.
4. Check the app log for the bound port. The server never listens beyond
   `127.0.0.1`.

## Invalid pairing token

Do **not regenerate the token immediately**. Open Settings, show/copy the
existing token locally, paste it into the extension popup, and choose Save &
Test Connection. Confirm you loaded the extension from the same release folder.
Regenerate only when you deliberately want to invalidate the old pairing.

## Accepted is not detected

1. Confirm the assigned problem session started and Java is selected.
2. Click LeetCode's actual Submit button; Run does not arm detection.
3. Wait for a new Accepted result. Historical Accepted UI is intentionally
   ignored.
4. Open the extension debug log and check the content-script version.
5. Reload the extension and refresh the problem tab after an update.

LeetCode can change its DOM. Developers should update/test selectors rather
than weakening the Submit/freshness rules.

## Language or code capture failed

Java is required. Monaco capture is preferred, with bridge/DOM fallbacks. After
a verified fresh Accepted event, use the app's retry/current-editor/manual-code
fallback when offered. Never mark a task complete without the actual Java code.

## Git commit failed

Verify the configured learner path is the intended writable Git repository and
that Git identity is set (`git config user.name` and `git config user.email`,
locally or globally as you prefer). The app stages only task files and will not
fall back to staging everything.

## GitHub push is pending

Local work remains valid. Verify `git remote -v`, network connectivity, and Git
Credential Manager/browser authentication. Automatic retries use backoff. If
you do not want GitHub, disable auto-push or remove the remote after ensuring no
pending work depends on it.

## Startup does not run

Run `scripts\verify-startup.ps1`. It should report a Startup-folder `.lnk` whose
target exists and whose working directory matches the packaged executable.
Move/install the app first, then toggle startup off/on to rebuild the shortcut.

## First Run appears again

Do not repeatedly complete it with different paths. Check that the packaged app
can write `%LOCALAPPDATA%\DSAAccountability` and that you are launching the same
release/user account. Preserve AppData before repair.

## Database recovery

Use a backup created through Settings/SQLite Online Backup API. Close the app,
preserve the entire current AppData directory, validate the candidate backup
with `PRAGMA integrity_check`, and only then restore it. Never copy only a live
WAL database main file or delete data to make the wizard reappear.
