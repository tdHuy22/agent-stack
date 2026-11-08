#!/bin/bash
# Lời giải mẫu: tự đọc đối số (không dùng argparse để giữ đúng thông báo), so sánh theo ngày thật.
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/bao_cao/bao_cao.py" <<'PY'
"""Báo cáo doanh thu theo sản phẩm từ file CSV giao dịch (cột ngay, san_pham, so_tien)."""
import csv
import sys
from collections import defaultdict
from datetime import datetime

CACH_DUNG = "Cách dùng: python3 bao_cao.py FILE.csv [--tu-ngay dd/mm/yyyy] [--den-ngay dd/mm/yyyy]"
CO_NGAY = ("--tu-ngay", "--den-ngay")


class LoiThamSo(Exception):
    """Lỗi tham số: in thông báo ra stderr rồi thoát với mã `ma`."""

    def __init__(self, thong_bao, ma=2):
        super().__init__(thong_bao)
        self.thong_bao = thong_bao
        self.ma = ma


def doc_ngay(chuoi):
    return datetime.strptime(chuoi.strip(), "%d/%m/%Y").date()


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


def doc_tham_so(argv):
    """Trả (đường dẫn file, ngày bắt đầu hoặc None, ngày kết thúc hoặc None)."""
    duong_dan = None
    gia_tri = {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("-") and a != "-":
            ten, dau_bang, v = a.partition("=")
            if ten not in CO_NGAY or ten in gia_tri:
                raise LoiThamSo(CACH_DUNG)
            if not dau_bang:
                i += 1
                if i >= len(argv):
                    raise LoiThamSo(CACH_DUNG)
                v = argv[i]
            gia_tri[ten] = v
        elif duong_dan is None:
            duong_dan = a
        else:
            raise LoiThamSo(CACH_DUNG)
        i += 1
    if duong_dan is None:
        raise LoiThamSo(CACH_DUNG)
    ngay = []
    for ten in CO_NGAY:
        v = gia_tri.get(ten)
        if v is None:
            ngay.append(None)
            continue
        try:
            ngay.append(doc_ngay(v))
        except ValueError:
            raise LoiThamSo(f"Lỗi: {ten} không hợp lệ: {v} (cần dạng dd/mm/yyyy).") from None
    if ngay[0] and ngay[1] and ngay[0] > ngay[1]:
        raise LoiThamSo("Lỗi: --tu-ngay không được sau --den-ngay.")
    return duong_dan, ngay[0], ngay[1]


def loc_theo_ngay(giao_dich, tu_ngay, den_ngay):
    if tu_ngay is None and den_ngay is None:
        return giao_dich
    ket_qua = []
    for g in giao_dich:
        d = doc_ngay(g["ngay"])
        if (tu_ngay is None or d >= tu_ngay) and (den_ngay is None or d <= den_ngay):
            ket_qua.append(g)
    return ket_qua


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        duong_dan, tu_ngay, den_ngay = doc_tham_so(argv)
        try:
            giao_dich = doc_giao_dich(duong_dan)
        except FileNotFoundError:
            raise LoiThamSo(f"Lỗi: không tìm thấy file: {duong_dan}", 3) from None
    except LoiThamSo as loi:
        print(loi.thong_bao, file=sys.stderr)
        return loi.ma
    giao_dich = loc_theo_ngay(giao_dich, tu_ngay, den_ngay)
    if not giao_dich and (tu_ngay or den_ngay):
        print("Không có giao dịch trong khoảng ngày đã chọn.")
        return 0
    tong = tong_hop(giao_dich)
    for san_pham in sorted(tong):
        print(f"{san_pham}: {dinh_dang_tien(tong[san_pham])}")
    print(f"Tổng: {dinh_dang_tien(sum(tong.values()))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
PY
