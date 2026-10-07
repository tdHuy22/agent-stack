"""Luật toàn cục: Claude Code nạp SHARED + CLAUDE; OpenCode nạp AGENTS, file ghép từ SHARED + OPENCODE."""
from __future__ import annotations

import subprocess
import sys
import unittest

from tests._util import REPO, TempDirTestCase

sys.path.insert(0, str(REPO / "tools"))
import build_rules  # noqa: E402

GLOBAL = REPO / "global"
# Dấu hiệu của luật chỉ dành cho OpenCode: Claude Code không được nạp chúng.
OPENCODE_ONLY = ("route.py --session", "Subagent là `build`")


def read(name):
    return (GLOBAL / name).read_text(encoding="utf-8")


class GlobalRules(unittest.TestCase):
    def test_opencode_file_is_built_from_sources(self):
        self.assertEqual(read("AGENTS.global.md"), build_rules.build(GLOBAL),
                         "global/AGENTS.global.md cũ hơn nguồn: chạy python3 tools/build_rules.py")

    def test_claude_imports_shared_rules_only(self):
        claude = read("CLAUDE.global.md")
        imports = [line for line in claude.splitlines() if line.startswith("@")]
        self.assertEqual(imports, ["@~/Documents/Claude/agent-stack/global/SHARED.global.md"])
        claude_view = read("SHARED.global.md") + claude
        for marker in OPENCODE_ONLY:
            self.assertNotIn(marker, claude_view)

    def test_opencode_view_has_shared_and_opencode_rules(self):
        opencode_view = read("AGENTS.global.md")
        self.assertIn(read("SHARED.global.md").strip(), opencode_view)
        self.assertIn(read("OPENCODE.global.md").strip(), opencode_view)
        for marker in OPENCODE_ONLY:
            self.assertIn(marker, opencode_view)
        self.assertNotIn("| Subagent | Skill |", opencode_view)  # bảng chọn là riêng Claude Code

    def test_skill_fallback_is_shared(self):
        # Plugin Claude Code trên máy có thể cũ hơn repo (chưa có skill mới), nên Claude cũng cần đường dự phòng này.
        self.assertIn("/SKILL.md` rồi làm theo", read("SHARED.global.md"))

    def test_footer_rule_is_shared(self):
        shared = read("SHARED.global.md")
        self.assertIn("Cuối mọi câu trả lời, kể cả câu trả lời ngắn", shared)
        self.assertIn("· Skill: <tên|không>", shared)


class BuildScript(TempDirTestCase):
    def write_sources(self):
        (self.tmp / "SHARED.global.md").write_text("# chung\n- a\n", encoding="utf-8")
        (self.tmp / "OPENCODE.global.md").write_text("# riêng\n- b\n", encoding="utf-8")

    def test_build_writes_then_check_passes(self):
        self.write_sources()
        self.assertEqual(build_rules.main([], root=self.tmp), 0)
        text = (self.tmp / "AGENTS.global.md").read_text(encoding="utf-8")
        self.assertIn("# chung\n- a\n", text)
        self.assertIn("# riêng\n- b\n", text)
        self.assertLess(text.index("# chung"), text.index("# riêng"))
        self.assertEqual(build_rules.main(["--check"], root=self.tmp), 0)

    def test_check_fails_when_a_source_changes(self):
        self.write_sources()
        build_rules.main([], root=self.tmp)
        (self.tmp / "SHARED.global.md").write_text("# chung\n- a đã sửa\n", encoding="utf-8")
        self.assertEqual(build_rules.main(["--check"], root=self.tmp), 1)

    def test_cli_check_on_repo(self):
        out = subprocess.run([sys.executable, str(REPO / "tools" / "build_rules.py"), "--check"],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)


if __name__ == "__main__":
    unittest.main()
