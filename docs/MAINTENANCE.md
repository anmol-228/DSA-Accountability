# Backup, update, recovery, and uninstall

## Backup and recovery

Use Settings → **Backup now**. The app uses SQLite's Online Backup API, which is
safe with WAL mode. Preserve the resulting `.sqlite` file outside the install
folder. Automatic pre-migration backups are also kept in Local AppData.

To recover, close the app, preserve the current AppData folder, and restore only
from a known-good SQLite-native backup. Do not delete or replace data while the
app is running. If uncertain, stop and seek help before changing files.

## Update

1. Close the old app.
2. Create and preserve a fresh backup.
3. Download/extract the new release to a stable folder.
4. Run it once; versioned migrations apply automatically and leave a
   pre-migration backup.
5. If startup was enabled and the folder changed, toggle startup off/on so the
   shortcut points to the new executable.
6. Reload the unpacked Chrome extension and refresh open LeetCode tabs when its
   version changes.

## Move to another PC

Preserve the learner Git repository and a SQLite-native backup. Install the app
on the new PC, close it, and restore/configure carefully. GitHub can help move
committed learner files, but it does not contain the local progress database.

## Uninstall or reset

1. Disable Windows startup in Settings or run `scripts\disable-startup.ps1`.
2. Remove the extension from `chrome://extensions`.
3. Delete the extracted application/build folder if desired.
4. Decide separately whether to preserve or delete
   `%LOCALAPPDATA%\DSAAccountability`.
5. Decide separately whether to preserve or delete the learner Git repository.

Steps 4 and 5 permanently remove progress/work. They are intentionally separate
and should never be automated without an explicit backup and confirmation.
