"""Khóa lại test đã mở khóa có lời duyệt (spec `khoa-lai-test`, TM-174): `receipt.py lock --relock`.

Viết TRƯỚC code. Test từng khóa, được người dùng duyệt mở (bản ghi `unlock` trong sổ), sửa xong thì khóa lại mà không
cần chứng minh trượt trước bản sửa (S1). Từ chối: chưa từng có bản ghi unlock (S2), lệnh test trượt (S3), file đang
khóa (S4). Khóa lại vẫn tính cho spec và hiện trong `receipt.py locks` (S5).
"""
import json
import sys

from tests._util import PLUGIN, TempDirTestCase, git, run_script

RECEIPT = PLUGIN / "skills" / "session-keeper" / "scripts" / "receipt.py"
SPEC = PLUGIN / "skills" / "session-keeper" / "scripts" / "spec.py"
sys.path.insert(0, str(PLUGIN / "lib"))
import testlock as TL  # noqa: E402

SLUG = "demo"
TEST_V1 = ("import unittest\n\n\nclass T(unittest.TestCase):\n    # spec:demo#S1\n    def test_a(self):\n"
           "        self.assertEqual(1 + 1, 2)\n")
# Bản sau khi sửa (đã được duyệt): thêm một hàm test.
TEST_V2 = TEST_V1 + "\n    # spec:demo#S1\n    def test_b(self):\n        self.assertEqual(2 + 2, 4)\n"
OTHER = "import unittest\n\n\nclass U(unittest.TestCase):\n    def test_o(self):\n        self.assertTrue(True)\n"
FAILING = ("import unittest\n\n\nclass T(unittest.TestCase):\n    def test_a(self):\n"
           "        self.assertEqual(1 + 1, 3)\n")
CMD = (sys.executable, "-m", "unittest", "test_calc")
CMD_BAD = (sys.executable, "-m", "unittest", "test_khong_ton_tai")
LOCKED_AGAIN = "đã khóa lại"
TS1, TS2 = "2026-11-18T09:00:00+07:00", "2026-11-19T10:30:00+07:00"


class RelockBase(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.state = self.tmp / "state"
        self.repo = self.tmp / "proj"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        (self.repo / "README.md").write_text("# demo\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "init")

    def put(self, rel, text):
        path = self.repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def run_receipt(self, *args):
        return run_script(RECEIPT, *args, env={"AGENT_STACK_STATE": str(self.state)})

    def relock(self, *tests, cmd=CMD):
        out = self.run_receipt("lock", "--relock", "--project", str(self.repo), "--tests", *tests, "--", *cmd)
        return out, out.stdout + out.stderr

    def seed(self, files=None, approvals=None):
        """Ghi sổ khóa trực tiếp: files {đường dẫn: (nội dung, mức)} (mục khóa như `lock` ghi), approvals là danh sách."""
        book = TL.empty()
        for rel, (text, level) in (files or {}).items():
            book["files"][rel] = TL.entry_for(text.encode("utf-8"), level)
        book["approvals"] = list(approvals or [])
        TL.save(self.repo, book)

    @staticmethod
    def unlock_record(rel, text, level="cao", reason="người dùng duyệt sửa test", ts=TS1):
        return {"path": rel, "action": "unlock", "reason": reason, "sha256": TL.digest(text.encode("utf-8")),
                "level": level, "ts": ts}

    def book_path(self):
        return self.repo / TL.LOCK_REL

    def book_bytes(self):
        path = self.book_path()
        return path.read_bytes() if path.exists() else None

    def book(self):
        return json.loads(self.book_path().read_text(encoding="utf-8"))

    def assertBookUnchanged(self, before):
        self.assertEqual(self.book_bytes(), before, "sổ khóa không được đổi")

    def assertFlagAccepted(self, text):
        """Từ chối do chính `--relock`, không phải argparse chê cờ lạ."""
        self.assertNotIn("usage:", text, "cờ --relock phải được nhận")


class RelockAccepted(RelockBase):
    def test_relock_after_unlock_restores_entry_with_relock_info(self):
        # spec:khoa-lai-test#S1
        # Dựng bằng chính receipt.py: khóa (sổ), mở khóa kèm lý do, sửa file, rồi khóa lại.
        self.put("test_calc.py", TEST_V1)
        self.put("test_other.py", OTHER)
        self.seed({"test_calc.py": (TEST_V1, "cao"), "test_other.py": (OTHER, "vua")})
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "khóa")
        out = self.run_receipt("unlock", "--project", str(self.repo), "--reason", "duyệt sửa test_calc", "test_calc.py")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        record = [a for a in self.book()["approvals"] if a["action"] == "unlock"][-1]
        other_entry = self.book()["files"]["test_other.py"]
        self.put("test_calc.py", TEST_V2)
        out, text = self.relock("test_calc.py")
        self.assertEqual(out.returncode, 0, text)
        self.assertIn(LOCKED_AGAIN, text)
        book = self.book()
        entry = book["files"]["test_calc.py"]
        self.assertEqual(entry["level"], "cao", "mức của lần khóa trước, không thấp hơn")
        self.assertEqual(entry["relock"], {"reason": "duyệt sửa test_calc", "unlocked_at": record["ts"]})
        self.assertNotIn("red", entry)
        self.assertEqual(entry["sha256"], TL.digest(TEST_V2.encode("utf-8")), "khóa nội dung hiện tại")
        self.assertEqual(TL.status(self.repo, "test_calc.py", entry), "same")
        self.assertEqual(book["files"]["test_other.py"], other_entry, "mục khóa khác giữ nguyên")
        self.assertIn(record, book["approvals"], "bản ghi unlock vẫn còn trong sổ")

    def test_level_is_that_of_the_unlock_record(self):
        # spec:khoa-lai-test#S1
        for level in ("vua", "cao"):
            with self.subTest(level):
                self.put("test_calc.py", TEST_V2)
                self.seed(approvals=[self.unlock_record("test_calc.py", TEST_V1, level=level)])
                out, text = self.relock("test_calc.py")
                self.assertEqual(out.returncode, 0, text)
                self.assertEqual(self.book()["files"]["test_calc.py"]["level"], level)

    def test_most_recent_unlock_record_decides_reason_and_time(self):
        # spec:khoa-lai-test#S1
        self.put("test_calc.py", TEST_V2)
        older = self.unlock_record("test_calc.py", TEST_V1, level="cao", reason="lần mở thứ nhất", ts=TS1)
        newer = self.unlock_record("test_calc.py", TEST_V1, level="vua", reason="lần mở thứ hai", ts=TS2)
        noise = self.unlock_record("test_khac.py", OTHER, level="cao", reason="file khác", ts="2026-11-20T08:00:00+07:00")
        self.seed(approvals=[older, newer, noise])
        out, text = self.relock("test_calc.py")
        self.assertEqual(out.returncode, 0, text)
        entry = self.book()["files"]["test_calc.py"]
        self.assertEqual(entry["relock"], {"reason": "lần mở thứ hai", "unlocked_at": TS2})
        self.assertEqual(entry["level"], "vua")
        self.assertNotIn("test_khac.py", self.book()["files"])

    def test_relock_several_files_at_once(self):
        # spec:khoa-lai-test#S1
        self.put("test_calc.py", TEST_V2)
        self.put("test_other.py", OTHER)
        self.seed(approvals=[self.unlock_record("test_calc.py", TEST_V1, reason="lý do A", ts=TS1),
                             self.unlock_record("test_other.py", OTHER, level="vua", reason="lý do B", ts=TS2)])
        out, text = self.relock("test_calc.py", "test_other.py")
        self.assertEqual(out.returncode, 0, text)
        files = self.book()["files"]
        self.assertEqual(sorted(files), ["test_calc.py", "test_other.py"])
        self.assertEqual(files["test_calc.py"]["relock"], {"reason": "lý do A", "unlocked_at": TS1})
        self.assertEqual(files["test_other.py"]["relock"], {"reason": "lý do B", "unlocked_at": TS2})
        self.assertEqual(files["test_other.py"]["level"], "vua")

    def test_relock_does_not_need_failing_test_before_the_fix(self):
        # spec:khoa-lai-test#S1
        # Test đạt cả trên commit gốc: `lock` thường (fails-before) sẽ từ chối, `--relock` thì không đòi trượt trước.
        self.put("test_calc.py", TEST_V1)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "test đạt sẵn")
        self.seed(approvals=[self.unlock_record("test_calc.py", TEST_V1)])
        out, text = self.relock("test_calc.py")
        self.assertEqual(out.returncode, 0, text)
        self.assertIn(LOCKED_AGAIN, text)
        self.assertIn("test_calc.py", self.book()["files"])


class RelockWithoutUnlockRecord(RelockBase):
    def assertRefused(self, out, text):
        self.assertFlagAccepted(text)
        self.assertEqual(out.returncode, 2, text)
        self.assertNotIn(LOCKED_AGAIN, text)
        self.assertRegex(text, r"lock --red|fails-before", "nhắc dùng lock thường (fails-before) hay lock --red")

    def test_never_locked_file_is_refused_and_book_not_written(self):
        # spec:khoa-lai-test#S2
        self.put("test_calc.py", TEST_V1)
        out, text = self.relock("test_calc.py")
        self.assertRefused(out, text)
        self.assertFalse(self.book_path().exists(), "không tạo sổ")

    def test_unlock_record_of_another_path_does_not_count(self):
        # spec:khoa-lai-test#S2
        self.put("test_calc.py", TEST_V1)
        self.put("test_other.py", OTHER)
        self.seed({"test_other.py": (OTHER, "cao")},
                  [self.unlock_record("test_khac.py", OTHER), self.unlock_record("sub/test_calc.py", TEST_V1)])
        before = self.book_bytes()
        out, text = self.relock("test_calc.py")
        self.assertRefused(out, text)
        self.assertBookUnchanged(before)

    def test_record_with_other_action_does_not_count(self):
        # spec:khoa-lai-test#S2
        self.put("test_calc.py", TEST_V1)
        record = dict(self.unlock_record("test_calc.py", TEST_V1), action="approve")
        self.seed(approvals=[record])
        before = self.book_bytes()
        out, text = self.relock("test_calc.py")
        self.assertRefused(out, text)
        self.assertBookUnchanged(before)

    def test_first_lock_by_red_cannot_use_relock(self):
        # spec:khoa-lai-test#S2
        # Test viết trước, chưa khóa lần nào, đang đỏ: --relock không phải đường vòng quanh `lock --red`.
        self.put("test_calc.py", FAILING)
        out, text = self.relock("test_calc.py", cmd=(sys.executable, "-m", "unittest", "test_calc"))
        self.assertFlagAccepted(text)
        self.assertNotEqual(out.returncode, 0, text)
        self.assertFalse(self.book_path().exists())
        out, text = self.relock("test_calc.py")
        self.assertRefused(out, text)


class RelockFailingCommand(RelockBase):
    def setUp(self):
        super().setUp()
        self.put("test_calc.py", TEST_V2)
        self.seed(approvals=[self.unlock_record("test_calc.py", TEST_V1)])
        self.before = self.book_bytes()

    def test_failing_test_is_not_locked(self):
        # spec:khoa-lai-test#S3
        self.put("test_calc.py", FAILING)
        out, text = self.relock("test_calc.py")
        self.assertFlagAccepted(text)
        self.assertNotEqual(out.returncode, 0, text)
        self.assertNotIn(LOCKED_AGAIN, text)
        self.assertBookUnchanged(self.before)

    def test_command_that_cannot_run_is_not_locked(self):
        # spec:khoa-lai-test#S3
        for name, cmd in (("module không có", CMD_BAD), ("lệnh không có", ("khong-co-lenh-nay-xyz", "--chay"))):
            with self.subTest(name):
                out, text = self.relock("test_calc.py", cmd=cmd)
                self.assertFlagAccepted(text)
                self.assertNotEqual(out.returncode, 0, text)
                self.assertNotIn(LOCKED_AGAIN, text)
                self.assertBookUnchanged(self.before)

    def test_one_failing_run_locks_none_of_several_files(self):
        # spec:khoa-lai-test#S3
        self.put("test_other.py", OTHER)
        self.seed(approvals=[self.unlock_record("test_calc.py", TEST_V1), self.unlock_record("test_other.py", OTHER)])
        before = self.book_bytes()
        out, text = self.relock("test_calc.py", "test_other.py", cmd=CMD_BAD)
        self.assertFlagAccepted(text)
        self.assertNotEqual(out.returncode, 0, text)
        self.assertBookUnchanged(before)


class RelockOfLockedFile(RelockBase):
    def test_already_locked_file_is_refused_and_entry_unchanged(self):
        # spec:khoa-lai-test#S4
        self.put("test_calc.py", TEST_V1)
        self.seed({"test_calc.py": (TEST_V1, "cao")}, [self.unlock_record("test_calc.py", TEST_V1)])
        before = self.book_bytes()
        out, text = self.relock("test_calc.py")
        self.assertFlagAccepted(text)
        self.assertEqual(out.returncode, 2, text)
        self.assertNotIn(LOCKED_AGAIN, text)
        self.assertRegex(text, r"đang khóa|có trong sổ|đã khóa(?! lại)", "nói file đang khóa")
        self.assertBookUnchanged(before)
        self.assertNotIn("relock", self.book()["files"]["test_calc.py"])

    def test_edited_locked_file_cannot_be_laundered_through_relock(self):
        # spec:khoa-lai-test#S4
        # Chiêu cần chặn: sửa file khóa kiểu nới rồi `--relock` để sổ ghi nội dung mới mà không ai duyệt.
        self.put("test_calc.py", TEST_V1.replace("1 + 1, 2", "1 + 1, 1 + 1"))
        self.seed({"test_calc.py": (TEST_V1, "cao")}, [self.unlock_record("test_calc.py", TEST_V1)])
        before = self.book_bytes()
        out, text = self.relock("test_calc.py")
        self.assertFlagAccepted(text)
        self.assertEqual(out.returncode, 2, text)
        self.assertNotIn(LOCKED_AGAIN, text)
        self.assertRegex(text, r"đang khóa|có trong sổ|đã khóa(?! lại)", "nói file đang khóa")
        self.assertBookUnchanged(before)
        self.assertEqual(self.book()["files"]["test_calc.py"]["sha256"], TL.digest(TEST_V1.encode("utf-8")))

    def test_relocked_file_cannot_be_relocked_again(self):
        # spec:khoa-lai-test#S4
        self.put("test_calc.py", TEST_V2)
        self.seed(approvals=[self.unlock_record("test_calc.py", TEST_V1)])
        out, text = self.relock("test_calc.py")
        self.assertEqual(out.returncode, 0, text)
        before = self.book_bytes()
        out, text = self.relock("test_calc.py")
        self.assertFlagAccepted(text)
        self.assertEqual(out.returncode, 2, text)
        self.assertNotIn(LOCKED_AGAIN, text)
        self.assertRegex(text, r"đang khóa|có trong sổ|đã khóa(?! lại)", "nói file đang khóa")
        self.assertBookUnchanged(before)

    def test_locked_file_blocks_the_whole_command(self):
        # spec:khoa-lai-test#S4
        # Một file đang khóa chung lệnh với file hợp lệ: không file nào được ghi (sổ giữ nguyên).
        self.put("test_calc.py", TEST_V2)
        self.put("test_other.py", OTHER)
        self.seed({"test_other.py": (OTHER, "vua")},
                  [self.unlock_record("test_calc.py", TEST_V1), self.unlock_record("test_other.py", OTHER)])
        before = self.book_bytes()
        out, text = self.relock("test_calc.py", "test_other.py")
        self.assertFlagAccepted(text)
        self.assertEqual(out.returncode, 2, text)
        self.assertBookUnchanged(before)


class RelockCountsForSpec(RelockBase):
    def setUp(self):
        super().setUp()
        self.put(f".agent/spec/{SLUG}.txt", "S1: Khi a thì b.\n")
        self.put("test_calc.py", TEST_V1)
        self.seed({"test_calc.py": (TEST_V1, "cao")})
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "khóa")
        out = self.run_receipt("unlock", "--project", str(self.repo), "--reason", "duyệt sửa", "test_calc.py")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.put("test_calc.py", TEST_V2)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "sửa")

    def spec_check(self):
        out = run_script(SPEC, "check", "--project", str(self.repo), env={"AGENT_STACK_STATE": str(self.state)})
        return out, out.stdout + out.stderr

    def test_spec_check_counts_relocked_file_as_locked(self):
        # spec:khoa-lai-test#S5
        out, text = self.spec_check()
        self.assertEqual(out.returncode, 1, "đang mở khóa thì dòng spec chưa có test khóa\n" + text)
        out, text = self.relock("test_calc.py")
        self.assertEqual(out.returncode, 0, text)
        out, text = self.spec_check()
        self.assertEqual(out.returncode, 0, text)
        self.assertIn("1 có test khóa", text)

    def test_locks_listing_marks_relocked_entry(self):
        # spec:khoa-lai-test#S5
        self.put("test_other.py", OTHER)
        book = TL.load(self.repo)
        book["files"]["test_other.py"] = TL.entry_for(OTHER.encode("utf-8"), "vua")
        TL.save(self.repo, book)
        out, text = self.relock("test_calc.py")
        self.assertEqual(out.returncode, 0, text)
        out = self.run_receipt("locks", "--project", str(self.repo))
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        lines = {ln.split(":")[0].lstrip("- "): ln for ln in out.stdout.splitlines() if ln.startswith("- ")}
        self.assertIn("(khóa lại sau khi mở khóa)", lines["test_calc.py"])
        self.assertNotIn("(khóa lại sau khi mở khóa)", lines["test_other.py"], "chỉ mục khóa lại mới có ghi chú")
