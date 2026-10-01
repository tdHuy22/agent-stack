"""Mọi skill trong plugin phải hợp lệ cho cả Claude Code lẫn OpenCode."""
import re
import sys
import unittest

from tests._util import PLUGIN

sys.path.insert(0, str(PLUGIN / "skills" / "vet-skill" / "scripts"))
from vet import frontmatter  # noqa: E402

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class SkillMetadata(unittest.TestCase):
    def skills(self):
        found = sorted((PLUGIN / "skills").glob("*/SKILL.md"))
        self.assertTrue(found, "chưa có skill nào")
        return found

    def test_name_and_description_limits(self):
        for path in self.skills():
            with self.subTest(skill=path.parent.name):
                fm = frontmatter(path.read_text(encoding="utf-8"))
                self.assertEqual(fm.get("name"), path.parent.name, "name phải trùng tên thư mục")
                self.assertRegex(fm["name"], NAME_RE)
                self.assertLessEqual(len(fm["name"]), 64)
                desc = fm.get("description", "")
                self.assertGreater(len(desc), 40, "description quá ngắn để kích hoạt đúng")
                self.assertLessEqual(len(desc), 1024, "OpenCode giới hạn description 1.024 ký tự")
                combined = len(desc) + len(fm.get("when_to_use", ""))
                self.assertLessEqual(combined, 1536, "Claude Code cắt description + when_to_use ở 1.536 ký tự")

    def test_scripts_referenced_exist(self):
        for path in self.skills():
            text = path.read_text(encoding="utf-8")
            for rel in re.findall(r"\$\{CLAUDE_SKILL_DIR\}/([\w./-]+)", text):
                with self.subTest(skill=path.parent.name, ref=rel):
                    self.assertTrue((path.parent / rel).exists(), f"{rel} không tồn tại")


if __name__ == "__main__":
    unittest.main()
