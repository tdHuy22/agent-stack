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
