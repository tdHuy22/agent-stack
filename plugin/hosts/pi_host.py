#!/usr/bin/env python3
"""agent-stack cho pi: kiểm hợp đồng hosts/pi.json và sinh subagent dạng pi.

Hợp đồng ghi những gì pi (project pi-agent) dựa vào ở agent-stack: hook nào chạy ở sự kiện pi nào, trường vào ra,
subagent và skill nào pi dùng hay bỏ kèm lý do. `check` trả về danh sách chỗ lệch giữa hợp đồng và thư mục plugin
(test, install.py và hook SessionStart khi chạy trong pi gọi); `sync_agents` sinh subagent cho extension subagent
của pi từ agents/ của plugin, chỉ ghi file đổi.

pi và Claude Code cùng chạy thẳng thư mục plugin/ của repo (Claude Code nạp marketplace nguồn thư mục tại chỗ), nên
không có bản cài riêng cho pi: ~/.pi/agent/agent-stack/plugin trỏ vào plugin/, agents trỏ vào state/pi/agents.

Ví dụ:
  python3 plugin/hosts/pi_host.py check
  python3 plugin/hosts/pi_host.py agents --out state/pi/agents
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO_PLUGIN = Path(__file__).resolve().parents[1]
CONTRACT = Path("hosts") / "pi.json"
AGENT_FIELDS = {"name", "description", "tools"}
# Giới hạn pi áp cho SKILL.md (dist/core/skills.js của pi 1.4.0): sai thì pi chỉ cảnh báo, hay bỏ skill khi thiếu mô tả.
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_SKILL_NAME = 64
MAX_SKILL_DESCRIPTION = 1024


def load_contract(plugin: Path) -> dict:
    return json.loads((plugin / CONTRACT).read_text(encoding="utf-8"))


def split_frontmatter(text: str):
    """(trường, thân) của file Markdown có frontmatter. Danh sách YAML nhiều dòng (`tools:` rồi `  - Read`) gộp vào
    khóa đứng trước thành chuỗi phân cách dấu phẩy; dòng thụt lề khác thì báo lỗi, vì bỏ qua nó có thể làm mất
    danh sách công cụ bị cấm."""
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        raise ValueError("thiếu frontmatter")
    fields, key = {}, None
    for line in m.group(1).splitlines():
        if not line.strip():
            continue
        if line.startswith((" ", "\t")):
            item = re.match(r"^\s+-\s+(.+)$", line)
            if not item or key is None:
                raise ValueError(f"dòng frontmatter không đọc được: {line.strip()[:60]}")
            fields[key] = ", ".join(filter(None, [fields[key], item.group(1).strip()]))
            continue
        if ":" not in line:
            raise ValueError(f"dòng frontmatter không đọc được: {line.strip()[:60]}")
        key, _, value = line.partition(":")
        key = key.strip()
        fields[key] = value.strip()
    return fields, m.group(2)


def yaml_problem(value: str):
    """Lý do giá trị một dòng (không nháy) sẽ hỏng khi pi đọc frontmatter bằng YAML chặt, hay None. Claude Code đọc
    dễ dãi hơn nên lỗi này không lộ ở Claude Code: pi 1.4.0 bỏ cả skill khi gặp `: ` trong description."""
    if not value:
        return None
    if value[0] in "\"'":
        return None if len(value) > 1 and value[-1] == value[0] else "mở dấu nháy mà không đóng"
    if value[0] == "[":
        return None if value.endswith("]") else "mở [ mà không đóng"
    if ": " in value or value.endswith(":"):
        return "có ': ' trong giá trị không nháy (YAML hiểu là khóa lồng nhau); đổi câu hay bọc trong dấu nháy kép"
    if " #" in value:
        return "có ' #' trong giá trị không nháy (YAML cắt phần sau làm chú thích)"
    if value[0] in "{}>|*&!%@`#," or value.startswith(("- ", "? ")):
        return f"bắt đầu bằng ký tự đặc biệt của YAML ({value[0]})"
    return None


def frontmatter_problems(label: str, fields: dict) -> list:
    return [f"{label}: trường {key} {why}" for key, value in fields.items() if (why := yaml_problem(value))]


def names(value: str) -> list:
    """Tên trong chuỗi `A, B` hay `[A, "B"]`."""
    value = (value or "").strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    return [n for x in value.split(",") if (n := x.strip().strip("'\""))]


def pi_tools(fields: dict, spec: dict) -> list:
    """Công cụ pi cho một subagent: có `tools` thì đổi tên từng cái, không có thì mọi công cụ pi trong tool_map
    (Claude Code và pi đều hiểu thiếu `tools` là được mọi công cụ); rồi luôn trừ `disallowedTools`, như Claude Code."""
    tool_map = spec["tool_map"]
    banned = {t for tool in names(fields.get("disallowedTools", "")) for t in tool_map.get(tool, [])}
    wanted = names(fields["tools"]) if "tools" in fields else tool_map
    out = dict.fromkeys(t for tool in wanted for t in tool_map.get(tool, []))
    return [t for t in out if t not in banned]


def check(plugin: Path) -> list:
    """Chỗ lệch giữa plugin và hợp đồng pi; rỗng là khớp."""
    try:
        contract = load_contract(plugin)
    except (OSError, ValueError) as exc:
        return [f"không đọc được {CONTRACT}: {exc}"]
    return (hook_problems(plugin, contract.get("hooks") or {}) + agent_problems(plugin, contract.get("agents") or {})
            + skill_problems(plugin, contract.get("skills") or {}))


def hook_problems(plugin: Path, declared: dict) -> list:
    """Mọi sự kiện trong hooks.json phải có mục (dùng hay bỏ), mục dùng phải gọi đúng script."""
    try:
        hooks_json = json.loads((plugin / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [f"không đọc được hooks/hooks.json: {exc}"]
    problems = []
    for event, groups in hooks_json.items():
        entry = declared.get(event)
        if entry is None:
            problems.append(f"hook {event} có trong hooks.json mà chưa có mục trong {CONTRACT} (dùng hay bỏ, vì sao)")
            continue
        if "skip" in entry:
            if not str(entry["skip"]).strip():
                problems.append(f"hook {event} bị bỏ mà không ghi lý do")
            continue
        script = str(entry.get("script"))
        scripts = {Path(arg).name for group in groups for hook in group.get("hooks", [])
                   for arg in hook.get("args", []) if str(arg).endswith(".py")}
        if script not in scripts:
            problems.append(f"hook {event}: hợp đồng gọi {script}, hooks.json gọi {sorted(scripts)}")
        if not (plugin / "hooks" / script).is_file():
            problems.append(f"hook {event}: không có file hooks/{script}")
        if not entry.get("pi_event"):
            problems.append(f"hook {event}: thiếu pi_event")
        if event == "PreToolUse":
            known = set(entry.get("tool_map", {}).values()) | set(entry.get("no_pi_tool", {}))
            matchers = {tool for group in groups for tool in str(group.get("matcher", "")).split("|") if tool}
            problems += [f"hook PreToolUse chặn công cụ {tool} mà hợp đồng chưa nói công cụ pi nào ứng với nó"
                         for tool in sorted(matchers - known)]
    problems += [f"hợp đồng có hook {event} mà hooks.json không còn" for event in declared if event not in hooks_json]
    return problems


def catalog_problems(kind: str, folder: str, present: set, spec: dict) -> list:
    """Mọi subagent hay skill có trong plugin phải được dùng hay bỏ, và hợp đồng chỉ nhắc cái có thật."""
    use, skip = set(spec.get("use", [])), set(spec.get("skip", {}))
    return ([f"{kind} {name} chưa có mục trong {CONTRACT} (dùng hay bỏ, vì sao)" for name in sorted(present - use - skip)]
            + [f"hợp đồng nhắc {kind} {name} mà {folder}/ không có" for name in sorted((use | skip) - present)]
            + [f"{kind} {name} vừa dùng vừa bỏ" for name in sorted(use & skip)])


def read_fields(path: Path, label: str, problems: list):
    """Trường frontmatter của một file, kèm lỗi YAML chặt ghi vào problems; None nếu không đọc được."""
    try:
        fields, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        problems.append(f"{label}: {exc}")
        return None
    problems += frontmatter_problems(label, fields)
    return fields


def agent_problems(plugin: Path, spec: dict) -> list:
    """Subagent dùng: trường và công cụ phải chuyển được sang pi."""
    tool_map, no_tool = spec.get("tool_map", {}), set(spec.get("no_pi_tool", []))
    known_fields = AGENT_FIELDS | set(spec.get("drop_fields", []))
    present = {p.stem for p in (plugin / "agents").glob("*.md")}
    problems = catalog_problems("subagent", "agents", present, spec)
    for name in sorted(set(spec.get("use", [])) & present):
        label, own = f"subagent {name}", []
        fields = read_fields(plugin / "agents" / f"{name}.md", label, own)
        if fields is not None:
            if not fields.get("description"):
                own.append(f"{label}: thiếu description")
            for key in ("tools", "disallowedTools"):
                if key in fields and not names(fields[key]):
                    own.append(f"{label}: trường {key} có mà rỗng hay không đọc được")
                own += [f"{label}: công cụ {tool} chưa có tên pi trong tool_map"
                        for tool in names(fields.get(key, "")) if tool not in tool_map and tool not in no_tool]
            own += [f"{label}: trường {key} chưa biết chuyển sang pi thế nào (thêm vào drop_fields hay cầu nối)"
                    for key in sorted(set(fields) - known_fields)]
            if not own and not pi_tools(fields, spec):
                own.append(f"{label}: sang pi không còn công cụ nào")
        problems += own
    return problems


def skill_problems(plugin: Path, spec: dict) -> list:
    """Skill dùng phải qua kiểm của pi (tên, mô tả, YAML chặt)."""
    present = {p.parent.name for p in (plugin / "skills").glob("*/SKILL.md")}
    problems = catalog_problems("skill", "skills", present, spec)
    for name in sorted(set(spec.get("use", [])) & present):
        fields = read_fields(plugin / "skills" / name / "SKILL.md", f"skill {name}", problems)
        if fields is None:
            continue
        declared_name = fields.get("name") or name
        if declared_name != name:
            problems.append(f"skill {name}: name trong SKILL.md là {declared_name}, khác tên thư mục")
        if len(declared_name) > MAX_SKILL_NAME or not SKILL_NAME_RE.match(declared_name):
            problems.append(f"skill {name}: tên không hợp lệ với pi (a-z, 0-9, gạch nối đơn, tối đa {MAX_SKILL_NAME})")
        description = fields.get("description", "")
        if not description:
            problems.append(f"skill {name}: thiếu description, pi sẽ bỏ qua skill này")
        elif len(description) > MAX_SKILL_DESCRIPTION:
            problems.append(f"skill {name}: description dài {len(description)} ký tự, pi chỉ nhận tới {MAX_SKILL_DESCRIPTION}")
    return problems


MARKER = "<!-- sinh bởi agent-stack plugin/hosts/pi_host.py"


def render_agent(plugin: Path, name: str, spec: dict) -> str:
    fields, body = split_frontmatter((plugin / "agents" / f"{name}.md").read_text(encoding="utf-8"))
    head = [f"name: {fields.get('name') or name}", f"description: {fields['description']}",
            "tools: " + ", ".join(pi_tools(fields, spec))]
    note = f"{MARKER} từ plugin/agents/{name}.md; sửa ở nguồn -->\n"
    return "---\n" + "\n".join(head) + "\n---\n" + note + body


def sync_agents(plugin: Path, out: Path) -> list:
    """Đưa out về đúng bộ subagent dạng pi của plugin: ghi file đổi (nguyên tử), xóa file do chính hàm này sinh mà
    không còn dùng (file .md khác trong out được giữ). Gọi lúc cài và mỗi lần mở phiên pi. Trả về tên subagent."""
    spec = load_contract(plugin)["agents"]
    used = sorted(spec.get("use", []))
    wanted = {f"{name}.md": render_agent(plugin, name, spec) for name in used}
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.md"):
        if old.name not in wanted and MARKER in old.read_text(encoding="utf-8", errors="replace"):
            old.unlink()
    for filename, text in wanted.items():
        path = out / filename
        try:
            if path.read_text(encoding="utf-8") == text:
                continue
        except OSError:
            pass
        tmp = path.with_name(f".{filename}.{os.getpid()}.tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    return used


def sync(plugin: Path, out: Path):
    """Kiểm hợp đồng rồi mới sinh subagent: (tên đã sinh, chỗ lệch). Lệch thì không ghi gì và giữ bộ cũ, vì bản sinh
    từ hợp đồng lệch có thể mở công cụ bị cấm. CLI, install.py và hook SessionStart trong pi cùng gọi hàm này."""
    problems = check(plugin)
    return ([], problems) if problems else (sync_agents(plugin, out), [])


def main(argv=None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--plugin", type=Path, default=REPO_PLUGIN)
    ap = argparse.ArgumentParser(description="Hợp đồng agent-stack cho pi.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", parents=[common], help="kiểm plugin khớp hợp đồng pi")
    sub.add_parser("agents", parents=[common], help="sinh subagent dạng pi").add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    if args.cmd == "check":
        problems = check(args.plugin)
        for line in problems:
            print(f"- {line}")
        print("Khớp hợp đồng pi." if not problems else f"{len(problems)} chỗ lệch với hợp đồng pi.")
        return 1 if problems else 0
    done, problems = sync(args.plugin, args.out)
    if problems:
        print(f"Không sinh: plugin lệch hợp đồng pi ({problems[0]}).")
        return 1
    print("subagent cho pi:", ", ".join(done))
    return 0


if __name__ == "__main__":
    sys.exit(main())
