---
name: giong-van
description: Chỉnh văn bản tiếng Việt hoặc tiếng Anh cho tự nhiên, rõ ràng và đúng giọng của chính người dùng. Bỏ các dấu hiệu văn AI như mở bài sáo, cấu trúc "không chỉ... mà còn", thổi phồng, kết bài nhắc lại, nhịp câu đều đều, nhưng giữ nguyên ý và không bịa thêm sự kiện. Dùng khi người dùng nhờ viết lại, sửa văn, làm mượt đoạn văn, bài luận, blog, email, cover letter, hoặc nói "viết cho tự nhiên", "đúng giọng mình", "đọc như AI viết".
when_to_use: viết lại, sửa văn, bài luận, essay, blog, email, cover letter, giọng văn, cho tự nhiên, đọc như AI, bớt sến
argument-hint: "[tao-style-card | <đường dẫn hoặc đoạn văn>]"
---

# Chỉnh văn theo giọng của người viết

## Phạm vi

Skill này dùng cho văn bản của chính người dùng: bản nháp, ý chính, hoặc văn họ đã viết. Mục tiêu là văn hay hơn và đúng giọng họ, không phải qua mặt công cụ phát hiện AI. Các công cụ đó báo nhầm nhiều, nhất là với người viết bằng ngôn ngữ thứ hai, còn người đọc có kinh nghiệm vẫn nhận ra văn chỉ được sửa bề mặt. Với bài nộp có quy định về AI (bài tập, hồ sơ), nhắc người dùng làm theo quy định nơi nhận.

## Tài liệu đi kèm

- `${CLAUDE_SKILL_DIR}/style-card.md`: đặc điểm giọng văn của người dùng. Nếu còn trống, đề nghị chế độ `tao-style-card`.
- `${CLAUDE_SKILL_DIR}/vi-ai-tells.md`: dấu hiệu văn AI trong tiếng Việt, cách sửa, và nguồn nghiên cứu.
- `${CLAUDE_SKILL_DIR}/scripts/tells.py`: dò dấu hiệu, so từ vựng với bài mẫu trong `samples/`, cho điểm trên 1.000 từ. Chạy script và dùng kết quả; chỉ đọc mã nguồn khi kết quả không đủ để sửa.

Nếu `${CLAUDE_SKILL_DIR}` không được thay bằng đường dẫn thật (ví dụ trong OpenCode), dùng `~/Documents/Claude/agent-stack/plugin/skills/giong-van/`.

## Chỉnh một văn bản

1. Đọc `style-card.md` và `vi-ai-tells.md`.
2. Lưu văn bản vào một file tạm và chạy `python3 <tells.py> <file>` để lấy điểm trước khi sửa. Script tự so với bài mẫu trong `samples/` nếu có.
3. Sửa nội dung trước. Mỗi câu khẳng định cần dựa trên chi tiết có trong văn gốc: câu thổi phồng thì thay bằng con số hoặc ví dụ có sẵn, ý kiến của "chuyên gia" thì ghi rõ là ai, câu bình luận chung chung thì bỏ. Chỉ dùng sự kiện, số liệu, tên người và trích dẫn có trong văn gốc; chỗ nào thiếu thì hỏi người dùng.
4. Sau đó sửa câu chữ theo `vi-ai-tells.md` và các dòng `tells.py` báo. Từ bị đánh dấu "không giống bài mẫu" thì đổi sang cách nói người dùng hay dùng.
5. Đưa văn về giọng trong `style-card.md`: cách xưng hô, độ dài câu, mức trang trọng, từ quen dùng. Giữ thành ngữ, cách nói và lối lập luận quen thuộc của người viết, kể cả khi chúng khác khuôn viết tiếng Anh. Xen câu ngắn với câu dài; các đoạn không cần dài bằng nhau.
6. Chạy lại `tells.py`. Điểm cần giảm, nhưng ý của văn gốc quan trọng hơn con số: dừng khi sửa tiếp sẽ làm mất ý.

Viết bản sửa thành đoạn văn liền mạch, theo đúng định dạng của văn gốc: văn gốc là đoạn văn thì trả về đoạn văn, văn gốc có danh sách thì giữ danh sách. Sau bản sửa, báo ngắn gọn: tối đa 5 thay đổi chính, mỗi thay đổi một dòng; điểm trước và sau; và những chỗ cần người dùng xác nhận.

Với văn tiếng Anh, dùng thêm skill `humanizer` nếu có; nếu không, dựa vào nhóm dấu hiệu tiếng Anh trong `tells.py`.

## Chế độ `tao-style-card`

1. Đọc 5 bài người dùng tự viết, càng khác loại càng tốt (blog, email, ghi chú, bài luận). Lấy từ `samples/`, hoặc từ đường dẫn người dùng đưa. Thêm bài ít khi giúp bắt chước tốt hơn; đa dạng mới quan trọng.
2. Điền `style-card.md`: mỗi mục kèm 1–2 câu trích nguyên văn làm ví dụ.
3. Cho người dùng duyệt từng mục trước khi lưu. Đây là giọng của họ, không phải nhận xét của Claude.
