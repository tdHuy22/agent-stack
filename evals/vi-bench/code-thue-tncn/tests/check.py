"""Chấm code-thue-tncn: gọi tinh_thue_tncn với các ca tính tay theo luật trong đề.

Các cách làm sai đã thử, đều phải trượt:
  - áp một thuế suất của bậc cao nhất lên cả khoản (không lũy tiến từng phần);
  - dùng round() của Python (làm tròn nửa về số chẵn) hay số thực nên các ca đúng 0,5 đồng bị lệch;
  - không chặn mức đóng bảo hiểm ở 36.000.000đ;
  - gộp bảo hiểm thành 10,5% rồi mới làm tròn (đề bắt làm tròn từng khoản), hay làm tròn thuế từng bậc;
  - bỏ qua giảm trừ người phụ thuộc, không báo ValueError, đổi tên tham số.
"""
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402

# (lương gộp, số người phụ thuộc, thuế đúng). Tính tay theo đề, soát lại bằng chương trình số nguyên riêng ngày 08/11/2026.
# Ví dụ tay: 120.000.000đ, không phụ thuộc: bảo hiểm trên mức 36.000.000đ = 2.880.000 + 540.000 + 360.000 = 3.780.000;
# tính thuế = 120.000.000 - 3.780.000 - 11.000.000 = 105.220.000; thuế = 250.000 + 500.000 + 1.200.000 + 2.800.000 +
# 5.000.000 + 8.400.000 + 25.220.000 x 35% (8.827.000) = 26.977.000.
CASES = [
    (0, 0, 0),
    (8_000_000, 0, 0),
    (11_000_000, 0, 0),
    (15_000_000, 0, 121_250),
    (20_000_000, 1, 125_000),
    (30_000_000, 0, 1_627_500),
    (50_000_000, 2, 3_634_000),
    (120_000_000, 0, 26_977_000),
    (36_000_000, 0, 2_594_000),
    (36_000_001, 0, 2_594_000),
    (500_000_000, 3, 155_357_000),
    (18_765_432, 1, 69_753),
    (27_654_321, 0, 1_312_593),
    # đúng nửa đồng: 12.294.000đ có thu nhập tính thuế 3.130đ, thuế 156,5đ nên phải lên 157
    (12_294_000, 0, 157),
    (17_214_000, 1, 327),    # 326,5 lên 327
    (22_126_000, 2, 139),    # 138,5 lên 139
    # bảo hiểm làm tròn từng khoản: 1.120.053 + 210.010 + 140.007 = 1.470.070 (không phải 1.470.069)
    (14_000_659, 0, 76_529),
]


def main():
    path = vncheck.app_dir() / "luong" / "thue.py"
    spec = importlib.util.spec_from_file_location("thue_check", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        f = mod.tinh_thue_tncn
    except Exception as exc:  # noqa: BLE001
        vncheck.finish([f"không nạp được luong/thue.py: {exc!r}"])
    errs = []
    for luong, npt, want in CASES:
        try:
            got = f(luong, npt)
        except Exception as exc:  # noqa: BLE001
            errs.append(f"tinh_thue_tncn({luong}, {npt}) lỗi {exc!r}, đúng là {want}")
            continue
        if got != want or type(got) is not int:
            errs.append(f"tinh_thue_tncn({luong}, {npt}) = {got!r}, đúng là {want} (số nguyên)")
    for args in ((-1, 0), (15_000_000, -1)):
        try:
            f(*args)
            errs.append(f"tinh_thue_tncn{args} phải báo ValueError")
        except ValueError:
            pass
        except Exception as exc:  # noqa: BLE001
            errs.append(f"tinh_thue_tncn{args} phải báo ValueError, đang báo {exc!r}")
    try:
        if f(20_000_000) != f(luong_gop=20_000_000, so_nguoi_phu_thuoc=0):
            errs.append("số người phụ thuộc phải mặc định là 0")
        if f(luong_gop=20_000_000, so_nguoi_phu_thuoc=1) != 125_000:
            errs.append("gọi theo tên tham số cho kết quả sai")
    except TypeError:
        errs.append("đã đổi tên hay chữ ký của hàm")
    vncheck.finish(errs)


main()
