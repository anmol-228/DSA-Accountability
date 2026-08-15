-- Initial schema for DSA Accountability
-- Migration 001

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS curriculum_days (
    day_number       INTEGER PRIMARY KEY,
    title            TEXT NOT NULL,
    topic            TEXT NOT NULL,
    original_due_date TEXT NOT NULL,
    completed        INTEGER NOT NULL DEFAULT 0,
    completed_at     TEXT,
    unlocked_at      TEXT,
    is_oa_day        INTEGER NOT NULL DEFAULT 0,
    is_mock_day      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS problems (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    leetcode_number INTEGER,
    slug            TEXT,
    title           TEXT NOT NULL,
    topic           TEXT,
    pattern         TEXT,
    difficulty      TEXT,
    premium         INTEGER NOT NULL DEFAULT 0,
    url             TEXT,
    UNIQUE(leetcode_number)
);

CREATE TABLE IF NOT EXISTS tasks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    day_number    INTEGER NOT NULL REFERENCES curriculum_days(day_number),
    task_type     TEXT NOT NULL CHECK (task_type IN
                      ('learn','exercise','leetcode','revision','concept','oa','mock','repair')),
    title         TEXT NOT NULL,
    description   TEXT,
    problem_id    INTEGER REFERENCES problems(id),
    required      INTEGER NOT NULL DEFAULT 1,
    completed     INTEGER NOT NULL DEFAULT 0,
    completed_at  TEXT,
    generated     INTEGER NOT NULL DEFAULT 0,
    original_problem_id INTEGER REFERENCES problems(id),
    premium_blocked_note TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_day ON tasks(day_number);

CREATE TABLE IF NOT EXISTS problem_sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_id   INTEGER NOT NULL REFERENCES problems(id),
    task_id      INTEGER REFERENCES tasks(id),
    day_number   INTEGER,
    session_type TEXT NOT NULL DEFAULT 'solve' CHECK (session_type IN ('solve','revision','oa','mock')),
    started_at   TEXT NOT NULL,
    ended_at     TEXT
);

CREATE TABLE IF NOT EXISTS leetcode_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    slug            TEXT NOT NULL,
    problem_number  INTEGER,
    language        TEXT,
    event_type      TEXT NOT NULL DEFAULT 'accepted',
    event_ts        TEXT NOT NULL,
    source          TEXT,
    session_id      INTEGER REFERENCES problem_sessions(id),
    event_hash      TEXT UNIQUE,
    raw_payload     TEXT,
    is_fresh        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS code_sync_events (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    leetcode_event_id INTEGER REFERENCES leetcode_events(id),
    file_path        TEXT,
    status           TEXT NOT NULL CHECK (status IN ('captured','failed','manual','retry')),
    error            TEXT,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attempts (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_id        INTEGER NOT NULL REFERENCES problems(id),
    task_id           INTEGER REFERENCES tasks(id),
    day_number        INTEGER,
    language          TEXT,
    result            TEXT,
    assistance_level  TEXT CHECK (assistance_level IN ('independent','small_hint','significant_hint','studied_solution')),
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reflections (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id           INTEGER REFERENCES tasks(id),
    problem_id        INTEGER REFERENCES problems(id),
    pattern           TEXT,
    time_complexity   TEXT,
    space_complexity  TEXT,
    explanation       TEXT NOT NULL,
    assistance_level  TEXT NOT NULL CHECK (assistance_level IN ('independent','small_hint','significant_hint','studied_solution')),
    confidence        TEXT NOT NULL CHECK (confidence IN ('green','yellow','red')),
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS confidence_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_id  INTEGER NOT NULL REFERENCES problems(id),
    confidence  TEXT NOT NULL CHECK (confidence IN ('green','yellow','red')),
    source      TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS git_commits (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_path    TEXT NOT NULL,
    commit_hash  TEXT,
    message      TEXT NOT NULL,
    files_json   TEXT NOT NULL,
    task_id      INTEGER REFERENCES tasks(id),
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS github_push_queue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    commit_id       INTEGER NOT NULL REFERENCES git_commits(id),
    status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','pushed','failed_config')),
    attempts        INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TEXT,
    last_error      TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS revision_schedule (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    problem_id            INTEGER NOT NULL REFERENCES problems(id),
    due_date              TEXT NOT NULL,
    interval_stage        INTEGER NOT NULL DEFAULT 0,
    confidence_at_schedule TEXT,
    status                TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','required_today','completed','deferred')),
    generated_for_day     INTEGER,
    task_id               INTEGER REFERENCES tasks(id),
    completed_at          TEXT,
    created_at            TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_revision_due ON revision_schedule(due_date, status);

CREATE TABLE IF NOT EXISTS daily_activity (
    activity_date            TEXT PRIMARY KEY,
    meaningful_activity      INTEGER NOT NULL DEFAULT 0,
    study_minutes            INTEGER NOT NULL DEFAULT 0,
    curriculum_days_worked   TEXT,
    curriculum_days_completed TEXT,
    commits                  INTEGER NOT NULL DEFAULT 0,
    pushes                   INTEGER NOT NULL DEFAULT 0,
    emergency_exit           INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS study_sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id      INTEGER REFERENCES tasks(id),
    problem_id   INTEGER REFERENCES problems(id),
    started_at   TEXT NOT NULL,
    ended_at     TEXT,
    duration_seconds INTEGER
);

CREATE TABLE IF NOT EXISTS oa_sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    day_number   INTEGER NOT NULL,
    started_at   TEXT NOT NULL,
    ended_at     TEXT,
    duration_seconds INTEGER,
    problems_json TEXT,
    results_json  TEXT
);

CREATE TABLE IF NOT EXISTS mock_sessions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    day_number   INTEGER NOT NULL,
    started_at   TEXT NOT NULL,
    ended_at     TEXT,
    notes        TEXT
);

CREATE TABLE IF NOT EXISTS reminders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scheduled_time  TEXT NOT NULL,
    fired_at        TEXT,
    snoozed_until   TEXT,
    day_number      INTEGER,
    message         TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL,
    actor      TEXT NOT NULL DEFAULT 'system',
    action     TEXT NOT NULL,
    details    TEXT
);

CREATE TABLE IF NOT EXISTS emergency_exits (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,
    day_number   INTEGER,
    remaining_tasks INTEGER,
    reason       TEXT
);

CREATE TABLE IF NOT EXISTS task_problem_links (
    task_id    INTEGER NOT NULL REFERENCES tasks(id),
    problem_id INTEGER NOT NULL REFERENCES problems(id),
    PRIMARY KEY (task_id, problem_id)
);
