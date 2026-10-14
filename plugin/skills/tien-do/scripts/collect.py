#!/usr/bin/env python3
"""Thu thập tiến độ của một project (hoặc mọi project) và xếp hạng việc nên làm tiếp.

Lệnh:
  collect.py [--project DIR] [--md | --json | --brief] [--gh] [--no-snapshot]
  collect.py --all [THƯ_MỤC_GỐC] [--md | --json] [--no-snapshot]

Thứ tự ưu tiên của "việc tiếp theo":
  1. chặn đường: xung đột merge, CI đỏ, kiểm tra đang trượt, file chưa commit quá 24 giờ
  2. dang dở: mục "Đang dở" và "Việc tiếp theo" trong §0, commit chưa push, PR đang chờ
  3. giai đoạn hiện tại: ô chưa tick đầu tiên; kiểm tra đã đạt nhưng code đổi sau đó
  4. nợ mới: TODO/FIXME trong các file vừa sửa
  5. bị bỏ quên: còn việc dở mà không hoạt động quá 14 ngày

Chỉ đọc project, không ghi gì vào project. Mỗi lần báo (--md, --json, --all), script so với snapshot lần
báo trước và in thêm mục "Đổi từ lần trước" (commit mới, việc mới xong, mới phát sinh, biến mất), rồi ghi
snapshot mới vào state/tien-do/ của agent-stack (một file mỗi project). Chưa có snapshot, hoặc snapshot
hỏng, thì không in mục này. --no-snapshot: vẫn so nhưng không ghi, để chạy thử. --brief (hook SessionStart)
không so và không ghi.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3] / "lib"))
import agentstack as A  # noqa: E402

DIRTY_STALE_HOURS = 24
FORGOTTEN_DAYS = 14
TODO_WINDOW_DAYS = 14
# TODO chỉ tính khi nằm trong chú thích của file mã nguồn (không tính chữ "TODO" trong tài liệu).
TODO_RE = re.compile(r"(#|//|/\*|\*|--|;|%|<!--)\s*(TODO|FIXME|XXX|HACK)\b")
CODE_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".go", ".rs", ".c", ".h", ".cc", ".cpp", ".hpp",
            ".java", ".kt", ".swift", ".rb", ".php", ".sh", ".bash", ".zsh", ".lua", ".sql", ".r", ".m", ".scala",
            ".cs", ".dart", ".vue", ".svelte", ".sv", ".svh", ".v", ".vh", ".vhd", ".vhdl", ".tcl", ".yaml", ".yml",
            ".toml", ".ex", ".exs", ".hs", ".ml", ".jl", ".zig", ".nim"}
SKIP_DIRS = {"node_modules", ".git", ".venv", "venv", "dist", "build", "vendor", "third_party", "__pycache__",
             ".tmp", ".cache", ".vet-cache", "site-packages"}
TIER_LABEL = {1: "chặn đường", 2: "dang dở", 3: "giai đoạn hiện tại", 4: "nợ mới", 5: "bị bỏ quên"}

# Snapshot để báo "đổi từ lần trước": state/tien-do/<sha1 đường dẫn>.json, một file mỗi project.
SNAPSHOT_VERSION = 1
SNAPSHOT_DIR = "tien-do"
SNAPSHOT_MAX_BYTES = 1_000_000  # lớn hơn mức này thì coi là hỏng, không đọc
ITEM_WIDTH = 90  # độ dài tiêu đề mỗi việc lưu trong snapshot
KEY_LEN = 40  # số ký tự đầu (đã chuẩn hóa) dùng để nhận ra cùng một việc giữa hai lần
KEY_MIN_PREFIX = 8  # khóa ngắn hơn mức này chỉ khớp khi bằng nhau, tránh khớp nhầm
MAX_OPEN, MAX_DONE = 100, 300  # chặn kích thước snapshot với kế hoạch rất dài
SHOW_ITEMS = 3  # số việc tối đa in ra cho mỗi nhóm; phần còn lại ghi "(+N nữa)"
COMMIT_WIDTH = 60  # tiêu đề commit dài hơn mức này bị cắt
HEX_RE = re.compile(r"[0-9a-f]{4,40}")
BOX_RE = re.compile(r"^\s*[-*]\s+\[( |x|X)\]\s+(.*)$")


def ago(ts) -> str:
    if not ts:
        return "?"
    sec = max(0, time.time() - ts)
    if sec < 3600:
        return f"{int(sec // 60)} phút trước"
    if sec < 86400:
        return f"{int(sec // 3600)} giờ trước"
    return f"{int(sec // 86400)} ngày trước"


def router():
    """Gợi ý model/effort từ skill task-router nếu có (GĐ5); không có thì bỏ qua."""
    try:
        sys.path.insert(0, str(HERE.parents[2] / "task-router" / "scripts"))
        import route  # noqa: E402
        return route.suggest
    except ImportError:
        return None


# ---------------------------------------------------------------- tín hiệu

def dirty_info(root: Path, dirty: list) -> dict:
    mtimes, conflicts = [], []
    status = A.git_out(root, "status", "--porcelain=v1") or ""
    for line in status.splitlines():
        if line[:2] in ("UU", "AA", "DD", "AU", "UA", "DU", "UD"):
            conflicts.append(line[3:])
    for item in dirty:
        path = root / item.split(" -> ")[-1].strip().strip('"')
        try:
            if path.is_file():
                mtimes.append(path.stat().st_mtime)
            elif path.is_dir():
                mtimes.extend(p.stat().st_mtime for p in list(path.rglob("*"))[:200] if p.is_file())
        except OSError:
            pass
    return {"oldest": min(mtimes) if mtimes else None, "newest": max(mtimes) if mtimes else None,
            "conflicts": conflicts}


def unmerged_branches(root: Path, current: str) -> list:
    out = A.git_out(root, "branch", "--format=%(refname:short)", "--no-merged", current or "HEAD") or ""
    return [b for b in out.split() if b][:5]


def recent_todos(root: Path, git: dict, limit: int = 8) -> list:
    """TODO/FIXME chỉ trong các file vừa sửa (14 ngày hoặc đang chưa commit), để tránh nhiễu từ code bên thứ ba."""
    names = set()
    if git.get("is_repo"):
        log = A.git_out(root, "log", f"--since={TODO_WINDOW_DAYS}.days", "--name-only", "--pretty=format:") or ""
        names |= {n.strip() for n in log.splitlines() if n.strip()}
        names |= {d.split(" -> ")[-1].strip().strip('"') for d in git.get("dirty", [])}
    else:
        cutoff = time.time() - TODO_WINDOW_DAYS * 86400
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
            for name in filenames:
                path = Path(dirpath) / name
                try:
                    if path.stat().st_mtime >= cutoff:
                        names.add(str(path.relative_to(root)))
                except OSError:
                    pass
            if len(names) > 300:
                break
    hits = []
    for name in sorted(names)[:300]:
        if any(part in SKIP_DIRS for part in Path(name).parts):
            continue
        path = root / name
        if path.suffix.lower() not in CODE_EXT:
            continue
        try:
            if not path.is_file() or path.stat().st_size > 1_000_000:
                continue
            for no, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                m = TODO_RE.search(line)
                if m and not in_string(line[:m.start()]):
                    hits.append({"file": name, "line": no, "text": A.clip(line.strip(), 120)})
                    if len(hits) >= limit:
                        return hits
        except OSError:
            continue
    return hits


def in_string(prefix: str) -> bool:
    """Ký hiệu chú thích đứng sau số lẻ dấu nháy thì đang nằm trong chuỗi, không phải chú thích thật."""
    return prefix.count('"') % 2 == 1 or prefix.count("'") % 2 == 1


def recent_sessions(root: Path, limit: int = 3) -> list:
    """Phiên gần đây của project, từ nhật ký mà hook SessionStart/SessionEnd ghi."""
    path = A.state_dir() / "sessions.jsonl"
    rows = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-2000:]
    except OSError:
        return rows
    seen = set()
    for line in reversed(lines):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("cwd") != str(root) or not rec.get("session") or rec["session"] in seen:
            continue
        seen.add(rec["session"])
        rows.append({"session": rec["session"], "ts": rec.get("ts"), "kind": rec.get("kind"),
                     "reason": rec.get("reason")})
        if len(rows) >= limit:
            break
    return rows


def last_tests(root: Path) -> dict:
    """Biên nhận kiểm tra do session-keeper/scripts/receipt.py ghi, kèm cờ fresh (còn khớp code không)."""
    return A.receipt_status(root)


def github_signals(root: Path) -> dict:
    remote = A.git_out(root, "remote", "get-url", "origin") or ""
    if "github.com" not in remote:
        return {}
    def gh(*args):
        try:
            out = subprocess.run(["gh", *args], cwd=str(root), capture_output=True, text=True, timeout=10)
            return json.loads(out.stdout) if out.returncode == 0 and out.stdout.strip() else None
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return None
    prs = gh("pr", "list", "--author", "@me", "--state", "open", "--limit", "5",
             "--json", "number,title,isDraft,reviewDecision,statusCheckRollup") or []
    runs = gh("run", "list", "--limit", "1", "--json", "status,conclusion,name,headBranch") or []
    return {"prs": prs, "last_run": runs[0] if runs else None}


# ---------------------------------------------------------------- tổng hợp

def collect(root: Path, use_gh: bool = False, scan_todos: bool = True) -> dict:
    found = A.read_plan(root)
    git = A.git_summary(root)
    data = {"project": root.name, "root": str(root), "plan": None, "section0": None, "progress": None,
            "git": git, "todos": [], "sessions": recent_sessions(root), "tests": last_tests(root), "github": {}}
    activity = []
    if found:
        path, text, sec = found
        data.update(plan=str(path), section0=sec, progress=A.checkbox_progress(text),
                    baseline=sec["fields"].get("checks") or A.baseline_anywhere(text))
        try:
            data["plan_mtime"] = path.stat().st_mtime
            activity.append(data["plan_mtime"])
        except OSError:
            pass
    if git.get("is_repo"):
        data["dirty_info"] = dirty_info(root, git["dirty"])
        data["unmerged"] = unmerged_branches(root, git.get("branch", ""))
        if git.get("last_commit_ts"):
            activity.append(git["last_commit_ts"])
        if data["dirty_info"]["newest"]:
            activity.append(data["dirty_info"]["newest"])
    if scan_todos:
        data["todos"] = recent_todos(root, git)
    if use_gh and git.get("is_repo"):
        data["github"] = github_signals(root)
    data["last_activity"] = max(activity) if activity else None
    data["actions"] = rank(data)
    return data


def rank(d: dict) -> list:
    actions = []
    sec = d.get("section0") or {"fields": {}, "next": []}
    f = sec["fields"]
    git, dinfo = d["git"], d.get("dirty_info") or {}
    if dinfo.get("conflicts"):
        actions.append((1, f"Giải quyết xung đột merge ở {len(dinfo['conflicts'])} file", "repo đang có xung đột"))
    run = (d.get("github") or {}).get("last_run")
    if run and run.get("conclusion") == "failure":
        actions.append((1, f"Sửa CI đang đỏ ({run.get('name')} trên {run.get('headBranch')})", "lần chạy CI gần nhất thất bại"))
    tests = d.get("tests") or {}
    for label, rec in tests.items():
        if rec.get("ok"):
            continue
        detail = f": {A.clip(rec['summary'], 80)}" if rec.get("summary") else ""
        if rec.get("fresh") is False:
            actions.append((1, f"Chạy lại kiểm tra `{label}`: lần gần nhất trượt{detail}, code đã đổi sau đó",
                            "chưa biết bản sửa có làm kiểm tra đạt lại không"))
        else:
            actions.append((1, f"Sửa kiểm tra đang trượt `{label}`{detail}", "lần chạy gần nhất trượt và code chưa đổi từ đó"))
    stale = sorted(label for label, rec in tests.items() if rec.get("ok") and rec.get("fresh") is False)
    if stale:
        actions.append((3, "Chạy lại mốc kiểm tra: " + ", ".join(f"`{x}`" for x in stale[:3]),
                        "code đã đổi sau lần đạt gần nhất; kết quả cũ không chứng minh cho code mới"))
    if git.get("dirty") and dinfo.get("oldest") and time.time() - dinfo["oldest"] > DIRTY_STALE_HOURS * 3600:
        actions.append((1, f"Commit hoặc dọn {len(git['dirty'])} file chưa commit (cũ nhất {ago(dinfo['oldest'])})",
                        "thay đổi chưa commit lâu dễ bị mất"))
    if A.has_value(f.get("in_progress")):
        actions.append((2, f"Làm nốt: {A.clip(f['in_progress'], 160)}", "§0 ghi đang dở"))
    steps = A.next_open(sec)
    if steps:
        actions.append((2, A.clip(steps[0], 160), "bước đầu tiên chưa xong trong \"Việc tiếp theo\" của §0"))
    if git.get("ahead"):
        actions.append((2, f"Push {git['ahead']} commit trên nhánh {git['branch']}", "có commit chưa push"))
    for pr in (d.get("github") or {}).get("prs", []):
        if pr.get("reviewDecision") == "CHANGES_REQUESTED":
            actions.append((2, f"Xử lý góp ý ở PR #{pr['number']}: {A.clip(pr['title'], 80)}", "PR được yêu cầu sửa"))
    prog = d.get("progress") or {}
    cur = prog.get("current")
    if cur and cur.get("first_todo") and not any(cur["first_todo"][:40] in a[1] for a in actions):
        actions.append((3, cur["first_todo"], f"giai đoạn \"{cur['title']}\" ({cur['done']}/{cur['done'] + cur['todo']})"))
    if d.get("todos"):
        t = d["todos"][0]
        actions.append((4, f"Xem {len(d['todos'])} TODO/FIXME mới, ví dụ {t['file']}:{t['line']}", "nợ kỹ thuật vừa phát sinh"))
    unfinished = bool(steps) or A.has_value(f.get("in_progress")) or bool(cur)
    if unfinished and d.get("last_activity") and time.time() - d["last_activity"] > FORGOTTEN_DAYS * 86400:
        actions.append((5, "Quyết định: làm tiếp, tạm dừng hay đóng project này",
                        f"còn việc dở nhưng không hoạt động từ {ago(d['last_activity'])}"))
    suggest = router()
    out = []
    for tier, text, why in sorted(actions, key=lambda a: a[0]):
        item = {"tier": tier, "label": TIER_LABEL[tier], "text": text, "why": why}
        if suggest:
            try:
                item["route"] = suggest(text)
            except Exception:  # noqa: BLE001
                pass
        out.append(item)
    return out


def warnings(d: dict) -> list:
    out = []
    git = d["git"]
    if d.get("plan_mtime") and git.get("last_commit_ts") and d["plan_mtime"] + 600 < git["last_commit_ts"]:
        out.append("file kế hoạch cập nhật trước commit gần nhất, §0 có thể đã cũ")
    sec = d.get("section0") or {}
    if d.get("plan") and not sec.get("heading"):
        out.append("file kế hoạch chưa có mục §0 \"Đang ở đâu, việc tiếp theo\"")
    if d.get("unmerged"):
        out.append("nhánh chưa merge: " + ", ".join(d["unmerged"]))
    if git.get("stash"):
        out.append(f"{git['stash']} stash đang treo")
    return out


def goal_hint(d: dict):
    baseline = d.get("baseline")
    if not baseline or not d.get("actions"):
        return None
    plain = A.clip(baseline.replace("`", ""), 120).rstrip(".")
    return f"/goal mốc kiểm tra đạt ({plain}), git status sạch, và §0 đã cập nhật"


# ---------------------------------------------------------------- so với lần báo trước (snapshot)

def snapshot_path(root: Path) -> Path:
    """File snapshot của project, khóa theo đường dẫn tuyệt đối đã chuẩn hóa (cùng quy ước với biên nhận)."""
    real = os.path.realpath(str(root))
    return A.state_dir() / SNAPSHOT_DIR / (hashlib.sha1(real.encode("utf-8", "surrogateescape")).hexdigest()[:12] + ".json")


def item_key(title: str) -> str:
    """Khóa nhận ra cùng một việc giữa hai lần: chữ thường, bỏ dấu và dấu câu, chỉ lấy phần đầu.
    Nhờ vậy tick ô, thêm đuôi "Xong 02/10" hay sửa phần cuối câu không biến việc cũ thành việc mới."""
    text = A.fold(A.strip_md(title.replace("~~", " ")))
    return re.sub(r"\W+", " ", text).strip()[:KEY_LEN].strip()


def same_item(a: str, b: str) -> bool:
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    return len(short) >= KEY_MIN_PREFIX and long_.startswith(short)


def matches(key: str, keys: list) -> bool:
    return any(same_item(key, other) for other in keys)


def step_title(raw: str):
    """(tiêu đề, đã xong?) của một bước trong "Việc tiếp theo": bước bị gạch (~~...~~) hay đánh ✅ là đã xong."""
    raw = raw.strip()
    if raw.startswith("~~"):
        return raw[2:].split("~~", 1)[0].strip(), True
    return raw, A.step_done(raw)


def section0_done(text: str) -> list:
    """Các mục Xong của §0: mục con cấp 1 dưới nhãn "Xong"; không có mục con thì phần chữ ngay sau nhãn."""
    return A.section0_items(text, "done")


def tidy_titles(items: list, cap: int) -> list:
    """Tiêu đề gọn, bỏ trống và trùng, giữ thứ tự, tối đa `cap` mục."""
    seen, out = set(), []
    for raw in items:
        title = A.clip(raw, ITEM_WIDTH)
        if title and title not in seen:
            seen.add(title)
            out.append(title)
    return out[:cap]


def plan_items(data: dict):
    """(còn mở, đã xong, số mục §0) của file kế hoạch mà collect() đã đọc.
    Còn mở: ô chưa tick, mục Đang dở, bước chưa xong trong Việc tiếp theo (bỏ mục con của bước đã xong).
    Đã xong: ô đã tick, mục Xong của §0, bước đã gạch (~~...~~) hay đánh ✅."""
    text = ""
    if data.get("plan"):
        try:
            text = Path(data["plan"]).read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
    boxes = {True: [], False: []}
    for line in text.splitlines():
        box = BOX_RE.match(line)
        if box:
            boxes[bool(box.group(1).strip())].append(box.group(2))
    sec = data.get("section0") or {}
    wip = (sec.get("fields") or {}).get("in_progress")
    wip = [wip] if A.has_value(wip) else []
    steps = [step_title(s) for s in sec.get("next") or []]
    s0_done = section0_done(text)
    still_open = boxes[False] + wip + A.next_open(sec)
    finished = boxes[True] + s0_done + [t for t, done in steps if done]
    counts = {"done": len(s0_done), "in_progress": len(wip), "next": len(steps)}
    return tidy_titles(still_open, MAX_OPEN), tidy_titles(finished, MAX_DONE), counts


def build_snapshot(root: Path, data: dict) -> dict:
    """Dữ kiện nhỏ đủ để so sánh lần sau: HEAD ngắn, nhánh, giai đoạn hiện tại, số mục §0, tiêu đề từng việc."""
    git = data.get("git") or {}
    head = None
    if git.get("is_repo"):
        out = (A.git_out(root, "rev-parse", "--short", "HEAD") or "").strip()
        head = out if HEX_RE.fullmatch(out) else None
    prog = data.get("progress") or {}
    cur = prog.get("current")
    plan = None
    if data.get("plan"):
        try:
            plan = Path(data["plan"]).relative_to(root).as_posix()
        except ValueError:
            plan = Path(data["plan"]).name
    still_open, finished, counts = plan_items(data)
    return {"v": SNAPSHOT_VERSION, "root": os.path.realpath(str(root)), "ts": time.time(), "head": head,
            "branch": git.get("branch") or None, "plan": plan,
            "phase": {"title": cur["title"], "done": cur["done"], "total": cur["done"] + cur["todo"]} if cur else None,
            "checkbox": {"done": prog.get("done", 0), "total": prog.get("total", 0)},
            "section0": counts, "open": still_open, "done": finished}


def clean_snapshot(raw, root: Path):
    """Snapshot đã kiểm định dạng, hoặc None nếu hỏng, sai phiên bản hay của project khác.
    head chỉ nhận chuỗi hex: giá trị này về sau được đưa vào lệnh git nên không được là tùy chọn dòng lệnh."""
    if not isinstance(raw, dict) or raw.get("root") != os.path.realpath(str(root)):
        return None
    version = raw.get("v")
    if isinstance(version, bool) or version != SNAPSHOT_VERSION:
        return None
    ts = raw.get("ts")
    if isinstance(ts, bool) or not isinstance(ts, (int, float)) or not math.isfinite(ts) or not 0 < ts < 32503680000:
        return None
    for key, cap in (("open", MAX_OPEN), ("done", MAX_DONE)):  # vượt mức bản ghi của chính script là bất thường
        items = raw.get(key)
        if not isinstance(items, list) or len(items) > cap:
            return None
        if not all(isinstance(x, str) and len(x) <= 4 * ITEM_WIDTH for x in items):
            return None
    head = raw.get("head")
    if head is not None and not (isinstance(head, str) and HEX_RE.fullmatch(head)):
        return None
    if any(raw.get(key) is not None and not isinstance(raw[key], str) for key in ("branch", "plan")):
        return None
    phase = raw.get("phase")
    if phase is not None and not (isinstance(phase, dict) and isinstance(phase.get("title"), str)):
        return None
    return raw


def load_snapshot(root: Path):
    """Snapshot lần trước của project, hoặc None nếu thiếu, hỏng, quá lớn hay sai định dạng."""
    try:
        path = snapshot_path(root)
        if path.stat().st_size > SNAPSHOT_MAX_BYTES:
            return None
        return clean_snapshot(A.read_json(path), root)
    except Exception:  # noqa: BLE001 - snapshot hỏng không được làm hỏng báo cáo
        return None


def save_snapshot(root: Path, snap: dict) -> bool:
    try:
        path = snapshot_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        A.write_json_atomic(path, snap)
        return True
    except (OSError, ValueError, TypeError):
        return False


def uniq(items) -> list:
    return list(dict.fromkeys(items))


def same_commit(a, b) -> bool:
    """Hai hash rút gọn của cùng một commit: git tự dài thêm độ dài khi repo lớn lên, nên so theo tiền tố."""
    return a == b or bool(a and b and (a.startswith(b) or b.startswith(a)))


def diff_snapshots(old: dict, new: dict) -> dict:
    """So hai snapshot hợp lệ: HEAD, nhánh, giai đoạn, file kế hoạch, và việc mới xong, mới phát sinh, biến mất.
    Mới xong: đã xong bây giờ mà lần trước chưa. Mới phát sinh: đang mở mà lần trước không mở.
    Biến mất: lần trước còn mở, bây giờ không còn (không mở, cũng không thấy đã xong).
    Mục Xong bị gộp hay xóa khỏi kế hoạch không tính. Đổi sang file kế hoạch khác thì không so từng việc."""
    ch = {"since": old["ts"], "head": None, "branch": None, "phase": None, "plan": None, "commits": None,
          "done": [], "new": [], "gone": []}
    if not same_commit(old.get("head"), new.get("head")):
        ch["head"] = {"old": old.get("head"), "new": new.get("head")}
    if old.get("branch") != new.get("branch"):
        ch["branch"] = {"old": old.get("branch"), "new": new.get("branch")}
    if old.get("plan") != new.get("plan"):
        ch["plan"] = {"old": old.get("plan"), "new": new.get("plan")}
    else:
        before = (old.get("phase") or {}).get("title")
        after = (new.get("phase") or {}).get("title")
        if before != after:
            ch["phase"] = {"old": before, "new": after}
        old_open = [item_key(t) for t in old["open"]]
        old_done = [item_key(t) for t in old["done"]]
        now = [item_key(t) for t in new["open"] + new["done"]]
        ch["done"] = uniq(t for t in new["done"] if not matches(item_key(t), old_done))
        ch["new"] = uniq(t for t in new["open"] if not matches(item_key(t), old_open))
        ch["gone"] = uniq(t for t in old["open"] if not matches(item_key(t), now))
    ch["changed"] = any(ch[k] for k in ("head", "branch", "phase", "plan", "done", "new", "gone"))
    return ch


def commit_log(root: Path, old_head, new_head, limit: int = SHOW_ITEMS):
    """Commit có trong new_head mà không có trong old_head: {"count", "log": [{"sha", "subject"}]}.
    None nếu git không so được (HEAD cũ đã mất sau rebase hay gc). Chỉ nhận head dạng hex."""
    if not all(isinstance(h, str) and HEX_RE.fullmatch(h) for h in (old_head, new_head)):
        return None
    span = f"{old_head}..{new_head}"
    count = (A.git_out(root, "rev-list", "--count", span, "--") or "").strip()
    if not count.isdigit():
        return None
    log = A.git_out(root, "log", f"--max-count={limit}", "--format=%h%x09%s", span, "--") or ""
    rows = [ln.split("\t", 1) for ln in log.splitlines() if "\t" in ln]
    return {"count": int(count), "log": [{"sha": sha, "subject": A.clip(subject, COMMIT_WIDTH)} for sha, subject in rows]}


def track_changes(root: Path, data: dict, save: bool = True):
    """So báo cáo hiện tại với snapshot lần trước, rồi (nếu save) ghi snapshot mới.
    Trả về dict thay đổi, hoặc None khi chưa có snapshot dùng được (lần đầu, hỏng, sai định dạng)
    hay đây không phải project (không có kế hoạch, không phải git repo). Mọi lỗi đều được nuốt."""
    if not (data.get("plan") or (data.get("git") or {}).get("is_repo")):
        return None
    changes, new = None, None
    try:
        new = build_snapshot(root, data)
        old = load_snapshot(root)
        if old:
            changes = diff_snapshots(old, new)
            if changes["head"]:
                changes["commits"] = commit_log(root, old.get("head"), new.get("head"))
    except Exception:  # noqa: BLE001 - phần so sánh không được làm hỏng báo cáo chính
        changes = None
    if save and new:
        save_snapshot(root, new)
    return changes


# ---------------------------------------------------------------- hiển thị

def route_text(item) -> str:
    r = item.get("route") or {}
    if not r:
        return ""
    # model_id: tên gõ được vào /model (vd claude-haiku-5-5 thay cho alias haiku còn trỏ bản cũ)
    bits = [r.get("model_id") or r.get("model"), r.get("effort")] + ([r["agent"]] if r.get("agent") else [])
    return " · " + " · ".join(b for b in bits if b)


def when_text(ts: float) -> str:
    return f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(ts))}, {ago(ts)}"


def list_text(items: list) -> str:
    """Tối đa SHOW_ITEMS tiêu đề, cắt gọn; phần còn lại ghi (+N nữa)."""
    text = "; ".join(A.clip(t, 70) for t in items[:SHOW_ITEMS])
    return text + (f" (+{len(items) - SHOW_ITEMS} nữa)" if len(items) > SHOW_ITEMS else "")


def commit_line(ch: dict):
    """Dòng về git của mục "Đổi từ lần trước": commit mới, HEAD đổi mà không có commit mới, hay đổi nhánh."""
    head, branch, commits = ch.get("head"), ch.get("branch"), ch.get("commits")
    moved = f"`{branch['old'] or '?'}` → `{branch['new'] or '?'}`" if branch else ""
    if not head:
        return f"Nhánh đổi: {moved}" if branch else None
    if commits and commits["count"]:
        shown = [f"`{c['sha']}` {c['subject']}" for c in commits["log"]]
        if shown and commits["count"] > len(shown):
            shown.append(f"+{commits['count'] - len(shown)} nữa")
        text = f"Commit mới: {commits['count']}" + (f" ({'; '.join(shown)})" if shown else "")
    else:
        span = f"`{head.get('old') or 'chưa có'}` → `{head.get('new') or 'chưa có'}`"
        why = "không có commit mới: đã lùi hoặc đổi nhánh" if commits else "không so được lịch sử"
        text = f"HEAD đổi: {span} ({why})"
    return f"{text} · nhánh {moved}" if moved else text


def render_changes(ch: dict) -> list:
    """Mục "Đổi từ lần trước". Không có gì đổi thì đúng một dòng; có thì tiêu đề cộng tối đa vài dòng ngắn."""
    lines = []
    commit = commit_line(ch)
    if commit:
        lines.append(f"- {commit}")
    for label, key in (("Mới xong", "done"), ("Mới phát sinh", "new"), ("Biến mất", "gone")):
        if ch.get(key):
            lines.append(f"- {label}: {list_text(ch[key])}")
    if ch.get("phase"):
        lines.append(f"- Giai đoạn hiện tại: {A.clip(ch['phase']['old'] or '(không có)', 50)} → "
                     f"{A.clip(ch['phase']['new'] or '(không có)', 50)}")
    if ch.get("plan"):
        lines.append(f"- Kế hoạch: `{ch['plan']['old'] or '(không có)'}` → `{ch['plan']['new'] or '(không có)'}` "
                     "(không so được từng việc)")
    when = when_text(ch["since"])
    if not lines:
        return [f"Đổi từ lần trước ({when}): không có gì đổi."]
    return [f"### Đổi từ lần trước ({when})", ""] + lines


def count_text(count: int, label: str, first: str) -> str:
    """"3 xong (việc đầu; +2 nữa)": số lượng kèm việc đầu tiên, vì mốc so sánh đã dời nên không xem lại được."""
    return f"{count} {label} ({A.clip(first, 45)}{f'; +{count - 1} nữa' if count > 1 else ''})"


def change_summary(ch: dict) -> str:
    """Tóm tắt một dòng cho chế độ --all: số lượng và việc đầu tiên của từng nhóm."""
    commits = ch.get("commits")
    parts = []
    if commits and commits["count"]:
        parts.append(count_text(commits["count"], "commit mới", commits["log"][0]["subject"]) if commits["log"]
                     else f"{commits['count']} commit mới")
    elif ch.get("head"):
        parts.append("HEAD đổi")
    elif ch.get("branch"):
        parts.append("đổi nhánh")
    for key, label in (("done", "xong"), ("new", "phát sinh"), ("gone", "biến mất")):
        if ch.get(key):
            parts.append(count_text(len(ch[key]), label, ch[key][0]))
    if ch.get("phase"):
        parts.append("đổi giai đoạn")
    if ch.get("plan"):
        parts.append("đổi file kế hoạch")
    return "; ".join(parts)


def render_all_changes(rows: list) -> list:
    """Mục "Đổi từ lần trước" cho --all: mỗi project đã đổi một dòng, project không đổi chỉ nêu tên."""
    tracked = [r for r in rows if r.get("changes")]
    if not tracked:
        return []
    changed = [r for r in tracked if r["changes"]["changed"]]
    if not changed:
        return ["", "Đổi từ lần trước: không project nào đổi."]
    lines = ["", "### Đổi từ lần trước", ""]
    for r in changed:
        lines.append(f"- **{r['project']}** ({ago(r['changes']['since'])}): {change_summary(r['changes'])}")
    quiet = [r["project"] for r in tracked if not r["changes"]["changed"]]
    if quiet:
        lines.append("- Không đổi: " + ", ".join(quiet[:5]) + (f" (+{len(quiet) - 5} project nữa)" if len(quiet) > 5 else ""))
    return lines


def render_md(d: dict) -> str:
    sec = d.get("section0") or {}
    prog = d.get("progress") or {}
    git = d["git"]
    L = [f"## Tiến độ: {d['project']}", ""]
    meta = []
    if d.get("plan"):
        meta.append(f"kế hoạch `{Path(d['plan']).name}`" + (f" (cập nhật {sec['updated']})" if sec.get("updated") else ""))
    else:
        meta.append("chưa có file kế hoạch")
    if git.get("is_repo"):
        meta.append(f"nhánh `{git['branch']}`, {len(git['dirty'])} file chưa commit")
    meta.append(f"hoạt động gần nhất {ago(d.get('last_activity'))}")
    L.append("- " + " · ".join(meta))
    if prog.get("total"):
        cur = prog.get("current")
        L.append(f"- Checkbox: {prog['done']}/{prog['total']}" + (f"; giai đoạn hiện tại: {cur['title']}" if cur else "; đã xong hết"))
    if A.has_value((sec.get("fields") or {}).get("in_progress")):
        L.append(f"- Đang dở: {sec['fields']['in_progress']}")
    if d.get("baseline"):
        L.append(f"- Mốc kiểm tra: {d['baseline']}")
    for label, rec in sorted((d.get("tests") or {}).items(), key=lambda kv: kv[1].get("ts", ""), reverse=True)[:3]:
        mark = "✓ đạt" if rec.get("ok") else f"✗ trượt (mã {rec.get('exit')})"
        fresh = {True: "còn khớp code hiện tại", False: "code đã đổi sau đó",
                 None: "không rõ code có đổi sau đó không"}[rec.get("fresh")]
        L.append(f"- Kiểm tra `{label}`: {mark}, {rec.get('ts', '?')[:16].replace('T', ' ')}, {fresh}")
    if d.get("changes"):
        L += [""] + render_changes(d["changes"])
    L += ["", "### Việc nên làm tiếp", ""]
    if d["actions"]:
        for i, a in enumerate(d["actions"][:6], 1):
            L.append(f"{i}. **[{a['label']}]** {a['text']}{route_text(a)}  \n   _Vì sao:_ {a['why']}")
    else:
        L.append("Không thấy việc dở nào. Nếu project còn việc, thêm mục §0 bằng skill session-keeper.")
    warn = warnings(d)
    if warn:
        L += ["", "### Cảnh báo", ""] + [f"- {w}" for w in warn]
    if d.get("todos"):
        L += ["", "### TODO/FIXME mới", ""] + [f"- `{t['file']}:{t['line']}` {t['text']}" for t in d["todos"]]
    if d.get("sessions"):
        L += ["", "### Phiên gần đây", ""] + [f"- `{s['session']}` ({s['kind']}, {s['ts']}) → `claude --resume {s['session']}`"
                                                for s in d["sessions"]]
    hint = goal_hint(d)
    if hint:
        L += ["", "Gợi ý goal để làm nốt việc dang dở (bạn tự chạy nếu đồng ý):", "", "```", hint, "```"]
    return "\n".join(L) + "\n"


def brief(root: Path) -> dict:
    """Bản tóm tắt cho hook SessionStart: bản của thư viện, thêm các cảnh báo nhanh (không gọi mạng)."""
    base = A.brief(root)
    if not base:
        return {}
    d = collect(root, use_gh=False, scan_todos=False)
    extra = [f"- Chặn đường: {a['text']}" for a in d["actions"] if a["tier"] == 1][:2]
    extra += [f"- Cảnh báo: {w}" for w in warnings(d) if "§0 có thể đã cũ" not in w][:2]
    if extra:
        lines = base["context"].splitlines()
        base["context"] = "\n".join(lines[:-1] + extra + lines[-1:])
        blocker = next((a for a in d["actions"] if a["tier"] == 1), None)
        if blocker:
            base["user"] += f" · ⚠️ {A.clip(blocker['text'], 70)}"
    return base


def scan_all(root: Path, save: bool = True) -> list:
    """Một dòng mỗi thư mục con; mỗi project được so và ghi snapshot riêng (save=False thì chỉ so)."""
    rows = []
    for child in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        d = collect(child, use_gh=False, scan_todos=False)
        top = d["actions"][0] if d["actions"] else None
        rows.append({"project": child.name, "last_activity": d.get("last_activity"),
                     "progress": d.get("progress"), "dirty": len(d["git"].get("dirty", [])) if d["git"].get("is_repo") else None,
                     "has_plan": bool(d.get("plan")), "top": top, "warnings": warnings(d),
                     "changes": track_changes(child, d, save=save)})
    rows.sort(key=lambda r: -(r["last_activity"] or 0))
    return rows


def render_all(rows: list) -> str:
    L = ["## Tổng quan các project", "", "| Project | Hoạt động | Tiến độ | Chưa commit | Việc nên làm tiếp | Cảnh báo |",
         "|---|---|---|---:|---|---|"]
    for r in rows:
        prog = r["progress"] or {}
        pct = f"{prog['done']}/{prog['total']}" if prog.get("total") else ("—" if r["has_plan"] else "chưa có kế hoạch")
        top = f"[{r['top']['label']}] {A.clip(r['top']['text'], 70)}" if r["top"] else "—"
        dirty = "—" if r["dirty"] is None else str(r["dirty"])
        L.append(f"| {r['project']} | {ago(r['last_activity'])} | {pct} | {dirty} | {top} | {'; '.join(r['warnings'])[:80]} |")
    L += render_all_changes(rows)
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Tiến độ project và việc nên làm tiếp. Chỉ đọc project; "
                                             "chỉ ghi snapshot nhỏ vào state/ của agent-stack.")
    ap.add_argument("--project", default=".")
    ap.add_argument("--all", nargs="?", const="", metavar="ROOT", help="mọi thư mục con của ROOT")
    fmt = ap.add_mutually_exclusive_group()
    fmt.add_argument("--md", action="store_true")
    fmt.add_argument("--json", action="store_true")
    fmt.add_argument("--brief", action="store_true")
    ap.add_argument("--gh", action="store_true", help="lấy thêm PR và CI qua gh (cần mạng)")
    ap.add_argument("--no-snapshot", action="store_true",
                    help="không ghi snapshot (chạy thử); vẫn so với snapshot lần trước nếu có")
    args = ap.parse_args(argv)
    if args.all is not None:
        home = A.home_dir()
        root = Path(args.all).expanduser() if args.all else (home.parent if home else Path.cwd())
        rows = scan_all(root.resolve(), save=not args.no_snapshot)
        print(json.dumps(rows, ensure_ascii=False, indent=2, default=str) if args.json else render_all(rows), end="")
        return 0
    root = A.project_root(Path(args.project).expanduser().resolve())
    if args.brief:
        print(brief(root).get("context", ""))
        return 0
    data = collect(root, use_gh=args.gh)
    data["changes"] = track_changes(root, data, save=not args.no_snapshot)
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str) if args.json else render_md(data), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
