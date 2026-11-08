"""Tính tiền làm thêm giờ trong tháng."""
from gio_cong import so_phut
from he_so import HE_SO, loai_ngay


def luong_gio(luong_thang):
    """Tiền lương một giờ làm việc bình thường."""
    return luong_thang / 30 / 8


def tinh_tien_lam_them(luong_thang, ca_lam, ngay_le=()):
    """Tổng tiền làm thêm giờ (đồng) của các ca trong `ca_lam`, mỗi ca là (ngay, bat_dau, ket_thuc)."""
    tong = 0
    for ngay, bat_dau, ket_thuc in ca_lam:
        gio = so_phut(bat_dau, ket_thuc) / 60
        tong += round(gio * luong_gio(luong_thang) * HE_SO[loai_ngay(ngay, ngay_le)])
    return tong
