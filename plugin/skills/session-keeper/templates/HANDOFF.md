# HANDOFF: {project}

*Cập nhật {date}.* Tạo bởi skill session-keeper. File này để một phiên khác (Claude Code hoặc công cụ khác) làm tiếp mà không phải hỏi lại.

## 0. Đang ở đâu, việc tiếp theo

- **Mục tiêu:** <!-- điền: việc này nhằm đạt điều gì -->
- **Xong:** {done}
- **Đang dở:** {in_progress}
- **Việc tiếp theo, theo thứ tự:**
{next}
- **Quyết định còn treo:** {decisions}
- **Mốc kiểm tra:** {checks}
- **Sau khi bị ngắt:** {after}

## Quyết định đã chốt (kèm lý do)

<!-- điền: các quyết định quan trọng, để phiên sau không bàn lại -->

## Trạng thái git lúc bàn giao

{git}

## Làm tiếp bằng công cụ khác

- **Claude Code:** mở phiên mới trong thư mục project. Hook của agent-stack sẽ tự nạp file này.
- **Công cụ không có hook:** mở trong thư mục project rồi nhắn: "Đọc .agent/HANDOFF.md rồi làm tiếp bước 1."
