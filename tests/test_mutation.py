"""Chạy mutmut chỉ trên dòng đổi (GĐ6, spec `gd6-spec-theo-lat`): `done-gate/scripts/mutation.py`.

Viết trước code (S9). Phần lớn test dùng mutmut GIẢ (script Python ghi lại lệnh gọi vào file log) để kiểm cách gọi,
thư mục làm việc, dọn dẹp và quá giờ; một test tích hợp chạy mutmut 2.5.1 thật khi có `.venv-mutmut/bin/mutmut`.
"""
import json
import os
import shlex
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

from tests._util import PLUGIN, REPO, TempDirTestCase, git, run_script

SCRIPT = PLUGIN / "skills" / "done-gate" / "scripts" / "mutation.py"
sys.path.insert(0, str(PLUGIN / "lib"))
import testlock as TL  # noqa: E402

REAL_MUTMUT = REPO / ".venv-mutmut" / "bin" / "mutmut"

CALC_BASE = '"""Máy tính."""\n\n\ndef add(a, b):\n    return a + b\n'
CALC_EXTRA = "\n\ndef neg(x):\n    return -x\n"
NEWMOD = "def sq(x):\n    return x * x\n"
TEST_BASE = ("import unittest\nfrom calc import add\n\n\nclass T(unittest.TestCase):\n"
             "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n")
CMD = (sys.executable, "-m", "unittest", "tests.test_calc")

# mutmut giả: ghi mỗi lần gọi vào FAKE_MUTMUT_LOG, phá một file nguồn trong cwd khi `run` (chứng minh project không bị
# đụng), trả XML/ids theo biến môi trường.
FAKE_MUTMUT = r'''#!/usr/bin/env python3
import json, os, subprocess, sys, time

argv = sys.argv[1:]


def opt(name):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else None


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


patch_path = opt("--use-patch-file")
rec = {"argv": argv, "cwd": os.getcwd(), "patch": read(patch_path) if patch_path else None,
       "calc": read("calc.py"), "newmod": read("newmod.py")}
with open(os.environ["FAKE_MUTMUT_LOG"], "a", encoding="utf-8") as f:
    f.write(json.dumps(rec) + "\n")

DEFAULT_XML = (
    '<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="mutmut" tests="2" errors="0" failures="1" '
    'skipped="0"><testcase classname="calc.py" file="calc.py" line="5" name="Mutant #1">'
    '<failure message="Mutant survived"/></testcase>'
    '<testcase classname="calc.py" file="calc.py" line="4" name="Mutant #2"/></testsuite></testsuites>')

cmd = argv[0] if argv else ""
if cmd == "run":
    with open("calc.py", "w", encoding="utf-8") as f:
        f.write("GARBAGE = (\n")
    pidfile = os.environ.get("FAKE_MUTMUT_PIDFILE")
    if pidfile:
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        with open(pidfile, "w", encoding="utf-8") as f:
            f.write(str(child.pid))
    time.sleep(float(os.environ.get("FAKE_MUTMUT_SLEEP", "0")))
    sys.exit(int(os.environ.get("FAKE_MUTMUT_RUN_EXIT", "0")))
elif cmd == "junitxml":
    xml = os.environ.get("FAKE_MUTMUT_XML")
    sys.stdout.write(read(xml) if xml else DEFAULT_XML)
elif cmd == "result-ids" and len(argv) > 1:
    if argv[1] == "killed":
        print(os.environ.get("FAKE_MUTMUT_KILLED", "2"))
    elif argv[1] == "untested":
        print(os.environ.get("FAKE_MUTMUT_UNTESTED", ""))
'''

# XML nhiều kết quả: hai mutant sống, một quá giờ, một bị diệt.
MIXED_XML = (
    '<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="mutmut" tests="4">'
    '<testcase classname="calc.py" file="calc.py" line="6" name="Mutant #1"><failure message="Mutant survived"/>'
    "</testcase>"
    '<testcase classname="newmod.py" file="newmod.py" line="2" name="Mutant #2"><failure message="Mutant survived"/>'
    "</testcase>"
    '<testcase classname="calc.py" file="calc.py" line="5" name="Mutant #3"><error type="timeout" message="t"/>'
    "</testcase>"
    '<testcase classname="calc.py" file="calc.py" line="4" name="Mutant #4"/></testsuite></testsuites>')


def snapshot(root: Path) -> dict:
    """Nội dung mọi file trong cây (trừ .git) để so trước và sau."""
    out = {}
    for path in sorted(root.rglob("*")):
        if ".git" in path.relative_to(root).parts or not path.is_file():
            continue
        out[path.relative_to(root).as_posix()] = path.read_bytes()
    return out


class MutationBase(TempDirTestCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("AGENT_STACK_MUTMUT", None)
        self.state = self.tmp / "state"
        self.repo = self.tmp / "proj"
        self.repo.mkdir()
        self.log = self.tmp / "fake.log"
        self.fake = self.make_fake(self.tmp / "fake_mutmut.py")

    def make_fake(self, path: Path) -> Path:
        path.write_text(FAKE_MUTMUT, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return path

    # ---- fixture ----
    def init_repo(self, book=True, repo=None):
        """Repo gốc: calc.py, tests/test_calc.py, README.md, app.js; sổ khóa có `cmd` cho test_calc.py."""
        repo = repo or self.repo
        for rel, text in (("calc.py", CALC_BASE), ("tests/test_calc.py", TEST_BASE), ("README.md", "# x\n"),
                          ("app.js", "let a = 1;\n")):
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        if book:
            TL.save(repo, {"files": {"tests/test_calc.py": TL.entry_for(TEST_BASE.encode(), "vua", cmd=list(CMD))}})
        git(repo, "init", "-q")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "init")
        return repo

    def append(self, rel, text):
        with open(self.repo / rel, "a", encoding="utf-8") as f:
            f.write(text)

    def change_code(self):
        """calc.py sửa (có hàm mới) và newmod.py mới chưa theo dõi."""
        self.append("calc.py", CALC_EXTRA)
        (self.repo / "newmod.py").write_text(NEWMOD, encoding="utf-8")

    def change_noise(self):
        """File không phải code Python: không được mutate."""
        self.append("README.md", "thêm\n")
        self.append("app.js", "let b = 2;\n")

    # ---- chạy ----
    def mut(self, *args, env=None, project=True):
        self.assertTrue(SCRIPT.is_file(), f"thiếu {SCRIPT}")
        argv = (["--project", str(self.repo)] if project else []) + list(args)
        full = {"AGENT_STACK_STATE": str(self.state), "FAKE_MUTMUT_LOG": str(self.log)}
        full.update(env or {})
        return run_script(SCRIPT, *argv, env=full)

    def fake_args(self):
        return ["--mutmut", str(self.fake)]

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines() if line.strip()]

    def run_call(self):
        runs = [c for c in self.calls() if c["argv"][:1] == ["run"]]
        self.assertEqual(len(runs), 1, f"phải gọi `mutmut run` đúng 1 lần: {self.calls()}")
        return runs[0]

    @staticmethod
    def opt(argv, name):
        return argv[argv.index(name) + 1]

    # ---- kiểm ----
    def status_line(self, out):
        lines = [x for x in out.stdout.splitlines() if x.strip()]
        self.assertTrue(lines, f"stdout rỗng, stderr: {out.stderr}")
        self.assertTrue(lines[-1].startswith("Mutation:"), f"dòng cuối phải mở bằng 'Mutation:': {lines[-1]!r}")
        return lines[-1]

    def assertSkipped(self, out, *words):
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        line = self.status_line(out)
        self.assertIn("chưa chạy:", line)
        for w in words:
            self.assertIn(w, line)
        self.assertEqual([c for c in self.calls() if c["argv"][:1] == ["run"]], [], "không được chạy mutmut")
        return line


class AlwaysExitZero(MutationBase):
    def test_nonexistent_project_exits_zero(self):
        # spec:gd6-spec-theo-lat#S9
        self.repo = self.tmp / "khong-co"
        out = self.mut(*self.fake_args())
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("chưa chạy:", self.status_line(out))

    def test_non_git_dir_exits_zero(self):
        # spec:gd6-spec-theo-lat#S9
        (self.repo / "calc.py").write_text(CALC_BASE, encoding="utf-8")
        out = self.mut("--cmd", "true", *self.fake_args())
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("chưa chạy:", self.status_line(out))

    def test_bad_option_value_exits_zero(self):
        # spec:gd6-spec-theo-lat#S9
        self.init_repo()
        self.change_code()
        out = self.mut("--timeout", "khong-phai-so", "--cmd", "true", *self.fake_args())
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.status_line(out)

    def test_mutmut_crash_exits_zero_and_cleans_copy(self):
        # spec:gd6-spec-theo-lat#S9
        self.init_repo()
        self.change_code()
        out = self.mut("--cmd", "true", *self.fake_args(), env={"FAKE_MUTMUT_RUN_EXIT": "1"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.status_line(out)
        self.assertFalse(Path(self.run_call()["cwd"]).exists(), "bản chép phải bị xóa")

    def test_garbage_junitxml_exits_zero(self):
        # spec:gd6-spec-theo-lat#S9
        self.init_repo()
        self.change_code()
        bad = self.write("bad.xml", "đây không phải xml <<<")
        out = self.mut("--cmd", "true", *self.fake_args(), env={"FAKE_MUTMUT_XML": str(bad)})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.status_line(out)
        self.assertFalse(Path(self.run_call()["cwd"]).exists())


class SkippedReasons(MutationBase):
    def test_missing_mutmut_binary(self):
        # spec:gd6-spec-theo-lat#S9
        self.init_repo()
        self.change_code()
        out = self.mut("--cmd", "true", "--mutmut", str(self.tmp / "khong-co" / "mutmut"))
        self.assertSkipped(out, "mutmut")

    def test_mutmut_not_executable(self):
        # spec:gd6-spec-theo-lat#S9
        self.init_repo()
        self.change_code()
        self.fake.chmod(0o644)
        out = self.mut("--cmd", "true", *self.fake_args())
        self.assertSkipped(out, "mutmut")

    def test_env_var_selects_mutmut(self):
        # spec:gd6-spec-theo-lat#S9
        self.init_repo()
        self.change_code()
        out = self.mut("--cmd", "true", env={"AGENT_STACK_MUTMUT": str(self.fake)})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertNotIn("chưa chạy", self.status_line(out))
        self.run_call()

    def test_env_var_missing_binary_is_skipped(self):
        # spec:gd6-spec-theo-lat#S9
        self.init_repo()
        self.change_code()
        out = self.mut("--cmd", "true", env={"AGENT_STACK_MUTMUT": str(self.tmp / "khong-co")})
        self.assertSkipped(out, "mutmut")

    def test_option_beats_env_var(self):
        # spec:gd6-spec-theo-lat#S9
        self.init_repo()
        self.change_code()
        out = self.mut("--cmd", "true", "--mutmut", str(self.tmp / "khong-co"),
                       env={"AGENT_STACK_MUTMUT": str(self.fake)})
        self.assertSkipped(out, "mutmut")

    def test_no_changes_at_all(self):
        # spec:gd6-spec-theo-lat#S9
        self.init_repo()
        out = self.mut("--cmd", "true", *self.fake_args())
        self.assertSkipped(out)

    def test_only_non_python_or_doc_changes(self):
        # spec:gd6-spec-theo-lat#S9
        self.init_repo()
        self.change_noise()
        out = self.mut("--cmd", "true", *self.fake_args())
        self.assertSkipped(out)

    def test_only_test_files_changed(self):
        # spec:gd6-spec-theo-lat#S9
        self.init_repo()
        self.append("tests/test_calc.py", "\n# thêm\n")
        (self.repo / "tests" / "test_new.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
        out = self.mut("--cmd", "true", *self.fake_args())
        self.assertSkipped(out)

    def test_no_test_command(self):
        # spec:gd6-spec-theo-lat#S9
        self.init_repo(book=False)
        self.change_code()
        out = self.mut(*self.fake_args())
        line = self.assertSkipped(out)
        self.assertTrue("--cmd" in line or "lệnh" in line, f"lý do phải nhắc lệnh test: {line!r}")

    def test_book_cmd_ignored_when_locked_test_unchanged(self):
        # spec:gd6-spec-theo-lat#S9
        self.init_repo()  # sổ có cmd cho tests/test_calc.py, nhưng file test này không đổi
        self.change_code()
        out = self.mut(*self.fake_args())
        line = self.assertSkipped(out)
        self.assertTrue("--cmd" in line or "lệnh" in line, line)

    def test_skipped_json_shape(self):
        # spec:gd6-spec-theo-lat#S9
        self.init_repo()
        out = self.mut("--json", "--cmd", "true", *self.fake_args())
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        data = json.loads(out.stdout)
        self.assertEqual(data["status"], "skipped")
        self.assertTrue(isinstance(data["reason"], str) and data["reason"])
        self.assertEqual(self.calls(), [])


class Invocation(MutationBase):
    def setUp(self):
        super().setUp()
        self.init_repo()
        self.change_code()
        self.change_noise()
        self.append("tests/test_calc.py", "\n# thêm\n")

    def test_run_args_cover_only_changed_code_files(self):
        # spec:gd6-spec-theo-lat#S9
        out = self.mut("--cmd", "mytest --flag", *self.fake_args())
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        argv = self.run_call()["argv"]
        paths = self.opt(argv, "--paths-to-mutate").split(",")
        self.assertEqual(sorted(paths), ["calc.py", "newmod.py"])
        self.assertEqual(self.opt(argv, "--runner"), "mytest --flag")
        self.assertIn("--use-patch-file", argv)
        self.assertIn("--tests-dir", argv)

    def test_patch_covers_only_changed_code_files(self):
        # spec:gd6-spec-theo-lat#S9
        self.mut("--cmd", "true", *self.fake_args())
        patch = self.run_call()["patch"]
        self.assertIsInstance(patch, str, "file patch phải tồn tại lúc `mutmut run`")
        files = set()
        for line in patch.splitlines():
            if line.startswith("+++ "):
                name = line[4:].split("\t")[0]
                if name != "/dev/null":
                    files.add(name.removeprefix("b/"))
        self.assertEqual(files, {"calc.py", "newmod.py"})
        self.assertIn("+    return -x", patch)
        self.assertIn("+    return x * x", patch)
        self.assertNotIn("README", patch)
        self.assertNotIn("app.js", patch)

    def test_results_queried_in_same_copy_after_run(self):
        # spec:gd6-spec-theo-lat#S9
        self.mut("--cmd", "true", *self.fake_args())
        calls = self.calls()
        argvs = [c["argv"] for c in calls]
        self.assertEqual(argvs[0][0], "run")
        self.assertIn(["junitxml"], argvs[1:])
        self.assertIn(["result-ids", "killed"], argvs[1:])
        self.assertIn(["result-ids", "untested"], argvs[1:])
        self.assertEqual({c["cwd"] for c in calls}, {calls[0]["cwd"]}, "mọi lệnh mutmut chạy trong cùng một bản chép")

    def test_cmd_taken_from_lock_book_when_changed_test_is_locked(self):
        # spec:gd6-spec-theo-lat#S9
        out = self.mut(*self.fake_args())
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        runner = self.opt(self.run_call()["argv"], "--runner")
        self.assertEqual(shlex.split(runner), list(CMD))

    def test_cmd_option_beats_lock_book(self):
        # spec:gd6-spec-theo-lat#S9
        self.mut("--cmd", "python3 -m pytest -x", *self.fake_args())
        runner = self.opt(self.run_call()["argv"], "--runner")
        self.assertEqual(shlex.split(runner), ["python3", "-m", "pytest", "-x"])

    def test_base_option_selects_older_diff(self):
        # spec:gd6-spec-theo-lat#S9
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "hai")
        out = self.mut("--cmd", "true", *self.fake_args())  # HEAD: không còn gì đổi
        self.assertSkipped(out)
        out = self.mut("--base", "HEAD~1", "--cmd", "true", *self.fake_args())
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        paths = self.opt(self.run_call()["argv"], "--paths-to-mutate").split(",")
        self.assertEqual(sorted(paths), ["calc.py", "newmod.py"])


class WorkingCopy(MutationBase):
    def setUp(self):
        super().setUp()
        self.init_repo()
        self.change_code()

    def test_cwd_is_temp_copy_and_deleted_afterwards(self):
        # spec:gd6-spec-theo-lat#S9
        out = self.mut("--cmd", "true", *self.fake_args())
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        calls = self.calls()
        self.assertTrue(calls)
        cwd = calls[0]["cwd"]
        tmp_root = os.path.realpath(tempfile.gettempdir())
        real = os.path.realpath(cwd)
        self.assertTrue(real.startswith(tmp_root + os.sep), f"{real} phải nằm dưới {tmp_root}")
        self.assertNotEqual(real, os.path.realpath(self.repo))
        self.assertFalse(real.startswith(os.path.realpath(self.repo) + os.sep))
        self.assertFalse(Path(cwd).exists(), "bản chép phải bị xóa khi xong")

    def test_copy_has_working_tree_changes_including_untracked(self):
        # spec:gd6-spec-theo-lat#S9
        self.mut("--cmd", "true", *self.fake_args())
        call = self.run_call()
        self.assertEqual(call["calc"], CALC_BASE + CALC_EXTRA)
        self.assertEqual(call["newmod"], NEWMOD)

    def test_project_untouched(self):
        # spec:gd6-spec-theo-lat#S9
        before_status = git(self.repo, "status", "--porcelain")
        before_files = snapshot(self.repo)
        out = self.mut("--cmd", "true", *self.fake_args())
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.run_call()  # mutmut giả đã chạy và phá file nguồn trong cwd của nó
        self.assertEqual(git(self.repo, "status", "--porcelain"), before_status)
        self.assertEqual(snapshot(self.repo), before_files)


class Results(MutationBase):
    def setUp(self):
        super().setUp()
        self.init_repo()
        self.change_code()

    def test_survivor_reported_as_file_line(self):
        # spec:gd6-spec-theo-lat#S9
        out = self.mut("--cmd", "true", *self.fake_args(), env={"FAKE_MUTMUT_RUN_EXIT": "2"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        line = self.status_line(out)
        self.assertNotIn("chưa chạy", line)
        self.assertIn("calc.py:5", out.stdout)

    def test_json_shape_and_counts(self):
        # spec:gd6-spec-theo-lat#S9
        out = self.mut("--json", "--cmd", "true", *self.fake_args())
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        data = json.loads(out.stdout)
        self.assertEqual(data["status"], "ran")
        for key in ("total", "killed", "timeout", "untested"):
            self.assertIsInstance(data[key], int, key)
        self.assertEqual((data["total"], data["killed"], data["timeout"], data["untested"]), (2, 1, 0, 0))
        self.assertEqual(len(data["survived"]), 1)
        item = data["survived"][0]
        self.assertEqual((item["file"], item["line"]), ("calc.py", 5))
        self.assertIsInstance(item["diff"], str)

    def test_json_survivors_timeouts_untested(self):
        # spec:gd6-spec-theo-lat#S9
        xml = self.write("mixed.xml", MIXED_XML)
        out = self.mut("--json", "--cmd", "true", *self.fake_args(),
                       env={"FAKE_MUTMUT_XML": str(xml), "FAKE_MUTMUT_KILLED": "4", "FAKE_MUTMUT_UNTESTED": "7 8 9"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        data = json.loads(out.stdout)
        self.assertEqual(data["status"], "ran")
        self.assertEqual({(s["file"], s["line"]) for s in data["survived"]}, {("calc.py", 6), ("newmod.py", 2)})
        self.assertEqual(data["timeout"], 1)
        self.assertEqual(data["untested"], 3)
        self.assertEqual(data["killed"], 1)

    def test_text_output_lists_every_survivor(self):
        # spec:gd6-spec-theo-lat#S9
        xml = self.write("mixed.xml", MIXED_XML)
        out = self.mut("--cmd", "true", *self.fake_args(), env={"FAKE_MUTMUT_XML": str(xml)})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.status_line(out)
        self.assertIn("calc.py:6", out.stdout)
        self.assertIn("newmod.py:2", out.stdout)
        listed = [ln for ln in out.stdout.splitlines() if ln.startswith("- sống:")]
        self.assertTrue(listed, out.stdout)
        self.assertFalse([ln for ln in listed if "calc.py:4" in ln], "mutant bị diệt không được liệt kê là sống")
        last = [ln for ln in out.stdout.splitlines() if ln.startswith("Mutation:")][-1]
        self.assertNotIn("calc.py:4", last, "phần ngoặc dòng cuối chỉ nêu đột biến sống")
        warn = [ln for ln in out.stdout.splitlines() if "ngoài dòng đổi" in ln]
        self.assertTrue([ln for ln in warn if "calc.py:4" in ln], "đột biến ngoài dòng đổi nằm ở dòng ⚠, không ở dòng sống")


class TimeCap(MutationBase):
    def setUp(self):
        super().setUp()
        self.init_repo()
        self.change_code()
        self.pidfile = self.tmp / "child.pid"
        self.slow = {"FAKE_MUTMUT_SLEEP": "30", "FAKE_MUTMUT_PIDFILE": str(self.pidfile)}

    def alive(self, pid):
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def assertChildKilled(self):
        pid = int(self.pidfile.read_text(encoding="utf-8"))
        self.addCleanup(lambda: self.alive(pid) and os.kill(pid, 9))
        for _ in range(40):
            if not self.alive(pid):
                return
            time.sleep(0.1)
        self.fail("tiến trình con của mutmut còn sống: phải kill cả nhóm tiến trình")

    def test_timeout_kills_run_and_reports(self):
        # spec:gd6-spec-theo-lat#S9
        start = time.monotonic()
        out = self.mut("--cmd", "true", "--timeout", "2", *self.fake_args(), env=self.slow)
        self.assertLess(time.monotonic() - start, 25, "phải dừng ngay khi quá giờ, không chờ mutmut")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        line = self.status_line(out)
        self.assertIn("chưa chạy", line)
        self.assertIn("quá giờ", line)
        self.assertFalse(Path(self.run_call()["cwd"]).exists(), "bản chép phải bị xóa cả khi quá giờ")
        self.assertChildKilled()

    def test_timeout_json_reason(self):
        # spec:gd6-spec-theo-lat#S9
        out = self.mut("--json", "--cmd", "true", "--timeout", "2", *self.fake_args(), env=self.slow)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        data = json.loads(out.stdout)
        self.assertIn(data["status"], ("skipped", "partial"))
        self.assertIn("quá giờ", data["reason"])
        self.assertFalse(Path(self.run_call()["cwd"]).exists())


class RealMutmut(MutationBase):
    """Tích hợp với mutmut 2.5.1 thật; bỏ qua khi chưa có `.venv-mutmut`. Có thể mất tới ~60 giây."""

    def test_real_mutmut_kills_and_finds_survivor(self):
        # spec:gd6-spec-theo-lat#S9
        if not REAL_MUTMUT.exists():
            self.skipTest(f"chưa có {REAL_MUTMUT}")
        self.assertTrue(SCRIPT.is_file(), f"thiếu {SCRIPT}")
        repo = self.repo
        (repo / "tests").mkdir()
        (repo / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
        (repo / "tests" / "test_calc.py").write_text(TEST_BASE, encoding="utf-8")
        git(repo, "init", "-q")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "init")
        fixed = "def add(a, b):\n    return a + b\n\n\ndef neg(x):\n    return -x\n"
        (repo / "calc.py").write_text(fixed, encoding="utf-8")
        neg_line = fixed.splitlines().index("    return -x") + 1
        env = dict(os.environ, AGENT_STACK_STATE=str(self.state))
        out = subprocess.run(
            [sys.executable, str(SCRIPT), "--project", str(repo), "--cmd", shlex.join(CMD), "--timeout", "300",
             "--json"], capture_output=True, text=True, env=env, timeout=400)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        data = json.loads(out.stdout)
        self.assertEqual(data["status"], "ran", data)
        self.assertGreaterEqual(data["killed"], 1, data)
        self.assertIn(("calc.py", neg_line), {(s["file"], s["line"]) for s in data["survived"]}, data)
        self.assertEqual(git(repo, "status", "--porcelain").strip(), "M calc.py", "project không bị đụng")


class JunitxmlFallback(MutationBase):
    """mutmut 2.5.1 thật: `junitxml` sập (pony OperationWithDeletedObjectError) sau lần chạy bị kill vì quá giờ.
    Khi đó mutation.py phải lấy số đếm từ `result-ids <trạng thái>` và vị trí mutant sống từ `mutmut show <id>`."""

    # mutmut giả: junitxml không in gì ra stdout, ghi traceback ra stderr, thoát 1; result-ids và show trả như mutmut thật.
    FAKE_FALLBACK = r'''#!/usr/bin/env python3
import json, os, subprocess, sys, time

argv = sys.argv[1:]


def opt(name):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else None


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


patch_path = opt("--use-patch-file")
rec = {"argv": argv, "cwd": os.getcwd(), "patch": read(patch_path) if patch_path else None,
       "calc": read("calc.py"), "newmod": read("newmod.py")}
with open(os.environ["FAKE_MUTMUT_LOG"], "a", encoding="utf-8") as f:
    f.write(json.dumps(rec) + "\n")

SHOW3 = "--- calc.py\n+++ calc.py\n@@ -4,7 +4,7 @@\n def add(a, b):\n-    return a + b\n+    return a - b\n"
IDS = {"killed": "1 2", "survived": "3", "timeout": "4"}

cmd = argv[0] if argv else ""
if cmd == "run":
    with open("calc.py", "w", encoding="utf-8") as f:
        f.write("GARBAGE = (\n")
    time.sleep(float(os.environ.get("FAKE_MUTMUT_SLEEP", "0")))
    sys.exit(int(os.environ.get("FAKE_MUTMUT_RUN_EXIT", "0")))
elif cmd == "junitxml":
    sys.stderr.write("Traceback (most recent call last):\n"
                     "pony.orm.core.OperationWithDeletedObjectError: Object was deleted\n")
    sys.exit(1)
elif cmd == "result-ids" and len(argv) > 1:
    ids = IDS.get(argv[1])
    if ids:
        print(ids)
elif cmd == "show" and len(argv) > 1 and argv[1] == "3":
    sys.stdout.write(SHOW3)
'''

    def make_fake(self, path: Path) -> Path:
        path.write_text(self.FAKE_FALLBACK, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return path

    def setUp(self):
        super().setUp()
        self.init_repo()
        self.change_code()

    def test_counts_and_survivor_from_result_ids_and_show(self):
        # spec:gd6-spec-theo-lat#S9
        out = self.mut("--json", "--cmd", "true", *self.fake_args())
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        data = json.loads(out.stdout)
        self.assertEqual(data["status"], "ran", data)
        self.assertEqual((data["total"], data["killed"], data["timeout"]), (4, 2, 1), data)
        self.assertEqual(len(data["survived"]), 1, data)
        item = data["survived"][0]
        self.assertEqual((item["file"], item["line"]), ("calc.py", 5))
        self.assertIsInstance(item["diff"], str)
        argvs = [c["argv"] for c in self.calls()]
        self.assertIn(["show", "3"], argvs, "vị trí mutant sống lấy từ `mutmut show <id>`")
        self.assertFalse(Path(self.run_call()["cwd"]).exists(), "bản chép phải bị xóa")

    def test_text_status_line_lists_survivor_location(self):
        # spec:gd6-spec-theo-lat#S9
        out = self.mut("--cmd", "true", *self.fake_args())
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        line = self.status_line(out)
        self.assertNotIn("chưa chạy", line)
        self.assertIn("calc.py:5", line)

    def test_timeout_then_fallback_is_partial_with_results(self):
        # spec:gd6-spec-theo-lat#S9
        out = self.mut("--json", "--cmd", "true", "--timeout", "2", *self.fake_args(),
                       env={"FAKE_MUTMUT_SLEEP": "30"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        data = json.loads(out.stdout)
        self.assertEqual(data["status"], "partial", data)
        self.assertIn("quá giờ", data["reason"])
        self.assertEqual(data["killed"], 2, data)
        self.assertIn(("calc.py", 5), {(s["file"], s["line"]) for s in data["survived"]}, data)
        self.assertFalse(Path(self.run_call()["cwd"]).exists(), "bản chép phải bị xóa cả khi quá giờ")

    def test_timeout_then_fallback_text_status_line(self):
        # spec:gd6-spec-theo-lat#S9
        out = self.mut("--cmd", "true", "--timeout", "2", *self.fake_args(), env={"FAKE_MUTMUT_SLEEP": "30"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        line = self.status_line(out)
        self.assertIn("chưa chạy", line)
        self.assertIn("quá giờ", line)
        self.assertIn("calc.py:5", line)
