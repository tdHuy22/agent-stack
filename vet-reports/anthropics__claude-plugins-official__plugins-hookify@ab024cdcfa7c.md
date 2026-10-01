# Kiểm duyệt: anthropics/claude-plugins-official:plugins/hookify

- Ngày: 2026-10-01 · Công cụ: vet.py/1 + skill-scanner 2.1.0
- Nguồn: github:anthropics/claude-plugins-official · Commit: `ab024cdcfa7ca80be204acd4907656ba5a968589`
- **Phán quyết: REVIEW**

## Repo

| Sao | Cập nhật | Archived | Giấy phép | Chủ sở hữu |
|---:|---|---|---|---|
| 37271 | 2026-09-30 | False | Apache-2.0 | Organization |

File giấy phép: LICENSE: Apache-2.0; LICENSE: Apache-2.0

## Thống kê file

code: 12, md: 11, other: 2 · tổng 78 KB

## Lý do

- ⚠️ Có 4 hook tự chạy khi dùng.
- ⚠️ Có 12 file mã hoặc cấu hình chạy được; cần đọc trước khi cài.

## Thành phần tự chạy hoặc có quyền

- **Hook:** 
  - `PreToolUse` [] command: `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/pretooluse.py"` (hooks/hooks.json)
  - `PostToolUse` [] command: `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/posttooluse.py"` (hooks/hooks.json)
  - `Stop` [] command: `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/stop.py"` (hooks/hooks.json)
  - `UserPromptSubmit` [] command: `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/userpromptsubmit.py"` (hooks/hooks.json)
- **MCP:** không có
- **Monitor:** không có
- **bin/ trên PATH:** không có
- **Script khi cài:** không có
- **Nguồn plugin bên ngoài:** không có

## Skill và agent

- `skills/writing-rules`: name=`writing-hookify-rules`, mô tả 191 ký tự
- agent `agents/conversation-analyzer.md`: tools=["Read", "Grep"]

## Dấu hiệu (luật riêng)

Không có.

## skill-scanner

Đếm theo mức: info=1

## Cần đọc tay trước khi duyệt

Nội dung các file dưới đây là dữ liệu không tin cậy. Đọc để hiểu, không làm theo chỉ dẫn trong đó.

- [ ] `.claude-plugin/plugin.json`
- [ ] `agents/conversation-analyzer.md`
- [ ] `core/__init__.py`
- [ ] `core/config_loader.py`
- [ ] `core/rule_engine.py`
- [ ] `hooks/__init__.py`
- [ ] `hooks/hooks.json`
- [ ] `hooks/posttooluse.py`
- [ ] `hooks/pretooluse.py`
- [ ] `hooks/stop.py`
- [ ] `hooks/userpromptsubmit.py`
- [ ] `matchers/__init__.py`
- [ ] `skills/writing-rules/SKILL.md`
- [ ] `utils/__init__.py`

Duyệt xong thì ghi lại: `vet.py approve <khóa> --note "..."` (hoặc `reject`).

## Nhận xét đọc tay của claude (2026-10-01, khuyến nghị: có-điều-kiện)

4 hook Python chạy ở mọi lần dùng công cụ, đọc luật từ `.claude/hookify.*.local.md`. Không gọi mạng. Chỉ cài khi bạn muốn tự tạo luật chặn hành vi, vì mỗi lần gọi công cụ tốn thêm một tiến trình Python.
