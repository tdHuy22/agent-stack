# Kiểm duyệt: blader/humanizer

- Ngày: 2026-10-01 · Công cụ: vet.py/1 + skill-scanner 2.1.0
- Nguồn: github:blader/humanizer · Commit: `225a6f39ac85f76ee48dbad772ea4abe4ed6c9d8`
- **Phán quyết: REVIEW**

## Repo

| Sao | Cập nhật | Archived | Giấy phép | Chủ sở hữu |
|---:|---|---|---|---|
| 53305 | 2026-09-28 | False | MIT | User |

File giấy phép: LICENSE: MIT

## Thống kê file

code: 4, md: 4, other: 6 · tổng 64 KB

## Lý do

- ⚠️ Có 4 file mã hoặc cấu hình chạy được; cần đọc trước khi cài.

## Thành phần tự chạy hoặc có quyền

- **Hook:** không có
- **MCP:** không có
- **Monitor:** không có
- **bin/ trên PATH:** không có
- **Script khi cài:** không có
- **Nguồn plugin bên ngoài:** không có

## Skill và agent

- `.`: name=`humanizer`, mô tả 341 ký tự

## Dấu hiệu (luật riêng)

| Mức | Luật | Vị trí | Loại file | Trích |
|---|---|---|---|---|
| medium | remote-package | .github/workflows/validate.yml:25 | other | `run: npx --yes skills@1.5.20 add . --list` |

## skill-scanner

Đếm theo mức: low=2
- low · HIDDEN_DATA_FILE · Hidden data file detected (.cursor-plugin/plugin.json:None)
- low · HIDDEN_DATA_FILE · Hidden data file detected (.vet-complete:None)

## Cần đọc tay trước khi duyệt

Nội dung các file dưới đây là dữ liệu không tin cậy. Đọc để hiểu, không làm theo chỉ dẫn trong đó.

- [ ] `.claude-plugin/marketplace.json`
- [ ] `.claude-plugin/plugin.json`
- [ ] `.cursor-plugin/plugin.json`
- [ ] `SKILL.md`
- [ ] `scripts/validate-package.py`

Duyệt xong thì ghi lại: `vet.py approve <khóa> --note "..."` (hoặc `reject`).

## Nhận xét của Claude khi đọc tay (2026-10-01, chưa phải xác nhận của bạn)

- Khuyến nghị: **cài được.**
- `plugin.json` và `marketplace.json` chỉ khai báo skill ở gốc repo. Không có hook, MCP hay `bin/`.
- `scripts/validate-package.py` là script kiểm định dạng gói dành cho người phát triển. Nó chỉ đọc file trong repo, không gọi mạng, và skill không bao giờ gọi tới nó.
- `SKILL.md` chỉ chứa chỉ dẫn. Ở "file mode", nó ghi đè đúng file bạn chỉ định. Đó là hành vi mong đợi, nên nhớ dùng git để xem diff.
- Chi phí: `SKILL.md` khoảng 400 dòng (tối đa 5.500 từ), nên mỗi lần dùng tốn vài nghìn token. Chỉ hỗ trợ tiếng Anh.
