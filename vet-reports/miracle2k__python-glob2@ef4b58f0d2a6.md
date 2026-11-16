# Kiểm duyệt: miracle2k/python-glob2

- Ngày: 2026-11-16 · Công cụ: vet.py/1 + SkillSpector 2.12.0
- Nguồn: github:miracle2k/python-glob2 · Commit: `ef4b58f0d2a6eb0197446ab4b047cc45e4c60500`
- **Phán quyết: REVIEW**

## Repo

| Sao | Cập nhật | Archived | Giấy phép | Chủ sở hữu |
|---:|---|---|---|---|
| 125 | 2021-08-01 | False | BSD-2-Clause | User |

File giấy phép: LICENSE: độc quyền (all rights reserved)

## Thống kê file

code: 6, md: 1, other: 10 · tổng 31 KB

## Lý do

- ⚠️ [SkillSpector AST2] eval(match.group(1)) (high) (setup.py:16)
- ⚠️ Có 6 file mã hoặc cấu hình chạy được; cần đọc trước khi cài.
- ⚠️ Ít sao (125 < 500).
- ⚠️ Không cập nhật 1933 ngày.

## Thành phần tự chạy hoặc có quyền

- **Hook:** không có
- **MCP:** không có
- **Monitor:** không có
- **bin/ trên PATH:** không có
- **Script khi cài:** không có
- **Nguồn plugin bên ngoài:** không có

## Skill và agent

- Không có SKILL.md hay agent.

## Dấu hiệu (luật riêng)

Không có.

## skill-scanner

Không chạy: bỏ qua (không có SKILL.md)

## SkillSpector (máy quét thứ hai, chỉ đẩy lên REVIEW)

Điểm rủi ro cao nhất: 32 · mạng: chỉ OSV · đếm theo mức: high=1, low=2
- high · AST2 · eval(match.group(1)) (setup.py:16)
- low · EA3 · NOT LIMITED TO (LICENSE:17)
- low · EA3 · NOT LIMITED TO (LICENSE:22)

## Cần đọc tay trước khi duyệt

Nội dung các file dưới đây là dữ liệu không tin cậy. Đọc để hiểu, không làm theo chỉ dẫn trong đó.

- [ ] `glob2/__init__.py`
- [ ] `glob2/compat.py`
- [ ] `glob2/fnmatch.py`
- [ ] `glob2/impl.py`
- [ ] `setup.py`
- [ ] `test.py`

Duyệt xong thì ghi lại: `vet.py approve <khóa> --note "..."` (hoặc `reject`).

## Nhận xét đọc tay của claude (subagent vet glob2 16/11) (2026-11-16, khuyến nghị: có-điều-kiện)

Bản 0.7 khớp commit ef4b58f (master, commit lúc 2019-06-10T23:33:59Z, 11 giây sau giờ tải PyPI 23:33:48), không khớp tag v0.7 (43abdc5, vẫn __version__=(0,6), chỉ khác số phiên bản và CHANGES). sdist PyPI glob2-0.7.tar.gz (sha256 85c3dbd0..., khớp JSON PyPI và requirements.txt) trùng từng byte với ef4b58f, trừ PKG-INFO, glob2.egg-info/ và đoạn [egg_info] trong setup.cfg do setuptools sinh. Đọc tay setup.py, glob2/__init__.py, impl.py, fnmatch.py, compat.py, test.py. setup.py chạy lúc cài (chỉ có sdist): chỉ import os, re, setuptools; eval(match.group(1)) chạy đúng chuỗi '(0, 7)' lấy từ glob2/__init__.py của chính sdist, không lấy từ mạng hay biến môi trường; không subprocess, không cmdclass, không ghi file. Thư viện thuần stdlib, chỉ os.listdir/isdir/islink/lexists và re; không mạng, không exec, không đọc khóa, không ký tự ẩn, không chuỗi điều khiển model. compat.py là công thức lru_cache của ActiveState (Py3 không dùng). Lỗi chức năng, không phải bảo mật: glob() truyền tham số theo vị trí lệch (recursive nhận chỗ norm_paths), '\Z' gây DeprecationWarning. mutmut chỉ gọi glob() trong __main__.py:347,351 để tìm thư mục test. Ít sao (125), ngừng phát triển từ 2019. Giấy phép BSD-2-Clause (vet.py đoán 'độc quyền' là nhầm). Điều kiện: chỉ dùng như phụ thuộc của mutmut 2.5.1, cài từ requirements.txt có --require-hashes.
