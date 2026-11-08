"""Báo cáo doanh thu theo sản phẩm từ file CSV giao dịch (cột ngay, san_pham, so_tien)."""
import csv
import sys
from collections import defaultdict

CACH_DUNG = "Cách dùng: python3 bao_cao.py FILE.csv"


def doc_giao_dich(duong_dan):
    """Đọc file CSV, trả danh sách dict mỗi giao dịch một dict."""
    with open(duong_dan, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def tong_hop(giao_dich):
    """Cộng số tiền theo sản phẩm, trả dict {sản phẩm: tổng}."""
    tong = defaultdict(int)
    for g in giao_dich:
        tong[g["san_pham"]] += int(g["so_tien"])
    return dict(tong)


def dinh_dang_tien(n):
    """Số nguyên đồng thành chuỗi có dấu chấm ngăn cách nghìn, vd. 1234567 thành 1.234.567."""
    return f"{n:,}".replace(",", ".")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(CACH_DUNG, file=sys.stderr)
        return 2
    try:
        giao_dich = doc_giao_dich(argv[0])
    except FileNotFoundError:
        print(f"Lỗi: không tìm thấy file: {argv[0]}", file=sys.stderr)
        return 3
    tong = tong_hop(giao_dich)
    for san_pham in sorted(tong):
        print(f"{san_pham}: {dinh_dang_tien(tong[san_pham])}")
    print(f"Tổng: {dinh_dang_tien(sum(tong.values()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
