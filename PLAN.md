# PLAN: triển khai agent-stack

**Đây là nguồn sự thật DUY NHẤT về tiến độ triển khai.** Thiết kế chi tiết ở `KE-HOACH.md`; file này chỉ ghi đang ở đâu và việc gì tiếp theo.

## 0. Đang ở đâu, việc tiếp theo (cập nhật mỗi lần dừng phiên)
*Cập nhật 01/10/2026.*

- **Xong:** GĐ0 (khung repo, sao lưu cấu hình, số liệu nền trong `BASELINE.md`).
- **Đang dở:** không có.
- **Việc tiếp theo, theo thứ tự:**
  1. GĐ1: cài skill-scanner vào `.venv`, viết `vet-skill`, kiểm duyệt 3 repo mẫu.
  2. GĐ2: dựng plugin, hook giữ trạng thái phiên, statusline, skill `session-keeper`.
  3. GĐ2b: skill `tien-do`.
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
- [ ] Cài `cisco-ai-skill-scanner` vào `.venv` (sau khi kiểm giấy phép).
- [ ] Skill `vet-skill` + `scripts/vet.py` + test.
- [ ] Kiểm duyệt 3 repo: anthropics/skills, OthmanAdi/planning-with-files, blader/humanizer. Ghi `vetted.lock` và `vet-reports/`.

### GĐ2: Bền bỉ phiên (#3)
- [ ] Plugin `plugin/` + `.claude-plugin/plugin.json`; `claude plugin validate`.
- [ ] `global/AGENTS.global.md`, `global/CLAUDE.global.md`, `templates/`.
- [ ] Hook: SessionStart, UserPromptSubmit (cảnh báo hạn mức), PreCompact, Stop, SessionEnd.
- [ ] Statusline ghi `state/limits.json`.
- [ ] Skill `session-keeper`.
- [ ] Test hook bằng dữ liệu giả; chạy thử 1 phiên `claude -p --plugin-dir`.

### GĐ2b: Theo dõi tiến độ (#7)
- [ ] Skill `tien-do` + `scripts/collect.py` + test.
- [ ] Gộp bản tóm tắt vào hook SessionStart.

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
