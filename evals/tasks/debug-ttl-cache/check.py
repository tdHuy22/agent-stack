import importlib.util, sys
from pathlib import Path


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def load(workdir):
    spec = importlib.util.spec_from_file_location("cache_under_test", Path(workdir) / "cache.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.TTLCache


def scenarios(TTLCache):
    """Mỗi ca trả về danh sách lỗi (rỗng là đạt). Tên ca là nhóm lỗi đặc tả."""
    out = {}

    def case(name):
        def deco(fn):
            try:
                errs = fn()
            except Exception as exc:  # noqa: BLE001
                errs = [f"ném {type(exc).__name__}: {exc}"]
            out[name] = errs
        return deco

    @case("tham số")
    def _():
        e = []
        for args, kw in (((0,), {}), ((1,), {"ttl": 0}), ((1,), {"ttl": -3})):
            try:
                TTLCache(*args, **kw); e.append(f"không ValueError với {args} {kw}")
            except ValueError:
                pass
        return e

    @case("hạn chính xác")
    def _():
        k = Clock(); c = TTLCache(3, ttl=10, clock=k)
        c.set("a", 1); k.now += 9.99
        e = [] if c.get("a") == 1 else ["hết hạn sớm"]
        c.set("b", 2, ttl=5); k.now += 5
        if "b" in c or c.get("b") is not None:
            e.append("hết hạn đúng hạn mà vẫn còn")
        return e

    @case("ghi đè")
    def _():
        k = Clock(); c = TTLCache(2, ttl=10, clock=k)
        c.set("a", 1); c.set("b", 2); k.now += 8
        c.set("a", 9)  # tính lại hạn, thành mới nhất
        k.now += 5
        e = [] if c.get("a") == 9 else ["ghi đè không tính lại hạn"]
        c.set("a", 9, ttl=100); k.now += 50
        if c.get("a") != 9:
            e.append("ttl riêng khi ghi đè bị bỏ qua")
        c2 = TTLCache(2, clock=k); c2.set("x", 1); c2.set("y", 2); c2.set("x", 3); c2.set("z", 4)
        if "y" in c2 or c2.get("x") != 3:
            e.append("ghi đè không đưa mục thành dùng gần nhất")
        return e

    @case("giá trị falsy")
    def _():
        k = Clock(); c = TTLCache(5, clock=k)
        e = []
        for v in (0, "", None, False, []):
            calls = []
            c.set("f", v)
            if c.get("f", "MISS") != v and not (v is None):
                e.append(f"get đọc sai giá trị falsy {v!r}")
            if v is None and c.get("f", "MISS") is not None:
                e.append("get đọc sai None")
            if c.get_or_load("f", lambda: calls.append(1) or "NEW") != v or calls:
                e.append(f"get_or_load nạp lại giá trị falsy {v!r}")
        return e

    @case("đẩy khi đầy")
    def _():
        k = Clock(); c = TTLCache(3, clock=k)
        c.set("old", 1, ttl=5); c.set("live1", 2); c.set("live2", 3)
        c.get("live1"); c.get("live2"); c.get("old")  # old mới dùng nhất; live1 cũ nhất còn hạn
        k.now += 6
        c.set("new", 4)
        e = []
        if "live1" not in c or "live2" not in c:
            e.append("đẩy mục còn hạn dù có mục hết hạn")
        if c.stats["evictions"] != 0 or c.stats["expirations"] != 1:
            e.append(f"thống kê khi dọn hết hạn sai: {c.stats}")
        c.set("n2", 5)  # đầy thật: đẩy live1 (cũ nhất còn hạn)
        if "live1" in c or c.stats["evictions"] != 1:
            e.append(f"không đẩy đúng mục LRU: {c.stats}")
        return e

    @case("len và in")
    def _():
        k = Clock(); c = TTLCache(4, clock=k)
        c.set("a", 1, ttl=1); c.set("b", 2); c.set("c", 3, ttl=1); k.now += 2
        e = []
        s0 = dict(c.stats)
        if "a" in c or "b" not in c:
            e.append("in sai")
        if c.stats != s0:
            e.append("in làm đổi thống kê")
        if len(c) != 1:
            e.append(f"len đếm cả mục hết hạn: {len(c)}")
        # len được phép dọn mục hết hạn (tính expirations), chỉ không được đổi hits/misses.
        if (c.stats["hits"], c.stats["misses"]) != (s0["hits"], s0["misses"]):
            e.append("len làm đổi hits/misses")
        c2 = TTLCache(2, clock=k); c2.set("x", 1); c2.set("y", 2)
        _ = "x" in c2; c2.set("z", 3)
        if "x" in c2:
            e.append("in làm đổi thứ tự LRU")
        return e

    @case("get hết hạn")
    def _():
        k = Clock(); c = TTLCache(3, ttl=1, clock=k)
        c.set("a", 1); k.now += 2
        e = []
        for _ in range(3):
            c.get("a")
        if c.stats["expirations"] != 1 or c.stats["misses"] != 3:
            e.append(f"hết hạn đếm sai: {c.stats}")
        store = getattr(c, "_data", None)  # đặc tả không bắt giữ tên _data; không có thì bỏ qua phép kiểm này
        if isinstance(store, dict) and "a" in store:
            e.append("mục hết hạn không bị xóa khi get")
        return e

    @case("pop")
    def _():
        k = Clock(); c = TTLCache(3, clock=k)
        c.set("a", 1, ttl=1); c.set("b", 2); k.now += 2
        e = []
        if c.pop("a", "D") != "D" or c.pop("zz", "D") != "D":
            e.append("pop mục hết hạn/không có phải trả default")
        if c.pop("b") != 2 or "b" in c:
            e.append("pop không gỡ mục")
        store = getattr(c, "_data", None)
        if isinstance(store, dict) and "a" in store:
            e.append("pop không gỡ mục hết hạn")
        if c.stats["hits"] or c.stats["misses"]:
            e.append("pop đổi hits/misses")
        return e

    @case("get_or_load")
    def _():
        k = Clock(); c = TTLCache(3, clock=k)
        calls = []
        v1 = c.get_or_load("a", lambda: calls.append(1) or 7)
        v2 = c.get_or_load("a", lambda: calls.append(1) or 8)
        e = []
        if (v1, v2, len(calls)) != (7, 7, 1) or c.stats["hits"] != 1 or c.stats["misses"] != 1:
            e.append(f"get_or_load sai: {(v1, v2, len(calls))} {c.stats}")

        def boom():
            raise RuntimeError("x")
        try:
            c.get_or_load("b", boom); e.append("không ném tiếp lỗi loader")
        except RuntimeError:
            pass
        if "b" in c or len(c) != 1 or c.stats["misses"] != 2:
            e.append(f"loader lỗi để lại dấu vết: {c.stats}")
        if c.get_or_load("b", lambda: 5) != 5:
            e.append("sau loader lỗi không nạp lại được")
        return e

    return out


def check(workdir, answer):
    workdir = Path(workdir)
    try:
        TTLCache = load(workdir)
    except Exception as exc:  # noqa: BLE001
        return False, f"không nạp được cache.py: {exc}"
    sys.dont_write_bytecode = True
    results = scenarios(TTLCache)
    problems = [f"{name}: {'; '.join(errs)}" for name, errs in results.items() if errs]
    return not problems, "; ".join(problems)[:600] or "đạt"
