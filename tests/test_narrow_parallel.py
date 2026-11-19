"""Chạy test song song (việc F2a): `narrow.py full` chạy cả bộ theo mảnh, mảnh trượt chạy lại một mình, tổng số test
phải bằng số test discover nạp được; `run --jobs`, `exec --jobs` song song theo module; biên nhận của `full` đúng dạng
là của cả bộ, mọi dạng khác vẫn `scope: narrow` (TM-160); vết ghi được khi tiến trình con chạy công cụ ngoài ở cả
trong và ngoài repo (lỗi sắp xếp None với chuỗi trong sitecustomize của linetrace)."""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from tests._util import TempDirTestCase, git
from tests.test_narrow import CALC, NARROW, RECEIPT, NarrowBase

TEST_A = """import unittest


class A(unittest.TestCase):
    def test_1(self):
        pass

    def test_2(self):
        pass


class B(unittest.TestCase):
    def test_3(self):
        pass
"""
# Lớp B nhập từ module khác: discover chạy nó trong cả hai module, nên module của test là module đã nạp nó.
TEST_B = """import unittest
from tests.test_a import B


class C(unittest.TestCase):
    def test_x(self):
        for i in range(3):
            with self.subTest(i=i):
                pass
"""
TEST_ENV = """import os, unittest


class D(unittest.TestCase):
    def test_env(self):
        self.assertIsNone(os.environ.get("NARROW_FAIL_ME"), "bị đặt NARROW_FAIL_ME")
"""
# load_tests trả bộ rỗng khi chạy theo tên (pattern None): chạy riêng module thì thiếu test so với discover.
TEST_SHY = """import unittest


class S(unittest.TestCase):
    def test_s(self):
        pass


def load_tests(loader, tests, pattern):
    return tests if pattern else unittest.TestSuite()
"""
# test_x trượt khi test_y chạy cùng lúc (thấy file y-started), đạt khi chạy một mình.
TEST_X = """import time, unittest
from pathlib import Path


class X(unittest.TestCase):
    def test_alone(self):
        mine, other = Path("x-started"), Path("y-started")
        mine.write_text("1")
        try:
            end = time.time() + 8  # chờ lâu: máy tải thì test_y có thể khởi động muộn
            while time.time() < end:
                self.assertFalse(other.exists(), "test_y đang chạy cùng lúc")
                time.sleep(0.05)
        finally:
            mine.unlink()
"""
TEST_Y = """import time, unittest
from pathlib import Path


class Y(unittest.TestCase):
    def test_partner(self):
        mine, other = Path("y-started"), Path("x-started")
        mine.write_text("1")
        try:
            end = time.time() + 15
            while time.time() < end and not other.exists():
                time.sleep(0.05)
            time.sleep(0.5)
        finally:
            mine.unlink()
"""
# Test in ra stdout một dòng giống tổng kết của unittest.
TEST_NOISY = """import unittest


class N(unittest.TestCase):
    def test_noisy(self):
        print("Ran 7 tests in 0.010s")
"""
# Tiến trình con chạy git ở ngoài repo (thư mục chạy None trong vết) và trong repo (""): ghi vết không được in lỗi
# ra stderr của tiến trình con lúc thoát.
TEST_SPAWN = """import subprocess, sys, unittest

CHILD = ("import subprocess; subprocess.run(['git', '--version'], cwd='/', capture_output=True); "
         "subprocess.run(['git', '--version'], capture_output=True)")


class T(unittest.TestCase):
    def test_child_is_quiet(self):
        out = subprocess.run([sys.executable, "-c", CHILD], capture_output=True, text=True)
        self.assertEqual((out.returncode, out.stderr), (0, ""))
"""


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FullBase(NarrowBase):
    def small(self, extra=None):
        files = {"tests/__init__.py": "", "tests/test_a.py": TEST_A, "tests/test_b.py": TEST_B,
                 "tests/test_env.py": TEST_ENV}
        files.update(extra or {})
        for rel, text in files.items():
            self.put(rel, text)
        git(self.proj, "init", "-q")
        self.commit("init")

    def full(self, *args, **env):
        self.env.update(env)
        return self.narrow("full", "--jobs", "3", *args)

    def summary(self, out) -> str:
        lines = [ln for ln in out.stdout.splitlines() if "cả bộ song song:" in ln]
        self.assertEqual(len(lines), 1, out.stdout + out.stderr)
        return lines[0]


class FullRunsTheWholeSuite(FullBase):
    def test_passing_suite_counts_every_test_discover_loads(self):
        self.small()
        out = self.full()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        # discover: A (2) + B (1) trong test_a, C (1) + B (1) trong test_b, D (1)
        self.assertIn("6/6 test, 3 mảnh, 3 tiến trình", self.summary(out))
        self.assertIn("đạt", self.summary(out))
        self.assertEqual(len(out.stdout.strip().splitlines()), 1, out.stdout)  # output gọn: chỉ dòng tổng kết

    def test_failing_shard_gives_one_short_line_and_nonzero_exit(self):
        self.small()
        out = self.full(NARROW_FAIL_ME="1")
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        bad = [ln for ln in out.stdout.splitlines() if ln.startswith("[narrow] ✗")]
        self.assertEqual(len(bad), 1, out.stdout)
        self.assertIn("tests.test_env", bad[0])
        self.assertIn("tests.test_env.D.test_env", bad[0])
        self.assertIn("bị đặt NARROW_FAIL_ME", bad[0])
        self.assertLess(len(bad[0]), 450)
        self.assertNotIn("chỉ trượt khi chạy song song", out.stdout)
        self.assertIn("TRƯỢT (1 mảnh trượt)", self.summary(out))

    def test_module_that_cannot_load_is_a_failing_shard_and_still_counted(self):
        self.small({"tests/test_broken.py": "import khong_co_goi_nay\n"})
        out = self.full()
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertIn("tests.test_broken", out.stdout)
        self.assertIn("khong_co_goi_nay", out.stdout)
        self.assertIn("7/7 test", self.summary(out))

    def test_fewer_tests_than_discover_loads_fails(self):
        self.small({"tests/test_shy.py": TEST_SHY})
        out = self.full()
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertIn("khác số test discover nạp được", out.stdout)
        self.assertIn("6/7 test", self.summary(out))

    def test_shard_failing_only_in_parallel_is_rerun_alone_and_named(self):
        self.small({"tests/test_x.py": TEST_X, "tests/test_y.py": TEST_Y})
        out = self.narrow("full", "--jobs", "5")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assert_rerun_is_visible(out)
        self.assertIn("8/8 test", self.summary(out))

    def test_rerun_shard_is_named_in_the_receipt_summary(self):
        # Review F2a mục 1: lần trượt đầu không được che; dòng tổng kết cuối (summary của biên nhận) nêu mảnh chạy lại.
        self.small({"tests/test_x.py": TEST_X, "tests/test_y.py": TEST_Y})
        env = dict(os.environ, **self.env)
        out = subprocess.run([sys.executable, str(RECEIPT), "run", "--project", str(self.proj), "--label", "full",
                              "--", sys.executable, str(NARROW), "full", "--jobs", "5"], capture_output=True,
                             text=True, env=env, cwd=str(self.proj))
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        shown = subprocess.run([sys.executable, str(RECEIPT), "show", "--json", "--project", str(self.proj)],
                               capture_output=True, text=True, env=env)
        summary = json.loads(shown.stdout)["full"]["summary"]
        self.assertIn("đạt (1 mảnh trượt lần đầu, đạt khi chạy lại: tests.test_x)", summary)

    def test_exec_jobs_also_shows_the_first_failure_of_a_rerun_shard(self):
        self.small({"tests/test_x.py": TEST_X, "tests/test_y.py": TEST_Y})
        out = self.narrow("exec", "--jobs", "2", "--", "tests.test_x", "tests.test_y")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assert_rerun_is_visible(out)

    def assert_rerun_is_visible(self, out):
        lines = out.stdout.strip().splitlines()
        first = [ln for ln in lines if "trượt lần đầu, đạt khi chạy lại một mình" in ln]
        self.assertEqual(len(first), 1, out.stdout)
        self.assertIn("tests.test_x", first[0])
        self.assertIn("tests.test_x.X.test_alone", first[0])  # tên test trượt lần đầu
        self.assertIn("test_y đang chạy cùng lúc", first[0])  # thông báo lỗi lần đầu
        self.assertLess(len(first[0]), 600)
        self.assertRegex(lines[-1], r": đạt \(1 mảnh trượt lần đầu, đạt khi chạy lại: tests\.test_x\)$")

    def test_test_printing_a_ran_line_does_not_change_the_count(self):
        # Review F2a mục 4: dòng `Ran N tests` do test in ra stdout không được tính.
        self.small({"tests/test_noisy.py": TEST_NOISY})
        out = self.full()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("7/7 test", self.summary(out))

    def test_no_argument_can_narrow_the_suite(self):
        self.small()
        for extra in (["tests.test_a"], ["--", "tests.test_a"], ["-k", "test_1"], ["--plan"]):
            with self.subTest(extra=extra):
                out = self.narrow("full", *extra)
                self.assertEqual(out.returncode, 2, out.stdout + out.stderr)

    def test_missing_tests_dir_is_exit_2(self):
        self.put("README.md", "x\n")
        git(self.proj, "init", "-q")
        self.commit("init")
        out = self.narrow("full")
        self.assertEqual(out.returncode, 2, out.stdout + out.stderr)
        self.assertIn("không nạp được bộ test", out.stdout)


class FullUsesTheTrace(FullBase):
    """Có vết: mảnh lâu chạy trước, module ước quá SPLIT_SECS tách theo lớp, vẫn đủ số test."""

    def test_slow_module_is_split_by_class_and_count_still_matches(self):
        self.small()
        self.record()
        path = self.map_file()
        data = json.loads(path.read_text())
        data["secs"] = [60.0 if t.startswith("tests.test_a.") else 0.1 for t in data["tests"]]
        path.write_text(json.dumps(data))
        out = self.full()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        # test_a (180 giây theo vết, hai lớp) thành 2 mảnh: A, B; cộng test_b, test_env
        self.assertIn("6/6 test, 4 mảnh", self.summary(out))

    def test_plan_shards_splits_orders_and_keeps_counts(self):
        N = load("narrow_f2a", NARROW)
        rows = [["m.fast", 3, {"F": 3}], ["m.slow", 10, {"P": 4, "Q": 3, "R": 3}], ["m.custom", 5, None]]
        by_module = {"m.fast": 2.0, "m.slow": 100.0, "m.custom": 50.0}
        by_class = {("m.slow", "P"): 60.0, ("m.slow", "Q"): 30.0, ("m.slow", "R"): 10.0}
        shards = N.plan_shards(rows, by_module, by_class)
        slow = [s for s in shards if s["module"] == "m.slow"]
        self.assertEqual(len(slow), 3)  # ceil(100 / 45)
        self.assertEqual(sorted(n for s in slow for n in s["names"]), ["m.slow.P", "m.slow.Q", "m.slow.R"])
        self.assertEqual(sum(s["expect"] for s in shards), 18)
        self.assertEqual([s["names"] for s in shards if s["module"] == "m.custom"], [["m.custom"]])  # load_tests
        self.assertEqual(shards[0]["names"], ["m.slow.P"])  # lâu nhất chạy trước
        self.assertEqual(shards[-1]["names"], ["m.fast"])
        no_trace = N.plan_shards(rows, {}, {})
        self.assertEqual([s["names"] for s in no_trace], [["m.slow"], ["m.custom"], ["m.fast"]])  # theo số test

    def test_no_empty_shard_even_when_class_times_are_zero(self):
        # Review F2a mục 3: mảnh rỗng chạy `python -m unittest` không tham số (discover cả cây).
        N = load("narrow_f2a_empty", NARROW)
        rows = [["m.z", 4, {"A": 1, "B": 1, "C": 1, "D": 1}]]
        by_class = {("m.z", c): 0.0 for c in "ABCD"}
        shards = N.plan_shards(rows, {"m.z": 200.0}, by_class)
        self.assertTrue(all(s["names"] for s in shards), shards)
        self.assertEqual(sorted(n for s in shards for n in s["names"]), ["m.z.A", "m.z.B", "m.z.C", "m.z.D"])
        self.assertEqual(N.plan_shards(rows, {"m.z": 200.0}, by_class), shards)  # ổn định
        with self.assertRaises(ValueError):
            N.launch(self.tmp, [], self.tmp, "rong")

    def test_default_jobs_is_performance_cores(self):
        N = load("narrow_f2a_jobs", NARROW)
        jobs = N.default_jobs()
        self.assertGreaterEqual(jobs, 1)
        if sys.platform == "darwin":
            got = subprocess.run(["sysctl", "-n", "hw.perflevel0.physicalcpu"], capture_output=True, text=True)
            if got.returncode == 0 and got.stdout.strip().isdigit():
                self.assertEqual(jobs, int(got.stdout.strip()))


class RunAndExecInParallel(NarrowBase):
    def test_run_jobs_runs_selected_modules_in_parallel_with_a_narrow_receipt(self):
        self.build()
        self.record()
        self.put("pkg/calc.py", CALC.replace("return a + b", "return b + a"))
        out = self.narrow("run", "--jobs", "2")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("bộ thu hẹp song song: 4 test, 2 mảnh, 2 tiến trình", out.stdout)
        checks = self.receipts()
        self.assertEqual([rec.get("scope") for rec in checks.values()], ["narrow"], checks)

    def test_run_jobs_falling_back_to_the_full_suite_uses_full_and_a_full_receipt(self):
        self.build()
        self.record()
        out = self.narrow("run", "--jobs", "2")  # diff rỗng: rơi về cả bộ
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("cả bộ song song: 10/10 test", out.stdout)
        checks = self.receipts()
        self.assertEqual([rec.get("scope") for rec in checks.values()], [None], checks)

    def test_exec_jobs_keeps_relevance_order_at_shard_level(self):
        N = load("narrow_f2a_groups", NARROW)
        groups = N.module_groups(["tests.test_b.T.test_1", "tests.test_a", "tests.test_b.T.test_2", "tests.new"],
                                 {"tests.test_a", "tests.test_b"})
        self.assertEqual([g["names"] for g in groups],
                         [["tests.test_b.T.test_1", "tests.test_b.T.test_2"], ["tests.test_a"], ["tests.new"]])

    def test_exec_jobs_test_needing_its_module_passes_and_is_remembered(self):
        self.build(order=True)
        self.record()
        out = self.narrow("exec", "--jobs", "2", "--", "tests.test_order.T.test_b", "tests.test_add")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("đạt khi chạy cả module tests.test_order", out.stdout)
        data = json.loads(self.map_file().read_text())
        self.assertIn("tests.test_order.T.test_b", data["alone_bad"])

    def test_exec_jobs_real_failure_and_load_error_are_reported(self):
        self.build(order=True)
        self.record()
        self.put("pkg/calc.py", CALC.replace("return a + b", "return a - b"))
        out = self.narrow("exec", "--jobs", "2", "--", "tests.test_add", "tests.khong_co_module")
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        bad = [ln for ln in out.stdout.splitlines() if ln.startswith("[narrow] ✗")]
        self.assertEqual(len(bad), 2, out.stdout)

    def receipts(self) -> dict:
        shown = subprocess.run([sys.executable, str(RECEIPT), "show", "--json", "--project", str(self.proj)],
                               capture_output=True, text=True, env=dict(os.environ, **self.env))
        return json.loads(shown.stdout)


class FullReceiptScope(TempDirTestCase):
    """TM-160: chỉ `narrow.py full` đúng dạng, ở chính project, mới là biên nhận cả bộ."""

    def setUp(self):
        super().setUp()
        self.R = load("receipt_f2a", RECEIPT)
        self.root = self.tmp / "proj"
        self.root.mkdir()
        git(self.root, "init", "-q")
        self.other = self.tmp / "other"
        self.other.mkdir()
        self.fake = self.other / "narrow.py"  # narrow.py giả: không kiểm số test
        self.fake.write_text("print('Ran 0 tests')\n")

    def narrow(self, cmd, root=None, run_dir=None):
        root = root or self.root
        return self.R.is_narrow(cmd, root, run_dir or root)

    def test_exact_full_form_is_not_narrow(self):
        py, tool = sys.executable, str(NARROW)
        for cmd in ([py, tool, "full"], ["python3", tool, "full", "--jobs", "4"], [py, tool, "full", "--jobs=4"],
                    [py, tool, "full", "--timeout", "600", "--jobs", "2"], [py, tool, "full", "--project", "."],
                    [py, tool, "full", "--project", str(self.root)], [tool, "full"],
                    ["python3.11", tool, "full", "--timeout=3600.5"],
                    [py, os.path.relpath(tool, self.root), "full"]):  # tương đối theo thư mục chạy
            with self.subTest(cmd=cmd):
                self.assertFalse(self.narrow(cmd))

    def test_every_other_form_stays_narrow(self):
        py, tool = sys.executable, str(NARROW)
        for cmd in ([py, tool, "run", "full"], [py, tool, "run", "--jobs", "4", "full"], [py, tool, "exec", "--", "full"],
                    [py, tool, "full", "tests.test_a"], [py, tool, "full", "--", "tests.test_a"],
                    [py, tool, "full", "-k", "x"], [py, tool, "full", "--jobs"], [py, tool, "full", "--jobs", "0"],
                    [py, tool, "full", "--jobs", "4", "x"], [py, tool, "full", "--plan"], [py, tool, "full", "--json"],
                    [py, tool, "full", "--project", str(self.other)], [py, tool, "full", "--project", "--jobs"],
                    [py, tool, "full", "--project=" + str(self.other)], ["env", py, tool, "full"],
                    [py, "-I", tool, "full"], ["timeout", "60", py, tool, "full"], [py, tool, tool, "full"],
                    [py, tool, "status"], [py, tool, "Full"], [py, tool, "full", "--jobs", "4 "],
                    ["bash", tool, "full"], [py, tool, "full", "--base", "HEAD"],
                    [py, str(self.fake), "full"], [py, "narrow.py", "full"]):  # narrow.py khác cùng tên
            with self.subTest(cmd=cmd):
                self.assertTrue(self.narrow(cmd))

    def test_receipt_root_must_be_the_git_root(self):
        sub = self.root / "sub"
        sub.mkdir()
        self.assertTrue(self.narrow([sys.executable, str(NARROW), "full"], root=sub))
        self.assertTrue(self.narrow([sys.executable, str(NARROW), "full"], run_dir=sub))

    def test_receipt_cli_writes_a_full_receipt_for_full_and_narrow_for_run(self):
        (self.root / "tests").mkdir()
        (self.root / "tests" / "__init__.py").write_text("")
        (self.root / "tests" / "test_a.py").write_text(TEST_A)
        env = dict(os.environ, AGENT_STACK_STATE=str(self.tmp / "state"))

        def receipt(label, *cmd):
            out = subprocess.run([sys.executable, str(RECEIPT), "run", "--project", str(self.root), "--label", label,
                                  "--", *cmd], capture_output=True, text=True, env=env, cwd=str(self.root))
            return out
        out = receipt("full", sys.executable, str(NARROW), "full", "--jobs", "2")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertNotIn("bộ thu hẹp", out.stdout)
        receipt("full-la", sys.executable, str(NARROW), "full", "--jobs", "2", "tests.test_a")
        shown = subprocess.run([sys.executable, str(RECEIPT), "show", "--project", str(self.root), "--json"],
                               capture_output=True, text=True, env=env)
        checks = json.loads(shown.stdout)
        self.assertIsNone(checks["full"].get("scope"))
        self.assertTrue(checks["full"]["ok"])
        self.assertEqual(checks["full-la"].get("scope"), "narrow")
        self.assertFalse(checks["full-la"]["ok"])


class TraceWithChildTools(NarrowBase):
    def test_child_running_tools_inside_and_outside_repo_is_traced_quietly(self):
        self.build(extra={"tests/test_spawn.py": TEST_SPAWN})
        out = self.narrow("record", "--jobs", "2")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertNotRegex(out.stdout, re.compile(r"trượt lúc ghi vết"))
