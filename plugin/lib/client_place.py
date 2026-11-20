"""Nơi người dùng gõ trong phiên Desktop (Mac hay điện thoại qua Remote Control), để nhắc Claude cách hỏi.

Trên điện thoại hộp next-step (wrap_up) của app Desktop không hiện, hộp AskUserQuestion thì hiện (thử 08/11/2026).
Nơi gõ chỉ có trong trường `clientPlatform` của tin người dùng trong transcript ("desktop_app" trên Mac, "ios" từ
iPhone); hook không nhận được trường này qua JSON đầu vào.

Lúc hook UserPromptSubmit chạy, tin vừa gửi chưa được ghi vào transcript (event 09/11/2026: tin iPhone ghi
`clientPlatform: ios` ngay sau khi hook đọc ra `desktop_app`). Nên việc chia hai bước:
1. UserPromptSubmit chỉ đánh dấu "lượt này cần kiểm" (`mark_pending`), kèm dấu của tin đang gửi.
2. PreToolUse của công cụ `mcp__ccd_turn__*` (chỉ app Desktop có; Claude gọi `update_plan` đầu lượt và `wrap_up`
   trước tin kết thúc) đọc transcript lúc tin đã nằm trong đó (`check`).

Để tiết kiệm token, lời nhắc chỉ chèn khi nơi gõ đổi so với lần báo trước: sang điện thoại thì nhắc viết câu hỏi bằng
chữ, về Mac thì một câu ngắn. Lời nhắc ở lại trong hội thoại nên các lượt sau không cần lặp. Sau compact hay /clear
lời nhắc cũ có thể mất, nên `forget` xóa "đã báo" để lần kiểm sau báo lại.
"""
import hashlib
import json
import os
from pathlib import Path

import agentstack as A

PHONE_PLATFORMS = {"ios", "android"}  # clientPlatform của tin gõ từ app Claude trên điện thoại (ios đã kiểm 08/11/2026)
TRANSCRIPT_BLOCK_BYTES = 256 * 1024
# Số lần kiểm (mỗi lần Claude gọi công cụ `mcp__ccd_turn__*`) mà tin đang gửi vẫn chưa thấy trong transcript, trước khi
# dùng tin người dùng gần nhất. Tin do hệ thống tạo (thông báo nền) không có clientPlatform nên luôn đi hết số lần này.
MAX_TRIES = 3
try:  # biến chỉ để test; giá trị hỏng không được làm hook văng lúc nạp
    TRANSCRIPT_SCAN_BYTES = int(os.environ.get("AGENT_STACK_TRANSCRIPT_SCAN_BYTES", ""))
except ValueError:
    TRANSCRIPT_SCAN_BYTES = 8 * 1024 * 1024

PHONE_NOTE = ("[agent-stack] Người dùng đang gõ từ điện thoại ({platform}, theo {which}) vào phiên Desktop qua Remote "
              "Control. Trên điện thoại hộp next-step (wrap_up) không hiện; hộp AskUserQuestion thì hiện và giữ lượt "
              "chạy tiếp. Từ giờ tới khi có thông báo người dùng về Mac: câu hỏi giữa lượt (cần người dùng chọn rồi "
              "mới làm tiếp được) thì gọi AskUserQuestion và làm tiếp ngay khi có câu trả lời, không viết câu hỏi bằng "
              "chữ rồi gọi wrap_up hay kết thúc lượt chỉ để chờ. Riêng câu hỏi cuối lượt, khi việc đã xong và câu hỏi "
              "đặt trong hộp wrap_up, thì viết bằng chữ trong tin nhắn cuối, kèm lựa chọn đánh số.")
BACK_NOTE = ("[agent-stack] Người dùng đã quay lại gõ trên Mac ({platform}): hộp next-step hiện lại, không cần viết "
             "lại câu hỏi bằng chữ nữa.")


def in_desktop() -> bool:
    """Phiên của app Desktop. Phiên `rc`, CloudCLI và terminal không có hộp next-step nên Claude vốn viết bằng chữ."""
    return os.environ.get("CLAUDE_CODE_ENTRYPOINT", "") == "claude-desktop"


def digest(text: str) -> str:
    return hashlib.sha1(text.strip().encode("utf-8", "replace")).hexdigest()[:16]


def state_path(sid: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in sid)[:100]
    folder = A.state_dir() / "client-place"
    folder.mkdir(exist_ok=True)
    return folder / f"{safe}.json"


def load(sid: str) -> dict:
    data = A.read_json(state_path(sid), {})
    return data if isinstance(data, dict) else {}


def reverse_lines(path: Path, limit: int):
    """(vị trí byte đầu dòng, dòng) của file từ cuối lên, đọc từng khối, tối đa `limit` byte cuối."""
    with path.open("rb") as fh:
        pos = fh.seek(0, 2)
        stop = max(0, pos - limit)
        carry = b""
        while pos > stop:
            size = min(TRANSCRIPT_BLOCK_BYTES, pos - stop)
            pos -= size
            fh.seek(pos)
            parts = (fh.read(size) + carry).split(b"\n")
            starts, at = [], pos
            for part in parts:
                starts.append(at)
                at += len(part) + 1
            carry = parts[0]
            yield from reversed(list(zip(starts[1:], parts[1:])))
        yield pos, carry


def message_text(message) -> str:
    """Chữ của tin người dùng: content là chuỗi, hay danh sách khối (tin kèm ảnh, tệp) thì ghép các khối text."""
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return content if isinstance(content, str) else ""


def _prompt_record(rec):
    """(chữ, nguồn) khi bản ghi transcript là một tin mở lượt: dòng `type: user` có `turnOrigin` hay `origin` (bỏ kết
    quả công cụ, khối meta, tóm tắt compact), hay tin xếp hàng (`attachment.type: queued_command`). Nguồn là
    `turnOrigin`, không có thì `origin.kind`; app đặt các trường này (đo trên bản ghi thật 20/11/2026, Claude Code
    2.1.326: tin gõ trên Mac và điện thoại `human`, brief phiên con `host_synthetic`, tin phiên khác `peer`, tin xếp
    hàng `origin.kind: human`). Agent có Bash vẫn nối được dòng giả vào transcript, như sửa được `state/`: rủi ro còn
    lại cùng loại TM-104, ghi ở TM-170. None khi không phải tin."""
    if not isinstance(rec, dict):
        return None
    if rec.get("type") == "attachment":
        att = rec.get("attachment")
        if isinstance(att, dict) and att.get("type") == "queued_command":
            origin = att.get("origin")
            kind = origin.get("kind") if isinstance(origin, dict) else None
            prompt = att.get("prompt")
            text = prompt if isinstance(prompt, str) else message_text({"content": prompt})
            return text, kind if isinstance(kind, str) else ""
        return None
    if rec.get("type") != "user" or rec.get("isMeta") or rec.get("isCompactSummary") or rec.get("isSidechain"):
        return None
    message = rec.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
        return None
    origin = rec.get("origin")
    kind = rec.get("turnOrigin") if "turnOrigin" in rec else (origin.get("kind") if isinstance(origin, dict) else None)
    if "turnOrigin" not in rec and "origin" not in rec:
        return None  # ghi chú ngắt lượt, kết quả lệnh slash: không phải tin mở lượt
    return message_text(message), kind if isinstance(kind, str) else ""


# Bản ghi của tin thường được app ghi sau khi hook UserPromptSubmit chạy (232/244 lần đo bằng `client-platform`), nên
# xác minh đọc từ cỡ transcript lúc đó; lùi thêm một đoạn cho trường hợp bản ghi đã nằm sẵn (tin xếp hàng).
ORIGIN_SLACK_BYTES = 64 * 1024
ORIGIN_FORWARD_BYTES = 64 * 1024 * 1024  # đọc xuôi tối đa chừng này sau mốc (lượt có output công cụ rất lớn)


def _origin_lines(path: Path, start):
    """Các dòng transcript để tìm bản ghi tin: đọc xuôi từ `start` (lùi ORIGIN_SLACK_BYTES) khi biết mốc, không thì
    TRANSCRIPT_SCAN_BYTES cuối (đọc ngược rồi đảo lại)."""
    if isinstance(start, int) and not isinstance(start, bool) and start >= 0:
        with path.open("rb") as fh:
            fh.seek(max(0, start - ORIGIN_SLACK_BYTES))
            if start > ORIGIN_SLACK_BYTES:
                fh.readline()  # bỏ dòng có thể bị cắt giữa chừng
            read = 0
            for raw in fh:
                read += len(raw)
                if read > ORIGIN_FORWARD_BYTES:
                    break
                yield raw
        return
    yield from reversed([raw for _offset, raw in reverse_lines(path, TRANSCRIPT_SCAN_BYTES)])


def prompt_origin(transcript, digest_value: str, start=None):
    """Nguồn (`human`, `host_synthetic`, `peer`…; "" khi bản ghi không ghi nguồn) của bản ghi tin CUỐI CÙNG có dấu chữ
    `digest_value` (agentstack.prompt_digest), tìm từ mốc `start` (cỡ transcript lúc hook UserPromptSubmit chạy). Lấy
    bản cuối để tin người dùng cũ cùng chữ không cho mượn lời đồng ý; tin khác chen vào sau (thông báo nền, tin xếp
    hàng) không làm lệch. None khi không đọc được hay chưa thấy: người gọi coi như không phải người dùng gõ."""
    import agentstack as A
    if not isinstance(transcript, str) or not transcript or not isinstance(digest_value, str) or not digest_value:
        return None
    found_kind = None
    try:
        for raw in _origin_lines(Path(transcript), start):
            if b'"user"' not in raw and b'queued_command' not in raw:
                continue
            try:
                rec = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            found = _prompt_record(rec)
            if found is not None and A.prompt_digest(found[0]) == digest_value:
                found_kind = found[1]
    except (OSError, TypeError, ValueError):
        return None
    return found_kind


def last_client_platform(transcript):
    """(clientPlatform của tin người dùng cuối trong transcript, dấu chữ của tin đó, vị trí byte của bản ghi).

    Trả (None, "", -1) khi không đọc được hay không thấy trong TRANSCRIPT_SCAN_BYTES cuối."""
    try:
        for offset, raw in reverse_lines(Path(transcript), TRANSCRIPT_SCAN_BYTES):
            if b'"clientPlatform"' not in raw:
                continue
            try:
                rec = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            if not isinstance(rec, dict) or rec.get("type") != "user" or not isinstance(rec.get("clientPlatform"), str):
                continue
            return rec["clientPlatform"], digest(message_text(rec.get("message"))), offset
    except (OSError, TypeError, ValueError):
        pass
    return None, "", -1


def transcript_size(transcript):
    """Cỡ transcript lúc người dùng vừa gửi tin: bản ghi nằm từ vị trí này trở đi là tin mới. None khi không biết."""
    if not isinstance(transcript, str) or not transcript:
        return None
    try:
        return os.path.getsize(transcript)
    except OSError:
        return 0 if not os.path.exists(transcript) else None  # phiên mới chưa có file: mọi bản ghi đều mới


def mark_pending(data: dict) -> None:
    """UserPromptSubmit: đánh dấu lượt mới cần kiểm nơi gõ. Không đọc transcript, không chèn gì."""
    sid = data.get("session_id", "")
    if not sid or not in_desktop():
        return
    state = load(sid)
    state["pending"] = {"prompt": digest(data.get("prompt") or ""), "size": transcript_size(data.get("transcript_path")),
                        "tries": 0}
    A.write_json_atomic(state_path(sid), state)


def forget(sid: str) -> None:
    """SessionStart sau compact hay /clear: lời nhắc cũ có thể đã mất khỏi hội thoại, nên lần kiểm sau báo lại."""
    path = state_path(sid) if sid else None
    if path is None or not path.exists():
        return
    state = load(sid)
    if state.pop("told", None) is not None:
        A.write_json_atomic(path, state)


def check(data: dict) -> str:
    """PreToolUse: lượt có đánh dấu thì đọc nơi gõ; trả lời nhắc khi nơi gõ đổi so với lần báo trước, không thì ""."""
    sid = data.get("session_id", "")
    if not sid or not in_desktop():
        return ""
    state = load(sid)
    pending = state.get("pending")
    if not isinstance(pending, dict):
        return ""  # lượt này đã kiểm: chỉ tốn một lần đọc file trạng thái nhỏ
    platform, found, offset = last_client_platform(data.get("transcript_path"))
    size = pending.get("size")
    if isinstance(size, int) and not isinstance(size, bool) and size >= 0:
        # bản ghi nằm sau chỗ cuối file lúc gửi tin là tin đang gửi; không so chữ vì tin kèm ảnh, tệp hay hai máy gõ
        # trùng chữ ("ok") làm phép so chữ sai
        current = offset >= size
    else:
        current = bool(found) and found == pending.get("prompt")
    tries = int(pending.get("tries") or 0) + 1
    if not current and tries < MAX_TRIES:
        state["pending"] = {**pending, "tries": tries}  # tin đang gửi chưa ghi xong: lần gọi công cụ sau kiểm lại
        A.write_json_atomic(state_path(sid), state)
        return ""
    state.pop("pending", None)
    # chỉ hai giá trị đã thấy thật; giá trị lạ (bản web của Remote Control chẳng hạn) thì không đoán
    kind = "phone" if platform in PHONE_PLATFORMS else "desktop" if platform == "desktop_app" else None
    told = state.get("told")
    note = ""
    if kind == "phone" and told != "phone":
        which = "tin này" if current else "tin người dùng gần nhất trong transcript"
        note = PHONE_NOTE.format(platform=platform, which=which)
    elif kind == "desktop" and told == "phone":
        note = BACK_NOTE.format(platform=platform)
    if kind is not None:
        state["told"] = kind  # lần đầu ở Mac chỉ ghi nhớ, không nhắc: Mac là mặc định
    A.write_json_atomic(state_path(sid), state)
    A.log_event("client-platform", {"session": sid, "platform": platform, "current": current, "tries": tries,
                                    "noted": bool(note)})
    return note
