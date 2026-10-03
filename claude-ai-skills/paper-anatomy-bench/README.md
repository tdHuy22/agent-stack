# Bench skill paper-anatomy

So bản skill cũ (bản claude.ai lúc nhập, chép ở `.tmp/paper-anatomy-bench/skill-snapshot/`) với bản mới trong
`claude-ai-skills/paper-anatomy/`, trên 5 bài báo thật lấy từ thư viện Zotero của bạn, bằng model sonnet. Kết quả và
cách đọc: `RESULTS.md`.

| Việc | Bài | Kiểu khó |
|---|---|---|
| `struq-full-anatomy` | StruQ (20 trang, hai cột) | giải phẫu đầy đủ một bài phương pháp |
| `pra-rag-theorem-narrow` | PRA-RAG (16 trang) | câu hỏi hẹp về định lý; nhãn trang kỷ yếu 36002… khác số trang PDF |
| `attacker-second-critique` | The Attacker Moves Second (29 trang) | phản biện: tuyên bố có vượt bằng chứng không |
| `camel-long-architecture` | CaMeL (125 trang) | bài dài, phụ lục 95 trang; kiến trúc dựng từ hình |
| `biba-scanned` | Biba 1975 (68 trang scan) | không có lớp chữ, máy không có OCR |

## Chạy lại

```bash
python3 claude-ai-skills/paper-anatomy-bench/run_bench.py --iteration 3                 # in kế hoạch, không tốn gì
python3 claude-ai-skills/paper-anatomy-bench/run_bench.py --iteration 3 --yes --parallel 5
python3 claude-ai-skills/paper-anatomy-bench/grade_bench.py --iteration 3              # phần máy chấm được
```

- Mỗi lượt chạy `claude -p --model sonnet --effort medium` trong thư mục tạm ngoài repo, chỉ có file PDF và bản skill
  của nhánh (`skill/`). Không nạp skill nào khác, không MCP, không hook hay plugin của người dùng. `python3` trỏ tới
  `.venv` của repo (có PyMuPDF); không cho `pip`.
- `grade_bench.py` kiểm mọi thẻ neo bằng `verify_anchors.py` trên cùng một bản trích cho cả hai nhánh, đo độ phủ
  trang (trang nào thật sự xuất hiện trong kết quả công cụ), số ảnh trang đã xem, chi phí.
- Phần nội dung do người chấm opus chấm mù theo `grader-prompt.md`: hai câu trả lời đổi tên thành A và B ngẫu nhiên,
  bảng giải mã để ngoài thư mục người chấm đọc. Người chấm tự dựng 8–12 ý chính từ bài trước, kiểm ngẫu nhiên 10
  nhận định mỗi bài, cho điểm 5 tiêu chí, rồi chọn bài sẽ đưa cho người dùng.
- Bài làm, transcript và kết quả chấm nằm trong `.tmp/paper-anatomy-bench/` (không đưa vào git).
