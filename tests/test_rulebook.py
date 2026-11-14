"""Sổ luật (`rulebook.json`, kiểm bằng `tools/rulebook.py`): mỗi luật khai loại kiểm và thứ đảm nhận có thật.

Test chống mất chữ (`test_global_rules.py`) chỉ biết câu chữ còn trong file; ở đây kiểm sổ trỏ tới test, hook, bài đo
có thật, và mỗi ca hỏng (luật không loại, trỏ tới test đã xóa, máy chặn mà chỉ có test câu chữ, gạch đầu dòng chưa vào
sổ) làm bộ kiểm báo lỗi.
"""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

from tests._util import REPO
from tests.test_global_rules import RULES

sys.path.insert(0, str(REPO / "tools"))
import rulebook as R  # noqa: E402

ANCHORS = R.legacy_anchors(RULES)


def book() -> dict:
    return json.loads((REPO / "rulebook.json").read_text(encoding="utf-8"))


def entry(b: dict, rid: str) -> dict:
    return next(r for r in b["rules"] if r["id"] == rid)


class RealRulebook(unittest.TestCase):
    def test_real_rulebook_has_no_problems(self):
        found = R.problems(book(), REPO, ANCHORS)
        self.assertEqual(found, [], "\n".join(found))

    def test_every_global_rule_id_is_in_the_book(self):
        ids = {r["id"] for r in book()["rules"]}
        missing = sorted(rid for rid, places in ANCHORS.items() if places and rid not in ids)
        self.assertEqual(missing, [])

    def test_repo_claude_md_rules_are_in_the_book(self):
        self.assertTrue(any(r.get("file") == "CLAUDE.md" for r in book()["rules"]))

    def test_all_five_check_types_are_known(self):
        self.assertEqual(set(R.TYPES), {"may-chan", "may-bao", "bo-viec", "model-review", "nguoi-duyet"})
        self.assertTrue({r["check"] for r in book()["rules"]} <= set(R.TYPES))


class BrokenRulebookIsCaught(unittest.TestCase):
    def problems_after(self, change) -> list:
        b = copy.deepcopy(book())
        change(b)
        return R.problems(b, REPO, ANCHORS)

    def first_machine_rule(self, b) -> dict:
        return next(r for r in b["rules"] if r["check"] in ("may-chan", "may-bao"))

    def test_rule_without_check_type(self):
        found = self.problems_after(lambda b: self.first_machine_rule(b).pop("check"))
        self.assertTrue(any("loại kiểm None" in p for p in found), found)

    def test_rule_with_unknown_check_type(self):
        found = self.problems_after(lambda b: self.first_machine_rule(b).update(check="co-test"))
        self.assertTrue(any("'co-test'" in p for p in found), found)

    def test_rule_pointing_to_missing_test_file(self):
        found = self.problems_after(lambda b: self.first_machine_rule(b)["by"].append(
            "test:tests/test_da_xoa.py::Lop.test_x"))
        self.assertTrue(any("không có file test tests/test_da_xoa.py" in p for p in found), found)

    def test_rule_pointing_to_missing_test_method(self):
        found = self.problems_after(lambda b: self.first_machine_rule(b)["by"].append(
            "test:tests/test_rulebook.py::RealRulebook.test_khong_co"))
        self.assertTrue(any("không có hàm test_khong_co" in p for p in found), found)

    def test_rule_pointing_to_missing_or_unregistered_hook(self):
        found = self.problems_after(lambda b: self.first_machine_rule(b)["by"].extend(
            ["hook:plugin/hooks/khong_co.py", "hook:plugin/hooks/ui_status.py"]))
        self.assertTrue(any("không có hook plugin/hooks/khong_co.py" in p for p in found), found)
        self.assertTrue(any("ui_status.py chưa đăng ký" in p for p in found), found)

    def test_rule_pointing_to_missing_eval(self):
        found = self.problems_after(lambda b: self.first_machine_rule(b)["by"].append("eval:evals/khong-co"))
        self.assertTrue(any("không có eval evals/khong-co" in p for p in found), found)

    def test_machine_rule_backed_only_by_text_test_is_not_checked(self):
        def change(b):
            self.first_machine_rule(b)["by"] = [
                "test:tests/test_global_rules.py::GlobalRulesStillHaveAHome.test_every_rule_keeps_its_strings"]
        found = self.problems_after(change)
        self.assertTrue(any("test chống mất chữ không tính là kiểm" in p for p in found), found)

    def test_measured_rule_needs_an_eval(self):
        def change(b):
            rule = self.first_machine_rule(b)
            rule.update(check="bo-viec", by=["hook:plugin/hooks/stop.py"])
        found = self.problems_after(change)
        self.assertTrue(any("đo bằng bộ việc cần ít nhất một tham chiếu eval" in p for p in found), found)

    def test_reference_outside_repo(self):
        found = self.problems_after(lambda b: self.first_machine_rule(b)["by"].append("file:../ngoai.txt"))
        self.assertTrue(any("ra ngoài repo" in p for p in found), found)

    def test_global_rule_dropped_from_book(self):
        found = self.problems_after(lambda b: b["rules"].remove(entry(b, "Q2a")))
        self.assertTrue(any("luật Q2a" in p and "chưa có mục" in p for p in found), found)

    def test_claude_md_bullet_without_rule(self):
        def change(b):
            b["rules"] = [r for r in b["rules"] if r.get("file") != "CLAUDE.md"]
        found = self.problems_after(change)
        self.assertTrue(any(p.startswith("CLAUDE.md: gạch đầu dòng chưa có luật") for p in found), found)

    def test_new_bullet_in_rule_file_needs_an_entry(self):
        fake = self.tmp_repo()
        with open(fake / "CLAUDE.md", "a", encoding="utf-8") as f:
            f.write("\n- Luật mới chưa vào sổ.\n")
        found = R.problems(book(), fake, ANCHORS)
        self.assertTrue(any("CLAUDE.md: gạch đầu dòng chưa có luật nào trong sổ: Luật mới chưa vào sổ." in p
                            for p in found), found)

    def tmp_repo(self):
        """Bản chép ba file luật và hooks.json vào thư mục tạm; tham chiếu test, hook trỏ về repo thật qua symlink."""
        import shutil
        import tempfile
        root = Path(tempfile.mkdtemp(dir=REPO / ".tmp" if (REPO / ".tmp").is_dir() else None))
        self.addCleanup(shutil.rmtree, root, True)
        for rel in R.RULE_FILES:
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO / rel, root / rel)
        for name in ("tests", "plugin", "evals", "tools"):
            (root / name).symlink_to(REPO / name)
        return root

    def test_duplicate_id(self):
        found = self.problems_after(lambda b: b["rules"].append(copy.deepcopy(b["rules"][0])))
        self.assertTrue(any("id trùng" in p for p in found), found)


if __name__ == "__main__":
    unittest.main()
