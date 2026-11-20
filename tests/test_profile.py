"""H5 mục 1, lát A (20/11/2026): `profile.py` v2, nhiều bộ plugin bật/tắt theo project hay theo người dùng.

Spec: `.agent/spec/h5-bo-profile.txt` (slug h5-bo-profile). Lệnh chạy như tiến trình con, mọi thư mục (project, cấu hình
Claude Code, state) là thư mục tạm; không đụng ~/.claude thật."""
import json
import os
import subprocess
import sys

from tests._util import PLUGIN, TempDirTestCase

PROFILE = PLUGIN / "skills" / "project-setup" / "scripts" / "profile.py"

CORE_PLUGINS = ("agent-stack@agent-stack-local", "differential-review@agent-stack-vendor-local")
SECURITY = ("static-analysis@agent-stack-vendor-local", "claude-security@claude-plugins-official")
UI = ("html-plan@agent-stack-vendor-local", "playground@claude-plugins-official",
      "project-artifact@claude-plugins-official", "agent-stack-vendor@agent-stack-vendor-local")
VENDOR = "agent-stack-vendor@agent-stack-vendor-local"
NON_CORE_PLUGINS = set(SECURITY) | set(UI)  # ml dùng lại VENDOR đã nằm trong UI
VALID_NAMES = ("bao-mat", "giao-dien", "ml", "viet", "cau-hinh")
KAGGLE_SKILL = PLUGIN / "skills" / "kaggle-gpu" / "SKILL.md"


class ProfileBase(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.state = self.tmp / "state"
        self.config = self.tmp / "claude-config"
        (self.config / "plugins").mkdir(parents=True)
        self.project = self.tmp / "proj"
        (self.project / ".claude").mkdir(parents=True)
        self.local = self.project / ".claude" / "settings.local.json"
        self.local.write_text(json.dumps({"enabledPlugins": {"pyright-lsp@claude-plugins-official": True},
                                          "permissions": {"allow": ["Bash(ls)"]}, "model": "opus"}))
        self.before = json.loads(self.local.read_text())

    def install(self, *plugins):
        """Ghi installed_plugins.json giả: chỉ các plugin này được coi là đã cài."""
        data = {"version": 2, "plugins": {p: [{"scope": "user", "installPath": f"/x/{p}", "version": "1"}]
                                          for p in plugins}}
        (self.config / "plugins" / "installed_plugins.json").write_text(json.dumps(data))

    def env(self):
        env = dict(os.environ, AGENT_STACK_STATE=str(self.state), CLAUDE_CONFIG_DIR=str(self.config))
        env.pop("AGENT_STACK_PLUGINS_DIR", None)
        return env

    def run_profile(self, *args, expect=0, user=False, env=None):
        scope = ["--user"] if user else ["--project", str(self.project)]
        out = subprocess.run([sys.executable, str(PROFILE), *scope, *args], capture_output=True, text=True,
                             env=env or self.env(), timeout=30)
        self.assertEqual(out.returncode, expect, out.stdout + out.stderr)
        return out.stdout + out.stderr

    def settings(self):
        return json.loads(self.local.read_text())

    def enabled(self):
        return self.settings().get("enabledPlugins", {})

    def records(self):
        folder = self.state / "profiles"
        return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


class ProfileTests(ProfileBase):
    def test_loi_disables_every_non_core_plugin_and_keeps_other_keys(self):
        # spec:h5-bo-profile#S1
        self.run_profile("loi")
        data = self.settings()
        for plugin in NON_CORE_PLUGINS:
            self.assertIs(data["enabledPlugins"].get(plugin), False, plugin)
        for plugin in CORE_PLUGINS:
            self.assertIsNot(data["enabledPlugins"].get(plugin), False, plugin)
        self.assertIs(data["enabledPlugins"]["pyright-lsp@claude-plugins-official"], True)
        self.assertNotIn("skillOverrides", data)
        self.assertEqual(data["permissions"], {"allow": ["Bash(ls)"]})
        self.assertEqual(data["model"], "opus")

    def test_gon_is_an_alias_of_loi(self):
        # spec:h5-bo-profile#S1
        self.run_profile("gon")
        data = self.settings()
        for plugin in NON_CORE_PLUGINS:
            self.assertIs(data["enabledPlugins"].get(plugin), False, plugin)
        self.assertNotIn("skillOverrides", data)

    def test_on_enables_installed_plugins_and_names_the_missing_ones(self):
        # spec:h5-bo-profile#S2
        self.install("playground@claude-plugins-official", "html-plan@agent-stack-vendor-local")
        out = self.run_profile("on", "giao-dien")
        enabled = self.enabled()
        self.assertIs(enabled["playground@claude-plugins-official"], True)
        self.assertIs(enabled["html-plan@agent-stack-vendor-local"], True)
        for plugin in ("project-artifact@claude-plugins-official", VENDOR):
            self.assertNotIn(plugin, enabled)
            self.assertTrue([ln for ln in out.splitlines() if plugin in ln and "chưa cài" in ln],
                            f"{plugin} phải được nêu là chưa cài:\n{out}")
        for plugin in ("playground@claude-plugins-official", "html-plan@agent-stack-vendor-local"):
            self.assertFalse([ln for ln in out.splitlines() if plugin in ln and "chưa cài" in ln], plugin)

    def test_on_ml_prints_kaggle_skill_path_and_enables_installed_vendor(self):
        # spec:h5-bo-profile#S2
        self.install(VENDOR)
        out = self.run_profile("on", "ml")
        self.assertIs(self.enabled()[VENDOR], True)
        self.assertIn(str(KAGGLE_SKILL), out)
        self.assertNotIn("chưa cài", out)

    def test_on_ml_without_vendor_installed_writes_nothing_for_it(self):
        # spec:h5-bo-profile#S2
        out = self.run_profile("on", "ml")
        self.assertNotIn(VENDOR, self.enabled())
        self.assertTrue([ln for ln in out.splitlines() if VENDOR in ln and "chưa cài" in ln], out)
        self.assertIn(str(KAGGLE_SKILL), out)

    def test_off_keeps_plugin_shared_with_a_bundle_still_on(self):
        # spec:h5-bo-profile#S3
        self.install(*UI, *SECURITY, *CORE_PLUGINS)
        self.run_profile("on", "ml", "giao-dien")
        self.assertIs(self.enabled()[VENDOR], True)
        self.run_profile("off", "giao-dien")
        enabled = self.enabled()
        for plugin in ("html-plan@agent-stack-vendor-local", "playground@claude-plugins-official",
                       "project-artifact@claude-plugins-official"):
            self.assertIs(enabled[plugin], False, plugin)
        self.assertIs(enabled[VENDOR], True)
        for plugin in CORE_PLUGINS:
            self.assertIsNot(enabled.get(plugin), False, plugin)

    def test_off_disables_shared_plugin_when_no_other_bundle_uses_it(self):
        # spec:h5-bo-profile#S3
        self.install(*UI, *CORE_PLUGINS)
        self.run_profile("on", "giao-dien")
        self.run_profile("off", "giao-dien")
        enabled = self.enabled()
        for plugin in UI:
            self.assertIs(enabled[plugin], False, plugin)
        for plugin in CORE_PLUGINS:
            self.assertIsNot(enabled.get(plugin), False, plugin)

    def test_off_never_disables_core_plugins_even_when_listed_as_on(self):
        # spec:h5-bo-profile#S3
        self.install(*CORE_PLUGINS, *SECURITY, *UI)
        self.run_profile("on", "bao-mat", "giao-dien", "ml")
        self.run_profile("off", "bao-mat", "giao-dien", "ml")
        for plugin in CORE_PLUGINS:
            self.assertIsNot(self.enabled().get(plugin), False, plugin)

    def test_du_restores_file_after_a_chain_of_changes(self):
        # spec:h5-bo-profile#S4
        self.install(*UI, *SECURITY, *CORE_PLUGINS)
        self.run_profile("loi")
        self.run_profile("on", "ml", "bao-mat")
        self.run_profile("off", "bao-mat")
        self.assertNotEqual(self.settings(), self.before)
        self.run_profile("du")
        self.assertEqual(self.settings(), self.before)

    def test_du_keeps_values_the_user_changed_afterwards(self):
        # spec:h5-bo-profile#S4
        self.install(*UI, *CORE_PLUGINS)
        self.run_profile("loi")
        self.run_profile("on", "giao-dien")
        self.run_profile("off", "giao-dien")
        data = self.settings()
        data["enabledPlugins"]["html-plan@agent-stack-vendor-local"] = True  # người dùng tự bật lại
        data["model"] = "sonnet"
        data["extra"] = {"keep": 1}
        self.local.write_text(json.dumps(data))
        self.run_profile("du")
        after = self.settings()
        self.assertIs(after["enabledPlugins"]["html-plan@agent-stack-vendor-local"], True)
        self.assertEqual(after["model"], "sonnet")
        self.assertEqual(after["extra"], {"keep": 1})
        self.assertEqual(after["permissions"], {"allow": ["Bash(ls)"]})
        for plugin in ("playground@claude-plugins-official", "project-artifact@claude-plugins-official", VENDOR):
            self.assertNotIn(plugin, after["enabledPlugins"], plugin)
        self.assertIs(after["enabledPlugins"]["pyright-lsp@claude-plugins-official"], True)

    def test_unknown_bundle_exits_2_lists_valid_names_and_writes_nothing(self):
        # spec:h5-bo-profile#S5
        raw = self.local.read_bytes()
        for verb in ("on", "off"):
            out = self.run_profile(verb, "khong-co-bo-nay", expect=2)
            for name in VALID_NAMES:
                self.assertIn(name, out)
        self.assertEqual(self.local.read_bytes(), raw)
        self.assertEqual(self.records(), [])

    def test_one_unknown_name_among_valid_ones_writes_nothing(self):
        # spec:h5-bo-profile#S5
        self.install(VENDOR)
        raw = self.local.read_bytes()
        out = self.run_profile("on", "ml", "khong-co-bo-nay", expect=2)
        for name in VALID_NAMES:
            self.assertIn(name, out)
        self.assertEqual(self.local.read_bytes(), raw)
        self.assertEqual(self.records(), [])

    def test_loi_is_rejected_by_on_and_off(self):
        # spec:h5-bo-profile#S5
        raw = self.local.read_bytes()
        for verb in ("on", "off"):
            out = self.run_profile(verb, "loi", expect=2)
            for name in VALID_NAMES:
                self.assertIn(name, out)
        self.run_profile("on", "ml", "loi", expect=2)
        self.assertEqual(self.local.read_bytes(), raw)
        self.assertEqual(self.records(), [])

    def test_user_scope_writes_config_settings_and_keeps_other_keys(self):
        # spec:h5-bo-profile#S6
        user_file = self.config / "settings.json"
        user_file.write_text(json.dumps({"theme": "dark", "enabledPlugins": {"x@y": True}}))
        project_raw = self.local.read_bytes()
        self.run_profile("loi", user=True)
        data = json.loads(user_file.read_text())
        self.assertEqual(data["theme"], "dark")
        self.assertIs(data["enabledPlugins"]["x@y"], True)
        for plugin in NON_CORE_PLUGINS:
            self.assertIs(data["enabledPlugins"].get(plugin), False, plugin)
        self.assertEqual(self.local.read_bytes(), project_raw)  # file của project không bị đụng

    def test_user_scope_creates_file_when_missing_and_on_works(self):
        # spec:h5-bo-profile#S6
        self.install(VENDOR)
        out = self.run_profile("on", "ml", user=True)
        data = json.loads((self.config / "settings.json").read_text())
        self.assertIs(data["enabledPlugins"][VENDOR], True)
        self.assertIn(str(KAGGLE_SKILL), out)
        self.assertEqual(self.settings(), self.before)

    def test_user_scope_symlinked_settings_exits_1_and_writes_nothing(self):
        # spec:h5-bo-profile#S6
        real = self.tmp / "real-settings.json"
        real.write_text(json.dumps({"theme": "dark"}))
        (self.config / "settings.json").symlink_to(real)
        self.run_profile("loi", user=True, expect=1)
        self.assertEqual(json.loads(real.read_text()), {"theme": "dark"})
        self.assertTrue((self.config / "settings.json").is_symlink())
        self.assertEqual(self.records(), [])

    def test_user_scope_symlinked_config_dir_exits_1_and_writes_nothing(self):
        # spec:h5-bo-profile#S6
        real_dir = self.tmp / "real-config"
        (real_dir / "plugins").mkdir(parents=True)
        (real_dir / "settings.json").write_text(json.dumps({"theme": "dark"}))
        link = self.tmp / "link-config"
        link.symlink_to(real_dir)
        env = dict(self.env(), CLAUDE_CONFIG_DIR=str(link))
        self.run_profile("loi", user=True, expect=1, env=env)
        self.assertEqual(json.loads((real_dir / "settings.json").read_text()), {"theme": "dark"})
        self.assertEqual(self.records(), [])

    def test_user_scope_broken_json_exits_1_and_keeps_bytes(self):
        # spec:h5-bo-profile#S6
        user_file = self.config / "settings.json"
        user_file.write_text('{"theme": "dark",')
        self.run_profile("on", "ml", user=True, expect=1)
        self.assertEqual(user_file.read_text(), '{"theme": "dark",')
        self.assertEqual(self.records(), [])

    def show_json(self, **kw):
        out = subprocess.run([sys.executable, str(PROFILE), *(["--user"] if kw.get("user") else
                              ["--project", str(self.project)]), "show", "--json"],
                             capture_output=True, text=True, env=self.env(), timeout=30)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        return json.loads(out.stdout)

    def test_show_json_lists_bundles_and_what_is_on(self):
        # spec:h5-bo-profile#S7
        self.install(*UI, *SECURITY, *CORE_PLUGINS)
        self.assertEqual(self.show_json()["on"], [])
        self.run_profile("on", "ml", "giao-dien")
        self.run_profile("off", "ml")
        data = self.show_json()
        self.assertEqual(sorted(data["on"]), ["giao-dien"])
        by_name = {b["name"]: b for b in data["bundles"]}
        for name in VALID_NAMES:
            self.assertIn(name, by_name)
        self.assertEqual(set(by_name["giao-dien"]["plugins"]), set(UI))
        self.assertEqual(set(by_name["bao-mat"]["plugins"]), set(SECURITY))
        self.assertEqual(list(by_name["ml"]["plugins"]), [VENDOR])
        self.assertEqual(list(by_name["ml"]["skills"]), ["kaggle-gpu"])
        self.assertEqual(list(by_name["viet"]["skills"]), ["writing-voice"])
        self.assertNotIn("web", by_name)  # aside-web vào lõi (bạn chốt 20/11: tắt Browser của app)
        self.assertIn("aside-web", by_name["loi"]["skills"])
        self.assertEqual(list(by_name["cau-hinh"]["skills"]), ["project-setup"])

    def test_show_json_is_per_scope_and_du_clears_on(self):
        # spec:h5-bo-profile#S7
        self.install(VENDOR)
        self.run_profile("on", "ml")
        self.assertEqual(self.show_json()["on"], ["ml"])
        self.assertEqual(self.show_json(user=True)["on"], [])
        self.run_profile("on", "ml", user=True)
        self.assertEqual(self.show_json(user=True)["on"], ["ml"])
        self.run_profile("du")
        self.assertEqual(self.show_json()["on"], [])
        self.assertEqual(self.show_json(user=True)["on"], ["ml"])

    def test_show_json_after_loi_has_no_bundle_on(self):
        # spec:h5-bo-profile#S7
        self.install(VENDOR)
        self.run_profile("on", "ml")
        self.run_profile("loi")
        self.assertEqual(self.show_json()["on"], [])

    def test_on_plugin_only_bundle_with_nothing_installed_is_refused(self):
        # spec:h5-bo-profile#S2 (review sonnet·xhigh 20/11: không ghi bộ là đang bật khi không plugin nào nạp được)
        self.install()
        out = self.run_profile("on", "bao-mat", expect=1)
        self.assertIn("chưa có plugin nào", out)
        self.assertEqual(self.settings(), self.before)
        self.assertEqual(self.show_json()["on"], [])

    def test_off_keeps_plugin_of_bundle_on_in_user_scope(self):
        # spec:h5-bo-profile#S3 (review sonnet·xhigh 20/11: bộ bật ở user cũng giữ plugin dùng chung)
        self.install(*UI)
        self.run_profile("on", "ml", user=True)
        self.run_profile("on", "giao-dien")
        self.run_profile("off", "giao-dien")
        self.assertIsNot(self.enabled().get(VENDOR), False)
        self.assertIs(self.enabled()["html-plan@agent-stack-vendor-local"], False)

    def test_off_restore_leaves_no_empty_table_and_du_returns_original(self):
        # spec:h5-bo-profile#S4 (review lại fable·high 20/11: trả khóa về như cũ không để lại bảng rỗng)
        self.install(*UI)
        self.local.unlink()
        self.run_profile("on", "ml")
        self.run_profile("on", "giao-dien", user=True)
        self.run_profile("off", "ml")
        self.assertNotIn("enabledPlugins", self.settings())
        self.run_profile("du")
        self.assertEqual(self.settings() if self.local.exists() else {}, {})

    def test_du_ignores_tampered_record_entries_for_core_plugins(self):
        # spec:h5-bo-profile#S4 (review sonnet·xhigh 20/11, TM-166: bản ghi bị sửa không tắt được plugin lõi)
        self.install(VENDOR)
        self.run_profile("on", "ml")
        data = self.settings()
        data["enabledPlugins"]["agent-stack@agent-stack-local"] = True
        self.local.write_text(json.dumps(data))
        for name in self.records():
            path = self.state / "profiles" / name
            rec = json.loads(path.read_text())
            rec["changes"].append({"key": "agent-stack@agent-stack-local", "had": True, "old": False, "set": True})
            path.write_text(json.dumps(rec))
        self.run_profile("du")
        self.assertIs(self.enabled()["agent-stack@agent-stack-local"], True)
