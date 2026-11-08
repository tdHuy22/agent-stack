# Bộ bài tiếng Việt (vi-bench)

30 bài tự viết để đo agent-stack khi giao việc cho Claude Code bằng tiếng Việt. Bạn chốt ngày 08/11/2026, theo trang đề xuất `.agent/trang/bench-tieng-viet.html`.

| Nhóm | Tiền tố | Đo gì |
|---|---|---|
| Sửa code theo đề tiếng Việt | `code-` | Hiểu đề tiếng Việt và nghiệp vụ Việt Nam: số tiền `1.234.567,5`, ngày dd/mm/yyyy, làm tròn đồng, tên tỉnh gõ tay |
| Xử lý chữ tiếng Việt | `chu-` | Thứ tự từ điển, dấu thanh, chữ `đ`, dạng NFD, đọc số thành chữ |
| Viết văn bản tiếng Việt | `viet-` | Số liệu đúng (tính từ dữ liệu), đúng người đọc, đủ mục, không văn AI, không chữ Anh thừa |

- Mỗi bài theo định dạng Harbor (như TBLite): `task.toml`, `instruction.md`, `environment/` (Dockerfile và thư mục `app/`), `tests/` (`test.sh`, `check.py`, `vncheck.py`), `solution/solve.sh`. Bài chạy chung job với bốn cấu hình trên máy Linux (xem `evals/harbor/README.md`).
- Chấm hoàn toàn bằng script, không gọi model. Mọi luật nghiệp vụ nằm trong đề. Đáp án trong `check.py` được ghi cứng, không chép logic từ lời giải mẫu.
- `Dockerfile` và `test.sh` của mọi bài giống hệt bản trong `_lib/`: image `python:3.12-slim`, chỉ thư viện chuẩn, không gọi mạng lúc dựng hay lúc chấm.
- `_lib/vncheck.py` là thư viện chấm chung (NFC, chữ thiếu dấu, câu tiếng Anh, số có phân cách nghìn). Mỗi bài chép nguyên file này vào `tests/`.
- Dấu hiệu văn AI không làm trượt bài (bạn chốt 08/11/2026). Danh sách mẫu chép cố định từ skill `writing-voice`; ba cấu hình có agent-stack thấy đúng danh sách đó, bản trơn thì không, nên chấm trượt theo nó là chấm vòng. Số lần gặp được ghi thành chỉ số phụ `van_ai` trong `reward.json` (cạnh `reward`), và `tuf.sh compare` in trung bình của chỉ số này cho mỗi cấu hình.
- `solution/dat-khac/<n>/` và `solution/truot/<n>/` là bài làm mẫu khác lời giải: chép đè lên `app/`, phải đạt (bài đúng viết kiểu khác) hay phải trượt (lỗi agent hay mắc). `selftest.py` chạy cả hai, để bài chấm không ép một cách diễn đạt.

## Tự kiểm (không cần Docker, không gọi model)

```bash
python3 evals/vi-bench/selftest.py -v                       # mọi bài
python3 evals/vi-bench/selftest.py -v code-phi-ship         # một bài
```

Với mỗi bài, script kiểm cấu trúc, rồi chép `environment/app/` vào thư mục tạm. Bài chấm phải trượt trên bản chưa làm. Sau đó script chạy `solution/solve.sh`, và bài chấm phải đạt. Cuối cùng script chạy các bài làm mẫu trong `solution/dat-khac/` và `solution/truot/`. `tests/test_vi_bench.py` gọi lệnh này cho cả 30 bài, đòi đúng 10 bài mỗi nhóm.

## Chạy trên máy Linux

1. Commit thay đổi trong `evals/vi-bench/`, rồi chạy `evals/harbor/tuf.sh sync` (lệnh này lấy bản của HEAD).
2. `evals/harbor/tuf.sh data vi`: gom bài vào `datasets/vi`, ghim mã băm theo commit, kiểm an toàn.
3. `evals/harbor/tuf.sh oracle vi --yes`: chạy lời giải mẫu trong container, trên danh sách `evals/harbor/tasks-vi.txt`.
4. Bài tiếng Việt đã nằm trong `tasks-candidates.txt`. Chạy `tuf.sh filter` để đưa bài có lời giải mẫu đạt vào `tasks-main.txt`. Pilot và job lớn chạy chúng cùng bài tiếng Anh. `tuf.sh compare` in thêm một bảng riêng cho bài tiếng Việt.

## Thêm hay sửa bài

Chép một bài cùng nhóm làm khuôn. Đổi `name` trong `task.toml` thành `agent-stack/<thư mục>`. Thêm tên bài vào `evals/harbor/tasks-vi.txt` và `tasks-candidates.txt`. Chạy `selftest.py` cho tới khi đạt. Thử ít nhất hai bài làm sai mà agent hay mắc, và ghi chúng ở đầu `check.py`. Sửa bài đã chạy thì mã băm đổi; `harbor_bench.py compare` sẽ từ chối gộp kết quả của hai phiên bản bộ bài.
