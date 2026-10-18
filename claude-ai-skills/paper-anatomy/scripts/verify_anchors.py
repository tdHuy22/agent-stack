#!/usr/bin/env python3
"""Kiểm từng thẻ neo 【…】 trong bản phân tích so với văn bản bài báo đã trích theo trang.

Cách dùng:
    python3 verify_anchors.py phan-tich.md --pages work/pages.json          # bảng kết quả + tổng kết
    python3 verify_anchors.py phan-tich.md --pages work/pages.json --json   # cho máy đọc

Mỗi thẻ có dạng 【§3.1 · tr.5 · Eq.(4) · "vài chữ nguyên văn"】; phần nào cũng có thể vắng trừ trang.
Kiểm:
  - trang có tồn tại không (nhãn in, hoặc tr.PDF<i> cho trang PDF thứ i);
  - mục có chứa trang đó không (theo bản đồ mục; không có trong bản đồ thì chỉ cảnh báo);
  - Hình/Bảng/Eq/Thuật toán/Định lý… có được nhắc trên trang đó không;
  - đoạn nguyên văn có nằm trên trang đó không (bỏ qua hoa thường, dấu câu, xuống dòng, chữ ghép).
Neo sai chỗ (nội dung đúng nhưng trỏ sai bảng hay trang), chỉ cảnh báo:
  - Bảng/Hình ghi trong thẻ, hoặc nhắc trong câu đi trước thẻ, có trang chú thích khác trang đã ghi;
  - con số trong câu đi trước thẻ (có %, có phần thập phân, hay từ 100 trở lên) không có trên trang đã ghi
    nhưng có ở trang khác.
Thêm: đoạn văn dài không có neo và không gắn nhãn [suy luận]/[minh họa]/[ngoài bài]; trích dài hơn 15 từ;
số từ của mục 0 "Đọc trong 1 phút" (tối đa 200, không tính neo) và các chữ tuyệt đối trong đó ("mọi", "chỉ",
"duy nhất"…), chỗ ý bị nén dễ khái quát quá tay; số mục (tiêu đề ##) nhảy hay dùng chữ cái.

Mã thoát: 0 khi không có lỗi (FAIL), 1 khi có, 2 khi sai cách dùng. Chỉ dùng thư viện chuẩn.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import unicodedata

ANCHOR = re.compile(r"【([^】]{1,400})】")
# Ghép đúng cặp ngoặc: “…”, "…", «…»; không vắt qua dòng, để không nhận nhầm đoạn văn giữa hai câu trích.
QUOTE = re.compile(r"“([^”\n]{2,300})”|\"([^\"\n]{2,300})\"|«([^»\n]{2,300})»")
PAGE_TOKEN = re.compile(r"^(?:tr|trang|p|pp|page)\.?\s*(PDF\s*)?([0-9]{1,6}|[ivxlcdm]{1,7})"
                        r"(?:\s*[-–—]\s*([0-9]{1,6}))?((?:\s*,\s*[0-9]{1,6})*)$", re.IGNORECASE)
AUX = [
    ("Figure", r"(?:Hình|Figure|Fig\.?)\s*([A-Z]?\.?\d{1,3}[a-z]?)"),
    ("Table", r"(?:Bảng|Table|Tab\.?)\s*([A-Z]?\.?\d{1,3})"),
    ("Eq", r"(?:Eq\.?|Equation|Công thức|CT\.?|PT\.?)\s*\(?\s*(\d{1,3}(?:\.\d{1,2})?[a-z]?)\s*\)?"),
    ("Algorithm", r"(?:Thuật toán|Algorithm|Alg\.?)\s*(\d{1,3})"),
    ("Theorem", r"(?:Định lý|Theorem|Thm\.?)\s*([A-Z]?\.?\d{1,3}(?:\.\d{1,2})?)"),
    ("Lemma", r"(?:Bổ đề|Lemma)\s*([A-Z]?\.?\d{1,3}(?:\.\d{1,2})?)"),
    ("Proposition", r"(?:Mệnh đề|Proposition|Prop\.?)\s*([A-Z]?\.?\d{1,3}(?:\.\d{1,2})?)"),
    ("Corollary", r"(?:Hệ quả|Corollary)\s*([A-Z]?\.?\d{1,3}(?:\.\d{1,2})?)"),
    ("Definition", r"(?:Định nghĩa|Definition|Def\.?)\s*([A-Z]?\.?\d{1,3}(?:\.\d{1,2})?)"),
    ("Listing", r"(?:Listing|Code)\s*(\d{1,3})"),
]
# Cách bài báo có thể nhắc tới từng loại trên trang (tiếng Anh là chính, thêm tiếng Việt).
MENTION = {
    "Figure": r"(?:Figure|Fig\.?|Hình)\s*{id}(?![\d])",
    "Table": r"(?:Table|Tab\.?|Bảng)\s*{id}(?![\d])",
    "Eq": r"\(\s*{id}\s*\)|(?:Eq\.?|Equation|eq\.)\s*\(?\s*{id}(?![\d])",
    "Algorithm": r"(?:Algorithm|Alg\.?|Thuật toán)\s*{id}(?![\d])",
    "Theorem": r"(?:Theorem|Thm\.?|Định lý)\s*{id}(?![\d])",
    "Lemma": r"(?:Lemma|Bổ đề)\s*{id}(?![\d])",
    "Proposition": r"(?:Proposition|Prop\.?|Mệnh đề)\s*{id}(?![\d])",
    "Corollary": r"(?:Corollary|Hệ quả)\s*{id}(?![\d])",
    "Definition": r"(?:Definition|Def\.?|Định nghĩa)\s*{id}(?![\d])",
    "Listing": r"(?:Listing|Code)\s*{id}(?![\d])",
}
LABELED = re.compile(r"\[(?:suy luận|minh họa|minh hoạ|ngoài bài|ý kiến|inference|illustration)", re.IGNORECASE)
MIN_QUOTE_CHARS = 12      # sau khi chuẩn hóa; ngắn hơn thì khớp ở đâu cũng được, không đủ để kiểm
LONG_QUOTE_WORDS = 15
QUICK_READ_WORDS = 200
# Chấp nhận các biến thể hay gặp: "##"/"###", chữ đậm, "0." hay "0)", khoảng trắng thừa.
QUICK_READ = re.compile(r"^#{2,3}[ \t]*\**[ \t]*0[ \t]*[.)][ \t]*\**[ \t]*Đọc[ \t]+trong[ \t]+1[ \t]+phút[^\n]*$",
                        re.MULTILINE | re.IGNORECASE)
# Chữ tuyệt đối hay bị thêm khi nén ý. "chỉ" bỏ qua các từ ghép không mang nghĩa "duy nhất" (chỉ ra, chỉ thị…).
ABSOLUTE = re.compile(r"(?<!\w)(mọi|duy nhất|luôn luôn|luôn|không bao giờ|tất cả|hoàn toàn|"
                      r"chỉ(?!\s+(?:ra|số|thị|định|dẫn|báo|tiêu|mục|rõ|huy|trích|đạo|tay)(?!\w)))(?!\w)",
                      re.IGNORECASE)
# Bảng và Hình có trang chú thích trong pages.json ("objects"); con số lấy từ chúng nên neo vào trang đó.
HOME_KINDS = {"Table": "Bảng", "Figure": "Hình"}
# Con số trong câu của người phân tích: không dính chữ (A100, 80GB, 1.3B), không phải số mục (§4.2).
CLAIM_NUMBER = re.compile(r"(?<![\w.,§])(\d+(?:[.,]\d+)*)(?!\w|[.,]\d)(\s*%)?")
PAGE_NUMBER = re.compile(r"(?<![\d.,])(\d+(?:[.,]\d+)*)")
THOUSANDS = re.compile(r"^[1-9]\d{0,2}(?:([.,])\d{3})(?:\1\d{3})*$")
SENTENCE_END = re.compile(r"[.!?…](?=\s)|\n|\|")
# Số mục: "## 2. …", "## 2) …", "## 2: …", "## 2 …", "## **2.** …"; không nhận số phân cấp "## 3.1 …". Chữ cái
# ("## A. …") chỉ nhận khi có dấu ngăn, để tiêu đề thường bắt đầu bằng chữ hoa không bị tính.
SECTION_HEAD = re.compile(r"^##[ \t]+\**[ \t]*(?:([0-9]{1,2})(?:[.):](?!\d)|[ \t])|([A-Z])[.):](?!\w))", re.MULTILINE)
# Tên mô hình hay đứng trước số phiên bản (Claude 3.5, Llama-3.3): số thập phân đứng sau chúng không phải số liệu.
MODEL_NAME = re.compile(r"(?:^|[\s(])(?:Claude|Gemini|Gemma|Llama|GPT|Qwen|Mistral|Mixtral|Phi|DeepSeek|Grok|"
                        r"Sonnet|Opus|Haiku|PaLM|Vicuna|Falcon|Yi|OLMo|Kimi|GLM|Command)[ -]$", re.IGNORECASE)
ILLUSTRATIVE = re.compile(r"\[(?:minh họa|minh hoạ|illustration)", re.IGNORECASE)
# "xem Bảng 6", "see Table 2": câu chỉ đường cho người đọc, không phải lấy số từ bảng đó.
POINTER = re.compile(r"(?:\bxem|\bsee|\bcf\.?)\s*$", re.IGNORECASE)


def number_value(token):
    """Giá trị số để so. "1.000", "30,000" là số nguyên có dấu phân cách hàng nghìn; còn lại coi dấu phẩy là dấu
    thập phân (60,2 = 60.2). None nếu không đọc được."""
    if THOUSANDS.match(token):
        token = re.sub(r"[.,]", "", token)
    try:
        return round(float(token.replace(",", ".")), 6)
    except ValueError:
        return None


def claim_numbers(claim):
    """Con số đáng kiểm trong câu: có %, có phần thập phân, hay từ 100 trở lên (trừ năm 1900–2099). Bỏ số đứng
    sau ≈ hay ~ (người phân tích tự tính) và số trong cụm Bảng/Hình/Eq/tr. (đã kiểm ở phần thẻ)."""
    text = re.sub(r"§\S+|\btr\.\s*\S+", " ", claim)
    out = []
    for m in CLAIM_NUMBER.finditer(text):
        token, pct = m.group(1), bool(m.group(2))
        before = text[max(0, m.start() - 25):m.start()]
        if re.search(r"[≈~]\s*$", before):
            continue
        value = number_value(token)
        if value is None:
            continue
        decimal = bool(re.search(r"[.,]", token))
        if decimal and not pct and MODEL_NAME.search(before):
            continue  # số phiên bản trong tên mô hình: Claude 3.5, Gemini 2.5, Llama-3.3
        big = value >= 100 and not (1900 <= value <= 2099 and not decimal)
        if pct or decimal or big:
            out.append((token + ("%" if pct else ""), value))
    return out


def squash(s):
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", s).casefold())


def roman_to_int(s):
    vals = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    total, prev = 0, 0
    for ch in reversed(s.lower()):
        v = vals.get(ch, 0)
        total = total - v if v < prev else total + v
        prev = max(prev, v)
    return total


class Paper:
    def __init__(self, cache):
        self.pages = cache["pages"]
        self.sections = cache.get("sections", [])
        self.by_label = {}
        for p in self.pages:
            self.by_label.setdefault(str(p["label"]).lower(), []).append(p["index"])
        self.flat = {p["index"]: squash(p["text"]) for p in self.pages}
        self.scanned = {p["index"] for p in self.pages if len(p["text"].strip()) < 60}
        self.homes = {}
        for o in cache.get("objects", []):
            if o.get("kind") in HOME_KINDS:
                self.homes.setdefault((o["kind"], str(o["id"]).lower()), []).append(o["page"])
        self.numbers = {p["index"]: {number_value(t) for t in PAGE_NUMBER.findall(p["text"])} for p in self.pages}

    def home(self, kind, ident):
        """Trang chú thích của Bảng/Hình (nơi nó được in), [] nếu không biết."""
        return sorted(self.homes.get((kind, str(ident).lower()), []))

    def pages_with_number(self, value):
        return [i for i, nums in self.numbers.items() if value in nums]

    def resolve(self, pdf_prefix, first, last, extra):
        """Danh sách trang PDF ứng với phần tr.… của thẻ; [] nếu không có trang đó."""
        def one(token, as_pdf):
            if as_pdf:
                i = int(token) if token.isdigit() else roman_to_int(token)
                return [i] if 1 <= i <= len(self.pages) else []
            return list(self.by_label.get(token.lower(), []))
        found = one(first, pdf_prefix)
        if last:
            start = found[0] if found else None
            end = one(last, pdf_prefix)
            if start and end:
                found = list(range(start, end[-1] + 1))
        for tok in re.findall(r"\d+", extra or ""):
            found += one(tok, pdf_prefix)
        return sorted(set(found))

    def section_span(self, ref):
        """(trang đầu, trang cuối) của mục; None nếu không tìm thấy trong bản đồ."""
        ref = ref.strip().rstrip(".")
        num = re.match(r"^((?:\d{1,2}|[A-H])(?:\.\d{1,2}){0,3}|[IVX]{1,5}(?:-[A-Z])?)(?:\s|$)", ref)
        spans = []
        if num:
            key = num.group(1)
            for s in self.sections:
                n = s.get("number") or ""
                if n == key or n.startswith(key + "."):
                    spans.append((s["page"], s["end"]))
        else:
            want = squash(re.sub(r"^(?:phụ lục|appendix|mục)\s*", "", ref, flags=re.IGNORECASE))
            if ref.lower().startswith(("phụ lục", "appendix")):
                letter = re.search(r"\b([A-H])\b", ref)
                if letter:
                    for s in self.sections:
                        if (s.get("number") or "").split(".")[0] == letter.group(1):
                            spans.append((s["page"], s["end"]))
            if want and not spans:
                for s in self.sections:
                    title = squash(re.sub(r"^\S*\d\S*\s+", "", s["title"]))
                    if title and (title.startswith(want) or want.startswith(title) and len(title) >= 5):
                        spans.append((s["page"], s["end"]))
        if not spans:
            return None
        return min(a for a, _ in spans), max(b for _, b in spans)

    def mentions(self, kind, ident, page):
        pat = MENTION[kind].format(id=re.escape(ident))
        return re.search(pat, unicodedata.normalize("NFKC", self.pages[page - 1]["text"]), re.IGNORECASE) is not None

    def pages_mentioning(self, kind, ident):
        return [p["index"] for p in self.pages if self.mentions(kind, ident, p["index"])]

    def quote_pages(self, quote):
        want = squash(quote)
        return [i for i, flat in self.flat.items() if want and want in flat]

    def fuzzy(self, quote, page):
        want = squash(quote)
        hay = self.flat.get(page, "")
        if not want or not hay:
            return 0.0
        m = difflib.SequenceMatcher(None, hay, want, autojunk=False).find_longest_match(0, len(hay), 0, len(want))
        return m.size / len(want)


def parse_anchor(body):
    """Tách thẻ thành mục, trang, đối tượng phụ, đoạn trích."""
    quotes = [next(g for g in m if g).strip() for m in QUOTE.findall(body)]
    rest = QUOTE.sub(" ", body)
    parts = [p.strip() for p in re.split(r"[·•|;]", rest) if p.strip()]
    out = {"section": "", "page": None, "aux": [], "quotes": quotes, "raw": body}
    for part in parts:
        if part.startswith("§"):
            out["section"] = part[1:].strip()
            continue
        m = PAGE_TOKEN.match(part)
        if m and out["page"] is None:
            out["page"] = (bool(m.group(1)), m.group(2), m.group(3), m.group(4))
            continue
        for kind, pat in AUX:
            for found in re.finditer(pat, part, re.IGNORECASE):
                out["aux"].append((kind, found.group(1).rstrip(".")))
    return out


def check_anchor(paper, anchor, claim="", illustrative=False):
    """Trả về (trạng thái, các lý do). Trạng thái: OK, WARN, FAIL. `claim` là câu đi trước thẻ (để dò neo sai
    chỗ: bảng, hình hay con số nằm ở trang khác). `illustrative`: đoạn có nhãn [minh họa], số trong đó do người
    phân tích tự tính nên không dò số."""
    a = parse_anchor(anchor)
    reasons, levels = [], ["OK"]

    def bump(level, why):
        reasons.append(why)
        levels.append(level)

    def status():
        return max(levels, key=("OK", "WARN", "FAIL").index)

    if a["page"] is None:
        bump("FAIL", "thiếu trang (tr.…)")
        return status(), reasons, a
    pages = paper.resolve(*a["page"])
    if not pages:
        bump("FAIL", f"trang {a['page'][1]} không có trong bài")
        return status(), reasons, a
    if a["section"]:
        span = paper.section_span(a["section"])
        if span is None:
            bump("WARN", f"không thấy mục §{a['section']} trong bản đồ mục")
        elif not any(span[0] <= p <= span[1] for p in pages):
            bump("FAIL", f"§{a['section']} nằm ở trang PDF {span[0]}–{span[1]}, không chứa trang đã ghi")
    scanned = all(p in paper.scanned for p in pages)
    for kind, ident in a["aux"]:
        if scanned:
            bump("WARN", f"trang không có chữ (scan): không kiểm được {kind} {ident}")
            continue
        if not any(paper.mentions(kind, ident, p) for p in pages):
            where = paper.pages_mentioning(kind, ident)
            hint = f"; được nhắc ở trang PDF {', '.join(map(str, where[:5]))}" if where else "; không thấy ở đâu trong bài"
            bump("FAIL", f"{kind} {ident} không có trên trang đã ghi{hint}")
            continue
        home = paper.home(kind, ident)
        if home and not any(p in pages for p in home):
            bump("WARN", f"{HOME_KINDS[kind]} {ident} in ở trang PDF {', '.join(map(str, home))}; trang đã ghi chỉ "
                         "nhắc tới nó (con số lấy từ bảng/hình thì neo vào trang đó)")
    if claim and not scanned:
        named = {(k, i.lower()) for k, i in a["aux"]}
        # Thẻ đã ghi một Bảng/Hình thì người viết đã chọn đối tượng chống đỡ; câu nhắc thêm đối tượng khác
        # thường là để so, không cảnh báo.
        anchor_has_home = any(k in HOME_KINDS for k, _ in a["aux"])
        for kind, pat in AUX:
            if kind not in HOME_KINDS or anchor_has_home:
                continue
            for found in re.finditer(pat, claim, re.IGNORECASE):
                ident = found.group(1).rstrip(".")
                home = paper.home(kind, ident)
                if (kind, ident.lower()) in named or not home or any(p in pages for p in home):
                    continue
                if POINTER.search(claim[:found.start()]):
                    continue
                named.add((kind, ident.lower()))
                bump("WARN", f"câu nhắc {HOME_KINDS[kind]} {ident} (in ở trang PDF {', '.join(map(str, home))}) "
                             "nhưng thẻ trỏ trang khác và không ghi nó")
        on_pages = set().union(*(paper.numbers.get(p, set()) for p in pages))
        for token, value in ([] if illustrative else claim_numbers(claim)):
            if value in on_pages:
                continue
            elsewhere = paper.pages_with_number(value)
            if elsewhere:
                bump("WARN", f"số {token} không có trên trang đã ghi; có ở trang PDF {', '.join(map(str, elsewhere[:3]))}")
    for quote in a["quotes"]:
        if len(quote.split()) > LONG_QUOTE_WORDS:
            bump("WARN", f"trích dài {len(quote.split())} từ (nên ≤ {LONG_QUOTE_WORDS})")
        if len(squash(quote)) < MIN_QUOTE_CHARS:
            bump("WARN", f"trích «{quote}» quá ngắn để kiểm")
            continue
        if scanned:
            bump("WARN", "trang không có chữ (scan): không kiểm được trích dẫn")
            continue
        found = paper.quote_pages(quote)
        if any(p in pages for p in found):
            continue
        near = [p for p in found if any(abs(p - q) == 1 for q in pages)]
        if near:
            bump("WARN", f"trích «{quote[:40]}» nằm ở trang PDF {near[0]} (trang kề)")
        elif found:
            bump("FAIL", f"trích «{quote[:40]}» nằm ở trang PDF {', '.join(map(str, found[:3]))}, không phải trang đã ghi")
        else:
            best = max(paper.fuzzy(quote, p) for p in pages)
            if best >= 0.8:
                bump("WARN", f"trích «{quote[:40]}» chỉ khớp gần đúng ({best:.0%}) trên trang đã ghi")
            else:
                bump("FAIL", f"không tìm thấy trích «{quote[:40]}» trong bài (chép sai hoặc là diễn giải)")
    return status(), reasons, a


def unanchored_paragraphs(text, min_words=60):
    """Đoạn văn dài (không phải tiêu đề, bảng, code) không có neo, không nhắc trang, không gắn nhãn suy luận.
    Chỉ để tham khảo: đoạn định vị hay đoạn tổng hợp của người phân tích có thể không cần neo."""
    found, in_code = [], False
    block, start = [], 0
    lines = text.splitlines() + [""]
    for no, line in enumerate(lines, 1):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if line.strip() == "" or line.lstrip().startswith(("#", "|", ">")):
            if block:
                para = " ".join(block)
                if (len(para.split()) >= min_words and "【" not in para and not LABELED.search(para)
                        and not re.search(r"\btr\.\s*\d|§\s*\w", para)):
                    found.append((start, para[:90]))
            block = []
            continue
        if not block:
            start = no
        block.append(line.strip())
    return found


def long_quotes(text):
    """Trích dài hơn 15 từ ngoài thẻ neo; bỏ qua khối code và đoạn gắn nhãn [minh họa] (ví dụ tự dựng)."""
    body = re.sub(r"```.*?```", " ", ANCHOR.sub(" ", text), flags=re.S)
    paras = [p for p in re.split(r"\n\s*\n", body) if not re.search(r"\[minh họa|\[minh hoạ", p, re.I)]
    found = []
    for para in paras:
        for m in QUOTE.findall(para):
            q = next(g for g in m if g)
            if len(q.split()) > LONG_QUOTE_WORDS:
                found.append(q)
    return found


def quick_read(text):
    """Mục 0 "Đọc trong 1 phút": số từ (không tính neo, ký hiệu đầu dòng) và vị trí các chữ tuyệt đối.
    None khi bản phân tích không có mục này (chế độ hỏi hẹp). Chuẩn hóa NFC trước, vì chữ Việt dạng tổ hợp dấu
    (NFD) làm cả tiêu đề lẫn chữ tuyệt đối trượt; NFC không đổi dấu xuống dòng nên số dòng vẫn đúng."""
    text = unicodedata.normalize("NFC", text)
    head = QUICK_READ.search(text)
    if not head:
        return None
    rest = text[head.end():]
    nxt = re.search(r"^#{1,2}\s", rest, re.MULTILINE)
    body = rest[: nxt.start()] if nxt else rest
    words = [w for w in ANCHOR.sub(" ", body).split() if re.search(r"\w", w)]
    first_line = text.count("\n", 0, head.end()) + 1
    absolutes = [{"line": first_line + body.count("\n", 0, m.start()), "word": m.group(1)}
                 for m in ABSOLUTE.finditer(ANCHOR.sub(lambda a: " " * len(a.group(0)), body))]
    return {"words": len(words), "limit": QUICK_READ_WORDS, "absolutes": absolutes}


def claim_before(text, start, floor):
    """Câu đi trước thẻ neo: từ dấu hết câu, đầu dòng, ô bảng hay thẻ neo trước (cái nào gần hơn) tới thẻ."""
    head = text[floor:start]
    ends = [m.end() for m in SENTENCE_END.finditer(head.rstrip(" \t*_"))]
    return head[ends[-1]:] if ends else head


def section_numbering(text):
    """Số của các tiêu đề ## có đánh số (bỏ qua khối mã). Trả về (dãy số, lỗi) với lỗi là None, "chữ cái" hay
    "nhảy"."""
    text = re.sub(r"^```.*?^```", "", unicodedata.normalize("NFC", text), flags=re.S | re.M)
    marks = [m.group(1) or m.group(2) for m in SECTION_HEAD.finditer(text)]
    if not marks:
        return marks, None
    if any(not x.isdigit() for x in marks):
        return marks, "chữ cái"
    nums = [int(x) for x in marks]
    return marks, (None if nums == list(range(nums[0], nums[0] + len(nums))) else "nhảy")


def run(analysis_text, cache):
    paper = Paper(cache)
    rows, prev_end = [], 0
    for m in ANCHOR.finditer(analysis_text):
        line = analysis_text.count("\n", 0, m.start()) + 1
        claim = claim_before(analysis_text, m.start(), prev_end)
        prev_end = m.end()
        line_start = analysis_text.rfind("\n", 0, m.start()) + 1
        illustrative = bool(ILLUSTRATIVE.search(analysis_text[line_start:m.start()]))
        status, reasons, parsed = check_anchor(paper, m.group(1), claim, illustrative)
        rows.append({"line": line, "anchor": m.group(1).strip(), "status": status, "reasons": reasons,
                     "has_quote": bool(parsed["quotes"])})
    counts = {k: sum(r["status"] == k for r in rows) for k in ("OK", "WARN", "FAIL")}
    quoted = [r for r in rows if r["has_quote"]]
    return {
        "anchors": len(rows), **counts,
        "with_quote": len(quoted), "quote_fail": sum(r["status"] == "FAIL" for r in quoted),
        "unanchored_paragraphs": [{"line": ln, "start": s} for ln, s in unanchored_paragraphs(analysis_text)],
        "long_quotes": long_quotes(analysis_text),
        "quick_read": quick_read(analysis_text),
        "numbering": dict(zip(("marks", "problem"), section_numbering(analysis_text))),
        "rows": rows,
    }


def render(result):
    out = []
    for r in result["rows"]:
        if r["status"] == "OK":
            continue
        out.append(f"{r['status']:<4} dòng {r['line']:>4}: 【{r['anchor'][:70]}】")
        out += [f"           - {why}" for why in r["reasons"]]
    out.append("")
    out.append(f"Neo: {result['anchors']} · khớp {result['OK']} · cảnh báo {result['WARN']} · sai {result['FAIL']} "
               f"· có trích nguyên văn {result['with_quote']}")
    if result["unanchored_paragraphs"]:
        lines = ", ".join(str(u["line"]) for u in result["unanchored_paragraphs"][:12])
        out.append(f"Tham khảo, không bắt buộc sửa: {len(result['unanchored_paragraphs'])} đoạn dài không có neo "
                   f"hay nhãn [suy luận] (dòng {lines}); thêm neo nếu đoạn đó nói về nội dung bài")
    if result["long_quotes"]:
        out.append(f"Trích dài hơn {LONG_QUOTE_WORDS} từ: {len(result['long_quotes'])} chỗ, rút ngắn hoặc diễn giải")
    quick = result.get("quick_read")
    if quick:
        verdict = "cắt chữ, không bỏ dòng" if quick["words"] > quick["limit"] else "đạt"
        out.append(f"Mục 0: {quick['words']} từ (đếm theo âm tiết, không tính neo; tối đa {quick['limit']}): {verdict}")
    if quick and quick["absolutes"]:
        found = ", ".join(f"'{a['word']}' dòng {a['line']}" for a in quick["absolutes"][:12])
        out.append(f"Mục 0 có chữ tuyệt đối, kiểm lại với bảng hay câu gốc: {found}")
    numbering = result.get("numbering") or {}
    if numbering.get("problem"):
        how = "dùng chữ cái" if numbering["problem"] == "chữ cái" else "nhảy"
        out.append(f"Số mục {how} ({', '.join(numbering['marks'])}): đánh số lại liên tục 0, 1, 2…")
    if result["anchors"] == 0:
        out.append("Không thấy thẻ neo 【…】 nào.")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Kiểm thẻ neo 【…】 so với văn bản bài báo theo trang.")
    ap.add_argument("analysis", help="file bản phân tích (Markdown)")
    ap.add_argument("--pages", required=True, help="pages.json do extract_paper.py --out ghi ra")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        with open(args.analysis, encoding="utf-8") as fh:
            text = fh.read()
        with open(args.pages, encoding="utf-8") as fh:
            cache = json.load(fh)
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"Không đọc được đầu vào: {exc}\n")
        return 2
    result = run(text, cache)
    print(json.dumps(result, ensure_ascii=False, indent=1) if args.json else render(result))
    return 1 if result["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
