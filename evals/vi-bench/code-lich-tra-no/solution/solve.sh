#!/bin/bash
# Lời giải mẫu: Fraction cho lãi, chia nguyên cho gốc, dồn phần lẻ vào tháng cuối.
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/vay/lich_tra_no.py" <<'PY'
"""Lập lịch trả nợ theo dư nợ giảm dần cho khoản vay."""
import re
from fractions import Fraction


def _doc_tien(gia_tri):
    if isinstance(gia_tri, str):
        s = gia_tri.strip()
        if not re.fullmatch(r"\d{1,3}(\.\d{3})+|\d+", s):
            raise ValueError(f"không đọc được số tiền: {gia_tri!r}")
        return int(s.replace(".", ""))
    if isinstance(gia_tri, bool) or int(gia_tri) != gia_tri:
        raise ValueError(f"số tiền phải là số nguyên đồng: {gia_tri!r}")
    return int(gia_tri)


def _doc_lai_suat(gia_tri):
    if isinstance(gia_tri, str):
        s = gia_tri.strip()
        if not re.fullmatch(r"\d+(,\d+)?", s):
            raise ValueError(f"không đọc được lãi suất: {gia_tri!r}")
        return Fraction(s.replace(",", "."))
    return Fraction(str(gia_tri))


def lap_lich_tra_no(so_tien_vay, lai_suat_nam, so_thang):
    """Trả danh sách mỗi tháng một dict gồm ky, goc, lai, tong, du_no_cuoi (đồng)."""
    vay = _doc_tien(so_tien_vay)
    lai_suat = _doc_lai_suat(lai_suat_nam)
    if vay <= 0 or lai_suat < 0 or so_thang < 1 or int(so_thang) != so_thang:
        raise ValueError("tham số không hợp lệ")
    so_thang = int(so_thang)
    ty_le_thang = lai_suat / 100 / 12
    goc_deu = vay // so_thang
    du_no = vay
    lich = []
    for ky in range(1, so_thang + 1):
        goc = du_no if ky == so_thang else goc_deu
        lai = int(du_no * ty_le_thang + Fraction(1, 2))
        du_no_cuoi = du_no - goc
        lich.append({"ky": ky, "goc": goc, "lai": lai, "tong": goc + lai, "du_no_cuoi": du_no_cuoi})
        du_no = du_no_cuoi
    return lich
PY
