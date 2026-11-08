"""Hệ số tiền lương làm thêm giờ theo loại ngày."""
from datetime import datetime

HE_SO = {"thuong": 1.5, "cuoi_tuan": 2.0, "le": 2.0}


def loai_ngay(ngay, ngay_le):
    """Loại của ngày `ngay` (dd/mm/yyyy): "thuong", "cuoi_tuan" hoặc "le"."""
    d = datetime.strptime(ngay, "%d/%m/%Y").date()
    if d.weekday() == 6:
        return "cuoi_tuan"
    if ngay in ngay_le:
        return "le"
    return "thuong"
