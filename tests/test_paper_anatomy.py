"""Script của skill paper-anatomy: dò nhãn trang in, tiêu đề mục, chỉ mục hình/bảng, và kiểm thẻ neo."""
import json
import sys
import unittest

from tests._util import REPO, TempDirTestCase, run_script

SCRIPTS = REPO / "claude-ai-skills" / "paper-anatomy" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import extract_paper  # noqa: E402
import verify_anchors  # noqa: E402

VERIFY = SCRIPTS / "verify_anchors.py"
EXTRACT = SCRIPTS / "extract_paper.py"


def page(i, label, text):
    return {"index": i, "label": label, "chars": len(text), "columns": 1, "text": text}


# Bài giả 4 trang, nhãn in kiểu kỷ yếu (101–104), có mục, hình, bảng, công thức và một trang scan.
CACHE = {
    "schema": 2, "page_count": 4,
    "pages": [
        page(1, "101", "1\nIntroduction\nWe propose structured queries that separate\ninstruc-\ntions from data.\n101"),
        page(2, "102", "3.1\nThreat Model\nThe attacker controls the data channel only.\n"
                       "Figure 2: Overview of the secure front-end.\nscore = q k / sqrt(d)\n(4)\n102"),
        page(3, "103", "4\nExperiments\nTable 3: Attack success rate drops to 1.2% on Llama.\n"
                       "As shown in Figure 2, the filter removes delimiters.\n103"),
        page(4, "104", ""),
    ],
    "sections": [
        {"title": "1 Introduction", "number": "1", "level": 1, "page": 1, "label": "101", "end": 2},
        {"title": "3.1 Threat Model", "number": "3.1", "level": 2, "page": 2, "label": "102", "end": 3},
        {"title": "4 Experiments", "number": "4", "level": 1, "page": 3, "label": "103", "end": 4},
    ],
    "objects": [],
}


def status_of(anchor):
    status, reasons, _ = verify_anchors.check_anchor(verify_anchors.Paper(CACHE), anchor)
    return status, " | ".join(reasons)


class PrintedLabels(unittest.TestCase):
    def test_offset_consensus_beats_stray_numbers(self):
        texts = [f"Body text with value\n12\nmore text\n{100 + i}" for i in range(1, 9)]
        labels, how = extract_paper.printed_labels(texts)
        self.assertEqual(labels[:3], ["101", "102", "103"])
        self.assertIn("+ 100", how)

    def test_declared_pdf_labels_win(self):
        labels, how = extract_paper.printed_labels(["a", "b", "c"], ["36002", "36003", "36004"])
        self.assertEqual(labels, ["36002", "36003", "36004"])
        self.assertIn("khai báo", how)

    def test_falls_back_to_pdf_index(self):
        labels, how = extract_paper.printed_labels(["no numbers here", "none either", "nope"])
        self.assertEqual(labels, ["1", "2", "3"])
        self.assertIn("trang PDF", how)


class Headings(unittest.TestCase):
    def test_number_and_title_on_separate_lines_are_merged(self):
        merged = extract_paper.merged_lines(["3.1", "Threat Model", "The attacker controls data."])
        self.assertEqual(merged[0], "3.1 Threat Model")

    def test_page_number_before_body_text_is_not_a_heading(self):
        lines = ["2", "LLM-integrated application, the application is written by a developer who wants"]
        self.assertEqual(extract_paper.merged_lines(lines), [s.strip() for s in lines])

    def test_heuristic_headings_keep_order(self):
        texts = ["1\nIntroduction\nbody.", "2 Method\nbody text here.\n12 apples were eaten", "Conclusion\nend."]
        heads = [h for _, h in extract_paper.heuristic_headings(texts)]
        self.assertEqual(heads, ["1 Introduction", "2 Method", "Conclusion"])

    def test_objects_index_captions_and_equations(self):
        objs = extract_paper.index_objects([p["text"] for p in CACHE["pages"]])
        found = {(o["kind"], o["id"], o["page"]) for o in objs}
        self.assertIn(("Figure", "2", 2), found)
        self.assertIn(("Table", "3", 3), found)
        self.assertIn(("Eq", "4", 2), found)
        self.assertNotIn(("Figure", "2", 3), found, "câu nhắc 'As shown in Figure 2' không phải chú thích")


class VerifyAnchors(unittest.TestCase):
    def test_good_anchors(self):
        for anchor in ('§1 · tr.101 · "separate instructions from data"',   # gạch nối xuống dòng vẫn khớp
                       "§3.1 · tr.102 · Hình 2 · Eq.(4)",
                       '§4 · tr.103 · Bảng 3 · "drops to 1.2% on Llama"',
                       "§3.1 · tr.PDF2",
                       "§Experiments · tr.102–103 · Figure 2"):
            with self.subTest(anchor=anchor):
                self.assertEqual(status_of(anchor)[0], "OK", status_of(anchor)[1])

    def test_failures(self):
        cases = {
            "§4 · tr.101 · Bảng 3": "Table 3 không có trên trang",
            "§1 · tr.999": "không có trong bài",
            '§4 · tr.103 · "the attack is fully solved forever"': "không tìm thấy trích",
            '§4 · tr.103 · "We propose structured queries that separate"': "trang PDF 1",
            "§4 · tr.101": "§4 nằm ở trang PDF 3",
            "Bảng 3": "thiếu trang",
        }
        for anchor, why in cases.items():
            with self.subTest(anchor=anchor):
                status, reasons = status_of(anchor)
                self.assertEqual(status, "FAIL", reasons)
                self.assertIn(why, reasons)

    def test_warnings(self):
        cases = {
            "§Methodology · tr.102": "không thấy mục",
            '§4 · tr.104 · "anything on a scanned page"': "scan",
            '§1 · tr.101 · "abc"': "quá ngắn",
        }
        for anchor, why in cases.items():
            with self.subTest(anchor=anchor):
                status, reasons = status_of(anchor)
                self.assertEqual(status, "WARN", reasons)
                self.assertIn(why, reasons)

    def test_unanchored_paragraphs_and_long_quotes(self):
        long_para = " ".join(["Câu này nói về bài mà không có neo nào cả."] * 6)
        inferred = "[suy luận] " + long_para
        text = (f"# Tiêu đề\n\n{long_para}\n\n{inferred}\n\n"
                'Họ viết "one two three four five six seven eight nine ten eleven twelve thirteen fourteen '
                'fifteen sixteen" ở đây 【§1 · tr.101】.\n')
        result = verify_anchors.run(text, CACHE)
        self.assertEqual(len(result["unanchored_paragraphs"]), 1)
        self.assertEqual(len(result["long_quotes"]), 1)

    def test_quotes_pair_correctly(self):
        # Hai câu trích ngắn trong cùng đoạn không được ghép thành một "câu trích" dài từ ngoặc đóng tới ngoặc mở.
        text = ('Lệnh "Print exactly Hacked" nằm trong data, ' + "chữ " * 30 + 'rồi "ignore previous" ở đây 【§1 · tr.101】.\n'
                '[minh họa] Prompt tự dựng: "one two three four five six seven eight nine ten eleven twelve '
                'thirteen fourteen fifteen sixteen".\n')
        self.assertEqual(verify_anchors.run(text, CACHE)["long_quotes"], [])
        status, reasons = status_of('§1 · tr.101 · "We propose structured queries" và “separate instructions from data”')
        self.assertEqual(status, "OK", reasons)

    def test_cli_exit_codes(self):
        tmp = REPO / ".tmp" / "test-paper-anatomy"
        tmp.mkdir(parents=True, exist_ok=True)
        (tmp / "pages.json").write_text(json.dumps(CACHE), encoding="utf-8")
        (tmp / "ok.md").write_text("Ý chính 【§1 · tr.101 · \"separate instructions from data\"】\n", encoding="utf-8")
        (tmp / "bad.md").write_text("Sai 【§1 · tr.999】\n", encoding="utf-8")
        ok = run_script(VERIFY, str(tmp / "ok.md"), "--pages", str(tmp / "pages.json"))
        bad = run_script(VERIFY, str(tmp / "bad.md"), "--pages", str(tmp / "pages.json"), "--json")
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        self.assertIn("sai 0", ok.stdout)
        self.assertEqual(bad.returncode, 1)
        self.assertEqual(json.loads(bad.stdout)["FAIL"], 1)
        self.assertEqual(run_script(VERIFY, str(tmp / "nope.md"), "--pages", str(tmp / "pages.json")).returncode, 2)


class SkillPackage(unittest.TestCase):
    def test_package_has_skill_and_scripts(self):
        import zipfile
        sys.path.insert(0, str(REPO / "claude-ai-skills"))
        import package
        self.assertEqual(package.check(REPO / "claude-ai-skills" / "paper-anatomy"), [])
        with zipfile.ZipFile(package.package("paper-anatomy")) as zf:
            names = set(zf.namelist())
        self.assertIn("paper-anatomy/SKILL.md", names)
        self.assertIn("paper-anatomy/scripts/verify_anchors.py", names)
        self.assertFalse([n for n in names if "__pycache__" in n or n.endswith(".pyc")])


class ExtractEndToEnd(TempDirTestCase):
    """Chạy thật trên một PDF dựng bằng PyMuPDF; bỏ qua khi máy không có PyMuPDF (vd Python 3.9 hệ thống)."""

    def setUp(self):
        super().setUp()
        self.mupdf = extract_paper._load_pymupdf()
        if self.mupdf is None:
            self.skipTest("không có PyMuPDF")

    def test_extract_find_pages_and_verify(self):
        doc = self.mupdf.open()
        bodies = ["1\nIntroduction\nWe separate instructions from data channels.",
                  "2\nMethod\nFigure 1: The secure front-end filters delimiters.",
                  "3\nResults\nTable 1: Attack success rate is 0.5 percent."]
        for i, body in enumerate(bodies):
            pg = doc.new_page()
            pg.insert_text((72, 72), body, fontsize=11)
            pg.insert_text((300, 800), str(10 + i), fontsize=9)
        pdf = self.tmp / "paper.pdf"
        doc.save(str(pdf))
        out = self.tmp / "work"
        res = run_script(EXTRACT, str(pdf), "--out", str(out))
        self.assertEqual(res.returncode, 0, res.stderr)
        cache = json.loads((out / "pages.json").read_text(encoding="utf-8"))
        self.assertEqual([p["label"] for p in cache["pages"]], ["10", "11", "12"])
        self.assertIn("2 Method", [s["title"] for s in cache["sections"]])
        self.assertTrue((out / "paper.txt").read_text(encoding="utf-8").startswith("===== PAGE 1/3 · tr.10"))
        found = run_script(EXTRACT, str(pdf), "--out", str(out), "--find", "secure front-end filters")
        self.assertIn("PDF   2 | tr.11", found.stdout)
        chunk = run_script(EXTRACT, str(pdf), "--out", str(out), "--pages", "3")
        self.assertIn("Attack success rate", chunk.stdout)
        self.assertNotIn("Introduction", chunk.stdout)
        analysis = self.tmp / "a.md"
        analysis.write_text('Bộ lọc 【§2 · tr.11 · Hình 1 · "filters delimiters"】, kết quả 【§3 · tr.12 · Bảng 1】\n',
                            encoding="utf-8")
        check = run_script(VERIFY, str(analysis), "--pages", str(out / "pages.json"))
        self.assertEqual(check.returncode, 0, check.stdout)


if __name__ == "__main__":
    unittest.main()
