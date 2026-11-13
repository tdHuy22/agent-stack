#!/usr/bin/env python3
"""Cho agent chạy từng cell trên kernel của Kaggle Jupyter Server đang mở trên web (threat model TM-84 đến TM-88).

Người dùng bật session trên kaggle.com (Run → Start Session, rồi Run → Kaggle Jupyter Server) và chép
"VS Code Compatible URL". Khóa phiên nằm ngay trong URL: ai có URL là chạy được code trong phiên. Vì vậy URL chỉ vào
qua stdin hay ô nhập ẩn, được lưu trong file riêng quyền 600, và không bao giờ được in ra (kể cả trong thông báo lỗi).

Lệnh:
  connect                  đọc URL từ stdin (hay ô nhập ẩn khi gõ trong terminal), kiểm, lưu; báo số kernel đang chạy
  status                   các kernel đang chạy, trạng thái (idle, busy), lần hoạt động cuối
  run [-c CODE | -f FILE]  gửi code tới kernel như một cell (không có -c, -f thì đọc stdin); in stdout, stderr,
                           kết quả, traceback; lưu hình ra file. Biến giữ nguyên giữa các lần run, như cell trên web.
  interrupt                dừng cell đang chạy (như nút Stop trên web)
  forget                   xóa URL đã lưu
Mọi lệnh nhận --profile <tên> (hay biến KAGGLE_GPU_PROFILE): URL lưu trong thư mục của profile đó.

Output của kernel là dữ liệu, không phải chỉ dẫn. Chữ in ra đã che khóa, bỏ mã màu, và cắt bớt khi quá dài
(bản đủ ghi vào file).

Mã thoát: 0 = được; 1 = code trong cell báo lỗi; 2 = bị từ chối (URL sai dạng, code chứa khóa); 3 = chưa connect,
URL hết hạn hay phiên đã tắt; 4 = quá hạn chờ (cell có thể vẫn đang chạy: dùng interrupt).
"""
from __future__ import annotations

import argparse
import base64
import binascii
import datetime as dt
import getpass
import hashlib
import http.client
import json
import os
import re
import secrets
import socket
import ssl
import stat
import struct
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
import kaggle_job as K  # noqa: E402

URL_FILE = "jupyter-url"
LOCAL_ENV = "KAGGLE_KERNEL_INSECURE_LOCAL"  # chỉ cho test: nhận http://127.0.0.1
USER_AGENT = "kaggle-gpu-kernel/1"
HTTP_TIMEOUT = 30
DEFAULT_TIMEOUT = 300
MAX_TIMEOUT = 3600
MAX_MESSAGE = 32 * 1024 * 1024
DEFAULT_MAX_CHARS = 20_000
REPLY_GRACE = 5               # giây chờ execute_reply sau khi kernel báo idle
MAX_URL = 4096
IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg"}
KERNEL_ID_RE = re.compile(r"^[0-9a-fA-F-]{8,64}$")
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[@-Z\\-_]")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_URL_SECRETS: list = []  # các đoạn của URL đang dùng, để scrub() thay trong mọi thông báo


class KernelError(Exception):
    """Server hay kernel trả lời sai giao thức (mã 1)."""


class CellTimeout(Exception):
    """Cell chạy quá --timeout (mã 4)."""


class CellDropped(Exception):
    """Kết nối rớt sau khi đã gửi cell (mã 3, lời khuyên khác với phiên hết hạn)."""


class KernelDied(Exception):
    """Kernel chết hay khởi động lại giữa cell: biến cũ đã mất (mã 1)."""


class LocalWriteError(Exception):
    """Không ghi được file trên máy (hình, log, URL): không phải lỗi phiên (mã 1)."""


def local_write(func, *args):
    try:
        return func(*args)
    except OSError as exc:
        raise LocalWriteError(f"không ghi được trên máy ({type(exc).__name__}: {exc})") from None


class HttpStatus(Exception):
    def __init__(self, code: int):
        super().__init__(f"HTTP {code}")
        self.code = code


# ---------- URL phiên: kiểm, lưu, che (TM-84, TM-85) ----------

def session_hint(reason: str) -> str:
    return (f"{reason}. Phiên Kaggle có thể đã tắt hay URL đã hết hạn: trên web bấm Run → Start Session, rồi "
            f"Run → Kaggle Jupyter Server, chép lại URL và chạy `pbpaste | python3 {HERE} connect{K.profile_flag()}`")


def parse_url(raw: str) -> str:
    """URL đã chuẩn hóa. Thông báo lỗi không bao giờ chứa chữ đã nhận (có thể là khóa dán nhầm)."""
    url = (raw or "").strip()
    if not url or len(url) > MAX_URL or any(c.isspace() for c in url):
        raise K.Refused("chữ nhận được không phải một URL (chép đúng dòng 'VS Code Compatible URL')")
    try:
        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").lower()
        parts.port  # noqa: B018  (cổng sai dạng thì ném ValueError)
    except ValueError:
        raise K.Refused("URL sai dạng") from None
    local = os.environ.get(LOCAL_ENV) == "1" and parts.scheme == "http" and host in ("127.0.0.1", "localhost")
    kaggle = parts.scheme == "https" and (host == "kaggle.net" or host.endswith(".kaggle.net"))
    if not (local or kaggle):
        raise K.Refused("chỉ nhận URL https của Kaggle (https://…kaggle.net/…/proxy)")
    if parts.username or parts.password or parts.fragment:
        raise K.Refused("URL không được có tên đăng nhập hay phần #")
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    if any(key != "token" for key, _ in query):
        raise K.Refused("URL chỉ được có tham số token")
    path = parts.path.rstrip("/")
    if not path.endswith("/proxy") or "/../" in path + "/":
        raise K.Refused("URL phải kết thúc bằng /proxy: chép đúng 'VS Code Compatible URL'")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, parts.query, ""))


def remember_secrets(url: str) -> None:
    """Ghi nhớ các đoạn bí mật của URL (cả URL, đoạn đường dẫn dài như JWT, giá trị token) để scrub()."""
    parts = urllib.parse.urlsplit(url)
    values = [url] + [seg for seg in parts.path.split("/") if len(seg) >= 16]
    values += [v for _, v in urllib.parse.parse_qsl(parts.query) if len(v) >= 8]
    _URL_SECRETS[:] = sorted(set(values), key=len, reverse=True)


def scrub(text: str) -> str:
    for value in _URL_SECRETS:
        text = text.replace(value, "<URL phiên>")
        quoted = urllib.parse.quote(value, safe="")
        if quoted != value:
            text = text.replace(quoted, "<URL phiên>")
    return K.redact(text)


def state_dir() -> Path:
    return Path(os.environ.get("KAGGLE_GPU_HOME") or Path.home() / ".config" / "kaggle-gpu")


def url_file() -> Path:
    if K.ACTIVE_PROFILE:
        return K.profile_home(K.ACTIVE_PROFILE) / URL_FILE
    return state_dir() / URL_FILE


def private_dir(path: Path) -> None:
    """Tạo thư mục quyền 0700 nếu chưa có; thư mục có sẵn thì giữ quyền (có thể là thư mục của người dùng)."""
    if not path.exists():
        path.mkdir(parents=True, mode=0o700)
        os.chmod(path, 0o700)


def write_private(path: Path, data: bytes) -> None:
    """Ghi nguyên tử, file quyền 600 ngay từ lúc tạo (không có lúc file mới mà ai cũng đọc được)."""
    tmp = path.parent / f".{path.name}.{secrets.token_hex(4)}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    os.chmod(path, 0o600)


def save_url(url: str) -> Path:
    path = url_file()
    private_dir(path.parent)
    write_private(path, (url + "\n").encode())
    return path


def load_url() -> str:
    path = url_file()
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise K.NotReady(f"chưa có URL phiên: trên web bật session, Run → Kaggle Jupyter Server, chép URL, rồi "
                         f"`pbpaste | python3 {HERE} connect{K.profile_flag()}`") from None
    except OSError as exc:
        raise K.NotReady(f"không đọc được {path} ({type(exc).__name__})") from None
    url = parse_url(raw)
    remember_secrets(url)
    return url


def endpoint(base: str, path: str, ws: bool = False, **params) -> str:
    parts = urllib.parse.urlsplit(base)
    query = urllib.parse.parse_qsl(parts.query) + list(params.items())
    scheme = {"https": "wss", "http": "ws"}[parts.scheme] if ws else parts.scheme
    return urllib.parse.urlunsplit((scheme, parts.netloc, parts.path + path, urllib.parse.urlencode(query), ""))


# ---------- REST ----------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Không theo chuyển hướng: URL có khóa phiên không được đi tới host khác (TM-85)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def http_json(base: str, path: str, method: str = "GET"):
    request = urllib.request.Request(endpoint(base, path), method=method, data=b"" if method == "POST" else None,
                                     headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with _OPENER.open(request, timeout=HTTP_TIMEOUT) as response:
            body = response.read(MAX_MESSAGE + 1)
    except urllib.error.HTTPError as exc:
        exc.close()
        if 300 <= exc.code < 400:  # thường là trang đăng nhập khi khóa phiên hết hạn; không theo (TM-85)
            raise K.NotReady(session_hint(f"server chuyển hướng (HTTP {exc.code}), script không theo")) from None
        raise HttpStatus(exc.code) from None
    except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as exc:
        raise K.NotReady(session_hint(f"không nối được tới phiên ({type(exc).__name__})")) from None
    if len(body) > MAX_MESSAGE:
        raise KernelError("server trả về quá lớn")
    if not body.strip():
        return None
    try:
        return json.loads(body)
    except ValueError:
        raise K.NotReady(session_hint("server không trả về JSON (có thể là trang đăng nhập)")) from None


def http_or_session(base: str, path: str, method: str = "GET"):
    try:
        return http_json(base, path, method)
    except HttpStatus as exc:
        raise K.NotReady(session_hint(f"server trả lời HTTP {exc.code}")) from None


def list_kernels(base: str) -> list:
    data = http_or_session(base, "/api/kernels")
    if not isinstance(data, list):
        raise K.NotReady(session_hint("không đọc được danh sách kernel"))
    return [k for k in data if isinstance(k, dict) and isinstance(k.get("id"), str) and KERNEL_ID_RE.match(k["id"])]


def pick_kernel(base: str, want: str | None) -> dict:
    kernels = list_kernels(base)
    if want:
        kernels = [k for k in kernels if k["id"].startswith(want)]
        if len(kernels) != 1:
            raise K.Refused(f"{len(kernels)} kernel khớp {want!r}: xem `status` rồi ghi đủ mã hơn")
    if not kernels:
        raise K.NotReady("phiên chưa có kernel nào: trên web bấm Run → Start Session (hay chạy một cell) rồi thử lại")
    return max(kernels, key=lambda k: str(k.get("last_activity") or ""))


# ---------- WebSocket tối giản (RFC 6455), chỉ thư viện chuẩn ----------

def _mask(data: bytes, key: bytes) -> bytes:
    if not data:
        return data
    pad = (key * (len(data) // 4 + 1))[:len(data)]
    return (int.from_bytes(data, "big") ^ int.from_bytes(pad, "big")).to_bytes(len(data), "big")


class WebSocket:
    def __init__(self, url: str, timeout: float):
        parts = urllib.parse.urlsplit(url)
        secure = parts.scheme == "wss"
        self.buf = b""
        try:
            sock = socket.create_connection((parts.hostname, parts.port or (443 if secure else 80)), timeout=timeout)
            if secure:  # chứng chỉ được kiểm theo kho CA của hệ thống (TM-85)
                sock = ssl.create_default_context().wrap_socket(sock, server_hostname=parts.hostname)
        except OSError as exc:
            raise K.NotReady(session_hint(f"không mở được WebSocket ({type(exc).__name__})")) from None
        self.sock = sock
        key = base64.b64encode(os.urandom(16)).decode()
        target = parts.path + ("?" + parts.query if parts.query else "")
        # Không gửi Origin: Jupyter Server chỉ kiểm Origin khi có, và client không phải trình duyệt.
        request = (f"GET {target} HTTP/1.1\r\nHost: {parts.netloc}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                   f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\nUser-Agent: {USER_AGENT}\r\n\r\n")
        try:
            sock.sendall(request.encode())
            head = self._read_head()
        except KernelError:
            self.close(send=False)
            raise
        except OSError as exc:
            self.close(send=False)
            raise K.NotReady(session_hint(f"WebSocket bắt tay hỏng ({type(exc).__name__})")) from None
        status, *lines = head.decode("latin-1").split("\r\n")
        fields = status.split(" ", 2)
        code = int(fields[1]) if len(fields) > 1 and fields[1].isdigit() else 0
        if code != 101:
            self.close(send=False)
            if 300 <= code < 400:
                raise K.NotReady(session_hint(f"server chuyển hướng WebSocket (HTTP {code}), script không theo"))
            raise K.NotReady(session_hint(f"WebSocket bị từ chối (HTTP {code})"))
        headers = {}
        for line in lines:
            name, _, value = line.partition(":")
            headers[name.strip().lower()] = value.strip()
        expect = base64.b64encode(hashlib.sha1((key + WS_GUID).encode()).digest()).decode()
        if headers.get("sec-websocket-accept") != expect or headers.get("upgrade", "").lower() != "websocket":
            self.close(send=False)
            raise KernelError("server bắt tay WebSocket sai")

    def _read_head(self) -> bytes:
        while b"\r\n\r\n" not in self.buf:
            if len(self.buf) > 65536:
                raise KernelError("phần đầu trả lời WebSocket quá dài")
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("server đóng kết nối khi bắt tay")
            self.buf += chunk
        head, self.buf = self.buf.split(b"\r\n\r\n", 1)
        return head

    def _read_exact(self, n: int) -> bytes:
        while len(self.buf) < n:
            chunk = self.sock.recv(max(65536, n - len(self.buf)))
            if not chunk:
                raise ConnectionError("server đóng kết nối")
            self.buf += chunk
        data, self.buf = self.buf[:n], self.buf[n:]
        return data

    def settimeout(self, seconds: float) -> None:
        self.sock.settimeout(max(0.05, seconds))

    def _send(self, opcode: int, payload: bytes) -> None:
        n = len(payload)
        if n < 126:
            head = struct.pack("!BB", 0x80 | opcode, 0x80 | n)
        elif n < 65536:
            head = struct.pack("!BBH", 0x80 | opcode, 0x80 | 126, n)
        else:
            head = struct.pack("!BBQ", 0x80 | opcode, 0x80 | 127, n)
        key = os.urandom(4)
        self.sock.sendall(head + key + _mask(payload, key))

    def send_text(self, text: str) -> None:
        self._send(0x1, text.encode("utf-8"))

    def recv(self) -> str | None:
        """Một message trọn vẹn: chữ thì trả str, nhị phân thì None. Tự trả lời ping; giới hạn cỡ (TM-87)."""
        parts, total, kind = [], 0, None
        while True:
            b1, b2 = self._read_exact(2)
            fin, opcode, masked, n = b1 & 0x80, b1 & 0x0F, b2 & 0x80, b2 & 0x7F
            if b1 & 0x70:
                raise KernelError("frame WebSocket có bit lạ")
            if n == 126:
                n = struct.unpack("!H", self._read_exact(2))[0]
            elif n == 127:
                n = struct.unpack("!Q", self._read_exact(8))[0]
            if opcode >= 0x8 and (n > 125 or not fin):
                raise KernelError("frame điều khiển WebSocket sai")
            if total + n > MAX_MESSAGE:
                raise KernelError(f"message WebSocket quá {MAX_MESSAGE // (1024 * 1024)} MiB")
            key = self._read_exact(4) if masked else b""
            data = self._read_exact(n)
            if masked:
                data = _mask(data, key)
            if opcode == 0x9:
                self._send(0xA, data)
                continue
            if opcode == 0xA:
                continue
            if opcode == 0x8:
                raise ConnectionError("server đóng WebSocket")
            if opcode in (0x1, 0x2):
                if kind is not None:
                    raise KernelError("frame WebSocket lồng nhau")
                kind = opcode
            elif opcode != 0x0 or kind is None:
                raise KernelError("frame WebSocket sai thứ tự")
            parts.append(data)
            total += n
            if fin:
                break
        payload = b"".join(parts)
        return payload.decode("utf-8", errors="replace") if kind == 0x1 else None

    def close(self, send: bool = True) -> None:
        try:
            if send:
                self._send(0x8, struct.pack("!H", 1000))
        except OSError:
            pass
        finally:
            try:
                self.sock.close()
            except OSError:
                pass


# ---------- giao thức kernel Jupyter (bản 5.3, JSON qua WebSocket) ----------

def kernel_message(msg_type: str, content: dict, session: str, channel: str) -> dict:
    now = dt.datetime.now(dt.UTC).isoformat()
    return {"header": {"msg_id": uuid.uuid4().hex, "username": "kaggle-gpu", "session": session,
                       "msg_type": msg_type, "version": "5.3", "date": now},
            "parent_header": {}, "metadata": {}, "content": content, "channel": channel, "buffers": []}


def open_channels(base: str, kernel_id: str) -> tuple:
    session = uuid.uuid4().hex
    ws = WebSocket(endpoint(base, f"/api/kernels/{kernel_id}/channels", ws=True, session_id=session), HTTP_TIMEOUT)
    return ws, session


def replies(ws: WebSocket, msg_id: str, deadline: list):
    """Các message trả lời đúng yêu cầu msg_id (kernel phát iopub cho mọi client, nên lọc theo parent).
    `deadline` là list một phần tử để bên gọi rút ngắn hạn chờ giữa chừng."""
    while True:
        remaining = deadline[0] - time.monotonic()
        if remaining <= 0:
            raise CellTimeout()
        ws.settimeout(remaining)
        try:
            raw = ws.recv()
        except TimeoutError:
            raise CellTimeout() from None
        if raw is None:
            continue
        try:
            msg = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(msg, dict):
            continue
        content = msg.get("content") if isinstance(msg.get("content"), dict) else {}
        kind = msg.get("msg_type") or (msg.get("header") or {}).get("msg_type")
        if kind == "status" and content.get("execution_state") in ("restarting", "dead"):
            # Jupyter Server báo kernel chết bằng status không có parent: dừng ngay, không chờ tới hết hạn
            raise KernelDied(content["execution_state"])
        if isinstance(msg.get("parent_header"), dict) and msg["parent_header"].get("msg_id") == msg_id:
            yield msg


class Output:
    """Gom output của một cell theo thứ tự; hình ghi ra file ngay khi tới."""

    def __init__(self, out_dir: Path | None):
        self.out_dir, self.chunks, self.images, self.failed = out_dir, [], [], False

    def directory(self) -> Path:
        return local_write(self._directory)

    def _directory(self) -> Path:
        if self.out_dir is None:
            path = Path(tempfile.gettempdir()) / f"kaggle-kernel-{os.getuid()}"
            private_dir(path)
            info = os.lstat(path)  # thư mục chung /tmp: không đi theo symlink, phải của chính mình
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
                raise K.Refused(f"{path} không phải thư mục riêng của người dùng hiện tại: dùng --out")
            self.out_dir = path
        else:
            private_dir(self.out_dir)  # tạo mới thì 0700; thư mục người dùng chọn có sẵn thì giữ quyền
            if not self.out_dir.is_dir():
                raise NotADirectoryError(f"{self.out_dir} không phải thư mục")
        return self.out_dir

    def data(self, data) -> None:
        if not isinstance(data, dict):
            return
        for mime, ext in IMAGE_TYPES.items():  # tên file do script đặt, chỉ nhận PNG, JPEG (TM-88)
            value = data.get(mime)
            if isinstance(value, str) and len(value) <= MAX_MESSAGE:
                try:
                    blob = base64.b64decode(value, validate=False)
                except (binascii.Error, ValueError):
                    continue
                stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
                path = self.directory() / f"cell-{stamp}-{secrets.token_hex(3)}{ext}"
                local_write(write_private, path, blob)
                self.images.append(path)
                self.chunks.append(f"[hình: {path}]\n")
                return
        text = data.get("text/plain")
        if isinstance(text, str):
            self.chunks.append(text if text.endswith("\n") else text + "\n")

    def handle(self, msg: dict) -> None:
        kind = msg.get("msg_type") or (msg.get("header") or {}).get("msg_type")
        content = msg.get("content") if isinstance(msg.get("content"), dict) else {}
        if kind == "stream" and isinstance(content.get("text"), str):
            self.chunks.append(content["text"])
        elif kind in ("execute_result", "display_data", "update_display_data"):
            self.data(content.get("data"))
        elif kind == "error":
            self.failed = True
            trace = content.get("traceback")
            if isinstance(trace, list) and trace:
                self.chunks.append("\n".join(str(t) for t in trace) + "\n")
            else:
                self.chunks.append(f"{content.get('ename', 'Error')}: {content.get('evalue', '')}\n")


def clean(text: str) -> str:
    """Bỏ mã màu và ký tự điều khiển (TM-86); dòng có \\r (thanh tiến độ) chỉ giữ lần vẽ cuối."""
    text = ANSI_RE.sub("", text)
    lines = []
    for line in text.split("\n"):
        if "\r" in line:
            pieces = [p for p in line.split("\r") if p]
            line = pieces[-1] if pieces else ""
        lines.append(line)
    return CONTROL_RE.sub("", "\n".join(lines))


def shorten(text: str, max_chars: int, out: Output) -> str:
    if len(text) <= max_chars:
        return text
    path = out.directory() / f"cell-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}.log"
    local_write(write_private, path, text.encode("utf-8"))
    head = max_chars // 5
    tail = max_chars - head
    return (f"{text[:head]}\n… (bỏ {len(text) - max_chars} ký tự ở giữa; bản đủ: {path}) …\n{text[-tail:]}")


def execute(base: str, kernel_id: str, code: str, timeout: int, out: Output) -> str | None:
    """Chạy code như một cell; trả status của execute_reply ('ok', 'error', 'aborted')."""
    ws, session = open_channels(base, kernel_id)
    try:
        request = kernel_message("execute_request", {"code": code, "silent": False, "store_history": True,
                                                     "user_expressions": {}, "allow_stdin": False,
                                                     "stop_on_error": True}, session, "shell")
        idle, status, deadline = False, None, [time.monotonic() + timeout]
        try:
            ws.send_text(json.dumps(request))
            for msg in replies(ws, request["header"]["msg_id"], deadline):
                kind = msg.get("msg_type") or (msg.get("header") or {}).get("msg_type")
                if kind == "status" and (msg.get("content") or {}).get("execution_state") == "idle":
                    idle = True  # kernel đã xong; execute_reply (kênh shell) thường tới ngay, chờ thêm tối đa vài giây
                    deadline[0] = min(deadline[0], time.monotonic() + REPLY_GRACE)
                elif kind == "execute_reply":
                    status = (msg.get("content") or {}).get("status") or "ok"
                else:
                    out.handle(msg)
                if idle and status is not None:
                    return status
        except CellTimeout:
            if idle:
                return "error" if out.failed else "ok"
            raise
        except (OSError, ConnectionError) as exc:  # rớt giữa cell: cell có thể vẫn chạy, đừng chạy lại ngay
            raise CellDropped(type(exc).__name__) from None
    finally:
        ws.close()
    return None


# ---------- lệnh ----------

def cmd_connect(args) -> int:
    if sys.stdin.isatty():
        raw = getpass.getpass("Dán 'VS Code Compatible URL' (chữ không hiện ra): ")
    else:
        raw = sys.stdin.read(MAX_URL + 1)
    url = parse_url(raw)
    remember_secrets(url)
    kernels = list_kernels(url)  # kiểm URL dùng được rồi mới lưu
    path = local_write(save_url, url)
    print(f"Đã lưu URL phiên vào {path} (quyền 600; không in ra). Kernel đang chạy: {len(kernels)}.")
    if not kernels:
        print("Chưa có kernel: trên web bấm Run → Start Session hay chạy một cell, rồi `status`.")
    return 0


def cmd_status(args) -> int:
    kernels = list_kernels(load_url())
    if not kernels:
        print("Phiên còn sống nhưng chưa có kernel nào (trên web chạy một cell để bật).")
        return 0
    for k in kernels:
        fields = [str(k.get(name, "?"))[:80] for name in ("name", "execution_state", "last_activity", "connections")]
        print(scrub(clean("{}  {}  {}  hoạt động cuối {}  kết nối {}".format(k["id"][:8], *fields))))
    return 0


def read_code(args) -> str:
    if args.code is not None:
        code = args.code
    elif args.file:
        try:
            code = Path(args.file).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise K.Refused(f"không đọc được {args.file} ({type(exc).__name__})") from None
    elif not sys.stdin.isatty():
        code = sys.stdin.read()
    else:
        raise K.Refused("không có code: dùng -c '<code>', -f <file>, hay đưa code qua stdin")
    if not code.strip():
        raise K.Refused("code rỗng")
    found = K.secret_lines(code.splitlines(), K.local_tokens())  # không gửi khóa trên máy lên Kaggle (TM-88)
    if found:
        raise K.Refused(f"code có thứ trông như khóa ở dòng {', '.join(map(str, found[:10]))}: đừng gửi khóa lên "
                        f"Kaggle, dùng Kaggle Secrets trong notebook. Chuỗi chắc chắn không phải khóa thì thêm "
                        f"chú thích '{K.ALLOW_MARK}' cùng dòng")
    return code


def cmd_run(args) -> int:
    code = read_code(args)
    timeout = min(max(1, args.timeout), MAX_TIMEOUT)
    out = Output(Path(args.out) if args.out else None)
    if args.out:
        out.directory()  # thư mục ra hỏng thì báo trước khi gọi mạng, không phải sau khi cell đã chạy
    base = load_url()
    kernel = pick_kernel(base, args.kernel)
    try:
        status = execute(base, kernel["id"], code, timeout, out)
    except Exception:
        partial = shorten(scrub(clean("".join(out.chunks))), args.max_chars, out)
        if partial:
            print(partial, end="" if partial.endswith("\n") else "\n")
        raise
    text = shorten(scrub(clean("".join(out.chunks))), args.max_chars, out)
    print(text, end="" if text.endswith("\n") or not text else "\n")
    if status == "aborted":
        print("(cell bị bỏ qua vì cell trước lỗi hay bị dừng)")
    return 1 if out.failed or status in ("error", "aborted") else 0


def cmd_interrupt(args) -> int:
    base = load_url()
    kernel = pick_kernel(base, args.kernel)
    try:
        http_json(base, f"/api/kernels/{kernel['id']}/interrupt", method="POST")
        print(f"Đã gửi lệnh dừng tới kernel {kernel['id'][:8]}.")
        return 0
    except HttpStatus as exc:
        if exc.code not in (403, 405):
            raise K.NotReady(session_hint(f"server trả lời HTTP {exc.code}")) from None
    # Server từ chối POST (thường do kiểm XSRF): gửi interrupt_request qua kênh control của WebSocket.
    ws, session = open_channels(base, kernel["id"])
    try:
        request = kernel_message("interrupt_request", {}, session, "control")
        ws.send_text(json.dumps(request))
        for msg in replies(ws, request["header"]["msg_id"], [time.monotonic() + HTTP_TIMEOUT]):
            if (msg.get("msg_type") or (msg.get("header") or {}).get("msg_type")) == "interrupt_reply":
                print(f"Đã dừng kernel {kernel['id'][:8]} qua kênh control.")
                return 0
    except CellTimeout:
        raise K.NotReady("kernel không trả lời lệnh dừng; dừng tay trên web (nút Stop)") from None
    finally:
        ws.close()
    return 1


def cmd_forget(args) -> int:
    path = url_file()
    if path.exists():
        path.unlink()
        print(f"Đã xóa URL phiên ({path}).")
    else:
        print("Không có URL phiên nào để xóa.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Chạy từng cell trên Kaggle Jupyter Server đang mở trên web.")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--profile", help="profile Kaggle (mặc định KAGGLE_GPU_PROFILE hay không profile)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("connect", parents=[common], help="đọc URL từ stdin hay ô nhập ẩn rồi lưu")
    sub.add_parser("status", parents=[common])
    run = sub.add_parser("run", parents=[common])
    source = run.add_mutually_exclusive_group()
    source.add_argument("-c", "--code")
    source.add_argument("-f", "--file")
    run.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help=f"giây, tối đa {MAX_TIMEOUT}")
    run.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    run.add_argument("--out", help="thư mục ghi hình và bản đủ của output dài")
    run.add_argument("--kernel", help="mã (hay đầu mã) kernel khi phiên có nhiều kernel")
    intr = sub.add_parser("interrupt", parents=[common])
    intr.add_argument("--kernel")
    sub.add_parser("forget", parents=[common])
    return parser


COMMANDS = {"connect": cmd_connect, "status": cmd_status, "run": cmd_run, "interrupt": cmd_interrupt,
            "forget": cmd_forget}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "max_chars", 1) < 200:
        args.max_chars = 200
    try:
        K.select_profile(args.profile)
        return COMMANDS[args.command](args)
    except K.Refused as exc:
        print(scrub(f"Từ chối: {exc}"))
        return 2
    except K.NotReady as exc:
        print(scrub(f"Chưa sẵn sàng: {exc}"))
        return 3
    except CellTimeout:
        print(scrub(f"Quá hạn chờ: cell có thể vẫn đang chạy trên Kaggle. Dừng bằng "
                    f"`python3 {HERE} interrupt{K.profile_flag()}`, hay chạy lại với --timeout lớn hơn"))
        return 4
    except CellDropped as exc:
        print(scrub(f"Mất kết nối giữa cell ({exc}): cell có thể vẫn đang chạy trên Kaggle, đừng chạy lại ngay. "
                    f"Xem `python3 {HERE} status{K.profile_flag()}` (busy thì `interrupt`); status báo hết hạn "
                    f"thì bật lại session và connect lại"))
        return 3
    except KernelDied as exc:
        print(scrub(f"Kernel đã chết hay khởi động lại giữa cell ({exc}), thường do hết RAM hay GPU: mọi biến cũ đã "
                    f"mất, chạy lại các cell cần thiết từ đầu"))
        return 1
    except LocalWriteError as exc:
        print(scrub(f"Lỗi trên máy: {exc}"))
        return 1
    except KernelError as exc:
        print(scrub(f"Lỗi giao thức: {exc}"))
        return 1
    except ConnectionError as exc:  # mạng rớt ngoài lúc chạy cell (lệnh dừng qua kênh control)
        print(scrub(f"Chưa sẵn sàng: {session_hint(f'mất kết nối ({type(exc).__name__})')}"))
        return 3
    except OSError as exc:  # ghi file trên máy (quyền, ổ đầy), không phải lỗi phiên
        print(scrub(f"Lỗi đọc ghi trên máy: {type(exc).__name__}: {exc}"))
        return 1
    except Exception as exc:  # không để traceback (có thể chứa URL) lọt ra
        print(scrub(f"Lỗi không lường trước: {type(exc).__name__}: {exc}"))
        return 1
    finally:
        K.ACTIVE_PROFILE = None
        _URL_SECRETS.clear()


if __name__ == "__main__":
    sys.exit(main())
