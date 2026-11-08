#!/bin/bash
# Lời giải mẫu: sửa cả ba file (tách ca qua nửa đêm, loại ngày, lương giờ chia 26, làm tròn một lần).
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/luong/gio_cong.py" <<'PY'
"""Đọc giờ trong ca làm việc."""
import re

_GIO = re.compile(r"^(\d{1,2}):(\d{2})$")


def doc_gio(chuoi):
    """Đổi "HH:MM" thành số phút tính từ 00:00."""
    m = _GIO.match(chuoi.strip())
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise ValueError(f"giờ không hợp lệ: {chuoi!r}")
    return int(m.group(1)) * 60 + int(m.group(2))


def tach_ca(bat_dau, ket_thuc):
    """Tách một ca thành [(số ngày lệch so với ngày bắt đầu, số phút)]: phần trước và sau nửa đêm."""
    b, k = doc_gio(bat_dau), doc_gio(ket_thuc)
    if b == k:
        raise ValueError("giờ bắt đầu và kết thúc bằng nhau")
    if k > b:
        return [(0, k - b)]
    phan = [(0, 24 * 60 - b)]
    if k > 0:
        phan.append((1, k))
    return phan


def so_phut(bat_dau, ket_thuc):
    """Số phút của một ca từ giờ `bat_dau` tới giờ `ket_thuc` (dạng "HH:MM")."""
    return sum(p for _, p in tach_ca(bat_dau, ket_thuc))
PY
cat > "$APP/luong/he_so.py" <<'PY'
"""Hệ số tiền lương làm thêm giờ theo loại ngày."""
from datetime import datetime
from fractions import Fraction

HE_SO = {"thuong": Fraction(3, 2), "cuoi_tuan": Fraction(2), "le": Fraction(3)}


def doc_ngay(chuoi):
    """Đổi chuỗi dd/mm/yyyy thành date."""
    return datetime.strptime(chuoi.strip(), "%d/%m/%Y").date()


def loai_ngay(ngay, ngay_le):
    """Loại của ngày `ngay` (dd/mm/yyyy hoặc date): "thuong", "cuoi_tuan" hoặc "le"."""
    d = ngay if hasattr(ngay, "weekday") else doc_ngay(ngay)
    le = {x if hasattr(x, "weekday") else doc_ngay(x) for x in ngay_le}
    if d in le:
        return "le"
    if d.weekday() >= 5:
        return "cuoi_tuan"
    return "thuong"
PY
cat > "$APP/luong/tinh_luong.py" <<'PY'
"""Tính tiền làm thêm giờ trong tháng."""
from datetime import timedelta
from fractions import Fraction

from gio_cong import tach_ca
from he_so import HE_SO, doc_ngay, loai_ngay


def luong_gio(luong_thang):
    """Tiền lương một giờ làm việc bình thường (chính xác, dạng phân số)."""
    return Fraction(luong_thang) / 26 / 8


def tinh_tien_lam_them(luong_thang, ca_lam, ngay_le=()):
    """Tổng tiền làm thêm giờ (đồng) của các ca trong `ca_lam`, mỗi ca là (ngay, bat_dau, ket_thuc)."""
    if luong_thang < 0:
        raise ValueError("lương tháng âm")
    ngay_le = list(ngay_le)
    tong = Fraction(0)
    for ngay, bat_dau, ket_thuc in ca_lam:
        d0 = doc_ngay(ngay)
        for lech, phut in tach_ca(bat_dau, ket_thuc):
            he = HE_SO[loai_ngay(d0 + timedelta(days=lech), ngay_le)]
            tong += luong_gio(luong_thang) * Fraction(phut, 60) * he
    return int(tong + Fraction(1, 2))
PY
