#!/bin/bash
# Lời giải mẫu: chia nhóm ba chữ số, nhóm đầu bỏ hàng trăm 0, các nhóm sau đọc đủ "không trăm"; phần tỷ đọc đệ quy.
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/doc_so.py" <<'PY'
"""Đọc số tiền thành chữ cho phiếu chi."""
import re

CHU = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
GIOI_HAN = 10 ** 15


def _doc_nhom(n, dau):
    """Đọc một nhóm 1..999; dau: đây là nhóm đứng đầu của cả số."""
    tram, chuc, dv = n // 100, n // 10 % 10, n % 10
    out = []
    doc_tram = tram > 0 or not dau
    if doc_tram:
        out.append(CHU[tram] + " trăm")
    if chuc == 1:
        out.append("mười")
    elif chuc >= 2:
        out.append(CHU[chuc] + " mươi")
    elif dv and doc_tram:
        out.append("linh")
    if dv:
        if dv == 1 and chuc >= 2:
            out.append("mốt")
        elif dv == 4 and chuc >= 2:
            out.append("tư")
        elif dv == 5 and chuc >= 1:
            out.append("lăm")
        else:
            out.append(CHU[dv])
    return " ".join(out)


def _doc_cum(n, da_co_truoc):
    """Đọc n (< 10^9) thành các nhóm triệu, nghìn, đơn vị."""
    phan = []
    for co_so, ten in ((10 ** 6, " triệu"), (10 ** 3, " nghìn"), (1, "")):
        g = n // co_so % 1000
        if g:
            phan.append(_doc_nhom(g, not phan and not da_co_truoc) + ten)
    return " ".join(phan)


def doc_so_tien(n):
    """Đọc số tiền (số nguyên đồng) thành chữ, ví dụ 24 -> 'Hai mươi tư đồng'."""
    if isinstance(n, str):
        if not re.fullmatch(r"\d{1,3}(\.\d{3})*|\d+", n):
            raise ValueError(f"không đọc được thành số: {n!r}")
        n = int(n.replace(".", ""))
    if isinstance(n, bool) or not isinstance(n, int) or n < 0 or n >= GIOI_HAN:
        raise ValueError(f"số tiền không hợp lệ: {n!r}")
    if n == 0:
        return "Không đồng"
    ty, du = divmod(n, 10 ** 9)
    phan = []
    if ty:
        phan.append(_doc_cum(ty, False) + " tỷ")
    if du:
        phan.append(_doc_cum(du, bool(ty)))
    chu = " ".join(phan)
    return chu[0].upper() + chu[1:] + " đồng"


if __name__ == "__main__":
    for so in (0, 24, 1250005, 2000000000):
        print(so, "->", doc_so_tien(so))
PY
