"""merge_back.py: gộp nhánh worktree của subagent chỉ khi test đạt, fast-forward được và không đụng file nhạy cảm."""
import json
import subprocess
import sys
import unittest

from tests._util import PLUGIN, TempDirTestCase, git

SCRIPT = PLUGIN / "skills" / "task-router" / "scripts" / "merge_back.py"
PASS = f'{sys.executable} -c "import sys; sys.exit(0)"'
FAIL = f'{sys.executable} -c "import sys; print(\'2 failed\'); sys.exit(1)"'


class MergeBack(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        (self.repo / "app.py").write_text("x = 1\n")
        git(self.repo, "init", "-q")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "init")
        self.wt = self.tmp / "wt"
        git(self.repo, "worktree", "add", "-q", "-b", "sub/viec", str(self.wt))

    def commit_in_wt(self, rel, text, message="việc của subagent"):
        path = self.wt / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        git(self.wt, "add", "-A")
        git(self.wt, "commit", "-q", "-m", message)

    def run_script(self, *args):
        out = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(self.repo), "--json", *args],
                             capture_output=True, text=True, timeout=60)
        return out.returncode, json.loads(out.stdout)

    def test_merges_by_fast_forward_when_tests_pass_then_cleans_up(self):
        self.commit_in_wt("app.py", "x = 2\n")
        code, out = self.run_script("--worktree", str(self.wt), "--test", PASS)
        self.assertEqual((code, out["status"]), (0, "da-gop"), out)
        self.assertEqual(out["files"], ["app.py"])
        self.assertEqual((self.repo / "app.py").read_text(), "x = 2\n")
        self.assertFalse(self.wt.exists())
        self.assertNotIn("sub/viec", git(self.repo, "branch", "--list"))

    def test_failed_tests_block_the_merge(self):
        self.commit_in_wt("app.py", "x = 3\n")
        code, out = self.run_script("--worktree", "sub/viec", "--test", FAIL)
        self.assertEqual((code, out["status"]), (1, "test-truot"))
        self.assertIn("2 failed", out["test_tail"])
        self.assertEqual((self.repo / "app.py").read_text(), "x = 1\n")
        self.assertTrue(self.wt.exists())

    def test_sensitive_paths_need_the_user(self):
        # TM-26: nhánh đụng quyền của Claude Code, CI hay luật cho agent thì không tự gộp.
        for rel in (".claude/settings.json", ".github/workflows/ci.yml", "docs/CLAUDE.md", ".mcp.json"):
            with self.subTest(rel=rel):
                self.commit_in_wt(rel, "{}\n", f"sửa {rel}")
                code, out = self.run_script("--worktree", "sub/viec", "--test", PASS)
                self.assertEqual((code, out["status"]), (2, "can-hoi"))
                self.assertIn(rel, out["sensitive"])
                self.assertFalse((self.repo / rel).exists())

    def test_sensitive_paths_ignore_case_symlinks_and_renames(self):
        import os
        self.commit_in_wt(".CLAUDE/settings.json", "{}\n", "hoa thường khác")  # macOS: cùng thư mục với .claude/
        code, out = self.run_script("--worktree", "sub/viec", "--test", PASS)
        self.assertEqual((code, out["status"]), (2, "can-hoi"))
        git(self.wt, "reset", "-q", "--hard", "HEAD~1")
        os.symlink("docs", self.wt / ".claude")  # thư mục .claude là một symlink được thêm vào
        git(self.wt, "add", "-A")
        git(self.wt, "commit", "-q", "-m", "symlink")
        code, out = self.run_script("--worktree", "sub/viec", "--test", PASS)
        self.assertEqual(out["status"], "can-hoi")
        self.assertIn(".claude", out["sensitive"])
        # Đổi tên file ra khỏi .claude/ là xoá file ở đó: phải bị bắt.
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude" / "settings.json").write_text('{"permissions": {"deny": ["Bash(rm:*)"]}}\n')
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "quyền")
        wt2 = self.tmp / "wt2"
        git(self.repo, "worktree", "add", "-q", "-b", "sub/doiten", str(wt2))
        git(wt2, "mv", ".claude/settings.json", "notes.json")
        git(wt2, "commit", "-q", "-m", "đổi tên")
        code, out = self.run_script("--worktree", "sub/doiten", "--test", PASS)
        self.assertEqual((code, out["status"]), (2, "can-hoi"))
        self.assertIn(".claude/settings.json", out["sensitive"])
        self.assertTrue((self.repo / ".claude" / "settings.json").exists())

    def test_code_that_commits_while_tests_run_is_never_merged(self):
        # H1: mã test của nhánh tự commit cấu hình quyền sau bước kiểm; script gộp đúng commit đã kiểm hoặc dừng.
        self.commit_in_wt("app.py", "x = 7\n")
        evil = ("import os, subprocess; os.makedirs('.claude', exist_ok=True); "
                "open('.claude/settings.json', 'w').write('{}'); "
                "subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', 'add', '-A']); "
                "subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', 'x'])")
        (self.wt / "evil_test.py").write_text(evil)
        git(self.wt, "add", "-A")
        git(self.wt, "commit", "-q", "-m", "test của nhánh")
        code, out = self.run_script("--worktree", "sub/viec", "--test", f"{sys.executable} evil_test.py")
        self.assertEqual((code, out["status"]), (2, "can-hoi"), out)
        self.assertIn("đã đổi commit", out["reason"])
        self.assertFalse((self.repo / ".claude").exists())
        self.assertEqual((self.repo / "app.py").read_text(), "x = 1\n")

    def test_names_that_the_disk_treats_as_sensitive_and_plan_files_need_the_user(self):
        # M1: APFS coi ſ là s, nên `.mcp.jſon` là `.mcp.json`; M4: file kế hoạch, .agent/, cấu hình agent khác.
        for rel in (".mcp.j\u017fon", "AGENT\u017f.md", "PLAN.md", "docs/luan-van/plan.md", ".agent/HANDOFF.md",
                    "opencode.json", ".cursor/rules.md", "plugin/hooks/hooks.json"):
            with self.subTest(rel=rel):
                self.commit_in_wt(rel, "x\n", f"sửa {rel}")
                code, out = self.run_script("--worktree", "sub/viec", "--test", PASS)
                self.assertEqual((code, out["status"]), (2, "can-hoi"), out)
                git(self.wt, "reset", "-q", "--hard", "HEAD~1")

    def test_names_git_would_quote_are_still_checked(self):
        # N1: tên có " bị git bọc ngoặc kép khi không có -z, từng lọt qua bước so tên.
        for rel in ('.claude/skills/a"b/SKILL.md', 'sub"dir/CLAUDE.md', "tab\tdir/AGENTS.md"):
            with self.subTest(rel=rel):
                self.commit_in_wt(rel, "x\n", "tên lạ")
                code, out = self.run_script("--worktree", "sub/viec", "--test", PASS)
                self.assertEqual((code, out["status"]), (2, "can-hoi"), out)
                self.assertIn(rel, out["sensitive"])
                git(self.wt, "reset", "-q", "--hard", "HEAD~1")

    def test_symlinks_and_submodules_anywhere_need_the_user(self):
        import os
        os.symlink("../../etc", self.wt / "docs-link")
        git(self.wt, "add", "-A")
        git(self.wt, "commit", "-q", "-m", "symlink")
        code, out = self.run_script("--worktree", "sub/viec", "--test", PASS)
        self.assertEqual((code, out["status"]), (2, "can-hoi"))
        self.assertIn("docs-link", out["sensitive"])

    def test_commit_flag_refuses_secret_like_files(self):
        (self.wt / ".env").write_text("TOKEN=abc\n")
        (self.wt / "new.py").write_text("z = 1\n")
        code, out = self.run_script("--worktree", "sub/viec", "--test", PASS, "--commit", "gom hết")
        self.assertEqual((code, out["status"]), (2, "can-hoi"))
        self.assertEqual(out["secret_like"], [".env"])
        self.assertEqual(git(self.wt, "rev-parse", "HEAD"), git(self.repo, "rev-parse", "HEAD"))

    def test_a_slow_test_is_stopped_with_its_children(self):
        self.commit_in_wt("app.py", "x = 8\n")
        marker = self.tmp / "con-van-song"
        slow = (f"import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', "
                f"'import time; time.sleep(3); open(r\"{marker}\", \"w\").write(\"x\")']); time.sleep(30)")
        code, out = self.run_script("--worktree", "sub/viec", "--test", f"{sys.executable} -c \"{slow}\"",
                                    "--timeout", "1")
        self.assertEqual((code, out["status"]), (1, "test-truot"))
        import time
        time.sleep(4)
        self.assertFalse(marker.exists(), "tiến trình cháu phải bị dừng cùng nhóm")

    def test_non_fast_forward_needs_the_user(self):
        self.commit_in_wt("app.py", "x = 4\n")
        (self.repo / "other.py").write_text("y\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "phiên chính commit tiếp")
        code, out = self.run_script("--worktree", "sub/viec", "--test", PASS)
        self.assertEqual((code, out["status"]), (2, "can-hoi"))
        self.assertIn("fast-forward", out["reason"])

    def test_uncommitted_work_in_the_worktree_needs_a_commit_message(self):
        (self.wt / "new.py").write_text("z = 1\n")
        code, out = self.run_script("--worktree", "sub/viec", "--test", PASS)
        self.assertEqual((code, out["status"]), (2, "can-hoi"))
        code, out = self.run_script("--worktree", "sub/viec", "--test", PASS, "--commit", "thêm new.py")
        self.assertEqual((code, out["status"]), (0, "da-gop"), out)
        self.assertTrue((self.repo / "new.py").exists())

    def test_overlapping_uncommitted_files_in_the_main_tree_need_the_user(self):
        self.commit_in_wt("app.py", "x = 5\n")
        (self.repo / "app.py").write_text("x = 'đang sửa dở'\n")
        code, out = self.run_script("--worktree", "sub/viec", "--test", PASS)
        self.assertEqual((code, out["status"]), (2, "can-hoi"))
        self.assertEqual(out["overlap"], ["app.py"])
        (self.repo / "app.py").write_text("x = 1\n")
        (self.repo / "notes.txt").write_text("ghi chú chưa commit\n")  # không trùng: vẫn gộp được
        code, out = self.run_script("--worktree", "sub/viec", "--test", PASS)
        self.assertEqual(out["status"], "da-gop", out)
        self.assertTrue((self.repo / "notes.txt").exists())

    def test_only_worktrees_of_this_repo_are_accepted(self):
        other = self.tmp / "other"
        other.mkdir()
        git(other, "init", "-q")
        for target in (str(other), "khong-co-nhanh", str(self.repo)):
            with self.subTest(target=target):
                code, out = self.run_script("--worktree", target, "--test", PASS)
                self.assertEqual((code, out["status"]), (1, "loi"))

    def test_test_command_runs_without_a_shell(self):
        self.commit_in_wt("app.py", "x = 6\n")
        marker = self.tmp / "pwned"
        code, out = self.run_script("--worktree", "sub/viec", "--test", f"{PASS} ; touch {marker}")
        self.assertFalse(marker.exists())

    def test_empty_branch_is_cleaned_up(self):
        code, out = self.run_script("--worktree", "sub/viec", "--test", PASS)
        self.assertEqual((code, out["status"]), (0, "rong"))
        self.assertFalse(self.wt.exists())


if __name__ == "__main__":
    unittest.main()
