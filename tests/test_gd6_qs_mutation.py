"""Test còn thiếu theo mutation trên diff việc 0 sau GĐ6 (commit `0d86a4f`, so với `dbae333`): đột biến sống trên dòng
đổi mà test của lát `gd6-qs-cong-cu`, `gd6-qs-hook` và bản review chưa bắt. Chỉ siết, không đổi code. Đột biến sống còn
lại là tương đương: lý do ở `EQUIVALENT` cuối file.
"""
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

from tests import test_guard
from tests._util import PLUGIN, TempDirTestCase, git
from tests.test_ratchet import write_lock

sys.path.insert(0, str(PLUGIN / "lib"))
import agentstack as A  # noqa: E402

LOCKED_B = "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_b(self):\n        self.assertEqual(1, 1)\n"
RECEIPT = "python3 plugin/skills/session-keeper/scripts/receipt.py"


# ---------------------------------------------------------------------------------------------------------------
# pretool_guard.receipt_run_dir: cờ nhiều giá trị (`--tests`, `--spec`, `--allow`) đứng trước `--cwd`

class MultiValueFlagBeforeCwd(test_guard.GuardBase):
    def setUp(self):
        super().setUp()
        (self.project / "tests").mkdir()
        (self.project / "tests" / "test_b.py").write_text(LOCKED_B)
        write_lock(self.project, "cao", "tests/test_b.py")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "lock")
        self.start("làm tiếp", "c1")

    def test_cwd_after_a_multi_value_flag_still_sets_the_run_dir(self):
        # spec:gd6-qs-cong-cu#S5 (mutation: bỏ qua giá trị thứ hai của `--tests` thì `--cwd` phía sau không được đọc)
        for cmd in [f"{RECEIPT} lock --tests tests/test_b.py tests/test_c.py --cwd tests -- rm test_b.py",
                    f"{RECEIPT} fails-before --tests a.py b.py --cwd tests rm test_b.py",
                    f"{RECEIPT} lock --red --level cao --spec a.txt b.txt --cwd=tests -- rm test_b.py",
                    f"{RECEIPT} lock --red --level cao --allow x.py y.py --cwd tests -- rm test_b.py"]:
            with self.subTest(cmd=cmd):
                out = self.bash(cmd, "c1")
                self.assertEqual(out and out[0], "deny", cmd)

    def test_harmless_inner_command_after_multi_value_flag_passes(self):
        # spec:gd6-qs-cong-cu#S5 (đối chứng: lệnh bên trong chỉ chạy test thì không bị chặn)
        self.assertIsNone(self.bash(f"{RECEIPT} lock --tests tests/test_b.py x.py --cwd tests -- "
                                    "python3 -m unittest test_b", "c1"))


# ---------------------------------------------------------------------------------------------------------------
# agentstack.ff_foreign_commits: mốc thời gian của dòng reflog và đường dự phòng khi `rev-parse` không ra gì

class FastForwardStampAndToplevel(TempDirTestCase):
    T = 1900000000  # mốc cố định: ngày commit và ngày dòng reflog đặt bằng GIT_COMMITTER_DATE

    def setUp(self):
        super().setUp()
        self.state = self.tmp / "state"
        patcher = mock.patch.dict(os.environ, {"AGENT_STACK_STATE": str(self.state)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.w1 = self.tmp / "w1"
        self.w2 = self.tmp / "w2"
        self.w1.mkdir()
        self.git(self.w1, "init", "-q")
        (self.w1 / "PLAN.md").write_text("# PLAN\n\n## 0. Đang ở đâu, việc tiếp theo\n- làm việc\n", encoding="utf-8")
        self.git(self.w1, "add", "-A")
        self.git(self.w1, "commit", "-q", "-m", "gốc", at=self.T - 10 ** 6)

    def git(self, cwd, *args, at=None):
        env = dict(os.environ)
        if at is not None:
            env["GIT_COMMITTER_DATE"] = env["GIT_AUTHOR_DATE"] = f"@{at} +0000"
        cmd = ["git", "-c", "user.name=test", "-c", "user.email=test@example.com", "-c", "init.defaultBranch=main",
               "-c", "commit.gpgsign=false", *args]
        return subprocess.run(cmd, cwd=str(cwd), env=env, check=True, capture_output=True, text=True).stdout

    def session_at(self, root):
        """Bản ghi lượt có transcript thật, làm ở `root` (như hook prompt_submit ghi)."""
        folder = self.state / A.TURN_DIR
        folder.mkdir(parents=True, exist_ok=True)
        transcript = self.tmp / f"{root.name}.jsonl"
        transcript.write_text("", encoding="utf-8")
        record = {"ts": self.T, "root": str(root.resolve()), "transcript": str(transcript)}
        (folder / f"{root.name}.json").write_text(json.dumps(record), encoding="utf-8")

    def fast_forward(self, ff_at):
        """Commit `foreign.py` (ngày T) ở worktree w2 nhánh `side`, rồi w1 tua nhanh tới nó lúc `ff_at`."""
        self.git(self.w1, "worktree", "add", "-q", str(self.w2), "-b", "side")
        (self.w2 / "foreign.py").write_text("x = 1\n", encoding="utf-8")
        self.git(self.w2, "add", "-A")
        self.git(self.w2, "commit", "-q", "-m", "phiên khác", at=self.T)
        self.git(self.w1, "merge", "-q", "--ff-only", "side", at=ff_at)
        log = self.git(self.w1, "reflog", "show", "-n", "1", "--date=unix", "--format=%gd %gs", "HEAD")
        self.assertIn(f"HEAD@{{{ff_at}}}", log, "dòng reflog phải mang mốc đã đặt")
        self.assertIn("Fast-forward", log)

    def test_fast_forward_exactly_at_since_is_foreign(self):
        # spec:gd6-qs-hook#S4 (mutation: mốc reflog bằng đúng `since` vẫn là sau mốc, `>=` không phải `>`)
        self.session_at(self.w2)
        self.fast_forward(self.T)
        self.assertNotIn("foreign.py", A.changed_since(self.w1, self.T))
        self.assertNotIn("foreign.py", A.changed_since(self.w1, self.T + 0.9), "mốc lẻ giây cắt về giây như reflog")

    def test_fast_forward_before_since_is_not_dropped(self):
        # spec:gd6-qs-hook#S4 (mutation: tua nhanh trước mốc của lượt không phải việc của lượt này, giữ cách tính cũ)
        self.session_at(self.w2)
        self.fast_forward(self.T - 1)
        self.assertEqual(A.ff_foreign_commits(self.w1, self.T), set())
        self.assertIn("foreign.py", A.changed_since(self.w1, self.T))

    def test_empty_toplevel_falls_back_to_root_not_process_cwd(self):
        # spec:gd6-qs-hook#S4 (mutation: `rev-parse --show-toplevel` không ra gì thì cây này là `root`; lấy nhầm thư
        # mục của tiến trình thì cây này thành "worktree khác", bản ghi của chính phiên này giấu commit của nó)
        self.session_at(self.w1)
        self.fast_forward(self.T)
        real = A.git_out
        for blank in ("", None):
            def fake(cwd, *args, _blank=blank, **kw):
                return _blank if args[:2] == ("rev-parse", "--show-toplevel") else real(cwd, *args, **kw)
            with self.subTest(blank=blank), mock.patch.object(A, "git_out", side_effect=fake):
                self.assertEqual(A.ff_foreign_commits(self.w1, self.T), set())
                self.assertIn("foreign.py", A.changed_since(self.w1, self.T))


if __name__ == "__main__":
    unittest.main()
