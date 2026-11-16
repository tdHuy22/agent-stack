#!/usr/bin/env python3
"""Spec theo lát (GĐ6): kiểm file spec, dựng trang duyệt, xem trạng thái.

File spec `.agent/spec/<slug>.txt`: mỗi dòng `Sn: Khi|Nếu|Trong khi … thì …`, chỉ ghi thêm ở cuối. Test gắn với dòng
bằng dấu `spec:<slug>#Sn` trong chính test, rồi được khóa (`receipt.py lock --red`).

Lệnh:
  spec.py check [--project DIR] [SLUG|FILE ...]
      Kiểm mẫu dòng, số thứ tự (S1), mỗi dòng có test mang dấu và test đó đã khóa (S2). Mặc định: mọi file spec.
      Mã 0: đạt; 1: có chỗ sai (in `<file>:<dòng>: …`); 2: đầu vào sai (không phải git repo, không có file spec).
  spec.py page SLUG [--project DIR]
      Dựng trang duyệt `.agent/trang/<slug>-spec.html` (trang công cụ của reader-page): người dùng đánh dấu từng dòng
      rồi chép câu "duyệt spec <mã>" về chat; hook prompt_submit ghi bản duyệt (S5). In đường dẫn trang ở dòng cuối.
  spec.py status [--project DIR]
      Mỗi file spec một dòng: số dòng, số dòng có test khóa, số dòng đã duyệt.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3] / "lib"))
import specbook as SB  # noqa: E402
import testlock as TL  # noqa: E402

CODE_LEN = 12  # trang hiện 12 ký tự mã (hook nhận từ 8): khó giả hơn nhiều so với 8 (TM-131)


def resolve_targets(top: Path, project: Path, names) -> list | None:
    """File spec cần xét; None khi có tên không hợp lệ hay không tồn tại."""
    if not names:
        return SB.spec_files(top)
    folder = (top / SB.SPEC_DIR).resolve()
    out = []
    for name in names:
        if name.endswith(".txt") or "/" in name:
            path = (project / name).resolve() if not Path(name).is_absolute() else Path(name).resolve()
            if not path.is_file() or path.parent != folder:
                return None
        else:
            if not SB.SLUG_RE.match(name) or not (top / SB.SPEC_DIR / f"{name}.txt").is_file():
                return None
            path = (top / SB.SPEC_DIR / f"{name}.txt").resolve()
        out.append(path)
    return out


def describe(top: Path, path: Path, book: dict, approved: dict):
    """(phân tích, dấu test, các dòng lỗi) của một file spec."""
    rel = path.relative_to(top.resolve()).as_posix() if path.is_absolute() else path.as_posix()
    slug = path.stem
    parsed = SB.parse(path.read_text(encoding="utf-8", errors="replace"))
    marks = SB.markers(top, slug)
    findings = [f"{rel}:{e['lineno']}: {e['msg']}" for e in parsed["errors"]]
    for line in parsed["lines"]:
        sid, files = line["id"], marks.get(line["id"], [])
        if not files:
            findings.append(f"{rel}:{line['lineno']}: {sid} chưa có test nào mang dấu `spec:{slug}#{sid}`")
        for f in files:
            if f not in book["files"]:
                findings.append(f"{rel}:{line['lineno']}: {sid}: {f} mang dấu nhưng chưa khóa "
                                "(`receipt.py lock --red` trước khi viết code)")
    return rel, parsed, marks, findings


def counts(parsed: dict, marks: dict, book: dict, approved: dict) -> str:
    lines = parsed["lines"]
    tested = sum(1 for x in lines if marks.get(x["id"]) and all(f in book["files"] for f in marks[x["id"]]))
    seen = [approved.get(SB.line_hash(x["id"], x["text"]), set()) for x in lines]
    by_user = sum(1 for s in seen if "duyet-spec" in s)
    by_plan = sum(1 for s in seen if s and "duyet-spec" not in s)
    return (f"{len(lines)} dòng, {tested} có test khóa, {by_user + by_plan} đã duyệt "
            f"(duyệt spec: {by_user}, kế hoạch: {by_plan})" + (f", {len(parsed['errors'])} dòng sai mẫu"
                                                              if parsed["errors"] else ""))


def cmd_check(top: Path, project: Path, names) -> int:
    targets = resolve_targets(top, project, names)
    if targets is None:
        print("[spec] không thấy file spec đã nêu (slug hay đường dẫn trong .agent/spec/)")
        return 2
    if not targets:
        print(f"[spec] chưa có file spec nào trong {SB.SPEC_DIR}/")
        return 2
    book, approved = TL.load(top), SB.approved(top)
    if book.get("broken"):
        print(f"[spec] sổ khóa {TL.LOCK_REL} hỏng: coi như chưa test nào khóa")
    bad = 0
    for path in targets:
        rel, parsed, marks, findings = describe(top, path, book, approved)
        for f in findings:
            print(f)
        bad += len(findings)
        print(f"[spec] {rel}: {counts(parsed, marks, book, approved)}")
    print(f"[spec] {'✗ ' + str(bad) + ' chỗ cần sửa' if bad else '✓ đạt'}")
    return 1 if bad else 0


def cmd_status(top: Path) -> int:
    book, approved = TL.load(top), SB.approved(top)
    files = SB.spec_files(top)
    if not files:
        print(f"Chưa có file spec nào trong {SB.SPEC_DIR}/.")
        return 0
    for path in files:
        rel, parsed, marks, _ = describe(top, path.resolve(), book, approved)
        print(f"- {path.stem} ({rel}): {counts(parsed, marks, book, approved)}")
    return 0


STYLE = """
:root { --bg:#f5f6f3; --panel:#fff; --fg:#1f2421; --muted:#5c665f; --line:#d8ddd6; --accent:#2f6a52;
  --ok:#2f6a52; --ok-soft:#e1eee7; --warn:#8a5a12; --warn-soft:#f8edd8; --code-bg:#eceee9; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#151916; --panel:#1d221f; --fg:#e3e8e4;
  --muted:#9aa69e; --line:#313a34; --accent:#79c2a2; --ok:#79c2a2; --ok-soft:#203a2f; --warn:#e0b260;
  --warn-soft:#3a2f1a; --code-bg:#111512; color-scheme:dark } }
* { box-sizing:border-box }
body { background:var(--bg); color:var(--fg); font:16px/1.6 system-ui, "Segoe UI", sans-serif; margin:0;
  padding:24px max(16px, env(safe-area-inset-left, 0px)) 64px }
main { max-width:860px; margin:0 auto; display:grid; gap:28px }
h1, h2 { margin:0; line-height:1.25 }
code, pre { font-family:ui-monospace, Menlo, monospace; font-size:.92em; background:var(--code-bg); border-radius:4px;
  padding:1px 5px; overflow-wrap:anywhere }
pre { padding:10px; white-space:pre-wrap }
ol.lines { list-style:none; padding:0; margin:0; display:grid; gap:12px }
ol.lines li { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:12px 14px;
  display:grid; gap:6px }
ol.lines label { display:flex; gap:10px; align-items:flex-start; cursor:pointer }
ol.lines input[type=checkbox] { margin-top:5px; width:18px; height:18px; flex:none }
ol.lines label > code { flex:none; white-space:nowrap }
samp.dong { font-family:inherit; font-size:1em; overflow-wrap:anywhere }
.meta { color:var(--muted); font-size:.9em }
.ok { color:var(--ok) } .warn { color:var(--warn) }
textarea { width:100%; min-height:2.4em; font:inherit; border:1px solid var(--line); border-radius:6px; padding:6px;
  background:var(--bg); color:var(--fg) }
button { font:inherit; padding:10px 16px; border-radius:8px; border:0; background:var(--accent); color:var(--panel);
  cursor:pointer }
"""

SCRIPT = """
(function () {
  var code = document.body.getAttribute('data-ma');
  var slug = document.body.getAttribute('data-slug');
  var boxes = Array.prototype.slice.call(document.querySelectorAll('input[data-id]'));
  var out = document.getElementById('ket-qua');
  function build() {
    var notes = [];
    boxes.forEach(function (b) {
      var id = b.getAttribute('data-id');
      var note = document.querySelector('textarea[data-note="' + id + '"]').value.trim();
      if (!b.checked || note) { notes.push(id + ': ' + (note || 'chưa đồng ý')); }
    });
    if (!notes.length) { return 'duyệt spec ' + code; }
    return 'Chưa duyệt spec ' + slug + ' (mã ' + code + '). Cần sửa:\\n' + notes.join('\\n');
  }
  function show() { out.textContent = build(); }
  boxes.forEach(function (b) { b.addEventListener('change', show); });
  Array.prototype.forEach.call(document.querySelectorAll('textarea'), function (t) {
    t.addEventListener('input', show);
  });
  document.querySelector('[data-xuat]').addEventListener('click', function () {
    var text = build();
    out.textContent = text;
    try { navigator.clipboard.writeText(text); } catch (e) { /* không chép được thì chép tay từ khung */ }
  });
  show();
})();
"""


def page_html(slug: str, rel: str, code: str, parsed: dict, marks: dict, book: dict, approved: dict) -> str:
    """Trang công cụ (data-loai="cong-cu"): mọi chữ lấy từ spec đi qua html.escape (S10, TM-131); câu xuất chỉ gồm mã
    do script tính và ghi chú người dùng gõ, không chép chữ của spec."""
    e = html.escape
    items = []
    for line in parsed["lines"]:
        sid = line["id"]
        files = marks.get(sid, [])
        tests = ", ".join(f"<code>{e(f)}</code>" + ("" if f in book["files"] else " <span class=\"warn\">(chưa khóa)"
                                                    "</span>") for f in files) or "<span class=\"warn\">chưa có test</span>"
        src = approved.get(SB.line_hash(sid, line["text"]), set())
        state = ("<span class=\"ok\">đã duyệt bằng câu duyệt spec</span>" if "duyet-spec" in src else
                 "<span class=\"ok\">đã duyệt qua kế hoạch</span>" if src else "<span class=\"warn\">chưa duyệt</span>")
        items.append(
            f'<li><label><input type="checkbox" data-id="{e(sid)}"> <code>{e(sid)}</code> '
            f'<samp class="dong">{e(line["text"])}</samp></label>'
            f'<div class="meta">Test: {tests} · {state}</div>'
            f'<textarea data-note="{e(sid)}" aria-label="Góp ý cho dòng {e(sid)}" '
            f'placeholder="Góp ý nếu dòng này sai hay thiếu"></textarea></li>')
    errors = "".join(f"<li>dòng {x['lineno']}: <samp class=\"dong\">{e(x['msg'])}</samp></li>" for x in parsed["errors"])
    error_part = (f'<section><h2>Dòng sai mẫu</h2><p class="warn">Các dòng này không vào bản duyệt; sửa file spec '
                  f'rồi dựng lại trang.</p><ul>{errors}</ul></section>' if errors else "")
    return f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Duyệt spec</title>
<style>{STYLE}</style>
</head>
<body data-ma="{e(code)}" data-slug="{e(slug)}">
<main data-loai="cong-cu">
<header><h1>Duyệt spec <code>{e(slug)}</code></h1>
<p class="meta">File <code>{e(rel)}</code> · mã băm <code>{e(code)}</code> · {len(parsed["lines"])} dòng</p></header>
<section data-phan="tom-tat">
<p>Mỗi dòng dưới đây nói phần mềm phải làm gì trong một tình huống, dạng "khi … thì …". Test được viết từ chính các
dòng này trước khi có code, rồi bị khóa để người viết code không sửa được. Đọc từng dòng, đánh dấu dòng đúng, ghi góp
ý cho dòng sai. Đủ hết thì bấm nút và dán câu <code>duyệt spec {e(code)}</code> vào chat; còn góp ý thì nút chép danh
sách cần sửa.</p>
</section>
<section><h2>Các dòng</h2><ol class="lines">
{"".join(items)}
</ol></section>
{error_part}
<section><h2>Chép về chat</h2>
<p>Câu duyệt chỉ có tác dụng khi chính bạn gõ hay dán vào chat, và chỉ cho đúng nội dung file lúc dựng trang: sửa
file thì mã đổi, phải duyệt lại.</p>
<p><button type="button" data-xuat>Chép kết quả</button></p>
<pre id="ket-qua" aria-live="polite">duyệt spec {e(code)}</pre>
</section>
</main>
<script>{SCRIPT}</script>
</body>
</html>
"""


def cmd_page(top: Path, slug: str) -> int:
    path = top / SB.SPEC_DIR / f"{slug}.txt"
    if not SB.SLUG_RE.match(slug or "") or not path.is_file() or path.is_symlink():
        print(f"[spec] không thấy file spec {SB.SPEC_DIR}/{slug}.txt")
        return 2
    data = path.read_bytes()
    code = hashlib.sha256(data).hexdigest()[:CODE_LEN]
    parsed = SB.parse(data.decode("utf-8", "replace"))
    book, approved = TL.load(top), SB.approved(top)
    rel = f"{SB.SPEC_DIR}/{slug}.txt"
    page = top / ".agent" / "trang" / f"{slug}-spec.html"
    # Không ghi xuyên symlink (repo lạ có thể để sẵn `.agent/trang/<slug>-spec.html` trỏ ra ngoài), như TM-109.
    for part in (top / ".agent", page.parent, page):
        if part.is_symlink():
            print(f"[spec] không dựng trang: {part.relative_to(top)} là symlink")
            return 2
    page.parent.mkdir(parents=True, exist_ok=True)
    if not page.parent.resolve().is_relative_to(top):
        print("[spec] không dựng trang: thư mục trang nằm ngoài repo")
        return 2
    body = page_html(slug, rel, code, parsed, SB.markers(top, slug), book, approved)
    fd, tmp = tempfile.mkstemp(dir=str(page.parent), prefix=".spec-page.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body)
        os.replace(tmp, page)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    print(f"[spec] trang duyệt: mã {code}; người dùng dán `duyệt spec {code}` vào chat để duyệt")
    print(str(page))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Spec theo lát: kiểm, dựng trang duyệt, xem trạng thái.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    check = sub.add_parser("check", help="kiểm mẫu dòng, dấu test và khóa")
    check.add_argument("names", nargs="*", metavar="SLUG|FILE")
    check.add_argument("--project", default=".")
    page = sub.add_parser("page", help="dựng trang duyệt spec")
    page.add_argument("slug")
    page.add_argument("--project", default=".")
    status = sub.add_parser("status", help="trạng thái các file spec")
    status.add_argument("--project", default=".")
    args = ap.parse_args(argv)
    project = Path(args.project).expanduser().resolve()
    top = SB.git_top(project)
    if top is None:
        print("[spec] cần git repo (dấu test tìm theo file git theo dõi, sổ khóa ở gốc repo)")
        return 2
    top = top.resolve()
    if args.cmd == "check":
        return cmd_check(top, project, args.names)
    if args.cmd == "page":
        return cmd_page(top, args.slug)
    return cmd_status(top)


if __name__ == "__main__":
    sys.exit(main())
