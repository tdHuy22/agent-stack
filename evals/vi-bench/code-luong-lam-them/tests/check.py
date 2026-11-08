"""Chấm code-luong-lam-them: gọi tinh_tien_lam_them với các ca tính tay theo luật trong đề.

Lỗi nằm ở ba file (gio_cong.py, he_so.py, tinh_luong.py); bài chỉ gọi hàm cuối. Các cách làm sai đã thử, đều phải trượt:
  - sửa mỗi lương giờ (chia 26 thay vì 30) như test có sẵn đòi, bỏ sót phần còn lại;
  - thứ Bảy vẫn tính là ngày thường (chỉ nhận Chủ nhật là cuối tuần);
  - hệ số ngày lễ để 200%, hay cuối tuần được ưu tiên hơn ngày lễ nên lễ rơi vào Chủ nhật hay thứ Bảy chỉ được 200%;
  - ca qua nửa đêm ra số phút âm, hoặc tính cả ca theo loại của ngày bắt đầu mà không tách phần sau 00:00;
  - làm tròn từng ca (lệch 1đ ở tổng), dùng round() của Python hay số thực (nửa đồng bị làm tròn xuống);
  - so ngày lễ bằng chuỗi nguyên văn nên "7/1/2024" không khớp "07/01/2024".
"""
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402

LE = ["18/04/2024", "7/1/2024", "02/09/2023"]   # thứ Năm, Chủ nhật, thứ Bảy
L = 10_400_000                                  # lương giờ đúng 50.000đ (10.400.000 / 26 / 8)

# (lương tháng, các ca, đáp án, ghi chú). Tính tay: giờ × 50.000 × hệ số, từng phần theo ngày lịch.
CASES = [
    (L, [("06/03/2024", "18:00", "20:30")], 187_500, "thứ Tư 2,5 giờ × 150%"),
    (L, [("09/03/2024", "08:00", "12:00")], 400_000, "thứ Bảy 4 giờ × 200%"),
    (L, [("10/03/2024", "13:00", "17:00")], 400_000, "Chủ nhật 4 giờ × 200%"),
    (L, [("18/04/2024", "08:00", "10:00")], 300_000, "lễ ngày thường 2 giờ × 300%"),
    (L, [("07/01/2024", "08:00", "10:00")], 300_000, "lễ rơi vào Chủ nhật: 300%, không phải 200%"),
    (L, [("02/09/2023", "09:00", "11:00")], 300_000, "lễ rơi vào thứ Bảy: 300%"),
    (L, [("08/03/2024", "22:00", "02:00")], 350_000, "thứ Sáu 22:00 → thứ Bảy 02:00: 2 giờ × 150% + 2 giờ × 200%"),
    (L, [("10/03/2024", "20:00", "01:30")], 512_500, "Chủ nhật 4 giờ × 200% + thứ Hai 1,5 giờ × 150%"),
    (L, [("17/04/2024", "22:00", "02:00")], 450_000, "thứ Tư 2 giờ × 150% + lễ 18/04 2 giờ × 300%"),
    (L, [("18/04/2024", "23:00", "03:00")], 375_000, "lễ 1 giờ × 300% + thứ Sáu 3 giờ × 150%"),
    (L, [("09/03/2024", "22:00", "00:00")], 200_000, "kết thúc đúng 00:00: 2 giờ × 200%"),
    (L, [], 0, "không có ca"),
    (0, [("06/03/2024", "18:00", "20:00")], 0, "lương 0"),
    (8_494_512, [("06/03/2024", "18:00", "19:00")], 61_259, "đúng nửa đồng: 61.258,5 phải lên 61.259"),
    (9_876_000, [("06/03/2024", "08:00", "08:20"), ("07/03/2024", "08:00", "08:20"), ("08/03/2024", "08:00", "08:20")],
     71_221, "ba ca 20 phút: tròn một lần ở cuối ra 71.221, tròn từng ca ra 71.220"),
    (15_500_000, [("2/3/2024", "17:30", "21:00"), ("04/03/2024", "18:00", "19:15"), ("08/03/2024", "23:00", "01:00"),
                  ("10/03/2024", "06:00", "12:00"), ("17/04/2024", "20:00", "00:00"), ("18/04/2024", "22:30", "02:30"),
                  ("19/04/2024", "18:00", "18:40")], 2_952_825, "cả tháng trộn đủ loại ngày và ca qua đêm"),
]
BAD = [
    ("giờ bắt đầu bằng giờ kết thúc", (L, [("06/03/2024", "08:00", "08:00")])),
    ("giờ 25:00", (L, [("06/03/2024", "08:00", "25:00")])),
    ("phút 75", (L, [("06/03/2024", "08:75", "09:00")])),
    ("ngày không có thật", (L, [("31/04/2024", "08:00", "09:00")])),
    ("lương âm", (-1, [("06/03/2024", "08:00", "09:00")])),
]


def main():
    luong_dir = vncheck.app_dir() / "luong"
    sys.path.insert(0, str(luong_dir))
    for ten in ("gio_cong", "he_so", "tinh_luong"):
        sys.modules.pop(ten, None)
    spec = importlib.util.spec_from_file_location("tinh_luong_check", luong_dir / "tinh_luong.py")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        f = mod.tinh_tien_lam_them
    except Exception as exc:  # noqa: BLE001
        vncheck.finish([f"không nạp được luong/tinh_luong.py: {exc!r}"])
    errs = []
    for luong, ca, want, note in CASES:
        try:
            got = f(luong, ca, LE)
        except Exception as exc:  # noqa: BLE001
            errs.append(f"{note}: lỗi {exc!r}, đúng là {want}")
            continue
        if got != want or type(got) is not int:
            errs.append(f"{note}: được {got!r}, đúng là {want} (số nguyên)")
    for note, (luong, ca) in BAD:
        try:
            f(luong, ca)
            errs.append(f"{note}: phải báo ValueError")
        except ValueError:
            pass
        except Exception as exc:  # noqa: BLE001
            errs.append(f"{note}: phải báo ValueError, đang báo {exc!r}")
    try:
        if f(L, [("09/03/2024", "08:00", "12:00")]) != 400_000:   # ngay_le mặc định rỗng
            errs.append("không truyền ngay_le thì thứ Bảy 4 giờ phải là 400.000")
        if f(luong_thang=L, ca_lam=[("09/03/2024", "08:00", "12:00")], ngay_le=[]) != 400_000:
            errs.append("gọi theo tên tham số cho kết quả sai")
    except TypeError:
        errs.append("đã đổi tên tham số của hàm")
    except Exception as exc:  # noqa: BLE001
        errs.append(f"gọi không có ngay_le lỗi {exc!r}")
    vncheck.finish(errs)


main()
