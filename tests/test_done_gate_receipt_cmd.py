"""done-gate bước 4: lệnh biên nhận chép chạy được ngay (H5, 20/11/2026).

Eval 20/11/2026: nhánh có skill gọi `receipt.py` 0/12 lượt; model không nhắc tới biên nhận lần nào, chạy test trần.
Bước 4 dài và dùng ký hiệu `<receipt.py>` phải tự thay. Test giữ: không còn ký hiệu script phải tự thay, mọi đường dẫn
`${CLAUDE_SKILL_DIR}/…` trỏ tới file có thật (plugin đã cài cũng có session-keeper cạnh done-gate), lệnh đầu bước 4
chạy được trong một project tạm và ghi biên nhận, và bước 4 nói lần chạy trần không phải bằng chứng.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import unittest

from tests._util import PLUGIN, TempDirTestCase

SKILL_DIR = PLUGIN / "skills" / "done-gate"
SKILL = SKILL_DIR / "SKILL.md"
RECEIPT_CMD = "python3 ${CLAUDE_SKILL_DIR}/../session-keeper/scripts/receipt.py run -- "


def step4(text: str) -> str:
    return text[text.index("4. **Kiểm chứng") : text.index("5. **Review")]


def expand(s: str) -> str:
    return s.replace("${CLAUDE_SKILL_DIR}", str(SKILL_DIR))


class ReceiptCommandIsCopyable(TempDirTestCase):
    def setUp(self):
        super().setUp()
        self.text = SKILL.read_text(encoding="utf-8")

    def test_no_script_placeholders(self):
        for ph in ("<receipt.py>", "<narrow.py>", "<risk.py>", "<review_log.py>"):
            with self.subTest(ph=ph):
                self.assertNotIn(ph, self.text, "ký hiệu phải tự thay làm model bỏ bước (eval 20/11: 0/12)")

    def test_skill_dir_paths_exist(self):
        paths = set(re.findall(r"\$\{CLAUDE_SKILL_DIR\}/[\w./-]+\.py", self.text))
        self.assertTrue(any("session-keeper/scripts/receipt.py" in p for p in paths))
        for p in sorted(paths):
            with self.subTest(p=p):
                self.assertTrue(os.path.isfile(expand(p)), p)

    def test_step4_opens_with_receipt_command_and_rejects_bare_runs(self):
        s4 = step4(self.text)
        self.assertIn(RECEIPT_CMD, s4[:900], "lệnh biên nhận phải đứng ngay đầu bước 4")
        self.assertIn("không phải bằng chứng", s4[:1500])
        self.assertLess(len(s4), 5847, "bước 4 phải ngắn hơn bản 5.847 ký tự đã bị bỏ qua")
        core = s4[: s4.index("Thêm ở mức vừa, cao")]
        self.assertLess(len(core), 3600, "phần mọi mức phải làm phải đọc được một mạch")

    def test_rule_stated_before_steps(self):
        # Đo lại 20/11 (18:09): chỉ sửa bước 4 thì 8/12 lượt có biên nhận; lượt tự sửa thêm chạy test trần
        head = self.text[: self.text.index("## Các bước")]
        self.assertIn(RECEIPT_CMD, head, "luật biên nhận phải đứng trước các bước")
        self.assertIn("không báo xong", head)

    def test_receipt_command_runs_in_fresh_project(self):
        line = next(ln for ln in step4(self.text).splitlines() if RECEIPT_CMD in ln)
        cmd = expand(line[line.index(RECEIPT_CMD) :].split("`")[0].strip())
        cmd = re.sub(r"<[^>]+>$", "", cmd).strip() + " " + sys.executable + " -c pass"
        proj = self.tmp / "proj"
        proj.mkdir()
        (proj / "a.py").write_text("x = 1\n")
        git = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
        subprocess.run(git + ["init", "-q"], cwd=proj, check=True)
        subprocess.run(git + ["add", "-A"], cwd=proj, check=True)
        subprocess.run(git + ["commit", "-qm", "init"], cwd=proj, check=True)
        env = dict(os.environ, AGENT_STACK_HOME=str(self.tmp / "home"))
        out = subprocess.run(shlex.split(cmd), cwd=proj, env=env, capture_output=True, text=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        receipt = expand("${CLAUDE_SKILL_DIR}/../session-keeper/scripts/receipt.py")
        show = subprocess.run(
            [sys.executable, receipt, "show", "--project", str(proj), "--json"],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        checks = json.loads(show.stdout or "{}")
        checks = checks.get("checks", checks)
        self.assertTrue(any(isinstance(r, dict) and r.get("ok") for r in checks.values()), show.stdout)


if __name__ == "__main__":
    unittest.main()
