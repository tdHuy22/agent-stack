import json
import sys

from tests._util import PLUGIN, TempDirTestCase, run_script

TELLS = PLUGIN / "skills" / "giong-van" / "scripts" / "tells.py"
sys.path.insert(0, str(TELLS.parent))
import tells  # noqa: E402

AI_LIKE = ("Trong bối cảnh chuyển đổi số hiện nay, trí tuệ nhân tạo đóng vai trò vô cùng quan trọng. "
           "Nó không chỉ giúp tiết kiệm thời gian mà còn mang lại giá trị to lớn.\nTóm lại, AI là chìa khóa cho tương lai.\n")
PLAIN = ("Tuần trước mình thử cho script tự gom log lỗi mỗi sáng. Nó chạy được ba ngày thì hỏng vì đổi định dạng ngày. "
         "Sửa mất mười phút.\n")


class Tells(TempDirTestCase):
    def test_ai_like_scores_high_and_plain_scores_low(self):
        ai, plain = tells.analyze(AI_LIKE), tells.analyze(PLAIN)
        self.assertGreater(ai["score_per_1000_words"], 100)
        self.assertEqual(plain["score_per_1000_words"], 0)
        codes = {h["code"] for h in ai["hits"]}
        self.assertTrue({"vi-mo-bai-sao", "vi-khong-chi-ma-con", "vi-thoi-phong", "vi-ket-sao"} <= codes)

    def test_english_tells(self):
        res = tells.analyze("In today's fast-paced world, we delve into the tapestry of ideas.\nIn conclusion, it works.\n")
        self.assertTrue({"en-delve", "en-conclusion"} <= {h["code"] for h in res["hits"]})

    def test_uniform_rhythm_and_dashes(self):
        same = " ".join(["Câu này có đúng tám chữ để thử nghiệm nhịp." for _ in range(9)])
        self.assertIn("nhip-deu", {h["code"] for h in tells.analyze(same)["hits"]})
        dashes = "Ý một — ý hai — ý ba — ý bốn — ý năm. " * 3
        self.assertIn("gach-dai", {h["code"] for h in tells.analyze(dashes)["hits"]})

    def test_cli_json(self):
        path = self.write("a.md", AI_LIKE)
        out = run_script(TELLS, "--json", str(path))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertGreater(json.loads(out.stdout)["score_per_1000_words"], 100)
