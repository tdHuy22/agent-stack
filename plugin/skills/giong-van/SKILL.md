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

- Style card (đặc điểm giọng văn của người dùng): trong project viết luận, dùng `.agent/giong-van/style-card.md` của project nếu có; không thì `${CLAUDE_SKILL_DIR}/style-card.md`. Nếu cả hai còn trống, đề nghị chế độ `tao-style-card`.
- Bài mẫu, `tells.py` tự chọn theo thứ tự và báo đã dùng bộ nào:
  1. `.agent/giong-van/samples/` của project: mẫu người dùng thêm cho từng project viết luận.
  2. Bài người dùng tự viết đặt thẳng trong `${CLAUDE_SKILL_DIR}/samples/` (không đưa vào git).
  3. `${CLAUDE_SKILL_DIR}/samples/kinh-dien/vi` hoặc `en`: 5 bài văn học kinh điển mỗi ngôn ngữ, thuộc phạm vi công cộng; danh sách và nguồn ở `samples/kinh-dien/README.md`. Đây là văn của người viết thật để tham khảo nhịp câu, chi tiết cụ thể, cách mở và kết. Đó không phải giọng của người dùng, nên đừng bắt chước giọng riêng của một tác giả.
- `${CLAUDE_SKILL_DIR}/vi-ai-tells.md`: dấu hiệu văn AI trong tiếng Việt, cách sửa, và nguồn nghiên cứu.
- `${CLAUDE_SKILL_DIR}/scripts/tells.py`: dò dấu hiệu, so từ vựng với bài mẫu cùng ngôn ngữ, cho điểm trên 1.000 từ. Chạy script và dùng kết quả; chỉ đọc mã nguồn khi kết quả không đủ để sửa.

Nếu `${CLAUDE_SKILL_DIR}` không được thay bằng đường dẫn thật (ví dụ khi đọc thẳng file này ngoài plugin), dùng `~/Documents/Claude/agent-stack/plugin/skills/giong-van/`.

## Chỉnh một văn bản

1. Đọc style card (của project nếu có) và `vi-ai-tells.md`.
2. Lưu văn bản vào một file tạm và chạy `python3 <tells.py> <file>` từ thư mục project (hoặc thêm `--project <thư mục project>`) để lấy điểm trước khi sửa. Script tự chọn bài mẫu như trên.
3. Sửa nội dung trước. Mỗi câu khẳng định cần dựa trên chi tiết có trong văn gốc: câu thổi phồng thì thay bằng con số hoặc ví dụ có sẵn, ý kiến của "chuyên gia" thì ghi rõ là ai, câu bình luận chung chung thì bỏ. Chỉ dùng sự kiện, số liệu, tên người và trích dẫn có trong văn gốc; chỗ nào thiếu thì hỏi người dùng.
4. Sau đó sửa câu chữ theo `vi-ai-tells.md` và các dòng `tells.py` báo. Từ bị đánh dấu "không giống bài mẫu" thì đổi sang cách nói người dùng hay dùng; nếu script đang so với văn kinh điển thì nói cụ thể hơn, nhưng giữ thuật ngữ cần cho chủ đề.
5. Đưa văn về giọng trong `style-card.md`: cách xưng hô, độ dài câu, mức trang trọng, từ quen dùng. Giữ thành ngữ, cách nói và lối lập luận quen thuộc của người viết, kể cả khi chúng khác khuôn viết tiếng Anh. Xen câu ngắn với câu dài; các đoạn không cần dài bằng nhau.
6. Chạy lại `tells.py`. Điểm cần giảm, nhưng ý của văn gốc quan trọng hơn con số: dừng khi sửa tiếp sẽ làm mất ý.

Viết bản sửa thành đoạn văn liền mạch, theo đúng định dạng của văn gốc: văn gốc là đoạn văn thì trả về đoạn văn, văn gốc có danh sách thì giữ danh sách. Sau bản sửa, báo ngắn gọn: tối đa 5 thay đổi chính, mỗi thay đổi một dòng; điểm trước và sau; và những chỗ cần người dùng xác nhận.

Với văn tiếng Anh, dựa vào nhóm dấu hiệu tiếng Anh trong `tells.py`.

## Chế độ `tao-style-card`

1. Đọc khoảng 5 bài mẫu, càng khác loại càng tốt. Trong project viết luận, lấy từ `.agent/giong-van/samples/` của project; ngoài ra lấy từ bài tự viết trong `samples/`, hoặc từ đường dẫn người dùng đưa. Thêm bài ít khi giúp bắt chước tốt hơn; đa dạng mới quan trọng. Không tạo style card từ văn kinh điển: đó không phải giọng của người dùng.
2. Điền style card, mỗi mục kèm 1–2 câu trích nguyên văn làm ví dụ. Mẫu của project thì ghi vào `.agent/giong-van/style-card.md` của project (chép khung từ `${CLAUDE_SKILL_DIR}/style-card.md`); bài tự viết chung thì ghi vào `${CLAUDE_SKILL_DIR}/style-card.md`.
3. Cho người dùng duyệt từng mục trước khi lưu. Đây là giọng của họ, không phải nhận xét của Claude.

## Project viết luận mới

Mỗi project viết luận có bộ mẫu riêng. Khi bắt đầu, tạo `.agent/giong-van/samples/` trong project và nhờ người dùng đặt vào 3–5 bài cùng thể loại, có thể là bài của họ hoặc bài họ muốn viết theo. Cần ít nhất 500 từ cùng ngôn ngữ với bài sẽ viết. Rồi chạy `tao-style-card` cho project. Chưa có mẫu thì `tells.py` so với văn kinh điển cùng ngôn ngữ và nhắc chỗ đặt mẫu.
