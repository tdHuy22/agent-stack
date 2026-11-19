"""GĐ3: archctl vào vòng lặp. Hook post_edit đưa dòng vi phạm `archctl check` về agent ngay lượt sửa file (Claude Code),
session_start báo số đề xuất chờ duyệt, done-gate (`checks.py`) chạy `check --strict` và `verify`.
Dùng archctl giả (ghi lại đối số, in đầu ra cho trước) để kiểm từng nhánh; archctl thật (khi máy có) cho ca đầu-cuối.

Tái hiện gốc (14/11/2026): hook do `archctl init` sinh chạy `archctl check --changed`, in vi phạm ra stdout và thoát
mã 1; Claude Code ghi là `hook_non_blocking_error`, model trả lời không thấy vi phạm nào.
"""
import json
import os
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path

from tests._util import PLUGIN, git
from tests.test_guard import GuardBase

HOOKS = PLUGIN / "hooks"
# PATH gọn cho hook: thư mục của python3 đang chạy test (3.11, như app gọi hook) rồi hệ thống; không có archctl thật.
BASE_PATH = f"{Path(sys.executable).parent}:/usr/bin:/bin"
CHECKS = PLUGIN / "skills" / "done-gate" / "scripts" / "checks.py"
MAX_LINES = 20  # archgate.MAX_LINES: không import thư viện ở đầu file, để test trượt ở assert trên code cũ
RULES = ("component Web    at app/web/**     @human #accepted\n"
         "component Report at app/report/**  @human #accepted\n"
         "deny Web -> Report\n")
VIOLATION = ("kiến trúc 52e8 · chỉ quét 1 file vừa đổi\n\n"
             "✗ VI PHẠM  Web -> Report  (bị cấm, #accepted)\n"
             "  app/web/view.py:1  import 'app.report.data'\n"
             "  luật: deny Web -> Report\n\n"
             "⚠ CHƯA CHỨNG MINH  cách kiểm `ok` — chưa chạy lần nào\n"
             "  → archctl verify ok\n\n"
             "1 vi phạm mới, 1 cảnh báo\n")
FAKE = """#!/usr/bin/env python3
import os, sys, time
args = sys.argv[1:]
with open(os.environ["FAKE_ARCH_LOG"], "a") as fh:
    fh.write(" ".join(args) + "\\n")
time.sleep(float(os.environ.get("FAKE_ARCH_SLEEP", "0")))
if args[:1] == ["verify"]:
    sys.exit(int(os.environ.get("FAKE_ARCH_VERIFY_CODE", "0")))
out = os.environ.get("FAKE_ARCH_OUT")
if out:
    sys.stdout.write(open(out, encoding="utf-8").read())
sys.exit(int(os.environ.get("FAKE_ARCH_CODE", "0")))
"""


def make_fake(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    fake = folder / "archctl"
    fake.write_text(FAKE)
    fake.chmod(0o755)
    return fake


class ArchHookBase(GuardBase):
    def setUp(self):
        super().setUp()
        for rel, text in {".arch/system.arch": RULES, "app/__init__.py": "", "app/web/__init__.py": "",
                          "app/report/__init__.py": "", "app/web/view.py": "Y = 2\n",
                          "app/report/data.py": "X = 1\n"}.items():
            path = self.project / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "arch")
        self.bin = self.tmp / "bin"
        make_fake(self.bin)
        self.log = self.tmp / "archctl.log"
        self.out = self.tmp / "archctl.out"

    def fake_env(self, code=0, text="", **extra):
        self.out.write_text(text)
        return {"PATH": f"{self.bin}:{BASE_PATH}", "FAKE_ARCH_LOG": str(self.log), "FAKE_ARCH_OUT": str(self.out),
                "FAKE_ARCH_CODE": str(code), **extra}

    def calls(self) -> list:
        return self.log.read_text().splitlines() if self.log.exists() else []

    def post(self, tool, tool_input, sid="p1", **env):
        out = self.hook("post_edit.py", {"session_id": sid, "cwd": str(self.project), "tool_name": tool,
                                         "tool_input": tool_input, "tool_response": {},
                                         "hook_event_name": "PostToolUse"}, **env)
        return out["hookSpecificOutput"]["additionalContext"] if out else ""

    def edit_view(self, sid="p1", **env):
        view = self.project / "app" / "web" / "view.py"
        view.write_text("from app.report.data import X\n")
        return self.post("Edit", {"file_path": str(view), "new_string": "from app.report.data import X"}, sid, **env)


class PostEditArch(ArchHookBase):
    def test_violation_reaches_agent_in_the_same_turn(self):
        ctx = self.edit_view(**self.fake_env(1, VIOLATION))
        self.assertIn("✗ VI PHẠM  Web -> Report", ctx)
        self.assertIn("app/web/view.py:1  import 'app.report.data'", ctx)
        self.assertIn("1 vi phạm mới", ctx)
        self.assertIn("archctl propose", ctx, "lời báo nhắc giao thức: đề xuất hay báo bế tắc rồi dừng")
        self.assertNotIn("CHƯA CHỨNG MINH", ctx, "cảnh báo không phải vi phạm thì không đưa vào")
        self.assertLess(self.elapsed, 2.0)
        view = self.project / "app" / "web" / "view.py"
        self.assertEqual(self.calls(), [f"check --root {self.project} {view}"], "kiểm đúng file vừa sửa")

    def test_clean_result_and_project_without_arch_are_silent(self):
        self.assertEqual(self.edit_view(**self.fake_env(0, "0 vi phạm mới\n")), "")
        other = self.tmp / "plain"
        (other / "a").mkdir(parents=True)
        git(other, "init", "-q")
        (other / "a" / "x.py").write_text("x = 1\n")
        self.calls_before = len(self.calls())
        out = self.hook("post_edit.py", {"session_id": "p1", "cwd": str(other), "tool_name": "Write",
                                         "tool_input": {"file_path": str(other / "a" / "x.py")}},
                        **self.fake_env(1, VIOLATION))
        self.assertIsNone(out)
        self.assertEqual(len(self.calls()), self.calls_before, "project không có .arch/system.arch: không gọi archctl")

    def test_broken_rules_file_is_reported(self):
        ctx = self.edit_view(**self.fake_env(2, "✗ .arch/system.arch:3: không hiểu `deny Web ->`\n"))
        self.assertIn("không đọc được `.arch/system.arch`", ctx)
        self.assertIn("Không tự sửa file luật", ctx)

    def test_editing_rules_file_itself_does_not_run_archctl(self):
        self.post("Edit", {"file_path": str(self.project / ".arch" / "system.arch")}, **self.fake_env(1, VIOLATION))
        self.assertEqual(self.calls(), [])

    def test_archctl_inside_the_project_is_never_run(self):
        """TM-112: file tên archctl do repo đặt sẵn (đứng trước trên PATH) không được chạy; coi như máy thiếu."""
        inside = make_fake(self.project / "bin")
        env = self.fake_env(1, VIOLATION)
        env["PATH"] = f"{inside.parent}:{BASE_PATH}"
        ctx = self.edit_view(sid="in1", **env)
        self.assertEqual(self.calls(), [])
        self.assertIn("máy chưa có archctl", ctx)

    def test_missing_archctl_is_mentioned_once_per_session(self):
        env = {"PATH": BASE_PATH}
        self.assertIn("máy chưa có archctl", self.edit_view(sid="m1", **env))
        self.assertEqual(self.edit_view(sid="m1", **env), "")
        self.assertIn("máy chưa có archctl", self.edit_view(sid="m2", **env), "phiên khác thì nhắc lại")

    def test_slow_archctl_is_cut_off_and_hook_stays_fast(self):
        start = time.time()
        ctx = self.edit_view(**self.fake_env(1, VIOLATION, FAKE_ARCH_SLEEP="5"))
        self.assertEqual(ctx, "")
        self.assertLess(time.time() - start, 2.5)

    def test_output_is_cleaned_and_capped(self):
        noisy = "".join(f"✗ VI PHẠM  Web -> Report\x1b[31m\u202e  ({i})\n  app/web/view.py:{i}  import 'x'\n"
                        for i in range(40)) + "40 vi phạm mới\n"
        ctx = self.edit_view(**self.fake_env(1, noisy))
        body = [x for x in ctx.splitlines() if x.startswith(("✗", "  ", "…"))]
        self.assertLessEqual(len(body), MAX_LINES + 1)
        self.assertNotIn("\x1b", ctx)
        self.assertNotIn("\u202e", ctx)
        self.assertIn("còn 60 dòng", ctx)

    def test_bash_that_writes_checks_changed_files_once_per_turn(self):
        self.start("làm tiếp", "b1")
        (self.project / "app" / "web" / "view.py").write_text("from app.report.data import X\n")
        env = self.fake_env(1, VIOLATION)
        first = self.post("Bash", {"command": "sed -i '' s/Y/X/ app/web/view.py"}, "b1", **env)
        self.assertIn("sau lệnh shell vừa chạy", first)
        self.assertIn("✗ VI PHẠM  Web -> Report", first)
        self.assertEqual(self.calls(), [f"check --root {self.project} --changed"])
        (self.project / "app" / "web" / "view.py").write_text("from app.report.data import X\ny = 1\n")  # lệnh ghi thật
        self.assertEqual(self.post("Bash", {"command": "echo y > app/web/view.py"}, "b1", **env), "",
                         "cùng vi phạm, cùng lượt: không báo lặp")
        self.assertEqual(self.post("Bash", {"command": "ls app"}, "b1", **env), "")
        self.assertEqual(len(self.calls()), 2, "lệnh không ghi file thì không gọi archctl")

    @unittest.skipUnless(shutil.which("archctl"), "máy chưa có archctl (cài: ./install.sh --only tools, mục cargo:archctl)")
    def test_real_archctl_end_to_end(self):
        env = {"PATH": f"{Path(shutil.which('archctl')).parent}:{BASE_PATH}"}
        ctx = self.edit_view(sid="real1", **env)
        self.assertIn("✗ VI PHẠM  Web -> Report", ctx)
        self.assertIn("app/web/view.py:1", ctx)
        (self.project / "app" / "web" / "view.py").write_text("Y = 3\n")
        self.assertEqual(self.post("Edit", {"file_path": str(self.project / "app/web/view.py")}, "real1", **env), "")


class PendingProposals(ArchHookBase):
    def test_count_reads_proposal_blocks_only(self):
        (self.project / ".arch" / "proposals.arch").write_text(
            "# đề xuất\n\nproposal p-0123456789abcdef @ai 2026-11-14\n  rule allow Web -> Report\n  reason x\n\n"
            "  proposal p-ffff @ai 2026-11-14\n  block deny Web -> Report\n  reason y\n# proposal p-cu\n")
        out = self.hook("session_start.py", {"session_id": "s0", "cwd": str(self.project), "source": "startup",
                                             "hook_event_name": "SessionStart"}) or {}
        self.assertIn("⏸ 2 đề xuất kiến trúc chờ bạn duyệt", out.get("systemMessage", ""))

    def test_session_start_reports_pending_count(self):
        (self.project / ".arch" / "proposals.arch").write_text("proposal p-1 @ai 2026-11-14\n  rule allow Web -> Report\n")
        out = self.hook("session_start.py", {"session_id": "s1", "cwd": str(self.project), "source": "startup",
                                             "hook_event_name": "SessionStart"})
        self.assertIn("⏸ 1 đề xuất kiến trúc chờ bạn duyệt", out.get("systemMessage", ""))
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("agent không chạy hai lệnh này", ctx)
        self.assertNotIn("allow Web -> Report", ctx, "chỉ đưa số, không đưa nội dung đề xuất (TM-113)")

    def test_no_pending_no_line(self):
        out = self.hook("session_start.py", {"session_id": "s2", "cwd": str(self.project), "source": "startup",
                                             "hook_event_name": "SessionStart"}) or {}
        self.assertNotIn("đề xuất kiến trúc", json.dumps(out, ensure_ascii=False))


class DoneGateArch(ArchHookBase):
    def checks(self, **env):
        out = subprocess.run([sys.executable, str(CHECKS), "--root", str(self.project), "--base", "HEAD"],
                             capture_output=True, text=True, timeout=120, env=dict(os.environ, **env))
        return out.returncode, out.stdout + out.stderr

    def setUp(self):
        super().setUp()
        with open(self.project / ".arch" / "system.arch", "a") as fh:
            fh.write('verify ok runs "true"   @human #accepted\n')
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "verify")
        (self.project / "app" / "web" / "view.py").write_text("from app.report.data import X\n")

    def test_new_violation_blocks_and_verify_runs_first(self):
        code, out = self.checks(**self.fake_env(1, VIOLATION))
        self.assertEqual(code, 1, out)
        self.assertIn("luật kiến trúc (archctl)", out)
        self.assertIn("Web -> Report", out)
        self.assertIn("ok = `true`", out, "báo cáo nêu lệnh verify sẽ chạy (TM-114)")
        self.assertEqual([c.split()[0] for c in self.calls()], ["verify", "check"])
        self.assertIn("--strict", self.calls()[1])

    def test_verify_is_skipped_when_rules_changed(self):
        with open(self.project / ".arch" / "system.arch", "a") as fh:
            fh.write('verify evil runs "touch pwned"   @human #accepted\n')
        code, out = self.checks(**self.fake_env(0, "0 vi phạm mới\n"))
        self.assertEqual(code, 2, out)
        self.assertNotIn("verify", " ".join(self.calls()))
        self.assertIn("TM-114", out)

    def test_missing_archctl_is_not_reported_clean(self):
        code, out = self.checks(PATH=BASE_PATH)
        self.assertEqual(code, 2, out)
        self.assertIn("archctl", out)
        self.assertIn("cargo:archctl", out)

    def test_broken_rules_or_failed_verify_never_pass(self):
        code, out = self.checks(**self.fake_env(2, "✗ .arch/system.arch:1: hỏng\n"))
        self.assertNotEqual(code, 0, out)
        code, out = self.checks(**self.fake_env(0, "0 vi phạm mới\n", FAKE_ARCH_VERIFY_CODE="1"))
        self.assertEqual(code, 1, out)
        self.assertIn("verify trượt", out)

    def test_strict_warnings_alone_count_as_errors(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("checks_mod", CHECKS)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        diags = mod.parse_archctl("⚠ CHƯA CHỨNG MINH  cách kiểm `ok`\n  → archctl verify ok\n")
        self.assertEqual([d.level for d in diags], ["error"])
        diags = mod.parse_archctl(VIOLATION)
        self.assertEqual([(d.path, d.line, d.level) for d in diags],
                         [("app/web/view.py", 1, "error"), (None, None, "warning")])

    @unittest.skipUnless(shutil.which("archctl"), "máy chưa có archctl (cài: ./install.sh --only tools, mục cargo:archctl)")
    def test_real_archctl_blocks_violation(self):
        code, out = self.checks(PATH=f"{Path(shutil.which('archctl')).parent}:{os.environ['PATH']}")
        self.assertEqual(code, 1, out)
        self.assertIn("Web -> Report", out)


if __name__ == "__main__":
    unittest.main()
