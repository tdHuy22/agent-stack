"""Chốt chặn test khóa khi thư mục chạy không biết trước (việc sau của tám quan sát GĐ6): `cd`, `pushd`, `receipt.py
--cwd`, `--project` có glob, biến hay lệnh con (`cd t*`, `--cwd $PWD/tests`) thì hook không biết thư mục thật. Lệnh có
thể đụng test đã khóa (đích khớp một mục sổ khi coi phần không biết là bất kỳ) thì hỏi người dùng thay vì cho qua; lệnh
thường ngày không đụng test khóa thì không hỏi. Viết trước bản sửa."""
from tests._util import git
from tests.test_guard import GuardBase
from tests.test_ratchet import write_lock

A_TEST = "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_a(self):\n        self.assertEqual(1, 1)\n"
B_TEST = A_TEST.replace("test_a", "test_b")
R = "python3 plugin/skills/session-keeper/scripts/receipt.py"


class UnknownRunDir(GuardBase):
    def setUp(self):
        super().setUp()
        tests = self.project / "tests"
        tests.mkdir()
        (tests / "test_a.py").write_text(A_TEST)
        (tests / "test_b.py").write_text(B_TEST)
        (self.project / "tools").mkdir()
        write_lock(self.project, "vua", "tests/test_a.py")
        write_lock(self.project, "cao", "tests/test_b.py")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "lock")

    def assertAsks(self, cmd, sid="u1", *needles):
        out = self.bash(cmd, sid)
        self.assertEqual(out and out[0], "ask", f"{cmd} -> {out}")
        for needle in needles:
            self.assertIn(needle, out[1])
        return out

    def test_glob_or_variable_in_cwd_flag_asks(self):
        self.start("làm tiếp", "u1")
        for cmd in [f"{R} run --cwd t* -- rm test_b.py", f"{R} run --cwd $PWD/tests -- rm test_b.py",
                    f"{R} run --cwd=te?ts -- sed -i '' s/1/2/ test_b.py", f"{R} lock --cwd \"$T\" -- rm test_b.py",
                    f"{R} fails-before --cwd '{{tests,tools}}' -- rm test_b.py",
                    f"{R} run --project $P -- rm tests/test_b.py"]:
            with self.subTest(cmd=cmd):
                self.assertAsks(cmd, "u1", "tests/test_b.py")

    def test_glob_or_variable_in_cd_target_asks(self):
        self.start("làm tiếp", "u2")
        for cmd in ["cd t* && rm test_b.py", "cd $PWD/tests && rm test_b.py", "pushd te[s]ts && rm test_b.py",
                    "cd \"$(git rev-parse --show-toplevel)\" && rm tests/test_b.py",
                    "cd $(dirname \"$f\") && echo pass > test_b.py", "cd \"$X\" && git rm -r tests",
                    "cd \"$X\" && rm *_b.py", "cd \"$X\" && cd tests && rm test_b.py",
                    "cd \"$X\" && git rm tests/test_b.py"]:
            with self.subTest(cmd=cmd):
                self.assertAsks(cmd, "u2")

    def test_lock_book_behind_unknown_dir_asks(self):
        for cmd in ["cd .ag* && rm test-lock.json", "cd \"$X\" && echo '{}' > .agent/test-lock.json"]:
            with self.subTest(cmd=cmd):
                self.assertAsks(cmd, "u3", "test-lock.json")

    def test_medium_level_locked_test_asks_too(self):
        self.assertAsks("cd t* && rm test_a.py", "u4", "tests/test_a.py")

    def test_everyday_commands_after_unknown_cd_do_not_ask(self):
        self.start("làm tiếp", "u5")
        (self.project / "foo.txt").write_text("x\n")
        for cmd in ["cd \"$X\" && python3 -m unittest discover", "cd \"$X\" && rm -f .tmp/build.log",
                    "cd \"$X\" && make > build.log 2>&1", "cd \"$(git rev-parse --show-toplevel)\" && git status",
                    "cd t* && rm foo.txt", "cd \"$X\" && rm -f \"$X\"/out.txt", "cd \"$d\" && touch x && rm x",
                    "cd t* && cat test_b.py", "cd \"$X\" && git diff tests/test_b.py",
                    f"{R} run --cwd $PWD -- python3 -m unittest tests.test_b",
                    f"{R} run --cwd t* -- python3 -m unittest test_b",
                    f"{R} run --cwd \"$X\" -- rm -f build.log"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd, "u5"), cmd)

    def test_known_dirs_keep_their_old_answers(self):
        self.start("làm tiếp", "u6")
        # Thư mục biết rõ, đích tuyệt đối, hay glob ở cả tên file (so mẫu với sổ như `rm tests/*.py`) vẫn chặn như cũ.
        for cmd in ["cd tests && rm test_b.py", f"{R} run --cwd tests -- rm test_b.py", "rm tests/test_b.py",
                    f"cd t* && rm {self.project}/tests/test_b.py", "cd t* && rm *_b.py",
                    "cd t* && rm ../tests/test_b.py", "cd \"$X\" && rm ../tests/test_b.py"]:
            with self.subTest(cmd=cmd):
                out = self.bash(cmd, "u6")
                self.assertEqual(out and out[0], "deny", cmd)

    def test_other_gates_still_win_over_the_question(self):
        # Câu hỏi về test khóa đứng sau cổng lệnh không đảo ngược: không thay lời nhắc `git push`, `rm -rf` bằng câu hỏi.
        self.start("làm tiếp", "u8")
        out = self.bash("cd \"$X\" && git rm -r tests && git push origin main", "u8")
        self.assertEqual(out and out[0], "deny")
        self.assertIn("không đảo ngược", out[1])
        # Project nằm trong thư mục tạm của hệ điều hành (fails-before chép repo ra đó) thì `rm -rf` không qua cổng: khi
        # đó vẫn phải hỏi về test khóa.
        in_temp = str(self.project.resolve()).startswith(("/tmp/", "/private/tmp/", "/private/var/folders/",
                                                           "/var/folders/"))
        out = self.bash("cd \"$X\" && rm -rf tests", "u8")
        self.assertEqual(out and out[0], "ask" if in_temp else "deny")
        self.assertIn("test đã khóa" if in_temp else "không đảo ngược", out[1])
        out = self.bash("cd \"$X\" && rm -rf .", "u8")  # xóa cả thư mục đang đứng: luôn qua cổng
        self.assertEqual(out and out[0], "deny")
        self.assertIn("không đảo ngược", out[1])

    def test_project_without_lock_book_is_unaffected(self):
        plain = self.tmp / "plain"
        (plain / "tests").mkdir(parents=True)
        (plain / "tests" / "test_b.py").write_text(B_TEST)
        git(plain, "init", "-q")
        out = self.hook("pretool_guard.py", {"session_id": "u7", "cwd": str(plain), "tool_name": "Bash",
                                             "tool_input": {"command": "cd t* && rm test_b.py; cd \"$X\" && git rm -r tests"},
                                             "hook_event_name": "PreToolUse"})
        self.assertIsNone(out)

    def test_review_dotdot_redirects_flags_and_dir_stack(self):
        # Review sonnet·high 17/11: `..` sau chỗ không biết không được gộp mất; `cd`, `pushd` kèm chuyển hướng hay cờ,
        # `builtin cd`, `cd -`, `popd` vẫn đổi thư mục chạy (về chỗ không biết khi không đoán được).
        self.start("làm tiếp", "u9")
        for cmd in ["cd \"$X/..\" && rm test_b.py", f"{R} run --cwd \"$X/..\" -- rm test_b.py",
                    "pushd \"$X\" >/dev/null && rm test_b.py", "cd \"$X\" 2>/dev/null && rm test_b.py",
                    "cd t* >/dev/null && rm test_b.py", "cd -- \"$X\" && rm test_b.py", "cd -L \"$X\" && rm test_b.py",
                    "builtin cd \"$X\" && rm test_b.py", "cd - && rm test_b.py", "popd && rm tests/test_b.py",
                    "cd tests && popd && rm tests/test_b.py"]:
            with self.subTest(cmd=cmd):
                self.assertAsks(cmd, "u9", "tests/test_b.py")
        # Chồng pushd và OLDPWD trong cùng chuỗi lệnh thì biết chắc thư mục: chặn như thư mục biết rõ.
        for cmd in ["cd tests >/dev/null && rm test_b.py", "cd -P tests && rm test_b.py",
                    "pushd tests > /dev/null && rm test_b.py", "cd -- tests && rm test_b.py",
                    "pushd tests && popd && rm tests/test_b.py", "cd tests && cd /tmp && cd - && rm test_b.py"]:
            with self.subTest(cmd=cmd):
                out = self.bash(cmd, "u9")
                self.assertEqual(out and out[0], "deny", cmd)
        for cmd in ["cd \"$X\" >/dev/null && python3 -m unittest", "pushd \"$X\" >/dev/null && make > build.log",
                    "cd - && git status", "pushd tests && popd && cat tests/test_b.py"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd, "u9"), cmd)

    def test_unknown_user_home_does_not_crash_the_hook(self):
        # Review lại 17/11: `~user` không có làm `Path.expanduser` ném lỗi, hook sập im lặng và mọi chốt chặn tắt.
        self.start("làm tiếp", "u10")
        for cmd in ["cd ~nosuchuser_zz && git push origin main", "git -C ~nosuchuser_zz push origin main",
                    "pushd ~nosuchuser_zz; git push origin main"]:
            with self.subTest(cmd=cmd):
                out = self.bash(cmd, "u10")
                self.assertEqual(out and out[0], "deny", cmd)
        for cmd in ["cd ~nosuchuser_zz; rm tests/test_b.py", "pushd ~nosuchuser_zz/x >/dev/null; rm tests/test_b.py"]:
            with self.subTest(cmd=cmd):
                self.assertAsks(cmd, "u10", "tests/test_b.py")
        out = self.bash("claude plugin marketplace add ~nosuchuser_zz/market", "u10")
        self.assertEqual(out and out[0], "ask")
