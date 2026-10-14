import json
import sys

from tests._util import PLUGIN, TempDirTestCase, git, run_script
from tests.test_agentstack_lib import PLAN

STATE = PLUGIN / "skills" / "session-keeper" / "scripts" / "state.py"
sys.path.insert(0, str(PLUGIN / "lib"))
import agentstack as A  # noqa: E402


class StateCli(TempDirTestCase):
    def test_init_creates_plan_then_refuses(self):
        out = run_script(STATE, "init", "--project", str(self.tmp))
        self.assertEqual(out.returncode, 0, out.stderr)
        plan = self.tmp / ".agent" / "PLAN.md"
        sec = A.parse_section0(plan.read_text())
        self.assertIsNotNone(sec["heading"])
        self.assertIsNotNone(sec["updated"])
        again = run_script(STATE, "init", "--project", str(self.tmp))
        self.assertEqual(again.returncode, 1)

    def test_show_json(self):
        self.write("PLAN.md", PLAN)
        out = run_script(STATE, "show", "--project", str(self.tmp), "--json")
        data = json.loads(out.stdout)
        self.assertEqual(data["baseline"], "120 passed, 3 xfailed")
        self.assertEqual(len(data["section0"]["next"]), 3)

    def test_show_without_plan(self):
        out = run_script(STATE, "show", "--project", str(self.tmp))
        self.assertEqual(out.returncode, 1)
        self.assertIn("chưa có file kế hoạch", out.stdout)

    def test_handoff_prefills_and_backs_up(self):
        self.write("PLAN.md", PLAN)
        git(self.tmp, "init", "-q")
        git(self.tmp, "add", "-A")
        git(self.tmp, "commit", "-q", "-m", "khởi tạo")
        self.write("draft.md", "nháp\n")
        out = run_script(STATE, "handoff", "--project", str(self.tmp))
        self.assertEqual(out.returncode, 0, out.stderr)
        handoff = (self.tmp / ".agent" / "HANDOFF.md").read_text()
        self.assertIn("1. User chạy `/compact`.".replace("`", ""), handoff.replace("`", ""))
        self.assertIn("120 passed, 3 xfailed", handoff)
        self.assertIn("draft.md", handoff)
        self.assertIn("khởi tạo", handoff)
        sec = A.parse_section0(handoff)  # HANDOFF có §0 nên hook đọc được
        self.assertEqual(len(sec["next"]), 3)
        run_script(STATE, "handoff", "--project", str(self.tmp))
        self.assertTrue((self.tmp / ".agent" / "HANDOFF.prev.md").exists())

    def test_handoff_keeps_only_open_steps(self):
        # Bước ✅ và mục con của nó không sang HANDOFF: HANDOFF mới hơn PLAN nên hook đọc nó thay PLAN.
        self.write("PLAN.md", "# PLAN\n\n## 0. Đang ở đâu, việc tiếp theo\n- **Việc tiếp theo:**\n"
                              "  1. **Bước 3:** ✅ tài liệu thiết kế\n     - chương threat model;\n"
                              "  2. Viết lại thiết kế đánh giá\n")
        out = run_script(STATE, "handoff", "--project", str(self.tmp))
        self.assertEqual(out.returncode, 0, out.stderr)
        handoff = (self.tmp / ".agent" / "HANDOFF.md").read_text()
        self.assertNotIn("chương threat model", handoff)
        self.assertNotIn("Bước 3", handoff)
        self.assertIn("tiếp theo → Viết lại thiết kế đánh giá", A.brief(self.tmp)["user"])
