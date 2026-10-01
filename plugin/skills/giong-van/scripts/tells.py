#!/usr/bin/env python3
"""Dò các dấu hiệu văn AI trong một đoạn văn tiếng Việt hoặc tiếng Anh. Chỉ đọc, không sửa.

Mục đích là sửa văn cho hay hơn và đúng giọng người viết, không phải để qua mặt công cụ
phát hiện AI. Các công cụ đó không đáng tin; một số dấu hiệu dưới đây người thật cũng dùng.
Điểm số chỉ để so trước và sau khi sửa trên cùng một đoạn.

Lệnh:
  tells.py FILE.md           in danh sách dấu hiệu theo dòng và điểm trên 1.000 từ
  tells.py --json FILE.md
  echo "..." | tells.py -
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

# (mã, nhóm, trọng số, regex, gợi ý sửa). Regex chạy trên văn bản gốc, không phân biệt hoa thường.
PATTERNS = [
    ("vi-mo-bai-sao", "mở bài sáo", 3, r"^\s*(trong bối cảnh|trong thời đại|ngày nay,|trong thế giới[^.]{0,40}ngày nay|hãy cùng (khám phá|tìm hiểu))",
     "Vào thẳng ý chính hoặc một chi tiết cụ thể."),
    ("vi-khong-chi-ma-con", "cấu trúc khuôn mẫu", 2, r"không (chỉ|những)[^.]{1,80}mà còn",
     "Nói thẳng hai ý, hoặc chỉ giữ ý quan trọng hơn."),
    ("vi-thoi-phong", "thổi phồng", 2,
     r"đóng (một )?vai trò (vô cùng |cực kỳ |hết sức )?(quan trọng|then chốt|chủ chốt|thiết yếu)|không thể phủ nhận|vô cùng quan trọng|"
     r"mang lại (những )?(giá trị|lợi ích) (to lớn|vượt trội)|đa dạng và phong phú|nâng tầm|bước ngoặt|giải pháp toàn diện|"
     r"tối ưu hóa (tối đa|hiệu quả)|một cách (hiệu quả|toàn diện|sâu sắc|tối ưu)",
     "Thay bằng số liệu, ví dụ, hoặc bỏ đi."),
    ("vi-hanh-trinh", "ẩn dụ sáo", 2, r"\bhành trình\b|\bkhám phá\b|\bchìa khóa\b|\bngọn hải đăng\b|\bbức tranh toàn cảnh\b",
     "Gọi đúng tên sự việc."),
    ("vi-ket-sao", "kết bài sáo", 3, r"^\s*(tóm lại|nhìn chung|tổng kết lại|có thể nói|như vậy,? có thể thấy|nói tóm lại)\b",
     "Kết bằng điều người đọc nên làm hoặc nhớ, không nhắc lại cả bài."),
    ("vi-dieu-nay", "câu nối rỗng", 1, r"\b(điều này cho thấy|điều đáng chú ý là|đáng chú ý,|không những thế|hơn thế nữa)\b",
     "Bỏ câu nối, để ý tự nối với nhau."),
    ("vi-ben-canh-do", "câu nối rỗng", 1, r"(^|[.!?]\s+)(bên cạnh đó|ngoài ra|thêm vào đó|mặt khác),",
     "Dùng ít; nhiều đoạn liền nhau mở bằng các từ này là dấu hiệu rõ."),
    ("en-delve", "từ vựng AI", 2,
     r"\b(delve|tapestry|testament to|realm|pivotal|embark|unleash|unlock the|elevate|seamless(ly)?|vibrant|"
     r"navigat(e|ing) the (complexities|landscape)|in today's (fast-paced|digital)|ever-evolving|game-changer)\b",
     "Dùng từ thường ngày."),
    ("en-important-note", "câu nối rỗng", 1, r"\b(it'?s (important|worth) (to note|noting)|it is important to note|moreover|furthermore|additionally),",
     "Bỏ, hoặc nói luôn ý đó."),
    ("en-not-only", "cấu trúc khuôn mẫu", 2, r"\bnot (only|just)\b[^.]{1,80}\bbut (also)?\b", "Nói thẳng."),
    ("en-conclusion", "kết bài sáo", 3, r"^\s*(in conclusion|overall|in summary|to sum up|ultimately),", "Kết bằng ý mới hoặc hành động."),
]
COMPILED = [(code, group, weight, re.compile(rx, re.IGNORECASE | re.MULTILINE), fix) for code, group, weight, rx, fix in PATTERNS]
EMOJI = re.compile("[" + chr(0x1F300) + "-" + chr(0x1FAFF) + chr(0x2600) + "-" + chr(0x27BF) + "]")


def words(text: str) -> int:
    return len(re.findall(r"\w+", text))


def sentences(text: str) -> list:
    body = re.sub(r"```.*?```", " ", text, flags=re.S)
    parts = re.split(r"(?<=[.!?])\s+|\n{2,}", body)
    return [p for p in (s.strip() for s in parts) if words(p) >= 3]


def analyze(text: str) -> dict:
    hits = []
    for code, group, weight, rx, fix in COMPILED:
        for m in rx.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            hits.append({"code": code, "group": group, "weight": weight, "line": line,
                         "match": m.group(0).strip()[:60], "fix": fix})
    n_words = max(words(text), 1)
    dashes = text.count("—")
    bold = len(re.findall(r"\*\*[^*\n]+\*\*", text))
    emoji = len(EMOJI.findall(text))
    lengths = [words(s) for s in sentences(text)]
    cv = statistics.pstdev(lengths) / statistics.mean(lengths) if len(lengths) >= 8 else None
    extra = []
    if dashes * 1000 / n_words > 8:
        extra.append({"code": "gach-dai", "group": "dấu câu", "weight": 2, "line": 0,
                      "match": f"{dashes} dấu —", "fix": "Thay phần lớn dấu — bằng dấu phẩy, hai chấm hoặc tách câu."})
    if bold >= 4 and bold * 1000 / n_words > 10:
        extra.append({"code": "in-dam-thua", "group": "định dạng", "weight": 1, "line": 0,
                      "match": f"{bold} cụm in đậm", "fix": "Chỉ in đậm thứ người đọc phải thấy ngay."})
    if emoji:
        extra.append({"code": "emoji", "group": "định dạng", "weight": 1, "line": 0, "match": f"{emoji} emoji",
                      "fix": "Bỏ emoji trong văn bản trang trọng."})
    if cv is not None and cv < 0.3:
        extra.append({"code": "nhip-deu", "group": "nhịp câu", "weight": 2, "line": 0,
                      "match": f"độ dài câu gần như bằng nhau (hệ số biến thiên {cv:.2f})",
                      "fix": "Xen câu ngắn với câu dài; đôi khi một câu chỉ vài chữ."})
    hits += extra
    score = sum(h["weight"] for h in hits) * 1000 / n_words
    return {"words": n_words, "score_per_1000_words": round(score, 1), "hits": hits,
            "sentence_length_cv": round(cv, 2) if cv is not None else None}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Dò dấu hiệu văn AI (chỉ đọc).")
    ap.add_argument("path", help="file văn bản, hoặc - để đọc từ stdin")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    text = sys.stdin.read() if args.path == "-" else Path(args.path).read_text(encoding="utf-8")
    result = analyze(text)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    print(f"Điểm: {result['score_per_1000_words']} trên 1.000 từ ({result['words']} từ). Càng thấp càng ít dấu hiệu.")
    for h in sorted(result["hits"], key=lambda x: (x["line"], -x["weight"])):
        where = f"dòng {h['line']}" if h["line"] else "toàn bài"
        print(f"- [{h['group']}] {where}: “{h['match']}” → {h['fix']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
