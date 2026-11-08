"""Tính thuế thu nhập cá nhân (TNCN) hằng tháng cho người làm công ăn lương."""

GIAM_TRU_BAN_THAN = 11000000
GIAM_TRU_PHU_THUOC = 4400000

# (trần của bậc, thuế suất)
BIEU_THUE = [
    (5000000, 0.05),
    (10000000, 0.10),
    (18000000, 0.15),
    (32000000, 0.20),
    (52000000, 0.25),
    (80000000, 0.30),
    (float("inf"), 0.35),
]


def tinh_thue_tncn(luong_gop, so_nguoi_phu_thuoc=0):
    """Trả thuế TNCN phải nộp trong tháng (đồng) từ lương gộp `luong_gop` (đồng)."""
    bao_hiem = luong_gop * 0.105
    thu_nhap = luong_gop - bao_hiem - GIAM_TRU_BAN_THAN
    if thu_nhap <= 0:
        return 0
    for tran, ty_le in BIEU_THUE:
        if thu_nhap <= tran:
            return round(thu_nhap * ty_le)
