"""Chấm code-lich-tra-no: so lịch trả nợ với bảng tính tay theo luật trong đề.

Các cách làm sai đã thử, đều phải trượt:
  - round() của Python (nửa về số chẵn): lãi 601.562,5 bị làm tròn xuống 601.562 thay vì lên 601.563;
  - gốc mỗi tháng làm tròn (hay chia số thực) nên tháng cuối còn dư nợ lẻ hoặc âm, tổng gốc khác số tiền vay;
  - dồn phần lẻ vào tháng đầu thay vì tháng cuối; tính lãi trên số tiền vay ban đầu (không phải dư nợ đầu kỳ);
  - không đọc được "1.200.000.000" hay "10,5" (float("10,5") lỗi, bỏ dấu phẩy rồi thành 105);
  - không báo ValueError, đổi tên tham số, trả số thực thay vì số nguyên.
"""
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402

# Bảng tính tay (gốc, lãi mỗi tháng) soát lại bằng chương trình số nguyên riêng ngày 08/11/2026.
# 75.000.000đ, 10,5%/năm, 12 tháng: gốc đều 6.250.000đ; lãi tháng 2 = 68.750.000 × 0,00875 = 601.562,5 → 601.563.
GOC_1 = [6_250_000] * 12
LAI_1 = [656_250, 601_563, 546_875, 492_188, 437_500, 382_813, 328_125, 273_438, 218_750, 164_063, 109_375, 54_688]
# 100.000.000đ, 12%/năm, 18 tháng: gốc 5.555.555đ mỗi tháng, phần lẻ 10đ dồn vào tháng cuối (5.555.565đ).
GOC_2 = [5_555_555] * 17 + [5_555_565]
LAI_2 = [1_000_000, 944_444, 888_889, 833_333, 777_778, 722_222, 666_667, 611_111, 555_556, 500_000, 444_445,
         388_889, 333_333, 277_778, 222_222, 166_667, 111_111, 55_556]
# 120.000.000đ, 7,5%/năm, 11 tháng: gốc 10.909.090đ, tháng cuối 10.909.100đ.
GOC_3 = [10_909_090] * 10 + [10_909_100]
LAI_3 = [750_000, 681_818, 613_636, 545_455, 477_273, 409_091, 340_909, 272_727, 204_546, 136_364, 68_182]

CASES = [  # (số tiền, lãi suất, số tháng, danh sách gốc, danh sách lãi)
    (75_000_000, 10.5, 12, GOC_1, LAI_1),
    (100_000_000, 12, 18, GOC_2, LAI_2),
    (120_000_000, 7.5, 11, GOC_3, LAI_3),
    ("75.000.000", "10,5", 12, GOC_1, LAI_1),                    # nhập kiểu form
    (10_000_000, 0, 3, [3_333_333, 3_333_333, 3_333_334], [0, 0, 0]),
    (30_000_000, 9.6, 1, [30_000_000], [240_000]),               # vay một tháng
    (100_000_000, "12", 18, GOC_2, LAI_2),
]


def so_khop(lich, vay, goc, lai):
    """Danh sách lỗi của một lịch so với gốc và lãi đúng."""
    loi = []
    if not isinstance(lich, list) or len(lich) != len(goc):
        return [f"lịch có {len(lich) if isinstance(lich, list) else lich!r} dòng, đúng là {len(goc)}"]
    du = vay
    for i, d in enumerate(lich):
        try:
            got = (d["ky"], d["goc"], d["lai"], d["tong"], d["du_no_cuoi"])
        except (KeyError, TypeError):
            return [f"dòng {i + 1} thiếu khóa: {d!r}"]
        du -= goc[i]
        want = (i + 1, goc[i], lai[i], goc[i] + lai[i], du)
        if got != want or any(type(x) is not int for x in got):
            loi.append(f"tháng {i + 1}: (ky, goc, lai, tong, du_no_cuoi) = {got}, đúng là {want}")
            if len(loi) >= 3:
                break
    return loi


def main():
    path = vncheck.app_dir() / "vay" / "lich_tra_no.py"
    spec = importlib.util.spec_from_file_location("lich_tra_no_check", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        f = mod.lap_lich_tra_no
    except Exception as exc:  # noqa: BLE001
        vncheck.finish([f"không nạp được vay/lich_tra_no.py: {exc!r}"])
    errs = []
    for vay, lai_suat, n, goc, lai in CASES:
        try:
            lich = f(vay, lai_suat, n)
        except Exception as exc:  # noqa: BLE001
            errs.append(f"lap_lich_tra_no({vay!r}, {lai_suat!r}, {n}) lỗi {exc!r}")
            continue
        so_vay = int(str(vay).replace(".", ""))
        for e in so_khop(lich, so_vay, goc, lai):
            errs.append(f"lap_lich_tra_no({vay!r}, {lai_suat!r}, {n}): {e}")
    # Khoản vay lớn 36 tháng: kiểm dòng đầu, dòng 18, dòng cuối và tổng.
    try:
        lich = f("1.200.000.000", "10,5", 36)
        if len(lich) != 36:
            errs.append(f"vay 1,2 tỷ 36 tháng: có {len(lich)} dòng, đúng là 36")
        else:
            want = {0: (1, 33_333_333, 10_500_000, 43_833_333, 1_166_666_667),
                    17: (18, 33_333_333, 5_541_667, 38_875_000, 600_000_006),
                    35: (36, 33_333_345, 291_667, 33_625_012, 0)}
            for i, w in want.items():
                d = lich[i]
                got = (d["ky"], d["goc"], d["lai"], d["tong"], d["du_no_cuoi"])
                if got != w:
                    errs.append(f"vay 1,2 tỷ 36 tháng, dòng {i + 1}: {got}, đúng là {w}")
            if sum(d["goc"] for d in lich) != 1_200_000_000 or sum(d["lai"] for d in lich) != 194_250_000:
                errs.append("vay 1,2 tỷ 36 tháng: tổng gốc phải là 1.200.000.000 và tổng lãi 194.250.000")
    except Exception as exc:  # noqa: BLE001
        errs.append(f"vay 1,2 tỷ 36 tháng lỗi {exc!r}")
    for args in ((0, 10, 12), (-5_000_000, 10, 12), (10_000_000, -1, 12), (10_000_000, 10, 0), ("abc", 10, 12),
                 (10_000_000, "mười", 12)):
        try:
            f(*args)
            errs.append(f"lap_lich_tra_no{args} phải báo ValueError")
        except ValueError:
            pass
        except Exception as exc:  # noqa: BLE001
            errs.append(f"lap_lich_tra_no{args} phải báo ValueError, đang báo {exc!r}")
    try:
        f(so_tien_vay=12_000_000, lai_suat_nam=12, so_thang=4)
    except TypeError:
        errs.append("đã đổi tên tham số của hàm")
    except Exception:  # noqa: BLE001
        pass
    vncheck.finish(errs)


main()
