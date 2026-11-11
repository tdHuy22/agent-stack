# PLAN: triển khai agent-stack

**Đây là nguồn sự thật DUY NHẤT về tiến độ triển khai.** Thiết kế chi tiết ở `KE-HOACH.md`; file này chỉ ghi đang ở đâu và việc gì tiếp theo.

## 0. Đang ở đâu, việc tiếp theo (cập nhật mỗi lần dừng phiên)

- **Xong (11/11/2026): hook push nhận tên repo/nhánh** (`c9029d2`): "Push <tên repo/nhánh>" tính là lời đồng ý; test phủ định của `PreConsentGuard` kiểm thật.
- **Xong (10–11/11/2026): bảng reviewer mới đã cài** (`822b549`, `00697e4`): mức cao khi Opus viết → fable·high + sonnet·high; cao đụng bảo mật → opus·xhigh + sonnet·xhigh; mức thấp có code → sonnet·medium (Opus/Fable viết) hay opus·low (Sonnet/Haiku viết), tự bỏ khi hạn mức tuần ≥80%; Sonnet viết mức vừa → opus·high; file chỉ dẫn agent tính như code; `review_log.py` ghi effort. Đo lại ở việc 3 bên dưới. `~/.claude/CLAUDE.md` đã có câu mới (nạp lại 11/11).
- **Xong (11/11/2026): Aside nhận Fable 5.2** (`a020a6b`; `aside models` liệt kê `claude-code/claude-fable-5-2`, 39 test aside đạt). Hai trang `.agent/trang/` còn sót đã commit (`ddaa6c7`); §0 rút 18K → 4K ký tự, lịch sử sang `.agent/NHAT-KY.md` (đợt 11/11).
- **Xong (11/11/2026): dọn phần OpenCode còn sót** (eval `handoff-opencode` → `handoff-cross-tool`; `7b1deca`).
- Chi tiết phần đã chuyển (cả các mục Xong 04–11/11, rà soát, trang đã commit, bench Harbor, bảng routing Fable 5.2): `.agent/NHAT-KY.md` mục 11/11/2026; cũ hơn cũng ở đó (`state.py trim`).
- **Việc tiếp theo, theo thứ tự:**
  1. Tùy chọn, không cài cũng không hỏng gì: `brew install gitleaks osv-scanner` (không code nào gọi).
  2. @cho Khoảng 24/11/2026: đo lại hạn mức bằng `python3 tools/usage_report.py`, so với mốc 10/11 (14 ngày: 88,6 triệu đơn vị; một phiên dài 47%; subagent review 14%; context TB 180–300 nghìn token mỗi lần gọi ở các phiên dài). Giảm rõ thì giữ hook nhắc phiên dài và luật gọn; không giảm thì xem lại.
  3. @cho Sau khoảng 2 tuần dùng bảng reviewer mới (hay khi mỗi ô mới có khoảng 10 lần review): đánh giá lại bằng `python3 plugin/skills/done-gate/scripts/review_log.py summary`. So từng ô mới với mốc cũ: fable·high với opus·high (lỗi tìm riêng khi Opus viết, mốc 68 lỗi Opus tìm riêng trên 40 lần review kép), sonnet·xhigh với sonnet·high (mốc 116), opus·xhigh với opus·high ở mức cao đụng bảo mật, review mức thấp (bao nhiêu lỗi thật trên mỗi lần), opus·high với opus·medium khi Sonnet viết mức vừa. Kèm chi phí: hạn mức tuần (`tools/usage_report.py`). Ô nào không tìm thêm lỗi thì hạ về cấu hình cũ.
- **Ghi nhớ (đã xong, không phải việc):** bỏ bench agent-stack/pi-agent trên Harbor/TBLite (02/11, lời bạn); `static-analysis` vá cục bộ `patches/static-analysis/` cho upstream #297, xoá khi PR #352 gộp; `writing-voice` có mẫu mặc định, mẫu riêng làm trong project viết luận. Chi tiết: `.agent/NHAT-KY.md`.
- **Đã quyết:** bạn xác nhận 11/10: 3 skill Trail of Bits còn lại và `cloudflare/security-audit-skill` chỉ vet khi cần; bộ duyệt web A2, B1 (Exa cài, Parallel và DeepWiki qua `remote-mcp`). paper-anatomy (17/10): giữ v4.4, bỏ v4.3, commit `6504f8d`, claude.ai vẫn v3. Chi tiết: `.agent/NHAT-KY.md`.
- **Mốc kiểm tra:** chạy qua `python3 plugin/skills/session-keeper/scripts/receipt.py run -- <lệnh>` để có biên nhận.
  - `python3 -m unittest discover -s tests -t .` (chỉ Python 3.11) → `OK`, 1239 test (10/11/2026); `python3` có PyMuPDF nên test của paper-anatomy chạy luôn (máy thiếu PyMuPDF thì bỏ qua 1 test, chạy riêng bằng `.venv/bin/python -m unittest tests.test_paper_anatomy`)
  - `"$(python3 tools/claude_app.py)" plugin validate plugin` → `Validation passed` (binary của app; `claude` brew 2.1.292 cũng đạt)
  - `"$(python3 tools/claude_app.py)" plugin test plugin` → 24 pass (04/11/2026)
  - `python3 evals/run_eval.py --self-test` → 24 dấu ✓ (12/10/2026)
  - `python3 plugin/skills/task-router/scripts/route.py --eval evals/router-prompts.jsonl` → 109/109 (04/11/2026)
- **Sau khi bị ngắt:** chạy `git -C ~/Documents/Claude/agent-stack status -sb` (phải khớp `origin/main` nếu không có việc dở), `git log --oneline -5`, `python3 plugin/skills/session-keeper/scripts/receipt.py show` và `claude plugin list`, rồi đọc `INSTALLED.md` và mục này.

## 1. Giai đoạn

#### GĐ30: File cho người đọc viết bằng HTML (01/11/2026)
Bạn chọn hướng B, ý (b) ngày 01/11/2026 (trang so sánh: https://claude.ai/artifact/V9dUnzLxS6kw5iBtSM1rWX): mọi file cho người đọc là HTML, chỉ file bắt buộc mới giữ `.md`; tích hợp skill có sẵn của Anthropic, thiếu thì tự viết. Quyết định reuse-best: không có skill chính thức nào làm đúng việc này (bài blog của đội Claude Code nói chỉ cần dặn); dùng lại `playground`, `project-artifact` (Anthropic), `html-plan` (tác giả bài blog, chợ cộng đồng), `frontend-design`, `artifact-design` có sẵn trong app; tự viết phần luật, loại trang và hook nhắc.
- [x] Vet 4 đích, ghi nhận xét vào `vetted.lock`: playground, project-artifact, frontend-design khuyên cài; html-plan khuyên có điều kiện (cần node, chỉ chạy pack.mjs trên trang của agent)
- [x] Luật chung mục "File cho người đọc viết bằng HTML" (`global/SHARED.global.md`) và bảng skill Anthropic theo việc (`global/CLAUDE.global.md`, mục "Trang HTML và Artifact")
- [x] `reader-page` thành skill viết mọi file HTML cho người đọc: thêm loại trang báo cáo (`bao-cao`, cần nguồn) và công cụ (`cong-cu`, cần nút `data-xuat`) trong `check_page.py`, kèm test
- [x] Hook PreToolUse nhắc một lần khi tạo file `.md` mới không bắt buộc Markdown (`pretool_guard.py`), kèm test; plugin 0.18.0
- [x] Bạn duyệt 4 đích (02/11/2026, "Duyệt và cài cả 4"); `install.sh --apply` lúc 10:08 02/11/2026, nhật ký `state/install-logs/20261102-100832.json`; `vet.py drift` khớp cả 4
- [x] `vet.py` ghi kèm bản `.html` cho mỗi báo cáo (scan, note, bản vá bị bỏ) qua `report_html.py`; `vet.py html` sinh lại; bản `.html` không vào git. Threat model TM-47 đến TM-49 (escape, CSP chặn script và tài nguyên ngoài, phán quyết lấy từ dữ liệu)
- [x] `done-gate`: mức cao thì mời làm trang review (loại báo cáo, diff có chú thích, escape từng dòng); chỉ làm khi bạn đồng ý
- [x] `HUONG-DAN.md` thành `HUONG-DAN.html` (02/11/2026, "Chuyển luôn"): mục lục dính bên trái, nút chép lệnh, `check_page.py` đạt (loại giải thích), đủ 38 khối lệnh và 9 bảng của bản cũ
- [x] `KE-HOACH.md`, `INSTALLED.md`, `BASELINE.md` giữ `.md` (bạn chọn 02/11/2026, "Giữ .md cả ba"): agent đọc `KE-HOACH.md` theo `CLAUDE.md`, `install.sh` tự ghi `INSTALLED.md`
- [x] Đo: so số lần bạn mở trang với tóm tắt chat sau 2 tuần, và token mỗi lượt có trang (luật chung: skill đổi cách trả lời cần số liệu trước khi bật lâu dài) → xong theo lời bạn (10/11/2026): "tôi sử dụng html nhiều hơn"; không đo số lần mở
