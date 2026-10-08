import json
import os
import subprocess
import sys
import time

from tests._util import PLUGIN, REPO, SUBAGENT_HANDBACK, TempDirTestCase

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

    def test_rules_are_consistent(self):
        efforts = {"low", "medium", "high", "xhigh", "max"}
        rules = route.rules()["rules"]
        ids = {r["id"] for r in rules}
        self.assertEqual(len(ids), len(rules), "id luật bị trùng")
        for r in rules:
            with self.subTest(rule=r["id"]):
                self.assertIn(r["model"], route.FAMILIES)
                self.assertIn(r.get("effort"), efforts)  # Haiku 5.5 cũng có effort
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

    def test_on_demand_skills_not_suggested(self):
        # Skill scope on-demand (vendor tắt mặc định 08/10/2026) không được nằm trong luật hay hồ sơ project.
        catalog = json.loads((REPO / "catalog.json").read_text(encoding="utf-8"))
        on_demand = {i["install"].get("name") or i["install"].get("plugin")
                     for i in catalog["items"] if i["scope"] == "on-demand"}
        self.assertTrue({"tdd", "diagnosing-bugs", "humanizer"} <= on_demand)
        data = route.rules()
        used = {s for r in data["rules"] for s in r.get("skills", [])}
        used |= {s for v in data["markers"].values() for s in v.get("skills", [])}
        used |= {s for k, v in data["profiles"].items() if k != "web" for s in v.get("skills", [])}
        self.assertEqual(used & on_demand, set())
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


class ProjectFixtures(TempDirTestCase):
    """Dựng project mẫu (git) cho các test chọn skill theo project. Không chứa test."""

    def setUp(self):
        super().setUp()
        os.environ["AGENT_STACK_STATE"] = str(self.tmp / "state")
        self.addCleanup(os.environ.pop, "AGENT_STACK_STATE", None)

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
    """Đề xuất LSP (pyright-lsp, clangd-lsp) riêng cho project cần nó, không cài toàn cục."""

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

    def test_c_project_with_cmake_gets_clangd(self):
        root = self.repo("cproj", {"src/a.c": "\n", "src/b.c": "\n", "src/c.h": "\n", "CMakeLists.txt": "project(x)\n"})
        hint = route.session_hint(root)
        self.assertIn("clangd-lsp", hint["context"])
        self.assertIn("CMakeLists.txt", hint["context"])


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
        self.assertIn("→ sonnet · medium · skill reuse-best", hint["context"])
        self.assertIn("dòng ➡️", hint["context"])
        self.assertIn("🧭 Python", hint["user"])

    def test_continue_prompt_is_routed_by_next_task_in_plan(self):
        root = self.python_repo(plan_next="Viết test cho module thanh toán rồi chạy pytest")
        hit = route.hook_suggestion("làm tiếp đi", {"session_id": "c1", "cwd": str(root)})
        self.assertIn("theo việc tiếp theo trong §0", hit["context"])
        self.assertIn("agent-stack:test-runner", hit["user"])
        self.assertIsNone(route.hook_suggestion("ok", {"session_id": "c2", "cwd": str(root)}))

    def test_project_type_adds_skills_to_a_rule(self):
        root = self.repo("c2", {"src/main.c": "\n", "src/io.c": "\n", "src/util.c": "\n"})
        hit = route.hook_suggestion("Review bảo mật hàm đăng nhập này giúp mình", {"session_id": "c3", "cwd": str(root)})
        self.assertIn("c-review", hit["user"])

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
    """OpenCode không chèn được ngữ cảnh lúc mở phiên, nên luật chung dặn chạy route.py --session."""

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

    def test_project_flag_adds_skills_by_project_type(self):
        root = self.repo("c3", {"src/main.c": "\n", "src/io.c": "\n", "src/util.c": "\n"})
        data = json.loads(self.run_cli("review bảo mật hàm đăng nhập", "--project", str(root)).stdout)
        self.assertIn("c-review", data["skills"])

    def test_opencode_rules_tell_tools_without_hooks_to_run_it(self):
        # OpenCode đọc AGENTS.global.md, file ghép từ SHARED.global.md và OPENCODE.global.md
        opencode = (REPO / "global" / "AGENTS.global.md").read_text(encoding="utf-8")
        self.assertIn("route.py --session <thư mục project>", opencode)
