#!/usr/bin/env python3
"""Tìm thứ có sẵn trước khi tự làm: repo trên GitHub và bài nghiên cứu. Chỉ đọc, có gọi mạng.

Lệnh:
  scout.py github "từ khóa" [--limit 10] [--language python] [--sort both|best-match|stars|updated] [--json]
  scout.py papers "từ khóa" [--limit 10] [--since 2023] [--json]

Nguồn: GitHub qua `gh` (dùng phiên đăng nhập sẵn có) hoặc API công khai khi không có `gh`;
bài báo qua OpenAlex, dự phòng bằng Semantic Scholar rồi arXiv. Câu tìm được gửi tới các dịch vụ
này, nên chỉ dùng từ khóa chung, không đưa code hay thông tin riêng vào.

Mặc định GitHub được tìm hai lần (khớp nhất và nhiều sao nhất) rồi gộp lại, vì xếp theo độ khớp
hay bỏ sót công cụ nổi tiếng, còn xếp theo sao lại bỏ sót công cụ mới.

Mã thoát: 0 = chạy xong (kể cả khi không có kết quả), 3 = lỗi mạng hoặc công cụ.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

HEADERS = {"User-Agent": "agent-stack-scout/1", "Accept": "application/json"}
TIMEOUT = 15
MAX_BYTES = 5_000_000
GH_FIELDS = "fullName,description,stargazersCount,pushedAt,license,isArchived,url,language"
GITHUB_API = "https://api.github.com/search/repositories"
OPENALEX_API = "https://api.openalex.org/works"
OPENALEX_SELECT = "id,display_name,publication_year,cited_by_count,doi,primary_location,open_access,type"
S2_API = "https://api.semanticscholar.org/graph/v1/paper/search"
S2_FIELDS = "title,year,venue,citationCount,externalIds,url,openAccessPdf"
ARXIV_API = "https://export.arxiv.org/api/query"
ATOM = {"a": "http://www.w3.org/2005/Atom"}
FEW_STARS = 50
COPYLEFT = ("GPL", "AGPL", "LGPL", "MPL", "EUPL", "SSPL", "CC-BY-SA")
NONSTANDARD = ("OTHER", "NOASSERTION")


class ScoutError(Exception):
    pass


def fetch(url: str, opener=urllib.request.urlopen) -> bytes:
    request = urllib.request.Request(url, headers=HEADERS)
    try:
        with opener(request, timeout=TIMEOUT) as response:
            return response.read(MAX_BYTES)
    except Exception as exc:  # noqa: BLE001 (HTTPError, URLError, timeout: đều là lỗi mạng với người dùng)
        raise ScoutError(f"{url.split('?')[0]}: {exc}") from exc


def fetch_json(url: str, opener=urllib.request.urlopen):
    try:
        return json.loads(fetch(url, opener).decode("utf-8"))
    except ValueError as exc:
        raise ScoutError(f"{url.split('?')[0]}: trả về dữ liệu không đọc được") from exc


def age_days(iso, now=None):
    if not iso:
        return None
    try:
        when = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return ((now or datetime.now(timezone.utc)) - when).days


def clip(text, limit: int) -> str:
    text = " ".join(str(text or "").split()).replace("|", "\\|")
    return text if len(text) <= limit else text[:limit - 1] + "…"


# ---------------------------------------------------------------- GitHub

def normalize_gh(row: dict) -> dict:
    return {"name": row.get("fullName", ""), "url": row.get("url", ""), "description": row.get("description") or "",
            "stars": row.get("stargazersCount") or 0, "pushed_at": row.get("pushedAt"),
            "license": ((row.get("license") or {}).get("key") or "").upper(), "archived": bool(row.get("isArchived")),
            "language": row.get("language") or ""}


def normalize_rest(row: dict) -> dict:
    return {"name": row.get("full_name", ""), "url": row.get("html_url", ""), "description": row.get("description") or "",
            "stars": row.get("stargazers_count") or 0, "pushed_at": row.get("pushed_at"),
            "license": ((row.get("license") or {}).get("spdx_id") or "").upper(), "archived": bool(row.get("archived")),
            "language": row.get("language") or ""}


def repo_flags(repo: dict, now=None) -> list:
    """Những điểm cần xem kỹ trước khi dùng lại một repo."""
    flags = []
    if repo.get("archived"):
        flags.append("đã lưu trữ, không còn phát triển")
    lic = repo.get("license") or ""
    if not lic:
        flags.append("không có giấy phép: không được chép code")
    elif lic in NONSTANDARD:
        flags.append("giấy phép không chuẩn: đọc file LICENSE")
    elif lic.startswith(COPYLEFT):
        flags.append(f"copyleft ({lic}): xem điều kiện trước khi dùng")
    days = age_days(repo.get("pushed_at"), now)
    if days is not None and days > 365:
        flags.append(f"không cập nhật {days // 30} tháng")
    if (repo.get("stars") or 0) < FEW_STARS:
        flags.append("ít người dùng")
    return flags


def search_github(query: str, limit: int = 10, language: str = None, sort: str = "both",
                  runner=subprocess.run, opener=urllib.request.urlopen) -> tuple:
    """(danh sách repo xếp theo sao, nguồn). sort="both": gộp kết quả khớp nhất và nhiều sao nhất."""
    merged, source = {}, ""
    for mode in (("best-match", "stars") if sort == "both" else (sort,)):
        found, source = search_github_once(query, limit, language, mode, runner, opener)
        for repo in found:
            merged.setdefault(repo["name"], repo)
    return sorted(merged.values(), key=lambda r: -r["stars"])[:limit], source


def search_github_once(query: str, limit: int, language, sort: str, runner, opener) -> tuple:
    """Một lượt tìm. Ưu tiên `gh` vì đã đăng nhập sẵn và không bị giới hạn chặt như API công khai."""
    cmd = ["gh", "search", "repos", query, "--limit", str(limit), "--json", GH_FIELDS]
    if language:
        cmd += ["--language", language]
    if sort != "best-match":
        cmd += ["--sort", sort]
    try:
        out = runner(cmd, capture_output=True, text=True, timeout=30)
        if out.returncode == 0:
            return [normalize_gh(r) for r in json.loads(out.stdout or "[]")], "gh"
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    params = {"q": query + (f" language:{language}" if language else ""), "per_page": str(limit)}
    if sort != "best-match":
        params["sort"] = sort
    data = fetch_json(f"{GITHUB_API}?{urllib.parse.urlencode(params)}", opener)
    return [normalize_rest(r) for r in data.get("items") or []][:limit], "api.github.com"


# ---------------------------------------------------------------- bài báo

def normalize_s2(paper: dict) -> dict:
    ids = paper.get("externalIds") or {}
    if ids.get("ArXiv"):
        url = f"https://arxiv.org/abs/{ids['ArXiv']}"
    elif ids.get("DOI"):
        url = f"https://doi.org/{ids['DOI']}"
    else:
        url = paper.get("url") or ""
    preprint = bool(ids.get("ArXiv")) and not ids.get("DOI") and not paper.get("venue")
    return {"title": paper.get("title") or "", "year": paper.get("year"), "venue": paper.get("venue") or "",
            "citations": paper.get("citationCount"), "url": url, "pdf": (paper.get("openAccessPdf") or {}).get("url"),
            "type": "preprint" if preprint else ""}


def normalize_openalex(work: dict) -> dict:
    location = work.get("primary_location") or {}
    return {"title": work.get("display_name") or "", "year": work.get("publication_year"),
            "venue": (location.get("source") or {}).get("display_name") or "", "citations": work.get("cited_by_count"),
            "url": work.get("doi") or work.get("id") or "", "pdf": (work.get("open_access") or {}).get("oa_url"),
            "type": work.get("type") or ""}


def search_openalex(query: str, limit: int, since=None, opener=urllib.request.urlopen) -> list:
    params = {"search": query, "per-page": str(limit), "select": OPENALEX_SELECT}
    if since:
        params["filter"] = f"from_publication_date:{since}-01-01"
    data = fetch_json(f"{OPENALEX_API}?{urllib.parse.urlencode(params)}", opener)
    return [normalize_openalex(w) for w in data.get("results") or []]


def search_semantic_scholar(query: str, limit: int, since=None, opener=urllib.request.urlopen) -> list:
    params = {"query": query, "limit": str(limit), "fields": S2_FIELDS}
    if since:
        params["year"] = f"{since}-"
    data = fetch_json(f"{S2_API}?{urllib.parse.urlencode(params)}", opener)
    return [normalize_s2(p) for p in data.get("data") or []]


def search_arxiv(query: str, limit: int, since=None, opener=urllib.request.urlopen) -> list:
    terms = " AND ".join(f"all:{word}" for word in query.split())
    params = {"search_query": terms, "start": "0", "max_results": str(limit * 3 if since else limit),
              "sortBy": "relevance"}
    try:
        root = ET.fromstring(fetch(f"{ARXIV_API}?{urllib.parse.urlencode(params)}", opener))
    except ET.ParseError as exc:
        raise ScoutError(f"{ARXIV_API}: trả về dữ liệu không đọc được") from exc
    papers = []
    for entry in root.findall("a:entry", ATOM):
        published = entry.findtext("a:published", default="", namespaces=ATOM)
        year = int(published[:4]) if published[:4].isdigit() else None
        if since and year and year < since:
            continue
        url = entry.findtext("a:id", default="", namespaces=ATOM).strip()
        papers.append({"title": " ".join(entry.findtext("a:title", default="", namespaces=ATOM).split()),
                       "year": year, "venue": "arXiv", "citations": None, "url": url, "type": "preprint",
                       "pdf": url.replace("/abs/", "/pdf/") if "/abs/" in url else None})
    return papers[:limit]


PAPER_SOURCES = (("openalex.org", search_openalex), ("semanticscholar.org", search_semantic_scholar),
                 ("arxiv.org", search_arxiv))


def search_papers(query: str, limit: int = 10, since=None, opener=urllib.request.urlopen) -> tuple:
    """(danh sách bài, nguồn). Thử lần lượt các nguồn; nguồn trước lỗi hoặc bị giới hạn thì sang nguồn sau."""
    errors = []
    for name, search in PAPER_SOURCES:
        try:
            rows = search(query, limit, since, opener)
        except ScoutError as exc:
            errors.append(str(exc))
            continue
        return rows, name + (f" (nguồn trước bị lỗi: {errors[-1][:80]})" if errors else "")
    raise ScoutError("; ".join(errors))


def paper_flags(paper: dict) -> list:
    venue = (paper.get("venue") or "").lower()
    flags = []
    if "arxiv" in venue or paper.get("type") == "preprint":
        flags.append("preprint, có thể chưa bình duyệt")
    elif not venue:
        flags.append("không rõ nơi đăng")
    if not paper.get("pdf"):
        flags.append("không có bản đọc miễn phí")
    return flags


# ---------------------------------------------------------------- hiển thị

def render_repos(rows: list, query: str, source: str) -> str:
    lines = [f"GitHub, từ khóa “{query}” (nguồn: {source})", "",
             "| Repo | ★ | Cập nhật | Giấy phép | Cần xem | Mô tả |", "|---|---:|---|---|---|---|"]
    for r in rows:
        lines.append(f"| [{r['name']}]({r['url']}) | {r['stars']} | {(r['pushed_at'] or '')[:10] or '–'} | "
                     f"{r['license'] or '–'} | {'; '.join(repo_flags(r)) or '–'} | {clip(r['description'], 90)} |")
    if not rows:
        lines.append("Không có kết quả. Thử từ khóa tiếng Anh khác, hoặc bớt từ.")
    elif max(r["stars"] for r in rows) < FEW_STARS:
        lines += ["", "Các repo đều ít sao: thử từ khóa chung hơn, ví dụ `link checker` thay vì `markdown link checker`."]
    return "\n".join(lines)


def render_papers(rows: list, query: str, source: str) -> str:
    lines = [f"Bài nghiên cứu, từ khóa “{query}” (nguồn: {source})", "",
             "| Bài | Năm | Nơi đăng | Trích dẫn | Cần xem |", "|---|---:|---|---:|---|"]
    for p in rows:
        cites = "–" if p["citations"] is None else str(p["citations"])
        lines.append(f"| [{clip(p['title'], 100)}]({p['url']}) | {p['year'] or '–'} | {clip(p['venue'], 40) or '–'} | "
                     f"{cites} | {'; '.join(paper_flags(p)) or '–'} |")
    if not rows:
        lines.append("Không có kết quả. Thử từ khóa tiếng Anh khác, hoặc lùi mốc --since.")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Tìm repo và bài nghiên cứu có sẵn (chỉ đọc, có gọi mạng).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    gh = sub.add_parser("github", help="tìm repo trên GitHub")
    gh.add_argument("query")
    gh.add_argument("--limit", type=int, default=10)
    gh.add_argument("--language")
    gh.add_argument("--sort", choices=("both", "best-match", "stars", "updated"), default="both")
    gh.add_argument("--json", action="store_true")
    pp = sub.add_parser("papers", help="tìm bài nghiên cứu")
    pp.add_argument("query")
    pp.add_argument("--limit", type=int, default=10)
    pp.add_argument("--since", type=int, help="chỉ lấy bài từ năm này")
    pp.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "github":
            rows, source = search_github(args.query, args.limit, args.language, args.sort)
            for r in rows:
                r["flags"] = repo_flags(r)
            text = render_repos(rows, args.query, source)
        else:
            rows, source = search_papers(args.query, args.limit, args.since)
            for p in rows:
                p["flags"] = paper_flags(p)
            text = render_papers(rows, args.query, source)
    except ScoutError as exc:
        print(f"Không tìm được: {exc}", file=sys.stderr)
        return 3
    print(json.dumps({"source": source, "results": rows}, ensure_ascii=False, indent=2) if args.json else text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
