"""Bộ test thu hẹp `narrow.py` (việc F1a, TM-156–160): chọn đúng test chạm dòng đổi, rơi về chạy rộng hơn khi không
chắc, chặn tên file và ref lạ, và biên nhận thu hẹp không thay biên nhận cả bộ (receipt.py, hook Stop)."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from unittest import mock

from tests._util import PLUGIN, TempDirTestCase, git

NARROW = PLUGIN / "skills" / "session-keeper" / "scripts" / "narrow.py"
RECEIPT = PLUGIN / "skills" / "session-keeper" / "scripts" / "receipt.py"

CALC = """LIMIT = 10


def add(a, b):
    # cộng
    return a + b


def mul(a, b):
    total = 0
    for _ in range(b):
        total += a
    return total
"""
TEST_ADD = """import unittest
from pkg import calc


class T(unittest.TestCase):
    def test_add(self):
        self.assertEqual(calc.add(1, 2), 3)
"""
TEST_MUL = """import json, subprocess, sys, unittest
from pathlib import Path
from pkg import calc


class T(unittest.TestCase):
    def test_mul(self):
        self.assertEqual(calc.mul(2, 3), 6)

    def test_data(self):
        self.assertEqual(json.loads(Path("pkg/data.json").read_text())["k"], 1)
        self.assertIn("name", Path("plugin/SKILL.md").read_text())
        self.assertIn("hooks", json.loads(Path("plugin/hooks.json").read_text()))

    def test_child(self):
        out = subprocess.run([sys.executable, "-c", "from pkg import calc; print(calc.add(2, 2))"],
                             capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "4")
"""
# test_b chỉ đạt khi test_a chạy trước trong cùng tiến trình
TEST_ORDER = """import subprocess, sys, unittest
from pkg import calc

STATE = []


class T(unittest.TestCase):
    def test_a(self):
        STATE.append(calc.LIMIT)

    def test_b(self):
        self.assertEqual(STATE, [10])
        self.assertEqual(calc.mul(1, 1), 1)
        subprocess.run([sys.executable, "-c", "import pkg.side"], check=True)
"""
# Module không chạm gì của pkg: giữ số test chọn dưới ngưỡng chạy cả bộ (70%)
TEST_FILLER = """import unittest


class T(unittest.TestCase):
""" + "".join(f"    def test_f{i}(self):\n        pass\n\n" for i in range(6))
TEST_TOOL = """import subprocess, unittest


class T(unittest.TestCase):
    def test_lists_repo(self):
        out = subprocess.run(["git", "ls-files"], capture_output=True, text=True)
        self.assertIn("pkg/calc.py", out.stdout)
"""


class NarrowBase(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.state = self.tmp / "state"
        self.state.mkdir()
        self.proj = self.tmp / "proj"
        self.env = {"AGENT_STACK_STATE": str(self.state)}

    def build(self, order=False, tool=False, extra=None):
        files = {"pkg/__init__.py": "", "pkg/calc.py": CALC, "pkg/data.json": '{"k": 1}\n',
                 "plugin/SKILL.md": "---\nname: x\n---\n", "plugin/hooks.json": '{"hooks": {}}\n',
                 "plugin/rulebook.json": "{}\n", "README.md": "đọc tôi\n", "tests/__init__.py": "",
                 "tests/test_add.py": TEST_ADD, "tests/test_mul.py": TEST_MUL, "tests/test_filler.py": TEST_FILLER}
        if order:
            files["tests/test_order.py"] = TEST_ORDER
            files["pkg/side.py"] = "X = 1\n"
        if tool:
            files["tests/test_tool.py"] = TEST_TOOL
        files.update(extra or {})
        for rel, text in files.items():
            self.put(rel, text)
        git(self.proj, "init", "-q")
        self.commit("init")

    def put(self, rel, text):
        path = self.proj / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self, msg):
        git(self.proj, "add", "-A")
        git(self.proj, "commit", "-qm", msg)

    def narrow(self, *args, timeout=120):
        env = dict(os.environ, **self.env)
        return subprocess.run([sys.executable, str(NARROW), *args], cwd=str(self.proj), capture_output=True,
                              text=True, env=env, timeout=timeout, stdin=subprocess.DEVNULL)

    def record(self):
        out = self.narrow("record", "--jobs", "2")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        return out

    def plan(self, *args):
        out = self.narrow("run", "--json", *args)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        return json.loads(out.stdout)

    def reasons(self, plan) -> str:
        return " | ".join(plan["reasons"] + [f"{f}: {why}" for f, why, _ in plan["items"]])

    def map_file(self) -> Path:
        files = list((self.state / "narrow").glob("*.json"))
        self.assertEqual(len(files), 1)
        return files[0]


class FileSelection(NarrowBase):
    """Chọn theo file: đổi dòng nào cũng chọn mọi test của các module test đã nạp file."""

    def setUp(self):
        super().setUp()
        self.build()
        self.record()

    def test_body_change_selects_every_module_that_loaded_the_file(self):
        self.put("pkg/calc.py", CALC.replace("return a + b", "return b + a"))
        plan = self.plan()
        self.assertEqual(plan["mode"], "narrow")
        self.assertEqual(sorted(plan["names"]), ["tests.test_add", "tests.test_mul"])
        self.assertEqual(plan["total"], 10)

    def test_comment_only_change_still_selects_by_file(self):
        self.put("pkg/calc.py", CALC.replace("# cộng", "# phép cộng"))
        plan = self.plan()
        self.assertEqual(sorted(plan["names"]), ["tests.test_add", "tests.test_mul"])

    def test_module_level_change_takes_every_test_touching_the_file(self):
        self.put("pkg/calc.py", CALC.replace("LIMIT = 10", "LIMIT = 11"))
        plan = self.plan()
        self.assertIn("mọi test đã nạp", self.reasons(plan))
        self.assertEqual(sorted(plan["names"]), ["tests.test_add", "tests.test_mul"])

    def test_run_writes_a_narrow_receipt(self):
        self.put("pkg/calc.py", CALC.replace("return a + b", "return b + a"))
        out = self.narrow("run")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("chọn 4/10 test", out.stdout)
        shown = subprocess.run([sys.executable, str(RECEIPT), "show", "--json", "--project", str(self.proj)],
                               capture_output=True, text=True, env=dict(os.environ, **self.env))
        checks = json.loads(shown.stdout)
        self.assertEqual([rec.get("scope") for rec in checks.values()], ["narrow"])
        self.assertTrue(all(rec["ok"] for rec in checks.values()))


class NonPythonAndNewFiles(NarrowBase):
    def setUp(self):
        super().setUp()
        self.build()
        self.record()

    def test_data_files_read_by_tests_select_their_readers(self):
        for rel, text in (("pkg/data.json", '{"k": 1, "x": 2}\n'), ("plugin/SKILL.md", "---\nname: y\n---\n"),
                          ("plugin/hooks.json", '{"hooks": {"a": 1}}\n')):
            with self.subTest(rel=rel):
                git(self.proj, "checkout", "-q", "--", ".")
                self.put(rel, text)
                plan = self.plan()
                # test_data đọc file trong tiến trình của tests.test_mul: cả module
                self.assertEqual(plan["names"], ["tests.test_mul"], self.reasons(plan))
                self.assertIn("mọi test đã nạp, chạy hay đọc", self.reasons(plan))

    def test_unread_file_runs_nothing_and_says_so(self):
        self.put("plugin/rulebook.json", '{"x": 1}\n')
        plan = self.plan()
        self.assertEqual(plan["mode"], "none")
        self.assertIn("không test nào nạp, chạy hay đọc file này", self.reasons(plan))

    def test_new_test_file_not_in_trace_runs_its_module(self):
        self.put("tests/test_new.py", "import unittest\n\n\nclass X(unittest.TestCase):\n"
                                      "    def test_x(self):\n        pass\n")
        plan = self.plan()
        self.assertIn("tests.test_new", plan["names"])
        self.assertIn("file test mới chưa có trong vết", self.reasons(plan))
        out = self.narrow("run")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("Ran 1 test", out.stdout + out.stderr)

    def test_changed_test_file_runs_whole_module(self):
        self.put("tests/test_add.py", TEST_ADD + "\n    def test_more(self):\n        pass\n")
        plan = self.plan()
        self.assertIn("tests.test_add", plan["names"])
        self.assertIn("file test đổi: cả module", self.reasons(plan))

    def test_new_file_in_a_directory_no_test_touches_falls_back_to_full_suite(self):
        self.put("tools/new_tool.py", "X = 1\n")
        plan = self.plan()
        self.assertEqual(plan["mode"], "full")
        self.assertIn("file mới, không test nào chạm thư mục tools", self.reasons(plan))

    def test_new_file_next_to_traced_files_takes_tests_touching_that_directory(self):
        self.put("pkg/extra.py", "Y = 2\n")
        plan = self.plan()
        self.assertIn("file mới chưa có trong vết", self.reasons(plan))
        self.assertIn(plan["mode"], ("narrow", "full"))
        self.assertGreater(plan["selected"], 0)

    def test_empty_diff_falls_back_to_full_suite(self):
        plan = self.plan()
        self.assertEqual(plan["mode"], "full")
        self.assertIn("diff rỗng", self.reasons(plan))

    def test_deleted_test_file_is_not_run(self):
        (self.proj / "tests" / "test_add.py").unlink()
        self.put("pkg/calc.py", CALC.replace("return a + b", "return b + a"))
        plan = self.plan()
        # xóa file trong tests/: mọi test đã liệt kê thư mục đó (bộ nạp module cũng liệt kê) — thà thừa
        self.assertNotIn("tests.test_add", plan["names"], self.reasons(plan))
        out = self.narrow("run")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_deleted_file_runs_the_full_suite(self):
        # test có thể chỉ kiểm `exists()` của file (os.stat không để lại vết): xóa hay đổi tên thì chạy cả bộ
        (self.proj / "pkg" / "data.json").unlink()
        plan = self.plan()
        self.assertEqual(plan["mode"], "full", self.reasons(plan))
        self.assertIn("file bị xóa hay đổi tên", self.reasons(plan))

    def test_renamed_file_runs_the_full_suite(self):
        (self.proj / "pkg" / "data.json").rename(self.proj / "pkg" / "data2.json")
        plan = self.plan()
        self.assertEqual(plan["mode"], "full", self.reasons(plan))


class StaleTrace(NarrowBase):
    def setUp(self):
        super().setUp()
        self.build()
        self.record()

    def test_no_trace_falls_back_to_full_suite(self):
        self.map_file().unlink()
        self.put("pkg/calc.py", CALC.replace("return a + b", "return b + a"))
        plan = self.plan()
        self.assertEqual(plan["mode"], "full")
        self.assertIn("chưa có vết", self.reasons(plan))

    def test_file_changed_after_recording_takes_every_test_touching_it(self):
        self.put("pkg/calc.py", CALC.replace("total = 0", "total = 0  # đầu"))
        self.commit("đổi sau khi ghi vết")
        self.put("pkg/calc.py", CALC.replace("total = 0", "total = 0  # đầu").replace("return a + b", "return b + a"))
        plan = self.plan()
        self.assertIn("file đã đổi sau khi ghi vết", self.reasons(plan))
        touching = [n for f, why, n in plan["items"] if f == "pkg/calc.py"]
        # mọi test chạm calc.py, không chỉ dòng đổi: cả test_data (module của nó đã nạp calc.py)
        self.assertEqual(touching, [4])

    def test_many_code_files_changed_since_recording_falls_back_to_full_suite(self):
        for i in range(11):
            self.put(f"pkg/m{i}.py", f"V = {i}\n")
        self.commit("nhiều file sau khi ghi vết")
        self.put("pkg/calc.py", CALC.replace("return a + b", "return b + a"))
        plan = self.plan()
        self.assertEqual(plan["mode"], "full")
        self.assertIn("vết cũ: 11 file code", self.reasons(plan))

    def test_test_file_changed_after_recording_runs_its_module(self):
        self.put("tests/test_add.py", TEST_ADD + "\n    def test_new_one(self):\n        calc.mul(1, 1)\n")
        self.commit("thêm test sau khi ghi vết")
        self.put("pkg/calc.py", CALC.replace("total = 0", "total = 0 * 1"))
        plan = self.plan()
        self.assertIn("tests.test_add", plan["names"])
        self.assertIn("sau khi ghi vết: cả module", self.reasons(plan))

    def test_status_reports_drift(self):
        self.put("pkg/calc.py", CALC.replace("return a + b", "return b + a"))
        out = self.narrow("status")
        self.assertEqual(out.returncode, 0)
        self.assertIn("1 file khác lúc ghi: pkg/calc.py", out.stdout)


class OrderAndTools(NarrowBase):
    def test_test_failing_alone_reruns_module_and_is_remembered(self):
        self.build(order=True)
        self.record()
        self.put("pkg/side.py", "X = 2\n")  # chỉ tiến trình con của test_b nạp file này: chọn riêng test_b
        plan = self.plan()
        self.assertIn("tests.test_order.T.test_b", plan["names"])
        self.assertNotIn("tests.test_order.T.test_a", plan["names"])
        out = self.narrow("run")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("trượt khi chạy riêng", out.stdout)
        again = self.plan()
        self.assertIn("tests.test_order", again["names"])
        self.assertIn("trượt khi chạy một mình", self.reasons(again))

    def test_real_failure_is_reported(self):
        self.build()
        self.record()
        self.put("pkg/calc.py", CALC.replace("return a + b", "return a - b"))
        out = self.narrow("run")
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("FAIL: test_add", out.stdout + out.stderr)

    def test_external_tool_run_inside_repo_is_always_included(self):
        self.build(tool=True)
        self.record()
        self.put("README.md", "đọc tôi nữa\n")
        plan = self.plan()
        self.assertEqual(plan["names"], ["tests.test_tool"])
        self.assertIn("test chạy git trong repo", self.reasons(plan))


class Safety(NarrowBase):
    def setUp(self):
        super().setUp()
        self.build()
        self.record()

    def test_bad_refs_are_refused_before_git_sees_them(self):
        target = self.tmp / "out.txt"
        for args in (["--base", f"--output={target}"], ["--base=-p"], ["--head", "HEAD;touch x"],
                     ["--base", "HEAD..HEAD~1"], ["--base", "khong-co"]):
            with self.subTest(args=args):
                out = self.narrow("run", "--plan", *args)
                self.assertEqual(out.returncode, 2, out.stdout)
                self.assertFalse(target.exists())
                self.assertFalse((self.proj / "x").exists())

    def test_shell_characters_in_file_names_never_become_commands(self):
        weird = "tests/test_$(touch pwned)`id`;x.py"
        self.put(weird, "import unittest\n")
        self.put("pkg/-rf.py", "Z = 1\n")
        out = self.narrow("run")
        self.assertFalse((self.proj / "pwned").exists())
        plan = self.plan()
        for name in plan["names"]:
            self.assertRegex(name, r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)*$")
        self.assertNotIn("Traceback", out.stdout + out.stderr)

    def test_exec_refuses_names_that_look_like_flags(self):
        for name in ("-k", "--failfast", "tests.x;rm", "$(id)"):
            with self.subTest(name=name):
                out = self.narrow("exec", "--", name)
                self.assertEqual(out.returncode, 2)

    def test_symlink_pointing_outside_is_not_read(self):
        outside = self.tmp / "outside.py"
        outside.write_text("def f():\n    return 1\n")
        (self.proj / "pkg" / "calc.py").unlink()
        (self.proj / "pkg" / "calc.py").symlink_to(outside)
        plan = self.plan()
        self.assertIn("pkg/calc.py", self.reasons(plan))
        self.assertIn("tests.test_add", plan["names"])

    def test_corrupt_or_foreign_trace_falls_back_to_full_suite(self):
        path = self.map_file()
        good = json.loads(path.read_text())
        self.put("pkg/calc.py", CALC.replace("return a + b", "return b + a"))
        for change, why in ((lambda d: d.__setitem__("tests", ["-rf"] + d["tests"][1:]), "tên test lạ"),
                            (lambda d: d.__setitem__("root", "/khac"), "repo khác"),
                            (lambda d: d.__setitem__("sets", [[99999]]), "vết hỏng"),
                            (lambda d: d.__setitem__("alone_bad", ["--x"]), "tên test lạ")):
            with self.subTest(why=why):
                data = json.loads(json.dumps(good))
                change(data)
                path.write_text(json.dumps(data))
                plan = self.plan()
                self.assertEqual(plan["mode"], "full")
                self.assertIn(why, self.reasons(plan))
        path.write_text("{hỏng")
        self.assertIn("chưa có vết", self.reasons(self.plan()))


def load_stop():
    spec = importlib.util.spec_from_file_location("stop_hook_narrow", PLUGIN / "hooks" / "stop.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NarrowReceiptDoesNotCount(TempDirTestCase):
    """TM-160: biên nhận bộ thu hẹp không thay biên nhận cả bộ."""

    def setUp(self):
        super().setUp()
        self.stop = load_stop()
        self.turn = {"ts": time.time() - 60, "gate_level": "vua"}
        self.now = datetime.now().astimezone().isoformat(timespec="seconds")

    def gaps(self, checks):
        A = self.stop.A
        with mock.patch.object(A, "done_gate_ran_since", return_value=True), \
                mock.patch.object(A, "done_gate_levels_since", return_value=["vua"]), \
                mock.patch.object(A, "receipt_status", return_value=checks), \
                mock.patch.object(A, "subagent_started_since", return_value=True), \
                mock.patch.object(self.stop, "foreign_filters", return_value=False):
            return self.stop.evidence_gaps(self.tmp, self.turn, "sid")

    def test_only_a_narrow_receipt_is_still_a_gap(self):
        res = self.gaps({"thu hẹp (narrow.py)": {"ok": True, "scope": "narrow", "current": True, "ts": self.now}})
        self.assertIsNotNone(res)
        kinds = [k for k, _ in res[1]]
        self.assertIn("chưa có biên nhận đạt", kinds)
        self.assertIn("thu hẹp", dict(res[1])["chưa có biên nhận đạt"])

    def test_full_receipt_closes_the_gap(self):
        res = self.gaps({"thu hẹp (narrow.py)": {"ok": True, "scope": "narrow", "current": True, "ts": self.now},
                         "python3 -m unittest discover -s tests -t .": {"ok": True, "current": True, "ts": self.now}})
        self.assertIsNone(res)

    def test_failing_narrow_receipt_still_counts_as_failing(self):
        res = self.gaps({"thu hẹp (narrow.py)": {"ok": False, "exit": 1, "scope": "narrow", "current": True,
                                                  "ts": self.now},
                         "cả bộ": {"ok": True, "current": True, "ts": self.now}})
        self.assertEqual([k for k, _ in res[1]], ["test trượt"])

    def run_receipt(self, *args):
        env = dict(os.environ, AGENT_STACK_STATE=str(self.tmp / "state"))
        git(self.tmp, "init", "-q")
        out = subprocess.run([sys.executable, str(RECEIPT), "run", "--project", str(self.tmp), *args],
                             capture_output=True, text=True, env=env, cwd=str(self.tmp))
        shown = subprocess.run([sys.executable, str(RECEIPT), "show", "--project", str(self.tmp), "--json"],
                               capture_output=True, text=True, env=env)
        return out, json.loads(shown.stdout)

    def test_receipt_marks_narrow_flag_and_narrow_tool(self):
        out, checks = self.run_receipt("--narrow", "--label", "a", "--", sys.executable, "-c", "pass")
        self.assertIn("bộ thu hẹp", out.stdout)
        self.assertEqual(checks["a"].get("scope"), "narrow")
        _, checks = self.run_receipt("--label", "b", "--", sys.executable, str(NARROW), "status",
                                     "--project", str(self.tmp))
        self.assertEqual(checks["b"].get("scope"), "narrow")
        _, checks = self.run_receipt("--label", "c", "--", sys.executable, "-c", "pass")
        self.assertIsNone(checks["c"].get("scope"))
        shown = subprocess.run([sys.executable, str(RECEIPT), "show", "--project", str(self.tmp)],
                               capture_output=True, text=True,
                               env=dict(os.environ, AGENT_STACK_STATE=str(self.tmp / "state")))
        self.assertIn("bộ thu hẹp, không thay cả bộ", shown.stdout)


TEST_SCRIPT = """import subprocess, sys, tempfile, unittest


class T(unittest.TestCase):
    def test_runs_script(self):
        out = subprocess.run([sys.executable, "pkg/script.py"], capture_output=True, text=True)
        self.assertEqual(out.stdout.strip(), "5")

    def test_git_elsewhere(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "-C", d, "init", "-q"], check=True)
"""
SCRIPT = """def five():
    return 5


print(five())
"""


class TraceDetails(NarrowBase):
    def test_script_run_by_a_child_selects_only_that_test(self):
        self.build()
        self.put("pkg/script.py", SCRIPT)
        self.put("tests/test_script.py", TEST_SCRIPT)
        self.commit("thêm script")
        self.record()
        data = json.loads(self.map_file().read_text())
        self.assertIn("pkg/script.py", data["touched"])
        self.assertIn("pkg/script.py", data["lines"])
        self.assertEqual(data["opaque"], {})  # `git -C <thư mục tạm>` không đọc repo
        self.put("pkg/script.py", SCRIPT.replace("return 5", "return 2 + 3"))
        plan = self.plan()
        self.assertEqual(plan["names"], ["tests.test_script.T.test_runs_script"], self.reasons(plan))


# Dòng Python 3.11 không phát sự kiện "line": `else:`, dòng tiếp của chữ ký nhiều dòng, docstring. Sửa chúng vẫn phải
# chọn test (lỗi 1 của review 20/11).
SHAPE = '''"""Mô-đun hình.

Dòng giữa của docstring module.
"""


class Box:
    @staticmethod
    def h(x,
          limit=10):
        return min(x, limit)


def pick(a):
    y = 1

    # chú thích
    if a:
        return y
    else:
        return 0


SCALE = 2


def scale(a):
    if a:
        return SCALE
    return 0
'''
TEST_SHAPE = """import unittest
from pkg import shape


class T(unittest.TestCase):
    def test_pick_true(self):
        self.assertEqual(shape.pick(True), 1)

    def test_pick_false(self):
        self.assertEqual(shape.pick(False), 0)

    def test_h(self):
        self.assertEqual(shape.Box.h(50), 10)

    def test_scale_true(self):
        self.assertEqual(shape.scale(True), 2)

    def test_scale_false(self):
        self.assertEqual(shape.scale(False), 0)
"""
NOTES = '''"""Ghi chú.

Bước mặc định: deny.
"""
STEPS = ["deny"]
'''
TEST_NOTES = """import unittest


class T(unittest.TestCase):
    def test_doc(self):
        from pkg import notes
        self.assertIn("deny", notes.__doc__)
"""


class UntracedLines(NarrowBase):
    def setUp(self):
        super().setUp()
        self.build(extra={"pkg/shape.py": SHAPE, "tests/test_shape.py": TEST_SHAPE, "pkg/notes.py": NOTES,
                          "tests/test_notes.py": TEST_NOTES})
        self.record()

    def selected(self, plan) -> set:
        """Tên ngắn của mọi test được chọn (tên module được mở ra thành các test của nó theo vết)."""
        tests = json.loads(self.map_file().read_text())["tests"]
        return {t.rsplit(".", 1)[-1] for t in tests for n in plan["names"] if t == n or t.startswith(n + ".")}

    def test_insert_between_blank_and_comment_takes_tests_of_the_function(self):
        self.put("pkg/shape.py", SHAPE.replace("    y = 1\n\n", "    y = 1\n\n    y = y + 1\n"))
        plan = self.plan()
        self.assertEqual(plan["mode"], "narrow", self.reasons(plan))
        self.assertLessEqual({"test_pick_true", "test_pick_false"}, self.selected(plan), self.reasons(plan))

    def test_else_line_change_takes_tests_of_the_function(self):
        self.put("pkg/shape.py", SHAPE.replace("    else:\n", "    elif a is None:\n"))
        plan = self.plan()
        self.assertIn("test_pick_false", self.selected(plan), self.reasons(plan))

    def test_second_line_of_a_decorated_signature_takes_its_tests(self):
        self.put("pkg/shape.py", SHAPE.replace("limit=10", "limit=11"))
        plan = self.plan()
        self.assertIn("test_h", self.selected(plan), self.reasons(plan))

    def test_module_docstring_change_takes_tests_touching_the_module(self):
        self.put("pkg/notes.py", NOTES.replace("deny.", "deny, ask."))
        plan = self.plan()
        self.assertIn("tests.test_notes", plan["names"], self.reasons(plan))

    def test_assignment_making_a_global_local_takes_every_test_of_the_function(self):
        # gán SCALE trong một nhánh làm SCALE thành biến cục bộ của cả hàm: nhánh kia hỏng dù không qua dòng đổi
        self.put("pkg/shape.py", SHAPE[:SHAPE.rindex("    return 0")] + "    SCALE = 0; return SCALE\n")
        plan = self.plan()
        self.assertIn("test_scale_true", self.selected(plan), self.reasons(plan))

    def test_traced_line_change_selects_the_whole_module(self):
        self.put("pkg/shape.py", SHAPE.replace("return y", "return y * 1"))
        plan = self.plan()
        self.assertIn("tests.test_shape", plan["names"], self.reasons(plan))
        self.assertEqual(plan["names"][0], "tests.test_shape")  # test đi qua dòng đổi chạy trước


# rules() chỉ đọc rules.json một lần mỗi tiến trình (lru_cache): test thứ hai dùng nội dung mà không mở file (lỗi 2).
RULES = """import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def rules():
    return json.loads(Path("pkg/rules.json").read_text())


def lookup(k):
    return rules()[k]
"""
TEST_RULES = """import unittest
from pkg import rules


class T(unittest.TestCase):
    def test_a(self):
        self.assertEqual(rules.lookup("a"), 1)

    def test_b(self):
        self.assertEqual(rules.lookup("b"), 2)
"""


class CachedReads(NarrowBase):
    def setUp(self):
        super().setUp()
        self.build(extra={"pkg/rules.py": RULES, "pkg/rules.json": '{"a": 1, "b": 2}\n',
                          "tests/test_rules.py": TEST_RULES})
        self.record()

    def test_cached_data_file_selects_every_test_through_the_reading_module(self):
        self.put("pkg/rules.json", '{"a": 1, "b": 3}\n')
        plan = self.plan()
        self.assertIn("tests.test_rules", plan["names"], self.reasons(plan))

    def test_older_trace_version_falls_back_to_full_suite(self):
        path = self.map_file()
        data = json.loads(path.read_text())
        data["version"] = 2
        path.write_text(json.dumps(data))
        self.put("pkg/rules.json", '{"a": 1, "b": 3}\n')
        plan = self.plan()
        self.assertEqual(plan["mode"], "full", self.reasons(plan))
        self.assertIn("phiên bản", self.reasons(plan))


class ExecKeepsRealFailures(NarrowBase):
    """Lỗi 3: lần chạy lại cả module đạt không được che lỗi khác của lần đầu."""

    def setUp(self):
        super().setUp()
        self.build(order=True)
        self.record()

    def test_other_failure_is_not_swallowed_by_a_passing_rerun(self):
        self.put("pkg/calc.py", CALC.replace("return a + b", "return a - b"))
        out = self.narrow("exec", "--", "tests.test_add", "tests.test_order.T.test_b")
        self.assertNotEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_load_error_is_not_swallowed_by_a_passing_rerun(self):
        out = self.narrow("exec", "--", "tests.test_order.T.test_b", "tests.khong_co_module")
        self.assertNotEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_test_needing_its_module_still_passes(self):
        out = self.narrow("exec", "--", "tests.test_add", "tests.test_order.T.test_b")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)


HELPER = """def h():
    return 1
"""
TEST_OTHER = """import unittest


class T(unittest.TestCase):
    def test_x(self):
        pass

    def test_y(self):
        pass

    def test_z(self):
        pass
"""


class DriftedFiles(NarrowBase):
    """Lỗi 4: file đổi sau lúc ghi vết làm vết cũ; test chạm chúng phải được chọn."""

    def test_tests_touching_a_drifted_file_are_selected(self):
        self.build(extra={"pkg/helper.py": HELPER, "tests/test_other.py": TEST_OTHER})
        self.record()
        self.put("pkg/calc.py", CALC.replace("    total = 0\n", "    from pkg import helper\n"
                                                                "    total = helper.h() - 1\n"))
        self.commit("mul gọi helper sau khi ghi vết")
        self.put("pkg/helper.py", HELPER.replace("return 1", "return 2"))
        plan = self.plan()
        self.assertTrue({"tests.test_mul", "tests.test_mul.T.test_mul"} & set(plan["names"]), self.reasons(plan))

    def test_stale_file_in_diff_only_loaded_at_import_selects_modules_that_loaded_it(self):
        # lib2/unused.py chỉ được nạp lúc nạp tests/test_add.py, không test nào chạy dòng nào của nó
        self.build(extra={"lib2/__init__.py": "", "lib2/unused.py": "def f():\n    return 1\n",
                          "tests/test_add.py": "import lib2.unused\n" + TEST_ADD})
        self.record()
        self.put("lib2/unused.py", "def f():\n    return 3\n")
        self.commit("đổi sau khi ghi vết")
        self.put("lib2/unused.py", "def f():\n    return 4\n")
        plan = self.plan()
        self.assertIn("tests.test_add", plan["names"], self.reasons(plan))


class TraceArgs(NarrowBase):
    """Lỗi 5: tham số unittest trong vết phải được kiểm."""

    def setUp(self):
        super().setUp()
        self.build()
        self.record()

    def test_trace_args_pointing_elsewhere_fall_back_to_default_full_suite(self):
        path = self.map_file()
        data = json.loads(path.read_text())
        data["args"] = ["discover", "-s", str(self.tmp), "-t", "/"]
        path.write_text(json.dumps(data))
        self.put("pkg/calc.py", CALC.replace("return a + b", "return b + a"))
        plan = self.plan()
        self.assertEqual(plan["mode"], "full")
        self.assertIn("tham số", self.reasons(plan))
        spec = importlib.util.spec_from_file_location("narrow_args", NARROW)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.unittest_args(data), ["discover", "-s", "tests", "-t", "."])

    def test_record_refuses_flags_that_shrink_the_suite(self):
        before = self.map_file().read_text()
        out = self.narrow("record", "--jobs", "1", "--", "-k", "add")
        self.assertEqual(out.returncode, 2, out.stdout + out.stderr)
        self.assertEqual(self.map_file().read_text(), before)

    def test_trace_without_root_key_does_not_crash(self):
        path = self.map_file()
        data = json.loads(path.read_text())
        del data["root"]
        path.write_text(json.dumps(data))
        self.put("pkg/calc.py", CALC.replace("return a + b", "return b + a"))
        out = self.narrow("run", "--plan")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertNotIn("Traceback", out.stdout + out.stderr)
        self.assertIn("chạy cả bộ", out.stdout)


class ModuleLoads(NarrowBase):
    """Mục A (review 20/11): test chỉ đọc giá trị mức module (calc.LIMIT) mà không chạy dòng nào của calc.py."""

    def setUp(self):
        super().setUp()
        self.build(order=True, extra={"tests/test_other.py": TEST_OTHER})
        self.record()

    def test_module_constant_change_selects_tests_of_modules_that_loaded_the_file(self):
        self.put("pkg/calc.py", CALC.replace("LIMIT = 10", "LIMIT = 11"))
        plan = self.plan()
        self.assertTrue({"tests.test_order", "tests.test_order.T.test_a"} & set(plan["names"]), self.reasons(plan))
        self.assertNotIn("tests.test_other", plan["names"])

    def test_trace_without_touched_map_runs_full_suite(self):
        path = self.map_file()
        data = json.loads(path.read_text())
        data.pop("touched", None)
        path.write_text(json.dumps(data))
        self.put("pkg/calc.py", CALC.replace("LIMIT = 10", "LIMIT = 11"))
        plan = self.plan()
        self.assertEqual(plan["mode"], "full", self.reasons(plan))


TEST_FIXTURE = """import subprocess, sys, unittest
from pkg import calc


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = calc.mul(2, 2)
        cls.child = subprocess.run([sys.executable, "-c", "from pkg import calc; print(calc.add(5, 1))"],
                                   capture_output=True, text=True).stdout.strip()

    def test_value(self):
        self.assertEqual(self.value, 4)

    def test_child(self):
        self.assertEqual(self.child, "6")
"""
TEST_SOURCE = """import inspect, unittest
from pkg import calc


class T(unittest.TestCase):
    def test_src_a(self):
        self.assertIn("a + b", inspect.getsource(calc.add))

    def test_src_b(self):
        self.assertIn("return a + b", inspect.getsource(calc.add))
"""


class FixturesAndSource(NarrowBase):
    """Mục B (code chạy trong setUpClass, cả tiến trình con khởi động từ đó) và C (đọc mã nguồn qua inspect)."""

    def setUp(self):
        super().setUp()
        self.build(extra={"tests/test_fixture.py": TEST_FIXTURE, "tests/test_source.py": TEST_SOURCE,
                          "tests/test_other.py": TEST_OTHER})
        self.record()

    def test_line_run_in_setupclass_selects_every_test_of_the_class(self):
        self.put("pkg/calc.py", CALC.replace("total += a", "total = total + a"))
        plan = self.plan()
        self.assertIn("tests.test_fixture", plan["names"], self.reasons(plan))

    def test_child_started_in_setupclass_is_attributed_to_the_class(self):
        data = json.loads(self.map_file().read_text())
        tests = data["tests"]
        by_line = data["lines"]["pkg/calc.py"]
        add_line = str(CALC.splitlines().index("    return a + b") + 1)
        chosen = {tests[i] for i in data["sets"][by_line[add_line]]}
        self.assertIn("tests.test_fixture.T.test_child", chosen)

    def test_source_read_through_inspect_selects_every_reader(self):
        self.put("pkg/calc.py", CALC.replace("return a + b", "return b + a"))
        plan = self.plan()
        self.assertIn("tests.test_source", plan["names"], self.reasons(plan))


# ---- Vòng 3 (review 20/11): chọn theo file. Trạng thái trong bộ nhớ sống theo tiến trình, mỗi module test ghi vết
# trong một tiến trình riêng: file đổi thì chọn mọi test của module đã nạp, chạy hay đọc nó.

RX = """def _r(x):
    return x * 2


RULES = [_r(1), _r(2)]
"""
TEST_RX = """import unittest
from pkg import rx


class T(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(rx.RULES, [2, 4])

    def test_call(self):
        self.assertEqual(rx._r(5), 10)
"""
MEMO = """from functools import lru_cache


@lru_cache(maxsize=1)
def table():
    return {"a": 1 + 1}


def get(k):
    return table()[k]
"""
MEMO2 = """_CACHE = {}


def val(k):
    if k not in _CACHE:
        _CACHE[k] = k * 10
    return _CACHE[k]
"""
TEST_MEMO = """import unittest
from pkg import memo, memo2


class T(unittest.TestCase):
    def test_a(self):
        self.assertEqual(memo.get("a"), 2)
        self.assertEqual(memo2.val(1), 10)

    def test_b(self):
        self.assertEqual(memo.get("a"), 2)
        self.assertEqual(memo2.val(1), 10)
"""
CONF2 = """import json
from pathlib import Path

DATA = json.loads(Path("pkg/conf.json").read_text())


def helper():
    return 1
"""
TEST_CONF2 = """import unittest
from pkg import conf2


class T(unittest.TestCase):
    def test_data(self):
        self.assertEqual(conf2.DATA["x"], 1)
"""
TEST_CONF2_HELPER = """import unittest
from pkg import conf2


class T(unittest.TestCase):
    def test_helper(self):
        self.assertEqual(conf2.helper(), 1)
"""
TEST_SETMOD = """import unittest
from pkg import calc

VALUE = []


def setUpModule():
    VALUE.append(calc.mul(3, 3))


class T(unittest.TestCase):
    def test_v(self):
        self.assertEqual(VALUE, [9])
"""


class FileLevelSelection(NarrowBase):
    def setUp(self):
        super().setUp()
        self.build(extra={"pkg/rx.py": RX, "tests/test_rx.py": TEST_RX, "pkg/memo.py": MEMO, "pkg/memo2.py": MEMO2,
                          "tests/test_memo.py": TEST_MEMO, "pkg/conf2.py": CONF2, "pkg/conf.json": '{"x": 1}\n',
                          "tests/test_conf2.py": TEST_CONF2, "tests/test_conf2_helper.py": TEST_CONF2_HELPER,
                          "tests/test_setmod.py": TEST_SETMOD, "tests/test_other.py": TEST_OTHER})
        self.record()

    def chosen(self, plan) -> set:
        tests = json.loads(self.map_file().read_text())["tests"]
        return {t for t in tests for n in plan["names"] if t == n or t.startswith(n + ".")}

    def test_function_run_at_import_selects_tests_using_the_built_constant(self):
        self.put("pkg/rx.py", RX.replace("return x * 2", "return x * 3"))
        self.assertIn("tests.test_rx.T.test_rules", self.chosen(self.plan()))

    def test_lru_cache_result_selects_every_test_of_the_module(self):
        self.put("pkg/memo.py", MEMO.replace("1 + 1", "1 + 2"))
        self.assertLessEqual({"tests.test_memo.T.test_a", "tests.test_memo.T.test_b"}, self.chosen(self.plan()))

    def test_module_dict_memo_selects_every_test_of_the_module(self):
        self.put("pkg/memo2.py", MEMO2.replace("k * 10", "k * 11"))
        self.assertLessEqual({"tests.test_memo.T.test_a", "tests.test_memo.T.test_b"}, self.chosen(self.plan()))

    def test_data_file_read_at_import_into_a_constant(self):
        self.put("pkg/conf.json", '{"x": 2}\n')
        plan = self.plan()
        self.assertIn("tests.test_conf2.T.test_data", self.chosen(plan), self.reasons(plan))
        self.assertNotIn("tests.test_other.T.test_x", self.chosen(plan))

    def test_setupmodule_selects_the_module(self):
        self.put("pkg/calc.py", CALC.replace("total += a", "total = total + a"))
        self.assertIn("tests.test_setmod.T.test_v", self.chosen(self.plan()))

    def test_tests_through_changed_lines_run_first(self):
        self.put("pkg/calc.py", CALC.replace("total += a", "total = total + a"))
        plan = self.plan()
        self.assertEqual(plan["mode"], "narrow", self.reasons(plan))
        first = plan["names"][0]
        self.assertTrue(first.startswith(("tests.test_mul", "tests.test_setmod")), plan["names"])
        self.assertNotIn("tests.test_other", plan["names"])


TEST_BROKEN = """import unittest


class T(unittest.TestCase):
    def test_fails(self):
        self.assertEqual(1, 2)
"""
TEST_WRITER = """import unittest
from pathlib import Path


class T(unittest.TestCase):
    def test_writes(self):
        Path("pkg/gen.txt").write_text("đổi trong lúc ghi vết\\n")
"""


class RecordDetails(NarrowBase):
    def test_tests_failing_at_record_time_are_always_planned(self):
        self.build(extra={"tests/test_broken.py": TEST_BROKEN, "tests/test_other.py": TEST_OTHER})
        out = self.narrow("record", "--jobs", "2")
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertIn("tests.test_broken.T.test_fails", out.stdout)
        self.put("plugin/rulebook.json", '{"x": 1}\n')
        plan = self.plan()
        self.assertTrue({"tests.test_broken", "tests.test_broken.T.test_fails"} & set(plan["names"]),
                        self.reasons(plan))

    def test_file_changed_while_recording_counts_as_drifted(self):
        self.build(extra={"pkg/gen.txt": "gốc\n", "tests/test_writer.py": TEST_WRITER})
        self.record()
        data = json.loads(self.map_file().read_text())
        self.assertEqual(data["inventory"]["pkg/gen.txt"], "")

    def test_full_mode_of_a_partial_trace_writes_a_narrow_receipt(self):
        self.build()
        out = self.narrow("record", "--jobs", "1", "--", "tests.test_add")
        self.assertIn(out.returncode, (0, 1), out.stdout + out.stderr)
        out = self.narrow("run")  # diff rỗng: chế độ cả bộ theo tham số của vết (chỉ tests.test_add)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        shown = subprocess.run([sys.executable, str(RECEIPT), "show", "--json", "--project", str(self.proj)],
                               capture_output=True, text=True, env=dict(os.environ, **self.env))
        checks = json.loads(shown.stdout)
        self.assertEqual([rec.get("scope") for rec in checks.values()], ["narrow"], checks)

    def test_names_and_refs_with_a_trailing_newline_are_refused(self):
        self.build()
        self.record()
        self.assertEqual(self.narrow("exec", "--", "tests.test_add\n").returncode, 2)
        self.assertEqual(self.narrow("run", "--plan", "--base", "HEAD\n").returncode, 2)
