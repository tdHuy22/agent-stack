#!/usr/bin/env python3
"""Đo phần nạp sẵn (context có từ đầu phiên) của Claude Code theo bộ plugin, không gọi model thật.

Chạy binary của app (`claude_app.py`) với thư mục cấu hình tạm (`CLAUDE_CONFIG_DIR`, không đụng `~/.claude/`) và
`ANTHROPIC_BASE_URL` trỏ vào một máy chủ giả trên 127.0.0.1: máy chủ giữ thân request đầu tiên (system, tin nhắn,
tool) rồi trả lỗi 400, nên không tốn tiền và không có gì ra mạng tới API. Đếm ký tự: tổng request, từng mục trong
danh sách skill và danh sách subagent.

Lệnh:
  tools/preload.py [--plugin-dir DIR ...] [--project DIR] [--config-dir DIR] [--state DIR] [--find STR ...] [--json]
--project: thư mục chạy phiên (đọc `.claude/settings.local.json` của nó, như phiên thật); mặc định là thư mục tạm
rỗng. Phiên `-p` chạy hook và cài đặt của thư mục đó mà không hỏi tin cậy: chỉ trỏ vào thư mục của bạn hay thư mục
tạm, không vào repo lạ. --config-dir: thư mục cấu hình đã dựng sẵn (ví dụ có plugin cài bằng `claude plugin install`); mặc định thư mục
tạm có `settings.json` rỗng.
"""
from __future__ import annotations

import argparse
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import claude_app  # noqa: E402

SKILLS_HEAD = "The following skills are available"
AGENTS_HEAD = "Available agent types"
# Chỉ chuyển cho binary các biến cần để chạy (danh sách cho phép): không khóa, token hay socket của phiên đang chạy.
KEEP_ENV = ("PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "TMPDIR", "TERM", "PYENV_ROOT", "PYENV_VERSION")


class Capture(http.server.BaseHTTPRequestHandler):
    bodies: list = []  # noqa: RUF012 (run() đặt lại mỗi lần đo)

    def do_POST(self):  # noqa: N802 (tên do http.server đặt)
        size = min(int(self.headers.get("content-length") or 0), 16 << 20)
        if self.path.startswith("/v1/messages"):
            self.bodies.append(self.rfile.read(size))
        else:
            self.rfile.read(size)
        msg = b'{"type":"error","error":{"type":"invalid_request_error","message":"preload capture"}}'
        self.send_response(400)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(msg)))
        self.end_headers()
        self.wfile.write(msg)

    def do_GET(self):  # noqa: N802
        self.send_response(404)
        self.end_headers()

    def log_message(self, *args):
        pass


def entries(text: str, head: str, stop: str | None) -> dict:
    """{tên: số ký tự} của các dòng `- tên: mô tả` trong khối bắt đầu bằng `head`."""
    start = text.find(head)
    if start < 0:
        return {}
    block = text[start:]
    if stop and stop in block[len(head):]:
        block = block[:len(head) + block[len(head):].index(stop)]
    out = {}
    for item in block.split("\n- ")[1:]:
        key = item.split(": ", 1)[0].strip()  # "plugin:skill: mô tả" hay "skill: mô tả"
        out[key] = len(item.split("\n\n")[0]) + 2
    return out


def measure(body: dict, find=()) -> dict:
    """Đếm ký tự của một request /v1/messages."""
    texts = [p.get("text", "") for p in body.get("system") or []]
    for msg in body.get("messages") or []:
        content = msg.get("content")
        texts += [content] if isinstance(content, str) else [p.get("text", "") for p in content or []]
    joined = "\n".join(texts)
    tools = sum(len(json.dumps(t, ensure_ascii=False)) for t in body.get("tools") or [])
    skills = entries(joined, SKILLS_HEAD, None)
    agents = entries(joined, AGENTS_HEAD, SKILLS_HEAD)
    return {"total": len(joined) + tools, "text": len(joined), "tools": tools,
            "found": {s: joined.count(s) for s in find},
            "skills": skills, "agents": agents, "skills_total": sum(skills.values()),
            "agents_total": sum(agents.values())}


def run(plugin_dirs, project=None, config_dir=None, timeout=120, state=None, find=()) -> dict:
    """Chạy một phiên `-p` tới máy chủ giả; trả số đo của request lớn nhất (request của vòng chính)."""
    binary = claude_app.find()
    if not binary:
        raise SystemExit("preload: không tìm thấy binary của app (tools/claude_app.py)")
    Capture.bodies = []
    server = http.server.HTTPServer(("127.0.0.1", 0), Capture)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    work = Path(tempfile.mkdtemp(prefix="preload-"))
    try:
        cfg = Path(config_dir) if config_dir else work / "cfg"
        if not config_dir:
            cfg.mkdir()
            (cfg / "settings.json").write_text("{}\n")
        cwd = Path(project) if project else work / "proj"
        cwd.mkdir(exist_ok=True)
        env = {k: v for k, v in os.environ.items() if k in KEEP_ENV or k.startswith("LC_")}
        env["NO_PROXY"] = env["no_proxy"] = "127.0.0.1,localhost"
        env.update(CLAUDE_CONFIG_DIR=str(cfg), ANTHROPIC_BASE_URL=f"http://127.0.0.1:{server.server_port}",
                   ANTHROPIC_API_KEY="sk-preload-dummy", CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1",
                   AGENT_STACK_STATE=str(state or work / "state"))
        cmd = [str(binary[1]), "-p", "hi"]
        for d in plugin_dirs:
            cmd += ["--plugin-dir", str(d)]
        subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, timeout=timeout, check=False)
    finally:
        server.shutdown()
        server.server_close()
        shutil.rmtree(work, ignore_errors=True)
    if not Capture.bodies:
        raise SystemExit("preload: binary không gửi request nào tới máy chủ giả")
    return measure(json.loads(max(Capture.bodies, key=len)), find)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Đo phần nạp sẵn của Claude Code (máy chủ API giả, cấu hình tạm)")
    ap.add_argument("--plugin-dir", action="append", default=[])
    ap.add_argument("--project")
    ap.add_argument("--config-dir")
    ap.add_argument("--state", help="AGENT_STACK_STATE cho hook (bản ghi bộ đang bật của profile.py)")
    ap.add_argument("--find", action="append", default=[], help="đếm số lần chuỗi xuất hiện trong phần chữ")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    result = run(args.plugin_dir, args.project, args.config_dir, state=args.state, find=args.find)
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
        return 0
    print(f"Tổng {result['total']} ký tự (chữ {result['text']}, tool {result['tools']}); "
          f"skill {result['skills_total']} ({len(result['skills'])} mục); "
          f"subagent {result['agents_total']} ({len(result['agents'])} mục)"
          + "".join(f"; «{s}» ×{n}" for s, n in result["found"].items()))
    for kind in ("skills", "agents"):
        for name, size in sorted(result[kind].items(), key=lambda x: -x[1]):
            print(f"  {kind[:-1]:6} {size:6}  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
