"""Đọc file CSV doanh thu xuất từ Excel và gộp doanh thu theo tháng."""
import csv
from collections import defaultdict
from decimal import Decimal


def tong_doanh_thu_theo_thang(duong_dan):
    """Trả dict {"yyyy-mm": tổng doanh thu (Decimal)} từ file CSV `duong_dan`."""
    tong = defaultdict(Decimal)
    with open(duong_dan, encoding="utf-8") as f:
        for dong in csv.DictReader(f, delimiter=";"):
            ngay = dong["Ngày"]
            thang = ngay[6:10] + "-" + ngay[3:5]
            tong[thang] += Decimal(dong["Doanh thu"].replace(",", "."))
    return dict(tong)
