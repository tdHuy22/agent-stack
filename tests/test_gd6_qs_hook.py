"""Tám quan sát sau GĐ6, lát hook (slug `gd6-qs-hook`): file spec `.agent/spec/gd6-qs-hook.txt`.

Viết TRƯỚC code. S1: `spec.py page` nói rõ câu duyệt. S2, S3: hook `prompt_submit.py` báo câu cần gõ khi tin "duyệt" không
ghi được bản duyệt (chạy như app: subprocess, JSON vào stdin, JSON ra stdout: chữ cho người ở `systemMessage`, chữ cho
agent ở `hookSpecificOutput.additionalContext`). S4: `agentstack.changed_since` bỏ commit tua nhanh từ worktree của phiên
khác. Repo git, thư mục trạng thái nằm trong thư mục tạm của test (tự xóa), `AGENT_STACK_STATE` trỏ vào đó.
Test ghi "vế cũ, giữ" là hành vi hiện có mà spec không đổi: chúng đạt ngay, để code mới không nới nhầm.
"""
import hashlib
import json
import os
import subprocess
import sys
import time
from unittest import mock

from tests._util import PLUGIN, TempDirTestCase, run_script
from tests.test_guard import GuardBase

SPEC_CLI = PLUGIN / "skills" / "session-keeper" / "scripts" / "spec.py"
sys.path.insert(0, str(PLUGIN / "lib"))
import agentstack as A  # noqa: E402
import specbook  # noqa: E402

SPEC_A = "S1: Khi bạn gõ a thì hệ thống ghi b\nS2: Khi bạn gõ c thì hệ thống ghi d\n"
SPEC_B = "S1: Khi trời mưa thì mang ô\nS2: Khi trời nắng thì đội mũ\n"


def code_of(text):
    """Mã 12 ký tự: đầu sha256 của file spec, như `spec.py page` in ra."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


class SpecProject(GuardBase):
    """Project git (của GuardBase) có `.agent/spec/a.txt` chưa duyệt."""

    def setUp(self):
        super().setUp()
        self.spec_dir = self.project / ".agent" / "spec"
        self.spec_dir.mkdir(parents=True)
        (self.spec_dir / "a.txt").write_text(SPEC_A, encoding="utf-8")
        self.code_a = code_of(SPEC_A)
        self.n = 0

    def add_spec(self, slug, text):
        (self.spec_dir / f"{slug}.txt").write_text(text, encoding="utf-8")
        return code_of(text)

    def build_page(self, slug="a"):
        out = run_script(SPEC_CLI, "page", slug, "--project", str(self.project),
                         env={"AGENT_STACK_STATE": str(self.state)})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        return out

    def say(self, prompt):
        """(chữ cho người dùng, chữ cho agent) của hook prompt_submit với một tin; rỗng khi hook không in gì."""
        self.n += 1
        out = self.hook("prompt_submit.py", {"session_id": f"s{self.n}", "cwd": str(self.project), "prompt": prompt}) or {}
        return out.get("systemMessage", ""), out.get("hookSpecificOutput", {}).get("additionalContext", "")

    def book(self):
        path = self.state / "spec-approvals.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    def user_approvals(self):
        return [r for r in self.book() if r.get("source") == "duyet-spec"]

    def assertNames(self, prompt, *codes, absent=()):
        """Hook báo câu `duyệt spec <mã>` của từng mã trong `codes` cho cả người dùng lẫn agent, và không của `absent`."""
        user, agent = self.say(prompt)
        for code in codes:
            self.assertIn(f"duyệt spec {code}", user, f"systemMessage với tin {prompt!r}")
            self.assertIn(f"duyệt spec {code}", agent, f"additionalContext với tin {prompt!r}")
        for code in absent:
            self.assertNotIn(f"duyệt spec {code}", user)
            self.assertNotIn(f"duyệt spec {code}", agent)

    def assertSilent(self, prompt):
        user, agent = self.say(prompt)
        self.assertNotIn("duyệt spec", user, f"tin {prompt!r}")
        self.assertNotIn("duyệt spec", agent, f"tin {prompt!r}")


# ---------------------------------------------------------------------------------------------------------------
# S1: spec.py page nói câu duyệt và dặn gửi thành tin riêng

class PageSaysTheSentence(SpecProject):
    def test_printed_line_names_sentence_and_asks_for_a_separate_message(self):
        # spec:gd6-qs-hook#S1
        out = self.build_page()
        self.assertIn(f"duyệt spec {self.code_a}", out.stdout)
        self.assertIn("tin riêng", out.stdout)
        self.assertIn("dừng", out.stdout)
        self.assertEqual(out.stdout.strip().splitlines()[-1], str(self.project / ".agent" / "trang" / "a-spec.html"),
                         "vế cũ, giữ: dòng cuối vẫn là đường dẫn trang")

    def test_page_file_has_the_same_instruction(self):
        # spec:gd6-qs-hook#S1
        self.build_page()
        page = (self.project / ".agent" / "trang" / "a-spec.html").read_text(encoding="utf-8")
        self.assertIn("tin riêng", page)
        self.assertIn(f"duyệt spec {self.code_a}", page, "vế cũ, giữ: câu duyệt nguyên văn trong trang")


# ---------------------------------------------------------------------------------------------------------------
# S2: tin có "duyệt" kèm "spec" hay mã hex mà hook không ghi được bản duyệt

class ApprovalMessageNotRecorded(SpecProject):
    # Chữ "A" đứng sau "duyệt spec" thì hook hiện tại vẫn ghi bản duyệt (A nằm trong từ đệm), nên dùng "MW1" như tin thật.
    MESSAGES = ("duyệt spec MW1 (mã {a})", "duyệt {a}", "duyệt spec 0000aaaa1111", "duyệt spec MW1 (mã 883e…)",
                "duyệt spec {a} (mã MW1)")

    def test_hook_names_the_sentence_for_user_and_agent_and_records_nothing(self):
        # spec:gd6-qs-hook#S2
        for template in self.MESSAGES:
            prompt = template.format(a=self.code_a)
            with self.subTest(prompt=prompt):
                self.assertNames(prompt, self.code_a)
                self.assertEqual(self.book(), [], "không ghi bản duyệt nào")

    def test_every_pending_spec_is_named(self):
        # spec:gd6-qs-hook#S2
        code_b = self.add_spec("b", SPEC_B)
        self.assertNames(f"duyệt spec MW1 (mã {self.code_a})", self.code_a, code_b)
        self.assertEqual(self.book(), [])

    def test_spec_already_approved_by_sentence_is_not_named(self):
        # spec:gd6-qs-hook#S2 (chỉ spec còn dòng chưa duyệt bằng câu duyệt)
        code_b = self.add_spec("b", SPEC_B)
        self.say(f"duyệt spec {self.code_a}")
        self.assertEqual([r["path"] for r in self.user_approvals()], [".agent/spec/a.txt"])
        self.assertNames(f"duyệt spec MW1 (mã {code_b})", code_b, absent=[self.code_a])
        self.assertEqual(len(self.user_approvals()), 1, "không ghi thêm bản duyệt")

    def test_lines_approved_only_through_the_plan_still_count_as_pending(self):
        # spec:gd6-qs-hook#S2 (duyệt qua kế hoạch không phải câu duyệt)
        rows = [{"top": str(self.project.resolve()), "path": None, "sha256": None,
                 "lines": [specbook.line_hash("S1", "Khi bạn gõ a thì hệ thống ghi b"),
                           specbook.line_hash("S2", "Khi bạn gõ c thì hệ thống ghi d")],
                 "source": "ke-hoach", "ts": "2026-11-17T10:00:00+07:00"}]
        self.state.mkdir(parents=True, exist_ok=True)
        (self.state / "spec-approvals.json").write_text(json.dumps(rows), encoding="utf-8")
        self.assertNames(f"duyệt {self.code_a}", self.code_a)
        self.assertEqual(self.user_approvals(), [])

    def test_exact_sentence_still_records_the_approval(self):
        # spec:gd6-qs-hook#S2 (đối chứng, vế cũ: đúng câu thì ghi bản duyệt)
        self.say(f"duyệt spec {self.code_a}")
        rows = self.user_approvals()
        self.assertEqual(len(rows), 1, self.book())
        self.assertEqual(rows[0]["path"], ".agent/spec/a.txt")
        self.assertEqual(rows[0]["sha256"], hashlib.sha256(SPEC_A.encode("utf-8")).hexdigest())


# ---------------------------------------------------------------------------------------------------------------
# S3: tin chỉ có từ đồng ý "duyệt"

class BareApprovalWord(SpecProject):
    def test_bare_word_with_pending_spec_and_built_page_names_the_sentence(self):
        # spec:gd6-qs-hook#S3
        self.build_page()
        for prompt in ("duyệt", "ok duyệt"):
            with self.subTest(prompt=prompt):
                self.assertNames(prompt, self.code_a)
                self.assertEqual(self.book(), [], "không ghi bản duyệt")

    def test_no_spec_means_no_message(self):
        # spec:gd6-qs-hook#S3
        (self.spec_dir / "a.txt").unlink()
        self.assertSilent("duyệt")

    def test_spec_approved_by_sentence_means_no_message(self):
        # spec:gd6-qs-hook#S3
        self.build_page()
        self.say(f"duyệt spec {self.code_a}")
        self.assertEqual(len(self.user_approvals()), 1)
        self.assertSilent("duyệt")
        self.assertSilent("ok duyệt")

    def test_pending_spec_without_built_page_means_no_message(self):
        # spec:gd6-qs-hook#S3 (cần trang đã dựng)
        self.assertSilent("duyệt")

    def test_long_message_that_is_not_an_agreement_means_no_message(self):
        # spec:gd6-qs-hook#S3
        self.build_page()
        self.assertSilent("duyệt lại giúp tôi đoạn code này")
        self.assertEqual(self.book(), [])


# ---------------------------------------------------------------------------------------------------------------
# S4: commit tua nhanh từ worktree của phiên khác không tính là file lượt này đổi

class FastForwardFromOtherWorktree(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.state = self.tmp / "state"
        patcher = mock.patch.dict(os.environ, {"AGENT_STACK_STATE": str(self.state)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.since = time.time() - 60  # mọi commit của cảnh nằm sau mốc này, trừ commit gốc (đặt ngày cũ)
        self.w1 = self.tmp / "w1"
        self.w2 = self.tmp / "w2"
        self.w1.mkdir()
        self.git(self.w1, "init", "-q")
        (self.w1 / "PLAN.md").write_text("# PLAN\n\n## 0. Đang ở đâu, việc tiếp theo\n- làm việc\n", encoding="utf-8")
        self.git(self.w1, "add", "-A")
        self.git(self.w1, "commit", "-q", "-m", "gốc", old=True)

    def git(self, cwd, *args, old=False):
        env = dict(os.environ)
        if old:
            env["GIT_COMMITTER_DATE"] = env["GIT_AUTHOR_DATE"] = "2020-01-01T00:00:00+0000"
        cmd = ["git", "-c", "user.name=test", "-c", "user.email=test@example.com", "-c", "init.defaultBranch=main",
               "-c", "commit.gpgsign=false", *args]
        return subprocess.run(cmd, cwd=str(cwd), env=env, check=True, capture_output=True, text=True).stdout

    def commit_file(self, cwd, name, msg):
        (cwd / name).write_text("x = 1\n", encoding="utf-8")
        self.git(cwd, "add", "-A")
        self.git(cwd, "commit", "-q", "-m", msg)

    def other_session(self, root):
        """Bản ghi lượt của một phiên khác, mở ở `since`, đang làm ở `root` (như hook prompt_submit ghi)."""
        folder = self.state / A.TURN_DIR
        folder.mkdir(parents=True, exist_ok=True)
        transcript = self.tmp / "other.jsonl"
        transcript.write_text("", encoding="utf-8")
        record = {"ts": self.since, "root": str(root.resolve()), "transcript": str(transcript)}
        (folder / "other.json").write_text(json.dumps(record), encoding="utf-8")

    def foreign_commit_in_second_worktree(self):
        self.git(self.w1, "worktree", "add", "-q", str(self.w2), "-b", "side")
        self.commit_file(self.w2, "foreign.py", "phiên khác")

    def fast_forward_then_commit_own(self):
        self.git(self.w1, "merge", "-q", "--ff-only", "side")
        self.assertIn("Fast-forward", self.git(self.w1, "reflog", "-n", "3"), "cảnh phải có dòng reflog Fast-forward")
        self.commit_file(self.w1, "own.py", "của cây này")

    def changed(self):
        return A.changed_since(self.w1, self.since)

    def test_files_only_in_other_sessions_commits_are_not_counted(self):
        # spec:gd6-qs-hook#S4
        self.foreign_commit_in_second_worktree()
        self.other_session(self.w2)
        self.fast_forward_then_commit_own()
        found = self.changed()
        self.assertNotIn("foreign.py", found)
        self.assertIn("own.py", found, "commit do chính cây này tạo vẫn được tính")

    def test_without_a_session_record_for_that_worktree_foreign_file_is_counted(self):
        # spec:gd6-qs-hook#S4 (đối chứng: không có phiên nào ở worktree đó)
        self.foreign_commit_in_second_worktree()
        self.fast_forward_then_commit_own()
        found = self.changed()
        self.assertIn("foreign.py", found)
        self.assertIn("own.py", found)

    def test_record_of_an_unrelated_repo_does_not_hide_the_file(self):
        # spec:gd6-qs-hook#S4 (đối chứng: phiên khác ở repo khác, không phải worktree của repo này)
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        self.git(elsewhere, "init", "-q")
        self.foreign_commit_in_second_worktree()
        self.other_session(elsewhere)
        self.fast_forward_then_commit_own()
        self.assertIn("foreign.py", self.changed())

    def test_fast_forward_from_a_branch_without_a_worktree_is_counted(self):
        # spec:gd6-qs-hook#S4 (đối chứng: tua nhanh từ nhánh trong chính cây này, không có phiên khác)
        self.git(self.w1, "checkout", "-q", "-b", "side")
        self.commit_file(self.w1, "foreign.py", "trên nhánh")
        self.git(self.w1, "checkout", "-q", "main")
        self.fast_forward_then_commit_own()
        found = self.changed()
        self.assertIn("foreign.py", found)
        self.assertIn("own.py", found)

    # Review sonnet·xhigh 17/11 (siết, viết trước bản sửa): chốt (c) của TM-140 phải là bản ghi của một phiên thật khác.

    def test_record_without_a_transcript_does_not_make_commits_foreign(self):
        # spec:gd6-qs-hook#S4 (review: bản ghi viết tay, không có transcript, không tính là phiên khác; TM-140)
        self.foreign_commit_in_second_worktree()
        folder = self.state / A.TURN_DIR
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "bare.json").write_text(json.dumps({"ts": self.since, "root": str(self.w2.resolve())}),
                                          encoding="utf-8")
        self.fast_forward_then_commit_own()
        self.assertIn("foreign.py", self.changed())

    def test_own_record_in_a_nested_worktree_does_not_make_the_parent_foreign(self):
        # spec:gd6-qs-hook#S4 (review: bản ghi của chính cây này, lồng dưới cây chính, không biến cây cha thành phiên khác)
        (self.w1 / ".gitignore").write_text(".wt/\n", encoding="utf-8")
        self.git(self.w1, "add", "-A")
        self.git(self.w1, "commit", "-q", "-m", "bỏ qua .wt", old=True)
        nested = self.w1 / ".wt" / "side"
        self.git(self.w1, "worktree", "add", "-q", str(nested), "-b", "side")
        self.commit_file(self.w1, "foreign.py", "trên main")
        self.other_session(nested)  # bản ghi lượt của chính phiên đang làm ở cây lồng
        self.git(nested, "merge", "-q", "--ff-only", "main")
        self.assertIn("foreign.py", A.changed_since(nested, self.since))

    def test_other_session_in_a_worktree_nested_under_main_makes_its_commits_foreign(self):
        # spec:gd6-qs-hook#S4 (review lần 2: bố cục `.claude/worktrees/<tên>` lồng dưới cây chính vẫn là phiên khác)
        (self.w1 / ".gitignore").write_text(".wt/\n", encoding="utf-8")
        self.git(self.w1, "add", "-A")
        self.git(self.w1, "commit", "-q", "-m", "bỏ qua .wt", old=True)
        nested = self.w1 / ".wt" / "b"
        self.git(self.w1, "worktree", "add", "-q", str(nested), "-b", "side")
        self.commit_file(nested, "foreign.py", "phiên khác ở cây lồng")
        self.other_session(nested)
        self.fast_forward_then_commit_own()
        found = self.changed()
        self.assertNotIn("foreign.py", found)
        self.assertIn("own.py", found)
