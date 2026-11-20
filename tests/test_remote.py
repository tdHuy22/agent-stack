"""Chạy test và mutation dài trên máy xa qua SSH (việc F2b, TM-161–165): `receipt.py run --host`, `mutation.py --host`,
module `session-keeper/scripts/remote.py`.

Viết trước code. Không gọi ssh thật, không mạng: `remote.SSH` được thay bằng một ssh GIẢ (script Python ghi argv vào
file log, rồi chạy chuỗi lệnh bằng `sh -c` trong một thư mục "máy xa" giả, HOME của nó cũng là thư mục đó). Các lần
chạy `receipt.py` đi qua một tiến trình con nhỏ (DRIVER) vá `remote.SSH`, `remote.MARGIN` rồi gọi `receipt.main`;
`mutation.main` chạy ngay trong tiến trình, vá `mutation.R.run_remote` khi cần dữ liệu máy xa giả.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from tests._util import PLUGIN, REPO, TempDirTestCase, git, run_script

SCRIPTS = PLUGIN / "skills" / "session-keeper" / "scripts"
DONE_SCRIPTS = PLUGIN / "skills" / "done-gate" / "scripts"
RECEIPT = SCRIPTS / "receipt.py"
NARROW = SCRIPTS / "narrow.py"
REAL_MUTMUT = REPO / ".venv-mutmut" / "bin" / "mutmut"
sys.path.insert(0, str(PLUGIN / "lib"))
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(DONE_SCRIPTS))

HEX40 = re.compile(r"^[0-9a-f]{40}$")

# ssh giả. CFG ghi ở đầu file. Chế độ: ok (chạy chuỗi lệnh như ssh thật), fail (thoát CFG["code"], không chạy gì),
# silent (thoát 0, không in gì), fakeend (chỉ in dòng kết thúc giả), hang (ngủ), trailer (chạy xong rồi in thêm chữ).
FAKE_SSH_BODY = r'''
import json, os, subprocess, sys, threading, time

LOG, HOME, MODE = CFG["log"], CFG["home"], CFG["mode"]
argv = sys.argv[1:]
with open(LOG, "a", encoding="utf-8") as f:
    f.write(json.dumps({"argv": argv}) + "\n")
if "--" not in argv or len(argv) < argv.index("--") + 3:
    sys.exit(255)
rest = argv[argv.index("--") + 2:]
if MODE == "fail":
    sys.exit(CFG["code"])
if MODE == "silent":
    sys.exit(0)
if MODE == "fakeend":
    print("[agent-stack-remote] exit deadbeef 0")
    sys.exit(0)
if MODE == "hang":
    time.sleep(25)
    sys.exit(255)
proc = subprocess.Popen(["sh", "-c", " ".join(rest)], stdin=subprocess.PIPE, cwd=HOME,
                        env=dict(os.environ, HOME=HOME))
count = [0]


def pump():
    try:
        while True:
            chunk = os.read(0, 65536)
            if not chunk:
                break
            count[0] += len(chunk)
            proc.stdin.write(chunk)
            proc.stdin.flush()
    except (OSError, ValueError):
        pass
    finally:
        try:
            proc.stdin.close()
        except (OSError, ValueError):
            pass


thread = threading.Thread(target=pump, daemon=True)
thread.start()
code = proc.wait()
thread.join(0.5)
with open(LOG, "a", encoding="utf-8") as f:
    f.write(json.dumps({"stdin": count[0]}) + "\n")
if MODE == "trailer":
    sys.stdout.write(CFG["trailer"])
    sys.stdout.flush()
sys.exit(code)
'''

# Tiến trình con: vá remote.SSH, remote.MARGIN rồi gọi receipt.main (mã thoát là giá trị trả về).
DRIVER = r'''
import json, sys
scripts, ssh, margin = sys.argv[1], json.loads(sys.argv[2]), float(sys.argv[3])
sys.path.insert(0, scripts)
import remote
remote.SSH = ssh
remote.MARGIN = margin
import receipt
sys.exit(receipt.main(sys.argv[4:]))
'''

# Lệnh chạy trên máy xa (python3 -c ...): in JSON ra một dòng để Mac đọc lại.
WALK = ("import os,json;print(json.dumps(sorted(os.path.relpath(os.path.join(d,f)) "
        "for d,ds,fs in os.walk('.') if '.git' not in d.split(os.sep) for f in fs)))")
PRINT_ARGV = "import sys,json;print(json.dumps(sys.argv[1:]))"
WHERE = "import os,json;print(json.dumps([os.getcwd(), sorted(os.listdir('.'))]))"
CONTENTS = ("import os,json;print(json.dumps({n:(open(n).read() if os.path.exists(n) else None) "
            "for n in ('keep.txt','mod.txt','new.txt','gone.txt','both.txt')}))")
PYTHON_WHICH = "import shutil,os,json;print(json.dumps([shutil.which('python3'), os.environ['PATH'].split(os.pathsep)[0]]))"

IGNORE = ".tmp/\nstate/\n.venv*\n"


def json_line(text: str):
    """Dòng JSON (list hay dict) đầu tiên trong output; None nếu không có."""
    for line in text.splitlines():
        line = line.strip()
        if line[:1] in "[{":
            try:
                return json.loads(line)
            except ValueError:
                continue
    return None


def load_stop():
    spec = importlib.util.spec_from_file_location("stop_hook_remote", PLUGIN / "hooks" / "stop.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RemoteBase(TempDirTestCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        for key in ("AGENT_STACK_MUTMUT", "AGENT_STACK_HOME"):
            os.environ.pop(key, None)
        import remote  # chưa có module thì mọi test trượt ở đây (ImportError)
        self.remote = remote
        self.addCleanup(setattr, remote, "SSH", remote.SSH)
        self.addCleanup(setattr, remote, "MARGIN", remote.MARGIN)
        self.state = self.tmp / "state"
        os.environ["AGENT_STACK_STATE"] = str(self.state)
        self.rhome = self.tmp / "rhome"  # "máy xa" giả: HOME của lệnh chạy ở đó
        self.rhome.mkdir()
        self.bin = self.tmp / "bin"  # thư mục `path` của cấu hình: chỉ có python3
        self.bin.mkdir()
        (self.bin / "python3").symlink_to(sys.executable)
        self.sshlog = self.tmp / "ssh.log"
        self.margin = 60.0
        self.set_ssh("ok")
        self.write_hosts({"hosts": {"tuf": {"path": str(self.bin)}}})
        self.repo = self.make_repo()

    # ---- dựng ----
    def set_ssh(self, mode="ok", code=255, trailer="", margin=None):
        cfg = {"log": str(self.sshlog), "home": str(self.rhome), "mode": mode, "code": code, "trailer": trailer}
        script = self.tmp / "fakessh.py"
        script.write_text(f"CFG = {cfg!r}\n" + FAKE_SSH_BODY, encoding="utf-8")
        self.ssh_cmd = [sys.executable, str(script)]
        if margin is not None:
            self.margin = margin
        self.remote.SSH = list(self.ssh_cmd)
        self.remote.MARGIN = self.margin

    def write_hosts(self, data):
        path = self.state / "remote-hosts.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
        return path

    def make_repo(self, name="proj"):
        """Repo có commit, rồi: mod.txt sửa, new.txt mới đã add, gone.txt xóa, both.txt add rồi sửa tiếp."""
        repo = self.tmp / name
        repo.mkdir()
        for rel, text in ((".gitignore", IGNORE), ("keep.txt", "keep\n"), ("mod.txt", "v1\n"), ("gone.txt", "gone\n"),
                          ("both.txt", "a\n"), ("sub/inner.txt", "inner\n")):
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        git(repo, "init", "-q")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "init")
        (repo / "mod.txt").write_text("v2 modified\n", encoding="utf-8")
        (repo / "new.txt").write_text("new content\n", encoding="utf-8")
        git(repo, "add", "new.txt")
        (repo / "gone.txt").unlink()
        (repo / "both.txt").write_text("b\n", encoding="utf-8")
        git(repo, "add", "both.txt")
        (repo / "both.txt").write_text("c\n", encoding="utf-8")
        return repo

    # ---- chạy ----
    def receipt_run(self, *command, host="tuf", repo=None, extra=(), timeout=120):
        argv = [sys.executable, "-c", DRIVER, str(SCRIPTS), json.dumps(self.ssh_cmd), str(self.margin),
                "run", "--project", str(repo or self.repo), f"--host={host}", *extra, "--", *command]
        return subprocess.run(argv, capture_output=True, text=True, cwd=str(repo or self.repo), timeout=timeout,
                              env=dict(os.environ))

    def py(self, code, *args, **kw):
        return self.receipt_run("python3", "-c", code, *args, **kw)

    def ssh_calls(self):
        if not self.sshlog.exists():
            return []
        rows = [json.loads(x) for x in self.sshlog.read_text(encoding="utf-8").splitlines() if x.strip()]
        return [r["argv"] for r in rows if "argv" in r]

    def ssh_stdin_bytes(self):
        if not self.sshlog.exists():
            return 0
        rows = [json.loads(x) for x in self.sshlog.read_text(encoding="utf-8").splitlines() if x.strip()]
        return sum(r.get("stdin", 0) for r in rows)

    def reset_ssh_log(self):
        self.sshlog.unlink(missing_ok=True)

    def checks(self, repo=None):
        out = run_script(RECEIPT, "show", "--project", str(repo or self.repo), "--json")
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def remote_checks(self, repo=None):
        return {k: v for k, v in self.checks(repo).items() if k.startswith("@")}

    def one_check(self, repo=None):
        found = self.remote_checks(repo)
        self.assertEqual(len(found), 1, f"phải có đúng một biên nhận xa: {list(self.checks(repo))}")
        return next(iter(found.values()))

    def control(self, repo=None):
        """Lần chạy hợp lệ: chứng minh cấu hình và repo dùng được, nên lần từ chối sau đó là do đúng điều kiện đang thử."""
        out = self.py("print('control-ok')", repo=repo)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("control-ok", out.stdout)
        self.assertTrue(self.ssh_calls(), "lần chạy hợp lệ phải gọi ssh")
        self.reset_ssh_log()
        run_script(RECEIPT, "forget", "--project", str(repo or self.repo), *list(self.remote_checks(repo)))

    def assertRefused(self, proc, repo=None, why=""):
        text = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 2, f"{why}: mã {proc.returncode}\n{text}")
        self.assertTrue(text.strip(), f"{why}: phải nói lý do")
        self.assertNotIn("usage:", text.lower(), f"{why}: đây là lỗi dòng lệnh, không phải từ chối: {text}")
        self.assertNotIn("unrecognized", text.lower(), f"{why}: {text}")
        self.assertEqual(self.ssh_calls(), [], f"{why}: không được gọi ssh")
        self.assertEqual(self.checks(repo), {}, f"{why}: không được ghi biên nhận")

    def rdir(self, *parts):
        return self.rhome / ".cache" / "agent-stack-remote" / Path(*parts)

    def remote_repos(self):
        return sorted(self.rdir("repos").glob("*.git")) if self.rdir("repos").is_dir() else []

    def left_over_runs(self):
        return sorted(p.name for p in self.rdir("runs").iterdir()) if self.rdir("runs").is_dir() else []

    def write_repo_file(self, rel, text, repo=None):
        path = (repo or self.repo) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


class RunOnRemoteCopy(RemoteBase):
    def test_remote_copy_is_head_plus_uncommitted_tracked_changes(self):
        """spec:f2b-chay-xa#S1 — bản chép: HEAD cộng thay đổi file theo dõi (sửa, add chưa commit, xóa)."""
        out = self.py(CONTENTS)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(json_line(out.stdout), {
            "keep.txt": "keep\n", "mod.txt": "v2 modified\n", "new.txt": "new content\n",
            "gone.txt": None, "both.txt": "c\n"})

    def test_remote_copy_has_exactly_the_tracked_files(self):
        """spec:f2b-chay-xa#S1 — không có file thừa (đã xóa, ignore) trong bản chép trên máy xa."""
        self.write_repo_file(".tmp/scratch", "x")
        out = self.py(WALK)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(json_line(out.stdout),
                         [".gitignore", "both.txt", "keep.txt", "mod.txt", "new.txt", "sub/inner.txt"])

    def test_runs_in_a_copy_not_in_the_mac_checkout(self):
        """spec:f2b-chay-xa#S1 — lệnh chạy trong thư mục runs/<id> của máy xa, không phải thư mục project trên Mac."""
        out = self.py(WHERE)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        cwd = os.path.realpath(json_line(out.stdout)[0])
        self.assertTrue(cwd.startswith(os.path.realpath(self.rdir("runs")) + os.sep), cwd)
        self.assertNotEqual(cwd, os.path.realpath(self.repo))

    def test_cwd_option_runs_in_the_same_subdirectory(self):
        """spec:f2b-chay-xa#S1 — `--cwd sub` chạy trong thư mục con tương ứng của bản chép."""
        out = self.py(WHERE, extra=["--cwd", "sub"])
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        cwd, names = json_line(out.stdout)
        self.assertEqual(Path(cwd).name, "sub")
        self.assertEqual(names, ["inner.txt"])

    def test_exit_code_and_output_come_back_to_mac(self):
        """spec:f2b-chay-xa#S1 — mã thoát của lệnh là mã thoát của receipt.py; stdout, stderr in trên Mac."""
        out = self.py("import sys; print('to-stdout'); print('to-stderr', file=sys.stderr); sys.exit(3)")
        self.assertEqual(out.returncode, 3, out.stdout + out.stderr)
        text = out.stdout + out.stderr
        self.assertIn("to-stdout", text)
        self.assertIn("to-stderr", text)

    def test_python3_is_the_python_of_the_configured_path(self):
        """spec:f2b-chay-xa#S1 — `path` đứng đầu PATH trên máy xa nên `python3` là python của cấu hình."""
        out = self.py(PYTHON_WHICH)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(json_line(out.stdout), [str(self.bin / "python3"), str(self.bin)])


class RemoteReceipt(RemoteBase):
    def test_receipt_fields(self):
        """spec:f2b-chay-xa#S2 — biên nhận ghi scope remote, host, mã commit tạm đã gửi và commit HEAD gốc."""
        out = self.py("print('hello')")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        rec = self.one_check()
        head = git(self.repo, "rev-parse", "HEAD").strip()
        self.assertTrue(rec["ok"])
        self.assertEqual(rec["scope"], "remote")
        self.assertEqual(rec["host"], "tuf")
        self.assertRegex(rec["remote_commit"], HEX40)
        self.assertEqual(rec["head"], head)
        self.assertNotEqual(rec["remote_commit"], head, "cây có thay đổi chưa commit nên commit tạm khác HEAD")
        self.assertNotIn("remote_error", rec)

    def test_default_label_is_at_host_then_command(self):
        """spec:f2b-chay-xa#S2 — nhãn mặc định `@tuf: <lệnh nối bằng dấu cách>`."""
        out = self.receipt_run("python3", "-c", "pass")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(list(self.remote_checks()), ["@tuf: python3 -c pass"])

    def test_long_label_is_cut_to_80_chars(self):
        """spec:f2b-chay-xa#S2 — nhãn mặc định cắt ở 80 ký tự."""
        out = self.py("pass  # " + "x" * 200)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        (label,) = self.remote_checks()
        self.assertTrue(label.startswith("@tuf: python3 -c "), label)
        self.assertLessEqual(len(label), 80)

    def test_remote_receipt_does_not_overwrite_local_one(self):
        """spec:f2b-chay-xa#S2 — chạy xa cùng lệnh không đè biên nhận chạy tại chỗ."""
        local = run_script(RECEIPT, "run", "--project", str(self.repo), "--", "python3", "-c", "pass")
        self.assertEqual(local.returncode, 0, local.stdout + local.stderr)
        out = self.receipt_run("python3", "-c", "pass")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        checks = self.checks()
        self.assertEqual(sorted(checks), ["@tuf: python3 -c pass", "python3 -c pass"])
        self.assertNotEqual(checks["python3 -c pass"].get("scope"), "remote")
        self.assertEqual(checks["@tuf: python3 -c pass"]["scope"], "remote")

    def test_show_says_it_ran_on_the_remote_machine(self):
        """spec:f2b-chay-xa#S2 — `receipt.py show` ghi "chạy trên máy tuf, không thay biên nhận trên máy này"."""
        self.py("pass")
        shown = run_script(RECEIPT, "show", "--project", str(self.repo))
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertIn("chạy trên máy tuf, không thay biên nhận trên máy này", shown.stdout)

    def test_receipt_goes_stale_after_editing_a_file(self):
        """spec:f2b-chay-xa#S2 — dấu vân tay là của code đã gửi: còn khớp lúc đầu, sửa file thì cũ."""
        self.py("pass")
        self.assertIs(self.one_check()["current"], True)
        self.write_repo_file("keep.txt", "đổi sau lần chạy\n")
        self.assertIs(self.one_check()["current"], False)

    def test_change_during_the_run_makes_the_receipt_stale(self):
        """spec:f2b-chay-xa#S2 — dấu vân tay lấy từ code đã gửi, không phải cây lúc lệnh xong: lệnh sửa file trên Mac
        trong khi chạy thì biên nhận ghi ra đã cũ."""
        target = str(self.repo / "keep.txt")
        out = self.py("import sys;open(sys.argv[1],'a').write('late\\n')", target)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("late", (self.repo / "keep.txt").read_text(encoding="utf-8"))
        rec = self.one_check()
        self.assertTrue(rec["ok"])
        self.assertIs(rec["current"], False)


class StopHookIgnoresRemote(RemoteBase):
    def setUp(self):
        super().setUp()
        self.stop = load_stop()
        self.turn = {"ts": time.time() - 60, "gate_level": "vua"}
        self.now = datetime.now().astimezone().isoformat(timespec="seconds")

    def gaps(self, checks=None, root=None):
        A_ = self.stop.A
        patches = [mock.patch.object(A_, "done_gate_ran_since", return_value=True),
                   mock.patch.object(A_, "done_gate_levels_since", return_value=["vua"]),
                   mock.patch.object(A_, "subagent_started_since", return_value=True),
                   mock.patch.object(self.stop, "foreign_filters", return_value=False)]
        if checks is not None:
            patches.append(mock.patch.object(A_, "receipt_status", return_value=checks))
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            return self.stop.evidence_gaps(root or self.tmp, self.turn, "sid")

    def test_only_a_passing_remote_receipt_is_still_a_gap(self):
        """spec:f2b-chay-xa#S3 — chỉ có biên nhận xa đạt, còn khớp code: hook Stop vẫn báo thiếu biên nhận đạt."""
        res = self.gaps({"@tuf: python3 -m unittest": {"ok": True, "scope": "remote", "host": "tuf",
                                                      "current": True, "ts": self.now}})
        self.assertIsNotNone(res)
        self.assertEqual([k for k, _ in res[1]], ["chưa có biên nhận đạt"])

    def test_remote_receipt_does_not_close_the_gap_when_a_local_one_exists(self):
        """spec:f2b-chay-xa#S3 — biên nhận cả bộ tại chỗ vẫn đóng khoảng trống như trước (đối chứng)."""
        res = self.gaps({"@tuf: x": {"ok": True, "scope": "remote", "current": True, "ts": self.now},
                         "python3 -m unittest discover -s tests -t .": {"ok": True, "current": True, "ts": self.now}})
        self.assertIsNone(res)

    def test_failing_remote_receipt_is_not_a_test_failure(self):
        """spec:f2b-chay-xa#S3 — biên nhận xa trượt không bị tính là "test trượt"."""
        res = self.gaps({"@tuf: x": {"ok": False, "exit": 1, "scope": "remote", "host": "tuf", "current": True,
                                     "ts": self.now}})
        self.assertIsNotNone(res)
        kinds = [k for k, _ in res[1]]
        self.assertNotIn("test trượt", kinds)
        self.assertEqual(kinds, ["chưa có biên nhận đạt"])

    def test_failing_remote_receipt_next_to_a_passing_local_one(self):
        """spec:f2b-chay-xa#S3 — có biên nhận cả bộ đạt tại chỗ và một biên nhận xa trượt: không còn khoảng trống."""
        res = self.gaps({"@tuf: x": {"ok": False, "exit": 1, "scope": "remote", "current": True, "ts": self.now},
                         "cả bộ": {"ok": True, "current": True, "ts": self.now}})
        self.assertIsNone(res)

    def test_real_remote_receipt_does_not_count_for_the_hook(self):
        """spec:f2b-chay-xa#S3 — biên nhận thật từ `--host` (đạt, còn khớp) không làm hook Stop hết báo thiếu."""
        out = self.py("print('ok')")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIs(self.one_check()["current"], True)
        res = self.gaps(root=self.repo)
        self.assertIsNotNone(res)
        self.assertIn("chưa có biên nhận đạt", [k for k, _ in res[1]])

    def test_narrow_full_command_on_remote_stays_remote_scope(self):
        """spec:f2b-chay-xa#S3 — `narrow.py full` chạy với --host vẫn là `scope: remote`, không phải cả bộ tại chỗ."""
        self.receipt_run("python3", str(NARROW), "full", "--timeout", "20", timeout=120)
        rec = self.one_check()
        self.assertEqual(rec["scope"], "remote")
        self.assertEqual(rec["host"], "tuf")


class HostConfig(RemoteBase):
    def test_unknown_host_name(self):
        """spec:f2b-chay-xa#S4 — tên máy không có trong remote-hosts.json: mã 2, không ssh, không biên nhận."""
        self.control()
        self.assertRefused(self.py("print('x')", host="khac"), why="tên không có trong file")

    def test_missing_config_file(self):
        """spec:f2b-chay-xa#S4 — thiếu file cấu hình: mã 2."""
        self.control()
        (self.state / "remote-hosts.json").unlink()
        self.assertRefused(self.py("print('x')"), why="thiếu file")

    def test_broken_or_wrong_shape_config(self):
        """spec:f2b-chay-xa#S4 — file hỏng hay sai kiểu: mã 2."""
        self.control()
        for text in ("{hỏng", "", "[]", "null", '{"hosts": []}', '{"hosts": {"tuf": "x"}}',
                     '{"hosts": {"tuf": {}}}', '{"hosts": {"tuf": {"path": 5}}}', '{"hosts": {"tuf": {"path": null}}}'):
            with self.subTest(config=text):
                self.write_hosts(text)
                self.assertRefused(self.py("print('x')"), why=f"cấu hình {text!r}")

    def test_bad_host_names_even_when_listed(self):
        """spec:f2b-chay-xa#S4 — tên sai mẫu (bắt đầu bằng `-`, dấu cách, `;`, `/`...) bị từ chối dù có trong file."""
        self.control()
        bad = ["-oProxyCommand=x", "-tuf", "a b", "a;b", "a/b", "tuf$(x)", "a\nb"]
        self.write_hosts({"hosts": {name: {"path": str(self.bin)} for name in bad}})
        for name in bad:
            with self.subTest(host=name):
                self.assertRefused(self.py("print('x')", host=name), why=f"tên {name!r}")

    def test_unsafe_paths(self):
        """spec:f2b-chay-xa#S4 — `path` không phải đường dẫn tuyệt đối an toàn: mã 2, không chạy lệnh chèn thêm."""
        self.control()
        marker = self.tmp / "PWNED-path"
        bad = ["bin", "./bin", "", "~/bin", "relative/bin", f"{self.bin}; touch {marker}", f"{self.bin}$(touch {marker})",
               f"{self.bin}`touch {marker}`", f"{self.bin}\nx", f"{self.bin}'x", f'{self.bin}"x']
        for path in bad:
            with self.subTest(path=path):
                self.write_hosts({"hosts": {"tuf": {"path": path}}})
                self.assertRefused(self.py("print('x')"), why=f"path {path!r}")
        self.assertFalse(marker.exists())

    def test_config_inside_the_repo_is_never_used(self):
        """spec:f2b-chay-xa#S4 — tên máy và cấu hình không đọc từ file trong repo (`.agent/stack.json`...)."""
        self.control()
        (self.state / "remote-hosts.json").unlink()
        body = json.dumps({"hosts": {"tuf": {"path": str(self.bin)}}, "host": "tuf", "remote": "tuf"})
        for rel in (".agent/stack.json", ".agent/remote-hosts.json", "remote-hosts.json", "state/remote-hosts.json"):
            self.write_repo_file(rel, body)
        git(self.repo, "add", "-f", ".agent", "remote-hosts.json")
        git(self.repo, "commit", "-q", "-m", "cấu hình trong repo")
        self.assertRefused(self.py("print('x')"), why="cấu hình trong repo")

    def test_repo_config_cannot_change_the_path_of_a_listed_host(self):
        """spec:f2b-chay-xa#S4 — máy có trong file ngoài repo thì dùng `path` ở đó, không phải `path` trong repo."""
        other = self.tmp / "other-bin"
        other.mkdir()
        self.write_repo_file(".agent/stack.json", json.dumps({"hosts": {"tuf": {"path": str(other)}}}))
        self.write_repo_file("remote-hosts.json", json.dumps({"hosts": {"tuf": {"path": str(other)}}}))
        git(self.repo, "add", "-f", ".agent", "remote-hosts.json")
        out = self.py(PYTHON_WHICH)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(json_line(out.stdout)[1], str(self.bin))

    def test_ssh_gets_options_then_double_dash_host_and_one_command_string(self):
        """spec:f2b-chay-xa#S4 — mỗi lần gọi ssh: `--`, rồi tên máy, rồi đúng một chuỗi lệnh (tên không thành cờ)."""
        self.assertEqual(self.py("print('x')").returncode, 0)
        calls = self.ssh_calls()
        self.assertTrue(calls)
        for argv in calls:
            with self.subTest(argv=argv[:6]):
                at = argv.index("--")
                self.assertEqual(argv[at + 1], "tuf")
                self.assertEqual(len(argv), at + 3, "đúng một chuỗi lệnh sau tên máy")


class RefusedRepos(RemoteBase):
    def test_untracked_file_is_refused_and_named(self):
        """spec:f2b-chay-xa#S5 — file chưa track mà không bị ignore: mã 2, nêu tên file, không ssh, không biên nhận."""
        self.control()
        self.write_repo_file("quen_add.txt", "chưa add\n")
        out = self.py("print('x')")
        self.assertRefused(out, why="file chưa track")
        self.assertIn("quen_add.txt", out.stdout + out.stderr)

    def test_untracked_file_inside_ignored_dir_is_not_a_reason_to_refuse(self):
        """spec:f2b-chay-xa#S5 — file chưa track nhưng bị ignore (`.tmp/`, `state/`, `.venv*`) không làm từ chối."""
        self.write_repo_file(".tmp/a.txt", "x")
        self.write_repo_file("state/b.txt", "x")
        self.write_repo_file(".venv-x/c.txt", "x")
        out = self.py("print('fine')")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_local_clean_filter_is_refused(self):
        """spec:f2b-chay-xa#S5 — có clean filter cục bộ: mã 2, không ssh, không biên nhận."""
        self.write_repo_file(".gitattributes", "*.txt filter=x\n")
        git(self.repo, "add", ".gitattributes")
        self.control()
        git(self.repo, "config", "filter.x.clean", "cat")
        self.assertRefused(self.py("print('x')"), why="clean filter")

    def test_repo_without_any_commit_is_refused(self):
        """spec:f2b-chay-xa#S5 — repo chưa có commit nào: mã 2 (file đã add, nên không phải vì file chưa track)."""
        fresh = self.tmp / "fresh"
        fresh.mkdir()
        (fresh / "a.txt").write_text("a\n", encoding="utf-8")
        git(fresh, "init", "-q")
        git(fresh, "add", "a.txt")
        self.assertRefused(self.py("print('x')", repo=fresh), repo=fresh, why="chưa có commit")

    def test_ignored_files_never_reach_the_remote(self):
        """spec:f2b-chay-xa#S5 — file bị ignore không có trong bản chép, cũng không trong repo trần trên máy xa."""
        secret = "TOP-SECRET-MARKER-9f3a"
        for rel in (".tmp/secret", "state/x", ".venv-local/lib/y.txt"):
            self.write_repo_file(rel, secret)
        out = self.py(WALK)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        names = json_line(out.stdout)
        for rel in (".tmp/secret", "state/x", ".venv-local/lib/y.txt"):
            self.assertNotIn(rel, names)
        repos = self.remote_repos()
        self.assertTrue(repos)
        for bare in repos:
            dump = subprocess.run(["git", "--git-dir", str(bare), "cat-file", "--batch-all-objects", "--batch"],
                                  capture_output=True, check=True).stdout
            self.assertNotIn(secret.encode(), dump)


class ShellCharacters(RemoteBase):
    def test_arguments_arrive_intact_and_nothing_extra_runs(self):
        """spec:f2b-chay-xa#S6 — `;`, `$(…)`, dấu nháy, dấu cách, xuống dòng: mỗi đối số đến nguyên vẹn, không lệnh thêm."""
        args = [f"a; touch {self.tmp}/PWNED1", f"$(touch {self.tmp}/PWNED2)", f"`touch {self.tmp}/PWNED3`",
                "a; touch PWNED", "$(touch PWNED2)", "it's", 'say "hi"', "x\ny", "two words", "back\\slash",
                "$HOME", "*", "", "a && b | c > d", "--", "-n"]
        out = self.py(PRINT_ARGV, *args)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(json_line(out.stdout), args)
        self.assertEqual([p.name for p in self.tmp.rglob("PWNED*")], [])

    def test_shell_characters_in_the_command_word_arguments_of_a_plain_program(self):
        """spec:f2b-chay-xa#S6 — đối số chứa ký tự shell truyền cho chương trình thường (không phải python -c)."""
        out = self.receipt_run("printf", "%s|", "a; touch PWNED4", "$(id)", "two words")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("a; touch PWNED4|$(id)|two words|", out.stdout)
        self.assertEqual([p.name for p in self.tmp.rglob("PWNED*")], [])


class TransportFailures(RemoteBase):
    def assertNoPassingReceipt(self):
        self.assertEqual([k for k, v in self.checks().items() if v.get("ok")], [])

    def test_ssh_exit_255_is_a_transport_error(self):
        """spec:f2b-chay-xa#S7 — ssh thoát 255 (mất mạng): receipt.py thoát 255, biên nhận trượt có `remote_error`."""
        self.set_ssh("fail", code=255)
        out = self.py("print('x')")
        self.assertEqual(out.returncode, 255, out.stdout + out.stderr)
        rec = self.one_check()
        self.assertFalse(rec["ok"])
        self.assertEqual(rec["exit"], 255)
        self.assertTrue(isinstance(rec.get("remote_error"), str) and rec["remote_error"].strip(), rec)
        self.assertNoPassingReceipt()

    def test_ssh_failing_with_another_code_is_still_255(self):
        """spec:f2b-chay-xa#S7 — ssh trả mã khác 0 trước khi lệnh xong (mã 7): receipt.py vẫn thoát 255."""
        self.set_ssh("fail", code=7)
        out = self.py("print('x')")
        self.assertEqual(out.returncode, 255, out.stdout + out.stderr)
        self.assertIn("remote_error", self.one_check())
        self.assertNoPassingReceipt()

    def test_output_without_the_end_line_is_a_transport_error(self):
        """spec:f2b-chay-xa#S7 — ssh thoát 0 nhưng output thiếu dòng kết thúc mang nonce: 255."""
        self.set_ssh("silent")
        out = self.py("print('x')")
        self.assertEqual(out.returncode, 255, out.stdout + out.stderr)
        self.assertIn("remote_error", self.one_check())
        self.assertNoPassingReceipt()

    def test_end_line_with_a_wrong_nonce_is_a_transport_error(self):
        """spec:f2b-chay-xa#S7 — chỉ có dòng kết thúc sai nonce: 255, không tin mã 0 trong dòng đó."""
        self.set_ssh("fakeend")
        out = self.py("print('x')")
        self.assertEqual(out.returncode, 255, out.stdout + out.stderr)
        self.assertIn("remote_error", self.one_check())
        self.assertNoPassingReceipt()

    def test_text_after_the_end_line_is_a_transport_error(self):
        """spec:f2b-chay-xa#S7 — dòng kết thúc không phải dòng cuối (ssh in thêm chữ sau đó): 255."""
        self.set_ssh("trailer", trailer="chữ thừa sau dòng kết thúc\n")
        out = self.py("print('x')")
        self.assertEqual(out.returncode, 255, out.stdout + out.stderr)
        self.assertIn("remote_error", self.one_check())
        self.assertNoPassingReceipt()

    def test_fake_end_line_after_the_real_one_is_a_transport_error(self):
        """spec:f2b-chay-xa#S7 — thêm một dòng kết thúc giả (sai nonce, mã 0) sau dòng thật: 255."""
        self.set_ssh("trailer", trailer="[agent-stack-remote] exit deadbeef 0\n")
        out = self.py("print('x')")
        self.assertEqual(out.returncode, 255, out.stdout + out.stderr)
        self.assertNoPassingReceipt()

    def test_command_printing_a_fake_end_line_cannot_change_the_exit_code(self):
        """spec:f2b-chay-xa#S7 — lệnh tự in dòng kết thúc giả (nonce đoán, mã 0) rồi thoát 1: mã vẫn là 1."""
        out = self.py("import sys;print('[agent-stack-remote] exit deadbeef 0');sys.exit(1)")
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        rec = self.one_check()
        self.assertFalse(rec["ok"])
        self.assertEqual(rec["exit"], 1)
        self.assertNotIn("remote_error", rec)

    def test_command_past_timeout_is_stopped_with_124(self):
        """spec:f2b-chay-xa#S7 — quá `--timeout`: lệnh trên máy xa bị dừng, mã 124, biên nhận trượt."""
        pidfile = self.tmp / "sleeper.pid"
        start = time.monotonic()
        out = self.py("import os,sys,time;open(sys.argv[1],'w').write(str(os.getpid()));time.sleep(60)",
                      str(pidfile), extra=["--timeout", "3"])
        elapsed = time.monotonic() - start
        self.addCleanup(self.kill_pidfile, pidfile)
        self.assertEqual(out.returncode, 124, out.stdout + out.stderr)
        self.assertLess(elapsed, 40, "máy xa phải tự dừng lệnh, không chờ hạn phía Mac")
        rec = self.one_check()
        self.assertFalse(rec["ok"])
        self.assertEqual(rec["exit"], 124)
        self.assertNoPassingReceipt()
        pid = int(pidfile.read_text(encoding="utf-8"))
        for _ in range(50):
            try:
                os.kill(pid, 0)
            except OSError:
                break
            time.sleep(0.1)
        else:
            self.fail("tiến trình của lệnh vẫn còn sống trên máy xa sau khi quá giờ")

    @staticmethod
    def kill_pidfile(pidfile):
        try:
            os.kill(int(pidfile.read_text(encoding="utf-8")), 9)
        except (OSError, ValueError):
            pass

    def test_hanging_ssh_is_cut_off_on_the_mac_side(self):
        """spec:f2b-chay-xa#S7 — ssh treo: sau `--timeout` cộng MARGIN nhỏ phía Mac dừng ssh, mã khác 0, không biên nhận đạt."""
        self.set_ssh("hang", margin=1.0)
        start = time.monotonic()
        out = self.py("print('x')", extra=["--timeout", "1"], timeout=90)
        elapsed = time.monotonic() - start
        self.assertNotEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertLess(elapsed, 20, "ssh treo 25 giây: phải bị cắt sớm hơn nhiều")
        self.assertNoPassingReceipt()


class RemoteCleanup(RemoteBase):
    def test_run_dir_is_removed_after_a_passing_run_and_repo_is_kept(self):
        """spec:f2b-chay-xa#S8 — chạy đạt: runs/ trên máy xa rỗng, repo trần còn."""
        out = self.py("print('x')")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertEqual(self.left_over_runs(), [])
        repos = self.remote_repos()
        self.assertEqual(len(repos), 1)
        bare = subprocess.run(["git", "--git-dir", str(repos[0]), "rev-parse", "--is-bare-repository"],
                              capture_output=True, text=True)
        self.assertEqual(bare.stdout.strip(), "true", bare.stderr)
        rec = self.one_check()
        has = subprocess.run(["git", "--git-dir", str(repos[0]), "cat-file", "-e", rec["remote_commit"]],
                             capture_output=True, text=True)
        self.assertEqual(has.returncode, 0, "commit tạm đã gửi phải nằm trong repo trần: " + has.stderr)

    def test_run_dir_is_removed_after_a_failing_run(self):
        """spec:f2b-chay-xa#S8 — chạy trượt (mã 1): runs/ rỗng, repo trần còn."""
        out = self.py("import sys;sys.exit(1)")
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertEqual(self.left_over_runs(), [])
        self.assertEqual(len(self.remote_repos()), 1)

    def test_run_dir_is_removed_after_a_timeout(self):
        """spec:f2b-chay-xa#S8 — quá giờ phía máy xa: runs/ rỗng, repo trần còn."""
        pidfile = self.tmp / "sleeper2.pid"
        self.addCleanup(TransportFailures.kill_pidfile, pidfile)
        out = self.py("import os,sys,time;open(sys.argv[1],'w').write(str(os.getpid()));time.sleep(60)",
                      str(pidfile), extra=["--timeout", "3"])
        self.assertEqual(out.returncode, 124, out.stdout + out.stderr)
        self.assertEqual(self.left_over_runs(), [])
        self.assertEqual(len(self.remote_repos()), 1)

    def test_second_run_passes_and_reuses_the_repo(self):
        """spec:f2b-chay-xa#S8 — lần chạy thứ hai vẫn đạt, vẫn một repo trần, runs/ rỗng."""
        for n in (1, 2):
            out = self.py(f"print('lần {n}')")
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
            self.assertIn(f"lần {n}", out.stdout)
        self.assertEqual(self.left_over_runs(), [])
        self.assertEqual(len(self.remote_repos()), 1)

    def test_second_run_sends_only_new_objects(self):
        """spec:f2b-chay-xa#S8 — repo trần được giữ: lần sau chỉ gửi object mới (file lớn không gửi lại)."""
        (self.repo / "big.bin").write_bytes(os.urandom(300_000))
        git(self.repo, "add", "big.bin")
        git(self.repo, "commit", "-q", "-m", "file lớn")
        self.assertEqual(self.py("print('1')").returncode, 0)
        first = self.ssh_stdin_bytes()
        self.assertGreater(first, 250_000, "lần đầu phải gửi file lớn qua ssh")
        self.reset_ssh_log()
        self.write_repo_file("keep.txt", "đổi nhỏ\n")
        self.assertEqual(self.py("print('2')").returncode, 0)
        self.assertLess(self.ssh_stdin_bytes(), 100_000)


# ---------------------------------------------------------------------------------------------------------------- mutation

CALC_BASE = '"""Máy tính."""\n\n\ndef add(a, b):\n    return a + b\n'
CALC_BUMP = "\n\ndef bump(x):\n    return x + 10\n"
CALC_SCALE = "\n\ndef scale(x):\n    return x * 2 + 1\n"
TEST_X = ("import unittest\nfrom calc import add\n\n\nclass T(unittest.TestCase):\n"
          "    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n")
MUT_CMD = "python3 -m unittest tests.test_x"
GOOD_JSON = {"status": "ran", "total": 3, "killed": 3, "survived": [], "timeout": 0, "untested": 0, "outside": [],
             "unreached": [], "unreached_known": True, "estimate_seconds": 0}


class MutationBase(RemoteBase):
    def setUp(self):
        super().setUp()
        import mutation  # noqa: PLC0415
        self.mutation = mutation
        self.stack = self.make_stack()
        os.environ["AGENT_STACK_HOME"] = str(self.stack)

    def make_stack(self, name="stack", bump_committed=False):
        """Repo tạm đóng vai agent-stack: có `plugin/`, calc.py, tests/test_x.py; calc.py sửa chưa commit."""
        stack = self.tmp / name
        stack.mkdir()
        shutil.copytree(PLUGIN, stack / "plugin", symlinks=True,
                        ignore=shutil.ignore_patterns("__pycache__", "node_modules", "*.pyc", "results"))
        shutil.copy2(REPO / ".agent-stack-root", stack / ".agent-stack-root")
        (stack / ".gitignore").write_text(".tmp/\nstate/\n__pycache__/\n*.pyc\n", encoding="utf-8")
        (stack / "calc.py").write_text(CALC_BASE, encoding="utf-8")
        (stack / "tests").mkdir()
        (stack / "tests" / "test_x.py").write_text(TEST_X, encoding="utf-8")
        git(stack, "init", "-q")
        git(stack, "add", "-A")
        git(stack, "commit", "-q", "-m", "gốc")
        if bump_committed:
            with open(stack / "calc.py", "a", encoding="utf-8") as f:
                f.write(CALC_BUMP)
            git(stack, "commit", "-qam", "thêm bump")
        with open(stack / "calc.py", "a", encoding="utf-8") as f:
            f.write(CALC_SCALE)
        return stack

    def mut(self, *args, project=None):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = self.mutation.main(["--project", str(project or self.stack), *args])
        return code, [x for x in buf.getvalue().splitlines() if x.strip()]

    def fake_result(self, **kw):
        base = {"code": 0, "output": "", "error": None, "ship": None, "head": None, "seconds": 0.1}
        base.update(kw)
        return self.remote.RemoteResult(**base)

    def good_result(self):
        return self.fake_result(output=json.dumps(GOOD_JSON))

    def patched(self, result):
        return mock.patch.object(self.mutation.R, "run_remote", return_value=result)

    def assertNotRan(self, code, lines, why=""):
        self.assertEqual(code, 0, f"{why}: {lines}")
        self.assertTrue(lines and lines[-1].startswith("Mutation: chưa chạy:"), f"{why}: {lines}")
        self.assertIsNone(re.match(r"Mutation: \d+ đột biến", lines[-1]), why)

    def control_mut(self):
        """Đối chứng: với tên máy hợp lệ và dữ liệu máy xa tốt, mutation in kết quả từ máy xa."""
        with self.patched(self.good_result()) as run:
            code, lines = self.mut("--host", "tuf", "--cmd", MUT_CMD, "--timeout", "60")
        self.assertEqual(code, 0, lines)
        self.assertTrue(run.called, "phải gọi run_remote")
        self.assertTrue(lines[-1].startswith("Mutation: 3 đột biến trên dòng đổi, 3 bị bắt, 0 sống"), lines)


class MutationOnRemote(MutationBase):
    @unittest.skipUnless(REAL_MUTMUT.is_file(), f"cần {REAL_MUTMUT} (mutation.py setup)")
    def test_mutation_runs_on_the_remote_machine_and_prints_the_local_format(self):
        """spec:f2b-chay-xa#S9 — `mutation.py --host`: mutmut chạy trên máy xa, dòng cuối `Mutation: N đột biến…`,
        thêm dòng `- máy chạy: tuf`; thay đổi chưa commit vẫn là thay đổi so với REF (HEAD)."""
        venv_bin = self.rdir("venv-mutmut", "bin")
        venv_bin.mkdir(parents=True)
        (venv_bin / "mutmut").symlink_to(REAL_MUTMUT)
        code, lines = self.mut("--host", "tuf", "--cmd", MUT_CMD, "--timeout", "300")
        self.assertEqual(code, 0, lines)
        self.assertTrue(self.ssh_calls(), "phải đi qua ssh")
        match = re.match(r"Mutation: (\d+) đột biến trên dòng đổi, (\d+) bị bắt, (\d+) sống", lines[-1])
        self.assertIsNotNone(match, lines[-5:])
        total, killed, survived = map(int, match.groups())
        self.assertGreaterEqual(total, 3)
        self.assertEqual(killed + survived, total, "test_x không chạm scale() nên đột biến còn sống")
        self.assertGreaterEqual(survived, 1)
        self.assertTrue(any(x.startswith("- máy chạy: tuf") for x in lines), lines)
        self.assertEqual(self.left_over_runs(), [])

    @unittest.skipUnless(REAL_MUTMUT.is_file(), f"cần {REAL_MUTMUT} (mutation.py setup)")
    def test_base_ref_is_resolved_on_the_mac_side(self):
        """spec:f2b-chay-xa#S9 — `--base REF` đổi thành mã băm trên Mac: so với HEAD~1 có thêm đột biến của `bump`."""
        self.stack = self.make_stack("stack2", bump_committed=True)
        os.environ["AGENT_STACK_HOME"] = str(self.stack)
        venv_bin = self.rdir("venv-mutmut", "bin")
        venv_bin.mkdir(parents=True)
        (venv_bin / "mutmut").symlink_to(REAL_MUTMUT)
        totals = []
        for base in ("HEAD", "HEAD~1"):
            code, lines = self.mut("--host", "tuf", "--base", base, "--cmd", MUT_CMD, "--timeout", "300")
            self.assertEqual(code, 0, lines)
            match = re.match(r"Mutation: (\d+) đột biến", lines[-1])
            self.assertIsNotNone(match, f"--base {base}: {lines[-5:]}")
            totals.append(int(match.group(1)))
        self.assertGreater(totals[1], totals[0], totals)

    def test_options_and_environment_are_forwarded_to_the_remote_command(self):
        """spec:f2b-chay-xa#S9 — --jobs, --no-select, --cmd, --timeout đi theo; REF thành mã băm; mutmut ở
        ~/.cache/agent-stack-remote/venv-mutmut."""
        want = git(self.stack, "rev-parse", "HEAD~0").strip()
        with self.patched(self.good_result()) as run:
            code, lines = self.mut("--host", "tuf", "--base", "HEAD", "--cmd", MUT_CMD, "--jobs", "2", "--no-select",
                                   "--timeout", "77")
        self.assertEqual(code, 0, lines)
        self.assertTrue(run.called)
        blob = json.dumps([run.call_args.args, run.call_args.kwargs], default=str)
        for needle in ("--jobs", "--no-select", "tests.test_x", want, "AGENT_STACK_MUTMUT",
                       "agent-stack-remote/venv-mutmut/bin/mutmut"):
            self.assertIn(needle, blob)
        self.assertNotIn('"HEAD"', blob, "REF phải đổi thành mã băm")
        self.assertTrue(lines[-1].startswith("Mutation: 3 đột biến"), lines)
        self.assertTrue(any(x.startswith("- máy chạy: tuf") for x in lines), lines)

    def test_remote_result_is_shown_in_the_local_format(self):
        """spec:f2b-chay-xa#S9 — kết quả JSON từ máy xa được in cùng định dạng chạy tại chỗ (đếm, dòng sống)."""
        data = dict(GOOD_JSON, total=4, killed=3, survived=[{"file": "calc.py", "line": 7, "diff": "+    return 1\n"}])
        with self.patched(self.fake_result(output=json.dumps(data))):
            code, lines = self.mut("--host", "tuf", "--cmd", MUT_CMD)
        self.assertEqual(code, 0, lines)
        self.assertTrue(lines[-1].startswith("Mutation: 4 đột biến trên dòng đổi, 3 bị bắt, 1 sống"), lines)
        self.assertTrue(any(x.startswith("- sống: calc.py:7") for x in lines), lines)
        self.assertTrue(any(x.startswith("- máy chạy: tuf") for x in lines), lines)


class MutationRefusals(MutationBase):
    def control_real(self):
        """Đối chứng không vá: tên máy hợp lệ thì có gọi ssh (máy xa giả không có mutmut nên kết quả vẫn là "chưa chạy")."""
        code, lines = self.mut("--host", "tuf", "--cmd", MUT_CMD, "--timeout", "120")
        self.assertEqual(code, 0, lines)
        self.assertTrue(self.ssh_calls(), "tên máy hợp lệ phải đi tới ssh")
        self.reset_ssh_log()

    def run_refused(self, *args, project=None, why=""):
        """Không vá run_remote: từ chối (kể cả `remote.Refused` bên trong) phải xảy ra trước khi gọi ssh."""
        self.reset_ssh_log()
        code, lines = self.mut(*args, project=project)
        self.assertNotRan(code, lines, why)
        self.assertEqual(self.ssh_calls(), [], f"{why}: không được gọi ssh")

    def test_unknown_or_unsafe_host_or_config(self):
        """spec:f2b-chay-xa#S10 — tên máy không được phép (không có trong file, sai mẫu, file thiếu hay hỏng): chưa chạy."""
        self.control_real()
        self.write_hosts({"hosts": {"-oProxyCommand=x": {"path": str(self.bin)}, "tuf": {"path": str(self.bin)}}})
        self.run_refused("--host", "khac", "--cmd", MUT_CMD, why="tên không có trong file")
        self.run_refused("--host", "-oProxyCommand=x", "--cmd", MUT_CMD, why="tên bắt đầu bằng -")
        self.write_hosts("{hỏng")
        self.run_refused("--host", "tuf", "--cmd", MUT_CMD, why="file hỏng")
        (self.state / "remote-hosts.json").unlink()
        self.run_refused("--host", "tuf", "--cmd", MUT_CMD, why="file thiếu")

    def test_relative_path_in_config(self):
        """spec:f2b-chay-xa#S10 — `path` không phải đường dẫn tuyệt đối: chưa chạy."""
        self.control_real()
        self.write_hosts({"hosts": {"tuf": {"path": "bin"}}})
        self.run_refused("--host", "tuf", "--cmd", MUT_CMD, why="path tương đối")

    def test_link_option_is_refused(self):
        """spec:f2b-chay-xa#S10 — `--link` không dùng được ở máy xa: chưa chạy."""
        self.control_real()
        (self.stack / ".venv").mkdir()
        self.run_refused("--host", "tuf", "--link", ".venv", "--cmd", MUT_CMD, why="--link")

    def test_mutmut_option_is_refused(self):
        """spec:f2b-chay-xa#S10 — `--mutmut` không dùng được ở máy xa: chưa chạy."""
        self.control_real()
        self.run_refused("--host", "tuf", "--mutmut", "x", "--cmd", MUT_CMD, why="--mutmut")

    def test_project_that_is_not_the_agent_stack_repo(self):
        """spec:f2b-chay-xa#S10 — project không phải repo agent-stack (AGENT_STACK_HOME): chưa chạy."""
        self.control_real()
        other = self.tmp / "other"
        other.mkdir()
        (other / "calc.py").write_text(CALC_BASE, encoding="utf-8")
        git(other, "init", "-q")
        git(other, "add", "-A")
        git(other, "commit", "-q", "-m", "x")
        (other / "calc.py").write_text(CALC_BASE + CALC_SCALE, encoding="utf-8")
        self.run_refused("--host", "tuf", "--cmd", MUT_CMD, project=other, why="project khác")

    def test_base_that_is_not_an_ancestor_of_head(self):
        """spec:f2b-chay-xa#S10 — REF không phải tổ tiên của HEAD: chưa chạy."""
        self.control_real()
        orphan = git(self.stack, "commit-tree", "HEAD^{tree}", "-m", "mồ côi").strip()
        self.run_refused("--host", "tuf", "--base", orphan, "--cmd", MUT_CMD, why="REF không phải tổ tiên")
        self.run_refused("--host", "tuf", "--base", "khong-co-ref-nay", "--cmd", MUT_CMD, why="REF không có")

    def test_ssh_failure_is_not_a_mutation_result(self):
        """spec:f2b-chay-xa#S10 — ssh lỗi (255): thoát 0, `Mutation: chưa chạy:`."""
        self.control_mut()
        self.set_ssh("fail", code=255)
        code, lines = self.mut("--host", "tuf", "--cmd", MUT_CMD, "--timeout", "60")
        self.assertNotRan(code, lines, "ssh 255")
        self.assertTrue(self.ssh_calls(), "phải đã thử ssh")

    def test_ssh_that_hangs_is_not_a_mutation_result(self):
        """spec:f2b-chay-xa#S10 — ssh treo, quá giờ phía Mac: thoát 0, `Mutation: chưa chạy:`, không treo theo."""
        self.control_mut()
        self.set_ssh("hang", margin=1.0)
        start = time.monotonic()
        code, lines = self.mut("--host", "tuf", "--cmd", MUT_CMD, "--timeout", "1")
        self.assertNotRan(code, lines, "ssh treo")
        self.assertTrue(self.ssh_calls(), "phải đã thử ssh")
        self.assertLess(time.monotonic() - start, 20)

    def test_remote_failure_results_are_not_a_mutation_result(self):
        """spec:f2b-chay-xa#S10 — máy xa báo lỗi vận chuyển (255), quá giờ (124) hay lệnh lỗi: chưa chạy."""
        self.control_mut()
        for code_, error in ((255, "ssh: mất kết nối"), (124, "quá giờ"), (1, None)):
            with self.subTest(code=code_):
                with self.patched(self.fake_result(code=code_, error=error, output=json.dumps(GOOD_JSON))):
                    code, lines = self.mut("--host", "tuf", "--cmd", MUT_CMD)
                self.assertNotRan(code, lines, f"RemoteResult mã {code_}")

    def test_unreadable_remote_json_is_never_turned_into_counts(self):
        """spec:f2b-chay-xa#S10 — JSON máy xa hỏng hay sai kiểu: không bao giờ ra "Mutation: N đột biến…"."""
        self.control_mut()
        bad = ['{"status":"ran","total":"x"}', "đây không phải JSON", "", "[]", "null", "[1, 2]",
               '{"status":"ran","total":3,"killed":"nhiều","survived":[]}',
               '{"status":"ran","total":3,"killed":3,"survived":"x"}', '{"status":"khac","total":3,"killed":3}',
               '{"status":"ran","total":3,"killed":3,']
        for text in bad:
            with self.subTest(output=text):
                with self.patched(self.fake_result(output=text)):
                    code, lines = self.mut("--host", "tuf", "--cmd", MUT_CMD)
                self.assertNotRan(code, lines, f"output {text!r}")


if __name__ == "__main__":
    unittest.main()
