---
name: giong-van
description: Chỉnh văn bản tiếng Việt hoặc tiếng Anh cho tự nhiên, rõ ràng và đúng giọng của chính người dùng. Bỏ các dấu hiệu văn AI như mở bài sáo, cấu trúc "không chỉ... mà còn", thổi phồng, kết bài nhắc lại, nhịp câu đều đều, nhưng giữ nguyên ý và không bịa thêm sự kiện. Dùng khi người dùng nhờ viết lại, sửa văn, làm mượt đoạn văn, bài luận, blog, email, cover letter, hoặc nói "viết cho tự nhiên", "đúng giọng mình", "đọc như AI viết".
when_to_use: viết lại, sửa văn, bài luận, essay, blog, email, cover letter, giọng văn, cho tự nhiên, đọc như AI, bớt sến
argument-hint: "[tao-style-card | <đường dẫn hoặc đoạn văn>]"
---

# Chỉnh văn theo giọng của người viết

## Phạm vi

Skill này dùng cho văn bản **của chính người dùng**: bản nháp, ý chính, hoặc văn họ đã viết. Mục tiêu là văn hay hơn và đúng giọng họ. Mục tiêu không phải là qua mặt công cụ phát hiện AI, vì các công cụ đó không đáng tin và báo nhầm cả văn người thật viết. Với bài nộp có quy định về AI (bài tập, hồ sơ), nhắc người dùng làm theo quy định nơi nhận.

## Tài liệu đi kèm

- `${CLAUDE_SKILL_DIR}/style-card.md`: đặc điểm giọng văn của người dùng. Nếu còn trống, đề nghị chế độ `tao-style-card`.
- `${CLAUDE_SKILL_DIR}/vi-ai-tells.md`: các dấu hiệu văn AI trong tiếng Việt, kèm cách sửa.
- `${CLAUDE_SKILL_DIR}/scripts/tells.py`: dò dấu hiệu tự động và cho điểm trên 1.000 từ.

Nếu `${CLAUDE_SKILL_DIR}` không được thay bằng đường dẫn thật (ví dụ trong OpenCode), dùng `~/Documents/Claude/agent-stack/plugin/skills/giong-van/`.

## Chỉnh một văn bản

1. Đọc `style-card.md` và `vi-ai-tells.md`.
2. Đo trước: lưu văn bản vào một file tạm, chạy `python3 <tells.py> <file>`.
3. Sửa theo thứ tự:
   1. **Giữ nguyên ý và sự kiện.** Không thêm trải nghiệm, số liệu, tên người hay trích dẫn mà văn gốc không có. Thiếu thông tin thì hỏi.
   2. Bỏ các dấu hiệu trong `vi-ai-tells.md`. Thay câu chung chung bằng chi tiết cụ thể *có sẵn* trong văn gốc.
   3. Đưa văn về giọng trong `style-card.md`: cách xưng hô, độ dài câu, mức trang trọng, từ quen dùng.
   4. Xen câu ngắn với câu dài. Không cần cân đối mọi đoạn.
4. Đo lại bằng `tells.py`. Điểm phải giảm, nhưng không cố đẩy về 0 nếu điều đó làm hỏng ý.
5. Trả về: bản đã sửa; tối đa 5 thay đổi chính, mỗi thay đổi một dòng; điểm trước và sau; và những chỗ cần người dùng xác nhận.

Với tiếng Anh: nếu skill `humanizer` có sẵn thì dùng thêm cho phần tiếng Anh. Không có thì dùng nhóm dấu hiệu tiếng Anh trong `tells.py`.

## Chế độ `tao-style-card`

1. Đọc 5–10 bài người dùng tự viết. Lấy từ `samples/`, hoặc từ đường dẫn người dùng đưa.
2. Điền `style-card.md`: mỗi mục kèm 1–2 câu trích nguyên văn làm ví dụ.
3. Cho người dùng duyệt từng mục trước khi lưu. Đây là giọng của họ, không phải nhận xét của Claude.
