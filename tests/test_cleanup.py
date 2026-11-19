"""Việc G mục 2 (19/11/2026): `tools/cleanup.py` dọn rác không dùng model. Mặc định chỉ liệt kê; `--apply` xóa đúng
các mục liệt kê. Không xóa worktree chưa gộp hay còn thay đổi (TM-152), không theo symlink ra ngoài (TM-151), không
đụng transcript `~/.claude/projects` (TM-153). Mọi dữ liệu nằm trong thư mục tạm của test."""
import json
import os
import subprocess
import sys
import time

from tests._util import REPO, TempDirTestCase, git

CLEANUP = REPO / "tools" / "cleanup.py"
OLD = time.time() - 30 * 86400


def age(path, when=OLD):
    """Đặt mtime cũ cho cả cây (không theo symlink)."""
    for dirpath, dirnames, filenames in os.walk(path, followlinks=False):
        for name in dirnames + filenames:
            os.utime(os.path.join(dirpath, name), (when, when), follow_symlinks=False)
    os.utime(path, (when, when), follow_symlinks=False)


class CleanupTests(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.root = self.tmp / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        (self.root / ".gitignore").write_text(".tmp/\n.claude/\nevals/results/\n")
        (self.root / "a.txt").write_text("a\n")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "init")
        wts = self.root / ".claude" / "worktrees"
        wts.mkdir(parents=True)
        # gộp rồi, sạch: được liệt kê
        git(self.root, "worktree", "add", "-q", "-b", "gop", str(wts / "gop"))
        age(wts / "gop")  # cleanup chỉ gỡ worktree không đổi từ --days ngày
        # gộp rồi nhưng còn file sửa chưa commit: giữ
        git(self.root, "worktree", "add", "-q", "-b", "ban", str(wts / "ban"))
        (wts / "ban" / "a.txt").write_text("sửa dở\n")
        # gộp rồi, sạch theo git nhưng có file git bỏ qua (.env): giữ (review sonnet·xhigh 19/11)
        git(self.root, "worktree", "add", "-q", "-b", "bo-qua", str(wts / "bo-qua"))
        (wts / "bo-qua" / ".gitignore").write_text(".env\n")
        git(wts / "bo-qua", "add", ".gitignore")
        git(wts / "bo-qua", "commit", "-q", "-m", "gitignore")
        git(self.root, "merge", "-q", "bo-qua")
        (wts / "bo-qua" / ".env").write_text("SECRET=1\n")
        # có commit chưa gộp vào main: giữ
        git(self.root, "worktree", "add", "-q", "-b", "chua-gop", str(wts / "chua-gop"))
        (wts / "chua-gop" / "b.txt").write_text("b\n")
        git(wts / "chua-gop", "add", "-A")
        git(wts / "chua-gop", "commit", "-q", "-m", "chưa gộp")
        # .tmp: một mục cũ, một mục mới, một symlink cũ trỏ ra ngoài
        self.outside = self.tmp / "ngoai"
        self.outside.mkdir()
        (self.outside / "quy.txt").write_text("đừng xóa\n")
        tmpdir = self.root / ".tmp"
        (tmpdir / "cu").mkdir(parents=True)
        (tmpdir / "cu" / "big.bin").write_bytes(b"x" * 50000)
        (tmpdir / "cu" / "link-ra-ngoai").symlink_to(self.outside)
        age(tmpdir / "cu")
        (tmpdir / "moi").mkdir()
        (tmpdir / "moi" / "f.txt").write_text("mới\n")
        (tmpdir / "link-cu").symlink_to(self.outside)
        os.utime(tmpdir / "link-cu", (OLD, OLD), follow_symlinks=False)
        # evals/results: 4 lần chạy cũ (mỗi lần 2 file), giữ 2 lần mới nhất
        res = self.root / "evals" / "results"
        res.mkdir(parents=True)
        for stamp in ("20261001-100000", "20261002-100000", "20261003-100000", "20261004-100000"):
            (res / f"{stamp}.jsonl").write_text("{}\n")
            (res / f"{stamp}.meta.json").write_text("{}\n")
        age(res)
        os.utime(res, None)
        # scratchpad: một phiên cũ, một phiên mới
        self.scratch = self.tmp / "scratch"
        (self.scratch / "-proj" / "cu-sess" / "scratchpad").mkdir(parents=True)
        (self.scratch / "-proj" / "cu-sess" / "scratchpad" / "n.txt").write_text("n\n")
        age(self.scratch / "-proj" / "cu-sess")
        (self.scratch / "-proj" / "moi-sess" / "scratchpad").mkdir(parents=True)
        # transcript giả trong HOME: không bao giờ bị đụng
        self.transcripts = self.home / ".claude" / "projects" / "-proj"
        self.transcripts.mkdir(parents=True)
        (self.transcripts / "s.jsonl").write_text("{}\n")
        age(self.home / ".claude" / "projects")

    def run_cleanup(self, *args, scratch=None, expect=0):
        env = dict(os.environ, HOME=str(self.home))
        cmd = [sys.executable, str(CLEANUP), "--root", str(self.root), "--days", "7", "--keep-results", "2",
               "--scratch-root", str(scratch or self.scratch), "--json", *args]
        out = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(out.returncode, expect, out.stdout + out.stderr)
        return json.loads(out.stdout)

    def paths(self, report):
        return {os.path.relpath(item["path"], self.tmp) for item in report["items"]}

    def test_list_mode_lists_expected_items_and_deletes_nothing(self):
        report = self.run_cleanup()
        self.assertFalse(report["applied"])
        self.assertEqual(self.paths(report), {
            "repo/.claude/worktrees/gop", "repo/.tmp/cu", "repo/.tmp/link-cu",
            "repo/evals/results/20261001-100000.jsonl", "repo/evals/results/20261001-100000.meta.json",
            "repo/evals/results/20261002-100000.jsonl", "repo/evals/results/20261002-100000.meta.json",
            "scratch/-proj/cu-sess"})
        self.assertGreaterEqual(report["total_bytes"], 50000)
        self.assertEqual(report["total_bytes"], sum(item["bytes"] for item in report["items"]))
        for item in report["items"]:
            self.assertTrue(os.path.lexists(item["path"]), item["path"])
        kept = {os.path.relpath(item["path"], self.tmp): item["why"] for item in report["kept"]}
        self.assertIn("repo/.claude/worktrees/ban", kept)
        self.assertIn("repo/.claude/worktrees/chua-gop", kept)
        self.assertIn("repo/.claude/worktrees/bo-qua", kept)

    def test_text_mode_prints_sizes_and_total(self):
        env = dict(os.environ, HOME=str(self.home))
        out = subprocess.run([sys.executable, str(CLEANUP), "--root", str(self.root), "--days", "7",
                              "--scratch-root", str(self.scratch)], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("CHỈ LIỆT KÊ", out.stdout)
        self.assertIn("Tổng:", out.stdout)
        self.assertIn("--apply", out.stdout)
        self.assertTrue((self.root / ".tmp" / "cu").exists())

    def test_symlink_size_is_not_followed(self):
        report = self.run_cleanup()
        link = next(item for item in report["items"] if item["path"].endswith("link-cu"))
        self.assertLess(link["bytes"], 4096)
        cu = next(item for item in report["items"] if item["path"].endswith(".tmp/cu"))
        self.assertLess(cu["bytes"], 50000 + 64 * 1024)

    def test_apply_removes_only_listed_items_and_never_follows_symlinks(self):
        listed = self.run_cleanup()
        report = self.run_cleanup("--apply")
        self.assertTrue(report["applied"])
        self.assertEqual(report["errors"], [])
        self.assertEqual({os.path.relpath(p, self.tmp) for p in report["removed"]}, self.paths(listed))
        for item in listed["items"]:
            self.assertFalse(os.path.lexists(item["path"]), item["path"])
        # đích của symlink còn nguyên
        self.assertEqual((self.outside / "quy.txt").read_text(), "đừng xóa\n")
        # mục giữ lại còn nguyên
        self.assertTrue((self.root / ".tmp" / "moi" / "f.txt").exists())
        self.assertEqual((self.root / ".claude" / "worktrees" / "ban" / "a.txt").read_text(), "sửa dở\n")
        self.assertTrue((self.root / ".claude" / "worktrees" / "chua-gop" / "b.txt").exists())
        self.assertTrue((self.root / ".claude" / "worktrees" / "bo-qua" / ".env").exists())
        self.assertTrue((self.root / "evals" / "results" / "20261004-100000.jsonl").exists())
        self.assertTrue((self.root / "evals" / "results" / "20261003-100000.meta.json").exists())
        self.assertTrue((self.scratch / "-proj" / "moi-sess").exists())
        self.assertTrue((self.transcripts / "s.jsonl").exists())
        # worktree gỡ bằng git: không còn trong danh sách worktree, nhánh vẫn còn
        listing = git(self.root, "worktree", "list", "--porcelain")
        self.assertNotIn("worktrees/gop\n", listing)
        self.assertIn("gop", git(self.root, "branch", "--list", "gop"))
        # chạy lại: không còn gì để dọn
        self.assertEqual(self.run_cleanup()["items"], [])

    def test_transcripts_are_never_listed(self):
        report = self.run_cleanup(scratch=self.home / ".claude" / "projects")
        self.assertFalse(any(".claude/projects" in item["path"] for item in report["items"]))
        report = self.run_cleanup("--apply", scratch=self.home / ".claude")
        self.assertTrue((self.transcripts / "s.jsonl").exists())

    def test_symlinked_base_directory_is_skipped(self):
        real = self.tmp / "tmp-that"
        real.mkdir()
        (real / "cu").mkdir()
        age(real / "cu")
        import shutil
        shutil.rmtree(self.root / ".tmp")
        (self.root / ".tmp").symlink_to(real)
        report = self.run_cleanup("--apply")
        self.assertTrue((real / "cu").exists())
        self.assertFalse(any(item["path"].startswith(str(self.root / ".tmp")) for item in report["items"]))

    def test_only_filter(self):
        report = self.run_cleanup("--only", "tmp")
        self.assertEqual({item["kind"] for item in report["items"]}, {"tmp"})
