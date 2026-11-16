"""Khóa test viết trước (GĐ6, spec `gd6-spec-theo-lat`): `receipt.py lock --red`.

Test và spec viết TRƯỚC code thì khóa ngay khi test đang đỏ: lệnh chạy một lần trên cây hiện tại, từ chối khi test đạt
(S3) hay khi file code đã đổi (S3); thành công thì test và spec vào sổ khóa kèm loại trượt, dòng trượt đầu tiên (S4).
Lần chạy đỏ không thành biên nhận.
"""
import json
import re
import sys

from tests._util import PLUGIN, TempDirTestCase, git, run_script

RECEIPT = PLUGIN / "skills" / "session-keeper" / "scripts" / "receipt.py"
sys.path.insert(0, str(PLUGIN / "lib"))
import testlock as TL  # noqa: E402

BUGGY = "def add(a, b):\n    return a - b\n"
# Test đỏ vì assert: code cũ trừ thay vì cộng.
RED_ASSERT = ("import unittest\nfrom calc import add\n\n\nclass T(unittest.TestCase):\n"
              "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n")
# Test đỏ vì thiếu: calc chưa có `mul`.
RED_MISSING = ("import unittest\nfrom calc import mul\n\n\nclass T(unittest.TestCase):\n"
               "    def test_mul(self):\n        self.assertEqual(mul(2, 3), 6)\n")
# Test đạt trên code hiện tại (add(0, 0) == 0 dù add sai).
GREEN = RED_ASSERT.replace("add(2, 3), 5", "add(0, 0), 0")
SPEC = "# Lát 1\n\n- S1: add cộng hai số.\n"
CMD = (sys.executable, "-m", "unittest", "test_calc")
SHA40 = re.compile(r"^[0-9a-f]{40}$")


class RedLockBase(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.state = self.tmp / "state"
        self.repo = self.tmp / "proj"
        self.repo.mkdir()
        (self.repo / "calc.py").write_text(BUGGY)
        git(self.repo, "init", "-q")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "init")

    def put(self, rel, text):
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def run_receipt(self, *args):
        return run_script(RECEIPT, *args, env={"AGENT_STACK_STATE": str(self.state)})

    def red(self, *args, level="vua", label="red-test", cmd=CMD, project=None):
        """`lock --red`; `--label` đứng sau mọi tuỳ chọn nhiều giá trị để `--` không bị nuốt vào chúng."""
        head = ["lock", "--red"] + (["--level", level] if level else [])
        return self.run_receipt(*head, "--project", str(project or self.repo), *args, "--label", label, "--", *cmd)

    def book_files(self):
        path = self.repo / TL.LOCK_REL
        return json.loads(path.read_text(encoding="utf-8"))["files"] if path.exists() else {}

    def assertNoLock(self):
        self.assertEqual(self.book_files(), {}, "không được ghi khóa nào")

    def assertRefusedByLock(self, out, code):
        """Từ chối do chính `lock --red` (không phải argparse chê cờ lạ): mã đúng, không có dòng usage."""
        text = out.stdout + out.stderr
        self.assertEqual(out.returncode, code, text)
        self.assertNotIn("usage:", text, "cờ --red phải được nhận")


class RedLockRefusals(RedLockBase):
    def test_passing_test_is_not_locked(self):
        # spec:gd6-spec-theo-lat#S3
        self.put("test_calc.py", GREEN)
        out = self.red()
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertNoLock()

    def test_changed_tracked_code_file_blocks_lock(self):
        # spec:gd6-spec-theo-lat#S3
        self.put("test_calc.py", RED_ASSERT)
        self.put("calc.py", BUGGY + "\n\ndef sub(a, b):\n    return a - b\n")
        out = self.red()
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self.assertIn("calc.py", out.stdout + out.stderr, "thông báo nêu file code đã đổi")
        self.assertNoLock()

    def test_new_untracked_code_file_blocks_lock(self):
        # spec:gd6-spec-theo-lat#S3
        self.put("test_calc.py", RED_ASSERT)
        self.put("helper.py", "X = 1\n")
        out = self.red()
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self.assertIn("helper.py", out.stdout + out.stderr)
        self.assertNoLock()

    def test_code_change_is_checked_against_given_base(self):
        # spec:gd6-spec-theo-lat#S3
        first = git(self.repo, "rev-parse", "HEAD").strip()
        self.put("calc.py", BUGGY + "\n\ndef sub(a, b):\n    return a - b\n")
        git(self.repo, "commit", "-q", "-am", "code mới")
        self.put("test_calc.py", RED_ASSERT)
        # So với HEAD thì cây chỉ có test; so với commit đầu thì calc.py đã đổi.
        out = self.red("--base", first)
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self.assertNoLock()
        out = self.red("--base", "HEAD")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_docs_do_not_block_lock(self):
        # spec:gd6-spec-theo-lat#S3
        self.put("test_calc.py", RED_ASSERT)
        self.put("README.md", "# Tài liệu mới\n")
        self.put("PLAN.md", "# Kế hoạch\n\n## 0. Đang ở đâu\n")
        out = self.red()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(sorted(self.book_files()), ["test_calc.py"])

    def test_test_dir_files_and_lock_book_do_not_block_lock(self):
        # spec:gd6-spec-theo-lat#S3
        self.put("tests/__init__.py", "")
        self.put("tests/test_calc.py", RED_ASSERT)
        out = self.red(cmd=(sys.executable, "-m", "unittest", "tests.test_calc"))
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        # Lần hai: sổ khóa (file mới, chưa commit) nằm trong cây mà không bị coi là code đổi.
        self.assertTrue((self.repo / TL.LOCK_REL).exists())
        again = self.red(cmd=(sys.executable, "-m", "unittest", "tests.test_calc"))
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)

    def test_unrunnable_command_exits_2(self):
        # spec:gd6-spec-theo-lat#S3
        self.put("test_calc.py", RED_ASSERT)
        out = self.red(cmd=("lenh-khong-ton-tai-gd6",))
        self.assertRefusedByLock(out, 2)
        self.assertNoLock()

    def test_timeout_exits_2(self):
        # spec:gd6-spec-theo-lat#S3
        self.put("test_calc.py", RED_ASSERT)
        out = self.red("--timeout", "1", cmd=(sys.executable, "-c", "import time; time.sleep(20)"))
        self.assertRefusedByLock(out, 2)
        self.assertNoLock()

    def test_no_test_files_exits_2(self):
        # spec:gd6-spec-theo-lat#S3
        self.put("README.md", "# chỉ tài liệu\n")
        out = self.red()
        self.assertRefusedByLock(out, 2)
        self.assertNoLock()

    def test_not_a_git_repo_exits_2(self):
        # spec:gd6-spec-theo-lat#S3
        plain = self.tmp / "plain"
        plain.mkdir()
        (plain / "calc.py").write_text(BUGGY)
        (plain / "test_calc.py").write_text(RED_ASSERT)
        out = self.red(project=plain)
        self.assertRefusedByLock(out, 2)
        self.assertFalse((plain / TL.LOCK_REL).exists())


class RedLockRecording(RedLockBase):
    def test_level_is_required_with_red(self):
        # spec:gd6-spec-theo-lat#S4
        self.put("test_calc.py", RED_ASSERT)
        out = self.red(level=None)
        self.assertEqual(out.returncode, 2, out.stdout + out.stderr)
        self.assertNotIn("unrecognized", out.stderr, "cờ --red phải được nhận")
        self.assertIn("level", (out.stdout + out.stderr).lower(), "thông báo nêu thiếu --level")
        self.assertFalse((self.repo / TL.LOCK_REL).exists())

    def test_assertion_failure_is_locked_with_kind_and_first_failure_line(self):
        # spec:gd6-spec-theo-lat#S4
        self.put("test_calc.py", RED_ASSERT)
        out = self.red(level="cao")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        files = self.book_files()
        self.assertEqual(list(files), ["test_calc.py"])
        entry = files["test_calc.py"]
        self.assertEqual(entry["level"], "cao")
        self.assertEqual(entry["sha256"], TL.digest(RED_ASSERT.encode()))
        self.assertEqual(entry["lines"], TL.line_hashes(RED_ASSERT))
        self.assertEqual(entry["label"], "red-test")
        self.assertEqual(entry["cmd"], list(CMD))
        self.assertIn("py", entry)
        self.assertTrue(entry["ts"])
        red = entry["red"]
        self.assertEqual(red["kind"], "assert")
        self.assertIsInstance(red["line"], str)
        self.assertIn("AssertionError", red["line"])
        self.assertRegex(red["base"], SHA40)
        self.assertEqual(red["base"], git(self.repo, "rev-parse", "HEAD").strip())
        self.assertTrue(red["ts"])

    def test_missing_import_is_recorded_as_thieu(self):
        # spec:gd6-spec-theo-lat#S4
        self.put("test_calc.py", RED_MISSING)
        out = self.red()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        red = self.book_files()["test_calc.py"]["red"]
        self.assertEqual(red["kind"], "thieu")
        self.assertRegex(red["line"], r"ImportError|ModuleNotFoundError|cannot import name")

    def test_spec_files_under_agent_spec_are_locked_too(self):
        # spec:gd6-spec-theo-lat#S4
        self.put("test_calc.py", RED_ASSERT)
        self.put(".agent/spec/gd6.md", SPEC)
        out = self.red()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        files = self.book_files()
        self.assertEqual(sorted(files), [".agent/spec/gd6.md", "test_calc.py"])
        spec = files[".agent/spec/gd6.md"]
        self.assertEqual(spec["sha256"], TL.digest(SPEC.encode()))
        self.assertEqual(spec["level"], "vua")
        self.assertIn(spec["red"]["kind"], ("assert", "thieu"))
        self.assertTrue(spec["red"]["line"])

    def test_extra_spec_file_option_locks_that_file(self):
        # spec:gd6-spec-theo-lat#S4
        self.put("test_calc.py", RED_ASSERT)
        self.put("docs/lat-1.md", SPEC)
        out = self.red("--spec", "docs/lat-1.md")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        files = self.book_files()
        self.assertEqual(sorted(files), ["docs/lat-1.md", "test_calc.py"])
        self.assertEqual(files["docs/lat-1.md"]["sha256"], TL.digest(SPEC.encode()))

    def test_tests_option_picks_exactly_the_given_files(self):
        # spec:gd6-spec-theo-lat#S4
        self.put("test_calc.py", RED_ASSERT)
        self.put("test_other.py", RED_ASSERT.replace("class T", "class U"))
        out = self.red("--tests", "test_calc.py")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(sorted(self.book_files()), ["test_calc.py"])

    def test_allowed_code_path_is_listed_not_locked(self):
        # spec:gd6-spec-theo-lat#S3
        # spec:gd6-spec-theo-lat#S4
        self.put("test_calc.py", RED_ASSERT)
        changed = BUGGY + "\n\ndef sub(a, b):\n    return a - b\n"
        self.put("calc.py", changed)
        out = self.red("--allow", "calc.py")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        files = self.book_files()
        self.assertEqual(sorted(files), ["test_calc.py"], "đường dẫn --allow không thành mục khóa")
        allowed = files["test_calc.py"]["red"]["allowed"]
        self.assertEqual(allowed, [{"path": "calc.py", "sha256": TL.digest(changed.encode())}])

    def test_level_only_rises_when_relocking_red(self):
        # spec:gd6-spec-theo-lat#S4
        self.put("test_calc.py", RED_ASSERT)
        self.put(".agent/spec/gd6.md", SPEC)
        self.assertEqual(self.red(level="cao").returncode, 0)
        out = self.red(level="vua")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        files = self.book_files()
        self.assertEqual(files["test_calc.py"]["level"], "cao")
        self.assertEqual(files[".agent/spec/gd6.md"]["level"], "cao")
        # Và ngược lại: nâng từ vua lên cao thì được.
        self.assertEqual(self.red(level="cao").returncode, 0)
        self.assertEqual(self.book_files()["test_calc.py"]["level"], "cao")

    def test_red_run_leaves_no_receipt(self):
        # spec:gd6-spec-theo-lat#S4
        self.put("test_calc.py", RED_ASSERT)
        out = self.red(label="lan-do-gd6")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        shown = self.run_receipt("show", "--json", "--project", str(self.repo))
        self.assertEqual(shown.returncode, 0, shown.stderr)
        checks = json.loads(shown.stdout)
        self.assertNotIn("lan-do-gd6", checks)
        self.assertEqual(checks, {}, "lần chạy đỏ không thành biên nhận trượt")

    def test_red_field_survives_load_and_save_round_trip(self):
        # spec:gd6-spec-theo-lat#S4
        self.put("test_calc.py", RED_ASSERT)
        self.assertEqual(self.red().returncode, 0)
        loaded = TL.load(self.repo)
        self.assertFalse(loaded.get("broken"))
        red = loaded["files"]["test_calc.py"]["red"]
        self.assertEqual(red["kind"], "assert")
        self.assertIn("AssertionError", red["line"])
        TL.save(self.repo, loaded)
        self.assertEqual(TL.load(self.repo)["files"]["test_calc.py"]["red"], red)

    def test_locks_command_shows_red_files(self):
        # spec:gd6-spec-theo-lat#S4
        self.put("test_calc.py", RED_ASSERT)
        self.assertEqual(self.red().returncode, 0)
        shown = self.run_receipt("locks", "--project", str(self.repo))
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertIn("test_calc.py", shown.stdout)
        self.assertTrue("đỏ" in shown.stdout or "viết trước" in shown.stdout, shown.stdout)

    def test_broken_lock_book_blocks_red_lock_and_is_left_alone(self):
        # spec:gd6-spec-theo-lat#S4
        self.put("test_calc.py", RED_ASSERT)
        self.put(TL.LOCK_REL, "{hỏng")
        out = self.red()
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self.assertEqual((self.repo / TL.LOCK_REL).read_text(), "{hỏng", "không ghi đè sổ hỏng")

    def test_loosened_locked_file_blocks_red_lock(self):
        # spec:gd6-spec-theo-lat#S4
        self.put("test_calc.py", RED_ASSERT)
        self.assertEqual(self.red().returncode, 0)
        before = (self.repo / TL.LOCK_REL).read_text()
        # Nới test đã khóa (đổi assert) rồi thêm một test đỏ khác: khóa mới bị từ chối.
        self.put("test_calc.py", RED_ASSERT.replace("assertEqual(add(2, 3), 5)", "assertTrue(add(2, 3))"))
        self.put("test_more.py", RED_ASSERT.replace("class T", "class V"))
        out = self.red("--tests", "test_more.py")
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self.assertIn("test_calc.py", out.stdout + out.stderr)
        self.assertEqual((self.repo / TL.LOCK_REL).read_text(), before)


class RedLockSurvivesRelock(RedLockBase):
    def test_plain_lock_after_red_keeps_red_evidence(self):
        # spec:gd6-spec-theo-lat#S4
        self.put("test_calc.py", RED_ASSERT)
        self.assertEqual(self.red(level="cao").returncode, 0)
        red_before = self.book_files()["test_calc.py"]["red"]
        self.assertEqual(red_before["kind"], "assert")
        # Sửa code cho test đạt rồi khóa thường: fails-before chứng minh test trượt trên commit gốc, đạt bây giờ.
        self.put("calc.py", "def add(a, b):\n    return a + b\n")
        out = self.run_receipt("lock", "--level", "cao", "--project", str(self.repo), "--tests", "test_calc.py",
                               "--label", "lock-sau-do", "--", *CMD)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        entry = self.book_files()["test_calc.py"]
        self.assertEqual(entry["level"], "cao")
        self.assertEqual(entry.get("red"), red_before, "khóa lại không được xóa bằng chứng viết test trước")
