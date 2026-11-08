"""Chấm viet-readme-script: README đúng cờ, mặc định, mã thoát theo code (không theo chú thích cũ), đủ bốn mục.

Từ saoluu.py (chú thích đầu file cũ: giữ 5 bản, --keep-all, --dry-run là bẫy):
  cờ --giu (mặc định 7, hoặc biến SAOLUU_GIU; 0 là giữ hết), --nen zip|tar (mặc định zip, tar cho ra .tar.gz), --bo-qua (dùng nhiều
  lần, CỘNG vào mặc định .git node_modules __pycache__), --thu (không ghi, không xóa), -v/--chi-tiet; Python 3.9+; mã thoát 2 (không
  có thư mục nguồn), 3 (đích không ghi được), 4 (đích còn trống dưới 1,2 lần dung lượng nguồn); tên file ten-YYYYMMDD-HHMMSS.

Mã thoát xét theo mệnh đề (tách ở dấu chấm, chấm phẩy, xuống dòng), coi "|" của bảng Markdown như khoảng trắng nên bảng cũng đạt.

Fixture (solution/dat-khac, solution/truot) chạy trong selftest.py:
  ĐẠT    1 bảng cho Tùy chọn, mã thoát viết trong một đoạn; 2 mã thoát viết bằng bảng Markdown, tùy chọn bằng gạch đầu dòng; 3 mở bằng câu sáo
         "Trong bối cảnh" nhưng đúng cờ, mặc định và mã thoát (văn AI không còn làm trượt)
  TRƯỢT  1 theo chú thích cũ (giữ 5 bản, --dry-run, --keep-all), thiếu hầu hết cờ; 2 mặc định 5, --exclude, thiếu biến SAOLUU_GIU và mục Mã thoát;
         3 --bo-qua thay mặc định, thiếu --giu 0, nhầm mã 2 và 3
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vncheck  # noqa: E402

NAMES = ["Yêu cầu", "Cách dùng", "Tùy chọn", "Mã thoát"]


def sections(text, names):
    lines = text.split("\n")
    pos = {}
    for i, ln in enumerate(lines):
        h = re.sub(r"^[\s#*\-\d.)]+|[\s*:]+$", "", ln).strip().lower()
        for n in names:
            if h == n.lower() and n not in pos:
                pos[n] = i
    order = sorted(pos.items(), key=lambda kv: kv[1])
    out = {}
    for k, (n, i) in enumerate(order):
        end = order[k + 1][1] if k + 1 < len(order) else len(lines)
        out[n] = "\n".join(lines[i + 1:end])
    return out, [n for n, _ in order]


def windows(text, token, width=400):
    return [text[m.start():m.start() + width] for m in re.finditer(re.escape(token), text)]


def main():
    text = vncheck.read("cong-cu/README.md")
    if text is None:
        vncheck.finish(["chưa có /app/cong-cu/README.md"])
    errs = vncheck.writing_checks(text, max_words=350, min_words=60)
    flat = text.replace("`", "")
    sec, order = sections(text, NAMES)
    miss = [n for n in NAMES if n not in sec]
    if miss:
        errs.append("thiếu mục: " + ", ".join(miss))
    elif order != NAMES:
        errs.append("bốn mục không đúng thứ tự Yêu cầu, Cách dùng, Tùy chọn, Mã thoát")
    for f in ("--giu", "--nen", "--bo-qua", "--thu"):
        if f not in flat:
            errs.append(f"thiếu cờ {f}")
    if not re.search(r"(?<![\w-])-v(?![\w-])|--chi-tiet", flat):
        errs.append("thiếu cờ -v hay --chi-tiet")
    for bad in ("--keep", "--dry-run", "--exclude", "--compress", "--verbose", "--retain"):
        if bad in flat:
            errs.append(f"có cờ không tồn tại {bad} (lấy từ chú thích cũ hay tự bịa)")
    # --giu: mặc định 7, 0 là giữ hết, biến SAOLUU_GIU
    if not any(re.search(r"(?<![\d,.])7(?![\d])", w) and re.search(r"(?<![\d,.])0(?![\d])", w) for w in windows(flat, "--giu")):
        errs.append("mục --giu phải nêu mặc định 7 và ý nghĩa của giá trị 0 (giữ hết)")
    if re.search(r"giữ[^.\n]{0,50}(?<![\d,.])5(?![\d])|(?<![\d,.])5\s*bản", flat, re.I):
        errs.append("còn ghi giữ 5 bản theo chú thích cũ (code mặc định 7)")
    if "SAOLUU_GIU" not in flat:
        errs.append("thiếu biến môi trường SAOLUU_GIU")
    if not any(re.search(r"không\s+(xóa|xoá)|giữ\s+(hết|tất cả|toàn bộ|lại hết)|không giới hạn", w, re.I) for w in windows(flat, "--giu")):
        errs.append("không nói --giu 0 nghĩa là không xóa bản cũ")
    # --nen
    if "tar.gz" not in flat:
        errs.append("không nói --nen tar cho ra file .tar.gz")
    if not any(re.search(r"zip", w) and re.search(r"tar", w) for w in windows(flat, "--nen")):
        errs.append("mục --nen thiếu hai lựa chọn zip và tar")
    # --bo-qua
    for d in (".git", "node_modules", "__pycache__"):
        if d not in flat:
            errs.append(f"thiếu mẫu bỏ qua mặc định {d}")
    if not any(re.search(r"thêm|bổ sung|ngoài|cộng|không (thay|ghi đè)|vẫn", w, re.I) for w in windows(flat, "--bo-qua")):
        errs.append("không nói --bo-qua được cộng thêm vào danh sách mặc định")
    # --thu
    if not any(re.search(r"không\s+(ghi|xóa|xoá|tạo|làm|thay|đụng|sửa)|chỉ (in|hiển thị|báo|cho xem)|chỉ xem", w, re.I) for w in windows(flat, "--thu")):
        errs.append("không nói --thu chỉ chạy thử, không ghi hay xóa gì")
    # tên file
    if not re.search(r"(YYYY|AAAA)\s?MM\s?DD|%Y%m%d|\d{8}-\d{6}", flat):
        errs.append("không nói cách đặt tên file kết quả (ngày giờ dạng YYYYMMDD-HHMMSS)")
    # yêu cầu, mã thoát
    if "Yêu cầu" in sec and not re.search(r"3\.9", sec["Yêu cầu"]):
        errs.append("mục Yêu cầu thiếu Python 3.9")
    if "Mã thoát" in sec:
        body = re.sub(r"(\d)[.,](\d)", r"\1_\2", sec["Mã thoát"].replace("|", " "))
        segs = [s for s in re.split(r"[.;\n|]", body) if s.strip()]
        for code, kw in ((2, r"nguồn"), (3, r"đích"), (4, r"chỗ|dung lượng|ổ đĩa|đầy")):
            if not any(re.search(rf"(?<![\d_]){code}(?![\d_])", s) and re.search(kw, s, re.I) for s in segs):
                errs.append(f"mục Mã thoát thiếu mã {code} đúng lý do")
        if not re.search(r"1_2", body):
            errs.append("mã 4 thiếu ngưỡng 1,2 lần dung lượng nguồn")
        for s in segs:
            if re.search(r"(?<![\d_])2(?![\d_])", s) and re.search(r"đích", s, re.I) and not re.search(r"nguồn", s, re.I):
                errs.append("nhầm mã 2 với lỗi thư mục đích")
    # ví dụ lệnh trong khối code
    blocks = re.findall(r"```.*?```", text, re.S)
    if not any(re.search(r"saoluu\.py\s+\S+\s+\S+", b) for b in blocks):
        errs.append("thiếu ví dụ lệnh saoluu.py NGUON DICH trong khối code")
    vncheck.finish(errs)


main()
