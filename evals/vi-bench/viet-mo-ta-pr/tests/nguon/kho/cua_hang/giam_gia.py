"""Mã giảm giá."""
from datetime import date

# mã: (loại, giá trị, trần giảm tối đa, hạn dùng đến hết ngày)
MA_GIAM = {
    "GIAM10": ("phan_tram", 10, 30_000, date(2026, 12, 31)),
    "BANMOI": ("phan_tram", 20, 50_000, date(2026, 11, 30)),
    "LAN1": ("co_dinh", 100_000, None, date(2026, 10, 31)),
}


def ma_con_han(ma, hom_nay):
    """Mã có tồn tại và còn dùng được vào ngày hom_nay không."""
    if ma not in MA_GIAM:
        return False
    return hom_nay <= MA_GIAM[ma][3]


def ap_dung_ma(tien_hang, ma, hom_nay):
    """Trả về số tiền được giảm: 0 nếu mã sai hay hết hạn, không bao giờ vượt tiền hàng."""
    if not ma_con_han(ma, hom_nay):
        return 0
    loai, gia_tri, tran, _han = MA_GIAM[ma]
    if loai == "phan_tram":
        giam = tien_hang * gia_tri // 100
        if tran is not None:
            giam = min(giam, tran)
    else:
        giam = gia_tri
    return min(giam, tien_hang)
