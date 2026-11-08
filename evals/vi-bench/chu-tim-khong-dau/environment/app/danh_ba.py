"""Tìm người trong danh bạ công ty."""


def tim(danh_ba, truy_van):
    """Trả về các tên trong danh bạ khớp với truy vấn."""
    q = truy_van.lower()
    return [ten for ten in danh_ba if q in ten.lower()]


if __name__ == "__main__":
    ds = ["Nguyễn Văn An", "Lê Thị Ân", "Hoàng Văn Dũng"]
    print(tim(ds, "an"))
