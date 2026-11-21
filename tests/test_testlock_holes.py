"""Vá lỗ có từ trước của chốt chặn test khóa, phần 2 (spec khoa-test-lo-cu, TM-172, TM-173): `cd` trong subshell hay
ống, `env -C`, tên viết hoa khác trên hệ file không phân biệt hoa thường, ngoặc nhọn bung quá nhiều, `--project`/`--cwd`
có biến, gán `HOME=`/`CDPATH=`, và `receipt.py unlock` có chuyển hướng. Mọi lệnh chỉ là chuỗi gửi cho hook, không chạy
thật. Viết trước bản sửa."""
import json
import os
import subprocess
import time

from tests._util import git
from tests.test_guard import HOOKS, GuardBase
from tests.test_ratchet import write_lock

A_TEST = "import unittest\n\n\nclass T(unittest.TestCase):\n    def test_a(self):\n        self.assertEqual(1, 1)\n"
B_TEST = A_TEST.replace("test_a", "test_b")
R = "python3 plugin/skills/session-keeper/scripts/receipt.py"
BLOCKED = ("deny", "ask")


class HoleBase(GuardBase):
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

    def bash_in(self, command, sid="h1", cwd=None, **env):
        """Như self.bash nhưng chọn thư mục làm việc của hook (trường cwd của payload) và đo giờ chạy."""
        payload = {"session_id": sid, "cwd": str(cwd or self.project), "tool_name": "Bash",
                   "tool_input": {"command": command}, "hook_event_name": "PreToolUse"}
        t0 = time.monotonic()
        try:
            out = subprocess.run(["python3", str(HOOKS / "pretool_guard.py")], input=json.dumps(payload),
                                 capture_output=True, text=True, env=self.env(**env), timeout=10)
        except subprocess.TimeoutExpired:
            self.fail(f"hook chạy quá 10 giây (timeout thật là 5): {command[:80]!r}")
        self.wall = time.monotonic() - t0
        self.assertEqual((out.returncode, out.stderr), (0, ""))
        if not out.stdout.strip():
            return None
        res = json.loads(out.stdout)["hookSpecificOutput"]
        return res["permissionDecision"], res["permissionDecisionReason"]

    def assertBlocked(self, cmd, allowed=BLOCKED, cwd=None, sid="h1"):
        out = self.bash_in(cmd, sid, cwd)
        self.assertIn(out and out[0], allowed, f"{cmd!r} -> {out}")
        return out

    def assertPasses(self, cmd, cwd=None, sid="h1"):
        self.assertIsNone(self.bash_in(cmd, sid, cwd), cmd)


class SubshellCd(HoleBase):
    # spec:khoa-test-lo-cu#S1
    def test_cd_inside_subshell_does_not_move_later_commands(self):
        self.start("làm tiếp", "h1")
        for cmd in ["(cd tools && true) && rm tests/test_b.py", "(cd tools); rm tests/test_b.py",
                    "(cd tools && true) && echo pass > tests/test_b.py",
                    "(cd tools && true) && sed -i '' s/1/2/ tests/test_b.py"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, ("deny",))

    # spec:khoa-test-lo-cu#S1
    def test_cd_in_one_side_of_a_pipe_does_not_move_later_commands(self):
        self.start("làm tiếp", "h1")
        for cmd in ["cd tools | cat && rm tests/test_b.py", "cd tools | cat; rm tests/test_b.py",
                    "echo x | cd tools; rm tests/test_b.py"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, ("deny",))

    # spec:khoa-test-lo-cu#S1
    def test_cd_inside_shell_dash_c_does_not_move_later_commands(self):
        self.start("làm tiếp", "h1")
        for cmd in ["bash -c 'cd tools && true' && rm tests/test_b.py", "sh -c 'cd tools'; rm tests/test_b.py",
                    "sh -c \"cd tools && true\" && rm tests/test_b.py"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, ("deny",))

    # spec:khoa-test-lo-cu#S1
    def test_plain_cd_still_moves_and_harmless_subshell_passes(self):
        self.start("làm tiếp", "h1")
        self.assertPasses("(cd tools && make)")
        self.assertPasses("bash -c 'cd tools && make'")
        self.assertPasses("cd tools | cat")
        self.assertBlocked("cd tests && rm test_b.py", ("deny",))  # cd thường vẫn đổi thư mục: không chặn nhầm kiểu mới
        self.assertPasses("cd tools && rm helper.py")


class EnvChdir(HoleBase):
    # spec:khoa-test-lo-cu#S2
    def test_env_dash_C_moves_the_target_into_locked_tests(self):
        self.start("làm tiếp", "h1")
        for cmd in ["env -C tests rm test_b.py", "env --chdir=tests rm test_b.py", "env -C tests sed -i '' s/1/2/ test_b.py",
                    "env -C tests rm -f test_b.py"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, ("deny",))

    # spec:khoa-test-lo-cu#S2
    def test_env_dash_C_other_dir_still_passes(self):
        self.start("làm tiếp", "h1")
        for cmd in ["env -C tools make", "env --chdir=tools make", "env -C tools rm helper.py", "env FOO=1 make"]:
            with self.subTest(cmd=cmd):
                self.assertPasses(cmd)

    # spec:khoa-test-lo-cu#S2
    def test_env_dash_C_then_cd_still_resolves_relative_to_new_dir(self):
        self.start("làm tiếp", "h1")
        self.assertBlocked("cd tools && env -C ../tests rm test_b.py", ("deny",))


class CaseInsensitive(HoleBase):
    def setUp(self):
        super().setUp()
        # Chỉ có nghĩa trên hệ file không phân biệt hoa thường (APFS mặc định); không thì bỏ qua.
        if not (self.project / "TESTS" / "test_b.py").exists():
            self.skipTest("hệ file phân biệt hoa thường: S3 không áp dụng")

    # spec:khoa-test-lo-cu#S3
    def test_different_case_directory_or_file_name_is_blocked(self):
        self.start("làm tiếp", "h1")
        for cmd in ["rm TESTS/test_b.py", "rm tests/TEST_B.py", "rm Tests/Test_B.py",
                    "echo pass > TESTS/test_b.py", "sed -i '' s/1/2/ tests/TEST_B.py", "mv TESTS/test_b.py /tmp/x.py"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, ("deny",))

    # spec:khoa-test-lo-cu#S3
    def test_different_case_via_cd_is_blocked_and_reads_pass(self):
        self.start("làm tiếp", "h1")
        self.assertBlocked("cd TESTS && rm test_b.py", ("deny",))
        self.assertBlocked("cd tests && rm TEST_B.py", ("deny",))
        for cmd in ["cat TESTS/test_b.py", "grep -n assert tests/TEST_B.py"]:
            with self.subTest(cmd=cmd):
                self.assertPasses(cmd)


class BraceExplosion(HoleBase):
    # `{,}` nhân số mẫu mà không đổi tên: `tests/{test_b.py,zz}` + n lần `{,}` bung ra 2^(n+1) mẫu, trong đó 2^n mẫu
    # là đúng `tests/test_b.py`. Trên code cũ hook vẫn chặn đúng nhưng chậm theo cấp số nhân (dbl16 ~7 giây,
    # lồng nhiều tầng quá 60 giây), mà app bỏ hook sau 5 giây rồi cho lệnh chạy.
    def timed(self, cmd, cwd=None):
        out = self.bash_in(cmd, "h1", cwd)
        self.assertLess(self.wall, 2.0, f"hook phải trả lời dưới 2 giây (timeout 5), mất {self.wall:.2f}s: {cmd[:70]}")
        return out

    # spec:khoa-test-lo-cu#S4
    def test_many_pieces_in_rm_target_answer_fast_and_block(self):
        self.start("làm tiếp", "h1")
        for cmd in ["rm tests/{test_b.py,zz}" + "{,}" * 16,  # 131072 mẫu
                    "rm {tests,a,b,c,d,e,f,g}/{test_b.py,a,b,c,d,e,f,g}" + "{,}" * 11]:  # 131072 mẫu, nhiều mảnh
            with self.subTest(cmd=cmd[:60]):
                out = self.timed(cmd)
                self.assertIn(out and out[0], BLOCKED, f"{out}")

    # spec:khoa-test-lo-cu#S4
    def test_nested_brace_levels_answer_fast_and_block(self):
        self.start("làm tiếp", "h1")
        level = "{{{,},{,}},{{,},{,}}}"  # 8 mẫu mỗi tầng
        for cmd in [f"rm tests/{level * 3}{{test_b.py,zz}}", f"rm tests/{level * 2}{{test_b.py,zz}}{{,}}{{,}}{{,}}{{,}}"]:
            with self.subTest(cmd=cmd[:60]):
                out = self.timed(cmd)
                self.assertIn(out and out[0], BLOCKED, f"{out}")

    # spec:khoa-test-lo-cu#S4
    def test_piece_beyond_the_fiftieth_alternative_is_not_dropped(self):
        self.start("làm tiếp", "h1")
        cmd = "rm tests/{" + ",".join(str(i) for i in range(60)) + ",test_b.py}"
        out = self.timed(cmd)
        self.assertIn(out and out[0], BLOCKED, f"{out}")

    # spec:khoa-test-lo-cu#S4
    def test_huge_brace_in_cd_target_answers_fast_and_does_not_pass(self):
        self.start("làm tiếp", "h1")
        for cmd in ["cd {tests,zz}" + "{,}" * 16 + " && rm test_b.py",
                    "cd {tests,zz}" + "{{,},{,}}" * 8 + " && rm test_b.py"]:
            with self.subTest(cmd=cmd[:60]):
                out = self.timed(cmd)
                self.assertIn(out and out[0], BLOCKED, f"{out}")

    # spec:khoa-test-lo-cu#S4
    def test_huge_brace_unrelated_to_locked_tests_still_answers_fast(self):
        self.start("làm tiếp", "h1")
        out = self.timed("rm app/{x,y}" + "{,}" * 16)
        self.assertIn(out and out[0], (None, "ask", "deny"))  # qua hay hỏi đều được: điều bắt buộc là nhanh


class ReceiptVariableDir(HoleBase):
    # spec:khoa-test-lo-cu#S5
    def test_project_or_cwd_with_variable_and_relative_locked_target(self):
        self.start("làm tiếp", "h1")
        for cmd in [f"{R} run --project $PWD/tests -- sed -i '' s/1/2/ test_b.py",
                    f"{R} run --cwd \"$HOME/x\" -- rm test_b.py", f"{R} run --cwd \"$HOME/x\" -- rm tests/test_b.py",
                    f"{R} run --project \"$HOME/x\" -- rm test_b.py", f"{R} run --cwd=$PWD/tests -- rm test_b.py",
                    f"{R} run --project=$PWD/tests -- echo pass > test_b.py",
                    f"{R} run --project ${{PROJ}}/tests -- rm -f test_b.py"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd)

    # spec:khoa-test-lo-cu#S5
    def test_unrelated_inner_command_with_variable_dir_is_not_blocked_for_nothing(self):
        self.start("làm tiếp", "h1")
        for cmd in [f"{R} run --project $PWD/tools -- python3 -m unittest", f"{R} run --cwd \"$HOME/x\" -- make"]:
            with self.subTest(cmd=cmd):
                self.assertPasses(cmd)


class HomeAndCdpath(HoleBase):
    # spec:khoa-test-lo-cu#S6
    def test_assigned_home_then_tilde_target(self):
        self.start("làm tiếp", "h1")
        for cmd in ["HOME=$PWD && rm ~/tests/test_b.py", "export HOME=$PWD; rm ~/tests/test_b.py",
                    "HOME=$PWD; echo pass > ~/tests/test_b.py", "export HOME=.; sed -i '' s/1/2/ ~/tests/test_b.py",
                    "HOME=\"$PWD\" && rm -f ~/tests/test_b.py"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd)

    # spec:khoa-test-lo-cu#S6
    def test_assigned_cdpath_then_cd_without_slash(self):
        self.start("làm tiếp", "h1")
        for cmd in ["CDPATH=$PWD && cd tests && rm test_b.py", "export CDPATH=$PWD; cd tests && rm test_b.py",
                    "CDPATH=$PWD; cd tests; echo pass > test_b.py"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, cwd=self.project / "tools")

    # spec:khoa-test-lo-cu#S6
    def test_cdpath_dot_from_project_root(self):
        self.start("làm tiếp", "h1")
        for cmd in ["CDPATH=. cd tests; rm test_b.py", "CDPATH=. && cd tests && rm test_b.py",
                    "export CDPATH=.; cd tests && sed -i '' s/1/2/ test_b.py"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd)

    # spec:khoa-test-lo-cu#S6
    def test_plain_cd_and_unrelated_assignments_still_work(self):
        self.start("làm tiếp", "h1")
        self.assertPasses("FOO=1 && cd tools && make")
        self.assertPasses("export CDPATH=$PWD; cd tools && make", cwd=self.project / "tools")
        self.assertPasses("HOME=$PWD && ls ~/tools")


class UnlockRedirects(HoleBase):
    UNLOCK = f"{R} unlock --reason 'bạn duyệt' tests/test_b.py"

    # spec:khoa-test-lo-cu#S7
    def test_unlock_with_redirect_passes_after_user_names_the_file(self):
        for i, redirect in enumerate(["2>&1", "2>/dev/null", "> log.txt", ">> log.txt 2>&1", "&> log.txt"]):
            sid = f"u{i}"
            self.start("mở khóa tests/test_b.py", sid)
            with self.subTest(redirect=redirect):
                self.assertIsNone(self.bash_in(f"{self.UNLOCK} {redirect}", sid), redirect)

    # spec:khoa-test-lo-cu#S7
    def test_unlock_with_redirect_records_the_consent_receipt_once(self):
        self.start("mở khóa tests/test_b.py", "r1")
        self.assertIsNone(self.bash_in(f"{self.UNLOCK} 2>&1", "r1"))
        receipts = json.loads((self.state / "unlock-consents.json").read_text())
        self.assertEqual([r["path"] for r in receipts], ["tests/test_b.py"])
        out = self.bash_in(f"{self.UNLOCK} 2>/dev/null", "r1")
        self.assertEqual(out and out[0], "deny", "một tin chỉ mở một lần, chuyển hướng không đổi điều đó")

    # spec:khoa-test-lo-cu#S7
    def test_unlock_with_redirect_for_another_file_is_still_blocked(self):
        for i, redirect in enumerate(["2>&1", "2>/dev/null", "> log.txt"]):
            sid = f"o{i}"
            self.start("mở khóa tests/test_a.py", sid)
            with self.subTest(redirect=redirect):
                out = self.bash_in(f"{self.UNLOCK} {redirect}", sid)
                self.assertEqual(out and out[0], "deny", redirect)

    # spec:khoa-test-lo-cu#S7
    def test_unlock_with_redirect_without_user_consent_is_blocked(self):
        self.start("làm tiếp đi", "n1")
        for redirect in ["2>&1", "2>/dev/null", "> log.txt"]:
            with self.subTest(redirect=redirect):
                out = self.bash_in(f"{self.UNLOCK} {redirect}", "n1")
                self.assertEqual(out and out[0], "deny", redirect)


class CdpathFromEnvironment(HoleBase):
    # spec:khoa-test-lo-cu#S6 (thêm lúc chốt việc: CDPATH đặt sẵn trong môi trường, không gán trong lệnh)
    def test_cdpath_already_in_environment_counts_too(self):
        self.start("làm tiếp", "h1")
        out = self.bash_in("cd tests && rm test_b.py", "h1", self.project / "tools",
                           CDPATH=os.fspath(self.project))
        self.assertIn(out and out[0], BLOCKED, f"{out}")
        self.assertIsNone(self.bash_in("cd tests && make", "h1", self.project / "tools",
                                       CDPATH=os.fspath(self.project)))


class ReviewFixesHoles(HoleBase):
    # Thêm lúc chốt việc, theo review opus·xhigh và sonnet·xhigh ngày 20/11/2026.
    # spec:khoa-test-lo-cu#S1 (`&` chạy nền: `cd` ở vế trước chạy trong tiến trình con)
    def test_cd_before_background_ampersand_does_not_move_later_commands(self):
        self.start("làm tiếp", "h1")
        for cmd in ["cd tools & rm tests/test_b.py", "cd tools && true & rm tests/test_b.py"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, ("deny",))

    # spec:khoa-test-lo-cu#S1 (`cd` tới thư mục không có thì thất bại, lệnh sau chạy ở thư mục cũ)
    def test_cd_to_missing_dir_keeps_the_old_dir(self):
        self.start("làm tiếp", "h1")
        self.assertBlocked("cd nope; rm tests/test_b.py", ("deny",))
        self.assertPasses("cd tools; rm helper.py")

    # spec:khoa-test-lo-cu#S2 (cờ gộp của env: `-iC dir`, `-iu X`)
    def test_env_combined_flags(self):
        self.start("làm tiếp", "h1")
        for cmd in ["env -iC tests rm test_b.py", "env -vC tests rm test_b.py", "env -iu X rm tests/test_b.py"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, ("deny",))

    # spec:khoa-test-lo-cu#S4 (dải `{a..c}` được shell bung: có thể trúng test khóa)
    def test_brace_range_is_not_ignored(self):
        self.start("làm tiếp", "h1")
        for cmd in ["rm tests/test_{a..c}.py", "echo x > tests/test_{a..c}.py"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd)

    # spec:khoa-test-lo-cu#S6 (`HOME=` rồi `cd ~`, `cd ~/tests`, `pushd ~`)
    def test_assigned_home_then_cd_tilde(self):
        self.start("làm tiếp", "h1")
        for cmd in ["HOME=$PWD; cd ~; rm tests/test_b.py", "export HOME=$PWD && cd ~ && rm tests/test_b.py",
                    "HOME=$PWD; cd ~/tests; rm test_b.py", "HOME=$PWD; pushd ~; rm tests/test_b.py",
                    "HOME=$PWD; cd; rm tests/test_b.py"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, cwd=self.project / "tools")


class ReviewRound2Holes(HoleBase):
    # Thêm lúc chốt việc, theo review lại opus·xhigh ngày 21/11/2026.
    # spec:khoa-test-lo-cu#S1 (chuyển hướng có `&` không phải `&` chạy nền: `cd` vẫn đổi thư mục)
    def test_redirect_with_ampersand_is_not_a_background_job(self):
        self.start("làm tiếp", "h1")
        for cmd in ["cd tests &>/dev/null; rm test_b.py", "cd tests >& /dev/null; rm test_b.py",
                    "cd tests <&0; rm test_b.py", "cd tests 2<&-; rm test_b.py",
                    "cd tests &>>log.txt && rm test_b.py"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, ("deny",))

    # spec:khoa-test-lo-cu#S6 (gán HOME, CDPATH theo cách khác `NAME=`)
    def test_other_ways_of_setting_home_or_cdpath(self):
        self.start("làm tiếp", "h1")
        for cmd in ["HOME+=/x; cd ~; rm tests/test_b.py", "read -r HOME <<< \"$PWD\"; cd ~; rm tests/test_b.py",
                    "for HOME in \"$PWD\"; do rm ~/tests/test_b.py; done",
                    "read -r CDPATH <<< ..; cd tests; rm test_b.py", "CDPATH+=..; cd tests; rm test_b.py"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, cwd=self.project / "tools")


class DifferentialReviewHoles(HoleBase):
    # Thêm lúc chốt việc, theo differential-review ngày 21/11/2026.
    # spec:khoa-test-lo-cu#S1 (chuyển hướng dính chữ trước, `&>` liền chữ: đích vẫn là test khóa)
    def test_redirect_glued_to_the_previous_word(self):
        self.start("làm tiếp", "h1")
        for cmd in ["rm tests/test_b.py&>/dev/null", "rm tests/test_b.py>/dev/null",
                    "cd tests>/dev/null && rm test_b.py", "cd tests&>/dev/null; rm test_b.py"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, ("deny",))

    # spec:khoa-test-lo-cu#S1 (`)` của mẫu `case` không đóng tiến trình con)
    def test_case_pattern_paren_is_not_a_subshell_close(self):
        self.start("làm tiếp", "h1")
        for cmd in ["(cd tools; case a in a) ;; esac; rm ../tests/test_b.py)",
                    "bash -c 'cd tools; case a in a) ;; esac; rm ../tests/test_b.py'",
                    "(case x in x) true;; esac; cd tools); rm tests/test_b.py"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, ("deny",))

    # spec:khoa-test-lo-cu#S1 (review lại 21/11: chữ `case`/`esac` không phải từ khóa thật không được làm lệch phạm vi)
    def test_case_words_that_do_not_open_a_case_block(self):
        self.start("làm tiếp", "h1")
        for cmd in ["(cd tools; case a in esac); rm tests/test_b.py", "(cd tools; \"case\"); rm tests/test_b.py",
                    "(cd tools; \\case x); rm tests/test_b.py",
                    "(cd tools; case a in a) \"esac\";; b) ;; esac; rm ../tests/test_b.py)",
                    "(cd tools; case b in a|esac) ;; esac; rm ../tests/test_b.py)"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd, ("deny",))

    # spec:khoa-test-lo-cu#S1 (chữ số cuối từ không phải số luồng: `tests/v2>/dev/null`)
    def test_word_ending_in_a_digit_before_redirect(self):
        sub = self.project / "tests" / "v2"
        sub.mkdir()
        (sub / "test_c.py").write_text(B_TEST)
        write_lock(self.project, "cao", "tests/v2/test_c.py")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "v2")
        self.start("làm tiếp", "h1")
        self.assertBlocked("rm -r tests/v2>/dev/null", ("deny",))
        self.assertBlocked("rm tests/v2/test_c.py>/dev/null", ("deny",))

    # spec:khoa-test-lo-cu#S1 (review lại 21/11: quá 8 trạng thái thì không được bỏ thư mục mới nhất; ngoặc trong nháy)
    def test_many_states_and_quoted_parens_do_not_drop_the_latest_cd(self):
        self.start("làm tiếp", "h1")
        for cmd in ["(cd /tmp); (cd /usr); (cd /bin); (cd /etc); cd tests; rm test_b.py; git commit -m 'test case'",
                    "cd /tmp | true; cd /usr | true; cd /bin | true; cd /etc | true; cd tests; rm test_b.py",
                    "cd n1; cd n2; cd n3; cd n4; cd tests; rm test_b.py",
                    "echo \"(\"; cd tests; echo \")\"; rm test_b.py", "echo \\(; cd tests; echo \\); rm test_b.py",
                    "(echo \")\"; cd tests); rm tests/test_b.py"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd)

    # spec:khoa-test-lo-cu#S1 (review lại 21/11: subshell lồng khi có chữ `case`, tràn trạng thái ở `next_dirs`)
    def test_nested_subshells_with_case_word_and_next_dirs_overflow(self):
        self.start("làm tiếp", "h1")
        for cmd in ["(cd tools && echo $(pwd)); rm tests/test_b.py; git commit -m \"fix(hook): x\"",
                    "(cd tools; (true)); rm tests/test_b.py # case",
                    "cd tests; cd /usr | true; cd /bin | true; cd /etc | true; cd x*; rm test_b.py"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd)

    # spec:khoa-test-lo-cu#S1 (review lại 21/11: giữ biến thể OLDPWD và chồng pushd; `)` không có cặp)
    def test_oldpwd_and_pushd_variants_and_unmatched_paren(self):
        self.start("làm tiếp", "h1")
        root = str(self.project)
        for cmd in [f"true | cd tests; cd {root}; cd -; rm test_b.py", f"true | cd tests; pushd {root}; popd; rm test_b.py",
                    "cd tests; echo ${x:-)}; rm test_b.py", "cd tests && echo ${x%)} && rm test_b.py"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd)


class TruncatedStatesHoles(HoleBase):
    """Chuỗi nhiều `cd`/`pushd`/`popd` làm hook phải cắt bớt trạng thái: lệnh ghi/xóa phía sau vẫn không được lọt."""
    CD7 = ("cd /bin | true; cd /etc | true; cd /var | true; cd /opt | true; cd /sbin | true; "
           "cd /Library | true; cd /System | true")

    # spec:khoa-test-lo-cu#S8 (7 lệnh `cd … | true` rồi `cd -`: OLDPWD có thể là tests, sau đó xóa hay ghi test_b.py)
    def test_cd_dash_after_many_cd_still_blocks_write_and_delete(self):
        self.start("làm tiếp", "h1")
        for cmd in [f"true | cd tests; cd /usr; {self.CD7}; cd -; rm test_b.py",
                    f"true | cd tests; cd /usr; {self.CD7}; cd -; echo x > test_b.py"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd)

    # spec:khoa-test-lo-cu#S8 (7 lệnh `cd … | true` rồi `popd`: chồng pushd có thể còn tests, sau đó xóa test_b.py)
    def test_popd_after_many_cd_still_blocks_delete(self):
        self.start("làm tiếp", "h1")
        root = str(self.project)
        for cmd in [f"true | pushd tests; pushd /usr; {self.CD7}; popd; rm test_b.py",
                    f"true | pushd tests; pushd {root}; {self.CD7}; popd; rm test_b.py"]:
            with self.subTest(cmd=cmd):
                self.assertBlocked(cmd)

    # spec:khoa-test-lo-cu#S8 (đối chứng: cùng chuỗi nhưng chỉ `ls`, `cat` thì vẫn qua; lệnh thường không bị vạ lây)
    def test_same_chain_without_write_or_delete_still_passes(self):
        self.start("làm tiếp", "h1")
        for cmd in [f"true | cd tests; cd /usr; {self.CD7}; cd -; ls; cat test_b.py",
                    "cd tools; rm -f foo.txt"]:
            with self.subTest(cmd=cmd):
                self.assertPasses(cmd)

    # spec:khoa-test-lo-cu#S8 (review 21/11: lệnh bọc `receipt.py run --cwd .`, `sh -c` sau chuỗi bị cắt vẫn bị xét)
    def test_wrapped_write_after_truncation_is_blocked(self):
        self.start("làm tiếp", "h1")
        for tail in ["cd -", "popd"]:
            head = "true | pushd tests; pushd /usr" if tail == "popd" else "true | cd tests; cd /usr"
            for inner in [f"{R} run --cwd . -- rm test_b.py", f"{R} run --cwd . -- sh -c 'rm test_b.py'"]:
                cmd = f"{head}; {self.CD7}; {tail}; {inner}"
                with self.subTest(cmd=cmd):
                    self.assertBlocked(cmd)

    # spec:khoa-test-lo-cu#S8 (review 21/11: đúng ngưỡng, tám bản chỉ khác OLDPWD giữ đủ, bản thứ chín bị cắt thì ghi lost)
    def test_merge_states_marks_lost_exactly_when_it_cuts(self):
        import sys
        sys.path.insert(0, str(HOOKS))
        import pretool_guard as g
        variants = [("/p/tests", f"/o{i}", []) for i in range(g.MAX_STATES + 1)]
        lost = []
        self.assertEqual(len(g.merge_states(variants[:g.MAX_STATES], lost=lost)), g.MAX_STATES)
        self.assertEqual(lost, [])
        self.assertEqual(len(g.merge_states(variants, lost=lost)), g.MAX_STATES)
        self.assertTrue(lost)
        lost = []
        stacks = [("/p", None, [f"/s{i}"]) for i in range(g.MAX_STATES)] + [("/p", None, [])]
        self.assertEqual(len(g.merge_states(stacks, lost=lost)), g.MAX_STATES)
        self.assertTrue(lost)

    # spec:khoa-test-lo-cu#S8 (review lại 21/11: phiên mở ở thư mục cha, lệnh bọc sau chuỗi bị cắt vẫn bị hỏi)
    def test_wrapped_write_after_truncation_from_parent_dir_is_blocked(self):
        self.start("làm tiếp", "h1")
        rp = "python3 proj/plugin/skills/session-keeper/scripts/receipt.py"
        for tail in ["cd -", "popd"]:
            head = "true | pushd proj/tests; pushd /usr" if tail == "popd" else "true | cd proj/tests; cd /usr"
            for inner in [f"{rp} run --cwd . -- rm test_b.py", f"{rp} run --cwd . -- sh -c 'rm test_b.py'",
                          f"{rp} lock -- {rp} run --cwd . -- rm test_b.py"]:
                cmd = f"{head}; {self.CD7}; {tail}; {inner}"
                with self.subTest(cmd=cmd):
                    self.assertBlocked(cmd, cwd=self.tmp)
        self.assertPasses(f"true | cd proj/tests; cd /usr; {self.CD7}; cd -; {rp} run --cwd . -- python3 -m unittest",
                          cwd=self.tmp)


class HookBudgetAndErrorHoles(HoleBase):
    """Lỗi nội bộ lúc xét một lệnh không làm mất quyết định các lệnh khác; xét quá ngân sách thì hỏi lại, không để app hết giờ."""
    LONG = "/tmp/" + "/".join(["d" * 200] * 20)  # ~4.000 ký tự: hệ điều hành báo tên quá dài
    CUT = f"true | cd tests; cd /usr; {TruncatedStatesHoles.CD7}; cd -"  # chuỗi bị cắt trạng thái

    def run_run(self, body, cmd="ls"):
        """Chạy `pretool_guard.run()` trong tiến trình con sau khi `body` thay `check_bash`; trả (mã thoát, stdout, giây)."""
        root = HOOKS.parents[1]
        script = ("import sys, time\n"
                  f"sys.path.insert(0, {str(HOOKS)!r})\n"
                  "import pretool_guard as g\n"
                  f"{body}\n"
                  "g.check_bash = boom\n"
                  "g.run()\n")
        payload = {"session_id": "h1", "cwd": str(self.project), "tool_name": "Bash",
                   "tool_input": {"command": cmd}, "hook_event_name": "PreToolUse"}
        t0 = time.monotonic()
        try:
            out = subprocess.run(["python3", "-c", script], input=json.dumps(payload), capture_output=True, text=True,
                                 cwd=str(root), env=self.env(), timeout=15)
        except subprocess.TimeoutExpired:
            self.fail("g.run() không dừng trong 15 giây: ngân sách thời gian không cắt được hàm xét")
        return out.returncode, out.stdout, time.monotonic() - t0

    def decision_of(self, stdout):
        self.assertTrue(stdout.strip(), "run() không in quyết định nào")
        return json.loads(stdout)["hookSpecificOutput"]["permissionDecision"]

    # spec:khoa-test-lo-cu#S9 (lỗi ở một lệnh không làm mất quyết định lệnh còn lại, ở cả hai thứ tự; lệnh lỗi bị hỏi)
    def test_error_in_one_command_keeps_decision_of_the_others(self):
        self.start("làm tiếp", "h1")
        alone = self.bash_in("rm tests/test_b.py")
        self.assertIn(alone and alone[0], BLOCKED, alone)
        for cmd in [f"rm tests/test_b.py; rm -r {self.LONG}", f"rm -r {self.LONG}; rm tests/test_b.py"]:
            with self.subTest(cmd=cmd[:40]):
                out = self.bash_in(cmd)
                self.assertEqual(out and out[0], alone[0], f"{cmd[:40]!r} -> {out}")
        out = self.bash_in(f"rm -r {self.LONG}")
        self.assertEqual(out and out[0], "ask", f"lệnh gây lỗi phải bị hỏi, không qua im lặng: {out}")

    # spec:khoa-test-lo-cu#S9 (lưới ở run(): check_bash ném lỗi bất kỳ thì in ask, thoát 0)
    def test_run_answers_ask_when_check_bash_raises(self):
        self.start("làm tiếp", "h1")
        code, stdout, _ = self.run_run('def boom(*a, **k):\n    raise RuntimeError("x")')
        self.assertEqual(code, 0)
        self.assertEqual(self.decision_of(stdout), "ask")

    # spec:khoa-test-lo-cu#S10 (ngân sách nội bộ thấp hơn hẳn hạn 5 giây của app; hàm xét treo thì hỏi lại dưới 5 giây)
    def test_run_answers_ask_under_five_seconds_when_check_bash_hangs(self):
        import sys
        sys.path.insert(0, str(HOOKS))
        import pretool_guard as g
        self.assertTrue(hasattr(g, "BUDGET_SECONDS"), "thiếu hằng BUDGET_SECONDS")
        self.assertLessEqual(g.BUDGET_SECONDS, 3.0)
        self.start("làm tiếp", "h1")
        code, stdout, wall = self.run_run("def boom(*a, **k):\n    time.sleep(20)")
        self.assertEqual(code, 0)
        self.assertEqual(self.decision_of(stdout), "ask")
        self.assertLess(wall, 5.0)

    # spec:khoa-test-lo-cu#S10 (code nuốt `except Exception` rồi ngủ tiếp vẫn bị cắt: ngoại lệ hết giờ không phải Exception thường)
    def test_run_budget_cuts_even_when_check_bash_swallows_exceptions(self):
        self.start("làm tiếp", "h1")
        body = ("def boom(*a, **k):\n"
                "    while True:\n"
                "        try:\n"
                "            time.sleep(20)\n"
                "        except Exception:\n"
                "            pass")
        code, stdout, wall = self.run_run(body)
        self.assertEqual(code, 0)
        self.assertEqual(self.decision_of(stdout), "ask")
        self.assertLess(wall, 5.0)

    # spec:khoa-test-lo-cu#S10 (ca thật: chuỗi bị cắt nối `receipt.py run -- echo <rất dài>` trả lời hỏi lại dưới 3 giây)
    def test_truncated_chain_with_long_receipt_run_answers_within_budget(self):
        self.start("làm tiếp", "h1")
        for n in (5000, 8000):
            cmd = f"{self.CUT}; {R} run -- echo {'x' * n}"
            with self.subTest(n=n):
                out = self.bash_in(cmd)
                self.assertIn(out[0] if out else None, (None, "ask"), out)
                self.assertLess(self.wall, 3.0, f"hook mất {self.wall:.1f} s cho {n} ký tự")

    # spec:khoa-test-lo-cu#S10 (đối chứng: lệnh thường vẫn qua không bị hỏi và nhanh)
    def test_ordinary_commands_still_pass_fast(self):
        self.start("làm tiếp", "h1")
        for cmd in ["ls -la", "git status", "cat tests/test_b.py"]:
            with self.subTest(cmd=cmd):
                self.assertPasses(cmd)
                self.assertLess(self.wall, 3.0)

    # spec:khoa-test-lo-cu#S9 (review 21/11: một đoạn tên quá 255 ký tự cũng lỗi trên Linux; lệnh khác vẫn bị chặn)
    def test_long_name_component_keeps_decision_of_the_others(self):
        self.start("làm tiếp", "h1")
        alone = self.bash_in("rm tests/test_b.py")
        out = self.bash_in(f"rm tests/test_b.py; rm -r /tmp/{'d' * 300}")
        self.assertEqual(out and out[0], alone and alone[0])

    # spec:khoa-test-lo-cu#S9 (review 21/11: lý do chép lệnh có surrogate lẻ thì in lỗi mã hóa; vẫn phải ra quyết định)
    def test_lone_surrogate_in_command_still_decides(self):
        self.start("làm tiếp", "h1")
        for cmd in ["git clean -fd . \ud800", "git reset --hard \ud800", "rm tests/test_b.py \ud800"]:
            with self.subTest(cmd=cmd.encode("unicode_escape")):
                self.assertBlocked(cmd)
