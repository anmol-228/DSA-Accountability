# Testing

## Complete automated suite

```powershell
.\scripts\test.ps1
```

Equivalent commands:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\venv\Scripts\python.exe -m pytest tests -q
node --test tests_js\*.test.js
```

Python tests cover SQLite migrations/backups, 135-day progression, configurable
dates, local Java execution, UI behavior, API freshness, Git/GitHub queueing,
startup, integration cleanup, and runtime isolation. JavaScript tests cover the
content script, page bridge, and service worker.

## Isolation model

Pytest forces the formal TEST environment. All default DB, log, backup, and
learner-repository paths are redirected to a pytest-owned temporary root.
Central guards reject protected production DB/repository paths. Tests must
never inspect, migrate, write, commit, or push a user's real resources.

Set `DSA_ACCOUNTABILITY_PRODUCTION_REPO` to a machine's private learner path
when running local tests if it differs from the generic default; the value is
machine configuration and must not be committed.

## Manual boundaries

Unit tests cannot prove a real user-authored LeetCode submission, Chrome UI
pairing persistence, Git credential-manager authorization, or Windows reboot.
Release validation documents those as deliberate manual checks using disposable
repositories—never fake curriculum completion.
