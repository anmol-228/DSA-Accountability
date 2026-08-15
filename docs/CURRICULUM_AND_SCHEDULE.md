# Curriculum and schedule

The bundled reference curriculum defines 135 ordered days of topics and tasks.
It contains day numbers, Java exercises, free-tier LeetCode references,
revisions, OA/mock metadata, and Core CS topics. It contains no learner dates or
solutions.

Each installation stores its chosen start date in SQLite. For curriculum day
`N`:

```text
due date = selected start date + (N - 1) calendar days
Day 135 = selected start date + 134 days
```

Examples verified by automated tests:

| Day 1 | Day 135 |
|---|---|
| 2026-08-15 | 2026-12-27 |
| 2027-01-01 | 2027-05-15 |
| 2027-06-15 | 2027-10-27 |

Calendar time never chooses the active day. If Day 1 is due Monday and remains
incomplete on Tuesday, Day 1 is still active and delay is one day. After Day 1
is completed, Day 2 unlocks.

Curriculum source files are `curriculum/build_schedule.py` and generated
`curriculum/schedule.json`. Developers should modify the source, regenerate the
JSON/Markdown, and run the full test suite.
