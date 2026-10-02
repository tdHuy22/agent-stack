"""Skill reuse-best: script tìm repo và bài nghiên cứu. Không gọi mạng thật: mọi lệnh và HTTP đều được giả lập."""
import contextlib
import io
import json
import subprocess
import sys
import unittest
import urllib.error
from datetime import datetime, timezone
from unittest import mock

from tests._util import PLUGIN

SCOUT = PLUGIN / "skills" / "reuse-best" / "scripts" / "scout.py"
sys.path.insert(0, str(SCOUT.parent))
import scout  # noqa: E402

NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)
GH_ROWS = [
    {"fullName": "good/tool", "description": "Fast | link checker", "stargazersCount": 3968, "pushedAt": "2026-09-28T10:00:00Z",
     "license": {"key": "apache-2.0"}, "isArchived": False, "url": "https://github.com/good/tool", "language": "Rust"},
    {"fullName": "old/gpl", "description": "Old checker", "stargazersCount": 12, "pushedAt": "2021-01-01T00:00:00Z",
     "license": {"key": "gpl-3.0"}, "isArchived": False, "url": "https://github.com/old/gpl", "language": "Python"},
    {"fullName": "dead/nolicense", "description": "", "stargazersCount": 900, "pushedAt": "2026-05-01T00:00:00Z",
     "license": None, "isArchived": True, "url": "https://github.com/dead/nolicense", "language": None},
]


class FakeResponse:
    def __init__(self, body):
        self.body = body.encode("utf-8") if isinstance(body, str) else body

    def read(self, limit=-1):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def opener_for(routes, seen=None):
    """routes: {tiền tố URL: nội dung trả về hoặc Exception}."""
    def opener(request, timeout=None):
        url = request.full_url
        if seen is not None:
            seen.append(url)
        for prefix, body in routes.items():
            if url.startswith(prefix):
                if isinstance(body, Exception):
                    raise body
                return FakeResponse(body)
        raise urllib.error.URLError("không có route giả cho " + url)
    return opener


def gh_runner(rows_by_sort, calls=None):
    def runner(cmd, **kwargs):
        if calls is not None:
            calls.append(cmd)
        sort = cmd[cmd.index("--sort") + 1] if "--sort" in cmd else "best-match"
        return subprocess.CompletedProcess(cmd, 0, json.dumps(rows_by_sort.get(sort, [])), "")
    return runner


class GitHubSearch(unittest.TestCase):
    def test_merges_best_match_and_stars_then_sorts_by_stars(self):
        calls = []
        runner = gh_runner({"best-match": GH_ROWS[1:], "stars": GH_ROWS[:2]}, calls)
        rows, source = scout.search_github("link checker", limit=5, runner=runner)
        self.assertEqual(source, "gh")
        self.assertEqual([r["name"] for r in rows], ["good/tool", "dead/nolicense", "old/gpl"])
        self.assertEqual(len(calls), 2)
        self.assertIn("--json", calls[0])

    def test_flags_show_what_to_check(self):
        rows = [scout.normalize_gh(r) for r in GH_ROWS]
        self.assertEqual(scout.repo_flags(rows[0], NOW), [])
        old = " | ".join(scout.repo_flags(rows[1], NOW))
        self.assertIn("copyleft (GPL-3.0)", old)
        self.assertIn("không cập nhật", old)
        self.assertIn("ít người dùng", old)
        dead = " | ".join(scout.repo_flags(rows[2], NOW))
        self.assertIn("đã lưu trữ", dead)
        self.assertIn("không có giấy phép", dead)
        self.assertIn("giấy phép không chuẩn", " ".join(scout.repo_flags(dict(rows[0], license="NOASSERTION"), NOW)))

    def test_falls_back_to_public_api_without_gh(self):
        def no_gh(cmd, **kwargs):
            raise FileNotFoundError("gh")
        api = {"items": [{"full_name": "a/b", "html_url": "https://github.com/a/b", "description": "x",
                          "stargazers_count": 70, "pushed_at": "2026-09-01T00:00:00Z",
                          "license": {"spdx_id": "MIT"}, "archived": False, "language": "Go"}]}
        seen = []
        rows, source = scout.search_github("link checker", limit=3, language="go", sort="stars", runner=no_gh,
                                           opener=opener_for({scout.GITHUB_API: json.dumps(api)}, seen))
        self.assertEqual(source, "api.github.com")
        self.assertEqual(rows[0]["license"], "MIT")
        self.assertIn("language%3Ago", seen[0])
        self.assertIn("sort=stars", seen[0])

    def test_markdown_table_escapes_pipes_and_hints_better_keywords(self):
        rows = [scout.normalize_gh(GH_ROWS[1])]
        text = scout.render_repos(rows, "markdown link checker", "gh")
        self.assertIn("thử từ khóa chung hơn", text)
        self.assertIn("Fast \\| link checker", scout.render_repos([scout.normalize_gh(GH_ROWS[0])], "q", "gh"))


ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><id>http://arxiv.org/abs/2401.00001v1</id><published>2024-01-02T00:00:00Z</published>
    <title>New   method
      for logs</title></entry>
  <entry><id>http://arxiv.org/abs/1901.00002v1</id><published>2019-01-02T00:00:00Z</published>
    <title>Old method</title></entry>
</feed>"""
OPENALEX = {"results": [
    {"id": "https://openalex.org/W1", "display_name": "LogFiT", "publication_year": 2024, "cited_by_count": 96,
     "doi": "https://doi.org/10.1109/x", "primary_location": {"source": {"display_name": "IEEE TNSM"}},
     "open_access": {"oa_url": "https://example.org/a.pdf"}, "type": "article"},
    {"id": "https://openalex.org/W2", "display_name": "A preprint", "publication_year": 2025, "cited_by_count": 3,
     "doi": None, "primary_location": {"source": {"display_name": "arXiv (Cornell University)"}},
     "open_access": {"oa_url": None}, "type": "preprint"},
]}
S2 = {"data": [{"title": "S2 paper", "year": 2024, "venue": "", "citationCount": 10,
                "externalIds": {"ArXiv": "2402.12345"}, "url": "https://www.semanticscholar.org/p/1",
                "openAccessPdf": None}]}


class PaperSearch(unittest.TestCase):
    def test_openalex_first_with_year_filter(self):
        seen = []
        rows, source = scout.search_papers("log anomaly detection", limit=5, since=2023,
                                           opener=opener_for({scout.OPENALEX_API: json.dumps(OPENALEX)}, seen))
        self.assertEqual(source, "openalex.org")
        self.assertIn("from_publication_date%3A2023-01-01", seen[0])
        self.assertEqual(rows[0]["url"], "https://doi.org/10.1109/x")
        self.assertEqual(scout.paper_flags(rows[0]), [])
        self.assertIn("preprint", " ".join(scout.paper_flags(rows[1])))

    def test_falls_back_to_semantic_scholar_then_arxiv(self):
        limited = urllib.error.HTTPError(scout.OPENALEX_API, 429, "Too Many Requests", {}, None)
        rows, source = scout.search_papers("logs", limit=5, opener=opener_for({
            scout.OPENALEX_API: limited, scout.S2_API: json.dumps(S2)}))
        self.assertTrue(source.startswith("semanticscholar.org"))
        self.assertEqual(rows[0]["url"], "https://arxiv.org/abs/2402.12345")
        self.assertIn("preprint", " ".join(scout.paper_flags(rows[0])))
        rows, source = scout.search_papers("logs", limit=5, since=2023, opener=opener_for({
            scout.OPENALEX_API: limited, scout.S2_API: limited, scout.ARXIV_API: ARXIV_XML}))
        self.assertTrue(source.startswith("arxiv.org"))
        self.assertEqual([(r["title"], r["year"]) for r in rows], [("New method for logs", 2024)])
        self.assertEqual(rows[0]["pdf"], "http://arxiv.org/pdf/2401.00001v1")

    def test_arxiv_query_requires_every_word(self):
        seen = []
        scout.search_arxiv("log anomaly", 3, opener=opener_for({scout.ARXIV_API: ARXIV_XML}, seen))
        self.assertIn("all%3Alog+AND+all%3Aanomaly", seen[0])

    def test_unknown_venue_is_not_called_preprint(self):
        flags = scout.paper_flags({"venue": "", "type": "article", "pdf": "x"})
        self.assertEqual(flags, ["không rõ nơi đăng"])


class Cli(unittest.TestCase):
    def test_all_sources_down_exits_3_with_reason(self):
        down = urllib.error.URLError("mất mạng")
        with mock.patch.object(scout, "search_papers", side_effect=scout.ScoutError("mất mạng")), \
                contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(scout.main(["papers", "logs"]), 3)
        self.assertIn("mất mạng", err.getvalue())
        with self.assertRaises(scout.ScoutError):
            scout.search_papers("logs", opener=opener_for({scout.OPENALEX_API: down, scout.S2_API: down,
                                                          scout.ARXIV_API: down}))

    def test_json_output_includes_flags(self):
        rows = [scout.normalize_gh(GH_ROWS[2])]
        with mock.patch.object(scout, "search_github", return_value=(rows, "gh")), \
                contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(scout.main(["github", "x", "--json"]), 0)
        data = json.loads(out.getvalue())
        self.assertEqual(data["source"], "gh")
        self.assertIn("đã lưu trữ, không còn phát triển", data["results"][0]["flags"])

    def test_age_days_handles_github_timestamps(self):
        self.assertEqual(scout.age_days("2026-09-30T00:00:00Z", NOW), 2)
        self.assertIsNone(scout.age_days("không phải ngày", NOW))


if __name__ == "__main__":
    unittest.main()
