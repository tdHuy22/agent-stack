"""mutation.py: test siết sau review vòng 1 (16/11/2026, opus·xhigh, sonnet·xhigh, differential-review) cho bản sửa
nhiều file và chạy song song (spec `mutation-nhieu-file`). Mỗi test giữ một lỗi reviewer đã tái hiện."""
import json
import os
import stat
from pathlib import Path

from tests._util import git
from tests.test_mutation import CALC_BASE, CALC_EXTRA, MutationBase
from tests.test_mutation_parallel import ParBase, patch_added

# mutmut giả: lần `run` đầu tiên (đánh dấu trong FAKE_SHARED) trượt baseline như mutmut thật; các lần sau đạt. `junitxml`
# của lần trượt không có testcase; của lần đạt: một đột biến sống ở dòng thêm đầu tiên trong bản vá. Ghi mỗi lần gọi vào
# FAKE_MUTMUT_LOG, kèm `bak_at_start` (có `<file>.bak` lúc `run` bắt đầu không). `run` ghi vào `<file>.bak` như mutmut.
FAKE = r'''#!/usr/bin/env python3
import json, os, re, sys

argv = sys.argv[1:]
cmd = argv[0] if argv else ""


def opt(name):
    return argv[argv.index(name) + 1] if name in argv else None


paths = [p for p in (opt("--paths-to-mutate") or "").split(",") if p]
rec = {"argv": argv, "cwd": os.getcwd(), "bak_at_start": {p: os.path.lexists(p + ".bak") for p in paths}}
with open(os.environ["FAKE_MUTMUT_LOG"], "a", encoding="utf-8") as f:
    f.write(json.dumps(rec) + "\n")
if cmd == "run":
    for p in paths:
        with open(p + ".bak", "w", encoding="utf-8") as f:
            f.write("BAN SAO\n")
    with open(opt("--use-patch-file"), encoding="utf-8") as f:
        patch = f.read()
    shared = os.environ.get("FAKE_SHARED")
    try:  # tạo nguyên tử: hai lần chạy song song không cùng trượt
        os.close(os.open(shared, os.O_CREAT | os.O_EXCL | os.O_WRONLY)) if shared else None
        first = bool(shared)
    except FileExistsError:
        first = False
    if first:
        open(".fake_failed", "w").close()
        print("Tests don't run cleanly without mutations. Test command was: x")
        sys.exit(1)
    name = re.search(r"^\+\+\+ b/(.+)$", patch, re.M).group(1)
    line = int(re.search(r"^@@ -\S+ \+(\d+)", patch, re.M).group(1))
    with open(".fake_case", "w", encoding="utf-8") as f:
        json.dump([os.path.normpath(name), line], f)
elif cmd == "junitxml":
    cases = ""
    if os.path.exists(".fake_case") and not os.path.exists(".fake_failed"):
        name, line = json.load(open(".fake_case", encoding="utf-8"))
        cases = ('<testcase classname="%s" file="%s" line="%d" name="Mutant #1"><failure message="s"/></testcase>'
                 % (name, name, line))
    print('<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="mutmut">' + cases
          + "</testsuite></testsuites>")
'''


class ReviewBase(ParBase):
    def make_fake(self, path: Path) -> Path:
        path.write_text(FAKE, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return path


class FailedRunIsNotHidden(ReviewBase):
    def test_one_failed_parallel_run_makes_result_partial_with_its_lines(self):
        # review vòng 1 (L1): một lần chạy song song trượt baseline thì nửa diff mất mà vẫn báo "ran"
        self.build(15, 12)
        env = {"FAKE_SHARED": str(self.tmp / "failed-once")}
        data = self.data(self.mut("--json", "--jobs", "2", "--cmd", "true", *self.fake_args(), env=env))
        self.assertEqual(data["jobs"], 2, data)
        self.assertEqual(data["status"], "partial", data)
        notes = "\n".join(data["notes"])
        self.assertIn("lần chạy mutmut lỗi", notes)
        self.assertIn("calc.py:", notes)
        out = self.mut("--jobs", "2", "--cmd", "true", *self.fake_args(), env={"FAKE_SHARED": str(self.tmp / "f2")})
        self.assertIn("lần chạy mutmut lỗi", out.stdout)
        self.assertIn("chưa chạy xong", self.status_line(out))


class OddTargets(MutationBase):
    def setUp(self):
        super().setUp()
        self.init_repo()
        self.change_code()

    def run_paths(self):
        runs = [c for c in self.calls() if c["argv"][:1] == ["run"]]
        self.assertEqual(len(runs), 1, self.calls())
        argv = runs[0]["argv"]
        return argv[argv.index("--paths-to-mutate") + 1].split(",")

    def test_symlinked_python_file_is_left_out(self):
        # review vòng 1 (L2, F2): mutmut ghi xuyên symlink ra file thật ngoài bản chép
        victim = self.tmp / "victim.py"
        victim.write_text("V = 1 + 1\n", encoding="utf-8")
        os.symlink(victim, self.repo / "lnk.py")
        data = json.loads(self.mut("--json", "--cmd", "true", *self.fake_args()).stdout)
        self.assertNotIn("lnk.py", self.run_paths())
        self.assertTrue(any("lnk.py" in n and "symlink" in n for n in data["notes"]), data["notes"])
        self.assertEqual(victim.read_text(encoding="utf-8"), "V = 1 + 1\n")

    def test_comma_in_name_is_left_out(self):
        # review vòng 1 (L3): mutmut tách --paths-to-mutate theo dấu phẩy, file tên có dấu phẩy bị bỏ âm thầm
        (self.repo / "com,ma.py").write_text("def f(x):\n    return x + 1\n", encoding="utf-8")
        data = json.loads(self.mut("--json", "--cmd", "true", *self.fake_args()).stdout)
        self.assertEqual(sorted(self.run_paths()), ["calc.py", "newmod.py"])
        self.assertTrue(any("com,ma.py" in n for n in data["notes"]), data["notes"])


class ExistingBakSymlink(ReviewBase):
    def test_bak_symlink_in_tree_is_removed_before_mutmut_writes_it(self):
        # review vòng 1 (opus 3): mutmut mở `<file>.bak` để ghi; symlink có sẵn trỏ ra ngoài thì file thật bị ghi đè
        victim = self.tmp / "victim.txt"
        victim.write_text("giữ nguyên\n", encoding="utf-8")
        os.symlink(victim, self.repo / "calc.py.bak")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "bak")
        self.change_code()
        self.mut("--cmd", "true", *self.fake_args())
        runs = [c for c in self.calls() if c["argv"][:1] == ["run"]]
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["bak_at_start"].get("calc.py"), False, runs[0])
        self.assertEqual(victim.read_text(encoding="utf-8"), "giữ nguyên\n")


# mutmut giả cho nhánh junitxml hỏng: `show 3` in đúng dạng mutmut 2.5.1 (tên file không có tiền tố a/).
SHOW_FAKE = r'''#!/usr/bin/env python3
import json, os, sys
argv = sys.argv[1:]
with open(os.environ["FAKE_MUTMUT_LOG"], "a", encoding="utf-8") as f:
    f.write(json.dumps({"argv": argv, "cwd": os.getcwd()}) + "\n")
cmd = argv[0] if argv else ""
if cmd == "junitxml":
    sys.exit(1)
elif cmd == "result-ids" and argv[1:2] == ["survived"]:
    print("3")
elif cmd == "show" and argv[1:2] == ["3"]:
    sys.stdout.write("--- a/m.py\n+++ a/m.py\n@@ -1,2 +1,2 @@\n def f():\n-    return 1\n+    return 2\n")
'''


class ShowKeepsDirA(MutationBase):
    def make_fake(self, path: Path) -> Path:
        path.write_text(SHOW_FAKE, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return path

    def test_survivor_in_dir_a_keeps_its_path(self):
        # review vòng 1 (F5): parse_show cắt nhầm thư mục `a/` thật, đột biến sống bị gắn "ngoài dòng đổi"
        self.init_repo()
        (self.repo / "a").mkdir()
        (self.repo / "a" / "m.py").write_text("def f():\n    return 0\n", encoding="utf-8")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "a")
        (self.repo / "a" / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")
        data = json.loads(self.mut("--json", "--cmd", "true", *self.fake_args()).stdout)
        self.assertEqual([(s["file"], s["line"]) for s in data["survived"]], [("a/m.py", 2)], data)
        self.assertEqual(data["outside"], [], data)


class DiffContextNotCounted(MutationBase):
    def test_git_diff_opts_context_lines_are_not_added_lines(self):
        # review vòng 1 (F6): GIT_DIFF_OPTS hay diff.interHunkContext thêm ngữ cảnh; chỉ dòng `+` là dòng thêm
        self.init_repo()
        self.change_code()
        self.mut("--cmd", "true", *self.fake_args(), env={"GIT_DIFF_OPTS": "--unified=3"})
        runs = [c for c in self.calls() if c["argv"][:1] == ["run"]]
        self.assertEqual(len(runs), 1)
        n_calc = len((CALC_BASE + CALC_EXTRA).splitlines())
        self.assertEqual(patch_added(runs[0]["patch"]), {"calc.py": set(range(6, n_calc + 1)), "newmod.py": {1, 2}})


class HintOnlyForTimeouts(MutationBase):
    def test_untested_without_timeout_does_not_suggest_a_longer_timeout(self):
        # review vòng 1 (opus 1): mutmut dừng sớm vì lỗi thì gợi ý --timeout là sai hướng
        self.init_repo()
        self.change_code()
        xml = self.write("x.xml", '<?xml version="1.0"?><testsuites><testsuite name="m">'
                                  '<testcase classname="calc.py" file="calc.py" line="9" name="Mutant #1"/>'
                                  '<testcase classname="calc.py" file="calc.py" line="8" name="Mutant #2"/>'
                                  "</testsuite></testsuites>")
        out = self.mut("--cmd", "true", *self.fake_args(),
                       env={"FAKE_MUTMUT_XML": str(xml), "FAKE_MUTMUT_KILLED": "1", "FAKE_MUTMUT_UNTESTED": "2"})
        line = [x for x in out.stdout.splitlines() if "chưa chạy tới:" in x]
        self.assertEqual(len(line), 1, out.stdout)
        self.assertIn("calc.py:8", line[0])
        self.assertIn("không phải vì quá giờ", line[0])
        self.assertNotIn("--timeout", out.stdout)


class EmptyRunIsNotAFailure(ReviewBase):
    def test_run_that_exits_zero_without_mutants_is_not_reported_as_failed(self):
        # review lại vòng 1 (sonnet·high): mutmut thoát 0 mà không sinh đột biến (nhóm chỉ có import, def) bị báo "lỗi".
        # mutmut giả: lần `run` đầu tiên (O_EXCL trên FAKE_SHARED) thoát 0, junitxml rỗng; các lần khác như FAKE.
        empty = FAKE.replace('print("Tests don\'t run cleanly without mutations. Test command was: x")\n'
                             "        sys.exit(1)", "sys.exit(0)")
        self.assertNotEqual(empty, FAKE, "mutmut giả phải khác FAKE")
        fake = self.tmp / "empty_fake.py"
        fake.write_text(empty, encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        self.build(15, 12)
        out = self.mut("--json", "--jobs", "2", "--cmd", "true", "--mutmut", str(fake),
                       env={"FAKE_SHARED": str(self.tmp / "empty-once")})
        data = self.data(out)
        self.assertEqual(data["jobs"], 2, data)
        self.assertEqual(data["status"], "ran", data)
        self.assertEqual(data["total"], 1, data)
        self.assertFalse(any("lần chạy mutmut lỗi" in n for n in data["notes"]), data["notes"])


class OutsideLinesLabelsOrderCut(ParBase):
    """Review lại 17/11/2026 (sonnet·high, S2): dòng ⚠ ghi mọi vị trí ngoài dòng đổi kèm nhãn trạng thái, sống và quá giờ
    xếp trước, cắt ở 12 kèm "và N chỗ khác". Trước đó test chỉ kiểm vị trí có mặt, nên đổi nhãn hay bỏ sắp xếp vẫn xanh."""

    def setUp(self):
        super().setUp()
        self.change_code()  # calc.py dòng 6-9 và newmod.py dòng 1-2 là dòng thêm

    def warn_line(self, out):
        lines = [ln for ln in out.stdout.splitlines() if "ngoài dòng đổi" in ln]
        self.assertEqual(len(lines), 1, out.stdout)
        return lines[0]

    def test_each_outside_mutant_has_its_status_label_survivors_first(self):
        # spec:mutation-nhieu-file#S2
        from tests.test_mutation_parallel import xml_of
        xml = self.write("labels.xml", xml_of([(1, "calc.py", 8, "survived"), (2, "calc.py", 4, "killed"),
                                              (3, "calc.py", 5, "survived"), (4, "calc.py", 3, "timeout"),
                                              (5, "other.py", 3, "killed")]))
        env = {"FAKE_MUTMUT_XML": str(xml), "FAKE_MUTMUT_KILLED": "2", "FAKE_MUTMUT_UNTESTED": "5"}
        warn = self.warn_line(self.mut("--cmd", "true", *self.fake_args(), env=env))
        spots = ["calc.py:5 (sống)", "calc.py:3 (quá giờ)", "calc.py:4 (bị bắt)", "other.py:3 (chưa chạy)"]
        for spot in spots:
            self.assertIn(spot, warn)
        self.assertEqual([warn.index(s) for s in spots], sorted(warn.index(s) for s in spots),
                         "sống, quá giờ trước; trong mỗi nhóm giữ thứ tự gốc")
        data = self.data(self.mut("--json", "--cmd", "true", *self.fake_args(), env=env))
        self.assertEqual({(o["file"], o["line"]): o["status"] for o in data["outside"]},
                         {("calc.py", 4): "killed", ("calc.py", 5): "survived", ("calc.py", 3): "timeout",
                          ("other.py", 3): "untested"})

    def test_more_than_twelve_outside_are_cut_and_the_survivor_stays_listed(self):
        # spec:mutation-nhieu-file#S2
        from tests.test_mutation_parallel import xml_of
        killed = [(i, "other.py", 9 + i, "killed") for i in range(1, 14)]  # 13 đột biến bị bắt, đứng trước
        xml = self.write("many.xml", xml_of(killed + [(14, "other.py", 40, "survived"), (15, "calc.py", 8, "survived")]))
        env = {"FAKE_MUTMUT_XML": str(xml), "FAKE_MUTMUT_KILLED": " ".join(str(i) for i in range(1, 14))}
        warn = self.warn_line(self.mut("--cmd", "true", *self.fake_args(), env=env))
        self.assertIn("14 đột biến ngoài dòng đổi", warn)
        self.assertIn("và 2 chỗ khác", warn)
        self.assertEqual(warn.count("other.py:"), 12, warn)
        self.assertIn("other.py:40 (sống)", warn, "đột biến sống không được rơi vào phần bị cắt")
        self.assertLess(warn.index("other.py:40 (sống)"), warn.index("other.py:10 (bị bắt)"))
        self.assertNotIn("calc.py:8", warn, "dòng thêm không phải ngoài dòng đổi")
