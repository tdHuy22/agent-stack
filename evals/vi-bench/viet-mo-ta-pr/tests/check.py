"""Chấm viet-mo-ta-pr: mô tả PR đúng tên file, hàm, test, ngưỡng cũ/mới, issue và ví dụ kiểm tay.

Từ thay-doi.diff và mã trong kho/: file đổi giam_gia.py, don_hang.py, cau_hinh.py, test_giam_gia.py; hàm thêm ma_con_han, sửa ap_dung_ma và
tinh_tong, xóa tinh_giam_gia_cu; ngưỡng miễn phí ship MIEN_PHI_SHIP_TU 300.000 lên 500.000; test mới test_ma_het_han,
test_giam_khong_vuot_tien_hang, test_phi_ship_khong_tinh_giam; đóng #87 (tổng âm, mã hết hạn, giảm cả phí ship).
Ví dụ kiểm tay ngày 10/11/2026, tiền hàng 420.000, ship 25.000, GIAM10: 420.000 < 500.000 nên vẫn tính ship 25.000; giảm min(10% = 42.000,
trần 30.000) = 30.000; tổng 420.000 - 30.000 + 25.000 = 415.000 (đã chạy thật tinh_tong). Số sai hay gặp: 390.000 (ngưỡng cũ 300.000 nên
miễn ship), 403.000 (quên trần 30.000), 387.000 (giảm tính cả ship, kiểu cũ).

Tiêu đề đánh số kiểu "## 1. Thay đổi" được; "#" chỉ bắt khi dính liền số (#87). Số tiền chấp nhận "415.000đ" hay "415 nghìn".

Fixture (solution/dat-khac, solution/truot) chạy trong selftest.py:
  ĐẠT    1 bảng hai cột cho mục Thay đổi, tiêu đề cấp ba, "Đóng #87" cuối mục Lý do; 2 tiêu đề đánh số "## 1. Thay đổi", lệnh test trong khối code;
         3 mở bằng câu sáo "Trong bối cảnh" và kết "Tóm lại" nhưng đủ tên, số liệu (văn AI không còn làm trượt)
  TRƯỢT  1 bịa hàm `kiem_tra_ma`, `tinh_giam_gia` và file `khuyen_mai.py`, thiếu hầu hết mục; 2 ví dụ ra 390.000, thiếu ngưỡng, #87, hàm xóa và một test;
         3 đủ mục Thay đổi và Lý do nhưng thiếu mục Cách kiểm và tên ba test mới
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402

NAMES = ["Thay đổi", "Lý do", "Cách kiểm"]
TESTS = ["test_ma_het_han", "test_giam_khong_vuot_tien_hang", "test_phi_ship_khong_tinh_giam"]
OK_WORDS = {"python3", "unittest", "pytest", "None", "True", "False", "date", "README", "MD"}


def sections(text, names):
    lines = text.split("\n")
    pos = {}
    for i, ln in enumerate(lines):
        h = re.sub(r"^[\s#*\-\d.)]+|[\s*:]+$", "", ln).strip().lower()
        for n in names:
            if h == n.lower() and n not in pos:
                pos[n] = i
    order = sorted(pos.items(), key=lambda kv: kv[1])
    out = {}
    for k, (n, i) in enumerate(order):
        end = order[k + 1][1] if k + 1 < len(order) else len(lines)
        out[n] = "\n".join(lines[i + 1:end])
    return out, [n for n, _ in order]


def known_names():
    # diff, mã và issue gốc chép sẵn trong tests/nguon/, không đọc từ /app (agent có thể sửa hay xóa)
    root = Path(__file__).resolve().parent / "nguon"
    words, files = set(), set()
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in (".py", ".diff", ".md", ".txt"):
            files.add(p.name)
            try:
                words.update(re.findall(r"[A-Za-z_][A-Za-z_0-9]*", p.read_text(encoding="utf-8")))
            except (OSError, UnicodeDecodeError):
                pass
    return words, files


def main():
    text = vncheck.read("MO-TA-PR.md")
    if text is None:
        vncheck.finish(["chưa có /app/MO-TA-PR.md"])
    errs = vncheck.writing_checks(text, max_words=250, min_words=70)
    sec, order = sections(text, NAMES)
    miss = [n for n in NAMES if n not in sec]
    if miss:
        errs.append("thiếu mục: " + ", ".join(miss))
    elif order != NAMES:
        errs.append("ba mục không đúng thứ tự Thay đổi, Lý do, Cách kiểm")
    flat = vncheck.norm_num(text)
    if "Thay đổi" in sec:
        s = sec["Thay đổi"]
        for fn in ("giam_gia.py", "don_hang.py", "cau_hinh.py", "test_giam_gia.py"):
            if fn not in s:
                errs.append(f"mục Thay đổi thiếu tên file {fn}")
        for fn in ("ap_dung_ma", "ma_con_han", "tinh_tong", "tinh_giam_gia_cu"):
            if fn not in s:
                errs.append(f"mục Thay đổi thiếu hàm {fn}")
        if not re.search(r"tinh_giam_gia_cu[^\n]{0,160}(xóa|bỏ|gỡ|loại)|(xóa|bỏ|gỡ|loại)[^\n]{0,160}tinh_giam_gia_cu", s, re.I):
            errs.append("không nói tinh_giam_gia_cu bị xóa")
        ns = vncheck.norm_num(s)
        if not all(vncheck.has_number(ns, n) or re.search(rf"(?<!\d){n // 1000}\s*(nghìn|ngàn|k)\b", ns, re.I) for n in (300000, 500000)):
            errs.append("thiếu ngưỡng miễn phí ship cũ 300.000 và mới 500.000")
    for t in TESTS:
        if t not in text:
            errs.append(f"thiếu tên test mới {t}")
    if "Lý do" in sec:
        s = sec["Lý do"]
        if not re.search(r"#87(?!\d)", s):
            errs.append("mục Lý do thiếu #87")
        if not re.search(r"(?<!\w)âm(?!\w)", s):
            errs.append("mục Lý do không nói lỗi tổng tiền bị âm")
        if not re.search(r"hết hạn", s):
            errs.append("mục Lý do không nói lỗi mã hết hạn vẫn dùng được")
        if not re.search(r"ship|vận chuyển", s, re.I):
            errs.append("mục Lý do không nói lỗi giảm cả phí ship")
    for m in re.finditer(r"(?<!#)#(\d+)", text):
        if m.group(1) != "87":
            errs.append(f"có số # lạ: #{m.group(1)}")
    if "Cách kiểm" in sec:
        s = sec["Cách kiểm"]
        if not re.search(r"unittest\s+discover\s+-s\s+tests", s):
            errs.append("mục Cách kiểm thiếu lệnh chạy test của dự án (python3 -m unittest discover -s tests)")
        if not (vncheck.has_number(s, 415000) or re.search(r"(?<!\d)415\s*(nghìn|ngàn|k)\b", s, re.I)):
            errs.append("ví dụ kiểm tay thiếu tổng đúng 415.000đ")
    for n, why in ((390000, "ngưỡng cũ 300.000 nên miễn ship"), (403000, "quên trần giảm 30.000"), (387000, "giảm tính cả phí ship")):
        if vncheck.has_number(text, n):
            errs.append(f"có số sai {n} ({why})")
    # tên trong dấu huyền phải có thật
    words, files = known_names()
    for tok in re.findall(r"`([^`\n]+)`", text):
        t = tok.strip()
        if re.fullmatch(r"[\w./]+\.(py|md|txt|diff)", t):
            if Path(t).name not in files:
                errs.append(f"nhắc file không có: `{t}`")
            continue
        if not re.fullmatch(r"[A-Za-z_][\w.]*(\(.*\))?", t):
            continue
        base = re.sub(r"\(.*\)$", "", t)
        for part in re.split(r"[./]", base):
            if len(part) > 2 and part not in words and part not in OK_WORDS:
                errs.append(f"nhắc tên không có trong diff và mã: `{t}`")
                break
    vncheck.finish(errs)


main()
