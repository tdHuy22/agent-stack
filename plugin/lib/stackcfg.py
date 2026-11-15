"""Cấu hình riêng của project `.agent/stack.json` (GĐ4): hook đọc, model không đọc.

File nằm trong repo nên không tin được (TM-116..120): đọc có trần, mục sai dạng thì bỏ, không bao giờ văng lỗi; chữ tự do
(reason, evidence, name) không bao giờ ra context của hook. Siết tự do, nới cần người dùng duyệt: router dùng cấu hình gộp
với bản chụp đã duyệt trong state/ (trên máy, ngoài repo), lấy mức cao hơn từng mục; `ignore` chỉ có tác dụng khi đã duyệt.
Bản chụp luôn được ghi lại bằng cấu hình gộp, nên mục đã có mà sau bị bỏ hay hạ mức vẫn giữ cho tới khi người dùng duyệt.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import time
from functools import lru_cache
from pathlib import Path, PurePosixPath

import agentstack as A

STACK_REL = ".agent/stack.json"
MAX_BYTES = 64_000
MAX_PHRASES = 200
MAX_PHRASE = 60
MAX_TEXT = 500
MAX_PATHS = 20
MODELS = ("haiku", "sonnet", "opus")  # fable, max không nhận: repo lạ không đẩy được mọi câu lên mức đắt nhất
EFFORTS = ("low", "medium", "high", "xhigh")
MODEL_RANK = {"haiku": 0, "sonnet": 1, "opus": 2, "fable": 3}
EFFORT_RANK = {"low": 0, "medium": 1, "high": 2, "xhigh": 3, "max": 4}
RISKS = ("thap", "vua", "cao")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.+-]{0,39}$")
APPROVED_DIR = "stack-approved"
LEARN_DIR = "stack-learn"
KINDS = ("keyword", "ignore", "area", "floor", "tool", "min_risk")


@lru_cache(maxsize=512)
def pattern(phrase: str):
    return re.compile(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])")


def contains(folded: str, phrase: str) -> bool:
    """Cụm `phrase` (đã bỏ dấu) có trong `folded` như một từ trọn vẹn; chỉ chạy regex khi có chuỗi con (TM-118)."""
    return phrase in folded and bool(pattern(phrase).search(folded))


def fold_phrase(value):
    """Cụm từ đã bỏ dấu, hay None khi sai dạng (không phải chuỗi, quá ngắn hay dài, có ký tự điều khiển)."""
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if not 2 <= len(text) <= MAX_PHRASE or any(ord(c) < 32 for c in value):
        return None
    folded = A.fold(text)
    return folded if re.search(r"[a-z0-9]", folded) else None


def level_of(entry, raise_only: bool = False):
    """(model, effort) hợp lệ hay None. `raise_only` (từ khóa, vùng: chỉ để nâng): tối thiểu sonnet · medium, để câu
    không khớp luật nào không thành gợi ý haiku · low (luật project-keyword) mà thiếu file thì không có."""
    m, e = entry.get("model"), entry.get("effort")
    if m not in MODELS or e not in EFFORTS:
        return None
    if raise_only and (MODEL_RANK[m] < MODEL_RANK["sonnet"] or EFFORT_RANK[e] < EFFORT_RANK["medium"]):
        return None
    return m, e


def lvl_max(a, b):
    """Mức cao hơn từng phần: model cao hơn, effort cao hơn (sàn sonnet·xhigh với opus·high ra opus·xhigh)."""
    if a is None or b is None:
        return a or b
    return (max(a[0], b[0], key=MODEL_RANK.__getitem__), max(a[1], b[1], key=EFFORT_RANK.__getitem__))


def at_least(a, b) -> bool:
    """`a` không dưới `b` ở cả hai phần."""
    return MODEL_RANK[a[0]] >= MODEL_RANK[b[0]] and EFFORT_RANK[a[1]] >= EFFORT_RANK[b[1]]


def raise_to(model, effort, floor):
    """(model, effort) sau khi nâng lên sàn. Fable cao hơn mọi sàn hợp lệ (sàn không nhận fable) nên giữ nguyên, kể cả
    effort (chính sách Fable: high). Model hay effort lạ thì lấy của sàn."""
    if floor is None:
        return model, effort
    if model == "fable":
        return model, effort
    m = model if model in MODEL_RANK else floor[0]
    e = effort if effort in EFFORT_RANK else floor[1]
    m = max(m, floor[0], key=MODEL_RANK.__getitem__)
    e = max(e, floor[1], key=EFFORT_RANK.__getitem__)
    return m, e


def safe_rel(rel) -> bool:
    """Đường dẫn tương đối kiểu posix, không ra ngoài repo, không ký tự điều khiển (TM-120)."""
    if not isinstance(rel, str) or not rel or len(rel) > 200 or "\\" in rel or any(ord(c) < 32 for c in rel):
        return False
    p = PurePosixPath(rel)
    return not p.is_absolute() and ".." not in p.parts and p.parts[:1] != ("",) and "*" not in rel


def under(path: str, prefix: str) -> bool:
    prefix = prefix.rstrip("/")
    return path == prefix or path.startswith(prefix + "/")


def _meta(entry: dict) -> dict:
    return {k: entry[k][:MAX_TEXT] for k in ("reason", "evidence", "date") if isinstance(entry.get(k), str)}


def empty() -> dict:
    return {"keywords": {}, "ignore": {}, "areas": {}, "floors": {}, "tools": {}, "min_risk": None, "fingerprint": None}


def _list(data, key):
    value = data.get(key)
    return value if isinstance(value, list) else []


def blocks_protected(phrase: str, protected) -> bool:
    """Bỏ qua `phrase` có làm mất khớp của luật bảo mật không: cụm này nằm trong cụm của luật được bảo vệ, hay ngược lại."""
    return any(contains(p, phrase) or contains(phrase, p) for p in protected)


def parse(text, protected=()) -> tuple:
    """(cấu hình đã chuẩn hóa, [vấn đề]) từ chữ JSON. File hỏng thì (None, [vấn đề]). Vấn đề chỉ nêu loại và vị trí,
    không chép nội dung file (TM-117)."""
    problems = []
    try:
        data = json.loads(text) if isinstance(text, (str, bytes)) and len(text) <= MAX_BYTES else None
    except (ValueError, RecursionError):
        data = None
    if not isinstance(data, dict):
        return None, ["không đọc được (không phải JSON object, hay quá 64 KB)"]
    cfg = empty()
    budget = [MAX_PHRASES]

    def take(phrase, where):
        if budget[0] <= 0:
            problems.append(f"{where}: quá {MAX_PHRASES} cụm từ, bỏ phần thừa")
            return None
        budget[0] -= 1
        return phrase

    def note_meta(entry, where):
        missing = [k for k in ("reason", "evidence", "date") if not (isinstance(entry.get(k), str) and entry[k].strip())]
        if missing:
            problems.append(f"{where}: thiếu {', '.join(missing)}")

    for i, entry in enumerate(_list(data, "keywords")):
        where = f"keywords[{i}]"
        key = fold_phrase(entry.get("phrase")) if isinstance(entry, dict) else None
        level = level_of(entry, raise_only=True) if isinstance(entry, dict) else None
        if not key or not level:
            problems.append(f"{where}: sai dạng (cần phrase 2–60 ký tự, model sonnet|opus, effort medium..xhigh)")
            continue
        if not take(key, where):
            continue
        note_meta(entry, where)
        old = cfg["keywords"].get(key)
        level = lvl_max(level, (old["model"], old["effort"])) if old else level
        cfg["keywords"][key] = {"model": level[0], "effort": level[1], **_meta(entry)}
    for i, entry in enumerate(_list(data, "ignore")):
        where = f"ignore[{i}]"
        key = fold_phrase(entry.get("phrase")) if isinstance(entry, dict) else None
        if not key:
            problems.append(f"{where}: sai dạng (cần phrase 2–60 ký tự)")
            continue
        if blocks_protected(key, protected):
            problems.append(f"{where}: trùng từ khóa của luật bảo mật, không được bỏ qua")
            continue
        if not take(key, where):
            continue
        note_meta(entry, where)
        cfg["ignore"][key] = _meta(entry)
    for i, entry in enumerate(_list(data, "areas")):
        where = f"areas[{i}]"
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str) or not entry["name"].strip():
            problems.append(f"{where}: thiếu name")
            continue
        name = " ".join(entry["name"].split())[:MAX_PHRASE]
        level = level_of(entry, raise_only=True)
        paths = [norm for p in _list(entry, "paths") if safe_rel(p.strip() if isinstance(p, str) else p)
                 for norm in [PurePosixPath(p.strip()).as_posix()] if norm not in (".", "")]
        bad = len(_list(entry, "paths")) - len(paths)
        words = []
        for w in _list(entry, "words"):
            key = fold_phrase(w)
            if key and take(key, where):
                words.append(key)
            elif not key:
                bad += 1
        if bad:
            problems.append(f"{where}: bỏ {bad} đường dẫn hay từ sai dạng")
        if not level or not (paths or words):
            problems.append(f"{where}: cần model sonnet|opus, effort medium..xhigh và ít nhất một paths hay words")
            continue
        note_meta(entry, where)
        cfg["areas"][name] = {"paths": sorted(set(paths))[:MAX_PATHS], "words": sorted(set(words)), "model": level[0],
                              "effort": level[1], **_meta(entry)}
    for i, entry in enumerate(_list(data, "floors")):
        where = f"floors[{i}]"
        group = entry.get("group") if isinstance(entry, dict) else None
        level = level_of(entry) if isinstance(entry, dict) else None
        if not (isinstance(group, str) and NAME_RE.match(group)) or not level:
            problems.append(f"{where}: sai dạng (cần group, model, effort)")
            continue
        note_meta(entry, where)
        old = cfg["floors"].get(group)
        level = lvl_max(level, (old["model"], old["effort"])) if old else level
        cfg["floors"][group] = {"model": level[0], "effort": level[1], **_meta(entry)}
    for i, entry in enumerate(_list(data, "tools")):
        name = entry.get("name") if isinstance(entry, dict) else entry
        if not (isinstance(name, str) and NAME_RE.match(name)):
            problems.append(f"tools[{i}]: tên công cụ sai dạng (chỉ tên, không nhận lệnh)")
            continue
        cfg["tools"][name] = _meta(entry) if isinstance(entry, dict) else {}
    process = data.get("process")
    if isinstance(process, dict) and process.get("min_risk") is not None:
        if process.get("min_risk") in RISKS:
            cfg["min_risk"] = process["min_risk"]
        else:
            problems.append("process.min_risk: chỉ nhận thap, vua, cao")
    fp = data.get("fingerprint")
    if isinstance(fp, dict):
        kinds = sorted({k for k in _list(fp, "kinds") if isinstance(k, str) and NAME_RE.match(k)})[:10]
        cfg["fingerprint"] = {"kinds": kinds, **{k: fp[k] for k in ("tests", "security", "archctl")
                                                 if isinstance(fp.get(k), bool)}}
    return cfg, problems


def git_dir(start: Path, max_depth: int = 40):
    """(thư mục gốc chứa .git, thư mục git chung) đi lên từ `start`; không gọi git (hook phải nhanh)."""
    here = Path(start)
    for _ in range(max_depth):
        dot = here / ".git"
        try:
            if dot.is_dir():
                return here, dot
            if dot.is_file():
                text = dot.read_text(encoding="utf-8", errors="replace")[:4096]
                line = next((x for x in text.splitlines() if x.startswith("gitdir:")), "")
                gd = (here / line[len("gitdir:"):].strip()).resolve() if line else None
                if gd is None:
                    return here, dot
                common = gd / "commondir"
                if common.is_file():
                    return here, (gd / common.read_text(encoding="utf-8", errors="replace").strip()).resolve()
                return here, gd
        except OSError:
            return None, None
        if here.parent == here:
            break
        here = here.parent
    return None, None


def find_file(root):
    """(đường dẫn stack.json, thư mục gốc của nó): ở `root`, không có thì ở gốc git gần nhất; không có thì (None, base)."""
    root = Path(root)
    top, _ = git_dir(root)
    for base in dict.fromkeys([root] + ([top] if top else [])):
        path = base / STACK_REL
        try:
            os.lstat(path)
        except OSError:
            continue
        return path, base
    return None, root


def read_file(path: Path):
    """Chữ của file, hay None khi là symlink (file hay thư mục .agent), không phải file thường, quá lớn (TM-118)."""
    try:
        for p in (path.parent, path):
            if stat.S_ISLNK(os.lstat(p).st_mode):
                return None
        if not stat.S_ISREG(os.lstat(path).st_mode):
            return None
        with open(path, "rb") as fh:
            raw = fh.read(MAX_BYTES + 1)
        return None if len(raw) > MAX_BYTES else raw.decode("utf-8", errors="replace")
    except OSError:
        return None


def repo_key(root) -> str:
    """Khóa của bản chụp: thư mục git chung (các worktree dùng chung) cộng đường dẫn của `root` tính từ gốc git (hai
    stack.json trong một repo, hay hai project không git dưới một thư mục cha có git, không dùng chung bản chụp)."""
    root = Path(root)
    top, common = git_dir(root)
    target = common or root
    rel = ""
    try:
        target = target.resolve()
        if top is not None:
            rel = root.resolve().relative_to(Path(top).resolve()).as_posix()
    except (OSError, ValueError):
        pass
    rel = "" if rel == "." else rel
    return hashlib.sha256(f"{target}|{rel}".encode()).hexdigest()[:16]


SEEN = "seen.json"


def seen_keys() -> set:
    data = A.read_json(A.state_dir() / APPROVED_DIR / SEEN, [])
    return {k for k in data if isinstance(k, str)} if isinstance(data, list) else set()


def mark_seen(key: str) -> None:
    keys = seen_keys()
    if key in keys:
        return
    path = A.state_dir() / APPROVED_DIR / SEEN
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        A.write_json_atomic(path, sorted(keys | {key})[-5000:])
    except OSError:
        pass


def pending_hash(pending: list) -> str:
    """Mã băm ngắn của danh sách mục chờ duyệt: lời "duyệt hết <mã>" chỉ áp cho đúng danh sách người dùng đã xem."""
    return hashlib.sha256("\n".join(sorted(p["id"] for p in pending)).encode()).hexdigest()[:6]


def snapshot_path(root) -> Path:
    return A.state_dir() / APPROVED_DIR / f"{repo_key(root)}.json"


def load_snapshot(root):
    data = A.read_json(snapshot_path(root), None)
    if not isinstance(data, dict) or not isinstance(data.get("cfg"), dict):
        return None
    cfg = empty()
    for k in cfg:
        if k in data["cfg"]:
            cfg[k] = data["cfg"][k]
    return cfg if all(isinstance(cfg[k], dict) for k in ("keywords", "ignore", "areas", "floors", "tools")) else None


LOST_DAYS = 7  # báo "bản chụp đã mất" trong từng này ngày sau khi phát hiện


def lost_since(root):
    """Lúc phát hiện bản chụp của project đã mất (ghi trong bản chụp mới), hay None."""
    data = A.read_json(snapshot_path(root), None)
    ts = data.get("lost_ts") if isinstance(data, dict) else None
    return ts if isinstance(ts, (int, float)) else None


def save_snapshot(root, cfg: dict, lost_ts=None) -> None:
    path = snapshot_path(root)
    lost_ts = lost_ts if lost_ts is not None else lost_since(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        A.write_json_atomic(path, {"root": str(Path(root)), "cfg": cfg,
                                   **({"lost_ts": lost_ts} if lost_ts is not None else {})})
    except OSError:
        pass


def _level(entry):
    return entry["model"], entry["effort"]


def merge(snap, cur) -> tuple:
    """(cấu hình dùng, [mục nới chờ duyệt]). Từ khóa, vùng, sàn, công cụ, min_risk: hợp của hai bên, mức cao hơn;
    `ignore`: chỉ mục có ở cả hai. Mục nới: bên hiện tại hạ mức, bỏ mục, bớt đường dẫn hay từ, thêm `ignore`."""
    eff, pending = empty(), []
    for kind, key_name in (("keywords", "keyword"), ("floors", "floor")):
        for key in sorted(set(snap[kind]) | set(cur[kind])):
            s, c = snap[kind].get(key), cur[kind].get(key)
            if s and c:
                level = lvl_max(_level(s), _level(c))
                eff[kind][key] = dict(c, model=level[0], effort=level[1])
                if not at_least(_level(c), _level(s)):
                    pending.append({"id": f"{key_name}:{key}", "what": "hạ mức"})
            elif c:
                eff[kind][key] = c
            else:
                eff[kind][key] = s
                pending.append({"id": f"{key_name}:{key}", "what": "bỏ mục"})
    for name in sorted(set(snap["areas"]) | set(cur["areas"])):
        s, c = snap["areas"].get(name), cur["areas"].get(name)
        if s and c:
            level = lvl_max(_level(s), _level(c))
            eff["areas"][name] = dict(c, model=level[0], effort=level[1],
                                      paths=sorted(set(s["paths"]) | set(c["paths"])),
                                      words=sorted(set(s["words"]) | set(c["words"])))
            if not at_least(_level(c), _level(s)) or not set(s["paths"]) <= set(c["paths"]) \
                    or not set(s["words"]) <= set(c["words"]):
                pending.append({"id": f"area:{name}", "what": "hạ mức hay bớt đường dẫn, từ"})
        elif c:
            eff["areas"][name] = c
        else:
            eff["areas"][name] = s
            pending.append({"id": f"area:{name}", "what": "bỏ mục"})
    for name in sorted(set(snap["tools"]) | set(cur["tools"])):
        eff["tools"][name] = cur["tools"].get(name, snap["tools"].get(name))
        if name not in cur["tools"]:
            pending.append({"id": f"tool:{name}", "what": "bỏ công cụ kiểm"})
    for key in sorted(cur["ignore"]):
        if key in snap["ignore"]:
            eff["ignore"][key] = cur["ignore"][key]
        else:
            pending.append({"id": f"ignore:{key}", "what": "thêm từ khóa bỏ qua"})
    s_risk, c_risk = snap.get("min_risk"), cur.get("min_risk")
    ranks = [r for r in (s_risk, c_risk) if r in RISKS]
    eff["min_risk"] = max(ranks, key=RISKS.index) if ranks else None
    if s_risk in RISKS and (c_risk not in RISKS or RISKS.index(c_risk) < RISKS.index(s_risk)):
        pending.append({"id": "min_risk", "what": "hạ mức rủi ro tối thiểu"})
    eff["fingerprint"] = cur.get("fingerprint") or snap.get("fingerprint")
    return eff, pending


def approve(snap, cur, item: str):
    """Bản chụp mới sau khi người dùng duyệt mục nới `item` (id trong danh sách chờ), hay None nếu không có mục đó."""
    kind, _, key = item.partition(":")
    snap = json.loads(json.dumps(snap))
    table = {"keyword": "keywords", "floor": "floors", "area": "areas", "tool": "tools", "ignore": "ignore"}.get(kind)
    if item == "min_risk":
        snap["min_risk"] = cur.get("min_risk")
        return snap
    if not table or not key:
        return None
    if key in cur[table]:
        snap[table][key] = cur[table][key]
    elif key in snap[table]:
        del snap[table][key]
    else:
        return None
    return snap


def effective(root, protected=(), write: bool = True):
    """Cấu hình router dùng cho project ở `root`: {cfg, pending, problems, file, base}; None khi không có stack.json và
    chưa từng có bản chụp. File mất hay hỏng mà đã có bản chụp thì vẫn dùng bản chụp (xóa file là nới, cần duyệt).
    `write`: ghi bản chụp mới khi khác (hook ghi; lệnh xem thử thì không). Không bao giờ văng lỗi."""
    try:
        path, base = find_file(root)
        snap = load_snapshot(base)
        if path is None and snap is None:
            return None
        problems = []
        text = read_file(path) if path is not None else None
        if path is not None and text is None:
            problems.append("không đọc được (symlink, không phải file thường, hay quá 64 KB)")
        cur, more = parse(text, protected) if text is not None else (None, [])
        problems += more
        readable = cur is not None  # file mất hay hỏng: dùng bản chụp, không ghi đè (giữ `ignore` đã duyệt)
        cur = cur or empty()
        first = snap is None
        key = repo_key(base)
        lost = first and key in seen_keys()  # đã từng có bản chụp mà nay mất: báo, không coi như mới gặp lặng lẽ
        if first:  # lần đầu gặp: tin phần siết, chưa tin `ignore`
            snap = dict(cur, ignore={})
        eff, pending = merge(snap, cur)
        if write and readable and (first or eff != snap):
            save_snapshot(base, eff, time.time() if lost else None)
            mark_seen(key)
        since = lost_since(base) if not first else None
        lost = lost or (since is not None and time.time() - since < LOST_DAYS * 86400)
        return {"cfg": eff, "pending": pending, "problems": problems, "file": path, "base": base, "current": cur,
                "snapshot": snap, "lost": lost, "first": first and not lost}
    except Exception as exc:  # noqa: BLE001 (hook không bao giờ kẹt vì file của repo lạ)
        A.log_event("hook-error", {"hook": "stackcfg", "error": repr(exc)[:300]})
        return None


def fingerprint(profile: dict, root) -> dict:
    """Dấu vân tay hồ sơ: ngôn ngữ, có test, có code bảo mật, có archctl (thư mục .arch/)."""
    markers = set(profile.get("markers") or [])
    return {"kinds": sorted(k for k in profile.get("kinds") or [] if isinstance(k, str)), "tests": "tests" in markers,
            "security": "security" in markers, "archctl": (Path(root) / ".arch").is_dir()}


FP_LABELS = {"kinds": "ngôn ngữ", "tests": "có test", "security": "code bảo mật", "archctl": "archctl"}


def fingerprint_drift(saved, now: dict) -> list:
    """Phần hồ sơ đã đổi so với lúc chạy project-setup (nhãn cố định, không chép chữ của file)."""
    if not isinstance(saved, dict):
        return []
    return [FP_LABELS[k] for k in ("kinds", "tests", "security", "archctl") if k in saved and saved[k] != now.get(k)]


def learn_count(root) -> int:
    """Số đề xuất sửa stack.json do `stack.py learn` ghi đệm (hook chỉ đọc số, không gom nhật ký)."""
    data = A.read_json(A.state_dir() / LEARN_DIR / f"{repo_key(root)}.json", {})
    count = data.get("count") if isinstance(data, dict) else 0
    return count if isinstance(count, int) and count > 0 else 0
