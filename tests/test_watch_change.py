import subprocess
import sys

from tests._util import PLUGIN, TempDirTestCase

WATCH = PLUGIN / "skills" / "session-keeper" / "scripts" / "watch_change.py"

# Lệnh giả: mỗi lần chạy đọc số lần chạy từ file đếm, in phần tử thứ n của dãy (hết dãy thì lặp phần tử cuối).
# Mỗi phần tử là "mã|chữ".
FAKE = """
import sys
from pathlib import Path
counter, *steps = sys.argv[1:]
path = Path(counter)
n = int(path.read_text()) if path.exists() else 0
path.write_text(str(n + 1))
code, _, text = steps[min(n, len(steps) - 1)].partition("|")
print(text)
sys.exit(int(code))
"""


class WatchChange(TempDirTestCase):
    def watch(self, steps, *flags, every="0.05"):
        fake = self.tmp / "fake.py"
        fake.write_text(FAKE)
        counter = self.tmp / "count"
        counter.unlink(missing_ok=True)
        return subprocess.run([sys.executable, str(WATCH), "--every", every, *flags, "--",
                               sys.executable, str(fake), str(counter), *steps],
                              capture_output=True, text=True, timeout=20)

    def test_prints_only_when_the_result_changes(self):
        out = self.watch(["0|đang chạy", "0|đang   chạy", "0|đang chạy", "0|xong"], "--until", "xong")
        self.assertEqual(out.returncode, 0, out.stderr)
        # lần đầu in; hai lần khác nhau mỗi khoảng trắng không tính; "xong" in rồi thoát
        self.assertEqual(out.stdout.count("[mã thoát 0]"), 2)
        self.assertEqual(out.stdout.count("đang chạy"), 1)
        self.assertIn("xong", out.stdout)
        self.assertRegex(out.stdout.splitlines()[0], r"^\d\d:\d\d \[mã thoát 0\]$")

    def test_until_exits_zero_even_on_first_match(self):
        out = self.watch(["0|completed"], "--until", "complete")
        self.assertEqual(out.returncode, 0)
        self.assertEqual(out.stdout.count("completed"), 1)

    def test_exit_code_change_is_reported(self):
        out = self.watch(["0|cùng chữ", "0|cùng chữ", "3|cùng chữ", "3|kết thúc"], "--until", "kết thúc")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("[mã thoát 0]", out.stdout)
        self.assertIn("[mã thoát 3]", out.stdout)
        self.assertEqual(out.stdout.count("cùng chữ"), 2)  # mã đổi mà chữ y nguyên vẫn in lại

    def test_redacts_a_fake_key(self):
        out = self.watch(["0|khóa sk-ant-fakefakefake_123-ABC rò"], "--until", "rò")
        self.assertIn("[KHÓA]", out.stdout)
        self.assertNotIn("fakefakefake", out.stdout)

    def test_max_hours_prints_one_line_and_exits_zero(self):
        out = self.watch(["0|mãi như vậy"], "--max-hours", "0.00003", every="0.02")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("hết thời gian theo dõi", out.stdout)
        self.assertEqual(out.stdout.count("mãi như vậy"), 1)

    def test_long_output_is_trimmed(self):
        lines = "\n".join(f"dòng {i}" for i in range(40))
        out = self.watch([f"0|{lines}"], "--until", "dòng")
        self.assertIn("dòng 0", out.stdout)
        self.assertNotIn("dòng 39", out.stdout)
        self.assertIn("(+", out.stdout)

    def test_command_that_cannot_run_is_reported_not_raised(self):
        out = subprocess.run([sys.executable, str(WATCH), "--every", "0.05", "--max-hours", "0.00003", "--",
                              str(self.tmp / "khong-co-lenh")], capture_output=True, text=True, timeout=20)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("[mã thoát 127]", out.stdout)

    def test_requires_a_command(self):
        out = subprocess.run([sys.executable, str(WATCH), "--every", "1"], capture_output=True, text=True, timeout=20)
        self.assertNotEqual(out.returncode, 0)
