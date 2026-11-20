"""H5 mục 1, lát B (20/11/2026): Claude thấy bộ đang bật và được gợi ý bật bộ khi việc cần.

Spec: `.agent/spec/h5-bo-goi-y.txt` (slug h5-bo-goi-y). Bộ đang bật tạo bằng chính `profile.py on` (lát A); hook, router
và tiêu đề skill được kiểm qua hành vi nhìn thấy. Mọi thư mục (project, cấu hình, state) là thư mục tạm."""
import json
import os
import re
import subprocess
import sys

from tests._util import PLUGIN, TempDirTestCase, git
from tests.test_agentstack_lib import PLAN

sys.path.insert(0, str(PLUGIN / "lib"))
sys.path.insert(0, str(PLUGIN / "skills" / "task-router" / "scripts"))

HOOKS = PLUGIN / "hooks"
PROFILE = PLUGIN / "skills" / "project-setup" / "scripts" / "profile.py"
SKILLS = PLUGIN / "skills"
KAGGLE_SKILL = SKILLS / "kaggle-gpu" / "SKILL.md"
VENDOR = "agent-stack-vendor@agent-stack-vendor-local"
CORE_SKILLS = {"done-gate", "session-keeper", "threat-model", "vet-skill", "task-router", "progress",
               "reader-page", "reuse-best", "recursive-session", "aside-web"}
NON_CORE_SKILL_PATHS = {name: SKILLS / name / "SKILL.md"
                        for name in ("kaggle-gpu", "writing-voice", "project-setup")}
KAGGLE_PROMPT = "chạy job train mô hình trên kaggle giúp mình"


def frontmatter(path):
    """Các dòng giữa hai dấu --- đầu file."""
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines and lines[0].strip() == "---", path
    end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    return [ln.strip() for ln in lines[1:end]]


class BundleBase(TempDirTestCase):
    """Project git có PLAN.md (để SessionStart không im lặng) cùng cấu hình Claude Code và state riêng."""

    def setUp(self):
        super().setUp()
        self.state = self.tmp / "state"
        self.config = self.tmp / "claude-config"
        (self.config / "plugins").mkdir(parents=True)
        self.project = self.tmp / "proj"
        self.project.mkdir()
        (self.project / "PLAN.md").write_text(PLAN, encoding="utf-8")
        git(self.project, "init", "-q")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "init")
        installed = {"version": 2, "plugins": {VENDOR: [{"scope": "user", "installPath": "/x", "version": "1"}]}}
        (self.config / "plugins" / "installed_plugins.json").write_text(json.dumps(installed))

    def env(self):
        env = dict(os.environ, AGENT_STACK_STATE=str(self.state), CLAUDE_CONFIG_DIR=str(self.config),
                   AGENT_STACK_PLUGINS_DIR=str(self.config / "plugins"))
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)
        return env

    def bundle_on(self, *names, user=False):
        scope = ["--user"] if user else ["--project", str(self.project)]
        out = subprocess.run([sys.executable, str(PROFILE), *scope, "on", *names], capture_output=True,
                             text=True, env=self.env(), timeout=30)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def hook(self, name, payload):
        out = subprocess.run([sys.executable, str(HOOKS / name)], input=json.dumps(payload), capture_output=True,
                             text=True, env=self.env(), timeout=30, cwd=str(self.project))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stderr, "")
        return json.loads(out.stdout) if out.stdout.strip() else None

    def context(self, out):
        return ((out or {}).get("hookSpecificOutput") or {}).get("additionalContext", "")

    def start_ctx(self, sid="s"):
        out = self.hook("session_start.py", {"session_id": sid, "source": "startup", "cwd": str(self.project)})
        self.assertIsNotNone(out)  # có PLAN §0 nên hook phải in
        return self.context(out)

    def prompt_ctx(self, sid, prompt):
        return self.context(self.hook("prompt_submit.py", {"session_id": sid, "prompt": prompt,
                                                           "cwd": str(self.project)}))


class SessionStartTests(BundleBase):
    def test_session_start_prints_bundle_name_and_skill_path(self):
        # spec:h5-bo-goi-y#S1
        self.bundle_on("ml")
        ctx = self.start_ctx()
        self.assertIn(str(KAGGLE_SKILL), ctx)
        self.assertRegex(ctx, r"\bml\b")
        self.assertIn("Việc tiếp theo", ctx)  # phần nạp §0 cũ vẫn còn

    def test_session_start_prints_bundle_turned_on_for_user_scope(self):
        # spec:h5-bo-goi-y#S1
        self.bundle_on("ml", user=True)
        ctx = self.start_ctx()
        self.assertIn(str(KAGGLE_SKILL), ctx)
        self.assertRegex(ctx, r"\bml\b")

    def test_session_start_has_no_bundle_line_when_none_is_on(self):
        # spec:h5-bo-goi-y#S1
        ctx = self.start_ctx()
        for path in NON_CORE_SKILL_PATHS.values():
            self.assertNotIn(str(path), ctx)
        self.assertNotRegex(ctx, r"\bml\b")
        self.assertIn("Việc tiếp theo", ctx)

    def test_session_start_stops_printing_after_bundle_is_off(self):
        # spec:h5-bo-goi-y#S1
        self.bundle_on("ml")
        subprocess.run([sys.executable, str(PROFILE), "--project", str(self.project), "off", "ml"],
                       env=self.env(), check=True, capture_output=True, timeout=30)
        self.assertNotIn(str(KAGGLE_SKILL), self.start_ctx())

    def test_local_off_hides_bundle_turned_on_for_user_scope(self):
        # spec:h5-bo-goi-y#S1 (review opus·xhigh 20/11: local tắt phải che bộ bật ở user)
        self.bundle_on("ml", user=True)
        for verb in (["off", "ml"], ["loi"]):
            subprocess.run([sys.executable, str(PROFILE), "--project", str(self.project), *verb],
                           env=self.env(), check=True, capture_output=True, timeout=30)
            self.assertNotIn(str(KAGGLE_SKILL), self.start_ctx(f"s-{verb[0]}"), verb)
        self.bundle_on("ml")
        self.assertIn(str(KAGGLE_SKILL), self.start_ctx("s-on-again"))

    def test_session_start_hides_bundle_whose_plugin_is_pinned_off_locally(self):
        # spec:h5-bo-goi-y#S1 (review lại opus·xhigh 20/11: local false đè user true, bộ không thật sự bật)
        self.bundle_on("giao-dien")
        subprocess.run([sys.executable, str(PROFILE), "--project", str(self.project), "off", "giao-dien"],
                       env=self.env(), check=True, capture_output=True, timeout=30)
        self.bundle_on("ml", user=True)
        self.assertNotIn(str(KAGGLE_SKILL), self.start_ctx("pinned-off"))
        self.assertIn("profile.py on ml", self.prompt_ctx("pinned-off-hint", KAGGLE_PROMPT))

    def test_off_returns_shared_plugin_to_the_other_scope(self):
        # spec:h5-bo-goi-y#S1 (review lại opus·xhigh 20/11: không để plugin ghim true khi không bộ nào còn bật)
        local = self.project / ".claude" / "settings.local.json"
        self.bundle_on("giao-dien", user=True)
        self.bundle_on("ml")
        subprocess.run([sys.executable, str(PROFILE), "--project", str(self.project), "off", "ml"],
                       env=self.env(), check=True, capture_output=True, timeout=30)
        data = json.loads(local.read_text()) if local.exists() else {}
        self.assertNotIn(VENDOR, data.get("enabledPlugins", {}))

    def test_profile_in_git_subfolder_writes_where_hooks_look(self):
        # spec:h5-bo-goi-y#S1 (review lại opus·xhigh 20/11: profile.py và hook cùng gốc git)
        subprocess.run(["git", "init", "-q", str(self.project)], check=True, capture_output=True, timeout=30)
        sub = self.project / "app" / "src"
        sub.mkdir(parents=True)
        subprocess.run([sys.executable, str(PROFILE), "--project", str(sub), "on", "ml"], env=self.env(), check=True,
                       capture_output=True, timeout=30)
        self.assertTrue((self.project / ".claude" / "settings.local.json").exists())
        self.assertFalse((sub / ".claude").exists())
        self.assertIn(str(KAGGLE_SKILL), self.start_ctx("git-sub"))

    def test_prompt_hint_skips_plugin_bundle_already_enabled_in_settings(self):
        # spec:h5-bo-goi-y#S3 (review opus·xhigh 20/11: cấu hình user cũ đã bật plugin thì khỏi gợi ý)
        semgrep = "static-analysis@agent-stack-vendor-local"
        installed = json.loads((self.config / "plugins" / "installed_plugins.json").read_text())
        installed["plugins"][semgrep] = [{"scope": "user", "installPath": "/x", "version": "1"}]
        (self.config / "plugins" / "installed_plugins.json").write_text(json.dumps(installed))
        prompt = "quét semgrep cả repo trước khi phát hành"
        self.assertIn("profile.py on bao-mat", self.prompt_ctx("sem-off", prompt))
        (self.config / "settings.json").write_text(json.dumps({"enabledPlugins": {semgrep: True}}))
        self.assertNotIn("profile.py on bao-mat", self.prompt_ctx("sem-on", prompt))

    def test_session_start_ignores_unknown_names_and_paths_in_records(self):
        # spec:h5-bo-goi-y#S2
        self.bundle_on("ml")
        self.bundle_on("ml", user=True)
        folder = self.state / "profiles"
        self.assertTrue(list(folder.glob("*")), "profile.py on phải để lại bản ghi")

        def poison(node):
            """Thêm tên bộ lạ và đường dẫn lạ vào mọi chỗ của bản ghi, giữ nguyên phần hợp lệ."""
            if isinstance(node, list):
                for item in list(node):
                    poison(item)
                if "ml" in node:
                    node.append("evil-bundle")
                    node.append("/etc/passwd")
            elif isinstance(node, dict):
                for item in list(node.values()):
                    poison(item)
                node.update({"evil-bundle": {"skills": ["/etc/passwd"]}, "skills": ["/etc/passwd"],
                             "paths": ["/etc/passwd"], "on": ["evil-bundle", "ml"]})
        for path in folder.glob("*"):
            if path.suffix == ".json":
                data = json.loads(path.read_text())
                poison(data)
                path.write_text(json.dumps(data))
        (folder / "bogus.json").write_text(json.dumps({"on": ["evil-bundle"], "bundles": ["evil-bundle"],
                                                       "skills": ["/etc/passwd"], "path": "/etc/passwd"}))
        ctx = self.start_ctx()
        self.assertNotIn("evil-bundle", ctx)
        self.assertNotIn("/etc/passwd", ctx)
        self.assertNotIn("passwd", ctx)
        self.assertIn(str(KAGGLE_SKILL), ctx)  # tên hợp lệ vẫn được in


class PromptHintTests(BundleBase):
    def test_prompt_hint_names_skill_and_command_for_bundle_not_on(self):
        # spec:h5-bo-goi-y#S3
        ctx = self.prompt_ctx("hint-off", KAGGLE_PROMPT)
        self.assertIn(str(KAGGLE_SKILL), ctx)
        self.assertIn("profile.py on ml", ctx)

    def test_prompt_hint_is_silent_when_bundle_already_on(self):
        # spec:h5-bo-goi-y#S3
        self.bundle_on("ml")
        ctx = self.prompt_ctx("hint-on", KAGGLE_PROMPT)
        self.assertNotIn("profile.py on ml", ctx)

    def test_prompt_hint_is_silent_for_unrelated_prompt(self):
        # spec:h5-bo-goi-y#S3
        ctx = self.prompt_ctx("hint-none", "sửa lỗi parser đọc sai ngày trong báo cáo")
        self.assertNotIn("profile.py on", ctx)

    def test_prompt_hint_matches_whole_words_only(self):
        # spec:h5-bo-goi-y#S3
        ctx = self.prompt_ctx("hint-word", "đổi tên biến kagglex_count và slackness trong hàm tính điểm")
        self.assertIsNone(re.search(r"profile\.py on (ml|viet)\b", ctx), ctx)


class RouterHintTests(BundleBase):
    def setUp(self):
        super().setUp()
        for key, value in (("AGENT_STACK_STATE", str(self.state)), ("CLAUDE_CONFIG_DIR", str(self.config)),
                           ("AGENT_STACK_PLUGINS_DIR", str(self.config / "plugins"))):
            old = os.environ.get(key)
            os.environ[key] = value
            self.addCleanup(lambda k=key, o=old: os.environ.pop(k, None) if o is None else os.environ.__setitem__(k, o))
        import route
        self.route = route

    def missing(self, skill):
        hit = self.route.localize({"skills": [skill]}, self.project)
        entries = [m for m in hit["missing"] if m["skill"] == skill]
        self.assertEqual(len(entries), 1, hit["missing"])
        return json.dumps(entries[0], ensure_ascii=False)

    def test_router_points_to_profile_command_for_plugin_of_bundle_not_on(self):
        # spec:h5-bo-goi-y#S4
        for skill, bundle in (("static-analysis", "bao-mat"), ("claude-security", "bao-mat"),
                              ("html-plan", "giao-dien")):
            text = self.missing(skill)
            self.assertIn(f"profile.py on {bundle}", text, skill)
            self.assertNotIn("install.sh", text, skill)
            self.assertNotIn("claude plugin install", text, skill)

    def test_router_keeps_install_hint_for_core_plugin(self):
        # spec:h5-bo-goi-y#S4
        text = self.missing("differential-review")
        self.assertIn("install.sh", text)
        self.assertNotIn("profile.py on", text)

    def test_router_notes_skill_md_path_for_hidden_agent_stack_skill(self):
        # spec:h5-bo-goi-y#S6
        notes = self.route.hidden_skill_notes(["writing-voice", "done-gate"])
        self.assertEqual(len(notes), 1, notes)
        self.assertIn(str(PLUGIN / "skills" / "writing-voice" / "SKILL.md"), notes[0])
        self.assertIn("viet", notes[0])


class SkillFrontmatterTests(TempDirTestCase):
    def folders(self):
        return sorted(p.parent.name for p in SKILLS.glob("*/SKILL.md"))

    def test_registry_lists_every_skill_folder_in_exactly_one_bundle(self):
        # spec:h5-bo-goi-y#S5
        import bundles
        self.assertEqual(bundles.CORE, "loi")
        self.assertEqual(set(bundles.BUNDLES), {"loi", "bao-mat", "giao-dien", "ml", "viet", "cau-hinh"})
        for name, bundle in bundles.BUNDLES.items():
            self.assertIsInstance(bundle["label"], str, name)
            for key in ("plugins", "skills", "keywords"):
                self.assertIsInstance(bundle[key], tuple, f"{name}.{key}")
        self.assertEqual(set(bundles.BUNDLES["loi"]["skills"]), CORE_SKILLS)
        counts = {}
        for bundle in bundles.BUNDLES.values():
            for skill in bundle["skills"]:
                counts[skill] = counts.get(skill, 0) + 1
        self.assertEqual({skill: n for skill, n in counts.items() if n != 1}, {}, "skill nằm ở nhiều bộ")
        self.assertEqual(sorted(counts), self.folders())

    def test_non_core_skills_are_hidden_from_model_and_core_skills_are_not(self):
        # spec:h5-bo-goi-y#S5
        import bundles
        owner = {skill: name for name, bundle in bundles.BUNDLES.items() for skill in bundle["skills"]}
        flag = "disable-model-invocation: true"
        for folder in self.folders():
            self.assertIn(folder, owner, f"{folder} chưa thuộc bộ nào")
            has_flag = flag in frontmatter(SKILLS / folder / "SKILL.md")
            if owner[folder] != bundles.CORE:
                self.assertTrue(has_flag, f"{folder} thuộc bộ {owner[folder]}, cần {flag}")
            elif folder != "recursive-session":
                self.assertFalse(has_flag, f"{folder} thuộc lõi, không được ẩn khỏi model")

    def test_known_non_core_skills_carry_the_flag_without_registry(self):
        # spec:h5-bo-goi-y#S5
        for folder in ("kaggle-gpu", "writing-voice", "project-setup"):
            self.assertIn("disable-model-invocation: true", frontmatter(SKILLS / folder / "SKILL.md"), folder)
        for folder in sorted(CORE_SKILLS - {"recursive-session"}):
            self.assertNotIn("disable-model-invocation: true", frontmatter(SKILLS / folder / "SKILL.md"), folder)
        self.assertIn("disable-model-invocation: true", frontmatter(SKILLS / "recursive-session" / "SKILL.md"))


class PluginBundleHintTests(BundleBase):
    def test_hint_for_plugin_bundle_lists_installed_skill_files_and_reload(self):
        # spec:h5-bo-goi-y#S7
        semgrep = "static-analysis@agent-stack-vendor-local"
        root = self.config / "plugins" / "cache" / "agent-stack-vendor-local" / "static-analysis" / "1.5.0"
        for skill in ("semgrep", "sarif-parsing"):
            (root / "skills" / skill).mkdir(parents=True)
            (root / "skills" / skill / "SKILL.md").write_text("---\nname: x\n---\n")
        installed = json.loads((self.config / "plugins" / "installed_plugins.json").read_text())
        installed["plugins"][semgrep] = [{"scope": "user", "installPath": str(root), "version": "1.5.0"}]
        (self.config / "plugins" / "installed_plugins.json").write_text(json.dumps(installed))
        ctx = self.prompt_ctx("plug-hint", "quét semgrep cả repo trước khi phát hành")
        self.assertIn("profile.py on bao-mat", ctx)
        for skill in ("semgrep", "sarif-parsing"):
            self.assertIn(str((root / "skills" / skill / "SKILL.md").resolve()), ctx)
        self.assertIn("/reload-plugins", ctx)


class RouterRootTests(BundleBase):
    def test_router_reads_settings_at_git_root_like_profile(self):
        # spec:h5-bo-goi-y#S4 (review lại fable·high 20/11: router tra cùng gốc với profile.py)
        for key, value in (("AGENT_STACK_STATE", str(self.state)), ("CLAUDE_CONFIG_DIR", str(self.config)),
                           ("AGENT_STACK_PLUGINS_DIR", str(self.config / "plugins"))):
            old = os.environ.get(key)
            os.environ[key] = value
            self.addCleanup(lambda k=key, o=old: os.environ.pop(k, None) if o is None else os.environ.__setitem__(k, o))
        import route
        sub = self.project / "sub"
        sub.mkdir()
        (sub / "PLAN.md").write_text(PLAN, encoding="utf-8")
        semgrep = "static-analysis@agent-stack-vendor-local"
        installed = json.loads((self.config / "plugins" / "installed_plugins.json").read_text())
        installed["plugins"][semgrep] = [{"scope": "user", "installPath": "/x", "version": "1"}]
        (self.config / "plugins" / "installed_plugins.json").write_text(json.dumps(installed))
        subprocess.run([sys.executable, str(PROFILE), "--project", str(sub), "on", "bao-mat"], env=self.env(),
                       check=True, capture_output=True, timeout=30)
        hit = route.localize({"skills": ["static-analysis"]}, sub)
        self.assertEqual(hit["missing"], [])
        self.assertIn("static-analysis", hit["skills"])

    def test_router_respects_false_at_git_root_over_user_true(self):
        # spec:h5-bo-goi-y#S4 (review lại fable·high 20/11: `false` ở gốc git đè `true` của user khi cwd là thư mục con)
        for key, value in (("AGENT_STACK_STATE", str(self.state)), ("CLAUDE_CONFIG_DIR", str(self.config)),
                           ("AGENT_STACK_PLUGINS_DIR", str(self.config / "plugins"))):
            old = os.environ.get(key)
            os.environ[key] = value
            self.addCleanup(lambda k=key, o=old: os.environ.pop(k, None) if o is None else os.environ.__setitem__(k, o))
        import route
        sub = self.project / "sub2"
        sub.mkdir()
        semgrep = "static-analysis@agent-stack-vendor-local"
        installed = json.loads((self.config / "plugins" / "installed_plugins.json").read_text())
        installed["plugins"][semgrep] = [{"scope": "user", "installPath": "/x", "version": "1"}]
        (self.config / "plugins" / "installed_plugins.json").write_text(json.dumps(installed))
        for args in (["--user", "on", "bao-mat"], ["--project", str(sub), "off", "bao-mat"]):
            subprocess.run([sys.executable, str(PROFILE), *args], env=self.env(), check=True, capture_output=True,
                           timeout=30)
        hit = route.localize({"skills": ["static-analysis"]}, sub)
        self.assertNotIn("static-analysis", hit["skills"])
        self.assertIn("profile.py on bao-mat", json.dumps(hit["missing"], ensure_ascii=False))


class AskedBundleTests(BundleBase):
    def test_user_saying_turn_on_bundle_gets_the_exact_command(self):
        # spec:h5-bo-goi-y#S8
        for sid, prompt, want in (("a1", "bật bộ ml giúp mình", "profile.py on ml"),
                                  ("a2", "bat bo bao mat", "profile.py on bao-mat"),
                                  ("a3", "Tắt bộ giao-dien đi", "profile.py off giao-dien")):
            ctx = self.prompt_ctx(sid, prompt)
            self.assertIn(want, ctx, prompt)
            self.assertIn("--project", ctx, prompt)

    def test_unknown_bundle_name_gets_no_command(self):
        # spec:h5-bo-goi-y#S8
        for sid, prompt in (("b1", "bật bộ hack cho mình"), ("b2", "bật bộ loi"), ("b3", "bật bộ mlx")):
            self.assertNotIn("profile.py on", self.prompt_ctx(sid, prompt), prompt)
            self.assertNotIn("profile.py off", self.prompt_ctx(sid + "x", prompt), prompt)

    def test_negation_question_or_discussion_is_not_a_command(self):
        # spec:h5-bo-goi-y#S8 (review fable·high 20/11: chỉ tin là lệnh ngắn mới tính)
        import bundles
        for prompt in ("không bật bộ ml, mình chỉ hỏi nó gồm gì", "đừng tắt bộ bảo mật nhé", "có nên bật bộ ml không?",
                       "sửa lỗi: khi tắt bộ ml thì plugin vendor bị tắt theo", "bật bộ giao diện tối cho app"):
            self.assertEqual(bundles.asked(prompt), [], prompt)
        self.assertEqual(bundles.asked("bật bộ ml và viết nhé"), [("on", "ml"), ("on", "viet")])
