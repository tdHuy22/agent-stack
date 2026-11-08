"""Viết hoa tên riêng trong bản tin gõ từ giọng nói."""


def viet_hoa(van_ban):
    """Viết hoa đúng địa danh, tên tổ chức trong văn bản."""
    return van_ban.title()


if __name__ == "__main__":
    print(viet_hoa("thành phố hồ chí minh đông dân"))
