import subprocess
import sys
import unittest

from tests._util import REPO

sys.path.insert(0, str(REPO / "tools"))
import maintain  # noqa: E402


class Maintain(unittest.TestCase):
    def test_version_parsing(self):
        self.assertEqual(maintain.version_tuple("2.1.267 (Claude Code)"), (2, 1, 267))
        self.assertLess(maintain.version_tuple("2.1.267"), maintain.MIN_CLAUDE)

    def test_drift_detection(self):
        lock = {
            "a/b": {"source": "github:a/b", "ref": "main", "sha": "1" * 40},
            "c/d": {"source": "github:c/d", "ref": "main", "sha": "2" * 40},
            "e/f": {"source": "github:e/f", "ref": "3" * 40, "sha": "3" * 40},
            "local:/x": {"source": "local:/x", "ref": None, "sha": "4"},
        }
        heads = {("a", "b"): "1" * 40, ("c", "d"): "9" * 40}
        drift = maintain.upstream_drift(lock, lambda o, r, ref: heads[(o, r)])
        self.assertEqual([d[0] for d in drift], ["c/d"])

    def test_offline_run_completes(self):
        out = subprocess.run([sys.executable, str(REPO / "tools" / "maintain.py"), "--offline", "--skip-tests"],
                             capture_output=True, text=True, timeout=300)
        self.assertEqual(out.returncode, 0, out.stderr)
        for section in ("## 1.", "## 2.", "## 3.", "## 4.", "## 5.", "## 6."):
            self.assertIn(section, out.stdout)
