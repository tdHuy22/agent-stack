# PLAN: triển khai agent-stack

**Đây là nguồn sự thật DUY NHẤT về tiến độ triển khai.** Thiết kế chi tiết ở `KE-HOACH.md`; file này chỉ ghi đang ở đâu và việc gì tiếp theo.

## 0. Đang ở đâu, việc tiếp theo (cập nhật mỗi lần dừng phiên)

- **Tiến độ (20/11/2026):** GĐ1–GĐ6 xong; GĐ7 (đo lại sau khoảng 2 tuần dùng thật) sau 24/11, cùng hai mục @cho dưới. `origin/main` = `0d86a4f`; `main` đi trước nhiều commit chưa push. Plugin nạp tại chỗ từ `plugin/` (README mục 5.4), nên ba commit chiều 20/11 (gỡ `remote-mcp`, `recursive-session` thành lệnh người dùng gõ, rút §0) có hiệu lực ở phiên mới hay sau `/reload-plugins`; version vẫn 0.23.0, `install.sh --apply` chỉ còn để ghi `INSTALLED.md`, chạy khi bạn duyệt. Toàn văn §0 trước lần rút này (gỡ pi, việc E, F1, F2a, F2b, H, H4, mốc kiểm tra cũ): `.agent/NHAT-KY.md`, đợt "20/11/2026, rút §0 bằng tay".
- **Xong 19–20/11/2026 (chi tiết ở nhật ký):** gỡ hỗ trợ pi (plugin 0.22.0; khôi phục từ `b1684c3`); F1 `narrow.py` chọn test theo file (`17c0c65`, `0e2ef39`, `facd397`); F2a `narrow.py full` chạy cả bộ song song; F2b chạy test, mutation trên TUF qua SSH (`868108f`; TUF nhanh hơn khoảng 1,75 lần cho mutation, không nhanh hơn cho cả bộ); E skill `recursive-session`, nay là lệnh người dùng gõ đầu phiên điều hành (`disable-model-invocation: true`, kiểm bằng docs và binary app 2.1.326); H đếm dùng thật 14 ngày và eval có/không skill cho 14 skill (khoảng 19,9 USD credit API; số và ghi chú `.tmp/h/eval/GHI-CHU-H.md`, ngoài git); H4 Aside so với Browser (Aside làm được cả 3 việc mẫu); gộp `remote-mcp` vào luật chung, gỡ skill và `call.py` (0 lần dùng 14 ngày).
- **Bạn chốt 20/11/2026 cho việc H5 (sáu mục đề xuất và việc chờ):**
  1. Bộ "gọn": làm theo khuyến nghị nhưng chia nhiều bộ hơn; Claude Code tự bật bộ cần trong lúc làm, hoặc bạn bật đầu phiên, hoặc phiên điều hành bật cho phiên con. Phiên riêng, chưa làm.
  2. Giữ `session-keeper`, `done-gate`, `progress`, `project-setup`, `reuse-best`, `writing-voice`, `kaggle-gpu`.
  3. `threat-model`, `vet-skill`: eval thêm với việc khó, xem thay được bằng lời dặn `CLAUDE.md` hay lời nhắc không (đang chạy ở phiên H3b).
  4. Sửa `reader-page`, `task-router`, `done-gate` (mỗi skill một phiên, chưa làm) và `recursive-session` (xong 20/11).
  5. Gộp `remote-mcp` vào luật chung (xong 20/11).
  6. Tắt Browser của app: bạn tự tắt ở Settings → Claude Code → Browser (app không cho agent đổi).
  7. Việc đang chờ (push, `tuf-config`, khóa lại `tests/test_remote.py`, đột biến sống, lỗ hook ở `plugin/lib/agentstack.py:788`): bạn giao phiên điều hành quyết.
- **Đang dở (20/11/2026):** phiên H3b eval `threat-model`, `vet-skill` với việc khó (chỉ ghi trong `.tmp/h/eval/`); việc 0 bên dưới.
- **Việc tiếp theo, theo thứ tự:**
  0. Việc 0 (tám quan sát): phân loại 180 đột biến sống của mutation 18/11 (kết quả `.tmp/mut0.json`, khóa `survived`), thêm test cho chỗ đáng, thêm `EQUIVALENT` vào file test mới, done-gate, commit. Cách dựng lại bản chép và các việc treo kèm (SCEE MW1, GĐ7 lớp model, `project-setup`, archctl): nhật ký.
  1. H5 phần còn lại theo mục "Bạn chốt" ở trên: chia bộ "gọn" và cách bật; sửa `reader-page`, `task-router`, `done-gate`; đọc kết quả H3b.
  2. Lỗ có từ trước của chốt chặn test khóa (review opus·xhigh 18/11: subshell và ống làm `cd` lọt, `env -C`, tên viết hoa khác, ngoặc nhọn nhiều tầng làm hook quá giờ, `--project $PWD/tests`, `HOME=`, `CDPATH`, `2>` trong `receipt.py unlock`; danh sách đủ ở nhật ký) và lỗ `plugin/lib/agentstack.py:788` (tin mở đầu phiên con bị coi là lời người dùng, nên `mở khóa …` chép vào brief có thể qua hook).
  3. Tối ưu mutation thêm: xếp test theo thời gian chạy tăng dần, số lần chạy song song theo số lõi thật, đo trước chi phí từng phần; kiểm như việc 1 (việc A vẫn 146 bắt, 3 sống; mốc 747,6 giây).
  4. Việc chờ phiên điều hành quyết (mục 7 ở trên): push `main`; `~/tuf-config/CHECKPOINT.md` mục A42 chưa `sync.sh`, chưa push; khóa lại `tests/test_remote.py` (mở khóa sửa fixture rồi không khóa lại được, `spec.py check` ✗ cho f2b); đột biến sống F1 `pretool_guard.py:1261`, `:1193`, `post_edit.py:228`, `route.py:961`.
  5. @cho Khoảng 24/11/2026: đo lại hạn mức bằng `python3 tools/usage_report.py`, so với mốc 10/11 (14 ngày: 88,6 triệu đơn vị; một phiên dài 47%; subagent review 14%). Giảm rõ thì giữ hook nhắc phiên dài và luật gọn; không giảm thì xem lại.
  6. @cho Sau khoảng 2 tuần dùng bảng reviewer mới (hay khi mỗi ô có khoảng 10 lần review): `python3 plugin/skills/done-gate/scripts/review_log.py summary`, so từng ô mới với mốc cũ (các mốc ở nhật ký), kèm hạn mức tuần; ô nào không tìm thêm lỗi thì hạ về cấu hình cũ.
- **Ghi nhớ (đã xong, không phải việc):** bỏ bench agent-stack/pi-agent trên Harbor/TBLite (02/11, lời bạn); `static-analysis` vá cục bộ `patches/static-analysis/` cho upstream issue #297 (còn mở 13/11; PR #352 bị đóng 27/10 vì người gửi chưa ký CLA, upstream vẫn còn lỗi ở `run-scans.sh:556`), xoá khi upstream sửa; `writing-voice` có mẫu mặc định, mẫu riêng làm trong project viết luận. Chi tiết: `.agent/NHAT-KY.md`.
- **Đã quyết:** bộ chọn test tự làm bằng bộ ghi vết (`plugin/lib/linetrace.py`), không dùng pytest-testmon hay coverage.py; `narrow.py` chọn theo file; chấp nhận TM-160 (biên nhận `narrow.py full` tính là cả bộ, chạy tuần tự một lần trước `install.sh --apply`); done-gate review lại tối đa 2 vòng, đột biến sống chỉ ghi lại. Cũ hơn (bộ duyệt web, paper-anatomy, Trail of Bits): nhật ký.
- **Mốc kiểm tra:** chạy qua `python3 plugin/skills/session-keeper/scripts/receipt.py run -- <lệnh>` để có biên nhận.
  - `python3 plugin/skills/session-keeper/scripts/narrow.py full` (cùng tập với `python3 -m unittest discover -s tests -t .`, chỉ Python 3.11) → đạt, 2169 test (20/11/2026, 434 giây, 4 tiến trình); `biome.json` lồng trong repo làm `test_biome_clean` trượt.
  - `"$(python3 tools/claude_app.py)" plugin validate plugin` → `Validation passed with warnings` (cảnh báo kiểu TS ở `plugin/tests/ui.test.tsx` và thiếu icon, có từ trước GĐ5)
  - `"$(python3 tools/claude_app.py)" plugin test plugin` → 26 pass (20/11/2026)
  - `python3 tools/rulebook.py` → sổ luật không lỗi; `python3 plugin/skills/session-keeper/scripts/receipt.py locks` → test khóa "không đổi"
  - `python3 evals/run_eval.py --self-test` → 24 dấu ✓ (12/10/2026)
  - `python3 plugin/skills/task-router/scripts/route.py --eval evals/router-prompts.jsonl` → 117/117 (20/11/2026)
- **Sau khi bị ngắt:** chạy `git -C ~/Documents/Claude/agent-stack status -sb` (phải khớp `origin/main` nếu không có việc dở), `git log --oneline -5`, `python3 plugin/skills/session-keeper/scripts/receipt.py show` và `claude plugin list`, rồi đọc `INSTALLED.md` và mục này.

## 1. Giai đoạn
