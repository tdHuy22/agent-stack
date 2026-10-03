#!/usr/bin/env python3
"""
extract_paper.py — Trích xuất TOÀN VĂN bài báo theo TRANG, kèm BẢN ĐỒ MỤC.

Mục đích: cho phép phân tích sâu và trích dẫn CHÍNH XÁC tới mục/trang gốc,
áp dụng cho mọi lĩnh vực. Đây là bước đọc "đầy đủ" — KHÔNG bỏ trang nào.

Cách dùng:
    python extract_paper.py <duong-dan-PDF>
    python extract_paper.py <duong-dan-PDF> --map-only   # chỉ in bản đồ mục

Đầu ra (stdout):
  1) BÁO CÁO: số trang, ước lượng text/scan, có cột hay không.
  2) BẢN ĐỒ MỤC: heading phát hiện được -> trang (để định vị nhanh).
  3) TOÀN VĂN theo trang, mỗi trang có mốc:
        ===== PAGE <i>/<N>  (printed: <nhãn-trang-in-trên-giấy>) =====
     Trong đó <i> là chỉ số trang vật lý của PDF (1-based);
     <printed> là số trang IN TRÊN GIẤY nếu dò được (dùng số này khi trích dẫn,
     vì đó là con số người đọc thấy khi mở PDF).

Phụ thuộc: PyMuPDF. Nếu thiếu:
    pip install pymupdf --break-system-packages
"""
import sys
import re
import argparse

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.stderr.write(
        "Thiếu PyMuPDF. Cài bằng:\n    pip install pymupdf --break-system-packages\n"
    )
    sys.exit(2)

# Từ khóa heading phổ biến, đa ngành (EN + một số VI). Dùng để dò mục khi không có đánh số.
HEADING_WORDS = [
    "abstract", "introduction", "background", "related work", "preliminaries",
    "motivation", "problem", "method", "methods", "methodology", "approach",
    "model", "architecture", "framework", "theory", "theoretical", "analysis",
    "design", "implementation", "experiment", "experiments", "evaluation",
    "results", "findings", "ablation", "discussion", "limitations",
    "conclusion", "conclusions", "future work", "references", "bibliography",
    "appendix", "acknowledg",  # acknowledgment/acknowledgement
    # Vietnamese
    "tóm tắt", "giới thiệu", "tổng quan", "phương pháp", "mô hình",
    "thực nghiệm", "kết quả", "thảo luận", "kết luận", "tài liệu tham khảo",
]

# Heading có đánh số: "1", "2.3", "3.1.2" theo sau bởi chữ.
NUM_HEADING = re.compile(r"^\s*(\d+(?:\.\d+){0,3})\s+([A-ZĐ][^\n]{0,80})$")
# Roman numerals đầu dòng: "II. Method"
ROMAN_HEADING = re.compile(r"^\s*([IVX]{1,5})\.\s+([A-ZĐ][^\n]{0,80})$")
# Số trang in trên giấy: một dòng chỉ chứa số (hoặc số kiểu "- 5 -") hoặc số La Mã thường.
PRINTED_NUM = re.compile(r"^\s*[-–—]?\s*(\d{1,4}|[ivxlc]{1,6})\s*[-–—]?\s*$")


def guess_printed_label(text):
    """Dò số trang in trên giấy: xét vài dòng đầu & cuối trang."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    candidates = lines[:2] + lines[-2:]
    for ln in candidates:
        m = PRINTED_NUM.match(ln)
        if m:
            return m.group(1)
    return None


def looks_like_heading(line):
    """Trả về chuỗi heading nếu dòng trông giống tiêu đề mục, ngược lại None."""
    s = line.strip()
    if not s or len(s) > 90:
        return None
    m = NUM_HEADING.match(s)
    if m:
        return s
    m = ROMAN_HEADING.match(s)
    if m:
        return s
    low = s.lower().rstrip(".:")
    # Khớp các heading không đánh số (Abstract, References...).
    for w in HEADING_WORDS:
        if low == w or low.startswith(w + " ") or low == w + "s":
            # tránh nuốt câu văn dài: heading không đánh số thường ngắn
            if len(s.split()) <= 6:
                return s
    # ALL-CAPS ngắn (kiểu "METHODS")
    if s.isupper() and 2 <= len(s) <= 40 and any(c.isalpha() for c in s):
        return s
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--map-only", action="store_true",
                    help="Chỉ in báo cáo + bản đồ mục, không in toàn văn.")
    args = ap.parse_args()

    doc = fitz.open(args.pdf)
    n = doc.page_count

    pages = []          # (idx1, printed_label, text)
    total_chars = 0
    headings = []       # (idx1, printed_label, heading_text)

    for i in range(n):
        page = doc[i]
        text = page.get_text("text")
        total_chars += len(text.strip())
        printed = guess_printed_label(text)
        pages.append((i + 1, printed, text))
        for ln in text.splitlines():
            h = looks_like_heading(ln)
            if h:
                headings.append((i + 1, printed, h))

    avg = total_chars / max(n, 1)
    scanned = avg < 120  # rất ít text/trang => nhiều khả năng là scan ảnh

    # ---- 1) BÁO CÁO ----
    print("=" * 70)
    print("BÁO CÁO TRÍCH XUẤT")
    print("=" * 70)
    print(f"File           : {args.pdf}")
    print(f"Số trang (PDF) : {n}")
    print(f"Ký tự trích    : {total_chars}  (~{avg:.0f}/trang)")
    if scanned:
        print("CẢNH BÁO       : Rất ít văn bản trích được -> có thể là PDF SCAN.")
        print("                 Cần OCR trước (dùng skill 'pdf' để OCR) rồi chạy lại.")
    else:
        print("Loại           : PDF dạng văn bản (trích xuất tốt).")
    print()

    # ---- 2) BẢN ĐỒ MỤC ----
    print("=" * 70)
    print("BẢN ĐỒ MỤC (heading phát hiện -> trang)")
    print("Ghi chú: cột 'tr.in' là số trang in trên giấy nếu dò được.")
    print("=" * 70)
    if not headings:
        print("(Không tự dò được heading rõ ràng — hãy đọc toàn văn để xác định mục.)")
    else:
        seen = set()
        for idx1, printed, h in headings:
            key = (idx1, h)
            if key in seen:
                continue
            seen.add(key)
            label = printed if printed else "?"
            print(f"  [PDF tr.{idx1:>3} | tr.in {label:>4}]  {h}")
    print()

    if args.map_only:
        return

    # ---- 3) TOÀN VĂN THEO TRANG ----
    print("=" * 70)
    print("TOÀN VĂN THEO TRANG")
    print("=" * 70)
    for idx1, printed, text in pages:
        label = printed if printed else "không-dò-được"
        print(f"\n===== PAGE {idx1}/{n}  (printed: {label}) =====")
        print(text.rstrip())


if __name__ == "__main__":
    main()
