import json
import os
import subprocess
import sys
import time

from tests._util import PLUGIN, TempDirTestCase, git, run_script
from tests.test_agentstack_lib import PLAN

COLLECT = PLUGIN / "skills" / "tien-do" / "scripts" / "collect.py"
sys.path.insert(0, str(COLLECT.parent))
import collect  # noqa: E402

LEARNING = """# Tiến độ: Security whitebox

## Giai đoạn 1: Nền tảng hệ thống
- [x] CS:APP ch. 7–12
- [ ] MIT 6.1810: lab util, syscall
- [ ] Stanford CS144

## Giai đoạn 2: Nền tảng bảo mật
- [ ] Berkeley CS161
"""


def git_dated(cwd, days_ago, *args):
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - days_ago * 86400))
    env = dict(os.environ, GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@e", "-c", "init.defaultBranch=main", *args],
                   cwd=str(cwd), check=True, capture_output=True, env=env)


def age(path, days):
    t = time.time() - days * 86400
    os.utime(path, (t, t))


class TienDo(TempDirTestCase):
    def repo(self, name="proj", plan=PLAN):
        root = self.tmp / name
        root.mkdir()
        (root / "PLAN.md").write_text(plan, encoding="utf-8")
        git(root, "init", "-q")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "init")
        return root

    def tiers(self, data):
        return [a["tier"] for a in data["actions"]]

    def test_old_dirty_file_is_a_blocker_and_ranked_first(self):
        root = self.repo()
        (root / "draft.py").write_text("x = 1\n")
        age(root / "draft.py", 2)
        data = collect.collect(root)
        self.assertEqual(data["actions"][0]["tier"], 1)
        self.assertIn("chưa commit", data["actions"][0]["text"])
        self.assertIn(2, self.tiers(data))  # bước đầu tiên của §0
        self.assertEqual(self.tiers(data), sorted(self.tiers(data)))

    def test_unpushed_commits(self):
        root = self.repo()
        remote = self.tmp / "remote.git"
        git(self.tmp, "init", "-q", "--bare", str(remote))
        git(root, "remote", "add", "origin", str(remote))
        git(root, "push", "-q", "-u", "origin", "main")
        (root / "a.txt").write_text("a\n")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "chưa push")
        data = collect.collect(root)
        self.assertTrue(any(a["text"].startswith("Push 1 commit") for a in data["actions"]))

    def test_recent_todo_counts_but_vendor_is_ignored(self):
        root = self.repo()
        (root / "src").mkdir()
        (root / "src" / "m.py").write_text("def f():\n    pass  # TODO: xử lý lỗi\n")
        (root / "vendor").mkdir()
        (root / "vendor" / "lib.py").write_text("# TODO: của bên thứ ba\n")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "thêm code")
        data = collect.collect(root)
        self.assertEqual([t["file"] for t in data["todos"]], ["src/m.py"])
        self.assertIn(4, self.tiers(data))

    def test_forgotten_project(self):
        root = self.tmp / "old"
        root.mkdir()
        (root / "PLAN.md").write_text(PLAN, encoding="utf-8")
        git(root, "init", "-q")
        git(root, "add", "-A")
        git_dated(root, 30, "commit", "-q", "-m", "cũ")
        age(root / "PLAN.md", 30)
        data = collect.collect(root)
        self.assertEqual(data["actions"][-1]["tier"], 5)

    def test_learning_folder_without_git(self):
        root = self.tmp / "security-whitebox"
        root.mkdir()
        (root / "PROGRESS.md").write_text(LEARNING, encoding="utf-8")
        data = collect.collect(root)
        self.assertFalse(data["git"]["is_repo"])
        self.assertEqual(data["actions"][0]["tier"], 3)
        self.assertIn("MIT 6.1810", data["actions"][0]["text"])
        md = collect.render_md(data)
        self.assertIn("Checkbox: 1/4", md)

    def test_stale_plan_warning_and_unmerged_branch(self):
        root = self.repo()
        age(root / "PLAN.md", 3)
        git(root, "switch", "-q", "-c", "thu-nghiem")
        (root / "b.txt").write_text("b\n")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "nhánh phụ")
        git(root, "switch", "-q", "main")
        (root / "c.txt").write_text("c\n")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "trên main")
        warn = collect.warnings(collect.collect(root))
        self.assertTrue(any("§0 có thể đã cũ" in w for w in warn))
        self.assertTrue(any("thu-nghiem" in w for w in warn))

    def test_merge_conflict_is_detected(self):
        root = self.repo()
        (root / "f.txt").write_text("gốc\n")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "f")
        git(root, "switch", "-q", "-c", "nhanh")
        (root / "f.txt").write_text("bên nhánh\n")
        git(root, "commit", "-qam", "nhánh sửa")
        git(root, "switch", "-q", "main")
        (root / "f.txt").write_text("bên main\n")
        git(root, "commit", "-qam", "main sửa")
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@e", "merge", "nhanh"], cwd=str(root),
                       capture_output=True)
        data = collect.collect(root)
        self.assertIn("xung đột", data["actions"][0]["text"])

    def test_all_mode_and_cli(self):
        self.repo("a")
        b = self.tmp / "b"
        b.mkdir()
        (b / "PROGRESS.md").write_text(LEARNING, encoding="utf-8")
        (self.tmp / "c").mkdir()  # thư mục không có gì
        out = run_script(COLLECT, "--all", str(self.tmp), "--md")
        self.assertEqual(out.returncode, 0, out.stderr)
        for name in ("| a |", "| b |", "| c |", "chưa có kế hoạch"):
            self.assertIn(name, out.stdout)
        out = run_script(COLLECT, "--project", str(self.tmp / "a"), "--json")
        self.assertEqual(json.loads(out.stdout)["project"], "a")

    def test_brief_adds_blocker_and_stays_fast(self):
        root = self.repo()
        (root / "draft.py").write_text("x\n")
        age(root / "draft.py", 2)
        start = time.time()
        info = collect.brief(root)
        self.assertLess(time.time() - start, 2.0)
        self.assertIn("Chặn đường", info["context"])
        self.assertIn("⚠️", info["user"])
        self.assertTrue(info["context"].splitlines()[-1].startswith("Đọc mục §0"))

    def test_todo_in_docs_or_prose_is_ignored(self):
        root = self.repo()
        (root / "NOTES.md").write_text("Bảng: TODO / FIXME là gì\n")
        (root / "run.sh").write_text("echo ok  # FIXME: bỏ cứng đường dẫn\n")
        (root / "rtl.sv").write_text("assign y = a; // TODO: thêm reset\n")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "docs + code")
        files = sorted(t["file"] for t in collect.collect(root)["todos"])
        self.assertEqual(files, ["rtl.sv", "run.sh"])

    def test_goal_hint_has_no_nested_backticks(self):
        root = self.repo()
        hint = collect.goal_hint(collect.collect(root))
        self.assertTrue(hint.startswith("/goal "))
        self.assertNotIn("`", hint)

    def test_todo_inside_string_literal_is_ignored(self):
        self.assertTrue(collect.in_string('x = "a  '))
        self.assertFalse(collect.in_string('print("x")  '))
        root = self.repo()
        (root / "gen.py").write_text('open("f").write("# TODO: không phải chú thích")\nx = 1  # TODO: thật\n')
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "gen")
        todos = collect.collect(root)["todos"]
        self.assertEqual([(t["file"], t["line"]) for t in todos], [("gen.py", 2)])
