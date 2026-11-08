#!/bin/bash
# Lời giải mẫu: khóa xếp theo bảng chữ cái tiếng Việt và dấu thanh, trên dạng NFD của chuỗi.
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/danh_sach.py" <<'PY'
"""In danh sách lớp."""
import unicodedata

THANH = {"̀": 1, "́": 2, "̉": 3, "̃": 4, "̣": 5}   # huyền, sắc, hỏi, ngã, nặng
DANG = {("a", "̆"): "ă", ("a", "̂"): "â", ("e", "̂"): "ê", ("o", "̂"): "ô",
        ("o", "̛"): "ơ", ("u", "̛"): "ư"}
BANG = "aăâbcdđeêghiklmnoôơpqrstuưvxy"


def _khoa_chu(chu):
    cai, thanh = [], 0
    for c in unicodedata.normalize("NFD", chu.lower()):
        if c in THANH:
            thanh = THANH[c]
        elif unicodedata.category(c) == "Mn":
            cai[-1] = DANG[(cai[-1], c)]
        else:
            cai.append(c)
    return (tuple(BANG.index(x) for x in cai), thanh)


def _khoa(ho_ten):
    chu = ho_ten.split()
    return [_khoa_chu(chu[-1])] + [_khoa_chu(c) for c in chu[:-1]]


def sap_xep(ds):
    """Xếp họ tên theo thứ tự từ điển tiếng Việt: tên trước, rồi họ đệm; giữ nguyên chuỗi gốc."""
    return sorted(ds, key=_khoa)


if __name__ == "__main__":
    for ten in sap_xep(["Trần Văn Bình", "Nguyễn Thị Ánh", "Lê Minh Đức", "Phạm Anh"]):
        print(ten)
PY
