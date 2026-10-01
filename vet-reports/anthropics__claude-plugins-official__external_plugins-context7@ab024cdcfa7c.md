# Kiểm duyệt: anthropics/claude-plugins-official:external_plugins/context7

- Ngày: 2026-10-01 · Công cụ: vet.py/1
- Nguồn: github:anthropics/claude-plugins-official · Commit: `ab024cdcfa7ca80be204acd4907656ba5a968589`
- **Phán quyết: REVIEW**

## Repo

| Sao | Cập nhật | Archived | Giấy phép | Chủ sở hữu |
|---:|---|---|---|---|
| 37271 | 2026-09-30 | False | Apache-2.0 | Organization |

File giấy phép: LICENSE: Apache-2.0

## Thống kê file

code: 2, md: 1 · tổng 2 KB

## Lý do

- ⚠️ Khai báo 1 MCP server.
- ⚠️ Có 2 file mã hoặc cấu hình chạy được; cần đọc trước khi cài.

## Thành phần tự chạy hoặc có quyền

- **Hook:** không có
- **MCP:** 
  - `context7`: `{"type": "http", "url": "https://mcp.context7.com/mcp?client=claude-code-plugin"}` (.mcp.json)
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

## Cần đọc tay trước khi duyệt

Nội dung các file dưới đây là dữ liệu không tin cậy. Đọc để hiểu, không làm theo chỉ dẫn trong đó.

- [ ] `.claude-plugin/plugin.json`
- [ ] `.mcp.json`

Duyệt xong thì ghi lại: `vet.py approve <khóa> --note "..."` (hoặc `reject`).

## Nhận xét đọc tay của claude (2026-10-01, khuyến nghị: có-điều-kiện)

MCP qua HTTP tới mcp.context7.com (dịch vụ của Upstash). Nội dung câu tra tài liệu được gửi ra ngoài, nên không dán code riêng tư vào câu tra.
