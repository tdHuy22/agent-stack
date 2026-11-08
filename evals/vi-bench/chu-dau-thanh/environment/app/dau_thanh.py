"""Chuẩn hóa vị trí dấu thanh trong văn bản trước khi in."""

DOI = {"hoà": "hòa", "hoá": "hóa", "thuỷ": "thủy", "tuỳ": "tùy"}


def chuan_hoa_dau(van_ban):
    """Đổi dấu thanh kiểu cũ sang kiểu mới."""
    for cu, moi in DOI.items():
        van_ban = van_ban.replace(cu, moi)
    return van_ban


if __name__ == "__main__":
    print(chuan_hoa_dau("Hoà bình, thuỷ điện"))
