#!/bin/bash
# Lời giải mẫu: tính bằng Fraction, làm tròn nửa lên từng bước, chuẩn hóa tên nhóm.
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/hoa_don/tinh_hoa_don.py" <<'PY'
"""Tính hóa đơn bán hàng nhiều dòng, có VAT."""
import re
import unicodedata
from fractions import Fraction

NHOM_VAT_10 = ["Viễn thông", "Tài chính", "Bất động sản", "Hóa chất", "Khai khoáng"]


def _khoa_nhom(nhom):
    s = unicodedata.normalize("NFC", nhom or "").lower()
    s = " ".join(s.split())
    return re.sub(r"\bhoá\b", "hóa", s)


_NHOM_10 = {_khoa_nhom(n) for n in NHOM_VAT_10}


def thue_suat(nhom):
    """Thuế suất VAT của một nhóm hàng (0.08 hoặc 0.1)."""
    if _khoa_nhom(nhom) in _NHOM_10:
        return 0.1
    return 0.08


def _nua_len(x):
    """Làm tròn nửa lên một Fraction không âm."""
    return int(x + Fraction(1, 2))


def _so(gia_tri):
    if isinstance(gia_tri, str):
        gia_tri = gia_tri.strip().replace(".", "").replace(",", ".")
    return Fraction(str(gia_tri))


def tinh_hoa_don(dong_hang):
    """Nhận danh sách dòng hàng (dict), trả dict gồm tien_hang, vat, tong (đồng)."""
    tien_hang = 0
    vat = 0
    for d in dong_hang:
        don_gia = d["don_gia"]
        so_luong = _so(d["so_luong"])
        giam = _so(d.get("giam_gia", 0))
        if don_gia < 0 or so_luong <= 0 or not 0 <= giam <= 100:
            raise ValueError("dòng hàng không hợp lệ")
        thanh_tien = _nua_len(don_gia * so_luong)
        sau_giam = thanh_tien - _nua_len(thanh_tien * giam / 100)
        ty_le = Fraction(10, 100) if thue_suat(d.get("nhom")) == 0.1 else Fraction(8, 100)
        tien_hang += sau_giam
        vat += _nua_len(sau_giam * ty_le)
    return {"tien_hang": tien_hang, "vat": vat, "tong": tien_hang + vat}
PY
