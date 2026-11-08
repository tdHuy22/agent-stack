"""Chia tiền ăn nhóm: ai trả trước thì được hoàn lại bằng chuyển khoản từ những người còn lại."""


def chia_tien(khoan_tra, thanh_vien):
    """Trả danh sách chuyển khoản [(người chuyển, người nhận, số tiền đồng)].

    `khoan_tra`: danh sách (tên, số tiền) những khoản đã trả; `thanh_vien`: danh sách tên mọi người cùng chia.
    """
    tong = sum(tien for _, tien in khoan_tra)
    phan = round(tong / len(thanh_vien) / 1000) * 1000
    da_tra = {}
    for ten, tien in khoan_tra:
        da_tra[ten] = tien
    so_du = {ten: da_tra.get(ten, 0) - phan for ten in thanh_vien}
    nguoi_no = [ten for ten in thanh_vien if so_du[ten] < 0]
    nguoi_nhan = [ten for ten in thanh_vien if so_du[ten] > 0]
    ket_qua = []
    for no in nguoi_no:
        for nhan in nguoi_nhan:
            if so_du[no] == 0:
                break
            chuyen = min(-so_du[no], so_du[nhan])
            if chuyen > 0:
                ket_qua.append((no, nhan, chuyen))
                so_du[no] += chuyen
                so_du[nhan] -= chuyen
    return ket_qua
