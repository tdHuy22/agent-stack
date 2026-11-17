"""Test siết sau review sonnet·xhigh 17/11 của tám quan sát GĐ6 (lát `gd6-qs-cong-cu`), viết trước bản sửa:
`--cwd` không mở đường qua chốt chặn test khóa; khóa lại không chứng minh không để biên nhận trượt; mutation chạy lệnh
test trong thư mục mục khóa ghi; dòng 🟡 của bánh cóc nói cách gỡ khi `lock` từ chối."""
import sys
import unittest

from tests import test_gd6_qs_cong_cu as base
from tests import test_guard
from tests._util import git
from tests.test_ratchet import write_lock

sys.path.insert(0, str(base.DONE_GATE))
import mutation  # noqa: E402
import ratchet  # noqa: E402
import risk  # noqa: E402

A = base.A
LOCKED_B = "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_b(self):\n        self.assertEqual(1, 1)\n"


class CwdFlagKeepsLockGuard(test_guard.GuardBase):
    def setUp(self):
        super().setUp()
        (self.project / "tests").mkdir()
        (self.project / "tests" / "test_b.py").write_text(LOCKED_B)
        write_lock(self.project, "cao", "tests/test_b.py")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "lock")

    def test_inner_command_after_cwd_is_still_checked(self):
        # spec:gd6-qs-cong-cu#S5 (review: cờ `--cwd` không được làm hook bỏ sót lệnh bên trong, TM-102..104)
        self.start("làm tiếp", "c1")
        r = "python3 plugin/skills/session-keeper/scripts/receipt.py"
        for cmd in [f"{r} run --cwd . -- rm tests/test_b.py", f"{r} run --cwd tests -- sed -i '' s/1/2/ test_b.py",
                    f"{r} lock --cwd tests -- rm test_b.py", f"{r} fails-before --cwd=tests -- rm test_b.py",
                    f"{r} run --project . --cwd tests rm test_b.py"]:
            with self.subTest(cmd=cmd):
                out = self.bash(cmd, "c1")
                self.assertEqual(out and out[0], "deny", cmd)
        self.assertIsNone(self.bash(f"{r} run --cwd tests -- python3 -m unittest test_b", "c1"))


class UnprovenRelockReceipt(base.LockedTestRepo):
    def test_unproven_relock_leaves_no_failing_receipt(self):
        # spec:gd6-qs-cong-cu#S6 (review: khóa lại không chứng minh không để biên nhận trượt làm hook Stop báo sai)
        self.append_new_test()
        out = self.lock("--level", "cao")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        bad = {k: v for k, v in A.receipt_status(self.repo).items() if v.get("ok") is False}
        self.assertEqual(bad, {}, bad)


class MutationRunnerUsesLockCwd(unittest.TestCase):
    def test_runner_runs_in_the_directory_the_lock_recorded(self):
        # spec:gd6-qs-cong-cu#S5 (review: mục khóa ghi `cwd` thì mutation chạy lệnh test ở đó)
        book = {"files": {"sub/test_calc.py": {"cmd": ["python3", "-m", "unittest", "test_calc"], "cwd": "sub"}}}
        runner = mutation.runner_for(None, book, {"sub/test_calc.py"})
        self.assertIn("cd sub &&", runner)
        self.assertIn("python3 -m unittest test_calc", runner)
        plain = {"files": {"t.py": {"cmd": ["python3", "-m", "unittest", "t"]}}}
        self.assertEqual(mutation.runner_for(None, plain, {"t.py"}), "python3 -m unittest t")


class RelockHintNamesBase(base.LockedTestRepo):
    def test_relock_line_says_how_to_lock_when_lock_refuses(self):
        # spec:gd6-qs-cong-cu#S7 (review: dòng 🟡 phải có đường gỡ khi `lock` từ chối vì test đạt cả trên code cũ)
        self.append_new_test()
        r = ratchet.classify(self.repo, risk.collect(self.repo), kind=risk.kind)
        self.assertTrue(r["relock"], r)
        self.assertIn("--base", r["relock"][0])


if __name__ == "__main__":
    unittest.main()
