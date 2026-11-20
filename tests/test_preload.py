"""`tools/preload.py` (H5, 20/11/2026): đo phần nạp sẵn bằng máy chủ API giả trên 127.0.0.1, cấu hình tạm.

Binary của app được thay bằng script giả: script gửi một request /v1/messages tới ANTHROPIC_BASE_URL, trong thân có
biến môi trường nó nhận được, và ghi đường dẫn cấu hình, cwd ra file để test kiểm thư mục tạm đã bị xóa."""
import json
import os
import sys
import textwrap
from pathlib import Path
from unittest import mock

from tests._util import REPO, TempDirTestCase

sys.path.insert(0, str(REPO / "tools"))
import preload  # noqa: E402

FAKE = textwrap.dedent("""\
    #!{python}
    import json, os, sys, urllib.request
    env = {{k: os.environ.get(k) for k in ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "SECRET_X",
                                           "CLAUDE_CONFIG_DIR", "NO_PROXY")}}
    open({trace!r}, "w").write(json.dumps({{"cfg": os.environ["CLAUDE_CONFIG_DIR"], "cwd": os.getcwd(),
                                           "argv": sys.argv[1:]}}))
    listing = "The following skills are available for use with the Skill tool:\\n\\n- a:b: mô tả một\\n- c: hai"
    body = {{"system": [{{"text": "hệ thống"}}], "tools": [{{"name": "Skill"}}],
             "messages": [{{"role": "user", "content": [{{"text": listing}}, {{"text": json.dumps(env)}}]}}]}}
    req = urllib.request.Request(os.environ["ANTHROPIC_BASE_URL"] + "/v1/messages?beta=true",
                                 data=json.dumps(body).encode(), method="POST")
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass
    """)


class PreloadTests(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.trace = self.tmp / "trace.json"
        self.fake = self.tmp / "claude"
        self.fake.write_text(FAKE.format(python=sys.executable, trace=str(self.trace)))
        self.fake.chmod(0o755)

    def run_preload(self, find=("mô tả",)):
        env = dict(os.environ, ANTHROPIC_API_KEY="sk-that", CLAUDE_CODE_OAUTH_TOKEN="oauth-that", SECRET_X="secret-x-123")
        with mock.patch.object(preload.claude_app, "find", return_value=("0", self.fake)), \
                mock.patch.dict(os.environ, env, clear=True):
            return preload.run([], find=find)

    def test_counts_skill_listing_from_the_captured_request(self):
        result = self.run_preload()
        self.assertEqual(set(result["skills"]), {"a:b", "c"})
        self.assertEqual(result["found"], {"mô tả": 1})
        self.assertGreater(result["total"], result["skills_total"])

    def test_real_keys_and_unlisted_env_never_reach_the_binary(self):
        secrets = ("sk-that", "oauth-that", "secret-x-123")
        found = self.run_preload(find=(*secrets, "sk-preload-dummy", "127.0.0.1"))["found"]
        self.assertEqual({s: found[s] for s in secrets}, dict.fromkeys(secrets, 0))
        self.assertEqual(found["sk-preload-dummy"], 1)  # binary chỉ thấy khóa giả
        self.assertGreaterEqual(found["127.0.0.1"], 1)  # NO_PROXY cho máy chủ giả
        self.assertEqual(json.loads(self.trace.read_text())["argv"], ["-p", "hi"])

    def test_temp_config_and_project_are_removed_and_repo_untouched(self):
        before = sorted(p.name for p in REPO.iterdir())
        self.run_preload()
        trace = json.loads(self.trace.read_text())
        self.assertFalse(Path(trace["cfg"]).exists())
        self.assertFalse(Path(trace["cwd"]).exists())
        self.assertFalse(Path(trace["cfg"]).resolve().is_relative_to(REPO))
        self.assertEqual(sorted(p.name for p in REPO.iterdir()), before)
