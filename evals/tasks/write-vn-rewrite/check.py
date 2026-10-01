import sys
from pathlib import Path

TELLS_DIR = Path(__file__).resolve().parents[3] / "plugin" / "skills" / "giong-van" / "scripts"
sys.path.insert(0, str(TELLS_DIR))
import tells  # noqa: E402

FACTS = ["4", "6 tuần", "18 phút", "7 phút", "dependency"]


def check(workdir, answer):
    workdir = Path(workdir)
    target = workdir / "rewrite.md"
    if not target.exists():
        return False, "chưa có rewrite.md"
    text = target.read_text(encoding="utf-8")
    missing = [f for f in FACTS if f.lower() not in text.lower()]
    if missing:
        return False, "thiếu sự kiện: " + ", ".join(missing)
    before = tells.analyze((workdir / "draft.md").read_text(encoding="utf-8"))["score_per_1000_words"]
    after = tells.analyze(text)["score_per_1000_words"]
    if after > before * 0.4:
        return False, f"còn nhiều dấu hiệu văn AI: {before} → {after}"
    if "mình" not in text.lower():
        return False, "chưa đúng giọng xưng 'mình'"
    return True, f"đạt ({before} → {after})"
