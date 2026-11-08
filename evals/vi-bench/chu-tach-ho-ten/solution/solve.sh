#!/bin/bash
# Lời giải mẫu: chuẩn hóa từng chữ, đọc ho_kep.txt mỗi lần gọi, thử họ kép từ nhiều chữ nhất xuống ít chữ nhất.
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/ho_ten.py" <<'PY'
"""Tách họ tên cho phần mềm nhân sự."""
import unicodedata
from pathlib import Path

FILE_HO_KEP = Path(__file__).with_name("ho_kep.txt")


def _chu(s):
    """Tách thành các chữ, mỗi chữ về dạng NFC thường."""
    return [unicodedata.normalize("NFC", w).lower() for w in s.split()]


def _doc_ho_kep():
    ds = []
    for dong in FILE_HO_KEP.read_text(encoding="utf-8").splitlines():
        c = _chu(dong)
        if len(c) >= 2:
            ds.append(c)
    return sorted(ds, key=len, reverse=True)


def _viet_hoa(chu):
    return " ".join(w[:1].upper() + w[1:].lower() for w in chu)


def tach_ho_ten(ho_va_ten):
    """Tách họ tên đầy đủ thành họ, đệm, tên."""
    chu = _chu(ho_va_ten)
    if not chu:
        raise ValueError("họ tên rỗng")
    if len(chu) == 1:
        return {"ho": "", "dem": "", "ten": _viet_hoa(chu)}
    so_ho = 1
    for ho_kep in _doc_ho_kep():
        if len(ho_kep) < len(chu) and chu[:len(ho_kep)] == ho_kep:
            so_ho = len(ho_kep)
            break
    return {"ho": _viet_hoa(chu[:so_ho]), "dem": _viet_hoa(chu[so_ho:-1]), "ten": _viet_hoa(chu[-1:])}


if __name__ == "__main__":
    print(tach_ho_ten("Nguyễn Văn An"))
    print(tach_ho_ten("Tôn Nữ Thị Hạnh"))
PY
