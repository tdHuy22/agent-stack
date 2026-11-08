"""In danh sách lớp."""


def sap_xep(ds):
    """Xếp họ tên theo thứ tự từ điển tiếng Việt."""
    return sorted(ds)


if __name__ == "__main__":
    for ten in sap_xep(["Trần Văn Bình", "Nguyễn Thị Ánh", "Lê Minh Đức", "Phạm Anh"]):
        print(ten)
