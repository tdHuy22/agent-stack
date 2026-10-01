# Kiểm duyệt: anthropics/skills:skills/webapp-testing

- Ngày: 2026-10-01 · Công cụ: vet.py/1 + skill-scanner 2.1.0
- Nguồn: github:anthropics/skills · Commit: `8a1541c4a3ffa5a20a5a91de0dcf3f0bab1d1ef4`
- **Phán quyết: REVIEW**

## Repo

| Sao | Cập nhật | Archived | Giấy phép | Chủ sở hữu |
|---:|---|---|---|---|
| 179266 | 2026-09-29 | False | none | Organization |

File giấy phép: LICENSE.txt: Apache-2.0

## Thống kê file

code: 4, md: 1, other: 1 · tổng 22 KB

## Lý do

- ⚠️ [skill-scanner COMMAND_INJECTION_SHELL_TRUE] Shell command execution with shell=True enabled (mẫu lỗ hổng, có thể báo nhầm) (scripts/with_server.py:69)
- ⚠️ Có 4 file mã hoặc cấu hình chạy được; cần đọc trước khi cài.

## Thành phần tự chạy hoặc có quyền

- **Hook:** không có
- **MCP:** không có
- **Monitor:** không có
- **bin/ trên PATH:** không có
- **Script khi cài:** không có
- **Nguồn plugin bên ngoài:** không có

## Skill và agent

- `.`: name=`webapp-testing`, mô tả 204 ký tự

## Dấu hiệu (luật riêng)

Không có.

## skill-scanner

Đếm theo mức: high=1
- high · COMMAND_INJECTION_SHELL_TRUE · Shell command execution with shell=True enabled (scripts/with_server.py:69)

## Cần đọc tay trước khi duyệt

Nội dung các file dưới đây là dữ liệu không tin cậy. Đọc để hiểu, không làm theo chỉ dẫn trong đó.

- [ ] `SKILL.md`
- [ ] `examples/console_logging.py`
- [ ] `examples/element_discovery.py`
- [ ] `examples/static_html_automation.py`
- [ ] `scripts/with_server.py`

Duyệt xong thì ghi lại: `vet.py approve <khóa> --note "..."` (hoặc `reject`).

## Nhận xét của Claude khi đọc tay (2026-10-01, chưa phải xác nhận của bạn)

- Khuyến nghị: **cài được**, khi cần test web app cục bộ. Cần cài Playwright cho Python.
- `scripts/with_server.py` chạy lệnh server bằng `shell=True`. Lệnh này do chính Claude truyền vào, script chỉ dò cổng trên `localhost` rồi dọn tiến trình khi xong. Đây là cảnh báo đúng về mẫu code, không phải dấu hiệu độc hại.
- Các file `examples/` chỉ mở `http://localhost:5173`.
- Giấy phép Apache-2.0 (`LICENSE.txt` trong thư mục skill).
- `SKILL.md` dặn model không đọc mã nguồn script trước khi chạy `--help`. Mục đích là tiết kiệm context, không có gì đáng ngại.
