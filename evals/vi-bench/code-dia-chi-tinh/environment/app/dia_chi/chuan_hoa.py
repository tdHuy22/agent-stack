"""Chuẩn hóa tên tỉnh, thành trong địa chỉ khách nhập tay."""


def _tai_bang():
    bang = []
    with open("bi_danh.tsv", encoding="utf-8") as f:
        for dong in f:
            if dong.startswith("#") or not dong.strip():
                continue
            chuan, bi_danh = dong.rstrip("\n").split("\t")
            bang.append((chuan, bi_danh.split("|")))
    return bang


BANG = _tai_bang()


def chuan_hoa_tinh(dia_chi):
    """Thay tên tỉnh, thành viết tắt hay viết sai trong `dia_chi` bằng tên chuẩn."""
    for chuan, bi_danh in BANG:
        for b in bi_danh:
            dia_chi = dia_chi.replace(b, chuan)
    return dia_chi
