#!/usr/bin/env python3
"""Kiểm tĩnh một trang Artifact (HTML) trước khi đăng, theo khuôn của skill trang-artifact.

  python3 check_page.py <trang.html>

Kiểm phần có đếm hay so được: có tóm tắt và phần nền tảng đủ dài, ít nhất 3 ví dụ cụ thể, mã nội bộ
(HC5, D22, GĐ24, ν…) được định nghĩa trước lần dùng đầu, mỗi phương án có phán quyết với từng ràng buộc
kèm nguồn, phương án được khuyên không vi phạm ràng buộc nào. Không chấm được trang có dễ hiểu thật không:
bước đọc thử bằng người lạ trong SKILL.md lo phần đó.

Thoát 0 khi đạt (có thể kèm NHẮC), 1 khi có LỖI, 2 khi không đọc được file.
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

MIN_EXAMPLES = 3
MIN_EXAMPLE_CHARS = 80
MIN_FOUNDATION_CHARS = 600
MIN_PATTERN_CHARS = 80
MIN_QUESTION_CHARS = 20
MIN_REASON_CHARS = 15  # ô "vi phạm" hay "cần duyệt" phải nói vì sao
MAX_SUMMARY_WORDS = 150
MAX_LISTED = 20
EXPLAINER = "giai-thich"  # data-loai của trang chỉ giải thích hay báo cáo, không có đề xuất

VERDICTS = {"dat": "đạt", "vi-pham": "vi phạm", "can-duyet": "cần duyệt", "khong-lien-quan": "không liên quan"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
SKIP = {"style", "script", "template"}
CODE = {"code", "pre", "kbd", "samp"}  # tên trong code không phải thuật ngữ cần định nghĩa
CONCRETE = CODE | {"table", "q", "blockquote", "figure", "img", "svg"}
# Thẻ mà chữ bên trong chỉ còn "…" (hay "Nhãn: …") là chữ mẫu của khuôn chưa thay.
TEXT_TAGS = {"p", "li", "dd", "dt", "td", "th", "h1", "h2", "h3", "h4", "b", "strong", "span", "code", "pre",
             "figcaption", "div"}
PLACEHOLDER_RE = re.compile(r"(?:[^…:]{0,40}:\s*)?…[\s…,.:;]*")
TEMPLATE_TEXTS = ("Tên trang", "Câu hỏi của trang, viết bằng lời thường", "Tên project · ngày",
                  "Một câu lời thường: phương án này làm gì.", "A[…] --> B[…]")

# Mã nội bộ có số (HC5, D22, GĐ24, TM-28): luôn phải định nghĩa, không miễn được.
CODE_RE = re.compile(r"(?<![\w-])[A-ZĐ]{1,5}-?\d+(?:\.\d+)*[a-z]?(?![\w-])")
# Dải mã nối bằng gạch ngang (HC5-HC7): CODE_RE bỏ qua vì gạch ngang dính hai bên.
RANGE_RE = re.compile(r"(?<![\w-])([A-ZĐ]{1,5}\d+)-([A-ZĐ]{1,5}\d+)(?![\w-])")
# Chữ viết tắt chỉ có chữ hoa ASCII (SCEE, MCP); bỏ tên file như PLAN.md.
ACRONYM_RE = re.compile(r"(?<![\w-])[A-Z]{2,7}(?![\w-]|\.[a-z])")
# Một chữ Hy Lạp đứng riêng (ν, λ) dùng như ký hiệu.
GREEK_RE = re.compile(r"(?<![\w-])[α-ωΑ-Ω](?![\w-])")
COMMON = {
    "AI", "API", "AWS", "BSD", "CD", "CI", "CLI", "CPU", "CSS", "CSV", "DNS", "FAQ", "GB", "GPL", "GPU", "HTML",
    "HTTP", "HTTPS", "ID", "IDE", "IP", "JS", "JSON", "KB", "LAN", "LLM", "MB", "MIT", "OK", "OS", "PDF", "PNG",
    "PR", "RAM", "SDK", "SQL", "SSD", "SSH", "SVG", "TB", "TLS", "TODO", "UI", "URL", "USB", "USD", "UTC", "UX",
    "VND", "VPN", "XML", "YAML", "DB", "VM", "JWT", "README", "HTTP2", "SSO",
}
# Mã có số mà ai làm nghề cũng biết: không cần định nghĩa.
COMMON_CODES = {"UTF-8", "UTF-16", "SHA-1", "SHA-256", "SHA-512", "MD5", "S3", "EC2", "MP3", "MP4", "ES6"}


def terms_in(text: str) -> list[tuple[int, str]]:
    found = []
    for rx in (CODE_RE, ACRONYM_RE, GREEK_RE):
        found += [(m.start(), m.group()) for m in rx.finditer(text)]
    for m in RANGE_RE.finditer(text):
        found += [(m.start(1), m.group(1)), (m.start(2), m.group(2))]
    for code in COMMON_CODES:  # "UTF-8" bị CODE_RE bắt thành "UTF-8"; bỏ ở đây
        found = [(at, term) for at, term in found if term != code]
    return sorted(found)


def needs_definition(term: str) -> bool:
    return bool(CODE_RE.fullmatch(term) or GREEK_RE.fullmatch(term))


@dataclass
class Node:
    tag: str
    attrs: dict
    start: int  # vị trí trong chữ hiển thị lúc mở thẻ
    text: list = field(default_factory=list)
    concrete: bool = False
    marks: list = field(default_factory=list)  # các Node con có thuộc tính data-* đáng kể

    def plain(self) -> str:
        return " ".join("".join(self.text).split())


class PageParser(HTMLParser):
    """Gom chữ hiển thị, vị trí của nó, và các phần có đánh dấu data-* của khuôn."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[Node] = []
        self.pos = 0
        self.title = ""
        self.uses: list[tuple[int, str, str]] = []  # (vị trí, thuật ngữ, đoạn chữ quanh nó)
        self.definitions: dict[str, int] = {}
        self.known: set[str] = set()
        self.kinds: set[str] = set()  # giá trị data-loai
        self.placeholders: list[str] = []
        self.marked: list[Node] = []  # mọi phần tử có data-* của khuôn, theo thứ tự mở

    def in_tag(self, names) -> bool:
        return any(n.tag in names for n in self.stack)

    def in_part(self, name: str) -> bool:
        return any(n.attrs.get("data-phan") == name for n in self.stack)

    def handle_starttag(self, tag, attrs):
        attrs = {k: (v or "") for k, v in attrs}
        node = Node(tag, attrs, self.pos)
        for value in re.split(r"[,\s]+", attrs.get("data-tu-quen", "")):
            if value:
                self.known.add(value)
        if attrs.get("data-loai"):
            self.kinds.add(attrs["data-loai"].strip())
        if tag in CONCRETE:
            for n in self.stack:
                n.concrete = True
        if any(k in attrs for k in ("data-phan", "data-vi-du", "data-phuong-an", "data-cau-hoi", "data-rang-buoc",
                                    "data-cho", "data-vi-pham")):
            self.marked.append(node)
            for n in self.stack:
                n.marks.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.stack and self.stack[-1].tag == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i].tag == tag:
                for node in self.stack[i:]:
                    self.check_placeholder(node)
                del self.stack[i:]
                return

    def check_placeholder(self, node: Node):
        if node.tag not in TEXT_TAGS:
            return
        text = node.plain()
        if PLACEHOLDER_RE.fullmatch(text) or text in TEMPLATE_TEXTS:
            self.placeholders.append(text)

    def handle_data(self, data):
        if self.in_tag(SKIP):
            return
        if self.in_tag({"title"}):
            self.title += data
            return
        for n in self.stack:
            n.text.append(data)
        defining = self.in_tag({"dfn"}) or (self.in_tag({"dt"}) and self.in_part("thuat-ngu"))
        in_code = self.in_tag(CODE)
        for offset, term in terms_in(data):
            at = self.pos + offset
            if defining:  # kể cả <dt><code>HC5</code></dt>
                self.definitions.setdefault(term, at)
            if not in_code:
                around = " ".join(data[max(0, offset - 30):offset + len(term) + 30].split())
                self.uses.append((at, term, around))
        self.pos += len(data)


@dataclass
class Report:
    errors: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def error(self, where: str, msg: str):
        self.errors.append(f"[{where}] {msg}")

    def note(self, where: str, msg: str):
        self.notes.append(f"[{where}] {msg}")


def row_label(row: Node, cells: list) -> str:
    """Tên hàng ràng buộc: chữ của hàng trừ chữ trong các ô phán quyết."""
    text = "".join(row.text)
    for cell in cells:
        text = text.replace("".join(cell.text), " ", 1)
    return " ".join(text.split())[:60] or "(hàng trống)"


def check(html: str) -> Report:
    p = PageParser()
    p.feed(unicodedata.normalize("NFC", html))  # chữ dấu tổ hợp (NFD) làm regex tách sai từ
    p.close()
    r = Report()
    parts: dict[str, list[Node]] = {}
    for n in p.marked:
        if "data-phan" in n.attrs:
            parts.setdefault(n.attrs["data-phan"], []).append(n)
    examples = [n for n in p.marked if "data-vi-du" in n.attrs]
    options = [n for n in p.marked if "data-phuong-an" in n.attrs]
    questions = [n for n in p.marked if "data-cau-hoi" in n.attrs]

    if not p.title.strip():
        r.error("tiêu đề", "Thiếu <title>: tên ngắn 2–4 chữ, không kèm giải thích.")
    elif " ".join(p.title.split()) in TEMPLATE_TEXTS:
        p.placeholders.append(p.title.strip())
    if p.placeholders:
        sample = "; ".join(f"“{s[:40]}”" for s in p.placeholders[:3])
        r.error("chữ mẫu", f"Còn {len(p.placeholders)} chỗ chữ mẫu của khuôn chưa thay, ví dụ {sample}.")

    # Loại trang: trang không có thẻ phương án phải tự khai là trang chỉ giải thích, để kế hoạch một hướng
    # không lọt qua bảng ràng buộc chỉ vì quên đánh dấu đề xuất.
    if not options and EXPLAINER not in p.kinds:
        r.error("loại trang", "Trang không có thẻ data-phuong-an. Có đề xuất (kể cả kế hoạch một hướng) thì đặt mỗi "
                              f"đề xuất vào một thẻ data-phuong-an; chỉ giải thích hay báo cáo thì khai "
                              f'data-loai="{EXPLAINER}" trên <main>.')
    if options and EXPLAINER in p.kinds:
        r.error("loại trang", f'Trang khai data-loai="{EXPLAINER}" mà có thẻ phương án: bỏ một trong hai.')

    # Tóm tắt và nền tảng
    summary = parts.get("tom-tat", [])
    if not summary:
        r.error("tóm tắt", 'Thiếu phần data-phan="tom-tat" ở đầu trang (3–5 câu lời thường).')
    else:
        words = len(summary[0].plain().split())
        if words > MAX_SUMMARY_WORDS:
            r.note("tóm tắt", f"Tóm tắt dài {words} chữ; nên dưới {MAX_SUMMARY_WORDS}, chi tiết để phần sau.")
    foundation = parts.get("nen-tang", [])
    if not foundation:
        r.error("nền tảng", 'Thiếu phần data-phan="nen-tang": bối cảnh, vấn đề, khái niệm cần biết trước.')
    else:
        size = sum(len(n.plain()) for n in foundation)
        if size < MIN_FOUNDATION_CHARS:
            r.error("nền tảng", f"Phần nền tảng mới {size} ký tự, cần ít nhất {MIN_FOUNDATION_CHARS}: "
                                "giải thích từ gốc cho người không nhớ phiên làm việc.")
        if summary and summary[0].start > foundation[0].start:
            r.error("thứ tự", "Tóm tắt phải đứng trước phần nền tảng.")
        early = [o.attrs["data-phuong-an"] for o in options if o.start < foundation[0].start]
        if early:
            r.error("thứ tự", f"Phương án {', '.join(early)} đứng trước phần nền tảng; giải thích gốc trước, "
                              "đề xuất sau.")

    # Ví dụ
    if len(examples) < MIN_EXAMPLES:
        r.error("ví dụ", f"Mới có {len(examples)} ví dụ (data-vi-du), cần ít nhất {MIN_EXAMPLES}.")
    for i, ex in enumerate(examples, 1):
        size = len(ex.plain())
        if size < MIN_EXAMPLE_CHARS:
            r.error("ví dụ", f"Ví dụ {i} chỉ {size} ký tự: kể tình huống, điều xảy ra, vì sao quan trọng.")
        elif not (ex.concrete or re.search(r"\d", ex.plain())):
            r.note("ví dụ", f"Ví dụ {i} chưa có dữ liệu cụ thể (số, tên file, lệnh, đoạn trích, bảng).")

    # Thuật ngữ
    for value in sorted(p.known):
        if needs_definition(value):
            r.error("thuật ngữ", f"data-tu-quen không miễn được mã nội bộ hay ký hiệu: {value}. Định nghĩa nó.")
    option_ids = {o.attrs.get("data-phuong-an", "") for o in options}
    exempt = COMMON | option_ids | {k for k in p.known if not needs_definition(k)}
    first_use: dict[str, tuple[int, str]] = {}
    for at, term, around in p.uses:
        if term not in exempt and term not in first_use:
            first_use[term] = (at, around)
    problems = []
    for term, (at, around) in sorted(first_use.items(), key=lambda kv: kv[1][0]):
        defined = p.definitions.get(term)
        if defined is None:
            problems.append(f"{term} chưa được định nghĩa (lần đầu: “…{around}…”)")
        elif defined > at:
            problems.append(f"{term} dùng trước khi định nghĩa (lần đầu: “…{around}…”)")
    for _, term in terms_in(p.title):
        if term not in exempt and term not in p.definitions and term not in first_use:
            problems.append(f"{term} ở tiêu đề chưa được định nghĩa trong trang")
    for msg in problems[:MAX_LISTED]:
        r.error("thuật ngữ", msg + ". Thay bằng tên mô tả, hoặc định nghĩa bằng <dfn> hay bảng thuật ngữ trước đó.")
    if len(problems) > MAX_LISTED:
        r.error("thuật ngữ", f"…và {len(problems) - MAX_LISTED} thuật ngữ khác.")

    # Phương án và ràng buộc
    seen = set()
    for o in options:
        oid = o.attrs["data-phuong-an"].strip()
        if not oid:
            r.error("phương án", "Có data-phuong-an rỗng: đặt mã ngắn như A, B hay 1A.")
        elif oid in seen:
            r.error("phương án", f"Mã phương án {oid} bị trùng.")
        seen.add(oid)
    if options:
        # Trang nhiều câu chốt có thể có nhiều bảng ràng buộc; mỗi bảng đối chiếu các phương án có ô trong nó,
        # và mọi hàng của bảng phải có phán quyết cho đủ các phương án đó.
        verdicts: dict[str, list[tuple[str, str]]] = {oid: [] for oid in seen}
        covered: set[str] = set()
        if not parts.get("rang-buoc"):
            r.error("ràng buộc", 'Có đề xuất mà thiếu phần data-phan="rang-buoc" đối chiếu với luật của project.')
        for part in parts.get("rang-buoc", []):
            rows = [n for n in part.marks if "data-rang-buoc" in n.attrs]
            if not rows:
                r.error("ràng buộc", "Phần ràng buộc chưa có hàng data-rang-buoc nào.")
            ids = {c.attrs["data-cho"].strip() for row in rows for c in row.marks if "data-cho" in c.attrs}
            for oid in sorted(ids - seen):
                r.error("ràng buộc", f"Bảng ràng buộc có ô cho phương án không tồn tại: {oid}.")
            ids &= seen
            covered |= ids
            for row in rows:
                cells = [n for n in row.marks if "data-cho" in n.attrs]
                label = row_label(row, cells)
                source = row.attrs.get("data-nguon", "").strip()
                if not source or "…" in source:
                    r.error("ràng buộc", f"Hàng “{label}” thiếu data-nguon (file:dòng của luật, hay "
                                         "\"yêu cầu của bạn, <ngày>\").")
                for oid in sorted(ids):
                    mine = [c for c in cells if c.attrs["data-cho"].strip() == oid]
                    if len(mine) != 1:
                        r.error("ràng buộc", f"Hàng “{label}” cần đúng một ô data-cho=\"{oid}\", "
                                             f"đang có {len(mine)}.")
                        continue
                    verdict = mine[0].attrs.get("data-ket-qua", "")
                    if verdict not in VERDICTS:
                        r.error("ràng buộc", f"Hàng “{label}”, phương án {oid}: data-ket-qua phải là một trong "
                                             f"{', '.join(VERDICTS)}.")
                        continue
                    if verdict in ("vi-pham", "can-duyet") and len(mine[0].plain()) < MIN_REASON_CHARS:
                        r.error("ràng buộc", f"Hàng “{label}”, phương án {oid}: ghi rõ vì sao "
                                             f"{VERDICTS[verdict]}.")
                    verdicts[oid].append((verdict, label))
        for oid in sorted(seen - covered):
            r.error("ràng buộc", f"Phương án {oid} chưa được đối chiếu với ràng buộc nào.")
        for o in options:
            oid = o.attrs["data-phuong-an"].strip()
            broken = [label for verdict, label in verdicts.get(oid, []) if verdict == "vi-pham"]
            if not broken:
                continue
            if "data-khuyen" in o.attrs:
                r.error("ràng buộc", f"Phương án {oid} được khuyên nhưng vi phạm: {'; '.join(broken)}. "
                                     "Không khuyên phương án vi phạm luật của project.")
            notes = [n for n in o.marks if "data-vi-pham" in n.attrs and len(n.plain()) >= MIN_REASON_CHARS]
            on_card = "data-vi-pham" in o.attrs and "vi phạm" in o.plain().lower()
            if not (notes or on_card):
                r.error("ràng buộc", f"Thẻ phương án {oid} phải ghi rõ trên thẻ (data-vi-pham, ít nhất "
                                     f"{MIN_REASON_CHARS} ký tự) rằng nó vi phạm: {'; '.join(broken)}.")
        pattern = parts.get("pattern-xau", [])
        if not pattern:
            r.error("pattern xấu", 'Có đề xuất mà thiếu phần data-phan="pattern-xau": đã soát gì, thấy gì.')
        elif sum(len(n.plain()) for n in pattern) < MIN_PATTERN_CHARS:
            r.error("pattern xấu", "Phần pattern xấu quá ngắn: nêu từng pattern đã soát và kết quả.")
        if not questions:
            r.error("câu chốt", "Có đề xuất mà chưa có câu nào cần chốt (data-cau-hoi).")
    if len(seen) >= 2:
        covered = {n.attrs["data-cho"].strip() for c in parts.get("vi-du-x-phuong-an", [])
                   for n in c.marks if "data-cho" in n.attrs}
        if not parts.get("vi-du-x-phuong-an"):
            r.error("so sánh", 'Có từ hai phương án mà thiếu bảng data-phan="vi-du-x-phuong-an": '
                               "chạy cùng các ví dụ qua từng phương án.")
        else:
            missing = sorted(seen - covered)
            if missing:
                r.error("so sánh", f"Bảng ví dụ × phương án chưa có ô data-cho cho: {', '.join(missing)}.")
            cells = [n.attrs["data-cho"].strip() for c in parts["vi-du-x-phuong-an"] for n in c.marks
                     if "data-cho" in n.attrs]
            thin = sorted(oid for oid in seen - set(missing) if cells.count(oid) < MIN_EXAMPLES)
            if thin:
                r.note("so sánh", f"Phương án {', '.join(thin)} mới chạy qua dưới {MIN_EXAMPLES} ví dụ trong bảng "
                                  "ví dụ × phương án.")
        if not any("data-khuyen" in o.attrs for o in options):
            r.note("phương án", "Chưa phương án nào có data-khuyen: nêu khuyến nghị và lý do, trừ khi thật sự ngang nhau.")
    for i, q in enumerate(questions, 1):
        if len(q.plain()) < MIN_QUESTION_CHARS:
            r.error("câu chốt", f"Câu chốt {i} quá ngắn: hỏi bằng lời thường, kèm lựa chọn và khuyến nghị.")

    r.stats = {"ví dụ": len(examples), "phương án": len(seen), "câu chốt": len(questions),
               "thuật ngữ đã định nghĩa": len(p.definitions)}
    return r


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Kiểm trang Artifact theo khuôn trang-artifact trước khi đăng.")
    ap.add_argument("file", help="file HTML sắp đăng")
    args = ap.parse_args(argv)
    try:
        html = Path(args.file).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"Không đọc được {args.file}: {exc}")
        return 2
    r = check(html)
    for title, items in (("LỖI", r.errors), ("NHẮC", r.notes)):
        if items:
            print(f"{title} ({len(items)}):")
            for item in items:
                print(f"  - {item}")
    summary = ", ".join(f"{v} {k}" for k, v in r.stats.items())
    if r.errors:
        print(f"Chưa đạt: {len(r.errors)} lỗi ({summary}). Sửa rồi chạy lại.")
        return 1
    print(f"Đạt ({summary}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
