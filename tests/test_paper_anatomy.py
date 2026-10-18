"""Script của skill paper-anatomy: dò nhãn trang in, tiêu đề mục, chỉ mục hình/bảng, và kiểm thẻ neo."""
import contextlib
import importlib.util
import io
import json
import os
import re
import sys
import unicodedata
import unittest
from argparse import Namespace
from unittest import mock

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


class MisplacedAnchors(unittest.TestCase):
    """Neo sai chỗ: nội dung đúng nhưng trỏ sai bảng hay trang. Chỉ cảnh báo, không làm hỏng mã thoát."""

    CACHE = {**CACHE,
             "pages": [p if p["index"] != 3 else page(3, "103", p["text"] + "We use 1,000 samples and 250 queries (2024).\n")
                       for p in CACHE["pages"]],
             "objects": [{"kind": "Figure", "id": "2", "page": 2, "caption": "Overview"},
                         {"kind": "Table", "id": "3", "page": 3, "caption": "Attack success rate"}]}

    def row(self, text):
        result = verify_anchors.run(text, self.CACHE)
        self.assertEqual(result["FAIL"], 0, result["rows"])
        return result["rows"][-1]

    def test_object_anchored_where_it_is_only_mentioned(self):
        row = self.row("Bộ lọc bỏ dấu phân cách 【§4 · tr.103 · Hình 2】.\n")
        self.assertEqual(row["status"], "WARN")
        self.assertIn("Hình 2 in ở trang PDF 2", " ".join(row["reasons"]))
        self.assertEqual(self.row("Tổng quan front-end 【§3.1 · tr.102 · Hình 2】.\n")["status"], "OK")

    def test_claim_names_a_table_the_anchor_does_not_point_to(self):
        row = self.row("Theo Bảng 3, tấn công gần như hết tác dụng 【§1 · tr.101】.\n")
        self.assertIn("câu nhắc Bảng 3", " ".join(row["reasons"]))
        # Thẻ đã ghi một hình: câu nhắc thêm Bảng 3 là để so, không cảnh báo về Bảng 3.
        row = self.row("Hình 2 khớp với Bảng 3 【§3.1 · tr.102 · Hình 2】.\n")
        self.assertEqual(row["status"], "OK", row["reasons"])

    def test_number_not_on_anchored_page(self):
        row = self.row("Tỉ lệ tấn công thành công còn 1,2% 【§1 · tr.101】.\n")
        self.assertEqual(row["status"], "WARN")
        self.assertIn("số 1,2% không có trên trang đã ghi; có ở trang PDF 3", " ".join(row["reasons"]))
        self.assertEqual(self.row("Tỉ lệ còn 1,2% trên Llama 【§4 · tr.103 · Bảng 3】.\n")["status"], "OK")

    def test_numbers_that_are_checked(self):
        cases = {"Thước đo ASR 1,2 trên Llama 【§1 · tr.101】.\n": "số 1,2",      # chữ hoa trước số không phải tên mô hình
                 "Chuỗi 1.000 mẫu 【§1 · tr.101】.\n": "số 1.000",                  # dấu phân cách hàng nghìn
                 "Có 250 truy vấn 【§1 · tr.101】.\n": "số 250"}                    # số nguyên từ 100 trở lên
        for text, why in cases.items():
            with self.subTest(text=text):
                row = self.row(text)
                self.assertEqual(row["status"], "WARN")
                self.assertIn(why, " ".join(row["reasons"]))
        self.assertEqual(self.row("Dùng 1.000 mẫu 【§4 · tr.103 · Bảng 3】.\n")["status"], "OK")

    def test_numbers_that_are_not_checked(self):
        for text in ("Mô hình Claude 3.1 được thử 【§1 · tr.101】.\n",       # số phiên bản trong tên mô hình
                     "Tự tính: tăng ≈ 1,2 lần 【§1 · tr.101】.\n",           # người phân tích tự tính
                     "[minh họa] Tự tính: còn 1,2% 【§1 · tr.101】.\n",
                     "Bài năm 2024, mục §3.1 【§1 · tr.101】.\n",             # năm (có ở trang 3), số mục
                     "Dùng 3 lớp 【§1 · tr.101】.\n",                          # số nguyên nhỏ
                     "Chi tiết, xem Bảng 3 【§1 · tr.101】.\n",               # câu chỉ đường, không lấy số từ bảng
                     "Còn 1,2% 【§4 · tr.104】.\n",                            # trang scan
                     "Đúng là 1,2%. Câu sau không có số 【§1 · tr.101】.\n"):  # số ở câu trước
            with self.subTest(text=text):
                self.assertEqual(self.row(text)["status"], "OK", self.row(text)["reasons"])

    def test_warnings_do_not_change_exit_code(self):
        tmp = REPO / ".tmp" / "test-paper-anatomy"
        tmp.mkdir(parents=True, exist_ok=True)
        (tmp / "pages-objects.json").write_text(json.dumps(self.CACHE), encoding="utf-8")
        (tmp / "misplaced.md").write_text("## 0. A\n## 2. B\nCòn 1,2% 【§1 · tr.101】 và 【§4 · tr.103 · Hình 2】\n",
                                         encoding="utf-8")
        out = run_script(VERIFY, str(tmp / "misplaced.md"), "--pages", str(tmp / "pages-objects.json"))
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("số 1,2% không có trên trang đã ghi", out.stdout)
        self.assertIn("Hình 2 in ở trang PDF 2", out.stdout)
        self.assertIn("Số mục nhảy (0, 2)", out.stdout)

    def test_section_numbering(self):
        self.assertEqual(verify_anchors.section_numbering("## 0. A\n## 1. B\n## Tự kiểm hiểu\n## 2. C\n"),
                         (["0", "1", "2"], None))
        self.assertEqual(verify_anchors.section_numbering("## 0. A\n## 1. B\n## 3. C\n")[1], "nhảy")
        self.assertEqual(verify_anchors.section_numbering("## 0. A\n## A. B\n## 1. C\n")[1], "chữ cái")
        self.assertEqual(verify_anchors.section_numbering("## Tóm lại\n## Vì sao\n"), ([], None))
        self.assertEqual(verify_anchors.section_numbering("## 3.1 Foo\n## 3.2 Bar\n"), ([], None))   # số phân cấp
        self.assertEqual(verify_anchors.section_numbering("## 1 A\n## **2.** B\n## 3: C\n"), (["1", "2", "3"], None))
        self.assertEqual(verify_anchors.section_numbering("## 1. A\n```\n## 7. mẫu\n```\n## 2. B\n")[1], None)
        self.assertEqual(verify_anchors.section_numbering("## 9. A\n## 10. B\n")[1], None)
        self.assertEqual(verify_anchors.section_numbering("## 1 A\n## 3 B\n")[1], "nhảy")
        out = verify_anchors.render(verify_anchors.run("## 0. A\n## 2. B\nÝ 【§1 · tr.101】\n", CACHE))
        self.assertIn("Số mục nhảy (0, 2)", out)


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


class QuickReadSection(TempDirTestCase):
    """Mục 0 "Đọc trong 1 phút": đếm từ không tính neo, báo chữ tuyệt đối, dừng ở mục kế tiếp."""

    TEXT = ("# Giải phẫu: Bài thử\n> Đã đọc: cả bài.\n\n## 0. Đọc trong 1 phút\n"
            "- **Một câu:** Mọi tấn công thủ công bị chặn 【§4 · tr.103 · Bảng 3 · mọi lúc】.\n"
            "- **Giả định:** Chỉ vững với tấn công tĩnh; bài chỉ ra giới hạn ở chỉ thị lồng nhau, chỉnh sửa luồng,\n"
            "  chỉ số và chỉ định thìmọi.\n"
            "### Ghi chú trong mục 0\n"
            "- **Bối cảnh:** so với BIPIA, luôn tốt hơn, chỉ cần một lần huấn luyện.\n"
            "\n## 1. Cốt lõi\nMục này nói mọi thứ, không tính vào mục 0.\n")
    FOUND = [("Mọi", 5), ("Chỉ", 6), ("luôn", 9), ("chỉ", 9)]

    def body_words(self, text):
        body = text.split("Đọc trong 1 phút\n")[1].split("## 1.")[0]
        plain = re.sub(r"【[^】]*】", " ", body)
        return [w for w in plain.split() if any(c.isalnum() for c in w)]

    def found(self, quick):
        return [(a["word"], a["line"]) for a in quick["absolutes"]]

    def test_counts_words_without_anchors_and_finds_absolutes(self):
        quick = verify_anchors.quick_read(self.TEXT)
        self.assertEqual(quick["words"], len(self.body_words(self.TEXT)))
        self.assertLess(quick["words"], len(self.body_words(self.TEXT.replace("【", "").replace("】", ""))))
        # Hoa đầu câu vẫn bắt; "mọi" trong neo, "chỉ ra", "chỉ thị", "chỉnh", "luồng" không bắt;
        # tiêu đề ### trong mục 0 không cắt mục; "## 1." thì cắt.
        self.assertEqual(self.found(quick), self.FOUND)

    def test_heading_variants_and_nfd_text(self):
        for head in ("### 0. Đọc trong 1 phút", "## **0. Đọc trong 1 phút**", "## 0) Đọc  trong 1 phút",
                     "## 0. ĐỌC TRONG 1 PHÚT (bản rút gọn)"):
            text = self.TEXT.replace("## 0. Đọc trong 1 phút", head)
            self.assertIsNotNone(verify_anchors.quick_read(text), head)
        nfd = verify_anchors.quick_read(unicodedata.normalize("NFD", self.TEXT))
        self.assertEqual(self.found(nfd), self.FOUND)
        self.assertEqual(nfd["words"], verify_anchors.quick_read(self.TEXT)["words"])

    def test_no_section_zero_in_narrow_mode(self):
        self.assertIsNone(verify_anchors.quick_read("# Định lý 1 nói gì\nChỉ cần đọc §3.\n"))

    def test_render_reports_length_and_warnings_do_not_fail(self):
        short = verify_anchors.render(verify_anchors.run(self.TEXT, CACHE))
        self.assertRegex(short, r"Mục 0: \d+ từ .*: đạt")
        self.assertIn("'Mọi' dòng 5", short)
        long_text = self.TEXT.replace("so với BIPIA", "so với BIPIA " + "rất " * 210)
        self.assertIn("cắt chữ", verify_anchors.render(verify_anchors.run(long_text, CACHE)))
        analysis, pages = self.tmp / "a.md", self.tmp / "pages.json"
        analysis.write_text(long_text.replace(" · mọi lúc", ""), encoding="utf-8")
        pages.write_text(json.dumps(CACHE), encoding="utf-8")
        res = run_script(VERIFY, str(analysis), "--pages", str(pages))
        self.assertEqual(res.returncode, 0, res.stdout)  # cảnh báo mục 0 không làm thoát mã 1
        self.assertIn("cắt chữ", res.stdout)


BENCH_DIR = REPO / "claude-ai-skills" / "paper-anatomy-bench"


def load_bench(name):
    """Nạp một script của bench theo đường dẫn (thư mục bench không phải package)."""
    spec = importlib.util.spec_from_file_location(f"bench_{name}", BENCH_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def quiet(fn, *args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = fn(*args)
    return code, buf.getvalue()


class BlindGrading(TempDirTestCase):
    """blind.py: đề chấm không lộ nhánh, bảng giải mã nằm ngoài thư mục người chấm đọc, tổng hợp giải mã đúng."""

    def setUp(self):
        super().setUp()
        self.blind = load_bench("blind")
        self.blind.BENCH = self.tmp / "bench"
        self.blind.MAPPINGS = self.tmp / "mappings"
        self.blind.load_evals = lambda: [{"name": "toy", "prompt": "Giải phẫu bài toy.pdf",
                                          "grader_note": "Ảnh trang ở `{papers}/toy/img/`."}]
        for arm in ("v3", "new"):
            run = self.blind.BENCH / "iteration-9" / "toy" / arm / "run-0"
            (run / "outputs").mkdir(parents=True)
            (run / "outputs" / "answer.md").write_text(f"BÀI LÀM {arm.upper()}", encoding="utf-8")
            (run / "timing.json").write_text(json.dumps({"is_error": False}), encoding="utf-8")
        old = self.blind.BENCH / "blind-1" / "toy"
        old.mkdir(parents=True)
        (old / "grading.json").write_text(json.dumps({"key_facts": [{"id": 1, "fact": "Ý cũ", "where": "tr.2"}]}),
                                          encoding="utf-8")
        self.round_dir = self.blind.BENCH / "blind-2" / "toy"

    def prepare(self, seed="1"):
        return quiet(self.blind.main, ["prepare", "--iteration", "9", "--round", "2", "--arms", "v3,new", "--seed", seed])

    def test_prepare_hides_arms_and_summary_decodes(self):
        self.assertEqual(self.prepare()[0], 0)
        mapping = json.loads((self.blind.MAPPINGS / "toy-2.json").read_text(encoding="utf-8"))
        self.assertEqual(sorted(mapping.values()), ["new", "v3"])
        self.assertEqual(sorted(p.name for p in self.round_dir.iterdir()), ["A.md", "B.md", "prompt.md"])
        for label, arm in mapping.items():
            self.assertEqual((self.round_dir / f"{label}.md").read_text(encoding="utf-8"), f"BÀI LÀM {arm.upper()}")
        prompt = (self.round_dir / "prompt.md").read_text(encoding="utf-8")
        self.assertIn("Ý cũ (tr.2)", prompt)
        self.assertIn(str(self.blind.BENCH / "papers" / "toy" / "img"), prompt)
        self.assertIn(str(self.round_dir / "grading.json"), prompt)
        self.assertNotIn("iteration-9", prompt)
        self.assertIn("nam_y_1_phut", prompt)

        win = "A" if mapping["A"] == "new" else "B"
        lose = "B" if win == "A" else "A"
        grading = {"answers": {
            win: {"scores": {k: 5 for k in self.blind.SCORES}, "facts": [{"status": "đủ"}],
                  "spot_checks": [{"verdict": "đúng"}]},
            lose: {"scores": {k: 3 for k in self.blind.SCORES}, "facts": [{"status": "thiếu"}],
                   "spot_checks": [{"verdict": "sai"}]}},
            "preference": win, "margin": "ro", "reason": "dòng một\n  dòng hai"}
        (self.round_dir / "grading.json").write_text(json.dumps(grading), encoding="utf-8")
        code, out = quiet(self.blind.main, ["summary", "--round", "2"])
        self.assertEqual(code, 0)
        self.assertIn("| toy | new | ro | dòng một dòng hai |", out)
        self.assertIn("| new | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | 5.0 | 100% | 100% |", out)
        self.assertIn("| v3 | 3.0 | 3.0 | 3.0 | 3.0 | 3.0 | 3.0 | 0% | 0% |", out)
        self.assertIn("Thắng: new 1/1", out)

        # Vòng đã có kết quả chấm thì không dựng lại: seed khác cũng không được xáo lại A/B hay chép đè bài làm.
        (self.round_dir / "A.md").write_text("ĐÃ CHẤM", encoding="utf-8")
        for seed in ("2", "3", "4", "5"):
            self.prepare(seed)
            self.assertEqual(json.loads((self.blind.MAPPINGS / "toy-2.json").read_text(encoding="utf-8")), mapping)
            self.assertEqual((self.round_dir / "A.md").read_text(encoding="utf-8"), "ĐÃ CHẤM")

    def test_task_missing_an_arm_is_skipped(self):
        (self.blind.BENCH / "iteration-9" / "toy" / "new" / "run-0" / "outputs" / "answer.md").unlink()
        code, out = self.prepare()
        self.assertEqual(code, 0)
        self.assertIn("thiếu bài làm", out)
        self.assertFalse(self.round_dir.exists())

    def test_failed_run_is_not_sent_to_grader(self):
        """Lượt lỗi để lại answer.md là thông báo lỗi; không được thành "câu trả lời" cho người chấm."""
        run = self.blind.BENCH / "iteration-9" / "toy" / "new" / "run-0"
        (run / "outputs" / "answer.md").write_text("Failed to authenticate", encoding="utf-8")
        for bad in ({"is_error": True}, {}, "hỏng{"):
            (run / "timing.json").write_text(bad if isinstance(bad, str) else json.dumps(bad), encoding="utf-8")
            code, out = self.prepare()
            self.assertIn("thiếu bài làm", out)
            self.assertFalse(self.round_dir.exists())

    def test_summary_without_gradings_fails(self):
        self.assertEqual(quiet(self.blind.main, ["summary", "--round", "7"])[0], 1)

    def test_rep_uses_its_own_run_and_summary_merges_rounds(self):
        for arm in ("v3", "new"):
            run = self.blind.BENCH / "iteration-9" / "toy" / arm / "run-1"
            (run / "outputs").mkdir(parents=True)
            (run / "outputs" / "answer.md").write_text(f"LƯỢT 2 {arm.upper()}", encoding="utf-8")
            (run / "timing.json").write_text(json.dumps({"is_error": False}), encoding="utf-8")
        for rnd, rep in (("2", "0"), ("3", "1")):
            quiet(self.blind.main, ["prepare", "--iteration", "9", "--round", rnd, "--rep", rep, "--arms", "v3,new"])
        texts = {(self.blind.BENCH / "blind-3" / "toy" / f"{x}.md").read_text(encoding="utf-8") for x in "AB"}
        self.assertEqual(texts, {"LƯỢT 2 V3", "LƯỢT 2 NEW"})
        for rnd in ("2", "3"):
            mapping = json.loads((self.blind.MAPPINGS / f"toy-{rnd}.json").read_text(encoding="utf-8"))
            win = "A" if mapping["A"] == "new" else "B"
            other = "B" if win == "A" else "A"
            g = {"answers": {win: {"scores": {"de_doc": 5}}, other: {"scores": {"de_doc": 3}}},
                 "preference": win, "margin": "it", "reason": "x"}
            (self.blind.BENCH / f"blind-{rnd}" / "toy" / "grading.json").write_text(json.dumps(g), encoding="utf-8")
        code, out = quiet(self.blind.main, ["summary", "--round", "2", "3"])
        self.assertEqual(code, 0)
        self.assertIn("| toy (vòng 2) | new |", out)
        self.assertIn("| toy (vòng 3) | new |", out)
        self.assertIn("Thắng: new 2/2", out)


class BenchRunnerGuards(TempDirTestCase):
    """run_bench.py: dừng khi CLI chưa đăng nhập; chạy lại lượt lỗi, bỏ qua lượt đã xong."""

    def setUp(self):
        super().setUp()
        self.bench = load_bench("run_bench")

    def fake_claude(self, body):
        exe = self.tmp / "claude"
        exe.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
        exe.chmod(0o755)
        return mock.patch.dict(os.environ, {"AGENT_STACK_CLAUDE_BIN": str(exe)})

    def test_cli_logged_in(self):
        with self.fake_claude("""echo '{"loggedIn": false}'"""):
            self.assertIs(self.bench.cli_logged_in(), False)
        with self.fake_claude("""echo '{"loggedIn": true}'"""):
            self.assertIs(self.bench.cli_logged_in(), True)
        with self.fake_claude("echo khong-phai-json"):
            self.assertIsNone(self.bench.cli_logged_in())
        with mock.patch.dict(os.environ, {"AGENT_STACK_CLAUDE_BIN": str(self.tmp / "khong-co")}):
            self.assertIsNone(self.bench.cli_logged_in())

    def test_finished_only_for_clean_timing(self):
        timing = self.tmp / "timing.json"
        self.assertFalse(self.bench.finished(timing))  # chưa có
        for text, expected in (('{"is_error": false}', True), ('{"is_error": true}', False), ("{}", False),
                               ("[]", False), ('{"is_err', False), ("", False)):
            timing.write_text(text, encoding="utf-8")
            self.assertIs(self.bench.finished(timing), expected, text)

    def test_failed_run_makes_exit_code_1(self):
        pdf = self.tmp / "toy.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        self.bench.BENCH = self.tmp / "bench"
        self.bench.load_evals = lambda selected: [{"id": 1, "name": "toy", "difficulty": "dễ", "tests": "thử",
                                                   "pdf": str(pdf), "file": "toy.pdf", "prompt": "Đọc bài."}]
        script = """if [ "$1" = auth ]; then echo '{"loggedIn": true}'; exit 0; fi
echo '{"type":"result","result":"Lỗi giả","total_cost_usd":0,"num_turns":1,"is_error":true}'"""
        with self.fake_claude(script):
            code, out = quiet(self.bench.main, ["--iteration", "1", "--arms", "new", "--yes", "--parallel", "1"])
        self.assertEqual(code, 1, out)
        self.assertIn("1 lượt lỗi", out)

    def test_logged_out_stops_before_any_run(self):
        pdf = self.tmp / "toy.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        self.bench.BENCH = self.tmp / "bench"
        self.bench.load_evals = lambda selected: [{"id": 1, "name": "toy", "difficulty": "dễ", "tests": "thử",
                                                   "pdf": str(pdf), "file": "toy.pdf", "prompt": "Đọc bài."}]
        with self.fake_claude("""echo '{"loggedIn": false}'"""):
            code, out = quiet(self.bench.main, ["--iteration", "1", "--arms", "new", "--yes"])
        self.assertEqual(code, 2)
        self.assertIn("chưa đăng nhập", out)
        self.assertFalse((self.bench.BENCH / "iteration-1").exists())

    def test_failed_run_is_rerun_and_finished_run_is_skipped(self):
        pdf = self.tmp / "toy.pdf"
        pdf.write_bytes(b"%PDF-1.4\n")
        ev = {"name": "toy", "pdf": str(pdf), "file": "toy.pdf", "prompt": "Đọc bài."}
        args = Namespace(force=False, model="sonnet", effort="low", cap_usd=0.1, timeout=60, keep=False)
        out_root, work_root = self.tmp / "out", self.tmp / "work"
        run_dir = out_root / "toy" / "new" / "run-0"
        run_dir.mkdir(parents=True)
        (run_dir / "timing.json").write_text(json.dumps({"is_error": True}), encoding="utf-8")
        result = """echo '{"type":"result","result":"xong","total_cost_usd":0.01,"num_turns":2,"is_error":false}'"""
        with self.fake_claude(result):
            row = self.bench.run_one(ev, "new", 0, args, work_root, self.tmp, out_root)
            self.assertNotIn("skipped", row)
            self.assertFalse(row["is_error"])
            self.assertEqual((run_dir / "outputs" / "answer.md").read_text(encoding="utf-8"), "xong")
            self.assertTrue(self.bench.run_one(ev, "new", 0, args, work_root, self.tmp, out_root).get("skipped"))


if __name__ == "__main__":
    unittest.main()
