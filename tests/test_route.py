import json
import re
import os
import subprocess
import sys
import time
from pathlib import Path

from tests._util import PLUGIN, REPO, SUBAGENT_HANDBACK, TempDirTestCase

ROUTE = PLUGIN / "skills" / "task-router" / "scripts" / "route.py"
sys.path.insert(0, str(ROUTE.parent))
import route  # noqa: E402
import agentstack as A  # noqa: E402


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

    def test_turn_flags_mark_progress_questions(self):
        self.assertEqual(route.turn_flags("làm gì tiếp theo", str(self.tmp)), {"progress": True})
        self.assertEqual(route.turn_flags("tiến độ tới đâu rồi?", str(self.tmp)), {"progress": True})
        self.assertEqual(route.turn_flags("làm tiếp đi", str(self.tmp)), {})  # chấm theo §0, không phải câu hỏi
        self.assertEqual(route.turn_flags("sửa lỗi parser đọc sai ngày", str(self.tmp)), {})
        for prompt in ("lỗi đang do hàm parse gây ra, sửa giúp tôi", "giải thích đoạn code này đang do ai gọi",
                       "refactor module thanh toán, việc tiếp theo là viết test", "sửa màu status bar",
                       "có vẻ như nhiều lúc claude vẫn quên vẽ tree graph cho tiến độ, như các phiên khác đang làm"):
            self.assertFalse(route.is_progress_question(prompt), prompt)
        for prompt in ("còn việc gì đang dở", "what's next?", "status", "đang ở đâu rồi"):
            self.assertTrue(route.is_progress_question(prompt), prompt)

    def test_word_boundaries(self):
        # "secretary" không được khớp "secret"
        hit = route.suggest("the secretary scheduled a meeting tomorrow")
        self.assertTrue(hit is None or hit["rule"] != "security-review")

    def test_rules_are_consistent(self):
        efforts = {"low", "medium", "high", "xhigh", "max"}
        rules = route.rules()["rules"]
        ids = {r["id"] for r in rules}
        self.assertEqual(len(ids), len(rules), "id luật bị trùng")
        for r in rules:
            with self.subTest(rule=r["id"]):
                self.assertIn(r["model"], route.FAMILIES)
                self.assertIn(r.get("effort"), efforts)  # Haiku 5.5 cũng có effort
                if r.get("with_tests"):
                    self.assertIn(r["with_tests"]["model"], route.FAMILIES)
                    self.assertIn(r["with_tests"]["effort"], efforts)
                for base in r["_refines"]:
                    self.assertIn(base, ids)
                if r.get("only_refine"):
                    self.assertTrue(r["_refines"], "only_refine cần luật gốc")
        self.assertEqual({r.get("effort") for r in rules} - {None}, efforts, "bảng phải trải đủ low tới max")

    def test_refinements_need_their_base(self):
        self.assertEqual(route.suggest("Review bảo mật phần mã hóa token")["rule"], "security-critical")
        self.assertEqual(route.suggest("Refactor module thanh toán này")["rule"], "refactor")
        self.assertEqual(route.suggest("Audit bảo mật toàn bộ codebase")["effort"], "max")
        hit = route.suggest("Đổi tên hàm getUser thành fetchUser trong cả project")
        self.assertEqual(route.describe(hit).split(" · ")[:2], ["claude-haiku-5-5", "low"])
        self.assertNotIn("None", route.describe(hit))

    def test_model_ids_point_to_newest(self):
        # Alias haiku của CLI còn trỏ Haiku 4.5 (không có effort), nên router ghi ID đầy đủ.
        self.assertEqual(route.model_name("haiku"), "claude-haiku-5-5")
        self.assertEqual(route.model_name("sonnet"), "sonnet")
        self.assertEqual(route.model_effort({"model": "haiku", "effort": "low"}), "claude-haiku-5-5 · low")
        self.assertEqual(route.suggest("Đổi tên hàm getUser thành fetchUser trong cả project")["model_id"], "claude-haiku-5-5")
        self.assertTrue(route.needs_model_switch("haiku", "claude-haiku-4-5-20251001"))
        self.assertFalse(route.needs_model_switch("haiku", "claude-haiku-5-5"))
        self.assertTrue(route.needs_model_switch("sonnet", "claude-haiku-5-5"))
        self.assertFalse(route.needs_model_switch("sonnet", "claude-sonnet-5-5"))
        self.assertFalse(route.needs_model_switch("opus", ""))

    def test_cheaper_model_only_when_project_has_tests(self):
        text = "Thêm tính năng xuất CSV cho báo cáo, viết hàm mới"
        plain = route.suggest_for(text, {"kinds": ["python"], "markers": []})
        tested = route.suggest_for(text, {"kinds": ["python"], "markers": ["tests"]})
        self.assertEqual((plain["model"], plain["effort"]), ("sonnet", "medium"))
        self.assertEqual((tested["model_id"], tested["effort"]), ("claude-haiku-5-5", "low"))
        self.assertEqual(tested["fallback"], "sonnet · medium")  # có đường lên bậc khi test trượt
        self.assertNotIn("test trượt", tested["note"])  # đường lên bậc chỉ có một nguồn (fallback)
        small = route.suggest_for("Sửa lỗi chính tả trong thông báo lỗi này", {"kinds": [], "markers": ["tests"]})
        self.assertEqual((small["rule"], small["model"], small["effort"]), ("small-fix", "sonnet", "low"))
        review = route.suggest_for("Review code PR này giúp mình", {"kinds": [], "markers": ["tests"]})
        self.assertEqual(review["model"], "opus")  # việc không chấm được bằng test thì giữ nguyên

    def test_on_demand_skills_not_suggested(self):
        # Skill scope on-demand không được nằm trong luật hay hồ sơ project; skill vendor đã xoá (09/10/2026) cũng vậy.
        catalog = json.loads((REPO / "catalog.json").read_text(encoding="utf-8"))
        on_demand = {i["install"].get("name") or i["install"].get("plugin")
                     for i in catalog["items"] if i["scope"] == "on-demand"}
        self.assertIn("webapp-testing", on_demand)
        removed = {"tdd", "diagnosing-bugs", "humanizer", "grill-me", "handoff", "c-review", "audit-context-building"}
        data = route.rules()
        used = {s for r in data["rules"] for s in r.get("skills", [])}
        used |= {s for v in data["markers"].values() for s in v.get("skills", [])}
        used |= {s for k, v in data["profiles"].items() if k != "web" for s in v.get("skills", [])}
        self.assertEqual(used & (on_demand | removed), set())
        extras = {s for v in data["rule_extras"].values() for names in v.values() for s in names}
        self.assertEqual(extras & removed, set())
        self.assertNotIn("lsp", data["profiles"]["c_cpp"])  # clangd-lsp đã xoá 10/10/2026
        # Skill theo loại project (rule_extras) cũng bị lọc khi chỉ cài khi cần.
        hit = route.suggest_for("Viết test cho module đăng nhập này", {"kinds": ["web"], "markers": []})
        self.assertEqual(hit["rule"], "tests")
        self.assertNotIn("webapp-testing", hit["skills"])

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

    def test_skips_messages_written_by_the_system(self):
        # Báo cáo của subagent quay về như một tin của người dùng; thân báo cáo nhắc "việc tiếp theo" nhưng đó không
        # phải việc cần định tuyến (từng làm router gợi ý nhầm skill tien-do sau mỗi lần subagent trả lời).
        texts = (SUBAGENT_HANDBACK,
                 "<task-notification>\n<task-id>b1</task-id>\nviệc tiếp theo đã xong rồi nhé\n</task-notification>")
        for i, text in enumerate(texts):
            with self.subTest(text=text[:30]):  # mỗi tin một session, để cơ chế chống lặp không che mất lỗi
                self.assertIsNone(route.hook_suggestion(text, {"session_id": f"sys{i}"}))

    def test_suggests_switch_once_per_session(self):
        data = {"session_id": "s1", "effort": {"level": "medium"}}
        first = route.hook_suggestion("Review bảo mật hàm đăng nhập này giúp mình", data)
        # Cho dải của mod: luôn có hai khóa; chỉ là tên model hay mức effort, hoặc None.
        self.assertIn("switch", first)
        self.assertIn("effort", first)
        for key in ("switch", "effort"):
            self.assertTrue(first[key] is None or re.fullmatch(r"[a-z0-9][a-z0-9.-]*", first[key]), first[key])
        self.assertNotIn("/effort", first["user"])  # reviewer tự chạy effort của nó (N2)
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

    # ---------------------------------------------------------------- GĐ24: đổi model chỉ khi rẻ, effort thoải mái

    DEBUG = "Test cứ lúc pass lúc fail, hình như race condition, debug giúp"  # luật debug-hard: opus · medium

    def transcript(self, name, model, ctx, age, ttl="1h"):
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - age)) + ".000Z"
        usage = {"input_tokens": 2, "cache_creation_input_tokens": 500, "cache_read_input_tokens": ctx,
                 "cache_creation": {f"ephemeral_{ttl}_input_tokens": 500}}
        path = self.tmp / f"{name}.jsonl"
        path.write_text(json.dumps({"type": "assistant", "timestamp": stamp, "message": {
            "model": model, "usage": usage, "content": [{"type": "text", "text": "x"}]}}) + "\n", encoding="utf-8")
        return str(path)

    def test_model_switch_mid_session_is_replaced_by_a_subagent_when_the_cache_is_warm(self):
        data = {"session_id": "w1", "effort": {"level": "medium"},
                "transcript_path": self.transcript("w1", "claude-sonnet-5-5", 250000, age=120)}
        hit = route.hook_suggestion(self.DEBUG, data)
        self.assertNotIn("/model", hit["user"])
        self.assertIn("giữ sonnet · medium (đổi tốn ≈2,00 USD)", hit["user"])  # effort đang dùng; 250K token × 4 USD/M × 2 (cache 1 giờ)
        self.assertIn("subagent opus · medium", hit["user"])
        self.assertIn("Đừng đổi /model lúc này: context ≈250K token", hit["context"])
        self.assertIn('Agent với model "opus", effort "medium"', hit["context"])
        self.assertIn("merge_back.py", hit["context"])
        self.assertIn("`Model: giữ sonnet`", hit["context"])

    def test_model_switch_is_suggested_when_it_is_cheap(self):
        cases = (("c1", 250000, 2 * 3600, "1h", "cache đã nguội"), ("c2", 20000, 60, "1h", "context nhỏ"),
                 ("c3", 250000, 10 * 60, "5m", "cache đã nguội"))
        for sid, ctx, age, ttl, why in cases:
            with self.subTest(sid=sid):
                data = {"session_id": sid, "transcript_path": self.transcript(sid, "claude-sonnet-5-5", ctx, age, ttl)}
                hit = route.hook_suggestion(self.DEBUG, data)
                self.assertIn(f"/model opus ({why})", hit["user"])
                self.assertNotIn("Đừng đổi", hit["context"])
        hit = route.hook_suggestion(self.DEBUG, {"session_id": "c4", "transcript_path": str(self.tmp / "chua-co.jsonl")})
        self.assertIsNone(hit)  # chưa biết model đang chạy: không gợi ý đổi bừa

    def test_effort_is_suggested_freely_on_models_that_keep_the_cache(self):
        data = {"session_id": "e1", "effort": {"level": "low"},
                "transcript_path": self.transcript("e1", "claude-opus-5-5", 400000, age=60)}
        hit = route.hook_suggestion(self.DEBUG, data)
        self.assertIn("/effort medium", hit["user"])
        self.assertNotIn("/model", hit["user"])
        old = {"session_id": "e2", "effort": {"level": "low"},
               "transcript_path": self.transcript("e2", "claude-opus-4-1", 400000, age=60)}
        self.assertIsNone(route.hook_suggestion(self.DEBUG, old))  # model cũ: đổi effort mất cache, cache còn ấm

    def test_agents_that_do_the_work_carry_their_own_model(self):
        data = {"session_id": "a9", "effort": {"level": "high"},
                "transcript_path": self.transcript("a9", "claude-sonnet-5-5", 300000, age=60)}
        hit = route.hook_suggestion("Review bảo mật hàm đăng nhập này giúp mình", data)
        self.assertNotIn("/model", hit["user"])
        self.assertNotIn("giữ sonnet", hit["user"])
        self.assertIn("agent-stack:reviewer", hit["user"])

    def test_effort_is_not_pushed_on_the_main_session_for_agent_work(self):
        # N2: luật security-critical là opus·xhigh nhưng reviewer tự chạy effort của nó.
        data = {"session_id": "n2", "effort": {"level": "medium"},
                "transcript_path": self.transcript("n2", "claude-sonnet-5-5", 300000, age=60)}
        hit = route.hook_suggestion("Review bảo mật phần mã hóa và xác thực token thanh toán giúp mình", data)
        self.assertIn("agent-stack:reviewer", hit["user"])
        self.assertNotIn("/effort", hit["user"])

    def test_a_fresh_model_switch_makes_another_switch_cheap(self):
        path = self.tmp / "sw.jsonl"
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 60)) + ".000Z"
        path.write_text(Path(self.transcript("sw0", "claude-sonnet-5-5", 300000, age=120)).read_text() + json.dumps(
            {"type": "attachment", "timestamp": stamp, "attachment": {"type": "model", "identity": {
                "modelId": "claude-haiku-5-5"}}}) + "\n", encoding="utf-8")
        hit = route.hook_suggestion(self.DEBUG, {"session_id": "sw", "transcript_path": str(path)})
        self.assertIn("/model opus (vừa đổi model, cache mới chưa có)", hit["user"])

    def mod_usage(self, sid, model, ctx, age, call_model=None, updated_age=1):
        """File số liệu do mod giao diện ghi (ui_status.py), như sau một lượt rồi một lần gửi tin."""
        now = time.time()
        assert A.record_mod_usage({"session_id": sid, "model": {"id": call_model or model}, "turn_end": True,
                                   "context_window": {"total_input_tokens": ctx}}, now=now - age)
        assert A.record_mod_usage({"session_id": sid, "model": model}, at_prompt=True, now=now - updated_age)

    def test_router_prefers_the_mod_figures_over_the_transcript(self):
        # Transcript nói cache còn ấm (250K, 2 phút trước); số của mod nói lượt cuối đã 2 giờ trước: theo mod.
        data = {"session_id": "m1", "transcript_path": self.transcript("m1", "claude-sonnet-5-5", 250000, age=120)}
        self.mod_usage("m1", "claude-sonnet-5-5", 250000, age=2 * 3600)
        self.assertIn("/model opus (cache đã nguội)", route.hook_suggestion(self.DEBUG, data)["user"])
        # /model giữa hai lượt (mod ghi lúc gửi tin): đổi tiếp là rẻ, như nhánh transcript.
        self.mod_usage("m2", "claude-haiku-5-5", 300000, age=60, call_model="claude-sonnet-5-5")
        hit = route.hook_suggestion(self.DEBUG, {"session_id": "m2", "transcript_path": str(self.tmp / "khong.jsonl")})
        self.assertIn("/model opus (vừa đổi model, cache mới chưa có)", hit["user"])
        # Cache còn ấm theo mod mà không có transcript: vẫn khuyên giữ model.
        self.mod_usage("m3", "claude-sonnet-5-5", 250000, age=60)
        hit = route.hook_suggestion(self.DEBUG, {"session_id": "m3"})
        self.assertIn("giữ sonnet (đổi tốn ≈2,00 USD)", hit["user"])

    def test_router_falls_back_to_the_transcript_without_fresh_mod_figures(self):
        warm = lambda sid: {"session_id": sid,
                            "transcript_path": self.transcript(sid, "claude-sonnet-5-5", 250000, age=120)}
        # Không có file (OpenCode, phiên -p): đọc transcript như cũ.
        self.assertIn("giữ sonnet", route.hook_suggestion(self.DEBUG, warm("f1"))["user"])
        # File cũ hơn 5 phút, hay của phiên khác: bỏ, đọc transcript (TM-34).
        self.mod_usage("f2", "claude-sonnet-5-5", 250000, age=2 * 3600, updated_age=400)
        self.assertIn("giữ sonnet", route.hook_suggestion(self.DEBUG, warm("f2"))["user"])
        self.mod_usage("khac", "claude-sonnet-5-5", 250000, age=2 * 3600)
        A.mod_usage_path("khac").rename(A.mod_usage_path("f3"))
        self.assertIn("giữ sonnet", route.hook_suggestion(self.DEBUG, warm("f3"))["user"])

    def test_switch_cost_uses_the_target_price_and_cache_lifetime(self):
        now = time.time()
        advice = route.switch_advice("sonnet", {"context": 250000, "ts": now - 60, "ttl": 3600}, now=now)
        self.assertFalse(advice["cheap"])
        self.assertAlmostEqual(advice["cost"], 1.0)
        short = route.switch_advice("sonnet", {"context": 250000, "ts": now - 60, "ttl": 300}, now=now)
        self.assertAlmostEqual(short["cost"], 0.625)
        long_haiku = route.switch_advice("haiku", {"context": 200000, "ts": now - 60, "ttl": 3600}, now=now)
        self.assertAlmostEqual(long_haiku["cost"], 0.2)  # prompt trên 100K: 0,5 USD/M
        self.assertTrue(route.switch_advice("opus", {}, now=now)["cheap"])

    def test_prompt_submit_hook_end_to_end(self):
        payload = {"session_id": "e2e", "prompt": "Review bảo mật hàm đăng nhập này giúp mình",
                   "effort": {"level": "low"}}
        out = subprocess.run([sys.executable, str(PLUGIN / "hooks" / "prompt_submit.py")], input=json.dumps(payload),
                             capture_output=True, text=True, timeout=30, env=dict(os.environ))
        data = json.loads(out.stdout)
        self.assertIn("🧭 router: security-review", data["systemMessage"])
        self.assertIn("[router]", data["hookSpecificOutput"]["additionalContext"])


class ProjectFixtures(TempDirTestCase):
    """Dựng project mẫu (git) cho các test chọn skill theo project. Không chứa test."""

    def setUp(self):
        super().setUp()
        # Cấu hình Claude Code giả và trống: kết quả không phụ thuộc plugin đang bật trên máy thật.
        empty = self.tmp / "empty-claude-config"
        (empty / "plugins").mkdir(parents=True)
        for key, value in (("AGENT_STACK_STATE", str(self.tmp / "state")), ("CLAUDE_CONFIG_DIR", str(empty)),
                           ("AGENT_STACK_PLUGINS_DIR", str(empty / "plugins"))):
            old = os.environ.get(key)
            os.environ[key] = value
            self.addCleanup(lambda k=key, o=old: os.environ.pop(k, None) if o is None else os.environ.__setitem__(k, o))

    def repo(self, name, files, plan_next=None):
        from tests._util import git
        root = self.tmp / name
        for rel, text in files.items():
            self.write(f"{name}/{rel}", text)
        if plan_next:
            self.write(f"{name}/PLAN.md", "# Kế hoạch\n\n## 0. Đang ở đâu, việc tiếp theo\n*Cập nhật 02/10/2026.*\n"
                                          f"- **Việc tiếp theo, theo thứ tự:**\n  1. {plan_next}\n")
        git(root, "init", "-q")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "init")
        return root

    def python_repo(self, plan_next=None):
        return self.repo("py", {"app/a.py": "x = 1\n", "app/b.py": "y = 2\n", "app/c.py": "z = 3\n",
                                "tests/test_a.py": "import unittest\n", ".github/workflows/ci.yml": "on: push\n"},
                         plan_next)



class LspSuggestion(ProjectFixtures):
    """Đề xuất LSP (pyright-lsp) riêng cho project cần nó, không cài toàn cục."""

    def setUp(self):
        super().setUp()
        from unittest import mock
        self.config = self.tmp / "claude-config"
        (self.config / "plugins").mkdir(parents=True)
        (self.config / "plugins" / "installed_plugins.json").write_text(json.dumps(
            {"version": 2, "plugins": {"pyright-lsp@claude-plugins-official": [{"scope": "user"}]}}), encoding="utf-8")
        for key, value in (("CLAUDE_CONFIG_DIR", str(self.config)), ("AGENT_STACK_PLUGINS_DIR", str(self.config / "plugins"))):
            old = os.environ.get(key)
            os.environ[key] = value
            self.addCleanup(lambda k=key, o=old: os.environ.pop(k, None) if o is None else os.environ.__setitem__(k, o))
        self.which = mock.patch.object(route.shutil, "which", return_value="/usr/local/bin/x")
        self.which.start()
        self.addCleanup(self.which.stop)

    def big_python(self, name="bigpy", extra=None):
        files = {f"pkg/m{i}.py": f"v{i} = {i}\n" for i in range(150)}
        files.update(extra or {})
        return self.repo(name, files)

    def test_large_python_project_gets_a_local_pyright_suggestion(self):
        hint = route.session_hint(self.big_python())
        self.assertIn("pyright-lsp", hint["context"])
        self.assertIn("claude plugin enable pyright-lsp@claude-plugins-official --scope local", hint["context"])
        self.assertNotIn("brew install pyright", hint["context"])
        self.assertIn("nên bật pyright-lsp", hint["user"])

    def test_small_python_project_gets_none(self):
        hint = route.session_hint(self.python_repo())
        self.assertNotIn("pyright-lsp", hint["context"])
        self.assertNotIn("pyright", hint["user"])

    def test_type_checker_config_is_enough(self):
        root = self.repo("typed", {"a.py": "x: int = 1\n", "b.py": "\n", "c.py": "\n",
                                   "pyproject.toml": "[project]\nname = 'x'\n\n[tool.mypy]\nstrict = true\n"})
        self.assertIn("[tool.mypy]", route.session_hint(root)["context"])

    def test_nothing_when_already_enabled_for_the_project_or_globally(self):
        root = self.big_python(extra={".claude/settings.local.json": json.dumps(
            {"enabledPlugins": {"pyright-lsp@claude-plugins-official": True}})})
        self.assertNotIn("pyright-lsp", route.session_hint(root)["context"])
        (self.config / "settings.json").write_text(json.dumps(
            {"enabledPlugins": {"pyright-lsp@claude-plugins-official": True}}), encoding="utf-8")
        self.assertNotIn("pyright-lsp", route.session_hint(self.big_python("bigpy2"))["context"])

    def test_disabled_locally_wins_over_user_scope(self):
        (self.config / "settings.json").write_text(json.dumps(
            {"enabledPlugins": {"pyright-lsp@claude-plugins-official": True}}), encoding="utf-8")
        root = self.big_python(extra={".claude/settings.local.json": json.dumps(
            {"enabledPlugins": {"pyright-lsp@claude-plugins-official": False}})})
        self.assertIn("pyright-lsp", route.session_hint(root)["context"])

    def test_missing_binary_and_plugin_change_the_steps(self):
        (self.config / "plugins" / "installed_plugins.json").write_text('{"version": 2, "plugins": {}}', encoding="utf-8")
        self.which.stop()
        from unittest import mock
        with mock.patch.object(route.shutil, "which", return_value=None):
            ctx = route.session_hint(self.big_python())["context"]
        self.which.start()
        self.assertIn("`brew install pyright`", ctx)
        self.assertIn("claude plugin install pyright-lsp@claude-plugins-official --scope local", ctx)

    def test_c_project_gets_no_lsp(self):
        # clangd-lsp đã xoá khỏi danh mục ngày 10/10/2026: project C không còn được đề xuất LSP.
        root = self.repo("cproj", {"src/a.c": "\n", "src/b.c": "\n", "src/c.h": "\n", "CMakeLists.txt": "project(x)\n"})
        hint = route.session_hint(root)
        self.assertNotIn("clangd", hint["context"])
        self.assertNotIn("lsp", hint["user"].lower())


class ProjectAware(ProjectFixtures):
    """Mục 4 kết hợp mục 5: chọn skill theo nội dung project và việc hiện tại, từ lúc mở phiên và mỗi tin nhắn."""

    def test_profile_detects_language_tests_ci_and_security(self):
        sys.path.insert(0, str(PLUGIN / "lib"))
        import agentstack as A
        prof = A.project_profile(self.python_repo(), use_cache=False)
        self.assertEqual(prof["kinds"][0], "python")
        self.assertEqual(set(prof["markers"]), {"tests", "ci"})
        c = self.repo("c", {"src/main.c": "int main(){}\n", "src/auth.c": "\n", "src/crypto_util.c": "\n",
                            "src/acl.h": "\n", "tests/fixtures/auth_fake.c": "\n"})
        prof = A.project_profile(c, use_cache=False)
        self.assertEqual(prof["kinds"], ["c_cpp"])
        self.assertIn("security", prof["markers"])
        plain = self.tmp / "plain"
        plain.mkdir()
        self.assertIsNone(A.project_profile(plain, use_cache=False))  # không quét thư mục thường như ~/Documents

    def test_session_hint_combines_profile_and_next_task(self):
        root = self.python_repo(plan_next="Thêm tính năng xuất CSV cho trang báo cáo")
        hint = route.session_hint(root)
        self.assertIn("Python", hint["context"])
        self.assertIn("agent-stack:test-runner", hint["context"])
        # Project có test nên dùng cấu hình rẻ, kèm đường lên bậc.
        self.assertIn("→ claude-haiku-5-5 · low (test trượt thì sonnet · medium) · skill reuse-best", hint["context"])
        self.assertIn("dòng ➡️", hint["context"])
        self.assertIn("🧭 Python", hint["user"])

    def test_continue_prompt_is_routed_by_next_task_in_plan(self):
        root = self.python_repo(plan_next="Viết test cho module thanh toán rồi chạy pytest")
        hit = route.hook_suggestion("làm tiếp đi", {"session_id": "c1", "cwd": str(root)})
        self.assertIn("theo việc tiếp theo trong §0", hit["context"])
        self.assertIn("agent-stack:test-runner", hit["user"])
        self.assertIsNone(route.hook_suggestion("ok", {"session_id": "c2", "cwd": str(root)}))

    def test_project_type_adds_skills_to_a_rule(self):
        # Luật thật không còn skill theo loại project cho C (c-review đã xoá 10/10/2026); thử cơ chế bằng một
        # plugin scope project có thật trong catalog (superpowers).
        from unittest import mock
        data = dict(route.rules())  # bản sao nông, không đụng bản rules() đã nạp
        data["rule_extras"] = {**data["rule_extras"], "c_cpp": {"security-review": ["superpowers"]}}
        root = self.repo("c2", {"src/main.c": "\n", "src/io.c": "\n", "src/util.c": "\n"})
        patch = mock.patch.object(route, "rules", return_value=data)
        patch.start()
        self.addCleanup(patch.stop)
        hit = route.hook_suggestion("Review bảo mật hàm đăng nhập này giúp mình", {"session_id": "c3", "cwd": str(root)})
        # Plugin chưa bật cho project: không gợi ý như thể dùng được, mà nêu lệnh cài và dùng skill dự phòng.
        self.assertNotIn("superpowers", hit["user"])
        self.assertIn("skill security-review", hit["user"])
        self.assertIn("chưa bật cho project này: differential-review (`./install.sh --apply --only catalog", hit["context"])
        self.assertIn("`claude plugin install superpowers@agent-stack-vendor-local --scope project`", hit["context"])
        self.assertIn("đừng tự cài", hit["context"])
        self.write("c2/.claude/settings.local.json", json.dumps({"enabledPlugins": {
            "superpowers@agent-stack-vendor-local": True, "differential-review@agent-stack-vendor-local": True}}))
        hit = route.hook_suggestion("Review bảo mật hàm xác thực khác giúp mình", {"session_id": "c3b", "cwd": str(root)})
        self.assertIn("skill differential-review, superpowers", hit["user"])
        self.assertNotIn("chưa bật", hit["context"])
        # Gọi thẳng differential-review (không qua chot-viec) vẫn mang theo chốt chặn TM-3, TM-4.
        self.assertIn("không git checkout", hit["context"])
        self.assertIn("đừng để ở gốc repo", hit["context"])

    def test_repo_audit_runs_semgrep_before_claude_security(self):
        # static-analysis cài toàn cục ngày 10/10/2026: audit cả repo quét Semgrep trước, kèm lời dặn không dùng CodeQL.
        root = self.python_repo()
        self.write("py/.claude/settings.local.json", json.dumps({"enabledPlugins": {
            "static-analysis@agent-stack-vendor-local": True, "claude-security@claude-plugins-official": True}}))
        hit = route.hook_suggestion("Audit bảo mật toàn bộ codebase trước khi phát hành", {"session_id": "a1", "cwd": str(root)})
        self.assertIn("skill static-analysis, claude-security", hit["user"])
        self.assertIn("static-analysis:semgrep", hit["context"])
        self.assertIn("không dùng static-analysis:codeql", hit["context"])
        self.assertIn("static_analysis_semgrep_N ở gốc repo", hit["context"])

    def test_feature_touching_trust_boundary_asks_for_threat_model_first(self):
        root = self.python_repo()
        hit = route.hook_suggestion("Thêm tính năng upload ảnh đại diện cho người dùng", {"session_id": "f1", "cwd": str(root)})
        self.assertIn("feature-boundary", hit["context"])
        self.assertIn("mo-hinh-de-doa", hit["context"])
        self.assertIn("trước khi code", hit["context"])
        plain = route.hook_suggestion("Thêm tính năng xuất CSV cho trang báo cáo", {"session_id": "f2", "cwd": str(root)})
        self.assertNotIn("mo-hinh-de-doa", plain["context"])

    def test_session_start_hook_speaks_for_git_repo_without_plan(self):
        root = self.python_repo()
        out = subprocess.run([sys.executable, str(PLUGIN / "hooks" / "session_start.py")],
                             input=json.dumps({"session_id": "s-np", "source": "startup", "cwd": str(root)}),
                             capture_output=True, text=True, timeout=30, env=dict(os.environ))
        data = json.loads(out.stdout)
        self.assertIn("Hồ sơ project", data["hookSpecificOutput"]["additionalContext"])
        self.assertIn("🧭 Python", data["systemMessage"])

    def test_footer_rule_is_every_message_and_includes_skill(self):
        shared = (REPO / "global" / "SHARED.global.md").read_text(encoding="utf-8")
        self.assertIn("Cuối mọi câu trả lời, kể cả câu trả lời ngắn", shared)
        self.assertIn("· Skill: <tên|không>", shared)
        claude = (REPO / "global" / "CLAUDE.global.md").read_text(encoding="utf-8")
        self.assertIn("| Việc | Model·Effort | Subagent | Skill |", claude)
        self.assertNotIn("Bỏ qua dòng này với câu hỏi nhanh", claude)


class SessionCliForToolsWithoutHooks(ProjectFixtures):
    """route.py --session in hồ sơ project cho công cụ không có hook SessionStart."""

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(ROUTE), *args], capture_output=True, text=True, timeout=30,
                              env=dict(os.environ))

    def test_session_cli_prints_profile_hint(self):
        root = self.python_repo(plan_next="Thêm tính năng xuất CSV cho trang báo cáo")
        out = self.run_cli("--session", str(root))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("[agent-stack] Hồ sơ project", out.stdout)
        self.assertIn("skill reuse-best", out.stdout)
        plain = self.tmp / "plain-dir"
        plain.mkdir()
        self.assertIn("Không có gợi ý", self.run_cli("--session", str(plain)).stdout)

    def test_project_flag_localizes_skills(self):
        # Plugin chưa bật cho project (cấu hình Claude Code cách ly trong ProjectFixtures): nêu lệnh cài, dùng skill dự phòng.
        root = self.repo("c3", {"src/main.c": "\n", "src/io.c": "\n", "src/util.c": "\n"})
        data = json.loads(self.run_cli("review bảo mật hàm đăng nhập", "--project", str(root)).stdout)
        self.assertIn("differential-review", [m["skill"] for m in data["missing"]])
        self.assertNotIn("differential-review", data["skills"])
        self.assertIn("security-review", data["skills"])
        self.assertNotIn("c-review", json.dumps(data))
