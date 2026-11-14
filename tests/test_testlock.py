"""Khóa test (GĐ2, 13/11/2026): `plugin/lib/testlock.py` và `receipt.py lock | locks | unlock`.

Test đã chứng minh trượt trên code cũ thì khóa (sha256 + dấu từng dòng); thêm dòng là siết, sửa hay xóa là nới.
"""
import json
import sys
from unittest import mock

from tests import test_receipt as TR
from tests._util import PLUGIN, TempDirTestCase, git, run_script

RECEIPT = PLUGIN / "skills" / "session-keeper" / "scripts" / "receipt.py"
sys.path.insert(0, str(PLUGIN / "lib"))
sys.path.insert(0, str(RECEIPT.parent))
import receipt  # noqa: E402
import testlock as TL  # noqa: E402


class LockLibrary(TempDirTestCase):
    PY = ("import unittest\nfrom calc import add\n\n\nclass T(unittest.TestCase):\n    def test_add(self):\n"
          "        for a, b, want in [(1, 2, 3)]:\n            self.assertEqual(add(a, b), want)\n")

    def test_python_tests_compare_by_structure(self):
        entry = TL.entry_for(self.PY.encode(), "cao")
        added = {"hàm test mới": self.PY + "\n    def test_neg(self):\n        self.assertEqual(add(-1, -1), -2)\n",
                 "class mới": self.PY + "\n\nclass U(unittest.TestCase):\n    def test_x(self):\n        pass\n",
                 "import mới": "import os\n" + self.PY}
        for name, text in added.items():
            with self.subTest(name):
                self.assertEqual(TL.compare(entry, text), "added")
        self.assertEqual(TL.compare(entry, self.PY + "\n\n"), "same")
        # Reviewer 13/11: các mẹo "làm test qua" mà chỉ thêm dòng thì phải là nới, không phải siết.
        loose = {"return đầu hàm": self.PY.replace("(self):\n", "(self):\n        return\n"),
                 "bọc try": self.PY.replace("            self.assertEqual(add(a, b), want)\n",
                                            "            try:\n                self.assertEqual(add(a, b), want)\n"
                                            "            except AssertionError:\n                pass\n"),
                 "lùi thụt lề": self.PY.replace("            self.assertEqual", "        self.assertEqual"),
                 "thêm skip": self.PY.replace("    def test_add", "    @unittest.skip('x')\n    def test_add"),
                 "setUp mới": self.PY + "\n    def setUp(self):\n        pass\n",
                 "fixture tự dùng": self.PY + "\n\n@pytest.fixture(autouse=True)\ndef f():\n    pass\n",
                 "vá ở mức module": self.PY + "\nunittest.TestCase.assertEqual = lambda *a: None\n",
                 "thuộc tính class": self.PY.replace("TestCase):\n", "TestCase):\n    assertEqual = print\n"),
                 "sửa assert": self.PY.replace("assertEqual(add(a, b), want)", "assertTrue(add(a, b))"),
                 "đảo thứ tự hàm": self.PY + "\n    def test_z(self):\n        pass\n",
                 "cú pháp hỏng": self.PY + "\n    def (\n"}
        loose["đảo thứ tự hàm"] = loose["đảo thứ tự hàm"].replace("    def test_add", "    def test_tmp", 1)
        for name, text in loose.items():
            with self.subTest(name):
                self.assertEqual(TL.compare(entry, text), "changed")
        self.assertEqual(TL.compare(entry, None), "deleted")

    def test_appending_asserts_to_an_old_test_is_tightening(self):
        # Bạn chọn 14/11/2026: thêm assert ở cuối hàm test cũ là siết; thêm thứ khác vào hàm cũ vẫn là nới.
        entry = TL.entry_for(self.PY.encode(), "cao")
        end = "            self.assertEqual(add(a, b), want)\n"
        ok = {"assert*": end + "        self.assertEqual(add(0, 0), 0)\n",
              "assert": end + "        assert add(1, 1) == 2\n        self.assertTrue(add(1, 1))\n"}
        for name, tail in ok.items():
            with self.subTest(name):
                self.assertEqual(TL.compare(entry, self.PY.replace(end, tail)), "added")
        bad = {"skipTest": end + "        self.skipTest('x')\n", "return": end + "        return\n",
               "if": end + "        if False:\n            self.assertTrue(1)\n",
               "gán": end + "        add = None\n"}
        for name, tail in bad.items():
            with self.subTest(name):
                self.assertEqual(TL.compare(entry, self.PY.replace(end, tail)), "changed")

    def test_redefining_or_shadowing_old_names_is_loosening(self):
        # Reviewer 14/11: Python dùng định nghĩa sau, nên định nghĩa lại trùng tên vô hiệu test cũ.
        entry = TL.entry_for(self.PY.encode(), "cao")
        cases = {"hàm trùng tên": self.PY + "\n    def test_add(self):\n        pass\n",
                 "class trùng tên": self.PY + "\n\nclass T(unittest.TestCase):\n    pass\n",
                 "che tên import": self.PY + "\n\ndef add(a, b):\n    return 3\n",
                 "import che tên": self.PY + "\nfrom other import add\n"}
        for name, text in cases.items():
            with self.subTest(name):
                self.assertEqual(TL.compare(entry, text), "changed")

    def test_new_tests_with_fixture_marks_or_new_classes_are_tightening(self):
        entry = TL.entry_for(self.PY.encode(), "cao")
        ok = {"usefixtures": self.PY + "\n    @pytest.mark.usefixtures('db')\n    def test_db(self):\n        pass\n",
              "parametrize": self.PY + "\n    @pytest.mark.parametrize('fixture_name', [1])\n"
                                       "    def test_p(self, fixture_name):\n        pass\n",
              "hàm phụ run ở module": self.PY + "\n\ndef run(cmd):\n    return cmd\n",
              "setUp trong class mới": self.PY + "\n\nclass U(unittest.TestCase):\n    def setUp(self):\n        pass\n"}
        for name, text in ok.items():
            with self.subTest(name):
                self.assertEqual(TL.compare(entry, text), "added")
        bad = {"setup_function": self.PY + "\n\ndef setup_function():\n    pass\n",
               "setup_method": self.PY + "\n    def setup_method(self):\n        pass\n",
               "_callTestMethod": self.PY + "\n    def _callTestMethod(self, m):\n        pass\n",
               "ghi đè assertEqual": self.PY + "\n    def assertEqual(self, *a):\n        pass\n"}
        for name, text in bad.items():
            with self.subTest(name):
                self.assertEqual(TL.compare(entry, text), "changed")

    def test_too_deep_python_falls_back_to_lines(self):
        deep = "x = " + "+".join(["1"] * 5000) + "\n"
        entry = TL.entry_for(deep.encode(), "vua")
        self.assertNotIn("py", entry)
        self.assertEqual(TL.compare(entry, deep + "y = 2\n"), "added")

    def test_broken_or_huge_book_is_flagged_not_silently_empty(self):
        repo = self.tmp / "b"
        (repo / "tests").mkdir(parents=True)
        git(repo, "init", "-q")
        (repo / ".agent").mkdir()
        for text in ("{hỏng", '{"files": {"tests/t.py": {"sha256": [], "lines": [], "level": "cao"}}}',
                     '{"files": [], "approvals": []}'):
            with self.subTest(text=text):
                (repo / ".agent" / "test-lock.json").write_text(text)
                self.assertTrue(TL.load(repo).get("broken"))
                self.assertEqual(TL.lookup(repo / "tests" / "test_x.py")[2]["level"], "cao", "file test bị coi là khóa")
                self.assertIsNone(TL.lookup(repo / "app.py"))
        (repo / ".agent" / "test-lock.json").write_text('{"files": {}, "approvals": [{"path": "t.py", "sha256": []}]}')
        self.assertEqual(TL.load(repo)["approvals"], [], "bản ghi duyệt sai kiểu bị bỏ")

    def test_other_files_only_tighten_by_appending(self):
        js = b"test('a', () => {\n  expect(add(1, 2)).toBe(3);\n});\n"
        entry = TL.entry_for(js, "vua")
        self.assertNotIn("py", entry)
        self.assertEqual(TL.compare(entry, js.decode() + "test('b', () => {});\n"), "added")
        self.assertEqual(TL.compare(entry, js.decode().replace("{\n", "{\n  return;\n", 1)), "changed")
        self.assertEqual(TL.compare(entry, js.decode().replace("  expect", "expect")), "changed", "thụt lề tính")

    def test_unsafe_or_broken_books_are_ignored(self):
        # TM-105: sổ từ repo lạ không được trỏ ra ngoài repo; sổ hỏng hay quá lớn coi như không có.
        good = {"sha256": "0" * 64, "lines": [], "level": "cao"}
        book = TL.parse(json.dumps({"files": {"../ngoai.py": good, "/etc/passwd": good, "a\\b.py": good,
                                              "tests/t.py": good, "tests/thap.py": dict(good, level="thap")}}))
        self.assertEqual(list(book["files"]), ["tests/t.py"])
        self.assertTrue(book["broken"], "mục sai dạng làm sổ bị đánh dấu hỏng")
        for text in ("{hỏng", "[]", "x" * (TL.MAX_BOOK_BYTES + 1)):
            self.assertEqual(TL.parse(text)["files"], {})
            self.assertTrue(TL.parse(text)["broken"])
        bad_py = dict(good, py={"v": TL.PY_VERSION, "items": [1]})
        self.assertNotIn("py", TL.parse(json.dumps({"files": {"tests/t.py": bad_py}}))["files"]["tests/t.py"])

    def test_lookup_finds_locked_file_only_inside_its_repo(self):
        repo = self.tmp / "r"
        (repo / "tests").mkdir(parents=True)
        git(repo, "init", "-q")
        (repo / "tests" / "test_a.py").write_text("assert True\n")
        TL.save(repo, {"files": {"tests/test_a.py": TL.entry_for(b"assert True\n", "cao")}})
        top, rel, entry = TL.lookup(repo / "tests" / "test_a.py")
        self.assertEqual((top, rel, entry["level"]), (repo.resolve(), "tests/test_a.py", "cao"))
        self.assertIsNone(TL.lookup(repo / "tests" / "test_b.py"))
        self.assertIsNone(TL.lookup(self.tmp / "ngoai.py"))
        self.assertTrue(TL.is_lock_file(repo / ".agent" / "test-lock.json"))
        self.assertFalse(TL.is_lock_file(repo / "tests" / "test_a.py"))


class LockCommand(TempDirTestCase):
    """receipt.py lock dùng lại fails-before: chỉ khóa test đã chứng minh trượt trên code cũ."""

    # Mượn dữ liệu của FailsBefore (test_receipt), không kế thừa để không chạy lại test của nó.
    BUGGY, FIXED, CATCHES, MISSES, CMD = (TR.FailsBefore.BUGGY, TR.FailsBefore.FIXED, TR.FailsBefore.CATCHES,
                                          TR.FailsBefore.MISSES, TR.FailsBefore.CMD)

    def setUp(self):
        super().setUp()
        self.state = self.tmp / "state"
        self.repo = self.tmp / "proj"
        self.repo.mkdir()
        (self.repo / "calc.py").write_text(self.BUGGY)
        git(self.repo, "init", "-q")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "init")

    def fix_with(self, test):
        (self.repo / "calc.py").write_text(self.FIXED)
        (self.repo / "test_calc.py").write_text(test)

    def lock(self, *args):
        return run_script(RECEIPT, "lock", "--project", str(self.repo), *args,
                          env={"AGENT_STACK_STATE": str(self.state)})

    def book(self):
        return TL.load(self.repo)

    def test_locks_test_that_catches_the_bug(self):
        self.fix_with(self.CATCHES)
        out = self.lock("--level", "vua", *self.CMD)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        entry = self.book()["files"]["test_calc.py"]
        self.assertEqual(entry["level"], "vua")
        self.assertEqual(entry["sha256"], TL.digest((self.repo / "test_calc.py").read_bytes()))
        self.assertEqual(entry["lines"], TL.line_hashes(self.CATCHES))
        self.assertIn("đã khóa 1 file test", out.stdout)

    def test_does_not_lock_test_that_passes_on_old_code(self):
        self.fix_with(self.MISSES)
        out = self.lock("--level", "cao", *self.CMD)
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertEqual(self.book()["files"], {})
        self.assertIn("không khóa", out.stdout)

    def test_low_risk_does_not_lock(self):
        # Câu 3: mức thấp không khóa (đổi một dòng code kèm test là mức thấp theo risk.py).
        self.fix_with(self.CATCHES)
        out = self.lock(*self.CMD)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("mức rủi ro thấp: không khóa", out.stdout)
        self.assertFalse((self.repo / TL.LOCK_REL).exists())

    def commit_locked(self):
        self.fix_with(self.CATCHES)
        self.assertEqual(self.lock("--level", "cao", *self.CMD).returncode, 0)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "fix + lock")

    def test_loosened_locked_test_blocks_new_lock_until_unlocked(self):
        self.commit_locked()
        (self.repo / "test_calc.py").write_text(self.MISSES)
        (self.repo / "calc.py").write_text(self.BUGGY)
        (self.repo / "test_more.py").write_text(self.CATCHES.replace("class T", "class U"))
        out = self.lock("--level", "cao", "--tests", "test_more.py", *self.CMD)
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        self.assertIn("test_calc.py", out.stdout)
        shown = run_script(RECEIPT, "locks", "--project", str(self.repo))
        self.assertIn("test_calc.py: mức cao", shown.stdout)
        self.assertIn("bị sửa (nới, cần duyệt)", shown.stdout)

    def test_unlock_needs_reason_and_records_approval(self):
        self.commit_locked()
        out = run_script(RECEIPT, "unlock", "--project", str(self.repo), "--reason", " ", "test_calc.py")
        self.assertEqual(out.returncode, 2)
        out = run_script(RECEIPT, "unlock", "--project", str(self.repo), "--reason", "bạn: mở khóa test_calc.py",
                         "test_calc.py", "khong_co.py")
        self.assertEqual(out.returncode, 1, out.stdout)
        book = self.book()
        self.assertNotIn("test_calc.py", book["files"])
        self.assertEqual([(a["path"], a["action"], a["level"]) for a in book["approvals"]],
                         [("test_calc.py", "unlock", "cao")])

    def test_tightening_a_locked_test_can_be_relocked(self):
        self.commit_locked()
        (self.repo / "calc.py").write_text("def add(a, b):\n    return a + b + 0\n\n\ndef sub(a, b):\n    return a - b\n")
        extra = self.CATCHES + "\n    def test_add_neg(self):\n        self.assertEqual(add(-1, -1), -2)\n"
        (self.repo / "test_calc.py").write_text(extra)
        self.assertEqual(TL.status(self.repo, "test_calc.py", self.book()["files"]["test_calc.py"]), "added")
        # Phía trước (code cũ đã đúng) giờ đạt: lock từ chối vì test mới không chứng minh được gì, sổ giữ nguyên.
        out = self.lock("--level", "cao", *self.CMD)
        self.assertNotEqual(out.returncode, 3, out.stdout)
        self.assertEqual(self.book()["files"]["test_calc.py"]["lines"], TL.line_hashes(self.CATCHES))

    def test_level_can_be_raised_not_lowered(self):
        self.fix_with(self.CATCHES)
        with mock.patch.object(receipt, "assessed_level", return_value="cao"):
            code = receipt.cmd_lock(self.repo, "x", list(self.CMD[1:]), "HEAD", None, None, 60, "vua")
        self.assertEqual(code, 2)
        self.assertFalse((self.repo / TL.LOCK_REL).exists())
