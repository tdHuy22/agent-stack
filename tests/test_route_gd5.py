"""GĐ5, phần sửa lớp từ khóa trước khi đo lớp model: router chỉ so chữ của người dùng (bỏ khối nhắc đứng đầu, thẻ
<ide_*>, tin "[Cross-session idle notice]"), câu "làm tiếp" của nhật ký thật, và `turn_flags` đọc `.agent/stack.json`
(câu chỉ khớp từ khóa riêng của project cũng cần tiêu chí xong)."""
import json
from unittest import mock

from tests import test_route_stack as RS  # không import lớp test vào module này (unittest sẽ chạy lại)
from tests.test_route import A, ProjectFixtures, route

# Dạng thật thấy trong nhật ký router 14–15/11/2026 (đã rút gọn).
IDE_ONLY = ("<ide_opened_file>The user opened the file /Users/x/Documents/Claude/SCEE/home.html in the IDE. This may "
            "or may not be related to the current task.</ide_opened_file>")
REMINDER_THEN_ASK = ("<system-reminder>\nThe session \"gd4: cau hinh theo project\" you started (local_99a5) finished a "
                     "turn. It reported: kiến trúc lõi, review bảo mật, sửa lỗi.\n</system-reminder>\n"
                     "ok cảm ơn nhé bạn")
IDLE_NOTICE = ('[Cross-session idle notice] "scee-0f", which you asked to be notified about, is idle now — it '
               "finished a turn at 22:28.")


class Fixtures(ProjectFixtures):
    scee = RS.StackFloors.scee  # dựng bản SCEE có stack.json đã duyệt (không kế thừa test của StackFloors)


class RoutableText(Fixtures):
    def test_strips_system_text(self):
        self.assertEqual(A.routable_text(IDE_ONLY), "")
        self.assertEqual(A.routable_text(REMINDER_THEN_ASK), "ok cảm ơn nhé bạn")
        self.assertEqual(A.routable_text(IDE_ONLY + "\nsửa lỗi parser đọc sai ngày"), "sửa lỗi parser đọc sai ngày")
        self.assertEqual(A.routable_text(None), "")

    def test_long_prompt_keeps_request_at_the_start(self):
        """Review GĐ5 (lỗi cao): routable_text từng giữ 2000 ký tự cuối như own_words, mất yêu cầu ở đầu tin dài."""
        long = "Thêm tính năng đăng nhập bằng OAuth cho trang quản trị. " + "Mô tả giao diện chi tiết. " * 120
        self.assertGreater(len(long), 2500)
        self.assertTrue(A.routable_text(long).startswith("Thêm tính năng đăng nhập"))
        self.assertEqual(route.turn_flags(long, str(self.tmp)), {"threat_model": True, "criteria": True})
        self.assertIn("feature-boundary", route.hook_suggestion(long, {"session_id": "long", "effort": {"level": "low"}})["context"])

    def test_unclosed_tag_or_fence_keeps_the_rest(self):
        """Thẻ <ide_…> hay ``` không đóng chỉ bỏ chính nó, không nuốt phần sau (differential-review GĐ5)."""
        self.assertIn("sửa lỗi auth", A.routable_text("<ide_selection>abc sửa lỗi auth"))
        self.assertIn("xóa dữ liệu thanh toán", A.routable_text("Giải thích thẻ <ide_foo> rồi xóa dữ liệu thanh toán"))
        self.assertIn("review bảo mật", A.routable_text("```python\nx = 1\nreview bảo mật hàm này"))
        self.assertNotIn("x = 1", A.routable_text("```python\nx = 1\n```\nreview bảo mật hàm này"))

    def test_idle_notice_is_automated(self):
        self.assertTrue(A.is_automated_prompt(IDLE_NOTICE))
        self.assertIsNone(route.hook_suggestion(IDLE_NOTICE, {"session_id": "idle"}))
        self.assertEqual(route.turn_flags(IDLE_NOTICE, str(self.tmp)), {})

    def test_system_text_is_not_routed(self):
        """Trước bản sửa: chữ trong khối nhắc ("kiến trúc lõi, review bảo mật") làm router gợi ý luật nặng."""
        self.assertIsNone(route.hook_suggestion(REMINDER_THEN_ASK, {"session_id": "rem"}))
        self.assertEqual(route.turn_flags(REMINDER_THEN_ASK, str(self.tmp)), {})
        self.assertIsNone(route.hook_suggestion(IDE_ONLY, {"session_id": "ide"}))
        hit = route.hook_suggestion(IDE_ONLY + "\nreview bảo mật hàm đăng nhập này giúp mình", {"session_id": "ide2"})
        self.assertIn("security-review", hit["context"])

    def test_continue_phrases_from_real_log(self):
        root = self.python_repo(plan_next="Refactor module thanh toán cho dễ đọc hơn")
        for i, text in enumerate(("commit và làm tiếp đi", "Continue from where you left off.", "làm tiếp việc đi")):
            with self.subTest(text=text):
                self.assertTrue(route.CONTINUE_RE.match(A.fold(text)))
                hit = route.hook_suggestion(text, {"session_id": f"cont{i}", "cwd": str(root), "effort": {"level": "low"}})
                self.assertIn("refactor", hit["context"])
                self.assertEqual(route.turn_flags(text, str(root)), {"criteria": True})
        self.assertFalse(route.CONTINUE_RE.match(A.fold("commit giúp mình")))


class TurnFlagsReadStack(Fixtures):
    def test_project_keyword_only_needs_criteria(self):
        root = self.scee()
        text = RS.EXAMPLE_1[3][0]  # "vá lỗi rò nhãn …": không khớp luật nào, chỉ khớp từ khóa riêng của SCEE
        self.assertIsNone(route.suggest(text))
        self.assertEqual(route.turn_flags(text, str(root)), {"criteria": True})

    def test_without_stack_unchanged(self):
        root = self.python_repo()
        self.assertEqual(route.turn_flags(RS.EXAMPLE_1[3][0], str(root)), {})
        self.assertEqual(route.turn_flags("thêm tính năng xuất CSV cho trang báo cáo", str(root)), {"criteria": True})

    def test_one_pass_reads_stack_once(self):
        root = self.scee()
        calls = []
        real = route.stack_lib().effective

        def counting(*a, **k):
            calls.append(1)
            return real(*a, **k)

        with mock.patch.object(route.stack_lib(), "effective", side_effect=counting):
            with route.one_pass():
                route.turn_flags(RS.EXAMPLE_1[3][0], str(root))
                route.hook_suggestion(RS.EXAMPLE_1[3][0], {"session_id": "op", "cwd": str(root)})
            self.assertEqual(len(calls), 1)
            route.turn_flags(RS.EXAMPLE_1[3][0], str(root))  # ngoài one_pass: đọc lại
            self.assertEqual(len(calls), 2)

    def test_stack_change_seen_outside_one_pass(self):
        root = self.scee(dict(RS.SCEE_STACK, keywords=[]))
        text = "chỉnh lại luật quyết định cho on_action"
        self.assertEqual(route.turn_flags(text, str(root)), {})
        self.write("py/.agent/stack.json", json.dumps(RS.SCEE_STACK, ensure_ascii=False))  # siết: có tác dụng ngay
        self.assertEqual(route.turn_flags(text, str(root)), {"criteria": True})
