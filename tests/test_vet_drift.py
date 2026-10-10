import json
import sys

from tests._util import PLUGIN, TempDirTestCase, run_script

SCRIPTS = PLUGIN / "skills" / "vet-skill" / "scripts"
VET = SCRIPTS / "vet.py"
sys.path.insert(0, str(SCRIPTS))
import drift  # noqa: E402

KEY = "acme/plugins:plugins/demo"
STEM = "acme__plugins__plugins-demo@abc123abc123"


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def install(plugins, pid, path):
    f = plugins / "installed_plugins.json"
    data = json.loads(f.read_text()) if f.exists() else {"version": 2, "plugins": {}}
    data["plugins"][pid] = [{"scope": "user", "installPath": str(path), "version": "1.0.0"}]
    write_json(f, data)


def make_fixture(tmp):
    """Một agent-stack giả (catalog, vetted.lock, .vet-cache) và một bản cài giống hệt bản đã kiểm.
    Trả về (home, plugins_dir, thư mục cài)."""
    home, plugins = tmp / "stack", tmp / "plugins"
    (home / ".agent-stack-root").parent.mkdir(parents=True, exist_ok=True)
    (home / ".agent-stack-root").write_text("")
    snap = home / ".vet-cache" / STEM / "plugins" / "demo"
    (snap / "skills").mkdir(parents=True)
    (snap / "README.md").write_text("đọc tôi\n")
    (snap / "skills" / "SKILL.md").write_text("---\nname: demo\n---\n")
    (home / ".vet-cache" / STEM / ".vet-complete").write_text("abc\n")
    write_json(home / "catalog.json", {"version": 1, "items": [
        {"key": KEY, "kind": "claude-plugin", "scope": "user",
         "install": {"marketplace": "mk", "plugin": "demo"}, "why": "thử"}]})
    write_json(home / "vetted.lock", {"version": 1, "entries": {KEY: {
        "sha": "abc123abc123" + "0" * 28, "subpath": "plugins/demo", "verdict": "PASS",
        "report": f"vet-reports/{STEM}.md", "human_review": {"status": "approved"}}}})
    installed = plugins / "cache" / "mk" / "demo" / "1.0.0"
    (installed / "skills").mkdir(parents=True)
    (installed / "README.md").write_text("đọc tôi\n")
    (installed / "skills" / "SKILL.md").write_text("---\nname: demo\n---\n")
    # Dấu vết của Claude Code, không phải nội dung plugin.
    (installed / ".in_use").mkdir()
    (installed / ".in_use" / "123").write_text("")
    (installed / ".orphaned_at").write_text("1")
    install(plugins, "demo@mk", installed)
    return home, plugins, installed


class DriftCheck(TempDirTestCase):
    """So file plugin đã cài với bản đã kiểm trong .vet-cache."""

    def setUp(self):
        super().setUp()
        self.home, self.plugins, self.installed = make_fixture(self.tmp)

    def write_json(self, path, data):
        write_json(path, data)

    def install(self, pid, path):
        install(self.plugins, pid, path)

    def run_cli(self, *args):
        return run_script(VET, "drift", "--plugins-dir", str(self.plugins), *args,
                          env={"AGENT_STACK_HOME": str(self.home)})

    def result(self, pid="demo@mk"):
        return {r["plugin"]: r for r in drift.check(self.home, self.plugins)}[pid]

    def test_identical_copy_matches_and_quiet_prints_nothing(self):
        self.assertEqual(self.result()["status"], "match")
        out = self.run_cli("--quiet")
        self.assertEqual((out.returncode, out.stdout, out.stderr), (0, "", ""))

    def test_changed_added_removed_files_are_drift(self):
        (self.installed / "README.md").write_text("đã đổi\n")
        (self.installed / "hooks.json").write_text("{}")
        (self.installed / "skills" / "SKILL.md").unlink()
        r = self.result()
        self.assertEqual(r["status"], "drift")
        self.assertEqual((r["changed"], r["added"], r["removed"]),
                         (["README.md"], ["hooks.json"], ["skills/SKILL.md"]))
        out = self.run_cli("--quiet")
        self.assertEqual(out.returncode, 1)
        self.assertIn("demo@mk", out.stdout)
        self.assertIn("hooks.json", out.stdout)

    def patch_readme(self, digest):
        lock = json.loads((self.home / "vetted.lock").read_text())
        lock["entries"][KEY]["local_patches"] = [{"path": "patches/demo/fix.patch", "sha256": "x",
                                                  "files": {"README.md": digest}}]
        self.write_json(self.home / "vetted.lock", lock)

    def test_approved_patch_matches_only_the_recorded_digest(self):
        import hashlib
        (self.installed / "README.md").write_text("đã vá\n")
        self.assertEqual(self.result()["status"], "drift")  # chưa ghi bản vá trong lock: là lệch
        self.patch_readme(hashlib.sha256("đã vá\n".encode()).hexdigest())
        self.assertEqual(self.result()["status"], "match")
        # Bản cài chưa vá (đúng bản đã kiểm) hay bị sửa thêm sau khi vá đều là lệch.
        (self.installed / "README.md").write_text("đọc tôi\n")
        self.assertEqual(self.result()["changed"], ["README.md"])
        (self.installed / "README.md").write_text("đã vá, rồi sửa thêm\n")
        self.assertEqual(self.result()["status"], "drift")
        # Bản vá xóa file: thiếu file đó là khớp, còn file đó là thừa.
        self.patch_readme(None)
        (self.installed / "README.md").unlink()
        self.assertEqual(self.result()["status"], "match")
        (self.installed / "README.md").write_text("đọc tôi\n")
        self.assertEqual(self.result()["added"], ["README.md"])

    def test_malformed_local_patches_flag_that_plugin_without_breaking_the_check(self):
        lock = json.loads((self.home / "vetted.lock").read_text())
        for bad in ({"files": {}}, ["x"], [{"files": ["README.md"]}], [{"files": {"README.md": "ngắn"}}]):
            lock["entries"][KEY]["local_patches"] = bad
            self.write_json(self.home / "vetted.lock", lock)
            self.assertEqual(self.result()["status"], "bad-lock", bad)
        out = self.run_cli("--quiet")
        self.assertEqual(out.returncode, 1)
        self.assertIn("sai dạng", out.stdout)

    def test_plugin_missing_from_catalog_is_unvetted(self):
        other = self.plugins / "cache" / "mk" / "other" / "2"
        other.mkdir(parents=True)
        self.install("other@mk", other)
        self.assertEqual(self.result("other@mk")["status"], "unvetted")
        self.assertEqual(self.run_cli("--quiet").returncode, 1)

    def test_own_marketplaces_are_skipped(self):
        own = self.plugins / "cache" / "agent-stack-local" / "agent-stack" / "0.1"
        own.mkdir(parents=True)
        self.install("agent-stack@agent-stack-local", own)
        self.assertEqual(self.result("agent-stack@agent-stack-local")["status"], "own")
        self.assertEqual(self.run_cli("--quiet").returncode, 0)

    def test_vendored_plugin_in_own_marketplace_is_still_checked(self):
        catalog = json.loads((self.home / "catalog.json").read_text())
        catalog["items"][0].update(kind="vendor-plugin", install={"marketplace": "agent-stack-vendor-local", "plugin": "demo"})
        self.write_json(self.home / "catalog.json", catalog)
        self.install("demo@agent-stack-vendor-local", self.installed)
        self.assertEqual(self.result("demo@agent-stack-vendor-local")["status"], "match")
        (self.installed / "README.md").write_text("đã đổi\n")
        self.assertEqual(self.result("demo@agent-stack-vendor-local")["status"], "drift",
                         "plugin bên thứ ba trong vendor/ không được coi là của agent-stack")
        bundle = self.plugins / "cache" / "agent-stack-vendor-local" / "agent-stack-vendor" / "1"
        bundle.mkdir(parents=True)
        self.install("agent-stack-vendor@agent-stack-vendor-local", bundle)
        self.assertEqual(self.result("agent-stack-vendor@agent-stack-vendor-local")["status"], "own")
        stray = self.plugins / "cache" / "agent-stack-vendor-local" / "da-go-khoi-catalog" / "1"
        stray.mkdir(parents=True)
        self.install("da-go-khoi-catalog@agent-stack-vendor-local", stray)
        self.assertEqual(self.result("da-go-khoi-catalog@agent-stack-vendor-local")["status"], "unvetted",
                         "plugin bên thứ ba bị xóa khỏi catalog mà chưa gỡ thì vẫn phải bị báo")

    def test_missing_snapshot_and_unapproved_entry_are_reported(self):
        import shutil
        shutil.rmtree(self.home / ".vet-cache")
        self.assertEqual(self.result()["status"], "no-snapshot")
        lock = json.loads((self.home / "vetted.lock").read_text())
        lock["entries"][KEY]["human_review"] = {"status": "pending"}
        self.write_json(self.home / "vetted.lock", lock)
        self.assertEqual(self.result()["status"], "unapproved")

    def test_missing_install_path_is_reported(self):
        import shutil
        shutil.rmtree(self.installed)
        self.assertEqual(self.result()["status"], "missing")

    def test_no_installed_plugins_file_is_ok(self):
        (self.plugins / "installed_plugins.json").unlink()
        self.assertEqual(drift.check(self.home, self.plugins), [])
        self.assertEqual(self.run_cli("--quiet").returncode, 0)

    def test_json_output(self):
        out = self.run_cli("--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        rows = json.loads(out.stdout)
        self.assertEqual([(r["plugin"], r["status"], r["key"]) for r in rows], [("demo@mk", "match", KEY)])


if __name__ == "__main__":
    import unittest
    unittest.main()
