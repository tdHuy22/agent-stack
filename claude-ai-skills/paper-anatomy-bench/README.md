# Bench skill paper-anatomy

So hai bản skill trên 7 bài báo thật (5 bài lấy từ thư viện Zotero của bạn, 2 bài ngoài mảng bảo mật thêm từ
16/10/2026), bằng model sonnet. Nhánh (`--arms`): `old` là
bản claude.ai lúc nhập (`.tmp/paper-anatomy-bench/skill-snapshot/`), `v3` là bản 03/10/2026 chụp trước khi sửa v4
(`.tmp/paper-anatomy-bench/skill-v3/`), `new` là bản đang sửa trong `claude-ai-skills/paper-anatomy/`. Kết quả và
cách đọc: `RESULTS.md`.

| Việc | Bài | Kiểu khó |
|---|---|---|
| `struq-full-anatomy` | StruQ (20 trang, hai cột) | giải phẫu đầy đủ một bài phương pháp |
| `pra-rag-theorem-narrow` | PRA-RAG (16 trang) | câu hỏi hẹp về định lý; nhãn trang kỷ yếu 36002… khác số trang PDF |
| `attacker-second-critique` | The Attacker Moves Second (29 trang) | phản biện: tuyên bố có vượt bằng chứng không |
| `camel-long-architecture` | CaMeL (125 trang) | bài dài, phụ lục 95 trang; kiến trúc dựng từ hình |
| `biba-scanned` | Biba 1975 (68 trang scan) | không có lớp chữ, máy không có OCR |
| `roformer-rope-anatomy` | RoFormer (14 trang) | ngoài mảng bảo mật, nặng công thức; người dùng nói mục đích, hỏi đích danh bốn ý |
| `flashattention2-anatomy` | FlashAttention-2 (14 trang) | bài hệ thống GPU, chưa từng dùng làm ví dụ trong skill; hỏi đích danh ba ý |

## Chạy lại

```bash
python3 claude-ai-skills/paper-anatomy-bench/run_bench.py --iteration 4 --arms v3,new          # in kế hoạch, không tốn gì
python3 claude-ai-skills/paper-anatomy-bench/run_bench.py --iteration 4 --arms v3,new --yes --parallel 5
python3 claude-ai-skills/paper-anatomy-bench/grade_bench.py --iteration 4              # phần máy chấm được
python3 claude-ai-skills/paper-anatomy-bench/blind.py prepare --iteration 4 --round 4 --arms v3,new
python3 claude-ai-skills/paper-anatomy-bench/blind.py summary --round 4               # sau khi người chấm xong
```

- CLI `claude` phải đăng nhập (`claude auth status`); chưa đăng nhập thì `run_bench.py` dừng trước khi chạy. Lượt
  lỗi được chạy lại khi chạy lại cùng lệnh; lượt đã xong thì bỏ qua, trừ khi thêm `--force`.

- Mỗi lượt chạy `claude -p --model sonnet --effort medium` trong thư mục tạm ngoài repo, chỉ có file PDF và bản skill
  của nhánh (`skill/`). Không nạp skill nào khác, không MCP, không hook hay plugin của người dùng. `python3` trỏ tới
  `.venv` của repo (có PyMuPDF); không cho `pip`.
- `grade_bench.py` kiểm mọi thẻ neo bằng `verify_anchors.py` trên cùng một bản trích cho cả hai nhánh, đo độ phủ
  trang (trang nào thật sự xuất hiện trong kết quả công cụ), số ảnh trang đã xem, chi phí.
- Phần nội dung do người chấm opus chấm mù theo `grader-prompt.md`: hai câu trả lời đổi tên thành A và B ngẫu nhiên,
  bảng giải mã để ngoài thư mục người chấm đọc. Người chấm tự dựng 8–12 ý chính từ bài trước, kiểm ngẫu nhiên 10
  nhận định mỗi bài, cho điểm 6 tiêu chí, rồi chọn bài sẽ đưa cho người dùng. Tiêu chí thứ sáu, `nam_y_1_phut`
  (từ vòng 4), chấm riêng khoảng 250 từ đầu: đọc chừng đó đã biết bài làm gì và đứng vững tới đâu chưa.
  `blind.py prepare` dựng đề (`blind-<vòng>/<việc>/prompt.md`, mỗi đề giao một người chấm opus) và lấy ý chính
  của lần chấm trước làm gợi ý; `blind.py summary` giải mã và in bảng điểm.
- Bài làm, transcript và kết quả chấm nằm trong `.tmp/paper-anatomy-bench/` (không đưa vào git).
