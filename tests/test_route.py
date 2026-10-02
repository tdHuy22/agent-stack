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
        shared = (REPO / "global" / "AGENTS.global.md").read_text(encoding="utf-8")
        self.assertIn("Cuối mọi câu trả lời, kể cả câu trả lời ngắn", shared)
        self.assertIn("· Skill: <tên|không>", shared)
        claude = (REPO / "global" / "CLAUDE.global.md").read_text(encoding="utf-8")
        self.assertIn("| Việc tiếp theo | Model · Effort | Subagent | Skill |", claude)
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

    def test_shared_rules_tell_tools_without_hooks_to_run_it(self):
        shared = (REPO / "global" / "AGENTS.global.md").read_text(encoding="utf-8")
        self.assertIn("route.py --session <thư mục project>", shared)
