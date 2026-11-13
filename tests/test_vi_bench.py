"""Test cho evals/vi-bench: bộ 30 bài tiếng Việt tự viết (tự kiểm từng bài, kiểm an toàn của harbor_bench, danh sách việc)
và thư viện chấm chung _lib/vncheck.py."""
import importlib.util
import subprocess
import sys
import unicodedata
import unittest

from tests._util import REPO

VI = REPO / "evals" / "vi-bench"
HARBOR = REPO / "evals" / "harbor"
sys.path.insert(0, str(VI / "_lib"))
import vncheck  # noqa: E402

_spec = importlib.util.spec_from_file_location("harbor_bench_vi", HARBOR / "harbor_bench.py")
B = importlib.util.module_from_spec(_spec)
sys.modules["harbor_bench_vi"] = B
_spec.loader.exec_module(B)


def task_names():
    return sorted(p.parent.name for p in VI.glob("*/task.toml"))


class SelfTestTests(unittest.TestCase):
    def test_every_task_fails_untouched_and_passes_its_reference_solution_ten_per_group(self):
        r = subprocess.run([sys.executable, str(VI / "selftest.py"), "--expect-per-group", "10"], capture_output=True,
                           text=True, timeout=900)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-1000:])
        self.assertIn("30/30 bài đạt tự kiểm", r.stdout)

    def test_selftest_catches_a_grader_that_passes_the_untouched_task(self):
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = __import__("pathlib").Path(tmp) / "vi-bench"
            shutil.copytree(VI / "_lib", root / "_lib")
            shutil.copy(VI / "selftest.py", root / "selftest.py")
            shutil.copytree(VI / "code-phi-ship", root / "code-phi-ship")
            (root / "code-phi-ship" / "tests" / "check.py").write_text("print('ĐẠT')\n", encoding="utf-8")
            r = subprocess.run([sys.executable, str(root / "selftest.py"), "code-phi-ship"], capture_output=True, text=True,
                               timeout=120)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("không trượt trên bài chưa làm", r.stdout)
            # Dockerfile khác khuôn (gọi mạng lúc dựng) cũng bị bắt
            (root / "code-phi-ship" / "tests" / "check.py").write_text(
                (VI / "code-phi-ship" / "tests" / "check.py").read_text(encoding="utf-8"), encoding="utf-8")
            with open(root / "code-phi-ship" / "environment" / "Dockerfile", "a", encoding="utf-8") as f:
                f.write("RUN pip install requests\n")
            r = subprocess.run([sys.executable, str(root / "selftest.py"), "code-phi-ship"], capture_output=True, text=True,
                               timeout=120)
            self.assertIn("environment/Dockerfile khác bản chuẩn", r.stdout)


class TestShTests(unittest.TestCase):
    """_lib/test.sh chạy thật, với /tests và /logs đổi sang thư mục tạm."""

    def run_sh(self, check_body, planted=None):
        import json
        import tempfile
        from pathlib import Path
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        (tmp / "tests").mkdir()
        (tmp / "logs" / "verifier").mkdir(parents=True)
        (tmp / "tests" / "check.py").write_text(check_body, encoding="utf-8")
        if planted is not None:
            (tmp / "logs" / "verifier" / "vi-metrics.json").write_text(planted)
        sh = (VI / "_lib" / "test.sh").read_text(encoding="utf-8")
        sh = sh.replace("/logs/", f"{tmp}/logs/").replace("/tests/", f"{tmp}/tests/")
        (tmp / "test.sh").write_text(sh)
        r = subprocess.run(["bash", str(tmp / "test.sh")], capture_output=True, text=True, timeout=60,
                           env={"PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin"})
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads((tmp / "logs" / "verifier" / "reward.json").read_text())

    def test_reward_json_carries_the_pass_bit_and_numeric_side_metrics_only(self):
        body = ("import json, sys, pathlib\n"
                "p = pathlib.Path(__file__).parents[1] / 'logs' / 'verifier' / 'vi-metrics.json'\n"
                "p.write_text(json.dumps({'van_ai': 4, 'reward': 7, 'ghi_chu': 'x', 'co': True}))\n"
                "sys.exit({code})\n")
        self.assertEqual(self.run_sh(body.replace("{code}", "0")), {"van_ai": 4, "reward": 1})
        self.assertEqual(self.run_sh(body.replace("{code}", "1")), {"van_ai": 4, "reward": 0})

    def test_metrics_left_by_the_agent_are_discarded_before_grading(self):
        self.assertEqual(self.run_sh("import sys; sys.exit(1)\n", planted='{"van_ai": 0, "reward": 1}'), {"reward": 0})


class HarborTests(unittest.TestCase):
    def test_every_task_passes_the_harbor_safety_vetting(self):
        for name in task_names():
            with self.subTest(name=name):
                self.assertEqual(B.vet_task(VI / name, {}), [])

    def test_task_list_for_the_vietnamese_report_matches_the_task_directories(self):
        spec = B.read_task_spec(HARBOR / "tasks-vi.txt")
        self.assertEqual(list(spec), ["vi"])
        self.assertEqual(sorted(spec["vi"]), task_names())
        cand = B.read_task_spec(HARBOR / "tasks-candidates.txt")
        self.assertEqual(sorted(cand.get("vi", [])), task_names())


class VnCheckTests(unittest.TestCase):
    def test_numbers_match_any_thousands_separator_but_not_inside_longer_numbers(self):
        for text in ("1.240 khách", "1 240 khách", "1240 khách", "1,240 khách", "1 240"):
            self.assertTrue(vncheck.has_number(text, 1240), text)
        for text in ("12.400 khách", "11240", "1.2400"):
            self.assertFalse(vncheck.has_number(text, 1240), text)

    def test_missing_accents_english_and_ai_tells_are_caught_but_valid_unaccented_words_are_not(self):
        self.assertEqual(vncheck.no_accent_words("trong cua chung nhung voi khong duoc"), ["khong", "duoc"])
        self.assertEqual(vncheck.no_accent_words("`khong` trong code thì bỏ qua"), [])
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["VI_METRICS"] = os.path.join(tmp, "m.json")
            try:
                errs = vncheck.writing_checks("Trong bối cảnh hiện nay, the system is ready and we will deploy.")
                # dấu hiệu văn AI không làm trượt (bạn chốt 08/11/2026), chỉ được đếm thành chỉ số phụ
                self.assertFalse(any("văn AI" in e for e in errs))
                with open(os.environ["VI_METRICS"]) as fh:
                    self.assertEqual(__import__("json").load(fh), {"van_ai": 1})
            finally:
                del os.environ["VI_METRICS"]
        self.assertTrue(any("tiếng Anh" in e for e in errs))
        self.assertEqual(vncheck.no_accent_words("chạy test_giam_khong_vuot rồi"), [])
        self.assertTrue(vncheck.has_number("ngưỡng 300_000", 300000))
        self.assertTrue(any("NFC" in e for e in vncheck.writing_checks(unicodedata.normalize("NFD", "Đơn hàng bị lỗi."))))
        self.assertEqual(vncheck.writing_checks("Lúc 14:05 trang đặt hàng ngừng chạy, mười tám phút sau mới chạy lại."), [])


if __name__ == "__main__":
    unittest.main()
