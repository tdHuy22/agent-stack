"""Test cho skill trang-artifact: script kiểm trang Artifact trước khi đăng."""
from __future__ import annotations

import re
import subprocess
import sys
import unittest

from tests._util import PLUGIN, TempDirTestCase

SKILL = PLUGIN / "skills" / "trang-artifact"
sys.path.insert(0, str(SKILL / "scripts"))
import check_page  # noqa: E402

FOUNDATION = ("Hệ thống đọc từng file cấu hình rồi kiểm tên dịch vụ có khớp luật không. " * 10).strip()
EXAMPLE = "Tình huống: file deploy.yaml đổi tên dịch vụ cart thành prod-cart, luật cũ không còn khớp, 3 lỗi giả."


def option(oid, rec=False, violation=False):
    rec_attr = " data-khuyen" if rec else ""
    note = '<p data-vi-pham>Vi phạm luật chỉ dùng thư viện chuẩn: không khuyên.</p>' if violation else ""
    return f'<article data-phuong-an="{oid}"{rec_attr}><h3>{oid}</h3><p>Phương án {oid} làm việc X.</p>{note}</article>'


def verdict(oid, result="dat", text="Đạt: chỉ dùng html.parser của thư viện chuẩn."):
    return f'<td data-cho="{oid}" data-ket-qua="{result}">{text}</td>'


def page(*, title="Kiểm overlay", summary="Trang này giúp bạn chọn cách đọc overlay.", foundation=FOUNDATION,
         glossary="", examples=3, options=(), compare=None, constraints=None, pattern=True, questions=1,
         before_foundation=""):
    """Dựng một trang đạt chuẩn; tham số cho phép làm hỏng từng phần."""
    ids = [o[0] for o in options]
    if compare is None:
        compare = "".join(f"<tr><th>Ví dụ {i}</th>{''.join(f'<td data-cho={x}>kết quả</td>' for x in ids)}</tr>"
                          for i in range(1, 4))
    if constraints is None:
        constraints = ('<tr data-rang-buoc data-nguon="CLAUDE.md:28"><th>Chỉ thư viện chuẩn</th>'
                       + "".join(verdict(o[0], *(("vi-pham", "Vi phạm: cần cài gói ngoài bs4.") if o[2] else ()))
                                 for o in options) + "</tr>")
    main = "<main>" if options else '<main data-loai="giai-thich">'
    body = [f"<title>{title}</title>", main,
            f'<section data-phan="tom-tat"><p>{summary}</p></section>', before_foundation,
            f'<section data-phan="nen-tang"><p>{foundation}</p>{glossary}</section>']
    body += [f"<article data-vi-du><p>{EXAMPLE}</p></article>" for _ in range(examples)]
    if options:
        body.append("".join(option(oid, rec, bad) for oid, rec, bad in options))
        if len(options) >= 2 and compare != "":
            body.append(f'<section data-phan="vi-du-x-phuong-an"><table>{compare}</table></section>')
        if constraints != "":
            body.append(f'<section data-phan="rang-buoc"><table>{constraints}</table></section>')
        if pattern:
            body.append('<section data-phan="pattern-xau"><ul><li>Theo code cũ: không thấy tiền lệ sai luật.</li>'
                        "<li>Chiều người dùng: phương án của bạn qua cùng bảng.</li></ul></section>")
        body += ['<div data-cau-hoi><p>Câu 1: chọn cách đọc overlay nào, A hay B?</p></div>'] * questions
    body.append("</main>")
    return "\n".join(body)


def errors(html):
    return check_page.check(html).errors


class Structure(unittest.TestCase):
    def test_good_explainer_passes(self):
        r = check_page.check(page())
        self.assertEqual(r.errors, [])
        self.assertEqual(r.stats["ví dụ"], 3)

    def test_good_decision_page_passes(self):
        r = check_page.check(page(options=[("A", True, False), ("B", False, True)]))
        self.assertEqual(r.errors, [])
        self.assertEqual(r.stats["phương án"], 2)

    def test_missing_summary_title_and_foundation(self):
        html = page().replace('data-phan="tom-tat"', "").replace('data-phan="nen-tang"', "")
        html = re.sub(r"<title>.*?</title>", "", html)
        found = " ".join(errors(html))
        for part in ("[tiêu đề]", "[tóm tắt]", "[nền tảng]"):
            self.assertIn(part, found)

    def test_short_foundation_fails(self):
        self.assertTrue(any("600" in e for e in errors(page(foundation="Ngắn quá."))))

    def test_needs_three_examples(self):
        self.assertTrue(any("Mới có 2 ví dụ" in e for e in errors(page(examples=2))))

    def test_short_example_fails(self):
        html = page().replace(EXAMPLE, "Ví dụ ngắn.", 1)
        self.assertTrue(any("Ví dụ 1 chỉ" in e for e in errors(html)))

    def test_vague_example_is_only_a_note(self):
        vague = "Tình huống chung chung: người dùng làm một việc gì đó và hệ thống trả lời không như mong đợi lắm."
        r = check_page.check(page().replace(EXAMPLE, vague, 1))
        self.assertEqual(r.errors, [])
        self.assertTrue(any("Ví dụ 1 chưa có dữ liệu cụ thể" in n for n in r.notes))

    def test_option_before_foundation_fails(self):
        html = page(options=[("A", True, False)], before_foundation=option("Z"))
        self.assertTrue(any("đứng trước phần nền tảng" in e for e in errors(html)))


class PageKind(unittest.TestCase):
    def test_one_way_plan_without_option_card_fails(self):
        # Kế hoạch một hướng viết thành chữ trơn, không thẻ phương án: trước đây lọt qua mọi kiểm ràng buộc.
        html = page(summary="Kế hoạch: cài bs4 bằng pip install --user rồi parse HTML.").replace(
            ' data-loai="giai-thich"', "")
        self.assertTrue(any(e.startswith("[loại trang]") for e in errors(html)))

    def test_explainer_with_options_is_contradictory(self):
        html = page(options=[("A", True, False)]).replace("<main>", '<main data-loai="giai-thich">')
        self.assertTrue(any("bỏ một trong hai" in e for e in errors(html)))


class Placeholders(unittest.TestCase):
    def test_leftover_ellipsis_and_template_title_fail(self):
        html = page(title="Tên trang", options=[("A", True, False), ("B", False, False)]).replace(
            "<td data-cho=A>kết quả</td>", "<td data-cho=A>…</td>", 1).replace(
            "<p>Phương án B làm việc X.</p>", "<p>Mất: …</p>")
        found = [e for e in errors(html) if e.startswith("[chữ mẫu]")]
        self.assertEqual(len(found), 1)
        self.assertIn("Còn 3 chỗ", found[0])

    def test_ellipsis_inside_a_quote_is_fine(self):
        summary = 'Bạn viết "chỉnh sửa lại việc tạo artifact … đồng thời xem đề xuất".'
        self.assertEqual(errors(page(summary=summary)), [])

    def test_unfilled_template_is_rejected(self):
        found = " ".join(errors((SKILL / "mau.html").read_text(encoding="utf-8")))
        self.assertIn("[chữ mẫu]", found)


class Terms(unittest.TestCase):
    def test_real_lede_flags_codes_and_symbols(self):
        # Câu mở của trang "Cổng 0 USD D22" (19/10/2026): người đọc vấp ở D22 và ν.
        lede = "D22 thêm trục dung lượng ν: một giá trị U lấy qua query_hidden mang số bit hữu hạn."
        found = errors(page(summary=lede))
        self.assertTrue(any(e.startswith("[thuật ngữ] D22 chưa được định nghĩa") for e in found))
        self.assertTrue(any(e.startswith("[thuật ngữ] ν chưa được định nghĩa") for e in found))

    def test_defined_in_glossary_before_use_passes(self):
        glossary = '<div data-phan="thuat-ngu"><dl><dt>HC5</dt><dd>Luật cứng số 5.</dd></dl></div><p>HC5 chặn.</p>'
        self.assertEqual(errors(page(glossary=glossary)), [])

    def test_used_before_definition_fails(self):
        glossary = '<div data-phan="thuat-ngu"><dl><dt>HC5</dt><dd>Luật cứng số 5.</dd></dl></div>'
        found = errors(page(summary="Đổi HC5 thành chế độ duyệt.", glossary=glossary))
        self.assertTrue(any("HC5 dùng trước khi định nghĩa" in e for e in found))

    def test_dfn_defines_inline(self):
        summary = "<dfn>TM-28</dfn> là mối đe dọa số 28 trong threat model; TM-28 đã có chốt chặn."
        self.assertEqual(errors(page(summary=summary)), [])

    def test_dt_outside_glossary_does_not_define(self):
        self.assertTrue(errors(page(summary="<dl><dt>G1</dt><dd>nhóm 1</dd></dl>")))

    def test_code_filenames_and_common_acronyms_are_ignored(self):
        summary = "Sửa <code>HC5_MODE</code> trong PLAN.md, gọi API và đọc JSON trả về."
        self.assertEqual(errors(page(summary=summary)), [])

    def test_known_terms_exempt_acronyms_but_not_codes(self):
        summary = '<span data-tu-quen="SCEE, D22">SCEE và D22.</span>'
        found = errors(page(summary=summary))
        self.assertFalse(any(e.startswith("[thuật ngữ] SCEE") for e in found))
        self.assertTrue(any("không miễn được mã nội bộ hay ký hiệu: D22" in e for e in found))
        self.assertTrue(any("D22 chưa được định nghĩa" in e for e in found))

    def test_term_in_title_must_be_defined(self):
        self.assertTrue(any("ở tiêu đề" in e for e in errors(page(title="Cổng D22"))))

    def test_code_inside_glossary_term_still_defines(self):
        glossary = ('<div data-phan="thuat-ngu"><dl><dt><code>HC5</code></dt><dd>Luật cứng số 5.</dd></dl></div>'
                    "<p>Xem HC5.</p>")
        self.assertEqual(errors(page(glossary=glossary)), [])

    def test_hyphen_range_is_caught(self):
        self.assertTrue(any(e.startswith("[thuật ngữ] HC5") for e in errors(page(summary="Luật HC5-HC7 chặn."))))

    def test_common_codes_and_nfd_text(self):
        import unicodedata
        summary = unicodedata.normalize("NFD", "Mã hóa UTF-8, băm SHA-256, lưu S3, NGÀY nào cũng chạy.")
        self.assertEqual(errors(page(summary=summary)), [])

    def test_option_ids_are_not_jargon(self):
        html = page(options=[("A1", True, False), ("B1", False, False)])
        self.assertEqual(errors(html), [])


class Proposals(unittest.TestCase):
    def test_recommending_a_violation_fails(self):
        found = errors(page(options=[("A", True, True), ("B", False, False)]))
        # tên luật trong thông báo không được dính chữ của các ô phán quyết
        self.assertIn("[ràng buộc] Phương án A được khuyên nhưng vi phạm: Chỉ thư viện chuẩn. Không khuyên", found[0])

    def test_violation_must_show_on_card(self):
        html = page(options=[("A", True, False), ("B", False, True)]).replace(" data-vi-pham>", ">")
        self.assertTrue(any("Thẻ phương án B phải ghi rõ" in e for e in errors(html)))
        empty = page(options=[("A", True, False), ("B", False, True)]).replace(
            "Vi phạm luật chỉ dùng thư viện chuẩn: không khuyên.", "")
        self.assertTrue(any("Thẻ phương án B phải ghi rõ" in e for e in errors(empty)))
        on_card = page(options=[("A", True, False), ("B", False, True)]).replace(
            '<p data-vi-pham>', "<p>").replace('data-phuong-an="B"', 'data-phuong-an="B" data-vi-pham')
        self.assertEqual(errors(on_card), [])

    def test_constraint_needs_source(self):
        html = page(options=[("A", True, False)]).replace(' data-nguon="CLAUDE.md:28"', "")
        self.assertTrue(any("thiếu data-nguon" in e for e in errors(html)))

    def test_every_option_needs_a_verdict_per_row(self):
        rows = ('<tr data-rang-buoc data-nguon="CLAUDE.md:28"><th>Luật 1</th>' + verdict("A") + verdict("B") + "</tr>"
                '<tr data-rang-buoc data-nguon="CLAUDE.md:30"><th>Luật 2</th>' + verdict("A") + "</tr>")
        found = errors(page(options=[("A", True, False), ("B", False, False)], constraints=rows))
        self.assertTrue(any("cần đúng một ô data-cho=\"B\", đang có 0" in e for e in found))

    def test_bad_verdict_value_and_missing_reason(self):
        rows = ('<tr data-rang-buoc data-nguon="x:1"><th>Luật</th>' + verdict("A", "tot") + verdict("B", "can-duyet", "?")
                + "</tr>")
        found = errors(page(options=[("A", True, False), ("B", False, False)], constraints=rows))
        self.assertTrue(any("data-ket-qua phải là một trong" in e for e in found))
        self.assertTrue(any("ghi rõ vì sao cần duyệt" in e for e in found))

    def test_option_without_constraint_table_fails(self):
        found = errors(page(options=[("A", True, False)], constraints=""))
        self.assertTrue(any('thiếu phần data-phan="rang-buoc"' in e for e in found))

    def test_pattern_section_and_question_required(self):
        found = errors(page(options=[("A", True, False)], pattern=False, questions=0))
        self.assertTrue(any(e.startswith("[pattern xấu]") for e in found))
        self.assertTrue(any(e.startswith("[câu chốt]") for e in found))

    def test_two_options_need_examples_through_each(self):
        found = errors(page(options=[("A", True, False), ("B", False, False)], compare=""))
        self.assertTrue(any("vi-du-x-phuong-an" in e for e in found))
        partial = "<tr><th>Ví dụ 1</th><td data-cho=A>kết quả</td></tr>"
        found = errors(page(options=[("A", True, False), ("B", False, False)], compare=partial))
        self.assertTrue(any("chưa có ô data-cho cho: B" in e for e in found))
        one_row = "<tr><th>Ví dụ 1</th><td data-cho=A>kết quả</td><td data-cho=B>kết quả</td></tr>"
        r = check_page.check(page(options=[("A", True, False), ("B", False, False)], compare=one_row))
        self.assertEqual(r.errors, [])
        self.assertTrue(any("mới chạy qua dưới 3 ví dụ" in n for n in r.notes))

    def test_separate_tables_per_question(self):
        rows1 = '<tr data-rang-buoc data-nguon="a:1"><th>L</th>' + verdict("1A") + verdict("1B") + "</tr>"
        rows2 = '<tr data-rang-buoc data-nguon="a:2"><th>M</th>' + verdict("2A") + verdict("2B") + "</tr>"
        opts = [("1A", True, False), ("1B", False, False), ("2A", True, False), ("2B", False, False)]
        html = page(options=opts, constraints=rows1).replace(
            "</table></section>\n<section data-phan=\"pattern-xau\"",
            f'</table></section>\n<section data-phan="rang-buoc"><table>{rows2}</table></section>\n'
            '<section data-phan="pattern-xau"', 1)
        self.assertEqual(errors(html), [])
        self.assertTrue(any("Phương án 2A chưa được đối chiếu" in e for e in errors(page(options=opts, constraints=rows1))))

    def test_no_recommendation_is_a_note(self):
        r = check_page.check(page(options=[("A", False, False), ("B", False, False)]))
        self.assertEqual(r.errors, [])
        self.assertTrue(any("data-khuyen" in n for n in r.notes))


class Template(unittest.TestCase):
    def test_template_has_every_marker_the_checker_reads(self):
        mau = (SKILL / "mau.html").read_text(encoding="utf-8")
        for marker in ('data-phan="tom-tat"', 'data-phan="nen-tang"', 'data-phan="thuat-ngu"', "data-vi-du",
                       "data-phuong-an=", "data-khuyen", 'data-phan="vi-du-x-phuong-an"', 'data-phan="rang-buoc"',
                       "data-rang-buoc", "data-nguon=", "data-cho=", "data-ket-qua=", "data-vi-pham",
                       'data-phan="pattern-xau"', "data-cau-hoi", "<title>",
                       '<meta name="claude:viewport-fit-sides" content="cover">'):
            with self.subTest(marker=marker):
                self.assertIn(marker, mau)
        self.assertEqual(mau.count("data-vi-du"), check_page.MIN_EXAMPLES)

    def test_skill_documents_every_verdict(self):
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        for value in check_page.VERDICTS:
            self.assertIn(f"`{value}`", text)


class Cli(TempDirTestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SKILL / "scripts" / "check_page.py"), *args],
                              capture_output=True, text=True)

    def test_exit_codes(self):
        good = self.write("dat.html", page())
        bad = self.write("hong.html", page(examples=1))
        out = self.run_cli(str(good))
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertIn("Đạt", out.stdout)
        out = self.run_cli(str(bad))
        self.assertEqual(out.returncode, 1)
        self.assertIn("LỖI", out.stdout)
        self.assertEqual(self.run_cli(str(self.tmp / "khong-co.html")).returncode, 2)


if __name__ == "__main__":
    unittest.main()
