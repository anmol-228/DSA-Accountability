"""Regression tests for the VS Code-based local exercise workflow (spec:
"the DSA Accountability app must not be a code editor"). Covers canonical
filenames, skeleton rejection, real javac/java compile+test execution,
timeout safety, and the full file-watcher-driven ExerciseTaskDialog path
against a disposable test repo/DB. Never touches the real DSA-135 repo or
the real progress database.
"""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from app.services import build_service, code_sync_service, exercise_tests, vscode_service


# --- canonical filenames -----------------------------------------------------

def test_maximum_of_three_uses_spelled_out_filename(seeded_conn):
    row = seeded_conn.execute(
        "SELECT canonical_filename FROM tasks WHERE day_number = 1 AND task_type = 'exercise' "
        "AND title = 'Maximum of 3'"
    ).fetchone()
    assert row["canonical_filename"] == "MaximumOfThree"  # not the naive "MaximumOf3"


def test_all_day1_exercises_have_canonical_filenames(seeded_conn):
    rows = seeded_conn.execute(
        "SELECT title, canonical_filename FROM tasks WHERE day_number = 1 AND task_type = 'exercise'"
    ).fetchall()
    assert len(rows) == 4
    for r in rows:
        assert r["canonical_filename"], f"{r['title']} has no canonical filename"


def test_backfill_populates_existing_null_rows(seeded_conn):
    seeded_conn.execute(
        "UPDATE tasks SET canonical_filename = NULL WHERE day_number = 1 AND task_type = 'exercise'"
    )
    seeded_conn.commit()
    from app.services import curriculum_service
    updated = curriculum_service.backfill_canonical_filenames(seeded_conn)
    assert updated == 4
    row = seeded_conn.execute(
        "SELECT canonical_filename FROM tasks WHERE day_number = 1 AND title = 'Maximum of 3'"
    ).fetchone()
    assert row["canonical_filename"] == "MaximumOfThree"


def test_exercise_file_path_uses_explicit_filename_not_title(tmp_path):
    path = code_sync_service.exercise_file_path(tmp_path, 1, "MaximumOfThree")
    assert path.name == "MaximumOfThree.java"
    assert path.parent.name == "exercises"
    assert path.parent.parent.name == "Day-001"


# --- skeleton handling ----------------------------------------------------------

def test_skeleton_created_matches_class_name(tmp_path):
    target = tmp_path / "Foo.java"
    created = code_sync_service.write_exercise_skeleton_if_missing(target, "Foo")
    assert created is True
    text = target.read_text()
    assert "public class Foo" in text
    assert "Write your solution" in text


def test_skeleton_not_overwritten_if_file_exists(tmp_path):
    target = tmp_path / "Foo.java"
    target.write_text("public class Foo { /* my real work */ public static void main(String[] a){int x=1;} }")
    created = code_sync_service.write_exercise_skeleton_if_missing(target, "Foo")
    assert created is False
    assert "my real work" in target.read_text()


def test_is_skeleton_detects_empty_main():
    skeleton = "public class X {\n public static void main(String[] a) {\n // Write your solution here.\n }\n}"
    assert build_service.is_skeleton_or_empty(skeleton) is True


def test_is_skeleton_rejects_comment_only_edits():
    still_skeleton = "public class X {\n public static void main(String[] a) {\n // I will do this later\n }\n}"
    assert build_service.is_skeleton_or_empty(still_skeleton) is True


def test_is_skeleton_false_for_real_code():
    real = "public class X {\n public static void main(String[] a) {\n int x = 5;\n System.out.println(x);\n }\n}"
    assert build_service.is_skeleton_or_empty(real) is False


# --- javac / java (REAL subprocess execution, no mocking) --------------------------

@pytest.fixture()
def isolated_build_root(tmp_path, monkeypatch):
    monkeypatch.setattr(build_service, "BUILD_ROOT", tmp_path / "build-temp")
    return tmp_path


def test_real_compile_and_run_pass(tmp_path, isolated_build_root):
    src = tmp_path / "Doubler.java"
    src.write_text(
        "import java.util.Scanner;\n"
        "public class Doubler {\n"
        "    public static void main(String[] a) {\n"
        "        Scanner sc = new Scanner(System.in);\n"
        "        System.out.println(sc.nextInt() * 2);\n"
        "    }\n"
        "}\n"
    )
    result = build_service.compile_java(src, "Doubler")
    assert result.success, result.summary
    run = build_service.run_java_class("Doubler", result.build_dir, "21\n")
    assert run.ok
    assert run.stdout.strip() == "42"


def test_real_compile_failure_gives_concise_summary(tmp_path, isolated_build_root):
    src = tmp_path / "Broken.java"
    src.write_text("public class Broken {\n public static void main(String[] a) {\n int x = \n }\n}")
    result = build_service.compile_java(src, "Broken")
    assert result.success is False
    assert "Line" in result.summary  # concise "Line N: message", not a raw dump


def test_real_hung_program_times_out_without_freezing(tmp_path, isolated_build_root):
    src = tmp_path / "Hangs.java"
    src.write_text(
        "public class Hangs {\n"
        "    public static void main(String[] a) throws Exception {\n"
        "        Thread.sleep(20000);\n"
        "    }\n"
        "}\n"
    )
    result = build_service.compile_java(src, "Hangs")
    assert result.success
    started = time.time()
    run = build_service.run_java_class("Hangs", result.build_dir, timeout=2)
    elapsed = time.time() - started
    assert run.timed_out is True
    assert elapsed < 10  # proves the process was actually killed, not left to finish


# --- Day 1 functional test specs, verified against REAL correct solutions ------------

_CORRECT_SOLUTIONS = {
    "EvenOdd": """
        import java.util.Scanner;
        public class EvenOdd {
            public static void main(String[] a) {
                int n = new Scanner(System.in).nextInt();
                System.out.println(n % 2 == 0 ? "Even" : "Odd");
            }
        }
    """,
    "MaximumOfThree": """
        import java.util.Scanner;
        public class MaximumOfThree {
            public static void main(String[] a) {
                Scanner sc = new Scanner(System.in);
                int x = sc.nextInt(), y = sc.nextInt(), z = sc.nextInt();
                System.out.println("Maximum: " + Math.max(x, Math.max(y, z)));
            }
        }
    """,
    "LeapYear": """
        import java.util.Scanner;
        public class LeapYear {
            public static void main(String[] a) {
                int year = new Scanner(System.in).nextInt();
                boolean leap = (year % 4 == 0 && year % 100 != 0) || (year % 400 == 0);
                System.out.println(leap ? "Leap Year" : "Not a Leap Year");
            }
        }
    """,
    "SimpleCalculator": """
        import java.util.Scanner;
        public class SimpleCalculator {
            public static void main(String[] a) {
                Scanner sc = new Scanner(System.in);
                double x = sc.nextDouble();
                String op = sc.next();
                double y = sc.nextDouble();
                double r = switch (op) { case "+" -> x+y; case "-" -> x-y; case "*" -> x*y; default -> x/y; };
                System.out.println("Result: " + r);
            }
        }
    """,
}


@pytest.mark.parametrize("class_name", list(_CORRECT_SOLUTIONS.keys()))
def test_real_correct_solution_passes_all_functional_tests(class_name, tmp_path, isolated_build_root):
    src = tmp_path / f"{class_name}.java"
    src.write_text(_CORRECT_SOLUTIONS[class_name])
    result = build_service.compile_java(src, class_name)
    assert result.success, result.summary
    suite = exercise_tests.run_functional_tests(class_name, class_name, result.build_dir)
    assert suite.defined
    assert suite.all_passed, [r for r in suite.results if not r.passed]


def test_leap_year_century_rule_actually_verified(tmp_path, isolated_build_root):
    """Regression guard for the specific case the spec calls out: a
    solution missing the century exception must fail on 1900."""
    src = tmp_path / "LeapYearBuggy.java"
    src.write_text(
        "import java.util.Scanner;\n"
        "public class LeapYearBuggy {\n"
        "    public static void main(String[] a) {\n"
        "        int year = new Scanner(System.in).nextInt();\n"
        "        boolean leap = (year % 4 == 0);\n"  # missing % 100 / % 400 handling
        "        System.out.println(leap ? \"Leap Year\" : \"Not a Leap Year\");\n"
        "    }\n"
        "}\n"
    )
    result = build_service.compile_java(src, "LeapYearBuggy")
    assert result.success
    suite = exercise_tests.run_functional_tests("LeapYear", "LeapYearBuggy", result.build_dir)
    assert suite.passed == 3  # 2024, 2023, 2000 pass; 1900 must fail
    failed_descriptions = [r.description for r in suite.results if not r.passed]
    assert any("1900" in d for d in failed_descriptions)


# --- VS Code detection (real, no mocking) -----------------------------------------

def test_vscode_detection_is_deterministic():
    first = vscode_service.find_vscode_executable()
    second = vscode_service.find_vscode_executable()
    assert first == second


def test_vscode_launch_uses_no_shell_interpolation(monkeypatch, tmp_path):
    """Ensures the launcher never goes through shell=True / string
    interpolation -- always a safe argument list."""
    captured = {}

    def fake_popen(args, shell=False, **kwargs):
        captured["args"] = args
        captured["shell"] = shell
        class _P:
            pass
        return _P()

    monkeypatch.setattr(vscode_service.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(vscode_service, "find_vscode_executable", lambda use_cache=True: "C:/fake/Code.exe")

    ok, _msg = vscode_service.open_file_in_vscode(tmp_path / "Foo.java", tmp_path)
    assert ok
    assert captured["shell"] is False
    assert isinstance(captured["args"], list)
    assert "-g" in captured["args"]


# --- full dialog-level end-to-end: file watcher -> debounce -> background --------
# compile+test -> finalize -> real git commit, against a disposable repo/DB.

@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_exercise_dialog_full_workflow_real_git_commit(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from app import config, database
    from app.services import curriculum_service, pipeline_service

    db_path = tmp_path / "dialog_test.sqlite"
    repo_root = tmp_path / "dialog_test_repo"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    database.run_migrations(db_path)
    conn = database.get_connection(db_path)
    curriculum_service.seed_curriculum(conn)
    pipeline_service.set_dsa135_repo(conn, repo_root)

    # Never let a real modal block this test -- record instead.
    shown = []
    monkeypatch.setattr(QMessageBox, "warning",
                         staticmethod(lambda *a, **k: shown.append(("warning", a)) or QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "information",
                         staticmethod(lambda *a, **k: shown.append(("information", a)) or QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "critical",
                         staticmethod(lambda *a, **k: shown.append(("critical", a)) or QMessageBox.Ok))

    from app.ui.dialogs import ExerciseTaskDialog

    task = conn.execute(
        "SELECT * FROM tasks WHERE day_number = 1 AND task_type = 'exercise' AND title = 'Maximum of 3'"
    ).fetchone()
    dlg = ExerciseTaskDialog(conn, task)
    try:
        for _ in range(10):
            qapp.processEvents()
        assert dlg.source_path.name == "MaximumOfThree.java"
        assert dlg.source_path.exists()
        assert dlg.finalize_btn.isEnabled() is False  # still skeleton

        dlg.source_path.write_text(
            "import java.util.Scanner;\n"
            "public class MaximumOfThree {\n"
            "    public static void main(String[] a) {\n"
            "        Scanner sc = new Scanner(System.in);\n"
            "        int x = sc.nextInt(), y = sc.nextInt(), z = sc.nextInt();\n"
            "        System.out.println(\"Maximum: \" + Math.max(x, Math.max(y, z)));\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )

        deadline = time.time() + 20
        while time.time() < deadline and not dlg.finalize_btn.isEnabled():
            qapp.processEvents()
            time.sleep(0.05)

        assert dlg.finalize_btn.isEnabled(), (
            f"file={dlg.file_status.text()} compile={dlg.compile_status.text()} "
            f"tests={dlg.tests_status.text()} detail={dlg.detail_label.text()}"
        )

        dlg.note_edit.setPlainText("I used Math.max nested calls to compare three integers.")
        dlg._on_finalize()
        for _ in range(5):
            qapp.processEvents()
    finally:
        if dlg._thread is not None and dlg._thread.isRunning():
            dlg._thread.quit()
            dlg._thread.wait(2000)

    updated = conn.execute("SELECT * FROM tasks WHERE id = ?", (task["id"],)).fetchone()
    assert updated["completed"] == 1

    commit_row = conn.execute("SELECT * FROM git_commits WHERE task_id = ?", (task["id"],)).fetchone()
    assert commit_row is not None
    assert "Maximum of 3" in commit_row["message"]

    import subprocess
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo_root, capture_output=True, text=True)
    assert status.stdout.strip() == ""  # working tree fully clean -- nothing unrelated left staged/dirty

    conn.close()
