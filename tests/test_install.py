"""install.py chạy trên HOME giả và agent-stack giả; `claude` giả chỉ ghi lại lệnh được gọi."""
import json
import os
import shutil
import subprocess
import sys

from tests._util import REPO, TempDirTestCase

INSTALL = REPO / "tools" / "install.py"
FAKE_CLAUDE = """#!/usr/bin/env python3
import sys, os
with open(os.environ["FAKE_CLAUDE_LOG"], "a") as fh:
    fh.write(" ".join(sys.argv[1:]) + "\\n")
sys.exit(int(os.environ.get("FAKE_CLAUDE_EXIT", "0")))
"""


class InstallTests(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.stack = self.tmp / "stack"
        for rel in ("global", "plugin/skills", "statusline", "opencode/agents", ".claude-plugin"):
            (self.stack / rel).mkdir(parents=True)
        (self.stack / "global" / "CLAUDE.global.md").write_text("# luật claude\n")
        (self.stack / "global" / "AGENTS.global.md").write_text("# luật chung\n")
        (self.stack / "plugin" / "skills" / "tien-do").mkdir()
        (self.stack / "plugin" / "skills" / "tien-do" / "SKILL.md").write_text("---\nname: tien-do\n---\n")
        (self.stack / "opencode" / "agents" / "worker.md").write_text("---\nmode: all\n---\n")
        (self.stack / "statusline" / "statusline.py").write_text("print('x')\n")
        shutil.copy(REPO / ".claude-plugin" / "marketplace.json", self.stack / ".claude-plugin" / "marketplace.json")
        self.lock = {"version": 1, "entries": {}}
        self.catalog = {"items": []}
        self.save()
        self.fake = self.tmp / "claude"
        self.fake.write_text(FAKE_CLAUDE)
        self.fake.chmod(0o755)
        self.calls = self.tmp / "calls.log"

    def save(self):
        (self.stack / "vetted.lock").write_text(json.dumps(self.lock, ensure_ascii=False))
        (self.stack / "catalog.json").write_text(json.dumps(self.catalog, ensure_ascii=False))

    def run_install(self, *args, expect=0, extra_env=None):
        env = dict(os.environ, HOME=str(self.home), AGENT_STACK_HOME=str(self.stack),
                   AGENT_STACK_CLAUDE_BIN=str(self.fake), FAKE_CLAUDE_LOG=str(self.calls), **(extra_env or {}))
        out = subprocess.run([sys.executable, str(INSTALL), *args], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(out.returncode, expect, out.stdout + out.stderr)
        return out.stdout

    def calls_made(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_dry_run_changes_nothing(self):
        out = self.run_install()
        self.assertIn("XEM TRƯỚC", out)
        self.assertIn("+ symlink", out)
        self.assertEqual(list(self.home.iterdir()), [])
        self.assertEqual(self.calls_made(), [])

    def test_apply_then_rollback(self):
        settings = self.home / ".claude" / "settings.json"
        settings.parent.mkdir()
        settings.write_text(json.dumps({"model": "sonnet", "skipWorkflowUsageWarning": True}))
        out = self.run_install("--apply", "--restore-workflow-warning")
        self.assertIn("THỰC HIỆN", out)
        claude_md = self.home / ".claude" / "CLAUDE.md"
        self.assertEqual(os.readlink(claude_md), str(self.stack / "global" / "CLAUDE.global.md"))
        self.assertTrue((self.home / ".config" / "opencode" / "AGENTS.md").is_symlink())
        self.assertTrue((self.home / ".config" / "opencode" / "skills" / "tien-do").is_symlink())
        self.assertTrue((self.home / ".config" / "opencode" / "agents" / "worker.md").is_symlink())
        data = json.loads(settings.read_text())
        self.assertEqual(data["model"], "sonnet")
        self.assertIn("statusline.py", data["statusLine"]["command"])
        self.assertIs(data["autoContinueAtUsageLimit"], True)
        self.assertIn("Tổng kết:", out)
        self.assertNotIn("skipWorkflowUsageWarning", data)
        self.assertIn(f"plugin marketplace add {self.stack}", self.calls_made())
        self.assertIn("plugin install agent-stack@agent-stack-local --scope user", self.calls_made())
        # chạy lại không tạo thay đổi trùng
        self.assertIn("= đã có", self.run_install("--apply", "--only", "rules"))
        self.run_install("--rollback", "--apply")
        self.assertFalse(claude_md.exists() or claude_md.is_symlink())
        self.assertEqual(json.loads(settings.read_text()), {"model": "sonnet", "skipWorkflowUsageWarning": True})
        self.assertIn("plugin uninstall agent-stack@agent-stack-local --scope user", self.calls_made())

    def test_existing_user_file_is_kept_unless_replace(self):
        claude_md = self.home / ".claude" / "CLAUDE.md"
        claude_md.parent.mkdir()
        claude_md.write_text("ghi chú riêng của tôi\n")
        out = self.run_install("--apply", "--only", "rules", expect=2)
        self.assertIn(f"- bỏ qua: {claude_md}", out)
        self.assertIn("Cài chưa đủ", out)
        self.assertFalse(claude_md.is_symlink())
        self.run_install("--apply", "--only", "rules", "--replace-existing")
        self.assertTrue(claude_md.is_symlink())
        self.run_install("--rollback", "--apply")
        self.assertEqual(claude_md.read_text(), "ghi chú riêng của tôi\n")

    def test_only_approved_items_are_installed_and_vendored(self):
        cache = self.stack / ".vet-cache" / "o__r@abcdefabcdef"
        (cache / "skill").mkdir(parents=True)
        (cache / "skill" / "SKILL.md").write_text("---\nname: demo\n---\n")
        (cache / "skill" / ".claude-plugin").mkdir()
        self.lock["entries"] = {
            "o/r:skill": {"verdict": "PASS", "sha": "abcdefabcdef1234", "subpath": "skill",
                          "report": "vet-reports/o__r@abcdefabcdef.md", "human_review": {"status": "approved"}},
            "x/y": {"verdict": "REVIEW", "sha": "1", "report": "vet-reports/x__y@1.md",
                    "human_review": {"status": "pending"}},
            "p/q": {"verdict": "PASS", "sha": "2", "report": "vet-reports/p__q@2.md",
                    "human_review": {"status": "approved"}},
        }
        self.catalog["items"] = [
            {"key": "o/r:skill", "kind": "vendor-skill", "scope": "user", "install": {"name": "demo"}},
            {"key": "x/y", "kind": "claude-plugin", "scope": "user", "install": {"marketplace": "m", "plugin": "y"}},
            {"key": "p/q", "kind": "claude-plugin", "scope": "project", "install": {"marketplace": "m", "plugin": "q"}},
        ]
        self.save()
        out = self.run_install("--apply", "--only", "catalog,opencode")
        self.assertIn("chờ duyệt: x/y", out)
        self.assertIn("project: tự cài khi cần", out)
        self.assertTrue((self.stack / "vendor" / "skills" / "demo" / "SKILL.md").exists())
        self.assertFalse((self.stack / "vendor" / "skills" / "demo" / ".claude-plugin").exists())
        self.assertTrue((self.home / ".config" / "opencode" / "skills" / "demo").is_symlink())
        mp = json.loads((self.stack / ".claude-plugin" / "marketplace.json").read_text())
        self.assertIn("agent-stack-vendor", [p["name"] for p in mp["plugins"]])
        made = self.calls_made()
        self.assertIn("plugin install agent-stack-vendor@agent-stack-local --scope user", made)
        self.assertFalse(any("y@m" in c or "q@m" in c for c in made))

    def test_failed_command_is_reported_and_exits_1(self):
        out = self.run_install("--apply", "--only", "plugin", expect=1, extra_env={"FAKE_CLAUDE_EXIT": "1"})
        self.assertIn("0 mục bị bỏ qua, 2 lỗi", out)  # marketplace add và plugin install đều lỗi
        self.assertIn("- lỗi:", out)
        self.assertFalse((self.stack / "state" / "install-logs").exists())  # không ghi bước lỗi vào nhật ký hoàn tác

    def test_existing_autocontinue_choice_is_kept(self):
        settings = self.home / ".claude" / "settings.json"
        settings.parent.mkdir()
        settings.write_text(json.dumps({"autoContinueAtUsageLimit": False}))
        out = self.run_install("--apply", "--only", "autocontinue")
        self.assertIn("giữ nguyên", out)
        self.assertIs(json.loads(settings.read_text())["autoContinueAtUsageLimit"], False)

    def test_invalid_settings_json_is_left_alone(self):
        settings = self.home / ".claude" / "settings.json"
        settings.parent.mkdir()
        settings.write_text("{hỏng")
        self.run_install("--apply", "--only", "statusline,autocontinue", expect=1)
        self.assertEqual(settings.read_text(), "{hỏng")
