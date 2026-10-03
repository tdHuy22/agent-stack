#!/usr/bin/env python3
"""Trích văn bản bài báo theo TRANG, kèm bản đồ mục, chỉ mục hình/bảng/công thức và nhãn trang in.

Cách dùng (nên luôn có --out để có file cho bước đọc và bước kiểm neo):
    python3 extract_paper.py bai.pdf --out work/                 # ghi pages.json + paper.txt, in báo cáo và bản đồ
    python3 extract_paper.py bai.pdf --out work/ --pages 1-8     # in văn bản trang PDF 1–8 để đọc theo đợt
    python3 extract_paper.py bai.pdf --out work/ --find "chuỗi"  # tìm chuỗi nằm ở trang nào (để neo đúng trang)
    python3 extract_paper.py bai.pdf --out work/ --render 4,7-9  # xuất PNG các trang để NHÌN hình, công thức, bản scan
    python3 extract_paper.py bai.pdf                             # kiểu cũ: in báo cáo, bản đồ và toàn văn ra stdout

Chỉ số trang trong --pages/--render/--find là trang PDF (1 = trang đầu file). Nhãn trang in
(số người đọc thấy trên giấy) nằm trong bản đồ và trong mốc "===== PAGE i/N · tr.<nhãn> =====".

Thư viện: PyMuPDF (tốt nhất, có xuất ảnh) → pypdf → lệnh pdftotext. Thiếu cả ba thì script báo cách xử lý,
không tự cài gì.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter

SCAN_CHARS = 60          # trang ít hơn chừng này ký tự thì coi là trang ảnh (scan)
SCHEMA = 2

# ---------------------------------------------------------------- đọc PDF


def _load_pymupdf():
    try:
        import pymupdf  # noqa: F401
        return pymupdf
    except ImportError:
        pass
    try:
        import fitz  # bản PyMuPDF cũ
        return fitz
    except ImportError:
        return None


def read_pdf(path):
    """Trả về dict: backend, texts, labels (nhãn từ siêu dữ liệu PDF, có thể rỗng), outline, columns."""
    mupdf = _load_pymupdf()
    if mupdf is not None:
        doc = mupdf.open(path)
        texts, labels, columns = [], [], []
        for page in doc:
            texts.append(page.get_text("text"))
            try:
                labels.append(page.get_label() or "")
            except Exception:
                labels.append("")
            columns.append(_guess_columns(page))
        outline = [(lvl, title.strip(), page) for lvl, title, page in doc.get_toc(simple=True) if page >= 1]
        fonts = _font_headings(doc)
        return {"backend": "pymupdf", "texts": texts, "labels": labels, "outline": outline,
                "columns": columns, "font_headings": fonts}
    try:
        import pypdf
    except ImportError:
        pypdf = None
    if pypdf is not None:
        reader = pypdf.PdfReader(path)
        texts = [(p.extract_text() or "") for p in reader.pages]
        try:
            labels = list(reader.page_labels)
        except Exception:
            labels = [""] * len(texts)
        # pypdf trả nhãn mặc định "1", "2"… khi PDF không khai báo nhãn: coi như không có.
        if labels == [str(i + 1) for i in range(len(texts))]:
            labels = [""] * len(texts)
        return {"backend": "pypdf", "texts": texts, "labels": labels, "outline": _pypdf_outline(reader),
                "columns": [0] * len(texts), "font_headings": []}
    if shutil.which("pdftotext"):
        out = subprocess.run(["pdftotext", "-enc", "UTF-8", path, "-"], capture_output=True, text=True)
        texts = out.stdout.split("\f")
        if texts and not texts[-1].strip():
            texts = texts[:-1]
        return {"backend": "pdftotext", "texts": texts, "labels": [""] * len(texts), "outline": [],
                "columns": [0] * len(texts), "font_headings": []}
    sys.stderr.write(
        "Không có thư viện đọc PDF (PyMuPDF, pypdf) hay lệnh pdftotext.\n"
        "- Trong sandbox dùng một lần (như claude.ai): pip install pymupdf rồi chạy lại.\n"
        "- Trên máy của người dùng: đừng cài toàn cục khi chưa hỏi; dùng venv riêng, hoặc đọc PDF bằng\n"
        "  công cụ đọc file có sẵn (Read của Claude Code đọc được PDF theo trang) và ghi rõ là không kiểm neo tự động.\n")
    sys.exit(2)


def _pypdf_outline(reader):
    found = []

    def walk(items, level):
        for item in items:
            if isinstance(item, list):
                walk(item, level + 1)
                continue
            try:
                page = reader.get_destination_page_number(item) + 1
                found.append((level, str(item.title).strip(), page))
            except Exception:
                continue
    try:
        walk(reader.outline, 1)
    except Exception:
        return []
    return found


def _guess_columns(page):
    """2 nếu trang trông như hai cột (nhiều khối chữ hẹp ở cả hai nửa), ngược lại 1."""
    try:
        width = page.rect.width
        blocks = [b for b in page.get_text("blocks") if b[6] == 0 and len(b[4].strip()) > 40]
    except Exception:
        return 0
    if len(blocks) < 4:
        return 1
    narrow = [b for b in blocks if (b[2] - b[0]) < width * 0.55]
    left = sum(1 for b in narrow if b[2] <= width * 0.55)
    right = sum(1 for b in narrow if b[0] >= width * 0.45)
    return 2 if left >= 2 and right >= 2 and len(narrow) >= 0.6 * len(blocks) else 1


def _font_headings(doc, limit=400):
    """Dòng ngắn có cỡ chữ lớn hơn thân bài hoặc in đậm và bắt đầu bằng số mục: ứng viên tiêu đề."""
    sizes, lines = Counter(), []
    for pno, page in enumerate(doc, 1):
        try:
            blocks = page.get_text("dict")["blocks"]
        except Exception:
            continue
        for block in blocks:
            for line in block.get("lines", []):
                spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
                if not spans:
                    continue
                text = "".join(s["text"] for s in spans).strip()
                size = max(s.get("size", 0) for s in spans)
                bold = all(s.get("flags", 0) & 16 for s in spans)
                sizes[round(size, 1)] += len(text)
                lines.append((pno, text, size, bold))
    if not sizes:
        return []
    body = sizes.most_common(1)[0][0]
    merged, i = [], 0
    while i < len(lines):
        pno, text, size, bold = lines[i]
        if BARE_NUM.match(text) and i + 1 < len(lines) and lines[i + 1][0] == pno and _title_like(lines[i + 1][1]):
            nxt = lines[i + 1]
            merged.append((pno, f"{BARE_NUM.match(text).group(1)} {nxt[1]}", max(size, nxt[2]), bold and nxt[3]))
            i += 2
            continue
        merged.append(lines[i])
        i += 1
    found = []
    for pno, text, size, bold in merged:
        if len(text) > 90 or len(text.split()) > 12:
            continue
        if (size >= body + 0.8 or bold) and (NUM_HEADING.match(text) or _keyword_heading(text)):
            found.append((pno, text))
        if len(found) >= limit:
            break
    return found


# ---------------------------------------------------------------- nhãn trang in

PRINTED_NUM = re.compile(r"^\s*(?:page\s+|trang\s+)?[-–—]?\s*(\d{1,5})\s*[-–—]?\s*(?:/\s*\d{1,5}|of\s+\d{1,5})?\s*$",
                         re.IGNORECASE)


def printed_labels(texts, pdf_labels=None):
    """Nhãn trang in cho từng trang và cách dò được.

    Ưu tiên nhãn khai báo trong PDF. Không có thì tìm số đứng riêng ở đầu hoặc cuối trang và chỉ tin khi
    các số đó cùng lệch một khoảng cố định so với số trang PDF (để không nhầm số của bảng hay công thức).
    """
    n = len(texts)
    if pdf_labels and any(pdf_labels) and len(set(pdf_labels)) > max(1, n // 2):
        return [lab or str(i + 1) for i, lab in enumerate(pdf_labels)], "nhãn khai báo trong PDF"
    offsets = Counter()
    for i, text in enumerate(texts):
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        seen = set()
        spots = list(range(min(3, len(lines)))) + list(range(max(3, len(lines) - 3), len(lines)))
        for k in spots:
            ln = lines[k]
            m = PRINTED_NUM.match(ln)
            # "3" ngay trên "Threat Model" là số mục, không phải số trang.
            if m and not (k + 1 < len(lines) and _title_like(lines[k + 1])):
                off = int(m.group(1)) - (i + 1)
                if off not in seen:
                    offsets[off] += 1
                    seen.add(off)
    if offsets:
        off, hits = offsets.most_common(1)[0]
        if hits >= max(3, n // 3):
            labels = [str(i + 1 + off) for i in range(n)]
            how = ("số in trên trang, trùng số trang PDF" if off == 0
                   else f"số in trên trang, bằng số trang PDF {'+' if off > 0 else '−'} {abs(off)}")
            return labels, how
    return [str(i + 1) for i in range(n)], "không dò được số in: dùng số trang PDF"


# ---------------------------------------------------------------- bản đồ mục

NUM_HEADING = re.compile(r"^\s*((?:\d{1,2}|[A-H])(?:\.\d{1,2}){0,3})\.?\s+([A-ZĐÀ-Ỹ][^\n]{1,80})$")
ROMAN_HEADING = re.compile(r"^\s*([IVX]{1,5})\.\s+([A-ZĐ][^\n]{1,80})$")
HEADING_WORDS = (
    "abstract", "introduction", "background", "related work", "preliminaries", "motivation",
    "problem", "method", "methods", "methodology", "approach", "model", "architecture", "framework",
    "theory", "analysis", "design", "implementation", "experiment", "experiments", "evaluation",
    "results", "findings", "ablation", "discussion", "limitations", "conclusion", "conclusions",
    "future work", "references", "bibliography", "appendix", "acknowledgment", "acknowledgement",
    "acknowledgments", "acknowledgements", "threat model", "security analysis", "case study",
    "tóm tắt", "giới thiệu", "tổng quan", "phương pháp", "mô hình", "thực nghiệm", "kết quả",
    "thảo luận", "kết luận", "tài liệu tham khảo", "phụ lục",
)


BARE_NUM = re.compile(r"^\s*((?:\d{1,2}|[A-H])(?:\.\d{1,2}){0,3})\.?\s*$")


def _title_like(s):
    s = s.strip()
    return (2 <= len(s) <= 80 and len(s.split()) <= 10 and s[:1].isupper() and not s.endswith((".", ",", ";"))
            and re.search(r"[^\W\d_]{3}", s) is not None)


def merged_lines(lines):
    """Ghép dòng chỉ có số mục với dòng tiêu đề ngay sau nó ("3.1" + "Threat Model" → "3.1 Threat Model"),
    vì nhiều PDF tách số mục và tên mục thành hai dòng."""
    out, i = [], 0
    while i < len(lines):
        s = lines[i].strip()
        if BARE_NUM.match(s) and i + 1 < len(lines) and _title_like(lines[i + 1]):
            out.append(f"{BARE_NUM.match(s).group(1)} {lines[i + 1].strip()}")
            i += 2
            continue
        out.append(s)
        i += 1
    return out


def _keyword_heading(text):
    low = text.lower().strip().rstrip(".:")
    low = re.sub(r"^(?:\d+(?:\.\d+)*|[ivx]+|[a-h])\.?\s+", "", low)
    return any(low == w or low.startswith(w + " ") for w in HEADING_WORDS) and len(text.split()) <= 6


def heuristic_headings(texts):
    """Dò tiêu đề mục bằng mẫu chữ khi PDF không có mục lục; giữ thứ tự số mục không lùi."""
    found, last_top = [], 0
    for i, text in enumerate(texts, 1):
        for s in merged_lines(text.splitlines()):
            if not s or len(s) > 90 or s.endswith((".", ",", ";")) and not _keyword_heading(s):
                continue
            m = NUM_HEADING.match(s)
            if m and len(m.group(2).split()) <= 10 and not re.match(r"^[\d\W]+$", m.group(2)):
                top = m.group(1).split(".")[0]
                top_num = int(top) if top.isdigit() else 100 + ord(top)  # phụ lục A, B… sau số
                if top_num >= last_top and (top_num - last_top) <= 2 or top_num >= 100:
                    found.append((i, s))
                    last_top = max(last_top, top_num)
                continue
            if ROMAN_HEADING.match(s) or _keyword_heading(s):
                found.append((i, s))
    return found


def section_number(title):
    m = re.match(r"^\s*((?:\d{1,2}|[A-H])(?:\.\d{1,2}){0,3}|[IVX]{1,5}(?:-[A-Z])?)[.\s]", title + " ")
    return m.group(1) if m else ""


def build_sections(data, texts, labels):
    """Danh sách mục: title, number, level, page (chỉ số PDF), label, end (trang PDF cuối), source."""
    raw, source = [], ""
    if data.get("outline"):
        source = "mục lục (outline) của PDF"
        for level, title, page in data["outline"]:
            if 1 <= page <= len(texts):
                raw.append((level, _recover_number(title, texts[page - 1]), page))
    else:
        heads = data.get("font_headings") or heuristic_headings(texts)
        source = "dò theo cỡ chữ" if data.get("font_headings") else "dò theo mẫu chữ (có thể thiếu hoặc nhầm)"
        seen = set()
        for page, title in heads:
            key = (page, title)
            if key in seen:
                continue
            seen.add(key)
            num = section_number(title)
            level = num.count(".") + 1 if num else 1
            raw.append((level, title, page))
    sections = []
    for idx, (level, title, page) in enumerate(raw):
        end = len(texts)
        for level2, _, page2 in raw[idx + 1:]:
            if level2 <= level:
                end = max(page, page2)
                break
        sections.append({"title": title, "number": section_number(title), "level": level, "page": page,
                         "label": labels[page - 1], "end": end})
    return sections, source


def _recover_number(title, page_text):
    """Mục lục PDF thường không ghi số mục; tìm lại dòng tiêu đề trên trang để lấy số."""
    if section_number(title):
        return title
    want = _squash(title)
    if not want:
        return title
    for s in merged_lines(page_text.splitlines()):
        num = section_number(s)
        if num and _squash(s[len(num):]).startswith(want[:40]):
            return f"{num} {title}"
    return title


def _squash(s):
    return re.sub(r"[\W_]+", "", s.casefold())


# ---------------------------------------------------------------- hình, bảng, công thức, định lý

OBJECT_RE = re.compile(
    r"^\s*(Figure|Fig\.|Table|Algorithm|Listing|Theorem|Lemma|Proposition|Corollary|Definition|Assumption|"
    r"Hình|Bảng|Thuật toán|Định lý|Bổ đề|Mệnh đề|Hệ quả|Định nghĩa)\s*"
    r"((?:[A-Z]\.?)?\d{1,3}(?:\.\d{1,2})?|[IVX]{1,5})\s*[:.|(—–-]?\s*(.{0,140})", re.IGNORECASE)
EQ_RE = re.compile(r"\((\d{1,3}(?:\.\d{1,2})?[a-z]?)\)\s*$")
KIND = {"fig.": "Figure", "hình": "Figure", "bảng": "Table", "thuật toán": "Algorithm", "định lý": "Theorem",
        "bổ đề": "Lemma", "mệnh đề": "Proposition", "hệ quả": "Corollary", "định nghĩa": "Definition"}


def index_objects(texts):
    """Lần xuất hiện ĐẦU TIÊN ở đầu dòng của mỗi hình/bảng/thuật toán/định lý (thường là chú thích hay
    phát biểu), và số công thức đánh ở cuối dòng."""
    objects, seen = [], set()
    eqs = {}
    for i, text in enumerate(texts, 1):
        for ln in text.splitlines():
            m = OBJECT_RE.match(ln)
            if m:
                kind = KIND.get(m.group(1).lower(), m.group(1).capitalize())
                ident = m.group(2).rstrip(".")
                rest = m.group(3).strip()
                # "Table 3 shows…" giữa câu không phải chú thích; chỉ nhận khi có dấu ngăn hoặc chữ hoa.
                after = ln[m.end(2):m.end(2) + 2]
                caption_like = bool(re.match(r"\s*[:.|(—–-]", after)) or (rest[:1].isupper() and len(rest) > 3)
                if caption_like and (kind, ident) not in seen:
                    seen.add((kind, ident))
                    objects.append({"kind": kind, "id": ident, "page": i, "caption": rest[:140]})
            e = EQ_RE.search(ln.strip())
            if e:
                eqs.setdefault(e.group(1), i)
    for num, page in eqs.items():
        objects.append({"kind": "Eq", "id": num, "page": page, "caption": ""})
    return objects


# ---------------------------------------------------------------- dựng cache và in

def build(path):
    data = read_pdf(path)
    texts = [t.replace("\x00", "") for t in data["texts"]]
    labels, label_how = printed_labels(texts, data.get("labels"))
    sections, section_source = build_sections(data, texts, labels)
    chars = [len(t.strip()) for t in texts]
    return {
        "schema": SCHEMA, "source": os.path.abspath(path), "backend": data["backend"],
        "page_count": len(texts), "label_method": label_how, "section_source": section_source,
        "pages": [{"index": i + 1, "label": labels[i], "chars": chars[i], "columns": data["columns"][i],
                   "text": texts[i]} for i in range(len(texts))],
        "sections": sections, "objects": index_objects(texts),
        "scanned_pages": [i + 1 for i, c in enumerate(chars) if c < SCAN_CHARS],
    }


def parse_range(spec, n):
    pages = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            lo, hi = int(a or 1), int(b or n)
            pages.extend(range(lo, hi + 1))
        else:
            pages.append(int(part))
    return [p for p in pages if 1 <= p <= n]


def page_header(p, n):
    return f"===== PAGE {p['index']}/{n} · tr.{p['label']} ====="


def report(cache):
    n = cache["page_count"]
    lines = ["=" * 72, "BÁO CÁO TRÍCH XUẤT", "=" * 72,
             f"File          : {cache['source']}",
             f"Thư viện      : {cache['backend']}",
             f"Số trang PDF  : {n}",
             f"Số trang in   : {cache['label_method']}"]
    total = sum(p["chars"] for p in cache["pages"])
    lines.append(f"Ký tự         : {total} (~{total / max(n, 1):.0f}/trang)")
    scanned = cache["scanned_pages"]
    if scanned and len(scanned) >= 0.5 * n:
        lines.append("CẢNH BÁO      : PDF gần như toàn ảnh (scan). Văn bản trích được không dùng được.")
        lines.append("                Xuất ảnh trang bằng --render rồi đọc bằng mắt (xem references/hard-pdfs.md).")
    elif scanned:
        lines.append(f"Trang ít chữ  : {_ranges(scanned)} (có thể là hình toàn trang hoặc trang scan: --render để xem)")
    two = [p["index"] for p in cache["pages"] if p["columns"] == 2]
    if two:
        lines.append(f"Hai cột       : {len(two)} trang. Thứ tự chữ theo luồng của PDF; đoạn nào đọc thấy lộn thì --render.")
    body_end = next((s["page"] for s in cache["sections"]
                     if re.search(r"references|bibliography|tài liệu tham khảo", s["title"], re.I)), None)
    if body_end:
        lines.append(f"Tài liệu tham khảo bắt đầu ở trang PDF {body_end} (tr.{cache['pages'][body_end - 1]['label']}).")
    lines.append("")
    lines.append("=" * 72)
    lines.append(f"BẢN ĐỒ MỤC (nguồn: {cache['section_source']})")
    lines.append("Cột 1: trang PDF · cột 2: nhãn trang in dùng khi trích dẫn")
    lines.append("=" * 72)
    if not cache["sections"]:
        lines.append("(Không dò được tiêu đề mục: tự xác định mục khi đọc toàn văn.)")
    for s in cache["sections"]:
        indent = "  " * (max(1, s["level"]) - 1)
        span = f"PDF {s['page']:>3}" + (f"–{s['end']:<3}" if s["end"] != s["page"] else "    ")
        lines.append(f"  {span} | tr.{s['label']:<6} {indent}{s['title'][:80]}")
    objs = [o for o in cache["objects"] if o["kind"] != "Eq"]
    if objs:
        lines += ["", "=" * 72, "HÌNH, BẢNG, THUẬT TOÁN, ĐỊNH LÝ (lần xuất hiện đầu ở đầu dòng)", "=" * 72]
        for o in objs:
            label = cache["pages"][o["page"] - 1]["label"]
            lines.append(f"  {o['kind']} {o['id']:<5} PDF {o['page']:>3} | tr.{label:<6} {o['caption'][:70]}")
    eqs = [o for o in cache["objects"] if o["kind"] == "Eq"]
    if eqs:
        shown = ", ".join(f"({o['id']})→tr.{cache['pages'][o['page'] - 1]['label']}" for o in eqs[:60])
        lines += ["", f"CÔNG THỨC ĐÁNH SỐ (dò ở cuối dòng, có thể sót hoặc nhầm): {shown}"
                  + (" …" if len(eqs) > 60 else "")]
    return "\n".join(lines)


def _ranges(nums):
    out, start, prev = [], None, None
    for x in nums:
        if start is None:
            start = prev = x
        elif x == prev + 1:
            prev = x
        else:
            out.append(f"{start}" if start == prev else f"{start}-{prev}")
            start = prev = x
    if start is not None:
        out.append(f"{start}" if start == prev else f"{start}-{prev}")
    return ",".join(out)


def squash_for_search(s):
    """Chuẩn hóa để so chuỗi: NFKC (tách chữ ghép như ﬁ), bỏ dấu câu, khoảng trắng và gạch nối xuống dòng."""
    import unicodedata
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", s).casefold())


def find(cache, needle):
    want = squash_for_search(needle)
    hits = []
    if not want:
        return hits
    head = want[:15]
    for p in cache["pages"]:
        if want in squash_for_search(p["text"]):
            line = next((ln.strip() for ln in p["text"].splitlines() if head in squash_for_search(ln)), "")
            hits.append((p["index"], p["label"], line[:120]))
    return hits


def render(path, pages, out_dir, dpi):
    mupdf = _load_pymupdf()
    if mupdf is None:
        if shutil.which("pdftoppm"):
            made = []
            for p in pages:
                prefix = os.path.join(out_dir, f"page-{p:03d}")
                subprocess.run(["pdftoppm", "-png", "-r", str(dpi), "-f", str(p), "-l", str(p), "-singlefile",
                                path, prefix], check=False)
                made.append(prefix + ".png")
            return made
        sys.stderr.write("Xuất ảnh cần PyMuPDF hoặc pdftoppm. Không có thì đọc trang PDF bằng công cụ đọc file có sẵn.\n")
        sys.exit(2)
    doc = mupdf.open(path)
    made = []
    for p in pages:
        pix = doc[p - 1].get_pixmap(dpi=dpi)
        target = os.path.join(out_dir, f"page-{p:03d}.png")
        pix.save(target)
        made.append(target)
    return made


def load_or_build(pdf, out_dir):
    cache_file = os.path.join(out_dir, "pages.json") if out_dir else ""
    if cache_file and os.path.exists(cache_file):
        with open(cache_file, encoding="utf-8") as fh:
            cache = json.load(fh)
        if cache.get("schema") == SCHEMA and cache.get("source") == os.path.abspath(pdf):
            return cache, False
    return build(pdf), True


def write_cache(cache, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "pages.json"), "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False)
    n = cache["page_count"]
    with open(os.path.join(out_dir, "paper.txt"), "w", encoding="utf-8") as fh:
        for p in cache["pages"]:
            fh.write(page_header(p, n) + "\n" + p["text"].rstrip() + "\n\n")
    with open(os.path.join(out_dir, "outline.txt"), "w", encoding="utf-8") as fh:
        fh.write(report(cache) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Trích bài báo theo trang, kèm bản đồ mục và nhãn trang in.")
    ap.add_argument("pdf")
    ap.add_argument("--out", help="thư mục ghi pages.json, paper.txt, outline.txt và ảnh trang")
    ap.add_argument("--pages", help="in văn bản các trang PDF này, vd 1-8 hoặc 3,5,9-12")
    ap.add_argument("--find", action="append", help="tìm chuỗi (bỏ qua hoa thường, dấu câu, xuống dòng)")
    ap.add_argument("--render", help="xuất PNG các trang PDF này vào --out")
    ap.add_argument("--dpi", type=int, default=110)
    ap.add_argument("--map-only", action="store_true", help="chỉ in báo cáo và bản đồ")
    args = ap.parse_args(argv)

    cache, fresh = load_or_build(args.pdf, args.out)
    if args.out and fresh:
        write_cache(cache, args.out)
    n = cache["page_count"]

    if args.render:
        if not args.out:
            ap.error("--render cần --out")
        for f in render(args.pdf, parse_range(args.render, n), args.out, args.dpi):
            print(f)
        return 0
    if args.find:
        for needle in args.find:
            hits = find(cache, needle)
            print(f"«{needle}»: " + ("không thấy" if not hits else f"{len(hits)} trang"))
            for idx, label, line in hits:
                print(f"  PDF {idx:>3} | tr.{label:<6} {line}")
        return 0
    if args.pages:
        for idx in parse_range(args.pages, n):
            p = cache["pages"][idx - 1]
            print(page_header(p, n))
            print(p["text"].rstrip())
            print()
        return 0

    print(report(cache))
    if args.out:
        print()
        print(f"Đã ghi: {os.path.join(args.out, 'paper.txt')} (toàn văn, có mốc trang), pages.json (cho kiểm neo), "
              f"outline.txt (báo cáo này).")
        print("Đọc toàn văn theo đợt bằng --pages, hoặc đọc paper.txt theo từng khúc. Đừng in cả bài một lần:")
        print("đầu ra quá dài sẽ bị cắt mà không báo, và phần bị cắt coi như chưa đọc.")
        return 0
    if args.map_only:
        return 0
    print()
    print("=" * 72)
    print("TOÀN VĂN THEO TRANG")
    print("=" * 72)
    for p in cache["pages"]:
        print()
        print(page_header(p, n))
        print(p["text"].rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
