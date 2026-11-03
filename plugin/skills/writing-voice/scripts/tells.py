#!/usr/bin/env python3
"""Dò các dấu hiệu văn AI trong một đoạn văn tiếng Việt hoặc tiếng Anh. Chỉ đọc, không sửa.

Mục đích là sửa văn cho hay hơn và đúng giọng người viết, không phải để qua mặt công cụ
phát hiện AI. Các công cụ đó không đáng tin; một số dấu hiệu dưới đây người thật cũng dùng.
Điểm số chỉ để so trước và sau khi sửa trên cùng một đoạn, với cùng một bộ bài mẫu.

Script so từ vựng của bản nháp với bài mẫu cùng ngôn ngữ, theo cách đo "từ dùng nhiều bất thường"
của Kobak và cộng sự (2025):
  - từ hay gặp ở văn AI mà bài mẫu hiếm khi dùng (tính điểm)
  - xưng hô khác bài mẫu (tính điểm; chỉ khi bài mẫu là của người viết)
  - cụm lặp lại mà bài mẫu không có (không tính điểm, vì có thể chỉ là từ của chủ đề)

Bộ bài mẫu mặc định, theo thứ tự ưu tiên:
  1. .agent/giong-van/samples/ của project (tìm từ thư mục hiện tại đi lên, dừng ở gốc git)
  2. bài riêng của người viết trong samples/ của skill (không tính samples/kinh-dien/)
  3. samples/kinh-dien/vi hoặc en: 5 bài văn học kinh điển thuộc phạm vi công cộng, cùng ngôn ngữ với bản nháp
Văn kinh điển không phải giọng của người viết, nên với bộ này script không so cách xưng hô.

Lệnh:
  tells.py FILE.md                  in danh sách dấu hiệu theo dòng và điểm trên 1.000 từ
  tells.py --json FILE.md
  tells.py --samples DIR FILE.md    so với bài mẫu ở DIR (thư mục hoặc một file)
  tells.py --project DIR FILE.md    tìm bài mẫu của project từ DIR thay vì thư mục hiện tại
  tells.py --no-samples FILE.md     không so với bài mẫu
  echo "..." | tells.py -
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import unicodedata
from collections import Counter
from pathlib import Path

DEFAULT_SAMPLES = Path(__file__).resolve().parents[1] / "samples"
CLASSICS_DIR = "kinh-dien"
PROJECT_SAMPLES = Path(".agent") / "giong-van" / "samples"
SAMPLE_EXT = {".md", ".txt"}
MIN_SAMPLE_WORDS = 500
FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
KIND_LABEL = {"project": "bài mẫu của project", "own": "bài mẫu của bạn", "classic": "bài văn mẫu kinh điển",
              "path": "bài mẫu"}
CHATBOT_FIX = "Xóa: đây là lời chatbot nói với người dùng, bị dán sót vào văn bản."

# (mã, nhóm, trọng số, regex, gợi ý sửa). Regex chạy trên văn bản đã chuẩn hóa NFC, không phân biệt hoa thường.
# Nguồn của từng nhóm: xem mục "Nguồn" trong vi-ai-tells.md.
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
    ("vi-thach-thuc", "kết bài khuôn mẫu", 2,
     r"\b(mặc dù|dù|bất chấp) (vẫn )?(còn )?(tồn tại )?(nhiều|những|không ít|một số) (thách thức|khó khăn|hạn chế)|"
     r"(tương lai|triển vọng)[^.\n]{0,40}(đầy hứa hẹn|hứa hẹn|tươi sáng|rộng mở)|tiềm năng (to lớn|vô hạn|phát triển mạnh mẽ)",
     "Nói cụ thể khó khăn nào và bước tiếp theo là gì, hoặc bỏ đoạn này."),
    ("vi-dieu-nay", "câu nối rỗng", 1, r"\b(điều này cho thấy|điều đáng chú ý là|đáng chú ý,|không những thế|hơn thế nữa)\b",
     "Bỏ câu nối, để ý tự nối với nhau."),
    ("vi-ben-canh-do", "câu nối rỗng", 1, r"(^|[.!?]\s+)(bên cạnh đó|ngoài ra|thêm vào đó|mặt khác),",
     "Dùng ít; nhiều đoạn liền nhau mở bằng các từ này là dấu hiệu rõ."),
    # Bản tiếng Việt của mệnh đề đuôi ", highlighting…": dấu hiệu phân biệt mạnh nhất trong nghiên cứu PNAS 2025.
    ("vi-menh-de-duoi", "phân tích hời hợt", 1,
     r",\s*(góp phần|qua đó|từ đó|nhờ đó|thể hiện|khẳng định|phản ánh|minh chứng cho|mở ra|tạo nên|tạo tiền đề|"
     r"đặt nền móng|hứa hẹn)\b",
     "Tách thành câu riêng, nói rõ ai làm gì và bằng chứng nào; nếu chỉ là lời bình chung chung thì bỏ."),
    ("vi-ne-la", "né chữ \"là\"", 1,
     r"\b(đóng vai trò (là|như)|được (xem|coi) (là|như)|là minh chứng (cho|sống)|đánh dấu (một )?(bước tiến|cột mốc))",
     "Dùng \"là\" hoặc một động từ cụ thể: \"X là Y\", \"X giúp Y làm Z\"."),
    ("vi-sot-chatbot", "sót từ chatbot", 3,
     r"hy vọng (rằng )?(thông tin|bài viết|những chia sẻ|câu trả lời|nội dung|gợi ý) (này|trên) (sẽ )?(hữu ích|giúp ích)|"
     r"\bchắc chắn rồi[!.,]|^\s*(đây là )?(một )?câu hỏi (rất )?hay[!.]|"
     r"(nếu|khi) bạn cần (thêm|hỗ trợ|giúp)[^.\n]{0,50}(hãy|cứ) (cho (tôi|mình) biết|hỏi|nhắn)|"
     r"dưới đây là (phiên bản|bản) (đã )?(được )?(chỉnh sửa|viết lại|sửa)|"
     r"với tư cách (là )?(một )?(mô hình ngôn ngữ|trợ lý ảo|trợ lý AI)|"
     r"(theo|tính đến) (lần )?(cập nhật|dữ liệu) (kiến thức )?(cuối cùng|gần nhất) của (tôi|mình)",
     CHATBOT_FIX),
    ("en-delve", "từ vựng AI", 2,
     r"\b(delve|tapestry|testament to|realm|pivotal|embark|unleash|unlock the|elevate|seamless(ly)?|vibrant|"
     r"navigat(e|ing) the (complexities|landscape)|in today's (fast-paced|digital)|ever-evolving|game-changer)\b",
     "Dùng từ thường ngày."),
    ("en-important-note", "câu nối rỗng", 1, r"\b(it'?s (important|worth) (to note|noting)|it is important to note|moreover|furthermore|additionally),",
     "Bỏ, hoặc nói luôn ý đó."),
    ("en-not-only", "cấu trúc khuôn mẫu", 2, r"\bnot (only|just)\b[^.]{1,80}\bbut (also)?\b", "Nói thẳng."),
    ("en-conclusion", "kết bài sáo", 3, r"^\s*(in conclusion|overall|in summary|to sum up|ultimately),", "Kết bằng ý mới hoặc hành động."),
    ("en-ing-analysis", "phân tích hời hợt", 1,
     r",\s+(highlighting|underscoring|emphasizing|reflecting|showcasing|ensuring|fostering|cultivating|contributing to|"
     r"paving the way|solidifying|reinforcing|symbolizing)\b",
     "Tách thành câu riêng có chủ ngữ và bằng chứng, hoặc bỏ."),
    ("en-copula", "né chữ \"là\"", 1, r"\b(serves|stands) as (a|an|the)\b|\bboasts\b", "Dùng \"is\" hoặc \"has\"."),
    ("en-challenges", "kết bài khuôn mẫu", 2, r"\b(despite (these|its|the|such) challenges|future (outlook|prospects))\b",
     "Nói cụ thể khó khăn và bước tiếp theo, hoặc bỏ."),
    ("en-chatbot", "sót từ chatbot", 3,
     r"\b(i hope this helps|great question|i'?d be (happy|glad) to help|let me know if you('d| need| have| want)|"
     r"as of my (last|latest) (knowledge )?(update|training))\b|\bcertainly!|\bas an ai\b|"
     r"\bhere'?s (a|an|the|your) (revised|rewritten|polished|improved|updated) (version|draft)\b",
     CHATBOT_FIX),
    ("cho-trong", "sót từ chatbot", 3,
     r"\[(your [a-z ]{2,20}|tên( của)? (bạn|anh|chị|em|công ty|trường|người nhận)|insert [^\]\n]{1,30}|"
     r"chèn [^\]\n]{1,30}|company name|date|ngày( tháng)?)\](?!\()",
     "Điền thông tin thật hoặc xóa chỗ trống."),
    ("ma-trich-dan", "sót từ chatbot", 3,
     r"oaicite|oai_citation|contentReference\[|\bturn\d+(search|news|view|fetch)\d+|"
     r"utm_source=(chatgpt\.com|openai|copilot|perplexity)|\[cite:\s*\d+\]|grok_card|ppl-ai-file-upload|attributableIndex",
     "Xóa mã trích dẫn của chatbot; nếu cần nguồn, chèn đường dẫn thật."),
]
COMPILED = [(code, group, weight, re.compile(rx, re.IGNORECASE | re.MULTILINE), fix) for code, group, weight, rx, fix in PATTERNS]
EMOJI = re.compile("[" + chr(0x1F300) + "-" + chr(0x1FAFF) + chr(0x2600) + "-" + chr(0x27BF) + "]")

# "việc/sự + động từ" (danh từ hóa). Bỏ các từ ghép đã thành danh từ thường: công việc, sự kiện...
NOMINAL_SKIP_PREV = {"công", "làm", "mọi", "các", "những", "nhiều", "một", "có", "xong", "lo", "bận", "hết", "từng"}
NOMINAL_SKIP_NEXT = {
    "việc": {"làm", "nhà", "riêng", "công", "chung", "khác", "này", "đó", "ấy", "kia", "gì", "nào", "đầu", "lớn", "nhỏ", "cần"},
    "sự": {"kiện", "cố", "thật", "nghiệp", "việc", "vật", "sống", "tích", "vụ", "tình", "thể"},
}

# Từ hay gặp ở văn AI (theo Kobak 2025 cho tiếng Anh; danh sách tiếng Việt tổng hợp từ các bài phổ thông).
# Chỉ bị đánh dấu khi bài mẫu cho thấy người viết hiếm khi dùng. Không lặp lại từ đã có trong PATTERNS.
STYLE_LEXICON = (
    "toàn diện", "then chốt", "vượt trội", "tối ưu", "hiệu quả", "đáng kể", "sâu sắc", "mạnh mẽ", "linh hoạt", "bền vững",
    "đột phá", "tiềm năng", "đa dạng", "phong phú", "nâng cao", "thúc đẩy", "góp phần", "khẳng định", "nhấn mạnh",
    "minh chứng", "trải nghiệm", "giá trị", "đáng chú ý", "tuy nhiên", "bên cạnh đó", "ngoài ra", "hơn nữa", "đồng thời",
    "do đó", "vì vậy", "nhằm", "thông qua", "đối với", "thiết yếu", "cốt lõi", "hoàn hảo", "tuyệt vời", "ấn tượng",
    "độc đáo", "vô cùng", "cực kỳ", "không ngừng", "ngày càng", "khía cạnh", "lĩnh vực", "xu hướng", "liền mạch",
    "tinh tế", "chuyên nghiệp", "hài hòa", "quan trọng", "chiến lược", "giải pháp", "đảm bảo",
    "showcase", "showcasing", "underscore", "underscores", "crucial", "intricate", "comprehensive", "notably",
    "meticulous", "meticulously", "commendable", "enhance", "enhancing", "insights", "valuable", "robust", "leverage",
    "leveraging", "foster", "multifaceted", "nuanced", "landscape", "boast", "navigate", "holistic", "paramount",
    "invaluable", "transformative", "innovative", "streamline", "unparalleled", "noteworthy", "garnered", "groundbreaking",
)
LEXICON_RX = [(term, re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.IGNORECASE)) for term in STYLE_LEXICON]
RARE_PER_1000 = 1.0      # người viết dùng ít hơn mức này trong bài mẫu thì coi là "hiếm khi dùng"
OVERUSE_RATIO = 3.0      # và bản nháp dùng nhiều hơn ít nhất ngần này lần
FIRST_PERSON = {
    "tôi": re.compile(r"(?<!\w)(?<!chúng )tôi(?!\w)", re.IGNORECASE),
    "mình": re.compile(r"(?<!\w)(?<!một )(?<!chính )(?<!tự )mình(?!\w)", re.IGNORECASE),
}
VI_LETTERS = re.compile("[ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]", re.IGNORECASE)
SEGMENT_SPLIT = re.compile(r"[.,;:!?()\[\]{}\"“”‘’«»…\n—–/]+")
VI_STOP = set("và của là có được những các một cho với trong này đó không người khi để thì mà cũng đã sẽ rất từ như về ra "
              "vào lại nên nhưng hay hoặc bạn mình tôi em anh chị nó họ ta chúng ở tại theo đến tới đi làm bị do vì nếu thế "
              "nào gì ai đây kia ấy còn chỉ đều rồi nữa vẫn đang mới cùng sau trước trên dưới giữa qua bằng hơn nhất lúc "
              "nhiều ít mỗi mọi cả phải thể việc sự".split())
EN_STOP = set("the and for that this with from have were will would there their they them what when which while into also "
              "been being more most some such than then only very just like your about after before other these those "
              "because could should does done each many much over under here where both same even make made said says "
              "can our are was not but you all any how why who its it's".split())


def words(text: str) -> int:
    return len(re.findall(r"\w+", text))


def sentences(text: str) -> list:
    body = re.sub(r"```.*?```", " ", text, flags=re.S)
    parts = re.split(r"(?<=[.!?])\s+|\n{2,}", body)
    return [p for p in (s.strip() for s in parts) if words(p) >= 3]


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def is_vietnamese(text: str) -> bool:
    toks = re.findall(r"\w+", text)
    return bool(toks) and sum(1 for t in toks if VI_LETTERS.search(t)) / len(toks) >= 0.2


def nominal_count(text: str) -> int:
    toks = re.findall(r"\w+", text.lower())
    count = 0
    for i, tok in enumerate(toks[:-1]):
        if tok not in NOMINAL_SKIP_NEXT:
            continue
        if tok == "việc" and i > 0 and toks[i - 1] in NOMINAL_SKIP_PREV:
            continue
        if toks[i + 1] in NOMINAL_SKIP_NEXT[tok] or toks[i + 1].isdigit():
            continue
        count += 1
    return count


# ---------------------------------------------------------------- so với bài mẫu

def ngram_counts(text: str, sizes) -> tuple:
    """(đếm n-gram viết thường, đếm số lần n-gram đó viết hoa mọi chữ đầu, tức nhiều khả năng là tên riêng).
    Không vắt qua dấu câu. Một từ đứng đầu câu viết hoa thì chưa chắc là tên riêng nên không tính."""
    counts, capitalized = Counter(), Counter()
    for segment in SEGMENT_SPLIT.split(text):
        toks = re.findall(r"\w+", segment)
        low = [t.lower() for t in toks]
        for n in sizes:
            for i in range(len(toks) - n + 1):
                gram = " ".join(low[i:i + n])
                counts[gram] += 1
                if not (i == 0 and n == 1) and all(t[:1].isupper() for t in toks[i:i + n]):
                    capitalized[gram] += 1
    return counts, capitalized


def unfamiliar_phrases(text: str, samples: str, limit: int = 8) -> list:
    """Cụm lặp lại ít nhất 3 lần trong bản nháp mà bài mẫu không có (cách lập hồ sơ "slop" của Antislop)."""
    vietnamese = is_vietnamese(text)
    sizes, stop = ((2, 3, 4), VI_STOP) if vietnamese else ((1,), EN_STOP)
    draft, caps = ngram_counts(text, sizes)
    known, _ = ngram_counts(samples, sizes)
    lexicon = set(STYLE_LEXICON)
    cands = {}
    for gram, n in draft.items():
        toks = gram.split()
        if n < 3 or known[gram] or gram in lexicon or caps[gram] * 2 >= n:
            continue
        if any(ch.isdigit() for ch in gram) or toks[0] in stop or toks[-1] in stop:
            continue
        if not vietnamese and len(gram) < 4:
            continue
        cands[gram] = n
    kept = []
    for gram in sorted(cands, key=lambda g: -len(g.split())):
        if not any(f" {gram} " in f" {k} " and cands[k] == cands[gram] for k in kept):
            kept.append(gram)
    kept.sort(key=lambda g: (-cands[g], -len(g)))
    return [{"phrase": g, "count": cands[g]} for g in kept[:limit]]


def compare_samples(text: str, samples: str, kind: str = "own") -> dict:
    """kind = classic: bài mẫu là văn kinh điển, không phải giọng người viết, nên không so cách xưng hô."""
    n_samples = words(samples)
    if n_samples < MIN_SAMPLE_WORDS:
        return {"used": False, "words": n_samples, "unfamiliar": [], "hits": [],
                "reason": f"bài mẫu mới có {n_samples} từ, cần ít nhất {MIN_SAMPLE_WORDS}"}
    n_draft = max(words(text), 1)
    hits = []
    for term, rx in LEXICON_RX:
        found = list(rx.finditer(text))
        if len(found) < 2:
            continue
        in_samples = len(rx.findall(samples))
        rate_samples = in_samples * 1000 / n_samples
        rate_draft = len(found) * 1000 / n_draft
        smoothed = (in_samples + 0.5) * 1000 / n_samples
        if rate_samples < RARE_PER_1000 and rate_draft >= OVERUSE_RATIO * smoothed:
            fix = ("Văn mẫu kinh điển gần như không dùng từ này: nói cụ thể hơn, hoặc giữ nếu là thuật ngữ của chủ đề."
                   if kind == "classic" else "Thay bằng cách nói bạn hay dùng, hoặc bỏ.")
            hits.append({"code": "khac-bai-mau", "group": "không giống bài mẫu", "weight": 1,
                         "line": line_of(text, found[0].start()),
                         "match": f"“{term}” ×{len(found)} (bài mẫu: {in_samples} lần trong {n_samples} từ)",
                         "fix": fix})
    sample_fp = {k: len(rx.findall(samples)) for k, rx in FIRST_PERSON.items()}
    if kind != "classic" and sum(sample_fp.values()) >= 5:
        for usual, other in (("mình", "tôi"), ("tôi", "mình")):
            if sample_fp[usual] < 4 * sample_fp[other]:
                continue
            found = list(FIRST_PERSON[other].finditer(text))
            if len(found) >= 2 and len(found) > len(FIRST_PERSON[usual].findall(text)):
                hits.append({"code": "xung-ho", "group": "không giống bài mẫu", "weight": 2,
                             "line": line_of(text, found[0].start()),
                             "match": f"xưng “{other}” ×{len(found)}, bài mẫu xưng “{usual}” "
                                      f"({sample_fp[usual]} lần; “{other}” {sample_fp[other]} lần)",
                             "fix": "Đổi về cách xưng của bài mẫu, trừ khi văn bản này cần trang trọng hơn."})
    return {"used": True, "words": n_samples, "unfamiliar": unfamiliar_phrases(text, samples), "hits": hits}


def strip_frontmatter(text: str) -> str:
    """Bỏ khối YAML đầu file (tên bài, nguồn, giấy phép), để siêu dữ liệu không lẫn vào từ vựng bài mẫu."""
    return FRONTMATTER.sub("", text, count=1)


def load_samples(path: Path, exclude: Path = None, vietnamese: bool = None, skip: Path = None) -> tuple:
    """(văn bản gộp, số bài). Bỏ README, chính file đang được chấm và cây thư mục `skip`.
    Với thư mục, `vietnamese` (True/False) chỉ giữ bài cùng ngôn ngữ với bản nháp; None là giữ hết."""
    if path.is_file():
        files, by_lang = [path], False
    elif path.is_dir():
        files = sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in SAMPLE_EXT
                       and p.name.lower() != "readme.md")
        by_lang = vietnamese is not None
    else:
        files, by_lang = [], False
    if exclude is not None:
        files = [p for p in files if p.resolve() != exclude.resolve()]
    if skip is not None:
        files = [p for p in files if skip.resolve() not in p.resolve().parents]
    texts = []
    for p in files:
        try:
            if p.stat().st_size > 1_000_000:
                continue
            body = strip_frontmatter(unicodedata.normalize("NFC", p.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
        if by_lang and is_vietnamese(body) != vietnamese:
            continue
        texts.append(body)
    return "\n\n".join(texts), len(texts)


def find_project_samples(start: Path):
    """Thư mục .agent/giong-van/samples/ gần nhất từ `start` đi lên; dừng ở gốc git hoặc thư mục nhà."""
    start = Path(start).resolve()
    home = Path.home().resolve()
    for d in (start, *start.parents):
        if (d / PROJECT_SAMPLES).is_dir():
            return d / PROJECT_SAMPLES
        if (d / ".git").exists() or d == home:
            break
    return None


def pick_samples(text: str, draft_path: Path = None, project_start: Path = None,
                 skill_samples: Path = DEFAULT_SAMPLES):
    """Chọn bộ bài mẫu cùng ngôn ngữ với bản nháp: bài của project, rồi bài riêng trong samples/ của skill,
    rồi văn mẫu kinh điển. Trả về {kind, where, text, files, words, note} hoặc None nếu không có gì."""
    vietnamese = is_vietnamese(unicodedata.normalize("NFC", text))
    classics = skill_samples / CLASSICS_DIR
    candidates = []
    project = find_project_samples(project_start or Path.cwd())
    if project is None and draft_path is not None:
        project = find_project_samples(Path(draft_path).resolve().parent)
    if project is not None:
        candidates.append(("project", project, None))
    candidates.append(("own", skill_samples, classics))
    candidates.append(("classic", classics / ("vi" if vietnamese else "en"), None))
    notes = []
    for kind, where, skip in candidates:
        combined, n = load_samples(where, draft_path, vietnamese=vietnamese, skip=skip)
        n_words = words(combined) if n else 0
        if n and n_words >= MIN_SAMPLE_WORDS:
            return {"kind": kind, "where": where, "text": combined, "files": n, "words": n_words,
                    "note": "; ".join(notes)}
        if n and kind == "project":
            notes.append(f"bài mẫu của project mới có {n_words} từ, cần ít nhất {MIN_SAMPLE_WORDS}")
    return None


# ---------------------------------------------------------------- phân tích

def analyze(text: str, samples: str = None, kind: str = "own") -> dict:
    """samples: văn bản gộp của bài mẫu. None nghĩa là không so (kết quả chỉ phụ thuộc vào text).
    kind: project, own, path hoặc classic (văn kinh điển: không so cách xưng hô)."""
    text = unicodedata.normalize("NFC", text)
    hits = []
    for code, group, weight, rx, fix in COMPILED:
        for m in rx.finditer(text):
            raw = m.group(0)
            start = m.start() + len(raw) - len(raw.lstrip())  # mẫu có ^\s* có thể bắt đầu từ dòng trống phía trên
            hits.append({"code": code, "group": group, "weight": weight, "line": line_of(text, start),
                         "match": raw.strip()[:60], "fix": fix})
    n_words = max(words(text), 1)
    dashes = text.count("—")
    bold = len(re.findall(r"\*\*[^*\n]+\*\*", text))
    emoji = len(EMOJI.findall(text))
    nominal = nominal_count(text)
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
    if nominal >= 4 and nominal * 1000 / n_words > 10:
        extra.append({"code": "danh-hoa", "group": "danh từ hóa", "weight": 1, "line": 0,
                      "match": f"{nominal} cụm “việc/sự + động từ”",
                      "fix": "Đổi thành động từ có chủ ngữ: “việc sử dụng AI giúp…” → “nhóm dùng AI để…”."})
    hits += extra
    compared = None
    if samples is not None:
        compared = compare_samples(text, unicodedata.normalize("NFC", samples), kind)
        hits += compared.pop("hits")
    score = sum(h["weight"] for h in hits) * 1000 / n_words
    result = {"words": n_words, "score_per_1000_words": round(score, 1), "hits": hits,
              "sentence_length_cv": round(cv, 2) if cv is not None else None}
    if compared is not None:
        result["samples"] = compared
    return result


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Dò dấu hiệu văn AI (chỉ đọc).")
    ap.add_argument("path", help="file văn bản, hoặc - để đọc từ stdin")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--samples", help="thư mục hoặc file bài mẫu (mặc định: tự chọn, xem đầu file)")
    ap.add_argument("--project", help="tìm .agent/giong-van/samples/ từ thư mục này (mặc định: thư mục hiện tại)")
    ap.add_argument("--samples-root", help=argparse.SUPPRESS)  # thư mục samples/ của skill; dùng trong test
    ap.add_argument("--no-samples", action="store_true", help="không so với bài mẫu")
    args = ap.parse_args(argv)
    text = sys.stdin.read() if args.path == "-" else Path(args.path).read_text(encoding="utf-8")
    samples_info = None
    if args.no_samples:
        result = analyze(text)
    else:
        draft = None if args.path == "-" else Path(args.path)
        vietnamese = is_vietnamese(unicodedata.normalize("NFC", text))
        if args.samples:
            where = Path(args.samples).expanduser()
            samples, n_files = load_samples(where, draft, vietnamese=vietnamese)
            picked = {"kind": "path", "where": where, "text": samples, "files": n_files, "note": ""} if n_files else None
        else:
            root = Path(args.samples_root).expanduser() if args.samples_root else DEFAULT_SAMPLES
            project = Path(args.project).expanduser() if args.project else None
            picked = pick_samples(text, draft, project, root)
            where = PROJECT_SAMPLES
        if picked:
            result = analyze(text, picked["text"], picked["kind"])
            result["samples"].update({"files": picked["files"], "kind": picked["kind"],
                                      "where": str(picked["where"]), "note": picked["note"],
                                      "language": "vi" if vietnamese else "en"})
        else:
            result = analyze(text)
            result["samples"] = {"used": False, "files": 0, "words": 0, "unfamiliar": [],
                                 "reason": f"chưa có bài mẫu ở {where} (thêm 5 bài tự viết để bật)"}
        samples_info = result["samples"]
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    print(f"Điểm: {result['score_per_1000_words']} trên 1.000 từ ({result['words']} từ). Càng thấp càng ít dấu hiệu.")
    for h in sorted(result["hits"], key=lambda x: (x["line"], -x["weight"])):
        where = f"dòng {h['line']}" if h["line"] else "toàn bài"
        print(f"- [{h['group']}] {where}: “{h['match']}” → {h['fix']}")
    if samples_info is not None:
        if not samples_info["used"]:
            print(f"Chưa so với bài mẫu: {samples_info['reason']}.")
        else:
            kind = samples_info.get("kind", "path")
            label = KIND_LABEL.get(kind, "bài mẫu")
            if kind == "classic":
                label += " tiếng Việt" if samples_info.get("language") == "vi" else " tiếng Anh"
            print(f"Đã so với {samples_info['files']} {label} ({samples_info['words']} từ).")
            if samples_info.get("note"):
                print(f"Ghi chú: {samples_info['note']}.")
            if kind == "classic":
                print(f"Chưa có bài của bạn cho project này: thêm vào {PROJECT_SAMPLES.as_posix()}/ của project "
                      "để so với giọng của bạn (văn kinh điển không so cách xưng hô).")
            if samples_info["unfamiliar"]:
                print("Cụm lặp lại mà bài mẫu không có (không tính điểm; có thể chỉ là từ của chủ đề): "
                      + ", ".join(f"“{u['phrase']}” ×{u['count']}" for u in samples_info["unfamiliar"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
