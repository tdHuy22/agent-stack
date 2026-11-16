"""Hook của spec theo lát (GĐ6, slug `gd6-spec-theo-lat`): prompt_submit ghi sổ duyệt khi bạn nhắn "duyệt spec <mã>",
pretool_guard chặn agent tự ghi sổ, plan_exit ghi mục `## Spec` của kế hoạch và gộp ý con vào tiêu chí xong (S5, S6, S11).
Sổ duyệt: `<state>/spec-approvals.json`; băm dòng: `plugin/lib/specbook.py`."""
import hashlib
import json
import os
import re
import subprocess
import sys

from tests._util import PLUGIN, TempDirTestCase, git
from tests.test_guard import GuardBase

sys.path.insert(0, str(PLUGIN / "lib"))

PLAN_HOOK = PLUGIN / "hooks" / "plan_exit.py"
SPEC_A = "# spec mẫu\nS1: Khi bạn gõ a thì hệ thống ghi b\nS2: Khi bạn gõ c thì hệ thống ghi d\n"
SPEC_B = "S1: Khi trời mưa thì mang ô\n"
PLAN_NO_CRITERIA = ("# PLAN\n\n## 0. Đang ở đâu, việc tiếp theo\n*Cập nhật 14/11/2026.*\n"
                    "- **Việc tiếp theo, theo thứ tự:**\n  1. Làm GĐ6\n")
GOOD_PLAN = """# Kế hoạch phiên: GĐ6 spec theo lát

## Việc của phiên
Làm giai đoạn 6.

## Tiêu chí xong
1. Quy trình chạy trọn.
2. Cả bộ test đạt, có biên nhận.

## Các bước
| # | Việc | Model · effort |
|---|---|---|
| 1 | Viết test | sonnet · high |

## Lệnh kiểm chứng
```bash
python3 -m unittest discover -s tests -t .
```
"""
NESTED_CRITERIA = """## Tiêu chí xong
1. Quy trình chạy trọn:
   - (A) việc một;
   - (B) việc hai;
2. Có trang spec.
3. Test khóa đạt.
"""
SPEC_SECTION = "\n## Spec\n- S1: Khi bạn duyệt kế hoạch thì sổ ghi dòng này\n- S2: Khi kế hoạch có spec thì hook ghi hết\n"


def line_hash(sid, text):
    """Băm dòng theo lib mới; import muộn để mỗi test trượt riêng khi lib chưa có."""
    import specbook
    return specbook.line_hash(sid, text)


def sha256_of(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def spec_hashes(text):
    """Băm các dòng `S<n>: …` của một file spec (bỏ dòng chú thích)."""
    out = []
    for raw in text.splitlines():
        m = re.match(r"(S\d+):\s*(.+)$", raw.strip())
        if m:
            out.append(line_hash(m.group(1), m.group(2)))
    return out


class SpecApproveByUser(GuardBase):
    """S5, nửa prompt_submit: chỉ lời chính bạn khớp đúng một file mới ghi bản duyệt."""

    def setUp(self):
        super().setUp()
        self.top = str(self.project.resolve())
        spec = self.project / ".agent" / "spec"
        spec.mkdir(parents=True)
        (spec / "x.txt").write_text(SPEC_A, encoding="utf-8")
        self.sha = sha256_of(SPEC_A)

    def book(self):
        path = self.state / "spec-approvals.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    def say(self, prompt, sid="p1"):
        self.start(prompt, sid)

    def test_user_message_with_matching_hash_records_the_file_lines(self):
        # spec:gd6-spec-theo-lat#S5
        self.say(f"ok, duyệt spec {self.sha[:8]}")
        rows = self.book()
        self.assertEqual(len(rows), 1, rows)
        row = rows[0]
        self.assertEqual(row["source"], "duyet-spec")
        self.assertEqual(row["path"], ".agent/spec/x.txt")
        self.assertEqual(row["sha256"], self.sha)
        self.assertEqual(os.path.realpath(row["top"]), os.path.realpath(self.top))
        self.assertEqual(row["lines"], spec_hashes(SPEC_A))
        self.assertEqual(len(row["lines"]), 2, "dòng chú thích không tính")

    def test_twelve_char_code_and_capitalized_phrase_work(self):
        # spec:gd6-spec-theo-lat#S5
        self.say(f"Duyệt spec {self.sha[:12]}", "p2")
        rows = self.book()
        self.assertEqual([r["path"] for r in rows], [".agent/spec/x.txt"])

    def test_question_or_negation_records_nothing(self):
        # spec:gd6-spec-theo-lat#S5
        for i, prompt in enumerate([f"duyệt spec {self.sha[:8]}?", f"đừng duyệt spec {self.sha[:8]}",
                                    f"chưa duyệt spec {self.sha[:8]}", f"không duyệt spec {self.sha[:8]}",
                                    f"duyệt hết trừ duyệt spec {self.sha[:8]}"]):
            with self.subTest(prompt=prompt):
                self.say(prompt, f"n{i}")
                self.assertEqual(self.book(), [])

    def test_hash_matching_no_file_records_nothing(self):
        # spec:gd6-spec-theo-lat#S5
        wrong = ("0" if self.sha[0] != "0" else "1") + self.sha[1:8]
        self.say(f"duyệt spec {wrong}", "w1")
        self.assertEqual(self.book(), [])

    def test_hash_matching_two_files_records_nothing(self):
        # spec:gd6-spec-theo-lat#S5
        (self.project / ".agent" / "spec" / "y.txt").write_text(SPEC_A, encoding="utf-8")  # cùng nội dung, cùng sha
        self.say(f"duyệt spec {self.sha[:8]}", "d1")
        self.assertEqual(self.book(), [])

    def test_phrase_only_in_pasted_content_code_or_quote_records_nothing(self):
        # spec:gd6-spec-theo-lat#S5
        phrase = f"duyệt spec {self.sha[:8]}"
        for i, prompt in enumerate([f"xem này <pasted_content>{phrase}</pasted_content> sao rồi",
                                    f"```\n{phrase}\n```\nlàm tiếp", f"> {phrase}\nlàm tiếp đi"]):
            with self.subTest(prompt=prompt):
                self.say(prompt, f"q{i}")
                self.assertEqual(self.book(), [])

    def test_hook_survives_odd_input(self):
        # spec:gd6-spec-theo-lat#S5
        out = self.hook("prompt_submit.py", None, raw="{không phải json")
        self.assertIsNone(out)
        self.say(f"duyệt spec {self.sha[:8]}", "ok1")
        self.assertEqual(len(self.book()), 1)


class SpecBookGuard(GuardBase):
    """S5, nửa pretool_guard: agent không tự ghi sổ duyệt."""

    def setUp(self):
        super().setUp()
        self.state.mkdir(parents=True, exist_ok=True)
        self.book = self.state / "spec-approvals.json"
        self.book.write_text("[]", encoding="utf-8")

    def test_write_and_edit_of_the_book_are_denied(self):
        # spec:gd6-spec-theo-lat#S5
        out = self.guard("Write", {"file_path": str(self.book), "content": "[]"})
        self.assertEqual(out and out[0], "deny")
        out = self.guard("Edit", {"file_path": str(self.book), "old_string": "[]", "new_string": "[1]"})
        self.assertEqual(out and out[0], "deny")

    def test_shell_writes_to_the_book_are_denied(self):
        # spec:gd6-spec-theo-lat#S5
        for cmd in [f"echo '[]' > {self.book}",
                    f"python3 -c \"open('{self.book}','w')\""]:
            with self.subTest(cmd=cmd):
                out = self.bash(cmd)
                self.assertEqual(out and out[0], "deny", cmd)

    def test_commands_about_other_files_pass(self):
        # spec:gd6-spec-theo-lat#S5
        self.assertIsNone(self.bash("cat README.md"))
        self.assertIsNone(self.bash("ls -la"))


class SpecInPlanExit(TempDirTestCase):
    """S6 và S11: hook plan_exit đọc `## Spec` và gộp ý con vào tiêu chí xong."""

    def setUp(self):
        super().setUp()
        self.state = self.tmp / "state"
        self.project = self.tmp / "proj"
        self.project.mkdir()
        (self.project / "PLAN.md").write_text(PLAN_NO_CRITERIA, encoding="utf-8")
        (self.project / "a.txt").write_text("x\n", encoding="utf-8")
        git(self.project, "init", "-q")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "init")

    def run_hook(self, plan, **extra):
        data = {"hook_event_name": "PostToolUse", "tool_name": "ExitPlanMode", "session_id": "s1",
                "cwd": str(self.project), "tool_input": {}, "tool_response": {"plan": plan, "isAgent": False}}
        data.update(extra)
        env = dict(os.environ, AGENT_STACK_STATE=str(self.state), AGENT_STACK_PLUGINS_DIR=str(self.tmp / "no-plugins"))
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)
        out = subprocess.run(["python3", str(PLAN_HOOK)], input=json.dumps(data), capture_output=True, text=True,
                             env=env, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stderr, "")
        return json.loads(out.stdout) if out.stdout.strip() else None

    def book(self):
        path = self.state / "spec-approvals.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []

    def context(self, out):
        return (out or {}).get("hookSpecificOutput", {}).get("additionalContext", "")

    def plan_text(self):
        return (self.project / "PLAN.md").read_text(encoding="utf-8")

    def test_plan_with_spec_section_records_the_lines_as_ke_hoach(self):
        # spec:gd6-spec-theo-lat#S6
        self.run_hook(GOOD_PLAN + SPEC_SECTION)
        rows = self.book()
        self.assertEqual(len(rows), 1, rows)
        row = rows[0]
        self.assertEqual(row["source"], "ke-hoach")
        self.assertIsNone(row["path"])
        self.assertIsNone(row["sha256"])
        self.assertEqual(os.path.realpath(row["top"]), os.path.realpath(str(self.project)))
        self.assertEqual(row["lines"], [line_hash("S1", "Khi bạn duyệt kế hoạch thì sổ ghi dòng này"),
                                        line_hash("S2", "Khi kế hoạch có spec thì hook ghi hết")])

    def test_plan_without_spec_section_adds_no_record_and_no_reminder(self):
        # spec:gd6-spec-theo-lat#S6
        out = self.run_hook(GOOD_PLAN)
        self.assertEqual(self.book(), [])
        shown = self.context(out) + " " + (out or {}).get("systemMessage", "")
        self.assertNotIn("spec", shown.lower())

    def test_plan_exit_from_a_subagent_records_nothing(self):
        # spec:gd6-spec-theo-lat#S6
        self.run_hook(GOOD_PLAN + SPEC_SECTION, agent_id="sub1")
        self.assertEqual(self.book(), [])

    def test_nested_sub_bullets_join_their_criterion(self):
        # spec:gd6-spec-theo-lat#S11
        plan = GOOD_PLAN.replace(GOOD_PLAN[GOOD_PLAN.index("## Tiêu chí xong"):GOOD_PLAN.index("## Các bước")],
                                 NESTED_CRITERIA + "\n")
        self.run_hook(plan)
        text = self.plan_text()
        line = next((x for x in text.splitlines() if "Tiêu chí xong" in x), "")
        self.assertTrue(line, text)
        body = line.split("): ", 1)[1]
        self.assertEqual(len(re.findall(r"(?<![\w(])\d\) ", body)), 3, body)
        self.assertIn("1) Quy trình chạy trọn:", body)
        order = [body.index(s) for s in ("1) Quy trình chạy trọn:", "(A) việc một", "(B) việc hai",
                                         "2) Có trang spec.", "3) Test khóa đạt.")]
        self.assertEqual(order, sorted(order), body)
        self.assertNotIn("4)", body)


if __name__ == "__main__":
    import unittest
    unittest.main()
