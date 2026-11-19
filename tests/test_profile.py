"""Việc G mục 1 (19/11/2026): công tắc bộ plugin "gọn" ↔ "đủ" theo project (`profile.py`).

"gọn" ghi vào `.claude/settings.local.json` của project (phạm vi local của Claude Code, đè user): `enabledPlugins` false
cho plugin ít dùng, `skillOverrides` "name-only" cho skill ít dùng (chỉ còn tên, bỏ mô tả khỏi phần nạp sẵn). "đủ" trả
đúng giá trị cũ của các khóa đã đổi, giữ khóa người dùng tự đổi sau đó. Danh sách lấy từ `profiles.gon` của
`.agent/stack.json`, không có thì dùng mặc định của script."""
import json
import os
import subprocess
import sys

from tests._util import PLUGIN, TempDirTestCase

PROFILE = PLUGIN / "skills" / "project-setup" / "scripts" / "profile.py"


class ProfileTests(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.state = self.tmp / "state"
        self.project = self.tmp / "proj"
        (self.project / ".claude").mkdir(parents=True)
        (self.project / ".agent").mkdir()
        self.local = self.project / ".claude" / "settings.local.json"
        self.local.write_text(json.dumps({"enabledPlugins": {"pyright-lsp@claude-plugins-official": True,
                                                             "playground@claude-plugins-official": True},
                                          "permissions": {"allow": ["Bash(ls)"]}}))
        self.before = json.loads(self.local.read_text())
        (self.project / ".agent" / "stack.json").write_text(json.dumps({"profiles": {"gon": {
            "plugins_off": ["playground@claude-plugins-official", "html-plan@agent-stack-vendor-local"],
            "skills_name_only": ["agent-stack:aside-web", "anthropic-skills:docx"]}}}))

    def run_profile(self, *args, expect=0):
        env = dict(os.environ, AGENT_STACK_STATE=str(self.state))
        out = subprocess.run([sys.executable, str(PROFILE), "--project", str(self.project), *args],
                             capture_output=True, text=True, env=env, timeout=30)
        self.assertEqual(out.returncode, expect, out.stdout + out.stderr)
        return out.stdout

    def settings(self):
        return json.loads(self.local.read_text())

    def test_gon_then_du_round_trip_in_one_command_each(self):
        out = self.run_profile("gon")
        self.assertIn("gọn", out)
        data = self.settings()
        self.assertIs(data["enabledPlugins"]["playground@claude-plugins-official"], False)
        self.assertIs(data["enabledPlugins"]["html-plan@agent-stack-vendor-local"], False)
        self.assertIs(data["enabledPlugins"]["pyright-lsp@claude-plugins-official"], True)
        self.assertEqual(data["skillOverrides"], {"agent-stack:aside-web": "name-only",
                                                  "anthropic-skills:docx": "name-only"})
        self.assertEqual(data["permissions"], {"allow": ["Bash(ls)"]})
        self.assertIn("gọn", self.run_profile("show"))
        self.run_profile("du")
        self.assertEqual(self.settings(), self.before)
        self.assertIn("đủ", self.run_profile("show"))

    def test_gon_twice_keeps_original_for_du(self):
        self.run_profile("gon")
        self.run_profile("gon")
        self.run_profile("du")
        self.assertEqual(self.settings(), self.before)

    def test_du_keeps_keys_the_user_changed_afterwards(self):
        self.run_profile("gon")
        data = self.settings()
        data["enabledPlugins"]["html-plan@agent-stack-vendor-local"] = True  # người dùng tự bật lại
        data["model"] = "sonnet"
        self.local.write_text(json.dumps(data))
        self.run_profile("du")
        data = self.settings()
        self.assertIs(data["enabledPlugins"]["html-plan@agent-stack-vendor-local"], True)
        self.assertIs(data["enabledPlugins"]["playground@claude-plugins-official"], True)
        self.assertEqual(data["model"], "sonnet")
        self.assertNotIn("skillOverrides", data)

    def test_dry_run_changes_nothing(self):
        out = self.run_profile("gon", "--dry-run")
        self.assertIn("playground@claude-plugins-official", out)
        self.assertEqual(self.settings(), self.before)

    def test_without_settings_file_or_stack_json_uses_defaults_and_du_removes_file_content(self):
        self.local.unlink()
        (self.project / ".agent" / "stack.json").unlink()
        self.run_profile("gon")
        data = self.settings()
        self.assertTrue(data["enabledPlugins"])
        self.assertTrue(all(v is False for v in data["enabledPlugins"].values()))
        self.assertTrue(all(v == "name-only" for v in data["skillOverrides"].values()))
        self.run_profile("du")
        self.assertEqual(self.settings(), {})

    def test_json_show(self):
        self.run_profile("gon")
        info = json.loads(self.run_profile("show", "--json"))
        self.assertEqual(info["profile"], "gon")
        self.assertIn("playground@claude-plugins-official", info["plugins_off"])

    def test_refuses_symlinked_settings_and_bad_json(self):
        target = self.tmp / "ngoai.json"
        target.write_text("{}")
        self.local.unlink()
        self.local.symlink_to(target)
        self.run_profile("gon", expect=1)
        self.assertEqual(target.read_text(), "{}")
        self.local.unlink()
        self.local.write_text("{hỏng")
        self.run_profile("gon", expect=1)
        self.assertEqual(self.local.read_text(), "{hỏng")

    def test_bad_names_in_stack_json_are_ignored(self):
        (self.project / ".agent" / "stack.json").write_text(json.dumps({"profiles": {"gon": {
            "plugins_off": ["../x", "ok@m", 5], "skills_name_only": ["__proto__", "a:b", "x" * 200]}}}))
        self.run_profile("gon")
        data = self.settings()
        self.assertIn("ok@m", data["enabledPlugins"])
        self.assertNotIn("../x", data["enabledPlugins"])
        self.assertEqual(data["skillOverrides"], {"a:b": "name-only"})

    def test_stack_json_cannot_turn_off_agent_stack_itself(self):
        # TM-154: stack.json nằm trong repo, không tin được: không tắt được plugin chứa các hook chặn.
        (self.project / ".agent" / "stack.json").write_text(json.dumps({"profiles": {"gon": {
            "plugins_off": ["agent-stack@agent-stack-local", "ok@m"]}}}))
        self.run_profile("gon")
        data = self.settings()
        self.assertNotIn("agent-stack@agent-stack-local", data["enabledPlugins"])
        self.assertIs(data["enabledPlugins"]["ok@m"], False)

    def test_symlinked_temp_file_cannot_redirect_the_write(self):
        # review opus·xhigh 19/11 (TM-155): repo lạ commit sẵn file tạm là symlink ra ngoài.
        victim = self.tmp / "victim.txt"
        victim.write_text("giữ nguyên\n")
        (self.project / ".claude" / "settings.local.json.agent-stack.tmp").symlink_to(victim)
        self.run_profile("gon")
        self.assertEqual(victim.read_text(), "giữ nguyên\n")
        self.assertFalse(self.local.is_symlink())
        self.assertIs(self.settings()["enabledPlugins"]["playground@claude-plugins-official"], False)

    def test_agent_stack_marketplace_is_protected_in_any_case(self):
        (self.project / ".agent" / "stack.json").write_text(json.dumps({"profiles": {"gon": {
            "plugins_off": ["Agent-Stack@agent-stack-local", "other@AGENT-STACK-LOCAL", "ok@m"]}}}))
        self.run_profile("gon")
        self.assertEqual({k: v for k, v in self.settings()["enabledPlugins"].items() if v is False}, {"ok@m": False})
