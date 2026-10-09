"""Máy quét thứ hai cho vet-skill: SkillSpector (NVIDIA/SkillSpector, Apache-2.0), dùng theo điều kiện đã duyệt.

Điều kiện (vetted.lock, người dùng duyệt 09/10/2026):
- venv riêng `.venv-skillspector` chạy Python 3.12 (yara-python chưa có bản dựng sẵn cho 3.11 trên máy này), cài từ
  đúng bản đã kiểm trong .vet-cache bằng `uv sync --frozen --no-dev` (uv.lock có hash); không extra `mcp`, contrib;
- luôn `--no-llm`; môi trường tối giản: không khóa API, không biến LangSmith hay LangChain;
- đích cục bộ (có thể là mã riêng tư) thì chặn mạng: phần kiểm OSV gửi tên và phiên bản gói tới api.osv.dev;
- kết quả chỉ đẩy lên REVIEW, không tự kết luận FAIL, cho tới khi đo được trên bộ mẫu của mình.

  vet.py spector --setup     # cài .venv-skillspector (cần mạng một lần)
  vet.py spector             # xem đã sẵn sàng chưa
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

LOCK_KEY = "NVIDIA/SkillSpector"
VENV = ".venv-skillspector"
PYTHON = "3.12"
TIMEOUT_S = 900
MAX_TARGETS = 40
SEVERITIES = ("critical", "high", "medium", "low", "info")
STD_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
BLOCKED_PROXY = "http://127.0.0.1:9"  # cổng discard: mọi kết nối qua proxy đều hỏng ngay
# Biến mạng mà uv cần để tải gói qua mạng của người dùng; mọi biến khác (khóa API, token) không đưa cho uv.
NETWORK_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy",
                "no_proxy", "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE")
FIELD_MAX = 120


def clean(value, limit: int = FIELD_MAX) -> str:
    """Chữ lấy từ kết quả quét là dữ liệu của đích (không tin cậy): một dòng, không ký tự điều khiển, vô hình hay
    đảo chiều, không backtick, cắt ngắn. Nếu không, đích có thể chèn tiêu đề hay mục giả vào báo cáo mà agent đọc."""
    text = "" if value is None else str(value)
    text = "".join(" " if unicodedata.category(ch) in ("Cc", "Zl", "Zp") else ch for ch in text
                   if unicodedata.category(ch) != "Cf")
    text = re.sub(r"\s+", " ", text.replace("`", "'")).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def lock_entry(home: Path) -> dict:
    try:
        data = json.loads((home / "vetted.lock").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    entry = (data.get("entries") or {}).get(LOCK_KEY)
    return entry if isinstance(entry, dict) else {}


def source_dir(home: Path, entry: dict) -> Path:
    return home / ".vet-cache" / Path(entry.get("report", "x.md")).stem


def binary(home: Path) -> Path:
    return home / VENV / "bin" / "skillspector"


def status(home: Path):
    """(sẵn sàng?, lý do). Chỉ chạy bản đã cài từ đúng commit đang được duyệt."""
    entry = lock_entry(home)
    if (entry.get("human_review") or {}).get("status") != "approved":
        return False, "SkillSpector chưa được duyệt trong vetted.lock"
    if not binary(home).exists():
        return False, "chưa cài: chạy `vet.py spector --setup`"
    try:
        installed = (home / VENV / ".vetted-sha").read_text(encoding="utf-8").strip()
    except OSError:
        installed = ""
    if installed != entry.get("sha"):
        return False, (f"bản đã cài ({installed[:12] or '?'}) khác commit đã duyệt ({str(entry.get('sha'))[:12]}): "
                       "chạy lại `vet.py spector --setup`")
    return True, "sẵn sàng"


def setup(home: Path, run=subprocess.run) -> str:
    """Cài .venv-skillspector từ đúng bản đã kiểm. Trả về thông báo; lỗi thì ném ValueError."""
    entry = lock_entry(home)
    if (entry.get("human_review") or {}).get("status") != "approved":
        raise ValueError("SkillSpector chưa được duyệt trong vetted.lock; không cài.")
    src, sha = source_dir(home, entry), entry.get("sha", "")
    head = run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(src), "rev-parse", "HEAD"],
               capture_output=True, text=True)
    dirty = run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(src), "status", "--porcelain",
                 "--untracked-files=all", "--ignored"], capture_output=True, text=True)
    extra = [x for x in (dirty.stdout or "").splitlines() if x.strip() and x[3:] != ".vet-complete"]
    if head.returncode != 0 or head.stdout.strip() != sha or dirty.returncode != 0 or extra:
        raise ValueError(f"{src.name} không phải checkout sạch ở commit đã duyệt {sha[:12]}; chạy lại vet.py scan.")
    venv = home / VENV
    (venv / ".vetted-sha").unlink(missing_ok=True)  # cài dở rồi lỗi thì không để dấu cũ báo "sẵn sàng"
    uv = shutil.which("uv") or "uv"
    # Môi trường tối giản cho uv: lúc build, công cụ build (hatchling, không có trong uv.lock) chạy với môi trường
    # này, nên không đưa khóa API hay token nào.
    env = {k: os.environ[k] for k in NETWORK_VARS if k in os.environ}
    env.update(PATH=f"{Path(uv).parent}:{STD_PATH}", HOME=str(Path.home()), LANG="C.UTF-8",
               UV_CACHE_DIR=str(home / ".cache" / "uv"), UV_PYTHON_INSTALL_DIR=str(home / ".cache" / "uv-python"),
               UV_PROJECT_ENVIRONMENT=str(venv), UV_PYTHON_PREFERENCE="only-managed")
    for cmd in ([uv, "python", "install", PYTHON],
                # --frozen: đúng uv.lock (có hash); --no-dev: không gói dev; --no-editable: chép mã vào venv để
                # venv không chạy mã từ .vet-cache (cache bị sửa về sau không ảnh hưởng); không extra nào.
                [uv, "sync", "--frozen", "--no-dev", "--no-editable", "--python", PYTHON, "--project", str(src)]):
        done = run(cmd, capture_output=True, text=True, env=env, timeout=1800)
        if done.returncode != 0:
            raise ValueError(f"`{' '.join(cmd[:3])}` lỗi ({done.returncode}): {(done.stderr or done.stdout)[-400:]}")
    after = run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(src), "status", "--porcelain",
                 "--untracked-files=all", "--ignored"], capture_output=True, text=True)
    left = [x[3:] for x in (after.stdout or "").splitlines() if x.strip() and x[3:] != ".vet-complete"]
    if left:
        raise ValueError(f"uv đã ghi vào bản đã kiểm ({', '.join(left[:3])}); xóa các file đó trước khi dùng.")
    (venv / ".vetted-sha").write_text(sha + "\n", encoding="utf-8")
    return f"Đã cài SkillSpector @ {sha[:12]} vào {VENV} (Python {PYTHON})."


def scan_env(home: Path, local: bool) -> dict:
    """Môi trường tối giản, dựng từ đầu: không mang theo biến nào của người dùng (khóa API, LangSmith, proxy...)."""
    tmp = home / ".tmp" / "skillspector"
    (tmp / "home").mkdir(parents=True, exist_ok=True)
    # HOME giả và cwd trong thư mục tạm: không đọc cấu hình hay file .env nào của người dùng.
    env = {"PATH": f"{home / VENV / 'bin'}:{STD_PATH}", "HOME": str(tmp / "home"), "LANG": "C.UTF-8",
           "TMPDIR": str(tmp), "PYTHONDONTWRITEBYTECODE": "1", "NO_COLOR": "1",
           "LANGCHAIN_TRACING_V2": "false", "LANGSMITH_TRACING": "false"}
    if local:
        env.update(HTTP_PROXY=BLOCKED_PROXY, HTTPS_PROXY=BLOCKED_PROXY, ALL_PROXY=BLOCKED_PROXY,
                   http_proxy=BLOCKED_PROXY, https_proxy=BLOCKED_PROXY, all_proxy=BLOCKED_PROXY, NO_PROXY="")
    return env


def targets(root: Path, skills: list) -> list:
    """Mỗi skill một lần quét (--recursive của SkillSpector chỉ xét một cấp); không có SKILL.md thì quét cả gốc."""
    dirs = []
    for s in skills:
        path = (root / (s.get("path") or "")).resolve()
        if path not in dirs:
            dirs.append(path)
    return (dirs or [root.resolve()])[:MAX_TARGETS]


def run(home: Path, root: Path, skills: list, local: bool, runner=subprocess.run) -> dict:
    """Chạy SkillSpector, trả {status, version, counts, findings, score}. Không bao giờ ném lỗi."""
    ready, why = status(home)
    if not ready:
        return {"status": why}
    exe, env = str(binary(home)), scan_env(home, local)
    counts = {s: 0 for s in SEVERITIES}
    findings, scores, errors = [], [], []
    for target in targets(root, skills):
        try:
            done = runner([exe, "scan", str(target), "--no-llm", "--format", "json"], capture_output=True, text=True,
                          env=env, cwd=str(env["TMPDIR"]), timeout=TIMEOUT_S)
            data = json.loads(done.stdout)
        except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
            errors.append(f"{target.name}: {exc.__class__.__name__}")
            continue
        if done.returncode not in (0, 1) or not isinstance(data, dict):
            errors.append(f"{target.name}: mã {done.returncode}")
            continue
        scores.append((data.get("risk_assessment") or {}).get("score") or 0)
        for issue in data.get("issues") or []:
            sev = clean(issue.get("severity", "info"), 12).lower()
            counts[sev] = counts.get(sev, 0) + 1
            loc = issue.get("location") or {}
            file_abs = target / (loc.get("file") or "")
            try:
                rel = str(file_abs.resolve().relative_to(root.resolve()))
            except ValueError:
                rel = loc.get("file") or ""
            line = loc.get("start_line")
            findings.append({"severity": sev, "rule": clean(issue.get("id"), 40),
                             "title": clean(issue.get("finding") or issue.get("pattern") or issue.get("category")),
                             "category": clean(issue.get("category"), 40), "file": clean(rel, 200),
                             "line": line if isinstance(line, int) else None, "confidence": issue.get("confidence")})
    if not scores and errors:
        return {"status": "lỗi: " + "; ".join(errors[:3])}
    order = {s: i for i, s in enumerate(SEVERITIES)}
    findings.sort(key=lambda x: order.get(x["severity"], 9))
    try:
        version = runner([exe, "--version"], capture_output=True, text=True, env=env, timeout=60).stdout.strip().split()
    except (subprocess.TimeoutExpired, OSError):
        version = []
    return {"status": "ok", "version": clean(version[-1].lstrip("v"), 20) if version else "?", "counts": counts,
            "findings": findings[:200], "score": max(scores) if scores else 0, "errors": errors,
            "network": "chặn (đích cục bộ)" if local else "chỉ OSV"}


def main_cli(args, home: Path) -> int:
    if args.setup:
        try:
            print(setup(home))
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            print(f"Không cài được: {exc}")
            return 3
        return 0
    ready, why = status(home)
    print(f"SkillSpector: {why}")
    return 0 if ready else 3
