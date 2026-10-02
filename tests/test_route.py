import json
import os
import subprocess
import sys
import time

from tests._util import PLUGIN, REPO, TempDirTestCase

ROUTE = PLUGIN / "skills" / "task-router" / "scripts" / "route.py"
sys.path.insert(0, str(ROUTE.parent))
import route  # noqa: E402


class RouterRules(TempDirTestCase):
    def test_labeled_prompts_accuracy(self):
        out = subprocess.run([sys.executable, str(ROUTE), "--eval", str(REPO / "evals" / "router-prompts.jsonl"),
                              "--min", "0.85"], capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stdout)

    def test_diacritics_do_not_matter(self):
        a = route.suggest("Review bảo mật hàm đăng nhập")
        b = route.suggest("review bao mat ham dang nhap")
        self.assertEqual(a["rule"], b["rule"])
        self.assertEqual(a["rule"], "security-review")

    def test_word_boundaries(self):
        # "secretary" không được khớp "secret"
        hit = route.suggest("the secretary scheduled a meeting tomorrow")
        self.assertTrue(hit is None or hit["rule"] != "security-review")

    def test_fast(self):
        route.suggest("khởi động")
        start = time.time()
        for _ in range(200):
            route.suggest("Test cứ lúc pass lúc fail, hình như race condition, debug giúp")
        self.assertLess((time.time() - start) / 200, 0.01)


class HookSuggestion(TempDirTestCase):
    def setUp(self):
        super().setUp()
        os.environ["AGENT_STACK_STATE"] = str(self.tmp / "state")
        self.addCleanup(os.environ.pop, "AGENT_STACK_STATE", None)

    def test_skips_commands_and_short_prompts(self):
        self.assertIsNone(route.hook_suggestion("/compact", {"session_id": "s"}))
        self.assertIsNone(route.hook_suggestion("ok cảm ơn", {"session_id": "s"}))

    def test_suggests_switch_once_per_session(self):
        data = {"session_id": "s1", "effort": {"level": "medium"}}
        first = route.hook_suggestion("Review bảo mật hàm đăng nhập này giúp mình", data)
        self.assertIn("/effort high", first["user"])
        self.assertIn("agent-stack:reviewer", first["user"])
        self.assertIn("đừng tự đổi", first["context"])
        self.assertIsNone(route.hook_suggestion("Review bảo mật thêm file khác nữa nhé", data))

    def test_no_noise_when_already_matching_and_nothing_to_add(self):
        data = {"session_id": "s2", "effort": {"level": "medium"}}
        sessions = self.tmp / "state" / "sessions"
        sessions.mkdir(parents=True)
        import hashlib
        (sessions / (hashlib.sha1(b"s2").hexdigest()[:16] + ".json")).write_text(json.dumps({"model": "claude-sonnet-5-5"}))
        self.assertIsNone(route.hook_suggestion("Refactor module thanh toán này cho dễ đọc hơn", data))

    def test_building_something_suggests_reuse_best_first(self):
        data = {"session_id": "s3", "effort": {"level": "medium"}}
        sessions = self.tmp / "state" / "sessions"
        sessions.mkdir(parents=True)
        import hashlib
        (sessions / (hashlib.sha1(b"s3").hexdigest()[:16] + ".json")).write_text(json.dumps({"model": "claude-sonnet-5-5"}))
        hit = route.hook_suggestion("Thêm tính năng xuất CSV cho trang báo cáo", data)
        self.assertIn("skill reuse-best", hit["user"])
        self.assertIn("không tầm thường", hit["context"])
        self.assertEqual(route.suggest("Có tool nào trên GitHub quét secret trong repo chưa?")["rule"], "reuse-best")

    def test_prompt_submit_hook_end_to_end(self):
        payload = {"session_id": "e2e", "prompt": "Review bảo mật hàm đăng nhập này giúp mình",
                   "effort": {"level": "low"}}
        out = subprocess.run([sys.executable, str(PLUGIN / "hooks" / "prompt_submit.py")], input=json.dumps(payload),
                             capture_output=True, text=True, timeout=30, env=dict(os.environ))
        data = json.loads(out.stdout)
        self.assertIn("🧭 router: security-review", data["systemMessage"])
        self.assertIn("[router]", data["hookSpecificOutput"]["additionalContext"])
