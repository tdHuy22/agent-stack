"""mutation.py với nhiều file đổi và chạy song song (spec `mutation-nhieu-file`, file `.agent/spec/mutation-nhieu-file.txt`).

Viết trước code. Dùng mutmut GIẢ (nhiều lần `run`, tạo `.bak`, ghi pid con, junitxml sinh từ chính bản vá nhận được) để
kiểm cách gọi; một test tích hợp chạy mutmut 2.5.1 thật khi có `.venv-mutmut/bin/mutmut`. Bản vá được đọc lại bằng hàm
`read_patch_data` thật của mutmut (venv riêng) hay bằng `patch_added` dưới đây (đi qua từng hunk).
"""
import inspect
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import time
from pathlib import Path

from tests._util import REPO, git
from tests.test_mutation import CMD, REAL_MUTMUT, SCRIPT, MutationBase

REAL_PY = REPO / ".venv-mutmut" / "bin" / "python"


def patch_added(text):
    """{tên file chuẩn hóa: tập số dòng thêm} của một bản vá (git hay hợp nhất): đi qua từng hunk, đếm dòng mới từ
    số bắt đầu `+s`, dòng `+` là dòng thêm, dòng ngữ cảnh tăng số dòng, dòng `-` không tăng."""
    out = {}
    name = None
    old_left = new_left = new_no = 0
    in_hunk = False
    for line in text.splitlines():
        if in_hunk and (old_left > 0 or new_left > 0):
            if line.startswith("\\"):
                continue
            tag = line[:1]
            if tag == "+":
                out.setdefault(name, set()).add(new_no)
                new_no += 1
                new_left -= 1
            elif tag == "-":
                old_left -= 1
            else:
                new_no += 1
                new_left -= 1
                old_left -= 1
            continue
        if line.startswith("+++ "):
            name = os.path.normpath(line[4:].split("\t")[0].strip().removeprefix("b/"))
        elif line.startswith("@@"):
            m = re.match(r"@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if m:
                old_left = int(m.group(1)) if m.group(1) is not None else 1
                new_no = int(m.group(2))
                new_left = int(m.group(3)) if m.group(3) is not None else 1
                in_hunk = True
    return {k: v for k, v in out.items() if v}


# mutmut giả cho nhiều lần chạy. `run`: ghi bản vá + danh sách file vào .fake_run.json trong cwd; với FAKE_BAK thì tạo
# `<file>.bak` (bản gốc) rồi ghi rác vào file như mutmut thật khi bị giết giữa chừng; FAKE_MUTMUT_PIDFILE: ghi pid một
# tiến trình con ngủ lâu (chế độ append, dùng chung); ngủ FAKE_MUTMUT_SLEEP giây. Mọi lời gọi ghi một dòng JSON vào
# FAKE_MUTMUT_LOG, kèm nội dung hiện tại của các file đang đột biến (`files`) và có `.bak` hay không (`bak`).
# `junitxml`: FAKE_MUTMUT_XML (file XML) nếu có; FAKE_MUTMUT_XML_BROKEN thì hỏng (stderr, thoát 1); không thì mỗi dòng
# thêm trong bản vá của lần chạy này là một đột biến sống. `result-ids`: killed/untested/survived theo biến môi trường.
FAKE_HEAD = "#!/usr/bin/env python3\nimport json, os, re, shutil, subprocess, sys, time\n"
FAKE_BODY = r'''

argv = sys.argv[1:]


def opt(name):
    return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else None


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


cmd = argv[0] if argv else ""
patch_path = opt("--use-patch-file")
state = None
if cmd != "run":
    try:
        state = json.loads(read(".fake_run.json"))
    except (TypeError, ValueError):
        state = None
rec = {"argv": argv, "cwd": os.getcwd(), "patch": read(patch_path) if patch_path else None}
if cmd == "run":
    paths = [p for p in (opt("--paths-to-mutate") or "").split(",") if p]
    rec["files"] = {p: read(p) for p in paths}
elif state:
    rec["files"] = {p: read(p) for p in state["paths"]}
    rec["bak"] = {p: os.path.exists(p + ".bak") for p in state["paths"]}
with open(os.environ["FAKE_MUTMUT_LOG"], "a", encoding="utf-8") as f:
    f.write(json.dumps(rec) + "\n")

if cmd == "run":
    with open(".fake_run.json", "w", encoding="utf-8") as f:
        json.dump({"patch": rec["patch"], "paths": paths}, f)
    if os.environ.get("FAKE_BAK"):
        for p in paths:
            if os.path.exists(p):
                shutil.copy(p, p + ".bak")
                with open(p, "w", encoding="utf-8") as f:
                    f.write("GARBAGE = (\n")
    pidfile = os.environ.get("FAKE_MUTMUT_PIDFILE")
    if pidfile:
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        with open(pidfile, "a", encoding="utf-8") as f:
            f.write(str(child.pid) + "\n")
    time.sleep(float(os.environ.get("FAKE_MUTMUT_SLEEP", "0")))
    sys.exit(int(os.environ.get("FAKE_MUTMUT_RUN_EXIT", "0")))
elif cmd == "junitxml":
    if os.environ.get("FAKE_MUTMUT_XML_BROKEN"):
        sys.stderr.write("Traceback (most recent call last):\n"
                         "pony.orm.core.OperationWithDeletedObjectError: Object was deleted\n")
        sys.exit(1)
    xml = os.environ.get("FAKE_MUTMUT_XML")
    if xml:
        sys.stdout.write(read(xml))
    else:
        added = patch_added((state or {}).get("patch") or "")
        cases, n = [], 0
        for name in sorted(added):
            for line in sorted(added[name]):
                n += 1
                cases.append('<testcase classname="%s" file="%s" line="%d" name="Mutant #%d">'
                             '<failure message="Mutant survived"/></testcase>' % (name, name, line, n))
        sys.stdout.write('<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="mutmut">'
                         + "".join(cases) + "</testsuite></testsuites>")
elif cmd == "result-ids" and len(argv) > 1:
    if argv[1] == "killed":
        print(os.environ.get("FAKE_MUTMUT_KILLED", "1 2 3"))
    elif argv[1] == "untested":
        print(os.environ.get("FAKE_MUTMUT_UNTESTED", ""))
    elif argv[1] == "survived":
        print(os.environ.get("FAKE_MUTMUT_SURVIVED", ""))
'''
PAR_FAKE = FAKE_HEAD + inspect.getsource(patch_added) + FAKE_BODY


def xml_of(cases):
    """XML kiểu mutmut: mỗi phần tử (id, file, dòng, trạng thái) với trạng thái killed / survived / timeout."""
    out = []
    for mid, name, line, st in cases:
        inner = {"survived": '<failure message="Mutant survived"/>',
                 "timeout": '<error type="timeout" message="t"/>'}.get(st, "")
        out.append(f'<testcase classname="{name}" file="{name}" line="{line}" name="Mutant #{mid}">{inner}</testcase>')
    return ('<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="mutmut">' + "".join(out)
            + "</testsuite></testsuites>")


def expected_jobs(code):
    return max(1, min(4, (os.cpu_count() or 1) // 2, code // 10))


class ParBase(MutationBase):
    """Repo gốc + mutmut giả nhiều lần chạy."""

    def make_fake(self, path: Path) -> Path:
        path.write_text(PAR_FAKE, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return path

    def setUp(self):
        super().setUp()
        self.init_repo()

    # ---- dựng diff ----
    def build(self, calc_code, new_code, comments=0):
        """calc.py thêm `calc_code` dòng code (cùng một dòng trống và `comments` dòng chú thích); newmod.py mới có
        `new_code` dòng code."""
        extra = ("\n" + "".join(f"V{i} = {i}\n" for i in range(calc_code))
                 + "".join(f"# ghi chú {i}\n" for i in range(comments)))
        self.append("calc.py", extra)
        if new_code:
            (self.repo / "newmod.py").write_text("".join(f"W{i} = {i}\n" for i in range(new_code)), encoding="utf-8")

    def git_added(self):
        """Dòng thêm theo git cho file Python code đổi: {file: tập dòng}; file mới chưa theo dõi thì mọi dòng."""
        added = patch_added(git(self.repo, "diff", "-U0", "HEAD"))
        for rel in git(self.repo, "ls-files", "--others", "--exclude-standard").splitlines():
            if rel.endswith(".py"):
                n = len((self.repo / rel).read_text(encoding="utf-8").splitlines())
                added[rel] = set(range(1, n + 1))
        return {f: s for f, s in added.items() if f.endswith(".py") and not f.startswith("tests/") and s}

    def code_count(self, added):
        n = 0
        for name, lines in added.items():
            text = (self.repo / name).read_text(encoding="utf-8").splitlines()
            n += sum(1 for i in lines if text[i - 1].strip() and not text[i - 1].strip().startswith("#"))
        return n

    # ---- đọc kết quả ----
    def runs(self):
        return [c for c in self.calls() if c["argv"][:1] == ["run"]]

    def only_run(self):
        runs = self.runs()
        self.assertEqual(len(runs), 1, f"phải có đúng một lần `mutmut run`: {self.calls()}")
        return runs[0]

    def data(self, out):
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        return json.loads(out.stdout)

    def run_paths(self, run):
        return {os.path.normpath(p) for p in self.opt(run["argv"], "--paths-to-mutate").split(",")}

    def assertPartition(self, truth, expected_runs):
        """Số lần chạy, cwd riêng đã xóa, truy vấn cùng cwd, bản vá ghép lại đúng dòng thêm theo git, không giao nhau."""
        runs = self.runs()
        self.assertEqual(len(runs), expected_runs, f"số lần `mutmut run`: {[r['argv'] for r in runs]}")
        cwds = [r["cwd"] for r in runs]
        self.assertEqual(len(set(cwds)), len(cwds), "mỗi lần chạy một bản chép (cwd) riêng")
        for cwd in cwds:
            self.assertFalse(Path(cwd).exists(), "bản chép phải bị xóa khi xong")
        merged, seen = {}, 0
        for run in runs:
            self.assertIsInstance(run["patch"], str, "bản vá phải tồn tại lúc `mutmut run`")
            added = patch_added(run["patch"])
            self.assertEqual(self.run_paths(run), set(added), "--paths-to-mutate chỉ gồm file có dòng trong bản vá")
            for name, lines in added.items():
                merged.setdefault(name, set()).update(lines)
                seen += len(lines)
        self.assertEqual(merged, truth, "hợp bản vá phải bằng đúng dòng thêm theo git")
        self.assertEqual(seen, sum(len(s) for s in truth.values()), "mỗi dòng thêm thuộc đúng một lần chạy")
        calls = self.calls()
        for c in calls:
            if c["argv"][:1] != ["run"]:
                self.assertIn(c["cwd"], cwds, "lệnh truy vấn phải chạy trong cwd của lần chạy của nó")
        for cwd in cwds:
            names = [c["argv"] for c in calls if c["cwd"] == cwd]
            self.assertEqual(names[0][0], "run")
            self.assertIn(["junitxml"], names[1:])
        return runs

    def real_read(self, patch_text):
        """Cho bản vá qua hàm mutmut thật dùng: {tên file: danh sách dòng đã sắp}."""
        path = self.tmp / "p.patch"
        path.write_text(patch_text, encoding="utf-8")
        code = ("import json, sys\nfrom mutmut import read_patch_data\n"
                "print(json.dumps({k: sorted(v) for k, v in read_patch_data(sys.argv[1]).items()}))")
        out = subprocess.run([str(REAL_PY), "-c", code, str(path)], capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        return {os.path.normpath(k): v for k, v in json.loads(out.stdout).items()}

    def need_cores(self, n):
        if (os.cpu_count() or 1) // 2 < n:
            self.skipTest(f"máy cần ít nhất {2 * n} lõi")


class PatchPerFile(ParBase):
    """S1: mỗi đột biến nằm trên dòng thêm của chính file chứa nó."""

    def setUp(self):
        super().setUp()
        if not REAL_PY.exists():
            self.skipTest(f"chưa có {REAL_PY}")

    def test_two_files_patch_maps_lines_to_own_file(self):
        # spec:mutation-nhieu-file#S1
        self.change_code()  # calc.py sửa, newmod.py mới
        truth = self.git_added()
        self.assertEqual(set(truth), {"calc.py", "newmod.py"})
        out = self.mut("--json", "--cmd", "true", *self.fake_args())
        self.data(out)
        run = self.only_run()
        got = self.real_read(run["patch"])
        self.assertEqual(got, {f: sorted(s) for f, s in truth.items()})
        self.assertEqual(set(got), self.run_paths(run), "key phải bằng đúng đường dẫn trong --paths-to-mutate")

    def test_three_modified_files_in_one_patch(self):
        # spec:mutation-nhieu-file#S1
        (self.repo / "newmod.py").write_text("W0 = 0\nW1 = 1\n", encoding="utf-8")
        (self.repo / "calc.py").write_text(CALC_WITH_MIDDLE, encoding="utf-8")  # thêm dòng ở giữa, không chỉ cuối file
        (self.repo / "tests" / "test_calc.py").write_text(
            (self.repo / "tests" / "test_calc.py").read_text(encoding="utf-8") + "\n# đổi test\n", encoding="utf-8")
        truth = self.git_added()
        out = self.mut("--json", "--jobs", "1", "--cmd", "true", *self.fake_args())
        self.data(out)
        got = self.real_read(self.only_run()["patch"])
        self.assertEqual(got, {f: sorted(s) for f, s in truth.items()})

    def add_dirs(self):
        """Thư mục tên `a` và `b` có file Python; cam kết vào bản gốc."""
        for rel in ("a/m.py", "b/m.py"):
            path = self.repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("def old():\n    return 1\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "dirs")

    def test_files_inside_dirs_named_a_and_b(self):
        # spec:mutation-nhieu-file#S1
        self.add_dirs()
        for rel in ("a/m.py", "b/m.py"):
            with open(self.repo / rel, "a", encoding="utf-8") as f:
                f.write("\n\ndef extra(x):\n    return x + 1\n")
        (self.repo / "b" / "n.py").write_text("def fresh(x):\n    return x * 2\n", encoding="utf-8")
        self.change_code()
        truth = self.git_added()
        self.assertEqual(set(truth), {"a/m.py", "b/m.py", "b/n.py", "calc.py", "newmod.py"})
        out = self.mut("--json", "--jobs", "1", "--cmd", "true", *self.fake_args())
        self.data(out)
        run = self.only_run()
        got = self.real_read(run["patch"])
        self.assertEqual(got, {f: sorted(s) for f, s in truth.items()})
        self.assertEqual(set(got), self.run_paths(run))

    def test_dirs_a_and_b_split_across_parallel_runs(self):
        # spec:mutation-nhieu-file#S1
        self.add_dirs()
        for rel in ("a/m.py", "b/m.py"):
            with open(self.repo / rel, "a", encoding="utf-8") as f:
                f.write("\n" + "".join(f"Z{i} = {i}\n" for i in range(8)))
        self.build(8, 8)
        truth = self.git_added()
        out = self.mut("--json", "--jobs", "3", "--cmd", "true", *self.fake_args())
        self.data(out)
        runs = self.runs()
        self.assertEqual(len(runs), 3)
        merged = {}
        for run in runs:
            got = self.real_read(run["patch"])
            self.assertEqual(set(got), self.run_paths(run))
            for name, lines in got.items():
                self.assertEqual(set(lines) - truth[name], set(), f"{name}: dòng không phải dòng thêm")
                self.assertEqual(set(lines) & merged.get(name, set()), set(), f"{name}: dòng trùng giữa các lần chạy")
                merged.setdefault(name, set()).update(lines)
        self.assertEqual(merged, truth)


CALC_WITH_MIDDLE = ('"""Máy tính."""\n\n\nMID = 1\n\n\ndef add(a, b):\n    return a + b\n'
                    + "\n" + "".join(f"V{i} = {i}\n" for i in range(3)))


class RealMutmutTwoFiles(ParBase):
    """S1 với mutmut 2.5.1 thật: hai file đổi, mỗi file một hàm mới mà test không gọi."""

    def test_real_mutmut_mutates_both_files_on_their_own_lines(self):
        # spec:mutation-nhieu-file#S1
        if not REAL_MUTMUT.exists():
            self.skipTest(f"chưa có {REAL_MUTMUT}")
        self.change_code()  # calc.py thêm neg, newmod.py mới có sq; tests/test_calc.py chỉ gọi add
        truth = self.git_added()
        env = dict(os.environ, AGENT_STACK_STATE=str(self.state))
        out = subprocess.run(
            [sys.executable, str(SCRIPT), "--project", str(self.repo), "--cmd", shlex.join(CMD), "--timeout", "300",
             "--json"], capture_output=True, text=True, env=env, timeout=400)
        data = self.data(out)
        self.assertEqual(data["status"], "ran", data)
        self.assertEqual(data.get("outside"), [], data)
        survived = {}
        for s in data["survived"]:
            survived.setdefault(s["file"], set()).add(s["line"])
        self.assertEqual(set(survived), {"calc.py", "newmod.py"}, f"cả hai file phải có đột biến sống: {data}")
        for name, lines in survived.items():
            self.assertEqual(lines - truth[name], set(), f"{name}: đột biến sống ngoài dòng thêm: {data}")


class OutsideChanged(ParBase):
    """S2: đột biến ở file hay dòng không thuộc dòng thêm được ghi riêng."""

    def setUp(self):
        super().setUp()
        self.change_code()  # calc.py dòng 6-9 thêm, newmod.py dòng 1-2 thêm
        self.assertEqual(self.git_added(), {"calc.py": {6, 7, 8, 9}, "newmod.py": {1, 2}})

    XML = xml_of([(1, "calc.py", 8, "survived"), (2, "newmod.py", 2, "survived"), (3, "calc.py", 4, "killed"),
                  (4, "calc.py", 5, "survived"), (5, "other.py", 3, "survived"), (6, "calc.py", 3, "timeout"),
                  (7, "calc.py", 9, "killed")])

    def mutate(self, *extra):
        xml = self.write("outside.xml", self.XML)
        return self.mut("--cmd", "true", *extra, *self.fake_args(), env={"FAKE_MUTMUT_XML": str(xml)})

    def test_json_outside_lists_exactly_the_stray_mutants(self):
        # spec:mutation-nhieu-file#S2
        data = self.data(self.mutate("--json"))
        outside = data.get("outside")
        self.assertIsInstance(outside, list, data)
        self.assertEqual(sorted((o["file"], o["line"]) for o in outside),
                         [("calc.py", 3), ("calc.py", 4), ("calc.py", 5), ("other.py", 3)])
        self.assertEqual({(s["file"], s["line"]) for s in data["survived"]},
                         {("calc.py", 8), ("newmod.py", 2), ("calc.py", 5), ("other.py", 3)},
                         "đột biến sống ngoài dòng đổi vẫn nằm trong survived")

    def test_text_output_has_warning_line_with_positions(self):
        # spec:mutation-nhieu-file#S2
        out = self.mutate()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.status_line(out)
        warn = [ln for ln in out.stdout.splitlines() if "ngoài dòng đổi" in ln]
        self.assertTrue(warn, out.stdout)
        text = "\n".join(warn)
        for pos in ("calc.py:3", "calc.py:4", "calc.py:5", "other.py:3"):
            self.assertIn(pos, text)
        for pos in ("calc.py:8", "calc.py:9", "newmod.py:2"):
            self.assertNotIn(pos, text, "vị trí trên dòng thêm không được ghi là ngoài dòng đổi")

    def test_no_outside_when_every_mutant_is_on_an_added_line(self):
        # spec:mutation-nhieu-file#S2
        xml = self.write("inside.xml", xml_of([(1, "calc.py", 8, "survived"), (2, "newmod.py", 2, "survived"),
                                              (3, "calc.py", 6, "killed"), (4, "calc.py", 9, "timeout")]))
        out = self.mut("--json", "--cmd", "true", *self.fake_args(), env={"FAKE_MUTMUT_XML": str(xml)})
        data = self.data(out)
        self.assertEqual(data.get("outside"), [], data)
        out = self.mut("--cmd", "true", *self.fake_args(), env={"FAKE_MUTMUT_XML": str(xml)})
        self.assertNotIn("ngoài dòng đổi", out.stdout)


class AutoJobs(ParBase):
    """S3: số lần chạy song song khi không nêu --jobs."""

    def test_big_diff_splits_into_computed_number_of_runs(self):
        # spec:mutation-nhieu-file#S3
        self.need_cores(2)
        self.build(30, 24, comments=6)
        truth = self.git_added()
        code = self.code_count(truth)
        self.assertEqual(code, 54)
        want = expected_jobs(code)
        self.assertGreaterEqual(want, 2)
        out = self.mut("--json", "--cmd", "true", *self.fake_args())
        data = self.data(out)
        self.assertEqual(data.get("jobs"), want, data)
        self.assertPartition(truth, want)
        n = sum(len(s) for s in truth.values())
        self.assertEqual(data["total"], n, "tổng đột biến cộng qua các lần chạy")
        self.assertEqual(len(data["survived"]), n, "survived nối danh sách")
        self.assertEqual(data["killed"], 3 * want, "killed cộng qua các lần chạy")
        self.assertEqual((data["timeout"], data["untested"]), (0, 0))
        self.assertEqual(data.get("outside"), [], data)

    def test_twenty_code_lines_is_two_runs_comments_do_not_count(self):
        # spec:mutation-nhieu-file#S3
        self.need_cores(2)
        self.build(10, 10, comments=5)
        truth = self.git_added()
        self.assertEqual(self.code_count(truth), 20)
        out = self.mut("--json", "--cmd", "true", *self.fake_args())
        data = self.data(out)
        self.assertEqual(data.get("jobs"), 2, data)
        self.assertPartition(truth, 2)

    def test_nineteen_code_lines_stay_one_run_despite_many_comment_lines(self):
        # spec:mutation-nhieu-file#S3
        self.build(10, 9, comments=40)
        truth = self.git_added()
        self.assertEqual(self.code_count(truth), 19)
        self.assertGreater(sum(len(s) for s in truth.values()), 50, "nhiều dòng thêm nhưng ít dòng code")
        out = self.mut("--json", "--cmd", "true", *self.fake_args())
        data = self.data(out)
        self.assertEqual(data.get("jobs"), 1, data)
        self.assertPartition(truth, 1)

    def test_small_diff_is_exactly_one_run_as_before(self):
        # spec:mutation-nhieu-file#S3
        self.build(8, 7)
        truth = self.git_added()
        self.assertEqual(self.code_count(truth), 15)
        out = self.mut("--json", "--cmd", "true", *self.fake_args())
        data = self.data(out)
        self.assertEqual(data.get("jobs"), 1, data)
        self.assertPartition(truth, 1)
        self.assertEqual(data["total"], sum(len(s) for s in truth.values()))
        self.assertEqual(data["killed"], 3)


class ExplicitJobs(ParBase):
    """S4: --jobs N."""

    def test_jobs_three_on_big_diff(self):
        # spec:mutation-nhieu-file#S4
        self.build(30, 24)
        truth = self.git_added()
        data = self.data(self.mut("--json", "--jobs", "3", "--cmd", "true", *self.fake_args()))
        self.assertEqual(data.get("jobs"), 3, data)
        self.assertPartition(truth, 3)
        self.assertEqual(data["killed"], 9)

    def test_jobs_larger_than_code_lines_is_capped(self):
        # spec:mutation-nhieu-file#S4
        self.build(3, 2)
        truth = self.git_added()
        self.assertEqual(self.code_count(truth), 5)
        data = self.data(self.mut("--json", "--jobs", "8", "--cmd", "true", *self.fake_args()))
        self.assertEqual(data.get("jobs"), 5, data)
        runs = self.assertPartition(truth, 5)
        per_run = [self.code_count(patch_added(r["patch"])) for r in runs]
        self.assertEqual(per_run, [1] * 5, "mỗi lần chạy có việc: một dòng code")

    def test_jobs_one_is_a_single_run_with_every_added_line(self):
        # spec:mutation-nhieu-file#S4
        self.build(30, 24)
        truth = self.git_added()
        data = self.data(self.mut("--json", "--jobs", "1", "--cmd", "true", *self.fake_args()))
        self.assertEqual(data.get("jobs"), 1, data)
        self.assertPartition(truth, 1)

    def test_jobs_beats_the_automatic_choice(self):
        # spec:mutation-nhieu-file#S4
        self.build(10, 9, comments=40)  # 19 dòng code: tự chọn sẽ là 1
        truth = self.git_added()
        data = self.data(self.mut("--json", "--jobs", "2", "--cmd", "true", *self.fake_args()))
        self.assertEqual(data.get("jobs"), 2, data)
        self.assertPartition(truth, 2)

    def test_invalid_jobs_values_are_skipped_not_run(self):
        # spec:mutation-nhieu-file#S4
        self.build(30, 24)
        ok = self.data(self.mut("--json", "--jobs", "2", "--cmd", "true", *self.fake_args()))
        self.assertEqual(ok.get("jobs"), 2, "giá trị hợp lệ phải được nhận")
        self.log.unlink()
        for value in ("0", "-1", "abc", "1.5"):
            with self.subTest(jobs=value):
                out = self.mut("--jobs", value, "--cmd", "true", *self.fake_args())
                self.assertSkipped(out, "tham số sai")

    def test_invalid_jobs_json_status(self):
        # spec:mutation-nhieu-file#S4
        self.build(30, 24)
        ok = self.data(self.mut("--json", "--jobs", "2", "--cmd", "true", *self.fake_args()))
        self.assertEqual(ok.get("jobs"), 2, "giá trị hợp lệ phải được nhận")
        self.log.unlink()
        data = self.data(self.mut("--json", "--jobs", "0", "--cmd", "true", *self.fake_args()))
        self.assertEqual(data["status"], "skipped")
        self.assertIn("tham số sai", data["reason"])
        self.assertEqual(self.calls(), [])


class TimeoutParallel(ParBase):
    """S5: hết giờ thì giết cả nhóm, xóa bản chép, trả file đột biến dở về bản gốc trước khi đọc kết quả."""

    def setUp(self):
        super().setUp()
        self.pidfile = self.tmp / "children.pid"
        self.slow = {"FAKE_MUTMUT_SLEEP": "30", "FAKE_MUTMUT_PIDFILE": str(self.pidfile), "FAKE_BAK": "1"}

    def alive(self, pid):
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def check_timeout_run(self, out, expected_runs, started):
        self.assertLess(time.monotonic() - started, 25, "phải dừng ngay khi quá giờ")
        data = self.data(out)
        self.assertIn(data["status"], ("skipped", "partial"), data)
        self.assertIn("quá giờ", data["reason"])
        runs = self.runs()
        self.assertEqual(len(runs), expected_runs)
        pids = [int(x) for x in self.pidfile.read_text(encoding="utf-8").split()]
        self.assertEqual(len(pids), expected_runs, "mỗi lần chạy có một tiến trình con")
        for pid in pids:
            self.addCleanup(lambda p=pid: self.alive(p) and os.kill(p, 9))
        by_cwd = {r["cwd"]: r for r in runs}
        self.assertEqual(len(by_cwd), expected_runs, "cwd riêng cho từng lần chạy")
        for run in runs:
            self.assertFalse(Path(run["cwd"]).exists(), "mọi bản chép phải bị xóa")
            self.assertTrue(all(isinstance(v, str) for v in run["files"].values()), run["files"])
        queries = [c for c in self.calls() if c["argv"][:1] != ["run"]]
        for cwd, run in by_cwd.items():
            mine = [c for c in queries if c["cwd"] == cwd]
            self.assertGreaterEqual(len(mine), 1, "mỗi lần chạy phải được đọc kết quả")
            for c in mine:
                self.assertEqual(c["files"], run["files"], f"{c['argv']}: file phải là bản gốc, không phải rác dở dang")
                self.assertEqual(set(c["bak"].values()), {False}, f"{c['argv']}: không còn .bak")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and any(self.alive(p) for p in pids):
            time.sleep(0.1)
        self.assertEqual([p for p in pids if self.alive(p)], [], "tiến trình con của mọi lần chạy phải chết")

    def test_parallel_runs_killed_restored_and_cleaned(self):
        # spec:mutation-nhieu-file#S5
        self.build(15, 12)
        started = time.monotonic()
        out = self.mut("--json", "--jobs", "3", "--timeout", "2", "--cmd", "true", *self.fake_args(), env=self.slow)
        self.check_timeout_run(out, 3, started)

    def test_single_run_restored_too(self):
        # spec:mutation-nhieu-file#S5
        self.change_code()
        started = time.monotonic()
        out = self.mut("--json", "--timeout", "2", "--cmd", "true", *self.fake_args(), env=self.slow)
        self.check_timeout_run(out, 1, started)


class Unreached(ParBase):
    """S6: đột biến chưa chạy tới được liệt kê theo khoảng dòng, kèm ước số giây."""

    def setUp(self):
        super().setUp()
        self.build(22, 3)  # calc.py dòng 6 (trống), 7-28 (code); newmod.py dòng 1-3
        self.assertEqual(self.git_added(), {"calc.py": set(range(6, 29)), "newmod.py": {1, 2, 3}})
        self.xml = self.write("partial.xml", xml_of([
            (1, "calc.py", 7, "killed"), (2, "calc.py", 25, "survived"), (3, "newmod.py", 3, "killed"),
            (4, "calc.py", 11, "killed"),
            (11, "calc.py", 8, "killed"), (12, "calc.py", 9, "killed"), (13, "calc.py", 9, "killed"),
            (14, "calc.py", 10, "killed"), (15, "calc.py", 20, "killed"), (16, "newmod.py", 2, "killed")]))
        self.env = {"FAKE_MUTMUT_XML": str(self.xml), "FAKE_MUTMUT_KILLED": "1 3 4",
                    "FAKE_MUTMUT_SURVIVED": "2", "FAKE_MUTMUT_UNTESTED": "11 12 13 14 15 16",
                    "FAKE_MUTMUT_SLEEP": "30"}

    WANT = [{"file": "calc.py", "start": 8, "end": 10, "mutants": 4},
            {"file": "calc.py", "start": 20, "end": 20, "mutants": 1},
            {"file": "newmod.py", "start": 2, "end": 2, "mutants": 1}]

    def mutate(self, *extra, env=None):
        full = dict(self.env)
        full.update(env or {})
        return self.mut("--jobs", "1", "--timeout", "2", "--cmd", "true", *extra, *self.fake_args(), env=full)

    def test_json_unreached_ranges_per_file(self):
        # spec:mutation-nhieu-file#S6
        data = self.data(self.mutate("--json"))
        self.assertEqual(data["untested"], 6, data)
        self.assertEqual(data.get("unreached"), self.WANT, data)
        self.assertEqual(data.get("unreached_known", True), True, data)
        estimate = data.get("estimate_seconds")
        self.assertIsInstance(estimate, (int, float), data)
        self.assertGreater(estimate, 0)

    def test_text_lists_positions_and_hints_timeout(self):
        # spec:mutation-nhieu-file#S6
        out = self.mutate()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.status_line(out)
        lines = [ln for ln in out.stdout.splitlines() if "chưa chạy tới:" in ln]
        self.assertEqual(len(lines), 1, out.stdout)
        for pos in ("calc.py:8-10", "calc.py:20", "newmod.py:2"):
            self.assertIn(pos, lines[0])
        for pos in ("calc.py:11", "calc.py:7", "newmod.py:3", "calc.py:25"):
            self.assertNotIn(pos, lines[0], "chỉ liệt kê đột biến chưa chạy tới")
        self.assertIn("--timeout", out.stdout)

    def test_unreached_reported_without_timeout_too(self):
        # spec:mutation-nhieu-file#S6
        out = self.mut("--json", "--jobs", "1", "--cmd", "true", *self.fake_args(),
                       env=dict(self.env, FAKE_MUTMUT_SLEEP="1"))
        data = self.data(out)
        self.assertEqual(data.get("unreached"), self.WANT, data)
        self.assertGreater(data.get("estimate_seconds") or 0, 0, data)

    def test_nothing_unreached_means_empty_list_and_zero_estimate(self):
        # spec:mutation-nhieu-file#S6
        env = dict(self.env, FAKE_MUTMUT_UNTESTED="")
        data = self.data(self.mutate("--json", env=env))
        self.assertEqual(data["untested"], 0)
        self.assertEqual(data.get("unreached"), [], data)
        self.assertEqual(data.get("estimate_seconds"), 0, data)
        out = self.mutate(env=env)
        self.assertNotIn("chưa chạy tới:", out.stdout)

    def test_broken_junitxml_says_positions_unknown(self):
        # spec:mutation-nhieu-file#S6
        env = {"FAKE_MUTMUT_XML_BROKEN": "1", "FAKE_MUTMUT_KILLED": "1 2", "FAKE_MUTMUT_SURVIVED": "",
               "FAKE_MUTMUT_UNTESTED": "3 4"}
        data = self.data(self.mutate("--json", env=env))
        self.assertEqual(data["untested"], 2, data)
        self.assertEqual(data.get("unreached_known"), False, data)
        self.assertEqual(data.get("unreached"), [], data)
        self.assertGreater(data.get("estimate_seconds") or 0, 0, data)

    def test_broken_junitxml_text_says_positions_unknown(self):
        # spec:mutation-nhieu-file#S6
        env = {"FAKE_MUTMUT_XML_BROKEN": "1", "FAKE_MUTMUT_KILLED": "1 2", "FAKE_MUTMUT_SURVIVED": "",
               "FAKE_MUTMUT_UNTESTED": "3 4"}
        out = self.mutate(env=env)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.status_line(out)
        self.assertIn("không lấy được vị trí", out.stdout)
        self.assertIn("--timeout", out.stdout)
