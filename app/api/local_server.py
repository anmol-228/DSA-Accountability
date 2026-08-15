"""Localhost-only HTTP API for the Chrome extension.

Binds ONLY to 127.0.0.1, never 0.0.0.0. Every endpoint except /api/health
requires a valid X-DSA-Token header (spec section 32). No LAN exposure, no
cloud backend.
"""
from __future__ import annotations

import json
import logging
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from app import config, database
from app.services import (
    code_sync_service,
    curriculum_service,
    integration_test_service,
    leetcode_service,
    pairing_service,
    progression_service as prog,
    streak_service,
)

logger = logging.getLogger("dsa.local_api")


class _NullHandler(socketserver.BaseRequestHandler):
    def handle(self):
        pass


def find_free_port() -> int:
    for port in config.LOCAL_API_PORT_RANGE:
        try:
            with socketserver.TCPServer((config.LOCAL_API_HOST, port), _NullHandler):
                return port
        except OSError:
            continue
    raise RuntimeError("No free port found in configured range")


class _Handler(BaseHTTPRequestHandler):
    server_version = "DSAAccountabilityAPI/1.0"

    def log_message(self, fmt, *args):  # quiet default stderr logging -> our logger
        logger.info("%s - %s", self.address_string(), fmt % args)

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-DSA-Token")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8")) if raw else {}

    def _authorized(self, conn) -> bool:
        token = self.headers.get("X-DSA-Token")
        valid = pairing_service.is_valid(conn, token)
        if not valid:
            import hashlib
            presented_fp = hashlib.sha256(token.encode()).hexdigest()[:8] if token else None
            expected = pairing_service.get_or_create_token(conn)
            expected_fp = hashlib.sha256(expected.encode()).hexdigest()[:8]
            logger.warning(
                "auth rejected: presented_fp=%s expected_fp=%s presented_len=%s expected_len=%s db_path=%s",
                presented_fp, expected_fp,
                len(token) if token else 0, len(expected), config.DB_PATH,
            )
        return valid

    def do_OPTIONS(self):
        self._send_json(200, {"ok": True})

    def do_GET(self):
        path = urlparse(self.path).path
        conn = database.get_connection()
        try:
            if path == "/api/health":
                self._send_json(200, {"status": "ok"})
                return
            if not self._authorized(conn):
                self._send_json(401, {"error": "invalid_or_missing_token"})
                return
            if path == "/api/status":
                self._handle_status(conn)
            elif path == "/api/curriculum/current":
                self._handle_current_curriculum(conn)
            else:
                self._send_json(404, {"error": "not_found"})
        except Exception as exc:  # noqa: BLE001 - surface as JSON, never crash the server
            logger.exception("GET %s failed", path)
            self._send_json(500, {"error": str(exc)})
        finally:
            conn.close()

    def do_POST(self):
        path = urlparse(self.path).path
        conn = database.get_connection()
        try:
            if not self._authorized(conn):
                self._send_json(401, {"error": "invalid_or_missing_token"})
                return
            body = self._read_json_body()
            if path == "/api/leetcode/accepted":
                self._handle_accepted(conn, body)
            elif path == "/api/leetcode/premium_blocked":
                self._handle_premium_blocked(conn, body)
            elif path == "/api/session/start":
                self._handle_session_start(conn, body)
            else:
                self._send_json(404, {"error": "not_found"})
        except Exception as exc:  # noqa: BLE001
            logger.exception("POST %s failed", path)
            self._send_json(500, {"error": str(exc)})
        finally:
            conn.close()

    # --- route implementations ------------------------------------------------

    def _handle_status(self, conn) -> None:
        status = prog.get_status(conn)
        payload = {
            "active_day": status.active_day,
            "post_plan_mode": status.post_plan_mode,
            "schedule_delay_days": status.schedule_delay_days,
            "projected_finish": status.projected_finish.isoformat(),
            "activity_streak": streak_service.current_activity_streak(conn),
        }
        self._send_json(200, payload)

    def _handle_current_curriculum(self, conn) -> None:
        active = prog.get_active_day(conn)
        if active is None:
            self._send_json(200, {"post_plan_mode": True})
            return
        day = curriculum_service.get_day(conn, active)
        tasks = curriculum_service.get_tasks_for_day(conn, active)
        leetcode_tasks = []
        for t in tasks:
            if t["task_type"] in ("leetcode", "revision") and not t["completed"] and t["problem_id"]:
                p = conn.execute("SELECT * FROM problems WHERE id = ?", (t["problem_id"],)).fetchone()
                leetcode_tasks.append({
                    "task_id": t["id"], "task_type": t["task_type"],
                    "leetcode_number": p["leetcode_number"], "title": p["title"], "slug": p["slug"],
                })
        self._send_json(200, {
            "day": active, "title": day["title"], "topic": day["topic"],
            "pending_leetcode_tasks": leetcode_tasks,
        })

    def _handle_session_start(self, conn, body: dict) -> None:
        """Canonical contract (matches the real extension payload — see
        chrome-extension/content-script.js::notifyPageOpened and
        service-worker.js::forwardSessionStart, POST {"slug": "..."}):
        `slug` is the primary key, matched against problems.slug for the
        active day's pending required task. `leetcode_number` is accepted
        too (checked as a fallback) for robustness / future callers, but
        the real extension only ever sends `slug` today.

        Previously this read body.get("leetcode_number"), which the real
        extension never sends, so every real browser session-start request
        silently no-opped — no problem_sessions row was ever created for
        genuine LeetCode use, so the freshness gate in
        leetcode_service.handle_accepted_event always rejected real
        Accepted events as stale. Confirmed against the real production
        DB: 3 real Accepted events for LC1 Two Sum, all is_fresh=0,
        session_id=NULL. See docs/PRODUCTION_STABILIZATION_2026-08-12.md.
        """
        slug = body.get("slug")
        leetcode_number = body.get("leetcode_number")
        active = prog.get_active_day(conn)
        if active is None or (slug is None and leetcode_number is None):
            self._send_json(200, {"matched": False})
            return

        task = None
        if slug is not None:
            task = conn.execute(
                "SELECT t.* FROM tasks t JOIN problems p ON t.problem_id = p.id "
                "WHERE t.day_number = ? AND p.slug = ? AND t.required = 1",
                (active, slug),
            ).fetchone()
        if task is None and leetcode_number is not None:
            task = conn.execute(
                "SELECT t.* FROM tasks t JOIN problems p ON t.problem_id = p.id "
                "WHERE t.day_number = ? AND p.leetcode_number = ? AND t.required = 1",
                (active, leetcode_number),
            ).fetchone()
        if task is None:
            # Not today's scheduled task. Before giving up, check whether
            # this exact slug is the one, explicit problem armed via
            # "Run Live LeetCode Integration Test" (production
            # stabilization pass, section 9-13) -- a diagnostic-only path
            # that creates a real session but never touches curriculum
            # completion. Anything else is genuinely unrelated and gets no
            # session, exactly as before.
            if slug is not None and integration_test_service.is_active_for_slug(conn, slug):
                test_status = integration_test_service.status(conn)
                problem_id = integration_test_service.get_or_create_test_problem(
                    conn, test_status["leetcode_number"], slug, test_status["title"]
                )
                session_id = leetcode_service.start_or_reuse_session(conn, problem_id, None, None, "solve")
                integration_test_service.record_session(conn, session_id)
                self._send_json(200, {"matched": True, "test_mode": True, "session_id": session_id})
                return
            # Genuinely unrelated/not-yet-scheduled problem page — never
            # creates a session for it (anti-gaming: only today's actual
            # required task, or an explicitly armed test-mode problem,
            # can start a session).
            self._send_json(200, {"matched": False})
            return

        session_id = leetcode_service.start_or_reuse_session(
            conn, task["problem_id"], task["id"], active,
            "solve" if task["task_type"] == "leetcode" else "revision",
        )
        self._send_json(200, {"matched": True, "task_id": task["id"], "session_id": session_id})

    def _handle_accepted(self, conn, body: dict) -> None:
        result = leetcode_service.handle_accepted_event(conn, body)
        response = {
            "status": result.status, "message": result.message, "event_id": result.event_id,
            "task_id": result.task_id,
        }

        if result.status == "ok":
            code = body.get("code")
            is_test_mode = integration_test_service.is_active_session(conn, result.session_id)
            response["test_mode"] = is_test_mode
            active = prog.get_active_day(conn)

            if code and is_test_mode:
                repo_root = integration_test_service.repo_path(conn)
                # Isolated non-curriculum archive path -- never a real
                # Week-*/Day-*/leetcode/ folder, never counted toward
                # curriculum progress (production stabilization pass,
                # section 9-13).
                problem = conn.execute("SELECT * FROM problems WHERE id = ?", (result.problem_id,)).fetchone()
                file_name = f"LC{problem['leetcode_number']:04d}_{problem['title'].replace(' ', '')}.java"
                target = integration_test_service.test_archive_path(repo_root, file_name)
                written_path, backup_path = code_sync_service.write_solution(target, code)
                conn.execute(
                    "INSERT INTO code_sync_events (leetcode_event_id, file_path, status, created_at) "
                    "VALUES (?, ?, 'captured', ?)",
                    (result.event_id, str(written_path), config.now_local().isoformat()),
                )
                conn.commit()
                response["code_captured"] = True
                response["file_path"] = str(written_path)
                if backup_path:
                    response["previous_version_backed_up_to"] = str(backup_path)
            elif code and active is not None and result.day_number == active:
                repo_root = _get_dsa135_repo(conn)
                problem = conn.execute("SELECT * FROM problems WHERE id = ?", (result.problem_id,)).fetchone()
                target = code_sync_service.leetcode_file_path(
                    repo_root, active, problem["leetcode_number"], problem["title"]
                )
                written_path, backup_path = code_sync_service.write_solution(target, code)
                conn.execute(
                    "INSERT INTO code_sync_events (leetcode_event_id, file_path, status, created_at) "
                    "VALUES (?, ?, 'captured', ?)",
                    (result.event_id, str(written_path), config.now_local().isoformat()),
                )
                conn.commit()
                response["code_captured"] = True
                response["file_path"] = str(written_path)
                if backup_path:
                    response["previous_version_backed_up_to"] = str(backup_path)
            else:
                conn.execute(
                    "INSERT INTO code_sync_events (leetcode_event_id, file_path, status, error, created_at) "
                    "VALUES (?, NULL, 'failed', 'no code payload received', ?)",
                    (result.event_id, config.now_local().isoformat()),
                )
                conn.commit()
                response["code_captured"] = False

            _notify_ui_state_changed()

        self._send_json(200, response)

    def _handle_premium_blocked(self, conn, body: dict) -> None:
        task_id = body.get("task_id")
        if task_id is None:
            self._send_json(400, {"error": "task_id required"})
            return
        task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if task is None:
            self._send_json(404, {"error": "task not found"})
            return
        day = curriculum_service.get_day(conn, task["day_number"])
        replacement = leetcode_service.apply_premium_fallback(conn, task_id, day["topic"])
        if replacement is None:
            self._send_json(200, {"replaced": False, "message": "No free replacement available in this topic."})
        else:
            _notify_ui_state_changed()
            self._send_json(200, {"replaced": True, "replacement": replacement})


def _notify_ui_state_changed() -> None:
    """Best-effort nudge so the desktop overlay polls immediately instead
    of waiting up to 4s for its next timer tick. Never allowed to break
    the API response — if the UI isn't running (e.g. under test, or the
    API used standalone), this silently no-ops."""
    try:
        from app.ui.events import bus
        bus.state_changed.emit()
    except Exception:  # noqa: BLE001
        pass


def _get_dsa135_repo(conn):
    # Delegates to the single canonical resolver -- this used to duplicate
    # the lookup independently (a plain settings read with no recovery
    # fallback), which could silently disagree with pipeline_service's
    # version. See pipeline_service.get_dsa135_repo for the resolution
    # order and why it can recover a valid repo even when the persisted
    # setting/default path is wrong.
    from app.services import pipeline_service
    return pipeline_service.get_dsa135_repo(conn)


class LocalAPIServer:
    def __init__(self, host: str | None = None, port: int | None = None):
        self.host = host or config.LOCAL_API_HOST
        self.port = port or find_free_port()
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._httpd = ThreadingHTTPServer((self.host, self.port), _Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        logger.info("Local API listening on http://%s:%s", self.host, self.port)

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    database.init_db()
    conn = database.get_connection()
    curriculum_service.seed_curriculum(conn)
    token = pairing_service.get_or_create_token(conn)
    conn.close()
    server = LocalAPIServer()
    server.start()
    print(f"Pairing token: {token}")
    print(f"Listening on http://{server.host}:{server.port}")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        server.stop()
