#!/bin/bash
# Lời giải mẫu: đọc file lễ bằng utf-8-sig, tính ngày nghỉ bù, đếm ngày.
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/lich/ngay_lam_viec.py" <<'PY'
"""Đếm ngày làm việc giữa hai ngày, có trừ ngày lễ và ngày nghỉ bù."""
from datetime import datetime, timedelta


def _doc_ngay(chuoi):
    return datetime.strptime(chuoi.strip(), "%d/%m/%Y").date()


def doc_ngay_le(duong_dan):
    """Đọc file ngày lễ, trả tập các ngày (date)."""
    ngay = set()
    with open(duong_dan, encoding="utf-8-sig") as f:
        for dong in f:
            dong = dong.strip()
            if not dong or dong.startswith("#"):
                continue
            ngay.add(_doc_ngay(dong.split(None, 1)[0]))
    return ngay


def ngay_nghi(le):
    """Tập ngày nghỉ gồm ngày lễ và ngày nghỉ bù cho lễ rơi vào cuối tuần."""
    nghi = set(le)
    bu = set()
    for d in sorted(le):
        if d.weekday() < 5:
            continue
        x = d + timedelta(days=1)
        while x.weekday() >= 5 or x in le or x in bu:
            x += timedelta(days=1)
        bu.add(x)
    return nghi | bu


def dem_ngay_lam_viec(tu_ngay, den_ngay, file_le):
    """Số ngày làm việc từ `tu_ngay` tới `den_ngay` (cả hai đầu), ngày viết dạng dd/mm/yyyy."""
    tu = _doc_ngay(tu_ngay)
    den = _doc_ngay(den_ngay)
    if tu > den:
        raise ValueError("tu_ngay sau den_ngay")
    nghi = ngay_nghi(doc_ngay_le(file_le))
    dem = 0
    ngay = tu
    while ngay <= den:
        if ngay.weekday() < 5 and ngay not in nghi:
            dem += 1
        ngay += timedelta(days=1)
    return dem
PY
