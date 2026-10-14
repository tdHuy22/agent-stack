"""Cây kế hoạch (tien-do/scripts/plan_tree.py) và hai hàm thư viện hook Stop dùng để nhắc hiện cây."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
import unittest
from datetime import datetime, timezone

from tests._util import PLUGIN, TempDirTestCase

SCRIPT = PLUGIN / "skills" / "tien-do" / "scripts" / "plan_tree.py"
sys.path.insert(0, str(SCRIPT.parent))
sys.path.insert(0, str(PLUGIN / "lib"))
import agentstack as A  # noqa: E402
import plan_tree  # noqa: E402

PLAN = """# PLAN: mẫu

## 0. Đang ở đâu, việc tiếp theo
*Cập nhật 11/10/2026.*

- **Xong:** G0.
- **Đang dở:** viết parser ngày.
- **Việc tiếp theo, theo thứ tự:**
  1. ~~Dọn thư mục cũ~~
  2. Viết test cho parser
  3. Khi upstream gộp PR #12: bỏ bản vá
- **Quyết định còn treo:**
  - Chọn thư viện ngày
    - chi tiết con không thành lá
  - Có nên đổi định dạng không
- [ ] ô trong §0 không thành mốc

## 1. Giai đoạn

### G0: Khung
- [x] Dọn kho
- [x] Đọc paper

### G1: Thiết kế
- [x] Khung
- [ ] Viết phần thiết kế
- [ ] **Bạn làm:** duyệt bản thiết kế
- [ ] Chạy eval thật (khoảng 3 USD)
- [ ] Hỏi ý thầy @cho
- [ ] Viết "báo cáo" </script><img src=x onerror=alert(1)>
"""


class PlanTree(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.write("PLAN.md", PLAN)
        self.tree = plan_tree.build(self.tmp)

    def titles(self):
        return [(m["kind"], m["title"]) for m in self.tree["milestones"]]

    def test_order_and_sources(self):
        self.assertEqual(self.titles(), [("wip", "Đang dở"), ("next", "Việc tiếp theo"), ("phase", "G1: Thiết kế"),
                                         ("decisions", "Quyết định còn treo")])
        nxt = self.tree["milestones"][1]["all_leaves"]
        self.assertEqual([leaf["text"] for leaf in nxt][0], "Viết test cho parser")  # bước đã gạch bị bỏ
        self.assertEqual(len(nxt), 2)
        dec = self.tree["milestones"][3]["all_leaves"]
        self.assertEqual(len(dec), 2)  # mục con cấp dưới không thành lá
        self.assertEqual(self.tree["done_phases"]["count"], 1)
        self.assertEqual(self.tree["boxes"], {"done": 3, "total": 8})  # ô trong §0 không tính

    def test_tags_written_and_guessed(self):
        g1 = {leaf["id"]: leaf for leaf in self.tree["milestones"][2]["all_leaves"]}
        self.assertEqual(g1["2.1"]["tags"], [])
        self.assertEqual(g1["2.2"]["tags"], ["ban"])
        self.assertEqual(g1["2.3"]["tags"], ["usd"])
        self.assertEqual(g1["2.4"]["tags"], ["cho"])
        self.assertNotIn("@cho", g1["2.4"]["text"])
        for text in ("Viết phần căn bản", "Cho OpenCode gọi harness", "Chạy `echo $1` trong script"):
            self.assertEqual(plan_tree.leaf_tags(text)[1], [], text)
        self.assertEqual(self.tree["milestones"][1]["all_leaves"][1]["tags"], ["cho"])  # "Khi upstream gộp…"
        self.assertTrue(all("ban" in leaf["tags"] for leaf in self.tree["milestones"][3]["all_leaves"]))

    def test_next_intro_marks_every_step_for_the_user(self):
        self.write("PLAN.md", PLAN.replace("theo thứ tự:**", "theo thứ tự (đều cần bạn):**"))
        tree = plan_tree.build(self.tmp)
        self.assertTrue(all("ban" in leaf["tags"] for leaf in tree["milestones"][1]["all_leaves"]))

    def test_text_tree_and_pick(self):
        text = plan_tree.render_text(self.tree)
        self.assertIn("✓ 1 mốc xong: G0: Khung", text)
        self.assertIn("[2.1] Viết phần thiết kế  · Claude làm", text)
        self.assertIn("[làm cả mốc: gõ 2; Claude tự làm 2/5]", text)
        self.assertIn("Viết test cho parser", plan_tree.render_pick(self.tree, "t.1"))
        whole = plan_tree.render_pick(self.tree, "2")
        self.assertEqual(whole.count("\n- ["), 5)
        self.assertIn("Không có mã", plan_tree.render_pick(self.tree, "9.9"))

    def test_ids_do_not_shift_when_a_group_appears(self):
        before = {m["title"]: m["id"] for m in self.tree["milestones"]}
        self.write("PLAN.md", PLAN.replace("- **Đang dở:** viết parser ngày.\n", ""))
        after = {m["title"]: m["id"] for m in plan_tree.build(self.tmp)["milestones"]}
        self.assertNotIn("Đang dở", after)
        self.assertEqual(after["G1: Thiết kế"], before["G1: Thiết kế"])
        self.assertEqual(after["Việc tiếp theo"], "T")

    def test_many_choices_become_a_list(self):
        one = plan_tree.pick_prompt(self.tree, "2.1")
        self.assertNotIn("\n", one)
        whole = plan_tree.pick_prompt(self.tree, "2").splitlines()
        self.assertTrue(whole[0].startswith("Làm cả mốc [2]"))
        self.assertEqual(len(whole), 1 + 5)
        self.assertTrue(all(line.startswith("- [2.") for line in whole[1:]))
        many = plan_tree.pick_prompt(self.tree, "t.1, 2.3 Q 9.9 2.3").splitlines()
        self.assertEqual(many[0], "Làm các việc đã chọn, lần lượt, dừng ở việc có nhãn:")
        self.assertEqual([line[:7] for line in many[1:]], ["- [T.1]", "- [2.3]", "- cả mố"])  # bỏ mã sai, mã trùng
        self.assertIn("tốn tiền", many[2])
        self.assertEqual(plan_tree.render_pick(self.tree, ["T.1", "2.3"]).count("Lá ["), 2)

    def test_widget_has_checkboxes_and_list_button(self):
        out = plan_tree.render_widget(self.tree)
        every = sum(len(m["all_leaves"]) for m in self.tree["milestones"])
        self.assertEqual(out.count('type="checkbox"'), every)  # mọi lá đều có trong widget, kể cả lá đang ẩn
        self.assertIn('<button class="go">', out)
        self.assertIn("a[a.length-1]", out)  # gốc là cây vừa vẽ, phòng nhiều widget chung một trang
        self.assertIn("Tick ít nhất một việc", out)  # bấm khi chưa chọn: báo lỗi, không gửi
        self.assertNotIn("<img", out)
        self.assertIn('<div class="pt" data-plan-tree>', out)  # hook Stop nhận ra cây qua dấu này
        self.assertNotIn("gõ ", out)  # không bảo người dùng gõ vào chat để xem thêm

    def test_leaf_cap(self):
        tree = plan_tree.build(self.tmp, max_leaves=2)
        g1 = tree["milestones"][2]
        self.assertEqual((len(g1["leaves"]), g1["hidden"]), (2, 3))
        self.assertIn('(+3 lá nữa: gõ "xem 2" để xem đủ)', plan_tree.render_text(tree))
        out = plan_tree.render_widget(tree)
        self.assertEqual(out.count('<div class="r x"'), 3)  # lá thừa vẫn có, ẩn tới khi bấm "Xem đủ"
        self.assertIn('<button class="more" data-l="Xem đủ (+3 lá)"', out)

    def test_widget_keeps_full_text(self):
        long = "Viết phần thiết kế " + "rất dài " * 40
        self.write("PLAN.md", PLAN.replace("- [ ] Viết phần thiết kế\n", f"- [ ] {long}\n"))
        tree = plan_tree.build(self.tmp)
        out = plan_tree.render_widget(tree)
        self.assertIn(A.strip_md(long), out)  # widget có đủ chữ, cây chữ mới cắt
        self.assertIn('<button class="more" data-c data-l="Xem đủ chữ" aria-expanded="false" hidden>', out)
        self.assertIn("document.currentScript", out)  # gốc là cây ngay trước thẻ script
        self.assertIn("ResizeObserver", out)
        self.assertNotIn(A.strip_md(long), plan_tree.render_text(tree))

    def test_widget_escapes_plan_text(self):
        out = plan_tree.render_widget(self.tree)
        self.assertNotIn("<img", out)
        self.assertEqual(out.count("</script>"), 1)  # chỉ thẻ script của widget, ở cuối
        self.assertTrue(out.rstrip().endswith("</script>"))
        self.assertIn("&lt;img src=x", out)
        self.assertIn('"one": "Làm việc [{id}] trong mốc \\"{ms}\\": {text}"', out)  # mẫu câu nhúng một lần
        self.assertIn("Làm cả mốc (2/5 Claude tự làm)", out)
        q = out[out.index('data-id="Q"'):]
        self.assertNotIn('class="all"', q)  # quyết định không có nút làm cả mốc

    @unittest.skipUnless(shutil.which("node"), "cần node để kiểm cú pháp JS")
    def test_widget_script_is_valid_js(self):
        script = re.search(r"<script>(.*)</script>", plan_tree.render_widget(self.tree), re.S).group(1)
        path = self.write("w.js", script)
        out = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_cli(self):
        def run(*args):
            return subprocess.run([sys.executable, str(SCRIPT), "--project", str(self.tmp), *args],
                                  capture_output=True, text=True, timeout=30)
        out = run("--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        data = json.loads(out.stdout)
        self.assertNotIn("all_leaves", data["milestones"][0])
        self.assertEqual(run("--pick", "8").returncode, 1)
        self.assertIn("Lá [T.1]", run("--pick", "T.1").stdout)

    def test_nested_steps_and_done_marks(self):
        plan = PLAN.replace("""  1. ~~Dọn thư mục cũ~~
  2. Viết test cho parser
""", """  0. ✅ *(01/10)* Chốt phương án A
  1. **Bước 3:** ✅ *(viết 01/10)* tài liệu thiết kế
     - chương threat model;
  2. Viết test cho parser
  3. **G1:** làm theo thứ tự:
     - (a) viết lại thiết kế đánh giá
       - *(12/10)* thêm hàng D21
       - ✅ *(08/10)* đã gộp D11
     - (b) chạy cổng 0 USD
     - (c) user đọc bộ lõi
""").replace("- **Quyết định còn treo:**", "- **Việc của user (không chặn việc tiếp theo):**\n  - Push lên GitHub\n"
             "- **Quyết định còn treo:**")
        self.write("PLAN.md", plan)
        tree = plan_tree.build(self.tmp)
        nxt = next(m for m in tree["milestones"] if m["id"] == "T")
        rows = [(leaf["id"], leaf["depth"], leaf["text"]) for leaf in nxt["all_leaves"]]
        self.assertEqual([r[:2] for r in rows], [("T.1", 0), ("T.2", 0), ("T.2.1", 1), ("T.2.2", 1), ("T.2.3", 1),
                                                 ("T.3", 0)])  # bước ✅ bị bỏ cùng mục con; nhãn trong ngoặc không lẫn
        self.assertEqual(rows[2][2], "(a) viết lại thiết kế đánh giá · (12/10) thêm hàng D21")  # cấp 3 gộp vào cấp 2
        tags = {leaf["id"]: leaf["tags"] for leaf in nxt["all_leaves"]}
        self.assertEqual((tags["T.2.2"], tags["T.2.3"]), ([], ["ban"]))  # "0 USD" không tốn tiền; "user đọc" cần bạn
        self.assertEqual(plan_tree.whole_note(nxt), "3/5")  # nhóm T.2 không tính là việc
        self.assertIn("   [T.2.1]", plan_tree.render_text(tree))
        group = plan_tree.render_pick(tree, "xem T.2")
        self.assertIn("Việc con, làm lần lượt:", group)
        self.assertEqual(group.count("\n- [T.2."), 3)
        whole = plan_tree.pick_prompt(tree, "T").splitlines()
        self.assertTrue(whole[3].startswith("  - [T.2.1]"))  # việc con thụt vào trong câu làm cả mốc
        self.assertEqual(A.plan_done_count(self.tmp)["count"], 3 + 3)  # 3 ô tick + 3 bước ✅, kể cả bước con

    def test_done_marks_and_guesses_stay_narrow(self):
        for text in ("✅ (01/10) Chốt phương án", "**Bước 3:** ✅ *(viết 01/10)* tài liệu", "~~Dọn thư mục~~", "[x] Xong"):
            self.assertTrue(A.step_done(text), text)
        for text in ("Viết test, xong thì đánh ✅", "Một nhãn rất dài hơn bốn mươi ký tự cho bước này: ✅ rồi",
                     "Kiểm ~~ trong chuỗi"):
            self.assertFalse(A.step_done(text), text)
        self.assertEqual(A.next_open({"next": ["~~a~~", "✅ b", "c"]}), ["c"])
        self.assertEqual(plan_tree.leaf_tags("Viết README để người dùng đọc được")[1], [])
        self.assertEqual(plan_tree.leaf_tags("(c) user đọc bộ lõi")[1], ["ban"])
        self.assertEqual(plan_tree.leaf_tags("User chạy `./package.sh`")[1], ["ban"])

    def test_next_steps_read_the_same_way_everywhere(self):
        def sec(body):
            return A.parse_section0("# P\n\n## 0. Đang ở đâu\n" + body)
        wrapped = sec("- **Việc tiếp theo:** chạy test toàn bộ\n  rồi commit giai đoạn 5.\n- **Xong:** G0\n")
        self.assertEqual(wrapped["next"], ["chạy test toàn bộ rồi commit giai đoạn 5."])
        self.assertEqual(A.next_open(wrapped), wrapped["next"])  # dòng nối tiếp của nhãn viết liền không mất
        two = sec("- **Việc tiếp theo:**\n  1. A\n- **Bước tiếp theo sau khi bạn duyệt:**\n  1. B\n")
        self.assertEqual(two["next"], ["A", "B"])  # nhiều nhãn cùng loại thì gộp, không ghi đè
        self.assertEqual(A.next_open(two), ["A", "B"])

    def test_pick_without_code(self):
        out = subprocess.run([sys.executable, str(SCRIPT), "--project", str(self.tmp), "--pick", "xem"],
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 1)
        self.assertIn("Thiếu mã", out.stdout)

    def test_no_plan(self):
        (self.tmp / "PLAN.md").unlink()
        self.assertEqual(plan_tree.build(self.tmp), {})
        self.assertIn("Không có file kế hoạch", plan_tree.render_text({}))


class StopHelpers(TempDirTestCase):
    def test_plan_done_count(self):
        self.assertIsNone(A.plan_done_count(self.tmp))
        self.write("PLAN.md", PLAN)
        self.assertEqual(A.plan_done_count(self.tmp)["count"], 4)  # 3 ô tick + 1 bước gạch

    def entry(self, ts, tool_input):
        stamp = datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")
        return json.dumps({"type": "assistant", "timestamp": stamp, "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": tool_input}]}})

    def test_tool_used_since(self):
        now = time.time()
        path = self.write("t.jsonl", "\n".join([
            self.entry(now - 100, {"command": "python3 plan_tree.py --widget"}),
            json.dumps({"type": "user", "timestamp": "x", "message": {"content": "plan_tree.py"}}),
            self.entry(now - 5, {"command": "ls"})]) + "\n")
        self.assertFalse(A.tool_used_since(path, now - 50, "plan_tree.py"))
        self.assertTrue(A.tool_used_since(path, now - 200, "plan_tree.py"))
        self.assertTrue(A.tool_used_since(self.tmp / "missing.jsonl", now, "plan_tree.py"))  # đọc lỗi: không nhắc
        self.assertFalse(A.tool_used_since(path, now - 200, "plan_tree.py", tool_suffix="show_widget"))
        self.assertTrue(A.tool_used_since(path, now - 200, "plan_tree.py", tool_suffix="Bash"))

    def test_transcript_offers_tool(self):
        listed = json.dumps({"type": "attachment", "attachment": {"type": "deferred_tools_delta",
                                                                  "addedNames": ["mcp__x__show_widget"]}})
        said = json.dumps({"type": "user", "message": {"content": "show_widget là gì?"}})
        rules = json.dumps({"type": "attachment", "attachment": {"type": "instructions", "files": [
            {"content": "đưa vào công cụ vẽ widget (như `show_widget`)"}]}})
        loaded = json.dumps({"type": "attachment", "attachment": {"type": "prompt_snapshot", "tools": [
            {"name": "Bash"}, {"name": "mcp__visualize__show_widget"}]}})
        removed = json.dumps({"type": "attachment", "attachment": {"type": "deferred_tools_delta",
                                                                   "addedNames": ["mcp__x__show_widget"],
                                                                   "removedNames": ["mcp__x__show_widget"]}})
        self.assertTrue(A.transcript_offers_tool(self.write("a.jsonl", listed + "\n"), "show_widget"))
        self.assertTrue(A.transcript_offers_tool(self.write("c.jsonl", loaded + "\n"), "show_widget"))
        for name, line in (("b", said), ("d", rules), ("e", removed)):  # chữ trong tin nhắn hay CLAUDE.md không tính
            self.assertFalse(A.transcript_offers_tool(self.write(f"{name}.jsonl", line + "\n"), "show_widget"), name)
        self.assertFalse(A.transcript_offers_tool(self.tmp / "missing.jsonl", "show_widget"))
