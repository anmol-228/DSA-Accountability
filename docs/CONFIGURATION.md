# Configuration

## Schedule

First Run stores `schedule_start_date` in the local SQLite `settings` table and
derives all 135 due dates. Existing installations infer this setting from their
already-seeded Day 1 row, so upgrades preserve their schedule.

The current UI intentionally treats the selected start date as a first-run
choice. Changing an established schedule after progress exists is not exposed
as a casual Settings action.

## Learner repository

Choose any local folder. An existing Git repository is reused; a new/empty
folder is initialized on `main`. The setting can be changed later, but move or
copy learner files yourself first and verify the destination's Git history.

## GitHub and automatic push

An `origin` remote is optional. Automatic push can be toggled in Settings. With
no remote or with auto-push off, finalized work remains in local Git.

## Chrome pairing

The random token authenticates the extension to the loopback API. It is hidden
by default in Settings. Regeneration disconnects the extension and should be a
last resort, not the first troubleshooting step.

## Windows startup and reminders

Startup is a per-user Startup-folder shortcut and can be toggled in First Run or
Settings. Default reminder times are 10:00, 16:00, and 20:00 local Windows time.

## Runtime paths

- Packaged data: `%LOCALAPPDATA%\DSAAccountability`
- Source-development data: `%LOCALAPPDATA%\DSAAccountability-Development`
- SQLite: `<data-root>\data\progress.sqlite`
- Backups: `<data-root>\backups`
- Logs: `<data-root>\logs`

Environment variables beginning with `DSA_ACCOUNTABILITY_` are reserved for
runtime/test isolation. Normal users should configure the app through its UI.
