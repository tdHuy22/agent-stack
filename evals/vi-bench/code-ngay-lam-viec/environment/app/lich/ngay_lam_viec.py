"""Đếm ngày làm việc giữa hai ngày, có trừ ngày lễ."""
from datetime import datetime, timedelta


def doc_ngay_le(duong_dan):
    """Đọc file ngày lễ, trả tập các ngày (date)."""
    ngay = set()
    with open(duong_dan) as f:
        for dong in f:
            dong = dong.strip()
            if dong:
                ngay.add(datetime.strptime(dong, "%d/%m/%Y").date())
    return ngay


def dem_ngay_lam_viec(tu_ngay, den_ngay, file_le):
    """Số ngày làm việc từ `tu_ngay` tới `den_ngay` (cả hai đầu), ngày viết dạng dd/mm/yyyy."""
    tu = datetime.strptime(tu_ngay, "%d/%m/%Y").date()
    den = datetime.strptime(den_ngay, "%d/%m/%Y").date()
    le = doc_ngay_le(file_le)
    dem = 0
    ngay = tu
    while ngay < den:
        if ngay.weekday() < 6 and ngay not in le:
            dem += 1
        ngay += timedelta(days=1)
    return dem
