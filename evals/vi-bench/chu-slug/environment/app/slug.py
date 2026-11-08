"""Tạo slug cho đường dẫn bài viết."""


def tao_slug(tieu_de, toi_da=60):
    """Đổi tiêu đề bài viết thành slug dùng trong URL."""
    return tieu_de.lower().replace(" ", "-")[:toi_da]


if __name__ == "__main__":
    for tieu_de in ("Hướng dẫn cài đặt Python", "Đường Điện Biên Phủ"):
        print(tao_slug(tieu_de))
