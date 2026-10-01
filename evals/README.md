# Bộ eval "giữ hiệu suất"

Mục đích: chọn cấu hình model và effort **rẻ nhất mà vẫn giữ chất lượng**, bằng số liệu trên việc giống việc thật của bạn, thay vì đoán.

| Nhóm | Việc | Cách chấm |
|---|---|---|
| Coding | `code-off-by-one`, `code-add-flag`, `code-refactor-dup`, `code-duration` (khó) | Chạy test, kể cả test ẩn; chặn việc sửa file test |
| Đọc tài liệu | `doc-ratelimit`, `doc-multihop`, `doc-decisions` | So đáp án; bẫy số liệu cũ và owner cũ |
| Review bảo mật | `sec-sqli`, `sec-path-traversal`, `sec-secrets` | Phải nêu đúng lỗ hổng; báo nhầm hàm an toàn thì trượt |
| QA | `qa-write-tests` | Mutation: bộ test phải bắt được ít nhất 2 trong 3 lỗi cấy |

Mỗi việc có lời giải mẫu trong `solution/`. Lệnh `--self-test` kiểm rằng grader chấm trượt bản chưa sửa và chấm đạt bản lời giải. Lệnh này không gọi model, không tốn gì.

## Chạy

```bash
python3 evals/run_eval.py --self-test                          # miễn phí
python3 evals/run_eval.py --configs A,C,D --repeats 2          # chỉ in kế hoạch + ước tính
python3 evals/run_eval.py --configs A,C,D --repeats 2 --yes    # chạy thật, tính vào hạn mức
```

- Cấu hình nằm trong `configs.json`: A sonnet·medium, B sonnet·high, C opus·medium, D opus·low, E = A + plugin, H haiku (chỉ để đo trần dưới).
- Mỗi lượt chạy trong một thư mục tạm ở `.tmp/eval/`, với `--setting-sources project` (không nạp hook cá nhân) và `--no-session-persistence`.
- Kết quả ghi ở `evals/results/` (không đưa vào git).
- Cần đăng nhập Claude Code ở terminal trước (`claude /login`).
- Nên chia lượt chạy ra vài ngày để không đốt hạn mức tuần. `--max-total-usd` đặt trần.

## Đọc kết quả

Quy tắc chọn: lấy cấu hình rẻ nhất trong các cấu hình có tỉ lệ đạt không thấp hơn cấu hình tốt nhất quá 1 việc. Hai cấu hình sát nhau thì chạy thêm lượt lặp trước khi chốt. Chốt xong thì ghi vào `routing-table.md` và cập nhật `plugin/skills/task-router/rules.json`.

Hạn chế: 11 việc là ít, và do Claude soạn. Hãy thêm vài việc lấy từ chính công việc của bạn (dữ liệu giả, đặt trong `evals/tasks/`), vì số liệu chỉ đáng tin khi bộ việc giống việc thật.
