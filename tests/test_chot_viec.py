"""Test cho skill chot-viec: script chấm mức rủi ro của thay đổi."""
from __future__ import annotations

import subprocess
import sys
import unittest

from tests._util import PLUGIN, TempDirTestCase

SCRIPTS = PLUGIN / "skills" / "chot-viec" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import risk  # noqa: E402


def change(path, added=1, deleted=0, text=""):
    return {"path": path, "added": added, "deleted": deleted, "text": text}


class Assess(unittest.TestCase):
    def test_docs_only_is_low(self):
        r = risk.assess([change("README.md", 40, 10), change("docs/guide.md", 5)])
        self.assertEqual(r["level"], "thap")
        self.assertEqual(r["hotspots"], [])

    def test_small_code_change_with_test_is_low(self):
        r = risk.assess([change("src/pager.py", 3, 1, "start = (page - 1) * per_page\n"),
                         change("tests/test_pager.py", 6)])
        self.assertEqual(r["level"], "thap")

    def test_code_without_test_is_flagged(self):
        r = risk.assess([change("src/pager.py", 30, 2)])
        self.assertTrue(any("không đổi test" in x for x in r["reasons"]), r["reasons"])

    def test_hook_change_is_hotspot(self):
        r = risk.assess([change("plugin/hooks/router.py", 20, 5), change("tests/test_hooks.py", 10)])
        self.assertIn(r["level"], ("vua", "cao"))
        self.assertEqual(r["hotspots"][0][0], "plugin/hooks/router.py")
        self.assertTrue(any("hook" in x for x in r["hotspots"][0][1]))

    def test_sensitive_path_is_high(self):
        r = risk.assess([change("app/auth/token_store.py", 40, 10)])
        self.assertEqual(r["level"], "cao")

    def test_hardcoded_secret_is_high_even_in_docs(self):
        r = risk.assess([change("notes.md", 1, 0, 'api_key = "sk-live-abcdef123456"\n')])
        self.assertEqual(r["level"], "cao")
        self.assertTrue(any("secret" in x for x in r["reasons"]))

    def test_dangerous_calls_are_reasons(self):
        r = risk.assess([change("tools/clean.py", 5, 0, "subprocess.run(cmd, shell=True)\nshutil.rmtree(p)\n"),
                         change("tests/test_clean.py", 5)])
        self.assertTrue(any("qua shell" in x for x in r["reasons"]), r["reasons"])
        self.assertTrue(any("xóa" in x for x in r["reasons"]), r["reasons"])

    def test_shrinking_tests_is_flagged(self):
        r = risk.assess([change("src/a.py", 2, 2), change("tests/test_a.py", 1, 30)])
        self.assertTrue(any("bớt test" in x for x in r["reasons"]), r["reasons"])

    def test_large_change_raises_level(self):
        small = risk.assess([change("src/a.py", 20), change("tests/test_a.py", 5)])
        big = risk.assess([change("src/a.py", 600), change("tests/test_a.py", 5)])
        self.assertGreater(big["score"], small["score"])
        self.assertTrue(any("lớn" in x for x in big["reasons"]))

    def test_dependency_and_install_files_are_hotspots(self):
        r = risk.assess([change("install.sh", 4, 1), change("requirements.txt", 1)])
        paths = [p for p, _ in r["hotspots"]]
        self.assertIn("install.sh", paths)
        self.assertIn("requirements.txt", paths)

    def test_session_in_path_is_not_sensitive(self):
        r = risk.assess([change("plugin/skills/session-keeper/scripts/receipt.py", 10),
                         change("tests/test_receipt.py", 5)])
        self.assertEqual(r["level"], "thap", r)

    def test_render_has_level_and_review_hint(self):
        out = risk.render(risk.assess([change("app/auth/login.py", 40)]))
        self.assertIn("Mức rủi ro: cao", out)
        self.assertIn("agent-stack:reviewer", out)

    def test_render_empty(self):
        self.assertIn("Không có thay đổi", risk.render(risk.assess([])))


class Collect(TempDirTestCase):
    def git(self, *args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
                       cwd=str(self.tmp), check=True, capture_output=True)

    def test_collects_tracked_and_untracked_changes(self):
        self.git("init", "-q")
        (self.tmp / "a.py").write_text("x = 1\n")
        self.git("add", "a.py")
        self.git("commit", "-q", "-m", "init")
        (self.tmp / "a.py").write_text("x = 2\ny = subprocess.run(c, shell=True)\n")
        (self.tmp / "new.md").write_text("một\nhai\n")
        changes = {c["path"]: c for c in risk.collect(self.tmp)}
        self.assertEqual(set(changes), {"a.py", "new.md"})
        self.assertEqual((changes["a.py"]["added"], changes["a.py"]["deleted"]), (2, 1))
        self.assertIn("shell=True", changes["a.py"]["text"])
        self.assertEqual(changes["new.md"]["added"], 2)

    def test_no_changes(self):
        self.git("init", "-q")
        (self.tmp / "a.py").write_text("x = 1\n")
        self.git("add", "a.py")
        self.git("commit", "-q", "-m", "init")
        self.assertEqual(risk.collect(self.tmp), [])

    def test_repo_without_commits(self):
        self.git("init", "-q")
        (self.tmp / "a.py").write_text("x = 1\n")
        self.assertEqual([c["path"] for c in risk.collect(self.tmp)], ["a.py"])

    def test_staged_then_edited_in_repo_without_commits(self):
        self.git("init", "-q")
        (self.tmp / "a.py").write_text("x = 1\n")
        self.git("add", "a.py")
        (self.tmp / "a.py").write_text("x = 1\nos.system(c)\n")
        changes = risk.collect(self.tmp)
        self.assertEqual([c["path"] for c in changes], ["a.py"])
        self.assertIn("os.system", changes[0]["text"])
        self.assertEqual(changes[0]["added"], 2)

    def test_unknown_base_is_an_error_not_an_empty_diff(self):
        self.git("init", "-q")
        (self.tmp / "a.py").write_text("x = 1\n")
        self.git("add", "a.py")
        self.git("commit", "-q", "-m", "init")
        (self.tmp / "a.py").write_text("x = 2\n")
        with self.assertRaises(risk.GitError):
            risk.collect(self.tmp, "nosuchref")
        out = subprocess.run([sys.executable, str(SCRIPTS / "risk.py"), str(self.tmp), "--base", "nosuchref"],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 2)
        self.assertIn("nosuchref", out.stdout + out.stderr)

    def test_cli_outside_repo_exits_2(self):
        out = subprocess.run([sys.executable, str(SCRIPTS / "risk.py"), str(self.tmp)], capture_output=True, text=True)
        self.assertEqual(out.returncode, 2)
        self.assertIn("git", out.stdout + out.stderr)


if __name__ == "__main__":
    unittest.main()
