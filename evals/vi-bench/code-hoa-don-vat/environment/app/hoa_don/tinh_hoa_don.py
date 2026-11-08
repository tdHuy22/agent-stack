"""Tính hóa đơn bán hàng nhiều dòng, có VAT."""

NHOM_VAT_10 = ["Viễn thông", "Tài chính", "Bất động sản", "Hóa chất", "Khai khoáng"]


def thue_suat(nhom):
    """Thuế suất VAT của một nhóm hàng (0.08 hoặc 0.1)."""
    if nhom in NHOM_VAT_10:
        return 0.1
    return 0.08


def tinh_hoa_don(dong_hang):
    """Nhận danh sách dòng hàng (dict), trả dict gồm tien_hang, vat, tong (đồng)."""
    tien_hang = 0
    for d in dong_hang:
        tien_hang += d["don_gia"] * d["so_luong"]
    vat = round(tien_hang * 0.1)
    return {"tien_hang": round(tien_hang), "vat": vat, "tong": round(tien_hang) + vat}
