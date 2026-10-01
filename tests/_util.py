"""Tiện ích dùng chung cho test. File tạm luôn nằm trong agent-stack/.tmp/."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TMP_ROOT = REPO / ".tmp"
PLUGIN = REPO / "plugin"


class TempDirTestCase(unittest.TestCase):
    """Mỗi test có một thư mục tạm riêng trong .tmp/, tự xóa khi xong."""

    def setUp(self):
        TMP_ROOT.mkdir(exist_ok=True)
        self.tmp = Path(tempfile.mkdtemp(prefix="test-", dir=str(TMP_ROOT)))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def write(self, rel: str, text: str) -> Path:
        path = self.tmp / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


def git(cwd: Path, *args: str) -> str:
    env_args = ["-c", "user.name=test", "-c", "user.email=test@example.com", "-c", "init.defaultBranch=main",
                "-c", "commit.gpgsign=false"]
    out = subprocess.run(["git", *env_args, *args], cwd=str(cwd), check=True,
                         capture_output=True, text=True)
    return out.stdout


def run_script(script: Path, *args: str, stdin: str = "", env: dict = None) -> subprocess.CompletedProcess:
    import os
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    return subprocess.run([sys.executable, str(script), *args], input=stdin, capture_output=True,
                          text=True, env=full_env, timeout=60)


def jsonl(path: Path, rows) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return path
