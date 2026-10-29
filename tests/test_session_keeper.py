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


TRIM_PLAN = """# PLAN

## 0. Đang ở đâu, việc tiếp theo
*Cập nhật 29/10/2026.*

- **Xong (29/10/2026): việc mới nhất.** commit `aaa`.
- **Đang dở:** không có.
- **Xong:**
  - **Việc B** (28/10): test đạt.
    - chi tiết B
  - Việc C (27/10).
  - Việc D (26/10).
- **Việc tiếp theo, theo thứ tự:**
  1. ~~Cài bản 0.9.~~ Xong 12/10.
  2. Viết tài liệu.
     - mục con còn mở
  3. ✅ Dọn rác.
- **Ghi nhớ (đã xong, không phải việc):**
  - giữ nguyên
- **Mốc kiểm tra:** `pytest` → `12 passed`

## 1. Giai đoạn

### GĐ1: Xong hết
- [x] việc một
- [x] việc hai
ghi chú của GĐ1

### GĐ2: Còn dở
- [x] việc ba
- [ ] việc bốn @ban

### GĐ3: Có mốc con
- [x] việc năm
#### GĐ3a
- [x] việc sáu
"""


class Trim(TempDirTestCase):
    def trim(self, *extra):
        return run_script(STATE, "trim", "--project", str(self.tmp), *extra)

    def test_moves_old_done_items_finished_steps_and_finished_phases(self):
        plan = self.write("PLAN.md", TRIM_PLAN)
        out = self.trim("--keep", "2")
        self.assertEqual(out.returncode, 0, out.stderr)
        text = plan.read_text()
        history = (self.tmp / ".agent" / "NHAT-KY.md").read_text()
        # Hai mục Xong đầu (theo thứ tự file) ở lại, các mục cũ hơn sang nhật ký nguyên văn, kể cả mục con.
        self.assertIn("việc mới nhất", text)
        self.assertIn("**Việc B**", text)
        self.assertIn("chi tiết B", text)
        for gone in ("Việc C", "Việc D", "Cài bản 0.9", "Dọn rác", "### GĐ1", "việc một", "ghi chú của GĐ1",
                     "### GĐ3", "##### GĐ3a"):
            self.assertNotIn(gone, text)
            self.assertIn(gone.replace("### ", "#### ") if gone.startswith("### ") else gone, history)
        # Bước còn mở, mốc còn dở, Ghi nhớ và Mốc kiểm tra giữ nguyên; mốc xong hết đi cùng mốc con của nó.
        for kept in ("2. Viết tài liệu.", "mục con còn mở", "### GĐ2", "- [ ] việc bốn @ban", "## 1. Giai đoạn",
                     "giữ nguyên", "`12 passed`"):
            self.assertIn(kept, text)
        self.assertIn("NHAT-KY.md", text)  # dòng trỏ sang nhật ký
        sec = A.parse_section0(text)
        self.assertEqual(A.next_open(sec)[0].split(" ")[0], "Viết")
        self.assertEqual(sec["fields"]["checks"].strip("`").split("`")[0], "pytest")
        # Chạy lại không đổi gì; dòng trỏ không bị coi là mục Xong để dời tiếp.
        again = self.trim("--keep", "0")
        self.assertEqual(plan.read_text().count("NHAT-KY.md"), 1)
        self.assertEqual(again.returncode, 0, again.stderr)

    def test_new_batch_goes_on_top_and_dry_run_writes_nothing(self):
        plan = self.write("PLAN.md", TRIM_PLAN)
        dry = self.trim("--dry-run")
        self.assertIn("chạy thử", dry.stdout)
        self.assertEqual(plan.read_text(), TRIM_PLAN)
        self.assertFalse((self.tmp / ".agent" / "NHAT-KY.md").exists())
        self.trim("--keep", "3")
        first = (self.tmp / ".agent" / "NHAT-KY.md").read_text()
        self.assertIn("Việc D", first)
        self.assertNotIn("Việc C", first)
        self.trim("--keep", "1")
        history = (self.tmp / ".agent" / "NHAT-KY.md").read_text()
        self.assertEqual(history.count("# Nhật ký"), 1)
        self.assertLess(history.index("Việc C"), history.index("Việc D"))  # đợt mới nhất ở trên

    def test_nothing_to_move_keeps_files_untouched(self):
        small = "# PLAN\n\n## 0. Đang ở đâu\n- **Xong:** việc A.\n- **Việc tiếp theo:**\n  1. Làm B.\n"
        plan = self.write("PLAN.md", small)
        out = self.trim()
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("đã gọn", out.stdout)
        self.assertEqual(plan.read_text(), small)
        self.assertFalse((self.tmp / ".agent").exists())

    def test_without_plan_fails(self):
        self.assertEqual(self.trim().returncode, 1)


def plan(section0: str, rest: str = "") -> str:
    return "# PLAN\n\n## 0. Đang ở đâu, việc tiếp theo\n*Cập nhật 29/10/2026.*\n\n" + section0 + rest


class TrimEdgeCases(TempDirTestCase):
    """Các kịch bản reviewer đã chạy được trên PLAN thật của các project khác."""

    def trim(self, *extra):
        return run_script(STATE, "trim", "--project", str(self.tmp), *extra)

    def test_newest_last_lists_keep_the_newest_items(self):
        p = self.write("PLAN.md", plan("- **Xong:**\n  - GDD 0.1 (01/10/2026)\n  - Lõi (05/10)\n  - UI (20/10)\n"
                                       "  - Âm thanh (27/10/2026)\n- **Việc tiếp theo:**\n  1. Làm X.\n"))
        self.assertEqual(self.trim("--keep", "2").returncode, 0)
        text = p.read_text()
        self.assertIn("UI (20/10)", text)
        self.assertIn("Âm thanh", text)
        self.assertNotIn("GDD 0.1", text)
        self.assertIn("Lõi", (self.tmp / ".agent" / "NHAT-KY.md").read_text())

    def test_unknown_order_refuses_until_a_flag_is_given(self):
        body = plan("- **Xong:**\n  - việc a\n  - việc b\n  - việc c\n")
        p = self.write("PLAN.md", body)
        out = self.trim("--keep", "1")
        self.assertEqual(out.returncode, 2)
        self.assertIn("--newest-first", out.stdout)
        self.assertEqual(p.read_text(), body)
        self.assertEqual(self.trim("--keep", "1", "--newest-last").returncode, 0)
        self.assertIn("việc c", p.read_text())
        self.assertNotIn("việc a", p.read_text())

    def test_subheading_and_paragraph_after_items_stay_in_section0(self):
        # Kịch bản A: tiêu đề con và đoạn văn sau mục con cuối không bị kéo theo.
        p = self.write("PLAN.md", plan(
            "### Đã xong\n- **Xong:**\n  - d1 (29/10/2026)\n  - d2 (28/10/2026)\n  - d3 (27/10/2026)\n"
            "  - d4 (26/10/2026)\n### Việc tiếp theo\nBạn chốt 28/10: chờ phiên khác.\n- Làm X\n- Làm Y\n"))
        self.assertEqual(self.trim("--keep", "3").returncode, 0)
        text = p.read_text()
        self.assertNotIn("d4", text)
        for kept in ("### Việc tiếp theo", "Bạn chốt 28/10", "- Làm X"):
            self.assertIn(kept, text)
        self.assertLess(text.index("NHAT-KY.md"), text.index("### Việc tiếp theo"))

    def test_decision_paragraph_and_table_after_next_steps_stay(self):
        # Kịch bản B: bước đã xong được dời, đoạn quyết định và bảng cột 0 sau dòng trống thì ở lại.
        p = self.write("PLAN.md", plan(
            "- **Việc tiếp theo:**\n  1. Làm X\n  2. ✅ Dọn rác\n\n**Đã quyết (28/10):** giữ repo private.\n"
            "| Mốc | Lệnh |\n|---|---|\n| test | `pytest` |\n"))
        self.assertEqual(self.trim().returncode, 0)
        text = p.read_text()
        self.assertNotIn("Dọn rác", text)
        for kept in ("1. Làm X", "**Đã quyết (28/10):**", "| test | `pytest` |"):
            self.assertIn(kept, text)
        self.assertIn("\n\n**Đã quyết", text)  # vẫn tách khỏi danh sách bằng dòng trống

    def test_comment_inside_code_block_is_not_a_heading(self):
        body = plan("- **Việc tiếp theo:**\n  1. Làm X\n",
                    "\n## 1. Giai đoạn\n\n### GĐ1\n- [x] cài\n```bash\n# cài bằng brew\nbrew install a\n```\n"
                    "- [x] chạy thử\n\n### GĐ2\n- [x] a\n```\n# ghi chú\n```\n- [ ] b còn mở\n")
        p = self.write("PLAN.md", body)
        self.assertEqual(self.trim().returncode, 0)
        text = p.read_text()
        history = (self.tmp / ".agent" / "NHAT-KY.md").read_text()
        self.assertNotIn("GĐ1", text)
        self.assertIn("# cài bằng brew\nbrew install a\n```\n- [x] chạy thử", history)
        self.assertIn("### GĐ2\n- [x] a\n```\n# ghi chú\n```\n- [ ] b còn mở", text)
        self.assertEqual(text.count("```") % 2, 0)

    def test_handoff_newer_than_plan_is_not_trimmed(self):
        p = self.write("PLAN.md", TRIM_PLAN)
        handoff = self.write(".agent/HANDOFF.md", TRIM_PLAN)
        self.assertEqual(self.trim().returncode, 0)
        self.assertEqual(handoff.read_text(), TRIM_PLAN)
        self.assertNotEqual(p.read_text(), TRIM_PLAN)

    def test_dry_run_lists_what_stays_and_what_moves(self):
        self.write("PLAN.md", TRIM_PLAN)
        out = self.trim("--keep", "1", "--dry-run").stdout
        self.assertIn("việc mới nhất", out.split("Dời")[0])
        self.assertIn("Việc B", out.split("Dời")[1])


class TrimAdvice(TempDirTestCase):
    def test_advice_only_promises_trim_when_it_shrinks_section0(self):
        filler = "".join(f"  - việc {i} ({28 - i % 20:02d}/10/2026): " + "x" * 300 + "\n" for i in range(60))
        helps = A.trim_advice(plan("- **Xong:**\n" + filler))
        self.assertTrue(helps[1])
        self.assertIn("state.py trim", helps[0])
        stuck = A.trim_advice(plan("### Lịch sử\n" + filler.replace("  - ", "- ")))
        self.assertFalse(stuck[1])
        self.assertIn("rút gọn tay", stuck[0])
        self.assertIsNone(A.trim_advice(plan("- **Xong:** a\n")))


class TrimStructure(TempDirTestCase):
    """Lần review thứ hai: kiểm cấu trúc sau trim, không chỉ kiểm chữ còn hay mất."""

    def trim(self, *extra):
        return run_script(STATE, "trim", "--project", str(self.tmp), *extra)

    def test_pointer_goes_above_the_label_when_kept_items_stay_under_it(self):
        p = self.write("PLAN.md", plan("- **Xong:**\n" + "".join(f"  - việc {d} ({d}/10/2026)\n" for d in range(20, 26))
                                       + "- **Việc tiếp theo:**\n  1. Làm X.\n"))
        self.assertEqual(self.trim("--keep", "2").returncode, 0)
        lines = p.read_text().splitlines()
        label = lines.index("- **Xong:**")
        self.assertTrue(lines[label - 1].startswith("- **Xong trước đó:**"))
        self.assertEqual(lines[label + 1:label + 3], ["  - việc 24 (24/10/2026)", "  - việc 25 (25/10/2026)"])
        # Mục nối thêm sau đó vẫn dời được ở lần trim sau.
        p.write_text(p.read_text().replace("  - việc 25 (25/10/2026)\n", "  - việc 25 (25/10/2026)\n  - việc 26 (26/10/2026)\n"))
        self.assertEqual(self.trim("--keep", "2").returncode, 0)
        text = p.read_text()
        self.assertNotIn("việc 24", text)
        self.assertEqual(text.count("Xong trước đó"), 1)
        self.assertIn("  - việc 26", text)

    def test_heading_that_wraps_section0_is_never_moved(self):
        body = ("# PLAN\n- [x] tạo repo\n\n## 0. Đang ở đâu, việc tiếp theo\n- **Việc tiếp theo:**\n  1. Làm X.\n"
                "\n## 1. Mốc\n- [x] c\n")
        p = self.write("PLAN.md", body)
        self.assertEqual(self.trim().returncode, 0)
        text = p.read_text()
        self.assertIn("## 0. Đang ở đâu", text)
        self.assertIn("- [x] tạo repo", text)
        self.assertNotIn("## 1. Mốc", text)

    def test_item_date_is_the_newest_date_on_its_line(self):
        self.assertEqual(A._item_dates(["- Sửa hồi quy của bản 01/09/2026 (29/10)"]), [(2026, 10, 29)])
        self.assertEqual(A._item_dates(["- A (01/10/2026), hạn bản sau 30/11/2099"]), [(2026, 10, 1)])

    def test_same_day_ties_keep_every_item_of_that_day(self):
        # Cùng ngày thì không biết mục nào viết sau: giữ cả, thà §0 dài hơn vài mục còn hơn dời mục mới nhất.
        p = self.write("PLAN.md", plan("- **Xong:**\n  - a (25/10/2026)\n  - b (27/10/2026)\n  - c (27/10/2026)\n"
                                       "  - d (27/10/2026)\n"))
        self.assertEqual(self.trim("--keep", "2").returncode, 0)
        text = p.read_text()
        for kept in ("  - b (27/10", "  - c (27/10", "  - d (27/10"):
            self.assertIn(kept, text)
        self.assertNotIn("  - a (25/10", text)


class TrimKeepsChecks(TempDirTestCase):
    """archctl 29/10/2026: dòng MỐC KIỂM TRA nằm trong một bước đã gạch, bị dời theo sang nhật ký."""

    def trim(self, *extra):
        return run_script(STATE, "trim", "--project", str(self.tmp), *extra)

    def test_done_step_or_item_that_holds_the_checks_stays(self):
        p = self.write("PLAN.md", plan(
            "- **Xong:**\n  - a (28/10/2026)\n  - b (27/10/2026): Mốc test `12 passed`\n  - c (20/10/2026)\n"
            "- **Việc tiếp theo:**\n  1. Làm X\n  7. ~~Đợt 7 Terraform~~ xong.\n"
            "     MỐC KIỂM TRA: `python3 bench/oracle.py --require terraform` khớp hết\n  8. ✅ Dọn rác\n"))
        self.assertEqual(self.trim("--keep", "1").returncode, 0)
        text = p.read_text()
        self.assertIn("MỐC KIỂM TRA: `python3 bench/oracle.py", text)
        self.assertIn("Mốc test `12 passed`", text)
        self.assertNotIn("Dọn rác", text)
        self.assertNotIn("  - c (20/10", text)
        self.assertEqual(A.baseline_anywhere(text), "12 passed")  # mốc đọc được không đổi

    def test_refuses_when_the_checks_would_still_change(self):
        # Mốc chỉ nằm trong một mốc đã xong hết ngoài §0: dời nó là mất mốc, nên không dời gì.
        body = plan("- **Việc tiếp theo:**\n  1. Làm X\n",
                    "\n## 1. Giai đoạn\n\n### GĐ1\n- [x] cài, Mốc kiểm tra `pytest` → `5 passed`\n")
        p = self.write("PLAN.md", body)
        out = self.trim()
        self.assertEqual(out.returncode, 3)
        self.assertIn("Mốc kiểm tra", out.stdout)
        self.assertEqual(p.read_text(), body)
        self.assertFalse((self.tmp / ".agent" / "NHAT-KY.md").exists())
