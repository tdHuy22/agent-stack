"""Test plugin/hooks/cloud_update.py: tự kéo bản agent-stack mới trên cloud (TM-43 đến TM-46)."""
import importlib.util
import os
import time
import unittest
from pathlib import Path

from tests._util import PLUGIN, TempDirTestCase, git, run_script

spec = importlib.util.spec_from_file_location("cloud_update", PLUGIN / "hooks" / "cloud_update.py")
cu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cu)

CLOUD = {"CLAUDE_CODE_REMOTE": "true"}


class OnCloudTest(unittest.TestCase):
    def test_only_remote_linux(self):
        self.assertTrue(cu.on_cloud(CLOUD, "linux"))
        self.assertFalse(cu.on_cloud(CLOUD, "darwin"))  # bản dev trên Mac không bao giờ bị reset
        self.assertFalse(cu.on_cloud({}, "linux"))
        self.assertFalse(cu.on_cloud({"CLAUDE_CODE_REMOTE": "1"}, "linux"))


class CloudCase(TempDirTestCase):
    def setUp(self):
        super().setUp()
        old = os.environ.get("AGENT_STACK_STATE")
        os.environ["AGENT_STACK_STATE"] = str(self.tmp / "state")
        self.addCleanup(lambda: os.environ.pop("AGENT_STACK_STATE") if old is None
                        else os.environ.__setitem__("AGENT_STACK_STATE", old))
        # Tên kết thúc bằng .git như URL thật: git ghi URL vào FETCH_HEAD không kèm .git (lỗi bản đầu chỉ lộ ra
        # khi chạy với URL GitHub thật). Hai commit để fetch --depth 1 tạo .git/shallow như trên cloud.
        self.src = self.tmp / "src.git"
        self.src.mkdir()
        git(self.src, "init", "-q")
        self.commit("v0")
        for name in cu.CORE_FILES:
            self.write(f"src.git/{name}", "x\n")
        self.commit("v1")
        self.url = f"file://{self.src}"
        old_url = cu.REPO_URL
        cu.REPO_URL = self.url
        self.addCleanup(setattr, cu, "REPO_URL", old_url)
        self.home = self.tmp / "home"

    def commit(self, msg: str) -> str:
        git(self.src, "add", "-A")
        git(self.src, "commit", "-q", "--allow-empty", "-m", msg)
        return git(self.src, "rev-parse", "HEAD").strip()

    def install(self, ref: str = "main"):
        """Như install_repo của tools/cloud_setup.sh: init + fetch --depth 1 + checkout FETCH_HEAD."""
        git(self.tmp, "init", "-q", str(self.home))
        git(self.home, "remote", "add", "origin", self.url)
        git(self.home, "fetch", "-q", "--depth", "1", "origin", ref)
        git(self.home, "checkout", "-q", "FETCH_HEAD")

    def head(self) -> str:
        return git(self.home, "rev-parse", "HEAD").strip()


class UpdateTest(CloudCase):
    def test_pulls_new_commit_then_reports_current(self):
        self.install()
        self.write("src.git/plugin/new.txt", "moi\n")
        new = self.commit("v2")
        self.assertEqual(cu.run(self.home), "da-cap-nhat")
        self.assertEqual(self.head(), new)
        self.assertTrue((self.home / "plugin" / "new.txt").exists())
        self.assertEqual(cu.run(self.home), "da-moi-nhat")
        state = cu.A.read_json(cu.A.state_dir() / cu.STATE_NAME)
        self.assertEqual(state["result"], "da-moi-nhat")
        self.assertEqual(state["head"], new[:len(state["head"])])

    def test_fetch_head_url_without_dot_git_still_tracks_branch(self):
        self.install()
        self.assertNotIn(".git\n", (self.home / ".git" / "FETCH_HEAD").read_text(encoding="utf-8"))
        self.assertEqual(cu.tracked_branch(self.home), "main")

    def test_same_repo(self):
        url = "https://github.com/tdHuy22/agent-stack.git"
        self.assertTrue(cu.same_repo("https://github.com/tdHuy22/agent-stack", url))
        self.assertTrue(cu.same_repo("https://github.com/tdHuy22/agent-stack/\n", url))
        self.assertFalse(cu.same_repo("https://github.com/tdHuy22/agent-stack-x", url))
        self.assertFalse(cu.same_repo("", url))

    def test_dev_checkout_with_unpushed_commit_is_left_alone(self):
        """Bản như trên Mac: clone đầy đủ, HEAD gắn nhánh main, có commit chưa push (TM-44)."""
        git(self.tmp, "clone", "-q", self.url, str(self.home))
        self.write("home/note.txt", "chưa push\n")
        git(self.home, "add", "note.txt")
        git(self.home, "commit", "-q", "-m", "local")
        local = self.head()
        git(self.home, "fetch", "-q", "origin", "main")
        self.commit("v2")
        self.assertEqual(cu.run(self.home), "khong-phai-ban-cloud")
        self.assertEqual(git(self.home, "rev-parse", "main").strip(), local)

    def test_run_entry_point_does_nothing_off_cloud(self):
        self.install()
        old = self.head()
        self.commit("v2")
        env = {"CLAUDE_CODE_REMOTE": "", "AGENT_STACK_STATE": str(self.tmp / "state")}
        result = run_script(PLUGIN / "hooks" / "cloud_update.py", "--run", str(self.home), env=env)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.head(), old)
        self.assertFalse((self.tmp / "state" / cu.STATE_NAME).exists())

    def test_stale_git_lock_is_cleared(self):
        self.install()
        lock = self.home / ".git" / "shallow.lock"
        lock.write_text("", encoding="utf-8")
        old = time.time() - cu.LOCK_STALE - 5
        os.utime(lock, (old, old))
        new = self.commit("v2")
        self.assertEqual(cu.run(self.home), "da-cap-nhat")
        self.assertEqual(self.head(), new)
        self.assertFalse(lock.exists())

    def test_reset_leaving_missing_core_files_rolls_back(self):
        self.install()
        old = self.head()
        self.commit("v2")
        real = cu.has_core
        cu.has_core = lambda home: False
        self.addCleanup(setattr, cu, "has_core", real)
        self.assertEqual(cu.run(self.home), "reset-do")
        self.assertEqual(self.head(), old)

    def test_pinned_sha_is_left_alone(self):
        pinned = git(self.src, "rev-parse", "HEAD").strip()
        self.install(pinned)
        self.commit("v2")
        self.assertEqual(cu.run(self.home), "ghim")
        self.assertEqual(self.head(), pinned)

    def test_local_edits_block_update(self):
        self.install()
        old = self.head()
        (self.home / "global" / "CLAUDE.global.md").write_text("sửa tay\n", encoding="utf-8")
        self.commit("v2")
        self.assertEqual(cu.run(self.home), "co-sua")
        self.assertEqual(self.head(), old)
        self.assertEqual((self.home / "global" / "CLAUDE.global.md").read_text(encoding="utf-8"), "sửa tay\n")

    def test_other_origin_is_refused(self):
        self.install()
        old = self.head()
        self.commit("v2")
        cu.REPO_URL = "https://github.com/someone/else.git"
        self.assertEqual(cu.run(self.home), "origin-khac")
        self.assertEqual(self.head(), old)

    def test_commit_missing_core_file_is_refused(self):
        self.install()
        old = self.head()
        (self.src / "plugin" / ".claude-plugin" / "plugin.json").unlink()
        self.commit("hỏng")
        self.assertEqual(cu.run(self.home), "thieu-file")
        self.assertEqual(self.head(), old)

    def test_fetch_failure_keeps_old(self):
        self.install()
        old = self.head()
        cu.REPO_URL = f"file://{self.tmp / 'missing'}"
        git(self.home, "remote", "set-url", "origin", cu.REPO_URL)
        (self.home / ".git" / "FETCH_HEAD").write_text(
            f"{old}\t\tbranch 'main' of {cu.REPO_URL}\n", encoding="utf-8")
        self.assertEqual(cu.run(self.home), "fetch-loi")
        self.assertEqual(self.head(), old)

    def test_failed_fetch_does_not_disable_later_updates(self):
        """git fetch xoá trắng FETCH_HEAD khi bắt đầu; lỗi mạng một lần không được làm các lần sau thành "ghim"."""
        self.install()
        self.assertEqual(cu.run(self.home), "da-moi-nhat")  # lần thường: nhớ nhánh vào config
        away = self.tmp / "away.git"
        self.src.rename(away)
        self.assertEqual(cu.run(self.home), "fetch-loi")
        self.assertEqual((self.home / ".git" / "FETCH_HEAD").read_text(encoding="utf-8"), "")
        away.rename(self.src)
        new = self.commit("v2")
        self.assertEqual(cu.run(self.home), "da-cap-nhat")
        self.assertEqual(self.head(), new)

    def test_shallow_clone_on_a_branch_is_left_alone(self):
        self.install()
        git(self.home, "checkout", "-q", "-b", "main")
        old = self.head()
        self.commit("v2")
        self.assertEqual(cu.run(self.home), "khong-phai-ban-cloud")
        self.assertEqual(self.head(), old)

    def test_fresh_lock_blocks_and_stale_lock_is_taken(self):
        self.install()
        lock = cu.A.state_dir() / "cloud-update.lock"
        lock.write_text("", encoding="utf-8")
        self.assertEqual(cu.run(self.home), "dang-chay")
        old = time.time() - cu.LOCK_STALE - 5
        os.utime(lock, (old, old))
        self.assertEqual(cu.run(self.home), "da-moi-nhat")
        self.assertFalse(lock.exists())


class MaybeStartTest(CloudCase):
    def start(self, now, env=CLOUD, platform="linux"):
        calls = []
        started = cu.maybe_start(self.home, now=now, env=env, platform=platform, spawn=calls.append)
        return started, calls

    def test_spawns_at_most_once_per_interval(self):
        self.install()
        started, calls = self.start(1000.0)
        self.assertTrue(started)
        self.assertEqual(calls[0][-2:], ["--run", str(self.home)])
        self.assertEqual(self.start(1000.0 + cu.INTERVAL - 1), (False, []))
        self.assertTrue(self.start(1000.0 + cu.INTERVAL)[0])

    def test_future_stamp_does_not_block(self):
        self.install()
        self.start(5000.0)
        self.assertTrue(self.start(1000.0)[0])

    def test_refuses_off_cloud_or_without_git(self):
        self.assertEqual(self.start(1000.0), (False, []))  # chưa có bản clone git
        self.install()
        self.assertEqual(self.start(1000.0, platform="darwin"), (False, []))
        self.assertEqual(self.start(1000.0, env={}), (False, []))
        self.assertEqual(self.start(1000.0, env=dict(CLOUD, AGENT_STACK_NO_BACKGROUND="1")), (False, []))
        self.assertFalse((cu.A.state_dir() / cu.STATE_NAME).exists())


class SessionStartHookTest(TempDirTestCase):
    def test_hook_still_runs_on_cloud(self):
        """Hook SessionStart ở cloud vẫn thoát 0 và không in lỗi khi có bước tự kéo (test đặt NO_BACKGROUND)."""
        project = self.tmp / "p"
        project.mkdir()
        result = run_script(PLUGIN / "hooks" / "session_start.py",
                            stdin='{"session_id": "s1", "source": "startup", "cwd": "%s"}' % project,
                            env=dict(CLOUD, AGENT_STACK_STATE=str(self.tmp / "state")))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertFalse((self.tmp / "state" / cu.STATE_NAME).exists())


if __name__ == "__main__":
    unittest.main()
