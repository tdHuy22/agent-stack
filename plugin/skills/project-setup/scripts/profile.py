#!/usr/bin/env python3
"""Bật, tắt các bộ skill và plugin (việc H5 mục 1, 20/11/2026; thay công tắc "gọn"/"đủ" của việc G).

Danh sách bộ cố định ở `plugin/lib/bundles.py`: bộ lõi luôn bật; bộ khác bật khi việc cần. Lệnh ghi `enabledPlugins`
vào `<project>/.claude/settings.local.json` (mặc định, đè cấu hình user và project) hay, với `--user`, vào
`$CLAUDE_CONFIG_DIR/settings.json` (mặc định `~/.claude/settings.json`). Skill agent-stack ngoài lõi không cần ghi gì:
chúng không nạp sẵn (`disable-model-invocation: true`), Claude đọc thẳng `SKILL.md` theo đường dẫn lệnh này in ra và
theo dòng của hook SessionStart khi bộ đang bật. Plugin có hiệu lực ở phiên mới hay sau khi người dùng gõ
/reload-plugins.

Chỉ đặt `true` cho plugin đã cài (`installed_plugins.json`): Claude Code tự tải plugin chưa cài khi cấu hình bật nó,
tức bản chưa qua vet-skill (TM-167). Plugin của bộ lõi không bao giờ bị đặt `false` (TM-166).

Lệnh:
  profile.py [--project DIR | --user] show [--json]
  profile.py [--project DIR | --user] on BỘ [BỘ...] [--dry-run]
  profile.py [--project DIR | --user] off BỘ [BỘ...] [--dry-run]
  profile.py [--project DIR | --user] loi [--dry-run]     # chỉ bộ lõi (bí danh: gon)
  profile.py [--project DIR | --user] du [--dry-run]      # trả mọi khóa đã đổi về như trước lần đổi đầu tiên
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
import agentstack as A  # noqa: E402
import bundles as B  # noqa: E402

TABLE = "enabledPlugins"
RESTORE = "restore"  # bước "trả khóa về giá trị trước lần đổi đầu tiên" của `off`


class ProfileError(Exception):
    pass


def check_path(path: Path) -> Path:
    """Từ chối file settings hay thư mục chứa nó là symlink (TM-155, TM-168)."""
    if path.parent.is_symlink() or path.is_symlink():
        raise ProfileError(f"{path} hay thư mục chứa nó là symlink: không ghi")
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


def write_settings(path: Path, data: dict) -> None:
    """Ghi nguyên tử qua file tạm tên ngẫu nhiên tạo mới (O_EXCL): file tạm có sẵn, kể cả symlink, không làm lệch chỗ
    ghi (TM-155)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".agent-stack.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        if path.exists():  # giữ quyền của file cũ (mkstemp tạo 0600)
            os.chmod(tmp, path.stat().st_mode & 0o777)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load_record(path: Path) -> dict:
    rec = A.read_json(B.record_path(path), {}) or {}
    if not isinstance(rec, dict) or not isinstance(rec.get("changes"), list):
        rec = {"changes": []}
    # Chỉ nhận khóa plugin ngoài lõi có trong danh sách cố định, giá trị bool hay None: bản ghi bị sửa không làm `du`
    # tắt được plugin lõi (TM-166).
    allowed = {p for n in B.non_core() for p in B.BUNDLES[n]["plugins"]} - B.core_plugins()
    rec["changes"] = [c for c in rec["changes"] if isinstance(c, dict) and c.get("key") in allowed
                      and c.get("old") in (True, False, None) and c.get("set") in (True, False)]
    rec["on"] = B.recorded_on(path)
    rec["off"] = B.recorded(path, "off")
    return rec


def save_record(path: Path, rec: dict, scope: str) -> None:
    target = B.record_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    A.write_json_atomic(target, dict(rec, settings=str(path), scope=scope))


def plan(action: str, names: list, rec: dict, project=None) -> tuple:
    """(bộ đang bật sau lệnh, bộ tắt rõ sau lệnh, [(id plugin, giá trị mới)], [id chưa cài]). Bộ tắt rõ ở local che
    bộ bật ở scope user (bundles.active)."""
    on, off = list(rec["on"]), list(rec["off"])
    core = B.core_plugins()
    installed = B.installed_plugins()
    steps, missing = [], []
    if action == "loi":
        on, off = [], B.non_core()
        for name in B.non_core():
            steps += [(p, False) for p in B.BUNDLES[name]["plugins"] if p not in core]
    elif action == "on":
        on = [n for n in B.non_core() if n in set(on) | set(names)]
        off = [n for n in off if n not in names]
        for name in names:
            for p in B.BUNDLES[name]["plugins"]:
                if p in core:
                    continue
                if p in installed:
                    steps.append((p, True))
                elif p not in missing:
                    missing.append(p)
    elif action == "off":
        on = [n for n in on if n not in names]
        off = [n for n in B.non_core() if n in set(off) | set(names)]
        here = {p for n in on for p in B.BUNDLES[n]["plugins"]} | core
        # Plugin dùng chung với bộ chỉ bật ở scope khác: không tắt, nhưng bỏ giá trị scope này đã ghim (trả về như cũ)
        # để scope kia quyết (review 20/11).
        other = {p for n in set(B.active(project)) - set(names) - set(on) for p in B.BUNDLES[n]["plugins"]}
        for name in names:
            for p in B.BUNDLES[name]["plugins"]:
                if p in here:
                    continue
                steps.append((p, RESTORE if p in other else False))
    return on, off, list(dict(steps).items()), missing


def apply(data: dict, steps: list, rec: dict, restored=None) -> list:
    """Đặt các khóa, ghi giá trị cũ vào bản ghi; trả các bước thật sự đổi."""
    table = data.get(TABLE)
    created = not isinstance(table, dict)
    if created:
        table = {}
    known = {c["key"]: c for c in rec["changes"]}
    done = []
    for plugin, value in steps:
        if value == RESTORE:
            change = known.pop(plugin, None)
            if change is None or table.get(plugin) != change.get("set"):
                continue  # scope này chưa ghim, hay người dùng đã tự đổi: giữ
            rec["changes"].remove(change)
            if restored is not None:
                restored.append(change)
            if change.get("had"):
                table[plugin] = change.get("old")
            else:
                table.pop(plugin, None)
            done.append((plugin, change.get("old")))
            continue
        if table.get(plugin) is value:
            continue
        if plugin not in known:
            change = {"key": plugin, "had": plugin in table, "old": table.get(plugin), "set": value,
                      "table_created": created}
            rec["changes"].append(change)
            known[plugin] = change
        else:
            known[plugin]["set"] = value
        table[plugin] = value
        done.append((plugin, value))
    if done:
        data[TABLE] = table
    return done


def restore(data: dict, rec: dict) -> list:
    """Trả các khóa về giá trị cũ, giữ khóa người dùng tự đổi sau đó."""
    table = data.get(TABLE)
    done = []
    for change in rec["changes"]:
        if not isinstance(table, dict) or table.get(change["key"]) != change.get("set"):
            continue
        if change.get("had"):
            table[change["key"]] = change.get("old")
        else:
            table.pop(change["key"], None)
        done.append(change["key"])
    if isinstance(table, dict) and not table and any(c.get("table_created") for c in rec["changes"]):
        data.pop(TABLE)
    return done


def show(path: Path, scope: str, rec: dict, as_json: bool, project=None) -> None:
    info = {"scope": scope, "settings": str(path), "on": rec["on"], "active": B.active(project),
            "bundles": [{"name": n, "label": b["label"], "plugins": list(b["plugins"]), "skills": list(b["skills"])}
                        for n, b in B.BUNDLES.items()]}
    if as_json:
        print(json.dumps(info, ensure_ascii=False))
        return
    print(f"Bộ đang bật ({scope}, {path}): lõi" + "".join(f", {n}" for n in rec["on"]) + "."
          + ("" if project is None else " Gộp cả scope user: lõi" + "".join(f", {n}" for n in info["active"]) + "."))
    for item in info["bundles"]:
        parts = ["plugin " + ", ".join(p.split("@")[0] for p in item["plugins"])] if item["plugins"] else []
        parts += ["skill " + ", ".join(item["skills"])] if item["skills"] else []
        print(f"  {item['name']:9} {item['label']} ({'; '.join(parts)})")
    print("Đổi: /stack-profile on|off <bộ>, loi (chỉ lõi), du (về như cũ); hay profile.py cùng tham số.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Bật, tắt các bộ skill và plugin của agent-stack")
    where = ap.add_mutually_exclusive_group()
    where.add_argument("--project", default=".")
    where.add_argument("--user", action="store_true", help="ghi cấu hình user ($CLAUDE_CONFIG_DIR/settings.json)")
    ap.add_argument("action", choices=("show", "on", "off", "loi", "gon", "du"))
    ap.add_argument("names", nargs="*")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    action = "loi" if args.action == "gon" else args.action
    valid = B.non_core()
    if action in ("on", "off"):
        bad = [n for n in args.names if n not in valid]
        if not args.names or bad:
            print(f"profile: bộ không hợp lệ: {', '.join(bad) or '(trống)'}. Bộ bật/tắt được: {', '.join(valid)} "
                  f"(bộ {B.CORE} luôn bật).", file=sys.stderr)
            return 2
    elif args.names:
        print(f"profile: lệnh {args.action} không nhận tên bộ", file=sys.stderr)
        return 2
    scope = "user" if args.user else "local"
    # Cùng thư mục với hook (bundles.settings_root): gốc git, ngoài git thì chính thư mục đó.
    project = None if args.user else B.settings_root(args.project)
    path = B.user_settings() if args.user else B.local_settings(project)
    try:
        check_path(path)
        rec = load_record(path)
        if action == "show":
            show(path, scope, rec, args.json, project)
            return 0
        data = load_settings(path)
    except ProfileError as exc:
        print(f"profile: {exc}", file=sys.stderr)
        return 1
    if action == "du":
        preview = copy.deepcopy(data)
        done = restore(preview, rec)
        for key in done:
            print(f"  - {TABLE}.{key}")
        if args.dry_run:
            print(f"Xem trước: {len(done)} khóa sẽ trả lại trong {path}")
            return 0
        try:
            if done:
                write_settings(path, preview)
            save_record(path, {"changes": [], "on": [], "off": []}, scope)
        except OSError as exc:
            print(f"profile: không ghi được: {exc}", file=sys.stderr)
            return 1
        print(f"Đã về như cũ: trả {len(done)} khóa trong {path}. Plugin có hiệu lực ở phiên mới hay sau /reload-plugins.")
        return 0
    on, off, steps, missing = plan(action, args.names, rec, project)
    if action == "on":
        # Bộ chỉ có plugin mà không plugin nào cài: không ghi bộ là đang bật (hook sẽ thôi gợi ý mà plugin không nạp).
        empty = [n for n in args.names if not B.BUNDLES[n]["skills"]
                 and not any(p in B.installed_plugins() for p in B.BUNDLES[n]["plugins"])]
        if empty:
            print(f"profile: bộ {', '.join(empty)} chưa có plugin nào được cài (cài qua install.sh): không bật",
                  file=sys.stderr)
            return 1
    preview = copy.deepcopy(data)
    trial = copy.deepcopy(rec)
    restored = []
    done = apply(preview, steps, trial, restored)
    for plugin, value in done:
        print(f"  {'+' if value else '-'} {TABLE}.{plugin} = {json.dumps(value)}")
    # Khóa vừa trả về "không có" làm bảng rỗng mà bảng do lần đổi đầu tiên tạo ra: bỏ bảng như `du`.
    if preview.get(TABLE) == {} and (TABLE not in data or any(c.get("table_created") for c in restored)):
        preview.pop(TABLE)
    for plugin in missing:
        print(f"  · {plugin} chưa cài: không bật (cài qua install.sh, mục đã duyệt trong catalog)")
    if action == "on":
        for name in args.names:
            for skill in B.BUNDLES[name]["skills"]:
                print(f"  đọc thẳng skill {skill}: {B.skill_md(skill)}")
            for plugin in B.BUNDLES[name]["plugins"]:
                for skill_file in B.plugin_skill_files(plugin):
                    print(f"  đọc thẳng (trước khi plugin nạp): {skill_file}")
    if args.dry_run:
        print(f"Xem trước: {len(done)} khóa sẽ đổi trong {path}")
        return 0
    trial["on"], trial["off"] = on, off
    try:
        # Bản ghi trước, còn giữ cả mục sắp trả (RESTORE): settings ghi lỗi thì `du` thấy khóa chưa đổi và bỏ qua, mục
        # trả chưa mất giá trị cũ. Settings ghi xong mới lưu bản ghi cuối.
        save_record(path, dict(trial, changes=trial["changes"] + restored), scope)
        if done:
            write_settings(path, preview)
        if restored:
            save_record(path, trial, scope)
    except OSError as exc:
        print(f"profile: không ghi được: {exc}", file=sys.stderr)
        return 1
    label = {"loi": "Chỉ còn bộ lõi", "on": "Đã bật bộ " + ", ".join(args.names),
             "off": "Đã tắt bộ " + ", ".join(args.names)}[action]
    label += f" ({len(missing)} plugin chưa cài, không bật)" if missing else ""
    print(f"{label} ({scope}): {len(done)} khóa đổi trong {path}. Bộ đang bật"
          + ("" if args.user else " (gộp user và local)") + ": lõi"
          + "".join(f", {n}" for n in (on if args.user else B.active(project))) + ". Plugin có hiệu lực ở phiên mới hay sau /reload-plugins; về như cũ: "
          "profile.py du.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
