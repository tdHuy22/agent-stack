# PLAN: triển khai agent-stack

**Đây là nguồn sự thật DUY NHẤT về tiến độ triển khai.** Thiết kế chi tiết ở `KE-HOACH.md`; file này chỉ ghi đang ở đâu và việc gì tiếp theo.

## 0. Đang ở đâu, việc tiếp theo (cập nhật mỗi lần dừng phiên)
*Cập nhật 01/10/2026.*

- **Xong:** GĐ0 (khung repo, số liệu nền). GĐ1 (`vet-skill`, kiểm duyệt 3 repo). GĐ2 (plugin, 5 hook, statusline, `session-keeper`). GĐ2b (`tien-do`, nối vào hook SessionStart). 61 test đạt.
- **Đang dở:** không có.
- **Việc tiếp theo, theo thứ tự:**
  1. GĐ3: kiểm duyệt danh mục cần cài, viết `install.sh` (chỉ chạy thử, không kích hoạt).
  2. GĐ4: đội agent và bộ eval (chưa chạy eval khi chưa được duyệt ngân sách).
  3. GĐ5: skill `task-router`, nối vào hook UserPromptSubmit và vào `tien-do`.
- **Quyết định còn treo:** 5 câu hỏi ở mục 10 của `KE-HOACH.md`.
- **Mốc kiểm tra:** `python3 -m unittest discover -s tests -t .` → `OK`. Từ GĐ2 thêm: `claude plugin validate plugin` → `Validation passed`.
- **Sau khi bị ngắt:** chạy `git -C ~/Documents/Claude/agent-stack status` và `git log --oneline -5`, chạy mốc kiểm tra, rồi đọc lại mục này.

## 1. Giai đoạn

### GĐ0: Chuẩn bị và đo nền
- [x] Khung repo, `.gitignore`, `CLAUDE.md`, `README.md`, `PLAN.md`.
- [x] Sao lưu `~/.claude/settings.json` và `~/.config/opencode/opencode.jsonc` vào `backups/2026-10-01/` (không đưa vào git).
- [x] Kiểm chứng OpenCode bằng `opencode debug config`: đọc được cả `tuf` lẫn `openai-oauth`.
- [x] `tools/usage_snapshot.py` kèm test; viết `BASELINE.md`.
- [x] Bỏ Jev khỏi kế hoạch; ghi các quyết định đã chốt vào đầu `KE-HOACH.md`.
- [ ] **Bạn làm:** `brew upgrade --cask claude-code` (cần bản ≥ 2.1.277 để đọc `AGENTS.md`).
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
- [ ] Kiểm duyệt các mục ghi "Cài" ở mục 6 của kế hoạch; ghi `catalog.json`.
- [ ] `install.sh` (mặc định chỉ chạy thử).

### GĐ4: Đội agent và eval
- [ ] Agent: reviewer, researcher, test-runner, oc-worker, explore-lite; agent OpenCode `worker`.
- [ ] Bộ việc eval tự chứa trong `evals/` + script chạy. **Chạy eval cần bạn duyệt ngân sách.**

### GĐ5: Router (#4, #5)
- [ ] Skill `task-router`: `rules.json`, `route.py`, gắn vào hook UserPromptSubmit.
- [ ] Bộ 40 prompt có nhãn; độ chính xác ≥ 85%.

### GĐ6: Viết tự nhiên (#6)
- [ ] Skill `giong-van` + `tells.py` + danh sách dấu hiệu văn AI tiếng Việt.

### GĐ7: Vận hành
- [ ] `tools/maintain.py`: kiểm tra phiên bản, kiểm duyệt lại khi upstream đổi, chạy test.
