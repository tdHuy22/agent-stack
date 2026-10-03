# PLAN: triển khai agent-stack

**Đây là nguồn sự thật DUY NHẤT về tiến độ triển khai.** Thiết kế chi tiết ở `KE-HOACH.md`; file này chỉ ghi đang ở đâu và việc gì tiếp theo.

## 0. Đang ở đâu, việc tiếp theo (cập nhật mỗi lần dừng phiên)
*Cập nhật chiều 03/10/2026.*

- **Xong:**
  - GĐ0 đến GĐ11 và mọi việc sau đó nằm trên nhánh `trien-khai-v1`, đã gộp vào `main`; chưa push.
  - Plugin `agent-stack` 0.4.1: 6 skill, 5 agent, 6 hook (thêm SubagentStart). **Đã cập nhật toàn cục** lúc 10:11 ngày 03/10/2026 theo lệnh của bạn (trước đó 0.4.0 lúc 09:25): `claude plugin list` báo 0.4.1, bản cache khớp nguồn từng file, có bản sửa lỗi báo cáo subagent bị lưu nhầm thành yêu cầu của bạn và bị router gợi ý nhầm. Chuỗi yêu cầu, subagent, báo cáo quay về, subagent thứ hai chạy thử trên file đã cài (Python 3.9 và 3.11): đạt. Các phiên desktop mở trước 10:11 vẫn chạy 0.4.0.
  - Bên thứ ba: 24 mục đã kiểm duyệt: 21 duyệt, 3 từ chối, không còn mục chờ. Ngày 03/10/2026 bạn quyết ba mục cuối theo khuyến nghị: `sandbox-runtime` duyệt có điều kiện (chỉ dùng cục bộ trong `.cache/srt`), `claude-security` duyệt có điều kiện (chỉ gọi tay, cài theo project khi cần; chưa cài), `plugin-dev` từ chối. Duyệt không có nghĩa là đã cài.
  - Bộ eval 12 việc đã chạy thật ngày 02/10/2026 (72 lượt, khoảng 7,5 USD giá niêm yết, tính vào hạn mức gói): sonnet·medium, opus·medium và opus·low đều đạt 24/24; sonnet rẻ nhất (0,063 USD/việc, so với 0,128 và 0,121). Bộ việc chưa phân biệt được các cấu hình (xem `routing-table.md`). Đo kích hoạt skill bằng `claude plugin eval` (13 ca, 3,67 USD): 10/10 ca cần kích hoạt đều gọi đúng skill, 3/3 ca không được kích hoạt đều sạch. 317 test đạt trên Python 3.9 và 3.11.
  - Bảng định tuyến đã đối chiếu với khuyến nghị chính thức của Anthropic (Claude Code, bài chọn model và effort, trang chi phí): `routing-table.md`. Chỉ một dòng đổi: debug khó bắt đầu ở opus·medium rồi nâng lên high nếu chưa ra; các dòng opus·high còn lại giữ vì không có kiểm tra tự động.
  - **Đã cài toàn cục** lúc 15:19 ngày 02/10/2026, theo đồng ý của bạn trong chat. Nhật ký: `state/install-logs/20261002-151930.json`, `…152532.json`, `…153032.json`, `20261002-221518.json` (context7), `20261003-092531.json` (cập nhật plugin 0.4.0), `20261003-101141.json` (cập nhật plugin 0.4.1). Mọi thay đổi và lệnh gỡ từng mục nằm trong `INSTALLED.md`; gỡ toàn bộ: `./install.sh --rollback --apply`.
  - Kiểm chứng sau khi cài:
    - 7 plugin đều bật lúc cài, file khớp bản đã kiểm duyệt (ngày 03/10/2026 năm plugin đã bị tắt trong `settings.json`: `clangd-lsp`, `claude-code-setup`, `claude-md-management`, `pyright-lsp`, `session-report`; đang bật: `agent-stack`, `agent-stack-vendor`, `context7`);
    - CLI nạp plugin tại chỗ, đã thấy `plugin_root` trong `state/sessions.jsonl`;
    - desktop app chạy bản chép trong cache, tìm về repo nhờ `plugin/.agent-stack-home`.
  - **Rà soát nguồn chính thức của Anthropic và việc a đến e** (02/10/2026; chi tiết ở `KE-HOACH.md` §6.13):
    - (a) `vet.py dynamic` (`sandbox-runtime` đã duyệt có điều kiện ngày 03/10/2026: chỉ dùng cục bộ): chạy MỘT lệnh của đối tượng trong sandbox-runtime (cài cô lập `.cache/srt`, `--ignore-scripts`, theo `tools/srt/package-lock.json`): không mạng, chỉ đọc ghi trong bản chép tạm, HOME thật bị chặn. Phát hiện chắc chắn bằng HOME giả rải 12 file mồi (đọc qua atime, rò rỉ qua dấu riêng); log vi phạm của macOS chỉ là phần thêm vì đo được nó mất khoảng một nửa sự kiện khi tiến trình thoát nhanh. Sửa hai luật quét báo nhầm (socat, CI). Mới kiểm trên macOS. **Review độc lập trước khi gộp** (agent `reviewer`, opus·high, 02/10/2026) tìm ra 1 lỗi cao, 6 trung bình, 6 thấp; đã sửa hết và thêm test: ghi vào `/tmp/claude` (srt tự mở), né bằng tên tiến trình, mồi bị đặt lại thời gian hay xóa, FIFO làm treo bước quét, tiến trình nền, lệnh không chạy được mà vẫn báo "không thấy gì", hạ bậc `.github/` quá rộng, che khóa còn sót, PLAN.md vào context như chỉ dẫn. Review lượt hai (0 cao, 3 trung bình, 6 thấp) cũng đã sửa: script ở gốc HOME từng mở cả HOME để đọc, giả chim hoàng yến qua tên người dùng proxy, kho vi phạm của srt chỉ giữ 100 sự kiện cuối (nay báo khi tràn), diệt nhầm tiến trình (nay chỉ tiến trình bắt đầu sau lúc chạy), PEM nuốt cả câu. Giới hạn còn lại đã ghi: truy vấn keychain qua dịch vụ hệ thống (không chặn được `security` bằng cấu hình), đọc mồi bằng clonefile `cp -c` không làm atime nhảy, mã nhận ra sandbox vẫn né được.
    - (b) `plugin-dev`: script kiểm hook của nó lỗi thời (đòi `matcher` mà `claude plugin validate` không đòi); `session_end.py` chạy 29 đến 68 ms nên giữ `timeout: 2`. Không cài; đã từ chối ngày 03/10/2026.
    - (c) `reviewer.md`: hình dạng lỗi, verifier phản biện, ngưỡng tin cậy 80, bảng lọc dương tính giả; `plugin/NOTICES.md` ghi nguồn MIT và Apache-2.0.
    - (d) `tien-do`: mục "Đổi từ lần trước" qua snapshot trong `state/tien-do/`.
    - (e) `claude-security`: đã vet và duyệt có điều kiện ngày 03/10/2026 (chỉ gọi tay, theo project); chưa cài.
  - **Skill và agent chạy context riêng không thấy hội thoại** (bạn nêu 02/10): hook SubagentStart đưa yêu cầu gần nhất của bạn (che khóa, tối đa 1200 ký tự) và 1 đến 2 việc đầu §0 vào đầu context của chúng; mọi agent và skill fork ghi rõ cần gì và thiếu thì nói rõ; luật chung dặn giao việc bằng prompt tự đủ. **Đã chạy thử bản đã cài ngoài phiên** (file trong cache, thư mục trạng thái tạm, Python 3.9 và 3.11): thoát 0, không in lỗi, khóa giả bị che, ngữ cảnh 747 ký tự (trần 1500), sự kiện `subagent-start` có `"request": true`. **Đã kiểm chạy thật** ngày 03/10/2026 bằng `claude -p` (CLI nạp plugin tại chỗ từ `plugin/`; hai lượt, khoảng 0,34 USD giá niêm yết): SubagentStart chạy, session_id khớp UserPromptSubmit, và subagent trích ra được yêu cầu của bạn (dấu ngẫu nhiên không có trong prompt giao việc). **Lỗi tìm thấy nhờ chạy thật, đã sửa ở 0.4.1:** báo cáo của subagent quay về phiên chính như một tin của người dùng (`<agent-message …>`, `[Subagent hand-back]`), nên bị lưu thành "yêu cầu gần nhất" (subagent thứ hai nhận nhầm báo cáo của subagent trước) và router gợi ý nhầm `tien-do`; nay bị coi là tin tự động. Chạy lại với hai subagent liên tiếp: cả hai nhận đúng yêu cầu. **App desktop đã kiểm trong phiên thật** lúc 15:03 ngày 03/10/2026 (phép thử `[PT-697887]`, phiên `69b1fb8a…`): `plugin_root` của phiên trong `state/sessions.jsonl` là bản cache `…/agent-stack/0.4.1`; `state/events.jsonl` có dòng `subagent-start` của phiên với `agent_type` `agent-stack:explore-lite`, `"request": true`, `"plan": true`, 1214 ký tự; subagent chép nguyên văn yêu cầu của bạn kèm mã phép thử và tìm đúng `plugin/hooks/subagent_start.py:72`. Báo cáo quay về không ghi đè yêu cầu: `state/last-request/` (quyền 0600) giữ tin tiếp theo của bạn, còn yêu cầu phép thử nằm ở mục `earlier`.
  - **Quyền riêng tư OpenCode**: model mặc định `opencode/muse-spark-1.3-contributor-free` dùng prompt và kết quả để huấn luyện model của Meta (trang OpenCode Zen). Luật chung và `oc-worker` ghi: không tự rơi về model từ xa, không giao secret hay mã riêng tư. Ngày 03/10/2026 bạn cho biết đã tự setup OpenCode riêng và không cần repo quan tâm: đây không còn là việc chờ bạn quyết; luật chung và `oc-worker` giữ nguyên.
- **Đang dở:** không có việc đang sửa dở.
- **Việc tiếp theo, theo thứ tự (đều cần bạn):**
  1. Cấp quyền cho MCP `context7` qua `/mcp` trong terminal `claude` tương tác (mình không bắt đầu được luồng này). Phiên desktop lúc 15:03 ngày 03/10 đã thấy công cụ của `context7` kết nối, nhưng chưa gọi thử; có thể việc này không còn cần.
  2. Tùy chọn, không cài cũng không hỏng gì: `brew install pyright` (chỉ để plugin pyright-lsp chạy; plugin này đang tắt), `brew install gitleaks osv-scanner` (không code nào gọi).
  3. Đặt 5 bài tự viết, càng khác loại càng tốt, vào `plugin/skills/giong-van/samples/`.
  4. Nếu muốn phân biệt được các cấu hình model: thêm 3 đến 4 việc khó hơn vào `evals/tasks/` (debug nhiều file, race, review diff thật) rồi chạy lại A, C, D (ước khoảng 6 đến 8 USD giá niêm yết), và chạy thêm H (haiku, khoảng 0,5 USD).
  5. Trả lời nốt `KE-HOACH.md` mục 10: project cần theo dõi và bản tổng hợp tuần; ngôn ngữ viết; việc hay thư mục tuyệt đối không được gửi ra ngoài.
  6. Push khi bạn muốn: `git push` (mình không tự push). Repo chưa có remote nào, nên cần `git remote add origin <url>` trước.
- **Quyết định còn treo:**
  - **Gác lại (bạn nói 03/10/2026: không cần quan tâm OpenCode vì đã setup riêng; chỉ làm khi bạn nhắc).** Có thêm eval bằng model free trên OpenRouter qua OpenCode không. Mục đích là đo xem worker OpenCode và phương án dự phòng khi hết hạn mức có giữ chất lượng không; việc này không thay eval Claude. Nếu làm, cần bạn:
    - tạo key OpenRouter và đặt vào biến môi trường (mình không nhập key);
    - quyết định có nạp 10 USD không (mức 1.000 request mỗi ngày, so với 50 khi chưa nạp);
    - chọn 2–3 model free có gọi tool, hoặc để `reuse-best` chọn theo benchmark.
    - Phần mình làm: thêm cấu hình `opencode run -m openrouter/<model>:free`, cách ly khỏi cấu hình toàn cục của OpenCode, giới hạn dưới 20 request mỗi phút, và `--resume`.
    - Bạn cho biết OpenCode đang dùng OpenRouter và model free của OpenCode (02/10/2026); chưa rõ key đã nằm trong biến môi trường chưa. Lưu ý quyền riêng tư ở trên: model free có thể dùng dữ liệu để huấn luyện.
- **Mốc kiểm tra:** chạy qua `python3 plugin/skills/session-keeper/scripts/receipt.py run -- <lệnh>` để có biên nhận.
  - `/usr/bin/python3 -m unittest discover -s tests -t .` và với `python3` → `Ran 317 tests … OK`
  - `claude plugin validate plugin` → `Validation passed`
  - `python3 evals/run_eval.py --self-test` → 12 dấu ✓
  - `python3 plugin/skills/task-router/scripts/route.py --eval evals/router-prompts.jsonl` → 53/53
- **Sau khi bị ngắt:** chạy `git -C ~/Documents/Claude/agent-stack status`, `git log --oneline -5`, `python3 plugin/skills/session-keeper/scripts/receipt.py show` và `claude plugin list`, rồi đọc `INSTALLED.md` và mục này.

## 1. Giai đoạn

### GĐ0: Chuẩn bị và đo nền
- [x] Khung repo, `.gitignore`, `CLAUDE.md`, `README.md`, `PLAN.md`.
- [x] Sao lưu `~/.claude/settings.json` và `~/.config/opencode/opencode.jsonc` vào `backups/2026-10-01/` (không đưa vào git).
- [x] Kiểm chứng OpenCode bằng `opencode debug config`: đọc được cả `tuf` lẫn `openai-oauth`.
- [x] `tools/usage_snapshot.py` kèm test; viết `BASELINE.md`.
- [x] Bỏ Jev khỏi kế hoạch; ghi các quyết định đã chốt vào đầu `KE-HOACH.md`.
- [x] Claude Code CLI đã tự nâng lên 2.1.285 trong lúc triển khai (≥ 2.1.277, đọc được `AGENTS.md`). OpenCode 2.0.21.
- [x] **Bạn làm:** điền số liệu `/usage` và `/insights` vào `BASELINE.md`. Xong 02/10/2026: số liệu ở `BASELINE.md` (phần `/usage` đọc lại bằng `get_usage`, chưa có phân tích theo skill/subagent/MCP).

### GĐ1: Cổng kiểm duyệt
- [x] Cài `cisco-ai-skill-scanner==2.1.0` vào `.venv` (Apache-2.0; kéo theo nhiều thư viện nặng như litellm, openai, fastapi, nên cài cô lập).
- [x] Skill `vet-skill`: `scripts/vet.py` + `scripts/redflags.py` + test (FAIL khi có dấu hiệu mã độc trong code, REVIEW khi cần người đọc).
- [x] Kiểm duyệt 3 repo, ghi `vetted.lock` và `vet-reports/`:
  - humanizer: REVIEW → Claude đọc tay, khuyến nghị cài.
  - webapp-testing: REVIEW → Claude đọc tay, khuyến nghị cài khi cần.
  - planning-with-files: REVIEW → không cài cả repo (507 file, 17 hook), dùng `session-keeper` tự viết thay thế.
- [x] **Bạn làm:** đọc báo cáo, rồi chạy `vet.py approve <khóa> --note "..."` cho mục bạn đồng ý. Xong 02/10/2026: 21 mục đã có quyết định (19 duyệt, 2 từ chối, 0 chờ).

### GĐ2: Bền bỉ phiên (#3)
- [x] Plugin `plugin/` + `.claude-plugin/plugin.json`; `claude plugin validate plugin` → passed.
- [x] `global/AGENTS.global.md`, `global/CLAUDE.global.md`. Mẫu PLAN/HANDOFF nằm trong `plugin/skills/session-keeper/templates/`.
- [x] Hook: SessionStart (nạp §0), UserPromptSubmit (cảnh báo hạn mức), PreCompact, Stop (chỉ nhắc, không thêm lượt), SessionEnd (ghi phiên). Chống chạy trùng bằng file đánh dấu O_EXCL.
- [x] `statusline/statusline.py` ghi `state/limits.json`.
- [x] Skill `session-keeper` + `scripts/state.py` (show / init / handoff).
- [x] Test hook bằng dữ liệu giả, trên Python 3.9 và 3.11.
- [x] Chạy thử 1 phiên `claude -p --plugin-dir`: hook chạy đúng và context chèn vào đúng. Bước gọi model bị lỗi vì **CLI ở terminal hết phiên đăng nhập**.
- [x] **Bạn làm:** chạy `claude /login` ở terminal, rồi thử `claude --plugin-dir ~/Documents/Claude/agent-stack/plugin` trong một thư mục có PLAN.md. Xong 02/10/2026: `claude -p` đáp bình thường; plugin đã cài toàn cục, `plugin_root` đã ghi trong `state/sessions.jsonl`.

### GĐ2b: Theo dõi tiến độ (#7)
- [x] Skill `tien-do` + `scripts/collect.py` + test. Xếp hạng 5 bậc; chế độ `--all` cho mọi project; tùy chọn `--gh` lấy PR/CI.
- [x] Gộp bản tóm tắt vào hook SessionStart (thêm dòng "Chặn đường" và các cảnh báo nhanh, không gọi mạng).
- [x] Chạy thử trên chính agent-stack. Đã sửa hai lỗi lộ ra: TODO trong tài liệu và TODO nằm trong chuỗi ký tự bị tính nhầm.
- [ ] **Bạn làm (tùy chọn):** `python3 plugin/skills/tien-do/scripts/collect.py --all --md` để xem tổng quan mọi project. Lệnh chỉ đọc project (chỉ ghi snapshot vào `state/` của agent-stack; thêm `--no-snapshot` để không ghi); mình không tự chạy vì bạn dặn không đụng vào project khác.

### GĐ3: Danh mục v1
- [x] Kiểm duyệt 18 mục mới (ghim đúng commit mà marketplace chính thức dùng) + 3 mục cũ. Claude đã đọc tay và ghi nhận xét vào `vetted.lock`: 11 cài, 7 có điều kiện hoặc chỉ dùng trong project, 1 thử trong 1 project, 2 không cài (semgrep plugin, planning-with-files).
- [x] Tinh chỉnh luật sau khi chạy thật: mẫu trong chú thích hạ một bậc; U+200B trước code fence là lành; bắt `allowed-tools` tự duyệt sẵn lệnh tải-rồi-chạy; nhận xét đọc tay giữ được qua các lần quét lại.
- [x] Sửa lỗi của chính repo: mã nguồn từng chứa ký tự vô hình thật (do escape bị giải mã khi ghi file). Có test vệ sinh chặn lỗi này.
- [x] `catalog.json` + `tools/install.py` (`install.sh`): mặc định chỉ xem trước; chỉ cài mục bạn đã `approve`; skill chỉ có chỉ dẫn được chép đúng commit đã kiểm vào `vendor/`; có `--rollback`. Test chạy trên HOME giả.
- [x] **Bạn làm:** đọc các báo cáo trong `vet-reports/`, rồi `python3 plugin/skills/vet-skill/scripts/vet.py approve <khóa> --note "..."` cho mục đồng ý. Xong 02/10/2026: 8 mục còn lại đã duyệt (xem dòng trên).
- [x] **Bạn làm:** xem trước bằng `./install.sh`, rồi `./install.sh --apply` khi đồng ý (thêm `--restore-workflow-warning` để bật lại cảnh báo usage). Xong lượt đầu 02/10/2026 (cờ `--restore-workflow-warning` chưa dùng, `skipWorkflowUsageWarning` vẫn `true`). Trong 8 mục duyệt sau đó, `context7` đã cài ở phạm vi user (xem mục 7 ở trên).

### GĐ4: Đội agent và eval
- [x] Agent Claude Code (trong plugin, tên có tiền tố `agent-stack:`): reviewer (opus·high, chỉ đọc), researcher (sonnet·medium), test-runner (haiku), explore-lite (haiku, không ghi đè Explore có sẵn), oc-worker (haiku, điều phối OpenCode).
- [x] Agent OpenCode `worker` (tuf/coder-fast): đã xác minh OpenCode v2 nạp được (theo symlink file) và áp đúng luật quyền (`shell` chặn hết trừ lệnh kiểm tra, `webfetch` chặn).
- [x] Bộ eval 11 việc trong `evals/` + `run_eval.py`: grader tự kiểm bằng lời giải mẫu; test chống grader dễ dãi; mặc định chỉ in kế hoạch.
- [x] **Bạn duyệt ngân sách** (ước tính khoảng 13,6 USD theo giá niêm yết, tức khoảng 66 lượt, tính vào hạn mức), rồi: `claude /login`, sau đó `python3 evals/run_eval.py --configs A,C,D --repeats 2 --yes`. Xong 02/10/2026: chạy thành ba đợt A, C, D; thực tế khoảng 7,5 USD.
- Ghi chú: máy `tuf` (192.168.1.13) đang không kết nối được, nên oc-worker chỉ chạy khi ở mạng nhà.
- Ghi chú: OpenCode v2.0.x trả về danh sách skill rỗng qua API, kể cả với skill tối giản. Phương án dự phòng: `AGENTS.global.md` ghi đường dẫn của từng skill để agent tự đọc.
- Ghi chú: OpenCode v2 báo các thiết lập `reasoning` và `temperature` kiểu cũ của provider `tuf` trong `opencode.jsonc` đang bị bỏ qua. Bạn có thể dọn khi tiện; mình không sửa file của bạn.

### GĐ5: Router (#4, #5)
- [x] Skill `task-router`: `rules.json` (14 luật), `route.py`. Đã nối vào hook UserPromptSubmit: chỉ gợi ý khi có việc nên làm (đổi model/effort, skill, subagent), mỗi luật nhắc tối đa một lần mỗi giờ trong một phiên, bỏ qua lệnh `/` và câu ngắn. Đã nối vào `tien-do`.
- [x] Bộ 47 prompt có nhãn (`evals/router-prompts.jsonl`): đúng 47/47. **Lưu ý thiên lệch:** Claude viết cả luật lẫn prompt, nên hãy thêm prompt thật của bạn.
- [x] `routing-table.md` (giả thuyết, chờ số liệu eval).
- [x] `plugin/evals/`: 10 case đo kích hoạt skill (7 nên kích hoạt, 3 không nên).
- [x] **Bạn làm (tốn một ít hạn mức):** `claude plugin eval ~/Documents/Claude/agent-stack/plugin --runs 1 --max-cost-usd 3 --trust-plugin --no-publish`. Dùng `--no-publish` để báo cáo chỉ nằm trên máy. Xong 02/10/2026: 13 ca, 3,67 USD giá niêm yết. 10/10 ca cần kích hoạt đều gọi đúng skill, 3/3 ca không được kích hoạt đều sạch. Cột Δ chỉ cho biết skill chạy khi có plugin, chưa đo skill làm việc tốt đến đâu.

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
- [x] **Bạn làm (tốn một ít hạn mức):** chạy `claude plugin eval` (xem GĐ5) để đo skill có tự kích hoạt đúng lúc không. Xong 02/10/2026: 13 ca, 3,67 USD giá niêm yết. 10/10 ca cần kích hoạt đều gọi đúng skill, 3/3 ca không được kích hoạt đều sạch. Cột Δ chỉ cho biết skill chạy khi có plugin, chưa đo skill làm việc tốt đến đâu.

### GĐ9: Sửa sau lần rà soát yêu cầu (02/10/2026)
- [x] A. Biên nhận kiểm tra: `session-keeper/scripts/receipt.py` chạy lệnh kiểm tra và ghi kết quả gắn với dấu vân tay nội dung code (commit mà không đổi nội dung thì vẫn khớp). `tien-do` xếp kiểm tra đang trượt vào bậc chặn đường và nhắc chạy lại khi kết quả đạt đã cũ; tín hiệu này trước đó không bao giờ hoạt động. Không viết skill `verify` riêng, vì Claude Code đã có `/verify`.
- [x] B. Eval chạy ngoài repo: model không thấy `CLAUDE.md`, grader hay lời giải; script từ chối chạy nếu thấy file chỉ dẫn ở thư mục cha. Bài làm được chốt thành patch, có `--regrade` và `--report`, chia nhóm lỗi vận hành và lỗi môi trường, chỉ chốt cấu hình khi ma trận đủ, ghi điều kiện chạy vào `.meta.json`.
- [x] C. `install.py` in tổng kết: mã thoát 1 khi có lỗi, 2 khi cài chưa đủ. Sửa thêm lỗi cũ do test mới lộ ra: hai bước cùng sửa `settings.json` thì bản sao lưu sau ghi đè bản đầu, làm hoàn tác sai.
- [x] D. `maintain.py` báo các CLI khuyến nghị chưa cài (gitleaks, osv-scanner, pyright, clangd); việc cài ghi ở §0.
- [x] E. Bước `autocontinue` trong `install.py` đặt `autoContinueAtUsageLimit = true`, chỉ khi bạn chưa tự đặt.
- [x] 25 test mới.

### GĐ10: Chọn skill theo project, gợi ý sau mỗi câu trả lời (#4 + #5, 02/10/2026)
- [x] Mô tả plugin (cả `plugin.json` lẫn marketplace) nhắc đủ các phần; phiên bản 0.3.0. (Kiểm chứng khi cài ngày 02/10/2026: CLI trong terminal nạp plugin tại chỗ từ `agent-stack/plugin`, còn desktop app chạy bản chép trong `~/.claude/plugins/cache/`. Bản chép tìm về repo nhờ file `plugin/.agent-stack-home` do `install.py` ghi. Sau khi sửa plugin: tăng `version`, chạy `./install.sh --apply --only plugin` (gồm `claude plugin update`), rồi mở phiên mới.)
- [x] Dòng ➡️ ở cuối mọi câu trả lời, có thêm trường Skill. Luật trong `AGENTS.global.md` áp cho cả Claude Code và OpenCode; bảng chọn của Claude Code có thêm cột Skill.
- [x] Hồ sơ project (`agentstack.project_profile`): loại code, có test, có CI, có Docker, có code nhạy cảm bảo mật. Chỉ dựng cho git repo hoặc thư mục có file kế hoạch; lưu tạm 6 giờ.
- [x] Hook mở phiên gợi ý skill hợp với project (phân biệt skill đã có và skill chờ bạn duyệt), subagent nên dùng, và cách làm việc tiếp theo trong §0. Git repo chưa có file kế hoạch cũng nhận gợi ý.
- [x] Mỗi tin nhắn: "làm tiếp" được định tuyến theo §0; loại project bổ sung skill cho luật đang khớp. 6 test mới.
- [x] Sửa sau lần rà soát thứ ba:
  - `KE-HOACH.md` từng ghi sai rằng tự làm tiếp ở giới hạn 5 giờ được bật mặc định; thực tế khóa này mặc định chưa đặt.
  - Tài liệu từng ghi skill OpenCode được link vào `~/.agents/skills/`, trong khi `install.py` link vào `~/.config/opencode/skills/`.
  - Lộ trình trong mục tóm tắt và README đã cập nhật.
  - OpenCode không có hook, nên luật chung dặn chạy `route.py --session` ở câu trả lời đầu tiên của phiên.
  - Có test chặn tài liệu nói khác code ở hai điểm trên. 5 test mới.

### GĐ11: Cài toàn cục (02/10/2026)
- [x] Trước khi cài:
  - Kiểm tra bản marketplace chính thức trên máy: commit khác bản đã kiểm duyệt, nhưng file của 5 plugin sắp cài giống hệt từng byte.
  - Kiểm tra các file và thư mục sắp bị sửa.
- [x] Sửa `install.py` để ghi lại và gỡ được sạch:
  - `INSTALLED.md` ghi mọi lần cài;
  - `--rollback` gỡ mọi lần cài, mới nhất trước;
  - `vendor/` có marketplace riêng và không đưa vào git;
  - mỗi lần gỡ xóa đúng các thư mục do lần cài tạo;
  - chụp cấu hình trước khi cài, rồi dọn `enabledPlugins`, `extraKnownMarketplaces`, cache và dữ liệu plugin khi gỡ.
- [x] Lỗi lộ ra khi làm, đã sửa và có test:
  - hai lần chạy cùng một giây ghi đè bản chụp;
  - lệnh gỡ chọn nhầm nhật ký cũ vì sắp theo tên file;
  - lần cài sau xóa bản ghi lần trước;
  - lệnh "đã có" bị ghi như một thay đổi.
- [x] Ghi quyết định của bạn vào `vetted.lock` (bạn đồng ý trong chat, mình gõ lệnh), rồi chạy `./install.sh --apply`: 28 thay đổi, 0 lỗi.
- [x] Kiểm chứng sau khi cài:
  - cả 7 plugin đều bật;
  - file của plugin đã cài khớp bản đã kiểm duyệt (chỉ thêm file `.in_use` do Claude Code tạo);
  - phiên `claude -p` cho thấy CLI nạp plugin tại chỗ;
  - desktop app chạy bản chép trong cache, nên thêm file `plugin/.agent-stack-home` để bản chép tìm về repo, và bước `plugin update`.
- [x] Có một phiên SCEE được resume lúc 15:24, trước khi có file trỏ. Hook của phiên đó ghi trạng thái vào `~/.claude/plugins/data/agent-stack-inline`. Hook chỉ đọc SCEE, không sửa gì; thư mục đó sẽ được dọn khi gỡ.
