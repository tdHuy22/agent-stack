"""So file của plugin đã cài với bản đã kiểm duyệt trong .vet-cache (chỉ đọc, không chạy mã nào).

Marketplace chính thức tự cập nhật, nên plugin đã cài có thể đổi sang commit chưa qua vet-skill.
Khớp plugin với khóa trong vetted.lock qua catalog.json, rồi so từng file (sha256) với bản đã kiểm.

Trạng thái: match (giống hệt), drift (có file đổi, thêm, mất), unvetted (không có trong catalog
hoặc vetted.lock), unapproved (chưa được người dùng duyệt), no-snapshot (thiếu bản đã kiểm trong
.vet-cache), missing (thư mục cài không còn), own (plugin của chính agent-stack, bỏ qua).

Bản vá cục bộ đã duyệt (mục local_patches của vetted.lock, install.py áp lúc chép vào vendor/): file bị vá chỉ khớp
khi sha256 đúng bằng giá trị ghi trong lock; mọi file khác vẫn so với bản đã kiểm.

Với --remote (chạy tay, có mạng): thêm một dòng cho mỗi MCP từ xa trong catalog (mcp_remote.drift_rows): lấy lại
định nghĩa tool, so sha256 với bản đã duyệt; MCP scope user trong ~/.claude.json mà không qua catalog thì là unvetted.

Giới hạn: plugin `strict: false` lấy cấu hình (ví dụ lệnh LSP) từ marketplace.json của marketplace;
phần đó không nằm trong thư mục plugin nên không được so ở đây.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

# Chỉ đúng hai plugin này là của agent-stack; plugin khác trong marketplace vendor là của bên thứ ba.
OWN_PLUGINS = {"agent-stack@agent-stack-local", "agent-stack-vendor@agent-stack-vendor-local"}
# Dấu vết Claude Code hay vet.py để lại, không phải nội dung plugin.
IGNORED_NAMES = {".in_use", ".orphaned_at", ".git", ".vet-complete"}
OK_STATUSES = {"match", "own", "absent"}


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _digests(root: Path) -> dict:
    """Đường dẫn tương đối → sha256, bỏ các dấu vết trong IGNORED_NAMES."""
    out = {}
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(part in IGNORED_NAMES for part in rel.parts) or not path.is_file():
            continue
        out[rel.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def _is_digest(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def patched_files(entry: dict) -> dict:
    """Đường dẫn → sha256 sau khi vá (None là file bị bản vá xóa), gộp từ mọi bản vá của mục trong lock.
    Mục local_patches sai dạng thì ném ValueError, để plugin đó bị báo lỗi thay vì làm hỏng cả lượt kiểm."""
    patches = entry.get("local_patches") or []
    if not isinstance(patches, list):
        raise ValueError("local_patches không phải danh sách")
    out = {}
    for patch in patches:
        files = patch.get("files") if isinstance(patch, dict) else None
        if not isinstance(files, dict) or not all(
                isinstance(k, str) and k and (v is None or _is_digest(v)) for k, v in files.items()):
            raise ValueError("local_patches có bản vá thiếu hay sai mục files")
        out.update(files)
    return out


def compare(snapshot: Path, installed: Path, patched=None) -> dict:
    want, have = _digests(snapshot), _digests(installed)
    for name, digest in (patched or {}).items():
        if digest is None:
            want.pop(name, None)
        else:
            want[name] = digest
    return {
        "changed": sorted(k for k in want.keys() & have.keys() if want[k] != have[k]),
        "added": sorted(have.keys() - want.keys()),
        "removed": sorted(want.keys() - have.keys()),
    }


def check(home: Path, plugins_dir: Path) -> list:
    """Trả về một dòng kết quả cho mỗi plugin trong installed_plugins.json."""
    installed = _load(plugins_dir / "installed_plugins.json") or {}
    catalog = _load(home / "catalog.json") or {}
    entries = (_load(home / "vetted.lock") or {}).get("entries", {})
    keys = {f"{i['install']['plugin']}@{i['install']['marketplace']}": i["key"]
            for i in catalog.get("items", [])
            if i.get("kind") in ("claude-plugin", "vendor-plugin") and isinstance(i.get("install"), dict)}
    rows = []
    for pid, installs in sorted((installed.get("plugins") or {}).items()):
        for inst in installs or [{}]:
            row = {"plugin": pid, "version": inst.get("version"), "path": inst.get("installPath"),
                   "key": keys.get(pid)}
            rows.append(row)
            if pid in OWN_PLUGINS:
                row["status"] = "own"
                continue
            entry = entries.get(row["key"]) if row["key"] else None
            if not entry:
                row["status"] = "unvetted"
                continue
            row["vetted_sha"] = (entry.get("sha") or "")[:12]
            if (entry.get("human_review") or {}).get("status") != "approved":
                row["status"] = "unapproved"
                continue
            path = Path(row["path"] or "")
            if not row["path"] or not path.is_dir():
                row["status"] = "missing"
                continue
            snapshot = home / ".vet-cache" / Path(entry.get("report", "")).stem
            if entry.get("subpath"):
                snapshot = snapshot / entry["subpath"]
            if not entry.get("report") or not snapshot.is_dir():
                row["status"] = "no-snapshot"
                continue
            try:
                patched = patched_files(entry)
            except ValueError as exc:
                row["status"], row["error"] = "bad-lock", str(exc)
                continue
            diff = compare(snapshot, path, patched)
            row.update(diff)
            row["status"] = "drift" if any(diff.values()) else "match"
    return rows


LABELS = {
    "match": "khớp bản đã kiểm",
    "drift": "LỆCH bản đã kiểm",
    "unvetted": "chưa qua vet-skill (không có trong catalog.json hoặc vetted.lock)",
    "unapproved": "chưa được bạn duyệt trong vetted.lock",
    "no-snapshot": "thiếu bản đã kiểm trong .vet-cache (chạy lại vet.py scan)",
    "missing": "thư mục cài không còn",
    "own": "plugin của agent-stack, bỏ qua",
    "bad-lock": "mục trong vetted.lock sai dạng (local_patches); sửa lock rồi kiểm lại",
    "absent": "chưa cài",
    "url-mismatch": "URL trong ~/.claude.json khác URL đã duyệt",
    "unreachable": "không lấy được định nghĩa tool để so",
}


def render(rows: list, quiet: bool) -> str:
    """Bản tóm tắt dễ đọc; quiet thì chỉ in khi có vấn đề."""
    bad = [r for r in rows if r["status"] not in OK_STATUSES]
    if quiet and not bad:
        return ""
    lines = []
    for r in (bad if quiet else rows):
        meta = ", ".join(x for x in (f"bản {r['version']}" if r.get("version") else "",
                                      f"đã kiểm {r['vetted_sha']}" if r.get("vetted_sha") else "") if x)
        lines.append(f"{r['plugin']}{f' ({meta})' if meta else ''}: {LABELS[r['status']]}")
        for kind, label in (("changed", "đổi"), ("added", "thêm"), ("removed", "mất")):
            for name in r.get(kind, []):
                lines.append(f"  - {label}: {name}")
        if r.get("error") and r["status"] == "unreachable":
            lines.append(f"  - lỗi: {r['error']}")
    if any(not r["plugin"].startswith("MCP ") for r in bad):
        lines.append("Đừng dùng plugin lệch hay chưa duyệt khi chưa kiểm lại: "
                     "chạy vet.py scan <khóa> rồi đọc báo cáo, hoặc tắt plugin.")
    if any(r["plugin"].startswith("MCP ") for r in bad):
        lines.append("MCP lệch hay chưa duyệt: gỡ bằng `claude mcp remove -s user <tên>`, hoặc chạy vet.py scan <url> "
                     "rồi đọc báo cáo và duyệt lại.")
    return "\n".join(lines) + "\n"


def main_cli(args, home: Path) -> int:
    plugins_dir = Path(args.plugins_dir).expanduser() if args.plugins_dir else Path("~/.claude/plugins").expanduser()
    rows = check(home, plugins_dir)
    if getattr(args, "remote", False):
        import mcp_remote
        claude_json = Path(args.claude_json).expanduser() if args.claude_json else mcp_remote.claude_json_path()
        rows += mcp_remote.drift_rows(home, claude_json)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        text = render(rows, args.quiet)
        if text:
            print(text, end="")
    return 0 if all(r["status"] in OK_STATUSES for r in rows) else 1
