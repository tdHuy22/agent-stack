# Hướng dẫn chấm (một việc, hai câu trả lời ẩn danh A và B)

Bạn chấm hai câu trả lời cho cùng một yêu cầu của người dùng về một bài báo khoa học. Hai câu trả lời do hai cấu
hình khác nhau tạo ra; bạn không biết cái nào là cái nào và không được đoán. Chỉ đọc đúng các file được liệt kê
bên dưới. Không mở thư mục nào khác trong `.tmp/paper-anatomy-bench/` (sẽ làm lộ danh tính A/B).

## Đầu vào
- Yêu cầu của người dùng: {prompt}
- Bài báo: văn bản theo trang ở `{paper_txt}` (mốc `===== PAGE i/N · tr.<nhãn> =====`; nhãn là số trang in).
  {paper_note}
- Câu trả lời A: `{answer_a}`
- Câu trả lời B: `{answer_b}`
- Ý chính gợi ý của người ra đề (kiểm lại với bài, sửa nếu sai): {seed_facts}

## Bước 1: dựng đáp án trước khi đọc câu trả lời
Đọc bài báo (đủ để trả lời đúng yêu cầu của người dùng; với bài dài, đọc thân bài và phần phụ lục liên quan).
Viết 8–12 **ý chính** mà một câu trả lời xuất sắc cho đúng yêu cầu này phải có, mỗi ý kèm vị trí trong bài.
Ưu tiên ý quyết định việc hiểu đúng (cơ chế, giả định, giới hạn, con số then chốt), không phải chi tiết vụn.

## Bước 2: chấm từng câu trả lời
Với mỗi ý chính: `đủ` (nêu đúng), `một phần`, `thiếu`, hoặc `sai` (nêu sai so với bài).

Kiểm chứng ngẫu nhiên 10 nhận định của mỗi câu trả lời, ưu tiên nhận định trung tâm và con số: tra đúng vị trí
được neo (và tìm trong cả bài nếu không thấy ở đó). Mỗi nhận định: `đúng`, `sai`, `neo sai chỗ` (nội dung đúng
nhưng vị trí sai), hoặc `không có trong bài` (bịa hoặc lấy từ ngoài mà không nói rõ). Ghi thêm mọi chỗ bịa hay
sai khác bạn thấy khi đọc.

Cho điểm 1–5:
- `trung_thuc`: không bịa, không phóng đại, tách rõ suy luận của người phân tích với điều bài nói;
- `do_sau`: giải thích cơ chế và *vì sao*, không chỉ *cái gì*; người đọc có hình dung được cách tái lập;
- `dung_cau_hoi`: trả lời đúng điều người dùng hỏi, đúng độ rộng (câu hỏi hẹp thì tập trung);
- `kiem_chung`: người đọc lật PDF kiểm được từng ý quan trọng nhanh và chính xác;
- `de_doc`: tiếng Việt rõ, thuật ngữ gốc giữ đúng, bố cục giúp hiểu.

## Bước 3: so sánh
Chọn câu trả lời bạn sẽ đưa cho người dùng (`A`, `B` hoặc `hoa`), mức chênh (`ro` hoặc `it`), và lý do 2–4 câu.
Độ dài không phải là ưu điểm tự thân.

## Đầu ra
Ghi đúng một file JSON vào `{out_file}` theo dạng:

```json
{{
  "key_facts": [{{"id": 1, "fact": "...", "where": "tr.…"}}],
  "answers": {{
    "A": {{
      "facts": [{{"id": 1, "status": "đủ|một phần|thiếu|sai", "note": "..."}}],
      "spot_checks": [{{"claim": "...", "anchor": "...", "verdict": "đúng|sai|neo sai chỗ|không có trong bài", "note": "..."}}],
      "other_errors": ["..."],
      "scores": {{"trung_thuc": 0, "do_sau": 0, "dung_cau_hoi": 0, "kiem_chung": 0, "de_doc": 0}},
      "strengths": "...", "weaknesses": "..."
    }},
    "B": {{"...": "giống A"}}
  }},
  "preference": "A|B|hoa", "margin": "ro|it", "reason": "..."
}}
```

Trả lời cuối cùng (ngắn): đã ghi file, chọn ai, tỉ lệ ý chính `đủ` của A và B.
