"""Spec theo lát (GĐ6, spec `gd6-spec-theo-lat`): `plugin/lib/specbook.py` và `session-keeper/scripts/spec.py`.

Viết TRƯỚC code. S1: lỗi mẫu dòng, số trùng hay lùi (mã 1, nêu số dòng). S2: dòng spec không có dấu test hay file test
chưa khóa (mã 1). S10: `spec.py page` thoát chữ bằng html.escape, qua check_page.py, nằm ngoài đường dẫn spec.
"""
import hashlib
import re
import sys

from tests._util import PLUGIN, TempDirTestCase, git, run_script

SPEC = PLUGIN / "skills" / "session-keeper" / "scripts" / "spec.py"
CHECK_PAGE = PLUGIN / "skills" / "reader-page" / "scripts" / "check_page.py"
RATCHET_DIR = PLUGIN / "skills" / "done-gate" / "scripts"
sys.path.insert(0, str(PLUGIN / "lib"))
import testlock as TL  # noqa: E402

SLUG = "demo"
GOOD = "S1: Khi a thì b.\nS2: Nếu c thì d.\nS3: Trong khi e thì f.\n"
TEST_BODY = "import unittest\n\n\nclass T(unittest.TestCase):\n    # spec:demo#S1\n    def test_a(self):\n        pass\n"


def specbook():
    """Nạp specbook khi test chạy, để thiếu module chỉ làm trượt test cần nó."""
    import specbook as sb
    return sb


class SpecRepo(TempDirTestCase):
    """Repo git nhỏ trong thư mục tạm: một file spec, vài file test, sổ khóa tùy chọn."""

    def setUp(self):
        super().setUp()
        self.state = self.tmp / "state"
        self.repo = self.tmp / "proj"
        self.repo.mkdir()
        git(self.repo, "init", "-q")

    def put(self, rel, text):
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def spec(self, text, slug=SLUG):
        return self.put(f".agent/spec/{slug}.txt", text)

    def add_test(self, rel, markers, lock=True):
        """File test mang các dấu `spec:<slug>#Sn` (mỗi dấu một dòng chú thích); lock=True thì vào sổ khóa."""
        body = "".join(f"# spec:{SLUG}#{m}\n" for m in markers) + "x = 1\n"
        path = self.put(rel, body)
        if lock:
            book = TL.load(self.repo)
            book["files"][rel] = TL.entry_for(body.encode("utf-8"), "vua")
            TL.save(self.repo, book)
        return path

    def commit(self):
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "fixture")

    def cli(self, *args, project=True):
        self.assertTrue(SPEC.is_file(), "thiếu spec.py (mã 2 của python khi không mở được file không tính là kết quả)")
        extra = ["--project", str(self.repo)] if project else []
        return run_script(SPEC, *args, *extra, env={"AGENT_STACK_STATE": str(self.state)})

    def check(self, *args):
        self.commit()
        out = self.cli("check", *args)
        return out, out.stdout + out.stderr


class ParseFormat(SpecRepo):
    def test_valid_file_parses_without_errors(self):
        # spec:gd6-spec-theo-lat#S1
        text = "# tiêu đề\n\nS1: Khi a thì b.\n\nS3: nếu c thì d.\nS7: Trong khi e thì f.\nS8: KHI g THÌ h.\n"
        got = specbook().parse(text)
        self.assertEqual(got["errors"], [])
        self.assertEqual([(x["id"], x["n"], x["lineno"]) for x in got["lines"]],
                         [("S1", 1, 3), ("S3", 3, 5), ("S7", 7, 6), ("S8", 8, 7)])
        self.assertEqual(got["lines"][0]["text"], "Khi a thì b.")

    def test_line_missing_then_is_an_error(self):
        # spec:gd6-spec-theo-lat#S1
        got = specbook().parse("S1: Khi a thì b.\nS2: Khi a mà không có từ nối.\n")
        self.assertEqual([e["lineno"] for e in got["errors"]], [2])
        self.assertTrue(got["errors"][0]["msg"])

    def test_line_starting_with_other_word_is_an_error(self):
        # spec:gd6-spec-theo-lat#S1
        got = specbook().parse("S1: Giả sử a thì b.\n")
        self.assertEqual([e["lineno"] for e in got["errors"]], [1])

    def test_line_not_matching_pattern_at_all_is_an_error(self):
        # spec:gd6-spec-theo-lat#S1
        for bad in ("- S1: Khi a thì b.", "S1 Khi a thì b.", "văn xuôi tự do", "Khi a thì b."):
            with self.subTest(bad):
                self.assertEqual([e["lineno"] for e in specbook().parse(bad + "\n")["errors"]], [1])

    def test_duplicate_id_is_an_error(self):
        # spec:gd6-spec-theo-lat#S1
        got = specbook().parse("S1: Khi a thì b.\nS2: Khi c thì d.\nS2: Khi e thì f.\n")
        self.assertEqual([e["lineno"] for e in got["errors"]], [3])

    def test_backward_id_is_an_error(self):
        # spec:gd6-spec-theo-lat#S1
        got = specbook().parse("S1: Khi a thì b.\nS5: Khi c thì d.\n\nS3: Khi e thì f.\n")
        self.assertEqual([e["lineno"] for e in got["errors"]], [4])

    def test_cli_valid_file_passes_format(self):
        # spec:gd6-spec-theo-lat#S1
        self.spec(GOOD)
        for sid in ("S1", "S2", "S3"):
            self.add_test(f"tests/test_{sid.lower()}.py", [sid])
        out, text = self.check()
        self.assertEqual(out.returncode, 0, text)

    def test_cli_format_error_exits_1_and_names_line_number(self):
        # spec:gd6-spec-theo-lat#S1
        # Dòng lỗi ở dòng 5 của file (sau comment và dòng trống), để số dòng không trùng số thứ tự S.
        self.spec("# tiêu đề\n\nS1: Khi a thì b.\n\nS2: Khi c nhưng thiếu từ nối.\nS3: Khi e thì f.\n")
        self.add_test("tests/test_all.py", ["S1", "S2", "S3"])
        out, text = self.check()
        self.assertEqual(out.returncode, 1, text)
        self.assertRegex(text, r"demo\.txt:5:")

    def test_cli_each_kind_of_format_error_exits_1(self):
        # spec:gd6-spec-theo-lat#S1
        cases = {"thiếu thì": "S1: Khi a mà thôi.\n", "từ lạ": "S1: Giả sử a thì b.\n",
                 "trùng số": "S1: Khi a thì b.\nS1: Khi c thì d.\n", "lùi số": "S4: Khi a thì b.\nS2: Khi c thì d.\n"}
        for name, text in cases.items():
            with self.subTest(name):
                self.spec(text)
                self.add_test("tests/test_all.py", ["S1", "S2", "S4"])
                out, said = self.check()
                self.assertEqual(out.returncode, 1, said)
                self.assertRegex(said, r"demo\.txt:\d+:")

    def test_cli_duplicate_id_names_the_second_line(self):
        # spec:gd6-spec-theo-lat#S1
        self.spec("S1: Khi a thì b.\nS2: Khi c thì d.\n# ghi chú\nS2: Khi e thì f.\n")
        self.add_test("tests/test_all.py", ["S1", "S2"])
        out, text = self.check()
        self.assertEqual(out.returncode, 1, text)
        self.assertRegex(text, r"demo\.txt:4:")


class LineHash(SpecRepo):
    def test_hash_is_16_hex_and_ignores_whitespace_noise(self):
        # spec:gd6-spec-theo-lat#S2
        sb = specbook()
        base = sb.line_hash("S1", "Khi a thì b.")
        self.assertRegex(base, r"^[0-9a-f]{16}$")
        self.assertEqual(base, sb.line_hash("S1", "  Khi   a  thì b.  "))
        self.assertNotEqual(base, sb.line_hash("S2", "Khi a thì b."))
        self.assertNotEqual(base, sb.line_hash("S1", "Khi a thì c."))


class Markers(SpecRepo):
    def test_markers_find_test_files_with_exact_word_boundary(self):
        # spec:gd6-spec-theo-lat#S2
        self.add_test("tests/test_one.py", ["S1"], lock=False)
        self.add_test("tests/test_twelve.py", ["S12"], lock=False)
        self.add_test("src/web/a.test.js", ["S1", "S2"], lock=False)
        self.add_test("pkg/foo_test.go", ["S2"], lock=False)
        self.put("src/app.py", f"# spec:{SLUG}#S1 nằm trong file không phải test\n")
        self.put("tests/test_other.py", "# spec:khac#S1\n")
        self.commit()
        got = specbook().markers(self.repo, SLUG)
        self.assertCountEqual(got.get("S1", []), ["tests/test_one.py", "src/web/a.test.js"])
        self.assertCountEqual(got.get("S2", []), ["src/web/a.test.js", "pkg/foo_test.go"])
        self.assertEqual(got.get("S12", []), ["tests/test_twelve.py"])


class CheckMarkersAndLocks(SpecRepo):
    def test_missing_marker_exits_1_and_names_the_line_id(self):
        # spec:gd6-spec-theo-lat#S2
        self.spec("S1: Khi a thì b.\nS3: Khi c thì d.\n")
        self.add_test("tests/test_a.py", ["S1"])
        out, text = self.check()
        self.assertEqual(out.returncode, 1, text)
        self.assertIn("S3", text)

    def test_marker_present_but_file_not_locked_exits_1(self):
        # spec:gd6-spec-theo-lat#S2
        self.spec("S1: Khi a thì b.\n")
        self.add_test("tests/test_a.py", ["S1"], lock=False)
        out, text = self.check()
        self.assertEqual(out.returncode, 1, text)
        self.assertIn("test_a.py", text)

    def test_marker_present_and_locked_exits_0(self):
        # spec:gd6-spec-theo-lat#S2
        self.spec("S1: Khi a thì b.\n")
        self.add_test("tests/test_a.py", ["S1"])
        out, text = self.check()
        self.assertEqual(out.returncode, 0, text)

    def test_one_locked_file_is_not_enough_when_another_carrying_file_is_unlocked(self):
        # spec:gd6-spec-theo-lat#S2
        self.spec("S1: Khi a thì b.\n")
        self.add_test("tests/test_a.py", ["S1"])
        self.add_test("tests/test_b.py", ["S1"], lock=False)
        out, text = self.check()
        self.assertEqual(out.returncode, 1, text)
        self.assertIn("test_b.py", text)

    def test_marker_s12_does_not_satisfy_s1(self):
        # spec:gd6-spec-theo-lat#S2
        self.spec("S1: Khi a thì b.\n")
        self.add_test("tests/test_a.py", ["S12"])
        out, text = self.check()
        self.assertEqual(out.returncode, 1, text)
        self.assertIn("S1", text)

    def test_marker_for_another_slug_does_not_count(self):
        # spec:gd6-spec-theo-lat#S2
        self.spec("S1: Khi a thì b.\n")
        body = "# spec:khac#S1\n"
        self.put("tests/test_a.py", body)
        book = TL.load(self.repo)
        book["files"]["tests/test_a.py"] = TL.entry_for(body.encode(), "vua")
        TL.save(self.repo, book)
        out, text = self.check()
        self.assertEqual(out.returncode, 1, text)

    def test_default_checks_every_spec_file_and_slug_or_path_selects_one(self):
        # spec:gd6-spec-theo-lat#S2
        self.spec("S1: Khi a thì b.\n")
        self.add_test("tests/test_a.py", ["S1"])
        self.spec("S1: Khi a thì b.\n", slug="loi")  # không có test mang dấu `spec:loi#S1`
        self.commit()
        self.assertEqual(self.cli("check").returncode, 1)
        self.assertEqual(self.cli("check", SLUG).returncode, 0)
        self.assertEqual(self.cli("check", ".agent/spec/demo.txt").returncode, 0)
        self.assertEqual(self.cli("check", "loi").returncode, 1)


class InputErrors(SpecRepo):
    def test_no_spec_file_exits_2(self):
        # spec:gd6-spec-theo-lat#S2
        self.put("README", "x\n")
        out, text = self.check()
        self.assertEqual(out.returncode, 2, text)

    def test_unknown_slug_exits_2(self):
        # spec:gd6-spec-theo-lat#S2
        self.spec(GOOD)
        out, text = self.check("khong-co")
        self.assertEqual(out.returncode, 2, text)

    def test_not_a_git_repo_exits_2(self):
        # spec:gd6-spec-theo-lat#S2
        plain = self.tmp / "plain"
        (plain / ".agent" / "spec").mkdir(parents=True)
        (plain / ".agent" / "spec" / "demo.txt").write_text(GOOD, encoding="utf-8")
        self.assertTrue(SPEC.is_file(), "thiếu spec.py")
        out = run_script(SPEC, "check", "--project", str(plain), env={"AGENT_STACK_STATE": str(self.state)})
        self.assertEqual(out.returncode, 2, out.stdout + out.stderr)


class Status(SpecRepo):
    def test_status_prints_a_line_per_spec_file_and_exits_0(self):
        # spec:gd6-spec-theo-lat#S2
        self.spec(GOOD)
        self.spec("S1: Khi a thì b.\n", slug="hai")
        self.commit()
        out = self.cli("status")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("demo", out.stdout)
        self.assertIn("hai", out.stdout)


class Page(SpecRepo):
    EVIL = 'S2: Khi <script>alert(1)</script> chạy thì trang "onload=boom() không thành thẻ sống.\n'

    def build(self):
        self.spec("S1: Khi a thì b.\n" + self.EVIL)
        self.add_test("tests/test_a.py", ["S1", "S2"])
        self.commit()
        out = self.cli("page", SLUG)
        return out, self.repo / ".agent" / "trang" / f"{SLUG}-spec.html"

    def test_page_is_written_at_expected_path_and_printed(self):
        # spec:gd6-spec-theo-lat#S10
        out, page = self.build()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue(page.is_file(), out.stdout + out.stderr)
        self.assertEqual(out.stdout.strip().splitlines()[-1].strip(), str(page))
        # Trang không làm spec đổi chữ và không đẻ file mới cạnh spec.
        self.assertEqual([p.name for p in (self.repo / ".agent" / "spec").iterdir()], [f"{SLUG}.txt"])

    def test_page_path_is_outside_the_spec_path_regex(self):
        # spec:gd6-spec-theo-lat#S10
        sys.path.insert(0, str(RATCHET_DIR))
        import ratchet
        out, page = self.build()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        rel = page.relative_to(self.repo).as_posix()
        self.assertEqual(rel, ".agent/trang/demo-spec.html")
        self.assertIsNone(ratchet.SPEC_RE.search(rel.lower()))

    def test_page_escapes_every_spec_text(self):
        # spec:gd6-spec-theo-lat#S10
        out, page = self.build()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        html = page.read_text(encoding="utf-8")
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn('"onload=', html)
        self.assertIn("&quot;onload=", html)
        self.assertEqual(html.count("alert(1)"), html.count("&lt;script&gt;alert(1)&lt;/script&gt;"))

    def test_page_is_a_tool_page_with_export_and_passes_check_page(self):
        # spec:gd6-spec-theo-lat#S10
        out, page = self.build()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        html = page.read_text(encoding="utf-8")
        self.assertRegex(html, r"<main\b[^>]*data-loai=\"cong-cu\"")
        self.assertIn("data-xuat", html)
        res = run_script(CHECK_PAGE, str(page))
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_page_shows_sha_prefix_and_approval_sentence(self):
        # spec:gd6-spec-theo-lat#S10
        out, page = self.build()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        sha = hashlib.sha256((self.repo / ".agent" / "spec" / f"{SLUG}.txt").read_bytes()).hexdigest()[:12]
        html = page.read_text(encoding="utf-8")
        self.assertIn(f"duyệt spec {sha}", html)
        self.assertRegex(html, re.escape(sha))

    def test_page_for_unknown_slug_exits_2(self):
        # spec:gd6-spec-theo-lat#S10
        self.spec(GOOD)
        self.commit()
        out = self.cli("page", "khong-co")
        self.assertEqual(out.returncode, 2, out.stdout + out.stderr)
        self.assertFalse((self.repo / ".agent" / "trang").exists())
