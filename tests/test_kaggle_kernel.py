"""Skill kaggle-gpu: chạy từng cell trên Kaggle Jupyter Server (kaggle_kernel.py, TM-84 đến TM-88).

Không gọi Kaggle thật: một Jupyter Server giả (REST và WebSocket viết bằng thư viện chuẩn) chạy ở 127.0.0.1, chạy code
bằng exec trong một namespace giữ qua các lần chạy, như kernel thật giữ biến giữa các cell.
"""
import base64
import contextlib
import hashlib
import io
import json
import os
import stat
import struct
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from tests._util import PLUGIN, TempDirTestCase

sys.path.insert(0, str(PLUGIN / "skills" / "kaggle-gpu" / "scripts"))
import kaggle_job as K  # noqa: E402
import kaggle_kernel as KK  # noqa: E402

JWT = "eyJhbGciOiJIUzI1NiJ9." + "c2Vzc2lvbi1zZWNyZXQ" * 3
KERNEL_ID = "0f3c2a9e-1111-4222-8333-944445555666"
PNG = b"\x89PNG\r\n\x1a\n" + b"fake-image"


def read_frame(rfile) -> tuple:
    b1, b2 = rfile.read(2)
    n = b2 & 0x7F
    if n == 126:
        n = struct.unpack("!H", rfile.read(2))[0]
    elif n == 127:
        n = struct.unpack("!Q", rfile.read(8))[0]
    key = rfile.read(4) if b2 & 0x80 else b""
    data = rfile.read(n)
    if key:
        data = bytes(b ^ key[i % 4] for i, b in enumerate(data))
    return b1 & 0x0F, data


def frame(opcode: int, payload: bytes, fin: bool = True) -> bytes:
    n = len(payload)
    first = (0x80 if fin else 0) | opcode
    if n < 126:
        return struct.pack("!BB", first, n) + payload
    if n < 65536:
        return struct.pack("!BBH", first, 126, n) + payload
    return struct.pack("!BBQ", first, 127, n) + payload


class FakeJupyter:
    """Jupyter Server giả. `mode` đổi hành vi theo từng test."""

    def __init__(self):
        self.namespace = {}
        self.mode = set()
        self.interrupts = []
        self.control = []
        self.requests = []
        self.interrupt_code = 204
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def reply(self, code, body=b"", ctype="application/json", headers=()):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                for k, v in headers:
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def route(self):
                prefix = f"/k/1/{JWT}/proxy"
                fake.requests.append(self.path)
                if not self.path.startswith(prefix) or "expired" in fake.mode:
                    self.reply(403, b"forbidden")
                    return None
                return self.path[len(prefix):]

            def do_GET(self):
                path = self.route()
                if path is None:
                    return
                if "redirect" in fake.mode or ("ws-redirect" in fake.mode and self.headers.get("Upgrade")):
                    self.reply(302, headers=[("Location", "https://evil.example/steal")])
                elif path == "/api/kernels":
                    if "login-page" in fake.mode:
                        self.reply(200, b"<html>sign in</html>", "text/html")
                        return
                    name = "python3\x1b]0;x\x07\x1b[31m" if "weird-status" in fake.mode else "python3"
                    kernels = [] if "no-kernel" in fake.mode else [
                        {"id": KERNEL_ID, "name": name, "execution_state": "idle",
                         "last_activity": "2026-11-09T05:00:00Z", "connections": 1}]
                    self.reply(200, json.dumps(kernels).encode())
                elif path.startswith(f"/api/kernels/{KERNEL_ID}/channels") and self.headers.get("Upgrade"):
                    self.websocket()
                else:
                    self.reply(404)

            def do_POST(self):
                path = self.route()
                if path is None:
                    return
                if path == f"/api/kernels/{KERNEL_ID}/interrupt":
                    fake.interrupts.append(path)
                    self.reply(fake.interrupt_code)
                else:
                    self.reply(404)

            def websocket(self):
                key = self.headers["Sec-WebSocket-Key"]
                accept = base64.b64encode(hashlib.sha1((key + KK.WS_GUID).encode()).digest()).decode()
                self.send_response(101)
                self.send_header("Upgrade", "websocket")
                self.send_header("Connection", "Upgrade")
                self.send_header("Sec-WebSocket-Accept", accept)
                self.end_headers()
                self.wfile.flush()
                self.close_connection = True
                while True:
                    try:
                        opcode, data = read_frame(self.rfile)
                    except (ValueError, OSError):
                        return
                    if opcode == 0x8:
                        return
                    if opcode != 0x1:
                        continue
                    fake.handle(self, json.loads(data))

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/k/1/{JWT}/proxy"

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def send(self, handler, msg_type, content, parent, channel="iopub"):
        msg = {"header": {"msg_id": uuid.uuid4().hex, "msg_type": msg_type}, "msg_type": msg_type,
               "parent_header": parent["header"], "metadata": {}, "content": content, "channel": channel}
        payload = json.dumps(msg).encode()
        if "fragment" in self.mode and msg_type == "stream":
            half = len(payload) // 2
            handler.wfile.write(frame(0x1, payload[:half], fin=False) + frame(0x9, b"hi")
                                + frame(0x0, payload[half:]))
        else:
            handler.wfile.write(frame(0x1, payload))
        handler.wfile.flush()

    def handle(self, handler, msg):
        kind = msg["header"]["msg_type"]
        if kind == "interrupt_request":
            self.control.append(msg["channel"])
            self.send(handler, "interrupt_reply", {"status": "ok"}, msg, "control")
            return
        if kind != "execute_request":
            return
        code = msg["content"]["code"]
        if "silent" in self.mode:
            return
        if "huge" in self.mode:
            handler.wfile.write(struct.pack("!BBQ", 0x81, 127, KK.MAX_MESSAGE + 1))
            handler.wfile.flush()
            return
        if "die" in self.mode:  # như Jupyter Server khi kernel chết: status không có parent
            self.send(handler, "status", {"execution_state": "restarting"}, {"header": {}})
            return
        if "drop" in self.mode:
            self.send(handler, "stream", {"name": "stdout", "text": "đã in một phần\n"}, msg)
            handler.wfile.write(frame(0x8, struct.pack("!H", 1001)))
            handler.wfile.flush()
            return
        if "ping" in self.mode:
            handler.wfile.write(frame(0x9, b"ping"))
        # message của client khác (cùng kernel) phải bị lọc bỏ
        self.send(handler, "stream", {"name": "stdout", "text": "của người khác\n"},
                  {"header": {"msg_id": "other"}})
        self.send(handler, "status", {"execution_state": "busy"}, msg)
        out = io.StringIO()
        status = "ok"
        try:
            with contextlib.redirect_stdout(out):
                exec(code, self.namespace)
        except Exception as exc:  # noqa: BLE001
            status = "error"
            if out.getvalue():
                self.send(handler, "stream", {"name": "stdout", "text": out.getvalue()}, msg)
            tb = ["\x1b[0;31m---------------------------------------------------------------------------\x1b[0m",
                  f"\x1b[0;31m{type(exc).__name__}\x1b[0m: {exc}"]
            self.send(handler, "error", {"ename": type(exc).__name__, "evalue": str(exc), "traceback": tb}, msg)
        else:
            if out.getvalue():
                self.send(handler, "stream", {"name": "stdout", "text": out.getvalue()}, msg)
            if "_image" in self.namespace:
                image = self.namespace.pop("_image")
                self.send(handler, "display_data", {"data": {"image/png": base64.b64encode(image).decode(),
                                                             "text/plain": "<Figure>"}}, msg)
            if "_result" in self.namespace:
                self.send(handler, "execute_result", {"data": {"text/plain": repr(self.namespace.pop("_result"))}},
                          msg)
        if "no-reply" in self.mode:  # proxy không chuyển kênh shell: chỉ có idle
            self.send(handler, "status", {"execution_state": "idle"}, msg)
            return
        self.send(handler, "execute_reply", {"status": status}, msg, "shell")
        self.send(handler, "status", {"execution_state": "idle"}, msg)


class KernelBase(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.fake = FakeJupyter()
        self.addCleanup(self.fake.stop)
        env = {"KAGGLE_GPU_HOME": str(self.tmp / "state"), "KAGGLE_GPU_PROFILES": str(self.tmp / "profiles"),
               KK.LOCAL_ENV: "1", "HOME": str(self.tmp / "home"), "KAGGLE_CONFIG_DIR": str(self.tmp / "home" / ".kaggle")}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in ("KAGGLE_API_TOKEN", "KAGGLE_KEY", "KAGGLE_GPU_PROFILE"):
            os.environ.pop(name, None)
        self.out = self.tmp / "out"
        for name, value in (("HTTP_TIMEOUT", 5),):
            patcher = mock.patch.object(KK, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def main(self, *argv, stdin: str = "") -> tuple:
        buf, err = io.StringIO(), io.StringIO()
        fake_in = io.StringIO(stdin)
        fake_in.isatty = lambda: False
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err), mock.patch.object(sys, "stdin", fake_in):
            code = KK.main(list(argv))
        text = buf.getvalue() + err.getvalue()
        self.assertNotIn(JWT, text)  # TM-84: không nhánh nào in khóa phiên
        self.assertNotIn("c2Vzc2lvbi1zZWNyZXQ", text)
        return code, text

    def connect(self):
        code, text = self.main("connect", stdin=self.fake.url + "\n")
        self.assertEqual(code, 0, text)

    def run_cell(self, code, *extra):
        return self.main("run", "-c", code, "--out", str(self.out), *extra)


class Connect(KernelBase):
    def test_connect_saves_private_url_without_printing_it(self):
        code, text = self.main("connect", stdin=self.fake.url)
        self.assertEqual(code, 0, text)
        self.assertIn("Kernel đang chạy: 1", text)
        path = self.tmp / "state" / KK.URL_FILE
        self.assertEqual(path.read_text().strip(), self.fake.url)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)

    def test_rejects_non_kaggle_and_plain_http_without_echo(self):
        os.environ.pop(KK.LOCAL_ENV)
        for raw in (self.fake.url, f"http://x.kaggle.net/k/1/{JWT}/proxy", f"https://kaggle.net.evil.io/k/{JWT}/proxy",
                    f"https://a.kaggle.net/k/1/{JWT}", f"https://u:{JWT}@a.kaggle.net/k/proxy",
                    f"https://a.kaggle.net/k/1/proxy?next={JWT}", f"hf_{JWT} and more", ""):
            code, text = self.main("connect", stdin=raw)
            self.assertEqual(code, 2, (raw, text))
        self.assertFalse((self.tmp / "state" / KK.URL_FILE).exists())
        self.assertEqual(self.fake.requests, [])

    def test_accepts_kaggle_https_shapes(self):
        os.environ.pop(KK.LOCAL_ENV)
        url = f"https://kkb-production.jupyter-proxy.kaggle.net/k/123/{JWT}/proxy/"
        self.assertEqual(KK.parse_url(url), url.rstrip("/"))
        self.assertEqual(KK.parse_url(url + "?token=abc"), url.rstrip("/") + "?token=abc")

    def test_expired_session_exits_3_and_does_not_save(self):
        self.fake.mode.add("expired")
        code, text = self.main("connect", stdin=self.fake.url)
        self.assertEqual(code, 3, text)
        self.assertIn("HTTP 403", text)
        self.assertIn("connect", text)
        self.assertFalse((self.tmp / "state" / KK.URL_FILE).exists())

    def test_redirect_is_refused_not_followed(self):
        self.fake.mode.add("redirect")
        code, text = self.main("connect", stdin=self.fake.url)
        self.assertEqual(code, 3, text)  # thường là trang đăng nhập khi phiên hết hạn: hướng dẫn connect lại
        self.assertIn("chuyển hướng", text)
        self.assertEqual(len(self.fake.requests), 1)

    def test_login_page_instead_of_json(self):
        self.fake.mode.add("login-page")
        code, text = self.main("connect", stdin=self.fake.url)
        self.assertEqual(code, 3, text)
        self.assertIn("không trả về JSON", text)

    def test_unreachable_server_exits_3(self):
        url = self.fake.url
        self.fake.stop()
        code, text = self.main("connect", stdin=url)
        self.assertEqual(code, 3, text)

    def test_commands_without_connect_exit_3(self):
        for argv in (["status"], ["run", "-c", "1"], ["interrupt"]):
            code, text = self.main(*argv)
            self.assertEqual(code, 3, text)
            self.assertIn("connect", text)

    def test_forget_removes_url(self):
        self.connect()
        code, _text = self.main("forget")
        self.assertEqual(code, 0)
        self.assertFalse((self.tmp / "state" / KK.URL_FILE).exists())

    def test_profile_keeps_its_own_url(self):
        (self.tmp / "profiles" / "an").mkdir(parents=True)
        code, text = self.main("connect", "--profile", "an", stdin=self.fake.url)
        self.assertEqual(code, 0, text)
        self.assertTrue((self.tmp / "profiles" / "an" / KK.URL_FILE).exists())
        self.assertFalse((self.tmp / "state" / KK.URL_FILE).exists())
        code, text = self.main("status")
        self.assertEqual(code, 3, text)  # không profile thì không mượn URL của profile an
        code, text = self.main("status", "--profile", "an")
        self.assertEqual(code, 0, text)
        self.assertIsNone(K.ACTIVE_PROFILE)

    def test_missing_profile_exits_3(self):
        code, text = self.main("connect", "--profile", "binh", stdin=self.fake.url)
        self.assertEqual(code, 3, text)


class Run(KernelBase):
    def setUp(self):
        super().setUp()
        self.connect()

    def test_state_kept_between_cells_and_output_filtered(self):
        code, text = self.run_cell("x = 41")
        self.assertEqual(code, 0, text)
        code, text = self.run_cell("x += 1\nprint('x =', x)\n_result = x * 2")
        self.assertEqual(code, 0, text)
        self.assertIn("x = 42", text)
        self.assertIn("84", text)
        self.assertNotIn("của người khác", text)

    def test_code_from_file_and_stdin(self):
        script = self.write("cell.py", "print('từ file')\n")
        code, text = self.main("run", "-f", str(script))
        self.assertEqual((code, text.strip()), (0, "từ file"))
        code, text = self.main("run", stdin="print('từ stdin')")
        self.assertEqual((code, text.strip()), (0, "từ stdin"))

    def test_error_exits_1_with_clean_traceback(self):
        code, text = self.run_cell("print('trước lỗi')\n1/0")
        self.assertEqual(code, 1, text)
        self.assertIn("trước lỗi", text)
        self.assertIn("ZeroDivisionError: division by zero", text)
        self.assertNotIn("\x1b", text)

    def test_image_saved_private(self):
        code, text = self.run_cell(f"_image = {PNG!r}")
        self.assertEqual(code, 0, text)
        images = list(self.out.glob("cell-*.png"))
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].read_bytes(), PNG)
        self.assertEqual(stat.S_IMODE(images[0].stat().st_mode), 0o600)
        self.assertIn(str(images[0]), text)

    def test_secrets_in_output_redacted_and_controls_stripped(self):
        token = "hf_" + "Qw7" * 12
        code, text = self.run_cell("print('tok', 'hf_' + 'Qw7' * 12)\nprint('\\x1b]0;title\\x07\\x1b[1mđậm\\x1b[0m\\x07')\n"
                                   "print('10%\\r50%\\r100%')")
        self.assertEqual(code, 0, text)
        self.assertNotIn(token[4:], text)
        self.assertIn("đậm", text)
        self.assertNotIn("\x1b", text)
        self.assertNotIn("\x07", text)
        self.assertIn("100%", text)
        self.assertNotIn("50%", text)

    def test_long_output_truncated_with_full_log(self):
        code, text = self.run_cell("print('\\n'.join(f'dòng {i}' for i in range(5000)))", "--max-chars", "1000")
        self.assertEqual(code, 0)
        self.assertLess(len(text), 1300)
        self.assertIn("dòng 4999", text)
        self.assertIn("dòng 0", text)
        logs = list(self.out.glob("cell-*.log"))
        self.assertEqual(len(logs), 1)
        self.assertIn("dòng 2500", logs[0].read_text())
        self.assertEqual(stat.S_IMODE(logs[0].stat().st_mode), 0o600)

    def test_code_with_secret_refused_before_sending(self):
        before = len(self.fake.requests)
        code, text = self.run_cell("import os\nos.environ['HF_TOKEN'] = 'hf_" + "Zx9" * 12 + "'")
        self.assertEqual(code, 2, text)
        self.assertIn("dòng 2", text)
        self.assertEqual(len(self.fake.requests), before)
        self.assertNotIn("os", self.fake.namespace)

    def test_silent_kernel_times_out_with_interrupt_hint(self):
        self.fake.mode.add("silent")
        code, text = self.run_cell("print(1)", "--timeout", "1")
        self.assertEqual(code, 4, text)
        self.assertIn("interrupt", text)

    def test_ping_and_fragmented_frames(self):
        self.fake.mode.update({"ping", "fragment"})
        code, text = self.run_cell("print('ghép ' * 3000)")
        self.assertEqual(code, 0, text)
        self.assertEqual(text.count("ghép"), 3000)

    def test_oversized_frame_refused(self):
        self.fake.mode.add("huge")
        code, text = self.run_cell("print(1)", "--timeout", "5")
        self.assertEqual(code, 1, text)
        self.assertIn("MiB", text)

    def test_drop_mid_cell_keeps_output_and_warns_not_to_rerun(self):
        self.fake.mode.add("drop")
        code, text = self.run_cell("print(1)")
        self.assertEqual(code, 3, text)
        self.assertIn("đã in một phần", text)
        self.assertIn("đừng chạy lại", text)
        self.assertIn("status", text)

    def test_idle_without_reply_finishes_after_grace(self):
        self.fake.mode.add("no-reply")
        with mock.patch.object(KK, "REPLY_GRACE", 0.5):
            code, text = self.run_cell("print('xong')", "--timeout", "60")
        self.assertEqual((code, text.strip()), (0, "xong"))

    def test_kernel_death_stops_immediately(self):
        self.fake.mode.add("die")
        code, text = self.run_cell("print(1)", "--timeout", "60")
        self.assertEqual(code, 1, text)
        self.assertIn("biến cũ đã mất", text)

    def test_bad_out_dir_refused_before_sending(self):
        blocked = self.write("blocked", "file")
        before = len(self.fake.requests)
        code, text = self.main("run", "-c", "x = 1", "--out", str(blocked))
        self.assertEqual(code, 1, text)
        self.assertIn("trên máy", text)
        self.assertEqual(len(self.fake.requests), before)

    def test_ws_redirect_not_followed(self):
        self.fake.mode.add("ws-redirect")
        code, text = self.run_cell("print(1)")
        self.assertEqual(code, 3, text)
        self.assertIn("chuyển hướng", text)

    def test_status_strips_control_chars_from_server(self):
        self.fake.mode.add("weird-status")
        code, text = self.main("status")
        self.assertEqual(code, 0, text)
        self.assertNotIn("\x1b", text)
        self.assertNotIn("\x07", text)

    def test_new_out_dir_private_and_local_write_error_not_session(self):
        code, text = self.run_cell(f"_image = {PNG!r}")
        self.assertEqual(code, 0, text)
        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o700)
        blocked = self.tmp / "blocked"
        blocked.write_text("không phải thư mục")
        code, text = self.main("run", "-c", f"_image = {PNG!r}", "--out", str(blocked / "x"))
        self.assertEqual(code, 1, text)
        self.assertIn("trên máy", text)
        self.assertNotIn("connect", text)

    def test_default_out_dir_symlink_refused(self):
        tmpdir = self.tmp / "systmp"
        tmpdir.mkdir()
        (tmpdir / f"kaggle-kernel-{os.getuid()}").symlink_to(self.tmp)
        with mock.patch.object(KK.tempfile, "gettempdir", return_value=str(tmpdir)):
            code, text = self.main("run", "-c", f"_image = {PNG!r}")
        self.assertEqual(code, 2, text)
        self.assertIn("--out", text)

    def test_status_lists_kernel(self):
        code, text = self.main("status")
        self.assertEqual(code, 0, text)
        self.assertIn(KERNEL_ID[:8], text)
        self.assertIn("idle", text)

    def test_no_kernel_yet(self):
        self.fake.mode.add("no-kernel")
        code, text = self.run_cell("print(1)")
        self.assertEqual(code, 3, text)
        self.assertIn("Start Session", text)

    def test_session_expires_after_connect(self):
        self.fake.mode.add("expired")
        code, text = self.run_cell("print(1)")
        self.assertEqual(code, 3, text)
        self.assertIn("connect", text)

    def test_tampered_url_file_refused(self):
        (self.tmp / "state" / KK.URL_FILE).write_text("https://evil.example/k/1/x/proxy\n")
        before = len(self.fake.requests)
        code, text = self.main("status")
        self.assertEqual(code, 2, text)
        self.assertEqual(len(self.fake.requests), before)

    def test_unexpected_error_does_not_leak_url(self):
        def boom(*_a, **_k):
            raise RuntimeError(f"hỏng ở {self.fake.url}")
        with mock.patch.object(KK, "pick_kernel", side_effect=boom):
            code, text = self.run_cell("print(1)")
        self.assertEqual(code, 1, text)
        self.assertIn("<URL phiên>", text)


class Interrupt(KernelBase):
    def setUp(self):
        super().setUp()
        self.connect()

    def test_interrupt_via_rest(self):
        code, text = self.main("interrupt")
        self.assertEqual(code, 0, text)
        self.assertEqual(len(self.fake.interrupts), 1)
        self.assertEqual(self.fake.control, [])

    def test_interrupt_falls_back_to_control_channel(self):
        self.fake.interrupt_code = 403
        code, text = self.main("interrupt")
        self.assertEqual(code, 0, text)
        self.assertEqual(self.fake.control, ["control"])


class WebSocketUnit(TempDirTestCase):
    def test_mask_roundtrip(self):
        key = b"\x01\x02\x03\x04"
        data = "chữ có dấu".encode() * 10
        self.assertEqual(KK._mask(KK._mask(data, key), key), data)
        self.assertEqual(KK._mask(data, key), bytes(b ^ key[i % 4] for i, b in enumerate(data)))


if __name__ == "__main__":
    import unittest
    unittest.main()
