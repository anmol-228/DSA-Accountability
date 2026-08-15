# LLM-assisted setup master prompt

Copy everything inside the block below into a capable coding agent that has
access to the downloaded/cloned repository and a terminal on your Windows PC.

```text
You are setting up DSA Accountability for a new user on Windows. Work from the
repository I provide. You have no prior project context: treat README.md and
docs/ as authoritative, inspect the actual source/scripts before choosing any
command, and never invent capabilities.

GOAL

Prepare a safe, working installation in which I can choose my own 135-day start
date, use my own learner Git repository, validate local Java exercises, pair the
included unpacked Chrome extension, and optionally sync to GitHub.

OPERATING LOOP

INSPECT → DETECT A MISSING REQUIREMENT → FIX SAFELY → TEST → CONTINUE.

Repeat until the acceptance checklist passes. Do not stop after installing
dependencies or building the executable. Keep short notes of commands, results,
paths selected, tests, and anything requiring my action.

SAFETY RULES

1. Never delete, reset, overwrite, move, or rewrite arbitrary user files.
2. Never run git reset --hard, clean, rebase, filter-repo, force-push, or
   force-delete a branch in my real learner repository.
3. Never fabricate a curriculum completion, solution, reflection, Accepted
   event, Git commit, or progress record.
4. Never solve or auto-submit a LeetCode problem for me. I author and submit it.
5. Never print, log, commit, upload, or include my pairing token in a report.
   Show/copy it only through the local app when I am pairing Chrome.
6. Never use a production database or my real learner repository for tests.
   Use disposable temporary directories and the documented TEST environment.
7. Back up an existing database through SQLite's Online Backup API or the app's
   Backup action before any migration/replacement. Do not raw-copy a live WAL
   database as if one file were a complete backup.
8. Never commit credentials, cookies, browser profiles, databases, logs, .env
   files, personal tokens, or Git credential-manager data.
9. Install only missing project prerequisites/dependencies. Ask immediately
   before privileged/global software installation or operating-system changes.
10. Do not change repository visibility, create a GitHub repository, add/change
    a remote, or authenticate to GitHub without telling me exactly what is
    needed. Hand control to me for authentication.
11. Pause for Chrome extension UI, GitHub/browser authorization, my real
    LeetCode submission, CAPTCHA, or a Windows reboot. Do not bypass these.

PHASE 1 — INSPECT

- Confirm Windows version/architecture and locate the repository root.
- Read README.md, docs/GETTING_STARTED.md, docs/INSTALLATION.md,
  docs/SECURITY_PRIVACY.md, docs/TESTING.md, and this prompt.
- Inspect git status without discarding changes.
- Run scripts/check-prerequisites.ps1 and independently locate Python, Java,
  javac, Git, VS Code (optional), Node.js (developer tests), and Chrome.
- Determine whether I want the prebuilt release or source-build route. Prefer
  prebuilt for ordinary use; source build requires Python/Node tooling.
- Detect any existing DSA Accountability AppData and learner repo. Preserve
  them; do not assume a fresh install if data already exists.

PHASE 2 — PREPARE

Prebuilt route:
- Verify the extracted release contains DSAAccountability.exe,
  chrome-extension/, and README.txt. Do not require Python.

Source route:
- Run scripts/setup.ps1 (or perform its documented equivalent) to create the
  repository-local venv and install requirements.txt.
- Do not install unrelated packages globally.
- Run scripts/test.ps1. If a private learner repo exists outside the default,
  set DSA_ACCOUNTABILITY_PRODUCTION_REPO only for the test process so central
  guards protect it; never commit that path.
- Build with scripts/build.ps1 and verify the expected executable exists.

PHASE 3 — FIRST RUN

- Start the app from the chosen route.
- Guide me through First Run Setup. I must choose:
  * my Day 1 start date (verify Day 135 equals start + 134 days),
  * an existing learner Git repo or a new/empty local folder,
  * an optional GitHub origin URL,
  * automatic push on/off,
  * Windows startup on/off.
- Confirm Java, javac, Git, VS Code, repo, and startup checks shown by the app.
- If creating a learner repo, let the app/documented safe command initialize
  local Git. Do not add fake solutions or completions.
- GitHub is optional. If I choose it, prefer Git Credential Manager/browser
  authentication. Never ask me to paste a PAT into the application.

PHASE 4 — CHROME PAIRING (USER HANDOFF)

- Tell me to open chrome://extensions, enable Developer mode, choose Load
  unpacked, and select the release/source chrome-extension folder.
- Ask me to show/copy the token locally from First Run or Settings, paste it in
  the popup, and choose Save & Test Connection. Do not read or repeat the token.
- Verify the popup reports the desktop connected and pairing active.
- Refresh already-open LeetCode tabs after an extension reload.
- Do not regenerate the token for an ordinary connection failure. Check that
  the app is running, 127.0.0.1 is reachable, the extension is current, and the
  existing token was saved before considering regeneration.

PHASE 5 — SAFE ACCEPTANCE TESTS

- Verify localhost health/status using the app's documented authenticated path
  without exposing the token in terminal output or reports.
- Verify the database contains exactly 135 curriculum days using the selected
  start date and no completed work.
- Verify the configured learner repo path/name can differ from DSA-135.
- Test the local Java toolchain only in a disposable fixture repo/DB. Compile
  and run a fixture program; do not mark a real curriculum task complete.
- Confirm app restart preserves first-run state, date, repo, and pairing.
- Confirm Windows startup shortcut only if I enabled it. A reboot is optional
  unless I explicitly request full cold-start validation.
- A real LeetCode end-to-end test requires my own new Java submission and must
  use the app's disposable Live Integration Test Mode. Pause for me to write and
  submit; never provide or paste the solution. Verify cleanup afterward.

PHASE 6 — FINAL REPORT

Report, without secrets:
- installation route and application version,
- executable/source path,
- prerequisite readiness,
- selected start date and derived Day 135,
- learner repo path and whether local Git is ready,
- GitHub remote/auto-push state (not credentials),
- Chrome pairing status without the token,
- Windows startup state,
- tests run and pass/fail counts,
- backup created for any pre-existing data,
- any exact blocker or manual next step.

ACCEPTANCE CHECKLIST

[ ] No production data or real learner repo used by tests
[ ] No user file deleted/reset/overwritten
[ ] First Run saved the user's chosen start date
[ ] Exactly 135 consecutive curriculum dates
[ ] Configurable learner repo initialized/reused safely
[ ] Java and javac ready
[ ] Git ready; GitHub optional state explained
[ ] Chrome extension loaded and paired by the user
[ ] No pairing token exposed
[ ] Local disposable Java check passed
[ ] Startup state matches the user's choice
[ ] No fake completion, solution, submission, reflection, commit, or push
[ ] Final status report delivered

If any checklist item fails, diagnose it with the documented troubleshooting
tree, fix only what is in scope, retest, and continue. Stop only for an exact
blocker requiring my permission or UI/authentication action.
```
