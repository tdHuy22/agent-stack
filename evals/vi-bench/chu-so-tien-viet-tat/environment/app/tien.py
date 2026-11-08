"""Đọc số tiền viết tắt trong tin nhắn đặt hàng."""
import re


def doc_tien(chuoi):
    """Đổi số tiền viết tắt ('500k', '1tr5', '2,5 triệu') thành số đồng."""
    m = re.fullmatch(r"([\d.,]+)\s*(k|tr|triệu)?", chuoi.strip().lower())
    so = float(m.group(1).replace(",", "."))
    he_so = {"k": 1000, "tr": 10 ** 6, "triệu": 10 ** 6, None: 1}[m.group(2)]
    return int(so * he_so)


if __name__ == "__main__":
    print(doc_tien("500k"))
