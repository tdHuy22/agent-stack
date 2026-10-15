"""Mod giao diện (plugin/hooks/ui.tsx): tìm binary của app, validate và test mod bằng engine của app."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import unittest

from tests._util import PLUGIN, REPO, TempDirTestCase

sys.path.insert(0, str(REPO / "tools"))
import claude_app  # noqa: E402


class FindAppBinaryTest(TempDirTestCase):
    def make(self, version, build="abc"):
        exe = self.tmp / version / build / claude_app.BINARY
        exe.parent.mkdir(parents=True)
        exe.write_text("")
        return exe

    def test_picks_highest_version_numerically(self):
        self.make("2.1.99")
        newest = self.make("2.1.295")
        self.make("2.1.293")
        self.assertEqual(claude_app.find(self.tmp), ("2.1.295", newest))

    def test_ignores_odd_names_and_missing_binary(self):
        (self.tmp / "2.1.300" / "abc").mkdir(parents=True)  # chưa tải xong, không có binary
        (self.tmp / "latest").mkdir()
        only = self.make("2.1.1")
        self.assertEqual(claude_app.find(self.tmp), ("2.1.1", only))

    def test_nothing_found(self):
        self.assertIsNone(claude_app.find(self.tmp / "khong-co"))
        self.assertIsNone(claude_app.find(self.tmp))


class ManifestTest(unittest.TestCase):
    def test_module_and_contract_are_declared(self):
        hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        self.assertEqual(hooks["modules"], ["./ui.tsx"])
        self.assertTrue((PLUGIN / "hooks" / "ui.tsx").is_file())
        manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertTrue((PLUGIN / manifest["types"]).is_file())

    def test_leaf_code_guard_matches_plan_tree_ids(self):
        # Mẫu kiểm mã trong ui.tsx phải nhận mọi mã plan_tree.py sinh ra (TM-28, TM-30).
        src = (PLUGIN / "hooks" / "ui.tsx").read_text(encoding="utf-8")
        pattern = re.search(r"const CODE = /(.+)/\n", src).group(1)
        for ok in ("T", "T.2", "14", "25.1.2", "C.1", "D.3", "Q.2"):
            self.assertRegex(ok, pattern)
        for bad in ("x; rm", "$(rm)", "T.2 ", "", ".1", "a" * 17):
            self.assertNotRegex(bad, pattern)


@unittest.skipIf(claude_app.find() is None, "máy không có app Claude desktop")
class AppEngineTest(unittest.TestCase):
    """Chạy validate và test của mod bằng chính engine của app (chậm vài giây)."""

    def run_app(self, *args):
        _, exe = claude_app.find()
        return subprocess.run([str(exe), "plugin", *args, str(PLUGIN)], capture_output=True,
                              text=True, timeout=300, cwd=REPO)

    def test_validate_passes_without_engine_complaints(self):
        res = self.run_app("validate")
        out = res.stdout + res.stderr
        self.assertEqual(res.returncode, 0, out)
        self.assertIn("Validation passed", out)
        self.assertNotIn("without .catch", out)

    def test_mod_tests_pass(self):
        res = self.run_app("test")
        out = res.stdout + res.stderr
        self.assertEqual(res.returncode, 0, out)
        self.assertRegex(out, r"\b[1-9]\d* pass\b")
        self.assertRegex(out, r"\b0 fail\b")


if __name__ == "__main__":
    unittest.main()
