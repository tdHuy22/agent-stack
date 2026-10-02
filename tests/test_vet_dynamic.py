import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests._util import PLUGIN, REPO, TempDirTestCase

SCRIPTS = PLUGIN / "skills" / "vet-skill" / "scripts"
VET = SCRIPTS / "vet.py"
sys.path.insert(0, str(SCRIPTS))
import dynamic  # noqa: E402


def violation(op, target, proc="Python(123)"):
    return f"{proc} deny(1) {op} {target}"


class Settings(TempDirTestCase):
    def test_default_is_no_network_and_write_only_in_workdir(self):
        cfg = dynamic.build_settings(self.tmp)
        self.assertEqual(cfg["network"]["allowedDomains"], [])
        self.assertIn(str(Path.home().resolve()), cfg["filesystem"]["denyRead"], "phải chặn HOME thật bằng đường dẫn tường minh")
        self.assertEqual(cfg["filesystem"]["allowWrite"], [str(self.tmp)])
        self.assertEqual(cfg["filesystem"]["allowRead"], [str(self.tmp)])

    def test_extra_read_and_domains_are_added_explicitly(self):
        cfg = dynamic.build_settings(self.tmp, extra_read=["/opt/x"], allow_domains=["example.com"])
        self.assertIn("/opt/x", cfg["filesystem"]["allowRead"])
        self.assertEqual(cfg["network"]["allowedDomains"], ["example.com"])
        self.assertEqual(cfg["filesystem"]["allowWrite"], [str(self.tmp)], "đọc thêm không được mở quyền ghi")

    def test_env_drops_secrets_and_points_tmp_inside_workdir(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-x", "GH_TOKEN": "ghp_x", "AWS_SECRET_ACCESS_KEY": "x"}):
            env = dynamic.safe_env(self.tmp)
        self.assertFalse({"ANTHROPIC_API_KEY", "GH_TOKEN", "AWS_SECRET_ACCESS_KEY"} & set(env))
        self.assertEqual(env["TMPDIR"], str(self.tmp / "tmp"))
        self.assertTrue((self.tmp / "tmp").is_dir())

    def test_home_is_fake_by_default_and_real_on_request(self):
        self.assertEqual(dynamic.safe_env(self.tmp)["HOME"], str(self.tmp / "home"))
        self.assertEqual(dynamic.safe_env(self.tmp, real_home=True)["HOME"], str(Path.home()))

    def test_runner_keeps_real_home_so_srt_expands_tilde_correctly(self):
        # nếu runner nhận HOME giả thì `~` trong cấu hình sẽ chặn nhầm HOME giả và bỏ ngỏ HOME thật
        child = dynamic.safe_env(self.tmp)
        env = dynamic.runner_env("/opt/node/bin/node", child)
        self.assertEqual(env["HOME"], str(Path.home()))
        self.assertEqual(json.loads(env["VET_CHILD_ENV"]), child)
        self.assertIn("/opt/node/bin", env["PATH"])
        self.assertNotIn("ANTHROPIC_API_KEY", env)


class Classification(unittest.TestCase):
    def test_groups_by_kind(self):
        g = dynamic.classify([
            violation("file-read-data", "/Users/x/.ssh/id_rsa"),
            violation("file-read-data", "/Users/x/notes.txt"),
            violation("file-write-create", "/Users/x/.zshrc"),
            violation("file-write-create", "/private/tmp/abc"),
            violation("network-outbound", "1.2.3.4:80"),
            "dòng không đúng khuôn",
        ])
        self.assertEqual(g["sensitive_reads"], ["/Users/x/.ssh/id_rsa"])
        self.assertEqual(g["reads"], ["/Users/x/notes.txt"])
        self.assertEqual(g["writes"], ["/Users/x/.zshrc"])
        self.assertEqual(g["tmp_writes"], ["/private/tmp/abc"])
        self.assertEqual(len(g["network"]), 1)
        self.assertEqual(g["other"], ["dòng không đúng khuôn"])

    def test_noise_is_dropped_and_counted(self):
        g = dynamic.classify([
            violation("sysctl-read", "kern.osversion"),
            violation("system-info", "vfs.disk-space"),
            violation("file-read-data", "/Users/x/Library/Caches/com.apple.python/a.pyc"),
        ])
        self.assertEqual(g["noise"], 3)
        self.assertFalse(any(g[k] for k in ("sensitive_reads", "reads", "writes", "tmp_writes", "network", "other")))

    def test_duplicates_count_once(self):
        line = violation("file-read-data", "/Users/x/a.txt")
        self.assertEqual(dynamic.classify([line, line, line])["reads"], ["/Users/x/a.txt"])

    def test_verdicts(self):
        empty = dynamic.classify([])
        ok = {"monitorOk": True}
        self.assertEqual(dynamic.judge(empty, ok)[0], dynamic.LABEL_NONE)
        self.assertEqual(dynamic.judge(empty, {**ok, "timedOut": True})[0], "CẦN ĐỌC")
        cases = {
            "ĐÁNG NGỜ": [violation("file-read-data", "/Users/x/.aws/credentials")],
            "ĐÁNG NGỜ ": [violation("network-outbound", "evil.example:443")],
            "ĐÁNG NGỜ  ": [violation("file-write-create", "/Users/x/Library/LaunchAgents/a.plist")],
            "CẦN ĐỌC": [violation("file-read-data", "/Users/x/notes.txt")],
            "CẦN ĐỌC ": [violation("file-write-create", "/private/var/tmp/a")],
        }
        self.assertNotEqual(dynamic.LABEL_NONE, "SẠCH", "không dùng chữ 'sạch' khi chỉ là chưa thấy gì")
        for expected, lines in cases.items():
            with self.subTest(expected=expected, lines=lines):
                self.assertEqual(dynamic.judge(dynamic.classify(lines), ok)[0], expected.strip())

    def test_never_clean_when_the_monitor_did_not_answer(self):
        empty = dynamic.classify([])
        label, reasons = dynamic.judge(empty, {"monitorOk": False})
        self.assertEqual(label, "CẦN ĐỌC")
        self.assertTrue(any("theo dõi" in r for r in reasons))
        self.assertEqual(dynamic.judge(empty, {})[0], "CẦN ĐỌC", "thiếu trường monitorOk cũng không được coi là sạch")

    def test_blocked_output_without_violations_is_not_clean(self):
        empty = dynamic.classify([])
        res = {"monitorOk": True, "stderr": "PermissionError: [Errno 1] Operation not permitted: '/x'"}
        self.assertEqual(dynamic.judge(empty, res)[0], "CẦN ĐỌC")


class FileListing(TempDirTestCase):
    def test_does_not_follow_symlinks_out_of_the_tree(self):
        outside = self.tmp / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("x", encoding="utf-8")
        tree = self.tmp / "tree"
        tree.mkdir()
        (tree / "a.txt").write_text("a", encoding="utf-8")
        os.symlink(outside, tree / "link")  # script không tin cậy có thể tạo symlink trỏ ra ngoài
        self.assertEqual(dynamic.list_files(tree), {"a.txt"})

    def test_tree_size_stops_early_and_counts_regular_files(self):
        tree = self.tmp / "tree"
        tree.mkdir()
        (tree / "a.bin").write_bytes(b"x" * 100)
        (tree / "b.bin").write_bytes(b"x" * 100)
        self.assertEqual(dynamic.tree_size(tree, 10_000), 200)
        self.assertGreater(dynamic.tree_size(tree, 50), 50)

    def test_run_refuses_oversized_tree(self):
        home = self.tmp / "home"
        pkg = home / ".cache" / "srt" / "node_modules" / "@anthropic-ai" / "sandbox-runtime"
        pkg.mkdir(parents=True)
        (pkg / "package.json").write_text(json.dumps({"version": dynamic.SRT_VERSION}), encoding="utf-8")
        (home / ".cache" / "srt" / "run.mjs").write_text("//\n", encoding="utf-8")
        tree = self.tmp / "big"
        tree.mkdir()
        (tree / "x.bin").write_bytes(b"x" * 2048)
        with mock.patch.object(dynamic, "MAX_TREE_BYTES", 1024), \
                mock.patch.object(dynamic.shutil, "which", return_value="/usr/bin/node"):
            with self.assertRaises(ValueError):
                dynamic.run(home, str(tree), ["true"])


class Output(unittest.TestCase):
    def test_parse_takes_last_json_line_with_exit(self):
        text = 'log rác\n{"x": 1}\n{"exit": 0, "violations": []}\n'
        self.assertEqual(dynamic.parse_output(text)["exit"], 0)

    def test_parse_rejects_garbage(self):
        with self.assertRaises(ValueError):
            dynamic.parse_output("không có JSON ở đây\nlỗi gì đó")


class SourceTree(TempDirTestCase):
    def make_home(self):
        home = self.tmp / "home"
        tree = home / ".vet-cache" / "o__r__skills-x@abcdef123456" / "skills" / "x"
        tree.mkdir(parents=True)
        (tree / "a.py").write_text("print(1)\n", encoding="utf-8")
        entry = {"source": "github:o/r", "subpath": "skills/x", "sha": "abcdef1234567890"}
        (home / "vetted.lock").write_text(json.dumps({"entries": {"o/r:skills/x": entry}}), encoding="utf-8")
        return home, tree

    def test_resolves_key_to_pinned_cache_dir(self):
        home, tree = self.make_home()
        self.assertEqual(dynamic.source_tree(home, "o/r:skills/x"), tree)

    def test_accepts_local_directory(self):
        home, tree = self.make_home()
        self.assertEqual(dynamic.source_tree(home, str(tree)), tree.resolve())

    def test_unknown_key_and_missing_cache_raise(self):
        home, tree = self.make_home()
        with self.assertRaises(ValueError):
            dynamic.source_tree(home, "khong/co")
        import shutil
        shutil.rmtree(home / ".vet-cache")
        with self.assertRaises(ValueError):
            dynamic.source_tree(home, "o/r:skills/x")


class RunWithFakeRunner(TempDirTestCase):
    """Chạy `run` mà không cần Node: runner giả trả về dòng JSON như run.mjs."""

    def make_home(self):
        home = self.tmp / "home"
        pkg = home / ".cache" / "srt" / "node_modules" / "@anthropic-ai" / "sandbox-runtime"
        pkg.mkdir(parents=True)
        (pkg / "package.json").write_text(json.dumps({"version": dynamic.SRT_VERSION}), encoding="utf-8")
        (home / ".cache" / "srt" / "run.mjs").write_text("// giả\n", encoding="utf-8")
        tree = self.tmp / "target"
        tree.mkdir()
        (tree / "a.py").write_text("print(1)\n", encoding="utf-8")
        (home / ".tmp").mkdir()
        return home, tree

    def test_run_wraps_command_cleans_up_and_classifies(self):
        home, tree = self.make_home()
        seen = {}

        def fake_runner(cmd, **kw):
            seen["cmd"], seen["env"] = cmd, kw["env"]
            payload = {"exit": 0, "signal": None, "timedOut": False, "durationMs": 5, "stdout": "ok", "stderr": "",
                       "monitorOk": True, "violations": [violation("file-read-data", "/Users/x/.ssh/id_rsa")]}
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload) + "\n", stderr="")

        with mock.patch.object(dynamic.shutil, "which", side_effect=lambda c: "/usr/bin/node" if c == "node" else None):
            res = dynamic.run(home, str(tree), ["python3", "a.py"], runner=fake_runner)
        self.assertEqual(res["label"], "ĐÁNG NGỜ")
        self.assertEqual(res["command"], ["python3", "a.py"], "báo cáo giữ lệnh gốc của người dùng")
        sep = seen["cmd"].index("--")
        self.assertEqual(seen["cmd"][sep + 1], "/usr/bin/env")
        self.assertTrue(seen["cmd"][sep + 2].startswith("TMPDIR="), "TMPDIR phải được đặt lại vì srt tự đặt /tmp/claude")
        self.assertEqual(seen["cmd"][sep + 3:], ["python3", "a.py"])
        self.assertNotIn("ANTHROPIC_API_KEY", seen["env"])
        self.assertEqual(list((home / ".tmp").iterdir()), [], "bản chép tạm phải bị xóa")

    def test_run_refuses_without_setup_or_command(self):
        home = self.tmp / "empty"
        home.mkdir()
        with self.assertRaises(ValueError):
            dynamic.run(home, "x", ["true"])
        home2, tree = self.make_home()
        with self.assertRaises(ValueError):
            dynamic.run(home2, str(tree), [])


class Cli(TempDirTestCase):
    def test_cli_without_setup_exits_3_with_hint(self):
        env = dict(os.environ, AGENT_STACK_HOME=str(self.tmp))
        done = subprocess.run([sys.executable, str(VET), "dynamic", str(self.tmp), "--", "true"], env=env,
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 3)
        self.assertIn("--setup", done.stderr)

    def test_options_after_key_are_parsed_before_the_dashes(self):
        env = dict(os.environ, AGENT_STACK_HOME=str(self.tmp))
        done = subprocess.run([sys.executable, str(VET), "dynamic", str(self.tmp), "--timeout", "7", "--json", "--",
                               "echo", "--json"], env=env, capture_output=True, text=True)
        self.assertEqual(done.returncode, 3)  # vẫn dừng vì chưa cài, nhưng không được lỗi cú pháp (mã 2)


@unittest.skipUnless(sys.platform == "darwin" and dynamic.srt_ready(REPO), "cần macOS và `vet.py dynamic --setup`")
class RealSandbox(TempDirTestCase):
    """Chạy sandbox thật. Bỏ qua êm nếu môi trường không cho lồng sandbox (ví dụ đang chạy trong một sandbox khác).

    Chỉ khẳng định những gì chắc chắn: việc bị chặn thật, file mồi (atime) và dấu rò rỉ. Không khẳng định gì dựa vào log
    vi phạm của macOS, vì đo được là nó mất sự kiện khi tiến trình thoát nhanh hoặc máy bận."""

    def run_probe(self, code, **kw):
        tree = self.tmp / "tree"
        tree.mkdir(exist_ok=True)
        (tree / "probe.py").write_text(code, encoding="utf-8")
        try:
            return dynamic.run(REPO, str(tree), ["/usr/bin/python3", "probe.py"], timeout=40, **kw)
        except (ValueError, subprocess.SubprocessError) as exc:
            self.skipTest(f"không chạy được sandbox ở đây: {exc}")

    def test_home_is_the_decoy_home_and_new_file_is_reported(self):
        res = self.run_probe("import os\nopen('out.txt', 'w').write('x')\nprint('HOME=' + os.path.expanduser('~'))\n")
        if res["exit"] != 0:
            self.skipTest(f"sandbox không chạy được lệnh: {res['stderr'][:200]}")
        self.assertIn(".noindex", res["stdout"], "HOME phải là thư mục giả trong bản chép tạm")
        self.assertIn("out.txt", res["created_files"])
        self.assertFalse(res["groups"]["decoys"], "không đọc mồi thì không được báo")

    def test_reading_decoy_credentials_and_copying_them_is_flagged(self):
        res = self.run_probe(
            "import os\n"
            "d = open(os.path.expanduser('~/.ssh/id_rsa')).read()\n"
            "open('stolen.txt', 'w').write(d)\n"
            "print(d)\n")
        if res["decoyMonitor"] is False:
            self.skipTest("hệ thống file không cập nhật atime")
        self.assertEqual(res["label"], "ĐÁNG NGỜ", res["reasons"])
        self.assertIn(".ssh/id_rsa", res["groups"]["decoys"])
        self.assertTrue(any(x.endswith("stolen.txt") for x in res["groups"]["leaks"]), res["groups"]["leaks"])
        self.assertIn("đầu ra của lệnh", res["groups"]["leaks"])

    def test_listing_decoy_dir_is_a_soft_signal(self):
        res = self.run_probe("import os\nprint(os.listdir(os.path.expanduser('~/.ssh')))\n")
        if res["decoyMonitor"] is False:
            self.skipTest("hệ thống file không cập nhật atime")
        self.assertIn(".ssh", res["groups"]["decoy_dirs"])
        self.assertEqual(res["groups"]["decoys"], [])
        self.assertIn(res["label"], ("CẦN ĐỌC", "ĐÁNG NGỜ"))

    def test_real_home_and_outside_writes_are_blocked_for_real(self):
        real = str(Path.home())
        res = self.run_probe(
            "import os\n"
            f"try: os.listdir({real!r})\n"
            "except OSError as e: print('chặn đọc', type(e).__name__)\n"
            "try: open('/Library/agent-stack-probe.txt', 'w')\n"
            "except OSError as e: print('chặn ghi', type(e).__name__)\n")
        if "chặn" not in res["stdout"]:
            self.skipTest(f"sandbox không chặn như mong đợi trong môi trường này: {res['stdout'][:200]}")
        self.assertIn("chặn đọc", res["stdout"], "HOME thật phải bị chặn dù HOME của lệnh là HOME giả")
        self.assertIn("chặn ghi", res["stdout"])
        self.assertFalse(Path("/Library/agent-stack-probe.txt").exists())

    def test_real_home_mode_skips_decoys(self):
        res = self.run_probe("print(1)\n", real_home=True)
        self.assertTrue(res["realHome"])
        self.assertEqual((res["groups"]["decoys"], res["groups"]["leaks"]), ([], []))


class Decoys(TempDirTestCase):
    def test_make_decoys_writes_marked_private_files(self):
        made = dynamic.make_decoys(self.tmp, "CANARYABC123")
        self.assertIn(".ssh/id_rsa", made)
        self.assertEqual(len(made), len(dynamic.DECOYS))
        body = (self.tmp / ".ssh" / "id_rsa").read_text(encoding="utf-8")
        self.assertIn("CANARYABC123", body)
        self.assertEqual(os.stat(self.tmp / ".ssh" / "id_rsa").st_mode & 0o777, 0o600)

    def test_unread_decoys_are_not_reported_and_stat_listing_do_not_count(self):
        dynamic.make_decoys(self.tmp, "M")
        os.stat(self.tmp / ".ssh" / "id_rsa")
        (self.tmp / ".ssh" / "id_rsa").exists()
        self.assertEqual(dynamic.decoys_read(self.tmp), [])

    def test_reading_a_decoy_is_detected_through_atime(self):
        if not dynamic.atime_updates(self.tmp):
            self.skipTest("hệ thống file không cập nhật atime")
        dynamic.make_decoys(self.tmp, "M")
        (self.tmp / ".aws" / "credentials").read_text(encoding="utf-8")
        self.assertEqual(dynamic.decoys_read(self.tmp), [".aws/credentials"])

    def test_listing_a_decoy_directory_is_detected(self):
        if not dynamic.atime_updates(self.tmp):
            self.skipTest("hệ thống file không cập nhật atime")
        dynamic.make_decoys(self.tmp, "M")
        os.listdir(self.tmp / ".ssh")
        self.assertIn(".ssh", dynamic.decoy_dirs_listed(self.tmp))
        self.assertEqual(dynamic.decoys_read(self.tmp), [])

    def test_find_marker_finds_copies_and_ignores_symlinks(self):
        root = self.tmp / "root"
        root.mkdir()
        (root / "copy.txt").write_text("xx CANARYZ yy", encoding="utf-8")
        (root / "clean.txt").write_text("không có gì", encoding="utf-8")
        outside = self.tmp / "outside.txt"
        outside.write_text("CANARYZ", encoding="utf-8")
        os.symlink(outside, root / "link.txt")
        self.assertEqual([os.path.basename(x) for x in dynamic.find_marker([root], "CANARYZ")], ["copy.txt"])

    def test_judge_flags_decoy_reads_and_leaks_as_suspicious(self):
        ok = {"monitorOk": True, "decoyMonitor": True}
        groups = dynamic.classify([])
        self.assertEqual(dynamic.judge({**groups, "decoys": [".ssh/id_rsa"]}, ok)[0], "ĐÁNG NGỜ")
        self.assertEqual(dynamic.judge({**groups, "leaks": ["đầu ra của lệnh"]}, ok)[0], "ĐÁNG NGỜ")
        self.assertEqual(dynamic.judge({**groups, "decoy_dirs": [".ssh"]}, ok)[0], "CẦN ĐỌC")
        self.assertEqual(dynamic.judge(groups, {"monitorOk": True, "decoyMonitor": False})[0], "CẦN ĐỌC",
                         "không đo được atime thì không được khẳng định là không thấy gì")


if __name__ == "__main__":
    unittest.main()
