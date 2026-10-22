"""Mọi skill trong plugin phải hợp lệ theo chuẩn Agent Skills; agent reviewer phải còn chỉ đọc."""
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
                self.assertLessEqual(len(desc), 1024, "chuẩn Agent Skills giới hạn description 1.024 ký tự")
                combined = len(desc) + len(fm.get("when_to_use", ""))
                self.assertLessEqual(combined, 1536, "Claude Code cắt description + when_to_use ở 1.536 ký tự")

    def test_scripts_referenced_exist(self):
        for path in self.skills():
            text = path.read_text(encoding="utf-8")
            for rel in re.findall(r"\$\{CLAUDE_SKILL_DIR\}/([\w./-]+)", text):
                with self.subTest(skill=path.parent.name, ref=rel):
                    self.assertTrue((path.parent / rel).exists(), f"{rel} không tồn tại")


class ReviewerAgent(unittest.TestCase):
    """Nâng cấp prompt của reviewer không được làm mất ràng buộc chỉ đọc, bước phản biện, ngưỡng tin cậy và ghi nguồn."""

    WRITE_TOOLS = {"Write", "Edit", "NotebookEdit"}

    def setUp(self):
        self.text = (PLUGIN / "agents" / "reviewer.md").read_text(encoding="utf-8")
        self.fm = frontmatter(self.text)
        self.body = self.text.split("\n---", 1)[1]  # phần sau frontmatter

    @staticmethod
    def names(value: str) -> set:
        return {t.strip() for t in value.split(",") if t.strip()}

    def test_frontmatter_valid_and_read_only(self):
        self.assertEqual(self.fm.get("name"), "reviewer")
        for key in ("description", "tools", "disallowedTools", "model", "effort"):
            self.assertTrue(self.fm.get(key), f"thiếu {key} trong frontmatter")
        tools = self.names(self.fm["tools"])
        self.assertIn("Read", tools)
        self.assertFalse(tools & self.WRITE_TOOLS, "reviewer không được có công cụ ghi")
        self.assertTrue(self.WRITE_TOOLS <= self.names(self.fm["disallowedTools"]), "phải cấm tường minh công cụ ghi")

    def test_has_refutation_step_and_confidence_threshold(self):
        # chỉ kiểm có ý, không ghim câu chữ: không phân biệt hoa thường, nhận vài cách viết khác nhau
        for pattern, what in ((r"^\s*\d+\.\s*(?:phản biện|bác bỏ|verifier)", "một bước đánh số mở đầu bằng phản biện"),
                              (r"0\s*(?:đến|-|–)\s*100", "thang tin cậy 0 đến 100"),
                              (r"(?:dưới|<)\s*80", "ngưỡng bỏ dưới 80")):
            with self.subTest(what=what):
                self.assertIsNotNone(re.search(pattern, self.body, re.IGNORECASE | re.MULTILINE),
                                     f"reviewer.md thiếu {what}")

    def test_third_party_sources_are_credited(self):
        notices = (PLUGIN / "NOTICES.md").read_text(encoding="utf-8")
        self.assertIn("claude-code-security-review", self.text)  # file nguồn nhắc nguồn MIT
        for needle in ("claude-code-security-review", "MIT", "Copyright (c) 2025 Anthropic",
                       "defending-code-reference-harness", "Apache"):
            with self.subTest(needle=needle):
                self.assertIn(needle, notices)


if __name__ == "__main__":
    unittest.main()
