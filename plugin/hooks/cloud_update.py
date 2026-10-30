#!/usr/bin/env python3
"""Tự kéo bản agent-stack mới trên cloud session (claude.ai/code).

Setup script của environment clone agent-stack một lần rồi máy ảo cache khoảng 7 ngày, nên bản trên cloud cũ
dần. Hook SessionStart gọi `maybe_start`: trên cloud, tối đa một lần mỗi 10 phút, khởi tiến trình nền chạy file
này với `--run` để fetch nhánh mà setup script đã tải rồi `reset --keep` sang commit mới. Hook không chờ;
bản mới có tác dụng từ lần gọi hook sau, skill mới từ phiên sau. Threat model: TM-43 đến TM-46.
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import agentstack as A  # noqa: E402

REPO_URL = "https://github.com/tdHuy22/agent-stack.git"  # khớp REPO_URL của tools/cloud_setup.sh
CORE_FILES = (".agent-stack-root", "plugin/.claude-plugin/plugin.json", "global/CLAUDE.global.md")
INTERVAL = 600  # giây giữa hai lần kiểm; đĩa máy ảo giữ giữa các phiên nên dấu này cũng vậy
LOCK_STALE = 600  # khoá cũ hơn mức này là của tiến trình đã chết
FETCH_TIMEOUT = 60
NO_BACKGROUND_ENV = "AGENT_STACK_NO_BACKGROUND"  # test luôn đặt, để không gọi mạng thật
STATE_NAME = "cloud-update.json"
BRANCH_RE = re.compile(r"\tbranch '([A-Za-z0-9._][A-Za-z0-9._/-]*)' of (\S+)$")
GIT_LOCKS = ("index.lock", "shallow.lock", "HEAD.lock")
BRANCH_KEY = "agent-stack.branch"  # nhánh đã thấy trong FETCH_HEAD, dùng khi fetch lỗi để lại FETCH_HEAD rỗng


def on_cloud(env=None, platform=None) -> bool:
    """Chỉ máy ảo cloud: biến CLAUDE_CODE_REMOTE=true và không phải macOS (bản dev nằm trên Mac)."""
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    return env.get("CLAUDE_CODE_REMOTE") == "true" and platform != "darwin"


def same_repo(a: str, b: str) -> bool:
    """So URL repo, bỏ `/` và `.git` ở cuối: git ghi URL vào FETCH_HEAD không kèm `.git`."""
    def norm(url):
        url = url.strip().rstrip("/")
        return url[:-4] if url.endswith(".git") else url
    return bool(a.strip()) and norm(a) == norm(b)


def _spawn(cmd: list) -> None:
    subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True, close_fds=True)


def maybe_start(home, now: float = None, env=None, platform=None, spawn=None) -> bool:
    """Khởi lần kéo nền nếu đang ở cloud, có bản clone git và lần trước đã quá INTERVAL. Trả về ngay."""
    env = os.environ if env is None else env
    if env.get(NO_BACKGROUND_ENV) or not on_cloud(env, platform):
        return False
    if not home or not (Path(home) / ".git").is_dir():
        return False  # bản tải từng file (proxy chặn clone) không có .git: để setup script lo
    now = time.time() if now is None else now
    path = A.state_dir() / STATE_NAME
    data = A.read_json(path, {}) or {}
    try:
        started = float(data["started_at"])
    except (KeyError, TypeError, ValueError):
        started = None
    if started is not None and 0 <= now - started < INTERVAL:  # mốc ở tương lai (đồng hồ sai) không chặn mãi
        return False
    data["started_at"] = now
    A.write_json_atomic(path, data)
    (spawn or _spawn)([sys.executable, str(Path(__file__).resolve()), "--run", str(home)])
    return True


def _git(home: Path, *args, timeout: float = 10) -> subprocess.CompletedProcess:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    return subprocess.run(["git", "-C", str(home), *args], capture_output=True, text=True, timeout=timeout,
                          env=env)


def tracked_branch(home: Path):
    """Nhánh mà lần tải trước đã fetch, đọc từ FETCH_HEAD; None nếu ghim SHA hay tag, hoặc từ repo khác.
    `git fetch` xoá trắng FETCH_HEAD ngay khi bắt đầu, nên fetch lỗi để lại file rỗng: khi đó dùng nhánh đã nhớ
    trong config `agent-stack.branch`, không thì một lần lỗi mạng sẽ tắt tự cập nhật tới khi dựng lại cache."""
    try:
        first = (home / ".git" / "FETCH_HEAD").read_text(encoding="utf-8").splitlines()[0]
    except (OSError, IndexError):
        saved = _git(home, "config", "--get", BRANCH_KEY).stdout.strip()
        return saved if BRANCH_RE.search(f"\tbranch '{saved}' of {REPO_URL}") else None
    match = BRANCH_RE.search(first)
    if not match or not same_repo(match.group(2), REPO_URL):
        return None
    _git(home, "config", BRANCH_KEY, match.group(1))
    return match.group(1)


def is_cloud_clone(home: Path) -> bool:
    """Bản do setup script tạo: clone nông (.git/shallow) và HEAD tách khỏi nhánh. Bản dev trên Mac có nhánh
    `main` gắn với HEAD và commit chưa push: `reset` ở đó làm rơi commit khỏi `main` (TM-44)."""
    if not (home / ".git" / "shallow").is_file():
        return False
    return _git(home, "symbolic-ref", "-q", "HEAD").returncode != 0


def clear_stale_git_locks(home: Path, now: float = None) -> None:
    """Khoá git do lần chạy trước bị giết vì quá giờ để lại; không gỡ thì mọi lần sau đều lỗi."""
    now = time.time() if now is None else now
    for name in GIT_LOCKS:
        path = home / ".git" / name
        try:
            if now - path.stat().st_mtime >= LOCK_STALE:
                path.unlink()
        except OSError:
            pass


def has_core(home: Path) -> bool:
    return all((home / name).is_file() for name in CORE_FILES)


def update(home: Path) -> str:
    """Kéo bản mới cho bản clone ở `home`. Trả về một từ mô tả kết quả, ghi vào state."""
    origin = _git(home, "remote", "get-url", "origin")
    if origin.returncode != 0 or not same_repo(origin.stdout, REPO_URL):
        return "origin-khac"
    if not is_cloud_clone(home):
        return "khong-phai-ban-cloud"
    branch = tracked_branch(home)
    if not branch:
        return "ghim"
    clear_stale_git_locks(home)
    status = _git(home, "status", "--porcelain", "--untracked-files=no")
    if status.returncode != 0 or status.stdout.strip():
        return "co-sua"
    before = _git(home, "rev-parse", "HEAD").stdout.strip()
    fetch = _git(home, "fetch", "--quiet", "--depth", "1", "origin", branch, timeout=FETCH_TIMEOUT)
    if fetch.returncode != 0:
        return "fetch-loi"
    after = _git(home, "rev-parse", "FETCH_HEAD").stdout.strip()
    if not after or after == before:
        return "da-moi-nhat"
    for name in CORE_FILES:
        if _git(home, "cat-file", "-e", f"FETCH_HEAD:{name}").returncode != 0:
            return "thieu-file"
    if _git(home, "reset", "--quiet", "--keep", "FETCH_HEAD", timeout=FETCH_TIMEOUT).returncode != 0:
        return "reset-loi"
    if not has_core(home):  # reset dở dang: quay về bản cũ
        _git(home, "reset", "--quiet", "--keep", before, timeout=FETCH_TIMEOUT)
        return "reset-do"
    return "da-cap-nhat"


def _acquire(lock: Path) -> bool:
    for _ in range(2):
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
            return True
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime < LOCK_STALE:
                    return False
                lock.unlink()
            except OSError:
                return False
    return False


def run(home: Path) -> str:
    lock = A.state_dir() / "cloud-update.lock"
    if not _acquire(lock):
        return "dang-chay"
    try:
        try:
            result = update(home)
        except (OSError, subprocess.SubprocessError):
            result = "loi"
        path = A.state_dir() / STATE_NAME
        data = A.read_json(path, {}) or {}
        data.update({"checked_at": time.time(), "result": result,
                     "head": _git(home, "rev-parse", "--short", "HEAD").stdout.strip()})
        A.write_json_atomic(path, data)
        return result
    finally:
        try:
            lock.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--run" and on_cloud():
        try:
            run(Path(sys.argv[2]))
        except Exception:  # tiến trình nền: không có ai đọc lỗi, không được để lại khoá
            pass
    sys.exit(0)
