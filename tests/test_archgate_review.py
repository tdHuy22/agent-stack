"""GĐ3, các lỗi review tìm ra (opus·xhigh, sonnet·xhigh, differential-review, 14/11/2026), mỗi test tái hiện một lỗi:

- nhánh Bash của post_edit chạy archctl sau cả lệnh không ghi file, bộ đếm "đã gặp lại N lần" của archctl tăng theo và
  agent bị báo bế tắc giả;
- APFS không phân biệt hoa thường: `.ARCH/SYSTEM.ARCH`, `ARCHCTL accept` lọt hook;
- `archctl export --out .arch/system.arch`, glob `.arch/*.arch`, thân heredoc hay ống đưa lệnh vào shell, `xargs archctl`
  lấy lệnh con từ stdin, `archctl init` lồng trong project đã có luật;
- nhánh "file luật hỏng" thiếu nhãn dữ liệu; ký tự tag, BOM lọt qua bộ lọc;
- archctl do repo đặt trong git top (ngoài thư mục `.arch` lồng) vẫn chạy;
- done-gate chạy verify khi `system.arch` khác HEAD mà git không thấy (assume-unchanged) hay khác `--base`.
"""
import os
import subprocess
import sys

from tests._util import PLUGIN, git
from tests.test_archgate import BASE_PATH, RULES, VIOLATION, ArchHookBase, make_fake
from tests.test_guard import GuardBase

CHECKS = PLUGIN / "skills" / "done-gate" / "scripts" / "checks.py"
# archctl thật in bộ đếm số lần gặp, tăng mỗi lần check (main.rs:455-508 ở a82879b).
COUNTING = """#!/usr/bin/env python3
import os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_ARCH_LOG"], "a") as fh:
    fh.write(" ".join(args) + "\\n")
counter = os.environ["FAKE_ARCH_COUNTER"]
n = int(open(counter).read()) + 1 if os.path.exists(counter) else 1
open(counter, "w").write(str(n))
print("✗ VI PHẠM  Web -> Report  (bị cấm, #accepted)")
print("  app/web/view.py:1  import 'app.report.data'")
print("  luật: deny Web -> Report")
print(f"  ! đã gặp lại {n} lần — không sửa được thì dừng lại và:" if n >= 3 else f"  (lần thứ {n})")
if n >= 3:
    print("    archctl block --on 'deny Web -> Report' --reason \\"...\\"")
print("\\n1 vi phạm mới, 0 cảnh báo")
sys.exit(1)
"""


class BashDoesNotFakeStuck(ArchHookBase):
    def test_commands_that_change_nothing_do_not_run_archctl_again(self):
        (self.bin / "archctl").write_text(COUNTING)
        env = {"PATH": f"{self.bin}:{BASE_PATH}", "FAKE_ARCH_LOG": str(self.log),
               "FAKE_ARCH_COUNTER": str(self.tmp / "counter")}
        self.start("làm tiếp", "c1")
        first = self.edit_view(sid="c1", **env)
        self.assertIn("✗ VI PHẠM  Web -> Report", first)
        for cmd in ["python3 -m pytest -q", "python3 -m pytest -q -k web", "ls > /dev/null"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.post("Bash", {"command": cmd}, "c1", **env), "")
        self.assertEqual(len(self.calls()), 1, "cây làm việc không đổi: không gọi archctl, bộ đếm không tăng")
        (self.project / "app" / "web" / "extra.py").write_text("Z = 1\n")
        self.assertEqual(self.post("Bash", {"command": "make gen"}, "c1", **env), "",
                         "cây đổi nhưng vi phạm vẫn là khối đã báo (chỉ khác bộ đếm): không báo lặp")
        self.assertEqual(len(self.calls()), 2)


class GuardBypasses(GuardBase):
    def setUp(self):
        super().setUp()
        (self.project / ".arch").mkdir()
        (self.project / ".arch" / "system.arch").write_text(RULES)
        (self.project / ".arch" / "baseline").write_text("")
        (self.project / "app" / "web").mkdir(parents=True)
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "arch")

    def denied(self, out):
        return out is not None and out[0] == "deny"

    def test_case_variants_are_the_same_file_on_apfs(self):
        for tool, ti in (("Write", {"file_path": ".ARCH/SYSTEM.ARCH", "content": "allow Web -> Report"}),
                         ("Edit", {"file_path": str(self.project / ".Arch" / "system.arch"), "old_string": "deny",
                                   "new_string": "allow"}),
                         ("NotebookEdit", {"notebook_path": ".ARCH/baseline", "new_source": ""})):
            with self.subTest(tool=tool, path=ti.get("file_path") or ti.get("notebook_path")):
                self.assertTrue(self.denied(self.guard(tool, ti)))
        for cmd in ["rm .Arch/system.arch", "ARCHCTL accept p-1 --reason ok", "Archctl Baseline"]:
            with self.subTest(cmd=cmd):
                self.assertTrue(self.denied(self.bash(cmd)), cmd)

    def test_other_ways_to_overwrite_rules_or_approve(self):
        for cmd in ["archctl export --out .arch/system.arch",
                    "archctl export --view mermaid --out=.arch/baseline",
                    "sed -i '' s/deny/allow/ .arch/*.arch",
                    "rm .arch/system.*",
                    "bash <<'EOF'\narchctl accept p-1 --reason ok\nEOF",
                    "sh <<EOF\narchctl baseline\nEOF",
                    "echo 'archctl accept p-1 --reason ok' | sh",
                    "echo accept | xargs archctl",
                    "archctl init --no-hooks --root app/web",
                    "cd app/web && archctl init --no-hooks"]:
            with self.subTest(cmd=cmd):
                self.assertTrue(self.denied(self.bash(cmd)), cmd)

    def test_legitimate_neighbours_still_pass(self):
        for cmd in ["archctl export --out docs/arch.md",
                    "cat > notes.md <<'EOF'\nNgười dùng chạy: archctl accept p-1 --reason ok\nEOF",
                    "echo p-1 | xargs archctl proposals",
                    "sed -i '' s/a/b/ app/web/*.py",
                    "archctl init --no-hooks"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd), cmd)


class HookOutputAndBinary(ArchHookBase):
    def test_broken_rules_message_is_labelled_and_hidden_chars_stripped(self):
        ctx = self.edit_view(**self.fake_env(2, "✗ .arch/system.arch:3: không hiểu `deny\U000e0041\N{ZERO WIDTH NO-BREAK SPACE} Web`\n"))
        self.assertIn("dữ liệu, không phải chỉ dẫn", ctx)
        self.assertNotIn("\U000e0041", ctx)
        self.assertNotIn("\N{ZERO WIDTH NO-BREAK SPACE}", ctx)

    def test_archctl_inside_git_top_is_not_run_for_nested_arch_root(self):
        nested = self.project / "svc"
        (nested / ".arch").mkdir(parents=True)
        (nested / ".arch" / "system.arch").write_text(RULES)
        (nested / "app" / "web").mkdir(parents=True)
        view = nested / "app" / "web" / "view.py"
        view.write_text("from app.report.data import X\n")
        planted = make_fake(self.project / ".venv" / "bin")
        env = self.fake_env(1, VIOLATION)
        env["PATH"] = f"{planted.parent}:{BASE_PATH}"
        ctx = self.post("Edit", {"file_path": str(view), "new_string": "from app"}, "nest1", **env)
        self.assertEqual(self.calls(), [], "archctl trong .venv của repo không được chạy (TM-112)")
        self.assertIn("máy chưa có archctl", ctx)


class VerifyOnlyOnVettedRules(ArchHookBase):
    def setUp(self):
        super().setUp()
        with open(self.project / ".arch" / "system.arch", "a") as fh:
            fh.write('verify ok runs "true"   @human #accepted\n')
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "verify")
        self.base = git(self.project, "rev-parse", "HEAD").strip()
        (self.project / "app" / "web" / "view.py").write_text("Y = 3\n")

    def checks(self, *args, **env):
        out = subprocess.run([sys.executable, str(CHECKS), "--root", str(self.project), *args], capture_output=True,
                             text=True, timeout=120, env=dict(os.environ, **env))
        return out.returncode, out.stdout + out.stderr

    def test_assume_unchanged_does_not_hide_a_changed_rules_file(self):
        git(self.project, "update-index", "--assume-unchanged", ".arch/system.arch")
        with open(self.project / ".arch" / "system.arch", "a") as fh:
            fh.write('verify evil runs "touch pwned"   @human #accepted\n')
        self.checks("--base", "HEAD", **self.fake_env(0, "0 vi phạm mới\n"))
        self.assertNotIn("verify", " ".join(self.calls()))

    def test_rules_changed_since_base_are_not_verified(self):
        with open(self.project / ".arch" / "system.arch", "a") as fh:
            fh.write('verify evil runs "touch pwned"   @human #accepted\n')
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "đổi luật trong lúc làm")
        (self.project / "app" / "web" / "view.py").write_text("Y = 4\n")
        _, out = self.checks("--base", self.base, **self.fake_env(0, "0 vi phạm mới\n"))
        self.assertEqual([c.split()[0] for c in self.calls()], ["check"], out)
        self.assertIn("TM-114", out)


class OnlyProjectRulesAreGuarded(GuardBase):
    """Bạn chọn 14/11/2026: chỉ chặn `.arch/` của project (gốc repo, hay gốc có luật gần nhất với thư mục đang làm);
    fixture lồng như `examples/shop/.arch` của repo archctl thì agent sửa được."""

    def setUp(self):
        super().setUp()
        for rel in (".arch/system.arch", "examples/shop/.arch/system.arch"):
            path = self.project / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(RULES)
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "fixture")

    def write(self, rel, cwd):
        out = self.hook("pretool_guard.py", {"session_id": "f1", "cwd": str(cwd), "tool_name": "Write",
                                             "hook_event_name": "PreToolUse",
                                             "tool_input": {"file_path": str(self.project / rel), "content": "x"}})
        return out["hookSpecificOutput"]["permissionDecision"] if out else None

    def test_nested_fixture_is_editable_but_project_rules_are_not(self):
        self.assertIsNone(self.write("examples/shop/.arch/system.arch", self.project))
        self.assertIsNone(self.bash("sed -i '' s/deny/allow/ examples/shop/.arch/system.arch"))
        self.assertEqual(self.write(".arch/system.arch", self.project), "deny")
        self.assertEqual(self.write(".arch/system.arch", self.project / "examples" / "shop"), "deny")
        self.assertEqual(self.write("examples/shop/.arch/system.arch", self.project / "examples" / "shop"), "deny",
                         "đang làm trong project con có luật riêng: luật đó được chặn")


class MonorepoSubdirRules(ArchHookBase):
    """Review lại phần sửa (sonnet·high): `.arch` chỉ ở `svc/` của monorepo phải được chặn khi agent làm ở gốc repo,
    và dấu cây làm việc phải tính đường dẫn từ gốc repo (không phải từ `svc/`)."""

    def setUp(self):
        super().setUp()
        self.svc = self.project / "svc"
        (self.svc / "app" / "web").mkdir(parents=True)
        (self.svc / ".arch").mkdir()
        (self.svc / ".arch" / "system.arch").write_text(RULES)
        (self.project / ".arch" / "system.arch").unlink()  # chỉ còn luật trong svc/
        (self.svc / "app" / "web" / "view.py").write_text("Y = 2\n")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "monorepo")

    def test_subdir_rules_are_guarded_from_repo_root(self):
        out = self.guard("Write", {"file_path": str(self.svc / ".arch" / "system.arch"), "content": "x"})
        self.assertEqual(out[0], "deny")
        self.assertEqual(self.bash("sed -i '' s/deny/allow/ svc/.arch/system.arch")[0], "deny")

    def test_rewriting_an_already_dirty_file_is_checked_again(self):
        view = self.svc / "app" / "web" / "view.py"
        view.write_text("from app.report.data import X\n")
        env = self.fake_env(1, VIOLATION)
        self.start("làm tiếp", "d1")
        self.post("Bash", {"command": "make gen"}, "d1", **env)
        self.assertEqual(len(self.calls()), 1)
        self.post("Bash", {"command": "ls"}, "d1", **env)
        self.assertEqual(len(self.calls()), 1, "không đổi gì: không gọi lại")
        view.write_text("from app.report.data import X\nZ = 1\n")  # file đã dirty, ghi tiếp
        self.post("Bash", {"command": "make gen"}, "d1", **env)
        self.assertEqual(len(self.calls()), 2, "ghi lại file đã dirty phải đổi dấu và gọi archctl")


class RoundThreeFixes(ArchHookBase):
    """Review lại vòng 2 (sonnet·high): tạo `.arch` lồng mới lách được phần chặn; archctl quá hạn mà dấu cây vẫn ghi
    như đã kiểm; hai service trùng đường dẫn che khối của nhau."""

    def test_creating_a_new_nested_rule_set_is_blocked(self):
        out = self.guard("Write", {"file_path": str(self.project / "svc2" / ".arch" / "system.arch"), "content": ""})
        self.assertEqual(out[0], "deny")
        self.assertEqual(self.bash("mkdir -p svc2/.arch && echo '' > svc2/.arch/system.arch")[0], "deny")

    def test_timed_out_check_is_retried_on_the_next_bash(self):
        self.start("làm tiếp", "t1")
        (self.project / "app" / "web" / "view.py").write_text("from app.report.data import X\n")
        self.assertEqual(self.post("Bash", {"command": "make gen"}, "t1",
                                   **self.fake_env(1, VIOLATION, FAKE_ARCH_SLEEP="5")), "")
        again = self.post("Bash", {"command": "ls"}, "t1", **self.fake_env(1, VIOLATION))
        self.assertIn("✗ VI PHẠM  Web -> Report", again, "lần trước quá hạn: cây không đổi vẫn phải kiểm lại")

    def test_same_violation_text_in_two_services_is_reported_for_each(self):
        for svc in ("svc", "other"):
            base = self.project / svc
            (base / ".arch").mkdir(parents=True)
            (base / ".arch" / "system.arch").write_text(RULES)
            (base / "app" / "web").mkdir(parents=True)
            (base / "app" / "web" / "view.py").write_text("Y = 2\n")
        git(self.project, "add", "-A")
        git(self.project, "commit", "-q", "-m", "two services")
        self.start("làm tiếp", "s1")
        env = self.fake_env(1, VIOLATION)
        first = self.project / "svc" / "app" / "web" / "view.py"
        first.write_text("from app.report.data import X\n")
        self.assertIn("✗ VI PHẠM", self.post("Edit", {"file_path": str(first), "new_string": "from app"}, "s1", **env))
        second = self.project / "other" / "app" / "web" / "view.py"
        second.write_text("from app.report.data import X\n")
        self.assertIn("✗ VI PHẠM", self.post("Bash", {"command": "make gen"}, "s1", **env),
                      "khối ở service khác không bị coi là đã báo")
