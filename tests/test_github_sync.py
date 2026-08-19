from app.services import git_service, github_sync_service


def _init_committed_repo(repo_root):
    git_service.ensure_repo(repo_root)
    f = repo_root / "README.md"
    f.write_text("hello", encoding="utf-8")
    result = git_service.safe_commit(repo_root, [f], "initial commit")
    assert result.success
    return result


def test_push_with_no_remote_is_config_error(seeded_conn, tmp_path):
    conn = seeded_conn
    repo_root = tmp_path / "repo"
    commit = _init_committed_repo(repo_root)
    cur = conn.execute(
        "INSERT INTO git_commits (repo_path, commit_hash, message, files_json, created_at) "
        "VALUES (?, ?, ?, '[]', datetime('now'))",
        (str(repo_root), commit.commit_hash, "initial commit"),
    )
    conn.commit()
    queue_id = github_sync_service.enqueue_push(conn, cur.lastrowid)
    success = github_sync_service.attempt_push(conn, queue_id, repo_root)
    assert success is False
    row = conn.execute("SELECT * FROM github_push_queue WHERE id = ?", (queue_id,)).fetchone()
    assert row["status"] == "failed_config"


def test_push_to_unreachable_remote_stays_pending_for_retry(seeded_conn, tmp_path):
    """An unreachable-but-configured remote (network-style failure) must
    stay 'pending' so it retries later, rather than being flagged as a
    broken config (spec section 26-27: network failure queues, never
    erases real progress)."""
    conn = seeded_conn
    repo_root = tmp_path / "repo"
    commit = _init_committed_repo(repo_root)
    git_service.add_remote(repo_root, "https://127.0.0.1:1/definitely-not-a-real-host/repo.git")

    cur = conn.execute(
        "INSERT INTO git_commits (repo_path, commit_hash, message, files_json, created_at) "
        "VALUES (?, ?, ?, '[]', datetime('now'))",
        (str(repo_root), commit.commit_hash, "initial commit"),
    )
    conn.commit()
    queue_id = github_sync_service.enqueue_push(conn, cur.lastrowid)
    success = github_sync_service.attempt_push(conn, queue_id, repo_root)
    assert success is False
    row = conn.execute("SELECT * FROM github_push_queue WHERE id = ?", (queue_id,)).fetchone()
    assert row["status"] == "pending"
    assert row["attempts"] == 1


def test_retry_does_not_create_duplicate_commit(seeded_conn, tmp_path):
    conn = seeded_conn
    repo_root = tmp_path / "repo"
    commit = _init_committed_repo(repo_root)
    cur = conn.execute(
        "INSERT INTO git_commits (repo_path, commit_hash, message, files_json, created_at) "
        "VALUES (?, ?, ?, '[]', datetime('now'))",
        (str(repo_root), commit.commit_hash, "initial commit"),
    )
    conn.commit()
    queue_id = github_sync_service.enqueue_push(conn, cur.lastrowid)
    github_sync_service.attempt_push(conn, queue_id, repo_root)
    github_sync_service.attempt_push(conn, queue_id, repo_root)  # retry
    commit_count = conn.execute("SELECT COUNT(*) c FROM git_commits").fetchone()["c"]
    assert commit_count == 1


def test_real_push_then_transient_failure_then_restart_retry_succeeds_no_duplicate(seeded_conn, tmp_path):
    """Real (non-mocked) end-to-end proof, using a local bare repo as the
    remote so this never touches network/GitHub: a genuine `git push`
    actually lands the commit on the remote, a transient failure (remote
    briefly misconfigured) correctly stays queued rather than being
    dropped, and a fresh attempt_push call afterward -- exactly what
    happens on the next app launch/timer tick, not a special "retry" code
    path -- succeeds and pushes the SAME commit exactly once, never
    duplicating it."""
    conn = seeded_conn
    repo_root = tmp_path / "repo"
    commit = _init_committed_repo(repo_root)

    bare_remote = tmp_path / "bare-remote.git"
    git_service._run(["init", "--bare", str(bare_remote)], cwd=tmp_path)

    cur = conn.execute(
        "INSERT INTO git_commits (repo_path, commit_hash, message, files_json, created_at) "
        "VALUES (?, ?, ?, '[]', datetime('now'))",
        (str(repo_root), commit.commit_hash, "initial commit"),
    )
    conn.commit()
    queue_id = github_sync_service.enqueue_push(conn, cur.lastrowid)

    # Transient failure: remote briefly points nowhere reachable.
    git_service.add_remote(repo_root, "https://127.0.0.1:1/definitely-not-a-real-host/repo.git")
    assert github_sync_service.attempt_push(conn, queue_id, repo_root) is False
    row = conn.execute("SELECT status, attempts FROM github_push_queue WHERE id = ?", (queue_id,)).fetchone()
    assert row["status"] == "pending"
    assert row["attempts"] == 1

    # "Restart": remote is fixed (as if the user reconnected/reconfigured),
    # and the next drain call is a fresh, independent attempt_push call --
    # not a special retry function, the same one every periodic drain uses.
    git_service._run(["remote", "set-url", "origin", str(bare_remote)], cwd=repo_root)
    assert github_sync_service.attempt_push(conn, queue_id, repo_root) is True

    row = conn.execute("SELECT status, attempts FROM github_push_queue WHERE id = ?", (queue_id,)).fetchone()
    assert row["status"] == "pushed"
    assert row["attempts"] == 2  # one failed + one succeeded, both recorded

    # The bare "remote" genuinely has the commit -- not just a local status flag.
    remote_log = git_service._run(["log", "--oneline", "main"], cwd=bare_remote)
    assert commit.commit_hash[:7] in remote_log.stdout

    # A further drain call (e.g. the next periodic timer tick) must be a
    # true no-op: already 'pushed', never re-pushed, never duplicated.
    assert github_sync_service.attempt_push(conn, queue_id, repo_root) is True
    row = conn.execute("SELECT status, attempts FROM github_push_queue WHERE id = ?", (queue_id,)).fetchone()
    assert row["attempts"] == 2  # unchanged -- the already-pushed short-circuit never re-attempts
    remote_log_after = git_service._run(["log", "--oneline", "main"], cwd=bare_remote)
    assert remote_log_after.stdout == remote_log.stdout  # no duplicate commit on the remote either


def test_queue_refuses_to_push_through_a_different_repo(seeded_conn, tmp_path):
    conn = seeded_conn
    recorded_repo = tmp_path / "recorded"
    wrong_repo = tmp_path / "wrong"
    commit = _init_committed_repo(recorded_repo)
    _init_committed_repo(wrong_repo)
    cur = conn.execute(
        "INSERT INTO git_commits (repo_path, commit_hash, message, files_json, created_at) "
        "VALUES (?, ?, ?, '[]', datetime('now'))",
        (str(recorded_repo), commit.commit_hash, "initial commit"),
    )
    conn.commit()
    queue_id = github_sync_service.enqueue_push(conn, cur.lastrowid)
    assert github_sync_service.attempt_push(conn, queue_id, wrong_repo) is False
    row = conn.execute("SELECT status, last_error FROM github_push_queue WHERE id=?", (queue_id,)).fetchone()
    assert row["status"] == "failed_config"
    assert "queue repo mismatch" in row["last_error"]
