import importlib.util
import json
import os
import subprocess
import time
import unittest

from tests._util import PLUGIN, REPO, TempDirTestCase, git
from tests.test_agentstack_lib import PLAN, secret_samples

HOOKS = PLUGIN / "hooks"
PYTHONS = [p for p in ("/usr/bin/python3",) if os.path.exists(p)] + ["python3"]

# Hai câu cố định của hook SubagentStart (đúng nguyên văn trong yêu cầu thiết kế).
SUBAGENT_INTRO = "Bạn chạy trong context riêng, không thấy hội thoại với người dùng; đây là bối cảnh từ phiên chính."
SUBAGENT_OUTRO = ("Việc cụ thể theo prompt giao việc. Nếu prompt thiếu thông tin cần thiết thì nêu rõ phần thiếu "
                  "ở dòng đầu báo cáo, đừng đoán.")
SUBAGENT_BARE = SUBAGENT_INTRO + "\n" + SUBAGENT_OUTRO  # khi không có yêu cầu đã lưu và không có PLAN
LONG_ITEM = "việc rất dài " * 40  # 520 ký tự
PLAN_LONG = (f"# PLAN\n\n## 0. Đang ở đâu, việc tiếp theo\n- **Việc tiếp theo:**\n  1. {LONG_ITEM}\n"
             f"  2. {LONG_ITEM}\n  3. việc thứ ba\n")
PLAN_STRUCK = ("# PLAN\n\n## 0. Đang ở đâu, việc tiếp theo\n- **Việc tiếp theo, theo thứ tự:**\n"
               "  1. ~~Chạy `claude /login`~~ Xong 02/10/2026: đã đăng nhập.\n"
               "  2. Mở phiên mới và kiểm tra dòng trạng thái.\n"
               "  3. Chọn việc từ rà soát nguồn chính thức.\n"
               "  4. Gộp vào main.\n")


class HookTests(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.state = self.tmp / "state"
        self.project = self.tmp / "proj"
        self.project.mkdir()

    def run_hook(self, name, payload, python="python3", cwd=None):
        env = dict(os.environ, AGENT_STACK_STATE=str(self.state))
        start = time.time()
        out = subprocess.run([python, str(HOOKS / name)], input=json.dumps(payload), capture_output=True,
                             text=True, env=env, timeout=30, cwd=cwd)
        self.elapsed = time.time() - start
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stderr, "")
        return json.loads(out.stdout) if out.stdout.strip() else None

    def with_plan(self):
        (self.project / "PLAN.md").write_text(PLAN, encoding="utf-8")
        git(self.project, "init", "-q")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "init")

    def test_session_start_injects_plan_on_both_pythons(self):
        self.with_plan()
        for i, py in enumerate(PYTHONS):
            out = self.run_hook("session_start.py", {"session_id": f"s{i}", "source": "startup",
                                                     "cwd": str(self.project)}, python=py)
            ctx = out["hookSpecificOutput"]["additionalContext"]
            self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "SessionStart")
            self.assertIn("Việc tiếp theo", ctx)
            self.assertIn("📍", out["systemMessage"])
            self.assertLess(self.elapsed, 3)

    def test_session_start_silent_without_plan(self):
        self.assertIsNone(self.run_hook("session_start.py", {"session_id": "s", "cwd": str(self.project)}))

    def test_session_start_dedupes_double_registration(self):
        self.with_plan()
        payload = {"session_id": "dup", "source": "startup", "cwd": str(self.project)}
        self.assertIsNotNone(self.run_hook("session_start.py", payload))
        self.assertIsNone(self.run_hook("session_start.py", payload))

    def test_compact_and_resume_variants(self):
        self.with_plan()
        out = self.run_hook("session_start.py", {"session_id": "c", "source": "compact", "cwd": str(self.project)})
        self.assertTrue(out["hookSpecificOutput"]["additionalContext"].startswith("Vừa compact"))
        out = self.run_hook("session_start.py", {"session_id": "r", "source": "resume", "cwd": str(self.project)})
        self.assertIn("git status", out["hookSpecificOutput"]["additionalContext"].split("resume")[-1])

    def write_limits(self, seven_day, five_hour=10, age=0):
        self.state.mkdir(exist_ok=True)
        (self.state / "limits.json").write_text(json.dumps({"ts": time.time() - age, "rate_limits": {
            "seven_day": {"used_percentage": seven_day, "resets_at": 1790000000},
            "five_hour": {"used_percentage": five_hour, "resets_at": 1780000000}}}))

    def test_prompt_submit_warns_once_per_threshold(self):
        self.write_limits(85)
        out = self.run_hook("prompt_submit.py", {"session_id": "p", "prompt": "làm tiếp"})
        self.assertIn("Hạn mức tuần đã dùng 85%", out["systemMessage"])
        self.assertIn("OpenCode", out["hookSpecificOutput"]["additionalContext"])
        again = self.run_hook("prompt_submit.py", {"session_id": "p", "prompt": "câu khác"})
        self.assertTrue(again is None or "tuần" not in again.get("systemMessage", ""))
        self.write_limits(96)
        higher = self.run_hook("prompt_submit.py", {"session_id": "p", "prompt": "câu thứ ba"})
        self.assertIn("96%", higher["systemMessage"])

    def test_prompt_submit_ignores_stale_limits(self):
        self.write_limits(99, age=3600)
        out = self.run_hook("prompt_submit.py", {"session_id": "q", "prompt": "x"})
        self.assertTrue(out is None or "Hạn mức" not in out.get("systemMessage", ""))

    def test_stop_reminds_after_several_changes_then_rate_limits(self):
        self.with_plan()
        past = time.time() - 3600
        os.utime(self.project / "PLAN.md", (past, past))
        for i in range(3):
            (self.project / f"f{i}.py").write_text("x\n")
        out = self.run_hook("stop.py", {"session_id": "st", "cwd": str(self.project)})
        self.assertIn("3 file", out["systemMessage"])
        self.assertNotIn("hookSpecificOutput", out)  # không thêm context: tránh Claude chạy thêm lượt
        self.assertIsNone(self.run_hook("stop.py", {"session_id": "st", "cwd": str(self.project)}))
        self.assertIsNone(self.run_hook("stop.py", {"session_id": "x", "cwd": str(self.project),
                                                    "stop_hook_active": True}))

    def test_session_end_is_fast_and_logged(self):
        self.assertIsNone(self.run_hook("session_end.py", {"session_id": "e", "cwd": "/x", "reason": "other"}))
        self.assertLess(self.elapsed, 1.0)
        line = (self.state / "sessions.jsonl").read_text().strip().splitlines()[-1]
        self.assertEqual(json.loads(line)["session"], "e")

    def test_bad_input_never_breaks_session(self):
        env = dict(os.environ, AGENT_STACK_STATE=str(self.state))
        for name in ("session_start.py", "prompt_submit.py", "pre_compact.py", "stop.py", "session_end.py",
                     "subagent_start.py"):
            out = subprocess.run(["python3", str(HOOKS / name)], input="not json", capture_output=True,
                                 text=True, env=env, timeout=30)
            self.assertEqual(out.returncode, 0, name)

    # ---------------------------------------------------------------- UserPromptSubmit lưu yêu cầu gần nhất

    def last_request(self, sid):
        path = self.state / "last-request" / f"{sid}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def submit(self, sid, prompt, python="python3", **extra):
        """Giả lập người dùng gõ một tin: chạy hook UserPromptSubmit trong project tạm."""
        return self.run_hook("prompt_submit.py", {"session_id": sid, "cwd": str(self.project), "prompt": prompt,
                                                  **extra}, python=python)

    def test_prompt_submit_saves_last_request_and_keeps_its_output(self):
        self.write_limits(85)
        out = self.submit("ps1", "làm tiếp")
        self.assertIn("Hạn mức tuần đã dùng 85%", out["systemMessage"])  # đầu ra cũ không đổi
        self.assertIn("OpenCode", out["hookSpecificOutput"]["additionalContext"])
        saved = self.last_request("ps1")
        self.assertEqual((saved["prompt"], saved["cwd"]), ("làm tiếp", str(self.project)))
        self.assertLess(time.time() - saved["ts"], 60)

    def test_prompt_submit_replaces_the_request_with_each_new_message(self):
        self.submit("ps", "việc thứ nhất của phiên")
        self.submit("ps", "việc thứ hai của phiên")
        self.assertEqual(self.last_request("ps")["prompt"], "việc thứ hai của phiên")

    def test_prompt_submit_masks_secrets_before_saving(self):
        secret = secret_samples()["anthropic"]
        self.submit("ps", f"gọi API bằng khóa {secret} giúp mình")
        self.assertEqual(self.last_request("ps")["prompt"], "gọi API bằng khóa [đã che] giúp mình")
        self.assertNotIn(secret, (self.state / "last-request" / "ps.json").read_text(encoding="utf-8"))

    def test_prompt_submit_skips_automated_and_sessionless_prompts(self):
        self.submit("ps2", "Yêu cầu thật của người dùng")
        for text in ("<task-notification>\n<task-id>b1</task-id>\n</task-notification>",
                     "[SYSTEM NOTIFICATION] việc nền đã xong", "NOT USER INPUT"):
            self.submit("ps2", text)
            self.assertEqual(self.last_request("ps2")["prompt"], "Yêu cầu thật của người dùng", text)
        self.run_hook("prompt_submit.py", {"prompt": "tin không có session_id", "cwd": str(self.project)})
        self.assertEqual(sorted(p.name for p in (self.state / "last-request").glob("*")), ["ps2.json"])

    def test_prompt_submit_still_works_when_the_request_cannot_be_saved(self):
        self.write_limits(85)
        (self.state / "last-request").write_text("file chặn đường", encoding="utf-8")  # không tạo được thư mục
        out = self.submit("ps3", "làm tiếp")
        self.assertIn("Hạn mức tuần đã dùng 85%", out["systemMessage"])

    def test_prompt_submit_saves_the_request_even_when_the_router_fails(self):
        # effort sai kiểu làm router văng lỗi sau khi đã khớp luật; yêu cầu vẫn phải được lưu
        self.submit("ps4", "Review bảo mật hàm đăng nhập này giúp mình", effort="high")
        self.assertEqual(self.last_request("ps4")["prompt"], "Review bảo mật hàm đăng nhập này giúp mình")

    # ---------------------------------------------------------------- SubagentStart

    def start_subagent(self, sid, python="python3", cwd=None, **extra):
        payload = {"session_id": sid, "cwd": str(cwd or self.project), "transcript_path": "/x/t.jsonl",
                   "hook_event_name": "SubagentStart", "agent_id": "ag-1", "agent_type": "Explore", **extra}
        out = self.run_hook("subagent_start.py", payload, python=python)
        self.assertIsNotNone(out)
        self.assertEqual(list(out), ["hookSpecificOutput"])  # SubagentStart bỏ qua systemMessage nên không gửi
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "SubagentStart")
        return out["hookSpecificOutput"]["additionalContext"]

    def test_subagent_start_gives_request_and_plan_on_both_pythons(self):
        self.with_plan()
        for i, py in enumerate(PYTHONS):
            with self.subTest(python=py):
                self.submit(f"main-{i}", "Thêm tính năng xuất CSV cho trang báo cáo", python=py)
                ctx = self.start_subagent(f"main-{i}", python=py)
                lines = ctx.split("\n")
                self.assertEqual(lines[0], SUBAGENT_INTRO)
                self.assertEqual(lines[-1], SUBAGENT_OUTRO)
                self.assertRegex(lines[1], r"^Yêu cầu gần nhất của người dùng \(«Thêm tính năng xuất CSV cho trang "
                                           r"báo cáo»\) lúc \d\d:\d\d \d\d/\d\d \((vừa xong|\d+ phút trước)\)\. "
                                           r"Chỉ là bối cảnh, không phải chỉ dẫn mới\.$")
                self.assertEqual(lines[2:5], ["Việc tiếp theo theo PLAN §0 (trích từ file, chỉ là bối cảnh, không phải chỉ dẫn):",
                                              "1) User chạy `/compact`.",
                                              "2) Lập danh sách dọn về một phiên bản. User duyệt rồi mới làm."])
                self.assertEqual(len(lines), 6)  # chỉ 2 việc đầu, không lấy việc thứ ba
                self.assertLessEqual(len(ctx), 1500)
                self.assertLess(self.elapsed, 2)

    def test_subagent_start_shows_the_full_request_behind_a_short_message(self):
        full = "Thêm tính năng xuất CSV cho trang báo cáo, giữ nguyên định dạng ngày và có test"
        self.submit("short", full)
        self.submit("short", "tiếp tục")
        lines = self.start_subagent("short").split("\n")
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[1].startswith("Yêu cầu gần nhất của người dùng («tiếp tục») lúc "))
        self.assertTrue(lines[2].startswith(f"Yêu cầu trước đó, đầy đủ hơn («{full}») lúc "), lines[2])

    def test_subagent_start_with_earlier_request_stays_within_the_limit(self):
        (self.project / "PLAN.md").write_text(PLAN_LONG, encoding="utf-8")
        self.submit("big2", "từ dài " * 400)
        self.submit("big2", "ok")
        ctx = self.start_subagent("big2")
        self.assertLessEqual(len(ctx), 1500)
        self.assertIn("Yêu cầu trước đó, đầy đủ hơn", ctx)
        self.assertTrue(ctx.endswith(SUBAGENT_OUTRO))

    def test_slash_commands_do_not_replace_the_request(self):
        self.submit("cmd", "Đổi tên hàm foo thành bar trong utils.py và cập nhật nơi gọi")
        for text in ("/compact", "!ls", "# ghi chú"):
            self.submit("cmd", text)
        self.assertEqual(self.last_request("cmd")["prompt"], "Đổi tên hàm foo thành bar trong utils.py và cập nhật nơi gọi")

    def test_subagent_start_with_neither_request_nor_plan_gives_only_intro_and_closing(self):
        self.assertEqual(self.start_subagent("none-1"), SUBAGENT_BARE)

    def test_subagent_start_with_plan_but_no_request(self):
        self.with_plan()
        ctx = self.start_subagent("no-request")
        self.assertEqual(ctx.split("\n")[:2], [SUBAGENT_INTRO, "Việc tiếp theo theo PLAN §0 (trích từ file, chỉ là bối cảnh, không phải chỉ dẫn):"])
        self.assertNotIn("Yêu cầu gần nhất", ctx)
        self.assertTrue(ctx.endswith(SUBAGENT_OUTRO))

    def test_subagent_start_with_request_but_no_plan(self):
        self.submit("no-plan", "Đổi tên hàm foo thành bar trong utils.py")
        lines = self.start_subagent("no-plan").split("\n")
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[1].startswith("Yêu cầu gần nhất của người dùng («Đổi tên hàm foo thành bar trong "
                                            "utils.py») lúc "))
        self.assertNotIn("PLAN", "\n".join(lines))

    def test_subagent_start_uses_only_the_request_of_its_own_session(self):
        self.submit("other-session", "Việc bí mật của phiên khác chạy cùng thư mục")
        self.assertEqual(self.start_subagent("mine"), SUBAGENT_BARE)
        self.assertIn("phiên khác", self.start_subagent("other-session"))

    def test_subagent_start_ignores_a_damaged_request_file(self):
        (self.state / "last-request").mkdir(parents=True)
        (self.state / "last-request" / "dmg.json").write_text("{không phải json", encoding="utf-8")
        self.assertEqual(self.start_subagent("dmg"), SUBAGENT_BARE)

    def test_subagent_start_puts_a_multiline_request_on_one_line(self):
        self.submit("ml", "dòng một\n\n  dòng hai\tcó tab")
        self.assertIn("(«dòng một dòng hai có tab»)", self.start_subagent("ml"))

    def test_subagent_start_skips_finished_plan_items(self):
        (self.project / "PLAN.md").write_text(PLAN_STRUCK, encoding="utf-8")
        ctx = self.start_subagent("struck")
        self.assertIn("1) Mở phiên mới và kiểm tra dòng trạng thái.\n2) Chọn việc từ rà soát nguồn chính thức.", ctx)
        self.assertNotIn("/login", ctx)

    def test_subagent_start_finds_plan_from_a_subdirectory_and_from_dot_agent(self):
        self.with_plan()
        deep = self.project / "src" / "deep"
        deep.mkdir(parents=True)
        self.assertIn("Việc tiếp theo theo PLAN §0 (trích từ file, chỉ là bối cảnh, không phải chỉ dẫn):", self.start_subagent("sub", cwd=deep))
        (self.project / ".agent").mkdir()
        (self.project / ".agent" / "PLAN.md").write_text(PLAN_STRUCK, encoding="utf-8")
        (self.project / "PLAN.md").unlink()
        self.assertIn("1) Mở phiên mới và kiểm tra dòng trạng thái.", self.start_subagent("dot-agent"))

    def test_subagent_start_keeps_context_within_the_limit(self):
        (self.project / "PLAN.md").write_text(PLAN_LONG, encoding="utf-8")
        self.submit("big", "từ dài " * 400)  # lưu 1200 ký tự
        ctx = self.start_subagent("big")
        self.assertLessEqual(len(ctx), 1500)
        self.assertGreater(len(ctx), 1300)  # phần trích yêu cầu được cắt vừa đủ chỗ, không bỏ phí
        self.assertTrue(ctx.endswith(SUBAGENT_OUTRO))
        self.assertIn("…»)", ctx)  # yêu cầu bị cắt thì có dấu …
        self.assertEqual(ctx.count("…"), 3)  # yêu cầu và hai việc trong PLAN đều bị cắt

    def test_subagent_start_survives_bad_input(self):
        env = dict(os.environ, AGENT_STACK_STATE=str(self.state))
        weird = ["not json", "", "[]", "null", '"text"', "123", "{", json.dumps({"session_id": 5, "cwd": 7}),
                 json.dumps({"session_id": {"a": 1}, "cwd": ["x"]}), json.dumps({"session_id": None, "cwd": None}),
                 json.dumps({"session_id": "../../etc/passwd", "cwd": "/không/có/thư/mục/này"})]
        for py in PYTHONS:
            for raw in weird:
                with self.subTest(python=py, raw=raw):
                    out = subprocess.run([py, str(HOOKS / "subagent_start.py")], input=raw, capture_output=True,
                                         text=True, env=env, timeout=30, cwd=str(self.project))
                    self.assertEqual((out.returncode, out.stderr), (0, ""))
                    self.assertEqual(json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"],
                                     SUBAGENT_BARE)

    def test_hooks_survive_an_unusable_state_dir(self):
        self.with_plan()
        self.state.write_text("file chứ không phải thư mục", encoding="utf-8")
        self.assertIsNone(self.submit("u1", "làm tiếp"))  # lỗi được nuốt, không in gì
        ctx = self.start_subagent("u1")  # không đọc được yêu cầu đã lưu, nhưng vẫn đưa phần PLAN
        self.assertEqual(ctx.split("\n")[:2], [SUBAGENT_INTRO, "Việc tiếp theo theo PLAN §0 (trích từ file, chỉ là bối cảnh, không phải chỉ dẫn):"])
        self.assertNotIn("Yêu cầu gần nhất", ctx)

    def test_subagent_start_is_logged_without_the_request_text(self):
        self.submit("lg", "bí mật riêng tư của tôi nhé")
        self.start_subagent("lg")
        text = (self.state / "events.jsonl").read_text(encoding="utf-8")
        record = [json.loads(line) for line in text.splitlines() if '"subagent-start"' in line][-1]
        self.assertEqual((record["session"], record["agent_type"], record["request"], record["plan"]),
                         ("lg", "Explore", True, False))
        self.assertNotIn("bí mật", text)


class SubagentContext(unittest.TestCase):
    """Hàm ghép bối cảnh của hook SubagentStart, thử trực tiếp (không qua tiến trình con)."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("subagent_start_hook", HOOKS / "subagent_start.py")
        cls.hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.hook)

    def test_age_is_spelled_out(self):
        now = 1_790_000_000.0
        for age, expected in ((10, "vừa xong"), (300, "5 phút trước"), (7200, "2 giờ trước"),
                              (3 * 86400, "3 ngày trước"), (-500, "vừa xong")):  # đồng hồ lệch: coi như vừa xong
            with self.subTest(age=age):
                ctx = self.hook.build_context({"ts": now - age, "prompt": "việc"}, [], now=now)
                self.assertIn(f" ({expected}). ", ctx)

    def test_time_is_left_out_when_unknown(self):
        for ts in (None, "hôm qua", float("nan"), float("inf"), True):
            with self.subTest(ts=ts):
                ctx = self.hook.build_context({"ts": ts, "prompt": "việc"}, [], now=1_790_000_000.0)
                self.assertIn("(«việc»). Chỉ là bối cảnh", ctx)
                self.assertNotIn("lúc", ctx)

    def test_context_fits_the_limit_with_the_largest_inputs(self):
        request = {"ts": 1.0, "prompt": "chữ " * 300}
        items = ["x" * 170, "y" * 170]
        ctx = self.hook.build_context(request, items, now=1_790_000_000.0)
        self.assertLessEqual(len(ctx), 1500)
        self.assertEqual(ctx.split("\n")[0], SUBAGENT_INTRO)
        self.assertEqual(ctx.split("\n")[-1], SUBAGENT_OUTRO)

    def test_nothing_to_add_gives_intro_and_closing(self):
        self.assertEqual(self.hook.build_context(None, []), SUBAGENT_BARE)


class HooksConfig(unittest.TestCase):
    def test_hooks_json_points_to_existing_scripts(self):
        data = json.loads((HOOKS / "hooks.json").read_text())
        for event, groups in data["hooks"].items():
            for group in groups:
                for hook in group["hooks"]:
                    with self.subTest(event=event):
                        script = hook["args"][0].replace("${CLAUDE_PLUGIN_ROOT}", str(PLUGIN))
                        self.assertTrue(os.path.exists(script), script)
                        self.assertLessEqual(hook["timeout"], 10)

    def test_hooks_json_registers_subagent_start_for_every_agent(self):
        hooks = json.loads((HOOKS / "hooks.json").read_text(encoding="utf-8"))["hooks"]
        for kept in ("SessionStart", "UserPromptSubmit", "PreCompact", "Stop", "SessionEnd"):
            self.assertIn(kept, hooks)  # các hook cũ giữ nguyên
        (group,) = hooks["SubagentStart"]
        self.assertNotIn("matcher", group)  # không matcher: khớp mọi subagent, kể cả skill chạy context: fork
        (hook,) = group["hooks"]
        self.assertEqual(hook, {"type": "command", "command": "python3",
                                "args": ["${CLAUDE_PLUGIN_ROOT}/hooks/subagent_start.py"], "timeout": 5})

    def test_statusline_writes_limits(self):
        state = REPO / ".tmp" / f"sl-{os.getpid()}"
        payload = {"model": {"display_name": "Sonnet 5.5"}, "effort": {"level": "medium"},
                   "context_window": {"used_percentage": 23.4},
                   "rate_limits": {"five_hour": {"used_percentage": 41}, "seven_day": {"used_percentage": 88}}}
        out = subprocess.run(["python3", str(REPO / "statusline" / "statusline.py")], input=json.dumps(payload),
                             capture_output=True, text=True, timeout=30,
                             env=dict(os.environ, AGENT_STACK_STATE=str(state), NO_COLOR="1"))
        self.assertEqual(out.stdout, "Sonnet 5.5 · medium · ctx 23% · 5h 41% · 7d 88%")
        saved = json.loads((state / "limits.json").read_text())
        self.assertEqual(saved["rate_limits"]["seven_day"]["used_percentage"], 88)
        import shutil
        shutil.rmtree(state, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
