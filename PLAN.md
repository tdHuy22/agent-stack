# PLAN: triển khai agent-stack

**Đây là nguồn sự thật DUY NHẤT về tiến độ triển khai.** Thiết kế chi tiết ở `KE-HOACH.md`; file này chỉ ghi đang ở đâu và việc gì tiếp theo.

## 0. Đang ở đâu, việc tiếp theo (cập nhật mỗi lần dừng phiên)
*Cập nhật 02/10/2026.*

- **Xong:** GĐ0 đến GĐ7 trên nhánh `trien-khai-v1`, nâng cấp `giong-van` theo nghiên cứu về văn AI, skill `reuse-best`, sửa 5 chỗ thiếu của lần rà soát, và router chọn skill theo nội dung project cùng dòng ➡️ sau mỗi câu trả lời (02/10/2026). Plugin `agent-stack` 0.3.0 gồm 6 skill, 5 agent, 5 hook; 21 mục bên thứ ba đã kiểm duyệt; bộ eval 12 việc; 149 test đạt trên Python 3.9 và 3.11. **Chưa kích hoạt gì ở `~/.claude` hay `~/.config/opencode`.**
- **Đang dở:** không có.
- **Việc tiếp theo, theo thứ tự (đều cần bạn):**
  1. Đọc các báo cáo trong `vet-reports/`, rồi `python3 plugin/skills/vet-skill/scripts/vet.py approve "<khóa>" --note "..."` cho những mục đồng ý (danh sách: `vet.py list`).
  2. Xem trước bằng `./install.sh`, rồi `./install.sh --apply` (thêm `--restore-workflow-warning` để bật lại cảnh báo usage của workflow).
  3. Duyệt ngân sách eval (khoảng 15 USD theo giá niêm yết), rồi `python3 evals/run_eval.py --configs A,C,D --repeats 2 --yes`. Dùng số liệu để cập nhật `routing-table.md` và `rules.json`.
  4. Đo kích hoạt skill: `claude plugin eval ~/Documents/Claude/agent-stack/plugin --runs 1 --max-cost-usd 3 --trust-plugin --no-publish`.
  5. Đặt 5 bài tự viết, càng khác loại càng tốt, vào `plugin/skills/giong-van/samples/` để tạo style card và bật phần so với bài mẫu của `tells.py`.
  6. Cài các CLI bạn muốn dùng (mình không tự cài gì toàn cục): `brew install gitleaks osv-scanner`, và `brew install pyright` nếu duyệt plugin pyright-lsp. `python3 tools/maintain.py` sẽ nhắc nếu còn thiếu.
  7. Gộp vào `main` khi hài lòng: `git -C ~/Documents/Claude/agent-stack switch main && git -C ~/Documents/Claude/agent-stack merge --ff-only trien-khai-v1`.
- **Quyết định còn treo:** 4 câu hỏi ở mục 10 của `KE-HOACH.md` (gói Claude, provider cho worker OpenCode, mục đích viết, project cần theo dõi). Câu "(luôn kiểm tra" đã rõ: thuộc reuse-best.
- **Mốc kiểm tra:** `python3 -m unittest discover -s tests -t .` → `Ran 149 tests … OK`; `claude plugin validate plugin` → `Validation passed`; `python3 evals/run_eval.py --self-test` → 12 dấu ✓.
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

### GĐ8: Dùng lại tốt nhất (#1, reuse-best)
- [x] Ghi rõ ý của câu "(luôn kiểm tra" theo lời bạn (02/10/2026): trước khi build hay làm gì, luôn tìm thứ có sẵn tốt nhất như công cụ trên GitHub hoặc bài nghiên cứu SOTA. Cập nhật `KE-HOACH.md` (N3, mục 7.9, mục 10).
- [x] Skill `reuse-best` (sonnet · medium, chạy trong context riêng) và `scripts/scout.py`: GitHub qua `gh` (tìm theo độ khớp và theo sao rồi gộp), bài báo qua OpenAlex rồi Semantic Scholar rồi arXiv; đánh dấu repo đã lưu trữ, không giấy phép, copyleft, lâu không cập nhật, và bài preprint. Đã chạy thử thật với GitHub và OpenAlex.
- [x] Luôn được nhắc: luật trong `AGENTS.global.md`, dòng mới trong bảng chọn model của `CLAUDE.global.md`, router gợi ý cho mọi việc "tính năng" và "kiến trúc" kèm lưu ý bỏ qua việc vặt, cộng luật riêng cho câu hỏi kiểu "có sẵn chưa", "SOTA". Bộ prompt có nhãn: 53/53.
- [x] 2 case đo kích hoạt mới trong `plugin/evals/` và 1 grader chặn kích hoạt nhầm với việc vặt. 12 test mới.
- [ ] **Bạn làm (tốn một ít hạn mức):** chạy `claude plugin eval` (xem GĐ5) để đo skill có tự kích hoạt đúng lúc không.

### GĐ9: Sửa sau lần rà soát yêu cầu (02/10/2026)
- [x] A. Biên nhận kiểm tra: `session-keeper/scripts/receipt.py` chạy lệnh kiểm tra và ghi kết quả gắn với dấu vân tay nội dung code (commit mà không đổi nội dung thì vẫn khớp). `tien-do` xếp kiểm tra đang trượt vào bậc chặn đường và nhắc chạy lại khi kết quả đạt đã cũ; tín hiệu này trước đó không bao giờ hoạt động. Không viết skill `verify` riêng, vì Claude Code đã có `/verify`.
- [x] B. Eval chạy ngoài repo: model không thấy `CLAUDE.md`, grader hay lời giải; script từ chối chạy nếu thấy file chỉ dẫn ở thư mục cha. Bài làm được chốt thành patch, có `--regrade` và `--report`, chia nhóm lỗi vận hành và lỗi môi trường, chỉ chốt cấu hình khi ma trận đủ, ghi điều kiện chạy vào `.meta.json`.
- [x] C. `install.py` in tổng kết: mã thoát 1 khi có lỗi, 2 khi cài chưa đủ. Sửa thêm lỗi cũ do test mới lộ ra: hai bước cùng sửa `settings.json` thì bản sao lưu sau ghi đè bản đầu, làm hoàn tác sai.
- [x] D. `maintain.py` báo các CLI khuyến nghị chưa cài (gitleaks, osv-scanner, pyright, clangd); việc cài ghi ở §0.
- [x] E. Bước `autocontinue` trong `install.py` đặt `autoContinueAtUsageLimit = true`, chỉ khi bạn chưa tự đặt.
- [x] 25 test mới.

### GĐ10: Chọn skill theo project, gợi ý sau mỗi câu trả lời (#4 + #5, 02/10/2026)
- [x] Mô tả plugin (cả `plugin.json` lẫn marketplace) nhắc đủ các phần; phiên bản 0.3.0. Plugin cài từ marketplace cục bộ được nạp tại chỗ, nên sửa code là có hiệu lực ngay.
- [x] Dòng ➡️ ở cuối mọi câu trả lời, có thêm trường Skill. Luật trong `AGENTS.global.md` áp cho cả Claude Code và OpenCode; bảng chọn của Claude Code có thêm cột Skill.
- [x] Hồ sơ project (`agentstack.project_profile`): loại code, có test, có CI, có Docker, có code nhạy cảm bảo mật. Chỉ dựng cho git repo hoặc thư mục có file kế hoạch; lưu tạm 6 giờ.
- [x] Hook mở phiên gợi ý skill hợp với project (phân biệt skill đã có và skill chờ bạn duyệt), subagent nên dùng, và cách làm việc tiếp theo trong §0. Git repo chưa có file kế hoạch cũng nhận gợi ý.
- [x] Mỗi tin nhắn: "làm tiếp" được định tuyến theo §0; loại project bổ sung skill cho luật đang khớp. 6 test mới.
