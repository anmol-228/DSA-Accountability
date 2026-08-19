# Data Model

SQLite under `%LOCALAPPDATA%\DSAAccountability-Development` (source) or
`%LOCALAPPDATA%\DSAAccountability` (packaged). Versioned migrations live in
`app/migrations/*.sql`, tracked in
`schema_migrations`. A backup is taken automatically before any migration
runs against an existing database (`database.backup_db`).

## Core tables

| Table | Purpose |
|---|---|
| `curriculum_days` | One row per day 1..135: `original_due_date`, `completed`, `completed_at`, `unlocked_at`. **`completed` is the only thing `progression_service` trusts.** |
| `tasks` | Individual required/optional items within a day: `task_type` (`learn`/`exercise`/`leetcode`/`revision`/`concept`/`repair`/`oa`/`mock`), `required`, `completed`, `generated` (1 = dynamically created, e.g. a spaced revision). |
| `problems` | LeetCode catalog entries referenced by tasks (`leetcode_number`, `slug`, `topic`, `pattern`, `premium`). |
| `task_problem_links` | Many-to-many for OA/mock tasks that bundle several problems. |
| `problem_sessions` | "I opened this problem to work on it" markers — the freshness anchor for Accepted validation. |
| `leetcode_events` | Every Accepted event received from the extension, with `is_fresh`, `event_hash` (dedup), and the raw payload. |
| `code_sync_events` | Outcome of writing captured code to disk (`captured`/`failed`/`manual`/`retry`). |
| `reflections` | The mandatory pattern/complexity/explanation/assistance/confidence write-up per solve. |
| `confidence_history` | Every Green/Yellow/Red rating over time, per problem. |
| `git_commits` / `github_push_queue` | Local commit records and their push status/retry history. |
| `revision_schedule` | Spaced-repetition due dates per problem (`interval_stage`, `status`: `pending`/`required_today`/`completed`/`deferred`). |
| `daily_activity` | One row per calendar date: `meaningful_activity` flag (drives the activity streak — opening the app doesn't count). |
| `study_sessions` / `oa_sessions` / `mock_sessions` | Timed session records. |
| `emergency_exits` / `audit_log` | Accountability trail: every emergency exit and every day-completed/day-unlocked/premium-fallback event. |
| `settings` | Key/value store: pairing token, learner repo path, selected start date/schedule version, reminder times, auto-push toggle, etc. |

## Why `curriculum_days.completed` is the only source of truth for "what day is it"

`progression_service.get_active_day()` always runs
`SELECT day_number FROM curriculum_days WHERE completed = 0 ORDER BY day_number LIMIT 1`
rather than reading a cached "current day" integer anywhere. Every other
piece of state (streaks, revisions, reminders) is derived *from* that
query, never the other way around. See `app/services/progression_service.py`.

## Practice Readiness formula (not currently surfaced in the UI)

`analytics_service.topic_readiness()` computes, on demand and not stored,
per topic: completion rate x independent-solve ratio x confidence
distribution (Green weighted highest) x revision performance x recency
decay. The function is real and unit-tested, but as of 1.1.1 it is not
called from the History dialog or the progress export -- topic/mastery
framing doesn't fit a strict day-by-day product regardless of how honestly
the number is computed. Kept in case a future surface needs it.
