#!/usr/bin/env python3
"""Kích hoạt agent-stack ở mức toàn cục cho Claude Code và OpenCode.

MẶC ĐỊNH CHỈ IN KẾ HOẠCH, không sửa gì. Thêm --apply để thực hiện. Mỗi lần --apply đều
sao lưu cấu hình trước, và ghi nhật ký vào state/install-logs/ để --rollback hoàn tác.

Các bước (chạy theo thứ tự; --only để chọn một phần):
  rules       ~/.claude/CLAUDE.md -> global/CLAUDE.global.md
              ~/.config/opencode/AGENTS.md -> global/AGENTS.global.md
  plugin      marketplace cục bộ agent-stack-local + plugin agent-stack (scope user)
  statusline  statusLine trong ~/.claude/settings.json (chỉ khi chưa có)
  catalog     cài các mục đã duyệt trong vetted.lock (scope user); mục scope project chỉ in lệnh
  opencode    symlink skill (agent-stack + vendor) vào ~/.agents/skills/, agent vào ~/.config/opencode/agents/

Ví dụ:
  python3 tools/install.py                 # xem trước
  python3 tools/install.py --apply         # thực hiện
  python3 tools/install.py --rollback      # hoàn tác lần --apply gần nhất
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HOME_STACK = Path(os.environ.get("AGENT_STACK_HOME") or Path(__file__).resolve().parents[1]).resolve()
STEPS = ("rules", "plugin", "statusline", "catalog", "opencode")
MARKETPLACE = "agent-stack-local"
SKIP_IN_VENDOR = {".git", ".vet-complete", ".claude-plugin", ".cursor-plugin", ".codex-plugin"}


class Installer:
    def __init__(self, apply: bool, replace_existing: bool, restore_workflow_warning: bool):
        self.apply = apply
        self.replace_existing = replace_existing
        self.restore_workflow_warning = restore_workflow_warning
        self.home = Path.home()
        self.claude_dir = self.home / ".claude"
        self.oc_dir = self.home / ".config" / "opencode"
        self.claude_bin = os.environ.get("AGENT_STACK_CLAUDE_BIN", "claude")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.backup_dir = HOME_STACK / "backups" / f"install-{stamp}"
        self.log_path = HOME_STACK / "state" / "install-logs" / f"{stamp}.json"
        self.actions = []
        self.lines = []

    # ------------------------------------------------------------ tiện ích

    def say(self, text: str) -> None:
        self.lines.append(text)
        print(text)

    def record(self, **action) -> None:
        self.actions.append(action)

    def backup(self, path: Path):
        """Sao lưu một file (hoặc symlink) trước khi thay; trả về đường dẫn bản sao lưu."""
        if not (path.exists() or path.is_symlink()):
            return None
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        if path.is_dir() and not path.is_symlink():
            dest = self.backup_dir / (str(path.relative_to(self.home)).replace("/", "__") + ".dir")
            shutil.move(str(path), str(dest))
            return str(dest)
        dest = self.backup_dir / str(path.relative_to(self.home)).replace("/", "__")
        if path.is_symlink():
            dest.with_suffix(dest.suffix + ".symlink").write_text(os.readlink(path))
            return str(dest.with_suffix(dest.suffix + ".symlink"))
        shutil.copy2(path, dest)
        return str(dest)

    def link(self, src: Path, dest: Path) -> None:
        if dest.is_symlink() and Path(os.readlink(dest)) == src:
            self.say(f"  = đã có: {dest} -> {src}")
            return
        if (dest.exists() or dest.is_symlink()) and not self.replace_existing:
            self.say(f"  ! bỏ qua: {dest} đã tồn tại và không phải của agent-stack (thêm --replace-existing để thay, có sao lưu)")
            return
        self.say(f"  + symlink: {dest} -> {src}")
        if not self.apply:
            return
        previous = self.backup(dest)  # thư mục thật thì được chuyển hẳn vào bản sao lưu
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        dest.symlink_to(src)
        self.record(type="symlink", path=str(dest), src=str(src), backup=previous)

    def run(self, args: list, undo: list = None, ok_if: str = "") -> None:
        self.say(f"  $ {' '.join(args)}")
        if not self.apply:
            return
        out = subprocess.run(args, capture_output=True, text=True)
        text = (out.stdout + out.stderr).strip()
        if out.returncode != 0 and not (ok_if and ok_if in text.lower()):
            self.say(f"    lỗi ({out.returncode}): {text[:300]}")
            return
        self.record(type="cmd", cmd=args, undo=undo)

    def edit_settings(self, mutate) -> None:
        path = self.claude_dir / "settings.json"
        data = {}
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        before = json.dumps(data, sort_keys=True)
        mutate(data)
        if json.dumps(data, sort_keys=True) == before:
            return
        if not self.apply:
            return
        previous = self.backup(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".agent-stack.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
        self.record(type="file", path=str(path), backup=previous)

    # ------------------------------------------------------------ các bước

    def step_rules(self) -> None:
        self.say("[rules] luật chung cho Claude Code và OpenCode")
        self.link(HOME_STACK / "global" / "CLAUDE.global.md", self.claude_dir / "CLAUDE.md")
        self.link(HOME_STACK / "global" / "AGENTS.global.md", self.oc_dir / "AGENTS.md")

    def step_plugin(self) -> None:
        self.say("[plugin] marketplace cục bộ và plugin agent-stack")
        self.run([self.claude_bin, "plugin", "marketplace", "add", str(HOME_STACK)],
                 undo=[self.claude_bin, "plugin", "marketplace", "remove", MARKETPLACE], ok_if="already")
        self.run([self.claude_bin, "plugin", "install", f"agent-stack@{MARKETPLACE}", "--scope", "user"],
                 undo=[self.claude_bin, "plugin", "uninstall", f"agent-stack@{MARKETPLACE}", "--scope", "user"],
                 ok_if="already")

    def step_statusline(self) -> None:
        self.say("[statusline] model · effort · ctx · 5h · 7d")
        command = f"python3 {HOME_STACK / 'statusline' / 'statusline.py'}"

        def mutate(data):
            if "statusLine" in data:
                self.say(f"  = đã có statusLine, giữ nguyên: {json.dumps(data['statusLine'])[:120]}")
            else:
                self.say(f"  + statusLine = {command}")
                data["statusLine"] = {"type": "command", "command": command}
            if self.restore_workflow_warning and data.get("skipWorkflowUsageWarning"):
                self.say("  + bỏ skipWorkflowUsageWarning (bật lại cảnh báo usage của workflow)")
                data.pop("skipWorkflowUsageWarning")
        self.edit_settings(mutate)

    def approved(self) -> dict:
        lock = json.loads((HOME_STACK / "vetted.lock").read_text(encoding="utf-8"))["entries"]
        return {k: v for k, v in lock.items() if (v.get("human_review") or {}).get("status") == "approved"}

    def step_catalog(self) -> None:
        self.say("[catalog] các mục đã duyệt trong vetted.lock")
        catalog = json.loads((HOME_STACK / "catalog.json").read_text(encoding="utf-8"))
        approved = self.approved()
        added_marketplaces = set()
        vendored = []
        for item in catalog["items"]:
            key, inst = item["key"], item["install"]
            entry = approved.get(key)
            if not entry:
                self.say(f"  · chờ duyệt: {key}")
                continue
            if entry["verdict"] == "FAIL":
                self.say(f"  ! bỏ qua (FAIL): {key}")
                continue
            if item["kind"] == "vendor-skill":
                vendored.append((item, entry))
                continue
            plugin_id = f"{inst['plugin']}@{inst['marketplace']}"
            if item["scope"] != "user":
                prefix = f"claude plugin marketplace add {inst['marketplace_repo']} && " if inst.get("marketplace_repo") else ""
                self.say(f"  · {item['scope']}: tự cài khi cần, trong project: {prefix}claude plugin install {plugin_id} --scope project")
                continue
            if inst.get("marketplace_repo") and inst["marketplace"] not in added_marketplaces:
                self.run([self.claude_bin, "plugin", "marketplace", "add", inst["marketplace_repo"]],
                         undo=[self.claude_bin, "plugin", "marketplace", "remove", inst["marketplace"]], ok_if="already")
                added_marketplaces.add(inst["marketplace"])
            self.run([self.claude_bin, "plugin", "install", plugin_id, "--scope", "user"],
                     undo=[self.claude_bin, "plugin", "uninstall", plugin_id, "--scope", "user"], ok_if="already")
        if vendored:
            self.vendor(vendored)

    def vendor(self, vendored: list) -> None:
        """Chép đúng commit đã kiểm của các skill chỉ-có-chỉ-dẫn vào vendor/skills, thành plugin agent-stack-vendor."""
        vendor_root = HOME_STACK / "vendor"
        record = {}
        for item, entry in vendored:
            name = item["install"]["name"]
            cache = HOME_STACK / ".vet-cache" / Path(entry["report"]).stem
            src = cache / entry["subpath"] if entry.get("subpath") else cache
            dest = vendor_root / "skills" / name
            if item["scope"] != "user":
                self.say(f"  · {item['scope']}: {name} không chép mặc định; khi cần, đổi scope trong catalog.json thành user rồi chạy lại")
                continue
            if not (src / "SKILL.md").exists():
                self.say(f"  ! thiếu bản đã kiểm trong cache cho {name}: chạy lại vet.py scan {item['key']}")
                continue
            self.say(f"  + vendor: {name} @ {entry['sha'][:12]} -> vendor/skills/{name}")
            record[name] = {"key": item["key"], "sha": entry["sha"]}
            if self.apply:
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(src, dest, ignore=lambda d, names: [n for n in names if n in SKIP_IN_VENDOR])
        if not record:
            return
        if self.apply:
            (vendor_root / ".claude-plugin").mkdir(parents=True, exist_ok=True)
            (vendor_root / ".claude-plugin" / "plugin.json").write_text(json.dumps({
                "name": "agent-stack-vendor", "version": time.strftime("%Y.%m.%d"),
                "description": "Skill của bên thứ ba, chép đúng commit đã kiểm duyệt bằng vet-skill.",
                "author": {"name": "tdHuy22"}}, ensure_ascii=False, indent=2) + "\n")
            (vendor_root / "VENDORED.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
            mp_path = HOME_STACK / ".claude-plugin" / "marketplace.json"
            mp = json.loads(mp_path.read_text(encoding="utf-8"))
            if not any(p["name"] == "agent-stack-vendor" for p in mp["plugins"]):
                mp["plugins"].append({"name": "agent-stack-vendor", "source": "./vendor",
                                      "description": "Skill của bên thứ ba đã kiểm duyệt, ghim commit."})
                mp_path.write_text(json.dumps(mp, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.run([self.claude_bin, "plugin", "install", f"agent-stack-vendor@{MARKETPLACE}", "--scope", "user"],
                 undo=[self.claude_bin, "plugin", "uninstall", f"agent-stack-vendor@{MARKETPLACE}", "--scope", "user"],
                 ok_if="already")

    def step_opencode(self) -> None:
        self.say("[opencode] skill và agent cho OpenCode")
        skills_dir = self.home / ".agents" / "skills"
        sources = sorted((HOME_STACK / "plugin" / "skills").glob("*/SKILL.md"))
        sources += sorted((HOME_STACK / "vendor" / "skills").glob("*/SKILL.md"))
        for skill_md in sources:
            self.link(skill_md.parent, skills_dir / skill_md.parent.name)
        for agent in sorted((HOME_STACK / "opencode" / "agents").glob("*.md")):
            self.link(agent, self.oc_dir / "agents" / agent.name)

    # ------------------------------------------------------------ chạy

    def run_steps(self, steps) -> int:
        mode = "THỰC HIỆN" if self.apply else "XEM TRƯỚC (chưa sửa gì; thêm --apply để thực hiện)"
        self.say(f"agent-stack install · {mode}")
        for step in steps:
            getattr(self, f"step_{step}")()
        if self.apply and self.actions:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_path.write_text(json.dumps({"backup_dir": str(self.backup_dir), "actions": self.actions},
                                                ensure_ascii=False, indent=2) + "\n")
            self.say(f"Đã ghi nhật ký: {self.log_path}. Hoàn tác: python3 tools/install.py --rollback")
        return 0


def rollback(log_arg: str, apply: bool) -> int:
    logs = sorted((HOME_STACK / "state" / "install-logs").glob("*.json"))
    if log_arg:
        log = Path(log_arg)
    elif logs:
        log = logs[-1]
    else:
        print("Không có nhật ký cài đặt nào để hoàn tác.")
        return 1
    data = json.loads(log.read_text(encoding="utf-8"))
    print(f"Hoàn tác theo {log} ({'THỰC HIỆN' if apply else 'XEM TRƯỚC'})")
    for action in reversed(data["actions"]):
        if action["type"] == "symlink":
            path = Path(action["path"])
            print(f"  - gỡ symlink {path}" + (f", khôi phục {action['backup']}" if action.get("backup") else ""))
            if apply and path.is_symlink():
                path.unlink()
                backup = action.get("backup")
                if backup and backup.endswith(".symlink"):
                    path.symlink_to(Path(backup).read_text())
                elif backup and backup.endswith(".dir"):
                    shutil.move(backup, str(path))
                elif backup:
                    shutil.copy2(backup, path)
        elif action["type"] == "file":
            print(f"  - khôi phục {action['path']}" + ("" if action.get("backup") else " (xóa vì trước đó chưa có)"))
            if apply:
                if action.get("backup"):
                    shutil.copy2(action["backup"], action["path"])
                else:
                    Path(action["path"]).unlink(missing_ok=True)
        elif action["type"] == "cmd" and action.get("undo"):
            print(f"  $ {' '.join(action['undo'])}")
            if apply:
                subprocess.run(action["undo"], capture_output=True, text=True)
    if apply:
        log.rename(log.with_suffix(".rolled-back.json"))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Kích hoạt agent-stack (mặc định chỉ xem trước).")
    ap.add_argument("--apply", action="store_true", help="thực hiện thay đổi")
    ap.add_argument("--only", help="danh sách bước, ngăn cách bằng dấu phẩy: " + ",".join(STEPS))
    ap.add_argument("--replace-existing", action="store_true", help="thay file/symlink đang có (có sao lưu)")
    ap.add_argument("--restore-workflow-warning", action="store_true", help="bỏ skipWorkflowUsageWarning")
    ap.add_argument("--rollback", nargs="?", const="", metavar="NHẬT_KÝ", help="hoàn tác lần cài gần nhất")
    args = ap.parse_args(argv)
    if args.rollback is not None:
        return rollback(args.rollback, args.apply)
    steps = STEPS if not args.only else tuple(s.strip() for s in args.only.split(",") if s.strip())
    unknown = [s for s in steps if s not in STEPS]
    if unknown:
        ap.error(f"bước không hợp lệ: {', '.join(unknown)}")
    return Installer(args.apply, args.replace_existing, args.restore_workflow_warning).run_steps(steps)


if __name__ == "__main__":
    sys.exit(main())
