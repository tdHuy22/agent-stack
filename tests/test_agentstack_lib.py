import os
import sys
import time
import unittest

from pathlib import Path

from tests._util import PLUGIN, REPO, TempDirTestCase, git

sys.path.insert(0, str(PLUGIN / "lib"))
import agentstack as A  # noqa: E402

# Cùng cấu trúc với mục §0 thật của người dùng (SCEE/PLAN.md), nội dung giả.
PLAN = """# PLAN — luận văn mẫu

**Ràng buộc thật:**
- **Mốc test hiện hành: `120 passed, 3 xfailed`** (28/09/2026).

---

## 0. Đang ở đâu, việc tiếp theo (cập nhật mỗi lần dừng phiên)

*Cập nhật 30/09/2026.* Đọc mục này trước tiên sau mỗi lần compact. Dữ liệu ở `Process/2026-09-28_bao-cao/`.

- **Xong:** G0 (trừ một ghi chú). G0.5 phần đọc paper.
- **Hướng đã chốt ngày 30/09 (user): làm bản ỨNG DỤNG.** Không chạy theo novelty.
- **Việc tiếp theo, theo thứ tự:**
  1. User chạy `/compact`.
  2. Lập **danh sách dọn** về một phiên bản.
     User duyệt rồi mới làm.
  3. Viết tài liệu thiết kế.
- **Quyết định còn treo:** không có.
- **Sau mỗi lần bị ngắt vì hết limit:** chạy kiểm tra nhanh:
  - `git status`;
  - pytest phải ra đúng mốc ở trên;

## 1. Giai đoạn

### G0
- [x] Dọn kho
- [x] Đọc paper

### G1
- [x] Khung
- [ ] Viết phần thiết kế
- [ ] Thử nghiệm
"""


class Section0(unittest.TestCase):
    def test_parse_fields_like_users_plan(self):
        sec = A.parse_section0(PLAN)
        self.assertTrue(sec["heading"].startswith("0."))
        self.assertEqual(sec["updated"], "2026-09-30")  # không lấy nhầm ngày trong đường dẫn
        self.assertIn("G0", sec["fields"]["done"])
        self.assertEqual(len(sec["next"]), 3)
        self.assertIn("User duyệt rồi mới làm", sec["next"][1])  # dòng nối tiếp được gộp
        self.assertEqual(sec["fields"]["decisions"], "không có.")
        self.assertEqual(sec["after_interrupt"][0], "`git status`;")
        self.assertTrue(any("ỨNG DỤNG" in n for n in sec["notes"]))

    def test_baseline_found_outside_section0(self):
        self.assertEqual(A.baseline_anywhere(PLAN), "120 passed, 3 xfailed")

    def test_checkbox_progress_and_current_phase(self):
        prog = A.checkbox_progress(PLAN)
        self.assertEqual((prog["done"], prog["total"]), (3, 5))
        self.assertEqual(prog["current"]["title"], "G1")
        self.assertEqual(prog["current"]["first_todo"], "Viết phần thiết kế")

    def test_english_and_iso_date(self):
        sec = A.parse_section0("## Where we are\nUpdated 2026-10-01.\n- **Next:**\n  1. Ship it\n")
        self.assertEqual((sec["updated"], sec["next"]), ("2026-10-01", ["Ship it"]))

    def test_fold(self):
        self.assertEqual(A.fold("Đang dở, Việc tiếp theo"), "dang do, viec tiep theo")


class PlanFilesAndGit(TempDirTestCase):
    def test_no_plan_means_empty_brief(self):
        self.assertEqual(A.brief(self.tmp), {})

    def test_newest_plan_wins(self):
        self.write("PLAN.md", PLAN)
        old = time.time() - 3600
        os.utime(self.tmp / "PLAN.md", (old, old))
        self.write(".agent/HANDOFF.md", "# HANDOFF\n\n## 0. Đang ở đâu\n- **Việc tiếp theo:**\n  1. Bước từ handoff\n")
        path, _, sec = A.read_plan(self.tmp)
        self.assertEqual(path.name, "HANDOFF.md")
        self.assertEqual(sec["next"], ["Bước từ handoff"])

    def test_brief_with_git(self):
        self.write("PLAN.md", PLAN)
        git(self.tmp, "init", "-q")
        git(self.tmp, "add", "-A")
        git(self.tmp, "commit", "-q", "-m", "init")
        self.write("src/a.py", "x = 1\n")
        info = A.brief(self.tmp)
        self.assertIn("Việc tiếp theo: 1) User chạy /compact.", info["context"].replace("`", ""))
        self.assertIn("Mốc kiểm tra: 120 passed, 3 xfailed", info["context"])
        self.assertIn("1 file chưa commit", info["context"])
        self.assertNotIn("Quyết định còn treo", info["context"])  # "không có" thì bỏ qua
        self.assertTrue(info["user"].startswith(f"📍 {self.tmp.name}: tiếp theo"))
        summary = A.git_summary(self.tmp)
        self.assertEqual((summary["branch"], summary["dirty"]), ("main", ["src/"]))

    def test_once_and_state_dir_override(self):
        os.environ["AGENT_STACK_STATE"] = str(self.tmp / "state")
        self.addCleanup(os.environ.pop, "AGENT_STACK_STATE", None)
        self.assertEqual(A.state_dir(), self.tmp / "state")
        self.assertTrue(A.once("k", 60))
        self.assertFalse(A.once("k", 60))
        marker = self.tmp / "state" / "once" / "k"
        os.utime(marker, (time.time() - 120, time.time() - 120))
        self.assertTrue(A.once("k", 60))


if __name__ == "__main__":
    unittest.main()


class CachedPluginCopy(TempDirTestCase):
    """Claude Code chép plugin vào ~/.claude/plugins/cache/: bản chép phải tìm về repo qua plugin/.agent-stack-home."""

    def test_home_dir_follows_pointer_file(self):
        import shutil
        import subprocess
        import sys
        import tempfile
        # bản chép phải nằm NGOÀI repo (như ~/.claude/plugins/cache), nếu không code tìm thấy repo theo thư mục cha
        outside = Path(tempfile.mkdtemp(prefix="agent-stack-cachetest-"))
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        copy = outside / "cache" / "agent-stack" / "0.3.1"
        (copy / "lib").mkdir(parents=True)
        shutil.copy(PLUGIN / "lib" / "agentstack.py", copy / "lib" / "agentstack.py")
        code = "import sys; sys.path.insert(0, sys.argv[1]); import agentstack as A; print(A.home_dir())"
        env = {k: v for k, v in __import__("os").environ.items() if k not in ("AGENT_STACK_HOME", "AGENT_STACK_STATE")}
        run = lambda: subprocess.run([sys.executable, "-c", code, str(copy / "lib")], capture_output=True, text=True,
                                     env=env, timeout=30).stdout.strip()
        self.assertEqual(run(), "None")  # chưa có file trỏ: không tìm được repo
        (copy / ".agent-stack-home").write_text(str(REPO) + "\n", encoding="utf-8")
        self.assertEqual(run(), str(REPO))
        (copy / ".agent-stack-home").write_text(str(outside) + "\n", encoding="utf-8")
        self.assertEqual(run(), "None")  # trỏ tới thư mục không phải agent-stack thì bỏ qua
