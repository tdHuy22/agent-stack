import json
import os
import stat
import sys
import time
import unittest
from unittest import mock

from pathlib import Path

from tests._util import PLUGIN, REPO, TempDirTestCase, git

sys.path.insert(0, str(PLUGIN / "lib"))
import agentstack as A  # noqa: E402

# Cùng cấu trúc với mục §0 thật của người dùng (SCEE/PLAN.md), nội dung giả.
PLAN = """# PLAN — luận văn mẫu

**Ràng buộc thật:**
- **Mốc test hiện hành: `120 passed, 3 xfailed`** (28/09/2026).

---

## 0. Đang ở đâu, việc tiếp theo (cập nhật mỗi lần dừng phiên)

*Cập nhật 30/09/2026.* Đọc mục này trước tiên sau mỗi lần compact. Dữ liệu ở `Process/2026-09-28_bao-cao/`.

- **Xong:** G0 (trừ một ghi chú). G0.5 phần đọc paper.
- **Hướng đã chốt ngày 30/09 (user): làm bản ỨNG DỤNG.** Không chạy theo novelty.
- **Việc tiếp theo, theo thứ tự:**
  1. User chạy `/compact`.
  2. Lập **danh sách dọn** về một phiên bản.
     User duyệt rồi mới làm.
  3. Viết tài liệu thiết kế.
- **Quyết định còn treo:** không có.
- **Sau mỗi lần bị ngắt vì hết limit:** chạy kiểm tra nhanh:
  - `git status`;
  - pytest phải ra đúng mốc ở trên;

## 1. Giai đoạn

### G0
- [x] Dọn kho
- [x] Đọc paper

### G1
- [x] Khung
- [ ] Viết phần thiết kế
- [ ] Thử nghiệm
"""


class Section0(unittest.TestCase):
    def test_parse_fields_like_users_plan(self):
        sec = A.parse_section0(PLAN)
        self.assertTrue(sec["heading"].startswith("0."))
        self.assertEqual(sec["updated"], "2026-09-30")  # không lấy nhầm ngày trong đường dẫn
        self.assertIn("G0", sec["fields"]["done"])
        self.assertEqual(len(sec["next"]), 3)
        self.assertIn("User duyệt rồi mới làm", sec["next"][1])  # dòng nối tiếp được gộp
        self.assertEqual(sec["fields"]["decisions"], "không có.")
        self.assertEqual(sec["after_interrupt"][0], "`git status`;")
        self.assertTrue(any("ỨNG DỤNG" in n for n in sec["notes"]))

    def test_baseline_found_outside_section0(self):
        self.assertEqual(A.baseline_anywhere(PLAN), "120 passed, 3 xfailed")

    def test_checkbox_progress_and_current_phase(self):
        prog = A.checkbox_progress(PLAN)
        self.assertEqual((prog["done"], prog["total"]), (3, 5))
        self.assertEqual(prog["current"]["title"], "G1")
        self.assertEqual(prog["current"]["first_todo"], "Viết phần thiết kế")

    def test_english_and_iso_date(self):
        sec = A.parse_section0("## Where we are\nUpdated 2026-10-01.\n- **Next:**\n  1. Ship it\n")
        self.assertEqual((sec["updated"], sec["next"]), ("2026-10-01", ["Ship it"]))

    def test_fold(self):
        self.assertEqual(A.fold("Đang dở, Việc tiếp theo"), "dang do, viec tiep theo")


class PlanFilesAndGit(TempDirTestCase):
    def test_no_plan_means_empty_brief(self):
        self.assertEqual(A.brief(self.tmp), {})

    def test_newest_plan_wins(self):
        self.write("PLAN.md", PLAN)
        old = time.time() - 3600
        os.utime(self.tmp / "PLAN.md", (old, old))
        self.write(".agent/HANDOFF.md", "# HANDOFF\n\n## 0. Đang ở đâu\n- **Việc tiếp theo:**\n  1. Bước từ handoff\n")
        path, _, sec = A.read_plan(self.tmp)
        self.assertEqual(path.name, "HANDOFF.md")
        self.assertEqual(sec["next"], ["Bước từ handoff"])

    def test_brief_with_git(self):
        self.write("PLAN.md", PLAN)
        git(self.tmp, "init", "-q")
        git(self.tmp, "add", "-A")
        git(self.tmp, "commit", "-q", "-m", "init")
        self.write("src/a.py", "x = 1\n")
        info = A.brief(self.tmp)
        self.assertIn("Việc tiếp theo: 1) User chạy /compact.", info["context"].replace("`", ""))
        self.assertIn("Mốc kiểm tra: 120 passed, 3 xfailed", info["context"])
        self.assertIn("1 file chưa commit", info["context"])
        self.assertNotIn("Quyết định còn treo", info["context"])  # "không có" thì bỏ qua
        self.assertTrue(info["user"].startswith(f"📍 {self.tmp.name}: tiếp theo"))
        summary = A.git_summary(self.tmp)
        self.assertEqual((summary["branch"], summary["dirty"]), ("main", ["src/"]))

    def test_once_and_state_dir_override(self):
        os.environ["AGENT_STACK_STATE"] = str(self.tmp / "state")
        self.addCleanup(os.environ.pop, "AGENT_STACK_STATE", None)
        self.assertEqual(A.state_dir(), self.tmp / "state")
        self.assertTrue(A.once("k", 60))
        self.assertFalse(A.once("k", 60))
        marker = self.tmp / "state" / "once" / "k"
        os.utime(marker, (time.time() - 120, time.time() - 120))
        self.assertTrue(A.once("k", 60))


class CachedPluginCopy(TempDirTestCase):
    """Claude Code chép plugin vào ~/.claude/plugins/cache/: bản chép phải tìm về repo qua plugin/.agent-stack-home."""

    def test_home_dir_follows_pointer_file(self):
        import shutil
        import subprocess
        import sys
        import tempfile
        # bản chép phải nằm NGOÀI repo (như ~/.claude/plugins/cache), nếu không code tìm thấy repo theo thư mục cha
        outside = Path(tempfile.mkdtemp(prefix="agent-stack-cachetest-"))
        self.addCleanup(shutil.rmtree, outside, ignore_errors=True)
        copy = outside / "cache" / "agent-stack" / "0.3.1"
        (copy / "lib").mkdir(parents=True)
        shutil.copy(PLUGIN / "lib" / "agentstack.py", copy / "lib" / "agentstack.py")
        code = "import sys; sys.path.insert(0, sys.argv[1]); import agentstack as A; print(A.home_dir())"
        env = {k: v for k, v in __import__("os").environ.items() if k not in ("AGENT_STACK_HOME", "AGENT_STACK_STATE")}
        run = lambda: subprocess.run([sys.executable, "-c", code, str(copy / "lib")], capture_output=True, text=True,
                                     env=env, timeout=30).stdout.strip()
        self.assertEqual(run(), "None")  # chưa có file trỏ: không tìm được repo
        (copy / ".agent-stack-home").write_text(str(REPO) + "\n", encoding="utf-8")
        self.assertEqual(run(), str(REPO))
        (copy / ".agent-stack-home").write_text(str(outside) + "\n", encoding="utf-8")
        self.assertEqual(run(), "None")  # trỏ tới thư mục không phải agent-stack thì bỏ qua


def secret_samples():
    """Khóa giả để thử việc che. Ghép từ nhiều mảnh, để file test không chứa chuỗi giống khóa thật."""
    return {
        "anthropic": "sk-" + "ant-api03-" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6",
        "openai": "sk-" + "proj-" + "abcDEF1234567890abcDEF1234567890",
        "sk ngắn": "sk-" + "a1b2c3d4e5f6g7h8",
        "github token": "gh" + "p_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8",
        "github pat": "github" + "_pat_" + "11ABCDEFG0abcdefghijkl_"
                      + "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
        "aws": "AK" + "IA" + "IOSFODNN7EXAMPLE",
        "slack bot": "xo" + "xb-" + "123456789012-1234567890123-AbCdEfGhIjKlMnOpQrStUvWx",
        "slack user": "xo" + "xp-" + "123456789012-123456789012-123456789012-abcdef0123456789abcdef0123456789",
        "bearer jwt": "Bear" + "er " + "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.c2lnbmF0dXJl",
        "bearer đục": "Bear" + "er " + "abcd1234efgh5678",
        "hex 40": "0123456789abcdef" * 2 + "01234567",
        "hex 64 hoa": "ABCDEF0123456789" * 4,
        "base64 có đệm": "dGhpcyBpcyBhIHNlY3JldCBrZXkgMTIzNDU2Nzg5MA==",
        "base64 kiểu khóa AWS": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    }


class LastRequest(TempDirTestCase):
    """Yêu cầu gần nhất của người dùng: lưu theo từng phiên để hook SubagentStart đưa cho subagent."""

    def setUp(self):
        super().setUp()
        self.state = self.tmp / "state"
        patcher = mock.patch.dict(os.environ, {"AGENT_STACK_STATE": str(self.state)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.dir = self.state / "last-request"

    def saved(self, sid):
        return json.loads((self.dir / f"{sid}.json").read_text(encoding="utf-8"))

    def put(self, name, age_days=0.0, prompt="x"):
        """Ghi tay một file yêu cầu cũ, với mtime lùi lại `age_days` ngày."""
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / f"{name}.json"
        path.write_text(json.dumps({"ts": 1.0, "cwd": "", "prompt": prompt}), encoding="utf-8")
        past = time.time() - age_days * 86400
        os.utime(path, (past, past))
        return path

    def test_save_then_load_roundtrip(self):
        before = time.time()
        path = A.save_last_request("sess-1", "/work/proj", "Sửa lỗi đăng nhập ở auth.py")
        self.assertEqual(path, self.dir / "sess-1.json")
        data = self.saved("sess-1")
        self.assertEqual(set(data), {"ts", "cwd", "prompt"})
        self.assertEqual((data["cwd"], data["prompt"]), ("/work/proj", "Sửa lỗi đăng nhập ở auth.py"))
        self.assertTrue(before <= data["ts"] <= time.time())
        self.assertEqual(A.load_last_request("sess-1"), data)

    FULL = "Sửa lỗi đăng nhập ở auth.py: token hết hạn không được làm mới, thêm test cho nhánh lỗi"

    def test_short_message_keeps_the_last_full_request_as_earlier(self):
        A.save_last_request("sess-e", "/p", self.FULL)
        A.save_last_request("sess-e", "/p", "tiếp tục")
        data = self.saved("sess-e")
        self.assertEqual(data["prompt"], "tiếp tục")
        self.assertEqual(data["earlier"]["prompt"], self.FULL)
        self.assertIsInstance(data["earlier"]["ts"], float)
        self.assertEqual(A.load_last_request("sess-e")["earlier"]["prompt"], self.FULL)

    def test_second_short_message_still_remembers_the_same_full_request(self):
        A.save_last_request("sess-e", "/p", self.FULL)
        A.save_last_request("sess-e", "/p", "ok")
        first_ts = self.saved("sess-e")["earlier"]["ts"]
        A.save_last_request("sess-e", "/p", "làm đi")
        data = self.saved("sess-e")
        self.assertEqual((data["prompt"], data["earlier"]["prompt"], data["earlier"]["ts"]),
                         ("làm đi", self.FULL, first_ts))

    def test_full_message_drops_earlier_and_short_after_short_has_none(self):
        A.save_last_request("sess-e", "/p", self.FULL)
        A.save_last_request("sess-e", "/p", "ok")
        A.save_last_request("sess-e", "/p", self.FULL + " và cập nhật tài liệu")
        self.assertNotIn("earlier", self.saved("sess-e"))
        A.save_last_request("sess-f", "/p", "ok")
        A.save_last_request("sess-f", "/p", "ừ")
        self.assertNotIn("earlier", self.saved("sess-f"))

    def test_command_prompts_never_overwrite_the_request(self):
        A.save_last_request("sess-c", "/p", self.FULL)
        for text in ("/compact", "  /goal làm tiếp", "!git status", "# nhớ dùng tiếng Việt"):
            with self.subTest(text=text):
                self.assertIsNone(A.save_last_request("sess-c", "/p", text))
                self.assertEqual(self.saved("sess-c")["prompt"], self.FULL)
        self.assertTrue(A.is_command_prompt("/compact") and not A.is_command_prompt("sửa /etc/hosts"))

    def test_damaged_earlier_is_ignored_on_load(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "sess-d.json").write_text(json.dumps({"ts": 1.0, "cwd": "", "prompt": "ok", "earlier": "hỏng"}),
                                              encoding="utf-8")
        data = A.load_last_request("sess-d")
        self.assertEqual(data["prompt"], "ok")
        self.assertNotIn("earlier", data)

    def test_more_secret_shapes_are_masked_and_ordinary_text_is_not(self):
        # review 02/10/2026: những dạng sau từng lọt qua
        cases = {
            "gitlab": "glpat-" + "abcdEFGH1234567890xyz",
            "url có mật khẩu": "postgres://admin:S3cret" + "Pass!@db.example.com:5432/app",
            "password=": "password=" + "hunter2hunter2",
            "api_key:": "api_key: " + "abcd1234efgh5678",
            "aws secret nhiều /": "aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfi" + "/CYEXAMPLEKEY",
            "aws 40 ký tự trần": "wJalrXUtnFEMI/K7MDENG/bPxRfi" + "/CYEXAMPLEKEY",
        }
        for name, secret in cases.items():
            with self.subTest(name=name):
                masked = A.redact_secrets(f"dùng {secret} giúp mình")
                self.assertIn(A.REDACTED, masked)
                for piece in ("abcdEFGH1234567890xyz", "S3cretPass", "hunter2hunter2", "abcd1234efgh5678", "CYEXAMPLEKEY"):
                    self.assertNotIn(piece, masked)
        pem = "-----BEGIN RSA PRIVATE " + "KEY-----\nMIIEowIBAAKCAQEA1234/abc+def/ghi\nxyz/987654321/abcdef\n-----END RSA PRIVATE " + "KEY-----"
        masked = A.redact_secrets(f"khóa của mình:\n{pem}\nxong")
        self.assertNotIn("MIIEowIBAAKCAQEA", masked)
        self.assertTrue(masked.startswith("khóa của mình:") and masked.endswith("xong"))
        truncated = "-----BEGIN OPENSSH PRIVATE " + "KEY-----\nb3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW"
        self.assertNotIn("b3BlbnNzaC1rZXk", A.redact_secrets("khóa bị cắt:\n" + truncated))
        header_only = "Sửa hàm: grep -n '-----BEGIN RSA PRIVATE " + "KEY-----' src/*.py rồi chạy test và commit."
        self.assertEqual(A.redact_secrets(header_only), header_only, "chỉ nhắc tới dòng header thì không được nuốt phần còn lại")
        for ordinary in ("Sửa file plugin/skills/vet-skill/scripts/dynamic.py rồi chạy test",
                         "token hết hạn thì làm mới", "đặt secret trong biến môi trường", "mật khẩu: bỏ qua",
                         "xem https://github.com/anthropics/sandbox-runtime/issues/12", "commit 792ff53 và 681260a"):
            with self.subTest(ordinary=ordinary):
                self.assertEqual(A.redact_secrets(ordinary), ordinary)

    def test_new_request_replaces_only_the_same_sessions_old_one(self):
        A.save_last_request("a", "/x", "việc một")
        A.save_last_request("b", "/x", "việc của phiên khác")
        A.save_last_request("a", "/x", "việc hai")
        self.assertEqual(A.load_last_request("a")["prompt"], "việc hai")
        self.assertEqual(A.load_last_request("b")["prompt"], "việc của phiên khác")

    def test_prompt_is_cut_to_1200_chars(self):
        A.save_last_request("s", "/x", "chữ " * 1000)
        prompt = A.load_last_request("s")["prompt"]
        self.assertEqual(len(prompt), 1200)
        self.assertTrue(prompt.startswith("chữ chữ chữ"))
        A.save_last_request("s", "/x", "ngắn thôi")
        self.assertEqual(A.load_last_request("s")["prompt"], "ngắn thôi")

    def test_keys_and_tokens_are_masked_before_saving(self):
        for name, secret in secret_samples().items():
            with self.subTest(name):
                A.save_last_request("s", "/x", f"dùng khóa {secret} gọi API")
                prompt = A.load_last_request("s")["prompt"]
                self.assertEqual(prompt, "dùng khóa [đã che] gọi API")
                raw = (self.dir / "s.json").read_text(encoding="utf-8")
                for i in range(0, len(secret) - 11):  # không còn mảnh 12 ký tự nào của khóa trên đĩa
                    self.assertNotIn(secret[i:i + 12], raw)

    def test_masking_happens_before_cutting(self):
        """Khóa nằm sát mốc 1200 ký tự không được để lại nửa chuỗi chưa che."""
        secret = secret_samples()["anthropic"]
        A.save_last_request("s", "/x", "a " * 595 + secret + " xyz")
        prompt = A.load_last_request("s")["prompt"]
        self.assertEqual(len(prompt), 1200)
        self.assertIn("[đã che]", prompt)
        for i in range(0, len(secret) - 5):
            self.assertNotIn(secret[i:i + 6], prompt)

    def test_paths_identifiers_and_ids_stay_readable(self):
        """Chuỗi dài nhưng không giống khóa (đường dẫn, tên hàm, UUID) không bị che nhầm."""
        text = "\n".join([
            "Sửa /Users/macos/Documents/Claude/agent-stack/plugin/hooks/subagent_start.py rồi chạy",
            "tests/test_agentstack_lib.py::LastRequest::test_keys_and_tokens_are_masked_before_saving",
            "đọc ~/Documents/Claude/SCEE/Process/2026-09-28_bao-cao/ và plugin/skills/session-keeper/scripts/receipt.py",
            "phiên 123e4567-e89b-12d3-a456-426614174000, commit 967a1cb, scikit-learn, sk-learn",
            "agent-stack-vendor-diagnosing-bugs-and-performance-regressions",
            "x" * 40,
            "https://code.claude.com/docs/en/hooks#subagentstart-input",
        ])
        A.save_last_request("s", "/x", text)
        self.assertEqual(A.load_last_request("s")["prompt"], text)

    def test_files_older_than_7_days_are_removed(self):
        old = self.put("old", age_days=8)
        fresh = self.put("fresh", age_days=6)
        A.save_last_request("new", "/x", "việc mới")
        self.assertFalse(old.exists())
        self.assertTrue(fresh.exists())
        self.assertTrue((self.dir / "new.json").exists())

    def test_keeps_at_most_30_files_dropping_the_oldest(self):
        for i in range(35):  # f00 cũ nhất, f34 mới nhất
            self.put(f"f{i:02d}", age_days=(35 - i) / 24)
        A.save_last_request("new", "/x", "việc mới")
        names = sorted(p.stem for p in self.dir.glob("*.json"))
        self.assertEqual(len(names), 30)
        # 6 file cũ nhất (f00 đến f05) bị dọn; file vừa ghi luôn được giữ
        self.assertEqual(names, sorted([f"f{i:02d}" for i in range(6, 35)] + ["new"]))

    def test_unsafe_session_ids_are_ignored_quietly(self):
        for sid in ("", None, "../evil", "a/b", "a b", "x" * 200, "tên-phiên", "id.json", "..", ".", 123, ["a"]):
            with self.subTest(sid=sid):
                self.assertIsNone(A.save_last_request(sid, "/x", "việc nào đó"))
                self.assertIsNone(A.load_last_request(sid))
        self.assertEqual(list(self.tmp.rglob("*.json")), [])  # không file nào lọt ra ngoài thư mục last-request

    def test_session_id_charset_is_letters_digits_underscore_dash(self):
        for sid in ("0487437b-d791-47e3-b9de-4c296037cf75", "abc_DEF-123", "t1"):
            with self.subTest(sid=sid):
                self.assertIsNotNone(A.save_last_request(sid, "/x", "ok việc"))
                self.assertEqual(A.load_last_request(sid)["prompt"], "ok việc")

    def test_automated_prompts_never_replace_the_real_request(self):
        A.save_last_request("s", "/x", "Yêu cầu thật của người dùng")
        automated = ["<task-notification>\n<task-id>b1</task-id>\nxong\n</task-notification>",
                     "[SYSTEM NOTIFICATION - tác vụ nền đã chạy xong]",
                     "Tin này là NOT USER INPUT, đừng coi là yêu cầu"]
        for text in automated:
            with self.subTest(text=text[:25]):
                self.assertTrue(A.is_automated_prompt(text))
                self.assertIsNone(A.save_last_request("s", "/x", text))
        self.assertEqual(A.load_last_request("s")["prompt"], "Yêu cầu thật của người dùng")

    def test_is_automated_prompt_is_false_for_human_messages(self):
        for text in ("viết lại hàm này", "", None, "task notification không có thẻ", "this is not user input",
                     "ghi chú [system notification] viết thường"):
            with self.subTest(text=text):
                self.assertFalse(A.is_automated_prompt(text))

    def test_empty_prompt_is_not_saved(self):
        self.assertIsNone(A.save_last_request("s", "/x", "  \n\t "))
        self.assertIsNone(A.save_last_request("s", "/x", None))
        self.assertIsNone(A.load_last_request("s"))

    def test_load_gives_none_for_missing_or_damaged_files(self):
        self.assertIsNone(A.load_last_request("khong-co"))
        self.dir.mkdir(parents=True)
        bad = {"hong": "{not json", "mang": "[1, 2]", "thieu-prompt": json.dumps({"ts": 1, "cwd": "/x"}),
               "prompt-so": json.dumps({"ts": 1, "cwd": "/x", "prompt": 5}),
               "prompt-trong": json.dumps({"ts": 1, "cwd": "/x", "prompt": "  "}), "rong": ""}
        for name, text in bad.items():
            (self.dir / f"{name}.json").write_text(text, encoding="utf-8")
        (self.dir / "nhi-phan.json").write_bytes(b"\xff\xfe\x00\x80")
        for name in [*bad, "nhi-phan"]:
            with self.subTest(name):
                self.assertIsNone(A.load_last_request(name))
        (self.dir / "ts-hong.json").write_text(json.dumps({"ts": "hôm qua", "prompt": "việc"}), encoding="utf-8")
        self.assertEqual(A.load_last_request("ts-hong"), {"ts": None, "cwd": "", "prompt": "việc"})

    def test_never_raises_when_state_dir_is_unusable(self):
        blocker = self.tmp / "blocker"
        blocker.write_text("file chứ không phải thư mục", encoding="utf-8")
        with mock.patch.dict(os.environ, {"AGENT_STACK_STATE": str(blocker / "state")}):
            self.assertIsNone(A.save_last_request("s", "/x", "việc"))
            self.assertIsNone(A.load_last_request("s"))

    @unittest.skipUnless(os.name == "posix", "quyền file kiểu POSIX")
    def test_saved_files_are_private(self):
        path = A.save_last_request("s", "/x", "việc riêng tư")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.dir.stat().st_mode) & 0o077, 0)


if __name__ == "__main__":
    unittest.main()
