#!/bin/bash
# Lời giải mẫu: viết thường, đ thành d, bỏ nháy đơn, NFD rồi bỏ dấu kết hợp, thu ký tự lạ thành một gạch nối, cắt theo từ.
set -euo pipefail
APP=${APP_DIR:-/app}
cat > "$APP/slug.py" <<'PY'
"""Tạo slug cho đường dẫn bài viết."""
import re
import unicodedata


def tao_slug(tieu_de, toi_da=60):
    """Đổi tiêu đề bài viết thành slug dùng trong URL."""
    s = tieu_de.lower().replace("đ", "d")
    s = re.sub("['’‘]", "", s)
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if not s:
        return "bai-viet"
    if len(s) <= toi_da:
        return s
    tu = s.split("-")
    if len(tu[0]) > toi_da:
        return tu[0][:toi_da]
    ra = tu[0]
    for t in tu[1:]:
        if len(ra) + 1 + len(t) > toi_da:
            break
        ra += "-" + t
    return ra


if __name__ == "__main__":
    for tieu_de in ("Hướng dẫn cài đặt Python", "Đường Điện Biên Phủ"):
        print(tao_slug(tieu_de))
PY
