# Changelog

All notable public changes are recorded here. Versions follow semantic
versioning.

## [1.1.1] — 2026-08-16

### Fixed

- Removed the "Practice Readiness" topic panel from the History dialog and
  progress export. It was honest, pre-existing analytics (not synthesized
  from day completion), but topic/mastery framing has no place in the
  strict day-by-day product regardless of how the numbers were computed.
- `SimpleCalculator`'s exercise validator accepted only one input ordering
  even though the scaffold comment never specified one; it now accepts
  both `number operator number` and `number number operator`.
- Pairing-token lookups now happen before first-run checks run, and both
  token creation and regeneration are recorded to the audit log.
- Revision task titles now include their spaced-repetition stage so
  repeated reviews of the same problem are distinguishable in the UI.

### Added

- `docs_sync_service`: deterministically regenerates the learner repo's
  PROGRESS.md/COMPLETED.md from live database state and commits them
  (only when content actually changed) after every real task completion,
  plus a `check_docs_in_sync()` consistency check. Previously these two
  files were not part of the automated pipeline at all, so they could only
  stay accurate if someone remembered to hand-edit them after the fact.
- Regression coverage for the canonical schedule anchor's full 135-day
  mapping, GitHub push retry/idempotency after a transient failure, and
  pairing-token stability across repeated lookups.

## [1.1.0] — 2026-08-15

### Added

- Per-user start date during First Run with Day 135 derived automatically.
- Configurable learner repository name/path and optional GitHub remote.
- Safe assisted setup, prerequisite, test, build, and release-packaging scripts.
- Complete manual, developer, security, and troubleshooting docs.
- Windows CI and public-portability checks.

### Improved

- Fresh, Submit-armed Java Accepted detection and persistent Chrome pairing.
- Test/runtime isolation and disposable live integration validation.
- Local-only Git workflow when GitHub is absent or auto-push is disabled.
- Durable GitHub retry/backoff and repository-bound queue safety.
- Embedded package version/commit/build identity and Windows startup reliability.

## [1.0.0] — internal verified baseline

- Initial 135-day desktop workflow, Java validation, LeetCode integration,
  progression, reflection, revision, Git/GitHub sync, backups, and packaging.
