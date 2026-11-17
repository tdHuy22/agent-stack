"""Tám quan sát sau GĐ6, lát công cụ (slug `gd6-qs-cong-cu`): file spec `.agent/spec/gd6-qs-cong-cu.txt`.

Viết TRƯỚC code. Gọi script như người dùng gọi (receipt.py, mutation.py qua dòng lệnh); phần chấm điểm gọi thẳng
`risk.assess`, `risk.collect`, `ratchet.classify`. Repo git, thư mục trạng thái nằm trong thư mục tạm của test (tự xóa),
`AGENT_STACK_STATE` trỏ vào đó cho mọi lần gọi. Test ghi "vế cũ, giữ" là hành vi hiện có mà spec không đổi: chúng đạt
ngay, để code mới không nới nhầm.
"""
import json
import os
import subprocess
import sys
from collections import Counter
from unittest import mock

from tests._util import PLUGIN, TempDirTestCase, git
from tests.test_mutation_parallel import PAR_FAKE, ParBase, patch_added

DONE_GATE = PLUGIN / "skills" / "done-gate" / "scripts"
RECEIPT = PLUGIN / "skills" / "session-keeper" / "scripts" / "receipt.py"
sys.path.insert(0, str(PLUGIN / "lib"))
sys.path.insert(0, str(DONE_GATE))
import agentstack as A  # noqa: E402
import ratchet  # noqa: E402
import risk  # noqa: E402
import testlock as TL  # noqa: E402

CALC = "def add(a, b):\n    return a + b\n"
CALC_SUB = CALC + "\n\ndef sub(a, b):\n    return a - b\n"
TEST_CALC = ("import unittest\nfrom calc import add\n\n\nclass AddTest(unittest.TestCase):\n"
             "    def test_add(self):\n        self.assertEqual(add(1, 2), 3)\n")
# Khối nối thêm vào cuối file test (không sửa dòng cũ): import mới, class mới.
TEST_MORE = ("\n\nfrom calc import sub\n\n\nclass SubTest(unittest.TestCase):\n"
             "    def test_sub(self):\n        self.assertEqual(sub(5, 3), 2)\n")
TEST_MORE_WRONG = TEST_MORE.replace("sub(5, 3), 2", "sub(5, 3), 99")  # trượt cả sau bản sửa
RED = {"kind": "assert", "line": "AssertionError: x", "base": "a" * 40, "ts": "2026-11-16T10:00:00+07:00"}
PLAN = "# PLAN\n\n## 0. Đang ở đâu, việc tiếp theo\n- làm việc\n"


class RepoCase(TempDirTestCase):
    """Repo git nhỏ trong thư mục tạm và thư mục trạng thái riêng."""

    def setUp(self):
        super().setUp()
        self.state = self.tmp / "state"
        patcher = mock.patch.dict(os.environ, {"AGENT_STACK_STATE": str(self.state)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.repo = self.tmp / "proj"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "test")
        git(self.repo, "config", "user.email", "test@example.com")
        git(self.repo, "config", "commit.gpgsign", "false")

    def put(self, rel, text):
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def commit(self, msg="fixture"):
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", msg)

    def receipt(self, *args, cwd=None):
        return subprocess.run([sys.executable, str(RECEIPT), *args], cwd=str(cwd or self.repo), capture_output=True,
                              text=True, timeout=120)

    def lock_raw(self):
        return json.loads((self.repo / TL.LOCK_REL).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------------------------------------------
# S1, S9: file trong `.agent/` không phải code, trừ khi có đuôi mã nguồn

class AgentFilesKind(TempDirTestCase):
    def test_agent_files_outside_spec_are_not_code(self):
        # spec:gd6-qs-cong-cu#S1
        for path in (".agent/stack.json", ".agent/test-lock.json", ".agent/ban-giao/x.patch"):
            with self.subTest(path=path):
                self.assertNotEqual(risk.kind(path), "code")
        self.assertEqual(risk.kind(".agent/spec/a.txt"), "test", "vế cũ, giữ: spec vẫn là test")

    def test_assess_does_not_count_agent_lines_as_code(self):
        # spec:gd6-qs-cong-cu#S1
        for path, added in ((".agent/ban-giao/x.patch", 1400), (".agent/stack.json", 500),
                            (".agent/test-lock.json", 450)):
            with self.subTest(path=path):
                result = risk.assess([{"path": path, "added": added, "deleted": 0, "text": "..."}])
                self.assertEqual(result["by_kind"]["code"], 0, result)
                self.assertFalse(any("thay đổi lớn" in r for r in result["reasons"]), result["reasons"])

    def test_agent_files_with_source_extension_stay_code(self):
        # spec:gd6-qs-cong-cu#S9 (chốt chặn chống nới, TM-142: có thể đạt ngay, phải giữ đạt)
        for path in (".agent/x.py", ".agent/hooks/a.sh"):
            with self.subTest(path=path):
                self.assertEqual(risk.kind(path), "code")
                self.assertIs(risk.doc_only(path), False)
        result = risk.assess([{"path": ".agent/x.py", "added": 30, "deleted": 0, "text": "x = 1\n"}])
        self.assertEqual(result["by_kind"]["code"], 30, result)


class LockRedIgnoresAgentFiles(RepoCase):
    """S1, vế `lock --red`: file `.agent/` ngoài spec đổi không bị coi là code đã đổi."""

    def setUp(self):
        super().setUp()
        self.put("calc.py", CALC)
        self.put("tests/__init__.py", "")
        self.commit()
        self.put("tests/test_new.py", "import unittest\nfrom calc import add\n\n\nclass T(unittest.TestCase):\n"
                 "    def test_add(self):\n        self.assertEqual(add(1, 2), 4)\n")

    def lock_red(self):
        return self.receipt("lock", "--red", "--level", "cao", "--project", str(self.repo), "--tests",
                            "tests/test_new.py", "--", sys.executable, "-m", "unittest", "tests.test_new")

    def test_agent_files_need_no_allow(self):
        # spec:gd6-qs-cong-cu#S1
        self.put(".agent/stack.json", "{}\n")  # chưa được git theo dõi
        self.put(".agent/ban-giao/x.patch", "diff --git a/x b/x\n")
        out = self.lock_red()
        text = out.stdout + out.stderr
        self.assertEqual(out.returncode, 0, text)
        self.assertNotIn("không khóa đỏ", text)
        self.assertEqual(self.lock_raw()["files"]["tests/test_new.py"]["red"]["kind"], "assert")

    def test_real_code_change_still_needs_allow(self):
        # spec:gd6-qs-cong-cu#S1 (vế cũ, giữ: file code vẫn bị chặn)
        self.put(".agent/stack.json", "{}\n")
        self.put("app.py", "x = 1\n")
        out = self.lock_red()
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self.assertIn("không khóa đỏ", out.stdout)
        self.assertIn("app.py", out.stdout)


# ---------------------------------------------------------------------------------------------------------------
# S2, S9: biên nhận còn khớp khi chỉ file `.agent/` (ngoài spec) đổi

class ReceiptAfterAgentChanges(RepoCase):
    def setUp(self):
        super().setUp()
        self.put("calc.py", CALC)
        self.put(".agent/stack.json", "{}\n")
        self.put(".agent/spec/a.txt", "S1: Khi a thì b\n")
        self.commit()
        out = self.receipt("run", "--project", str(self.repo), "--label", "X", "--", sys.executable, "-c", "print(1)")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def current(self):
        status = A.receipt_status(self.repo.resolve())
        self.assertIn("X", status)
        return status["X"]["current"]

    def test_only_agent_files_changed_keeps_receipt_current(self):
        # spec:gd6-qs-cong-cu#S2
        self.put(".agent/ban-giao/x.patch", "diff --git a/x b/x\n")
        self.put(".agent/stack.json", '{"areas": {}}\n')
        TL.save(self.repo, {"files": {}})
        self.assertIs(self.current(), True)
        shown = json.loads(self.receipt("show", "--project", str(self.repo), "--json").stdout)
        self.assertIs(shown["X"]["current"], True)

    def test_code_change_makes_receipt_stale(self):
        # spec:gd6-qs-cong-cu#S2 (đối chứng, vế cũ: code đổi thì cũ)
        self.put(".agent/ban-giao/x.patch", "diff --git a/x b/x\n")
        self.put("app.py", "x = 1\n")
        self.assertIs(self.current(), False)

    def test_spec_file_change_makes_receipt_stale(self):
        # spec:gd6-qs-cong-cu#S2 (vế cũ: chỉ `.agent/spec/` được loại khỏi ngoại lệ)
        self.put(".agent/spec/a.txt", "S1: Khi a thì b\nS2: Khi c thì d\n")
        self.assertIs(self.current(), False)

    def test_agent_source_file_makes_receipt_stale(self):
        # spec:gd6-qs-cong-cu#S9 (biên nhận coi file mã nguồn trong .agent/ là code; chốt chặn chống nới, TM-142)
        self.put(".agent/x.py", "x = 1\n")
        self.assertIs(self.current(), False)

    def test_agent_shell_script_makes_receipt_stale(self):
        # spec:gd6-qs-cong-cu#S9
        self.put(".agent/hooks/a.sh", "echo hi\n")
        self.assertIs(self.current(), False)


# ---------------------------------------------------------------------------------------------------------------
# S3: threat-model.md đổi cùng code là đụng ranh giới tin cậy

class ThreatModelBoundary(TempDirTestCase):
    GATE = {"path": "src/gate.py", "added": 5, "deleted": 0, "text": "x = 1\ny = 2\nz = 3\nw = 4\nv = 5\n"}
    TM_ROWS = "| TM-1 | luồng vào | chặn bằng danh sách |\n| TM-2 | luồng ra | ghi log |\n" * 2

    def tm(self, added=4, deleted=0):
        return {"path": ".agent/threat-model.md", "added": added, "deleted": deleted,
                "text": self.TM_ROWS if added else ""}

    def crossed(self, result):
        return [b for b in result["boundaries"] if ".agent/threat-model.md" in b["paths"]]

    def test_code_plus_added_threat_model_lines_crosses_a_boundary(self):
        # spec:gd6-qs-cong-cu#S3
        result = risk.assess([self.GATE, self.tm()])
        self.assertEqual(len(self.crossed(result)), 1, result["boundaries"])
        self.assertIn(result["level"], ("vua", "cao"), result)

    def test_threat_model_alone_is_not_a_boundary(self):
        # spec:gd6-qs-cong-cu#S3 (đối chứng: không có code đổi)
        result = risk.assess([self.tm()])
        self.assertEqual(self.crossed(result), [], result["boundaries"])

    def test_code_with_only_deleted_threat_model_lines_is_not_a_boundary(self):
        # spec:gd6-qs-cong-cu#S3 (spec nói "có thêm dòng": chỉ xóa dòng thì không tính)
        result = risk.assess([self.GATE, self.tm(added=0, deleted=3)])
        self.assertEqual(self.crossed(result), [], result["boundaries"])


# ---------------------------------------------------------------------------------------------------------------
# S4: mục khóa mức cao mới hay đổi, cùng code, thì mức cao

class LockLevelRaisesRisk(RepoCase):
    TEST_GATE = ("import unittest\n\n\nclass T(unittest.TestCase):\n    def test_gate(self):\n"
                 "        self.assertEqual(1, 1)\n")
    GATE = "x = 1\ny = 2\nz = 3\n"

    def setUp(self):
        super().setUp()
        self.put("README.md", "# x\n")
        self.commit()

    def lock(self, level, data=None, rel="tests/test_gate.py", keep=None):
        book = dict(keep or {"files": {}})
        book["files"] = dict(book["files"])
        book["files"][rel] = TL.entry_for((data or self.TEST_GATE).encode(), level)
        TL.save(self.repo, book)

    def assess(self):
        return risk.assess(risk.collect(self.repo))

    def add_code_and_test(self):
        self.put("src/gate.py", self.GATE)
        self.put("tests/test_gate.py", self.TEST_GATE)

    def test_new_high_lock_entry_with_code_is_high_risk(self):
        # spec:gd6-qs-cong-cu#S4
        self.add_code_and_test()
        self.lock("cao")
        result = self.assess()
        self.assertEqual(result["level"], "cao", result["reasons"])
        self.assertTrue(any("khóa test" in r and "cao" in r for r in result["reasons"]), result["reasons"])

    def test_changed_high_lock_entry_with_code_is_high_risk(self):
        # spec:gd6-qs-cong-cu#S4 (mục đã có ở base với mức vừa, đổi thành mức cao)
        self.put("tests/test_gate.py", self.TEST_GATE)
        self.lock("vua")
        self.commit("test + khóa vừa")
        self.put("src/gate.py", self.GATE)
        self.put("tests/test_gate.py", self.TEST_GATE + "\n    def test_more(self):\n        self.assertEqual(2, 2)\n")
        self.lock("cao", data=(self.repo / "tests/test_gate.py").read_text(encoding="utf-8"))
        result = self.assess()
        self.assertEqual(result["level"], "cao", result["reasons"])
        self.assertTrue(any("khóa test" in r for r in result["reasons"]), result["reasons"])

    def test_medium_lock_entry_does_not_raise_to_high(self):
        # spec:gd6-qs-cong-cu#S4 (đối chứng: mức vừa không lên cao vì luật này)
        self.add_code_and_test()
        self.lock("vua")
        result = self.assess()
        self.assertNotEqual(result["level"], "cao", result["reasons"])
        self.assertFalse(any("khóa test" in r for r in result["reasons"]), result["reasons"])

    def test_high_lock_without_code_change_does_not_raise_to_high(self):
        # spec:gd6-qs-cong-cu#S4 (đối chứng: không có code đổi)
        self.put("tests/test_gate.py", self.TEST_GATE)
        self.lock("cao")
        result = self.assess()
        self.assertNotEqual(result["level"], "cao", result["reasons"])
        self.assertFalse(any("khóa test" in r for r in result["reasons"]), result["reasons"])

    def test_unchanged_high_entry_at_base_does_not_raise_to_high(self):
        # spec:gd6-qs-cong-cu#S4 (đối chứng: mục cao đã có ở base, không thêm hay đổi; chỉ thêm mục mức vừa)
        self.put("tests/test_a_old.py", self.TEST_GATE)
        self.lock("cao", rel="tests/test_a_old.py")
        self.commit("khóa cao có từ trước")
        self.add_code_and_test()
        self.lock("vua", keep=TL.load(self.repo))
        result = self.assess()
        self.assertNotEqual(result["level"], "cao", result["reasons"])
        self.assertFalse(any("khóa test" in r for r in result["reasons"]), result["reasons"])


# ---------------------------------------------------------------------------------------------------------------
# S5: --cwd

class CwdOption(RepoCase):
    def setUp(self):
        super().setUp()
        self.put("PLAN.md", PLAN)
        self.put("sub/calc.py", "def add(a, b):\n    return a - b\n")  # base có lỗi
        self.commit()
        self.sub = self.repo / "sub"
        self.pwd = ["-c", "import os;print('CWD=' + os.getcwd())"]

    @staticmethod
    def cwd_line(out):
        lines = [x for x in out.stdout.splitlines() if x.startswith("CWD=")]
        assert len(lines) == 1, out.stdout + out.stderr
        return os.path.realpath(lines[0][4:])

    def test_run_with_cwd_runs_there_and_show_prints_it(self):
        # spec:gd6-qs-cong-cu#S5
        out = self.receipt("run", "--project", str(self.repo), "--cwd", str(self.sub), "--label", "Y", "--",
                           sys.executable, *self.pwd)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(self.cwd_line(out), str(self.sub.resolve()))
        shown = json.loads(self.receipt("show", "--project", str(self.repo), "--json").stdout)
        self.assertEqual(shown["Y"]["cwd"], "sub")
        text = self.receipt("show", "--project", str(self.repo)).stdout
        line = next(x for x in text.splitlines() if x.startswith("- Y:"))
        self.assertIn("chạy trong sub", line)

    def test_relative_cwd_counts_from_process_directory(self):
        # spec:gd6-qs-cong-cu#S5
        out = self.receipt("run", "--project", ".", "--cwd", "sub", "--label", "Z", "--", sys.executable, *self.pwd)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(self.cwd_line(out), str(self.sub.resolve()))

    def test_cwd_outside_project_exits_2_without_running(self):
        # spec:gd6-qs-cong-cu#S5
        marker = self.tmp / "da-chay"
        elsewhere = self.tmp / "ngoai"
        elsewhere.mkdir()
        write_marker = [sys.executable, "-c", f"open({str(marker)!r}, 'w').close()"]
        for outside in (elsewhere, self.repo.parent):
            with self.subTest(cwd=str(outside)):
                out = self.receipt("run", "--project", str(self.repo), "--cwd", str(outside), "--", *write_marker)
                self.assertEqual(out.returncode, 2, out.stdout + out.stderr)
                self.assertNotIn("unrecognized", out.stderr, "mã 2 phải do kiểm thư mục, không phải do cờ lạ")
                self.assertFalse(marker.exists(), "lệnh không được chạy")

    def test_cwd_outside_project_exits_2_for_fails_before_and_lock(self):
        # spec:gd6-qs-cong-cu#S5
        elsewhere = self.tmp / "ngoai"
        elsewhere.mkdir()
        self.put("sub/test_x.py", "import unittest\n")
        for name, extra in (("fails-before", []), ("lock", ["--red", "--level", "cao"])):
            with self.subTest(command=name):
                out = self.receipt(name, "--project", str(self.repo), "--cwd", str(elsewhere), *extra, "--",
                                   sys.executable, "-c", "print(1)")
                self.assertEqual(out.returncode, 2, out.stdout + out.stderr)
                self.assertNotIn("unrecognized", out.stderr, "mã 2 phải do kiểm thư mục, không phải do cờ lạ")

    def test_without_cwd_from_subdirectory_prints_run_directory_first(self):
        # spec:gd6-qs-cong-cu#S5
        out = self.receipt("run", "--project", ".", "--label", "W", "--", sys.executable, *self.pwd, cwd=self.sub)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(self.cwd_line(out), str(self.repo.resolve()), "vẫn chạy ở gốc project như cũ")
        lines = out.stdout.splitlines()
        notes = [i for i, x in enumerate(lines) if x.startswith("[receipt] chạy ở ")]
        self.assertEqual(len(notes), 1, out.stdout)
        self.assertIn(str(self.repo.resolve()), lines[notes[0]])
        self.assertLess(notes[0], next(i for i, x in enumerate(lines) if x.startswith("CWD=")))

    def test_without_cwd_at_project_root_prints_no_directory_line(self):
        # spec:gd6-qs-cong-cu#S5 (vế cũ, giữ: cùng thư mục thì không in thêm)
        out = self.receipt("run", "--project", ".", "--label", "V", "--", sys.executable, *self.pwd)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertFalse(any(x.startswith("[receipt] chạy ở ") for x in out.stdout.splitlines()), out.stdout)

    def add_fixed_code_and_test(self):
        """Bản sửa ở cây làm việc (calc.py đúng) cùng test mới trong sub/."""
        self.put("sub/calc.py", "def add(a, b):\n    return a + b\n")
        self.put("sub/test_x.py", "import unittest\nfrom calc import add\n\n\nclass T(unittest.TestCase):\n"
                 "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n")

    def test_fails_before_with_cwd_finds_the_module_and_catches_the_bug(self):
        # spec:gd6-qs-cong-cu#S5
        self.add_fixed_code_and_test()
        cmd = (sys.executable, "-m", "unittest", "test_x")
        out = self.receipt("fails-before", "--project", str(self.repo), "--cwd", str(self.sub), "--label", "F", "--",
                           *cmd)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        text = self.receipt("show", "--project", str(self.repo)).stdout
        self.assertIn("chạy trong sub", next(x for x in text.splitlines() if x.startswith("- F:")))

    def test_fails_before_without_cwd_does_not_find_the_module(self):
        # spec:gd6-qs-cong-cu#S5 (đối chứng: ở gốc repo không có module test_x)
        self.add_fixed_code_and_test()
        out = self.receipt("fails-before", "--project", str(self.repo), "--", sys.executable, "-m", "unittest", "test_x")
        self.assertNotEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_lock_red_with_cwd_runs_the_test_there(self):
        # spec:gd6-qs-cong-cu#S5 (chạy ở gốc thì test_x không import được: red.kind là "thieu", không phải "assert")
        self.put("sub/test_x.py", "import unittest\nfrom calc import add\n\n\nclass T(unittest.TestCase):\n"
                 "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n")
        out = self.receipt("lock", "--red", "--level", "cao", "--project", str(self.repo), "--cwd", str(self.sub),
                           "--tests", "sub/test_x.py", "--", sys.executable, "-m", "unittest", "test_x")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(self.lock_raw()["files"]["sub/test_x.py"]["red"]["kind"], "assert")


# ---------------------------------------------------------------------------------------------------------------
# S6, S7: khóa lại file test đã khóa chỉ có dòng thêm

class LockedTestRepo(RepoCase):
    """Commit gốc: calc.py, tests/test_calc.py (đạt), sổ khóa mức cao kèm bằng chứng đỏ cũ."""

    def setUp(self):
        super().setUp()
        self.put("calc.py", CALC)
        self.put("tests/__init__.py", "")
        self.put("tests/test_calc.py", TEST_CALC)
        TL.save(self.repo, {"files": {"tests/test_calc.py": TL.entry_for(TEST_CALC.encode(), "cao", red=dict(RED))}})
        self.commit("test + khóa")

    def append_new_test(self, more=TEST_MORE):
        self.put("calc.py", CALC_SUB)
        self.put("tests/test_calc.py", TEST_CALC + more)

    def lock(self, *extra):
        return self.receipt("lock", "--project", str(self.repo), *extra, "--", sys.executable, "-m", "unittest",
                            "tests.test_calc")


class RelockAfterAppend(LockedTestRepo):
    def check_relocked(self, out):
        text = out.stdout + out.stderr
        self.assertEqual(out.returncode, 0, text)
        raw = self.lock_raw()["files"]["tests/test_calc.py"]
        book = TL.load(self.repo)
        self.assertEqual(TL.status(self.repo, "tests/test_calc.py", book["files"]["tests/test_calc.py"]), "same", text)
        self.assertEqual(raw["level"], "cao")
        self.assertEqual(raw["red"], RED, "giữ nguyên bằng chứng red cũ")
        self.assertIsInstance(raw.get("fails_before"), str, raw)
        self.assertIn("không kết luận", raw["fails_before"])

    def test_added_lines_are_locked_when_fails_before_is_inconclusive_on_missing_import(self):
        # spec:gd6-qs-cong-cu#S6 (không --level: chấm vừa nhờ requirements.txt đổi, mục cũ giữ mức cao)
        self.append_new_test()
        self.put("requirements.txt", "x\n")
        self.check_relocked(self.lock())

    def test_added_lines_are_locked_with_explicit_level(self):
        # spec:gd6-qs-cong-cu#S6
        self.append_new_test()
        self.check_relocked(self.lock("--level", "cao"))

    def test_edited_old_line_is_still_refused_and_book_unchanged(self):
        # spec:gd6-qs-cong-cu#S6 (vế cũ, giữ: sửa dòng cũ là nới, mã 3, sổ không đổi)
        self.append_new_test()
        edited = (self.repo / "tests/test_calc.py").read_text(encoding="utf-8").replace("add(1, 2), 3", "add(1, 2), 3 + 0")
        self.put("tests/test_calc.py", edited)
        before = (self.repo / TL.LOCK_REL).read_bytes()
        out = self.lock("--level", "cao")
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self.assertEqual((self.repo / TL.LOCK_REL).read_bytes(), before)

    def test_inconclusive_for_another_reason_does_not_write_the_book(self):
        # spec:gd6-qs-cong-cu#S6 (chỉ thiếu import hay tên mới được qua; test cũng trượt sau bản sửa thì không khóa)
        self.append_new_test(TEST_MORE_WRONG)
        before = (self.repo / TL.LOCK_REL).read_bytes()
        out = self.lock("--level", "cao")
        self.assertNotEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual((self.repo / TL.LOCK_REL).read_bytes(), before)


class RatchetRelock(LockedTestRepo):
    def classify(self):
        return ratchet.classify(self.repo, risk.collect(self.repo), kind=risk.kind)

    def test_appended_test_in_locked_file_is_yellow_with_relock_command(self):
        # spec:gd6-qs-cong-cu#S7
        self.append_new_test()
        result = self.classify()
        relock = result.get("relock")
        self.assertIsInstance(relock, list, result)
        self.assertEqual(len(relock), 1, result)
        self.assertIn("tests/test_calc.py", relock[0])
        self.assertIn("receipt.py lock", relock[0])
        self.assertEqual(result["verdict"], "vang", result)

    def test_relock_case_is_not_reported_as_tightening(self):
        # spec:gd6-qs-cong-cu#S7
        self.append_new_test()
        result = self.classify()
        self.assertFalse(any("chưa khóa lại" in x for x in result["tighten"]), result["tighten"])
        self.assertEqual(result["tighten"], [], "chỉ có ca này thì không có gì để báo 🟢")
        lines = ratchet.render(result)
        self.assertFalse(any(x.startswith("- 🟢") for x in lines), lines)
        yellow = [x for x in lines if x.startswith("- 🟡") and "tests/test_calc.py" in x]
        self.assertEqual(len(yellow), 1, lines)

    def test_after_relock_nothing_is_left_to_relock(self):
        # spec:gd6-qs-cong-cu#S7 (đã khóa lại bằng đúng bản ghi receipt.py lock sẽ ghi: hết 🟡)
        self.append_new_test()
        data = (self.repo / "tests/test_calc.py").read_bytes()
        TL.save(self.repo, {"files": {"tests/test_calc.py": TL.entry_for(data, "cao", red=dict(RED))}})
        result = self.classify()
        self.assertEqual(result.get("relock"), [], result)
        self.assertEqual(result["verdict"], "xanh", result)


# ---------------------------------------------------------------------------------------------------------------
# S8: mutation.py chạy lại một lần nhóm trượt ở baseline

def retry_fake():
    """PAR_FAKE thêm cách trượt: lần `run` đầu tiên (O_EXCL trên FAKE_SHARED) của một nhóm trượt baseline (in câu của
    mutmut, thoát 1); nhóm đó được nhận ra bằng khóa (file đầu, dòng đầu của bản vá), nên chạy lại ở đâu cũng được.
    FAKE_ALWAYS_FAIL: nhóm đó trượt mọi lần. FAKE_CRASH: nhóm đó chạy đột biến rồi sập (thoát 1, không phải baseline)."""
    marker = ('if cmd == "run":\n    with open(".fake_run.json", "w", encoding="utf-8") as f:\n'
              '        json.dump({"patch": rec["patch"], "paths": paths}, f)\n')
    block = '''if cmd == "run":
    crash = False
    shared = os.environ.get("FAKE_SHARED")
    key = json.dumps(sorted((n, min(s)) for n, s in patch_added(rec["patch"] or "").items()))
    won, bad = False, None
    if shared:
        try:
            fd = os.open(shared, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, key.encode("utf-8"))
            os.close(fd)
            won = True
        except FileExistsError:
            bad = read(shared)
    if won or (os.environ.get("FAKE_ALWAYS_FAIL") and bad == key):
        if os.environ.get("FAKE_CRASH"):
            crash = True
            print("Traceback (most recent call last):\\n  RuntimeError: boom")
        else:
            print("Tests don't run cleanly without mutations. Test command was: x")
            sys.exit(1)
    with open(".fake_run.json", "w", encoding="utf-8") as f:
        json.dump({"patch": rec["patch"], "paths": paths}, f)
'''
    assert marker in PAR_FAKE
    text = PAR_FAKE.replace(marker, block)
    exit_line = 'sys.exit(int(os.environ.get("FAKE_MUTMUT_RUN_EXIT", "0")))'
    assert exit_line in text
    return text.replace(exit_line, 'sys.exit(1 if crash else int(os.environ.get("FAKE_MUTMUT_RUN_EXIT", "0")))')


def rerun_notes(data):
    """Ghi chú về việc chạy lại nhóm trượt (bỏ dòng cũ nhắc `--jobs 1`, cũng có chữ "chạy lại" nhưng nói chuyện khác)."""
    return [n for n in data["notes"] if "chạy lại" in n and "--jobs" not in n]


def group_key(patch):
    """Cùng cách tính khóa nhóm như mutmut giả."""
    return json.dumps(sorted((n, min(s)) for n, s in patch_added(patch or "").items()))


class BaselineRetry(ParBase):
    def make_fake(self, path):
        path.write_text(retry_fake(), encoding="utf-8")
        path.chmod(path.stat().st_mode | 0o111)
        return path

    def setUp(self):
        super().setUp()
        self.build(15, 12)

    def go(self, **env):
        env = dict({"FAKE_SHARED": str(self.tmp / "failed-once")}, **env)
        data = self.data(self.mut("--json", "--jobs", "2", "--cmd", "true", *self.fake_args(), env=env))
        self.assertEqual(data["jobs"], 2, data)
        runs = self.runs()
        counts = Counter(group_key(r["patch"]) for r in runs)
        return data, runs, counts

    def test_group_failing_baseline_is_rerun_once_and_counted(self):
        # spec:gd6-qs-cong-cu#S8
        data, runs, counts = self.go()
        self.assertEqual(data["status"], "ran", data)
        self.assertTrue(rerun_notes(data), data["notes"])
        self.assertEqual(sorted(counts.values()), [1, 2], f"đúng một nhóm chạy hai lần: {counts}")
        patches = {group_key(r["patch"]): r["patch"] for r in runs}
        expected = sum(len(lines) for p in patches.values() for lines in patch_added(p).values())
        self.assertEqual(data["total"], expected, "tổng gồm cả phần của nhóm chạy lại")

    def test_group_failing_baseline_again_is_partial_after_one_retry(self):
        # spec:gd6-qs-cong-cu#S8 (đối chứng: trượt cả hai lần thì partial, và chỉ chạy lại một lần)
        data, _runs, counts = self.go(FAKE_ALWAYS_FAIL="1")
        self.assertEqual(data["status"], "partial", data)
        self.assertEqual(sorted(counts.values()), [1, 2], f"chạy lại đúng một lần, không hơn: {counts}")

    def test_crash_after_mutating_is_not_rerun(self):
        # spec:gd6-qs-cong-cu#S8 (vế "chưa kiểm đột biến nào": sập giữa chừng không phải trượt baseline, không chạy lại)
        data, _runs, counts = self.go(FAKE_CRASH="1")
        self.assertEqual(data["status"], "partial", data)
        self.assertEqual(sorted(counts.values()), [1, 1], f"không chạy lại: {counts}")
        self.assertEqual(rerun_notes(data), [], data["notes"])
