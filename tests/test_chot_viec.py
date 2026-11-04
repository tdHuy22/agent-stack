"""Test cho skill done-gate: script chấm mức rủi ro của thay đổi."""
from __future__ import annotations

import subprocess
import sys
import unittest

from tests._util import PLUGIN, TempDirTestCase

SCRIPTS = PLUGIN / "skills" / "done-gate" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import risk  # noqa: E402


def change(path, added=1, deleted=0, text="", removed=""):
    return {"path": path, "added": added, "deleted": deleted, "text": text, "removed": removed}


class FreshChanges(unittest.TestCase):
    def test_keeps_only_lines_not_seen_and_marks_file_reviewed(self):
        old = "a = 1\nb = 2\n"
        seen = {"app.py": risk.line_hashes(old)}
        picked, reviewed = risk.fresh_changes(
            [change("app.py", 3, 0, old + "eval(x)\n"), change("new.py", 2, 0, "x = 1\ny = 2\n")], seen)
        self.assertEqual([(c["path"], c["text"], c["added"]) for c in picked],
                         [("app.py", "eval(x)", 1), ("new.py", "x = 1\ny = 2\n", 2)])
        self.assertEqual(reviewed, frozenset({"app.py"}))

    def test_file_with_no_new_lines_is_dropped(self):
        seen = {"app.py": risk.line_hashes("a = 1\n")}
        self.assertEqual(risk.fresh_changes([change("app.py", 1, 0, "a = 1\n")], seen), ([], frozenset()))

    def test_removed_lines_count_only_when_new_since_the_mark(self):
        removed = "    self.assertEqual(a, 1)\n    self.assertEqual(b, 2)"
        seen, gone = {"tests/test_a.py": []}, {"tests/test_a.py": risk.line_hashes("    self.assertEqual(a, 1)")}
        picked, _ = risk.fresh_changes([change("tests/test_a.py", 0, 2, "", removed)], seen, gone)
        self.assertEqual((picked[0]["removed"], picked[0]["deleted"]), ("    self.assertEqual(b, 2)", 1))
        # Dấu cũ (trước khi lưu dòng bị xóa): coi mọi dòng bị xóa là đã chấm, không chặn lại việc cũ.
        self.assertEqual(risk.fresh_changes([change("tests/test_a.py", 0, 2, "", removed)], seen), ([], frozenset()))

    def test_reviewed_assert_that_vanished_is_kept_with_its_strictness(self):
        before = "    self.assertEqual(r['level'], 'cao')"
        after = "    self.assertIn(r['level'], ('vua', 'cao'))"
        h = risk.line_hashes(before)[0]
        picked, reviewed = risk.fresh_since_mark([change("tests/test_a.py", 1, 0, after)],
                                                 {"files": {"tests/test_a.py": [h]}, "removed": {},
                                                  "asserts": {"tests/test_a.py": [[h, True], "hỏng"]}})
        self.assertEqual(picked[0]["vanished"], [True])
        r = risk.assess(picked, reviewed)
        self.assertTrue(any("nới assert" in x for x in r["reasons"]), r["reasons"])

    def test_reviewed_assert_still_in_the_file_is_not_vanished(self):
        kept = "    self.assertEqual(f(1), 1)"
        h = risk.line_hashes(kept)[0]
        mark = {"files": {"tests/test_x.py": [h]}, "removed": {}, "asserts": {"tests/test_x.py": [[h, True]]}}
        c = dict(change("tests/test_x.py", 1, 0, "    self.assertTrue(g())"),
                 content=kept + "\n    self.assertTrue(g())")
        picked, _ = risk.fresh_since_mark([c], mark)
        self.assertEqual(picked[0]["vanished"], [], "assert đã commit vẫn nằm trong file")
        gone = dict(change("tests/test_x.py", 1, 1, "    self.assertTrue(f(1))", kept),
                    content="    self.assertTrue(f(1))")
        picked, reviewed = risk.fresh_since_mark([gone], mark)
        self.assertEqual(picked[0]["vanished"], [], "đã đếm ở dòng bị xóa, không đếm hai lần")
        r = risk.assess(picked, reviewed)
        self.assertTrue(any("nới assert" in x for x in r["reasons"]), r["reasons"])


class Assess(unittest.TestCase):
    def test_docs_only_is_low(self):
        r = risk.assess([change("README.md", 40, 10), change("docs/guide.md", 5)])
        self.assertEqual(r["level"], "thap")
        self.assertEqual(r["hotspots"], [])

    def test_reader_html_pages_are_docs(self):
        # trang cho người đọc dài hàng trăm dòng, không có test: không được chấm như code
        page = '<main data-loai="bao-cao">\n<section data-phan="tom-tat">'
        r = risk.assess([change(".agent/trang/de-xuat.html", 600), change("HUONG-DAN.html", 300, 40, page),
                         {**change("notes/bao-cao.htm", 80), "page": True}])
        self.assertEqual(r["level"], "thap", r["reasons"])
        self.assertEqual(r["by_kind"]["code"], 0)

    def test_html_without_reader_mark_is_code(self):
        # index.html của Vite ở gốc repo, template: vẫn chấm như code, kể cả <script> có eval
        for path in ("index.html", "site/about.html", "app/templates/login.html"):
            self.assertEqual(risk.change_kind(change(path, 5, 0, "<div id=app></div>")), "code", path)
        r = risk.assess([change("index.html", 3, 0, "<script>eval(location.hash)</script>")])
        self.assertTrue(any("mã động" in x for x in r["reasons"]), r["reasons"])

    def test_small_code_change_with_test_is_low(self):
        r = risk.assess([change("src/pager.py", 3, 1, "start = (page - 1) * per_page\n"),
                         change("tests/test_pager.py", 6)])
        self.assertEqual(r["level"], "thap")

    def test_code_without_test_is_flagged(self):
        r = risk.assess([change("src/pager.py", 30, 2)])
        self.assertTrue(any("không đổi test" in x for x in r["reasons"]), r["reasons"])

    def test_hook_change_is_hotspot(self):
        r = risk.assess([change("plugin/hooks/router.py", 20, 5), change("tests/test_hooks.py", 10)])
        self.assertIn(r["level"], ("vua", "cao"))
        self.assertEqual(r["hotspots"][0][0], "plugin/hooks/router.py")
        self.assertTrue(any("hook" in x for x in r["hotspots"][0][1]))

    def test_sensitive_path_is_high(self):
        r = risk.assess([change("app/auth/token_store.py", 40, 10)])
        self.assertEqual(r["level"], "cao")

    def test_hardcoded_secret_is_high_even_in_docs(self):
        r = risk.assess([change("notes.md", 1, 0, 'api_key = "sk-live-abcdef123456"\n')])
        self.assertEqual(r["level"], "cao")
        self.assertTrue(any("secret" in x for x in r["reasons"]))

    def test_dangerous_calls_are_reasons(self):
        r = risk.assess([change("tools/clean.py", 5, 0, "subprocess.run(cmd, shell=True)\nshutil.rmtree(p)\n"),
                         change("tests/test_clean.py", 5)])
        self.assertTrue(any("qua shell" in x for x in r["reasons"]), r["reasons"])
        self.assertTrue(any("xóa" in x for x in r["reasons"]), r["reasons"])

    def test_shrinking_tests_is_flagged(self):
        r = risk.assess([change("src/a.py", 2, 2), change("tests/test_a.py", 1, 30)])
        self.assertTrue(any("bớt test" in x for x in r["reasons"]), r["reasons"])

    def test_large_change_raises_level(self):
        small = risk.assess([change("src/a.py", 20), change("tests/test_a.py", 5)])
        big = risk.assess([change("src/a.py", 600), change("tests/test_a.py", 5)])
        self.assertGreater(big["score"], small["score"])
        self.assertTrue(any("lớn" in x for x in big["reasons"]))

    def test_dependency_and_install_files_are_hotspots(self):
        r = risk.assess([change("install.sh", 4, 1), change("requirements.txt", 1)])
        paths = [p for p, _ in r["hotspots"]]
        self.assertIn("install.sh", paths)
        self.assertIn("requirements.txt", paths)

    def test_session_in_path_is_not_sensitive(self):
        r = risk.assess([change("plugin/skills/session-keeper/scripts/receipt.py", 10),
                         change("tests/test_receipt.py", 5)])
        self.assertEqual(r["level"], "thap", r)

    def test_render_has_level_and_review_hint(self):
        out = risk.render(risk.assess([change("app/auth/login.py", 40)]))
        self.assertIn("Mức rủi ro: cao", out)
        self.assertIn("agent-stack:reviewer", out)

    def test_trust_boundary_raises_low_to_medium_and_names_the_boundary(self):
        r = risk.assess([change("app/avatar.py", 6, 0, "@app.post('/avatar')\ndef up():\n    f = request.files['f']\n"),
                         change("tests/test_avatar.py", 8)])
        self.assertEqual(r["level"], "vua", r)
        self.assertEqual([b["kind"] for b in r["boundaries"]], ["input từ bên ngoài"])
        self.assertFalse(r["threat_model_updated"])
        out = risk.render(r)
        self.assertIn("Ranh giới tin cậy bị đụng:", out)
        self.assertIn("chạy skill threat-model", out)

    def test_each_boundary_kind_is_detected(self):
        cases = {
            "gọi ra ngoài": change("src/client.py", 2, 0, "resp = requests.post(url, json=body)\n"),
            "xác thực, phân quyền": change("src/views.py", 2, 0, "@login_required\ndef page(): pass\n"),
            "dữ liệu nhạy cảm": change("src/profile.py", 1, 0, "phone_number = form['phone_number']\n"),
            "thêm dependency": change("requirements.txt", 1, 0, "httpx==0.27\n"),
            "chạy mã, lệnh hay đường dẫn từ input": change("src/run.py", 1, 0, "subprocess.run([tool, name])\n"),
        }
        for want, c in cases.items():
            with self.subTest(want=want):
                self.assertIn(want, [b["kind"] for b in risk.assess([c])["boundaries"]])

    def test_boundary_in_tests_or_docs_is_ignored_and_threat_model_is_noticed(self):
        r = risk.assess([change("tests/test_client.py", 2, 0, "requests.get('http://x')\n"),
                         change("docs/api.md", 2, 0, "requests.get(url)\n"),
                         change("router/rules.json", 2, 0, '"match": ["login", "subprocess."]\n')])
        self.assertEqual(r["boundaries"], [])
        self.assertEqual(r["level"], "thap")
        r = risk.assess([change("src/client.py", 2, 0, "requests.get(url)\n"), change("tests/test_client.py", 3),
                         change(".agent/threat-model.md", 12)])
        self.assertTrue(r["threat_model_updated"])
        self.assertIn("có mục mới trong", risk.render(r))

    def test_render_empty(self):
        self.assertIn("Không có thay đổi", risk.render(risk.assess([])))


class ReviewPlan(unittest.TestCase):
    """Cấu hình review bạn chốt 04/11/2026: reviewer khác model người viết, hỏi trước khi tốn hạn mức."""

    def plan(self, level, writer, **kw):
        return [(r["model"], r["effort"]) for r in risk.review_plan(level, writer, **kw)["reviewers"]]

    def test_each_cell_of_the_table(self):
        cases = [
            (("vua", "opus"), {}, [("sonnet", "high")]),
            (("vua", "sonnet"), {}, [("opus", "medium")]),
            (("cao", "opus"), {}, [("opus", "high"), ("sonnet", "high")]),
            (("cao", "sonnet"), {}, [("opus", "high")]),
            (("cao", "sonnet"), {"security": True}, [("opus", "high"), ("sonnet", "high")]),
            (("cao", "opus"), {"security": True, "crypto": True}, [("opus", "xhigh"), ("sonnet", "high")]),
            (("cao", "sonnet"), {"security": True, "crypto": True}, [("opus", "xhigh"), ("sonnet", "high")]),
            (("thap", "opus"), {}, []),
        ]
        for (level, writer), kw, want in cases:
            with self.subTest(level=level, writer=writer, **kw):
                self.assertEqual(self.plan(level, writer, **kw), want)

    def test_rereview_of_a_fix_is_one_sonnet_unless_the_fix_itself_is_high(self):
        for writer in ("opus", "sonnet"):
            self.assertEqual(self.plan("vua", writer, rereview=True), [("sonnet", "high")])
            self.assertEqual(self.plan("cao", writer, rereview=True, security=True), [("opus", "high")])
        self.assertEqual(self.plan("thap", "opus", rereview=True), [])

    def test_writer_from_model_id_and_other_families(self):
        self.assertEqual(self.plan("vua", "claude-opus-5-5"), [("sonnet", "high")])
        self.assertEqual(self.plan("vua", "claude-sonnet-5-5"), [("opus", "medium")])
        self.assertEqual(self.plan("vua", "claude-fable-5-1"), [("sonnet", "high")])
        self.assertEqual(self.plan("vua", "claude-haiku-5-5"), [("opus", "medium")])

    def test_unknown_writer_names_both_cases(self):
        r = risk.review_plan("vua", None)
        self.assertEqual(r["reviewers"], [])
        self.assertIn("Opus viết: giao `agent-stack:reviewer` trong context mới, model sonnet, effort high", r["review"])
        self.assertIn("Sonnet viết: giao `agent-stack:reviewer` trong context mới, model opus, effort medium",
                      r["review"])

    def test_dual_review_text_asks_for_parallel_and_log(self):
        text = risk.review_plan("cao", "opus")["review"]
        self.assertIn("giao song song 2 `agent-stack:reviewer`", text)
        self.assertIn("opus·high và sonnet·high", text)
        self.assertIn("review_log.py add", text)

    def test_assess_marks_security_and_crypto_from_paths(self):
        auth = risk.assess([change("app/auth/login.py", 40)], writer="sonnet")
        self.assertEqual(auth["level"], "cao", auth)
        self.assertEqual([(r["model"], r["effort"]) for r in auth["reviewers"]], [("opus", "high"), ("sonnet", "high")])
        self.assertIn("differential-review", auth["review"])
        pay = risk.assess([change("src/payments/charge.py", 40)], writer="sonnet")
        self.assertEqual(pay["reviewers"][0], {"model": "opus", "effort": "xhigh"})
        # Mức cao vì hook và xóa file, không đụng bảo mật: Sonnet viết thì một Opus.
        plain = risk.assess([change("plugin/hooks/clean.py", 10, 0, "shutil.rmtree(p)\n")], writer="sonnet")
        self.assertEqual(plain["level"], "cao", plain)
        self.assertEqual(plain["reviewers"], [{"model": "opus", "effort": "high"}])

    def limits(self, week=None, five=None, reset_in=3600):
        now = 1_000_000.0
        windows = {}
        if week is not None:
            windows["seven_day"] = {"used_percentage": week, "resets_at": now + reset_in}
        if five is not None:
            windows["five_hour"] = {"used_percentage": five, "resets_at": now + reset_in}
        return {"rate_limits": windows}, now

    def test_budget_asks_before_opus_or_dual_review(self):
        limits, now = self.limits(week=84)
        self.assertEqual(risk.budget_asks([("opus", "medium")], "vua", 10, limits, now),
                         ["hạn mức tuần đã dùng 84% (từ 80%)"])
        self.assertEqual(len(risk.budget_asks([("opus", "high"), ("sonnet", "high")], "cao", 10, limits, now)), 1)
        # Chỉ một Sonnet: rẻ, không hỏi.
        self.assertEqual(risk.budget_asks([("sonnet", "high")], "vua", 10, limits, now), [])
        limits, now = self.limits(week=79, five=90)
        self.assertEqual(risk.budget_asks([("opus", "high")], "cao", 10, limits, now),
                         ["hạn mức 5 giờ đã dùng 90% (từ 90%)"])
        limits, now = self.limits(week=10)
        self.assertEqual(risk.budget_asks([("opus", "high")], "cao", 801, limits, now),
                         ["diff lớn (801 dòng code, trên 800)"])
        self.assertEqual(risk.budget_asks([("opus", "high")], "cao", 800, limits, now), [])

    def test_window_past_reset_is_ignored(self):
        limits, now = self.limits(week=95, five=99, reset_in=-1)
        self.assertEqual(risk.budget_asks([("opus", "high")], "cao", 10, limits, now), [])
        self.assertEqual(risk.budget_asks([("opus", "high")], "cao", 10, {"rate_limits": "x"}, now), [])
        self.assertEqual(risk.budget_asks([("opus", "high")], "cao", 10, None, now), [])

    def test_threshold_edges_and_security_from_boundary_alone(self):
        limits, now = self.limits(week=80)
        self.assertEqual(risk.budget_asks([("opus", "medium")], "vua", 10, limits, now),
                         ["hạn mức tuần đã dùng 80% (từ 80%)"])
        limits, now = self.limits(week=10)
        self.assertEqual(risk.budget_asks([("opus", "medium")], "vua", 5000, limits, now), [],
                         "diff lớn chỉ hỏi ở mức cao")
        # Mức cao vì hook, khá lớn, không đổi test.
        body = "x = 1\n" * 199
        plain = risk.assess([change("plugin/hooks/sync.py", 200, 0, body)], writer="sonnet")
        called = risk.assess([change("plugin/hooks/sync.py", 200, 0, body + "requests.post(url)\n")], writer="sonnet")
        self.assertEqual((plain["level"], called["level"]), ("cao", "cao"), (plain, called))
        self.assertEqual(len(plain["reviewers"]), 1)
        # Gọi ra ngoài, thêm dependency: ranh giới tin cậy nhưng không kéo review kép (bước 5 chỉ tính xác thực, mã
        # hóa, input, chạy lệnh, dữ liệu nhạy cảm).
        self.assertEqual(len(called["reviewers"]), 1, called)
        ran = risk.assess([change("plugin/hooks/sync.py", 200, 0, body + "subprocess.run(cmd)\n")], writer="sonnet")
        self.assertEqual((ran["level"], len(ran["reviewers"])), ("cao", 2), ran)
        # Đường dẫn ký, jwt chỉ có trong CRYPTO_RE: vẫn là bảo mật, nên Sonnet viết thì hai reviewer, Opus xhigh.
        signing = risk.assess([change("plugin/hooks/signing.py", 200, 0, body)], writer="sonnet")
        self.assertEqual(signing["reviewers"], [{"model": "opus", "effort": "xhigh"}, {"model": "sonnet", "effort": "high"}])
        self.assertIn("differential-review", signing["review"])

    def test_render_shows_ask_line(self):
        future = {"rate_limits": {"seven_day": {"used_percentage": 90, "resets_at": 4_000_000_000}}}
        out = risk.render(risk.assess([change("app/auth/login.py", 40)], writer="opus", limits=future))
        self.assertIn("Review đề nghị: giao song song 2", out)
        self.assertIn("Hỏi người dùng trước khi giao review này: hạn mức tuần đã dùng 90% (từ 80%)", out)
        self.assertIn("chỉ một reviewer sonnet·high", out)


class Weakening(unittest.TestCase):
    """Nới test để cho đạt: assert chặt đổi sang dạng lỏng, bớt assert, thêm skip (ví dụ 3 của trang đánh giá)."""

    def reasons(self, *changes):
        return risk.assess([change("src/a.py", 2), *changes])

    def test_loosened_assert_with_same_line_count_is_flagged(self):
        r = self.reasons(change("tests/test_a.py", 1, 1, '        self.assertIn(r["level"], ("vừa", "cao"))',
                                '        self.assertEqual(r["level"], "cao")'))
        self.assertTrue(any("nới assert" in x for x in r["reasons"]), r["reasons"])
        self.assertIn("tests/test_a.py", dict(r["hotspots"]))
        self.assertEqual(r["level"], "vua")

    def test_pytest_equality_to_not_none_is_loosening(self):
        r = self.reasons(change("tests/test_b.py", 1, 1, "    assert x is not None", "    assert x == 3"))
        self.assertTrue(any("nới assert" in x for x in r["reasons"]), r["reasons"])

    def test_removed_and_commented_out_asserts_are_fewer_asserts(self):
        for added in ("", "    # self.assertEqual(a, 1)"):
            with self.subTest(added=added):
                r = self.reasons(change("tests/test_a.py", 1, 1, added, "    self.assertEqual(a, 1)"))
                self.assertTrue(any("bớt assert (+0/−1" in x for x in r["reasons"]), r["reasons"])

    def test_added_skip_is_flagged(self):
        for line in ("    @unittest.skip('tạm')", "@pytest.mark.xfail", "  it.skip('đăng nhập', () => {",
                     "        self.skipTest('chưa sửa')"):
            with self.subTest(line=line):
                r = self.reasons(change("tests/test_a.py", 1, 0, line))
                self.assertTrue(any("thêm skip" in x for x in r["reasons"]), r["reasons"])

    def test_legit_changes_are_not_flagged(self):
        cases = {
            "đổi giá trị mong đợi": [change("tests/test_a.py", 1, 1, "    self.assertEqual(x, 2)",
                                            "    self.assertEqual(x, 1)")],
            "đổi tên file test": [change("tests/test_old.py", 0, 2, "", "    assert a == 1\n    assert b == 2"),
                                  change("tests/test_new.py", 2, 0, "    assert a == 1\n    assert b == 2")],
            "thêm assert": [change("tests/test_a.py", 2, 0, "    self.assertTrue(ok)\n    assert y")],
            "assert trong code không phải test": [change("src/b.py", 1, 1, "    assert x", "    assert x == 1")],
            "skip trong chú thích": [change("tests/test_a.py", 1, 0, "    # @unittest.skip bỏ ngày 03/11")],
            "skip trong dữ liệu của test": [change("tests/test_a.py", 1, 0,
                                                   "        for line in (\"@unittest.skip('x')\", \"it.skip(\"):")],
        }
        for name, changes in cases.items():
            with self.subTest(name):
                r = self.reasons(*changes)
                self.assertFalse(any("assert" in x or "skip" in x for x in r["reasons"]), r["reasons"])

    def test_diff_lines_reads_removed_lines_and_content_that_looks_like_headers(self):
        patch = ("diff --git a/t.sql b/t.sql\n--- a/t.sql\n+++ b/t.sql\n@@ -1,2 +1,2 @@\n"
                 "--- ghi chú SQL bị xóa\n-select 1;\n+++ dòng thêm vào\n+select 2;\n"
                 "diff --git a/gone.py b/gone.py\ndeleted file mode 100644\n--- a/gone.py\n+++ /dev/null\n"
                 "@@ -1 +0,0 @@\n-x = 1\n")
        added, removed = risk.diff_lines(patch)
        self.assertEqual(added, {"t.sql": "++ dòng thêm vào\nselect 2;"})
        self.assertEqual(removed, {"t.sql": "-- ghi chú SQL bị xóa\nselect 1;", "gone.py": "x = 1"})


class DocOnly(TempDirTestCase):
    def test_reader_page_outside_agent_dir_is_a_doc_only_when_marked(self):
        (self.tmp / "HUONG-DAN.html").write_text('<main data-loai="giai-thich"></main>')
        (self.tmp / "index.html").write_text("<div id=app></div>")
        self.assertTrue(risk.doc_only("HUONG-DAN.html", self.tmp))
        self.assertFalse(risk.doc_only("index.html", self.tmp), "trang của web app là code")
        self.assertFalse(risk.doc_only("HUONG-DAN.html"), "không có gốc repo thì không đọc được dấu")
        self.assertTrue(risk.doc_only("PLAN.md") and risk.doc_only(".agent/trang/a.html"))
        self.assertFalse(risk.doc_only("plugin/skills/x/SKILL.md"), "chỉ dẫn cho agent không phải tài liệu")
        # Reviewer 03/11/2026: file mà test hay build đọc không được coi là tài liệu.
        for path in ("requirements.txt", "docs/conf.py", "docs/examples/a.py",
                     "plugin/skills/writing-voice/samples/kinh-dien/vi/a.md", "tests/data/expected.md"):
            self.assertFalse(risk.doc_only(path, self.tmp), path)


class Collect(TempDirTestCase):
    def git(self, *args):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
                       cwd=str(self.tmp), check=True, capture_output=True)

    def test_collects_tracked_and_untracked_changes(self):
        self.git("init", "-q")
        (self.tmp / "a.py").write_text("x = 1\n")
        self.git("add", "a.py")
        self.git("commit", "-q", "-m", "init")
        (self.tmp / "a.py").write_text("x = 2\ny = subprocess.run(c, shell=True)\n")
        (self.tmp / "new.md").write_text("một\nhai\n")
        changes = {c["path"]: c for c in risk.collect(self.tmp)}
        self.assertEqual(set(changes), {"a.py", "new.md"})
        self.assertEqual((changes["a.py"]["added"], changes["a.py"]["deleted"]), (2, 1))
        self.assertIn("shell=True", changes["a.py"]["text"])
        self.assertEqual(changes["new.md"]["added"], 2)
        self.assertEqual(changes["a.py"]["removed"], "x = 1")

    def test_reader_mark_outside_the_diff_still_counts(self):
        # sửa giữa trang HUONG-DAN.html: diff không chứa <main data-loai>, collect phải đọc cả file
        self.git("init", "-q")
        body = "\n".join(f"<p>đoạn {i}</p>" for i in range(30))
        (self.tmp / "HUONG-DAN.html").write_text(f'<main data-loai="giai-thich">\n{body}\n</main>\n')
        (self.tmp / "index.html").write_text(f"<div id=app>\n{body}\n</div>\n")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "init")
        for name in ("HUONG-DAN.html", "index.html"):
            path = self.tmp / name
            path.write_text(path.read_text().replace("đoạn 15", "đoạn mười lăm"))
        kinds = {c["path"]: risk.change_kind(c) for c in risk.collect(self.tmp)}
        self.assertEqual(kinds, {"HUONG-DAN.html": "doc", "index.html": "code"})

    def test_untracked_reader_page_keeps_mark_on_later_turns(self):
        # lượt sau chỉ chấm dòng mới (fresh_changes): dấu trang ở dòng cũ vẫn phải giữ trang là tài liệu
        self.git("init", "-q")
        (self.tmp / "a.py").write_text("x = 1\n")
        self.git("add", "a.py")
        self.git("commit", "-q", "-m", "init")
        page = self.tmp / "HUONG-DAN.html"
        page.write_text('<main data-loai="giai-thich">\n' + "\n".join(f"<p>{i}</p>" for i in range(200)) + "\n</main>\n")
        seen = {c["path"]: risk.line_hashes(c["text"]) for c in risk.collect(self.tmp)}
        page.write_text(page.read_text() + "\n".join(f"<p>mới {i}</p>" for i in range(200)) + "\n")
        picked, _ = risk.fresh_changes(risk.collect(self.tmp), seen)
        self.assertNotIn("data-loai", picked[0]["text"])
        self.assertEqual(risk.change_kind(picked[0]), "doc")

    def test_no_changes(self):
        self.git("init", "-q")
        (self.tmp / "a.py").write_text("x = 1\n")
        self.git("add", "a.py")
        self.git("commit", "-q", "-m", "init")
        self.assertEqual(risk.collect(self.tmp), [])

    def test_repo_without_commits(self):
        self.git("init", "-q")
        (self.tmp / "a.py").write_text("x = 1\n")
        self.assertEqual([c["path"] for c in risk.collect(self.tmp)], ["a.py"])

    def test_staged_then_edited_in_repo_without_commits(self):
        self.git("init", "-q")
        (self.tmp / "a.py").write_text("x = 1\n")
        self.git("add", "a.py")
        (self.tmp / "a.py").write_text("x = 1\nos.system(c)\n")
        changes = risk.collect(self.tmp)
        self.assertEqual([c["path"] for c in changes], ["a.py"])
        self.assertIn("os.system", changes[0]["text"])
        self.assertEqual(changes[0]["added"], 2)

    def test_unknown_base_is_an_error_not_an_empty_diff(self):
        self.git("init", "-q")
        (self.tmp / "a.py").write_text("x = 1\n")
        self.git("add", "a.py")
        self.git("commit", "-q", "-m", "init")
        (self.tmp / "a.py").write_text("x = 2\n")
        with self.assertRaises(risk.GitError):
            risk.collect(self.tmp, "nosuchref")
        out = subprocess.run([sys.executable, str(SCRIPTS / "risk.py"), str(self.tmp), "--base", "nosuchref"],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 2)
        self.assertIn("nosuchref", out.stdout + out.stderr)

    def test_cli_writer_limits_and_new_reach_the_review_plan(self):
        import json
        import os
        self.git("init", "-q")
        (self.tmp / "app" / "auth").mkdir(parents=True)
        (self.tmp / "app" / "auth" / "login.py").write_text("x = 1\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "init")
        (self.tmp / "app" / "auth" / "login.py").write_text("x = 1\n" + "y = 2\n" * 40)
        state = self.tmp / "state"
        state.mkdir()
        (state / "limits.json").write_text(json.dumps({
            "rate_limits": {"seven_day": {"used_percentage": 85, "resets_at": 4_000_000_000}},
            "model": {"id": "claude-sonnet-5-5"}}))
        env = dict(os.environ, AGENT_STACK_STATE=str(state))

        def run(*args):
            out = subprocess.run([sys.executable, str(SCRIPTS / "risk.py"), str(self.tmp), "--json", *args],
                                 capture_output=True, text=True, env=env)
            self.assertEqual(out.returncode, 0, out.stderr)
            return json.loads(out.stdout)

        first = run("--writer", "opus")
        self.assertEqual(first["level"], "cao")
        self.assertEqual(first["reviewers"], [{"model": "opus", "effort": "high"}, {"model": "sonnet", "effort": "high"}])
        self.assertEqual(first["ask"], ["hạn mức tuần đã dùng 85% (từ 80%)"])
        self.assertIn("(người viết: Opus)", first["review"])
        # Không truyền --writer: lấy model trong limits.json và nói rõ là suy đoán.
        guessed = run()
        self.assertIn("người viết: Sonnet, suy từ state/limits.json", guessed["review"])
        # Phần sửa sau lần chấm (mức vừa vì xóa file): một sonnet·high, dù Sonnet viết.
        with (self.tmp / "app" / "auth" / "login.py").open("a") as f:
            f.write("os.remove(path)\n")
        fix = run("--new", "--writer", "sonnet")
        self.assertEqual(fix["level"], "vua", fix)
        self.assertEqual(fix["reviewers"], [{"model": "sonnet", "effort": "high"}])

    def test_cli_outside_repo_exits_2(self):
        out = subprocess.run([sys.executable, str(SCRIPTS / "risk.py"), str(self.tmp)], capture_output=True, text=True)
        self.assertEqual(out.returncode, 2)
        self.assertIn("git", out.stdout + out.stderr)


if __name__ == "__main__":
    unittest.main()
