"""Test setup script cho cloud session: tải repo (git hay từng file), trỏ ~/.claude, luôn thoát 0."""
from __future__ import annotations

import os
import platform
import subprocess
import unittest
from pathlib import Path

from tests._util import REPO, TempDirTestCase, git

SCRIPT = REPO / "tools" / "cloud_setup.sh"
MANIFEST = REPO / "tools" / "cloud-files.txt"
CORE = {".agent-stack-root": "", "plugin/.claude-plugin/plugin.json": '{"name": "agent-stack"}\n',
        "global/CLAUDE.global.md": "# luật\n", "plugin/hooks/x.py": "print(1)\n"}


class CloudSetupTest(TempDirTestCase):

    def setUp(self):
        super().setUp()
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.dest = self.home / "Documents" / "Claude" / "agent-stack"

    def make_repo(self, files=CORE) -> Path:
        """Repo git giả làm nguồn clone, có danh sách file như repo thật."""
        src = self.tmp / "src"
        for rel, text in files.items():
            self.write(f"src/{rel}", text)
        self.write("src/tools/cloud-files.txt", "# chú thích\n" + "\n".join(files) + "\n")
        git(src, "init", "-q")
        git(src, "add", "-A")
        git(src, "commit", "-qm", "c1")
        return src

    def make_raw(self, files=CORE, manifest=None) -> Path:
        """Thư mục giả lập raw.githubusercontent.com/<owner>/<repo>, nhánh main."""
        raw = self.tmp / "raw"
        for rel, text in files.items():
            self.write(f"raw/main/{rel}", text)
        lines = manifest if manifest is not None else list(files)
        self.write("raw/main/tools/cloud-files.txt", "\n".join(lines) + "\n")
        return raw

    def run_setup(self, repo_url="file:///nonexistent/repo.git", raw_base="file:///nonexistent/raw", force=True,
                  ref="main"):
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home), "AGENT_STACK_REPO_URL": repo_url,
               "AGENT_STACK_RAW_BASE": raw_base, "AGENT_STACK_REF": ref, "GIT_CEILING_DIRECTORIES": str(self.tmp)}
        if force:
            env["AGENT_STACK_SETUP_FORCE"] = "1"
        return subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=120)

    def assert_linked(self):
        claude_md = self.home / ".claude" / "CLAUDE.md"
        self.assertTrue(claude_md.is_symlink())
        self.assertEqual(claude_md.resolve(), (self.dest / "global" / "CLAUDE.global.md").resolve())
        plugin = self.home / ".claude" / "skills" / "agent-stack"
        self.assertEqual(plugin.resolve(), (self.dest / "plugin").resolve())

    def test_clone_then_links_rules_and_plugin(self):
        src = self.make_repo()
        out = self.run_setup(repo_url=f"file://{src}")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue((self.dest / ".git").is_dir())
        self.assertTrue((self.dest / "plugin" / "hooks" / "x.py").is_file())
        self.assert_linked()

    def test_second_run_pulls_new_commit_and_keeps_state(self):
        src = self.make_repo()
        self.run_setup(repo_url=f"file://{src}")
        (self.dest / "state").mkdir()
        (self.dest / "state" / "events.jsonl").write_text("{}\n", encoding="utf-8")
        self.write("src/global/CLAUDE.global.md", "# luật mới\n")
        git(src, "commit", "-qam", "c2")
        out = self.run_setup(repo_url=f"file://{src}")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual((self.dest / "global" / "CLAUDE.global.md").read_text(encoding="utf-8"), "# luật mới\n")
        self.assertTrue((self.dest / "state" / "events.jsonl").is_file())

    def test_falls_back_to_raw_files_when_clone_fails(self):
        raw = self.make_raw()
        out = self.run_setup(raw_base=f"file://{raw}")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("đã tải 4 file", out.stdout)
        self.assertTrue((self.dest / "plugin" / "hooks" / "x.py").is_file())
        self.assertTrue(os.access(self.dest / "plugin" / "hooks" / "x.py", os.X_OK))
        self.assert_linked()

    def test_raw_reinstall_keeps_state(self):
        raw = self.make_raw()
        self.run_setup(raw_base=f"file://{raw}")
        (self.dest / "state").mkdir()
        (self.dest / "state" / "events.jsonl").write_text("{}\n", encoding="utf-8")
        self.write("raw/main/global/CLAUDE.global.md", "# luật mới\n")
        out = self.run_setup(raw_base=f"file://{raw}")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual((self.dest / "global" / "CLAUDE.global.md").read_text(encoding="utf-8"), "# luật mới\n")
        self.assertTrue((self.dest / "state" / "events.jsonl").is_file())
        self.assertFalse(Path(f"{self.dest}.old").exists())

    def test_ref_can_pin_full_commit_sha(self):
        src = self.make_repo()
        sha = git(src, "rev-parse", "HEAD").strip()
        self.write("src/global/CLAUDE.global.md", "# luật mới\n")
        git(src, "commit", "-qam", "c2")
        out = self.run_setup(repo_url=f"file://{src}", ref=sha)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue((self.dest / ".git").is_dir())
        self.assertEqual((self.dest / "global" / "CLAUDE.global.md").read_text(encoding="utf-8"), "# luật\n")

    def test_unsafe_manifest_line_aborts_raw_download(self):
        for bad in ["../evil", "/etc/evil", "plugin/../../evil", "tools/run.sh", "plugin//x", "plugin/a b"]:
            with self.subTest(bad=bad):
                raw = self.make_raw(manifest=[*CORE, bad])
                out = self.run_setup(raw_base=f"file://{raw}")
                self.assertEqual(out.returncode, 0)
                self.assertIn("không hợp lệ", out.stdout)
                self.assertFalse(self.dest.exists())
                self.assertFalse((self.home / ".claude").exists())
                self.assertFalse((self.tmp / "evil").exists())

    def test_missing_core_file_is_not_installed(self):
        files = {k: v for k, v in CORE.items() if k != "global/CLAUDE.global.md"}
        raw = self.make_raw(files=files)
        out = self.run_setup(raw_base=f"file://{raw}")
        self.assertEqual(out.returncode, 0)
        self.assertFalse(self.dest.exists())
        self.assertFalse((self.home / ".claude").exists())
        self.assertEqual([p.name for p in self.dest.parent.iterdir()], [])

    def test_failed_update_keeps_existing_copy(self):
        src = self.make_repo()
        self.run_setup(repo_url=f"file://{src}")
        out = self.run_setup()
        self.assertEqual(out.returncode, 0)
        self.assertIn("dùng bản đã có", out.stdout)
        self.assertTrue((self.dest / "plugin" / "hooks" / "x.py").is_file())
        self.assert_linked()

    def test_nothing_reachable_still_exits_zero(self):
        out = self.run_setup()
        self.assertEqual(out.returncode, 0)
        self.assertIn("không tải được agent-stack", out.stdout)
        self.assertFalse((self.home / ".claude").exists())

    def test_existing_claude_md_is_backed_up(self):
        src = self.make_repo()
        self.write("home/.claude/CLAUDE.md", "luật riêng\n")
        out = self.run_setup(repo_url=f"file://{src}")
        self.assertEqual(out.returncode, 0)
        backups = list((self.home / ".claude").glob("CLAUDE.md.bak-*"))
        self.assertEqual([b.read_text(encoding="utf-8") for b in backups], ["luật riêng\n"])
        self.assert_linked()

    @unittest.skipUnless(platform.system() == "Darwin", "chỉ chặn trên macOS")
    def test_refuses_on_mac_without_force(self):
        src = self.make_repo()
        out = self.run_setup(repo_url=f"file://{src}", force=False)
        self.assertEqual(out.returncode, 0)
        self.assertIn("install.sh", out.stdout)
        self.assertFalse(self.dest.exists())
        self.assertFalse((self.home / ".claude").exists())


class CloudManifestTest(unittest.TestCase):

    def test_manifest_matches_tracked_files(self):
        listed = [line for line in MANIFEST.read_text(encoding="utf-8").splitlines()
                  if line and not line.startswith("#")]
        cmd = next(line for line in MANIFEST.read_text(encoding="utf-8").splitlines()
                   if line.startswith("# Tạo lại: ")).removeprefix("# Tạo lại: ").split()
        tracked = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True, check=True).stdout.split()
        self.assertEqual(listed, tracked, "danh sách lệch: chạy lại lệnh ở dòng '# Tạo lại' của tools/cloud-files.txt")

    def test_manifest_has_core_files(self):
        listed = MANIFEST.read_text(encoding="utf-8").splitlines()
        for core in CORE:
            if core != "plugin/hooks/x.py":
                self.assertIn(core, listed)


if __name__ == "__main__":
    unittest.main()
