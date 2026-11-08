"""Chấm code-cli-bao-cao: chạy bao_cao.py như người dùng (subprocess) và so stdout, stderr, mã thoát nguyên văn.

Các cách làm sai đã thử, đều phải trượt:
  - so sánh ngày như chuỗi ("5/3/2024" > "15/03/2024", "02/12/2023" > "01/04/2024") thay vì theo ngày thật;
  - dùng argparse mặc định: lỗi ra "usage: ..." và "error: ..." bằng tiếng Anh, sai thông báo đã cho;
  - ngày sai (30/02/2024, 2024-03-31) làm chương trình sập có traceback, hoặc mã thoát 1 thay vì 2;
  - không tìm thấy file ra traceback / mã 1 thay vì 3; kiểm file trước khi kiểm ngày;
  - khi không còn giao dịch nào chỉ in "Tổng: 0" mà không in thông báo "Không có giao dịch…";
  - quên dạng --tu-ngay=..., hay cờ đứng trước tên file; không lọc đầu mút (tính cả hai đầu).
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402

CACH_DUNG = "Cách dùng: python3 bao_cao.py FILE.csv [--tu-ngay dd/mm/yyyy] [--den-ngay dd/mm/yyyy]"
CSV = """ngay,san_pham,so_tien
05/03/2024,Cà phê,45000
5/3/2024,Trà đào,38000
15/03/2024,Cà phê,90000
31/03/2024,Bánh mì,25000
01/04/2024,Cà phê,45000
10/04/2024,Đèn học,1200000
02/12/2023,Cà phê,30000
2/1/2024,Trà đào,38000
"""
TEN_FILE = "doanh thu tháng 3.csv"
KHONG_CO = "dữ liệu/không có.csv"

# (đối số trước/sau tên file được viết bằng {F}, stdout đúng, stderr đúng, mã thoát đúng)
CASES = [
    ([r"{F}"], "Bánh mì: 25.000\nCà phê: 210.000\nTrà đào: 76.000\nĐèn học: 1.200.000\nTổng: 1.511.000\n", "", 0),
    ([r"{F}", "--tu-ngay", "01/03/2024", "--den-ngay", "31/03/2024"],
     "Bánh mì: 25.000\nCà phê: 135.000\nTrà đào: 38.000\nTổng: 198.000\n", "", 0),
    ([r"{F}", "--tu-ngay", "5/3/2024", "--den-ngay", "15/3/2024"],
     "Cà phê: 135.000\nTrà đào: 38.000\nTổng: 173.000\n", "", 0),
    (["--den-ngay", "15/03/2024", r"{F}", "--tu-ngay", "05/03/2024"],
     "Cà phê: 135.000\nTrà đào: 38.000\nTổng: 173.000\n", "", 0),
    ([r"{F}", "--tu-ngay", "01/04/2024"], "Cà phê: 45.000\nĐèn học: 1.200.000\nTổng: 1.245.000\n", "", 0),
    ([r"{F}", "--den-ngay", "31/12/2023"], "Cà phê: 30.000\nTổng: 30.000\n", "", 0),
    ([r"{F}", "--tu-ngay=01/04/2024", "--den-ngay=30/04/2024"],
     "Cà phê: 45.000\nĐèn học: 1.200.000\nTổng: 1.245.000\n", "", 0),
    ([r"{F}", "--tu-ngay", "05/03/2024", "--den-ngay", "05/03/2024"],
     "Cà phê: 45.000\nTrà đào: 38.000\nTổng: 83.000\n", "", 0),
    ([r"{F}", "--tu-ngay", "01/01/2024", "--den-ngay", "31/01/2024"], "Trà đào: 38.000\nTổng: 38.000\n", "", 0),
    ([r"{F}", "--tu-ngay", "01/01/2025"], "Không có giao dịch trong khoảng ngày đã chọn.\n", "", 0),
    ([r"{F}", "--tu-ngay", "30/02/2024"], "", "Lỗi: --tu-ngay không hợp lệ: 30/02/2024 (cần dạng dd/mm/yyyy).\n", 2),
    ([r"{F}", "--den-ngay", "2024-03-31"], "", "Lỗi: --den-ngay không hợp lệ: 2024-03-31 (cần dạng dd/mm/yyyy).\n", 2),
    ([r"{F}", "--den-ngay", "xyz", "--tu-ngay", "31/04/2024"], "",
     "Lỗi: --tu-ngay không hợp lệ: 31/04/2024 (cần dạng dd/mm/yyyy).\n", 2),
    ([r"{F}", "--tu-ngay", "01/04/2024", "--den-ngay", "01/03/2024"], "",
     "Lỗi: --tu-ngay không được sau --den-ngay.\n", 2),
    ([KHONG_CO], "", f"Lỗi: không tìm thấy file: {KHONG_CO}\n", 3),
    ([KHONG_CO, "--tu-ngay", "32/01/2024"], "", "Lỗi: --tu-ngay không hợp lệ: 32/01/2024 (cần dạng dd/mm/yyyy).\n", 2),
    ([], "", CACH_DUNG + "\n", 2),
    ([r"{F}", "thua.csv"], "", CACH_DUNG + "\n", 2),
    ([r"{F}", "--thang", "3"], "", CACH_DUNG + "\n", 2),
    ([r"{F}", "-h"], "", CACH_DUNG + "\n", 2),
    ([r"{F}", "--tu-ngay"], "", CACH_DUNG + "\n", 2),
]


def main():
    script = vncheck.app_dir() / "bao_cao" / "bao_cao.py"
    if not script.exists():
        vncheck.finish(["không thấy bao_cao/bao_cao.py"])
    errs = []
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
    with tempfile.TemporaryDirectory(prefix="vi-cli-") as tmp:
        f = os.path.join(tmp, TEN_FILE)
        with open(f, "w", encoding="utf-8", newline="") as fh:
            fh.write(CSV)
        for args, out, err, code in CASES:
            argv = [f if a == "{F}" else a for a in args]
            try:
                r = subprocess.run([sys.executable, str(script)] + argv, capture_output=True, timeout=20, env=env, cwd=tmp)
            except subprocess.TimeoutExpired:
                errs.append(f"{args}: chạy quá 20 giây")
                continue
            got = (r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace"), r.returncode)
            if got != (out, err, code):
                errs.append(f"đối số {' '.join(a if a != '{F}' else 'FILE' for a in args)!r}: "
                            f"được stdout={got[0]!r} stderr={got[1]!r} mã={got[2]}; đúng là stdout={out!r} "
                            f"stderr={err!r} mã={code}")
    vncheck.finish(errs)


main()
