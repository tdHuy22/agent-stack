"""GĐ6 (16/11/2026), slug `gd6-spec-theo-lat`: bánh cóc và mục Spec của `risk.py` với file spec theo lát
`.agent/spec/<slug>.txt` (S7, S8, S12).

Gọi `risk.py` qua dòng lệnh như done-gate gọi, sổ duyệt viết thẳng vào `<AGENT_STACK_STATE>/spec-approvals.json` (định
dạng của plugin/lib/specbook.py). Test mới trượt ở assert (thiếu mục tighten, đỏ thừa, thiếu khóa `spec`), không ở import.
"""
import hashlib
import json
import subprocess
import sys

from tests._util import PLUGIN, TempDirTestCase, git

sys.path.insert(0, str(PLUGIN / "lib"))
import specbook as SB  # noqa: E402
import testlock as TL  # noqa: E402

RISK = PLUGIN / "skills" / "done-gate" / "scripts" / "risk.py"
SPEC_REL = ".agent/spec/x.txt"
LINES = [("S1", "Khi a thì b"), ("S2", "Khi c thì d")]
SPEC1 = "S1: Khi a thì b\n"
SPEC2 = SPEC1 + "S2: Khi c thì d\n"
HOOK_VUA = "X = 1\n"  # đường dẫn hooks/ cộng 2 điểm: mức vừa
HOOK_CAO = "import os\nos.system('ls')\n"  # hooks/ (2) + chạy lệnh (2): mức cao
TEST_BODY = ("import unittest\n\n\nclass T(unittest.TestCase):\n    def test_a(self):\n"
             "        # spec:x#S1\n        self.assertEqual(1, 1)\n")


class SpecRatchetBase(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.repo = self.tmp / "proj"
        (self.repo / "tests").mkdir(parents=True)
        (self.repo / "hooks").mkdir()
        (self.repo / "calc.py").write_text("def add(a, b):\n    return a + b\n")
        (self.repo / "tests" / "test_calc.py").write_text("import unittest\n")
        (self.repo / "hooks" / "h.py").write_text("X = 0\n")
        (self.repo / "README.md").write_text("# proj\n")
        git(self.repo, "init", "-q")
        self.commit("init")

    def commit(self, msg):
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", msg)

    def put(self, rel, text):
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def head(self):
        return git(self.repo, "rev-parse", "HEAD").strip()

    def lock(self, *rels, level="cao", red=None):
        """Thêm mục vào sổ khóa theo đúng định dạng của testlock; ghi một dòng để không thêm điểm cỡ diff."""
        path = self.repo / TL.LOCK_REL
        book = json.loads(path.read_text()) if path.exists() else {"schema": 1, "files": {}, "approvals": []}
        for rel in rels:
            extra = {"red": red} if red else {}
            book["files"][rel] = TL.entry_for((self.repo / rel).read_bytes(), level, **extra)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(book, ensure_ascii=False))

    def red_info(self):
        return {"kind": "assert", "line": "AssertionError: 1 != 2", "base": self.head(), "ts": "2026-11-16T10:00:00+07:00"}

    def approve(self, pairs, source, top=None):
        """Bản ghi duyệt như hook ghi: duyệt `duyet-spec` gắn với file, `ke-hoach` thì không."""
        path = self.tmp / "state" / "spec-approvals.json"
        rows = json.loads(path.read_text()) if path.exists() else []
        sha = hashlib.sha256((self.repo / SPEC_REL).read_bytes()).hexdigest() if source == "duyet-spec" else None
        rows.append({"top": top or str(self.repo.resolve()), "path": SPEC_REL if source == "duyet-spec" else None,
                     "sha256": sha, "lines": [SB.line_hash(s, t) for s, t in pairs], "source": source,
                     "ts": "2026-11-16T10:00:00+07:00"})
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows))

    def run_risk(self, *extra, as_json=True, writer="opus"):
        cmd = [sys.executable, str(RISK), str(self.repo), "--writer", writer, *extra]
        out = subprocess.run(cmd + (["--json"] if as_json else []), capture_output=True, text=True,
                             env={"AGENT_STACK_STATE": str(self.tmp / "state"), "PATH": "/usr/bin:/bin:/usr/local/bin"})
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        return json.loads(out.stdout) if as_json else out.stdout

    def ratchet(self):
        return self.run_risk().get("ratchet") or {}

    def spec_red(self, r):
        return [x for x in r["red"] if "spec" in x.lower()]


class SpecRatchetLoosenTighten(SpecRatchetBase):
    """S8: sửa hay xóa dòng spec có sẵn thì nới; thêm dòng ở cuối thì siết."""

    def setUp(self):
        super().setUp()
        self.put(SPEC_REL, SPEC1)
        self.commit("spec S1")

    def test_editing_an_existing_line_is_loosening(self):
        # spec:gd6-spec-theo-lat#S8
        self.put(SPEC_REL, "S1: Khi a thì khác b\n")
        r = self.ratchet()
        self.assertEqual(r.get("verdict"), "do", r)
        self.assertTrue(any(SPEC_REL in x for x in r["loosen"]), r)

    def test_deleting_a_line_is_loosening(self):
        # spec:gd6-spec-theo-lat#S8
        self.put(SPEC_REL, SPEC2)
        self.commit("spec S2")
        self.put(SPEC_REL, SPEC1)
        r = self.ratchet()
        self.assertEqual(r.get("verdict"), "do", r)
        self.assertTrue(any(SPEC_REL in x for x in r["loosen"]), r)

    def test_editing_and_appending_together_is_still_loosening(self):
        # spec:gd6-spec-theo-lat#S8
        self.put(SPEC_REL, "S1: Khi a thì khác b\nS2: Khi c thì d\n")
        r = self.ratchet()
        self.assertEqual(r.get("verdict"), "do", r)
        self.assertTrue(any(SPEC_REL in x for x in r["loosen"]), r)

    def test_appending_an_approved_line_is_tightening(self):
        # spec:gd6-spec-theo-lat#S8
        self.put(SPEC_REL, SPEC2)
        self.approve(LINES, "duyet-spec")
        r = self.ratchet()
        self.assertEqual(r.get("verdict"), "xanh", r)
        self.assertTrue(any(SPEC_REL in x for x in r["tighten"]), r)
        self.assertFalse(any(SPEC_REL in x for x in r["loosen"]), r)
        self.assertEqual(r["red"], [], r)
        self.assertEqual(r.get("pending") or [], [], r)

    def test_appending_an_unapproved_line_without_code_is_pending_yellow(self):
        # spec:gd6-spec-theo-lat#S8
        self.put(SPEC_REL, SPEC2)
        self.approve(LINES[:1], "duyet-spec")  # chỉ S1 đã duyệt
        full = self.run_risk()
        self.assertIn(full["level"], ("thap", "vua"), full["reasons"])
        r = full["ratchet"]
        self.assertEqual(r.get("verdict"), "vang", r)
        self.assertTrue(any(SPEC_REL in x and "S2" in x for x in r.get("pending", [])), r)
        self.assertFalse(any("S1" in x for x in r.get("pending", [])), "S1 đã duyệt, không được nêu là chưa duyệt")
        self.assertEqual(r["red"], [], r)
        self.assertEqual(r["loosen"], [], r)
        text = self.run_risk(as_json=False)
        self.assertTrue(any("🟡" in ln and "chưa duyệt" in ln for ln in text.splitlines()), text)

    def test_appending_an_unapproved_line_at_high_level_is_red(self):
        # spec:gd6-spec-theo-lat#S8
        # Mức cao mà diff không có code: file phụ thuộc (2) cộng file schema dạng tài liệu (3) = 5 điểm.
        self.put(SPEC_REL, SPEC2)
        self.approve(LINES, "ke-hoach")  # ở mức cao chỉ tính câu duyệt spec, nên S2 vẫn là chưa duyệt
        self.put("requirements.txt", "requests==2.0\n")
        self.put("docs/schema.txt", "bảng a\n")
        full = self.run_risk()
        self.assertEqual(full["level"], "cao", full["reasons"])
        r = full["ratchet"]
        self.assertEqual(r.get("verdict"), "do", r)
        self.assertTrue(any(SPEC_REL in x and "S2" in x for x in r["red"]), r)


class SpecRatchetRed(SpecRatchetBase):
    """S7: spec và code cùng đổi thì đỏ, trừ khi spec đã khóa và mọi dòng đã duyệt (mức cao chỉ tính duyệt-spec)."""

    def setup_spec(self, text=SPEC2, lock=True):
        self.put(SPEC_REL, text)
        if lock:
            self.lock(SPEC_REL)

    def change_code(self, text=HOOK_VUA):
        self.put("hooks/h.py", text)

    def test_unlocked_spec_with_code_is_red(self):
        # spec:gd6-spec-theo-lat#S7
        self.setup_spec(lock=False)
        self.approve(LINES, "duyet-spec")
        self.change_code()
        r = self.ratchet()
        self.assertEqual(r.get("verdict"), "do", r)
        self.assertTrue(self.spec_red(r), r)

    def test_spec_without_any_approval_with_code_is_red(self):
        # spec:gd6-spec-theo-lat#S7
        self.setup_spec(lock=False)
        self.change_code()
        r = self.ratchet()
        self.assertEqual(r.get("verdict"), "do", r)
        self.assertTrue(self.spec_red(r), r)

    def test_locked_and_user_approved_spec_with_code_is_not_red(self):
        # spec:gd6-spec-theo-lat#S7
        self.setup_spec()
        self.approve(LINES, "duyet-spec")
        self.change_code(HOOK_CAO)
        full = self.run_risk()
        self.assertEqual(full["level"], "cao", full["reasons"])
        r = full["ratchet"]
        self.assertEqual(self.spec_red(r), [], r)
        self.assertNotEqual(r.get("verdict"), "do", r)

    def test_appended_spec_relocked_and_approved_is_not_red(self):
        # spec:gd6-spec-theo-lat#S7
        self.put(SPEC_REL, SPEC1)
        self.lock(SPEC_REL)
        self.commit("spec S1 đã khóa")
        self.setup_spec(SPEC2)
        self.approve(LINES, "duyet-spec")
        self.change_code()
        r = self.ratchet()
        self.assertEqual(self.spec_red(r), [], r)
        self.assertNotEqual(r.get("verdict"), "do", r)

    def test_plan_approval_is_enough_at_medium_level(self):
        # spec:gd6-spec-theo-lat#S7
        self.setup_spec()
        self.approve(LINES, "ke-hoach")
        self.change_code(HOOK_VUA)
        full = self.run_risk()
        self.assertEqual(full["level"], "vua", full["reasons"])
        self.assertEqual(self.spec_red(full["ratchet"]), [], full["ratchet"])
        self.assertNotEqual(full["ratchet"].get("verdict"), "do", full["ratchet"])

    def test_plan_approval_is_not_enough_at_high_level(self):
        # spec:gd6-spec-theo-lat#S7
        self.setup_spec()
        self.approve(LINES, "ke-hoach")
        self.change_code(HOOK_CAO)
        full = self.run_risk()
        self.assertEqual(full["level"], "cao", full["reasons"])
        self.assertEqual(full["ratchet"].get("verdict"), "do", full["ratchet"])
        self.assertTrue(self.spec_red(full["ratchet"]), full["ratchet"])

    def test_unapproved_new_line_is_red_and_named(self):
        # spec:gd6-spec-theo-lat#S7
        self.setup_spec()
        self.approve(LINES[:1], "duyet-spec")
        self.change_code()
        r = self.ratchet()
        self.assertEqual(r.get("verdict"), "do", r)
        self.assertTrue(any("S2" in x for x in r["red"]), r)
        self.assertFalse(any("S1" in x for x in r["red"]), "S1 đã duyệt, không được nêu như dòng thiếu duyệt")

    def test_edited_line_after_approval_is_not_approved(self):
        # spec:gd6-spec-theo-lat#S7
        self.setup_spec()
        self.approve(LINES, "duyet-spec")
        self.put(SPEC_REL, "S1: Khi a thì khác b\nS2: Khi c thì d\n")
        self.lock(SPEC_REL)
        self.change_code()
        r = self.ratchet()
        self.assertEqual(r.get("verdict"), "do", r)
        self.assertTrue(any("S1" in x for x in r["red"]), r)

    def test_approval_for_another_repo_does_not_count(self):
        # spec:gd6-spec-theo-lat#S7
        self.setup_spec()
        self.approve(LINES, "duyet-spec", top=str(self.tmp / "khac"))
        self.change_code()
        r = self.ratchet()
        self.assertEqual(r.get("verdict"), "do", r)
        self.assertTrue(self.spec_red(r), r)


class SpecSection(SpecRatchetBase):
    """S12: mục Spec của risk.py ở mức vừa trở lên có đổi code."""

    def spec_diff(self, code=HOOK_VUA):
        self.put(SPEC_REL, SPEC2)
        self.put("hooks/h.py", code)

    def section_lines(self, text):
        return [x for x in text.splitlines() if x.startswith("Spec:")]

    def test_lists_spec_file_with_counts(self):
        # spec:gd6-spec-theo-lat#S12
        self.spec_diff()
        self.put("tests/test_x.py", TEST_BODY)
        self.lock("tests/test_x.py", level="vua")  # gd6-qs-cong-cu S4: mục khóa mức cao nâng diff có code lên cao
        self.approve(LINES[:1], "duyet-spec")
        self.approve(LINES[1:], "ke-hoach")
        full = self.run_risk()
        self.assertEqual(full["level"], "vua", full["reasons"])
        spec = full.get("spec")
        self.assertIsInstance(spec, dict, full.keys())
        self.assertEqual([f["path"] for f in spec["files"]], [SPEC_REL], spec)
        item = spec["files"][0]
        self.assertEqual((item["lines"], item["approved_user"], item["approved_plan"], item["tests_locked"]),
                         (2, 1, 1, 1), item)
        self.assertFalse(spec.get("missing"), spec)
        text = self.run_risk(as_json=False)
        self.assertTrue(self.section_lines(text), text)
        self.assertIn(SPEC_REL, text)

    def test_high_lock_of_a_test_raises_a_code_diff_to_high(self):
        # spec:gd6-qs-cong-cu#S4 (cùng cảnh như trên, khóa test ở mức cao: mức khai lúc khóa là mức của lát)
        self.spec_diff()
        self.put("tests/test_x.py", TEST_BODY)
        self.lock("tests/test_x.py", level="cao")
        full = self.run_risk()
        self.assertEqual(full["level"], "cao", full["reasons"])
        self.assertTrue(any("khóa test" in r for r in full["reasons"]), full["reasons"])

    def test_lists_red_locked_tests_only(self):
        # spec:gd6-spec-theo-lat#S12
        self.spec_diff()
        self.put("tests/test_x.py", TEST_BODY)
        self.put("tests/test_y.py", TEST_BODY.replace("test_a", "test_b").replace("S1", "S2"))
        self.lock("tests/test_x.py", red=self.red_info())
        self.lock("tests/test_y.py")
        spec = self.run_risk().get("spec")
        self.assertIsInstance(spec, dict)
        self.assertEqual(spec["red_locked"], ["tests/test_x.py"], spec)

    def test_writer_is_other_family_at_high_level(self):
        # spec:gd6-spec-theo-lat#S12
        self.spec_diff(HOOK_CAO)
        for writer, other in (("opus", "sonnet"), ("sonnet", "opus"), ("fable", "opus"), ("haiku", "opus")):
            with self.subTest(writer=writer):
                full = self.run_risk(writer=writer)
                self.assertEqual(full["level"], "cao", full["reasons"])
                tw = (full.get("spec") or {}).get("test_writer")
                self.assertIsInstance(tw, str, full.get("spec"))
                self.assertIn(other, tw.lower())

    def test_writer_is_present_at_medium_level(self):
        # spec:gd6-spec-theo-lat#S12
        self.spec_diff()
        full = self.run_risk()
        self.assertEqual(full["level"], "vua", full["reasons"])
        tw = (full.get("spec") or {}).get("test_writer")
        self.assertTrue(isinstance(tw, str) and tw.strip(), full.get("spec"))

    def test_missing_spec_is_reported_without_turning_the_ratchet_red(self):
        # spec:gd6-spec-theo-lat#S12
        self.put("hooks/h.py", HOOK_VUA)
        full = self.run_risk()
        self.assertEqual(full["level"], "vua", full["reasons"])
        spec = full.get("spec")
        self.assertIsInstance(spec, dict, full.keys())
        self.assertIs(spec.get("missing"), True, spec)
        self.assertEqual(spec.get("files"), [], spec)
        text = self.run_risk(as_json=False)
        self.assertTrue(self.section_lines(text), text)
        self.assertIn("thiếu spec", text.lower())
        self.assertNotEqual(full["ratchet"].get("verdict"), "do", full["ratchet"])
        self.assertEqual(full["ratchet"]["red"], [], full["ratchet"])

    def test_red_locked_test_without_spec_file_is_not_missing(self):
        # spec:gd6-spec-theo-lat#S12
        self.put("hooks/h.py", HOOK_VUA)
        self.put("tests/test_x.py", TEST_BODY)
        self.lock("tests/test_x.py", red=self.red_info())
        spec = self.run_risk().get("spec")
        self.assertIsInstance(spec, dict)
        self.assertFalse(spec.get("missing"), spec)
        self.assertEqual(spec["red_locked"], ["tests/test_x.py"], spec)

    def test_no_section_at_low_level(self):
        # spec:gd6-spec-theo-lat#S12
        self.put("README.md", "# proj\n\nThêm một dòng.\n")
        full = self.run_risk()
        self.assertEqual(full["level"], "thap", full["reasons"])
        self.assertFalse(full.get("spec"), full.get("spec"))
        self.assertEqual(self.section_lines(self.run_risk(as_json=False)), [])


if __name__ == "__main__":
    import unittest
    unittest.main()
