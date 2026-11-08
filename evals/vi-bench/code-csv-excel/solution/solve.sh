#!/bin/bash
# Lời giải mẫu: đọc bằng csv với utf-8-sig, tìm cột theo tiêu đề, đọc số kiểu Việt Nam bằng Decimal.
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/bao_cao/doc_csv.py" <<'PY'
"""Đọc file CSV doanh thu xuất từ Excel và gộp doanh thu theo tháng."""
import csv
import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

_DON_VI = re.compile(r"\s*(₫|đ|vnđ|vnd)$", re.I)
_SO = re.compile(r"^\d+(\.\d{3})*(,\d+)?$|^\d+(,\d+)?$")


def _khoa(tieu_de):
    return " ".join(unicodedata.normalize("NFC", tieu_de).split()).casefold()


def _doc_so(o):
    s = unicodedata.normalize("NFC", o).replace(" ", " ").strip()
    s = _DON_VI.sub("", s).strip()
    am = False
    if s.startswith("(") and s.endswith(")"):
        am, s = True, s[1:-1].strip()
    elif s.startswith("-"):
        am, s = True, s[1:].strip()
    if not _SO.match(s):
        raise ValueError(f"không đọc được số tiền: {o!r}")
    so = Decimal(s.replace(".", "").replace(",", "."))
    return -so if am else so


def _doc_thang(o):
    phan_ngay = o.split()[0]
    d = datetime.strptime(phan_ngay, "%d/%m/%Y")
    return f"{d.year:04d}-{d.month:02d}"


def tong_doanh_thu_theo_thang(duong_dan):
    """Trả dict {"yyyy-mm": tổng doanh thu (Decimal)} từ file CSV `duong_dan`."""
    tong = defaultdict(Decimal)
    with open(duong_dan, encoding="utf-8-sig", newline="") as f:
        doc = csv.reader(f, delimiter=";")
        tieu_de = next(doc, None) or []
        khoa = [_khoa(t) for t in tieu_de]
        try:
            c_ngay = khoa.index("ngày")
            c_tien = next(i for i, k in enumerate(khoa) if k in ("doanh thu", "doanh thu (đồng)"))
        except (ValueError, StopIteration):
            raise ValueError("thiếu cột Ngày hoặc Doanh thu") from None
        for dong in doc:
            if len(dong) <= max(c_ngay, c_tien):
                dong = dong + [""] * (max(c_ngay, c_tien) + 1 - len(dong))
            if not dong[c_ngay].strip():
                continue
            if not dong[c_tien].strip():
                continue
            thang = _doc_thang(dong[c_ngay])
            tong[thang] += _doc_so(dong[c_tien])
    return dict(tong)
PY
