# Developer guide

## Setup and layout

Follow [Build from source](BUILD_FROM_SOURCE.md). Domain logic belongs under
`app/services`; UI should orchestrate rather than duplicate repository,
schedule, or database rules.

## Non-negotiable test safety

**TESTS MUST NEVER TOUCH PRODUCTION DATA OR A REAL LEARNER REPOSITORY.**

Use the fixtures in `tests/conftest.py`. Never replace a temporary path with a
developer machine path, never weaken `runtime_env` guards, and never make a
network push from the ordinary suite. Add regression tests for every new
fallback or filesystem side effect.

## Migrations

Add a numbered SQL file under `app/migrations`. Migrations must be transactional
and idempotent through the migration ledger. The runner creates a SQLite-native
pre-migration backup and preserves it on failure.

## Curriculum changes

Edit `curriculum/build_schedule.py`, then regenerate schedule JSON and
curriculum Markdown with their scripts. Do not add solutions. Keep 135 ordered
days and update tests for filenames, task shape, fallback, and schedule
independence.

## Chrome development

Edit `chrome-extension`, run `node --test tests_js\*.test.js`, reload the
unpacked extension, then refresh open LeetCode tabs. Never automate a real user
submission. Manual end-to-end validation uses disposable integration mode.

## Release process

Run public-safety checks, full tests, clean-user/second-user simulations, build,
package, hash, and test the extracted ZIP. Update `CHANGELOG.md` and release
notes. Never publish AppData, logs, DBs, credentials, or internal forensic
reports.
