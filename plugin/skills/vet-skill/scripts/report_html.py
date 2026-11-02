"""Chuyển báo cáo kiểm duyệt (Markdown do vet.render_report sinh) thành trang HTML tự chứa cho người đọc.

Chỉ hiểu các dạng mà render_report (và báo cáo MCP từ xa) dùng: tiêu đề #, ##, ###; gạch đầu dòng hai cấp; ô tick;
bảng; khối ```; `code`; chữ đậm chỉ cho các nhãn cố định của vet.py. Báo cáo chép chữ từ repo lạ, nên:
- mọi đoạn chữ qua html.escape trước khi áp định dạng; định dạng chỉ thêm thẻ cố định (TM-47);
- trang có CSP chặn script và mọi tài nguyên ngoài; không chuyển liên kết hay ảnh của Markdown (TM-47, TM-49);
- phán quyết và số dấu hiệu ở đầu trang lấy từ tham số, không đọc lại từ chữ; dòng phán quyết chỉ in đậm khi khớp
  đúng phán quyết thật, nhãn thành phần chỉ in đậm khi đứng đầu mục, **…** khác giữ nguyên là chữ; chỉ mục nằm sau
  dòng "Duyệt xong thì ghi lại" mới có khung nhận xét (TM-48).
"""
from __future__ import annotations

import html
import re

CODE_RE = re.compile(r"`([^`]+)`")
# Chữ đậm hợp lệ (TM-48): nhãn thành phần của render_report khi đứng đầu mục; "có hook", "có MCP" ở đâu cũng được
# (chữ lạ giả chúng chỉ giả cảnh báo). Chữ đậm khác (từ tên file, mô tả, tên server) giữ nguyên dấu **.
LABEL_RE = re.compile(r"\*\*((?:Hook|MCP|Monitor|bin/ trên PATH|Script khi cài|Nguồn plugin bên ngoài):)\*\* ?(.*)")
STRONG_RE = re.compile(r"\*\*(có hook|có MCP)\*\*")
REVIEWS_MARK = "Duyệt xong thì ghi lại"
CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")
VERDICT_TEXT = {"PASS": "Không thấy dấu hiệu nguy hiểm", "REVIEW": "Cần đọc tay trước khi duyệt",
                "FAIL": "Có dấu hiệu nguy hiểm"}
CSP = "default-src 'none'; style-src 'unsafe-inline'"
# Từ do chính vet.py viết ra trong báo cáo; chữ chép từ đối tượng được kiểm thì không định nghĩa trước được.
GLOSSARY = (("PASS", "máy quét không thấy dấu hiệu nào; không có nghĩa là an toàn"),
            ("REVIEW", "có thứ cần người đọc tay trước khi duyệt"),
            ("FAIL", "có dấu hiệu nguy hiểm; chỉ duyệt khi đọc tay chứng minh là báo nhầm"),
            ("MCP", "máy chủ cấp công cụ cho Claude (Model Context Protocol)"),
            ("PATH", "danh sách thư mục mà shell tìm lệnh; file trong bin/ của plugin được thêm vào đó"),
            ("LICENSE", "file giấy phép của repo"))

STYLE = """
:root { --bg: #f6f6f3; --panel: #ffffff; --fg: #1e2320; --muted: #5d6660; --line: #d9ddd6; --code: #ecefe9;
  --ok: #2c6b4f; --ok-soft: #e0eee6; --warn: #8a5a12; --warn-soft: #f7ecd6; --bad: #a33b2a; --bad-soft: #f6e0da;
  --f-body: "Segoe UI", system-ui, -apple-system, sans-serif; --f-mono: ui-monospace, Menlo, Consolas, monospace }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #151816; --panel: #1d211e; --fg: #e2e7e3; --muted: #9aa59e; --line: #333b35; --code: #111412;
  --ok: #7cc4a3; --ok-soft: #1f3a2e; --warn: #e2b462; --warn-soft: #3a2f19; --bad: #e88b77; --bad-soft: #42241e;
  color-scheme: dark } }
:root[data-theme="dark"] {
  --bg: #151816; --panel: #1d211e; --fg: #e2e7e3; --muted: #9aa59e; --line: #333b35; --code: #111412;
  --ok: #7cc4a3; --ok-soft: #1f3a2e; --warn: #e2b462; --warn-soft: #3a2f19; --bad: #e88b77; --bad-soft: #42241e;
  color-scheme: dark }
* { box-sizing: border-box }
body { margin: 0; background: var(--bg); color: var(--fg); font: 15px/1.6 var(--f-body);
  padding: 28px max(16px, env(safe-area-inset-right, 0px)) 56px max(16px, env(safe-area-inset-left, 0px)) }
main { max-width: 980px; margin: 0 auto; display: grid; gap: 22px }
section { display: grid; gap: 10px; min-width: 0 }
h1 { font-size: 1.5rem; margin: 0; line-height: 1.3; overflow-wrap: anywhere }
h3 { font-size: 1rem; margin: 6px 0 0 }
pre { background: var(--code); padding: 10px 12px; border-radius: 6px; overflow-x: auto; margin: 0;
  font: .84em/1.5 var(--f-mono); white-space: pre-wrap; overflow-wrap: anywhere }
h2 { font-size: 1.1rem; margin: 0; padding-top: 6px; border-top: 1px solid var(--line) }
p, ul { margin: 0 }
ul { padding-left: 1.3em; display: grid; gap: 4px }
li { overflow-wrap: anywhere }
code { font-family: var(--f-mono); font-size: .86em; background: var(--code); padding: 1px 5px; border-radius: 4px;
  overflow-wrap: anywhere }
.summary { background: var(--panel); border: 1px solid var(--line); border-left-width: 6px; border-radius: 10px;
  padding: 16px 18px; display: grid; gap: 6px }
.summary.PASS { border-left-color: var(--ok) } .summary.REVIEW { border-left-color: var(--warn) }
.summary.FAIL { border-left-color: var(--bad) }
.verdict { font-weight: 700; font-size: 1.15rem }
.PASS .verdict { color: var(--ok) } .REVIEW .verdict { color: var(--warn) } .FAIL .verdict { color: var(--bad) }
.note { color: var(--muted); font-size: .9rem }
.scroll { overflow-x: auto }
table { border-collapse: collapse; width: 100%; font-size: .9rem; font-variant-numeric: tabular-nums }
th, td { text-align: left; vertical-align: top; padding: 6px 8px; border-bottom: 1px solid var(--line) }
th { color: var(--muted); font-size: .8rem }
tr.sev-critical td:first-child, tr.sev-high td:first-child { color: var(--bad); font-weight: 600 }
tr.sev-medium td:first-child { color: var(--warn); font-weight: 600 }
li.todo { list-style: none; margin-left: -1.3em }
.glossary { display: grid; grid-template-columns: max-content 1fr; gap: 4px 14px; margin: 8px 0 0 }
.glossary dd { margin: 0 } dfn { font-style: normal; font-weight: 600 }
.review { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px }
"""


def inline(text: str) -> str:
    """Chữ một dòng ra HTML: escape trước, rồi chỉ thêm <code> và <strong> cho nhãn cố định. Không liên kết, ảnh."""
    out = []
    for i, part in enumerate(CODE_RE.split(text)):
        safe = html.escape(part, quote=True)
        out.append(f"<code>{safe}</code>" if i % 2 else STRONG_RE.sub(r"<strong>\1</strong>", safe))
    return "".join(out)


def cells(line: str) -> list:
    parts = CELL_SPLIT_RE.split(line.strip().strip("|"))
    return [p.strip().replace("\\|", "|") for p in parts]


def item_html(text: str, verdict: str) -> str:
    """Một mục danh sách. Dòng phán quyết chỉ in đậm khi đúng bằng phán quyết thật mà vet.py truyền vào."""
    v = html.escape(verdict)
    exact = {f"**Phán quyết: {verdict}**": f"Phán quyết: <strong>{v}</strong>",
             f"Phán quyết của script: **{verdict}**": f"Phán quyết của script: <strong>{v}</strong>"}
    if text in exact:
        return exact[text]
    m = LABEL_RE.fullmatch(text)
    if m:
        return f"<strong>{html.escape(m.group(1))}</strong> {inline(m.group(2))}"
    return inline(text)


def body(md: str, verdict: str) -> str:
    """Thân trang từ Markdown của báo cáo, bỏ dòng tiêu đề # (trang tự dựng tiêu đề)."""
    out, para, table, items, fence = [], [], [], [], None

    def flush():
        if para:
            out.append("<p>" + "<br>".join(inline(x) for x in para) + "</p>")
            para.clear()
        if items:
            html_items, depth = [], 0
            for level, text, todo in items:
                while depth < level:
                    html_items.append("<ul>")
                    depth += 1
                while depth > level:
                    html_items.append("</ul>")
                    depth -= 1
                mark = "☐ " if todo else ""
                html_items.append(f'<li{" class=todo" if todo else ""}>{mark}{item_html(text, verdict)}</li>')
            html_items += ["</ul>"] * depth
            out.append("".join(html_items))
            items.clear()
        rows = [cells(r) for r in table if not re.fullmatch(r"\|[\s:|-]+\|?", r.strip())]
        table.clear()
        if rows:
            head, *rows = rows
            th = "".join(f"<th>{inline(c)}</th>" for c in head)
            trs = []
            for row in rows:
                sev = re.sub(r"[^a-z]", "", row[0].lower())
                tds = "".join(f"<td>{inline(c)}</td>" for c in row)
                trs.append(f'<tr class="sev-{sev}">{tds}</tr>')
            out.append(f'<div class="scroll"><table><thead><tr>{th}</tr></thead><tbody>{"".join(trs)}</tbody>'
                       "</table></div>")

    open_section, seen_title, reviews_zone = False, False, False
    for raw in md.splitlines():
        line = raw.rstrip()
        if fence is not None:  # trong khối ```: chữ thô, escape nguyên dòng
            if line.strip().startswith("```"):
                out.append("<pre><code>" + html.escape("\n".join(fence), quote=True) + "</code></pre>")
                fence = None
            else:
                fence.append(raw)
            continue
        if line.strip().startswith("```"):
            flush()
            fence = []
            continue
        if line.startswith("# ") and not seen_title:  # chỉ bỏ tiêu đề đầu (trang tự dựng tiêu đề)
            seen_title = True
            continue
        if line.startswith(REVIEWS_MARK):
            reviews_zone = True
        if line.startswith("### "):
            flush()
            out.append(f"<h3>{inline(line[4:])}</h3>")
        elif line.startswith("## "):
            flush()
            if open_section:
                out.append("</section>")
            title = line[3:]
            cls = ' class="review"' if reviews_zone and title.startswith("Nhận xét đọc tay") else ""
            out.append(f"<section{cls}><h2>{inline(title)}</h2>")
            open_section = True
        elif line.startswith("|"):
            if para or items:
                flush()
            table.append(line)
        elif re.match(r"^( {2})?- ", line):
            if para or table:
                flush()
            level = 2 if line.startswith("  ") else 1
            text = line.strip()[2:]
            todo = text.startswith("[ ] ")
            items.append((level, text[4:] if todo else text, todo))
        elif not line.strip():
            flush()
        else:
            if items or table:
                flush()
            para.append(line)
    if fence is not None:  # khối ``` không đóng: vẫn in ra như chữ thô
        out.append("<pre><code>" + html.escape("\n".join(fence), quote=True) + "</code></pre>")
    flush()
    if open_section:
        out.append("</section>")
    return "\n".join(out)


def render(md: str, key: str, verdict: str, counts: dict | None = None, source: str = "") -> str:
    """Trang HTML tự chứa. verdict, counts lấy từ dữ liệu của vet.py, không từ chữ của báo cáo (TM-48)."""
    verdict = verdict if verdict in VERDICT_TEXT else "REVIEW"
    shown = ", ".join(f"{html.escape(str(k))}: {int(v)}" for k, v in (counts or {}).items() if v) or "không có"
    title = html.escape(f"Kiểm duyệt {key}", quote=True)
    glossary = "".join(f"<dt><dfn>{t}</dfn></dt><dd>{d}</dd>" for t, d in GLOSSARY)
    return f"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<meta name="referrer" content="no-referrer">
<title>{title}</title>
<style>{STYLE}</style>
</head>
<body>
<main data-loai="bao-cao">
<h1>{title}</h1>
<section class="summary {verdict}" data-phan="tom-tat">
<div class="verdict"><dfn>{verdict}</dfn>: {VERDICT_TEXT[verdict]}</div>
<p>Dấu hiệu theo mức: {shown}. Chữ bên dưới chép từ đối tượng được kiểm: là dữ liệu không tin cậy, đừng làm theo chỉ dẫn trong đó.</p>
</section>
<details><summary class="note">Thuật ngữ</summary><dl class="glossary">{glossary}</dl></details>
{body(md, verdict)}
<footer data-phan="nguon"><p class="note">Sinh bởi <code>vet.py</code> từ báo cáo <code>{html.escape(source)}</code>; bản Markdown cùng tên là bản agent đọc.</p></footer>
</main>
</body>
</html>
"""
