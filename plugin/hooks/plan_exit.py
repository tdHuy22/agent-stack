#!/usr/bin/env python3
"""Hook PostToolUse sau ExitPlanMode (ý 6 của kế hoạch agent-stack theo project): kế hoạch phiên vừa được người dùng duyệt.

Kiểm bằng luật tĩnh (khuôn `ke-hoach` của skill session-keeper): có mục "Tiêu chí xong" và mục "Lệnh kiểm chứng" có lệnh
(khối mã hay chữ trong dấu huyền); thiếu thì nhắc model qua additionalContext (kế hoạch đã duyệt nên không chặn được).
Đủ tiêu chí thì ghi MỘT dòng `- **Tiêu chí xong** (…): 1) … 2) …` vào §0, chỉ khi §0 chưa có tiêu chí.

Ghi vào file của người dùng nên theo threat model TM-107 đến TM-110: chỉ chép mục tiêu chí (tối đa 4 mục, mỗi mục tối
đa 240 ký tự, một dòng); chỉ ghi file kế hoạch trong gốc project, bỏ qua symlink; ghi nguyên tử; đọc tối đa 20 000 ký
tự; mọi lỗi thì im lặng, thoát 0. Log sự kiện chỉ ghi tên khóa của payload, không ghi nội dung kế hoạch.
Chấm model cho từng bước là việc của GĐ5, không làm ở đây.
"""
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import agentstack as A  # noqa: E402

MAX_PLAN = 20_000
MAX_ITEMS = 4
MAX_ITEM = 240
ITEM_RE = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s+(\S.*)$")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


def plan_text(data) -> str:
    """Văn bản kế hoạch: `tool_response.plan`, dự phòng `tool_input.plan`; chuỗi rỗng nếu không có."""
    for key in ("tool_response", "tool_input"):
        value = data.get(key)
        if isinstance(value, dict) and isinstance(value.get("plan"), str):
            return value["plan"][:MAX_PLAN]
        if key == "tool_response" and isinstance(value, str):
            return value[:MAX_PLAN]
    return ""


def keys_of(data, key) -> list:
    value = data.get(key)
    return sorted(str(k) for k in value) if isinstance(value, dict) else []


def sections(plan: str) -> list:
    """[(tên đề mục đã bỏ dấu, các dòng thân)] theo đề mục markdown; dòng trong khối mã không tính là đề mục."""
    out, name, body, fenced = [], None, [], False
    for line in plan.splitlines():
        if FENCE_RE.match(line):
            fenced = not fenced
        m = None if fenced else A.HEADING_RE.match(line)
        if m:
            if name is not None:
                out.append((name, body))
            name, body = A.fold(m.group(2)), []
        elif name is not None:
            body.append(line)
    if name is not None:
        out.append((name, body))
    return out


def find_section(parts, needle: str):
    return next((body for name, body in parts if needle in name), None)


def clean(text: str, limit: int = MAX_ITEM) -> str:
    text = CONTROL_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip().lstrip("#>").strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def indent(line: str) -> int:
    return len(line.expandtabs(4)) - len(line.expandtabs(4).lstrip())


HTML_COMMENT_RE = re.compile(r"<!--.*?(?:-->|\Z)", re.S)


def raw_criteria(body) -> list:
    """Các mục đánh số hay gạch đầu dòng của mục tiêu chí, chưa cắt; dòng thụt vào sâu hơn mục đầu (kể cả ý con có
    gạch đầu dòng, S11) được nối vào mục trước, không thành tiêu chí riêng."""
    items, top = [], None
    for line in body or []:
        m = ITEM_RE.match(line)
        if m and (top is None or indent(line) <= top):
            top = indent(line) if top is None else top
            items.append(m.group(1))
        elif items and line.strip() and line[:1] in " \t":
            items[-1] += " " + (m.group(1) if m else line.strip())
    return items[:MAX_ITEMS]


def criteria_items(body) -> list:
    """Tiêu chí đã làm sạch và cắt ở MAX_ITEM ký tự (raw_criteria)."""
    return [x for x in (clean(i) for i in raw_criteria(body)) if x][:MAX_ITEMS]


def has_command(body) -> bool:
    text = "\n".join(body or [])
    return bool(re.search(r"```|~~~", text) or re.search(r"`[^`\n]+`", text))


def task_title(plan: str) -> str:
    """Tên việc: đề mục `#` ngoài khối mã và trước đề mục `##` đầu tiên; không có thì "kế hoạch phiên"."""
    fenced = False
    for line in plan.splitlines():
        if FENCE_RE.match(line):
            fenced = not fenced
            continue
        m = None if fenced else A.HEADING_RE.match(line)
        if not m:
            continue
        if len(m.group(1)) > 1:
            break
        title = re.sub(r"^(kế hoạch phiên|ke hoach phien)\s*:\s*", "", m.group(2), flags=re.I)
        return clean(title, 80) or "kế hoạch phiên"
    return "kế hoạch phiên"


def section0_bounds(lines):
    """(chỉ số dòng tiêu đề §0, chỉ số dòng hết §0) hay (-1, -1)."""
    for i, line in enumerate(lines):
        m = A.HEADING_RE.match(line)
        if m and A.SECTION0_RE.search(A.fold(m.group(2))):
            level = len(m.group(1))
            for j in range(i + 1, len(lines)):
                h = A.HEADING_RE.match(lines[j])
                if h and len(h.group(1)) <= level:
                    return i, j
            return i, len(lines)
    return -1, -1


def is_criteria_label(line: str) -> bool:
    m = re.match(r"^[-*]\s+\*\*\s*([^*:(]+)", line)
    return bool(m) and A.fold(m.group(1)).strip().startswith(A.CRITERIA_LABELS)


def write_criteria(root: Path, items, title: str):
    """Ghi dòng tiêu chí vào §0 của file kế hoạch trong gốc project. Trả về ("wrote", tên file), ("exists", tên file)
    khi §0 đã có tiêu chí (không ghi đè), hay ("", "") khi không ghi được."""
    found = A.read_plan(root)
    if not found or not found[2]["heading"]:
        return "", ""
    path = found[0]
    try:
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            return "", ""
    except OSError:
        return "", ""
    name = str(path.relative_to(root))
    text = path.read_bytes().decode("utf-8")  # (giữ nguyên CRLF) đọc lại ngay trước khi ghi (hai phiên có thể cùng ghi)
    if A.has_value(A.parse_section0(text)["fields"].get("criteria")):
        return "exists", name
    lines = text.splitlines(keepends=True)
    start, end = section0_bounds([x.rstrip("\r\n") for x in lines])
    if start < 0:
        return "", ""
    day = time.strftime("%d/%m/%Y")
    body = " ".join(f"{n}) {item}" for n, item in enumerate(items, 1))
    nl = "\r\n" if "\r\n" in text else "\n"
    new = f"- **Tiêu chí xong** ({title}, {day}, nguồn: kế hoạch phiên, bạn duyệt): {body}{nl}"
    labels = [i for i in range(start + 1, end) if is_criteria_label(lines[i])]
    if labels:  # nhãn có sẵn mà rỗng ("chưa có"): thay ngay tại dòng đó, không thêm dòng trùng
        lines[labels[-1]] = new
    else:  # trước gạch đầu dòng đầu tiên của §0, để dòng "Cập nhật" của mẫu vẫn đứng riêng
        bullets, fenced = [], False  # chỉ gạch đầu dòng cấp đầu ngoài khối mã, như parse_section0
        for i in range(start + 1, end):
            if FENCE_RE.match(lines[i]):
                fenced = not fenced
            elif not fenced and re.match(r"^[-*]\s", lines[i]):
                bullets.append(i)
        at = bullets[0] if bullets else end
        while not bullets and at - 1 > start and not lines[at - 1].strip():
            at -= 1  # §0 không có gạch đầu dòng: cuối §0, trước các dòng trống cuối, để không nuốt dòng bên dưới
        if at > 0 and not lines[at - 1].endswith("\n"):
            lines[at - 1] += nl
        lines.insert(at, new)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    try:
        tmp.write_bytes("".join(lines).encode("utf-8"))
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    return "wrote", name


def main():
    data = A.read_hook_input()
    if data.get("tool_name") not in (None, "ExitPlanMode"):
        return
    response = data.get("tool_response")
    if data.get("agent_id") or (isinstance(response, dict) and response.get("isAgent")):
        return  # ExitPlanMode của subagent: người dùng chưa duyệt gì, không ghi vào §0
    plan = plan_text(data)
    cwd = data.get("cwd")
    if not plan.strip() or not isinstance(cwd, str) or not cwd:
        return
    parts = sections(plan)
    body = find_section(parts, "tieu chi xong")
    items = criteria_items(body)
    missing = []
    if not items:
        missing.append("mục `## Tiêu chí xong` (2–4 mục, mỗi mục một lệnh phải đạt hay một cặp đầu vào và đầu ra)")
    if not has_command(find_section(parts, "lenh kiem")):
        missing.append("mục `## Lệnh kiểm chứng` có lệnh (khối mã hay chữ trong dấu huyền)")
    clipped = [n for n, raw in enumerate(raw_criteria(body), 1) if len(re.sub(r"\s+", " ", raw).strip()) > MAX_ITEM]
    spec_rec = None
    # Mục `## Spec` chỉ tính phần người dùng thấy lúc duyệt: bỏ chú thích HTML (F8); phiên không người (`claude -p`)
    # thì không có ai duyệt, không ghi.
    visible = HTML_COMMENT_RE.sub("", plan)
    spec_body = next((b for name, b in sections(visible) if name.strip() == "spec"), None)
    if spec_body is not None and not A.non_interactive(data):  # S6: duyệt kế hoạch có `## Spec` là duyệt các dòng đó
        try:
            import specbook
            spec_rec = specbook.approve_plan(cwd, spec_body)
        except Exception as exc:  # noqa: BLE001
            A.log_event("hook-error", {"hook": "plan_exit.spec", "error": repr(exc)[:300]})
    root = A.project_root(cwd)
    status, where = "", ""
    if items:
        try:
            status, where = write_criteria(root, items, task_title(plan))
        except OSError:
            status, where = "", ""
    wrote = where if status == "wrote" else ""
    A.log_event("plan-exit", {"session": data.get("session_id"), "response_keys": keys_of(data, "tool_response"),
                              "input_keys": keys_of(data, "tool_input"), "plan_chars": len(plan),
                              "criteria": len(items), "missing": len(missing), "wrote": bool(wrote),
                              "kept_existing": status == "exists"})
    context = ""
    if missing:
        context = ("[agent-stack] Kế hoạch phiên vừa được duyệt còn thiếu " + " và ".join(missing) + ". Bổ sung vào §0 "
                   "(khuôn: skill session-keeper, mục `ke-hoach`) và nói với người dùng trước khi sửa file.")
    elif wrote:
        context = (f"[agent-stack] Đã ghi tiêu chí xong của kế hoạch phiên vào §0 của `{wrote}`. Done-gate cuối phiên so "
                   "kết quả với các tiêu chí này; đổi tiêu chí giữa chừng thì hỏi người dùng.")
    elif status == "exists":
        context = (f"[agent-stack] §0 của `{where}` đã có tiêu chí xong (của việc trước hay việc khác), hook không ghi đè tiêu "
                   "chí của kế hoạch vừa duyệt. Hỏi người dùng nên thay hay giữ; done-gate sẽ so kết quả với tiêu chí đang "
                   "ở §0.")
    if wrote and clipped:  # S11: tiêu chí gộp ý con dài quá trần thì bị cắt; báo để chép tay phần còn lại
        context += (f" Tiêu chí {', '.join(str(n) for n in clipped)} dài quá {MAX_ITEM} ký tự nên bị cắt khi ghi vào "
                    "§0: chép tay phần bị cắt từ kế hoạch vào §0.")
    if spec_rec:
        context = (context + " " if context else "") + (
            f"[agent-stack] Đã ghi {len(spec_rec['lines'])} dòng của mục `## Spec` vào sổ duyệt spec (nguồn: kế "
            "hoạch). Chép đúng nguyên chữ từng dòng, cả số thứ tự, vào `.agent/spec/<slug>.txt` thì bánh cóc của "
            "done-gate tính là đã duyệt ở mức vừa; mức cao còn cần trang `spec.py page` và câu \"duyệt spec <mã>\".")
    system = f"📝 Đã ghi tiêu chí xong vào §0 ({wrote})" if wrote else ""
    A.emit("PostToolUse", context, system)


if __name__ == "__main__":
    A.run_hook(main)
