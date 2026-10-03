import hashlib, importlib, subprocess, sys
from pathlib import Path

TEST_SHA = "6e153a00bab67ff147f40ad939903f8cc2162215c5e7af90f6f00701f1bbed34"
SPEC_SHA = "69f18efea311a403c14a8c8bb914e8ea337a43385fe7d1b37f4b17b660c49df2"
BAD_PRICES = ["-1", "1.005", "abc", "", "1,5"]
CATALOG = {"P15": ("percent", 15), "P20": ("percent", 20), "BIG": ("fixed", 5000)}
# (mô tả, lines, code, tax_rate, (subtotal, discounted, tax, total))
CASES = [
    ("giá 0.29 không bị cắt xu", [("a", 3, "0.29")], None, 10, (87, 87, 9, 96)),
    ("thuế làm tròn nửa lên", [("a", 1, "0.25")], None, 10, (25, 25, 3, 28)),
    ("thuế suất lẻ 8.25%", [("a", 1, "10.00")], None, 8.25, (1000, 1000, 83, 1083)),
    ("tiền giảm % làm tròn nửa lên", [("a", 1, "10.10")], "P15", 10, (1010, 858, 86, 944)),
    ("giảm cố định không làm tổng âm", [("a", 1, "19.99")], "BIG", 10, (1999, 0, 0, 0)),
    ("thuế tính trên số tiền sau giảm", [("a", 1, "100.00")], "P20", 10, (10000, 8000, 800, 8800)),
    ("thuế tính một lần cho cả hóa đơn", [("a", 1, "0.05"), ("b", 1, "0.05")], None, 10, (10, 10, 1, 11)),
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(workdir, answer):
    workdir = Path(workdir)
    if sha(workdir / "tests" / "test_invoice.py") != TEST_SHA:
        return False, "đã sửa tests/test_invoice.py"
    if sha(workdir / "SPEC.md") != SPEC_SHA:
        return False, "đã sửa SPEC.md"
    out = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"], cwd=str(workdir),
                         capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        return False, "test có sẵn chưa đạt: " + (out.stdout + out.stderr)[-200:]
    sys.path.insert(0, str(workdir))
    for name in [m for m in sys.modules if m == "billing" or m.startswith("billing.")]:
        del sys.modules[name]
    wrong = []
    try:
        money = importlib.import_module("billing.money")
        invoice = importlib.import_module("billing.invoice")
        for text, cents in (("19.99", 1999), ("0.29", 29), ("5", 500), ("0.5", 50), ("1.10", 110)):
            got = money.to_cents(text)
            if got != cents:
                wrong.append(f"to_cents({text!r}) = {got}, cần {cents}")
        for text in BAD_PRICES:
            try:
                money.to_cents(text)
                wrong.append(f"to_cents({text!r}) phải ném ValueError")
            except ValueError:
                pass
        for desc, lines, code, rate, want in CASES:
            try:
                inv = invoice.build_invoice(lines, code=code, catalog=CATALOG, tax_rate=rate)
                got = (inv["subtotal"], inv["discounted"], inv["tax"], inv["total"])
            except Exception as exc:
                got = repr(exc)
            if got != want:
                wrong.append(f"{desc}: {got}, cần {want}")
        try:
            invoice.build_invoice([("a", 1, "1.00")], code="NOPE", catalog=CATALOG)
            wrong.append("mã lạ phải ném ValueError")
        except ValueError:
            pass
    except Exception as exc:
        wrong.append(f"lỗi khi chạy: {exc!r}")
    finally:
        sys.path.remove(str(workdir))
    return not wrong, "; ".join(wrong[:4]) or "đạt"
