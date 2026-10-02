#!/usr/bin/env python3
"""Kích hoạt agent-stack ở mức toàn cục cho Claude Code và OpenCode.

MẶC ĐỊNH CHỈ IN KẾ HOẠCH, không sửa gì. Thêm --apply để thực hiện. Mỗi lần --apply đều
sao lưu cấu hình trước, và ghi nhật ký vào state/install-logs/ để --rollback hoàn tác.

Các bước (chạy theo thứ tự; --only để chọn một phần):
  rules       ~/.claude/CLAUDE.md -> global/CLAUDE.global.md
              ~/.config/opencode/AGENTS.md -> global/AGENTS.global.md
  plugin      marketplace cục bộ agent-stack-local + plugin agent-stack (scope user)
  statusline  statusLine trong ~/.claude/settings.json (chỉ khi chưa có)
  autocontinue  autoContinueAtUsageLimit = true trong ~/.claude/settings.json (chỉ khi chưa đặt): phiên trong
              terminal tự chờ rồi làm tiếp khi chạm giới hạn 5 giờ
  catalog     cài các mục đã duyệt trong vetted.lock (scope user); mục scope project chỉ in lệnh
  opencode    symlink skill (agent-stack + vendor) vào ~/.config/opencode/skills/, agent vào ~/.config/opencode/agents/

Mã thoát: 0 = cài đủ; 1 = có bước lỗi; 2 = không lỗi nhưng có mục bị bỏ qua (cài chưa đủ).
Cài một phần không phải là thành công: phần tổng kết cuối luôn liệt kê mục bị bỏ qua và mục lỗi.

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
STEPS = ("rules", "plugin", "statusline", "autocontinue", "catalog", "opencode")
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
        self.skipped = []
        self.failures = []

    # ------------------------------------------------------------ tiện ích

    def say(self, text: str) -> None:
        self.lines.append(text)
        print(text)

    def record(self, **action) -> None:
        self.actions.append(action)

    def backup_target(self, path: Path, suffix: str = "") -> Path:
        """Đường dẫn bản sao lưu chưa dùng. Cùng một file được sao lưu nhiều lần trong một lần cài
        (ví dụ settings.json ở hai bước) thì mỗi bản một tên, để hoàn tác về đúng bản gốc."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        base = str(path.relative_to(self.home)).replace("/", "__")
        n = 1
        while True:
            target = self.backup_dir / (base + (f".{n}" if n > 1 else "") + suffix)
            if not (target.exists() or target.is_symlink()):
                return target
            n += 1

    def backup(self, path: Path):
        """Sao lưu một file (hoặc symlink) trước khi thay; trả về đường dẫn bản sao lưu."""
        if not (path.exists() or path.is_symlink()):
            return None
        if path.is_dir() and not path.is_symlink():
            dest = self.backup_target(path, ".dir")
            shutil.move(str(path), str(dest))
            return str(dest)
        if path.is_symlink():
            dest = self.backup_target(path, ".symlink")
            dest.write_text(os.readlink(path))
            return str(dest)
        dest = self.backup_target(path)
        shutil.copy2(path, dest)
        return str(dest)

    def link(self, src: Path, dest: Path) -> None:
        if dest.is_symlink() and Path(os.readlink(dest)) == src:
            self.say(f"  = đã có: {dest} -> {src}")
            return
        if (dest.exists() or dest.is_symlink()) and not self.replace_existing:
            self.say(f"  ! bỏ qua: {dest} đã tồn tại và không phải của agent-stack (thêm --replace-existing để thay, có sao lưu)")
            self.skipped.append(f"{dest}: đã có file không phải của agent-stack")
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
        try:
            out = subprocess.run(args, capture_output=True, text=True)
        except OSError as exc:
            self.say(f"    lỗi: {exc}")
            self.failures.append(f"{' '.join(args[:4])}: {exc}")
            return
        text = (out.stdout + out.stderr).strip()
        if out.returncode != 0 and not (ok_if and ok_if in text.lower()):
            self.say(f"    lỗi ({out.returncode}): {text[:300]}")
            self.failures.append(f"{' '.join(args[:4])}: mã {out.returncode}: {text[:160]}")
            return
        self.record(type="cmd", cmd=args, undo=undo)

    def edit_settings(self, mutate) -> None:
        path = self.claude_dir / "settings.json"
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except ValueError as exc:
                self.say(f"  ! không đọc được {path}: {exc}. Không sửa file này.")
                self.failures.append(f"{path}: JSON không hợp lệ")
                return
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

    def step_autocontinue(self) -> None:
        self.say("[autocontinue] tự chờ rồi làm tiếp khi chạm giới hạn 5 giờ (autoContinueAtUsageLimit)")

        def mutate(data):
            if "autoContinueAtUsageLimit" in data:
                self.say(f"  = đã đặt autoContinueAtUsageLimit = {json.dumps(data['autoContinueAtUsageLimit'])}, giữ nguyên")
            else:
                self.say("  + autoContinueAtUsageLimit = true")
                data["autoContinueAtUsageLimit"] = True
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
                self.failures.append(f"{item['key']}: đã duyệt nhưng thiếu bản đã kiểm trong .vet-cache")
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
        # OpenCode v2 theo dõi ~/.config/opencode/skills; glob của nó đi theo symlink.
        skills_dir = self.oc_dir / "skills"
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
        return self.summary()

    def summary(self) -> int:
        """In tổng kết. Cài một phần không được trông như thành công."""
        planned = sum(1 for line in self.lines if line.startswith(("  + ", "  $ ")))
        done = f"{len(self.actions)} thay đổi đã làm" if self.apply else f"{planned} thay đổi sẽ làm"
        self.say(f"Tổng kết: {done}, {len(self.skipped)} mục bị bỏ qua, {len(self.failures)} lỗi.")
        for item in self.skipped:
            self.say(f"  - bỏ qua: {item}")
        for item in self.failures:
            self.say(f"  - lỗi: {item}")
        if self.failures:
            self.say("⚠️ Có lỗi: phần cài chưa hoàn tất. Sửa lỗi rồi chạy lại; các bước đã xong sẽ không bị làm lại.")
            return 1
        if self.skipped:
            self.say("⚠️ Cài chưa đủ: các mục bị bỏ qua ở trên chưa được kích hoạt.")
            return 2
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
