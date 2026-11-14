"""Bánh cóc của done-gate (GĐ2, 13/11/2026): `risk.py` phân loại siết hay nới bằng diff và sổ khóa test, không theo
lời agent. Nới (sửa/xóa test khóa, mở khóa không duyệt, hạ ngưỡng, sửa spec, nới assert) thì đỏ; spec và code cùng đổi
thì đỏ; mở khóa có bản ghi duyệt thì vàng; chỉ thêm test thì xanh.

Gọi `risk.py` qua dòng lệnh như done-gate gọi, để test trượt trên code trước GĐ2 ở assert chứ không ở import.
"""
import hashlib
import json
import subprocess
import sys

from tests._util import PLUGIN, TempDirTestCase, git

RISK = PLUGIN / "skills" / "done-gate" / "scripts" / "risk.py"
RECEIPT = PLUGIN / "skills" / "session-keeper" / "scripts" / "receipt.py"
TEST = ("import unittest\nfrom calc import add\n\n\nclass T(unittest.TestCase):\n    def test_add(self):\n"
        "        self.assertEqual(add(2, 3), 5)\n")


def write_lock(repo, level, *files):
    """Thêm mục vào sổ khóa theo đúng định dạng của plugin/lib/testlock.py (định dạng sổ là hợp đồng giữa receipt.py,
    hook và done-gate), không import module đó, để test trượt ở assert trên code trước GĐ2."""
    path = repo / ".agent" / "test-lock.json"
    book = json.loads(path.read_text()) if path.exists() else {"schema": 1, "files": {}, "approvals": []}
    for rel in files:
        data = (repo / rel).read_bytes()
        lines = [hashlib.sha1(x.rstrip().encode()).hexdigest()[:12] for x in data.decode().splitlines() if x.strip()]
        book["files"][rel] = {"sha256": hashlib.sha256(data).hexdigest(), "lines": lines, "level": level}
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(book))


class Ratchet(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.repo = self.tmp / "proj"
        (self.repo / "tests").mkdir(parents=True)
        (self.repo / "calc.py").write_text("def add(a, b):\n    return a + b\n")
        (self.repo / "tests" / "test_calc.py").write_text(TEST)
        (self.repo / "pyproject.toml").write_text("[tool.coverage.report]\nfail_under = 90\n")
        (self.repo / "specs").mkdir()
        (self.repo / "specs" / "calc.md").write_text("- Khi cộng 2 và 3 thì phải ra 5.\n")
        git(self.repo, "init", "-q")
        self.lock("cao", "tests/test_calc.py")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "init + khóa")

    def lock(self, level, *files):
        write_lock(self.repo, level, *files)

    def risk(self):
        out = subprocess.run([sys.executable, str(RISK), str(self.repo), "--json", "--writer", "opus"],
                             capture_output=True, text=True, env={"AGENT_STACK_STATE": str(self.tmp / "state"),
                                                                  "PATH": "/usr/bin:/bin:/usr/local/bin"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        return json.loads(out.stdout).get("ratchet") or {}

    def text(self):
        out = subprocess.run([sys.executable, str(RISK), str(self.repo), "--writer", "opus"], capture_output=True,
                             text=True, env={"AGENT_STACK_STATE": str(self.tmp / "state"),
                                             "PATH": "/usr/bin:/bin:/usr/local/bin"})
        return out.stdout

    def put(self, rel, text):
        (self.repo / rel).write_text(text)

    def test_loosening_a_locked_test_is_red(self):
        # Ca chứng minh của GĐ2: agent nới assert của test đã khóa để test qua.
        self.put("tests/test_calc.py", TEST.replace("assertEqual(add(2, 3), 5)", "assertTrue(add(2, 3))"))
        r = self.risk()
        self.assertEqual(r.get("verdict"), "do", r)
        self.assertTrue(any("sửa test đã khóa tests/test_calc.py" in x for x in r["loosen"]), r)
        self.assertIn("Bánh cóc: 🔴", self.text())

    def test_deleting_a_locked_test_is_red(self):
        (self.repo / "tests" / "test_calc.py").unlink()
        r = self.risk()
        self.assertEqual(r.get("verdict"), "do", r)
        self.assertTrue(any("xóa test đã khóa" in x for x in r["loosen"]), r)

    def test_adding_to_a_locked_test_or_a_new_test_is_tightening(self):
        self.put("tests/test_calc.py", TEST + "\n    def test_neg(self):\n        self.assertEqual(add(-1, -1), -2)\n")
        self.put("tests/test_more.py", TEST.replace("class T", "class U"))
        r = self.risk()
        self.assertEqual(r.get("verdict"), "xanh", r)
        self.assertTrue(any("thêm test vào test đã khóa tests/test_calc.py" in x for x in r["tighten"]), r)
        self.assertTrue(any("thêm test tests/test_more.py" in x for x in r["tighten"]), r)

    def test_hand_edited_lock_book_without_approval_is_red(self):
        self.put(".agent/test-lock.json", '{"files": {}}')
        r = self.risk()
        self.assertEqual(r.get("verdict"), "do", r)
        self.assertTrue(any("không có bản ghi duyệt" in x for x in r["loosen"]), r)

    def unlock(self):
        out = subprocess.run([sys.executable, str(RECEIPT), "unlock", "--project", str(self.repo), "--reason",
                              "bạn: mở khóa tests/test_calc.py", "tests/test_calc.py"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def hook_consent(self, rel, sha=None):
        """Biên nhận hook pretool_guard ghi vào state/ khi cho `unlock` qua nhờ lời người dùng (định dạng hợp đồng),
        gắn sha256 của bản đã khóa."""
        if sha is None:
            book = json.loads(subprocess.run(["git", "-C", str(self.repo), "show", "HEAD:.agent/test-lock.json"],
                                             capture_output=True, text=True).stdout)
            sha = book["files"][rel]["sha256"]
        path = self.tmp / "state" / "unlock-consents.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([{"top": str(self.repo.resolve()), "path": rel, "sha256": sha, "ts": 0,
                                     "text": "mở khóa"}]))

    def test_consent_for_another_version_does_not_count(self):
        self.unlock()
        self.hook_consent("tests/test_calc.py", sha="0" * 64)
        self.assertEqual(self.risk().get("verdict"), "do")

    def test_entry_weakened_while_file_is_unchanged_is_red(self):
        # Review lại 14/11: cắt `lines` của mục sổ (file giữ nguyên) để lần sau mọi sửa phía sau tính là siết.
        book = json.loads((self.repo / ".agent" / "test-lock.json").read_text())
        book["files"]["tests/test_calc.py"]["lines"] = book["files"]["tests/test_calc.py"]["lines"][:2]
        self.put(".agent/test-lock.json", json.dumps(book))
        r = self.risk()
        self.assertEqual(r.get("verdict"), "do", r)
        self.assertTrue(any("không khớp file hiện tại" in x for x in r["loosen"]), r)

    def test_broken_lock_book_is_red(self):
        self.put(".agent/test-lock.json", "{hỏng")
        r = self.risk()
        self.assertEqual(r.get("verdict"), "do", r)
        self.assertTrue(any("hỏng hay quá lớn" in x for x in r["loosen"]), r)

    def test_hand_edited_entry_with_same_sha_is_judged_against_base(self):
        # Sửa test rồi sửa tay `lines` trong sổ cho khớp (giữ sha cũ): so với bản ở base nên vẫn đỏ.
        loose = TEST.replace("assertEqual(add(2, 3), 5)", "assertTrue(add(2, 3))")
        self.put("tests/test_calc.py", loose)
        book = json.loads((self.repo / ".agent" / "test-lock.json").read_text())
        book["files"]["tests/test_calc.py"]["lines"] = [
            hashlib.sha1(x.rstrip().encode()).hexdigest()[:12] for x in loose.splitlines() if x.strip()]
        self.put(".agent/test-lock.json", json.dumps(book))
        r = self.risk()
        self.assertEqual(r.get("verdict"), "do", r)

    def test_unlock_with_hook_consent_is_yellow(self):
        self.unlock()
        self.hook_consent("tests/test_calc.py")
        r = self.risk()
        self.assertEqual(r.get("verdict"), "vang", r)
        self.assertIn("bạn: mở khóa", r["approved"][0])

    def test_approval_written_without_hook_consent_is_red(self):
        # Reviewer 13/11: agent tự ghi bản ghi duyệt vào sổ (script hook không soi) thì không được tính là đã duyệt.
        self.unlock()
        r = self.risk()
        self.assertEqual(r.get("verdict"), "do", r)
        self.assertTrue(any("không có biên nhận đồng ý của hook" in x for x in r["loosen"]), r)

    def test_relocking_after_an_approved_unlock_is_yellow_not_red(self):
        self.unlock()
        self.hook_consent("tests/test_calc.py")
        self.put("tests/test_calc.py", TEST.replace("(2, 3), 5", "(2, 2), 4"))
        write_lock(self.repo, "cao", "tests/test_calc.py")
        r = self.risk()
        self.assertEqual(r.get("verdict"), "vang", r)
        self.assertTrue(any("sửa rồi khóa lại tests/test_calc.py" in x for x in r["approved"]), r)

    def test_removing_or_commenting_out_a_threshold_is_red(self):
        for text in ("[tool.coverage.report]\n", "[tool.coverage.report]\n# fail_under = 90\n"):
            with self.subTest(text=text):
                self.put("pyproject.toml", text)
                r = self.risk()
                self.assertEqual(r.get("verdict"), "do", r)
                self.assertTrue(any("bỏ ngưỡng fail_under = 90" in x for x in r["loosen"]), r)

    def test_names_that_only_contain_min_or_max_are_not_thresholds(self):
        self.put("tests/test_c.py", "ADMIN_COUNT = 2\nterminal_width = 80\nMAX_ROWS = 5\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "c")
        self.put("tests/test_c.py", "ADMIN_COUNT = 1\nterminal_width = 60\nMAX_ROWS = 9\n")
        r = self.risk()
        self.assertFalse(any("admin" in x or "terminal" in x for x in r["loosen"]), r)
        self.assertTrue(any("hạ ngưỡng max_rows: 5 → 9" in x for x in r["loosen"]), r)

    def test_lowering_a_threshold_is_red_and_raising_is_tightening(self):
        self.put("pyproject.toml", "[tool.coverage.report]\nfail_under = 80\n")
        r = self.risk()
        self.assertEqual(r.get("verdict"), "do", r)
        self.assertTrue(any("hạ ngưỡng fail_under: 90 → 80" in x for x in r["loosen"]), r)
        self.put("pyproject.toml", "[tool.coverage.report]\nfail_under = 95\n")
        self.assertTrue(any("nâng ngưỡng fail_under" in x for x in self.risk()["tighten"]))

    def test_changing_spec_lines_is_loosening(self):
        self.put("specs/calc.md", "- Khi cộng 2 và 3 thì phải ra một số dương.\n")
        r = self.risk()
        self.assertEqual(r.get("verdict"), "do", r)
        self.assertTrue(any("đổi spec specs/calc.md" in x for x in r["loosen"]), r)

    def test_spec_and_code_in_one_change_is_red(self):
        self.put("specs/calc.md", "- Khi cộng 2 và 3 thì phải ra 5.\n- Khi cộng 0 và 0 thì phải ra 0.\n")
        self.put("calc.py", "def add(a, b):\n    return b + a\n")
        r = self.risk()
        self.assertEqual(r.get("verdict"), "do", r)
        self.assertEqual(r["loosen"], [], "chỉ thêm dòng spec thì không phải nới")
        self.assertTrue(any("spec và code đổi trong cùng một thay đổi" in x for x in r["red"]), r)

    def test_weakened_assert_in_unlocked_test_is_still_loosening(self):
        self.put("tests/test_other.py", TEST)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "test khác, không khóa")
        self.put("tests/test_other.py", TEST.replace("assertEqual(add(2, 3), 5)", "assertTrue(add(2, 3))"))
        r = self.risk()
        self.assertEqual(r.get("verdict"), "do", r)
        self.assertTrue(any("nới assert" in x for x in r["loosen"]), r)

    def test_project_without_locks_and_without_tests_has_no_section(self):
        self.put("calc.py", "def add(a, b):\n    return a + b  # cộng\n")
        self.assertEqual(self.risk().get("verdict"), "", self.risk())
        self.assertNotIn("Bánh cóc", self.text())
