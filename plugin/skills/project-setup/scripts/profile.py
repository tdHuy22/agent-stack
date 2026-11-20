#!/usr/bin/env python3
"""Công tắc bộ plugin theo project (việc G mục 1, 19/11/2026): "gọn" ↔ "đủ", mỗi chiều một lệnh.

"gọn" ghi vào `<project>/.claude/settings.local.json` (phạm vi local của Claude Code, đè cài đặt user và project):
  - `enabledPlugins[<id>] = false` cho plugin ít dùng: plugin không nạp skill, subagent, hook của nó;
  - `skillOverrides[<tên>] = "name-only"` cho skill ít dùng: skill chỉ còn tên trong danh sách nạp sẵn, bỏ mô tả, vẫn
    gọi được bằng tên.
"đủ" trả đúng giá trị cũ của các khóa "gọn" đã đổi (khóa người dùng tự đổi sau đó thì giữ). Giá trị cũ nằm ở
`state/profiles/` của agent-stack, ngoài repo. Có hiệu lực từ phiên mới (Claude Code đọc cài đặt lúc mở phiên).

Danh sách lấy từ `profiles.gon.plugins_off` và `profiles.gon.skills_name_only` của `.agent/stack.json`; không có thì
dùng mặc định dưới. stack.json nằm trong repo nên không tin được (TM-154): plugin agent-stack (chứa hook chặn) không
bao giờ bị tắt, skill chỉ được đặt "name-only", tên sai dạng bị bỏ. Không bỏ skill nào vĩnh viễn: việc H mới quyết.

Lệnh:
  profile.py --project <thư mục> show [--json]   # bộ đang dùng
  profile.py --project <thư mục> gon [--dry-run]
  profile.py --project <thư mục> du [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
import agentstack as A  # noqa: E402

PROTECTED_PLUGINS = {"agent-stack@agent-stack-local"}
PROTECTED_MARKETPLACE = "agent-stack-local"
PLUGIN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}@[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SKILL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}(?::[A-Za-z0-9][A-Za-z0-9._-]{0,63})?$")
MAX_NAMES = 100
# Mặc định của "gọn": plugin và skill ít dùng khi code (bạn đổi trong stack.json; việc H quyết bỏ hẳn hay không).
DEFAULT_PLUGINS_OFF = (
    "playground@claude-plugins-official",
    "project-artifact@claude-plugins-official",
    "html-plan@agent-stack-vendor-local",
    "claude-security@claude-plugins-official",
)
DEFAULT_SKILLS_NAME_ONLY = (
    "agent-stack:aside-web", "agent-stack:kaggle-gpu", "agent-stack:writing-voice",
    "agent-stack-vendor:kaggle-cli", "agent-stack-vendor:frontend-design",
    "anthropic-skills:docx", "anthropic-skills:pptx", "anthropic-skills:xlsx", "anthropic-skills:pdf",
    "anthropic-skills:google-workspace", "anthropic-skills:docs", "anthropic-skills:paper-anatomy",
    "anthropic-skills:deep-research", "anthropic-skills:import-memory", "anthropic-skills:setup-claude",
    "anthropic-skills:morning", "anthropic-skills:computer-use", "anthropic-skills:chrome-browser",
    "cowork-plugin-management:create-cowork-plugin", "cowork-plugin-management:cowork-plugin-customizer",
)
LABEL = {"gon": "gọn", "du": "đủ"}


class ProfileError(Exception):
    pass


def names(values, pattern) -> list:
    out = []
    for value in values if isinstance(values, list) else []:
        if isinstance(value, str) and pattern.match(value) and value not in out:
            out.append(value)
    return out[:MAX_NAMES]


def protected(plugin_id: str) -> bool:
    """Plugin của marketplace agent-stack-local (chứa hook chặn) không bao giờ bị tắt; so không phân biệt hoa thường."""
    folded = plugin_id.casefold()
    return folded in PROTECTED_PLUGINS or folded.endswith("@" + PROTECTED_MARKETPLACE)


def wanted(project: Path) -> dict:
    """Danh sách của bộ "gọn" cho project: từ stack.json nếu có, không thì mặc định."""
    data = A.read_json(project / ".agent" / "stack.json", {}) or {}
    gon = ((data.get("profiles") or {}) if isinstance(data, dict) else {}).get("gon")
    gon = gon if isinstance(gon, dict) else {}
    plugins = names(gon["plugins_off"], PLUGIN_RE) if "plugins_off" in gon else list(DEFAULT_PLUGINS_OFF)
    skills = names(gon["skills_name_only"], SKILL_RE) if "skills_name_only" in gon else list(DEFAULT_SKILLS_NAME_ONLY)
    return {"plugins_off": [p for p in plugins if not protected(p)], "skills_name_only": skills,
            "source": ".agent/stack.json" if gon else "mặc định"}


def settings_path(project: Path) -> Path:
    folder = project / ".claude"
    path = folder / "settings.local.json"
    if folder.is_symlink() or path.is_symlink():
        raise ProfileError(f"{path} hay thư mục .claude là symlink: không ghi (TM-155)")
    return path


def load_settings(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProfileError(f"không đọc được {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ProfileError(f"{path} không phải JSON object")
    return data


def record_path(project: Path) -> Path:
    digest = hashlib.sha256(str(project.resolve()).encode()).hexdigest()[:16]
    return A.state_dir() / "profiles" / f"{digest}.json"


def save_record(project: Path, rec: dict) -> None:
    path = record_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    A.write_json_atomic(path, rec)


def load_record(project: Path) -> dict:
    rec = A.read_json(record_path(project), {}) or {}
    return rec if isinstance(rec, dict) and isinstance(rec.get("changes"), list) else {"changes": []}


def plan_gon(data: dict, want: dict) -> list:
    """Các khóa cần đặt: (bảng, khóa, giá trị mới)."""
    targets = [("enabledPlugins", p, False) for p in want["plugins_off"]]
    targets += [("skillOverrides", s, "name-only") for s in want["skills_name_only"]]
    return [(t, k, v) for t, k, v in targets if (data.get(t) or {}).get(k) != v]


def apply_gon(data: dict, steps: list, rec: dict) -> dict:
    known = {(c["table"], c["key"]) for c in rec["changes"]}
    for table, key, value in steps:
        current = data.get(table)
        created = not isinstance(current, dict)
        if not isinstance(current, dict):
            current = data[table] = {}
        if (table, key) not in known:
            rec["changes"].append({"table": table, "key": key, "had": key in current, "old": current.get(key),
                                   "set": value, "table_created": created})
        else:
            for change in rec["changes"]:
                if (change["table"], change["key"]) == (table, key):
                    change["set"] = value
        current[key] = value
    rec["profile"] = "gon"
    return rec


def apply_du(data: dict, rec: dict) -> list:
    """Trả các khóa về giá trị cũ; trả về danh sách khóa đã trả."""
    done = []
    for change in rec["changes"]:
        table = data.get(change["table"])
        if not isinstance(table, dict) or table.get(change["key"]) != change["set"]:
            continue  # người dùng đã tự đổi sau "gọn": giữ
        if change["had"]:
            table[change["key"]] = change["old"]
        else:
            table.pop(change["key"], None)
        done.append(f"{change['table']}.{change['key']}")
    for change in rec["changes"]:
        if change.get("table_created") and data.get(change["table"]) == {}:
            data.pop(change["table"])
    return done


def write_settings(path: Path, data: dict) -> None:
    """Ghi nguyên tử qua file tạm tên ngẫu nhiên tạo mới (O_EXCL): file tạm có sẵn trong repo, kể cả symlink, không
    làm lệch chỗ ghi (TM-155)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".settings.local.", suffix=".agent-stack.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Công tắc bộ plugin gọn/đủ theo project")
    ap.add_argument("--project", default=".")
    ap.add_argument("action", choices=("show", "gon", "du"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    project = Path(args.project).expanduser().resolve()
    rec = load_record(project)
    current = rec.get("profile") if rec["changes"] else "du"
    if args.action == "show":
        want = wanted(project)
        info = {"profile": current or "du", "plugins_off": want["plugins_off"],
                "skills_name_only": want["skills_name_only"], "source": want["source"]}
        if args.json:
            print(json.dumps(info, ensure_ascii=False))
        else:
            print(f"Bộ đang dùng: {LABEL.get(info['profile'], info['profile'])}. Bộ gọn ({info['source']}): tắt "
                  f"{len(info['plugins_off'])} plugin, {len(info['skills_name_only'])} skill chỉ còn tên. "
                  "Đổi: /stack-profile gon|du (có hiệu lực từ phiên mới).")
        return 0
    try:
        path = settings_path(project)
        data = load_settings(path)
    except ProfileError as exc:
        print(f"profile: {exc}", file=sys.stderr)
        return 1
    if args.action == "gon":
        want = wanted(project)
        steps = plan_gon(data, want)
        for table, key, value in steps:
            print(f"  + {table}.{key} = {json.dumps(value)}")
        if args.dry_run:
            print(f"Xem trước bộ gọn: {len(steps)} khóa sẽ đổi trong {path}")
            return 0
        rec = apply_gon(data, steps, rec)
        rec["project"] = str(project)
        write_settings(path, data)
        save_record(project, rec)
        print(f"Đã chuyển sang bộ gọn: {len(steps)} khóa đổi trong {path}. Mở phiên mới để có hiệu lực; "
              "trả lại: /stack-profile du")
        return 0
    if not rec["changes"]:
        print("Project đang ở bộ đủ, không có gì để trả.")
        return 0
    preview = json.loads(json.dumps(data))
    done = apply_du(preview, rec)
    for key in done:
        print(f"  - {key}")
    if args.dry_run:
        print(f"Xem trước bộ đủ: {len(done)} khóa sẽ trả lại trong {path}")
        return 0
    write_settings(path, preview)
    save_record(project, {"changes": [], "profile": "du", "project": str(project)})
    print(f"Đã chuyển về bộ đủ: trả {len(done)} khóa trong {path}. Mở phiên mới để có hiệu lực.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
