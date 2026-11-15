"""Lớp model của router nối vào hook (GĐ5) với `claude` giả: tin nhắn không bao giờ chờ quá hạn (TM-124), chế độ nền
không chờ, lớp tắt thì không gọi `claude` lần nào, phiên không tương tác không gọi (TM-123), "làm tiếp" dùng kết quả
nền lúc mở phiên, chấm từng bước của kế hoạch vừa duyệt (hook plan_steps.py), nhật ký giữ trường của lớp từ khóa."""
import contextlib
import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path
from unittest import mock

from tests import test_route_stack as RS
from tests.test_route import A, ProjectFixtures, route
from tests.test_routemodel import FAKE, RM

HOOKS = Path(__file__).resolve().parents[1] / "plugin" / "hooks"
UNSURE = "app sập ngẫu nhiên khi nhiều người dùng cùng lúc, kiểm tra giúp mình với"
PLAN = """# Kế hoạch phiên: thử

## Tiêu chí xong
1. `python3 -m unittest` đạt

## Các bước
| # | Việc | Model · effort | Subagent |
|---|---|---|---|
| 1 | Sửa lỗi trong module lattice của lõi nhãn | sonnet · low | không |
| 2 | Review bảo mật hàm đăng nhập trước khi gộp | sonnet·low | không |
| 3 | Cập nhật README cho phần hướng dẫn cài đặt | sonnet · low | không |

## Lệnh kiểm chứng
```
python3 -m unittest
```
"""


class Base(ProjectFixtures):
    scee = RS.StackFloors.scee

    def setUp(self):
        super().setUp()
        self.fake = self.tmp / "bin" / "claude"
        self.fake.parent.mkdir()
        self.fake.write_text(FAKE, encoding="utf-8")
        self.fake.chmod(self.fake.stat().st_mode | stat.S_IXUSR)
        self.log = self.tmp / "fake.log"
        env = {"AGENT_STACK_CLAUDE_BIN": str(self.fake), "FAKE_CLAUDE_LOG": str(self.log),
               "AGENT_STACK_NO_BACKGROUND": "", "AGENT_STACK_ROUTER_MODEL": "", "CLAUDE_CODE_ENTRYPOINT": "cli"}
        patch = mock.patch.dict(os.environ, env)
        patch.start()
        self.addCleanup(patch.stop)
        procs = []

        def keep(cmd, env):  # như RM._spawn, giữ tiến trình để chờ lúc dọn
            procs.append(subprocess.Popen(cmd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                          stderr=subprocess.DEVNULL, start_new_session=True))
            self.addCleanup(procs[-1].wait, 30)

        spawn = mock.patch.object(RM, "_spawn", side_effect=keep)
        spawn.start()
        self.addCleanup(spawn.stop)

    def enable(self, **cfg):
        patch = mock.patch.object(RM, "config", return_value=dict(RM.DEFAULTS, enabled=True, **cfg))
        patch.start()
        self.addCleanup(patch.stop)

    def mode(self, mode):
        patch = mock.patch.dict(os.environ, {"FAKE_CLAUDE_MODE": mode})
        patch.start()
        self.addCleanup(patch.stop)

    def calls(self):
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    def route_log(self):
        path = A.state_dir() / route.ROUTE_LOG
        return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def data(self, root, sid, **extra):
        return dict({"session_id": sid, "cwd": str(root), "effort": {"level": "low"}, "_hook_t0": time.time()}, **extra)


class Deadline(Base):
    def test_message_never_waits_past_deadline(self):
        root = self.python_repo()
        self.enable(wait_s=1.0)
        self.mode("sleep:30")
        start = time.time()
        self.assertIsNone(route.hook_suggestion(UNSURE, self.data(root, "d1")), "quá hạn thì dùng lớp từ khóa")
        self.assertLess(time.time() - start, 2.0)
        self.assertEqual(self.route_log()[-1]["model_layer"]["status"], "qua-han")

    def test_prompt_submit_hook_returns_within_deadline(self):
        """Tiêu chí 3: claude giả ngủ 30 giây, hook UserPromptSubmit trả về trong hạn chờ + 1 giây."""
        root = self.python_repo()
        self.enable(wait_s=1.0)
        self.mode("sleep:30")
        spec = importlib.util.spec_from_file_location("prompt_submit_gd5", HOOKS / "prompt_submit.py")
        assert spec and spec.loader
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        payload = json.dumps({"session_id": "d2", "cwd": str(root), "prompt": UNSURE, "hook_event_name": "UserPromptSubmit"})
        out = io.StringIO()
        start = time.time()
        with mock.patch.object(sys, "stdin", io.StringIO(payload)), contextlib.redirect_stdout(out):
            hook.main()
        self.assertLess(time.time() - start, 1.0 + 1.0)
        self.assertEqual(self.route_log()[-1]["model_layer"]["status"], "qua-han")

    def test_background_mode_does_not_wait(self):
        root = self.python_repo()
        self.enable(wait_s=0)
        self.mode("sleep:2")
        start = time.time()
        self.assertIsNone(route.hook_suggestion(UNSURE, self.data(root, "d3")))
        self.assertLess(time.time() - start, 0.8)
        self.assertEqual(self.route_log()[-1]["model_layer"]["status"], "nen")


class UsesModel(Base):
    def test_model_rule_used_and_flags_share_one_call(self):
        root = self.python_repo()
        self.enable(wait_s=8.0)
        self.mode("answer:debug-hard")
        with route.one_pass():
            hit = route.hook_suggestion(UNSURE, self.data(root, "u1"))
            flags = route.turn_flags(UNSURE, str(root))
        self.assertIn("debug-hard", hit["context"])
        self.assertIn("lớp model chọn", hit["context"])
        self.assertEqual(flags, {"criteria": True}, "cờ tiêu chí theo luật lớp model chọn")
        self.assertEqual(len(self.calls()), 1, "cờ lượt dùng lại kết quả, không hỏi model lần hai")
        row = self.route_log()[-1]
        self.assertIsNone(row["rule"], "trường của lớp từ khóa giữ nguyên nghĩa cho learn")
        self.assertEqual(row["final"]["rule"], "debug-hard")
        self.assertEqual(row["model_layer"]["rule"], "debug-hard")

    def test_model_cannot_lower_keyword_layer(self):
        root = self.python_repo()
        self.enable(wait_s=8.0)
        self.mode("answer:small-fix")
        text = "mình muốn xem lại " + " ".join(["phần"] * 30) + " security"  # dài, chỉ khớp một cụm một chữ
        self.assertEqual(route.uncertain(text), "dai-mong")
        hit, kw, meta = route.two_layer(text, None, None, self.data(root, "u2"), time.time(), root=root)
        self.assertEqual(meta["rule"], "small-fix")
        self.assertEqual(hit["rule"], kw["rule"])
        self.assertEqual(hit["rule"], "security-review")


class NeverCalls(Base):
    def run_hooks(self, root, env):
        for hook, payload in (("prompt_submit.py", {"session_id": "n2", "cwd": str(root), "prompt": UNSURE}),
                              ("session_start.py", {"session_id": "n3", "cwd": str(root), "source": "startup"}),
                              ("plan_steps.py", {"session_id": "n4", "cwd": str(root), "tool_name": "ExitPlanMode",
                                                 "tool_response": {"plan": PLAN}})):
            subprocess.run([sys.executable, str(HOOKS / hook)], input=json.dumps(payload), env=env, timeout=30,
                           capture_output=True, text=True)
        time.sleep(0.5)

    def test_disabled_layer_never_calls_claude(self):
        """Lớp tắt (model_layer.enabled false, hay AGENT_STACK_ROUTER_MODEL=off): không hook nào gọi claude."""
        root = self.python_repo(plan_next="Chuẩn bị bộ dữ liệu mẫu cho giao diện mới của trang chủ")
        with mock.patch.object(RM, "config", return_value=dict(RM.DEFAULTS, enabled=False)):
            route.hook_suggestion(UNSURE, self.data(root, "n1"))
            route.prefetch(root, {"session_id": "n1", "cwd": str(root)})
            route.score_plan(PLAN, str(root), {}, time.time())
        self.run_hooks(root, dict(os.environ, AGENT_STACK_STATE=str(self.tmp / "state"), AGENT_STACK_ROUTER_MODEL="off"))
        self.assertEqual(self.calls(), [])

    def test_real_config_calls_only_for_plan_steps(self):
        """Cấu hình bạn chọn 15/11/2026 (rules.json: moments buoc): tin nhắn và §0 không gọi, chấm bước gọi một lần."""
        cfg = RM.config(route.rules())
        self.assertEqual((cfg["enabled"], cfg["model"], cfg["effort"], cfg["moments"]), (True, "sonnet", "low", ["buoc"]))
        root = self.python_repo(plan_next="Chuẩn bị bộ dữ liệu mẫu cho giao diện mới của trang chủ")
        self.assertIsNone(route.hook_suggestion(UNSURE, self.data(root, "n6")))
        self.assertEqual(self.route_log()[-1]["model_layer"]["status"], "tat-luc-nay")
        self.assertEqual(route.prefetch(root, {"session_id": "n6", "cwd": str(root)}), "tat-luc-nay")
        self.run_hooks(root, dict(os.environ, AGENT_STACK_STATE=str(self.tmp / "state"), FAKE_CLAUDE_MODE="answer:none"))
        deadline = time.time() + 10
        while not self.calls() and time.time() < deadline:
            time.sleep(0.2)
        calls = [json.loads(x) for x in self.calls()]
        self.assertEqual(len(calls), 1, "chỉ hook chấm bước gọi, một lần cho cả nhóm bước không chắc")
        argv = calls[0]["argv"]
        self.assertEqual(argv[argv.index("--model") + 1], "sonnet")
        self.assertIn("TỪNG bước", argv[argv.index("--system-prompt") + 1])

    def test_non_interactive_session_never_calls(self):
        root = self.python_repo()
        self.enable(wait_s=1.0)
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_ENTRYPOINT": "sdk-cli"}):
            route.hook_suggestion(UNSURE, self.data(root, "n5"))
            self.assertEqual(route.prefetch(root, {"session_id": "n5", "cwd": str(root)}), "")  # §0 trống
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.route_log()[-1]["model_layer"]["status"], "khong-tuong-tac")


class Prefetch(Base):
    def test_session_start_prefetch_then_continue(self):
        root = self.python_repo(plan_next="Chuẩn bị bộ dữ liệu mẫu cho giao diện mới của trang chủ")
        self.enable(wait_s=0, continue_wait_s=8.0)
        self.mode("answer:architecture")
        self.assertEqual(route.prefetch(root, {"session_id": "p1", "cwd": str(root)}), "nen")
        rec = json.loads(route.prefetch_path("p1").read_text(encoding="utf-8"))
        self.assertIsNone(rec["rule"], "lúc mở phiên lớp từ khóa không gợi ý gì")
        allowed = [rid for rid, _ in RM.choices(route.rules(), RM.config(route.rules()))]
        self.assertIsNotNone(RM.wait(rec["key"], time.time() + 15, allowed, 3600))
        note = route.prefetch_note({"session_id": "p1", "cwd": str(root)})
        self.assertIn("architecture", note)
        self.assertEqual(route.prefetch_note({"session_id": "p1", "cwd": str(root)}), "", "chỉ báo một lần")
        hit = route.hook_suggestion("làm tiếp đi", self.data(root, "p1"))
        self.assertIn("architecture", hit["context"])
        self.assertEqual(len(self.calls()), 1, "làm tiếp đọc kết quả nền, không gọi lại")

    def test_note_waits_until_result_and_drops_when_plan_changes(self):
        root = self.python_repo(plan_next="Chuẩn bị bộ dữ liệu mẫu cho giao diện mới của trang chủ")
        self.enable(wait_s=0)
        self.mode("sleep:3")
        self.assertEqual(route.prefetch(root, {"session_id": "p2", "cwd": str(root)}), "nen")
        self.assertEqual(route.prefetch_note({"session_id": "p2", "cwd": str(root)}), "", "worker chưa xong")
        self.assertTrue(route.prefetch_path("p2").exists(), "giữ để tin sau xem")
        self.write("py/PLAN.md", "# Kế hoạch\n\n## 0. Đang ở đâu, việc tiếp theo\n- **Việc tiếp theo, theo thứ tự:**\n"
                                 "  1. Việc khác hẳn để kiểm bản ghi cũ bị bỏ\n")
        self.assertEqual(route.prefetch_note({"session_id": "p2", "cwd": str(root)}), "")
        self.assertFalse(route.prefetch_path("p2").exists(), "§0 đổi thì bỏ bản ghi")


class PlanSteps(Base):
    def test_rows_parsed_from_table_and_list(self):
        rows = route.plan_step_rows(PLAN)
        self.assertEqual([r[0] for r in rows], ["1", "2", "3"])
        self.assertEqual(rows[1][2], ("sonnet", "low"))
        listed = route.plan_step_rows("## Các bước\n1. Viết test cho parser ngày tháng · opus·high\n2. Chạy cả bộ\n")
        self.assertEqual(listed[0][2], ("opus", "high"))
        self.assertEqual(route.plan_step_rows("## Việc của phiên\n1. a b c d\n"), [])
        # Review GĐ5: mức khai có số phiên bản, đề mục con và khối code trong mục
        versioned = route.plan_step_rows(
            "## Các bước\n### Giai đoạn 1\n1. Viết hàm đọc cấu hình mới · Opus 5.5 · high (phiên)\n```\n# không phải "
            "đề mục\n```\n2. Chạy kiểm tĩnh trên dòng đổi · Sonnet 5.5·low\n3. Dịch tài liệu hướng dẫn · "
            "claude-haiku-5-5 low\n## Lệnh kiểm chứng\n1. không phải bước của mục này nhé\n")
        self.assertEqual([r[2] for r in versioned], [("opus", "high"), ("sonnet", "low"), ("haiku", "low")])

    def test_flags_steps_under_floor_and_security(self):
        root = self.scee()
        note = route.score_plan(PLAN, str(root), {}, time.time())
        self.assertIn("bước 1 khai sonnet · low, dưới mức sàn opus · high", note)
        self.assertIn("bước 2 là việc bảo mật (security-review)", note)
        self.assertNotIn("bước 3", note)

    def test_security_step_raised_by_model_keeps_warning(self):
        """Review GĐ5 (lỗi vừa): model chọn luật mức cao hơn mà không thuộc nhóm bảo mật thì cảnh báo không được mất."""
        root = self.python_repo()
        step = ("Chuyển cách lưu secret của người dùng sang bảng mới: viết script chuyển dữ liệu cũ, đổi cột, chạy thử "
                "trên bản sao, kiểm số dòng hai bên, rồi xóa bảng cũ sau khi đối chiếu xong toàn bộ dữ liệu")
        plan = f"## Các bước\n| # | Việc | Model · effort |\n|---|---|---|\n| 1 | {step} | sonnet · low |\n"
        self.assertTrue(route.uncertain(step))
        for picked in (None, "architecture-critical", "debug-stuck"):
            with self.subTest(model=picked), mock.patch.object(
                    route, "ask_model", return_value=[{"status": "ok", "rule": picked}]):
                note = route.score_plan(plan, str(root), {}, time.time())
                self.assertIn("bước 1 là việc bảo mật", note)
                self.assertIn("security-review" if picked is None else "security", note)

    def test_model_rule_of_other_group_cannot_drop_project_floor(self):
        """Review GĐ5 (lỗi vừa): luật model ở nhóm không có sàn từng làm mất cảnh báo dưới sàn của nhóm luật từ khóa."""
        stack = dict(RS.SCEE_STACK, floors=[dict(RS.SCEE_STACK["floors"][0], group="debug", model="opus", effort="xhigh")])
        root = self.scee(stack)
        step = "gặp traceback trong module đọc cấu hình " + " ".join(["phần"] * 26)
        self.assertEqual(route.uncertain(step), "dai-mong", "phải đi qua lớp model")
        plan = f"## Các bước\n| # | Việc | Model · effort |\n|---|---|---|\n| 1 | {step} | opus · high |\n"
        with mock.patch.object(route, "ask_model", return_value=[{"status": "ok", "rule": "architecture"}]) as asked:
            note = route.score_plan(plan, str(root), {}, time.time())
        asked.assert_called_once()
        self.assertIn("bước 1 khai opus · high, dưới mức sàn opus · xhigh", note)

    def test_turn_flags_keep_keyword_flags_when_model_wins(self):
        root = self.python_repo()
        text = "Thêm tính năng đăng nhập bằng OAuth cho trang quản trị"
        kw = route.suggest(text)
        self.assertEqual(kw["rule"], "feature-boundary")
        with route.one_pass():
            route._MODEL_MEMO[text] = (route.rule_hit("architecture-critical"), kw, {"status": "ok"})
            self.assertEqual(route.turn_flags(text, str(root)), {"threat_model": True, "criteria": True})

    def test_hook_emits_context_only_when_needed(self):
        root = self.scee()
        env = dict(os.environ)
        payload = {"session_id": "s1", "cwd": str(root), "tool_name": "ExitPlanMode", "tool_response": {"plan": PLAN}}
        out = subprocess.run([sys.executable, str(HOOKS / "plan_steps.py")], input=json.dumps(payload), env=env,
                             timeout=30, capture_output=True, text=True)
        ctx = json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("bước 1", ctx)
        quiet = PLAN.replace("sonnet · low | không |\n| 2", "opus · high | không |\n| 2").replace("sonnet·low", "opus·high")
        payload["tool_response"] = {"plan": quiet}
        out = subprocess.run([sys.executable, str(HOOKS / "plan_steps.py")], input=json.dumps(payload), env=env,
                             timeout=30, capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "")
        payload["agent_id"] = "x"
        payload["tool_response"] = {"plan": PLAN}
        out = subprocess.run([sys.executable, str(HOOKS / "plan_steps.py")], input=json.dumps(payload), env=env,
                             timeout=30, capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "", "ExitPlanMode của subagent: người dùng chưa duyệt gì")
