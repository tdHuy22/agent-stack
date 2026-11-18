"""Review opus·xhigh 18/11 của chốt chặn thư mục chạy không biết trước (nhánh cwd-glob-guard): câu hỏi không được dùng
hết lời nhắc mức vừa của lượt; `cd` có thể thất bại (`popd`, `cd -`, `cd t*`) thì lệnh sau `;` vẫn chạy ở thư mục cũ nên
vẫn bị chặn; `receipt.py run … > sổ khóa` không được hạ từ chặn xuống hỏi; `cp x .` sau `cd "$X"` không hỏi thừa."""
import tests.test_cwd_glob_guard as base
from tests._util import git
from tests.test_guard import GuardBase
from tests.test_ratchet import write_lock

R = base.R


class UnknownRunDirReview(GuardBase):
    assertAsks = base.UnknownRunDir.assertAsks

    def setUp(self):
        super().setUp()
        tests = self.project / "tests"
        tests.mkdir()
        (tests / "test_a.py").write_text(base.A_TEST)
        (tests / "test_b.py").write_text(base.B_TEST)
        (self.project / "tools").mkdir()
        write_lock(self.project, "vua", "tests/test_a.py")
        write_lock(self.project, "cao", "tests/test_b.py")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "lock")

    def test_question_does_not_use_up_medium_level_nudge(self):
        self.start("làm tiếp", "r1")
        self.assertAsks("cd \"$X\" && echo x > test_a.py", "r1", "tests/test_a.py")
        out = self.bash("sed -i '' s/1/2/ tests/test_a.py", "r1")
        self.assertEqual(out and out[0], "deny", out)

    def test_failed_dir_change_keeps_old_dir(self):
        self.start("làm tiếp", "r2")
        for cmd in ["popd 2>/dev/null; rm tests/test_b.py", "pushd; rm tests/test_b.py", "cd - && rm tests/test_b.py",
                    "cd t* ; rm tests/test_b.py", "cd tests && popd; rm test_b.py"]:
            with self.subTest(cmd=cmd):
                out = self.bash(cmd, "r2")
                self.assertEqual(out and out[0], "deny", f"{cmd} -> {out}")
        # Không đụng test khóa ở cả hai thư mục thì vẫn như cũ.
        for cmd in ["cd - && git status", "popd; ls", "cd t* && python3 -m unittest"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd, "r2"), cmd)

    def test_outer_redirect_to_lock_book_still_denied(self):
        self.start("làm tiếp", "r3")
        out = self.bash(f"{R} run --project \"$(pwd)\" -- echo '{{}}' > .agent/test-lock.json", "r3")
        self.assertEqual(out and out[0], "deny", out)

    def test_copy_into_dot_after_unknown_cd_does_not_ask(self):
        self.start("làm tiếp", "r4")
        for cmd in ["cd \"$X\" && cp /etc/hosts .", "cd \"$(mktemp -d)\" && cp -r ../src .",
                    "cd \"$X\" && mv foo.txt ./", "cd \"$X\" && cp a.txt sub/"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd, "r4"), cmd)
        self.assertAsks("cd \"$X\" && cp /tmp/test_b.py .", "r4", "tests/test_b.py")
