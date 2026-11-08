#!/usr/bin/env python3
"""saoluu.py: sao lưu một thư mục thành file nén có đóng dấu thời gian.

Dùng: saoluu.py NGUON DICH [--giu 5] [--nen zip|tar] [--keep-all]
(Ghi chú cũ: mặc định giữ 5 bản gần nhất, chạy thử bằng --dry-run.)
"""
import argparse
import fnmatch
import os
import shutil
import sys
import tarfile
import time
import zipfile

if sys.version_info < (3, 9):
    sys.exit("Cần Python 3.9 trở lên")

MAC_DINH_BO_QUA = [".git", "node_modules", "__pycache__"]
THOAT_NGUON_KHONG_CO = 2
THOAT_DICH_KHONG_GHI_DUOC = 3
THOAT_HET_CHO = 4


def doc_tham_so(argv=None):
    p = argparse.ArgumentParser(prog="saoluu.py", description="Sao lưu thư mục thành file nén")
    p.add_argument("nguon", help="thư mục cần sao lưu")
    p.add_argument("dich", help="thư mục chứa các bản sao lưu")
    p.add_argument("--giu", type=int, default=int(os.environ.get("SAOLUU_GIU", "7")),
                   help="số bản gần nhất được giữ lại, 0 là giữ hết (mặc định 7, hoặc theo biến môi trường SAOLUU_GIU)")
    p.add_argument("--nen", choices=["zip", "tar"], default="zip", help="dạng nén (mặc định zip)")
    p.add_argument("--bo-qua", action="append", default=[], metavar="MAU",
                   help="mẫu tên cần bỏ qua, dùng được nhiều lần, cộng thêm vào danh sách mặc định")
    p.add_argument("--thu", action="store_true", help="chạy thử: chỉ in việc sẽ làm, không ghi và không xóa gì")
    p.add_argument("-v", "--chi-tiet", action="store_true", help="in từng file được thêm vào bản sao lưu")
    return p.parse_args(argv)


def bi_loai(ten, mau):
    return any(fnmatch.fnmatch(ten, m) for m in mau)


def danh_sach_file(nguon, mau):
    for goc, thu_muc, files in os.walk(nguon):
        thu_muc[:] = [d for d in thu_muc if not bi_loai(d, mau)]
        for f in files:
            if not bi_loai(f, mau):
                yield os.path.join(goc, f)


def dung_luong(nguon, mau):
    return sum(os.path.getsize(f) for f in danh_sach_file(nguon, mau))


def main(argv=None):
    a = doc_tham_so(argv)
    mau = MAC_DINH_BO_QUA + a.bo_qua
    if not os.path.isdir(a.nguon):
        print(f"Không thấy thư mục nguồn: {a.nguon}", file=sys.stderr)
        return THOAT_NGUON_KHONG_CO
    if not a.thu:
        try:
            os.makedirs(a.dich, exist_ok=True)
            if not os.access(a.dich, os.W_OK):
                raise OSError("không ghi được")
        except OSError:
            print(f"Không ghi được vào thư mục đích: {a.dich}", file=sys.stderr)
            return THOAT_DICH_KHONG_GHI_DUOC
    can = dung_luong(a.nguon, mau)
    if os.path.isdir(a.dich) and shutil.disk_usage(a.dich).free < can * 1.2:
        print("Ổ đĩa đích không đủ chỗ trống (cần ít nhất 1,2 lần dung lượng nguồn)", file=sys.stderr)
        return THOAT_HET_CHO
    ten = os.path.basename(os.path.abspath(a.nguon))
    duoi = "zip" if a.nen == "zip" else "tar.gz"
    ra = os.path.join(a.dich, f"{ten}-{time.strftime('%Y%m%d-%H%M%S')}.{duoi}")
    if a.thu:
        print(f"[chạy thử] sẽ tạo {ra}")
        return 0
    if a.nen == "zip":
        with zipfile.ZipFile(ra, "w", zipfile.ZIP_DEFLATED) as z:
            for f in danh_sach_file(a.nguon, mau):
                z.write(f, os.path.relpath(f, a.nguon))
                if a.chi_tiet:
                    print("thêm", f)
    else:
        with tarfile.open(ra, "w:gz") as t:
            for f in danh_sach_file(a.nguon, mau):
                t.add(f, os.path.relpath(f, a.nguon))
                if a.chi_tiet:
                    print("thêm", f)
    print(f"Đã tạo {ra}")
    if a.giu > 0:
        cu = sorted(f for f in os.listdir(a.dich) if f.startswith(ten + "-") and f.endswith((".zip", ".tar.gz")))
        for f in cu[:-a.giu]:
            os.remove(os.path.join(a.dich, f))
            print("Đã xóa bản cũ", f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
