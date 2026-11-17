#!/usr/bin/env python3
"""Mutation trên dòng vừa đổi (done-gate bước 4, mức cao; GĐ6, S9): cài lỗi nhỏ vào dòng code vừa đổi rồi chạy test;
đột biến nào test không bắt (sống) là chỗ test còn yếu. Chỉ để báo, không chặn: luôn thoát mã 0, dòng cuối `Mutation:`.

Python dùng mutmut 2.5.1 (bạn duyệt 16/11/2026, cài vào `.venv-mutmut/` của agent-stack bằng `mutation.py setup`):
`--runner` nhận lệnh test bất kỳ, `--use-patch-file` chỉ đột biến dòng thêm trong bản vá. mutmut sửa file tại chỗ và nạp
`mutmut_config.py` ở thư mục đang chạy, nên luôn chạy trong bản chép cây làm việc ở thư mục tạm của hệ điều hành, xóa
bản chép khi xong, kể cả khi quá giờ (TM-129). Rust (cargo-mutants), Go (gremlins), TypeScript (Stryker) chưa vet: báo
"chưa chạy".

Dòng thêm lấy bằng `git diff --no-index -U0` (như checks.py, risk.py). Bản vá cho mutmut có tiêu đề git đủ cho từng
file: whatthepatch (mutmut dùng để đọc) gộp các file nối nhau chỉ có `---`/`+++` thành một file (spec
`mutation-nhieu-file`, S1). mutmut 2.5.1 chạy cả lệnh test cho mỗi đột biến, lần lượt, nên diff lớn chia dòng thêm cho
vài lần chạy song song, mỗi lần một bản chép (S3, S4). Đột biến báo ở ngoài dòng thêm được ghi riêng (S2); quá giờ thì
file đang đột biến dở được trả về bản gốc trước khi đọc kết quả (S5), và đột biến chưa chạy tới có vị trí và ước thời gian
còn cần (S6).

Lệnh:
  mutation.py [--project DIR] [--base REF] [--cmd "<lệnh test>"] [--timeout GIÂY] [--mutmut PATH] [--link PATH...]
              [--jobs N] [--json]
      Lệnh test: `--cmd`, không thì `cmd` trong sổ khóa của các file test đã khóa có trong diff. mutmut: `--mutmut`,
      biến AGENT_STACK_MUTMUT, rồi `<agent-stack>/.venv-mutmut/bin/mutmut`. Số lần chạy song song: `--jobs N` (tối đa
      bằng số dòng code thêm), không thì min(4, số lõi/2, số dòng code thêm/10), ít nhất 1. `--timeout` là hạn chung.
  mutation.py setup
      Tạo `.venv-mutmut/` của agent-stack từ `tools/mutmut-requirements.txt` (mã băm) và
      `tools/mutmut-build-constraints.txt`; mã thoát khác 0 khi cài hỏng.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3] / "lib"))
sys.path.insert(0, str(HERE.parents[2] / "session-keeper" / "scripts"))  # fails_before: dựng bản chép
sys.path.insert(0, str(HERE.parent))
IMPORT_ERROR = None
try:  # bản cài hỏng cũng phải thoát 0 với dòng trạng thái (S9)
    import agentstack as A
    import fails_before as FB
    import risk
    import testlock as TL
except Exception as exc:  # noqa: BLE001
    IMPORT_ERROR = exc

DEFAULT_TIMEOUT = 540.0  # dưới trần 600 giây của lệnh Bash chạy trước mặt, để kịp in dòng trạng thái
QUERY_TIMEOUT = 60
GIT_TIMEOUT = 60
MAX_LISTED = 12
# nhãn trạng thái của đột biến ngoài dòng đổi trong dòng ⚠ (khóa `status` của `outside`)
OUTSIDE_LABELS = {"killed": "bị bắt", "survived": "sống", "timeout": "quá giờ", "untested": "chưa chạy",
                  "suspicious": "đáng ngờ", "skipped": "bỏ qua", "other": "trạng thái khác"}
MAX_RANGES = 20  # khoảng dòng chưa chạy tới in ra chữ (JSON có đủ)
MAX_JOBS = 4
LINES_PER_JOB = 10  # dòng code thêm cho mỗi lần chạy song song khi tự chọn (S3)
# str.splitlines (whatthepatch dùng) tách dòng ở các ký tự này, git chỉ tách ở \n: đổi thành dấu cách trong bản vá để hai
# bên đếm dòng như nhau.
LINE_BREAKS = {ord(c): " " for c in "\r\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029"}
OTHER_LANGS = {".rs": "Rust (cargo-mutants)", ".go": "Go (gremlins)", ".ts": "TypeScript (Stryker)",
               ".tsx": "TypeScript (Stryker)", ".js": "JavaScript (Stryker)", ".jsx": "JavaScript (Stryker)",
               ".mjs": "JavaScript (Stryker)", ".cjs": "JavaScript (Stryker)"}


class Skip(Exception):
    """Không chạy được: lý do vào dòng trạng thái "chưa chạy: …"."""


class Args(argparse.ArgumentParser):
    def error(self, message):  # tham số sai cũng không được thoát khác 0 (S9)
        raise Skip(f"tham số sai ({message})")


def stack_root() -> Path:
    try:
        return Path(A.home_dir())
    except Exception:  # noqa: BLE001
        return HERE.parents[4]


def find_mutmut(option) -> Path:
    value = option or os.environ.get("AGENT_STACK_MUTMUT") or str(stack_root() / ".venv-mutmut" / "bin" / "mutmut")
    path = Path(value).expanduser()
    if not (path.is_file() and os.access(path, os.X_OK)):
        raise Skip(f"thiếu mutmut ({path}); cài bằng `python3 {HERE} setup` (bạn đã duyệt mutmut 2.5.1, 16/11/2026)")
    return path


def runner_for(option, book: dict, changed) -> str:
    """Lệnh test cho `--runner` (một chuỗi; mutmut tách bằng shlex, không qua shell)."""
    if option:
        return option
    cmds = []
    for rel, entry in sorted(book["files"].items()):
        cmd, cwd = entry.get("cmd"), entry.get("cwd")
        if not (rel in changed and isinstance(cmd, list) and cmd and all(isinstance(x, str) for x in cmd)):
            continue
        # Mục khóa ghi bằng `--cwd`: chạy lệnh test trong thư mục đó (tương đối với project, không ra ngoài).
        where = cwd if isinstance(cwd, str) and cwd not in ("", ".") and ".." not in Path(cwd).parts \
            and not Path(cwd).is_absolute() else None
        if (cmd, where) not in cmds:
            cmds.append((cmd, where))
    if not cmds:
        raise Skip("không biết lệnh test: nêu --cmd \"<lệnh test>\", hay khóa test trước (`receipt.py lock --red`) để sổ "
                   "khóa có lệnh")
    if len(cmds) == 1 and cmds[0][1] is None:
        return shlex.join(cmds[0][0])
    parts = [(f"cd {shlex.quote(where)} && " if where else "") + shlex.join(cmd) for cmd, where in cmds]
    return shlex.join(["sh", "-c", " && ".join(f"({p})" if len(cmds) > 1 else p for p in parts)])


def text_lines(data: bytes) -> list:
    """Các dòng của file theo cách git đếm (chỉ tách ở \\n)."""
    lines = data.decode("utf-8", "replace").split("\n")
    return lines[:-1] if lines and lines[-1] == "" else lines


def is_code(line: str) -> bool:
    """Dòng code: không trống, không chỉ có chú thích (S3)."""
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("#")


def added_lines(paths, entries: dict, blobs: dict, current: dict, work: Path) -> dict:
    """{file: danh sách dòng thêm đã sắp} theo `git diff --no-index -U0` giữa bản ở base (hay rỗng nếu file mới) và bản
    hiện tại. Chỉ đọc dòng `@@`, không đọc tên file trong output của git."""
    work.mkdir()
    out = {}
    for i, rel in enumerate(paths):
        old = work / f"old-{i}"
        new = work / f"new-{i}"
        old.write_bytes(blobs.get(entries[rel][1], b"") if rel in entries else b"")
        new.write_bytes(current[rel][1])
        try:
            proc = subprocess.run(["git", "-c", "diff.interHunkContext=0", "diff", "--no-index", "-U0", "--no-color", "--no-ext-diff", "--no-textconv",
                                   "-a", "--", str(old), str(new)], cwd=str(work), capture_output=True,
                                  timeout=GIT_TIMEOUT)
        except (OSError, subprocess.SubprocessError) as exc:
            raise Skip(f"git diff lỗi với {rel} ({exc.__class__.__name__})") from None
        if proc.returncode not in (0, 1):
            raise Skip(f"git diff lỗi với {rel}: {proc.stderr.decode('utf-8', 'replace').strip()[:200]}")
        lines, number = set(), None
        for line in proc.stdout.decode("utf-8", "replace").split("\n"):
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            if m:
                number = int(m.group(1))
            elif number is not None and line[:1] == "+":  # chỉ dòng `+`: ngữ cảnh (GIT_DIFF_OPTS, interHunkContext) bỏ
                lines.add(number)
                number += 1
            elif number is not None and line[:1] == " ":
                number += 1
        if lines:
            out[rel] = sorted(lines)
    return out


def jobs_for(option, code: int) -> int:
    """Số lần chạy mutmut song song (S3, S4)."""
    if option is not None:
        return max(1, min(option, code))
    return max(1, min(MAX_JOBS, (os.cpu_count() or 2) // 2, code // LINES_PER_JOB))


def split_lines(added: dict, texts: dict, jobs: int) -> list:
    """Chia dòng thêm cho `jobs` lần chạy: dòng code chia vòng tròn (đang dở khi quá giờ thì phần đã chạy vẫn rải đều cả
    diff); dòng trống hay chú thích đi theo lần chạy của dòng code đứng trước nó trong cùng file (đầu file thì của dòng
    code sau nó; file không có dòng code thì lần chạy đầu). Mỗi dòng thêm thuộc đúng một lần chạy."""
    groups = [{} for _ in range(jobs)]
    turn = 0
    for rel in sorted(added):
        owner, pending = None, []
        for n in added[rel]:
            if is_code(texts[rel][n - 1]):
                owner, turn = turn % jobs, turn + 1
                groups[owner].setdefault(rel, []).extend(pending + [n])
                pending = []
            elif owner is None:
                pending.append(n)
            else:
                groups[owner].setdefault(rel, []).append(n)
        if pending:
            groups[0].setdefault(rel, []).extend(pending)
    return [{rel: sorted(lines) for rel, lines in g.items()} for g in groups if g]


def runs_of(lines: list) -> list:
    """[[dòng đầu, dòng cuối]] của các đoạn dòng liền nhau."""
    out = []
    for n in lines:
        if out and n == out[-1][1] + 1:
            out[-1][1] = n
        else:
            out.append([n, n])
    return out


def make_patch(group: dict, texts: dict, prefix: str) -> str:
    """Bản vá cho mutmut: mỗi file một tiêu đề git đủ (`diff --git`, `index`, `---`, `+++`) để whatthepatch tách đúng
    từng file và đọc tên bằng `parse_git_header` (tên có dấu cách, dấu hai chấm vẫn đúng); hunk chỉ có dòng thêm. Tên
    tính từ thư mục chạy mutmut; tên bắt đầu bằng `a/` hay `b/` viết thành `./tên` vì whatthepatch bỏ tiền tố đó hai lần
    (mutmut `normpath` lại)."""
    out = []
    for rel in sorted(group):
        name = rel[len(prefix):]
        shown = "./" + name if name.startswith(("a/", "b/")) else name
        out += [f"diff --git a/{shown} b/{shown}", "index 0000000..0000000", f"--- a/{shown}", f"+++ b/{shown}"]
        for first, last in runs_of(group[rel]):
            out.append(f"@@ -{first - 1},0 +{first},{last - first + 1} @@")
            out += ["+" + texts[rel][n - 1].translate(LINE_BREAKS) for n in range(first, last + 1)]
    return "\n".join(out) + "\n"


def tests_dir(cwd: Path, book: dict, prefix: str) -> str:
    for name in ("tests", "test"):
        if (cwd / name).is_dir():
            return name
    for rel in sorted(book["files"]):
        if rel.startswith(prefix) and risk.kind(rel) == "test":
            parent = Path(rel[len(prefix):]).parent.as_posix()
            if (cwd / parent).is_dir():
                return parent
    return "."


RUNNING: list = []  # tiến trình mutmut đang chạy, để SIGTERM và finally giết cả nhóm (TM-129)


def kill_group(proc) -> None:
    """Giết cả nhóm tiến trình của mutmut, kể cả khi mutmut đã thoát mà lệnh test con còn sống trong nhóm."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def baseline_failed(w: dict) -> bool:
    """Lần chạy trượt ngay ở lần chạy test gốc: mutmut in "don't run cleanly" và dừng trước khi đột biến gì."""
    return w["code"] is not None and bool(w["code"] & 1) and "cleanly" in (w["output"] or "")


def retry_alone(w: dict, mutmut: Path, deadline: float, started: float) -> None:
    """Chạy lại một mình lần chạy `w` (cùng hạn chót). Chỉ thay kết quả khi lần chạy lại thật sự kiểm được đột biến;
    không thì giữ lần trượt, phần đó vẫn tính là chưa kiểm. Ghi `retry_ok` cho dòng ghi chú."""
    (w["cwd"] / ".mutmut-cache").unlink(missing_ok=True)
    code, output = finish_group(start_group(w["cmd"], w["cwd"], w["log"]), deadline, w["log"])
    restore_backups(w["cwd"], w["targets"])
    res = collect(mutmut, w["cwd"])
    w["retry_ok"] = code is not None and not code & 1 and bool(res["total"])
    if w["retry_ok"]:
        w.update(code=code, output=output, res=res, seconds=time.monotonic() - started)


def start_group(cmd: list, cwd: Path, log: Path):
    """Chạy `cmd` trong nhóm tiến trình riêng. Output ghi ra file (không qua pipe: tiến trình cháu tách session mà giữ
    pipe thì đọc pipe treo mãi)."""
    with open(log, "wb") as out:
        proc = subprocess.Popen(cmd, cwd=str(cwd), stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                start_new_session=True)
    RUNNING.append(proc)
    return proc


def finish_group(proc, deadline: float, log: Path):
    """(mã thoát hay None khi quá hạn chót, output). Quá hạn thì giết cả nhóm tiến trình (lệnh test con của mutmut)."""
    try:
        code = proc.wait(timeout=max(0.0, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        code = None
    finally:
        kill_group(proc)  # cả khi xong: lệnh test con có thể còn sống trong nhóm
        RUNNING.remove(proc)
    try:
        text = log.read_bytes()[-20000:].decode("utf-8", "replace")
    except OSError:
        text = ""
    return code, text


def guard_targets(tree: Path, cwd: Path, targets) -> None:
    """Trước khi mutmut chạy: mỗi file đích phải nằm thật trong bản chép (không qua thư mục symlink), và `<đích>.bak` có
    sẵn trong cây bị xóa, vì mutmut mở `<đích>.bak` để ghi và sẽ ghi xuyên symlink ra file thật (TM-137)."""
    root = os.path.realpath(tree) + os.sep
    for rel in targets:
        if not os.path.realpath(cwd / rel).startswith(root):
            raise Skip(f"{rel} trỏ ra ngoài bản chép (symlink trong đường dẫn): không chạy mutmut")
        bak = cwd / (rel + ".bak")
        if bak.is_dir() and not bak.is_symlink():
            shutil.rmtree(bak)
        elif os.path.lexists(bak):
            bak.unlink()


def restore_backups(cwd: Path, targets) -> None:
    """mutmut bị giết giữa một đột biến thì file còn mã đột biến và bản gốc nằm ở `<file>.bak`: trả về trước khi đọc kết
    quả, vì `junitxml`, `show` đọc lại file nguồn (S5). Chỉ trong bản chép, chỉ các file đích của chính lần chạy."""
    for rel in targets:
        bak = cwd / (rel + ".bak")
        if bak.is_file() and not bak.is_symlink():
            try:
                os.replace(bak, cwd / rel)
            except OSError:
                pass


def on_term(*_):
    for proc in RUNNING:
        kill_group(proc)
    sys.exit(143)


def query(mutmut: Path, cwd: Path, *args: str) -> str:
    try:
        out = subprocess.run([str(mutmut), *args], cwd=str(cwd), capture_output=True, text=True, errors="replace",
                             timeout=QUERY_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout or ""


def parse_results(xml_text: str) -> dict:
    """Kết quả từ `mutmut junitxml`: mỗi testcase là một đột biến (tên `Mutant #<id>`); có <failure> là sống, <error
    type=timeout> là quá giờ. `where`: (id, file, dòng, trạng thái) của mọi testcase. XML hỏng thì như không có kết quả."""
    res = {"total": 0, "survived": [], "timeout": 0, "where": []}
    try:
        root = ET.fromstring(xml_text) if xml_text.strip() else None
    except ET.ParseError:
        root = None
    if root is None:
        return res
    for case in root.iter("testcase"):
        res["total"] += 1
        try:
            line = int(case.get("line") or 0)
        except ValueError:
            line = 0
        name = case.get("file") or "?"
        mid = (case.get("name") or "").rpartition("#")[2].strip()
        failure = case.find("failure")
        error = case.find("error")
        state = "other"
        if failure is not None:
            diff = (failure.text or failure.get("message") or "").strip()
            res["survived"].append({"file": name, "line": line, "diff": diff[:600]})
            state = "survived"
        elif error is not None and (error.get("type") or "") == "timeout":
            res["timeout"] += 1
            state = "timeout"
        res["where"].append((mid, name, line, state))
    return res


STATUSES = ("killed", "survived", "timeout", "suspicious", "untested", "skipped")
MAX_SHOW = 40  # số đột biến sống lấy vị trí bằng `mutmut show` khi junitxml hỏng


def parse_show(text: str):
    """Vị trí đột biến từ `mutmut show <id>` (bản vá hợp nhất): file ở dòng `--- `, dòng = đầu đoạn phía cũ cộng số
    dòng ngữ cảnh đứng trước dòng `-` đầu tiên."""
    path, start, offset = None, None, 0
    for line in text.splitlines():
        if line.startswith("--- ") and path is None:
            path = line[4:].strip().split("\t")[0]  # mutmut show in đúng tên file, không thêm tiền tố a/
        elif line.startswith("@@") and start is None:
            m = re.match(r"@@ -(\d+)", line)
            start = int(m.group(1)) if m else None
        elif start is not None and line.startswith("-"):
            return {"file": path or "?", "line": start + offset, "diff": text.strip()[:600]}
        elif start is not None and line.startswith(" "):
            offset += 1
    return None


def results_by_ids(mutmut: Path, cwd: Path) -> dict:
    """Kết quả khi `mutmut junitxml` hỏng (mutmut 2.5.1 văng lỗi pony sau khi lần chạy bị giết vì quá giờ): đếm bằng
    `result-ids`, vị trí đột biến sống bằng `show`."""
    ids = {st: query(mutmut, cwd, "result-ids", st).split() for st in STATUSES}
    survived = []
    for i, mid in enumerate(ids["survived"]):
        loc = parse_show(query(mutmut, cwd, "show", mid)) if i < MAX_SHOW else None
        survived.append(loc or {"file": "?", "line": 0, "diff": ""})
    return {"total": sum(len(v) for v in ids.values()), "survived": survived, "timeout": len(ids["timeout"]),
            "killed": len(ids["killed"]), "untested": len(ids["untested"])}


def analyse(args) -> dict:
    root = Path(args.project).expanduser()
    if not root.is_dir():
        raise Skip(f"không thấy thư mục project {root}")
    root = root.resolve()
    top_out = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if top_out.returncode != 0 or not top_out.stdout.strip():
        raise Skip("không phải git repo (cần git để biết dòng nào vừa đổi)")
    top = Path(top_out.stdout.strip()).resolve()
    try:
        sha = FB.git(top, "rev-parse", "--verify", "-q", args.base + "^{commit}").decode().strip()
        entries, current = FB.base_entries(top, sha), FB.current_files(top)
    except FB.Problem as exc:
        raise Skip(str(exc)) from None
    changed, _deleted = FB.diff(entries, current)
    sub = root.relative_to(top).as_posix()
    prefix = "" if sub == "." else sub + "/"
    code = [p for p in sorted(changed) if risk.kind(p) == "code" and p.startswith(prefix)]
    py = [p for p in code if p.endswith(".py")]
    others = sorted({OTHER_LANGS[Path(p).suffix] for p in code if Path(p).suffix in OTHER_LANGS})
    notes = [f"chưa chạy cho {lang}: công cụ chưa vet (ngoài phạm vi GĐ6)" for lang in others]
    odd = [p for p in py if current[p][0] == FB.SYMLINK or any(c in p for c in ",\n\r")]
    notes += [f"bỏ {p}: " + ("là symlink, mutmut sẽ ghi xuyên ra file thật ngoài bản chép"
                             if current[p][0] == FB.SYMLINK else "tên có dấu phẩy hay xuống dòng, mutmut không đọc được")
              for p in odd]
    py = [p for p in py if p not in odd]
    if not py:
        raise Skip("không có file Python nào đổi so với " + args.base + (f" ({'; '.join(notes)})" if notes else ""))
    mutmut = find_mutmut(args.mutmut)
    book = TL.load(top)
    runner = runner_for(args.cmd, book, changed)
    links = FB.check_links(root, top, args.link)
    blobs = FB.read_blobs(top, [entries[p][1] for p in py if p in entries])
    return {"top": top, "sub": sub, "prefix": prefix, "py": py, "notes": notes, "mutmut": mutmut, "book": book,
            "runner": runner, "links": links, "entries": entries, "blobs": blobs, "current": current}


def build_tree(info: dict, base: Path, first=None) -> Path:
    """Bản chép cây làm việc (cả file chưa track) dưới `base`; trả về thư mục chạy mutmut. Có `first` (bản chép đầu,
    chưa chạy gì) thì chép nguyên cây đó, giữ symlink `--link` là symlink."""
    tree = base / info["top"].name
    if first is not None:
        base.mkdir()
        shutil.copytree(first, tree, symlinks=True)
    else:
        tree.mkdir(parents=True)
        for rel, (mode, data) in info["current"].items():
            FB.put(tree, rel, mode, data)
        for rel in info["links"]:
            FB.put(tree, rel, FB.SYMLINK, os.fsencode(str(info["top"] / rel)))
    return tree / info["sub"] if info["sub"] != "." else tree


def collect(mutmut: Path, cwd: Path) -> dict:
    """Kết quả một lần chạy, đọc trong chính bản chép của nó. `located`: (file, dòng, trạng thái) của các đột biến biết
    vị trí (trạng thái sống, quá giờ theo junitxml; bị bắt, chưa chạy theo `result-ids`); `known`: biết vị trí phần chưa
    chạy tới."""
    res = parse_results(query(mutmut, cwd, "junitxml"))
    if res["total"]:
        killed = query(mutmut, cwd, "result-ids", "killed").split()
        untested = query(mutmut, cwd, "result-ids", "untested").split()
        by_id = {**dict.fromkeys(untested, "untested"), **dict.fromkeys(killed, "killed")}
        res.update(killed=len(set(killed)), untested=len(set(untested)), known=True,
                   located=[(name, line, by_id.get(mid, state) if state == "other" else state)
                            for mid, name, line, state in res.pop("where")])
    else:
        res = results_by_ids(mutmut, cwd)
        res.update(known=not res["untested"],
                   located=[(s["file"], s["line"], "survived") for s in res["survived"] if s["file"] != "?"])
    return res


def line_ranges(points) -> list:
    """Gộp (file, dòng) thành khoảng dòng liền nhau theo file, kèm số đột biến (S6)."""
    by_file = {}
    for name, line in points:
        counts = by_file.setdefault(name, {})
        counts[line] = counts.get(line, 0) + 1
    out = []
    for name in sorted(by_file):
        counts = by_file[name]
        for first, last in runs_of(sorted(counts)):
            out.append({"file": name, "start": first, "end": last,
                        "mutants": sum(counts[n] for n in range(first, last + 1))})
    return out


def run(args) -> dict:
    info = analyse(args)
    prefix = info["prefix"]
    tmp = Path(tempfile.mkdtemp(prefix="mutation-"))  # quyền 0700
    previous = signal.signal(signal.SIGTERM, on_term)
    started = time.monotonic()
    workers = []
    try:
        added = added_lines(info["py"], info["entries"], info["blobs"], info["current"], tmp / "diff")
        if not added:
            raise Skip("không có dòng Python nào thêm so với " + args.base + " (chỉ xóa dòng)")
        texts = {rel: text_lines(info["current"][rel][1]) for rel in added}
        info["notes"] += [f"{rel} có ký tự \\r đứng riêng: mutmut tính nó là xuống dòng, git thì không, nên số dòng có "
                          "thể lệch" for rel in added if re.search(rb"\r(?!\n)", info["current"][rel][1])]
        code = sum(1 for rel, lines in added.items() for n in lines if is_code(texts[rel][n - 1]))
        deadline = started + args.timeout
        first = None
        for i, group in enumerate(split_lines(added, texts, jobs_for(args.jobs, code))):
            base = tmp / f"w{i}"
            cwd = build_tree(info, base, first)  # dựng đủ các bản chép trước khi mutmut nào chạy (mutmut ghi vào cây)
            first = first or base / info["top"].name
            patch = base / "mutmut.patch"
            patch.write_text(make_patch(group, texts, prefix), encoding="utf-8")
            targets = [rel[len(prefix):] for rel in sorted(group)]
            guard_targets(base / info["top"].name, cwd, targets)
            workers.append({"cwd": cwd, "targets": targets, "log": base / "mutmut-run.log", "group": group, "cmd": [
                str(info["mutmut"]), "run", "--paths-to-mutate", ",".join(targets), "--runner", info["runner"],
                "--use-patch-file", str(patch), "--tests-dir", tests_dir(cwd, info["book"], prefix)]})
        info["current"] = info["blobs"] = None  # nội dung cả repo không cần giữ trong lúc chờ mutmut
        for w in workers:
            w["proc"] = start_group(w["cmd"], w["cwd"], w["log"])
        for w in workers:  # cùng một hạn chót: lần chạy sau không được thêm giờ
            w["code"], w["output"] = finish_group(w["proc"], deadline, w["log"])
            w["seconds"] = time.monotonic() - started
        for w in workers:
            restore_backups(w["cwd"], w["targets"])
            w["res"] = collect(info["mutmut"], w["cwd"])
        for w in workers:  # trượt ở lần chạy test gốc khi máy bận (nhiều lần chạy song song): chạy lại một mình, một lần
            if baseline_failed(w) and time.monotonic() < deadline:
                retry_alone(w, info["mutmut"], deadline, started)
    finally:
        mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM})  # SIGTERM lúc dọn: chờ dọn xong mới nhận
        try:
            for proc in list(RUNNING):  # lỗi giữa chừng: không để lần chạy nào sống sau khi xóa bản chép
                kill_group(proc)
                RUNNING.remove(proc)
            shutil.rmtree(tmp, ignore_errors=True)
        finally:
            signal.signal(signal.SIGTERM, previous)
            signal.pthread_sigmask(signal.SIG_SETMASK, mask)
    expected = {rel[len(prefix):]: set(lines) for rel, lines in added.items()}
    res = {"total": 0, "killed": 0, "timeout": 0, "untested": 0, "survived": []}
    outside, unreached, estimate = [], [], 0
    for w in workers:
        part = w["res"]
        for key in ("total", "killed", "timeout", "untested"):
            res[key] += part[key]
        res["survived"] += part["survived"]
        unreached += [(name, line) for name, line, state in part["located"] if state == "untested"]
        outside += [{"file": name, "line": line, "status": state} for name, line, state in part["located"]
                    if line not in expected.get(os.path.normpath(name), ())]
        if part["untested"]:  # ước theo nhịp của chính lần chạy đó (mỗi đột biến chạy cả lệnh test)
            tested = max(0, part["total"] - part["untested"])
            estimate = max(estimate, math.ceil(part["untested"] * w["seconds"] / (tested + 1)))
    res.update(notes=info["notes"], files=info["py"], runner=info["runner"], jobs=len(workers), outside=outside,
               unreached=line_ranges(unreached), unreached_known=all(w["res"]["known"] for w in workers),
               estimate_seconds=estimate, seconds=round(time.monotonic() - started, 1))
    output = "\n".join(w["output"] for w in workers)
    # bit 1 của mã thoát: mutmut lỗi nặng (baseline trượt, sập giữa chừng). Thoát 0 mà không có đột biến là hợp lệ
    # (nhóm chỉ có import, def, docstring).
    failed = [w for w in workers if w["code"] is not None and w["code"] & 1]
    for w in workers:
        if "retry_ok" in w:
            res["notes"].append(f"lần chạy mutmut của {', '.join(w['targets'][:3])} trượt ở lần chạy test gốc (máy bận?), "
                                "đã chạy lại một mình: "
                                + ("đạt, phần đó đã kiểm" if w["retry_ok"] else "vẫn chưa kiểm được"))
    for w in failed:
        tail = " ".join(w["output"].strip().splitlines()[-2:])[-200:]
        spans = line_ranges((rel[len(prefix):], n) for rel, lines in w["group"].items() for n in lines)
        where = ", ".join(f"{r['file']}:{r['start']}" + (f"-{r['end']}" if r["end"] != r["start"] else "")
                          for r in spans[:MAX_RANGES])
        res["notes"].append(f"lần chạy mutmut lỗi (mã {w['code']}), có thể chưa kiểm {where}; mutmut: {tail}")
    if len(workers) > 1:
        res["notes"].append(f"{len(workers)} lần chạy song song: test phải chạy song song được (cổng, file cố định), "
                            "không thì chạy lại với --jobs 1")
    res["timed_out"] = any(w["code"] is None for w in workers)
    if res["timed_out"]:
        res.update(status="partial" if res["total"] else "skipped", reason=f"quá giờ sau {args.timeout:g} giây")
    elif not res["total"]:
        tail = " ".join(workers[0]["output"].strip().splitlines()[-2:])[-200:]
        why = ("test không đạt trên code hiện tại (mutmut cần test xanh trước khi đột biến)"
               if "cleanly" in output else
               "mutmut không sinh đột biến nào trên dòng đổi (dòng đổi chỉ là chú thích hay chuỗi tài liệu, hay "
               "đường dẫn trong bản vá lệch)")
        res.update(status="skipped", reason=why + (f"; mutmut: {tail}" if tail else ""))
    elif failed:
        res.update(status="partial", reason=f"{len(failed)}/{len(workers)} lần chạy mutmut lỗi, phần của nó chưa kiểm")
    else:
        res.update(status="ran")
    return res


def outside_lines(res: dict) -> list:
    """Cảnh báo đột biến ngoài dòng đổi (S2): bản vá lệch, không phải kết quả của dòng đổi. Liệt kê mọi vị trí, mỗi vị
    trí kèm nhãn trạng thái (`calc.py:4 (bị bắt)`, `(chưa chạy)`, `(sống)`, `(quá giờ)`), cắt ở MAX_LISTED kèm "và N chỗ
    khác". Đột biến sống và quá giờ xếp trước, để phần bị cắt không phải là phần người đọc cần thấy."""
    outside = res.get("outside") or []
    if not outside:
        return []
    order = {"survived": 0, "timeout": 1}
    ranked = sorted(outside, key=lambda o: order.get(o.get("status"), 2))  # sort ổn định: giữ thứ tự gốc trong mỗi nhóm
    spots = ", ".join(f"{o['file']}:{o['line']} ({OUTSIDE_LABELS.get(o.get('status'), o.get('status') or '?')})"
                      for o in ranked[:MAX_LISTED])
    more = len(ranked) - MAX_LISTED
    return [f"- ⚠ {len(outside)} đột biến ngoài dòng đổi (bản vá lệch, không tính là kết quả của dòng đổi): {spots}"
            + (f" và {more} chỗ khác" if more > 0 else "")]


def unreached_lines(res: dict) -> list:
    """Đột biến chưa chạy tới: vị trí theo khoảng dòng và ước thời gian còn cần (S6)."""
    if not res.get("untested"):
        return []
    estimate = res.get("estimate_seconds") or 0
    suggest = math.ceil((res.get("seconds", 0) + estimate) * 1.2 / 60) * 60  # chạy lại từ đầu: bản chép đã xóa
    if res.get("timed_out", True):
        hint = (f"ước cần thêm khoảng {max(1, math.ceil(estimate / 60))} phút với {res.get('jobs', 1)} lần chạy song "
                f"song; chạy lại với --timeout {suggest}" + (f" (chạy nền; qua receipt.py thì `receipt.py run --timeout "
                f"{suggest + 300}`, không thì receipt giết mutation.py sau 1800 giây và mutmut chạy tiếp không ai dừng)"
                if suggest > DEFAULT_TIMEOUT else ""))
    else:
        hint = "mutmut dừng trước khi chạy hết, không phải vì quá giờ (xem lỗi ở trên)"
    spans = res.get("unreached") or []
    if not (res.get("unreached_known", True) and spans):
        return [f"- chưa chạy tới: {res['untested']} đột biến, không lấy được vị trí (mutmut junitxml lỗi); {hint}"]
    spots = ", ".join(f"{r['file']}:{r['start']}" + (f"-{r['end']}" if r["end"] != r["start"] else "")
                      for r in spans[:MAX_RANGES])
    more = f" và {len(spans) - MAX_RANGES} khoảng khác" if len(spans) > MAX_RANGES else ""
    return [f"- chưa chạy tới: {spots}{more} ({res['untested']} đột biến); {hint}"]


def summary(res: dict) -> list:
    lines = [f"- {n}" for n in res.get("notes") or []]
    survived = res.get("survived") or []
    for s in survived[:MAX_LISTED]:
        first = next((ln for ln in s["diff"].splitlines() if ln.startswith("+") and not ln.startswith("+++")), "")
        lines.append(f"- sống: {s['file']}:{s['line']}" + (f"  {first.strip()[:120]}" if first else ""))
    if len(survived) > MAX_LISTED:
        lines.append(f"- và {len(survived) - MAX_LISTED} đột biến sống khác")
    lines += outside_lines(res) + unreached_lines(res)
    where = ", ".join(f"{s['file']}:{s['line']}" for s in survived[:MAX_LISTED])
    counts = (f"{res['total']} đột biến trên dòng đổi, {res['killed']} bị bắt, {len(survived)} sống"
              + (f", {res['timeout']} quá giờ" if res.get("timeout") else "")
              + (f", {res['untested']} chưa chạy tới" if res.get("untested") else "")
              + (f", {res['jobs']} lần chạy song song" if res.get("jobs", 1) > 1 else ""))
    if res["status"] == "ran":
        lines.append(f"Mutation: {counts}" + (f" ({where})" if where else ""))
    elif res["status"] == "partial":
        lines.append(f"Mutation: chưa chạy xong: {res['reason']}; đã có {counts}" + (f" ({where})" if where else ""))
    else:
        lines.append(f"Mutation: chưa chạy: {res['reason']}")
    return lines


def cmd_setup() -> int:
    """Cài mutmut 2.5.1 vào `.venv-mutmut/` của agent-stack, đúng bộ gói đã vet (mã băm), không cài toàn cục."""
    home = stack_root()
    venv, req = home / ".venv-mutmut", home / "tools" / "mutmut-requirements.txt"
    build = home / "tools" / "mutmut-build-constraints.txt"
    uv = shutil.which("uv")
    if uv is None:
        print("[mutation] thiếu uv (cài qua install.sh của agent-stack)")
        return 2
    env = dict(os.environ, UV_CACHE_DIR=str(home / ".cache" / "uv"), UV_PYTHON_DOWNLOADS="never")
    steps = []
    if not (venv / "bin" / "python").exists():
        steps.append([uv, "venv", "--python", "3.11", "--python-preference", "only-system", str(venv)])
    steps.append([uv, "pip", "install", "--python", str(venv / "bin" / "python"), "--require-hashes", "-r", str(req),
                  "--build-constraints", str(build)])
    steps.append([str(venv / "bin" / "mutmut"), "version"])
    for step in steps:
        out = subprocess.run(step, cwd=str(home), env=env, capture_output=True, text=True)
        print((out.stdout + out.stderr).strip()[-800:])
        if out.returncode != 0:
            print(f"[mutation] lỗi ở bước: {' '.join(step[:3])} (mã {out.returncode})")
            return out.returncode
    print(f"[mutation] đã cài mutmut vào {venv}")
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["setup"]:
        return cmd_setup()
    as_json = "--json" in argv
    try:
        ap = Args(description="Mutation trên dòng vừa đổi (chỉ để báo, luôn thoát 0).")
        ap.add_argument("--project", default=".")
        ap.add_argument("--base", default="HEAD")
        ap.add_argument("--cmd", help="lệnh test cho mutmut --runner (mặc định: lệnh trong sổ khóa)")
        ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="giới hạn cả lần chạy, giây")
        ap.add_argument("--mutmut", help="đường dẫn mutmut (mặc định: .venv-mutmut của agent-stack)")
        ap.add_argument("--link", action="append", metavar="PATH", help="nối thư mục bị git bỏ qua, như .venv")
        ap.add_argument("--jobs", type=int, help="số lần chạy mutmut song song (mặc định: tự chọn theo cỡ diff)")
        ap.add_argument("--json", action="store_true")
        args = ap.parse_args(argv)
        if args.jobs is not None and args.jobs < 1:
            raise Skip(f"tham số sai (--jobs phải là số nguyên dương, nhận {args.jobs})")
        if IMPORT_ERROR is not None:
            raise Skip(f"không nạp được thư viện của agent-stack ({IMPORT_ERROR!r})"[:300])
        res = run(args)
    except Skip as exc:
        res: dict = {"status": "skipped", "reason": str(exc)}
    except Exception as exc:  # noqa: BLE001 (chỉ để báo: lỗi nào cũng không được làm trượt done-gate)
        res = {"status": "skipped", "reason": f"lỗi bất ngờ: {exc!r}"[:300]}
    for key, empty in (("total", 0), ("killed", 0), ("survived", []), ("timeout", 0), ("untested", 0),
                       ("outside", []), ("unreached", []), ("unreached_known", True), ("estimate_seconds", 0)):
        res.setdefault(key, empty)
    if as_json:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        print("\n".join(summary(res)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
