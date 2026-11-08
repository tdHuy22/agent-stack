"""Đọc giờ trong ca làm việc."""


def doc_gio(chuoi):
    """Đổi "HH:MM" thành số phút tính từ 00:00."""
    gio, phut = chuoi.split(":")
    return int(gio) * 60 + int(phut)


def so_phut(bat_dau, ket_thuc):
    """Số phút của một ca từ giờ `bat_dau` tới giờ `ket_thuc` (dạng "HH:MM")."""
    return doc_gio(ket_thuc) - doc_gio(bat_dau)
