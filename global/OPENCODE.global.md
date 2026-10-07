# Riêng OpenCode và công cụ không có hook của agent-stack

- Ở câu trả lời đầu tiên của phiên, chạy `python3 ~/Documents/Claude/agent-stack/plugin/skills/task-router/scripts/route.py --session <thư mục project>`; chưa chắc chọn gì cho một việc thì chạy `route.py "<việc>" --project <thư mục project>`.
- Dòng ➡️ trong OpenCode: Model là model trong cấu hình OpenCode (việc cơ học dùng model local của agent `worker`), Effort chỉ ghi khi model hỗ trợ, Subagent là `build`, `plan` hoặc `worker`.
