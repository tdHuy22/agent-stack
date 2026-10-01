#!/usr/bin/env python3
"""Thu thập tiến độ của một project (hoặc mọi project) và xếp hạng việc nên làm tiếp. Chỉ đọc.

Lệnh:
  collect.py [--project DIR] [--md | --json | --brief] [--gh]
  collect.py --all [THƯ_MỤC_GỐC] [--md | --json]

Thứ tự ưu tiên của "việc tiếp theo":
  1. chặn đường: xung đột merge, CI đỏ, test lệch mốc, file chưa commit quá 24 giờ
  2. dang dở: mục "Đang dở" và "Việc tiếp theo" trong §0, commit chưa push, PR đang chờ
  3. giai đoạn hiện tại: ô chưa tick đầu tiên
  4. nợ mới: TODO/FIXME trong các file vừa sửa
  5. bị bỏ quên: còn việc dở mà không hoạt động quá 14 ngày
"""
from __future__ import annotations

import argparse
import hashlib
import json
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


def last_test(root: Path):
    """Kết quả test gần nhất do skill verify ghi (state/tests/<băm đường dẫn>.json), nếu có."""
    name = hashlib.sha1(str(root).encode()).hexdigest()[:12] + ".json"
    return A.read_json(A.state_dir() / "tests" / name)


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
            "git": git, "todos": [], "sessions": recent_sessions(root), "test": last_test(root), "github": {}}
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
    test = d.get("test")
    if test and not test.get("ok"):
        actions.append((1, f"Sửa test đang lệch mốc: {A.clip(str(test.get('result')), 100)}", "kết quả test gần nhất không đạt"))
    if git.get("dirty") and dinfo.get("oldest") and time.time() - dinfo["oldest"] > DIRTY_STALE_HOURS * 3600:
        actions.append((1, f"Commit hoặc dọn {len(git['dirty'])} file chưa commit (cũ nhất {ago(dinfo['oldest'])})",
                        "thay đổi chưa commit lâu dễ bị mất"))
    if A.has_value(f.get("in_progress")):
        actions.append((2, f"Làm nốt: {A.clip(f['in_progress'], 160)}", "§0 ghi đang dở"))
    if sec.get("next"):
        actions.append((2, A.clip(sec["next"][0], 160), "bước đầu tiên trong \"Việc tiếp theo\" của §0"))
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
    unfinished = bool(sec.get("next")) or A.has_value(f.get("in_progress")) or bool(cur)
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


# ---------------------------------------------------------------- hiển thị

def route_text(item) -> str:
    r = item.get("route") or {}
    if not r:
        return ""
    bits = [r.get("model"), r.get("effort")] + ([r["agent"]] if r.get("agent") else [])
    return " · " + " · ".join(b for b in bits if b)


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


def scan_all(root: Path) -> list:
    rows = []
    for child in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        d = collect(child, use_gh=False, scan_todos=False)
        top = d["actions"][0] if d["actions"] else None
        rows.append({"project": child.name, "last_activity": d.get("last_activity"),
                     "progress": d.get("progress"), "dirty": len(d["git"].get("dirty", [])) if d["git"].get("is_repo") else None,
                     "has_plan": bool(d.get("plan")), "top": top, "warnings": warnings(d)})
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
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Tiến độ project và việc nên làm tiếp (chỉ đọc).")
    ap.add_argument("--project", default=".")
    ap.add_argument("--all", nargs="?", const="", metavar="ROOT", help="mọi thư mục con của ROOT")
    fmt = ap.add_mutually_exclusive_group()
    fmt.add_argument("--md", action="store_true")
    fmt.add_argument("--json", action="store_true")
    fmt.add_argument("--brief", action="store_true")
    ap.add_argument("--gh", action="store_true", help="lấy thêm PR và CI qua gh (cần mạng)")
    args = ap.parse_args(argv)
    if args.all is not None:
        home = A.home_dir()
        root = Path(args.all).expanduser() if args.all else (home.parent if home else Path.cwd())
        rows = scan_all(root.resolve())
        print(json.dumps(rows, ensure_ascii=False, indent=2, default=str) if args.json else render_all(rows), end="")
        return 0
    root = A.project_root(Path(args.project).expanduser().resolve())
    if args.brief:
        print(brief(root).get("context", ""))
        return 0
    data = collect(root, use_gh=args.gh)
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str) if args.json else render_md(data), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
