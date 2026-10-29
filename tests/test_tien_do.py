import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from tests._util import PLUGIN, TMP_ROOT, TempDirTestCase, git, run_script
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


class IsolatedState(TempDirTestCase):
    """Mỗi test có state/ riêng qua AGENT_STACK_STATE, để không chạm vào state/ thật của repo.
    Thư mục state nằm cạnh self.tmp (không nằm trong đó) nên `--all self.tmp` không quét nhầm nó."""

    def setUp(self):
        super().setUp()
        self.state = Path(tempfile.mkdtemp(prefix="state-", dir=str(TMP_ROOT)))
        self.addCleanup(shutil.rmtree, self.state, ignore_errors=True)
        old = os.environ.get("AGENT_STACK_STATE")
        os.environ["AGENT_STACK_STATE"] = str(self.state)
        self.addCleanup(lambda: os.environ.pop("AGENT_STACK_STATE", None) if old is None
                        else os.environ.__setitem__("AGENT_STACK_STATE", old))


class TienDo(IsolatedState):
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


# ---------------------------------------------------------------- "Đổi từ lần trước" (snapshot)

TRACK_PLAN = """# PLAN: dự án thử

## 0. Đang ở đâu, việc tiếp theo
*Cập nhật 01/10/2026.*

- **Xong:**
  - Dựng khung repo và CI.
  - Viết bộ test nền.
- **Đang dở:** Viết bộ lọc dữ liệu đầu vào.
- **Việc tiếp theo, theo thứ tự:**
  1. Thêm bộ nhớ đệm cho truy vấn nặng.
  2. Viết tài liệu cài đặt.

## 1. Giai đoạn

### GĐ1: Nền tảng
- [x] Dựng khung repo
- [ ] Viết bộ lọc dữ liệu đầu vào
- [ ] Đo hiệu năng cơ sở

### GĐ2: Mở rộng
- [ ] Thêm API công khai
"""


def snap(**kw):
    """Snapshot giả đúng định dạng, để thử riêng hàm so sánh."""
    base = {"v": 1, "root": "/x", "ts": 100.0, "head": None, "branch": None, "plan": "PLAN.md", "phase": None,
            "checkbox": {"done": 0, "total": 0}, "section0": {"done": 0, "in_progress": 0, "next": 0},
            "open": [], "done": []}
    base.update(kw)
    return base


class SnapshotCase(IsolatedState):
    def project(self, name="proj", plan=TRACK_PLAN, parent=None):
        root = (parent or self.tmp) / name
        root.mkdir(parents=True)
        (root / "PLAN.md").write_text(plan, encoding="utf-8")
        git(root, "init", "-q")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "init")
        return root

    def report(self, root, *flags):
        """Chạy collect.main trong tiến trình này, trả về stdout."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = collect.main(["--project", str(root), *flags])
        self.assertEqual(code, 0)
        return buf.getvalue()

    def edit(self, root, old, new):
        path = root / "PLAN.md"
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def commit(self, root, message):
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", message)

    def snapshot_files(self):
        folder = self.state / "tien-do"
        return sorted(folder.glob("*.json")) if folder.is_dir() else []

    def age_snapshot(self, root, hours):
        path = collect.snapshot_path(root)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["ts"] = time.time() - hours * 3600
        path.write_text(json.dumps(data), encoding="utf-8")
        return data["ts"]

    def section(self, out):
        """Các dòng không rỗng của mục "Đổi từ lần trước" (từ tiêu đề tới tiêu đề kế tiếp)."""
        lines = out.splitlines()
        start = next(i for i, ln in enumerate(lines) if ln.startswith("### Đổi từ lần trước"))
        end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("###")), len(lines))
        return [ln for ln in lines[start:end] if ln.strip()]

    def make_changes(self, root):
        """Một đợt thay đổi đủ bốn loại: tick (kèm đuôi), gạch bước, thêm bước, xóa việc, thêm mục Xong, commit."""
        self.edit(root, "- [ ] Viết bộ lọc dữ liệu đầu vào", "- [x] Viết bộ lọc dữ liệu đầu vào. Xong 02/10/2026")
        self.edit(root, "- [ ] Đo hiệu năng cơ sở\n", "")
        self.edit(root, "1. Thêm bộ nhớ đệm cho truy vấn nặng.", "1. ~~Thêm bộ nhớ đệm cho truy vấn nặng~~ Xong 02/10/2026.")
        self.edit(root, "  2. Viết tài liệu cài đặt.\n", "  2. Viết tài liệu cài đặt.\n  3. Chạy thử trên dữ liệu thật.\n")
        self.edit(root, "- **Đang dở:** Viết bộ lọc dữ liệu đầu vào.", "- **Đang dở:** không có.")
        self.edit(root, "  - Viết bộ test nền.\n", "  - Viết bộ test nền.\n  - Cài xong bộ nhớ đệm.\n")
        self.commit(root, "Thêm bộ nhớ đệm")


class SnapshotContent(SnapshotCase):
    def test_snapshot_keeps_small_comparable_facts(self):
        root = self.project()
        self.report(root)
        files = self.snapshot_files()
        self.assertEqual(len(files), 1)
        self.assertLess(files[0].stat().st_size, 8000)  # snapshot nhỏ
        snapshot = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertEqual(snapshot["root"], os.path.realpath(str(root)))
        self.assertEqual(snapshot["head"], git(root, "rev-parse", "--short", "HEAD").strip())
        self.assertEqual(snapshot["branch"], "main")
        self.assertEqual(snapshot["plan"], "PLAN.md")
        self.assertEqual(snapshot["phase"]["title"], "GĐ1: Nền tảng")
        self.assertEqual(snapshot["section0"], {"done": 2, "in_progress": 1, "next": 2})
        self.assertEqual(len(snapshot["open"]), 6)  # 3 ô chưa tick + đang dở + 2 bước
        self.assertEqual(len(snapshot["done"]), 3)  # 1 ô đã tick + 2 mục Xong
        self.assertIn("Đo hiệu năng cơ sở", snapshot["open"])
        self.assertIn("Viết bộ test nền.", snapshot["done"])

    def test_one_file_per_project_keyed_by_normalized_absolute_path(self):
        a, b = self.project("a"), self.project("b")
        link = self.tmp / "lien-ket"
        link.symlink_to(a)
        self.assertEqual(collect.snapshot_path(a), collect.snapshot_path(a / ".." / "a"))
        self.assertEqual(collect.snapshot_path(a), collect.snapshot_path(link))
        self.assertNotEqual(collect.snapshot_path(a), collect.snapshot_path(b))
        self.assertEqual(collect.snapshot_path(a).parent.parent, self.state)  # nằm trong state/
        self.report(a)
        self.report(b)
        self.assertEqual(len(self.snapshot_files()), 2)


class SnapshotDiff(SnapshotCase):
    """Hàm so sánh thuần, không cần git."""

    def test_nothing_changed(self):
        s = snap(open=["Việc còn dở dang A"], done=["Việc đã xong B"], head="abc1234", branch="main")
        self.assertFalse(collect.diff_snapshots(s, dict(s, ts=200.0))["changed"])

    def test_matching_ignores_case_accents_punctuation_and_appended_notes(self):
        old = snap(open=["Chạy eval", "Viết `README`: phần cài đặt"])
        new = snap(done=["chay eval. Xong 02/10/2026", "Viet README phan cai dat"])
        ch = collect.diff_snapshots(old, new)
        self.assertEqual(ch["done"], ["chay eval. Xong 02/10/2026", "Viet README phan cai dat"])
        self.assertEqual((ch["new"], ch["gone"]), ([], []))  # ô đã tick không bị tính là biến mất

    def test_new_open_item_and_vanished_open_item(self):
        old = snap(open=["Việc cũ còn dở dang", "Việc sẽ bị xóa khỏi kế hoạch"])
        new = snap(open=["Việc cũ còn dở dang", "Việc mới phát sinh hôm nay"])
        ch = collect.diff_snapshots(old, new)
        self.assertEqual(ch["new"], ["Việc mới phát sinh hôm nay"])
        self.assertEqual(ch["gone"], ["Việc sẽ bị xóa khỏi kế hoạch"])
        self.assertEqual(ch["done"], [])

    def test_vanished_done_item_is_not_reported(self):
        ch = collect.diff_snapshots(snap(done=["Mục Xong đã bị gộp lại"]), snap())
        self.assertEqual((ch["done"], ch["new"], ch["gone"]), ([], [], []))
        self.assertFalse(ch["changed"])

    def test_item_already_done_before_is_not_new_done(self):
        old = snap(done=["Việc đã xong từ trước"])
        ch = collect.diff_snapshots(old, snap(done=["Việc đã xong từ trước", "Việc vừa xong xuôi"]))
        self.assertEqual(ch["done"], ["Việc vừa xong xuôi"])

    def test_phase_and_head_changes(self):
        old = snap(head="abc1234", branch="main", phase={"title": "GĐ1", "done": 1, "total": 2})
        new = snap(head="def5678", branch="phu", phase={"title": "GĐ2", "done": 0, "total": 3})
        ch = collect.diff_snapshots(old, new)
        self.assertEqual(ch["head"], {"old": "abc1234", "new": "def5678"})
        self.assertEqual(ch["branch"], {"old": "main", "new": "phu"})
        self.assertEqual(ch["phase"], {"old": "GĐ1", "new": "GĐ2"})
        self.assertTrue(ch["changed"])

    def test_same_commit_with_longer_abbreviation_is_not_a_head_change(self):
        # git tự dài thêm độ dài hash rút gọn khi repo lớn lên: cùng một commit thì không phải "HEAD đổi"
        ch = collect.diff_snapshots(snap(head="abc1234"), snap(head="abc12345"))
        self.assertIsNone(ch["head"])
        self.assertFalse(ch["changed"])
        self.assertTrue(collect.diff_snapshots(snap(head="abc1234"), snap(head="abd1234"))["changed"])
        self.assertTrue(collect.diff_snapshots(snap(head=None), snap(head="abc1234"))["changed"])

    def test_other_plan_file_skips_item_comparison(self):
        ch = collect.diff_snapshots(snap(plan="PLAN.md", open=["Việc cũ còn dở dang"]),
                                    snap(plan=".agent/HANDOFF.md", open=["Việc khác hẳn nhau"]))
        self.assertEqual(ch["plan"], {"old": "PLAN.md", "new": ".agent/HANDOFF.md"})
        self.assertEqual((ch["done"], ch["new"], ch["gone"]), ([], [], []))
        self.assertTrue(ch["changed"])

    def test_all_mode_summary_names_the_first_item_of_each_group(self):
        ch = collect.diff_snapshots(
            snap(open=["Việc bị xóa khỏi kế hoạch"], head="abc1234"),
            snap(open=["Việc mới một", "Việc mới hai"], done=["Việc vừa xong"], head="def5678"))
        ch["commits"] = {"count": 3, "log": [{"sha": "def5678", "subject": "Sửa lỗi lớn"}]}
        text = collect.change_summary(ch)
        self.assertEqual(text, "3 commit mới (Sửa lỗi lớn; +2 nữa); 1 xong (Việc vừa xong); "
                               "2 phát sinh (Việc mới một; +1 nữa); 1 biến mất (Việc bị xóa khỏi kế hoạch)")
        self.assertEqual(collect.change_summary(collect.diff_snapshots(snap(), snap())), "")

    def test_commit_count_without_readable_subjects(self):
        ch = collect.diff_snapshots(snap(head="abc1234"), snap(head="def5678"))
        ch["commits"] = {"count": 3, "log": []}
        self.assertEqual(collect.commit_line(ch), "Commit mới: 3")
        ch["branch"] = {"old": "main", "new": "phu"}
        self.assertEqual(collect.commit_line(ch), "Commit mới: 3 · nhánh `main` → `phu`")

    def test_long_commit_subjects_are_clipped(self):
        ch = collect.diff_snapshots(snap(head="abc1234"), snap(head="def5678"))
        ch["commits"] = {"count": 1, "log": [{"sha": "def5678", "subject": collect.A.clip("Từ " * 60, 60)}]}
        line = collect.commit_line(ch)
        self.assertLess(len(line), 100)
        self.assertTrue(line.startswith("Commit mới: 1 (`def5678` Từ Từ"))

    def test_render_unchanged_is_exactly_one_line_with_last_time(self):
        ch = collect.diff_snapshots(snap(ts=time.time() - 7200), snap())
        lines = collect.render_changes(ch)
        self.assertEqual(len(lines), 1)
        self.assertIn("Đổi từ lần trước", lines[0])
        self.assertIn("không có gì đổi", lines[0])
        self.assertIn("2 giờ trước", lines[0])

    def test_render_caps_each_group(self):
        items = [f"Việc mới số {i} cần làm" for i in range(1, 7)]
        lines = collect.render_changes(collect.diff_snapshots(snap(), snap(open=items)))
        self.assertTrue(lines[0].startswith("### Đổi từ lần trước"))
        self.assertLessEqual(len(lines), 4)  # tiêu đề, dòng trống, một dòng "Mới phát sinh"
        self.assertIn("(+3 nữa)", "\n".join(lines))
        self.assertIn("Việc mới số 3 cần làm", "\n".join(lines))
        self.assertNotIn("Việc mới số 4 cần làm", "\n".join(lines))


class ChangesSinceLastReport(SnapshotCase):
    def test_first_report_prints_no_section_but_saves_a_snapshot(self):
        root = self.project()
        out = self.report(root)
        self.assertIn("## Tiến độ: proj", out)
        self.assertNotIn("Đổi từ lần trước", out)
        self.assertEqual(len(self.snapshot_files()), 1)

    def test_second_report_without_changes_is_one_line(self):
        root = self.project()
        self.report(root)
        out = self.report(root)
        mentions = [ln for ln in out.splitlines() if "Đổi từ lần trước" in ln]
        self.assertEqual(len(mentions), 1)
        self.assertIn("không có gì đổi", mentions[0])
        self.assertNotIn("### Đổi từ lần trước", out)
        self.assertIn("### Việc nên làm tiếp", out)  # báo cáo thường vẫn còn nguyên

    def test_changes_are_summarised_by_kind(self):
        root = self.project()
        self.report(root)
        self.make_changes(root)
        out = self.report(root)
        lines = self.section(out)
        self.assertLessEqual(len(lines), 7)  # gọn: tiêu đề + tối đa vài dòng
        text = "\n".join(lines)
        self.assertIn("Commit mới: 1", text)
        self.assertIn("Thêm bộ nhớ đệm", text)  # tiêu đề commit
        done = next(ln for ln in lines if ln.startswith("- Mới xong:"))
        for title in ("Viết bộ lọc dữ liệu đầu vào", "Thêm bộ nhớ đệm cho truy vấn nặng", "Cài xong bộ nhớ đệm"):
            self.assertIn(title, done)  # ô được tick, bước bị gạch, mục Xong mới
        new = next(ln for ln in lines if ln.startswith("- Mới phát sinh:"))
        self.assertIn("Chạy thử trên dữ liệu thật", new)
        gone = next(ln for ln in lines if ln.startswith("- Biến mất:"))
        self.assertIn("Đo hiệu năng cơ sở", gone)
        self.assertNotIn("Viết bộ lọc", gone)  # đã tick nên không phải biến mất
        phase = next(ln for ln in lines if ln.startswith("- Giai đoạn hiện tại:"))
        self.assertIn("GĐ1: Nền tảng", phase)
        self.assertIn("GĐ2: Mở rộng", phase)

    def test_commit_subjects_from_git_are_clipped(self):
        root = self.project()
        self.report(root)
        (root / "x.txt").write_text("x\n")
        self.commit(root, "Tiêu đề commit rất dài " * 8)
        line = next(ln for ln in self.section(self.report(root)) if ln.startswith("- Commit mới"))
        self.assertLess(len(line), 100)  # "- Commit mới: 1 (`hash` " + tối đa 60 ký tự tiêu đề + ")"
        self.assertIn("…", line)

    def test_section_sits_before_the_ranked_actions(self):
        root = self.project()
        self.report(root)
        self.make_changes(root)
        out = self.report(root)
        self.assertLess(out.index("### Đổi từ lần trước"), out.index("### Việc nên làm tiếp"))

    def test_last_time_is_shown(self):
        root = self.project()
        self.report(root)
        ts = self.age_snapshot(root, 3)
        out = self.report(root)
        line = next(ln for ln in out.splitlines() if "Đổi từ lần trước" in ln)
        self.assertIn(time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)), line)
        self.assertIn("3 giờ trước", line)

    def test_report_moves_the_baseline(self):
        root = self.project()
        self.report(root)
        self.make_changes(root)
        self.assertIn("### Đổi từ lần trước", self.report(root))
        again = self.report(root)  # mốc đã dời sang lần báo vừa rồi
        self.assertNotIn("### Đổi từ lần trước", again)
        self.assertIn("không có gì đổi", again)

    def test_many_new_items_are_capped(self):
        root = self.project()
        self.report(root)
        extra = "".join(f"- [ ] Việc phát sinh thứ {i} cần xử lý\n" for i in range(1, 7))
        self.edit(root, "- [ ] Thêm API công khai\n", "- [ ] Thêm API công khai\n" + extra)
        lines = self.section(self.report(root))
        self.assertLessEqual(len(lines), 3)
        self.assertIn("(+3 nữa)", "\n".join(lines))

    def test_unknown_old_head_does_not_crash(self):
        root = self.project()
        self.report(root)
        path = collect.snapshot_path(root)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["head"] = "deadbee"  # đúng dạng hex nhưng không có trong repo (như sau rebase hoặc gc)
        path.write_text(json.dumps(data), encoding="utf-8")
        out = self.report(root)
        self.assertIn("HEAD đổi", out)
        self.assertIn("không so được lịch sử", out)

    def test_head_that_moved_back_is_not_called_a_new_commit(self):
        root = self.project()
        (root / "x.txt").write_text("x\n")
        self.commit(root, "commit thứ hai")
        self.report(root)
        git(root, "reset", "-q", "--hard", "HEAD~1")
        out = self.report(root)
        self.assertIn("HEAD đổi", out)
        self.assertNotIn("Commit mới", out)

    def test_plan_switch_is_reported_without_item_noise(self):
        root = self.project()
        self.report(root)
        handoff = root / ".agent" / "HANDOFF.md"
        handoff.parent.mkdir()
        handoff.write_text("# HANDOFF\n\n## 0. Đang ở đâu\n- **Việc tiếp theo:**\n  1. Bước từ bàn giao\n", encoding="utf-8")
        future = time.time() + 60  # HANDOFF.md mới hơn PLAN.md nên được chọn làm file kế hoạch
        os.utime(handoff, (future, future))
        text = "\n".join(self.section(self.report(root)))
        self.assertIn("Kế hoạch", text)
        self.assertIn("HANDOFF.md", text)
        self.assertNotIn("Biến mất", text)

    def test_folder_without_git_tracks_checkboxes(self):
        root = self.tmp / "hoc"
        root.mkdir()
        (root / "PROGRESS.md").write_text(LEARNING, encoding="utf-8")
        self.report(root)
        (root / "PROGRESS.md").write_text(LEARNING.replace("- [ ] MIT 6.1810", "- [x] MIT 6.1810"), encoding="utf-8")
        text = "\n".join(self.section(self.report(root)))
        self.assertIn("Mới xong: MIT 6.1810: lab util, syscall", text)
        self.assertNotIn("Commit", text)

    def test_directory_without_plan_or_git_gets_no_snapshot(self):
        root = self.tmp / "trong"
        root.mkdir()
        out = self.report(root)
        self.assertNotIn("Đổi từ lần trước", out)
        self.assertEqual(self.snapshot_files(), [])

    def test_json_carries_the_changes(self):
        root = self.project()
        self.assertIsNone(json.loads(self.report(root, "--json"))["changes"])
        self.make_changes(root)
        changes = json.loads(self.report(root, "--json"))["changes"]
        self.assertTrue(changes["changed"])
        self.assertIn("Chạy thử trên dữ liệu thật", changes["new"][0])
        self.assertEqual(changes["commits"]["count"], 1)
        self.assertIsInstance(changes["since"], float)


class NoSnapshotFlag(SnapshotCase):
    def test_dry_run_writes_nothing(self):
        root = self.project()
        out = self.report(root, "--no-snapshot")
        self.assertIn("## Tiến độ: proj", out)
        self.assertEqual(self.snapshot_files(), [])

    def test_dry_run_still_compares_but_keeps_the_old_snapshot(self):
        root = self.project()
        self.report(root)
        path = self.snapshot_files()[0]
        before = path.read_bytes()
        self.make_changes(root)
        out = self.report(root, "--no-snapshot")
        self.assertIn("### Đổi từ lần trước", out)
        self.assertEqual(path.read_bytes(), before)
        self.assertIn("### Đổi từ lần trước", self.report(root))  # lần chạy thật vẫn thấy đủ thay đổi
        self.assertNotEqual(path.read_bytes(), before)

    def test_brief_and_session_hook_never_write_snapshots(self):
        root = self.project()
        collect.brief(root)
        self.assertEqual(self.report(root, "--brief").count("Đổi từ lần trước"), 0)
        self.assertEqual(self.snapshot_files(), [])
        out = run_script(PLUGIN / "hooks" / "session_start.py", stdin=json.dumps(
            {"session_id": "s1", "source": "startup", "cwd": str(root)}))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.snapshot_files(), [])


class BrokenSnapshots(SnapshotCase):
    """Snapshot hỏng, thiếu hay sai định dạng thì bỏ qua êm: không lỗi, không in thêm, mã thoát 0."""

    def cli(self, *args):
        out = run_script(COLLECT, *args)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stderr, "")
        return out.stdout

    def test_bad_contents_are_ignored_and_replaced(self):
        root = self.project()
        self.report(root)
        path = collect.snapshot_path(root)
        base = json.loads(path.read_text(encoding="utf-8"))
        bad = {
            "không phải JSON": b"{khong phai json",
            "rỗng": b"",
            "byte rác": b"\xff\xfe\x00\x01",
            "JSON nhưng là danh sách": b"[1, 2, 3]",
            "thiếu trường": b'{"v": 1}',
            "sai phiên bản": json.dumps(dict(base, v=99)).encode(),
            "ts không phải số": json.dumps(dict(base, ts="hôm qua")).encode(),
            "ts là NaN": json.dumps(dict(base, ts=float("nan"))).encode(),
            "ts là true": json.dumps(dict(base, ts=True)).encode(),
            "open sai kiểu": json.dumps(dict(base, open="không phải danh sách")).encode(),
            "open chứa số": json.dumps(dict(base, open=[1, 2])).encode(),
            "done chứa null": json.dumps(dict(base, done=[None])).encode(),
            "phase sai kiểu": json.dumps(dict(base, phase=["GĐ1"])).encode(),
            "snapshot của project khác": json.dumps(dict(base, root="/noi/khac")).encode(),
            "quá nhiều việc mở": json.dumps(dict(base, open=[f"việc số {i}" for i in range(collect.MAX_OPEN + 1)])).encode(),
            "quá nhiều việc xong": json.dumps(dict(base, done=[f"việc số {i}" for i in range(collect.MAX_DONE + 1)])).encode(),
            "tiêu đề dài bất thường": json.dumps(dict(base, open=["x" * 5000])).encode(),
            "head giống tùy chọn dòng lệnh": json.dumps(dict(base, head=f"--output={self.tmp / 'khong-duoc-tao'}")).encode(),
        }
        for name, content in bad.items():
            with self.subTest(name):
                path.write_bytes(content)
                out = self.cli("--project", str(root))
                self.assertIn("## Tiến độ: proj", out)
                self.assertNotIn("Đổi từ lần trước", out)
                fixed = json.loads(path.read_text(encoding="utf-8"))  # bản hỏng được ghi đè bằng bản tốt
                self.assertEqual((fixed["v"], fixed["root"]), (1, base["root"]))
        self.assertEqual(list(self.tmp.glob("khong-duoc-tao*")), [])  # git không bao giờ nhận head hỏng làm tham số

    def test_json_modes_survive_bad_snapshot(self):
        root = self.project()
        self.report(root)
        collect.snapshot_path(root).write_text("rác", encoding="utf-8")
        data = json.loads(self.cli("--project", str(root), "--json"))
        self.assertIsNone(data["changes"])

    def test_directory_or_file_in_the_wrong_place(self):
        root = self.project()
        self.report(root)
        path = collect.snapshot_path(root)
        path.unlink()
        path.mkdir()  # thư mục nằm đúng chỗ file snapshot: không đọc được, không ghi đè được
        self.assertIn("## Tiến độ: proj", self.cli("--project", str(root)))
        shutil.rmtree(path.parent)
        path.parent.write_text("không phải thư mục", encoding="utf-8")  # state/tien-do là file thường
        out = self.cli("--project", str(root))
        self.assertIn("## Tiến độ: proj", out)
        self.assertNotIn("Đổi từ lần trước", out)

    def test_all_mode_one_bad_snapshot_does_not_block_others(self):
        ws = self.tmp / "ws"
        ws.mkdir()
        a, b = self.project("a", parent=ws), self.project("b", parent=ws)
        self.cli("--all", str(ws))
        collect.snapshot_path(a).write_text("rác", encoding="utf-8")
        self.edit(b, "- [ ] Thêm API công khai", "- [x] Thêm API công khai")
        out = self.cli("--all", str(ws))
        self.assertIn("**b**", out.split("### Đổi từ lần trước")[1])


class AllModeChanges(SnapshotCase):
    def run_all(self, ws, *flags):
        out = run_script(COLLECT, "--all", str(ws), *flags)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stderr, "")
        return out.stdout

    def workspace(self):
        ws = self.tmp / "ws"
        ws.mkdir()
        a, b = self.project("a", parent=ws), self.project("b", parent=ws)
        (ws / "c").mkdir()  # không phải project
        return ws, a, b

    def test_each_project_is_compared_with_its_own_snapshot(self):
        ws, a, b = self.workspace()
        first = self.run_all(ws)
        for name in ("| a |", "| b |", "| c |"):
            self.assertIn(name, first)
        self.assertNotIn("Đổi từ lần trước", first)
        self.assertEqual(len(self.snapshot_files()), 2)  # c không phải project nên không có snapshot
        self.edit(a, "- [ ] Đo hiệu năng cơ sở", "- [x] Đo hiệu năng cơ sở")
        self.commit(a, "Đo xong hiệu năng")
        second = self.run_all(ws)
        lines = [ln for ln in second.split("### Đổi từ lần trước")[1].splitlines() if ln.strip()]
        self.assertLessEqual(len(lines), 3)
        self.assertTrue(lines[0].startswith("- **a**"))
        for part in ("1 commit mới (Đo xong hiệu năng)", "1 xong (Đo hiệu năng cơ sở)"):
            self.assertIn(part, lines[0])
        self.assertEqual(lines[1], "- Không đổi: b")
        third = self.run_all(ws)
        self.assertNotIn("### Đổi từ lần trước", third)
        self.assertIn("Đổi từ lần trước: không project nào đổi", third)

    def test_last_time_of_each_project(self):
        ws, a, b = self.workspace()
        self.run_all(ws)
        self.age_snapshot(a, 5)
        self.edit(a, "- [ ] Đo hiệu năng cơ sở", "- [x] Đo hiệu năng cơ sở")
        line = next(ln for ln in self.run_all(ws).splitlines() if ln.startswith("- **a**"))
        self.assertIn("5 giờ trước", line)

    def test_no_snapshot_flag(self):
        ws, a, b = self.workspace()
        self.run_all(ws, "--no-snapshot")
        self.assertEqual(self.snapshot_files(), [])
        self.run_all(ws)
        before = {p.name: p.read_bytes() for p in self.snapshot_files()}
        self.edit(a, "- [ ] Đo hiệu năng cơ sở", "- [x] Đo hiệu năng cơ sở")
        out = self.run_all(ws, "--no-snapshot")
        self.assertIn("**a**", out.split("### Đổi từ lần trước")[1])
        self.assertEqual({p.name: p.read_bytes() for p in self.snapshot_files()}, before)

    def test_json_rows_carry_changes_per_project(self):
        ws, a, b = self.workspace()
        rows = {r["project"]: r for r in json.loads(self.run_all(ws, "--json"))}
        self.assertTrue(all(r["changes"] is None for r in rows.values()))
        self.edit(a, "- [ ] Đo hiệu năng cơ sở", "- [x] Đo hiệu năng cơ sở")
        rows = {r["project"]: r for r in json.loads(self.run_all(ws, "--json"))}
        self.assertTrue(rows["a"]["changes"]["changed"])
        self.assertFalse(rows["b"]["changes"]["changed"])
        self.assertIsNone(rows["c"]["changes"])


class RouteText(TempDirTestCase):
    def test_shows_model_id_effort_and_agent(self):
        item = {"route": {"model": "haiku", "model_id": "claude-haiku-5-5", "effort": "low",
                          "agent": "agent-stack:test-runner"}}
        self.assertEqual(collect.route_text(item), " · claude-haiku-5-5 · low · agent-stack:test-runner")
        self.assertEqual(collect.route_text({"route": {"model": "sonnet", "effort": "medium"}}), " · sonnet · medium")
        self.assertEqual(collect.route_text({}), "")


class LongSection0Warning(TempDirTestCase):
    def test_warns_when_section0_is_long_and_not_when_short(self):
        self.write("PLAN.md", PLAN)
        self.assertFalse([w for w in collect.warnings(collect.collect(self.tmp, scan_todos=False)) if "§0 dài" in w])
        filler = "".join(f"  - việc cũ {i}: " + "x" * 200 + "\n" for i in range(80))
        self.write("PLAN.md", PLAN.replace("- **Việc tiếp theo", "- **Xong cũ:**\n" + filler + "- **Việc tiếp theo", 1))
        found = [w for w in collect.warnings(collect.collect(self.tmp, scan_todos=False)) if "§0 dài" in w]
        self.assertEqual(len(found), 1)
        self.assertIn("state.py trim", found[0])
