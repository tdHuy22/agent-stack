"""Hook pretool_guard với test đã khóa (GĐ2, câu 3): mức vừa nhắc một lần mỗi lượt, mức cao chặn, chỉ thêm dòng thì
qua; sổ khóa không sửa tay được; `receipt.py unlock` chỉ qua khi tin người dùng bảo mở khóa đúng file."""
import json

from tests._util import git
from tests.test_guard import GuardBase
from tests.test_ratchet import write_lock

A_TEST = "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_a(self):\n        self.assertEqual(1, 1)\n"
B_TEST = A_TEST.replace("test_a", "test_b")


class LockedTestGuard(GuardBase):
    def setUp(self):
        super().setUp()
        tests = self.project / "tests"
        tests.mkdir()
        (tests / "test_a.py").write_text(A_TEST)
        (tests / "test_b.py").write_text(B_TEST)
        # Ghi sổ theo định dạng hợp đồng, không import testlock: test trượt ở assert trên code trước GĐ2.
        write_lock(self.project, "vua", "tests/test_a.py")
        write_lock(self.project, "cao", "tests/test_b.py")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "lock")

    def edit(self, rel, old, new, sid="g1"):
        return self.guard("Edit", {"file_path": str(self.project / rel), "old_string": old, "new_string": new}, sid)

    def test_adding_a_test_to_a_locked_file_passes(self):
        add = "        self.assertEqual(1, 1)\n\n    def test_more(self):\n        self.assertTrue(True)\n"
        self.assertIsNone(self.edit("tests/test_b.py", "        self.assertEqual(1, 1)\n", add))
        self.assertIsNone(self.guard("Write", {"file_path": str(self.project / "tests/test_b.py"),
                                               "content": B_TEST + "\n    def test_c(self):\n        pass\n"}))

    def test_loosening_medium_level_test_is_nudged_once_per_turn(self):
        self.start("làm tiếp", "m1")
        first = self.edit("tests/test_a.py", "assertEqual(1, 1)", "assertTrue(1)", "m1")
        self.assertEqual(first[0], "deny")
        self.assertIn("test đã khóa (mức vừa)", first[1])
        self.assertIn("receipt.py unlock tests/test_a.py", first[1])
        self.assertIsNone(self.edit("tests/test_a.py", "assertEqual(1, 1)", "assertTrue(1)", "m1"),
                          "nhắc chỉ một lần mỗi lượt")

    def test_loosening_high_level_test_is_always_blocked(self):
        self.start("làm tiếp", "h1")
        for _ in range(2):
            out = self.edit("tests/test_b.py", "assertEqual(1, 1)", "assertTrue(1)", "h1")
            self.assertEqual(out[0], "deny")
            self.assertIn("mức rủi ro cao", out[1])
        out = self.guard("Write", {"file_path": str(self.project / "tests/test_b.py"), "content": "pass\n"}, "h1")
        self.assertEqual(out[0], "deny")

    def test_lock_book_cannot_be_edited_directly(self):
        book = str(self.project / ".agent" / "test-lock.json")
        self.assertEqual(self.guard("Write", {"file_path": book, "content": "{}"})[0], "deny")
        self.assertEqual(self.guard("Edit", {"file_path": book, "old_string": "cao", "new_string": "vua"})[0], "deny")
        for cmd in ["echo '{}' > .agent/test-lock.json", "rm .agent/test-lock.json",
                    "python3 -c 'open(\".agent/test-lock.json\",\"w\")' .agent/test-lock.json",
                    "sed -i '' s/cao/vua/ .agent/test-lock.json"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash(cmd)[0], "deny")
        for cmd in ["cat .agent/test-lock.json", "git add .agent/test-lock.json", "git diff .agent/test-lock.json",
                    "python3 plugin/skills/session-keeper/scripts/receipt.py locks",
                    "cp .agent/test-lock.json /tmp/backup.json"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd))

    def test_shell_commands_that_rewrite_locked_tests(self):
        self.start("làm tiếp", "s1")
        for cmd in ["rm tests/test_b.py", "sed -i '' 's/1, 1/1, 2/' tests/test_b.py", "echo pass > tests/test_b.py",
                    "rm -rf tests", "git checkout HEAD~1 -- tests/test_b.py", "git rm tests/test_b.py",
                    "mv tests/test_b.py /tmp/x.py", "cp /tmp/x.py tests/test_b.py", "perl -pi -e s/1/2/ tests/test_b.py",
                    "rm tests/*.py", "cd tests && rm test_b.py", "sed -i '' s/1/2/ tests/test_?.py",
                    "git -C tests rm test_b.py", "git -C tests checkout HEAD~1 -- test_b.py",
                    "pushd tests && rm test_b.py", "cp plugin/skills/session-keeper/scripts/receipt.py tests/test_b.py",
                    "echo '    def test_c(self): pass' >> tests/test_b.py"]:
            with self.subTest(cmd=cmd):
                out = self.bash(cmd, "s1")
                self.assertEqual(out and out[0], "deny", cmd)
        for cmd in ["cat tests/test_b.py", "python3 -m unittest tests.test_b", "grep -n assert tests/test_a.py",
                    "cp tests/test_b.py /tmp/copy.py"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd, "s1"))

    def test_unlock_needs_the_user_to_name_the_file(self):
        cmd = "python3 plugin/skills/session-keeper/scripts/receipt.py unlock --reason 'bạn duyệt' tests/test_b.py"
        self.start("làm tiếp đi", "u1")
        self.assertEqual(self.bash(cmd, "u1")[0], "deny")
        self.start("mở khóa tests/test_a.py", "u2")
        self.assertEqual(self.bash(cmd, "u2")[0], "deny", "tin nêu file khác")
        self.start("đừng mở khóa tests/test_b.py", "u3")
        self.assertEqual(self.bash(cmd, "u3")[0], "deny", "phủ định")
        self.start("Đồng ý, mở khóa tests/test_b.py", "u4")
        self.assertIsNone(self.bash(cmd, "u4"))

    def test_unlock_is_not_opened_by_any_later_reply(self):
        # Reviewer 13/11: khác git push, trả lời "không" hay một câu hỏi sau lần chặn không mở khóa được.
        cmd = "python3 plugin/skills/session-keeper/scripts/receipt.py unlock --reason 'bạn duyệt' tests/test_b.py"
        self.start("làm tiếp", "r1")
        self.assertEqual(self.bash(cmd, "r1")[0], "deny")
        for reply in ["không, đừng mở khóa", "sao test lại sai?", "ok"]:
            with self.subTest(reply=reply):
                self.start(reply, "r1")
                self.assertEqual(self.bash(cmd, "r1")[0], "deny")
        self.start("mở khóa tests/test_b.py", "r1")
        self.assertIsNone(self.bash(cmd, "r1"))
        self.assertEqual(self.bash(cmd, "r1")[0], "deny", "một tin chỉ mở một lần")
        receipts = json.loads((self.state / "unlock-consents.json").read_text())
        self.assertEqual([(r["path"], r["top"]) for r in receipts], [("tests/test_b.py", str(self.project.resolve()))])

    def test_unlock_through_a_runner_is_still_gated(self):
        self.start("làm tiếp", "w1")
        for cmd in ["uv run python3 -X utf8 plugin/skills/session-keeper/scripts/receipt.py unlock --reason x "
                    "tests/test_b.py", "env python3 receipt.py unlock --reason x tests/test_b.py"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash(cmd, "w1")[0], "deny")

    def test_edit_that_inserts_a_return_is_not_tightening(self):
        out = self.edit("tests/test_b.py", "    def test_b(self):\n", "    def test_b(self):\n        return\n")
        self.assertEqual(out[0], "deny")

    def test_bad_targets_do_not_disable_other_guards(self):
        # Reviewer 13/11: đích lạ (~người dùng không có, tên quá dài) làm hook văng lỗi thì mọi chốt chặn khác tắt theo.
        for target in ["~nosuchuser_zz/x", "a" * 300]:
            with self.subTest(target=target[:20]):
                out = self.bash(f"echo hi > {target}; git push --force origin main")
                self.assertEqual(out and out[0], "deny")

    def test_heredoc_and_glued_redirects_are_seen(self):
        # Reviewer 14/11: chuyển hướng trên dòng mở heredoc hay dính liền chữ trước từng lọt qua.
        for cmd in ["cat <<'EOF' > tests/test_b.py\npass\nEOF", "cat <<EOF >tests/test_b.py\npass\nEOF",
                    "cat <<'EOF' | tee tests/test_b.py\npass\nEOF", "python3 - <<'EOF' > tests/test_b.py\nx\nEOF",
                    "cat <<'EOF' > .agent/test-lock.json\n{}\nEOF", "echo pass>tests/test_b.py",
                    "cat x>.agent/test-lock.json", "echo hi >|tests/test_b.py"]:
            with self.subTest(cmd=cmd):
                out = self.bash(cmd)
                self.assertEqual(out and out[0], "deny", cmd)

    def test_commands_run_through_receipt_are_checked(self):
        r = "python3 plugin/skills/session-keeper/scripts/receipt.py"
        self.start("làm tiếp", "rr")
        for cmd in [f"{r} run -- rm tests/test_b.py", f"{r} run -- sh -c 'echo > .agent/test-lock.json'",
                    f"{r} run -- {r} unlock --reason x tests/test_b.py"]:
            with self.subTest(cmd=cmd):
                out = self.bash(cmd, "rr")
                self.assertEqual(out and out[0], "deny", cmd)
        self.assertIsNone(self.bash(f"{r} run -- python3 -m unittest tests.test_b", "rr"))

    def test_glob_brace_and_directory_targets(self):
        for cmd in ["rm tests/test_{a,b}.py", "rm -rf .agent", "rm .agent/*.json", "rm .agent/test-lock*",
                    "git checkout HEAD~1 -- .agent", "dd if=/dev/null of=tests/test_b.py"]:
            with self.subTest(cmd=cmd):
                out = self.bash(cmd)
                self.assertIn(out and out[0], ("deny", "ask"), cmd)  # ask: test mức vừa khi chưa có lượt
        (self.project / "x.py").write_text("x = 1\n")
        for cmd in ["cp x.py tests/", "git restore --staged tests/test_b.py", "git rm --cached tests/test_b.py",
                    "rm app/*.pyc"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd))

    def test_multiedit_replace_all_and_notebook(self):
        path = str(self.project / "tests/test_b.py")
        add = {"old_string": "        self.assertEqual(1, 1)\n",
               "new_string": "        self.assertEqual(1, 1)\n\n    def test_c(self):\n        pass\n"}
        self.assertIsNone(self.guard("MultiEdit", {"file_path": path, "edits": [add]}))
        loosen = {"old_string": "1, 1", "new_string": "1, 2"}
        self.assertEqual(self.guard("MultiEdit", {"file_path": path, "edits": [add, loosen]})[0], "deny")
        self.assertEqual(self.guard("Edit", {"file_path": path, "old_string": "1", "new_string": "2",
                                             "replace_all": True})[0], "deny")
        self.assertEqual(self.guard("NotebookEdit", {"notebook_path": path, "new_source": "x"})[0], "deny")

    def test_broken_book_treats_test_files_as_locked(self):
        (self.project / ".agent" / "test-lock.json").write_text("{hỏng")
        out = self.edit("tests/test_a.py", "assertEqual(1, 1)", "assertTrue(1)")
        self.assertEqual(out[0], "deny")
        self.assertIsNone(self.guard("Write", {"file_path": str(self.project / "app" / "views.py"), "content": "x=2\n"}))

    def test_huge_locked_file_counts_as_changed_and_hook_stays_fast(self):
        big = self.project / "tests" / "test_big.py"
        big.write_text("# " + "x" * 1_100_000 + "\n")
        write_lock(self.project, "cao", "tests/test_big.py")
        out = self.guard("Write", {"file_path": str(big), "content": big.read_text() + "def test_x():\n    pass\n"})
        self.assertEqual(out and out[0], "deny")
        self.bash("rm -f tests/*.pyc app/*.pyc")
        self.assertLess(self.elapsed, 3.0, "hook phải nhanh (timeout 5 giây)")

    def test_second_review_round(self):
        r = "python3 plugin/skills/session-keeper/scripts/receipt.py"
        self.start("làm tiếp", "v2")
        deny = [f"{r} run rm tests/test_b.py", f"{r} run --timeout 5 rm tests/test_b.py",  # run không có `--`
                f"{r} run git push origin main",
                "python3 -c \"open('.agent/test-lock.json','w').write('{}')\"", "node -e 'x' .agent/test-lock.json",
                "python3 - <<'EOF'\nopen('.agent/test-lock.json','w')\nEOF",
                "rm -rf *", "rm -rf ./*", "echo x>|tests/test_b.py", "echo x> tests/test_b.py",
                "echo x >&tests/test_b.py", f"{r} locks > tests/test_b.py", "echo pass receipt.py show > tests/test_b.py"]
        for cmd in deny:
            with self.subTest(cmd=cmd):
                out = self.bash(cmd, "v2")
                self.assertIn(out and out[0], ("deny", "ask"), cmd)
        allow = ["git add .agent/test-lock.json && python3 -m unittest tests.test_b", "git checkout -- .",
                 "git restore .", "git checkout -- tests/test_b.py", f"{r} locks"]
        for cmd in allow:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd, "v2"), cmd)

    def test_long_names_do_not_disable_other_guards(self):
        out = self.bash("cp tests/test_a.py " + "a" * 300 + " ; git push --force origin main")
        self.assertEqual(out and out[0], "deny")

    def test_unlock_by_bare_name_is_refused_when_ambiguous(self):
        (self.project / "tests" / "unit").mkdir()
        (self.project / "tests" / "unit" / "test_b.py").write_text(B_TEST)
        write_lock(self.project, "cao", "tests/unit/test_b.py")
        cmd = "python3 plugin/skills/session-keeper/scripts/receipt.py unlock --reason x tests/test_b.py"
        self.start("mở khóa test_b.py", "amb")
        self.assertEqual(self.bash(cmd, "amb")[0], "deny", "tên cuối trùng hai file khóa: phải nêu đường dẫn")
        self.start("mở khóa tests/test_b.py", "amb2")
        self.assertIsNone(self.bash(cmd, "amb2"))
        self.assertEqual(self.bash(cmd.replace("tests/test_b.py", "./tests/test_b.py"), "amb2")[0], "deny",
                         "cùng file viết khác vẫn chỉ một lần mỗi tin")

    def test_project_without_lock_book_is_unaffected(self):
        (self.project / ".agent" / "test-lock.json").unlink()
        self.assertIsNone(self.edit("tests/test_b.py", "assertEqual(1, 1)", "assertTrue(1)"))
        self.assertIsNone(self.bash("rm tests/test_b.py"))
