"""Chấm code-phi-ship: gọi tinh_phi_ship với các đơn tính tay."""
import importlib.util
import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402

NFD_HN = unicodedata.normalize("NFD", "Hà Nội")
CASES = [  # (tổng tiền, tỉnh, phí đúng)
    (499_000, "Hà Nội", 20_000),
    (500_000, "Đà Nẵng", 0),
    (500_000, "Hà Nội", 0),
    (501, "Cần Thơ", 35_000),       # dưới 500.000đ dù lớn hơn 500
    (120_000, "ha noi", 20_000),
    (120_000, "  TP. Hà Nội", 20_000),
    (120_000, "Thành phố Hà Nội ", 20_000),
    (120_000, "HÀ  NỘI", 20_000),
    (120_000, NFD_HN, 20_000),       # chữ có dấu kiểu tách rời
    (120_000, "Hà Nam", 35_000),
    (120_000, "Hà Nội Mới", 35_000),
    (0, "Huế", 35_000),
    (2_000_000, "Huế", 0),
]


def main():
    path = vncheck.app_dir() / "shop" / "phi_ship.py"
    spec = importlib.util.spec_from_file_location("phi_ship_check", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        f = mod.tinh_phi_ship
    except Exception as exc:  # noqa: BLE001
        vncheck.finish([f"không nạp được shop/phi_ship.py: {exc!r}"])
    errs = []
    for tong, tinh, want in CASES:
        try:
            got = f(tong, tinh)
        except Exception as exc:  # noqa: BLE001
            errs.append(f"tinh_phi_ship({tong}, {tinh!r}) lỗi {exc!r}, đúng là {want}")
            continue
        if got != want:
            errs.append(f"tinh_phi_ship({tong}, {tinh!r}) = {got!r}, đúng là {want}")
    try:
        f(-1, "Hà Nội")
        errs.append("tổng tiền âm phải báo ValueError")
    except ValueError:
        pass
    except Exception as exc:  # noqa: BLE001
        errs.append(f"tổng tiền âm phải báo ValueError, đang báo {exc!r}")
    try:
        f(120_000, tinh="Hà Nội")       # tham số giữ tên cũ
    except TypeError:
        errs.append("đã đổi tên tham số của hàm")
    vncheck.finish(errs)


main()
