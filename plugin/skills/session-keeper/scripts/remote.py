#!/usr/bin/env python3
"""Chạy một lệnh kiểm tra trên máy xa qua SSH (F2b, TM-161–165), dùng cho `receipt.py run --host` và
`mutation.py --host`.

Máy xa chỉ nhận đúng code đang có ở máy này: commit HEAD cộng thay đổi chưa commit của các file git đang theo dõi
(một commit tạm dựng bằng chỉ mục tạm, index thật không đổi). Object git đi qua stdin của `ssh` (`git pack-objects`
→ `git index-pack`), không dùng giao thức git qua ssh, nên cấu hình git của repo (`url.*.insteadOf`,
`core.sshCommand`) không đổi được đích. File chưa track (không bị ignore) thì từ chối; file bị ignore (`state/`,
`.tmp/`, `.venv*`) không bao giờ được gửi.

Tên máy chỉ lấy từ `state/remote-hosts.json` của agent-stack (ngoài git, bạn kiểm soát), không từ file nào trong
repo: `{"hosts": {"tuf": {"path": "/home/<tên>/.pyenv/versions/3.11.16/bin"}}}`. `path` được đặt trước PATH trên máy
xa để `python3` là Python 3.11.

Trên máy xa (tính từ HOME): `.cache/agent-stack-remote/repos/<repo>-<mã>.git` (repo trần, giữ lại để lần sau chỉ gửi
object mới), `.cache/agent-stack-remote/runs/<id>` (thư mục chạy, xóa khi lệnh xong). Mã thoát chỉ tin dòng cuối
`[agent-stack-remote] exit <nonce> <mã>` do chương trình chạy lệnh in ra; thiếu hay sai thì là lỗi vận chuyển (255).
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3] / "lib"))  # agentstack
import agentstack as A  # noqa: E402

SSH = ["ssh"]
SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=4", "-T"]
MARGIN = 60  # giây chờ thêm ở máy này sau hạn của lệnh (dựng bản chép, dọn)
SETUP_TIMEOUT = 300  # giây cho bước chuẩn bị và gửi object
CLEANUP_TIMEOUT = 20
BASE = ".cache/agent-stack-remote"
HOSTS_FILE = "remote-hosts.json"
HOST_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,62}")
BIN_RE = re.compile(r"/[A-Za-z0-9._/+-]{0,250}")
REL_RE = re.compile(r"[A-Za-z0-9._+-][A-Za-z0-9._/+-]{0,250}")
ENV_RE = re.compile(r"[A-Z][A-Z0-9_]{0,63}")
SHA_RE = re.compile(r"[0-9a-f]{40}")
END = "[agent-stack-remote] exit"
GIT = ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null"]
GIT_ID = {"GIT_AUTHOR_NAME": "agent-stack", "GIT_AUTHOR_EMAIL": "agent-stack@localhost",
          "GIT_COMMITTER_NAME": "agent-stack", "GIT_COMMITTER_EMAIL": "agent-stack@localhost",
          "GIT_AUTHOR_DATE": "@0 +0000", "GIT_COMMITTER_DATE": "@0 +0000"}
MAX_LISTED = 8

# Chạy lệnh trên máy xa với hạn giờ, gộp stderr vào stdout, giết cả nhóm tiến trình khi quá giờ, rồi in dòng kết thúc
# có nonce. Chạy bằng `python3 -I -c` (không nạp module từ thư mục chạy, là nội dung repo).
RUNNER = """import os, signal, subprocess, sys
limit, nonce, cmd = float(sys.argv[1]), sys.argv[2], sys.argv[3:]
try:
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        code = proc.wait(timeout=limit)
    except subprocess.TimeoutExpired:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(proc.pid, sig)
            except OSError:
                pass
            try:
                proc.wait(timeout=10)
                break
            except subprocess.TimeoutExpired:
                continue
        print("\\n[agent-stack-remote] dừng sau %.0f giây" % limit, flush=True)
        code = 124
except OSError as exc:
    print("[agent-stack-remote] không chạy được lệnh: %s" % exc, flush=True)
    code = 127
if code < 0:
    code = 128 - code
sys.stdout.write("\\n[agent-stack-remote] exit %s %d\\n" % (nonce, code))
sys.stdout.flush()
"""


class Refused(Exception):
    """Từ chối trước khi gọi ssh (mã 2, không ghi biên nhận)."""


@dataclasses.dataclass
class RemoteResult:
    code: int
    output: str
    error: str | None = None
    ship: str | None = None
    head: str | None = None
    seconds: float = 0.0
    fingerprint: str | None = None
    code_fingerprint: str | None = None


def hosts_file() -> Path:
    return A.state_dir() / HOSTS_FILE


def host_config(name) -> dict:
    """Cấu hình của máy `name` trong danh sách cho phép (TM-161). Raise Refused khi tên sai mẫu, không có trong danh
    sách, file thiếu hay hỏng, `path` không an toàn."""
    if not isinstance(name, str) or not HOST_RE.fullmatch(name):
        raise Refused(f"tên máy {name!r} sai mẫu (chữ, số, `.`, `_`, `-`; không bắt đầu bằng `-`)")
    path = hosts_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Refused(f"chưa có danh sách máy {path} (ngoài git; dạng {{\"hosts\": {{\"{name}\": {{\"path\": "
                      "\"<thư mục bin của python3.11>\"}}}})") from None
    except (OSError, ValueError) as exc:
        raise Refused(f"danh sách máy {path} hỏng ({exc})") from None
    hosts = data.get("hosts") if isinstance(data, dict) else None
    conf = hosts.get(name) if isinstance(hosts, dict) else None
    if not isinstance(conf, dict):
        raise Refused(f"máy {name} không có trong danh sách máy được phép {path}")
    bindir = conf.get("path")
    if not (isinstance(bindir, str) and BIN_RE.fullmatch(bindir) and ".." not in bindir.split("/")):
        raise Refused(f"máy {name}: `path` phải là đường dẫn tuyệt đối chỉ gồm chữ, số, `._/+-` (nhận {bindir!r})")
    return {"path": bindir.rstrip("/") or "/"}


def git(top: Path, *args: str, env=None, data: bytes | None = None, timeout: float = 120) -> bytes:
    """Chạy git ở máy này; lỗi thì Refused (chưa gọi ssh)."""
    try:
        out = subprocess.run([*GIT, "-C", str(top), *args], input=data, capture_output=True, env=env, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Refused(f"git {args[0]} lỗi ({exc})") from None
    if out.returncode != 0:
        raise Refused(f"git {args[0]} lỗi: {out.stderr.decode('utf-8', 'replace').strip()[-300:]}")
    return out.stdout


def fingerprints(root: Path):
    """(dấu vân tay cả cây, dấu phần code) như receipt.fingerprints."""
    blobs, docs = A.tree_blobs(root), A.doc_filter(root)
    after = None if blobs is None else A.blobs_digest(blobs)
    return after, (None if blobs is None or docs is None else A.blobs_digest(blobs, docs))


def ship(root: Path) -> dict:
    """Commit tạm = HEAD + thay đổi của file đang theo dõi (TM-163, TM-164). Không ghi index thật hay ref nào; object
    của commit tạm nằm lơ lửng trong repo tới khi git dọn."""
    try:
        top = Path(subprocess.run([*GIT, "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True,
                                  text=True, timeout=30).stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        top = Path()
    if not top.is_absolute():
        raise Refused("không phải git repo")
    try:
        head = git(top, "rev-parse", "--verify", "-q", "HEAD^{commit}").decode().strip()
    except Refused:
        raise Refused("repo chưa có commit nào") from None
    staged = git(top, "ls-files", "-s", "-z").decode("utf-8", "surrogateescape").split("\0")
    gitlinks = [e.partition("\t")[2] for e in staged if e.startswith("160000 ")]
    if gitlinks:
        raise Refused(f"repo có submodule ({', '.join(gitlinks[:MAX_LISTED])}): máy xa chỉ nhận repo chính nên sẽ chạy "
                      "thiếu code")
    if A.local_clean_filters(top):
        raise Refused("repo khai báo clean filter cục bộ: đóng gói sẽ chạy lệnh của repo (TM-57)")
    untracked = [p for p in git(top, "ls-files", "--others", "--exclude-standard", "-z").decode(
        "utf-8", "surrogateescape").split("\0") if p]
    if untracked:
        names = ", ".join(untracked[:MAX_LISTED]) + (f" và {len(untracked) - MAX_LISTED} file khác"
                                                    if len(untracked) > MAX_LISTED else "")
        raise Refused(f"có file chưa track không bị ignore: {names}. Máy xa chỉ nhận file git đang theo dõi; "
                      "`git add` hay thêm vào .gitignore rồi chạy lại")
    before = fingerprints(root)
    if before[0] is None:
        raise Refused("không tính được dấu vân tay của cây làm việc (git lỗi hay quá giờ): biên nhận sẽ không gắn được "
                      "với code đã gửi")
    index = Path(git(top, "rev-parse", "--path-format=absolute", "--git-path", "index").decode().strip())
    with tempfile.TemporaryDirectory(prefix="agent-stack-remote-") as tmp:
        tmp_index = Path(tmp) / "index"
        if index.is_file():
            shutil.copyfile(index, tmp_index)
            # Mục tạm có mốc giờ rất cũ: git coi mọi mục là "racy" và so nội dung, không tin stat (file sửa hai lần trong
            # cùng giây, cùng cỡ vẫn được thấy).
            os.utime(tmp_index, (1, 1))
        env = {**os.environ, "GIT_INDEX_FILE": str(tmp_index), **GIT_ID}
        if not index.is_file():
            git(top, "read-tree", head, env=env)
        git(top, "add", "-u", env=env)
        tree = git(top, "write-tree", env=env).decode().strip()
        if tree == git(top, "rev-parse", head + "^{tree}").decode().strip():
            commit = head
        else:
            commit = git(top, "commit-tree", tree, "-p", head, "-m", "agent-stack-remote: HEAD + thay đổi chưa commit",
                         env=env).decode().strip()
    if fingerprints(root) != before:
        raise Refused("cây làm việc đổi trong lúc đóng gói; chạy lại khi không còn ai sửa file")
    return {"top": top, "head": head, "ship": commit, "fingerprint": before[0], "code_fingerprint": before[1]}


def repo_name(top: Path) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", top.name)[:40].lstrip(".-") or "repo"
    return f"{safe}-{hashlib.sha1(str(top).encode('utf-8', 'surrogateescape')).hexdigest()[:8]}"


def ssh(host: str, script: str, timeout: float, stdin=None):
    """Gọi ssh bằng danh sách tham số (TM-162); `script` chỉ ghép từ phần cố định và shlex.quote."""
    return subprocess.run([*SSH, *SSH_OPTS, "--", host, script], stdin=stdin if stdin is not None else
                          subprocess.DEVNULL, capture_output=True, timeout=timeout)


def text(data) -> str:
    return (data or b"").decode("utf-8", "replace")


def upload(host: str, info: dict, bare: str, limit: float) -> str | None:
    """Đưa object còn thiếu lên repo trần của máy xa. None khi xong, chữ khi lỗi. `limit`: hạn mỗi lần gọi ssh."""
    q = shlex.quote
    prepare = (f'cd "$HOME" && mkdir -p {q(BASE + "/repos")} {q(BASE + "/runs")} && '
               f'{{ [ -d {q(bare)} ] || git init -q --bare {q(bare)}; }} && '
               f"git -C {q(bare)} for-each-ref --format='%(objectname)' refs/heads/")
    try:
        out = ssh(host, prepare, limit)
    except subprocess.TimeoutExpired:
        return f"quá {limit:.0f} giây khi chuẩn bị repo trên máy {host}"
    except OSError as exc:
        return f"không chạy được ssh ({exc})"
    if out.returncode != 0:
        return f"ssh mã {out.returncode} khi chuẩn bị repo: {text(out.stderr).strip()[-300:]}"
    known = [s for s in text(out.stdout).split() if SHA_RE.fullmatch(s)]
    if info["ship"] in known:
        return None
    top = info["top"]
    have = [s for s in known if subprocess.run([*GIT, "-C", str(top), "cat-file", "-e", s + "^{commit}"],
                                               capture_output=True).returncode == 0]
    revs = (info["ship"] + "\n" + "".join(f"^{s}\n" for s in have)).encode()
    with tempfile.TemporaryFile() as pack:
        try:
            made = subprocess.run([*GIT, "-C", str(top), "pack-objects", "--revs", "--stdout", "-q"], input=revs,
                                  stdout=pack, stderr=subprocess.PIPE, timeout=SETUP_TIMEOUT)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return f"git pack-objects lỗi ({exc})"
        if made.returncode != 0:
            return f"git pack-objects lỗi: {text(made.stderr).strip()[-300:]}"
        pack.seek(0)
        store = (f'cd "$HOME" && git -C {q(bare)} index-pack --stdin >/dev/null && '
                 f"git -C {q(bare)} update-ref refs/heads/last {info['ship']}")
        try:
            out = ssh(host, store, limit, stdin=pack)
        except subprocess.TimeoutExpired:
            return f"quá {limit:.0f} giây khi gửi object lên máy {host}"
        except OSError as exc:
            return f"không chạy được ssh ({exc})"
    if out.returncode != 0:
        return f"ssh mã {out.returncode} khi gửi object: {text(out.stderr).strip()[-300:]}"
    return None


def run_script(info: dict, bare: str, run: str, sub: str, bindir: str, cmd: list, timeout: float, nonce: str,
               home_env: dict) -> str:
    """Chuỗi lệnh shell cho máy xa: dựng thư mục chạy đúng commit tạm, kiểm cây khớp, chạy lệnh, xóa thư mục."""
    q = shlex.quote
    fail = "{ echo '[agent-stack-remote] lỗi: %s'; exit 97; }"
    exports = "".join(f'export {key}="$HOME"/{q(rel)}\n' for key, rel in home_env.items())
    reset = f"git reset -q --soft {info['head']}\n" if info["ship"] != info["head"] else ""
    return (
        'cd "$HOME" || exit 97\n'
        f"trap 'cd \"$HOME\" && rm -rf -- {q(run)} >/dev/null 2>&1' EXIT\n"
        f"git clone -q --no-checkout --shared {q(bare)} {q(run)} >/dev/null 2>&1 || " + fail % "dựng bản chép" + "\n"
        f"cd {q(run)} || exit 97\n"
        f"git -c core.hooksPath=/dev/null -c advice.detachedHead=false checkout -q --detach {info['ship']} "
        "|| " + fail % "checkout" + "\n"
        + reset +
        f"git diff --quiet {info['ship']} -- && test -z \"$(git ls-files --others)\" || "
        + fail % "cây chạy không khớp commit tạm" + "\n"
        f"cd {q(sub)} || " + fail % "thư mục chạy" + "\n"
        f"export PATH={q(bindir)}:\"$PATH\"\n" + exports
        + " ".join(q(x) for x in [f"{bindir}/python3", "-I", "-c", RUNNER, f"{timeout:g}", nonce, *cmd]) + "\n")


def split_end(raw: str, nonce: str):
    """(output của lệnh, mã) khi dòng cuối là dòng kết thúc đúng nonce (TM-165); (raw, None) khi không."""
    body = raw.removesuffix("\n")
    head, _, last = body.rpartition("\n")
    match = re.fullmatch(re.escape(END) + r" ([0-9a-f]+) (\d{1,3})", last)
    if not match or not secrets.compare_digest(match.group(1), nonce):
        return raw, None
    head = head.removesuffix("\n")  # dòng trống RUNNER chèn trước dòng kết thúc
    return head + ("\n" if head else ""), int(match.group(2))


def cleanup(host: str, run: str) -> None:
    try:
        ssh(host, f'cd "$HOME" && rm -rf -- {shlex.quote(run)}', CLEANUP_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        pass


def run_remote(root: Path, run_dir: Path, cmd: list, host: str, timeout: float, home_env=None) -> RemoteResult:
    """Chạy `cmd` trên máy `host` trong bản chép của code hiện tại, ở thư mục tương ứng `run_dir`. Raise Refused khi
    từ chối trước khi gọi ssh; lỗi ssh, mạng, quá giờ thì mã khác 0 kèm `error`."""
    start = time.time()
    conf = host_config(host)
    if not (isinstance(cmd, list) and cmd and all(isinstance(x, str) and "\0" not in x for x in cmd)):
        raise Refused("lệnh phải là danh sách chuỗi, không rỗng")
    env_map = {}
    for key, rel in (home_env or {}).items():
        if not (ENV_RE.fullmatch(key) and REL_RE.fullmatch(rel) and ".." not in rel.split("/")):
            raise Refused(f"biến {key!r} cho máy xa không an toàn")
        env_map[key] = rel
    info = ship(root)
    try:
        sub = run_dir.resolve().relative_to(info["top"].resolve()).as_posix()
    except ValueError:
        raise Refused(f"thư mục chạy {run_dir} nằm ngoài repo") from None
    bare = f"{BASE}/repos/{repo_name(info['top'])}.git"
    run = f"{BASE}/runs/{repo_name(info['top'])}-{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"
    result = RemoteResult(code=255, output="", ship=info["ship"], head=info["head"],
                          fingerprint=info["fingerprint"], code_fingerprint=info["code_fingerprint"])
    error = upload(host, info, bare, min(SETUP_TIMEOUT, timeout + MARGIN))
    if error:
        result.error, result.seconds = error, time.time() - start
        return result
    nonce = secrets.token_hex(8)
    script = run_script(info, bare, run, sub, conf["path"], cmd, timeout, nonce, env_map)
    try:
        out = ssh(host, script, timeout + MARGIN)
    except subprocess.TimeoutExpired as exc:
        cleanup(host, run)
        result.code, result.output = 124, text(exc.stdout)
        result.error = f"máy {host} không trả lời sau {timeout + MARGIN:.0f} giây"
        result.seconds = time.time() - start
        return result
    except OSError as exc:
        result.error, result.seconds = f"không chạy được ssh ({exc})", time.time() - start
        return result
    output, code = split_end(text(out.stdout), nonce)
    result.output, result.seconds = output, time.time() - start
    if code is None:
        cleanup(host, run)
        result.error = (f"không có dòng kết thúc hợp lệ từ máy {host} (ssh mã {out.returncode}; mất mạng, lỗi dựng "
                        f"bản chép hay output bị cắt): {text(out.stderr).strip()[-300:]}")
        return result
    result.code = code
    return result
