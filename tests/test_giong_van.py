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


class ResearchPatterns(TempDirTestCase):
    """Mẫu thêm theo Wikipedia "Signs of AI writing" và Reinhart và cộng sự (PNAS 2025)."""

    def codes(self, text):
        return {h["code"] for h in tells.analyze(text)["hits"]}

    def test_trailing_clause_copula_and_challenges(self):
        text = ("Dự án đóng vai trò là cầu nối giữa hai nhóm, góp phần nâng cao hiệu suất. "
                "Mặc dù còn nhiều thách thức, tương lai của dự án rất hứa hẹn.")
        self.assertTrue({"vi-menh-de-duoi", "vi-ne-la", "vi-thach-thuc"} <= self.codes(text))

    def test_chatbot_leftovers_weigh_most(self):
        text = ("Chắc chắn rồi! Dưới đây là phiên bản đã chỉnh sửa.\nHy vọng thông tin này hữu ích! "
                "Gửi [Tên của bạn]. Nguồn: example.com?utm_source=chatgpt.com")
        hits = [h for h in tells.analyze(text)["hits"] if h["group"] == "sót từ chatbot"]
        self.assertTrue({"vi-sot-chatbot", "cho-trong", "ma-trich-dan"} <= {h["code"] for h in hits})
        self.assertTrue(all(h["weight"] == 3 for h in hits))

    def test_english_tells_from_research(self):
        text = ("The library serves as a hub for the town, highlighting its role. Despite these challenges, it grows.\n"
                "I hope this helps! Here's the revised version.\n")
        self.assertTrue({"en-copula", "en-ing-analysis", "en-challenges", "en-chatbot"} <= self.codes(text))

    def test_no_false_alarm_on_similar_text(self):
        self.assertNotIn("cho-trong", self.codes("Xem [date](https://example.com) để biết thêm."))
        self.assertNotIn("en-chatbot", self.codes("As an aid to readers, we add notes."))

    def test_nominalization_density(self):
        dense = ("Việc sử dụng AI giúp việc học dễ hơn. Sự phát triển của công nghệ thúc đẩy việc áp dụng rộng rãi. "
                 "Sự hỗ trợ của nhà trường cũng quan trọng.")
        self.assertIn("danh-hoa", self.codes(dense))
        everyday = "Công việc tuần này nhiều. Sự kiện hôm qua vui. Mình làm việc tới tối. " * 3
        self.assertNotIn("danh-hoa", self.codes(everyday))

    def test_line_number_skips_blank_lines_before_match(self):
        hits = tells.analyze("Đoạn một ở đây.\n\nTóm lại, xong việc.\n")["hits"]
        self.assertEqual([h["line"] for h in hits if h["code"] == "vi-ket-sao"], [3])

    def test_decomposed_unicode_scores_the_same(self):
        import unicodedata
        nfd = unicodedata.normalize("NFD", AI_LIKE)
        self.assertEqual(tells.analyze(nfd)["score_per_1000_words"], tells.analyze(AI_LIKE)["score_per_1000_words"])


SAMPLE = ("Mình viết cái này sau một tuần vật lộn với CI. Nhưng mà cuối cùng cũng xong. "
          "Mình thấy cách dễ nhất là đọc log trước, rồi mới đoán. ") * 40
DRAFT = ("Tôi cho rằng giải pháp này toàn diện và hiệu quả. Tôi đã áp dụng giải pháp toàn diện này cho mạch tích hợp. "
         "Mạch tích hợp chạy ổn. Tôi kiểm tra mạch tích hợp hai lần.")


class SamplesComparison(TempDirTestCase):
    """So với bài mẫu của người viết, theo cách đo từ dùng nhiều bất thường (Kobak 2025, Antislop 2026)."""

    def test_flags_words_and_pronoun_you_do_not_use(self):
        res = tells.analyze(DRAFT, SAMPLE)
        self.assertTrue(res["samples"]["used"])
        self.assertIn("xung-ho", {h["code"] for h in res["hits"]})
        flagged = " ".join(h["match"] for h in res["hits"] if h["code"] == "khac-bai-mau")
        self.assertIn("toàn diện", flagged)
        self.assertNotIn("hiệu quả", flagged)  # chỉ xuất hiện một lần

    def test_repeated_topic_phrase_is_listed_but_not_scored(self):
        res = tells.analyze(DRAFT, SAMPLE)
        self.assertIn({"phrase": "mạch tích hợp", "count": 3}, res["samples"]["unfamiliar"])
        self.assertFalse(any("mạch tích hợp" in h["match"] for h in res["hits"]))
        without = tells.analyze(DRAFT)
        scored = sum(h["weight"] for h in res["hits"]) - sum(h["weight"] for h in without["hits"])
        self.assertEqual(scored, 1 + 1 + 2)  # "toàn diện", "giải pháp", xưng hô

    def test_words_you_use_are_not_flagged(self):
        yours = SAMPLE + "Mình nghĩ giải pháp toàn diện vẫn tốt hơn. " * 20
        res = tells.analyze(DRAFT, yours)
        self.assertEqual([h for h in res["hits"] if h["code"] == "khac-bai-mau"], [])

    def test_sentence_initial_word_is_not_a_proper_noun(self):
        en_samples = "I wrote this after a long week fighting the build. It finally works, and I am glad. " * 40
        draft = "Flaky deploys hurt. Flaky tests too. We fixed the flaky runner."
        phrases = [u["phrase"] for u in tells.analyze(draft, en_samples)["samples"]["unfamiliar"]]
        self.assertIn("flaky", phrases)

    def test_too_few_sample_words_is_reported(self):
        res = tells.analyze(DRAFT, "Mình viết ngắn thôi.")
        self.assertFalse(res["samples"]["used"])
        self.assertIn("500", res["samples"]["reason"])
        self.assertEqual(res["score_per_1000_words"], tells.analyze(DRAFT)["score_per_1000_words"])

    def test_cli_samples_dir_and_flags(self):
        samples = self.tmp / "samples"
        samples.mkdir()
        (samples / "README.md").write_text("Không phải bài mẫu. " * 300, encoding="utf-8")
        (samples / "a.md").write_text(SAMPLE, encoding="utf-8")
        draft = self.write("draft.md", DRAFT)
        data = json.loads(run_script(TELLS, "--json", "--samples", str(samples), str(draft)).stdout)
        self.assertTrue(data["samples"]["used"])
        self.assertEqual(data["samples"]["files"], 1)
        self.assertNotIn("samples", json.loads(run_script(TELLS, "--json", "--no-samples", str(draft)).stdout))
        # file đang chấm nằm trong samples/ thì không được so với chính nó
        inside = samples / "b.md"
        inside.write_text(DRAFT, encoding="utf-8")
        data = json.loads(run_script(TELLS, "--json", "--samples", str(samples), str(inside)).stdout)
        self.assertEqual(data["samples"]["files"], 1)

    def test_cli_without_samples_says_how_to_enable(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        (empty / "README.md").write_text("Đặt bài mẫu vào đây.", encoding="utf-8")
        out = run_script(TELLS, "--samples", str(empty), str(self.write("d.md", DRAFT)))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Chưa so với bài mẫu", out.stdout)
        self.assertIn("5 bài", out.stdout)


EN_SAMPLE = "I wrote this after a long week fighting the build. It finally works, and I am glad of it. " * 40
CLASSIC_KEYS = ("title", "author", "year", "genre", "source", "license")


def frontmatter_doc(body, **meta):
    head = "".join(f"{k}: {v}\n" for k, v in meta.items())
    return f"---\n{head}---\n{body}"


class SampleSelection(TempDirTestCase):
    """Chọn bộ bài mẫu: bài của project, rồi bài riêng trong samples/ của skill, rồi văn mẫu kinh điển cùng ngôn ngữ."""

    def setUp(self):
        super().setUp()
        self.skill = self.tmp / "skill-samples"
        (self.skill / "kinh-dien" / "vi").mkdir(parents=True)
        (self.skill / "kinh-dien" / "en").mkdir(parents=True)
        (self.skill / "README.md").write_text("Không phải bài mẫu. " * 300, encoding="utf-8")
        (self.skill / "kinh-dien" / "vi" / "a.md").write_text(
            frontmatter_doc(SAMPLE, title="Bài A", source="https://vi.wikisource.org/x"), encoding="utf-8")
        (self.skill / "kinh-dien" / "en" / "b.md").write_text(
            frontmatter_doc(EN_SAMPLE, title="Essay B", source="https://en.wikisource.org/y"), encoding="utf-8")
        self.project = self.tmp / "proj"
        self.project.mkdir()

    def pick(self, draft, **kw):
        return tells.pick_samples(draft, project_start=self.project, skill_samples=self.skill, **kw)

    def test_frontmatter_is_stripped(self):
        text, n = tells.load_samples(self.skill / "kinh-dien" / "vi")
        self.assertEqual(n, 1)
        self.assertNotIn("wikisource", text)
        self.assertTrue(text.startswith(SAMPLE[:20]))

    def test_directory_samples_follow_the_draft_language(self):
        mixed = self.tmp / "mixed"
        mixed.mkdir()
        (mixed / "vi.md").write_text(SAMPLE, encoding="utf-8")
        (mixed / "en.md").write_text(EN_SAMPLE, encoding="utf-8")
        vi_text, vi_n = tells.load_samples(mixed, vietnamese=True)
        en_text, en_n = tells.load_samples(mixed, vietnamese=False)
        self.assertEqual((vi_n, en_n), (1, 1))
        self.assertNotIn("fighting the build", vi_text)
        self.assertNotIn("Mình", en_text)

    def test_falls_back_to_classics_of_the_same_language(self):
        vi = self.pick(DRAFT)
        self.assertEqual((vi["kind"], vi["files"]), ("classic", 1))
        self.assertEqual(vi["where"].name, "vi")
        en = self.pick("We shipped the robust fix. The robust tests passed. " * 3)
        self.assertEqual((en["kind"], en["where"].name), ("classic", "en"))

    def test_project_samples_win(self):
        own = self.project / ".agent" / "giong-van" / "samples"
        own.mkdir(parents=True)
        (own / "p.md").write_text(SAMPLE, encoding="utf-8")
        nested = self.project / "chuong-1"
        nested.mkdir()
        got = tells.pick_samples(DRAFT, project_start=nested, skill_samples=self.skill)
        self.assertEqual((got["kind"], got["files"]), ("project", 1))

    def test_own_samples_in_skill_dir_beat_classics_without_mixing(self):
        (self.skill / "cua-toi.md").write_text(SAMPLE, encoding="utf-8")
        got = self.pick(DRAFT)
        self.assertEqual((got["kind"], got["files"]), ("own", 1))

    def test_too_few_project_words_falls_back_with_a_note(self):
        own = self.project / ".agent" / "giong-van" / "samples"
        own.mkdir(parents=True)
        (own / "p.md").write_text("Mình viết ngắn thôi.", encoding="utf-8")
        got = self.pick(DRAFT)
        self.assertEqual(got["kind"], "classic")
        self.assertIn("project", got["note"])

    def test_classics_do_not_judge_pronouns(self):
        res = tells.analyze(DRAFT, SAMPLE, kind="classic")
        codes = {h["code"] for h in res["hits"]}
        self.assertNotIn("xung-ho", codes)
        flagged = [h for h in res["hits"] if h["code"] == "khac-bai-mau"]
        self.assertTrue(flagged)
        self.assertIn("kinh điển", flagged[0]["fix"])

    def test_cli_reports_which_samples_were_used(self):
        draft = self.write("draft.md", DRAFT)
        data = json.loads(run_script(TELLS, "--json", "--project", str(self.project),
                                     "--samples-root", str(self.skill), str(draft)).stdout)
        self.assertEqual((data["samples"]["kind"], data["samples"]["files"]), ("classic", 1))
        out = run_script(TELLS, "--project", str(self.project), "--samples-root", str(self.skill), str(draft))
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("văn mẫu kinh điển", out.stdout)
        self.assertIn(".agent/giong-van/samples", out.stdout)


class CommittedClassics(TempDirTestCase):
    """5 bài văn học kinh điển cho mỗi ngôn ngữ, thuộc phạm vi công cộng, có nguồn."""

    def test_five_public_domain_classics_per_language(self):
        root = TELLS.parents[1] / "samples" / "kinh-dien"
        for lang, vietnamese in (("vi", True), ("en", False)):
            files = sorted(p for p in (root / lang).glob("*.md"))
            self.assertEqual(len(files), 5, lang)
            total = 0
            for f in files:
                raw = f.read_text(encoding="utf-8")
                self.assertTrue(raw.startswith("---\n"), f.name)
                head = raw.split("\n---\n", 1)[0]
                for key in CLASSIC_KEYS:
                    self.assertRegex(head, rf"(?m)^{key}: \S", f"{f.name} thiếu {key}")
                self.assertRegex(head, r"(?m)^source: https://(vi|en)\.wikisource\.org/", f.name)
                body = tells.strip_frontmatter(raw)
                self.assertEqual(tells.is_vietnamese(body), vietnamese, f.name)
                self.assertGreaterEqual(tells.words(body), 400, f.name)
                total += tells.words(body)
            self.assertGreaterEqual(total, 10000, lang)
