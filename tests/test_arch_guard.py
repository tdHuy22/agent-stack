"""GĐ3, TM-111: hook pretool_guard giữ giao thức archctl. Agent không ghi file luật trong `.arch/` (Write, Edit,
MultiEdit, NotebookEdit, lệnh shell, trình thông dịch) và không chạy lệnh chỉ người được chạy (`accept`, `reject`,
`baseline`, `serve`, `init --force`), kể cả qua đường dẫn tuyệt đối, env, sudo, `bash -c`, xargs, find -exec. Ghi đề
xuất (`archctl propose`, `block`) và đọc luật vẫn qua. Ca của pi đi qua cùng hook với payload của cầu nối."""
import json

from tests._util import PLUGIN, git
from tests.test_guard import GuardBase

PROTECTED = ("system.arch", "decisions.md", "baseline", ".archignore", ".verified")


class ArchProtocolGuard(GuardBase):
    def setUp(self):
        super().setUp()
        arch = self.project / ".arch"
        arch.mkdir()
        for name in PROTECTED:
            (arch / name).write_text("x\n")
        (arch / "proposals.arch").write_text("")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "arch")

    def assert_denied(self, result, what):
        self.assertIsNotNone(result, what)
        self.assertEqual(result[0], "deny", what)

    def test_rules_files_cannot_be_written_by_tools(self):
        for name in PROTECTED:
            full = str(self.project / ".arch" / name)
            for tool, ti in (("Write", {"file_path": full, "content": "allow Web -> Report\n"}),
                             ("Edit", {"file_path": full, "old_string": "x", "new_string": "y"}),
                             ("MultiEdit", {"file_path": full, "edits": [{"old_string": "x", "new_string": "y"}]}),
                             ("NotebookEdit", {"notebook_path": full, "new_source": "y"}),
                             ("Write", {"file_path": f".arch/{name}", "content": "y"})):
                with self.subTest(tool=tool, name=name, path=ti.get("file_path")):
                    out = self.guard(tool, ti)
                    self.assert_denied(out, f"{tool} {name}")
                    self.assertIn("archctl propose", out[1])

    def test_symlink_to_rules_file_is_seen(self):
        link = self.project / "rules-link"
        link.symlink_to(self.project / ".arch" / "system.arch")
        self.assert_denied(self.guard("Write", {"file_path": str(link), "content": "y"}), "symlink")

    def test_proposals_and_other_files_stay_writable(self):
        self.assertIsNone(self.guard("Write", {"file_path": str(self.project / ".arch" / "proposals.arch"),
                                               "content": "proposal p-1 @ai 2026-11-14\n"}))
        self.assertIsNone(self.guard("Write", {"file_path": str(self.project / "app" / "system.arch.md"),
                                               "content": "ghi chú"}))

    def test_shell_writes_to_rules_files_are_blocked(self):
        for cmd in ["echo 'allow Web -> Report' >> .arch/system.arch",
                    "printf x > .arch/decisions.md",
                    "sed -i '' s/deny/allow/ .arch/system.arch",
                    "cp /tmp/x .arch/baseline",
                    "mv .arch/system.arch /tmp/old",
                    "rm .arch/.verified",
                    "rm -rf .arch",
                    "tee .arch/.archignore < /dev/null",
                    "git checkout HEAD~1 -- .arch/system.arch",
                    "cd .arch && echo x > system.arch",
                    "python3 -c \"open('.arch/system.arch','a').write('allow A -> B')\"",
                    "python3 - <<'EOF'\nopen('.arch/decisions.md','w').write('ok')\nEOF",
                    "bash -c 'echo x >> .arch/system.arch'"]:
            with self.subTest(cmd=cmd):
                self.assert_denied(self.bash(cmd), cmd)

    def test_human_only_commands_are_blocked_in_every_form(self):
        for cmd in ["archctl accept p-0123 --reason ok",
                    "archctl reject p-0123 --reason no",
                    "archctl baseline",
                    "archctl serve --port 4000",
                    "archctl init --force",
                    "archctl --root . accept p-1 --reason ok",
                    "/Users/x/.cargo/bin/archctl accept p-1 --reason ok",
                    "env FOO=1 archctl baseline",
                    "sudo archctl baseline",
                    "bash -c \"archctl reject p-2 --reason x\"",
                    "eval 'archctl accept p-3 --reason y'",
                    "echo p-1 | xargs archctl accept --reason ok",
                    "find . -name x -exec archctl baseline \\;",
                    "archctl check && archctl accept p-4 --reason z"]:
            with self.subTest(cmd=cmd):
                out = self.bash(cmd)
                self.assert_denied(out, cmd)
                self.assertIn("lệnh của người dùng", out[1])

    def test_agent_side_protocol_commands_pass(self):
        for cmd in ["archctl propose 'allow Web -> Report' --reason 'cần gọi báo cáo'",
                    "archctl block --on 'deny Web -> Report' --reason 'bế tắc'",
                    "archctl check --changed", "archctl check --strict", "archctl verify", "archctl proposals",
                    "archctl init --from-code --no-hooks", "archctl diff HEAD~1",
                    "cat .arch/system.arch", "git diff -- .arch/system.arch", "grep deny .arch/system.arch",
                    "echo accept"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd), cmd)

    def test_pi_payload_is_guarded_too(self):
        """Cầu nối pi gửi PreToolUse với tool_input {file_path, content} cho write/edit, {command} cho bash
        (tool_map trong pi.json)."""
        tool_map = json.loads((PLUGIN / "hosts" / "pi.json").read_text())["hooks"]["PreToolUse"]["tool_map"]
        for tool, ti in ((tool_map["write"], {"file_path": str(self.project / ".arch/system.arch"), "content": "y"}),
                         (tool_map["edit"], {"file_path": ".arch/decisions.md", "content": None}),
                         (tool_map["bash"], {"command": "archctl accept p-1 --reason ok"})):
            with self.subTest(tool=tool):
                out = self.hook("pretool_guard.py", {"session_id": "pi1", "cwd": str(self.project),
                                                     "hook_event_name": "PreToolUse", "transcript_path": "",
                                                     "interactive": False, "tool_name": tool, "tool_input": ti},
                                AGENT_STACK_HOST="pi")
                self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
