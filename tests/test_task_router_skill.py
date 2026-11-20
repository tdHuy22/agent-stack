"""Skill task-router trả đúng bảng của chính nó (eval H 20/11/2026: có skill 8/12).

Hai nguyên nhân lệch:
- Skill chạy `context: fork` chỉ thấy `$ARGUMENTS`; model gọi skill không kèm args ở 7/12 lượt, nên bản fork không biết
  việc là gì và model chính tự đoán.
- "thêm chức năng upload …" không khớp luật `feature`, nên luật `feature-boundary` (chỉ tinh chỉnh `feature`) không áp
  và `route.py` ra null.
"""
import re
import subprocess
import sys

from tests._util import PLUGIN, TempDirTestCase

SKILL = PLUGIN / "skills" / "task-router" / "SKILL.md"
ROUTE = PLUGIN / "skills" / "task-router" / "scripts" / "route.py"
sys.path.insert(0, str(ROUTE.parent))
sys.path.insert(0, str(PLUGIN / "lib"))
import route  # noqa: E402

UPLOAD = "Mình sắp thêm chức năng upload ảnh đại diện cho người dùng vào web app Flask; project chưa có test."
BUGFIX = "Mình sắp sửa một lỗi KeyError có traceback rõ trong hàm parse_config; project có bộ test pytest đầy đủ."


def frontmatter(text: str) -> str:
    return text.split("---", 2)[1]


class TaskRouterSkill(TempDirTestCase):
    def line(self, text):
        out = subprocess.run([sys.executable, str(ROUTE), "--line", text], capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        return out.stdout.strip()

    def test_skill_runs_inline_so_it_sees_the_task(self):
        # Bản fork chỉ nhận args; chạy trong phiên thì model thấy tin của người dùng dù gọi skill không kèm args.
        head = frontmatter(SKILL.read_text(encoding="utf-8"))
        self.assertNotRegex(head, r"(?m)^context:\s*fork")
        self.assertNotRegex(head, r"(?m)^model:")  # model: mà không fork thì đổi model cả phiên (mục 10)

    def test_new_feature_touching_trust_boundary_routes_to_feature_boundary(self):
        for text in (UPLOAD, "thêm chức năng đăng nhập bằng Google cho web app"):
            hit = route.suggest(text)
            self.assertIsNotNone(hit, text)
            self.assertEqual((hit["rule"], hit["model"], hit["effort"]), ("feature-boundary", "sonnet", "high"), text)
            self.assertIn("threat-model", hit["skills"])

    def test_line_mode_prints_the_answer_line(self):
        out = self.line(BUGFIX)
        self.assertRegex(out, r"^➡️ Model: sonnet · Effort: high · Subagent: agent-stack:test-runner · Skill: không · "
                              r"Lý do: .+")
        self.assertIn("Skill: threat-model, reuse-best", self.line(UPLOAD))

    def test_line_mode_without_a_rule_points_to_the_table(self):
        out = self.line("xin chào")
        self.assertFalse(out.startswith("➡️"), out)  # không có dòng trả lời giả
        self.assertIn("Bảng mặc định cho dòng ➡️", out)

    def test_skill_tells_model_to_run_line_mode_and_keep_its_answer(self):
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn('route.py" --line', text)
        step1 = text[text.index("## Bước 1"):text.index("## Bước 2")]
        self.assertRegex(step1, re.compile(r"giữ nguyên", re.I))
