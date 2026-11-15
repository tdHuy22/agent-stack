"""Hook pretool_guard với cấu hình project (GĐ4, TM-119): `stack.py approve` chỉ qua khi tin người dùng bảo duyệt đúng
mục; bản chụp đã duyệt trong state/stack-approved/ không ghi thẳng được."""
from tests.test_guard import GuardBase

APPROVE = "python3 ~/Documents/Claude/agent-stack/plugin/skills/project-setup/scripts/stack.py approve ignore:schema"


class StackApproveGuard(GuardBase):
    def test_approve_needs_the_user_to_name_the_item(self):
        self.start("làm tiếp đi", "a1")
        self.assertEqual(self.bash(APPROVE, "a1")[0], "deny")
        self.start("duyệt lattice", "a2")
        self.assertEqual(self.bash(APPROVE, "a2")[0], "deny", "tin nêu mục khác")
        self.start("đừng duyệt schema", "a3")
        self.assertEqual(self.bash(APPROVE, "a3")[0], "deny", "phủ định")
        self.start("duyệt schema?", "a4")
        self.assertEqual(self.bash(APPROVE, "a4")[0], "deny", "câu hỏi")
        self.start("Ok, duyệt bỏ qua schema", "a5")
        self.assertIsNone(self.bash(APPROVE, "a5"))
        self.assertEqual(self.bash(APPROVE, "a5")[0], "deny", "một tin chỉ duyệt một lần")

    def test_approve_through_a_runner_is_still_gated(self):
        self.start("làm tiếp", "r1")
        for cmd in ["uv run python3 -X utf8 stack.py approve ignore:schema", "env python3 stack.py approve all"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash(cmd, "r1")[0], "deny")

    def test_other_subcommands_pass(self):
        self.start("làm tiếp", "o1")
        for cmd in ["python3 stack.py check", "python3 stack.py scan .", "python3 stack.py learn"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd, "o1"))

    def test_snapshot_cannot_be_written_directly(self):
        snap = self.state / "stack-approved" / "abc.json"
        snap.parent.mkdir(parents=True, exist_ok=True)
        snap.write_text("{}")
        self.start("làm tiếp", "w1")
        self.assertEqual(self.guard("Write", {"file_path": str(snap), "content": "{}"}, "w1")[0], "deny")
        self.assertEqual(self.guard("Edit", {"file_path": str(snap), "old_string": "{", "new_string": "["}, "w1")[0],
                         "deny")
        for cmd in [f"echo '{{}}' > {snap}", f"rm {snap}", "python3 -c 'import stackcfg; stackcfg.save_snapshot(1, 2)'",
                    "python3 - <<'EOF'\nopen('state/stack-approved/x.json','w')\nEOF"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash(cmd, "w1")[0], "deny")
