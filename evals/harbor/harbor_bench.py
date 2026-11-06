#!/usr/bin/env python3
"""Bench Claude Code có và không có agent-stack trên Harbor (xem README.md cùng thư mục).

Bốn cấu hình (cùng model, effort, phiên bản Claude Code): plain, agent-stack, agent-stack-nohooks, agent-stack-noagents.
Hai bộ việc: TBLite (openthoughts/openthoughts-tblite) và SWE-rebench (swe-rebench/swe-rebench-leaderboard).

Lệnh (chạy trên Mac hay trên TUF; chỉ dùng thư viện chuẩn, trừ validate-config cần harbor):
  build-payload SRC DST --commit SHA   dựng ba bản chép agent-stack (full, nohooks, noagents) từ danh sách cho phép
  datasets                              in khóa, tên và ref của hai bộ việc
  flatten SRC --out DIR                 gom thư mục việc (có task.toml) ở bất kỳ độ sâu nào thành DIR/<tên việc>
  lock DIR --name KEY --lock FILE       ghi hay đối chiếu mã băm nội dung bộ việc (ghim bản)
  vet DIR [--drop]                      kiểm từng việc (container đặc quyền, mạng host, gắn thư mục ngoài…); --drop loại việc vi phạm
  vet-config CONFIG --root DIR          kiểm đúng các việc mà cấu hình job sẽ chạy
  status JOB_DIR                        số lượt đã xong và số lỗi hạn mức
  pick-swerebench DIR [--n 25]          chọn việc SWE-rebench của tháng mới nhất (hạt cố định), in ra danh sách
  make-configs --kind pilot|main|oracle  sinh cấu hình job (JSON, Harbor đọc qua -c)
  plan CONFIG                           in số lượt và trần chi phí (tuf.sh chỉ chạy khi có --yes)
  meta CONFIG --out FILE --payload DIR  ghi phiên bản đã ghim (Harbor, Claude Code, commit bản chép, mã băm bộ việc)
  validate-config CONFIG                kiểm cấu hình bằng chính mô hình của Harbor (cần harbor)
  watch JOB_DIR --pid PID               dừng job khi số lượt lỗi hạn mức hay rate limit vượt ngưỡng
  export JOB_DIR... --out DIR [--env-file F]  chép kết quả cần thiết, che mọi chuỗi sk-ant-… (và khóa thật trong .env,
                                        cả dạng base64) trong MỌI file kéo về, rồi quét lại
  residual DIR... [--env-file F]        quét lại thư mục đã kéo về với đúng mẫu của export (mọi file, kể cả nhị phân)
  scrub                                 stdin -> stdout: che khóa, bỏ ký tự điều khiển (dùng cho đoạn log in ra terminal)
  select DATASETS_DIR --swerebench FILE sinh tasks-main.txt từ nhãn độ khó công bố của TBLite + cả danh sách SWE-rebench
  pilot-report JOB_DIR                  tỉ lệ đạt và chi phí của pilot theo nhãn độ khó (chỉ gợi ý, không chọn gì)
  compare JOB_DIR... [--oracle JOB_DIR] so ghép cặp bốn cấu hình
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import random
import re
import shutil
import signal
import statistics
import subprocess
import sys
import time
from pathlib import Path

PLAIN = "claude-code-plain"
STACK = "claude-code-agent-stack"
NOHOOKS = "claude-code-agent-stack-nohooks"
NOAGENTS = "claude-code-agent-stack-noagents"
ARMS = (PLAIN, STACK, NOHOOKS, NOAGENTS)
SHORT = {PLAIN: "plain", STACK: "stack", NOHOOKS: "nohooks", NOAGENTS: "noagents"}
CLASS_OF = {PLAIN: "ClaudeCodePlain", STACK: "ClaudeCodeAgentStack", NOHOOKS: "ClaudeCodeAgentStackNoHooks",
            NOAGENTS: "ClaudeCodeAgentStackNoAgents"}
VARIANT_OF = {STACK: "full", NOHOOKS: "nohooks", NOAGENTS: "noagents"}
HOOK_ARMS = (STACK, NOAGENTS)           # bản mà hook phải chạy (cần python3)
PLUGIN_ARMS = (STACK, NOHOOKS, NOAGENTS)  # bản mà plugin phải được nạp
SUBAGENT_ARMS = (STACK, NOHOOKS)        # bản mà subagent riêng của agent-stack phải hiện ra
# Các cặp so sánh: ba bản so với bản trơn, và hai phép bớt (bỏ hook, bỏ subagent) so với bản đủ.
PAIRS = ((PLAIN, STACK), (PLAIN, NOHOOKS), (PLAIN, NOAGENTS), (NOHOOKS, STACK), (NOAGENTS, STACK))
STACK_AGENTS = ("reviewer", "researcher", "test-runner", "explore-lite", "cold-reader")  # plugin/agents/*.md

MODULE = "agent_stack_agents"
HARBOR_VERSION = "0.25.0"   # ghim (TM-75); tuf.sh cài đúng bản này và kiểm sha256 của wheel
HARBOR_WHEEL_SHA256 = "51923ac567fc57b03279e93468b105f689628bcac2cd3d541d4e44aa5c0ec309"
MIN_PYTHON = (3, 9)         # hook của agent-stack chạy được từ 3.9 (đã kiểm 3.9 và 3.11, xem README)
SEED = 20261106
DEFAULTS = {
    "model": "anthropic/claude-sonnet-5-5",
    "effort": "medium",
    "version": "2.1.311",       # Claude Code đang chạy trên Mac lúc dựng (claude --version, 06/11/2026); mọi bản dùng chung
    "max_budget_usd": "1",      # trần mỗi lượt (TM-77)
    "concurrent": 3,            # TUF có 15 GB RAM
}
# Bộ việc. `ref` có thể đổi bằng biến môi trường TBLITE_REF, SWEREBENCH_REF khi chạy `datasets`.
DATASETS = {
    "tblite": {"name": "openthoughts/openthoughts-tblite", "ref": "latest", "env": "TBLITE_REF"},
    "swerebench": {"name": "swe-rebench/swe-rebench-leaderboard",
                   "ref": "sha256:ebe7444e313a0d8db94fa541139826eaebe2b0abcd4900c6f73e750494910dca",
                   "env": "SWEREBENCH_REF"},
}
# TM-76: chỉ những mục này vào container.
PAYLOAD_ALLOW = (".agent-stack-root", "plugin", "global", "routing-table.md", "vetted.lock")
PAYLOAD_VARIANTS = ("full", "nohooks", "noagents")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@+-]*$")


# ---------------------------------------------------------------- bản chép agent-stack (TM-76)

def _skip_junk(_dir, names):
    return [n for n in names if n in ("__pycache__", ".DS_Store") or n.endswith(".pyc")]


def verify_payload(root: Path) -> list:
    """Danh sách lỗi của một bản chép: thừa mục ngoài danh sách cho phép, hay có file nghi chứa nội dung riêng."""
    problems = []
    for item in sorted(root.iterdir()):
        if item.name not in PAYLOAD_ALLOW and item.name != ".payload-commit":
            problems.append(f"mục thừa ở gốc: {item.name}")
    for p in root.rglob("*"):
        rel = p.relative_to(root).as_posix()
        if p.is_symlink():
            problems.append(f"symlink: {rel}")
        if p.name.startswith(".env"):
            problems.append(f"file môi trường: {rel}")
        if p.is_dir() and p.name in (".agent", "state", ".git", "backups", ".tmp"):
            problems.append(f"thư mục riêng: {rel}")
        if p.is_file() and p.name in ("PLAN.md", "LAST-TURN.md", "threat-model.md", "NHAT-KY.md"):
            problems.append(f"file kế hoạch hay trạng thái: {rel}")
    return problems


def build_payload(src: Path, dst: Path, commit: str) -> list:
    """Dựng dst/{full,nohooks,noagents} từ src, chỉ chép các mục trong PAYLOAD_ALLOW. Trả về danh sách lỗi (rỗng là đạt).
    nohooks bỏ plugin/hooks/hooks.json (plugin.json không trỏ hook nào, nên Claude Code chỉ tìm hook ở file này);
    noagents bỏ plugin/agents/."""
    if not (src / ".agent-stack-root").exists():
        raise SystemExit(f"{src} không phải bản chép agent-stack (thiếu .agent-stack-root)")
    if dst.exists():
        shutil.rmtree(dst)
    for variant in PAYLOAD_VARIANTS:
        out = dst / variant
        out.mkdir(parents=True)
        for name in PAYLOAD_ALLOW:
            s = src / name
            if s.is_dir():
                shutil.copytree(s, out / name, symlinks=True, ignore=_skip_junk)
            elif s.is_file():
                shutil.copy2(s, out / name)
        if variant == "nohooks":
            (out / "plugin" / "hooks" / "hooks.json").unlink(missing_ok=True)
        if variant == "noagents":
            shutil.rmtree(out / "plugin" / "agents", ignore_errors=True)
        (out / ".payload-commit").write_text(commit + "\n", encoding="utf-8")
    problems = []
    for variant in PAYLOAD_VARIANTS:
        problems += [f"{variant}: {p}" for p in verify_payload(dst / variant)]
    return problems


def cmd_build_payload(args) -> int:
    problems = build_payload(Path(args.src), Path(args.dst), args.commit)
    for p in problems:
        print("✗", p, file=sys.stderr)
    if problems:
        shutil.rmtree(args.dst, ignore_errors=True)
        return 1
    print(f"Đã dựng {', '.join(PAYLOAD_VARIANTS)} từ commit {args.commit} vào {args.dst}")
    return 0


# ---------------------------------------------------------------- bộ việc

def dataset_info() -> dict:
    out = {}
    for key, d in DATASETS.items():
        ref = os.environ.get(d["env"], "").strip() or d["ref"]
        out[key] = {"name": d["name"], "ref": ref}
    return out


def cmd_datasets(_args) -> int:
    for key, d in dataset_info().items():
        print(f"{key}\t{d['name']}\t{d['ref']}")
    return 0


def find_task_dirs(root: Path) -> list:
    """Thư mục việc: có task.toml, không nằm trong một thư mục việc khác. Cấu trúc xuất của `harbor download` có thể
    là <org>/<tên>/<việc> hay <việc>; tìm ở mọi độ sâu."""
    found = []
    for toml in sorted(root.rglob("task.toml")):
        d = toml.parent
        if any(f == d or f in d.parents for f in found):
            continue
        found.append(d)
    return found


def list_tasks(dataset_dir: Path) -> list:
    """Tên các việc nằm ngay dưới dataset_dir (đã gom phẳng)."""
    return sorted(p.name for p in dataset_dir.iterdir() if p.is_dir() and (p / "task.toml").is_file())


def cmd_flatten(args) -> int:
    src, out = Path(args.src), Path(args.out)
    dirs = find_task_dirs(src)
    if not dirs:
        print(f"Không thấy việc nào (thư mục có task.toml) dưới {src}", file=sys.stderr)
        return 1
    names = [d.name for d in dirs]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        print("Tên việc trùng: " + ", ".join(dup), file=sys.stderr)
        return 1
    bad = [n for n in names if not NAME_RE.match(n)]
    if bad:
        print("Tên việc có ký tự lạ: " + ", ".join(bad), file=sys.stderr)
        return 1
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for d in dirs:
        shutil.copytree(d, out / d.name, symlinks=True)
    print(f"Đã gom {len(dirs)} việc vào {out}")
    return 0


def dataset_hash(root: Path) -> str:
    """Mã băm nội dung (đường dẫn tương đối và byte của mọi file; symlink ghi theo đích)."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix().encode()
        if p.is_symlink():
            h.update(b"L" + rel + b"\0" + os.readlink(p).encode() + b"\0")
        elif p.is_file():
            h.update(b"F" + rel + b"\0" + hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()


def cmd_lock(args) -> int:
    root, lock = Path(args.dir), Path(args.lock)
    digest = dataset_hash(root)
    entry = {"name": args.name, "ref": args.ref, "tasks": len(list_tasks(root)), "sha256": digest}
    if lock.exists():
        old = json.loads(lock.read_text(encoding="utf-8"))
        if old.get("sha256") != digest:
            print(f"✗ Nội dung bộ việc {args.name} khác bản đã ghim ({old.get('sha256', '?')[:12]} → {digest[:12]}). "
                  f"Xóa {lock} nếu chủ ý đổi bản (và chạy lại pilot).", file=sys.stderr)
            return 1
        print(f"✓ {args.name}: khớp bản đã ghim {digest[:12]} ({entry['tasks']} việc)")
        return 0
    lock.write_text(json.dumps(entry, indent=2) + "\n", encoding="utf-8")
    print(f"Đã ghim {args.name}: {entry['tasks']} việc, sha256 {digest[:12]}")
    return 0


# ---------------------------------------------------------------- kiểm việc trước khi chạy (TM-74)

SOCK_RE = re.compile(r"docker\.sock|containerd\.sock|/run/podman", re.I)
INSECURE_BUILD_RE = re.compile(r"--security\s*=\s*insecure|--network\s*=\s*host", re.I)
# File compose: Harbor chạy `docker compose` với --project-directory <việc>/environment, nên mọi đường dẫn tương đối trong
# compose (env_file, secrets, configs, build.context, volumes…) đi được tới file của máy chủ (~/harbor-eval/.env, ~/.ssh/…), và
# YAML có quá nhiều cách viết cùng một việc (flow style, khóa có nháy, include, extends, driver_opts…) để lọc bằng mẫu chữ.
# Nên mặc định từ chối mọi việc có file compose; việc nào bạn đã đọc tay thì ghi vào compose-allow.txt kèm sha256 của file.
COMPOSE_NAME_RE = re.compile(r"compose", re.I)
YAML_SUFFIXES = (".yml", ".yaml")
COMPOSE_PROBLEM = "compose chưa duyệt"
ALLOW_FILE = Path(__file__).resolve().with_name("compose-allow.txt")


def load_allow(path=None) -> dict:
    """{tên việc: {sha256 đã duyệt}} từ compose-allow.txt (mỗi dòng `<tên việc> <sha256 nội dung file compose>`)."""
    path = Path(path) if path else ALLOW_FILE
    allow = {}
    if not path.is_file():
        return allow
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.split("#", 1)[0].strip()
        if not ln:
            continue
        parts = ln.split()
        if len(parts) != 2 or not NAME_RE.match(parts[0]) or not re.fullmatch(r"[0-9a-f]{64}", parts[1]):
            raise SystemExit(f"{path}: dòng không hợp lệ (cần `<tên việc> <sha256 hex 64 ký tự>`): {ln[:80]!r}")
        allow.setdefault(parts[0], set()).add(parts[1])
    return allow


def compose_like_files(task_dir: Path) -> list:
    """File compose trong thư mục việc: tên có 'compose' và đuôi yaml/yml ở bất kỳ đâu, hay mọi file yaml/yml trong environment/."""
    env_dir = task_dir / "environment"
    found = []
    for p in sorted(task_dir.rglob("*")):
        if p.is_symlink() or not p.is_file() or p.suffix.lower() not in YAML_SUFFIXES:
            continue
        in_env = env_dir in p.parents
        if in_env or COMPOSE_NAME_RE.search(p.name):
            found.append(p)
    return found


def _toml_findings(data, path="") -> list:
    """Khóa nguy hiểm và mẫu `${…}` (đọc biến môi trường máy chủ, như khóa đăng nhập) trong task.toml."""
    out = []
    if isinstance(data, dict):
        for k, v in data.items():
            here = f"{path}.{k}" if path else str(k)
            if k in ("privileged", "cap_add", "devices", "mounts", "volumes", "network_mode", "pid", "ipc", "docker_socket") and v:
                out.append(f"task.toml khai {here}")
            out += _toml_findings(v, here)
    elif isinstance(data, list):
        for i, v in enumerate(data):
            out += _toml_findings(v, f"{path}[{i}]")
    elif isinstance(data, str):
        if "${" in data and (re.search(r"(^|\.)(env|headers)(\.|\[|$)", path)):
            out.append(f"task.toml đọc biến của máy chủ ({path} = {data[:40]})")
        if SOCK_RE.search(data):
            out.append(f"task.toml nhắc socket của Docker ({path})")
    return out


def vet_task(task_dir: Path, allow: dict = None) -> list:
    """Danh sách lý do từ chối một việc (rỗng là sạch): file compose chưa duyệt, Dockerfile, task.toml, symlink ra ngoài."""
    allow = load_allow() if allow is None else allow
    problems = []
    env_dir = task_dir / "environment"
    for f in compose_like_files(task_dir):
        digest = hashlib.sha256(f.read_bytes()).hexdigest()
        if digest not in allow.get(task_dir.name, set()):
            problems.append(f"{COMPOSE_PROBLEM}: {f.relative_to(task_dir)} sha256 {digest}")
    if env_dir.is_dir():
        for f in sorted(env_dir.rglob("*")):
            if f.is_file() and not f.is_symlink() and f.stat().st_size < 1_000_000:
                text = f.read_text(encoding="utf-8", errors="replace")
                if SOCK_RE.search(text):
                    problems.append(f"{f.relative_to(task_dir)}: nhắc socket của Docker")
                if f.name.lower().startswith("dockerfile") and INSECURE_BUILD_RE.search(text):
                    problems.append(f"{f.relative_to(task_dir)}: build không an toàn (--security=insecure hay --network=host)")
    # Harbor nạp environment/docker-compose.yaml qua .exists() (theo symlink): symlink trong environment/ có thể trỏ tới
    # một compose trá hình nằm trong việc (tên, đuôi bất kỳ) mà vòng băm ở trên bỏ qua. Từ chối mọi symlink ở đó.
    if env_dir.is_symlink():
        problems.append("environment: là symlink")
    elif env_dir.is_dir():
        for p in sorted(env_dir.rglob("*")):
            if p.is_symlink():
                problems.append(f"{p.relative_to(task_dir)}: symlink trong environment/ ({os.readlink(p)})")
    for p in sorted(task_dir.rglob("*")):
        if p.is_symlink():
            target = os.readlink(p)
            resolved = (p.parent / target).resolve()
            if os.path.isabs(target) or not (resolved == task_dir.resolve() or task_dir.resolve() in resolved.parents):
                problems.append(f"{p.relative_to(task_dir)}: symlink trỏ ra ngoài thư mục việc ({target})")
    toml = task_dir / "task.toml"
    if toml.is_file():
        try:
            import tomllib
            problems += _toml_findings(tomllib.loads(toml.read_text(encoding="utf-8")))
        except Exception as exc:   # task.toml hỏng (kể cả lồng quá sâu) thì Harbor cũng không chạy được; không coi là sạch
            problems.append(f"task.toml không đọc được: {type(exc).__name__}")
    else:
        problems.append("thiếu task.toml")
    return problems


def vet_names(root: Path, names, allow: dict = None) -> dict:
    """{tên việc: [lý do]} cho các việc vi phạm; names=None là cả bộ."""
    allow = load_allow() if allow is None else allow
    all_names = list_tasks(root)
    if names:
        missing = [n for n in names if n not in all_names]
        if missing:
            raise SystemExit("✗ Thiếu trong bộ việc: " + ", ".join(missing[:10]))
        all_names = list(names)
    return {n: p for n in all_names if (p := vet_task(root / n, allow))}


def compose_rejects(bad: dict) -> list:
    return sorted(n for n, probs in bad.items() if any(p.startswith(COMPOSE_PROBLEM) for p in probs))


def print_compose_summary(bad: dict, total: int) -> None:
    names = compose_rejects(bad)
    if names:
        print(f"{len(names)}/{total} việc bị loại vì có file compose chưa duyệt: {', '.join(names[:40])}"
              + (f" … (+{len(names) - 40})" if len(names) > 40 else "")
              + ". Đọc file compose rồi thêm `<tên việc> <sha256>` vào compose-allow.txt nếu muốn giữ.", file=sys.stderr)


def cmd_vet(args) -> int:
    root = Path(args.dir)
    total = len(list_tasks(root))
    bad = vet_names(root, None, load_allow(args.allow))
    for n, probs in bad.items():
        print(f"✗ {n}: " + "; ".join(probs), file=sys.stderr)
    print_compose_summary(bad, total)
    if bad and args.drop:
        rej = root.parent / (root.name + ".rejected.txt")
        rej.write_text("".join(f"{n}\t{'; '.join(p)}\n" for n, p in bad.items()), encoding="utf-8")
        for n in bad:
            shutil.rmtree(root / n)
        print(f"Đã loại {len(bad)}/{total} việc vi phạm, trong đó {len(compose_rejects(bad))} vì compose "
              f"(danh sách ở {rej}); còn {total - len(bad)}")
        return 0
    if bad:
        print(f"{len(bad)}/{total} việc bị từ chối", file=sys.stderr)
        return 1
    print(f"✓ {total} việc sạch")
    return 0


def cmd_vet_config(args) -> int:
    """Kiểm đúng các việc mà cấu hình job sẽ chạy (TM-74), ngay trước khi chạy."""
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    allow = load_allow(args.allow)
    code, checked = 0, 0
    for d in cfg.get("datasets", []):
        root = Path(args.root) / d["path"]
        bad = vet_names(root, d.get("task_names"), allow)
        checked += len(d.get("task_names") or list_tasks(root))
        for n, probs in bad.items():
            print(f"✗ {d['path']}/{n}: " + "; ".join(probs), file=sys.stderr)
            code = 1
        print_compose_summary(bad, len(d.get("task_names") or list_tasks(root)))
    if not code:
        print(f"✓ {checked} việc sạch")
    return code


def cmd_status(args) -> int:
    job = Path(args.job)
    done = len(list(job.glob("*/result.json")))
    print(f"{done} lượt đã có kết quả; lỗi hạn mức/rate limit: {count_limit_errors(job)} (ngưỡng dừng 3)")
    states = {}
    for label, suffix in (("harbor", ".pid"), ("watcher", ".watch.pid")):
        f = Path(str(job) + suffix)
        try:
            pid = int(f.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            print(f"{label}: không thấy {f.name}")
            states[label] = None
            continue
        states[label] = pid_alive(pid)
        print(f"{label}: PID {pid} {'đang chạy' if states[label] else 'ĐÃ DỪNG'}")
    if states.get("harbor") and states.get("watcher") is False:
        print("⚠️ watcher đã dừng: lỗi hạn mức sẽ không tự dừng job. Dừng job (tuf.sh stop) hoặc chạy lại watch.")
    marker = Path(str(job) + ".stopped")
    if marker.is_file():
        print(marker.read_text(encoding="utf-8").strip())
    return 0


# ---------------------------------------------------------------- danh sách việc và cấu hình job

def read_task_spec(path: Path, default_ds=None) -> dict:
    """{khóa bộ việc: [tên việc…]}. Mỗi dòng `bộ:tên` hay chỉ `tên` (khi có default_ds); `*` là cả bộ. Bỏ dòng trống và #."""
    spec = {}
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.split("#", 1)[0].strip()
        if not ln:
            continue
        ds, _, name = ln.rpartition(":")
        ds = ds or default_ds
        if ds is None:
            raise SystemExit(f"{path}: dòng '{ln}' thiếu tên bộ việc (dạng bộ:tên)")
        if name != "*" and not NAME_RE.match(name):
            raise SystemExit(f"{path}: tên việc không hợp lệ: {name!r}")
        if ds not in DATASETS and ds != default_ds:
            raise SystemExit(f"{path}: bộ việc lạ: {ds!r} (có {', '.join(DATASETS)})")
        bucket = spec.setdefault(ds, [])
        if name in bucket or (name == "*" and bucket) or (bucket == ["*"]):
            raise SystemExit(f"{path}: việc trùng hay lẫn '*': {ds}:{name}")
        bucket.append(name)
    if not spec:
        raise SystemExit(f"{path} không có tên việc nào")
    return spec


def agent_config(arm: str, opts: dict) -> dict:
    # dùng gói thuê bao: khóa nằm trong .env trên TUF (CLAUDE_CODE_OAUTH_TOKEN), không bao giờ trong cấu hình
    env = {"CLAUDE_FORCE_OAUTH": "1"}
    if arm != PLAIN:
        # tắt lượt kiểm MCP chạy nền lúc mở phiên: chỉ gọi mạng, không đổi gì model thấy
        env["AGENT_STACK_NO_BACKGROUND"] = "1"
    return {
        "import_path": f"{MODULE}:{CLASS_OF[arm]}",
        "model_name": opts["model"],
        "kwargs": {"version": opts["version"], "reasoning_effort": opts["effort"],
                   "max_budget_usd": str(opts["max_budget_usd"])},
        "env": env,
    }


def dataset_entries(spec: dict) -> list:
    out = []
    for ds in DATASETS:
        if ds in spec:
            entry = {"path": f"datasets/{ds}"}
            if spec[ds] != ["*"]:
                entry["task_names"] = list(spec[ds])
            out.append(entry)
    return out


def make_config(spec: dict, name: str, attempts: int, opts: dict, arms) -> dict:
    """Mọi cấu hình nằm chung một job để Harbor xen kẽ lượt chạy, tránh lệch theo giờ trong ngày."""
    return {"job_name": name, "jobs_dir": "jobs", "n_attempts": attempts, "n_concurrent_trials": opts["concurrent"],
            "retry": {"max_retries": 0}, "environment": {"delete": True},
            "datasets": dataset_entries(spec), "agents": [agent_config(a, opts) for a in arms]}


def make_oracle_config(spec: dict, name: str, opts: dict) -> dict:
    return {"job_name": name, "jobs_dir": "jobs", "n_attempts": 1, "n_concurrent_trials": opts["concurrent"],
            "environment": {"delete": True}, "datasets": dataset_entries(spec), "agents": [{"name": "oracle"}]}


def cmd_make_configs(args) -> int:
    opts = {k: getattr(args, k) for k in DEFAULTS}
    if args.kind == "pilot":
        spec = {"tblite": ["*"], "swerebench": read_task_spec(Path(args.swerebench), "swerebench")["swerebench"]}
        cfg = make_config(spec, args.name, args.attempts, opts, (PLAIN,))
    elif args.kind == "oracle":
        spec = read_task_spec(Path(args.tasks), None) if args.tasks else {
            "tblite": ["*"], "swerebench": read_task_spec(Path(args.swerebench), "swerebench")["swerebench"]}
        cfg = make_oracle_config(spec, args.name, opts)
    else:
        if not args.tasks:
            raise SystemExit("--kind main cần --tasks (tasks-main.txt do `select` ghi)")
        cfg = make_config(read_task_spec(Path(args.tasks)), args.name, args.attempts, opts, ARMS)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(out)
    return 0


def count_trials(cfg: dict, root: Path) -> tuple:
    """(số lượt, số việc, số bản) của một cấu hình; `*` đếm theo thư mục bộ việc dưới `root`."""
    tasks = 0
    for d in cfg.get("datasets", []):
        names = d.get("task_names")
        tasks += len(names) if names else len(list_tasks(root / d["path"]))
    agents = len(cfg.get("agents", []))
    return tasks * agents * int(cfg.get("n_attempts", 1)), tasks, agents


def cmd_plan(args) -> int:
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    n, tasks, agents = count_trials(cfg, Path(args.root))
    budget = max((float(a.get("kwargs", {}).get("max_budget_usd", 0) or 0) for a in cfg["agents"]), default=0)
    print(f"Job {cfg['job_name']}: {n} lượt = {tasks} việc × {agents} cấu hình × {cfg.get('n_attempts', 1)} lần")
    if budget:
        print(f"Trần chi phí: {n} × ${budget:g} = ${n * budget:,.0f} theo giá niêm yết (mỗi lượt có --max-budget-usd {budget:g}). "
              "Gói Max không tính tiền thật nhưng tính vào hạn mức; số thật thường thấp hơn trần.")
    else:
        print("Lời giải mẫu: không gọi model.")
    return 0


def pinned_versions(cfg: dict) -> dict:
    kw = (cfg.get("agents") or [{}])[0].get("kwargs", {})
    return {"claude_code": kw.get("version"), "model": (cfg.get("agents") or [{}])[0].get("model_name"),
            "effort": kw.get("reasoning_effort"), "max_budget_usd": kw.get("max_budget_usd")}


def pip_freeze():
    """Danh sách gói của venv đang chạy script (pip freeze), None khi không lấy được."""
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    return sorted(ln.strip() for ln in r.stdout.splitlines() if ln.strip()) if r.returncode == 0 else None


def cmd_meta(args) -> int:
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    try:
        from importlib.metadata import version as _v
        harbor = _v("harbor")
    except Exception:
        harbor = None
    commit = None
    pf = Path(args.payload) / "full" / ".payload-commit"
    if pf.is_file():
        commit = pf.read_text(encoding="utf-8").strip()
    root = Path(args.root)
    locks = {}
    for ds in DATASETS:
        lf = root / "datasets" / f"{ds}.lock.json"
        if lf.is_file():
            locks[ds] = json.loads(lf.read_text(encoding="utf-8"))
    freeze = pip_freeze()
    meta = {"job": cfg["job_name"], "harbor": harbor, "harbor_pinned": HARBOR_VERSION, "payload_commit": commit,
            "arms": [a.get("import_path", a.get("name")) for a in cfg["agents"]], "datasets": locks,
            "attempts": cfg.get("n_attempts", 1), "difficulty": difficulty_map(cfg, root),
            "pip_freeze_sha256": hashlib.sha256("\n".join(freeze).encode()).hexdigest() if freeze else None,
            "pip_freeze": freeze, **pinned_versions(cfg)}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"Đã ghi {out}")
    return 0


def cmd_validate_config(args) -> int:
    try:
        from importlib import import_module
        from importlib.metadata import version as _v
        from harbor.models.job.config import JobConfig
    except ImportError as exc:
        print(f"✗ chưa cài harbor ở python này ({exc})", file=sys.stderr)
        return 3
    if _v("harbor") != HARBOR_VERSION:
        print(f"✗ Harbor {_v('harbor')} khác bản đã ghim {HARBOR_VERSION}", file=sys.stderr)
        return 1
    cfg = JobConfig.model_validate_json(Path(args.config).read_text(encoding="utf-8"))
    for a in cfg.agents:
        if a.import_path:
            mod, _, cls = a.import_path.partition(":")
            klass = getattr(import_module(mod), cls)
            klass.parse_options(a.kwargs, a.env)
    print(f"✓ {args.config}: hợp lệ ({len(cfg.agents)} bản)")
    return 0


# ---------------------------------------------------------------- chọn việc SWE-rebench

def task_month_info(task_dir: Path):
    """(tháng 'YYYY-MM', instance_id) từ tests/config.json của việc SWE-rebench; None khi thiếu."""
    f = task_dir / "tests" / "config.json"
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
        created = str(d["created_at"])
        m = re.match(r"^(\d{4})-(\d{2})", created)
        return (f"{m.group(1)}-{m.group(2)}", d.get("instance_id") or task_dir.name) if m else None
    except (OSError, ValueError, KeyError, RecursionError):
        return None


def pick_swerebench(root: Path, n: int = 25, seed: int = SEED, month: str = None) -> tuple:
    """Chọn n việc của tháng mới nhất có ít nhất n việc sạch. Trả (danh sách tên, tháng, đếm theo tháng)."""
    allow = load_allow()
    by_month = {}
    for name in list_tasks(root):
        info = task_month_info(root / name)
        if info and not vet_task(root / name, allow):
            by_month.setdefault(info[0], []).append(name)
    if not by_month:
        raise SystemExit(f"Không thấy việc nào có tests/config.json với created_at dưới {root}")
    counts = {m: len(v) for m, v in sorted(by_month.items())}
    if month:
        chosen_month = month
    else:
        enough = [m for m in sorted(by_month, reverse=True) if len(by_month[m]) >= n]
        if not enough:
            raise SystemExit(f"Không tháng nào có đủ {n} việc sạch: {counts}")
        chosen_month = enough[0]
    pool = sorted(by_month.get(chosen_month, []))
    if len(pool) < n:
        raise SystemExit(f"Tháng {chosen_month} chỉ có {len(pool)} việc sạch, cần {n}")
    return sorted(random.Random(seed).sample(pool, n)), chosen_month, counts


def cmd_pick_swerebench(args) -> int:
    root = Path(args.dir)
    names, month, counts = pick_swerebench(root, args.n, args.seed, args.month)
    lock = root.parent / "swerebench.lock.json"
    sha = json.loads(lock.read_text())["sha256"] if lock.is_file() else dataset_hash(root)
    recent = ", ".join(f"{m}: {c}" for m, c in list(counts.items())[-6:])
    print(f"# {args.n} việc SWE-rebench (swe-rebench/swe-rebench-leaderboard), chọn ngày {time.strftime('%d/%m/%Y')}.")
    print(f"# Cách chọn: tháng mới nhất có ít nhất {args.n} việc sạch theo created_at trong tests/config.json "
          f"là {month} ({len(counts)} tháng có việc; 6 tháng gần nhất: {recent}).")
    print(f"# Việc vi phạm kiểm an toàn (vet) bị bỏ trước. Rút bằng random.Random({args.seed}).sample(danh sách đã sắp, {args.n}), "
          "in theo thứ tự chữ cái.")
    print(f"# Mã băm nội dung bộ việc: {sha}")
    for n in names:
        print(n)
    return 0


# ---------------------------------------------------------------- watch (TM-77)

LIMIT_ERRORS = {"ApiUsageLimitError", "ApiRateLimitError"}


def count_limit_errors(job_dir: Path) -> int:
    n = 0
    for res in Path(job_dir).glob("*/result.json"):
        try:
            d = json.loads(res.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        exc = d.get("exception_info") if isinstance(d, dict) else None
        if isinstance(exc, dict) and exc.get("exception_type") in LIMIT_ERRORS:
            n += 1
    return n


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:   # tiến trình đã thoát nhưng chưa được thu dọn thì coi như đã hết
        stat = Path(f"/proc/{pid}/stat").read_text()
        return stat.rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return True


def watch(job_dir: Path, pid: int, limit: int = 3, interval: float = 60.0, sleep=time.sleep) -> int:
    """Chờ job; số lượt lỗi hạn mức hay rate limit vượt `limit` thì gửi SIGTERM cho cả nhóm tiến trình của job."""
    while pid_alive(pid):
        n = count_limit_errors(job_dir)
        if n > limit:
            marker = Path(str(job_dir) + ".stopped")
            marker.write_text(f"Dừng lúc {time.strftime('%d/%m/%Y %H:%M:%S')}: {n} lượt lỗi hạn mức hay rate limit "
                              f"(ngưỡng {limit}).\n", encoding="utf-8")
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
            return 3
        sleep(interval)
    return 0


def cmd_watch(args) -> int:
    return watch(Path(args.job), args.pid, args.limit, args.interval)


# ---------------------------------------------------------------- đọc kết quả

def _seconds(span):
    from datetime import datetime
    try:
        a = datetime.fromisoformat(span["started_at"].replace("Z", "+00:00"))
        b = datetime.fromisoformat(span["finished_at"].replace("Z", "+00:00"))
        return (b - a).total_seconds()
    except (TypeError, KeyError, ValueError, AttributeError):
        return None


def parse_stream(path: Path) -> dict:
    """Đọc log stream-json của Claude Code: sự kiện init (phiên bản, plugin, subagent), số lần gọi subagent và skill,
    sự kiện result cuối. Trả dict rỗng khi không có log."""
    info = {"init": None, "agent_calls": 0, "stack_agent_calls": 0, "skill_calls": 0, "result": None}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if not isinstance(ev, dict):
            continue
        t = ev.get("type")
        if t == "system" and ev.get("subtype") == "init" and info["init"] is None:
            agents = ev.get("agents")
            plugins = ev.get("plugins")
            flat = json.dumps(ev, ensure_ascii=False)
            info["init"] = {
                "version": ev.get("claude_code_version"),
                "plugin": ("agent-stack" in json.dumps(plugins, ensure_ascii=False)) if plugins is not None
                else ("agent-stack" in flat),
                "stack_agents": (any(f"agent-stack:{a}" in json.dumps(agents, ensure_ascii=False) for a in STACK_AGENTS)
                                 if isinstance(agents, list) else None),
            }
        elif t == "assistant":
            content = (ev.get("message") or {}).get("content")
            for part in content if isinstance(content, list) else []:
                if isinstance(part, dict) and part.get("type") == "tool_use":
                    tool = part.get("name")
                    if tool in ("Task", "Agent"):
                        info["agent_calls"] += 1
                        sub = (part.get("input") or {}).get("subagent_type")
                        if isinstance(sub, str) and sub.startswith("agent-stack:"):
                            info["stack_agent_calls"] += 1
                    elif tool == "Skill":
                        info["skill_calls"] += 1
        elif t == "result":
            info["result"] = {"subtype": ev.get("subtype"), "is_error": ev.get("is_error"),
                              "cost": ev.get("total_cost_usd")}
    return info


def parse_env_file(path: Path):
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    env = {}
    for line in text.splitlines():
        k, sep, v = line.partition("=")
        if sep:
            env[k.strip()] = v.strip()
    return env


def python_ok(ver: str) -> bool:
    m = re.match(r"^(\d+)\.(\d+)", ver or "")
    return bool(m) and (int(m.group(1)), int(m.group(2))) >= MIN_PYTHON


def structure_problems(arm: str, env: dict) -> list:
    """Cấu trúc thật trong container có đúng định nghĩa của bản không (ghi bởi agent_stack_agents)."""
    if env is None:
        return []
    # Claude Code của Harbor đọc CLAUDE.md cấp người dùng ở $CLAUDE_CONFIG_DIR (=<logs>/sessions), không phải ~/.claude: kiểm cả hai.
    want = {PLAIN: {"plugin_dir": "no", "user_claude_md": "no", "config_claude_md": "no"},
            STACK: {"plugin_dir": "yes", "user_claude_md": "yes", "config_claude_md": "yes", "hooks_json": "yes",
                    "agents_dir": "yes"},
            NOHOOKS: {"plugin_dir": "yes", "user_claude_md": "yes", "config_claude_md": "yes", "hooks_json": "no",
                      "agents_dir": "yes"},
            NOAGENTS: {"plugin_dir": "yes", "user_claude_md": "yes", "config_claude_md": "yes", "hooks_json": "yes",
                       "agents_dir": "no"}}[arm]
    return [f"{k}={env.get(k)} (cần {v})" for k, v in want.items() if env.get(k) != v]


def task_key(name) -> str:
    """Tên việc = tên thư mục việc. Harbor đặt task_name = config.task.name, mà gói Hub bắt buộc dạng org/tên, còn thư mục
    xuất bởi `harbor download --export` và `task_names` của job dùng tên ngắn. Cắt phần org/ để mọi chỗ dùng một dạng."""
    return str(name).rsplit("/", 1)[-1]


def load_trials(job_dirs) -> list:
    trials = []
    for job in job_dirs:
        for res in sorted(Path(job).glob("*/result.json")):
            try:
                d = json.loads(res.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(d, dict) or "task_name" not in d:
                continue
            rewards = (d.get("verifier_result") or {}).get("rewards") or {}
            ar = d.get("agent_result") or {}
            exc = d.get("exception_info") or None
            agent = (d.get("agent_info") or {}).get("name") or "?"
            stream = parse_stream(next(iter(sorted(res.parent.glob("agent/**/claude-code.txt"))), res.parent / "none"))
            env = parse_env_file(res.parent / "agent" / "agent-stack-env.txt")
            result = stream.get("result") or {}
            trials.append({
                "task": task_key(d["task_name"]),
                "task_full": d["task_name"],
                "agent": agent,
                "source": d.get("source"),
                "reward": rewards.get("reward"),
                "exception": (exc.get("exception_type") or "lỗi") if isinstance(exc, dict) else (str(exc) if exc else None),
                "input": ar.get("n_input_tokens"), "cache": ar.get("n_cache_tokens"),
                "output": ar.get("n_output_tokens"), "cost": ar.get("cost_usd"),
                "seconds": _seconds(d.get("agent_execution")),
                "version": (d.get("agent_info") or {}).get("version"),
                "init": stream.get("init"),
                "budget_hit": str(result.get("subtype") or "").startswith("error_max_budget"),
                "agent_calls": stream.get("agent_calls"), "stack_agent_calls": stream.get("stack_agent_calls"),
                "skill_calls": stream.get("skill_calls"),
                "env": env,
                "python3": (env or {}).get("python3"),
                "hooks_ok": None if env is None else python_ok(env.get("python3", "")),
                "payload_commit": (env or {}).get("payload_commit") or None,
                "structure": structure_problems(agent, env) if agent in ARMS else [],
                "job": Path(job).name,
                "trial": res.parent.name,
            })
    return trials


def load_metas(job_dirs) -> list:
    metas = []
    for job in job_dirs:
        for f in (Path(job) / "bench-meta.json", Path(str(job) + ".meta.json")):
            if f.is_file():
                try:
                    metas.append(json.loads(f.read_text(encoding="utf-8")))
                except ValueError:
                    pass
                break
    return metas


def consistency(trials: list, metas: list) -> list:
    """TM-75: lý do không được gộp các lượt (khác phiên bản Claude Code, khác commit bản chép, khác bộ việc, lệch cấu trúc)."""
    problems = []
    versions = {t["init"]["version"] for t in trials if t.get("init") and t["init"].get("version")}
    if len(versions) > 1:
        problems.append("khác phiên bản Claude Code giữa các lượt: " + ", ".join(sorted(versions)))
    harbor_versions = {t["version"] for t in trials if t.get("version") and t["version"] != "unknown"}
    if len(harbor_versions) > 1:
        problems.append("agent_info.version khác nhau giữa các lượt: " + ", ".join(sorted(harbor_versions)))
    commits = {t["payload_commit"] for t in trials if t.get("payload_commit") and t["agent"] in PLUGIN_ARMS}
    if len(commits) > 1:
        problems.append("khác commit bản chép agent-stack: " + ", ".join(sorted(commits)))
    for key in ("claude_code", "harbor", "payload_commit", "model", "effort", "max_budget_usd"):
        vals = {m.get(key) for m in metas if m.get(key) is not None}
        if len(vals) > 1:
            problems.append(f"bench-meta khác nhau ở {key}: " + ", ".join(sorted(map(str, vals))))
    for ds in DATASETS:
        vals = {(m.get("datasets") or {}).get(ds, {}).get("sha256") for m in metas}
        vals.discard(None)
        if len(vals) > 1:
            problems.append(f"khác nội dung bộ việc {ds}")
    pinned = {m.get("claude_code") for m in metas if m.get("claude_code")}
    if pinned and versions and not versions <= pinned:
        problems.append(f"phiên bản Claude Code thật ({', '.join(sorted(versions))}) khác bản đã ghim ({', '.join(sorted(pinned))})")
    return problems


def warnings_for(metas: list) -> list:
    """Cảnh báo, không từ chối: môi trường Python của Harbor (pip freeze) khác nhau giữa các job."""
    sums = {m.get("pip_freeze_sha256") for m in metas if m.get("pip_freeze_sha256")}
    if len(sums) > 1:
        return ["pip freeze của venv Harbor khác nhau giữa các job (phụ thuộc của Harbor có thể đã đổi): "
                + ", ".join(sorted(x[:12] for x in sums))]
    return []


# Lỗi do hạ tầng, không do agent: Harbor vẫn chạy grader sau các lỗi này nên lượt có điểm 0 mà không nói gì về chất lượng.
# Lượt dính lỗi này làm cả việc bị loại khỏi phép so (kể cả khi việc đó còn lượt khác dùng được). Hết giờ, hết context, lỗi thoát chung thì giữ là kết quả thật (luật dài hơn có thể
# chính là nguyên nhân). Chạm trần ngân sách mỗi lượt cũng giữ: bản tốn hơn chạm trần sớm hơn là một cái giá.
INFRA_ERRORS = {"ApiUsageLimitError", "ApiRateLimitError", "ApiOverloadedError", "AgentAuthenticationError",
                "NetworkConnectionError", "ModelNotFoundError", "ApiInternalServerError", "ApiConnectionClosedError",
                "ApiResponseStalledError", "UnknownApiError", "ApiProviderResourceNotFoundError"}   # tên trong harbor 0.25.0 agents/installed/base.py


def graded(t) -> bool:
    return t["reward"] is not None and t["exception"] not in INFRA_ERRORS


def passed(t) -> bool:
    return isinstance(t["reward"], (int, float)) and t["reward"] >= 1.0 - 1e-9


def exact_binomial_p(b: int, c: int) -> float:
    """Kiểm dấu chính xác hai phía trên b, c cặp lệch nhau. Với một lượt mỗi việc đây chính là McNemar chính xác; với nhiều
    lượt mỗi việc, b và c là số việc mà tỉ lệ đạt của bản này thấp hơn, cao hơn (việc bằng nhau bỏ qua)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


def _summary(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals:
        return None
    return {"n": len(vals), "median": statistics.median(vals), "total": sum(vals)}


def compare(trials: list, oracle: list = None, arms=None) -> dict:
    """So ghép cặp theo việc trên tập việc chung của mọi bản có mặt. Một lượt không có điểm (môi trường hỏng) hay hỏng vì
    hạ tầng, ở bất kỳ bản nào và dù còn lượt khác của việc đó, loại cả việc khỏi mọi phép so. Việc mà bản cần hook (agent-stack, noagents) chạy trong container không có python3 từ 3.9 cũng bị loại,
    vì hook không chạy thì bản đó không còn là bản đã định nghĩa. Nhiều lượt mỗi việc thì so tỉ lệ đạt theo việc."""
    arms = list(arms) if arms else [a for a in ARMS if any(t["agent"] == a for t in trials)]
    by = {}
    for t in trials:
        by.setdefault((t["agent"], t["task"]), []).append(t)
    tasks = sorted({t["task"] for t in trials if t["agent"] in arms})
    bad_grader = sorted({t["task"] for t in (oracle or []) if not passed(t)})
    oracle_tasks = {t["task"] for t in (oracle or [])}
    rows, excluded = [], []
    for task in tasks:
        if task in bad_grader:
            excluded.append((task, "lời giải mẫu không đạt"))
            continue
        if oracle is not None and task not in oracle_tasks:
            excluded.append((task, "chưa chạy lời giải mẫu"))
            continue
        why, rates = None, {}
        for arm in arms:
            ts = by.get((arm, task), [])
            ok = ts
            bad = [t for t in ts if not graded(t)]
            if not ts or bad:       # bất kỳ lượt nào hỏng vì hạ tầng hay không có điểm: loại cả việc, không giữ lượt còn lại
                why = f"thiếu điểm ở {SHORT.get(arm, arm)}: " + ", ".join(
                    sorted({t["exception"] or "chưa chạy" for t in bad}) or ["chưa chạy"])
                break
            if arm in HOOK_ARMS and any(t["hooks_ok"] is False for t in ok):
                why = f"container thiếu python3 từ {MIN_PYTHON[0]}.{MIN_PYTHON[1]} ở {SHORT[arm]}: hook không chạy"
                break
            rates[arm] = sum(passed(t) for t in ok) / len(ok)
        if why:
            excluded.append((task, why))
        else:
            rows.append({"task": task, "rates": rates})
    common = {r["task"] for r in rows}
    multi = any(len(by.get((a, r["task"]), [])) > 1 for r in rows for a in arms)

    comparisons = []
    for a, b in PAIRS:
        if a in arms and b in arms:
            worse = [r["task"] for r in rows if r["rates"][b] < r["rates"][a]]    # b kém hơn a
            better = [r["task"] for r in rows if r["rates"][b] > r["rates"][a]]
            comparisons.append({"a": a, "b": b, "worse": worse, "better": better,
                                "p_value": exact_binomial_p(len(worse), len(better))})

    def arm_stats(name):
        all_ts = [t for t in trials if t["agent"] == name]
        ts = [t for t in all_ts if t["task"] in common and graded(t)]
        passes = sum(passed(t) for t in ts)
        cost = _summary(t["cost"] for t in ts)
        expect_plugin = name in PLUGIN_ARMS
        expect_agents = name in SUBAGENT_ARMS
        init = [t["init"] for t in ts]
        mismatch = 0
        for i in init:
            if i is None:
                continue
            if i["plugin"] != expect_plugin or (i["stack_agents"] is not None and i["stack_agents"] != expect_agents):
                mismatch += 1
        return {
            "trials": len(ts),
            "pass_rate": (passes / len(ts)) if ts else None,
            "exceptions": sorted({t["exception"] for t in ts if t["exception"]}),
            "infra_dropped": sum(1 for t in all_ts if t["exception"] in INFRA_ERRORS),
            "limit_errors": sum(1 for t in all_ts if t["exception"] in LIMIT_ERRORS),
            "n_exceptions": sum(1 for t in ts if t["exception"]),
            "budget_hit": sum(1 for t in ts if t["budget_hit"]),
            "input": _summary(t["input"] for t in ts), "cache": _summary(t["cache"] for t in ts),
            "output": _summary(t["output"] for t in ts), "cost": cost,
            "seconds": _summary(t["seconds"] for t in ts),
            "cost_per_pass": (cost["total"] / passes) if cost and passes else None,
            "agent_calls": _summary(t["agent_calls"] for t in ts),
            "stack_agent_calls": _summary(t["stack_agent_calls"] for t in ts),
            "skill_calls": _summary(t["skill_calls"] for t in ts),
            "init_seen": sum(1 for i in init if i is not None),
            "init_mismatch": mismatch,
            "no_log": sum(1 for i in init if i is None),
            "hooks_missing": sum(1 for t in all_ts if t["hooks_ok"] is False),
            "structure_bad": sum(1 for t in ts if t["structure"]),
        }
    stats = {a: arm_stats(a) for a in arms}
    return {"arms": arms, "pairs": len(rows), "rows": rows, "excluded": excluded, "comparisons": comparisons,
            "multi_attempt": multi, "stats": stats, "limit_errors": sum(s["limit_errors"] for s in stats.values())}


def _fmt(s, key="median", digits=0):
    if not s:
        return "—"
    return f"{s[key]:,.{digits}f}"


def report(res: dict) -> str:
    arms = res["arms"]
    col = 12
    lines = [f"Việc so được (chung cho mọi bản): {res['pairs']}" + (f" (loại {len(res['excluded'])})" if res["excluded"] else "")]
    for task, why in res["excluded"][:40]:
        lines.append(f"  - loại {task}: {why}")
    if len(res["excluded"]) > 40:
        lines.append(f"  … và {len(res['excluded']) - 40} việc nữa")
    lines.append("")
    lines.append(f"{'':34s}" + "".join(f"{SHORT.get(a, a):>{col}s}" for a in arms))

    def row(label, fn):
        lines.append(f"{label:34s}" + "".join(f"{fn(res['stats'][a]):>{col}s}" for a in arms))
    row("Tỉ lệ đạt", lambda s: "—" if s["pass_rate"] is None else f"{100 * s['pass_rate']:.1f}%")
    row("Số lượt", lambda s: str(s["trials"]))
    for label, key, digits in (("Token vào (trung vị)", "input", 0), ("Token cache (trung vị)", "cache", 0),
                               ("Token ra (trung vị)", "output", 0), ("Chi phí USD (trung vị)", "cost", 3),
                               ("Thời gian agent, giây (trung vị)", "seconds", 0)):
        row(label, lambda s, k=key, d=digits: _fmt(s[k], digits=d))
    row("Chi phí USD (tổng)", lambda s: _fmt(s["cost"], "total", 2))
    row("Chi phí USD mỗi lượt đạt", lambda s: "—" if s["cost_per_pass"] is None else f"{s['cost_per_pass']:.3f}")
    row("Gọi subagent (tổng)", lambda s: _fmt(s["agent_calls"], "total"))
    row("  trong đó subagent agent-stack", lambda s: _fmt(s["stack_agent_calls"], "total"))
    row("Gọi skill (tổng)", lambda s: _fmt(s["skill_calls"], "total"))
    row("Lượt lỗi (hết giờ, lỗi agent)", lambda s: str(s["n_exceptions"]))
    row("Lượt chạm trần ngân sách", lambda s: str(s["budget_hit"]))
    row("Lượt bỏ vì hạ tầng", lambda s: str(s["infra_dropped"]))
    row("  trong đó lỗi hạn mức/rate limit", lambda s: str(s["limit_errors"]))
    row("Lượt thiếu hook (không có python3)", lambda s: str(s["hooks_missing"]))
    lines.append("")
    total = len(res["rows"])
    for c in res["comparisons"]:
        a, b = SHORT[c["a"]], SHORT[c["b"]]
        test = ("kiểm dấu chính xác theo tỉ lệ đạt từng việc" if res.get("multi_attempt")
                else "McNemar chính xác")
        lines.append(f"{b} so với {a}: kém hơn ở {len(c['worse'])} việc, tốt hơn ở {len(c['better'])} việc; "
                     f"{test} p = {c['p_value']:.3f}.")
        for label, names in (("kém hơn", c["worse"]), ("tốt hơn", c["better"])):
            if names:
                lines.append(f"    {label}: {', '.join(names[:12])}" + (f" … (+{len(names) - 12})" if len(names) > 12 else ""))
    if res["comparisons"]:
        k = len(res["comparisons"])
        lines.append(f"p chưa hiệu chỉnh; {k} phép so sánh nên ngưỡng 0,05 theo Bonferroni là {0.05 / k:.3f}.")
    lines.append("")
    for a in arms:
        s = res["stats"][a]
        extra = f"; {s['no_log']} lượt không có log" if s["no_log"] else ""
        lines.append(f"{SHORT[a]}: log init khớp định nghĩa ở {s['init_seen'] - s['init_mismatch']}/{s['init_seen']} lượt{extra}"
                     + (f"; cấu trúc container lệch ở {s['structure_bad']} lượt" if s["structure_bad"] else ""))
        if s["init_mismatch"] and a == PLAIN:
            lines.append("⚠️ Bản trơn thấy agent-stack: hai bản không tách nhau, kết quả không dùng được.")
        elif s["init_mismatch"] or s["structure_bad"]:
            lines.append(f"⚠️ {SHORT[a]} không đúng định nghĩa ở {max(s['init_mismatch'], s['structure_bad'])} lượt: đọc trước khi tin số liệu.")
    if res["limit_errors"] > 3:
        lines.append(f"⚠️ {res['limit_errors']} lượt lỗi hạn mức hay rate limit (ngưỡng dừng job là 3): số liệu có thể lệch.")
    if total < 100:
        lines.append(f"Lưu ý: {total} việc chung chỉ đủ thấy chênh lệch lớn; muốn thấy chênh 10 điểm cần khoảng 160–235 cặp: "
                     "chạy thêm việc, hoặc thêm lần chạy mỗi việc (--attempts).")
    return "\n".join(lines)


def cmd_compare(args) -> int:
    trials = load_trials(args.jobs)
    if not trials:
        print("Không thấy lượt chạy nào (*/result.json) trong các thư mục đã cho.", file=sys.stderr)
        return 1
    problems = consistency(trials, load_metas(args.jobs))
    if problems:
        print("Từ chối gộp các lượt này (TM-75):", file=sys.stderr)
        for p in problems:
            print("  - " + p, file=sys.stderr)
        return 2
    oracle = [t for t in load_trials([args.oracle]) if t["agent"] == "oracle"] if args.oracle else None
    res = compare(trials, oracle)
    for w in warnings_for(load_metas(args.jobs)):
        print("⚠️ " + w, file=sys.stderr)
        res.setdefault("warnings", []).append(w)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(report(res))
    return 0


# ---------------------------------------------------------------- export (TM-73)

# Khóa của Anthropic, kể cả dạng OAuth sk-ant-oat01-…; và dạng NAME=giá trị của ba biến chứa khóa.
TOKEN_RE = re.compile(rb"sk-ant-[A-Za-z0-9_\-]{6,}")
NAMED_RE = re.compile(rb"""((?:CLAUDE_CODE_OAUTH_TOKEN|ANTHROPIC_API_KEY|ANTHROPIC_AUTH_TOKEN)["']?\s*[=:]\s*["']?)[^\s"',}]{8,}""")
MASK = b"[da che]"
EXPORT_NAMES = ("result.json", "claude-code.txt", "reward.txt", "agent-stack-env.txt", "config.json", "lock.json")
ANSI_RE = re.compile(rb"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]")


def secret_variants(token: bytes) -> list:
    """Chuỗi khóa thật và các dạng base64 của nó (chuẩn và url-safe), ở cả ba độ lệch có thể có khi khóa nằm giữa một
    chuỗi base64 dài hơn. Mỗi dạng chỉ giữ phần ký tự chỉ phụ thuộc vào byte của khóa."""
    out = {token}
    for enc in (base64.b64encode, base64.urlsafe_b64encode):
        for off in range(3):
            raw = b"\0" * off + token
            e = enc(raw).rstrip(b"=")
            lead = (0, 2, 3)[off]
            trail = 0 if len(raw) % 3 == 0 else 1
            piece = e[lead:len(e) - trail]
            if len(piece) >= 12:
                out.add(piece)
    return sorted(out, key=len, reverse=True)


def read_env_token(env_file) -> bytes:
    """Giá trị CLAUDE_CODE_OAUTH_TOKEN trong file .env (b'' khi không có). Không bao giờ in giá trị này."""
    try:
        text = Path(env_file).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return b""
    for line in text.splitlines():
        m = re.match(r"""^\s*(?:export\s+)?CLAUDE_CODE_OAUTH_TOKEN\s*=\s*["']?([^"'\s#]+)""", line)
        if m and len(m.group(1)) >= 8:
            return m.group(1).encode()
    return b""


def env_secrets(env_file) -> list:
    tok = read_env_token(env_file) if env_file else b""
    return secret_variants(tok) if tok else []


def mask_secrets(data: bytes, extra=()) -> bytes:
    """Che mọi chuỗi giống khóa Anthropic, giá trị của ba biến chứa khóa, và (nếu có) giá trị khóa thật cùng dạng base64."""
    for v in extra:
        data = data.replace(v, MASK)
    return NAMED_RE.sub(rb"\1" + MASK, TOKEN_RE.sub(MASK, data))


def sanitize_log(data: bytes) -> str:
    """Văn bản an toàn để in ra terminal: che khóa, bỏ chuỗi điều khiển ANSI và ký tự điều khiển (trừ xuống dòng, tab)."""
    data = ANSI_RE.sub(b"", mask_secrets(data)).replace(b"\r", b"\n")
    text = data.decode("utf-8", errors="replace")
    return "".join(c for c in text if c in "\n\t" or (ord(c) >= 0x20 and not 0x7F <= ord(c) <= 0x9F))


def _walk_files(root: Path) -> list:
    """File thường dưới root, không theo symlink: mã trong container có thể đặt symlink trỏ ra file của máy chủ vào thư mục log."""
    found = []
    for base, dirs, names in os.walk(root, followlinks=False):
        dirs.sort()
        for n in sorted(names):
            p = Path(base) / n
            if not p.is_symlink() and p.is_file():
                found.append(p)
    return found


def export(job_dirs, out: Path, extra=()) -> tuple:
    """Chép các file kết quả (và bench-meta.json) của các job sang `out`, giữ đường dẫn job/lượt/…; mọi file đều qua
    mask_secrets. Trả (số file, số file đã che)."""
    n = masked = 0
    for job in job_dirs:
        job = Path(job)
        if not job.is_dir():
            continue
        files = [(p, p.relative_to(job)) for p in _walk_files(job) if p.name in EXPORT_NAMES]
        meta = Path(str(job) + ".meta.json")
        if meta.is_file() and not meta.is_symlink():
            files.append((meta, Path("bench-meta.json")))
        for src, rel in files:
            dst = out / job.name / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            raw = src.read_bytes()
            clean = mask_secrets(raw, extra)
            masked += clean != raw
            dst.write_bytes(clean)
            n += 1
    return n, masked


def residual_secrets(root: Path, extra=()) -> list:
    """File dưới `root` (mọi file, kể cả nhị phân) còn chuỗi giống khóa, hay còn giá trị khóa thật hay dạng base64 của nó.
    Trả [(đường dẫn, loại)]; không bao giờ trả giá trị."""
    found = []
    for p in _walk_files(root):
        data = p.read_bytes()
        if TOKEN_RE.search(data):
            found.append((str(p), "mẫu sk-ant-"))
        elif any(v in data for v in extra):
            found.append((str(p), "giá trị khóa trong .env"))
    return found


def cmd_export(args) -> int:
    out = Path(args.out)
    try:
        out.mkdir(parents=True)
    except FileExistsError:
        print(f"{out} đã có; chọn thư mục mới", file=sys.stderr)
        return 1
    extra = env_secrets(args.env_file)
    n, masked = export(args.jobs, out, extra)
    if not n or not any(out.glob("*/*/result.json")):  # chưa có lượt nào xong: báo lỗi để fetch dừng trước khi xóa bản cũ trên Mac
        print("Chưa có kết quả nào để chép (job chưa có lượt nào xong?)", file=sys.stderr)
        return 1
    left = residual_secrets(out, extra)
    if left:
        print("✗ Còn khóa sau khi che, không kéo về: " + ", ".join(f"{p} ({k})" for p, k in left[:5]), file=sys.stderr)
        shutil.rmtree(out, ignore_errors=True)
        return 1
    print(f"Đã chép {n} file vào {out}" + (f"; che khóa trong {masked} file" if masked else ""))
    return 0


def cmd_residual(args) -> int:
    """Quét lại thư mục đã kéo về với đúng mẫu mà export dùng (và khóa trong --env-file nếu chạy nơi có nó)."""
    extra = env_secrets(args.env_file)
    bad = []
    for d in args.dirs:
        if Path(d).is_dir():
            bad += residual_secrets(Path(d), extra)
    for p, kind in bad:
        print(f"✗ {p}: {kind}", file=sys.stderr)
    if not bad:
        print(f"✓ không thấy khóa trong {len([d for d in args.dirs if Path(d).is_dir()])} thư mục")
    return 1 if bad else 0


def cmd_scrub(_args) -> int:
    sys.stdout.write(sanitize_log(sys.stdin.buffer.read()))
    return 0


# ---------------------------------------------------------------- chọn việc theo độ khó công bố

LEVELS = ("easy", "medium", "hard", "extreme")
KEEP_LEVELS = ("medium", "hard", "extreme")


def _level(raw):
    if isinstance(raw, str):
        low = raw.strip().lower()
        for lv in LEVELS:
            if low == lv or low.startswith(lv + " ") or low.startswith(lv + "-") or low.startswith(lv + "_"):
                return lv
    return None


def _find_key(data, key, depth=0):
    """Giá trị đầu tiên của khóa `key` trong dict/list lồng nhau (ưu tiên metadata, task, rồi gốc, rồi tìm sâu)."""
    if depth > 8:
        return None
    if isinstance(data, dict):
        for table in ("metadata", "task"):
            sub = data.get(table)
            if isinstance(sub, dict) and key in sub:
                return sub[key]
        if key in data:
            return data[key]
        for v in data.values():
            r = _find_key(v, key, depth + 1)
            if r is not None:
                return r
    elif isinstance(data, list):
        for v in data:
            r = _find_key(v, key, depth + 1)
            if r is not None:
                return r
    return None


def task_difficulty(task_dir: Path):
    """Nhãn độ khó (easy, medium, hard, extreme) mà bộ đo công bố cho việc, hay None. TBLite gắn nhãn theo tỉ lệ đạt của Haiku 4.5.
    Đọc linh hoạt vì chưa thấy file thật: khóa `difficulty` trong task.toml (bảng [metadata], [task] hay gốc, rồi tìm sâu),
    rồi nhãn nằm trong `tags`, rồi các file JSON nhỏ metadata.json, info.json, task.json cạnh task.toml."""
    docs = []
    toml = task_dir / "task.toml"
    if toml.is_file():
        try:
            import tomllib
            docs.append(tomllib.loads(toml.read_text(encoding="utf-8")))
        except Exception:
            pass
    for name in ("metadata.json", "info.json", "task.json"):
        f = task_dir / name
        if f.is_file() and f.stat().st_size < 1_000_000:
            try:
                docs.append(json.loads(f.read_text(encoding="utf-8")))
            except (ValueError, RecursionError):
                pass
    for doc in docs:
        lv = _level(_find_key(doc, "difficulty"))
        if lv:
            return lv
    for doc in docs:
        tags = _find_key(doc, "tags")
        for tag in tags if isinstance(tags, list) else []:
            lv = _level(tag)
            if lv:
                return lv
    return None


def select_main(root: Path, swe_names, levels=KEEP_LEVELS) -> dict:
    """Việc cho job lớn, không dựa vào kết quả của bản nào: mọi việc TBLite có nhãn trong `levels` cộng các việc SWE-rebench đã
    chọn. Dừng với lỗi rõ khi không đọc được nhãn nào."""
    tb = root / "tblite"
    names = list_tasks(tb)
    labels = {n: task_difficulty(tb / n) for n in names}
    if not any(labels.values()):
        raise SystemExit(f"Không đọc được nhãn độ khó ở việc nào dưới {tb} (tìm `difficulty` trong task.toml/metadata.json): "
                         "xem một task.toml thật rồi sửa task_difficulty() trong harbor_bench.py")
    swe_have = set(list_tasks(root / "swerebench"))
    missing = [n for n in swe_names if n not in swe_have]
    if missing:
        raise SystemExit("Việc SWE-rebench không còn trong bộ việc (bị loại khi kiểm an toàn?): " + ", ".join(missing[:10]))
    counts = {}
    for lv in labels.values():
        counts[lv or "không nhãn"] = counts.get(lv or "không nhãn", 0) + 1
    return {"tblite": sorted(n for n, lv in labels.items() if lv in levels), "swerebench": sorted(swe_names),
            "counts": counts, "unlabeled": sorted(n for n, lv in labels.items() if lv is None), "labels": labels,
            "levels": list(levels)}


def cmd_select(args) -> int:
    root = Path(args.datasets)
    swe = [n for ln in Path(args.swerebench).read_text(encoding="utf-8").splitlines()
           if (n := ln.split("#", 1)[0].strip())]
    levels = tuple(x for x in args.levels.split(",") if x)
    bad = [x for x in levels if x not in LEVELS]
    if bad:
        print(f"Nhãn lạ: {bad} (có {', '.join(LEVELS)})", file=sys.stderr)
        return 2
    res = select_main(root, swe, levels)
    counts = ", ".join(f"{k} {v}" for k, v in sorted(res["counts"].items()))
    lines = [f"# Việc cho job lớn, sinh ngày {time.strftime('%d/%m/%Y')} từ nhãn độ khó mà bộ đo công bố, KHÔNG từ kết quả của bản nào.",
             f"# TBLite: mọi việc có nhãn {'/'.join(levels)} ({len(res['tblite'])} việc; số việc theo nhãn trong bộ: {counts}).",
             "# TBLite gắn nhãn theo tỉ lệ đạt của Haiku 4.5; việc easy bị bỏ vì ở đó mọi cấu hình đạt gần hết, không phân biệt được.",
             f"# SWE-rebench: cả {len(res['swerebench'])} việc trong tasks-swerebench.txt."]
    if res["unlabeled"]:
        lines.append(f"# Không đọc được nhãn nên bị bỏ ({len(res['unlabeled'])}): " + ", ".join(res["unlabeled"][:30]))
    lines += [f"tblite:{n}" for n in res["tblite"]] + [f"swerebench:{n}" for n in res["swerebench"]]
    text = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    print(f"{len(res['tblite'])} việc TBLite + {len(res['swerebench'])} SWE-rebench = "
          f"{len(res['tblite']) + len(res['swerebench'])} việc (nhãn: {counts})", file=sys.stderr)
    if res["unlabeled"]:
        print(f"⚠️ {len(res['unlabeled'])} việc TBLite không có nhãn, đã bỏ.", file=sys.stderr)
    return 0


def difficulty_map(cfg: dict, root: Path) -> dict:
    """{tên việc: nhãn} cho các việc trong cấu hình job (SWE-rebench ghi 'swerebench'); ghi vào meta để pilot-report dùng."""
    out = {}
    for d in cfg.get("datasets", []):
        ds_root = Path(root) / d["path"]
        for n in d.get("task_names") or (list_tasks(ds_root) if ds_root.is_dir() else []):
            out[n] = "swerebench" if d["path"].endswith("swerebench") else (task_difficulty(ds_root / n) or "không nhãn")
    return out


def pilot_report(trials: list, metas: list, main_tasks=None, attempts: int = 1) -> str:
    """Pilot (bản plain) chỉ để đo chi phí mỗi lượt và độ bão hòa theo nhãn độ khó. Không chọn gì: chỉ in gợi ý."""
    labels = {}
    for m in metas:
        labels.update(m.get("difficulty") or {})
    plain = [t for t in trials if t["agent"] == PLAIN]
    if not plain:
        return "Không có lượt plain nào."
    groups = {}
    for t in plain:
        groups.setdefault(labels.get(t["task"]) or ("swerebench" if t.get("source") == "swerebench" or "__" in t["task"]
                                                    else "không nhãn"), []).append(t)
    order = list(LEVELS) + ["swerebench", "không nhãn"]
    lines = ["Pilot (bản plain): tỉ lệ đạt và chi phí theo nhãn độ khó", f"{'nhãn':14s}{'lượt':>6s}{'đạt':>8s}{'chi phí trung vị':>20s}"]
    notes = []
    for g in sorted(groups, key=lambda k: order.index(k) if k in order else 99):
        ok = [t for t in groups[g] if graded(t)]
        rate = (sum(passed(t) for t in ok) / len(ok)) if ok else None
        med = statistics.median([t["cost"] for t in ok if isinstance(t["cost"], (int, float))] or [0])
        lines.append(f"{g:14s}{len(ok):>6d}{'—' if rate is None else f'{100 * rate:.0f}%':>8s}{med:>20.3f}")
        if rate is not None and len(ok) >= 5 and rate >= 0.95:
            notes.append(f"Gợi ý: nhóm '{g}' bão hòa ({100 * rate:.0f}% đạt trên {len(ok)} lượt): ít phân biệt được các cấu hình. "
                         "Chỉ là gợi ý, tasks-main.txt không đổi; bạn quyết định có bỏ nhóm này không.")
    costs = [t["cost"] for t in plain if graded(t) and isinstance(t["cost"], (int, float))]
    if costs:
        med = statistics.median(costs)
        lines.append(f"Chi phí trung vị mỗi lượt plain: ${med:.3f} (tổng pilot ${sum(costs):.2f}). Bản có agent-stack luôn tốn hơn "
                     "(thêm luật và mô tả skill vào mỗi lần gọi model).")
        if main_tasks:
            n = main_tasks * 4 * attempts
            lines.append(f"Job lớn: {main_tasks} việc × 4 cấu hình × {attempts} lần = {n} lượt; nếu mỗi lượt bằng plain thì khoảng "
                         f"${n * med:,.0f} theo giá niêm yết (cận dưới).")
    lines += notes
    return "\n".join(lines)


def cmd_pilot_report(args) -> int:
    trials = load_trials(args.jobs)
    if not trials:
        print("Không thấy lượt chạy nào trong các thư mục đã cho.", file=sys.stderr)
        return 1
    main_tasks = None
    if args.main_tasks:
        main_tasks = sum(len(v) for v in read_task_spec(Path(args.main_tasks)).values())
    print(pilot_report(trials, load_metas(args.jobs), main_tasks, args.attempts))
    return 0


# ---------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    bp = sub.add_parser("build-payload")
    bp.add_argument("src")
    bp.add_argument("dst")
    bp.add_argument("--commit", required=True)
    sub.add_parser("datasets")
    fl = sub.add_parser("flatten")
    fl.add_argument("src")
    fl.add_argument("--out", required=True)
    lk = sub.add_parser("lock")
    lk.add_argument("dir")
    lk.add_argument("--name", required=True)
    lk.add_argument("--ref", default="")
    lk.add_argument("--lock", required=True)
    vt = sub.add_parser("vet")
    vt.add_argument("dir")
    vt.add_argument("--drop", action="store_true")
    vt.add_argument("--allow", help="compose-allow.txt (mặc định file cạnh script)")
    vc2 = sub.add_parser("vet-config")
    vc2.add_argument("config")
    vc2.add_argument("--root", default=".")
    vc2.add_argument("--allow")
    st = sub.add_parser("status")
    st.add_argument("job")
    pk = sub.add_parser("pick-swerebench")
    pk.add_argument("dir")
    pk.add_argument("--n", type=int, default=25)
    pk.add_argument("--seed", type=int, default=SEED)
    pk.add_argument("--month")
    mk = sub.add_parser("make-configs")
    mk.add_argument("--kind", choices=("pilot", "main", "oracle"), required=True)
    mk.add_argument("--name", required=True)
    mk.add_argument("--tasks", help="tasks-main.txt (bộ:tên mỗi dòng)")
    mk.add_argument("--swerebench", default="tasks-swerebench.txt")
    mk.add_argument("--attempts", type=int, default=1)
    mk.add_argument("--out", required=True)
    for key, val in DEFAULTS.items():
        mk.add_argument(f"--{key.replace('_', '-')}", dest=key, type=type(val), default=val, help=f"mặc định {val}")
    pl = sub.add_parser("plan")
    pl.add_argument("config")
    pl.add_argument("--root", default=".")
    mt = sub.add_parser("meta")
    mt.add_argument("config")
    mt.add_argument("--out", required=True)
    mt.add_argument("--payload", required=True)
    mt.add_argument("--root", default=".")
    vc = sub.add_parser("validate-config")
    vc.add_argument("config")
    wt = sub.add_parser("watch")
    wt.add_argument("job")
    wt.add_argument("--pid", type=int, required=True)
    wt.add_argument("--limit", type=int, default=3)
    wt.add_argument("--interval", type=float, default=60.0)
    ex = sub.add_parser("export")
    ex.add_argument("jobs", nargs="+")
    ex.add_argument("--out", required=True)
    ex.add_argument("--env-file", help="file .env có CLAUDE_CODE_OAUTH_TOKEN: che cả giá trị thật (không in)")
    rs = sub.add_parser("residual")
    rs.add_argument("dirs", nargs="+")
    rs.add_argument("--env-file")
    sub.add_parser("scrub")
    se = sub.add_parser("select")
    se.add_argument("datasets", help="thư mục chứa tblite/ và swerebench/")
    se.add_argument("--swerebench", required=True, help="tasks-swerebench.txt")
    se.add_argument("--levels", default=",".join(KEEP_LEVELS))
    se.add_argument("--out")
    pr = sub.add_parser("pilot-report")
    pr.add_argument("jobs", nargs="+")
    pr.add_argument("--main-tasks", help="tasks-main.txt, để ước chi phí job lớn")
    pr.add_argument("--attempts", type=int, default=1)
    cp = sub.add_parser("compare")
    cp.add_argument("jobs", nargs="+", help="thư mục job của Harbor (chứa */result.json)")
    cp.add_argument("--oracle", help="thư mục job chạy lời giải mẫu; việc mà lời giải mẫu không đạt bị loại")
    cp.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    if getattr(args, "attempts", 1) < 1:
        ap.error("--attempts phải từ 1")
    handlers = {"build-payload": cmd_build_payload, "datasets": cmd_datasets, "flatten": cmd_flatten, "lock": cmd_lock,
                "vet": cmd_vet, "vet-config": cmd_vet_config, "status": cmd_status, "pick-swerebench": cmd_pick_swerebench, "make-configs": cmd_make_configs,
                "plan": cmd_plan, "meta": cmd_meta, "validate-config": cmd_validate_config, "watch": cmd_watch,
                "export": cmd_export, "residual": cmd_residual, "scrub": cmd_scrub, "select": cmd_select,
                "pilot-report": cmd_pilot_report, "compare": cmd_compare}
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
