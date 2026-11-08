"""Lập lịch trả nợ theo dư nợ giảm dần cho khoản vay."""


def lap_lich_tra_no(so_tien_vay, lai_suat_nam, so_thang):
    """Trả danh sách mỗi tháng một dict gồm ky, goc, lai, tong, du_no_cuoi (đồng)."""
    goc_thang = round(so_tien_vay / so_thang)
    du_no = so_tien_vay
    lich = []
    for ky in range(1, so_thang + 1):
        lai = round(du_no * lai_suat_nam / 100 / 12)
        du_no -= goc_thang
        lich.append({"ky": ky, "goc": goc_thang, "lai": lai, "tong": goc_thang + lai, "du_no_cuoi": du_no})
    return lich
