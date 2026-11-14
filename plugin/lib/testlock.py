"""Sổ khóa test của một project: `.agent/test-lock.json` ở gốc repo, commit cùng repo (bạn chọn 13/11/2026).

Test đã chứng minh trượt trên code cũ (`receipt.py lock` chạy fails-before) thì được khóa: sổ ghi sha256 cả file và dấu
băm từng dòng theo thứ tự; file Python có thêm dấu cấu trúc từng hàm (ast). Siết: thêm hàm test mới, class mới, import
không che tên cũ, hay thêm assert ở cuối một hàm test cũ; mọi phần cũ giữ nguyên (file không phải Python: chỉ thêm dòng
ở cuối). Còn lại (sửa, xóa, bọc assert, thêm
`return`, setUp hay fixture mới, câu lệnh mới ở mức module) là nới, phải người dùng duyệt. Hook `pretool_guard.py`, `receipt.py` và `ratchet.py` của done-gate cùng đọc qua module này.

Sổ có thể đến từ repo lạ: chỉ nhận đường dẫn tương đối nằm trong repo, sổ quá lớn hay sai dạng thì coi như không có
(TM-105). Chạy được trên Python 3.9 như mọi file trong plugin/lib.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath

LOCK_REL = ".agent/test-lock.json"
MAX_BYTES = 1_000_000  # file test lớn hơn thì không so (coi là sửa)
MAX_BOOK_BYTES = 20_000_000  # sổ lớn hơn thì coi là hỏng (báo đỏ), không lặng lẽ bỏ khóa
LEVELS = ("vua", "cao")  # mức thấp không khóa (câu 3)


def safe_rel(rel) -> bool:
    """Đường dẫn tương đối kiểu posix, không ra ngoài repo."""
    if not isinstance(rel, str) or not rel or "\\" in rel or "\0" in rel:
        return False
    p = PurePosixPath(rel)
    return not p.is_absolute() and ".." not in p.parts and p.parts[:1] != ("",)


def line_hashes(text: str) -> list:
    """Dấu băm ngắn từng dòng không rỗng, giữ thụt lề đầu dòng (bỏ khoảng trắng cuối dòng), giữ thứ tự và dòng trùng:
    lùi thụt lề một assert ra khỏi vòng lặp là sửa, không phải giữ nguyên."""
    return [hashlib.sha1(line.rstrip().encode("utf-8", "replace")).hexdigest()[:12]
            for line in text.splitlines() if line.strip()]


# Hàm mới mang tên này chạy trước, quanh hay thay mọi test (unittest, pytest kiểu xUnit, hook của pytest): thêm chúng có
# thể vô hiệu test cũ, nên không tính là siết. Ở mức module và ở mức class tên khác nhau (`run` ở module chỉ là hàm phụ).
SPECIAL_MODULE_RE = re.compile(r"^(setUpModule|tearDownModule|load_tests|setup_module|teardown_module|setup_function|"
                               r"teardown_function|setup|teardown|pytest_\w+)$")
SPECIAL_METHOD_RE = re.compile(r"^(setUp\w*|tearDown\w*|setup_method|teardown_method|setup_class|teardown_class|setup|"
                               r"teardown|run|debug|__\w+__|_call\w+|assert\w*|fail\w*|skipTest|subTest)$")


def _is_fixture(decorator) -> bool:
    """Decorator `@fixture`, `@pytest.fixture(...)`, hay có keyword `autouse` (so theo cấu trúc, không theo chuỗi con)."""
    func = decorator.func if isinstance(decorator, ast.Call) else decorator
    name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
    autouse = isinstance(decorator, ast.Call) and any(k.arg == "autouse" for k in decorator.keywords)
    return name == "fixture" or autouse


PY_VERSION = f"{sys.version_info[0]}.{sys.version_info[1]}"


ASSERT_CALL_RE = re.compile(r"^(assert|expect)\w*$")


def _dump(node) -> str:
    return hashlib.sha1(ast.dump(node, include_attributes=False).encode("utf-8")).hexdigest()[:16]


def _bound(node) -> list:
    """Tên mà câu lệnh mức module ràng buộc (import, gán, def, class), để biết phần thêm có che tên cũ không."""
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return [(a.asname or a.name).split(".")[0] for a in node.names]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [node.name]
    targets = node.targets if isinstance(node, ast.Assign) else [getattr(node, "target", None)]
    return [n.id for t in targets if t is not None for n in ast.walk(t) if isinstance(n, ast.Name)]


def is_assert_stmt(node) -> bool:
    """Câu lệnh chỉ kiểm thêm: `assert …` hay lời gọi assert*/expect* (không phải skip, return, if, try, with)."""
    if isinstance(node, ast.Assert):
        return True
    call = node.value if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) else None
    func = call.func if call is not None else None
    name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
    return bool(ASSERT_CALL_RE.match(name))


def py_items(text: str):
    """Cấu trúc file test Python: danh sách [loại, tên, dấu, tên ràng buộc, dấu đầu hàm, dấu từng câu thân hàm] theo
    thứ tự (def kèm decorator, class, import, câu lệnh khác ở mức module hay class). None khi không phải Python hợp lệ
    hay quá sâu để phân tích (khi đó so theo dòng)."""
    try:
        tree = ast.parse(text)
        out = []

        def walk(body, owner):
            for node in body:
                names = ",".join(_bound(node)) if not owner else ""
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names_re = SPECIAL_METHOD_RE if owner else SPECIAL_MODULE_RE
                    special = bool(names_re.match(node.name)) or any(_is_fixture(d) for d in node.decorator_list)
                    head = copy.copy(node)
                    head.body = []
                    out.append(["def!" if special else "def", owner + node.name, _dump(node), names, _dump(head),
                                ",".join(_dump(x) + ("a" if is_assert_stmt(x) else "") for x in node.body)])
                elif isinstance(node, ast.ClassDef):
                    head = copy.copy(node)
                    head.body = []
                    out.append(["class", owner + node.name, _dump(head), names, "", ""])
                    walk(node.body, owner + node.name + ".")
                elif isinstance(node, (ast.Import, ast.ImportFrom)) and not owner:
                    out.append(["import", "", _dump(node), names, "", ""])
                elif not (isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Constant)
                          and isinstance(node.value.value, str)):  # docstring không tính
                    out.append(["stmt", owner, _dump(node), names, "", ""])
        walk(tree.body, "")
        return out
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None


def _extends(old: tuple, new: tuple) -> bool:
    """Hàm `new` là hàm `old` thêm assert ở cuối thân (bạn chọn 14/11/2026): cùng đầu hàm, thân cũ giữ nguyên, phần
    thêm chỉ là câu kiểm (`assert`, assert*/expect*)."""
    if old[0] != new[0] or old[0] not in ("def", "def!") or old[1] != new[1] or old[4] != new[4]:
        return False
    a, b = old[5].split(",") if old[5] else [], new[5].split(",") if new[5] else []
    return len(b) > len(a) and b[:len(a)] == a and all(x.endswith("a") for x in b[len(a):])


def py_compare(old: list, new: list) -> str:
    """same, added (siết: thêm hàm test thường, class mới, import, hay thêm assert ở cuối hàm cũ; mọi phần cũ giữ nguyên)
    hay changed (nới)."""
    old_t, new_t = [tuple(x) for x in old], [tuple(x) for x in new]
    if old_t == new_t:
        return "same"
    matched, it = set(), iter(range(len(new_t)))
    for item in old_t:
        hit = next((j for j in it if new_t[j] == item or _extends(item, new_t[j])), None)
        if hit is None:
            return "changed"
        matched.add(hit)
    old_classes = {q for k, q, *_ in old_t if k == "class"}
    old_quals = {(k.rstrip("!"), q) for k, q, *_ in old_t if k in ("def", "def!", "class")}
    old_names = {n for x in old_t for n in x[3].split(",") if n}
    for j, (kind, qual, _d, names, *_rest) in enumerate(new_t):
        if j in matched:
            continue
        owner = qual.rsplit(".", 1)[0] if "." in qual else ""
        if kind in ("def!", "stmt") and (not owner or owner in old_classes):
            return "changed"  # hàm đặc biệt hay câu lệnh mới ở mức module hay trong class cũ (class mới thì không sao)
        if (kind.rstrip("!"), qual) in old_quals or any(n in old_names for n in names.split(",") if n):
            return "changed"  # định nghĩa lại trùng tên, hay che tên cũ: Python dùng định nghĩa sau, test cũ mất
    return "added"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_subsequence(old: list, new: list) -> bool:
    it = iter(new)
    return all(any(x == y for y in it) for x in old)


def find_top(start: Path):
    """Gốc repo (thư mục có `.git`) chứa `start`, không gọi git (hook phải nhanh); None khi không có."""
    try:
        here = Path(start).resolve()
    except (OSError, RuntimeError):
        return None
    for folder in [here, *here.parents]:
        if (folder / ".git").exists():
            return folder
    return None


def empty() -> dict:
    return {"schema": 1, "files": {}, "approvals": []}


def _strs(value, n=None) -> bool:
    return isinstance(value, list) and all(isinstance(x, str) for x in value) and (n is None or len(value) == n)


def parse(text) -> dict:
    """Sổ từ chữ JSON; bỏ mục sai dạng, đường dẫn không an toàn hay mức lạ (TM-105). Sổ có mà không đọc được (hỏng,
    quá lớn, sai dạng) thì `broken` = True: hook và done-gate báo đỏ, `receipt.py lock` không ghi đè."""
    out = empty()
    try:
        data = json.loads(text) if isinstance(text, (str, bytes)) and len(text) <= MAX_BOOK_BYTES else None
    except (ValueError, RecursionError):
        data = None
    if not isinstance(data, dict) or not isinstance(data.get("files", {}), dict):
        out["broken"] = True
        return out
    for rel, entry in data.get("files", {}).items():
        if not (safe_rel(rel) and isinstance(entry, dict) and isinstance(entry.get("sha256"), str)
                and _strs(entry.get("lines")) and entry.get("level") in LEVELS):
            out["broken"] = True
            continue
        clean = {k: v for k, v in entry.items() if k in ("sha256", "lines", "level", "ts", "cmd", "base", "label")}
        py = entry.get("py")
        if (isinstance(py, dict) and isinstance(py.get("v"), str) and isinstance(py.get("items"), list)
                and all(_strs(x, 6) for x in py["items"])):
            clean["py"] = py
        out["files"][rel] = clean  # `py` sai dạng thì bỏ: so theo dòng, chặt hơn
    approvals = data.get("approvals", [])
    for a in approvals if isinstance(approvals, list) else []:
        if isinstance(a, dict) and safe_rel(a.get("path")) and all(
                isinstance(a.get(k, ""), str) for k in ("sha256", "ts", "reason", "action", "level")):
            out["approvals"].append(a)
    return out


def load(top) -> dict:
    """Sổ của repo `top`; không có thì sổ rỗng; quá lớn hay hỏng thì sổ rỗng có `broken`. Không bao giờ văng lỗi."""
    try:
        path = Path(top) / LOCK_REL
        if not path.is_file():
            return empty()
        if path.stat().st_size > MAX_BOOK_BYTES:
            return dict(empty(), broken=True)
        return parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, TypeError, ValueError):
        return dict(empty(), broken=True)


def save(top, data: dict) -> None:
    path = Path(top) / LOCK_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"schema": 1, "about": "Sổ khóa test của agent-stack (receipt.py lock). Sửa bằng receipt.py, "
                       "không sửa tay: sửa hay xóa test đã khóa là nới, phải người dùng duyệt.",
                       "files": data.get("files", {}), "approvals": data.get("approvals", [])},
                      ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".test-lock.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def entry_for(data: bytes, level: str, **extra) -> dict:
    text = data.decode("utf-8", "replace")
    entry = {"sha256": digest(data), "lines": line_hashes(text), "level": level,
             "ts": datetime.now().astimezone().isoformat(timespec="seconds"), **extra}
    items = py_items(text)
    if items is not None:
        entry["py"] = {"v": PY_VERSION, "items": items}
    return entry


def compare(entry: dict, text) -> str:
    """So nội dung mới với mục khóa: same (không đổi), added (chỉ thêm dòng: siết), changed (sửa hay xóa dòng: nới),
    deleted (file mất)."""
    if text is None:
        return "deleted"
    data = text.encode("utf-8", "replace") if isinstance(text, str) else text
    if digest(data) == entry.get("sha256"):
        return "same"
    if len(data) > MAX_BYTES:
        return "changed"  # quá lớn để so (TM-106)
    text = data.decode("utf-8", "replace")
    py = entry.get("py")
    if isinstance(py, dict) and py.get("v") == PY_VERSION and isinstance(py.get("items"), list):
        items = py_items(text)
        # Python: so cấu trúc từng hàm (thêm `return`, bọc try, thêm decorator vào hàm cũ đều là sửa).
        return "changed" if items is None else py_compare(py["items"], items)
    if entry.get("broken"):
        return "changed"
    new = line_hashes(text)
    old = entry.get("lines") or []
    if new == old:
        return "same"  # chỉ đổi khoảng trắng cuối dòng hay dòng trống
    # Không so được cấu trúc: chỉ tính siết khi thêm dòng sau toàn bộ phần cũ (chèn vào giữa có thể vô hiệu assert).
    return "added" if new[:len(old)] == old else "changed"


def status(top, rel: str, entry: dict) -> str:
    """compare với file hiện trên đĩa; file quá lớn tính là changed (không so dòng, TM-106)."""
    path = Path(top) / rel
    try:
        if not path.exists():
            return "deleted"
        if path.stat().st_size > MAX_BYTES:
            return "changed"
        return compare(entry, path.read_bytes())
    except OSError:
        return "changed"


def lookup(full):
    """(gốc repo, đường dẫn tương đối, mục khóa) khi `full` là file đã khóa; không thì None."""
    try:
        full = Path(full)
        top = find_top(full.parent if not full.is_dir() else full)
        if top is None or not (top / LOCK_REL).is_file():
            return None
        rel = full.resolve().relative_to(top).as_posix()
    except (OSError, ValueError, RuntimeError):
        return None
    book = load(top)
    entry = book["files"].get(rel)
    if entry is None and book.get("broken"):
        entry = {"level": "cao", "broken": True}  # sổ hỏng: không biết file nào khóa, coi file test nào cũng khóa
        if not re.search(r"(^|/)(tests?|spec|__tests__)/|(^|/)(test_[^/]*|[^/]*_test\.\w+|[^/]*\.(test|spec)\.\w+)$",
                         rel):
            return None
    return (top, rel, entry) if entry else None


def is_lock_file(full) -> bool:
    try:
        full = Path(full).resolve()
        top = find_top(full.parent)
        return top is not None and full == (top / LOCK_REL).resolve()
    except (OSError, RuntimeError):
        return False
