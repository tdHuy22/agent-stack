"""Chấm code-ngay-lam-viec: đếm ngày làm việc với các file lễ dựng tại chỗ, đáp án đếm tay trên lịch.

Các cách làm sai đã thử, đều phải trượt:
  - chỉ trừ ngày lễ rơi vào thứ Hai–thứ Sáu, quên nghỉ bù cho lễ cuối tuần;
  - nghỉ bù nhưng chỉ xét lễ nằm trong khoảng đếm (lễ thứ Bảy 01/01/2022 vẫn bù vào thứ Hai 03/01/2022);
  - bù vào "thứ Hai kế tiếp" mà không tránh ngày lễ hay ngày đã bù (lễ liền nhau, lễ + thứ Hai lễ);
  - đọc file bằng utf-8 thường nên dòng đầu vỡ vì BOM; không bỏ qua dòng `#`; tách ngày bằng cách cắt cố định 10 ký tự
    nên hỏng với `1/1/2022`; coi cả dòng là ngày nên vỡ vì tên lễ;
  - quên tính ngày cuối, hoặc không báo ValueError.
"""
import importlib.util
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402

BOM = "\ufeff"

# Mỗi file lễ: (tên, nội dung, có BOM, kiểu xuống dòng)
SET_2022 = (
    BOM + "# Ngày lễ 2022\r\n"
    "1/1/2022\tTết Dương lịch\r\n"
    "\r\n"
    "30/04/2022 Giải phóng miền Nam 30/4\r\n"
    "01/05/2022 Quốc tế Lao động 1/5\r\n"
    "01/05/2022 Quốc tế Lao động (ghi lặp)\r\n"
)
SET_2023 = "02/09/2023 Quốc khánh\n04/09/2023 Nghỉ thêm\n"
SET_2024 = (
    BOM + "# 2024-2025\n"
    "07/01/2024\tNghỉ Chủ nhật\n"
    "08/01/2024\tNghỉ thứ Hai\n"
    "09/01/2024\tNghỉ thứ Ba\n"
    "18/04/2024\tGiỗ Tổ Hùng Vương\n"
    "01/01/2025\tTết Dương lịch"
)
SET_2025 = "29/03/2025 Lễ rơi vào thứ Bảy\n"
SET_TET = "".join(f"{d}/01/2025 Tết\n" for d in range(25, 32)) + "1/2/2025 Tết\n2/2/2025 Tết\n"
SET_TRONG = "# chỉ có chú thích\n\n"

# (file, từ ngày, đến ngày, đáp án, ghi chú)
CASES = [
    (SET_2022, "03/01/2022", "07/01/2022", 4, "lễ thứ Bảy 01/01 (ngoài khoảng) bù vào thứ Hai 03/01"),
    (SET_2022, "01/01/2022", "02/01/2022", 0, "thứ Bảy và Chủ nhật"),
    (SET_2022, "03/01/2022", "03/01/2022", 0, "một ngày, là ngày nghỉ bù"),
    (SET_2022, "04/01/2022", "04/01/2022", 1, "một ngày làm việc"),
    (SET_2022, "25/04/2022", "06/05/2022", 8, "lễ thứ Bảy và Chủ nhật liền nhau, bù thứ Hai và thứ Ba"),
    (SET_2022, "02/05/2022", "03/05/2022", 0, "hai ngày nghỉ bù"),
    (SET_2022, "04/05/2022", "04/05/2022", 1, "ngày làm việc ngay sau kỳ nghỉ"),
    (SET_2023, "01/09/2023", "08/09/2023", 4, "lễ thứ Bảy mà thứ Hai kế tiếp cũng là lễ: bù thứ Ba 05/09"),
    (SET_2024, "08/01/2024", "12/01/2024", 2, "lễ Chủ nhật, thứ Hai, thứ Ba: bù thứ Tư 10/01"),
    (SET_2024, "15/04/2024", "19/04/2024", 4, "lễ ngày thường không bù"),
    (SET_2024, "01/01/2024", "31/12/2024", 258, "cả năm 2024: 262 ngày thứ Hai–thứ Sáu trừ 08/01, 09/01, 10/01, 18/04"),
    (SET_2024, "30/12/2024", "03/01/2025", 4, "qua năm, 01/01/2025 là lễ ngày thường"),
    (SET_2025, "31/03/2025", "04/04/2025", 4, "31/03 là ngày bù của lễ 29/03"),
    (SET_2025, "28/03/2025", "31/03/2025", 1, "chỉ thứ Sáu 28/03 là ngày làm việc"),
    (SET_TET, "20/01/2025", "14/02/2025", 11, "Tết 9 ngày liền, 4 ngày bù dồn sang 03–06/02"),
    (SET_TET, "03/02/2025", "07/02/2025", 1, "chỉ thứ Sáu 07/02"),
    (SET_TRONG, "01/03/2024", "31/03/2024", 21, "file không có lễ"),
    (SET_TRONG, "1/3/2024", "1/3/2024", 1, "ngày viết bỏ số 0, thứ Sáu"),
]
BAD = [  # (từ ngày, đến ngày)
    ("30/02/2024", "05/03/2024"),
    ("2024-03-01", "05/03/2024"),
    ("05/03/2024", "31/04/2024"),
    ("05/03/2024", "01/03/2024"),
]


def main():
    path = vncheck.app_dir() / "lich" / "ngay_lam_viec.py"
    spec = importlib.util.spec_from_file_location("ngay_lam_viec_check", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        f = mod.dem_ngay_lam_viec
    except Exception as exc:  # noqa: BLE001
        vncheck.finish([f"không nạp được lich/ngay_lam_viec.py: {exc!r}"])
    errs = []
    with tempfile.TemporaryDirectory(prefix="vi-lich-") as tmp:
        os.chdir(tmp)
        files = {}
        for i, content in enumerate(dict.fromkeys(c[0] for c in CASES)):
            p = os.path.join(tmp, f"le{i}.txt")
            with open(p, "wb") as fh:
                fh.write(content.encode("utf-8"))
            files[content] = p
        for content, tu, den, want, note in CASES:
            try:
                got = f(tu, den, files[content])
            except Exception as exc:  # noqa: BLE001
                errs.append(f"{tu} → {den} ({note}): lỗi {exc!r}, đúng là {want}")
                continue
            if got != want or type(got) is not int:
                errs.append(f"{tu} → {den} ({note}): được {got!r}, đúng là {want}")
        any_file = next(iter(files.values()))
        for tu, den in BAD:
            try:
                f(tu, den, any_file)
                errs.append(f"({tu!r}, {den!r}) phải báo ValueError")
            except ValueError:
                pass
            except Exception as exc:  # noqa: BLE001
                errs.append(f"({tu!r}, {den!r}) phải báo ValueError, đang báo {exc!r}")
        try:
            f(tu_ngay="04/01/2022", den_ngay="04/01/2022", file_le=any_file)
        except TypeError:
            errs.append("đã đổi tên tham số của hàm")
        except Exception:  # noqa: BLE001
            pass  # lỗi khác đã được báo ở các ca trên
        os.chdir("/")
    vncheck.finish(errs)


main()
