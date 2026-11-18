"""mutation.py chọn test theo dòng (spec `mutation-chon-test`, file `.agent/spec/mutation-chon-test.txt`).

Viết trước code. Chạy mutmut 2.5.1 THẬT (`.venv-mutmut`) trên project nhỏ; bỏ qua khi máy thiếu mutmut hay `ps`.
Mỗi test của fixture ghi tên mình vào file log (đường dẫn tuyệt đối ngoài project, qua biến môi trường `SEL_LOG`) để
đếm test nào chạy bao nhiêu lần: có chọn test thì test không liên quan chỉ chạy ở lần chạy gốc và lần ghi vết (hằng
số nhỏ), còn chạy cả lệnh test thì chạy ít nhất một lần cho mỗi đột biến.

Giao diện giả định (xem báo cáo): cờ `--no-select`; JSON `selection` là "theo dòng" hay "tắt: <lý do>" (với
`--no-select`: đúng "tắt: --no-select"); chữ có dòng chứa `chọn test tắt:`; `AGENT_STACK_MUT_TRACE=1` chỉ có trong
tiến trình của bước ghi vết.

Chạy file này tốn vài phút (mỗi test chạy mutmut thật một hay hai lần): chỉ chạy lúc cuối.
"""
import collections
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from tests._util import git
from tests.test_mutation import REAL_MUTMUT, SCRIPT, MutationBase, snapshot

# ---------------------------------------------------------------------------------------------------------------
# fixture: sut.py (f đổi, g không đổi), tool.py (chạy bằng tiến trình con), tests/test_x.py (test_a gọi f, test_b gọi
# g, test_c gọi tool.py)

SUT_OLD = "def f(x):\n    return x\n\n\ndef g(x):\n    return x * 2\n"
SUT_NEW = ("def f(x):\n    a = x + 1\n    b = a * 3\n    c = b - 2\n    d = c + 10\n    return d\n\n\n"
           "def g(x):\n    return x * 2\n")  # f(1) == 14
TOOL_OLD = "import sys\n\nif __name__ == \"__main__\":\n    n = int(sys.argv[1])\n    print(n)\n"
TOOL_NEW = ("import sys\n\nif __name__ == \"__main__\":\n    n = int(sys.argv[1])\n    m = n * 3 + 1\n    k = m - 4\n"
            "    print(k)\n")  # tool.py 2 in ra 3

TESTS_HEAD = '''import os
import subprocess
import sys
import time
import unittest

from sut import f, g

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def note(name):
    path = os.environ.get("SEL_LOG")
    if path:
        with open(path, "a") as fh:
            fh.write(name + "\\n")


def slow():
    """Chỉ khi có SEL_PIDS và không phải bước ghi vết: ghi pid rồi ngủ lâu (test S6)."""
    if os.environ.get("SEL_PIDS") and not os.environ.get("AGENT_STACK_MUT_TRACE"):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        with open(os.environ["SEL_PIDS"], "a") as fh:
            fh.write("%d %d\\n" % (os.getpid(), child.pid))
        time.sleep(120)

'''
TESTS_MAIN = TESTS_HEAD + '''
class T(unittest.TestCase):
    def test_a(self):
        note("a")
        slow()
        self.assertEqual(f(1), 14)

    def test_b(self):
        note("b")
        if os.environ.get("SEL_FAIL_TRACE") and os.environ.get("AGENT_STACK_MUT_TRACE"):
            self.fail("bước ghi vết bị làm trượt")
        self.assertEqual(g(3), 6)

    def test_c(self):
        note("c")
        out = subprocess.run([sys.executable, os.path.join(ROOT, "tool.py"), "2"], capture_output=True, text=True,
                             cwd=ROOT)
        self.assertEqual(out.stdout.strip(), "3")
'''

# fixture S2: đột biến sống ở dòng có test đi qua (`unused`), ở dòng không test nào đi qua (`never`), và đột biến ở
# dòng test_a đi qua nhưng chỉ test_b (không đi qua dòng đó) bắt được (`mark`).
S2_OLD = 'STATE = {"n": 0}\n\n\ndef f(x):\n    return x\n\n\ndef mark():\n    pass\n'
S2_NEW = ('STATE = {"n": 0}\n\n\ndef f(x):\n    a = x + 1\n    unused = x + 100\n    b = a * 3\n    return b\n\n\n'
          'def mark():\n    STATE["n"] = STATE["n"] + 1\n\n\ndef never(x):\n    return x - 7\n')
S2_TESTS = TESTS_HEAD.replace("from sut import f, g", "from sut import STATE, f, mark") + '''
class T(unittest.TestCase):
    def test_a(self):
        note("a")
        self.assertEqual(f(1), 6)
        mark()

    def test_b(self):
        note("b")
        self.assertEqual(STATE["n"], 1)
'''

PYTEST_SHIM = 'import unittest\n\nunittest.main(module=None, argv=["pytest", "tests.test_x"])\n'
CMD_X = "python3 -m unittest tests.test_x"


def line_of(text, needle):
    return text.splitlines().index(needle) + 1


class SelBase(MutationBase):
    """Project nhỏ + chạy mutmut thật; bỏ qua khi máy thiếu mutmut hay ps."""

    def setUp(self):
        super().setUp()
        if not REAL_MUTMUT.exists():
            self.skipTest(f"chưa có {REAL_MUTMUT}")
        if shutil.which("ps") is None:
            self.skipTest("máy không có ps")
        self.tmpdir = self.tmp / "tmpdir"  # TMPDIR riêng cho mutation.py và mọi tiến trình con
        self.tmpdir.mkdir()
        self.runs_done = 0

    # ---- dựng project ----
    def build(self, base, work, extra=None):
        """Commit `base` (cộng `extra`), rồi ghi `work` vào cây làm việc (chưa commit)."""
        for rel, text in {**base, **(extra or {})}.items():
            path = self.repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        git(self.repo, "init", "-q")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "init")
        for rel, text in work.items():
            (self.repo / rel).write_text(text, encoding="utf-8")

    def build_f(self, extra=None):
        """Diff chỉ đổi f trong sut.py; tool.py đã commit bản mới."""
        self.build({"sut.py": SUT_OLD, "tool.py": TOOL_NEW, "tests/test_x.py": TESTS_MAIN}, {"sut.py": SUT_NEW}, extra)

    def build_tool(self):
        """Diff chỉ đổi tool.py (chạy bằng tiến trình Python con); sut.py đã commit bản mới."""
        self.build({"sut.py": SUT_NEW, "tool.py": TOOL_OLD, "tests/test_x.py": TESTS_MAIN}, {"tool.py": TOOL_NEW})

    def build_s2(self):
        self.build({"sut.py": S2_OLD, "tests/test_x.py": S2_TESTS}, {"sut.py": S2_NEW})

    # ---- chạy ----
    def env(self, log=None, extra=None):
        env = dict(os.environ, AGENT_STACK_STATE=str(self.state), TMPDIR=str(self.tmpdir))
        env.pop("AGENT_STACK_MUT_TRACE", None)
        if log is not None:
            env["SEL_LOG"] = str(log)
        env.update(extra or {})
        return env

    def mutate(self, *args, cmd=CMD_X, as_json=True, extra_env=None):
        """Chạy mutation.py thật trên project; trả (tiến trình đã xong, số lần mỗi test chạy)."""
        self.runs_done += 1
        log = self.tmp / f"sel{self.runs_done}.log"
        argv = [sys.executable, str(SCRIPT), "--project", str(self.repo), "--cmd", cmd, "--timeout", "300",
                "--jobs", "1"] + (["--json"] if as_json else []) + list(args)
        out = subprocess.run(argv, capture_output=True, text=True, env=self.env(log, extra_env), timeout=420)
        counts = collections.Counter(log.read_text(encoding="utf-8").split()) if log.exists() else collections.Counter()
        return out, counts

    def ran(self, *args, **kw):
        """Như `mutate` với --json: kiểm thoát 0 và status "ran"; trả (dữ liệu JSON, đếm)."""
        out, counts = self.mutate(*args, **kw)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        data = json.loads(out.stdout)
        self.assertEqual(data["status"], "ran", data)
        return data, counts

    def assertSameOutcome(self, a, b):
        """Số bắt, sống (và vị trí sống) bằng nhau giữa hai lần chạy."""
        for key in ("total", "killed", "timeout", "untested"):
            self.assertEqual(a[key], b[key], f"{key}: {a} / {b}")
        self.assertEqual(sorted((s["file"], s["line"]) for s in a["survived"]),
                         sorted((s["file"], s["line"]) for s in b["survived"]))

    def assertSelection(self, data, expected):
        self.assertEqual(data.get("selection"), expected, data)

    def assertOff(self, data, reason=None):
        sel = data.get("selection")
        self.assertIsInstance(sel, str, data)
        self.assertTrue(sel.startswith("tắt: ") and len(sel) > len("tắt: "), sel)
        if reason is not None:
            self.assertEqual(sel, reason)

    def assertFullRuns(self, data, counts):
        """Cả lệnh test chạy cho mọi đột biến: test_b (không liên quan) chạy ít nhất một lần mỗi đột biến."""
        self.assertGreaterEqual(data["total"], 8, f"fixture phải có đủ đột biến: {data}")
        self.assertGreaterEqual(counts["b"], data["total"], counts)
        self.assertEqual(data["killed"], data["total"], data)


# ---------------------------------------------------------------------------------------------------------------
class SelectByLine(SelBase):
    """S1: có chọn test, đột biến chỉ chạy test đi qua dòng của nó."""

    SMALL = 3  # lần chạy gốc và lần ghi vết: hằng số nhỏ, không phụ thuộc số đột biến

    def test_unrelated_tests_do_not_run_per_mutant(self):
        # spec:mutation-chon-test#S1
        self.build_f()
        sel, c_sel = self.ran()
        self.assertSelection(sel, "theo dòng")
        self.assertGreaterEqual(sel["total"], 8, f"fixture phải có đủ đột biến: {sel}")
        self.assertLessEqual(c_sel["b"], self.SMALL, f"test_b không đi qua dòng đổi: {c_sel}")
        self.assertLessEqual(c_sel["c"], self.SMALL, f"test_c không đi qua dòng đổi: {c_sel}")
        self.assertGreaterEqual(c_sel["a"], sel["total"], f"mỗi đột biến chạy test_a: {c_sel}")
        full, c_full = self.ran("--no-select")
        self.assertFullRuns(full, c_full)
        self.assertSameOutcome(sel, full)

    def test_code_run_in_python_child_process_is_traced(self):
        # spec:mutation-chon-test#S1
        self.build_tool()
        sel, c_sel = self.ran()
        self.assertSelection(sel, "theo dòng")
        self.assertGreaterEqual(sel["total"], 6, f"fixture phải có đủ đột biến: {sel}")
        self.assertLessEqual(c_sel["a"], self.SMALL, f"test_a không đi qua tool.py: {c_sel}")
        self.assertLessEqual(c_sel["b"], self.SMALL, f"test_b không đi qua tool.py: {c_sel}")
        self.assertGreaterEqual(c_sel["c"], sel["total"], f"mỗi đột biến chạy test_c: {c_sel}")
        full, c_full = self.ran("--no-select")
        self.assertGreaterEqual(c_full["a"], full["total"], c_full)
        self.assertGreaterEqual(c_full["b"], full["total"], c_full)
        self.assertSameOutcome(sel, full)
        self.assertEqual(sel["killed"], sel["total"], "mọi đột biến của tool.py bị test_c bắt")

    def test_flags_after_unittest_still_select(self):
        # spec:mutation-chon-test#S1
        self.build_f()
        data, counts = self.ran(cmd="python3 -m unittest -f -q tests.test_x")
        self.assertSelection(data, "theo dòng")
        self.assertGreaterEqual(data["total"], 8, data)
        self.assertLessEqual(counts["b"], self.SMALL, counts)
        self.assertLessEqual(counts["c"], self.SMALL, counts)
        self.assertEqual(data["killed"], data["total"], data)


# ---------------------------------------------------------------------------------------------------------------
class SameResult(SelBase):
    """S2: chọn test không đổi kết quả (bắt, sống, vị trí sống)."""

    def test_survivors_and_uncovered_lines_same_as_full_run(self):
        # spec:mutation-chon-test#S2
        self.build_s2()
        sel, _ = self.ran()
        self.assertSelection(sel, "theo dòng")
        full, _ = self.ran("--no-select")
        self.assertSameOutcome(sel, full)
        want = {line_of(S2_NEW, "    unused = x + 100"), line_of(S2_NEW, "    return x - 7")}
        got = {s["line"] for s in sel["survived"]}
        self.assertEqual(want & got, want, f"đột biến sống ở dòng có test (unused) và dòng không test nào đi qua (never): {sel}")
        self.assertEqual({s["file"] for s in sel["survived"]}, {"sut.py"})
        self.assertGreaterEqual(sel["killed"], 5, f"có đột biến bị bắt, kể cả ở mark: {sel}")
        self.assertGreater(sel["total"], sel["killed"], sel)

    def test_mutant_killed_only_by_test_not_through_the_line(self):
        # spec:mutation-chon-test#S2
        self.build_s2()
        sel, _ = self.ran()
        self.assertSelection(sel, "theo dòng")
        mark_line = line_of(S2_NEW, '    STATE["n"] = STATE["n"] + 1')
        self.assertNotIn(mark_line, {s["line"] for s in sel["survived"]},
                         "đột biến ở mark chỉ test_b (không đi qua dòng) bắt được: phải chạy cả lệnh test rồi mới tính sống")


# ---------------------------------------------------------------------------------------------------------------
class SelectionOff(SelBase):
    """S3, S4: các trường hợp tắt chọn test, vẫn chạy cả lệnh test cho mọi đột biến."""

    def test_no_select_flag(self):
        # spec:mutation-chon-test#S3
        # spec:mutation-chon-test#S4
        self.build_f()
        data, counts = self.ran("--no-select")
        self.assertOff(data, "tắt: --no-select")
        self.assertFullRuns(data, counts)

    def test_no_select_flag_text_has_no_reason_line(self):
        # spec:mutation-chon-test#S4
        self.build_f()
        out, _ = self.mutate("--no-select", as_json=False)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        last = [ln for ln in out.stdout.splitlines() if ln.strip()][-1]
        self.assertTrue(last.startswith("Mutation:"), out.stdout)
        self.assertNotIn("chưa chạy", last, out.stdout)
        self.assertNotIn("chọn test tắt:", out.stdout, "tắt do --no-select thì không cần dòng lý do")
        self.assertIn("đột biến", out.stdout)  # đã chạy thật (cờ lạ làm chương trình thoát với "tham số sai")

    def test_sh_c_command(self):
        # spec:mutation-chon-test#S3
        # spec:mutation-chon-test#S4
        self.build_f()
        data, counts = self.ran(cmd=f"sh -c '{CMD_X}'")
        self.assertOff(data)
        self.assertNotEqual(data["selection"], "tắt: --no-select")
        self.assertFullRuns(data, counts)

    def test_pytest_command(self):
        # spec:mutation-chon-test#S3
        # spec:mutation-chon-test#S4
        self.build_f(extra={"pytest.py": PYTEST_SHIM})  # `python3 -m pytest` chạy bản giả ở gốc project
        data, counts = self.ran(cmd="python3 -m pytest")
        self.assertOff(data)
        self.assertNotEqual(data["selection"], "tắt: --no-select")
        self.assertFullRuns(data, counts)

    def test_project_with_mutmut_config(self):
        # spec:mutation-chon-test#S3
        # spec:mutation-chon-test#S4
        self.build_f(extra={"mutmut_config.py": ""})
        data, counts = self.ran()
        self.assertOff(data)
        self.assertNotEqual(data["selection"], "tắt: --no-select")
        self.assertFullRuns(data, counts)

    def test_failed_trace_step_falls_back_to_full_runs(self):
        # spec:mutation-chon-test#S3
        # spec:mutation-chon-test#S4
        self.build_f()
        data, counts = self.ran(extra_env={"SEL_FAIL_TRACE": "1"})  # test_b trượt khi thấy AGENT_STACK_MUT_TRACE
        self.assertOff(data)
        self.assertNotEqual(data["selection"], "tắt: --no-select")
        self.assertFullRuns(data, counts)

    def test_text_output_names_reason_when_off_not_by_flag(self):
        # spec:mutation-chon-test#S4
        self.build_f()
        out, _ = self.mutate(cmd=f"sh -c '{CMD_X}'", as_json=False)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        lines = [ln for ln in out.stdout.splitlines() if "chọn test tắt:" in ln]
        self.assertEqual(len(lines), 1, out.stdout)
        reason = lines[0].split("chọn test tắt:", 1)[1].strip()
        self.assertTrue(reason, f"dòng phải nêu lý do: {lines[0]!r}")
        last = [ln for ln in out.stdout.splitlines() if ln.strip()][-1]
        self.assertTrue(last.startswith("Mutation:"), "dòng cuối vẫn là dòng trạng thái")
        self.assertNotIn("chưa chạy", last, out.stdout)


class SelectionOn(SelBase):
    def test_json_says_by_line(self):
        # spec:mutation-chon-test#S4
        self.build_f()
        data, _ = self.ran()
        self.assertSelection(data, "theo dòng")

    def test_text_has_no_off_line_when_selecting(self):
        # spec:mutation-chon-test#S4
        self.build_f()
        out, counts = self.mutate(as_json=False)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        last = [ln for ln in out.stdout.splitlines() if ln.strip()][-1]
        self.assertTrue(last.startswith("Mutation:"), out.stdout)
        self.assertNotIn("chưa chạy", last, out.stdout)
        self.assertNotIn("chọn test tắt:", out.stdout)
        self.assertLessEqual(counts["b"], SelectByLine.SMALL, f"phải thật sự chọn test: {counts}")


# ---------------------------------------------------------------------------------------------------------------
def tree_paths(root: Path) -> list:
    """Mọi đường dẫn (file, thư mục) trong cây, trừ .git."""
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if ".git" not in p.relative_to(root).parts)


class Cleanliness(SelBase):
    """S5: xong thì project không đổi, thư mục tạm riêng sạch."""

    def test_project_and_tmpdir_untouched_after_run(self):
        # spec:mutation-chon-test#S5
        self.build_f()
        before = (git(self.repo, "status", "--porcelain"), snapshot(self.repo), tree_paths(self.repo))
        data, _ = self.ran()
        self.assertEqual(git(self.repo, "status", "--porcelain"), before[0])
        self.assertEqual(snapshot(self.repo), before[1])
        self.assertEqual(tree_paths(self.repo), before[2])
        self.assertEqual(list(self.repo.rglob("mutmut_config.py")), [], "không viết mutmut_config.py vào project")
        self.assertEqual(sorted(os.listdir(self.tmpdir)), [], "không còn gì trong thư mục tạm của lần chạy")
        self.assertSelection(data, "theo dòng")  # cuối cùng: đang chọn test thật, không phải chạy như cũ

    def test_project_untouched_when_selection_off_too(self):
        # spec:mutation-chon-test#S5
        self.build_f(extra={"mutmut_config.py": ""})
        before = (git(self.repo, "status", "--porcelain"), snapshot(self.repo), tree_paths(self.repo))
        data, _ = self.ran()
        self.assertEqual(git(self.repo, "status", "--porcelain"), before[0])
        self.assertEqual(snapshot(self.repo), before[1])
        self.assertEqual(tree_paths(self.repo), before[2])
        self.assertEqual(sorted(os.listdir(self.tmpdir)), [])
        self.assertOff(data)


# ---------------------------------------------------------------------------------------------------------------
def ps_lines():
    """[(pid, dòng lệnh đầy đủ)] của mọi tiến trình."""
    out = subprocess.run(["ps", "-axww", "-o", "pid=,command="], capture_output=True, text=True, timeout=30)
    rows = []
    for line in out.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and parts[0].isdigit():
            rows.append((int(parts[0]), parts[1]))
    return rows


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class KilledHard(SelBase):
    """S6: mutation.py bị SIGKILL giữa lúc mutmut chạy thì mutmut, lệnh test và thư mục tạm đều được dọn."""

    def under_tmpdir(self):
        """pid các tiến trình có đường dẫn TMPDIR riêng trong dòng lệnh (mutmut, và nếu có, tiến trình canh)."""
        me = os.getpid()
        return [pid for pid, cmd in ps_lines() if str(self.tmpdir) in cmd and pid != me]

    def mutmut_running(self):
        return [pid for pid, cmd in ps_lines() if str(self.tmpdir) in cmd and "mutmut" in cmd and "--use-patch-file" in cmd]

    def read_pids(self):
        try:
            return [int(x) for x in self.pidfile.read_text(encoding="utf-8").split()]
        except (OSError, ValueError):
            return []

    def reap(self, proc):
        """Dọn mọi thứ còn sót để test không để rác."""
        for _ in range(3):
            for pid in set(self.under_tmpdir()) | set(self.read_pids()):
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
            time.sleep(0.2)
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        proc.wait()

    def test_sigkill_leaves_no_process_and_no_tmpdir(self):
        # spec:mutation-chon-test#S6
        self.build_f()
        self.pidfile = self.tmp / "slow.pids"
        argv = [sys.executable, str(SCRIPT), "--project", str(self.repo), "--cmd", CMD_X, "--timeout", "300",
                "--jobs", "1", "--json"]
        env = self.env(self.tmp / "sel.log", {"SEL_PIDS": str(self.pidfile)})  # test_a ngủ lâu (trừ bước ghi vết)
        proc = subprocess.Popen(argv, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                start_new_session=True)
        self.addCleanup(self.reap, proc)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            self.assertIsNone(proc.poll(), "mutation.py thoát trước khi mutmut chạy test chậm")
            if self.mutmut_running() and len(self.read_pids()) >= 2:
                break
            time.sleep(0.2)
        mutmut_before, test_pids = self.mutmut_running(), self.read_pids()
        self.assertTrue(mutmut_before and len(test_pids) >= 2, "mutmut và lệnh test chậm phải đang chạy trước khi giết")
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait()
        stop = time.monotonic() + 10
        while time.monotonic() < stop:
            if (not self.under_tmpdir() and not any(alive(p) for p in test_pids)
                    and not os.listdir(self.tmpdir)):
                break
            time.sleep(0.2)
        self.assertEqual(self.under_tmpdir(), [], "tiến trình có đường dẫn thư mục tạm còn sống sau 10 giây")
        self.assertEqual([p for p in test_pids if alive(p)], [], "lệnh test của mutmut còn sống sau 10 giây")
        self.assertEqual(sorted(os.listdir(self.tmpdir)), [], "thư mục tạm của lần chạy phải bị xóa")
