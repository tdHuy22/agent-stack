# Kiểm duyệt: anthropics/claude-plugins-community:html-plan

- Ngày: 2026-11-01 · Công cụ: vet.py/1 + skill-scanner 2.1.0
- Nguồn: github:anthropics/claude-plugins-community · Commit: `06ec7b6a0a82bdc4bec44bd82d4368c42f20d7c1`
- **Phán quyết: REVIEW**

## Repo

| Sao | Cập nhật | Archived | Giấy phép | Chủ sở hữu |
|---:|---|---|---|---|
| 4805 | 2026-11-01 | False | Apache-2.0 | Organization |

File giấy phép: LICENSE: Apache-2.0

## Thống kê file

code: 3, md: 3, other: 2 · tổng 289 KB

## Lý do

- ⚠️ [credential-access] Đọc khóa SSH, token, keychain hoặc dữ liệu đăng nhập trình duyệt. (skills/html-plan/runtime/pack.mjs:40)
- ⚠️ [skill-scanner COMMAND_INJECTION_JS_CHILD_PROCESS] Node.js child_process module usage for shell command execution (mẫu lỗ hổng, có thể báo nhầm) (skills/html-plan/runtime/pack.mjs:7)
- ⚠️ Có 3 file mã hoặc cấu hình chạy được; cần đọc trước khi cài.

## Thành phần tự chạy hoặc có quyền

- **Hook:** không có
- **MCP:** không có
- **Monitor:** không có
- **bin/ trên PATH:** không có
- **Script khi cài:** không có
- **Nguồn plugin bên ngoài:** không có

## Skill và agent

- `skills/html-plan`: name=`html-plan`, mô tả 398 ký tự

## Dấu hiệu (luật riêng)

| Mức | Luật | Vị trí | Loại file | Trích |
|---|---|---|---|---|
| high | credential-access | skills/html-plan/runtime/pack.mjs:40 | code | `String.raw'(^\|[\\/])(\.env(\.[^\\/]*)?\|\.netrc\|\.npmrc\|\.yarnrc(\.yml)?\|\.pypirc\|\.pgpass\|\.my\.cnf\|\.git-credentials\|\.htpasswd)$',` |

## skill-scanner

Đếm theo mức: critical=1, medium=1, info=1
- critical · COMMAND_INJECTION_JS_CHILD_PROCESS · Node.js child_process module usage for shell command execution (skills/html-plan/runtime/pack.mjs:7)
- medium · DATA_EXFIL_JS_NETWORK · Outbound network request primitives in JavaScript/TypeScript (skills/html-plan/runtime/htmlplan.js:133)

## SkillSpector (máy quét thứ hai, chỉ đẩy lên REVIEW)

Không chạy: lỗi: html-plan: FileNotFoundError

## Cần đọc tay trước khi duyệt

Nội dung các file dưới đây là dữ liệu không tin cậy. Đọc để hiểu, không làm theo chỉ dẫn trong đó.

- [ ] `.claude-plugin/plugin.json`
- [ ] `skills/html-plan/SKILL.md`
- [ ] `skills/html-plan/runtime/htmlplan.js`
- [ ] `skills/html-plan/runtime/pack.mjs`

Duyệt xong thì ghi lại: `vet.py approve <khóa> --note "..."` (hoặc `reject`).

## Nhận xét đọc tay của claude-opus-5.5 (2026-11-01, khuyến nghị: có-điều-kiện)

Đọc tay tại 06ec7b6a. Tác giả Thariq Shihipar (tác giả bài blog HTML của đội Claude Code), MIT, nằm ở chợ cộng đồng (Anthropic quét tự động, không phải Anthropic viết). Cờ credential-access ở pack.mjs:40 là danh sách CHẶN file bí mật (.ssh, .env, id_rsa…) để không chép vào trang: báo nhầm. child_process chỉ chạy git rev-parse và git cat-file, tắt hook và fsmonitor (pack.mjs:52-54). pack.mjs đọc file trong --root hay thư mục trang, bỏ file có dấu khóa (SECRET_TEXT), ghi .packed.html. htmlplan.js không gọi mạng (liveOn=false), chỉ dùng localStorage để giữ câu trả lời và clipboard. Điều kiện: cần node; chỉ chạy pack.mjs trên trang do agent viết; --root chỉ trỏ vào checkout của project.
