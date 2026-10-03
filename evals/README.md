# Bộ eval "giữ hiệu suất"

Mục đích: chọn cấu hình model và effort **rẻ nhất mà vẫn giữ chất lượng**, bằng số liệu trên việc giống việc thật của bạn, thay vì đoán.

| Nhóm | Việc | Cách chấm |
|---|---|---|
| Coding | `code-off-by-one`, `code-add-flag`, `code-refactor-dup`, `code-duration` (khó) | Chạy test, kể cả test ẩn; chặn việc sửa file test |
| Đọc tài liệu | `doc-ratelimit`, `doc-multihop`, `doc-decisions` | So đáp án; bẫy số liệu cũ và owner cũ |
| Review bảo mật | `sec-sqli`, `sec-path-traversal`, `sec-secrets` | Phải nêu đúng lỗ hổng; báo nhầm hàm an toàn thì trượt |
| QA | `qa-write-tests` | Mutation: bộ test phải bắt được ít nhất 2 trong 3 lỗi cấy |
| Viết | `write-vn-rewrite` | Giữ đủ 5 sự kiện, xưng "mình", điểm dấu hiệu văn AI (`tells.py`) giảm ít nhất 60% |
| Debug khó (03/10/2026) | `debug-multifile`: 4 nguyên nhân ở 4 file, test có sẵn chỉ lộ 1; `debug-race`: race, deadlock khi khóa không thứ tự, tự chuyển cho chính mình | Test ẩn theo SPEC; sửa thiếu file nào cũng trượt. Race: chạy tải nặng trong tiến trình con có hạn giờ, đo song song, không cho khóa chung |
| Review diff thật (03/10/2026) | `review-diff`: PR có 4 lỗi đưa vào và 3 thay đổi đúng trông đáng ngờ | Phải nêu đủ 4 lỗi theo dạng `LỖI n: file:hàm — …`; nêu thay đổi đúng là lỗi thì trượt |
| Đặc tả nhiều ca biên (03/10/2026) | `code-cron-next` (khó), `code-async-pool` và `code-unified-diff` (rất khó) | Cron: luật OR ngày/thứ, 29/2, không bao giờ khớp, < 0,5 giây. Pool asyncio: 8 kịch bản hủy, hết giờ, kết nối hỏng, `close()`. Diff: tối thiểu (so LCS), áp lại ra đúng file, khớp `diff -u` ở 13 ca chuẩn, 5.000 dòng < 2 giây |

Mỗi việc có lời giải mẫu trong `solution/`. Lệnh `--self-test` kiểm rằng grader chấm trượt bản chưa sửa và chấm đạt bản lời giải. Lệnh này không gọi model, không tốn gì.

## Chạy

```bash
python3 evals/run_eval.py --self-test                          # miễn phí
python3 evals/run_eval.py --configs A,C,D --repeats 2          # chỉ in kế hoạch + ước tính
python3 evals/run_eval.py --configs A,C,D --repeats 2 --yes    # chạy thật, tính vào hạn mức
```

- Cấu hình nằm trong `configs.json`: A sonnet·medium, B sonnet·high, C opus·medium, D opus·low, E = A + plugin, H haiku (chỉ để đo trần dưới).
- Mỗi lượt chạy trong thư mục tạm của hệ điều hành, **ngoài agent-stack**, nên model không đọc được `CLAUDE.md` của repo, grader (`check.py`) hay lời giải. Nếu `--work-root` nằm trong repo hoặc dưới một thư mục có `CLAUDE.md`/`AGENTS.md`, script từ chối chạy.
- Chạy với `--setting-sources project` (không nạp hook cá nhân) và `--no-session-persistence`. File `evals/results/<thời điểm>.meta.json` ghi điều kiện chạy: commit, phiên bản CLI và plugin, dấu vân tay từng việc, và có `~/.claude/CLAUDE.md` hay không.
- Bài làm được chốt ngay khi lượt chạy kết thúc: patch nằm trong `evals/results/<thời điểm>/`, câu trả lời nằm trong file JSONL (không đưa vào git). Thư mục tạm bị xóa sau khi chấm, trừ khi có `--keep-workdirs`.
- Cần đăng nhập Claude Code ở terminal trước (`claude /login`).
- Nên chia lượt chạy ra vài ngày để không đốt hạn mức tuần. `--max-total-usd` đặt trần.

## Đọc kết quả

Quy tắc chọn: lấy cấu hình rẻ nhất trong các cấu hình có tỉ lệ đạt không thấp hơn cấu hình tốt nhất quá 1 việc. Hai cấu hình sát nhau thì chạy thêm lượt lặp trước khi chốt. Chốt xong thì ghi vào `routing-table.md` và cập nhật `plugin/skills/task-router/rules.json`.

Script chỉ chốt khi ma trận đủ:
- mọi cấu hình có cùng số lượt cho mọi việc;
- không lượt nào hỏng vì môi trường (chưa đăng nhập, hết hạn mức);
- mọi lượt dùng cùng đề bài và cùng grader.

Lượt hỏng vì vận hành (hết giờ, chạm trần chi phí) vẫn tính là trượt và được đếm riêng ở cột "Lỗi vận hành".

```bash
python3 evals/run_eval.py --report evals/results/*.jsonl   # gộp các lần chạy ở nhiều ngày
python3 evals/run_eval.py --regrade evals/results/X.jsonl  # đổi grader thì chấm lại bài đã chốt trước khi so
```

Self-test chỉ chứng minh grader đúng. Nó không phải số liệu về model.

Hạn chế: 18 việc là ít, và do Claude soạn. Hãy thêm vài việc lấy từ chính công việc của bạn (dữ liệu giả, đặt trong `evals/tasks/`), vì số liệu chỉ đáng tin khi bộ việc giống việc thật.
