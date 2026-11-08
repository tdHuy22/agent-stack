"""Đọc ngày viết tự do trong đơn từ."""
from datetime import datetime


def doc_ngay(chuoi, hom_nay=None):
    """Đổi ngày viết tự do thành chuỗi ISO 'YYYY-MM-DD'."""
    return datetime.strptime(chuoi.strip(), "%d/%m/%Y").date().isoformat()


if __name__ == "__main__":
    print(doc_ngay("7/11/2026"))
