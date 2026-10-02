# PLAN: triển khai agent-stack

**Đây là nguồn sự thật DUY NHẤT về tiến độ triển khai.** Thiết kế chi tiết ở `KE-HOACH.md`; file này chỉ ghi đang ở đâu và việc gì tiếp theo.

## 0. Đang ở đâu, việc tiếp theo (cập nhật mỗi lần dừng phiên)
*Cập nhật 02/10/2026.*

- **Xong:** GĐ0 đến GĐ7 trên nhánh `trien-khai-v1`, và nâng cấp `giong-van` theo nghiên cứu về văn AI (02/10/2026). Plugin `agent-stack` gồm 5 skill, 5 agent, 5 hook; 21 mục bên thứ ba đã kiểm duyệt; bộ eval 12 việc; 106 test đạt trên Python 3.9 và 3.11. **Chưa kích hoạt gì ở `~/.claude` hay `~/.config/opencode`.**
- **Đang dở:** không có.
- **Việc tiếp theo, theo thứ tự (đều cần bạn):**
  1. Đọc các báo cáo trong `vet-reports/`, rồi `python3 plugin/skills/vet-skill/scripts/vet.py approve "<khóa>" --note "..."` cho những mục đồng ý (danh sách: `vet.py list`).
  2. Xem trước bằng `./install.sh`, rồi `./install.sh --apply` (thêm `--restore-workflow-warning` để bật lại cảnh báo usage của workflow).
  3. Duyệt ngân sách eval (khoảng 15 USD theo giá niêm yết), rồi `python3 evals/run_eval.py --configs A,C,D --repeats 2 --yes`. Dùng số liệu để cập nhật `routing-table.md` và `rules.json`.
  4. Đo kích hoạt skill: `claude plugin eval ~/Documents/Claude/agent-stack/plugin --runs 1 --max-cost-usd 3 --trust-plugin --no-publish`.
  5. Đặt 5 bài tự viết, càng khác loại càng tốt, vào `plugin/skills/giong-van/samples/` để tạo style card và bật phần so với bài mẫu của `tells.py`.
  6. Gộp vào `main` khi hài lòng: `git -C ~/Documents/Claude/agent-stack switch main && git -C ~/Documents/Claude/agent-stack merge --ff-only trien-khai-v1`.
- **Quyết định còn treo:** 5 câu hỏi ở mục 10 của `KE-HOACH.md` (gói Claude, câu "(luôn kiểm tra" bị cắt, provider cho worker OpenCode, mục đích viết, project cần theo dõi).
- **Mốc kiểm tra:** `python3 -m unittest discover -s tests -t .` → `Ran 106 tests … OK`; `claude plugin validate plugin` → `Validation passed`; `python3 evals/run_eval.py --self-test` → 12 dấu ✓.
- **Sau khi bị ngắt:** chạy `git -C ~/Documents/Claude/agent-stack status` và `git log --oneline -5`, chạy mốc kiểm tra, rồi đọc lại mục này.

## 1. Giai đoạn

### GĐ0: Chuẩn bị và đo nền
- [x] Khung repo, `.gitignore`, `CLAUDE.md`, `README.md`, `PLAN.md`.
- [x] Sao lưu `~/.claude/settings.json` và `~/.config/opencode/opencode.jsonc` vào `backups/2026-10-01/` (không đưa vào git).
- [x] Kiểm chứng OpenCode bằng `opencode debug config`: đọc được cả `tuf` lẫn `openai-oauth`.
- [x] `tools/usage_snapshot.py` kèm test; viết `BASELINE.md`.
- [x] Bỏ Jev khỏi kế hoạch; ghi các quyết định đã chốt vào đầu `KE-HOACH.md`.
- [x] Claude Code CLI đã tự nâng lên 2.1.285 trong lúc triển khai (≥ 2.1.277, đọc được `AGENTS.md`). OpenCode 2.0.21.
- [ ] **Bạn làm:** điền số liệu `/usage` và `/insights` vào `BASELINE.md`.

### GĐ1: Cổng kiểm duyệt
- [x] Cài `cisco-ai-skill-scanner==2.1.0` vào `.venv` (Apache-2.0; kéo theo nhiều thư viện nặng như litellm, openai, fastapi, nên cài cô lập).
- [x] Skill `vet-skill`: `scripts/vet.py` + `scripts/redflags.py` + test (FAIL khi có dấu hiệu mã độc trong code, REVIEW khi cần người đọc).
- [x] Kiểm duyệt 3 repo, ghi `vetted.lock` và `vet-reports/`:
  - humanizer: REVIEW → Claude đọc tay, khuyến nghị cài.
  - webapp-testing: REVIEW → Claude đọc tay, khuyến nghị cài khi cần.
  - planning-with-files: REVIEW → không cài cả repo (507 file, 17 hook), dùng `session-keeper` tự viết thay thế.
- [ ] **Bạn làm:** đọc báo cáo, rồi chạy `vet.py approve <khóa> --note "..."` cho mục bạn đồng ý.

### GĐ2: Bền bỉ phiên (#3)
- [x] Plugin `plugin/` + `.claude-plugin/plugin.json`; `claude plugin validate plugin` → passed.
- [x] `global/AGENTS.global.md`, `global/CLAUDE.global.md`. Mẫu PLAN/HANDOFF nằm trong `plugin/skills/session-keeper/templates/`.
- [x] Hook: SessionStart (nạp §0), UserPromptSubmit (cảnh báo hạn mức), PreCompact, Stop (chỉ nhắc, không thêm lượt), SessionEnd (ghi phiên). Chống chạy trùng bằng file đánh dấu O_EXCL.
- [x] `statusline/statusline.py` ghi `state/limits.json`.
- [x] Skill `session-keeper` + `scripts/state.py` (show / init / handoff).
- [x] Test hook bằng dữ liệu giả, trên Python 3.9 và 3.11.
- [x] Chạy thử 1 phiên `claude -p --plugin-dir`: hook chạy đúng và context chèn vào đúng. Bước gọi model bị lỗi vì **CLI ở terminal hết phiên đăng nhập**.
- [ ] **Bạn làm:** chạy `claude /login` ở terminal, rồi thử `claude --plugin-dir ~/Documents/Claude/agent-stack/plugin` trong một thư mục có PLAN.md.

### GĐ2b: Theo dõi tiến độ (#7)
- [x] Skill `tien-do` + `scripts/collect.py` + test. Xếp hạng 5 bậc; chế độ `--all` cho mọi project; tùy chọn `--gh` lấy PR/CI.
- [x] Gộp bản tóm tắt vào hook SessionStart (thêm dòng "Chặn đường" và các cảnh báo nhanh, không gọi mạng).
- [x] Chạy thử trên chính agent-stack. Đã sửa hai lỗi lộ ra: TODO trong tài liệu và TODO nằm trong chuỗi ký tự bị tính nhầm.
- [ ] **Bạn làm (tùy chọn):** `python3 plugin/skills/tien-do/scripts/collect.py --all --md` để xem tổng quan mọi project. Lệnh chỉ đọc; mình không tự chạy vì bạn dặn không đụng vào project khác.

### GĐ3: Danh mục v1
- [x] Kiểm duyệt 18 mục mới (ghim đúng commit mà marketplace chính thức dùng) + 3 mục cũ. Claude đã đọc tay và ghi nhận xét vào `vetted.lock`: 11 cài, 7 có điều kiện hoặc chỉ dùng trong project, 1 thử trong 1 project, 2 không cài (semgrep plugin, planning-with-files).
- [x] Tinh chỉnh luật sau khi chạy thật: mẫu trong chú thích hạ một bậc; U+200B trước code fence là lành; bắt `allowed-tools` tự duyệt sẵn lệnh tải-rồi-chạy; nhận xét đọc tay giữ được qua các lần quét lại.
- [x] Sửa lỗi của chính repo: mã nguồn từng chứa ký tự vô hình thật (do escape bị giải mã khi ghi file). Có test vệ sinh chặn lỗi này.
- [x] `catalog.json` + `tools/install.py` (`install.sh`): mặc định chỉ xem trước; chỉ cài mục bạn đã `approve`; skill chỉ có chỉ dẫn được chép đúng commit đã kiểm vào `vendor/`; có `--rollback`. Test chạy trên HOME giả.
- [ ] **Bạn làm:** đọc các báo cáo trong `vet-reports/`, rồi `python3 plugin/skills/vet-skill/scripts/vet.py approve <khóa> --note "..."` cho mục đồng ý.
- [ ] **Bạn làm:** xem trước bằng `./install.sh`, rồi `./install.sh --apply` khi đồng ý (thêm `--restore-workflow-warning` để bật lại cảnh báo usage).

### GĐ4: Đội agent và eval
- [x] Agent Claude Code (trong plugin, tên có tiền tố `agent-stack:`): reviewer (opus·high, chỉ đọc), researcher (sonnet·medium), test-runner (haiku), explore-lite (haiku, không ghi đè Explore có sẵn), oc-worker (haiku, điều phối OpenCode).
- [x] Agent OpenCode `worker` (tuf/coder-fast): đã xác minh OpenCode v2 nạp được (theo symlink file) và áp đúng luật quyền (`shell` chặn hết trừ lệnh kiểm tra, `webfetch` chặn).
- [x] Bộ eval 11 việc trong `evals/` + `run_eval.py`: grader tự kiểm bằng lời giải mẫu; test chống grader dễ dãi; mặc định chỉ in kế hoạch.
- [ ] **Bạn duyệt ngân sách** (ước tính khoảng 13,6 USD theo giá niêm yết, tức khoảng 66 lượt, tính vào hạn mức), rồi: `claude /login`, sau đó `python3 evals/run_eval.py --configs A,C,D --repeats 2 --yes`.
- Ghi chú: máy `tuf` (192.168.1.13) đang không kết nối được, nên oc-worker chỉ chạy khi ở mạng nhà.
- Ghi chú: OpenCode v2.0.x trả về danh sách skill rỗng qua API, kể cả với skill tối giản. Phương án dự phòng: `AGENTS.global.md` ghi đường dẫn của từng skill để agent tự đọc.
- Ghi chú: OpenCode v2 báo các thiết lập `reasoning` và `temperature` kiểu cũ của provider `tuf` trong `opencode.jsonc` đang bị bỏ qua. Bạn có thể dọn khi tiện; mình không sửa file của bạn.

### GĐ5: Router (#4, #5)
- [x] Skill `task-router`: `rules.json` (14 luật), `route.py`. Đã nối vào hook UserPromptSubmit: chỉ gợi ý khi có việc nên làm (đổi model/effort, skill, subagent), mỗi luật nhắc tối đa một lần mỗi giờ trong một phiên, bỏ qua lệnh `/` và câu ngắn. Đã nối vào `tien-do`.
- [x] Bộ 47 prompt có nhãn (`evals/router-prompts.jsonl`): đúng 47/47. **Lưu ý thiên lệch:** Claude viết cả luật lẫn prompt, nên hãy thêm prompt thật của bạn.
- [x] `routing-table.md` (giả thuyết, chờ số liệu eval).
- [x] `plugin/evals/`: 10 case đo kích hoạt skill (7 nên kích hoạt, 3 không nên).
- [ ] **Bạn làm (tốn một ít hạn mức):** `claude plugin eval ~/Documents/Claude/agent-stack/plugin --runs 1 --max-cost-usd 3 --trust-plugin --no-publish`. Dùng `--no-publish` để báo cáo chỉ nằm trên máy.

### GĐ6: Viết tự nhiên (#6)
- [x] Skill `giong-van` (chế độ chỉnh văn và chế độ `tao-style-card`): giữ nguyên ý, không bịa sự kiện, nêu rõ phạm vi (không nhằm qua mặt công cụ phát hiện AI).
- [x] `scripts/tells.py`: dò dấu hiệu văn AI tiếng Việt và tiếng Anh, nhịp câu đều, lạm dụng gạch dài, in đậm, emoji; cho điểm trên 1.000 từ để so trước và sau.
- [x] `vi-ai-tells.md` (danh sách có ví dụ và cách sửa), `style-card.md` (mẫu chờ điền), `samples/` (không đưa vào git).
- [x] Việc eval thứ 12 `write-vn-rewrite` + case đo kích hoạt `writing-rewrite`.
- [x] Nâng cấp theo nghiên cứu (02/10/2026; nguồn ở cuối `vi-ai-tells.md`): `tells.py` thêm mệnh đề đuôi bình luận, né chữ "là", kết bài "thách thức và triển vọng", phần chatbot bị dán sót, mật độ "việc/sự + động từ"; so với bài mẫu của bạn (từ bạn hiếm dùng, xưng hô, cụm lặp lại); chuẩn hóa Unicode NFC; sửa lỗi báo sai số dòng. `SKILL.md` viết lại theo lối khẳng định: sửa nội dung trước, giữ chất Việt, trả về đúng định dạng của văn gốc, 5 bài mẫu là đủ.
- [ ] **Bạn làm:** thêm 5 bài tự viết (nhiều loại) vào `samples/`, rồi nhờ Claude chạy `giong-van tao-style-card` và duyệt từng mục.

### GĐ7: Vận hành
- [x] `tools/maintain.py`: phiên bản, đồ bên thứ ba có commit mới (so với commit đã kiểm), test và validate, ngân sách mô tả skill, mức dùng 7 ngày so với nền, dọn cache. Chạy mỗi tháng: `python3 tools/maintain.py`.
