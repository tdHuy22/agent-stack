"""Mã nguồn của agent-stack không được chứa ký tự vô hình hoặc đảo chiều.

Chính vet-skill bắt loại ký tự này ở đồ của bên thứ ba, nên repo này phải sạch trước.
Trong test và trong luật, viết ký tự đặc biệt bằng escape (backslash + u200b) hoặc chr(0x200B).
"""
import re
import unittest

from tests._util import REPO

INVISIBLE = re.compile("[" + "".join(f"{chr(a)}-{chr(b)}" for a, b in [
    (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x2064), (0x2066, 0x2069), (0xFEFF, 0xFEFF), (0xE0000, 0xE007F)]) + "]")
DIRS = ("plugin", "tools", "statusline", "tests", "global", "opencode", "evals")


class RepoHygiene(unittest.TestCase):
    def test_no_invisible_characters_in_source(self):
        bad = []
        for top in DIRS:
            for path in (REPO / top).rglob("*"):
                if not path.is_file() or path.suffix in (".pyc",):
                    continue
                try:
                    text = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    continue
                for no, line in enumerate(text.splitlines(), 1):
                    if INVISIBLE.search(line):
                        bad.append(f"{path.relative_to(REPO)}:{no}")
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()


class DocsMatchCode(unittest.TestCase):
    """Tài liệu kế hoạch không được nói khác với code (hai lỗi đã gặp ngày 02/10/2026)."""

    def test_opencode_skill_dir_in_docs_matches_install(self):
        install = (REPO / "tools" / "install.py").read_text(encoding="utf-8")
        target = re.search(r"symlink skill \(agent-stack \+ vendor\) vào (\S+?/skills)/", install).group(1)
        plan = (REPO / "KE-HOACH.md").read_text(encoding="utf-8")
        # chỉ các câu nói về nơi install.sh đặt skill cho OpenCode (câu kể lịch sử bản đầu không tính)
        claimed = re.findall(r"(?:`install\.sh` symlink từng skill vào|OpenCode dùng skill qua) `([^`]+?)/?`", plan)
        self.assertTrue(claimed)
        self.assertEqual(set(claimed), {target})

    def test_auto_continue_is_not_claimed_on_by_default(self):
        plan = (REPO / "KE-HOACH.md").read_text(encoding="utf-8")
        self.assertNotIn("mặc định bật từ v2.1.234", plan)
        self.assertIn("mặc định chưa đặt", plan)
