"""Biên nhận kiểm tra (session-keeper/scripts/receipt.py) và cách progress dùng nó."""
import json
import os
import subprocess
import sys

from tests._util import PLUGIN, TempDirTestCase, git, run_script

RECEIPT = PLUGIN / "skills" / "session-keeper" / "scripts" / "receipt.py"
sys.path.insert(0, str(PLUGIN / "lib"))
sys.path.insert(0, str(PLUGIN / "skills" / "progress" / "scripts"))
import agentstack as A  # noqa: E402
import collect  # noqa: E402

PASS = "import sys; print('Ran 3 tests'); print('OK')"
FAIL = "import sys; print('FAILED (failures=1)'); sys.exit(1)"


class Base(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.state = self.tmp / "state"
        os.environ["AGENT_STACK_STATE"] = str(self.state)
        self.addCleanup(os.environ.pop, "AGENT_STACK_STATE", None)
        self.repo = self.tmp / "proj"
        self.repo.mkdir()
        self.write("proj/app.py", "print('v1')\n")
        self.write("proj/.gitignore", "build/\n")
        self.write("proj/PLAN.md", "# Kế hoạch\n\n## 0. Đang ở đâu, việc tiếp theo\n*Cập nhật 01/10/2026.*\n- **Đang dở:** không có.\n")
        git(self.repo, "init", "-q")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "init")

    def receipt(self, *args):
        return run_script(RECEIPT, *args, env={"AGENT_STACK_STATE": str(self.state)})


class Fingerprint(Base):
    def test_depends_on_content_not_on_commits(self):
        first = A.tree_fingerprint(self.repo)
        self.assertTrue(first)
        self.write("proj/app.py", "print('v2')\n")
        edited = A.tree_fingerprint(self.repo)
        self.assertNotEqual(first, edited)
        git(self.repo, "commit", "-qam", "v2")
        self.assertEqual(A.tree_fingerprint(self.repo), edited)  # commit không đổi nội dung

    def test_new_and_deleted_files_count_but_ignored_files_do_not(self):
        base = A.tree_fingerprint(self.repo)
        self.write("proj/build/out.bin", "x")
        self.assertEqual(A.tree_fingerprint(self.repo), base)
        self.write("proj/new.py", "x = 1\n")
        with_new = A.tree_fingerprint(self.repo)
        self.assertNotEqual(with_new, base)
        (self.repo / "new.py").unlink()
        (self.repo / "app.py").unlink()
        self.assertNotIn(A.tree_fingerprint(self.repo), (base, with_new))

    def test_not_a_git_repo(self):
        plain = self.tmp / "plain"
        plain.mkdir()
        self.assertIsNone(A.tree_fingerprint(plain))


class ReceiptCli(Base):
    def test_pass_and_fail_are_recorded_with_exit_code(self):
        out = self.receipt("run", "--project", str(self.repo), "--label", "unit", "--", sys.executable, "-c", PASS)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Ran 3 tests", out.stdout)
        self.assertIn("✓ đạt", out.stdout)
        out = self.receipt("run", "--project", str(self.repo), "--label", "lint", "--", sys.executable, "-c", FAIL)
        self.assertEqual(out.returncode, 1)
        data = json.loads(A.receipt_path(self.repo).read_text(encoding="utf-8"))
        self.assertTrue(data["checks"]["unit"]["ok"])
        self.assertFalse(data["checks"]["lint"]["ok"])
        self.assertEqual(data["checks"]["lint"]["summary"], "FAILED (failures=1)")
        self.assertEqual(data["checks"]["unit"]["fingerprint"], A.tree_fingerprint(self.repo))

    def test_show_reports_stale_results_after_edit(self):
        self.receipt("run", "--project", str(self.repo), "--label", "unit", "--", sys.executable, "-c", PASS)
        self.assertIn("còn khớp code hiện tại", self.receipt("show", "--project", str(self.repo)).stdout)
        self.write("proj/app.py", "print('v3')\n")
        self.assertIn("code đã đổi", self.receipt("show", "--project", str(self.repo)).stdout)

    def test_editing_docs_after_the_run_keeps_the_result_current(self):
        # Cập nhật §0, thêm README sau bước kiểm: show khớp hook Stop (code_fresh), không đòi chạy lại.
        self.receipt("run", "--project", str(self.repo), "--label", "unit", "--", sys.executable, "-c", PASS)
        self.write("proj/PLAN.md", "# Kế hoạch\n\n## 0. Đang ở đâu, việc tiếp theo\n- **Xong:** unit đạt.\n")
        self.write("proj/README.md", "# Proj\n")
        out = self.receipt("show", "--project", str(self.repo)).stdout
        self.assertIn("còn khớp code hiện tại (sau đó chỉ tài liệu đổi)", out)
        self.assertNotIn("code đã đổi", out)
        rec = A.receipt_status(self.repo)["unit"]
        self.assertEqual((rec["fresh"], rec["code_fresh"], rec["current"]), (False, True, True))
        self.write("proj/app.py", "print('v3')\n")
        self.assertIn("code đã đổi", self.receipt("show", "--project", str(self.repo)).stdout)
        self.assertIs(A.receipt_status(self.repo)["unit"]["current"], False)

    def test_old_receipt_without_code_fingerprint_still_uses_the_whole_tree(self):
        self.receipt("run", "--project", str(self.repo), "--label", "unit", "--", sys.executable, "-c", PASS)
        path = A.receipt_path(self.repo)
        data = json.loads(path.read_text(encoding="utf-8"))
        del data["checks"]["unit"]["code_fingerprint"]
        path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("còn khớp code hiện tại", self.receipt("show", "--project", str(self.repo)).stdout)
        self.write("proj/PLAN.md", "# Kế hoạch\n\n## 0. Đang ở đâu, việc tiếp theo\n- **Xong:** unit đạt.\n")
        self.assertIn("code đã đổi", self.receipt("show", "--project", str(self.repo)).stdout)
        rec = A.receipt_status(self.repo)["unit"]
        self.assertEqual((rec["code_fresh"], rec["current"]), (None, False))

    def test_missing_command_and_timeout(self):
        out = self.receipt("run", "--project", str(self.repo), "--", "lenh-khong-ton-tai-xyz")
        self.assertEqual(out.returncode, 127)
        out = self.receipt("run", "--project", str(self.repo), "--timeout", "1", "--",
                           sys.executable, "-c", "import time; time.sleep(5)")
        self.assertEqual(out.returncode, 124)
        self.assertIn("dừng sau", out.stdout)

    def test_requires_a_command(self):
        out = self.receipt("run", "--project", str(self.repo))
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("thiếu lệnh", out.stderr)


class ForgetAndPrune(Base):
    def labels(self):
        return set(json.loads(A.receipt_path(self.repo).read_text(encoding="utf-8"))["checks"])

    def test_forget_by_label(self):
        self.receipt("run", "--project", str(self.repo), "--label", "unit", "--", sys.executable, "-c", PASS)
        self.receipt("run", "--project", str(self.repo), "--label", "lint", "--", sys.executable, "-c", FAIL)
        out = self.receipt("forget", "--project", str(self.repo), "lint", "khong-co")
        self.assertEqual(out.returncode, 1)
        self.assertIn("Đã xoá biên nhận: lint", out.stdout)
        self.assertIn("Các tên hiện có: unit", out.stdout)
        self.assertEqual(self.labels(), {"unit"})
        self.assertEqual(self.receipt("forget", "--project", str(self.repo), "unit").returncode, 0)
        self.assertFalse(A.receipt_path(self.repo).exists())
        self.assertIn("Chưa có biên nhận", self.receipt("show", "--project", str(self.repo)).stdout)

    def test_prune_drops_failing_runs_of_deleted_tests_only(self):
        self.write("proj/tests/__init__.py", "")
        self.write("proj/tests/test_ok.py", "import unittest\nclass T(unittest.TestCase):\n    def test_a(self):\n        pass\n")
        run = lambda label, *cmd: self.receipt("run", "--project", str(self.repo), "--label", label, "--", *cmd)
        run("gone", sys.executable, "-m", "unittest", "tests.test_ok", "tests.test_da_xoa")      # trượt: module mất
        run("kept-pass", sys.executable, "-m", "unittest", "tests.test_ok.T.test_a")            # đạt
        run("kept-fail", sys.executable, "-c", FAIL)                                            # trượt nhưng không phải test
        run("gone-pytest", "pytest", "tests/test_da_xoa.py::test_x")                            # trượt (127 hay lỗi)
        dry = self.receipt("prune", "--project", str(self.repo), "--dry-run")
        self.assertIn("Sẽ xoá biên nhận: gone (không còn: tests.test_da_xoa)", dry.stdout)
        self.assertEqual(len(self.labels()), 4)
        out = self.receipt("prune", "--project", str(self.repo))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(self.labels(), {"kept-pass", "kept-fail"})
        self.assertIn("Không có biên nhận nào", self.receipt("prune", "--project", str(self.repo)).stdout)


class MissingTargets(Base):
    """Nhận diện test đã xoá phải thận trọng: không chắc thì không xoá, để không che một test đang trượt thật."""

    def setUp(self):
        super().setUp()
        import importlib.util
        spec = importlib.util.spec_from_file_location("receipt_mod", RECEIPT)
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        self.write("proj/tests/__init__.py", "")
        self.write("proj/tests/test_a.py", "")

    def miss(self, *cmd):
        return self.mod.missing_targets(self.repo, ["python3", *cmd])

    def test_detects_deleted_modules_and_files(self):
        self.assertEqual(self.miss("-m", "unittest", "-v", "tests.test_a", "tests.test_gone"), ["tests.test_gone"])
        self.assertEqual(self.miss("-m", "pytest", "-q", "tests/test_gone.py::test_x"), ["tests/test_gone.py::test_x"])
        self.assertEqual(self.mod.missing_targets(self.repo, ["pytest", "tests/test_gone.py"]), ["tests/test_gone.py"])

    def test_keeps_when_unsure(self):
        cases = [
            ("-m", "unittest", "tests.test_a.T.test_x"),                       # lớp và hàm trong file còn
            ("-m", "unittest", "discover", "-s", "tests", "-p", "test_a.py"),  # discover theo pattern
            ("-m", "unittest", "-k", "T.test_x", "tests.test_a"),              # giá trị của -k
            ("-m", "unittest", "pkg_installed.mod"),                           # gói ngoài project
            ("-m", "pytest", "--junitxml", "reports/j.xml", "tests/test_a.py"),
            ("-m", "pytest", "-k", "a/b", "tests/test_a.py"),
            ("-m", "pytest", "other/test_x.py"),                               # thư mục không có trong project
            ("-m", "pytest", "tests", "--ignore", "tests/test_old.py"),        # file bị loại khỏi lần chạy
            ("-c", "print('unittest a.b')"),
        ]
        for cmd in cases:
            self.assertEqual(self.miss(*cmd), [], cmd)
        self.assertEqual(self.mod.missing_targets(self.repo, ["echo", "unittest", "a.b"]), [])
        for bad in (None, "zz", [1, 2], []):
            self.assertEqual(self.mod.missing_targets(self.repo, bad), [])

    def test_corrupt_receipt_file_does_not_crash(self):
        path = A.receipt_path(self.repo)
        path.parent.mkdir(parents=True, exist_ok=True)
        for raw in ("[1, 2]", '{"checks": ["ab"]}', '{"checks": 5}', '{"checks": {"x": null, "y": "s"}}', "khong-phai-json"):
            path.write_text(raw, encoding="utf-8")
            for args in (("prune",), ("forget", "x")):
                out = self.receipt(*args, "--project", str(self.repo))
                self.assertEqual(out.stderr, "", (raw, args))

    def test_forget_with_repeated_label(self):
        self.receipt("run", "--project", str(self.repo), "--label", "lint", "--", sys.executable, "-c", FAIL)
        out = self.receipt("forget", "--project", str(self.repo), "lint", "lint")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.count("Đã xoá biên nhận: lint"), 1)


class TienDoUsesReceipts(Base):
    def run_check(self, code):
        self.receipt("run", "--project", str(self.repo), "--label", "unit", "--", sys.executable, "-c", code)

    def actions(self):
        return [(a["tier"], a["text"]) for a in collect.collect(self.repo, scan_todos=False)["actions"]]

    def test_failing_check_is_a_blocker(self):
        self.run_check(FAIL)
        self.assertIn((1, "Sửa kiểm tra đang trượt `unit`: FAILED (failures=1)"), self.actions())
        self.write("proj/app.py", "print('đã sửa')\n")
        self.assertTrue(any(t == 1 and "Chạy lại kiểm tra `unit`" in x for t, x in self.actions()))
        # Biên nhận trượt cũ (lệnh đã bỏ, chạy sai thư mục) chỉ cách gỡ, để không kẹt ở "Chặn đường" mãi.
        stale = [a for a in collect.collect(self.repo, scan_todos=False)["actions"] if a["tier"] == 1][0]
        self.assertIn("receipt.py forget", stale["text"])
        if stale.get("route"):
            self.assertNotEqual(stale["route"]["rule"], "debug-hard")  # lời chỉ cách gỡ không đổi định tuyến

    def test_old_pass_does_not_prove_new_code(self):
        self.run_check(PASS)
        self.assertFalse(any("kiểm tra" in x.lower() for _, x in self.actions()))
        self.assertIn("còn khớp code hiện tại", collect.render_md(collect.collect(self.repo, scan_todos=False)))
        self.write("proj/app.py", "print('v4')\n")
        self.assertIn((3, "Chạy lại mốc kiểm tra: `unit`"), self.actions())

    def test_docs_edit_after_the_run_is_not_a_code_change(self):
        # progress và cây kế hoạch dùng cùng cờ current với receipt.py show và hook Stop.
        import plan_tree
        self.run_check(PASS)
        self.write("proj/PLAN.md", "# Kế hoạch\n\n## 0. Đang ở đâu, việc tiếp theo\n- **Xong:** unit đạt.\n")
        self.assertFalse(any("kiểm tra" in x.lower() for _, x in self.actions()))
        self.assertIn("còn khớp code hiện tại", collect.render_md(collect.collect(self.repo, scan_todos=False)))
        self.run_check(FAIL)
        self.write("proj/README.md", "# Proj\n")
        self.assertIn((1, "Sửa kiểm tra đang trượt `unit`: FAILED (failures=1)"), self.actions())
        self.assertIn("code chưa đổi từ lần trượt", plan_tree.failing_checks(self.repo)[0])
        self.write("proj/app.py", "print('đã sửa')\n")
        self.assertIn("code đã đổi sau lần trượt", plan_tree.failing_checks(self.repo)[0])

    def test_session_start_brief_shows_failing_check(self):
        self.run_check(FAIL)
        brief = collect.brief(self.repo)
        self.assertIn("Chặn đường: Sửa kiểm tra đang trượt", brief["context"])


class FailsBefore(TempDirTestCase):
    """Cải tiến 4 (04/11/2026): bằng chứng test bắt được lỗi, kiểu FAIL_TO_PASS của SWE-bench."""

    BUGGY = "def add(a, b):\n    return a - b\n"
    FIXED = "def add(a, b):\n    return a + b\n"
    CATCHES = "import unittest\nfrom calc import add\n\n\nclass T(unittest.TestCase):\n" \
              "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n"
    MISSES = CATCHES.replace("add(2, 3), 5", "add(0, 0), 0")
    CMD = ("--", sys.executable, "-m", "unittest", "test_calc")

    def setUp(self):
        super().setUp()
        self.state = self.tmp / "state"
        self.repo = self.tmp / "proj"
        self.repo.mkdir()
        (self.repo / "calc.py").write_text(self.BUGGY)
        (self.repo / ".gitignore").write_text("local_cfg.py\n")
        git(self.repo, "init", "-q")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "init")

    def receipt(self, *args):
        return run_script(RECEIPT, "fails-before", "--project", str(self.repo), *args,
                          env={"AGENT_STACK_STATE": str(self.state)})

    def checks(self):
        os.environ["AGENT_STACK_STATE"] = str(self.state)
        self.addCleanup(os.environ.pop, "AGENT_STACK_STATE", None)
        return A.receipt_status(A.project_root(self.repo))

    def snapshot(self):
        files = {p.relative_to(self.repo).as_posix(): p.read_bytes() for p in self.repo.rglob("*")
                 if p.is_file() and ".git" not in p.relative_to(self.repo).parts}
        return files, git(self.repo, "status", "--porcelain")

    def leftovers(self):
        import tempfile
        from pathlib import Path
        return set(Path(tempfile.gettempdir()).glob("receipt-fails-before-*"))

    def fix_with(self, test):
        (self.repo / "calc.py").write_text(self.FIXED)
        (self.repo / "test_calc.py").write_text(test)

    def test_test_that_catches_the_bug(self):
        self.fix_with(self.CATCHES)
        before, temps = self.snapshot(), self.leftovers()
        out = self.receipt(*self.CMD)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("test bắt được lỗi", out.stdout)
        self.assertIn("trước bản sửa (commit", out.stdout)
        self.assertEqual(self.snapshot(), before, "thư mục làm việc không đổi")
        self.assertEqual(self.leftovers(), temps, "thư mục tạm đã bị xóa")
        rec = next(iter(self.checks().values()))
        self.assertEqual((rec["ok"], rec["kind"], rec["tests"], rec["before_exit"], rec["after_exit"]),
                         (True, "fails-before", ["test_calc.py"], 1, 0))
        self.assertTrue(rec["fresh"])

    def test_test_that_passes_on_the_old_code_too(self):
        self.fix_with(self.MISSES)
        out = self.receipt(*self.CMD)
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertIn("test không bắt được lỗi", out.stdout)
        self.assertFalse(next(iter(self.checks().values()))["ok"])

    def test_missing_environment_is_inconclusive_until_linked(self):
        # Lệnh cần file bị git bỏ qua (như .venv): thiếu trong thư mục tạm thì không được tính là bằng chứng.
        (self.repo / "local_cfg.py").write_text("FACTOR = 1\n")
        self.fix_with("import local_cfg\n" + self.CATCHES)
        out = self.receipt(*self.CMD)
        self.assertEqual(out.returncode, 2, out.stdout + out.stderr)
        self.assertIn("không kết luận được", out.stdout)
        out = self.receipt("--link", "local_cfg.py", *self.CMD)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual((self.repo / "local_cfg.py").read_text(), "FACTOR = 1\n")

    def test_link_must_be_an_ignored_path_inside_the_project(self):
        self.fix_with(self.CATCHES)
        for link in ("calc.py", "../state", "khong-co"):
            with self.subTest(link=link):
                out = self.receipt("--link", link, *self.CMD)
                self.assertEqual(out.returncode, 2, out.stdout)
                self.assertIn("--link", out.stdout)

    def test_no_repo_command_hook_or_filter_runs(self):
        marks = {name: self.tmp / name for name in ("fsmonitor", "clean", "smudge", "hook")}
        (self.repo / ".gitattributes").write_text("*.py filter=x\n")
        git(self.repo, "add", ".gitattributes")
        git(self.repo, "commit", "-q", "-m", "thuộc tính")
        git(self.repo, "config", "core.fsmonitor", f"touch {marks['fsmonitor']}; false")
        git(self.repo, "config", "filter.x.clean", f"sh -c 'touch {marks['clean']}; cat'")
        git(self.repo, "config", "filter.x.smudge", f"sh -c 'touch {marks['smudge']}; cat'")
        hook = self.repo / ".git" / "hooks" / "post-checkout"
        hook.write_text(f"#!/bin/sh\ntouch {marks['hook']}\n")
        hook.chmod(0o755)
        self.fix_with(self.CATCHES)
        out = self.receipt(*self.CMD)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual([n for n, m in marks.items() if m.exists()], [])

    def test_symlink_in_the_old_tree_never_leads_outside(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        (self.repo / "escape").symlink_to(outside)
        git(self.repo, "add", "escape")
        git(self.repo, "commit", "-q", "-m", "symlink")
        (self.repo / "escape").unlink()
        (self.repo / "escape").mkdir()
        (self.repo / "escape" / "test_x.py").write_text("x = 1\n")
        (self.repo / "calc.py").write_text(self.FIXED)
        out = self.receipt(*self.CMD)
        self.assertEqual(out.returncode, 2, out.stdout)
        self.assertIn("symlink", out.stdout)
        self.assertEqual(list(outside.iterdir()), [])

    def test_unexpected_errors_exit_2_not_1(self):
        # Differential review 04/11/2026: object git thiếu làm script văng KeyError, thoát 1 như "test yếu".
        self.fix_with(self.CATCHES)
        blob = git(self.repo, "rev-parse", "HEAD:calc.py").strip()
        (self.repo / ".git" / "objects" / blob[:2] / blob[2:]).unlink()
        out = self.receipt(*self.CMD)
        self.assertEqual(out.returncode, 2, out.stdout + out.stderr)
        self.assertIn("thiếu object git", out.stdout)

    def test_failing_only_on_a_missing_name_is_not_proof(self):
        # Reviewer 04/11/2026: bản sửa thêm hàm mới, test chỉ import nó; trước bản sửa trượt vì ImportError.
        (self.repo / "calc.py").write_text(self.FIXED + "\n\ndef helper():\n    return 1\n")
        (self.repo / "test_calc.py").write_text(
            "import unittest\nfrom calc import helper\n\n\nclass T(unittest.TestCase):\n"
            "    def test_h(self):\n        self.assertTrue(callable(helper))\n")
        out = self.receipt(*self.CMD)
        self.assertEqual(out.returncode, 2, out.stdout)
        self.assertIn("không phải ở assert", out.stdout)
        self.assertIn("cannot import name", out.stdout)

    def test_command_missing_on_the_old_tree_is_not_proof(self):
        (self.repo / "calc.py").write_text(self.FIXED)
        (self.repo / "test_calc.py").write_text(self.MISSES)
        script = self.repo / "runtests.sh"
        script.write_text(f"#!/bin/sh\nexec {sys.executable} -m unittest test_calc\n")
        script.chmod(0o755)
        out = self.receipt("--", "./runtests.sh")
        self.assertEqual(out.returncode, 2, out.stdout)
        self.assertIn("không tìm thấy lệnh", out.stdout)

    def src_layout(self):
        (self.repo / "src" / "pkg").mkdir(parents=True)
        (self.repo / "src" / "pkg" / "__init__.py").write_text(self.BUGGY)
        (self.repo / ".gitignore").write_text("local_cfg.py\n.venv/\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "src")
        (self.repo / "src" / "pkg" / "__init__.py").write_text(self.FIXED)
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "test_pkg.py").write_text(self.CATCHES.replace("from calc import", "from pkg import"))

    def test_environment_loading_the_real_code_is_not_called_a_weak_test(self):
        # Reviewer 04/11/2026: PYTHONPATH hay pip install -e trỏ về thư mục làm việc, nên phía trước bản sửa chạy
        # code đã sửa; script không được kết luận "test không bắt được lỗi" (agent sẽ sửa hỏng một test đúng).
        self.src_layout()
        cmd = ("--", sys.executable, "-m", "unittest", "discover", "-s", "tests")
        out = run_script(RECEIPT, "fails-before", "--project", str(self.repo), *cmd,
                         env={"AGENT_STACK_STATE": str(self.state), "PYTHONPATH": str(self.repo / "src")})
        self.assertEqual(out.returncode, 2, out.stdout)
        self.assertIn("PYTHONPATH", out.stdout)
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(self.repo / ".venv")], check=True)
        site = next((self.repo / ".venv" / "lib").glob("python3*/site-packages"))
        (site / "__editable__.pkg.pth").write_text(str(self.repo.resolve() / "src") + "\n")
        out = self.receipt("--link", ".venv", "--", ".venv/bin/python", "-m", "unittest", "discover", "-s", "tests")
        self.assertEqual(out.returncode, 2, out.stdout)
        self.assertRegex(out.stdout, r"sys\.path của \.venv/bin/python có|trỏ về thư mục làm việc")

    def test_missing_attribute_or_name_is_not_proof_either(self):
        # Reviewer vòng 2 (04/11/2026): cách viết thứ hai của lỗi "thiếu tên mới" (AttributeError), và lỗi build.
        sys.path.insert(0, str(RECEIPT.parent))
        import fails_before as FB
        for out in ("AttributeError: module 'calc' has no attribute 'helper'\nFAILED (errors=1)",
                    "NameError: name 'helper' is not defined", "./calc.go:3:2: undefined: Helper\nFAIL\tpkg [build failed]",
                    "error[E0432]: unresolved import `crate::helper`", "ImportError: cannot import name 'ExpectedResult'",
                    "ModuleNotFoundError: No module named 'assert.helpers'"):
            with self.subTest(out=out[:40]):
                self.assertEqual(FB.verdict(1, 0, out)[0], 2)
        for out in ("FAIL: test_add\nAssertionError: 1 != 5", "E       assert 1 == 5", "--- FAIL: TestAdd",
                    "thread 'add' panicked at src/lib.rs:3", "    Expected: 5\n    Received: -1"):
            with self.subTest(out=out[:40]):
                self.assertEqual(FB.verdict(1, 0, out)[0], 0)

    def test_paths_are_compared_after_symlinks_and_by_folder(self):
        sys.path.insert(0, str(RECEIPT.parent))
        import fails_before as FB
        (self.tmp / "lnk").symlink_to(self.repo)
        sibling = self.tmp / "proj2"
        sibling.mkdir()
        cwd = self.tmp
        self.assertTrue(FB.env_points_home(self.repo, [], cwd, {"PYTHONPATH": str(self.tmp / "lnk" / "src")})[0])
        self.assertIsNone(FB.env_points_home(self.repo, [], cwd, {"PYTHONPATH": str(sibling)})[0],
                          "/proj2 không nằm trong /proj")

    def test_wrapped_commands_are_probed_through_the_shebang_or_flagged(self):
        self.src_layout()
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(self.repo / ".venv")], check=True)
        site = next((self.repo / ".venv" / "lib").glob("python3*/site-packages"))
        (site / "__editable__.pkg.pth").write_text(str(self.repo.resolve() / "src") + "\n")
        runner = self.repo / ".venv" / "bin" / "runtests"
        runner.write_text(f"#!{self.repo / '.venv' / 'bin' / 'python'}\nimport sys, unittest\n"
                          "unittest.main(module=None, argv=['runtests', 'discover', '-s', 'tests'])\n")
        runner.chmod(0o755)
        out = self.receipt("--link", ".venv", "--", ".venv/bin/runtests")
        self.assertEqual(out.returncode, 2, out.stdout)
        self.assertIn("trỏ về thư mục làm việc", out.stdout)
        out = self.receipt("--link", ".venv", "--", "sh", "-c", ".venv/bin/runtests")
        self.assertEqual(out.returncode, 1, out.stdout)
        self.assertIn("không dò được môi trường", out.stdout)

    def test_venv_inside_the_repo_linked_in_still_reports_a_weak_test(self):
        # Reviewer vòng 3 (04/11/2026): site-packages của chính .venv được link bị coi là "trỏ về thư mục làm việc",
        # nên test yếu ra mã 2 thay vì 1 với cách đặt venv phổ biến nhất.
        (self.repo / ".gitignore").write_text("local_cfg.py\n.venv/\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "ignore venv")
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(self.repo / ".venv")], check=True)
        self.fix_with(self.MISSES)
        out = self.receipt("--link", ".venv", "--", ".venv/bin/python", "-m", "unittest", "test_calc")
        self.assertEqual(out.returncode, 1, out.stdout)
        self.assertIn("test không bắt được lỗi", out.stdout)

    def test_unsafe_paths_are_refused(self):
        sys.path.insert(0, str(RECEIPT.parent))
        import fails_before as FB
        for rel in ("../x", "/etc/x", "a/../../x", ".git/config"):
            with self.subTest(rel=rel), self.assertRaises(FB.Problem):
                FB.safe_parent(self.tmp, rel)

    def test_fix_already_committed_needs_base(self):
        self.fix_with(self.CATCHES)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "sửa")
        out = self.receipt(*self.CMD)
        self.assertEqual(out.returncode, 2, out.stdout)
        self.assertIn("--base", out.stdout)
        out = self.receipt("--base", "HEAD~1", *self.CMD)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_bad_input_is_explained(self):
        self.assertIn("--base", self.receipt(*self.CMD).stdout)  # chưa đổi gì: bản sửa có thể đã commit
        (self.repo / "calc.py").write_text(self.FIXED)
        self.assertIn("không thấy file test", self.receipt(*self.CMD).stdout)  # sửa code mà chưa có test
        self.fix_with(self.CATCHES)
        self.assertIn("không tìm thấy commit", self.receipt("--base", "khong-co", *self.CMD).stdout)
        plain = self.tmp / "plain"
        plain.mkdir()
        out = run_script(RECEIPT, "fails-before", "--project", str(plain), *self.CMD,
                         env={"AGENT_STACK_STATE": str(self.state)})
        self.assertEqual(out.returncode, 2)
        self.assertIn("không phải git repo", out.stdout)
