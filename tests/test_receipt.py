"""Biên nhận kiểm tra (session-keeper/scripts/receipt.py) và cách tien-do dùng nó."""
import json
import os
import sys

from tests._util import PLUGIN, TempDirTestCase, git, run_script

RECEIPT = PLUGIN / "skills" / "session-keeper" / "scripts" / "receipt.py"
sys.path.insert(0, str(PLUGIN / "lib"))
sys.path.insert(0, str(PLUGIN / "skills" / "tien-do" / "scripts"))
import agentstack as A  # noqa: E402
import collect  # noqa: E402

PASS = "import sys; print('Ran 3 tests'); print('OK')"
FAIL = "import sys; print('FAILED (failures=1)'); sys.exit(1)"


class Base(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.state = self.tmp / "state"
        os.environ["AGENT_STACK_STATE"] = str(self.state)
        self.addCleanup(os.environ.pop, "AGENT_STACK_STATE", None)
        self.repo = self.tmp / "proj"
        self.repo.mkdir()
        self.write("proj/app.py", "print('v1')\n")
        self.write("proj/.gitignore", "build/\n")
        self.write("proj/PLAN.md", "# Kế hoạch\n\n## 0. Đang ở đâu, việc tiếp theo\n*Cập nhật 01/10/2026.*\n- **Đang dở:** không có.\n")
        git(self.repo, "init", "-q")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "init")

    def receipt(self, *args):
        return run_script(RECEIPT, *args, env={"AGENT_STACK_STATE": str(self.state)})


class Fingerprint(Base):
    def test_depends_on_content_not_on_commits(self):
        first = A.tree_fingerprint(self.repo)
        self.assertTrue(first)
        self.write("proj/app.py", "print('v2')\n")
        edited = A.tree_fingerprint(self.repo)
        self.assertNotEqual(first, edited)
        git(self.repo, "commit", "-qam", "v2")
        self.assertEqual(A.tree_fingerprint(self.repo), edited)  # commit không đổi nội dung

    def test_new_and_deleted_files_count_but_ignored_files_do_not(self):
        base = A.tree_fingerprint(self.repo)
        self.write("proj/build/out.bin", "x")
        self.assertEqual(A.tree_fingerprint(self.repo), base)
        self.write("proj/new.py", "x = 1\n")
        with_new = A.tree_fingerprint(self.repo)
        self.assertNotEqual(with_new, base)
        (self.repo / "new.py").unlink()
        (self.repo / "app.py").unlink()
        self.assertNotIn(A.tree_fingerprint(self.repo), (base, with_new))

    def test_not_a_git_repo(self):
        plain = self.tmp / "plain"
        plain.mkdir()
        self.assertIsNone(A.tree_fingerprint(plain))


class ReceiptCli(Base):
    def test_pass_and_fail_are_recorded_with_exit_code(self):
        out = self.receipt("run", "--project", str(self.repo), "--label", "unit", "--", sys.executable, "-c", PASS)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Ran 3 tests", out.stdout)
        self.assertIn("✓ đạt", out.stdout)
        out = self.receipt("run", "--project", str(self.repo), "--label", "lint", "--", sys.executable, "-c", FAIL)
        self.assertEqual(out.returncode, 1)
        data = json.loads(A.receipt_path(self.repo).read_text(encoding="utf-8"))
        self.assertTrue(data["checks"]["unit"]["ok"])
        self.assertFalse(data["checks"]["lint"]["ok"])
        self.assertEqual(data["checks"]["lint"]["summary"], "FAILED (failures=1)")
        self.assertEqual(data["checks"]["unit"]["fingerprint"], A.tree_fingerprint(self.repo))

    def test_show_reports_stale_results_after_edit(self):
        self.receipt("run", "--project", str(self.repo), "--label", "unit", "--", sys.executable, "-c", PASS)
        self.assertIn("còn khớp code hiện tại", self.receipt("show", "--project", str(self.repo)).stdout)
        self.write("proj/app.py", "print('v3')\n")
        self.assertIn("code đã đổi", self.receipt("show", "--project", str(self.repo)).stdout)

    def test_missing_command_and_timeout(self):
        out = self.receipt("run", "--project", str(self.repo), "--", "lenh-khong-ton-tai-xyz")
        self.assertEqual(out.returncode, 127)
        out = self.receipt("run", "--project", str(self.repo), "--timeout", "1", "--",
                           sys.executable, "-c", "import time; time.sleep(5)")
        self.assertEqual(out.returncode, 124)
        self.assertIn("dừng sau", out.stdout)

    def test_requires_a_command(self):
        out = self.receipt("run", "--project", str(self.repo))
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("thiếu lệnh", out.stderr)


class ForgetAndPrune(Base):
    def labels(self):
        return set(json.loads(A.receipt_path(self.repo).read_text(encoding="utf-8"))["checks"])

    def test_forget_by_label(self):
        self.receipt("run", "--project", str(self.repo), "--label", "unit", "--", sys.executable, "-c", PASS)
        self.receipt("run", "--project", str(self.repo), "--label", "lint", "--", sys.executable, "-c", FAIL)
        out = self.receipt("forget", "--project", str(self.repo), "lint", "khong-co")
        self.assertEqual(out.returncode, 1)
        self.assertIn("Đã xoá biên nhận: lint", out.stdout)
        self.assertIn("Các tên hiện có: unit", out.stdout)
        self.assertEqual(self.labels(), {"unit"})
        self.assertEqual(self.receipt("forget", "--project", str(self.repo), "unit").returncode, 0)
        self.assertFalse(A.receipt_path(self.repo).exists())
        self.assertIn("Chưa có biên nhận", self.receipt("show", "--project", str(self.repo)).stdout)

    def test_prune_drops_failing_runs_of_deleted_tests_only(self):
        self.write("proj/tests/__init__.py", "")
        self.write("proj/tests/test_ok.py", "import unittest\nclass T(unittest.TestCase):\n    def test_a(self):\n        pass\n")
        run = lambda label, *cmd: self.receipt("run", "--project", str(self.repo), "--label", label, "--", *cmd)
        run("gone", sys.executable, "-m", "unittest", "tests.test_ok", "tests.test_da_xoa")      # trượt: module mất
        run("kept-pass", sys.executable, "-m", "unittest", "tests.test_ok.T.test_a")            # đạt
        run("kept-fail", sys.executable, "-c", FAIL)                                            # trượt nhưng không phải test
        run("gone-pytest", "pytest", "tests/test_da_xoa.py::test_x")                            # trượt (127 hay lỗi)
        dry = self.receipt("prune", "--project", str(self.repo), "--dry-run")
        self.assertIn("Sẽ xoá biên nhận: gone (không còn: tests.test_da_xoa)", dry.stdout)
        self.assertEqual(len(self.labels()), 4)
        out = self.receipt("prune", "--project", str(self.repo))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.labels(), {"kept-pass", "kept-fail"})
        self.assertIn("Không có biên nhận nào", self.receipt("prune", "--project", str(self.repo)).stdout)


class MissingTargets(Base):
    """Nhận diện test đã xoá phải thận trọng: không chắc thì không xoá, để không che một test đang trượt thật."""

    def setUp(self):
        super().setUp()
        import importlib.util
        spec = importlib.util.spec_from_file_location("receipt_mod", RECEIPT)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        self.write("proj/tests/__init__.py", "")
        self.write("proj/tests/test_a.py", "")

    def miss(self, *cmd):
        return self.mod.missing_targets(self.repo, ["python3", *cmd])

    def test_detects_deleted_modules_and_files(self):
        self.assertEqual(self.miss("-m", "unittest", "-v", "tests.test_a", "tests.test_gone"), ["tests.test_gone"])
        self.assertEqual(self.miss("-m", "pytest", "-q", "tests/test_gone.py::test_x"), ["tests/test_gone.py::test_x"])
        self.assertEqual(self.mod.missing_targets(self.repo, ["pytest", "tests/test_gone.py"]), ["tests/test_gone.py"])

    def test_keeps_when_unsure(self):
        cases = [
            ("-m", "unittest", "tests.test_a.T.test_x"),                       # lớp và hàm trong file còn
            ("-m", "unittest", "discover", "-s", "tests", "-p", "test_a.py"),  # discover theo pattern
            ("-m", "unittest", "-k", "T.test_x", "tests.test_a"),              # giá trị của -k
            ("-m", "unittest", "pkg_installed.mod"),                           # gói ngoài project
            ("-m", "pytest", "--junitxml", "reports/j.xml", "tests/test_a.py"),
            ("-m", "pytest", "-k", "a/b", "tests/test_a.py"),
            ("-m", "pytest", "other/test_x.py"),                               # thư mục không có trong project
            ("-m", "pytest", "tests", "--ignore", "tests/test_old.py"),        # file bị loại khỏi lần chạy
            ("-c", "print('unittest a.b')"),
        ]
        for cmd in cases:
            self.assertEqual(self.miss(*cmd), [], cmd)
        self.assertEqual(self.mod.missing_targets(self.repo, ["echo", "unittest", "a.b"]), [])
        for bad in (None, "zz", [1, 2], []):
            self.assertEqual(self.mod.missing_targets(self.repo, bad), [])

    def test_corrupt_receipt_file_does_not_crash(self):
        path = A.receipt_path(self.repo)
        path.parent.mkdir(parents=True, exist_ok=True)
        for raw in ("[1, 2]", '{"checks": ["ab"]}', '{"checks": 5}', '{"checks": {"x": null, "y": "s"}}', "khong-phai-json"):
            path.write_text(raw, encoding="utf-8")
            for args in (("prune",), ("forget", "x")):
                out = self.receipt(*args, "--project", str(self.repo))
                self.assertEqual(out.stderr, "", (raw, args))

    def test_forget_with_repeated_label(self):
        self.receipt("run", "--project", str(self.repo), "--label", "lint", "--", sys.executable, "-c", FAIL)
        out = self.receipt("forget", "--project", str(self.repo), "lint", "lint")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.count("Đã xoá biên nhận: lint"), 1)


class TienDoUsesReceipts(Base):
    def run_check(self, code):
        self.receipt("run", "--project", str(self.repo), "--label", "unit", "--", sys.executable, "-c", code)

    def actions(self):
        return [(a["tier"], a["text"]) for a in collect.collect(self.repo, scan_todos=False)["actions"]]

    def test_failing_check_is_a_blocker(self):
        self.run_check(FAIL)
        self.assertIn((1, "Sửa kiểm tra đang trượt `unit`: FAILED (failures=1)"), self.actions())
        self.write("proj/app.py", "print('đã sửa')\n")
        self.assertTrue(any(t == 1 and "Chạy lại kiểm tra `unit`" in x for t, x in self.actions()))
        # Biên nhận trượt cũ (lệnh đã bỏ, chạy sai thư mục) chỉ cách gỡ, để không kẹt ở "Chặn đường" mãi.
        stale = [a for a in collect.collect(self.repo, scan_todos=False)["actions"] if a["tier"] == 1][0]
        self.assertIn("receipt.py forget", stale["text"])
        if stale.get("route"):
            self.assertNotEqual(stale["route"]["rule"], "debug-hard")  # lời chỉ cách gỡ không đổi định tuyến

    def test_old_pass_does_not_prove_new_code(self):
        self.run_check(PASS)
        self.assertFalse(any("kiểm tra" in x.lower() for _, x in self.actions()))
        self.assertIn("còn khớp code hiện tại", collect.render_md(collect.collect(self.repo, scan_todos=False)))
        self.write("proj/app.py", "print('v4')\n")
        self.assertIn((3, "Chạy lại mốc kiểm tra: `unit`"), self.actions())

    def test_session_start_brief_shows_failing_check(self):
        self.run_check(FAIL)
        brief = collect.brief(self.repo)
        self.assertIn("Chặn đường: Sửa kiểm tra đang trượt", brief["context"])
