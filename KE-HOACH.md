# Kế hoạch: hệ thống làm việc Claude Code + OpenCode

> Lập ngày 2026-10-01. Trạng thái: **bản kế hoạch, chưa triển khai gì**.
> Bổ sung cùng ngày: yêu cầu **#7**, theo dõi tiến độ project, việc cần làm tiếp và việc dang dở (mục 7.8, GĐ2b).
> Cập nhật lần 2 (2026-10-01): bỏ Jev; bắt đầu triển khai. Tiến độ thực hiện theo dõi ở [`PLAN.md`](PLAN.md).
> Cập nhật lần 3 (2026-10-02): rà soát nguồn chính thức của Anthropic, quyết định dùng lại hay tự làm ở mục 6.13.

**Quyết định đã chốt (2026-10-01):**
- Bỏ Jev khỏi kế hoạch. Router chỉ còn tầng A (luật từ khóa) và tầng B (model local).
- Chỉ làm việc trong `agent-stack/`. Không đụng các project khác. Không sửa `~/.claude` hay `~/.config/opencode` cho tới khi bạn duyệt chạy `install.sh`.
- Claude viết v1 các skill lõi kèm test, bạn review.
- Commit sau mỗi giai đoạn trong repo `agent-stack` (không push).
- Đóng gói thành **plugin Claude Code** đặt ở `agent-stack/plugin/`, thử bằng `claude --plugin-dir`, không cần symlink. OpenCode dùng skill qua `~/.config/opencode/skills/` khi cài (mục 7.1).
> Căn cứ: docs chính thức Claude Code (code.claude.com) và OpenCode (opencode.ai), số liệu GitHub API lấy ngày 2026-10-01, và cấu hình thực tế trên máy bạn. Nguồn ở mục 11.
> File này nằm trên đĩa nên không mất khi phiên hết hạn mức. Đó cũng là nguyên tắc chính của yêu cầu #3.

**Ký hiệu:** ✍️ bạn tự viết (Claude hướng dẫn và review, đúng nguyên tắc học-qua-build của bạn) · 📦 cài từ nguồn đã qua kiểm duyệt · ⚙️ chỉ cấu hình

---

## 0. Tóm tắt

Bảy yêu cầu của bạn thực chất là **một hệ thống bốn lớp**, không phải bảy món rời:

1. **Kho năng lực** (yêu cầu #1, #6): skills, MCP, plugin đã kiểm duyệt.
2. **Định tuyến** (#2, #4, #5): chọn skill nào, model và effort nào, giao cho agent nào. Ba yêu cầu này là cùng một bài toán ở ba mức chi tiết, nên chỉ cần **một** bộ luật và **một** hook.
3. **Bền bỉ phiên** (#3, #7): trạng thái công việc nằm trên đĩa, nên Claude Code hay OpenCode đều tiếp tục được. #3 lo **ghi** trạng thái; #7 lo **đọc** trạng thái đó để báo tiến độ, việc dang dở và việc nên làm tiếp.
4. **Kiểm chứng** (lớp mới, yêu cầu gốc còn thiếu): đo xem đổi model/effort có giữ được chất lượng không. Bạn đặt "giữ nguyên hiệu suất" là **bắt buộc**, mà không đo thì không thể biết mình có giữ được hay không.

Năm phát hiện quan trọng nhất:

| # | Phát hiện | Hệ quả cho kế hoạch |
|---|---|---|
| 1 | Claude Code **có sẵn** cơ chế tự chờ rồi làm tiếp khi chạm giới hạn 5 giờ (`autoContinueAtUsageLimit`, từ v2.1.234), nhưng khóa này **mặc định chưa đặt**, nên phải bật; `install.py` đặt `true` nếu bạn chưa tự chọn. (Bản trước của kế hoạch ghi nhầm là mặc định bật; đã sửa ngày 02/10/2026 theo [tài liệu chính thức](https://code.claude.com/docs/en/settings-reference.md).) Cơ chế này **không** xử lý: giới hạn tuần, phiên `-p` hoặc background, phiên đã thoát, và crash. | Skill #3 chỉ cần lấp các khoảng trống đó, không viết lại cơ chế retry. |
| 2 | Kho skill công khai có rủi ro thật. Snyk quét 3.984 skill (02/2026): **13,4% có lỗi nghiêm trọng**, 76 payload độc. Chiến dịch ClawHavoc có 341 skill độc phát tán phần mềm đánh cắp dữ liệu **cho macOS**. | Dựng cổng kiểm duyệt **trước** khi cài bất cứ thứ gì. |
| 3 | Số đo của Anthropic: **hạ effort trên model mạnh thường giữ chất lượng tốt hơn đổi sang model yếu.** Haiku 4.5 chỉ đạt 63% so với 92% của Opus ở câu hỏi kiến thức. | Quy tắc: hạ effort trước, hạ model sau, và mọi thay đổi phải qua eval. |
| 4 | **Hook không thể đổi model hay effort** (docs chính thức), và đổi model giữa chừng làm mất prompt cache. | Router chỉ **gợi ý**, bạn tự đổi ở ranh giới việc. Không tự động đổi theo từng tin nhắn. |
| 5 | Danh sách task có sẵn của Claude Code **không bật mặc định trên Opus 5.5 và Sonnet 5.5**, và chỉ dùng chung giữa các phiên khi đặt `CLAUDE_CODE_TASK_LIST_ID`. Trong khi đó `SCEE/PLAN.md` của bạn đã có sẵn mẫu rất tốt: mục §0 "Đang ở đâu, việc tiếp theo". | Skill #7 lấy file Markdown theo mẫu SCEE làm nguồn sự thật. Task list chỉ là công cụ phụ trong phiên. |

Lộ trình ban đầu: 9 giai đoạn (GĐ0 đến GĐ7, cộng GĐ2b), khoảng **14–18 buổi × 2 giờ**. GĐ4 và GĐ5 có thể tính vào giờ lab của trục AI Engineer. Sau đó có thêm GĐ6b (giong-van theo nghiên cứu), GĐ8 (reuse-best), GĐ9 (sửa sau rà soát) và GĐ10 (chọn skill theo project, gợi ý sau mỗi câu trả lời). Tiến độ thật nằm ở mục §0 của `PLAN.md`.

---

## 1. Hiện trạng máy bạn (đã kiểm tra ngày 2026-10-01)

| Thành phần | Hiện trạng | Nhận xét |
|---|---|---|
| Claude Code CLI | 2.1.267 (Homebrew cask `claude-code`) | Bản mới nhất khoảng 2.1.286. Bản của bạn **chưa có**: đọc `AGENTS.md` trực tiếp (cần ≥2.1.277), `/doctor prompt-audit` (cần ≥2.1.283). Cần nâng cấp. |
| Model mặc định | `"model": "sonnet"` (Sonnet 5.5) | Hợp lý về chi phí. Mặc định của gói Pro/Max là Opus 5.5. |
| `switchModelsOnFlag: false` | Khi bộ lọc an toàn gắn cờ (ví dụ nhóm "cyber", dễ gặp khi học security), Claude dừng lại để bạn chọn, thay vì tự chuyển sang Opus 4.8. | Giữ nguyên, hợp với hướng security. |
| `enableWorkflows: true` + `skipWorkflowUsageWarning: true` | Workflow/ultracode có thể sinh rất nhiều agent, và bạn đã tắt cảnh báo usage. | ⚠️ Nên bật lại cảnh báo, vì đây là nguồn đốt hạn mức nhanh nhất. |
| Skill, agent, hook cá nhân | Trống (`~/.claude/skills`, `agents`, `hooks` chưa tồn tại) | Nền sạch, thuận lợi. |
| Plugin | Đã thêm marketplace chính thức `claude-plugins-official` (314 plugin), chưa cài plugin nào. | |
| Skill đồng bộ từ claude.ai | skill-creator, pdf/docx/xlsx/pptx, paper-anatomy (của bạn), consolidate-memory… | Tận dụng, không cài trùng. |
| OpenCode | v2.0.12 (cask `opencode-v2`). Model mặc định `opencode/muse-spark-1.3-contributor-free`. Provider `tuf` (llama-server trong LAN, 192.168.1.13) có gpt-oss 20B, Coder 4B/9B, Qwen3.5 4B/9B (Phi-4-mini đã gỡ ngày 05/10/2026). | Worker miễn phí tốt cho việc cơ học, nhưng chỉ dùng được khi ở mạng nhà. |
| Khối `providers` → `openai-oauth` trong `opencode.jsonc` | Đã kiểm chứng bằng `opencode debug config`: OpenCode v2 nhận cả khối này lẫn khối `provider` kiểu v1 (tự chuyển sang `providers`). | Không cần sửa. Nhận định ban đầu (khối bị bỏ qua) là sai, vì docs mình đọc lúc đầu là của v1. |
| jcode v0.86.0 | Harness dùng OAuth của Claude Max/ChatGPT Pro, có hook SessionStart. | ⚠️ Rủi ro điều khoản dịch vụ (mục 9). |
| Ollama 0.34.2, `gh` (đã đăng nhập), uv, Node 24, Python 3.11 | | Đủ công cụ cho mọi giai đoạn. |
| Dấu vết tiến độ hiện có | SCEE: `PLAN.md` có §0 "Đang ở đâu, việc tiếp theo" và checklist kiểm tra sau khi bị ngắt vì hết limit. Ba thư mục học: `PROGRESS.md` + `ROADMAP.md` dạng checkbox, **không phải git repo**. pdf-translator: 1 file chưa commit. XiaomiMiMo: 138 file chứa TODO/FIXME, phần lớn là code bên thứ ba. | Mẫu §0 của SCEE nên thành chuẩn chung. Quét TODO phải loại code bên thứ ba. |
| Task list có sẵn (`~/.claude/tasks/`) | Trống | Không bật mặc định trên model 5.5 (mục N7). |

---

## 2. Đánh giá bảy yêu cầu

| # | Yêu cầu | Điểm tốt | Vấn đề, khoảng trống | Hướng xử lý |
|---|---|---|---|---|
| 1 | Nghiên cứu skills/MCP/plugins cho coding, research, build-ship-production, benchmark, QA, security, reuse-best | Phạm vi đúng, có ý thức "luôn kiểm tra" | (a) Câu "(luôn kiểm tra" bị cắt; ngày 02/10 bạn làm rõ: nó thuộc reuse-best, nghĩa là trước khi build hay làm gì đều tìm thứ có sẵn tốt nhất (công cụ trên GitHub, bài nghiên cứu SOTA). (b) **Cài nhiều là phản tác dụng**: phần mô tả skill chỉ được khoảng 1% context window, vượt ngân sách thì mô tả bị cắt và skill kích hoạt kém. Mỗi MCP thêm nhiễu. (c) 13% skill công khai có lỗi nghiêm trọng. | Thang quyết định "dùng lại" (N3), cổng kiểm duyệt (7.6), giới hạn khoảng 20 skill bật toàn cục. |
| 2 | Subagent Sonnet/Haiku/OpenCode, giữ hiệu suất, rẻ hơn càng tốt | Đúng hướng: chia việc theo độ khó | "Giữ nguyên hiệu suất" chưa có cách đo. Haiku không thay được model lớn ở việc khó. Model local 4B–20B yếu hơn nhiều. **Subagent vẫn ăn chung hạn mức.** | Bộ eval nhỏ (7.7), và mọi output từ tầng rẻ phải qua cổng chất lượng (test, lint, review). |
| 3 | Skill chống mất dữ liệu khi hết limit hoặc qua phiên mới | Đúng nỗi đau thật | Retry ở giới hạn 5 giờ đã có sẵn. Khoảng trống thật là: giới hạn tuần, crash, `-p`/background, đổi công cụ, và compaction làm rơi chi tiết. | Trạng thái trên đĩa, git checkpoint, bàn giao sang OpenCode (7.3). |
| 4 | Luôn dùng skill, có skill chọn skill | Đúng tinh thần tái sử dụng | "Luôn" dễ biến thành ép skill vào việc vặt (tốn token, lệch hướng). | Gộp vào router (7.4). |
| 5 | Sau mỗi tin, gợi ý model, effort, subagent cho bước tiếp | Rất hữu ích để tự kỷ luật chi phí | Hook không đổi được model/effort. Đổi liên tục làm mất cache, nên có thể **đắt hơn**. | Chỉ gợi ý (dòng ➡️ cuối câu trả lời + hook), chỉ đổi ở ranh giới việc. |
| 6 | Viết như người thật, tránh trang phát hiện AI | Muốn văn bản tự nhiên, có hồn | Detector không đáng tin, báo nhầm cả bài người thật viết, nhất là người viết bằng ngôn ngữ thứ hai. Chính humanizer (53k★) tuyên bố không nhằm qua mặt detector. Skill có sẵn chỉ hỗ trợ tiếng Anh. Với bài nộp có quy định về AI, mục tiêu "né detector" là vi phạm. | Đổi mục tiêu thành: **giọng văn của chính bạn** + bỏ dấu hiệu văn AI. Bạn viết ý hoặc nháp, skill chỉnh (7.5). |
| 7 | Theo dõi tiến độ project, cần làm gì tiếp theo, task dang dở | Đúng nhu cầu khi chạy nhiều project song song (SCEE, pdf-translator, ba lộ trình học…) | Dễ thành một hệ thống quản lý thứ hai, lệch với file kế hoạch đang có. Task list có sẵn không bật mặc định trên model 5.5. Để LLM tự quét repo mỗi lần thì tốn token. Quét TODO bị nhiễu bởi code bên thứ ba. | Dùng lại mẫu §0 của `SCEE/PLAN.md` làm chuẩn. Script thu thập dữ liệu (0 token), LLM chỉ xếp hạng. Bản tóm tắt chạy miễn phí ở đầu mỗi phiên (7.8). |

---

## 3. Làm rõ: các giả định đang dùng

| Mã | Giả định | Nếu sai thì sao |
|---|---|---|
| G1 | "(luôn kiểm tra" nghĩa là luôn kiểm tra **bảo mật, độ bảo trì và giấy phép** trước khi cài. | Đổi tiêu chí ở cổng kiểm duyệt. |
| G2 | "Rẻ hơn" là **tốn ít hạn mức gói thuê bao** (cửa sổ 5 giờ và tuần), không phải tiền API. | Nếu dùng API key thì đo bằng đô la. |
| G3 | OpenCode đóng hai vai: (a) worker cho việc cơ học bằng model local hoặc miễn phí, (b) phương án dự phòng khi hết hạn mức tuần của Claude. Không chạy tài khoản Claude bên trong OpenCode. | |
| G4 | Viết luận là cho bài của chính bạn (blog, email, tài liệu, hồ sơ cho phép dùng AI), bằng tiếng Việt và tiếng Anh. | |
| G5 | **Đã chốt:** Claude viết v1 các skill lõi (vet-skill, session-keeper, tien-do, task-router, giong-van) kèm test và ghi chú thiết kế; bạn review. | — |
| G6 | "Project" gồm mọi thư mục trong `~/Documents/Claude/`, kể cả ba thư mục học. Nguồn sự thật về tiến độ là file Markdown trong project, không phải công cụ quản lý task bên ngoài. | Nếu bạn muốn GitHub Issues hoặc beads làm nguồn chính thì đổi tầng dữ liệu của skill #7. |

Các câu hỏi cần bạn trả lời nằm ở mục 10.

---

## 4. Liên kết: một kiến trúc chung

```
┌────────────────────────── Lớp 0: Nền chung (repo git agent-stack) ──────────────────────────┐
│ AGENTS.md (luật chung, cả Claude Code và OpenCode đều đọc) · ~/.claude/skills (một kho skill) │
│ vetted.lock (danh sách đồ bên thứ ba đã kiểm, ghim commit SHA)                               │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
        │
prompt ─┼─► [Lớp 2: Định tuyến]  hook UserPromptSubmit + router-rules.json
        │        └─► gợi ý: skill · model · effort · subagent   (#4, #5)
        │                  │                         │
        │                  ▼                         ▼
        │   [Lớp 1: Kho năng lực]          [Đội agent]                                    (#2)
        │   skills/MCP/plugin đã kiểm      Explore(haiku) · researcher(sonnet)
        │   (#1, #6)                        reviewer(opus) · test-runner(haiku)
        │                                   oc-worker ─► OpenCode (model local, miễn phí)
        │                  │                         │
        │                  └───────────┬─────────────┘
        │                              ▼
        ├─► [Lớp 3: Bền bỉ]  PLAN §0 · PROGRESS · HANDOFF + git checkpoint          (#3 ghi)
        │        ├─ hết 5 giờ  → Claude Code tự chờ rồi làm tiếp (sẵn có)
        │        ├─ hết hạn mức tuần, crash → mở OpenCode, đọc HANDOFF, làm tiếp
        │        └─ tien-do: đọc PLAN/PROGRESS + git + mốc test → tiến độ, việc dang dở,
        │           việc tiếp theo (kèm gợi ý model/effort lấy từ router)       (#7 đọc)
        │
        └─► [Lớp 4: Kiểm chứng]  skill verify trước commit · claude plugin eval (so model)
                                 · /usage (phân bổ theo skill/subagent/MCP)    (ràng buộc "giữ hiệu suất")
```

**Sáu mối liên kết:**

1. **#2, #4, #5 là một bộ định tuyến** ở ba mức chi tiết: skill nào, model+effort nào, ai làm. Dùng một file luật `router-rules.json` và một hook. Bảng luật lấy từ kết quả eval ở GĐ4, không đoán.
2. **#3 là điều kiện để #2 dùng OpenCode làm dự phòng.** Trạng thái lưu ở dạng trung lập (Markdown + git), và cả hai công cụ đều đọc chung `AGENTS.md` cùng `~/.claude/skills/`.
3. **#1 cung cấp danh mục để #4 định tuyến tới**, và cổng kiểm duyệt bảo vệ #1.
4. **#6 là một skill trong danh mục.** Router gọi nó khi gặp việc viết.
5. **Lớp 4 biến "bắt buộc giữ hiệu suất" thành con số.** Mọi thay đổi model, effort hay agent phải qua lớp này.
6. **#7 là mặt "đọc" của #3.** #3 ghi trạng thái, #7 đọc lại để báo tiến độ. Hai yêu cầu dùng **chung một file**: mục §0 trong `PLAN.md` vừa là chỗ #3 ghi bàn giao, vừa là nguồn chính của #7. Mỗi việc tiếp theo mà #7 đề xuất được gắn gợi ý model/effort/subagent từ bảng định tuyến (#5). #7 cũng dùng mốc test của lớp 4 để phát hiện hồi quy.

**Nền chung giữa hai công cụ (đã kiểm chứng trong docs):**

- Claude Code đọc `AGENTS.md` trực tiếp từ v2.1.277. Mặc định nó chỉ đọc khi không có `CLAUDE.md`; muốn đọc cả hai thì đặt **Project instructions** = `claude-md-and-agents-md`, hoặc thêm `@AGENTS.md` vào `CLAUDE.md`.
- OpenCode đọc `AGENTS.md`, không có thì đọc `CLAUDE.md`. Ở mức toàn cục, nó đọc `~/.config/opencode/AGENTS.md`, không có thì đọc `~/.claude/CLAUDE.md`.
- OpenCode tự tìm skill trong `~/.claude/skills/`, `~/.agents/skills/`, `~/.config/opencode/skills/` và các thư mục tương ứng trong project. Vậy **một kho skill dùng được cho cả hai**.
- Chuẩn Agent Skills (agentskills.io): các trường riêng của Claude Code (`model`, `effort`, `context: fork`, `hooks`, `paths`) bị OpenCode bỏ qua, không gây lỗi.
- Để chạy được ở cả hai: `name` dài 1–64 ký tự, chỉ chữ thường và gạch nối; `description` **≤ 1.024 ký tự** (giới hạn của OpenCode; Claude Code cho tới 1.536).

---

## 5. Hoàn thiện và nâng cấp: những gì yêu cầu gốc còn thiếu

**N1. Lớp đo lường (bắt buộc).** Không có eval thì "giữ hiệu suất" chỉ là hy vọng. Claude Code có sẵn `claude plugin eval`: chạy bộ case có plugin so với không plugin, có cờ `--model` để so model, có grader miễn phí (regex, tool_used, file_exists) và grader có giám khảo. Mỗi lượt chạy tính vào hạn mức. Thiết kế ở 7.7.

**N2. Nguyên tắc định tuyến dựa trên số đo của Anthropic** (lấy từ hướng dẫn tối ưu chi phí trong skill `claude-api`; đo trên Fable 5 và Opus 5, cần đo lại trên bản 5.5, đó chính là GĐ4):

- **Hạ effort trước, hạ model sau.** Việc nghiên cứu: đường cong gần phẳng, `medium` đạt bằng mức mặc định với 70–85% chi phí. Coding dài hơi thì có đánh đổi thật: `medium` mất khoảng 2 điểm và tốn một nửa chi phí; `low` mất khoảng 8 điểm và tốn một phần tư.
- **Chạy rẻ trước, hỏng thì chạy lại ở mức cao.** Kết quả khoảng 93% đạt với khoảng một nửa chi phí, so với 91,7% khi chạy mọi thứ ở mức mặc định. Chỉ áp dụng khi có tín hiệu thất bại tự động như test hoặc linter.
- **Haiku 4.5** hợp việc khối lượng lớn mà kết quả kiểm tra được. Không hợp vòng agent dài.
- **Mô hình "điều phối viên + worker rẻ"** chỉ có lời khi có nhiều phần việc độc lập. Với một chuỗi việc phụ thuộc nhau, một model mạnh ở effort thấp hơn thường thắng.
- **Cache gắn với từng model.** Đổi model hoặc effort giữa chừng làm mất cache, nên chỉ đổi ở ranh giới việc (sau `/clear` hoặc khi sang việc mới).

**N3. Thang quyết định "dùng lại tốt nhất" (reuse-best).** Đây là ý của chữ "luôn kiểm tra" trong yêu cầu #1: trước khi build hay làm gì không tầm thường, tìm thứ có sẵn tốt nhất, kể cả công cụ trên GitHub và bài nghiên cứu SOTA. Skill `reuse-best` (mục 7.9) làm việc này cho mọi việc build. Với skill, plugin và MCP, dừng ở bậc đầu tiên đáp ứng được:
tính năng có sẵn → plugin hoặc skill chính thức của Anthropic → plugin chính chủ của hãng (Microsoft Playwright, Semgrep…) → repo cộng đồng (≥1k★, có cập nhật trong 3 tháng, giấy phép rõ, qua cổng kiểm duyệt) → ✍️ tự viết.

**N4. Ngân sách ngữ cảnh.** Tối đa khoảng 20 skill bật toàn cục; phần còn lại để theo project hoặc đặt `skillOverrides: "name-only"`. Tối đa 4 MCP. Ưu tiên CLI hơn MCP: docs khuyên dùng `gh` thay GitHub MCP vì tiết kiệm context hơn. Mỗi tháng chạy `/skill-doctor`, `/context`, `/usage`.

**N5. Cổng kiểm duyệt chuỗi cung ứng** (7.6): thứ tìm được ở N3 phải qua cổng này trước khi cài.

**N6. Một repo git `agent-stack` làm nguồn sự thật**, symlink vào `~/.claude/` và `~/.config/opencode/`. Có lịch sử thay đổi, dễ sao lưu và chuyển máy.

**N7. Tính năng có sẵn nên dùng (ít người biết):**

| Tính năng | Tác dụng |
|---|---|
| Alias `opusplan` | Opus khi lập kế hoạch, Sonnet khi thực thi. Đây là một router có sẵn. |
| `autoContinueAtUsageLimit` | Tự chờ và làm tiếp khi chạm giới hạn 5 giờ, tự kích hoạt lại tối đa 2 lần liên tiếp. |
| Skill `/verify` có sẵn | Claude Code có sẵn skill `/verify` để build, chạy và quan sát thay đổi ([blog Anthropic, 07/2026](https://claude.com/blog/building-verification-loops-in-claude-code-with-skills)). Theo một bài tổng hợp của bên thứ ba, từ v2.1.215 nó chỉ chạy khi được gọi. Nhận định cũ trong kế hoạch này rằng nó "tự chạy trước khi commit từ v2.1.284" không kiểm chứng được nên đã bỏ. agent-stack không viết skill `verify` riêng; phần còn thiếu (ghi kết quả kiểm tra cho phiên sau) do `session-keeper/scripts/receipt.py` làm. |
| `model:` / `effort:` trong frontmatter skill và subagent | Gán model theo từng việc. |
| `ultrathink` trong prompt | Nghĩ sâu hơn cho đúng một lượt, không đổi effort của phiên. |
| `/usage` | Phân bổ hạn mức theo skill, subagent, plugin, MCP. `/insights` cho báo cáo thói quen làm việc. |
| `/skill-doctor`, `/doctor prompt-audit` | Tìm skill tốn ngân sách mà ít dùng; tìm chỉ dẫn lỗi thời hoặc mâu thuẫn. |
| `--fallback-model` | **Chỉ** dùng khi model quá tải. Không cứu được hạn mức (hạn mức tính chung cho mọi model). |
| `/goal <điều kiện>` | Claude làm tiếp cho đến khi một điều kiện kiểm chứng được (test pass, `git status` sạch…) thành đúng. Goal được khôi phục khi resume; chạm hạn mức thì tạm dừng rồi tự làm tiếp khi hết chờ. Hợp để "làm nốt việc dang dở". |
| `/recap`, session recap | Tóm tắt phiên trong ≤ 400 ký tự khi bạn quay lại (tự động, hoặc gõ `/recap`). |
| Task list (`Ctrl+T`) | Checklist trong phiên, giữ được qua compaction; dùng chung giữa các phiên bằng `CLAUDE_CODE_TASK_LIST_ID=<tên>`. **Không bật mặc định trên Opus 5.5 và Sonnet 5.5**, phải đặt thêm `CLAUDE_CODE_ENABLE_TODO_TOOLS=1`. |

**N8. Gắn với lộ trình học.** Router cộng eval là một dự án L2 lên L3 đúng nghĩa trong trục AI Engineer của bạn (skill có output cấu trúc và có eval, rồi điều phối nhiều skill). Còn `vet-skill` thuộc trục security, mảng supply chain của agent, giao điểm AI × Security trong `LO-TRINH-TONG-QUAN.md`.

---

## 6. Kết quả nghiên cứu: danh mục đề xuất

★ = GitHub stars ngày 2026-10-01 · CC = Claude Code · OC = OpenCode · "chính thức" = có trong marketplace `claude-plugins-official`

**Nguồn tra cứu chính:** [anthropics/skills](https://github.com/anthropics/skills) (179k★), marketplace chính thức (314 plugin, đã có trên máy), [skills.sh](https://skills.sh) (Vercel, cài bằng `npx skills add <owner/repo>`), [agentskills.io](https://agentskills.io) (chuẩn mở), các danh sách awesome-claude-code (55k★), ComposioHQ/awesome-claude-skills (76k★), VoltAgent/awesome-agent-skills (35k★), awesome-opencode (10k★).

### 6.1 Coding

| Tên | Loại | ★ / cập nhật | CC/OC | Đề xuất | Ghi chú |
|---|---|---|---|---|---|
| superpowers (obra) | plugin skills | 294k / 09-27 | CC (chính thức), OC | **Thử ở 1 project trước** | Quy trình bắt buộc: brainstorm → plan → subagent → TDD → verify. Có cơ chế "kiểm tra skill trước mọi việc", liên quan #4. Nặng, có chủ kiến riêng, trùng vai với bộ của Matt Pocock. |
| mattpocock/skills | skills | 273k / 09-29 | CC, OC | **Cài lẻ**: grill-me, tdd, diagnosing-bugs, handoff | `handoff` phục vụ trực tiếp #3. `ask-matt` là router cho bộ skill của ông. |
| feature-dev, code-review, pr-review-toolkit, code-simplifier, commit-commands | plugin chính thức | — | CC | Chọn 2–3 theo nhu cầu | Của Anthropic. |
| pyright-lsp, clangd-lsp (+ typescript/rust nếu cần) | plugin chính thức | — | CC | **Cài** Python và C/C++ | Nhảy tới định nghĩa thay vì grep, giảm đọc file thừa. clangd hợp hướng bán dẫn và firmware. Đổi ngày 03/10/2026: chỉ bật riêng từng project khi router đề xuất (project lớn hoặc có cấu hình kiểm kiểu, biên dịch). |
| context7 | MCP | 62.6k / 10-01 | CC, OC | **Cài** | Tra docs thư viện bản mới nhất. |
| serena | MCP | 29.9k / 09-30 | CC, OC | Thử khi repo lớn | Trùng một phần với plugin LSP. |
| wshobson/agents | plugin | 40.1k / 09-29 | CC, OC | Tham khảo, lấy lẻ | Hỗ trợ nhiều harness. |
| github/spec-kit | bộ công cụ | 139.6k / 09-30 | CC, OC | Để sau | Spec-driven development, hợp dự án lớn. |

### 6.2 Research

| Tên | Loại | ★ / cập nhật | CC/OC | Đề xuất | Ghi chú |
|---|---|---|---|---|---|
| `/deep-research`, WebSearch, WebFetch | có sẵn | — | CC | **Dùng ngay** | |
| Tavily | MCP / plugin chính thức | 2.4k / 09-29 | CC, OC | Đã kết nối trong desktop app | search, extract, crawl, research. |
| exa, firecrawl | plugin chính thức | 5.1k / 7.5k | CC | Tùy chọn | |
| K-Dense scientific-agent-skills | skills | 47.2k / 10-01 | CC, OC | Thử chọn lẻ | Đọc paper khoa học, hợp trục bán dẫn và AI. |
| paper-anatomy (của bạn) | skill | — | CC | **Dùng tiếp** | Đã có sẵn. |
| `research` (mattpocock) | skill | — | CC, OC | Thử | Ưu tiên nguồn gốc (primary sources). |

### 6.3 Build, ship, production

| Tên | Loại | ★ / cập nhật | CC/OC | Đề xuất | Ghi chú |
|---|---|---|---|---|---|
| `gh` CLI | CLI | — | CC, OC | **Dùng thay GitHub MCP** | Đã đăng nhập sẵn. |
| `/security-review`, `/code-review`, `/ultrareview` | có sẵn | — | CC | Dùng trước khi merge | `/ultrareview` chạy trên cloud và **tính phí**. |
| claude-code-security-review | GitHub Action | 6.3k / 02-11 | CI | Khi có repo dùng CI | |
| sentry, vercel, cloudflare, railway… | plugin chính thức | — | CC | Chỉ khi dùng dịch vụ đó | |
| langfuse, deepeval, mlflow | plugin chính thức | — | CC | Khi build ứng dụng LLM | Observability và eval cho trục AI Engineer. |
| Skill PRR + threat model (security-whitebox) | ✍️ skill | — | CC, OC | Làm theo roadmap | Bản tham khảo đã có trong `reference/skills/`. |

### 6.4 Benchmark và eval

| Tên | Loại | ★ / cập nhật | Đề xuất | Ghi chú |
|---|---|---|---|---|
| `claude plugin eval` | có sẵn | — | **Dùng ở GĐ4–5** | So có/không plugin; `--model` để so model; `--max-cost-usd` đặt trần. |
| skill-creator (evals/evals.json) | skill chính thức | — | Dùng khi viết skill | Đã có sẵn qua claude.ai. |
| promptfoo | CLI | 25.6k / 10-01 | Khi làm ứng dụng LLM | Có red-team, hợp trục AI security. |
| inspect_ai (UK AISI) | framework | 2.9k / 10-01 | Khi học eval bài bản | |
| hyperfine | CLI | 28.9k / 04-30 | `brew install hyperfine` | Benchmark thời gian chạy lệnh. |
| codspeed, k6 (AGPL) | plugin / CLI | — / 31.7k | Tùy chọn | Hiệu năng, kiểm thử tải. |
| session-report (chính thức), ccusage | plugin / CLI | — / 18.8k | **Cài** | Đo token, cache, subagent. Phục vụ baseline GĐ0. |

### 6.5 QA

| Tên | Loại | ★ / cập nhật | CC/OC | Đề xuất | Ghi chú |
|---|---|---|---|---|---|
| webapp-testing (anthropics/skills) | skill | 179k | CC, OC | **Cài** | |
| playwright (Microsoft) | MCP / plugin chính thức | 37.7k / 09-28 | CC, OC | **Cài** | Kiểm thử e2e. |
| chrome-devtools-mcp | MCP | 52.8k / 10-01 | CC, OC | Tùy chọn | Debug hiệu năng trình duyệt. |
| `/verify` có sẵn + biên nhận kiểm tra | có sẵn + ⚙️ script | — | CC, OC | **Dùng** | Dùng `/verify` có sẵn để kiểm tra; ghi kết quả bằng `receipt.py` để `tien-do` biết kết quả còn khớp code hay đã cũ. |
| mutation-testing (Trail of Bits) | skill | 7.3k | CC | Thử | Đo xem test có bắt được lỗi thật không. |
| tdd (mattpocock) hoặc TDD (superpowers) | skill | — | CC, OC | Chọn **một** | Tránh hai skill tranh nhau kích hoạt. |

### 6.6 Security (whitebox, phòng thủ)

| Tên | Loại | ★ / cập nhật | Đề xuất | Ghi chú |
|---|---|---|---|---|
| trailofbits/skills: differential-review, static-analysis, audit-context-building, variant-analysis, c-review, constant-time-analysis, zeroize-audit | skills | 7.3k / 09-28 (CC-BY-SA-4.0) | **Cài chọn lọc** | Rất hợp trục security và bán dẫn (C/C++, crypto). Giấy phép share-alike nếu bạn phân phối lại bản sửa. |
| security-guidance, claude-security | plugin chính thức | — | Thử | security-guidance review diff bằng LLM, nên tốn hạn mức. |
| semgrep | plugin chính thức + CLI | 16.8k | **Cài** | Repo `semgrep/mcp` cũ đã archived, dùng plugin chính thức. |
| gitleaks / trufflehog | CLI | 29.6k / 28.2k | **Cài gitleaks** | Quét secret trước commit. |
| osv-scanner / trivy | CLI | 11.1k / 38.2k | Cài một | Lỗ hổng trong dependency. |
| garak (NVIDIA), promptfoo red-team | CLI | 9.4k / 25.6k | Khi học AI security | Quét lỗ hổng của LLM. |
| skill-scanner (Cisco) | CLI | 2.6k / 10-01 | **Cài ở GĐ1** | Lõi chạy local, không cần API key. |
| agent-scan (Snyk) | CLI | 3.1k / 09-30 | Tùy chọn | Cần `SNYK_TOKEN`, gửi thông tin thành phần lên Snyk. |

### 6.7 Reuse-best và meta

| Tên | Loại | Đề xuất | Ghi chú |
|---|---|---|---|
| claude-code-setup | plugin chính thức | **Chạy 1 lần mỗi project** | Phân tích codebase rồi đề xuất hook, skill, MCP, subagent phù hợp. |
| claude-md-management, hookify | plugin chính thức | Cài | Giữ CLAUDE.md gọn; tạo hook từ mẫu hội thoại. |
| skill-creator | skill | Có sẵn | Viết skill và chạy eval cho skill. |
| find-skills (skills.sh) | skill | **Chỉ dùng để tìm** | Đứng đầu skills.sh với 3,6 triệu lượt cài trong 8 tuần. Cài thì phải qua cổng kiểm duyệt. |
| `/doctor prompt-audit`, `/skill-doctor`, `/insights` | có sẵn | Chạy hằng tháng | |

### 6.8 Bền bỉ phiên và hạn mức (cho #3)

| Tên | Loại | ★ / cập nhật | CC/OC | Đề xuất | Ghi chú |
|---|---|---|---|---|---|
| Tự chờ và làm tiếp ở giới hạn 5 giờ | có sẵn (≥2.1.234) | — | CC | **Bật** (mặc định chưa đặt; `install.py` đặt `autoContinueAtUsageLimit: true`) | Không áp dụng cho: hạn mức tuần, `-p`, background, phiên đã thoát. |
| `--continue`, `--resume <tên>`, `-n`, `/rename`, `/branch`, `/rewind`, resume-from-summary, auto-memory | có sẵn | — | CC | **Dùng** | |
| planning-with-files | skill + hooks | 27.2k / 09-27 | CC, OC (cả hai có hook) | 📦 **Thử 1 tuần làm nền** | Ba file kế hoạch, có hook SessionStart/PreCompact/Stop. Tác giả đo phục hồi trong 5 lượt, so với 13,3 khi không dùng. |
| handoff (mattpocock) | skill | — | CC, OC | Cài | Nén hội thoại để agent khác làm tiếp. |
| claude-mem | plugin | 95k / 10-01 | CC, OC | Để sau | Nặng (worker Bun, Chroma). Nén bằng AI nên tốn token. Có cloud sync tùy chọn. |
| beads | CLI | 27.6k / 10-01 | CC, OC | Để sau | Bộ nhớ dạng issue tracker cho dự án lớn. |
| Statusline 5h/7d | ⚙️ script | — | CC (terminal) | **Tự làm đơn giản** | Hoặc dùng ccstatusline (13.1k★). |

### 6.9 Định tuyến model (cho #2, #4, #5)

| Tên | Loại | ★ / cập nhật | Đề xuất | Ghi chú |
|---|---|---|---|---|
| `opusplan`, `model`/`effort` theo agent và skill, `/effort`, `ultrathink` | có sẵn | — | **Dùng** | Không cần cài gì. |
| Agent OpenCode có `model` riêng | có sẵn | OpenCode 211k | **Dùng** | |
| claude-code-router | gateway | 37.5k / 09-26 | Chưa cần | Cần API key của provider khác. |
| oh-my-openagent (tên cũ oh-my-opencode) | plugin OC | 69.7k / 10-01, giấy phép riêng | Tham khảo | Điều phối nhiều model trong OpenCode. |

### 6.10 Viết (cho #6)

| Tên | Loại | ★ / cập nhật | Đề xuất | Ghi chú |
|---|---|---|---|---|
| humanizer | plugin skill | 53.2k / 09-28 | **Cài** (tiếng Anh) | 26 dấu hiệu lấy từ trang "Signs of AI writing" của Wikipedia. Tác giả viết rõ: qua mặt detector không phải mục tiêu, và detector vẫn gắn cờ phần lớn output của nó. |
| stop-slop | skill | 17.7k / 03-17 | Tham khảo | |
| giong-van (VI + EN) | ✍️ skill | — | **Viết ở GĐ6** | Xem 7.5. |

### 6.11 Theo dõi tiến độ (cho #7)

| Tên | Loại | ★ / cập nhật | CC/OC | Đề xuất | Ghi chú |
|---|---|---|---|---|---|
| Mẫu §0 trong `SCEE/PLAN.md` | quy ước của bạn | — | CC, OC | **Chuẩn hóa thành mẫu chung** | Đã chạy tốt trong SCEE: một nguồn sự thật, mục "Đang ở đâu, việc tiếp theo", checklist kiểm tra sau khi bị ngắt. |
| `/goal`, `/recap`, task list, `/resume` theo tên, `claude agents` | có sẵn | — | CC | **Dùng** | Xem bảng N7. |
| project-artifact | plugin chính thức | — | CC | Thử cho project lớn (SCEE) | Trang trạng thái "sống" có dải "Next steps". Lấy trạng thái PR/CI qua `gh`; làm mới thì đăng lại đúng URL cũ. Cần đăng nhập claude.ai và có tính năng Artifact. |
| beads | CLI | 27.6k / 10-01 (MIT) | CC, OC | Để sau | Issue tracker dành cho agent, có quan hệ phụ thuộc giữa các việc; `bd ready` liệt kê việc không bị chặn. Hợp khi việc nhiều và đan xen. |
| Backlog.md | CLI + MCP | 6.9k / 09-28 (MIT) | CC, OC | Tham khảo | Task dạng Markdown nằm trong repo, có bảng kanban. |
| planning-with-files | skill | 27.2k | CC, OC | (đã có ở 6.8) | `tien-do` đọc được file `progress.md` của nó. |
| `tien-do` | ✍️ skill + script | — | CC, OC | **Viết ở GĐ2b** | Xem 7.8. |

### 6.12 Không khuyến nghị lúc này

| Tên | Lý do |
|---|---|
| get-shit-done (64k★) | Đã archived từ 05/2026. |
| claude-task-master (28.1k★) | Không cập nhật từ 04/2026, giấy phép không rõ ràng. |
| ccpm (8.4k★) | Không cập nhật từ 03/2026. |
| pal-mcp-server (zen) | Không cập nhật từ 12/2025. |
| Continuous-Claude-v3 | Không cập nhật từ 01/2026. |
| semgrep/mcp, open_deep_research | Đã archived. |
| ECC / everything-claude-code (270k★) | Gói "mọi thứ", trùng lặp hook và skill, làm phình context. Chỉ nên đọc để lấy ý. |
| SuperClaude, BMAD | Khung nặng, trùng vai superpowers. Quá tải cho người học một mình. |
| Skill từ ClawHub | Nơi xảy ra chiến dịch ClawHavoc (341 skill độc nhắm macOS). |
| Dùng tài khoản Claude Pro/Max trong công cụ bên thứ ba | Rủi ro điều khoản dịch vụ (mục 9). |

### 6.13 Rà soát nguồn chính thức của Anthropic (02/10/2026)

**Cách làm.** Năm lượt đọc song song, chỉ đọc, theo ba bước: (1) bốn plugin sát repo này nhất; (2) `anthropics/skills`, `anthropics/claude-code` và 13 plugin chính thức chưa xét; (3) kho mẫu, SDK, plugin công việc tri thức, rồi nhóm bảo mật, sandbox và marketplace cộng đồng. Nguồn là bản chép marketplace trên máy (commit `ab024cdcfa7c`, đúng bản trong `vetted.lock`) và GitHub API ngày 02/10/2026. Các dữ kiện quyết định (giấy phép, hook, số liệu, câu trích) đã được kiểm lại trực tiếp; phần chưa kiểm ghi ở 6.13.4. Chưa cài gì và chưa sửa code nào.

**Kết luận**
- Không mục nào đáng "dùng lại nguyên bản" ngoài `claude-security`, và chỉ để gọi tay khi cần quét sâu. Phần lớn thứ Anthropic có đã nằm sẵn trong Claude Code (`/code-review`, `/simplify`, `/security-review`, `/goal`, `/loop`, skill `claude-api`) hoặc trùng bản tự viết.
- Một mục đáng đưa vào lộ trình: **sandbox-runtime**, để `vet-skill` có phân tích động. Đây là lỗ hổng thật duy nhất tìm thấy, vì `vet.py` hiện chỉ phân tích tĩnh.
- Các ý nên lấy để nâng cấp bản tự viết, không chép code: `reviewer` (bước verifier phản biện, bảng lọc dương tính giả, mô tả "hình dạng" lỗi thay vì liệt kê loại lỗi, soi nuốt lỗi và test thiếu), `tien-do` (báo phần thay đổi), `session-keeper` (kiểm bằng agent không có ngữ cảnh), `vet-skill` (danh sách kiểm MCP), grader (rubric từng tiêu chí).
- Nên tránh: Stop hook tự lặp (`ralph-loop`) và `security-guidance` (SessionStart tự `pip install`, Stop gọi LLM mỗi lượt có sửa file).

**Giấy phép quyết định được chép hay chỉ học ý** (đọc từ file LICENSE; API trả `null` cho `claude-code` và `skills` vì giấy phép nằm ở từng thư mục)
- **Chỉ học ý:** `anthropics/claude-code` (kể cả `examples/` và `plugins/ralph-wiggum`; "All rights reserved", theo Commercial Terms); plugin `claude-security` (LICENSE riêng, đóng); skill `docx`, `pdf`, `pptx`, `xlsx` (source-available); `doc-coauthoring` (không có LICENSE.txt, coi là chưa xác định); `claude-agent-sdk-typescript` và `claude-agent-sdk-demos` (API báo không có giấy phép).
- **Chép được, giữ thông báo bản quyền và ghi nguồn:** Apache-2.0 gồm 16 trong 17 plugin đã xét ở bước 1 và 2b (trừ `claude-security`), `sandbox-runtime`, `knowledge-work-plugins`, `claude-plugins-community`, `defending-code-reference-harness`, và các skill của `anthropics/skills` đã đọc LICENSE (mcp-builder, discernment-nudge, internal-comms, claude-api, academy-guide); MIT gồm `claude-cookbooks`, `claude-quickstarts`, `claude-agent-sdk-python`, `claude-code-security-review`, `claude-code-action`.

**6.13.1 Việc nên làm (dùng lại hoặc điều chỉnh).** Thứ tự trong bảng là thứ tự đề xuất làm. Mục nào cài hay chạy đồ bên thứ ba thì phải qua `vet-skill` và được bạn duyệt trước.

| Mục | Quyết định | Áp vào | Việc cần làm | Bằng chứng · giấy phép |
|---|---|---|---|---|
| [sandbox-runtime](https://github.com/anthropics/sandbox-runtime) (`srt`) | **ĐIỀU CHỈNH, ưu tiên 1** | `vet-skill` | Vet gói npm `@anthropic-ai/sandbox-runtime`, cài cô lập (`npm install --prefix .cache/srt`, không `-g`), thử trên một script vô hại, rồi thêm bước "phân tích động" tùy chọn vào `vet.py`: không mạng, chỉ ghi vào thư mục tạm, `denyRead` cho `~/.ssh`, `~/.aws`, `~/.config`. Ràng buộc phải do sandbox thực thi, không dựa vào lời dặn model. | ★5,4k · 10-01 · Apache-2.0 · npm 0.0.78, 4 phụ thuộc trực tiếp. macOS dùng Seatbelt (`/usr/bin/sandbox-exec` và Node 24 đã có trên máy). Nhãn "Beta Research Preview", 262 issue mở. |
| [plugin-dev](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/plugin-dev) | **ĐIỀU CHỈNH** | kiểm tra `plugin/` | Vet `plugins/plugin-dev`, chạy một lần ba script `validate-hook-schema.sh`, `hook-linter.sh`, `test-hook.sh` từ bản chép (không cài), so với `claude plugin validate`. Đã biết trước một cảnh báo: `SessionEnd` có `timeout: 2`, mà script coi dưới 5 giây là "rất thấp" (`validate-hook-schema.sh` dòng 139). Không cài toàn cục (660 KB; lệnh `/create-plugin` có Bash, Write, Task). | Apache-2.0 · 7 skill, 3 agent, 10 script `.sh` |
| `reviewer` ← [defending-code-reference-harness](https://github.com/anthropics/defending-code-reference-harness) | **ĐIỀU CHỈNH** (ý, không cài) | `plugin/agents/reviewer.md` | Theo `docs/prompting.md` và `docs/best-practices.md` của harness: (a) mô tả "hình dạng" lỗ hổng thay vì liệt kê loại lỗi, vì liệt kê làm giảm recall (`reviewer.md` dòng 14 đang liệt kê); (b) mỗi phát hiện qua một bước verifier đối kháng ("tìm lý do nó sai") rồi mới báo. Pipeline tự động (Docker, ASAN, gVisor) quá nặng, không dùng. | ★7,5k · 08-06 · Apache-2.0 · README ghi "not maintained" |
| `reviewer` ← [claude-code-security-review](https://github.com/anthropics/claude-code-security-review) | **ĐIỀU CHỈNH** | `reviewer.md` | Lấy danh sách loại trừ cứng (HARD EXCLUSIONS), tiền lệ (PRECEDENTS) và ngưỡng tin cậy làm bảng lọc dương tính giả; diễn đạt lại bằng tiếng Việt, ghi nguồn, giữ thông báo MIT. Chỉ áp cho `reviewer`, không áp cho `vet-skill` (vài loại trừ như DoS và rò secret trên đĩa không hợp khi soi đồ lạ). | ★6,3k · 02-11 (8 tháng chưa cập nhật) · MIT |
| `reviewer` ← `pr-review-toolkit`, `code-review` | **BỎ QUA cài, lấy ý** | `reviewer.md` | Thêm hai mục kiểm từ `agents/silent-failure-hunter.md` (nuốt lỗi, fallback sai) và `agents/pr-test-analyzer.md` (thiếu test ở nhánh lỗi), hợp với C/C++ firmware; thêm quy tắc "chấm tin cậy 0 đến 100, bỏ dưới 80" từ `code-review/commands/code-review.md`. | Apache-2.0 |
| `tien-do` ← `project-artifact` | **BỎ QUA cài, lấy ý** | `tien-do` | Lưu một snapshot nhỏ trong `state/` rồi báo "đã đổi gì từ lần trước" thay vì kể lại đầy đủ (mục "Refreshing an artifact (deltas, not re-narratives)", `SKILL.md` dòng 131). Phần Artifact và claude.ai không cần. | Apache-2.0 |
| [claude-security](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/claude-security) | **DÙNG LẠI**, gọi tay | quét sâu repo hoặc diff | Vet trước. Chỉ chạy khi cần; có hỏi xác nhận chi phí trước mỗi lần quét. Hook chỉ in banner, đếm usage qua telemetry của Claude Code và nhắc quét sau `git push`; tắt bằng `DISABLE_TELEMETRY=1` và `CLAUDE_SECURITY_SCAN_TIP=off`. | 46 file, ~8,3k dòng; 8 agent chạy song song nên tốn hạn mức. LICENSE riêng (đóng): chỉ dùng, không chép. |
| `session-keeper` ← [doc-coauthoring](https://github.com/anthropics/skills/tree/main/skills/doc-coauthoring) | **ĐIỀU CHỈNH** (ý) | `session-keeper` | Thêm bước "kiểm người đọc": đưa `PLAN.md` §0 hoặc `HANDOFF.md` cho một subagent không có ngữ cảnh, hỏi "làm gì tiếp?" rồi xem chỗ nào bị hiểu sai. Viết lại bằng lời mình, không chép. | Không có LICENSE.txt: coi là chưa xác định |
| `vet-skill` ← `mcp-server-dev`, [mcp-builder](https://github.com/anthropics/skills/tree/main/skills/mcp-builder) | **ĐIỀU CHỈNH** (lấy ý) | `vet-skill` (soi MCP) | Lấy ba danh sách kiểm: `build-mcpb/references/local-security.md` (path traversal, command injection, mặc định chỉ đọc), `build-mcp-server/references/tool-design.md` (annotation `readOnlyHint`, `destructiveHint`; mô tả tool không được ra lệnh cho Claude, coi là prompt injection), `auth.md` (audience của token, nơi lưu token). Khi tự viết MCP server: cài `mcp-server-dev` và đọc `mcp-builder/reference/evaluation.md` để dựng bộ câu hỏi chấm; không chạy `evaluation.py` (gọi API Anthropic bằng khóa). | Apache-2.0 cả hai |
| `evals/`, `session-keeper` ← [claude-cookbooks](https://github.com/anthropics/claude-cookbooks), [knowledge-work-plugins/productivity](https://github.com/anthropics/knowledge-work-plugins/tree/main/productivity) | **ĐIỀU CHỈNH** (ý) | `plugin/evals/*/graders`, `session-keeper` | (a) Viết grader theo rubric từng tiêu chí kiểm được, như `managed_agents/CMA_verify_with_outcome_grader.ipynb`. (b) Giữ §0 ngắn, đẩy chi tiết sang file riêng (mẫu bộ nhớ nóng và kho sâu). (c) Ý "dựng sẵn bản tóm tắt từ ngưỡng mềm" trong `misc/session_memory_compaction.ipynb`: để sau, vì hook không được gọi model. | MIT · Apache-2.0 |
| [claude-code/examples](https://github.com/anthropics/claude-code/tree/main/examples) | **TỰ LÀM theo ý**, chưa gấp | hook mới, `install.py` | Mẫu hook `PreToolUse` chặn lệnh nguy hiểm bằng thoát mã 2 kèm stderr. Nếu làm thì tự viết `plugin/hooks/pretooluse_guard.py` (Python 3.9, thoát 0 khi không chắc; mẫu gốc thoát 1 khi JSON lỗi nên không theo). `settings-bash-sandbox.json`: thêm làm tùy chọn trong `install.py`, mặc định tắt. | All rights reserved: chỉ học ý |

**Kết quả triển khai 6.13.1 (02/10/2026).** Đã làm: `sandbox-runtime` (phân tích động `vet.py dynamic`, kèm phát hiện bằng file mồi vì log vi phạm của macOS mất sự kiện), `plugin-dev` (chạy ba script một lần, kết luận không dùng, giữ `timeout: 2`), `reviewer` (hình dạng lỗi, verifier phản biện, bảng lọc dương tính giả, ghi nguồn), `tien-do` (báo phần đổi), `claude-security` (đã vet, chờ duyệt). Chưa làm, vẫn là ý để sau: bước "kiểm người đọc" cho `session-keeper`, ba danh sách kiểm MCP cho `vet-skill`, grader theo rubric và §0 ngắn, hook `PreToolUse` chặn lệnh nguy hiểm.

**6.13.2 Giữ bản tự viết** (đã so với bản chính thức tương ứng)

| Thành phần của mình | So với | Lý do giữ |
|---|---|---|
| `reviewer` | feature-dev, pr-review-toolkit, code-review, code-simplifier, `/code-review`, `/security-review` | Bản chính thức trùng lệnh có sẵn hoặc quá nặng (nhiều agent chạy song song); không bản nào thay được. Nâng cấp bằng các ý ở 6.13.1. |
| `tien-do` | project-artifact | Artifact cần đăng nhập claude.ai và công cụ `Artifact`; `tien-do` chạy cục bộ. |
| `evals/run_eval.py` | claude-agent-sdk-python, agent-sdk-dev | SDK cần Python 3.10 trở lên cùng `anyio`, `mcp`, trái ràng buộc stdlib và Python 3.9. SDK chỉ bọc CLI `claude` bằng subprocess, đúng thứ script đang làm, và script đã lấy `total_cost_usd`, `num_turns`, `permission_denials` từ `--output-format json` (dòng 168 đến 197). |
| `vet-skill` | claude-plugins-community | Kho này (2.283 plugin, 2.274 có `sha` ghim) nói đã "quét bảo mật tự động" nhưng không công bố tiêu chí hay kết quả. Chỉ dùng làm danh mục để tra; không add marketplace; vẫn phải vet từng mục. |
| `task-router` | cookbooks `patterns/agents` | Không có thứ tương đương trực tiếp; các notebook là khung khái niệm. Mục `cost_optimization/` chưa mở. |
| `giong-van` | brand-review, internal-comms, doc-coauthoring | Các mục kia cần style guide công ty hoặc là quy trình viết tài liệu; `giong-van` chỉnh giọng cá nhân. |
| §0 và `session-keeper` | claude-quickstarts `autonomous-coding` | Cùng ý (file tiến độ giữa các phiên), mình đã có. |

**6.13.3 Bỏ qua** (ghi lý do để phiên sau không phải xét lại)

| Mục | Lý do |
|---|---|
| `ralph-loop` (marketplace), `ralph-wiggum` (claude-code) | Stop hook chặn thoát phiên và nạp lại cùng prompt; `--max-iterations` mặc định là vô hạn (`setup-ralph-loop.sh` dòng 10 và 27); điều kiện dừng dựa vào chuỗi `<promise>` do model tự khai. Trùng `/goal`, `/loop`, và ngược ràng buộc "hook không làm kẹt phiên". |
| `security-guidance` | SessionStart chạy `ensure_agent_sdk.py` (timeout 180 giây), tự tạo venv ở `~/.claude/security/agent-sdk-venv` rồi `pip install` SDK, nằm ngoài `vet-skill`. Stop và SubagentStop gửi diff tới LLM mỗi lượt có sửa file. Hook `asyncRewake` có thể đánh thức model sau câu trả lời và làm lệch dòng ➡️ (suy luận từ cấu hình, chưa chạy thử). Chỉ lấy ý: một file luật bảo mật riêng nạp vào bước review (plugin dùng `~/.claude/claude-security-guidance.md`), áp cho `reviewer`. Nếu sau này vẫn muốn cài: vet, đặt `ENABLE_STOP_REVIEW=0`. |
| discernment-nudge | Ý hay (nhắc giả định, số liệu cần kiểm) nhưng `SKILL.md` dòng 208 bắt "không thêm gì sau phần nudge", mâu thuẫn dòng ➡️ phải ở cuối mọi câu trả lời. Lấy ý cho `researcher`, không cài. |
| academy-guide | Gợi ý khóa học sau mỗi câu trả lời về cách dùng Claude; nhiễu với người đã thạo. |
| code-modernization | 107 file; hook ở 5 sự kiện (SessionStart, UserPromptSubmit, Stop, PostToolUseFailure, StopFailure), chủ yếu telemetry; dành cho di trú hệ thống legacy lớn. |
| feature-dev, code-simplifier, commit-commands | Trùng quy trình có sẵn (Explore, Plan, `reviewer`), `/simplify` và `git`, `gh`. `/commit-push-pr` ngược luật "không push"; chỉ `/clean_gone` tiện, tự viết được trong vài dòng. |
| explanatory-output-style, learning-output-style | Hook SessionStart làm mọi câu trả lời dài hơn hoặc đổi hành vi agent; ngược mục tiêu ngắn gọn và dòng ➡️. |
| receipts | Trùng tên `receipt.py` nhưng khác chức năng: báo cáo mức dùng để giải trình với quản lý. Không cần. |
| agent-sdk-dev, frontend-design (cả bản plugin và bản skill), playground, mcp-tunnels, cwc-makers, math-olympiad, math-proof | Không liên quan hướng của bạn. Ba mục sau cùng chỉ xét qua mô tả. |
| 10 plugin LSP ngôn ngữ khác (csharp, gopls, jdtls, kotlin, lua, php, ruby, rust-analyzer, swift, typescript) | Không dùng ngôn ngữ đó; chưa đọc. Cài khi cần, theo cách đã làm với pyright-lsp. |
| claude-code-action | `git remote -v` của `agent-stack` rỗng (không có remote GitHub, không push) nên Action vô dụng lúc này. Xem lại khi repo có CI. |
| claude-quickstarts, claude-agent-sdk-demos, claude-agent-sdk-typescript, cookbooks `patterns/agents`, `tool_evaluation`, `building_evals` | Demo hoặc khung khái niệm, mình đã có tương đương. SDK TypeScript và demos không rõ giấy phép. |
| `anthropics/skills`: docx, pdf, pptx, xlsx, claude-api, internal-comms, algorithmic-art, canvas-design, slack-gif-creator, theme-factory, brand-guidelines, web-artifacts-builder | docx, pdf, pptx, xlsx đã có qua claude.ai (source-available, không chép); `claude-api` trùng skill built-in cùng tên; các mục còn lại không liên quan. |
| claude-opus-4-5-migration (`claude-code/plugins`) | Đã lỗi thời (hiện là Opus 5.5); skill `claude-api` có sẵn lo phần này. |
| `knowledge-work-plugins`: sales, legal, finance, HR, marketing, cowork-plugin-management… | Vai trò doanh nghiệp, nặng connector `.mcp.json` gọi mạng ngoài; không có hook. `cowork-plugin-management` đã có qua claude.ai. |

**6.13.4 Giới hạn của đợt rà này**
- **Chưa chạy thử:** `srt` trên macOS (Darwin 27.0.0), ba script kiểm hook của plugin-dev, và mọi hook của plugin bên thứ ba. Nhận định về hành vi đến từ đọc mã và tài liệu.
- **Chưa đọc:** `scan.js` và các agent của `claude-security` (nên chưa biết chi phí mỗi mức effort); ngưỡng bỏ qua Stop review của `security-guidance`; `cost_optimization/` và `claude_agent_sdk/` trong cookbooks; `commands/` và `dashboard.html` của productivity; các skill `/threat-model`, `/patch`, `/verify` của harness; mã `connections.py` và `evaluation.py` của mcp-builder; 262 issue mở của sandbox-runtime (có thể có lỗi thoát sandbox).
- **Chưa kiểm với docs chính thức:** dạng `command` kèm `args` của hook trong `plugin/hooks/hooks.json` và trường `disallowed-tools` ở skill. Hook vẫn chạy (đầu ra SessionStart xuất hiện trong phiên) và `claude plugin validate` đạt.
- **Ngoài phạm vi ba bước, chưa rà:** "Anthropic Directory" trên claude.ai; các repo Anthropic khác trong danh sách theo sao như financial-services, claude-for-legal, commerce-agents, prompt-eng-interactive-tutorial, anthropic-sdk-*.

### 6.14 Áp dụng ý từ video của Kun Chen (07/10/2026)

Nguồn: video "L8 Principal's Agentic Engineering Workflow" (Kun Chen, YouTube `iQyg-KypKAA`, 45 phút; đọc bản phụ đề tự động), README của `no-mistakes`, `gnhf`, `lavish-axi` (đều MIT) và trang `axi.md`. Số liệu trong video (MCP GitHub tốn gấp 3 lần token so với CLI; một repo skill 177 nghìn sao làm kết quả tệ hơn và tốn thêm 5% token) là benchmark của chính tác giả, chưa có kiểm độc lập.

| Ý trong video | Quyết định | Ở đâu |
|---|---|---|
| File nhớ toàn cục ngắn (27 dòng) vì nạp vào mọi phiên; phần chỉ cần cho một loại việc thì chuyển vào skill | Áp dụng một phần: thêm 5 luật nhưng viết gọn chỗ khác, nên hai file chỉ tăng từ 9.240 lên 10.190 byte (khoảng 10%). Sau đó, theo yêu cầu của bạn, tách phần OpenCode (GĐ13): Claude Code nạp `SHARED.global.md` + `CLAUDE.global.md`, OpenCode nạp `AGENTS.global.md` là file ghép bằng `tools/build_rules.py`, không đổi symlink hay cấu hình OpenCode; viết gọn từng luật nên Claude Code nạp 8.924 thay vì 10.190 byte (−12%), OpenCode 5.683 thay vì 5.922 (−4%) | `global/` |
| Model ước lượng công theo tốc độ người nên chọn cách rẻ mà kém | Thêm luật chọn theo chất lượng, độ bền, độ dễ bảo trì; thêm vào bước chấm ứng viên của `reuse-best` | `SHARED.global.md`, `reuse-best` |
| Sửa lỗi bắt đầu từ tái hiện end-to-end, giống người dùng nhất | Thêm luật chung; `diagnosing-bugs` đã có bước này nhưng chỉ khi được gọi | `SHARED.global.md` |
| File nhớ project lớn dần từ các lần người dùng sửa agent | Thêm luật: đề nghị ghi bài học thành luật ngắn trong `CLAUDE.md`/`AGENTS.md` của project, hoặc vào skill nếu chỉ cần cho một loại việc | `SHARED.global.md` |
| Sao không chứng minh skill giúp được agent | Thêm vào luật cài đồ bên thứ ba và vào `reuse-best`. Bộ eval có cấu hình V (A + plugin vendor) và ghi skill nào thực sự được gọi; chưa chạy thật | `evals/` |
| `no-mistakes`: ý định, review đối kháng ở context mới, test có bằng chứng, rà tài liệu, chấm rủi ro để quyết người đọc tới đâu | Tự làm skill `chot-viec` từ các mảnh đã có (`receipt.py`, `agent-stack:reviewer`) cộng `risk.py`. Không cài `no-mistakes`: nó tự push, mở PR, trông CI (repo không push), và cài bằng `curl \| sh` | `plugin/skills/chot-viec` |
| `lavish`: lên kế hoạch bằng trang HTML có bình luận và nút chọn | Dùng Artifact có sẵn của Claude (riêng tư, có bình luận đọc được bằng `ArtifactComments`), không cài lavish. Chỉ khi kế hoạch có từ hai phương án hoặc ba quyết định | `CLAUDE.global.md` |
| `gnhf`: vòng lặp qua đêm có trần vòng, trần token, điều kiện dừng, mỗi vòng một commit | Ghi cách chạy vào dòng "agent tự chạy dài" của bảng định tuyến và ghi chú của luật router `long-agent`; `/goal`, `/loop` đã có | `routing-table.md`, `rules.json` |
| AXI: công cụ cho agent nên in gọn, có trạng thái rỗng rõ ràng, gợi ý bước tiếp | `risk.py` theo các nguyên tắc này (dòng tổng trước, "Không có thay đổi nào", dòng "Review đề nghị"). Ngày 07/10/2026 rà thêm `scout.py` (mục 6.16); các script cũ khác chưa rà | `chot-viec/scripts/risk.py`, `reuse-best/scripts/scout.py` |
| WezTerm, tmux, Neovim, nhập bằng giọng (OpenSuperWhisper), Treehouse, firstmate | Không áp dụng: là thói quen terminal cá nhân, cần cài toàn cục, hoặc app desktop đã làm thay (worktree mỗi phiên, nhiều phiên song song) | |

### 6.15 Sửa `reuse-best` sau eval có bẫy (07/10/2026)

**Câu hỏi của bạn:** `reuse-best` có làm agent lười như [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) không. Lỗi "lười" của ponytail lấy từ issue của chính repo đó: vá triệu chứng thay vì đọc hiểu (#245; tác giả đo thấy dặn bằng lời "trace the flow" thì 0/3 lần có tác dụng, phải đổi thành bước thao tác cụ thể), cắt bớt việc được giao (#602), lan sang subagent review (#502). Gốc của chúng là luật luôn bật và mục tiêu "ít code". `reuse-best` không có hai điều này: nó chỉ chạy khi build thứ không tầm thường, chạy trong context riêng và chỉ trả về báo cáo. Mình vẫn nêu 4 rủi ro giả định (dừng ở thứ "đủ dùng", chấm trên đề bài mỏng, hụt phạm vi khi dùng lại, đọc nông) cộng việc chưa có eval; bạn yêu cầu sửa hết và test kỹ.

**Tái hiện trước khi sửa.** Bộ đo `suite:reuse-best` gồm 4 việc có bẫy (`evals/README.md`, mục "Bộ đo riêng cho skill"), chạy bằng cấu hình E (sonnet · medium + plugin) trong thư mục tạm, chấm bằng code. Bản cũ (plugin 0.5.0, chụp từ HEAD) đạt 12/12 lượt: tự đọc `CONTRIBUTING.md` và `pyproject.toml`, đọc code `md_links.py` thấy `anchor_exists` luôn trả True, đọc `gunicorn.conf.py` và `docker-compose.yml` rồi tính ra 1.200 request/phút. Nghĩa là **4 rủi ro giả định không tái hiện được**; nhận định ban đầu đã thổi phồng chúng. Lỗi thật tìm được nhờ lưu luồng sự kiện (`--save-streams`, `evals/trace_stats.py`):

1. Không kiểm chứng được ứng viên: `gh api`, `gh repo view` và WebFetch bị chặn khi quyền hạn chế, nên skill quyết theo trí nhớ (trung bình 2,6 chỗ "chưa kiểm", "theo hiểu biết" mỗi báo cáo). Ví dụ: không kiểm được lychee có kiểm anchor không, nên chọn tự viết phần tạo slug heading cho tiếng Việt.
2. Lệnh shell ghép (`cd …; ls`, `S=…; [ -f $S ] || …`): 6,3 lệnh mỗi lượt, 3,6 lệnh bị chặn.
3. `scout.py github "toml parser python" --language python` ra 0 kết quả vì GitHub đòi mọi từ đều khớp; skill đọc thành "có thể máy không có mạng". 1,1 trên 3,3 lần tìm mỗi lượt ra rỗng.

**Sửa:**
- `scout.py repo owner/name --find "từ khóa"`: phát hành gần nhất, issue đang mở, giấy phép, các dòng README nhắc tới từng tiêu chí kèm số dòng. Chỉ cần quyền chạy `python3`.
- `scout.py github`: câu ra rỗng thì bỏ từ chung chung và tên ngôn ngữ rồi tìm lại một lần; thông báo rỗng nói rõ không phải lỗi mạng.
- `SKILL.md`: mỗi lần gọi Bash một lệnh đơn; đọc ràng buộc trong file của project trước khi tìm; viết nhu cầu thành tiêu chí bắt buộc và nên có; chỉ dừng ở một bậc khi có ứng viên đạt mọi tiêu chí bắt buộc, có bằng chứng; kiểm ứng viên ngoài bằng `scout.py repo`; hai mục bắt buộc "Phần còn phải làm" và "Cần người dùng quyết"; quyết định không được thu hẹp nhu cầu. Chốt chặn cho 4 rủi ro giả định được viết thành bước thao tác và mục đầu ra, theo bài học #245 của ponytail, không phải lời dặn chung.
- Luật chung (`SHARED.global.md`): phần nhu cầu mà thứ dùng lại chưa đáp ứng vẫn phải làm hoặc hỏi người dùng, không lặng lẽ bỏ.
- Harness eval: bộ đo riêng (`"suite"` trong `meta.json`, không lẫn vào bộ chọn cấu hình), `--plugin-root` + `--tag` để so hai phiên bản plugin, dấu vân tay plugin mỗi lượt (đã bắt được chính lần mình sửa `scout.py` giữa đợt chạy), `skill_outputs`, thư mục tạm riêng cho self-test và regrade (hai phiên chạy test cùng lúc từng xóa thư mục của nhau).

**Kết quả** (cấu hình E, mỗi bản 12 lượt; bảng đầy đủ ở `evals/README.md`): cả hai bản đạt 12/12. Bản mới không còn lệnh ghép (6,3 → 0), lệnh bị chặn giảm từ 3,6 xuống 0,2, kiểm repo bằng bằng chứng 2,7 lần mỗi lượt (bản cũ 0), chỗ "chưa kiểm" giảm từ 2,6 xuống 1,2; đổi lại đắt hơn 7% (0,203 → 0,218 USD) và chậm hơn 24% (45 → 55 giây), vì đọc README của ứng viên. Tổng chi phí eval 7,49 USD giá niêm yết.

**Review độc lập** (agent `reviewer`, opus · high): 0 cao, 4 vừa, 2 thấp, đều đã sửa. Bốn lỗi vừa nằm ở grader: bản đầu cho lọt 10 trên 27 câu sai (câu của model tin docstring, chép lại đề, nhắc tên `CONTRIBUTING.md` mà quyết định trái luật) và chấm oan 8 trên 26 câu đúng. Grader nay chỉ tính lời phủ định nằm cùng mệnh đề với điều nó phủ định, và chấm cả quyết định. Hai lỗi thấp: `scout.py repo` ghi "chưa có bản phát hành" cho repo chỉ phát hành bằng tag (`hukkin/tomli`), nay ghi tag mới nhất kèm ngày; `--self-test` với tên bộ đo gõ sai từng thoát 0. Chấm lại bài thật bằng bản sửa đầu tiên của grader còn lộ 3 lượt bị chấm oan vì coi "còn" ("`anchor_exists` còn TODO") là chữ nối; đã sửa và đưa vào test.

**Chưa làm lúc đó:** câu tìm nhiều khái niệm chuyên ngành vẫn ra rỗng, và skill gọi `scout.py repo` lặp lại cho cùng một repo; cả hai đã sửa ở mục 6.16. Còn lại: bốn bẫy chưa phân biệt được các bản ở đầu ra; muốn đo kỹ hơn thì cần bẫy mà quyết định đúng phụ thuộc vào một chi tiết chỉ kiểm được bằng README.

### 6.16 Gộp kết quả phiên "Video review và áp dụng": AXI cho `scout.py` (07/10/2026)

Phiên đó (GĐ12, GĐ13, đã commit) để lại một ý chưa áp dụng: nguyên tắc AXI cho công cụ dành cho agent ([axi.md](https://axi.md), mục 6.14), với ghi chú "chưa rà lại các script cũ". `scout.py` là script như vậy, và eval ở mục 6.15 cho thấy đúng các triệu chứng AXI nhắm tới: gọi `repo` lặp lại, gọi `repo --help`, in 2.000 ký tự README mặc định, câu tìm nhiều khái niệm ra rỗng mà không có gợi ý.

- Dòng tổng đứng đầu; cuối kết quả có dòng "Tiếp:" là lệnh chạy được ngay, tên repo điền sẵn, bỏ repo đã lưu trữ.
- `repo` kiểm tối đa 5 repo trong một lần gọi; repo lỗi được ghi ngay trong kết quả; mỗi từ khóa có số dòng khớp và cách xem thêm (`--max-lines`, từ khóa quá chung thì gợi ý từ cụ thể hơn); có `--find` thì không in README, chỉ ghi độ dài và cách xem.
- Câu tìm vẫn rỗng sau khi bỏ từ chung chung thì bỏ thêm từ cuối; còn rỗng thì gợi ý câu ngắn hơn.
- Chạy không tham số thì in cách dùng; đầu vào sai (`--max-lines 0`, quá 5 repo) thì báo lỗi, thoát mã 2.
- `SKILL.md`: kiểm các ứng viên đầu bảng trong một lệnh, gộp mọi tiêu chí vào một `--find`, làm theo dòng "Tiếp:".

**Kết quả** (cấu hình E, 12 lượt; bảng ở `evals/README.md`): đạt 12/12; 0,198 USD và 46 giây mỗi lượt, tức rẻ hơn bản 0.5.1 (0,218 USD, 55 giây) và ngang bản cũ (0,203 USD, 45 giây); 0 lệnh bị chặn, 0 lần tìm ra rỗng; vẫn kiểm 2,2 repo mỗi lượt nhưng chỉ bằng 0,9 lần gọi (0.5.1: 2,6 repo, 2,7 lần gọi); chỗ "chưa kiểm" còn 1,0. Một lượt ban đầu bị chấm trượt là grader chấm oan (câu quyết định nói "bằng thư viện chuẩn", chữ SHA-256 nằm xa); đã sửa grader, đưa câu đó vào test, chấm lại cả năm đợt: không lượt nào khác đổi. Review độc lập (sonnet): không lỗi nào đạt ngưỡng, ba nhận xét nhỏ đã sửa. Chi phí đợt này 2,38 USD.

### 6.17 Tự lưu sau mỗi lượt (09/10/2026)

Yêu cầu của bạn: sau mỗi yêu cầu xong, luôn mở được phiên mới để làm tiếp. Trước đó §0 chỉ được cập nhật khi Claude nhớ, nên phiên mới có thể thấy §0 cũ (ví dụ thật: §0 ghi `context7` đang bật nhiều ngày sau khi bạn tắt). `reuse-best` không thấy thứ có sẵn đáp ứng đủ: claude-mem cần worker nền và SQLite, chưa vet; skill handoff chỉ chạy khi được gọi. Tài liệu hook chính thức cho hook Stop trường `last_assistant_message`, nên chỉ cần mở rộng hook của repo. Trang so sánh: https://claude.ai/artifact/X7wMhJyxe6QXMNLoccs1Qe.

Bạn chốt: phương án B, lưu trong project, phiên mới tự nạp, có lưu câu trả lời cuối.
- UserPromptSubmit ghi lúc bắt đầu lượt và dấu §0 lúc đó (`state/turns/<phiên>.json`), ở mọi tin, kể cả tin do hệ thống tạo.
- Stop ghi `.agent/LAST-TURN.md` sau mỗi lượt trọn vẹn: yêu cầu (đã che khóa), câu trả lời cuối (che khóa, cắt 1.500 ký tự), việc tiếp theo lấy từ dòng ➡️ (thiếu thì ghi "không rõ", không đoán), file đổi trong lượt (mtime sau lúc bắt đầu lượt, cộng file trong commit tạo trong lượt), §0 đã cập nhật chưa. File quyền 0600; hook thêm nó vào `.git/info/exclude` (cục bộ, không sửa file nào được commit) để không hiện trong `git status`.
- Lượt có đổi file mà dấu §0 không đổi thì Stop trả `decision: block` một lần; lần dừng thứ hai (`stop_hook_active`) không chặn và giữ câu trả lời của lần đầu. Lời nhắn cho Claude có lối ra: file do phiên khác đổi hay thay đổi quá nhỏ thì trả lời một câu và không sửa gì.
- SessionStart nạp bản rút gọn (khoảng 500 ký tự) vào phiên mới, trừ khi resume lại đúng phiên đã ghi. `route.py --session` in cùng nội dung cho OpenCode.
- Giới hạn: Stop không chạy khi người dùng bấm dừng giữa chừng hay app tắt giữa lượt, nên lượt đó không được ghi; file đổi do phiên khác cùng repo trong lúc lượt chạy cũng bị tính là của lượt này; OpenCode không có hook Stop nên lượt làm trong OpenCode không được ghi.


### 6.18 Quy trình bảo mật theo mức rủi ro và plugin bảo mật đã duyệt (09/10/2026)

Bạn hỏi nên chạy threat model và review bảo mật cho mỗi chức năng, hay làm xong hết rồi mới review. Mình trả lời là cả hai cách đều kém hơn làm theo mức rủi ro. Chạy đủ cho mọi chức năng tốn nhiều nhất: một lần review opus · high cho diff khoảng 140 dòng tốn khoảng 54 nghìn token, phần lớn là chi phí cố định. Làm xong mới review thì diff lớn nên review sót nhiều, và lỗi thiết kế phải sửa muộn. Bạn bảo làm, và thêm luôn những skill đã duyệt giúp được cho bảo mật. Review độc lập (agent `reviewer`, opus · high) tìm 0 cao, 3 vừa, 2 thấp, đã sửa cả năm kèm test. Có ba bước:

1. **Threat model trước khi code**, chỉ khi chức năng đụng ranh giới tin cậy (input từ bên ngoài, xác thực, gọi ra ngoài, dữ liệu nhạy cảm, dependency, chạy lệnh). Skill mới `mo-hinh-de-doa`: đọc ít, sáu câu STRIDE, tối đa 5 mối đe dọa, mỗi mối có chốt chặn kiểm được, ghi vào `.agent/threat-model.md`. `reuse-best` không tìm được thứ dùng lại được: skill `threat-model` của `anthropics/defending-code-reference-harness` chạy nhiều subagent cho cả codebase, không có điều kiện kích hoạt và chưa vet; `fr33d3m0n/threat-modeling` cần Python 3.10+ và là cả một pipeline; `stride-gpt` là app Streamlit. Vì vậy mình tự viết, lấy ý từ harness (phép thử lỗi và mối đe dọa, tên cột của bảng). Trigger có ba lớp: luật `feature-boundary` của router (khi xin làm tính năng đăng nhập, upload, webhook…), một dòng trong luật chung, và `risk.py` làm lưới cuối.
2. **Review từng thay đổi theo rủi ro.** `risk.py` liệt kê ranh giới bị đụng trong file mã nguồn và nâng mức thấp lên vừa. `chot-viec` đưa bảng mối đe dọa cho reviewer kiểm từng chốt chặn. Ở mức cao có đụng phần bảo mật, `differential-review` (Trail of Bits) chạy trên diff, rồi reviewer lọc dương tính giả, vì skill đó không lọc.
3. **Audit cả repo trước phát hành** bằng `claude-security`, cài theo project và gọi tay. Đây là công cụ duy nhất có threat model cho từng component. `/security-review` chỉ xem diff của nhánh nên không thay được.

Đánh giá các mục đã duyệt (subagent đọc bản ghim trong `.vet-cache`):
- `differential-review`: rẻ, không có hook, chỉ chạy khi được gọi, nên cài cho mọi phiên. Phần riêng của nó là blame code bị xóa, lỗi cũ tái phát, blast radius.
- `static-analysis`: cài theo project, cần `brew install semgrep` (máy chưa có). Chỉ dùng phần Semgrep; bỏ CodeQL.
- `c-review`: theo project, chỉ cho C/C++ userspace. Catalog cũ ghi "firmware, bán dẫn" là sai.
- `audit-context-building`: theo project, khi cần, vì tốn tới 40 agent. Không bật chung vì tự kích khi nghe "threat model".
- `claude-security`: theo project, gọi tay. Ghi chú cũ trong `vetted.lock` nói hook chạy ở mỗi lần sửa file là sai: hook chỉ chạy với script của chính plugin, `git push` và `gh pr create`.
- `hookify`, `superpowers`, `webapp-testing`, các skill của Matt Pocock: không giúp gì cho bảo mật.

**Ghim commit.** `install.py` cũ cài plugin Trail of Bits bằng `marketplace add trailofbits/skills`, tức theo HEAD, không phải bản `82fe822` đã duyệt, và làm khoảng 45 plugin chưa duyệt hiện ra là cài được. Loại catalog mới `vendor-plugin` chép nguyên plugin từ `.vet-cache` vào `vendor/plugins/<tên>`, dùng marketplace cục bộ có sẵn `agent-stack-vendor-local`. Đây là TM-1 trong `.agent/threat-model.md`: kiểm lệch so với chính `.vet-cache`, nên không bắt được việc cache bị sửa. Chốt chặn gồm hai lớp. Trước khi chép, bộ cài kiểm `HEAD` bằng sha đã duyệt, cây sạch kể cả file bị ignore, và không có file bị ẩn khỏi `git status` trong thư mục con; cờ skip-worktree mà sparse checkout của `vet.py` đặt ngoài thư mục con là bình thường. Sau đó chỉ xuất file git ghi nhận ở sha đó, bằng `git archive` và `tarfile` với bộ lọc `data`. Kiểm lệch nay so cả plugin trong `vendor/`, và chỉ bỏ qua đúng hai plugin của agent-stack. Bộ cài so bản đã cài với bản đã duyệt, khác thì gỡ rồi cài lại, vì đã thử thấy `claude plugin update` không chép lại khi version không đổi.

**Router** chỉ gợi ý skill của plugin đang bật cho project (đọc `enabledPlugins` theo thứ tự user, project, local). Plugin chưa bật thì dùng skill dự phòng (`differential-review` → `/security-review`) và nêu lệnh cài, kèm dặn chỉ đề xuất với người dùng. Lỗ hổng cũ là mọi câu về bảo mật đều được gợi ý `differential-review` dù chưa cài ở đâu.

**Giới hạn và việc chưa làm.**
- Chưa có số đo cho thấy bước threat model làm review bắt được nhiều lỗi hơn. Harness của Anthropic cũng không công bố số liệu. Muốn biết thì đo bằng eval.
- Regex của `risk.py` có thể báo nhầm (ví dụ `subprocess` chạy lệnh cố định) hoặc bỏ sót; báo nhầm thì `chot-viec` ghi một dòng lý do rồi bỏ qua.
- TM-3 và TM-4 (`git checkout` baseline, ghi báo cáo vào thư mục project) có chốt chặn khi `differential-review` được gọi qua router hay `chot-viec`: lời dặn đi kèm gợi ý (`skill_notes` trong `rules.json`). Khi skill tự kích theo description của nó, không qua router, thì chưa có.
- `semgrep` chưa cài nên `static-analysis` chưa dùng được.


### 6.19 Skill cần thiết tự chạy (09/10/2026)

Bạn muốn các skill cần thiết luôn tự chạy, không đợi bạn nhắc, và bảo làm hết các việc còn treo của GĐ19. Trước đó, việc chạy `chot-viec`, `mo-hinh-de-doa` và `vet-skill` chỉ dựa vào luật chung và gợi ý của router: Claude nhớ thì chạy, quên thì thôi. Nay có hai chốt chặn bằng hook, nên không còn phụ thuộc vào trí nhớ của model:

- **Hook Stop buộc chạy `chot-viec`** khi lượt đổi code có mức rủi ro từ vừa trở lên mà chưa chạy nó. Mức rủi ro do `risk.py` chấm, chỉ trên file lượt này đổi, so với HEAD lúc bắt đầu lượt, nên file đã commit trong lượt vẫn được tính. `risk.py` ghi dấu "đã chốt việc" theo từng project. `chot-viec` kéo theo `mo-hinh-de-doa` khi đụng ranh giới tin cậy, `differential-review` ở mức cao, và cập nhật §0. Mức thấp (tài liệu, sửa nhỏ có test) không bị chặn, để không tốn thêm lượt model vô ích.
- **Hook PreToolUse mới:**
  - từ chối cài plugin, skill hay MCP chưa duyệt, nên Claude phải chạy `vet-skill` trước;
  - hỏi bạn trước khi thêm marketplace lạ;
  - hỏi bạn trước `git checkout` hay `git switch` khi cây có thay đổi chưa commit (TM-3);
  - từ chối ghi báo cáo `differential-review` vào chỗ git không bỏ qua (TM-4), kể cả khi skill tự kích, không qua router;
  - khi router đánh dấu lượt là chức năng đụng ranh giới tin cậy mà chưa có threat model, từ chối một lần lần sửa file mã nguồn đầu tiên, nên `mo-hinh-de-doa` chạy trước khi code.
  
  Lệnh thường chỉ tốn khoảng 20 ms.
- **Bước `tools` của `install.sh`** cài công cụ mà mục đã duyệt cần (khóa `brew` trong catalog; hiện là `semgrep` cho `static-analysis`), có ghi nhật ký và gỡ được.
- **Phát hiện khi tự chạy threat model cho GĐ20 (TM-7):** `git status` trong repo lạ chạy lệnh mà repo đặt ở `core.fsmonitor`. Mình đã tái hiện. Mọi lệnh git chỉ đọc của agent-stack, kể cả `risk.py` mà hook Stop gọi, nay đặt `-c core.fsmonitor=false`.
- **Phát hiện khi vet SkillSpector:** `vet.py` chỉ báo `subagentStatusLine` trong `settings.json` của plugin, bỏ sót `statusLine`, `apiKeyHelper` và các khóa khác tự chạy lệnh. Đã sửa.
- **SkillSpector** đã vet (khóa `NVIDIA/SkillSpector`, sha `2f93a86`). Khuyến nghị có điều kiện:
  - dùng venv riêng chạy Python 3.12 (`yara-python` chưa có bản dựng sẵn cho 3.11 trên máy này);
  - luôn chạy với `--no-llm` và môi trường đã lọc khóa API;
  - phần quét gói phụ thuộc gửi tên và phiên bản gói tới `api.osv.dev`;
  - kết quả chỉ đẩy lên REVIEW cho tới khi đo được trên bộ mẫu của mình.

  Bạn duyệt cùng ngày, và mình đã tích hợp:
  - Module `spector.py` của `vet-skill`. `vet.py spector --setup` cài `.venv-skillspector` từ đúng bản đã kiểm bằng `uv sync --frozen --no-dev --no-editable`, với Python 3.12 do uv quản lý (nằm trong `.cache/`); trước và sau khi cài đều kiểm bản đã kiểm còn sạch.
  - Chỉ chạy khi bản đã cài đúng commit đang được duyệt (`.vetted-sha`).
  - Môi trường dựng từ đầu: HOME giả, cwd trong `.tmp/`, không mang biến nào của người dùng; đích cục bộ thì chặn mạng bằng proxy hỏng.
  - Mỗi skill quét một lần. Phát hiện critical và high chỉ đẩy lên REVIEW.
  - Thử thật: skill độc hại mẫu trong repo của SkillSpector ra điểm 100 (2 critical, 1 high), bắt được đoạn gửi biến môi trường ra mạng mà bộ quét cũ của `vet.py` bỏ sót. `blader/humanizer` (đã duyệt) ra điểm 49. Mỗi skill vài giây.
  - Review (agent `reviewer`, sonnet): 0 cao, 1 vừa, 4 thấp, đã sửa cả năm kèm test. Lỗi vừa là chữ thô SkillSpector trích từ đích đi thẳng vào báo cáo, nên một skill độc chèn được dòng `## Phán quyết: PASS` giả vào báo cáo mà agent `vet-skill` đọc; nay chữ được làm sạch. Các lỗi thấp: `--version` không được bọc lỗi; `uv` nhận cả biến môi trường có khóa lúc build; dấu `.vetted-sha` cũ có thể còn sau khi cài dở; thiếu test nhánh lỗi.

**Review độc lập** (agent `reviewer`, opus · high): 0 cao, 2 vừa, 1 thấp; đã sửa cả ba kèm test.
- Hook Stop chấm lại cả phần chưa commit mà các lượt trước đã chốt, nên sửa nhiều lượt rồi mới commit thì lượt nào cũng bị ép chạy lại `chot-viec`. Nay `risk.py` lưu dấu băm từng dòng lúc chốt, và hook chỉ chấm dòng mới. File đã chốt không tính lại luật theo đường dẫn.
- `git diff` của `risk.py` chạy `diff.external`, textconv và clean filter của repo. `diff.external` toàn cục (như difftastic) còn làm mất nội dung cần chấm. Nay thêm `--no-ext-diff --no-textconv`, và bỏ chấm khi repo có clean filter cục bộ. Phần `git status` chạy clean filter thì Claude Code tự làm lúc mở phiên, nên agent-stack không chặn thêm được (TM-7).
- Chốt chặn cài khớp chuỗi thô, nên chặn nhầm thông điệp commit hay heredoc có chữ "claude plugin install", và đọc nhầm `--scope` thành tên plugin. Nay hook phân tích lệnh bằng `shlex`: bỏ thân heredoc, chỉ xét lệnh có argv[0] là `claude`, `git` hay `npx`, mở `bash -c` thêm một tầng, bỏ qua cờ và giá trị của cờ.

**Giới hạn.**
- Hook PreToolUse so chuỗi lệnh theo mẫu, nên là lớp nhắc chứ không phải ranh giới bảo mật (TM-6).
- Mỗi lần Stop chặn tốn thêm một lượt model.
- Mức "vừa" của `risk.py` dựa vào regex, nên có thể chặn nhầm; khi đó `chot-viec` ghi một dòng lý do rồi kết thúc nhanh.

---

## 7. Thiết kế chi tiết

### 7.1 Cấu trúc repo `agent-stack`

Bản đầu của kế hoạch dùng symlink từng skill vào `~/.claude/`. Khi triển khai, mình đổi sang **đóng gói thành plugin Claude Code**, vì ba lý do:
(a) thử được bằng `claude --plugin-dir agent-stack/plugin` mà không sửa gì trong `~/.claude`;
(b) kiểm tra được bằng `claude plugin validate`, và đo kích hoạt skill bằng `claude plugin eval`;
(c) khi bạn duyệt kích hoạt toàn cục, cài qua một marketplace cục bộ. Kiểm chứng khi cài ngày 02/10/2026: CLI trong terminal nạp plugin tại chỗ từ `agent-stack/plugin`, còn desktop app chạy bản chép trong `~/.claude/plugins/cache/`. Bản chép tìm về repo nhờ file `plugin/.agent-stack-home` do `install.py` ghi. Sau khi sửa plugin: tăng `version`, chạy `./install.sh --apply --only plugin` (gồm `claude plugin update`), rồi mở phiên mới.

Plugin nằm trong thư mục con `plugin/`, vì `CLAUDE.md` đặt ở gốc plugin không được nạp và `claude plugin validate` sẽ cảnh báo.

```
~/Documents/Claude/agent-stack/          # git repo, nguồn sự thật
├── KE-HOACH.md · PLAN.md · BASELINE.md · README.md · CLAUDE.md
├── .claude-plugin/marketplace.json      # marketplace cục bộ (dùng khi bạn duyệt cài)
├── plugin/                              # plugin Claude Code
│   ├── .claude-plugin/plugin.json
│   ├── skills/   vet-skill/ session-keeper/ tien-do/ task-router/ giong-van/
│   ├── agents/   reviewer · researcher · test-runner · oc-worker · explore-lite
│   ├── hooks/    hooks.json + script Python (stdlib, chạy bằng `python3` 3.11)
│   └── lib/      thư viện dùng chung: đọc §0/checkbox, git chỉ đọc, thư mục state
├── global/                              # SHARED (chung), CLAUDE (riêng Claude Code), OPENCODE (riêng OpenCode), AGENTS (file ghép cho OpenCode); chỉ link khi cài
├── opencode/agents/worker.md            # agent OpenCode
├── statusline/ · tools/ · evals/ · tests/      # mẫu PLAN/HANDOFF nằm trong skill session-keeper
├── vet-reports/ · vetted.lock           # kết quả kiểm duyệt đồ bên thứ ba
├── install.sh                           # kích hoạt toàn cục; mặc định chỉ in ra việc sẽ làm
└── state/ · backups/ · .venv/ · .tmp/   # không đưa vào git
```

OpenCode không đọc plugin Claude Code. Khi cài, `install.sh` symlink từng skill vào `~/.config/opencode/skills/` (OpenCode v2 theo dõi thư mục này và đi theo symlink). Claude Code không đọc thư mục này, nên không bị nạp trùng.

### 7.2 Đội agent (#2)

| Agent | Chạy ở | Model · effort | Quyền | Dùng khi | Cổng chất lượng |
|---|---|---|---|---|---|
| Phiên chính | CC | `opusplan` hoặc `sonnet`, effort `medium` (giả thuyết, GĐ4 quyết định) | — | — | — |
| `Explore` (ghi đè agent có sẵn) | CC | `haiku` | chỉ đọc | Tìm và đọc code diện rộng | Phiên chính tự đọc lại các dòng then chốt trước khi sửa. A/B ở GĐ4. |
| `researcher` | CC | `sonnet` · `medium` | WebSearch, WebFetch, Read | Nghiên cứu web, tài liệu | Mọi nhận định phải kèm URL. |
| `reviewer` | CC | `opus` · `high` | chỉ đọc + Bash | Review code và bảo mật trước commit/PR | Chính nó là cổng. |
| `test-runner` | CC | `haiku` | Bash, Read | Chạy test/lint, chỉ trả về lỗi | Output là kết quả thật của test, không phải nhận định. |
| `oc-worker` | CC → OC | `haiku` để điều phối; việc thật chạy bằng `opencode run` với model local | Bash, Read | Việc cơ học hàng loạt | **Bắt buộc** qua test/lint. Chạm code quan trọng thì `reviewer` xem diff. |
| `worker` | OC | `tuf/coder-fast`, lỗi thì thử `tuf/gpt-oss-medium` | edit: allow, bash: chỉ lệnh test, webfetch: deny | Được `oc-worker` gọi | |
| `build` (dự phòng) | OC | Model tốt nhất không phải Claude mà bạn có | mặc định | Khi hết hạn mức tuần của Claude | Đọc `.agent/HANDOFF.md` trước tiên. |

Ví dụ một file agent ⚙️ (`agents/reviewer.md`). Các agent khác viết theo cùng mẫu:

```markdown
---
name: reviewer
description: Review code và bảo mật trước commit hoặc PR. Dùng chủ động sau khi xong một thay đổi chạm tới xác thực, xử lý input, crypto, quyền truy cập hoặc cấu hình.
tools: Read, Grep, Glob, Bash
disallowedTools: Write, Edit
model: opus
effort: high
# skills: [differential-review]   # bật sau khi cài Trail of Bits ở GĐ3
---
Bạn chỉ đọc, không sửa. Với mỗi vấn đề nêu: mức độ, file:dòng, vì sao sai, cách sửa.
Ưu tiên lỗi đúng/sai và bảo mật hơn style. Không thấy vấn đề thì liệt kê những gì đã kiểm tra.
```

Agent OpenCode ⚙️ (`opencode-agents/worker.md`):

```markdown
---
description: Làm việc cơ học được giao (đổi tên, định dạng, boilerplate, dịch tài liệu, test đơn giản). Không tự mở rộng phạm vi.
mode: all
model: tuf/coder-fast
temperature: 0.2
steps: 30
permission:
  edit: allow
  webfetch: deny
  bash:
    "*": deny
    "pytest*": allow
    "npm test*": allow
    "git diff*": allow
---
Chỉ làm đúng việc được giao, trong thư mục hiện tại. Xong thì liệt kê file đã sửa và lệnh kiểm tra đã chạy.
```

`oc-worker` gọi worker bằng lệnh sau (thêm `--standalone` nếu service nền của OpenCode chưa chạy):
`opencode run --agent worker -m tuf/coder-fast --format json --auto "<việc + tiêu chí hoàn thành>"`

**Quy tắc chung:**
- Subagent vẫn ăn chung hạn mức. Nó chỉ có lời khi (a) đẩy output dài như log test hay kết quả tìm kiếm ra khỏi context chính, hoặc (b) việc đủ đơn giản để model rẻ làm tốt.
- **Không** đặt `CLAUDE_CODE_SUBAGENT_MODEL=haiku` toàn cục, vì làm yếu mọi subagent, kể cả general-purpose. Gán model theo từng agent.
- Agent teams tốn khoảng 7 lần token (theo docs) và workflow/ultracode sinh nhiều agent. Chỉ dùng khi có rất nhiều phần việc độc lập.

### 7.3 Bền bỉ phiên (#3), skill `session-keeper` ✍️ hoặc 📦 planning-with-files

Gồm năm tầng, từ có sẵn đến tự làm:

1. **Tính năng sẵn có (⚙️):** bật `autoContinueAtUsageLimit` (mặc định chưa đặt; `install.py` đặt `true` nếu bạn chưa chọn); đặt tên phiên `claude -n <việc>`; quay lại bằng `claude --resume <tên>`; thử hướng khác bằng `/branch`; lùi lại bằng `/rewind`.
2. **Trạng thái trên đĩa**, thư mục `.agent/` trong mỗi project. Project nào đã có `PLAN.md` kiểu SCEE thì mục §0 của nó đóng vai bàn giao rút gọn, không tạo file trùng; chỉ tách `.agent/HANDOFF.md` khi cần bàn giao dài, ví dụ sang OpenCode (7.8):
   - `PLAN.md`: các giai đoạn dạng checkbox, là điểm quay lại.
   - `PROGRESS.md`: nhật ký từng mốc.
   - `FINDINGS.md`: quyết định và lý do.
   - `HANDOFF.md`, theo mẫu:
     ```markdown
     # HANDOFF: <việc>   ·   cập nhật <ngày giờ>   ·   công cụ/model: <...>
     ## Mục tiêu
     ## Trạng thái: đã xong / đang dở / chưa làm
     ## Quyết định đã chốt (kèm lý do)
     ## File đã chạm
     ## Cách kiểm chứng (lệnh, kết quả mong đợi)
     ## Bước tiếp theo (cụ thể, theo thứ tự)
     ## Câu hỏi còn mở
     ```
3. **Hook ✍️:**

   | Sự kiện | Việc làm |
   |---|---|
   | `SessionStart` (matcher `startup\|resume\|compact\|clear`) | Nếu có `.agent/HANDOFF.md`, chèn tóm tắt vào `additionalContext`. |
   | `PreCompact` | Nhắc cập nhật PROGRESS và commit thư mục `.agent/`. Không chặn compaction. |
   | `Stop` | Nếu đã sửa file mà PROGRESS chưa cập nhật, thêm lời nhắc. Không chặn. |
   | `SessionEnd` | Tự commit `.agent/` với nhãn `wip`. Chỉ thư mục này, không đụng code. |

4. **Cảnh báo hạn mức:** statusline ⚙️ đọc `rate_limits.five_hour.used_percentage` và `rate_limits.seven_day.used_percentage`, hiển thị `model · effort · ctx% · 5h% · 7d%`, đồng thời ghi ra `agent-stack/state/limits.json`. Hook `UserPromptSubmit` ✍️ đọc file đó:
   - 5h ≥ 90%: nhắc ghi checkpoint.
   - 7d ≥ 80%: nhắc cập nhật HANDOFF ngay, ưu tiên việc quan trọng, đẩy việc cơ học sang `oc-worker`.
   - Lưu ý: statusline là tính năng của terminal, có thể không chạy trong desktop app (cần kiểm tra ở GĐ2). Trong desktop app thì xem `/usage` bằng tay.
5. **Bàn giao chéo công cụ:** `AGENTS.md` có luật: "Nếu có `.agent/HANDOFF.md` thì đọc trước khi làm gì khác." OpenCode đọc được cả luật lẫn skill, nên tiếp tục đúng chỗ.

**Diễn tập (nghiệm thu GĐ2):** (a) `kill -9` giữa chừng rồi `claude --continue`; (b) `/clear` rồi khôi phục từ file; (c) giả lập hết hạn mức tuần: mở OpenCode và làm tiếp từ HANDOFF. Mục tiêu: phục hồi trong ≤ 5 lượt và không mất quyết định nào đã chốt.

### 7.4 Bộ định tuyến (#4 + #5), skill `task-router` ✍️

**Cập nhật 02/10/2026 theo yêu cầu của bạn:**
- **Dòng ➡️ có ở cuối mọi câu trả lời**, kể cả câu hỏi nhanh, và có thêm trường Skill: `➡️ Tiếp: <việc> · Model · Effort · Subagent · Skill`. Luật nằm trong `SHARED.global.md`, nên áp cho cả Claude Code lẫn OpenCode; bảng chọn của Claude Code nằm trong `CLAUDE.global.md`.
- **Router đọc nội dung project**, không chỉ đọc câu bạn gõ.
  - Lúc mở phiên, hook dựng hồ sơ project từ danh sách file: loại code, có test, có CI, có code xác thực hay mã hóa. Hồ sơ được lưu tạm 6 giờ, và chỉ dựng cho git repo hoặc thư mục có file kế hoạch.
  - Từ hồ sơ đó, hook gợi ý skill và subagent hợp với project, rồi định tuyến luôn việc tiếp theo trong §0.
- **Mỗi tin nhắn:**
  - Tin nhắn kiểu "làm tiếp" được định tuyến theo việc tiếp theo trong §0.
  - Loại project bổ sung skill cho luật đang khớp, ví dụ `c-review` khi review bảo mật code C.
  - Dòng ➡️ dùng chính các gợi ý này.


| Tầng | Cách làm | Chi phí | Khi nào dùng |
|---|---|---|---|
| A. Luật | Hook `UserPromptSubmit` đọc `router-rules.json`, so khớp từ khóa tiếng Việt (đã chuẩn hóa bỏ dấu) và tiếng Anh. | 0 token, dưới 50 ms | Luôn luôn |
| B. Model local | Ollama hoặc tuf (Qwen3.5 4B), trả về JSON theo schema. | Miễn phí, riêng tư, 1–3 giây | Khi tầng A không khớp và prompt dài |

Hook trả về hai thứ: `additionalContext` để Claude biết gợi ý, và `systemMessage` để **bạn** thấy gợi ý ngay trên màn hình. Ví dụ:

```json
{"systemMessage": "router: security-review → /model opus · /effort high · agent reviewer · skill differential-review",
 "hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
   "additionalContext": "[router] Gợi ý: dùng skill differential-review, giao agent reviewer. Lý do: prompt khớp 'bảo mật'."}}
```

Mẫu `router-rules.json` (bản thật lấy từ kết quả GĐ4):

```json
{"rules": [
  {"id": "security-review", "match": ["bao mat", "lo hong", "review", "audit", "threat"],
   "skills": ["differential-review"], "model": "opus", "effort": "high", "agent": "reviewer"},
  {"id": "research", "match": ["nghien cuu", "so sanh", "tim hieu", "research"],
   "skills": ["research"], "model": "sonnet", "effort": "medium", "agent": "researcher"},
  {"id": "mechanical", "match": ["doi ten", "rename", "format", "boilerplate"],
   "model": "haiku", "effort": "low", "agent": "oc-worker"},
  {"id": "writing", "match": ["bai luan", "essay", "viet lai", "blog"],
   "skills": ["giong-van", "humanizer"], "model": "sonnet", "effort": "medium"}
], "default": null}
```

**Gợi ý sau mỗi tin (#5).** Thêm vào `CLAUDE.md` một luật: với câu trả lời có việc tiếp theo, kết thúc bằng một dòng

`➡️ Tiếp: <việc> · Model: <...> · Effort: <...> · Subagent: <...>`

Bỏ qua với câu hỏi nhanh. Chi phí khoảng 30 token mỗi lượt.

Bảng định tuyến khởi điểm (giả thuyết, GĐ4 sẽ chỉnh bằng số liệu):

| Việc tiếp theo | Model | Effort | Subagent |
|---|---|---|---|
| Hỏi nhanh, giải thích ngắn | sonnet | low | — |
| Xem tiến độ, hỏi "làm gì tiếp?" | sonnet | low | — (skill tien-do) |
| Tìm code, đọc nhiều file | (giữ model hiện tại) | — | Explore (haiku) |
| Nghiên cứu web, tài liệu | sonnet | medium | researcher |
| Viết tính năng thông thường | sonnet | medium | — |
| Debug khó, nhiều bước | opus | high | — |
| Lập kế hoạch, thiết kế kiến trúc | opusplan / opus | high | Plan |
| Review code hoặc bảo mật trước commit | opus | high | reviewer |
| Chạy test/lint và tóm tắt lỗi | — | — | test-runner (haiku) |
| Việc cơ học hàng loạt | haiku / OpenCode local | low | oc-worker |
| Việc tự chủ nhiều giờ, cực khó | fable (nếu gói cho phép) | high | — |
| Viết văn bản | sonnet | medium | — (skill giong-van) |

**"Luôn dùng skill" (#4)** làm bằng ba cách, không ép:
(1) Viết `description` đặt use-case lên đầu, thêm `when_to_use`; (2) luật ngắn trong `AGENTS.md`: "Trước việc không tầm thường, xem có skill phù hợp không. Có thì dùng, không có thì nói rõ."; (3) đo bằng `claude plugin eval` với grader "skill đã kích hoạt" trên 10 prompt nên kích hoạt và 10 prompt không nên.

### 7.5 Viết tự nhiên (#6), skill `giong-van` ✍️

- 📦 humanizer cho tiếng Anh.
- ✍️ Skill `giong-van` cho cả tiếng Việt và tiếng Anh:
  ```
  giong-van/
  ├── SKILL.md          # quy trình + checklist
  ├── samples/          # bài bạn tự viết (không commit) và kinh-dien/: 5 bài văn học kinh điển mỗi ngôn ngữ (có commit);
  │                     # mẫu riêng từng project viết luận nằm ở .agent/giong-van/samples/ của project
  ├── style-card.md     # đặc điểm giọng văn, Claude rút ra, bạn duyệt
  └── vi-ai-tells.md    # dấu hiệu văn AI tiếng Việt, bạn bổ sung dần
  ```
- Quy trình: bạn đưa ý hoặc bản nháp → skill sửa theo `style-card` → bỏ dấu hiệu văn AI → giữ nguyên ý, **không bịa trải nghiệm hay sự kiện** → trả về bản sửa kèm danh sách thay đổi để bạn duyệt.
- Danh sách `vi-ai-tells.md` khởi đầu: mở bài "Trong bối cảnh…"; "không chỉ… mà còn…"; "đóng vai trò quan trọng", "góp phần"; mở hoặc kết bằng "Tóm lại", "Nhìn chung"; bộ ba tính từ; các câu dài đều nhau; in đậm hoặc emoji thừa; kết luận sáo rỗng; "hành trình", "khám phá".
- **Phạm vi:** dùng cho bài của chính bạn. Detector AI không đáng tin, nên mục tiêu là chất lượng và giọng thật, không phải qua mặt công cụ. Với bài nộp có quy định về AI, làm theo quy định nơi nhận.
- Eval: đọc mù 5 cặp (bản bạn tự viết so với bản qua skill) xem còn giữ được giọng của bạn không.

### 7.6 Cổng kiểm duyệt, skill `vet-skill` ✍️

Đầu vào: URL repo hoặc đường dẫn. Các bước:

1. **Metadata** (`gh api repos/<owner>/<repo>`): archived thì loại; không cập nhật trên 6 tháng thì cảnh báo; không có giấy phép thì cảnh báo (không được phân phối lại); dưới 500★ thì phải đọc kỹ hơn.
2. **Ghim phiên bản:** clone tại một commit cụ thể, ghi SHA.
3. **Quét tĩnh:** `skill-scanner scan <path> --use-behavioral --format markdown` (chạy local).
4. **Đọc toàn bộ:** `SKILL.md`, `scripts/`, **hook của plugin (tự chạy mỗi phiên!)**, `.mcp.json` (endpoint mạng), `allowed-tools`, các lệnh `` !`cmd` `` (chạy khi skill được gọi).
5. **Tìm dấu hiệu xấu:** `curl | sh`, base64, `eval`, đọc `~/.ssh`, `~/.aws` hay keychain, gửi dữ liệu tới domain lạ, câu kiểu "bỏ qua hướng dẫn trước", ký tự ẩn.
6. **Chạy thử cô lập:** trong thư mục rỗng, bằng `claude --plugin-dir <path>` (chỉ có hiệu lực cho phiên đó).
7. **Ghi `vetted.lock`:** tên, nguồn, SHA, ngày, kết quả, ghi chú. Khi có bản mới thì diff giữa SHA cũ và mới rồi kiểm lại.

Luật cứng: không cài từ ClawHub; không chạy installer `curl | sh` khi chưa đọc; không dùng `--dangerously-skip-permissions`; ưu tiên marketplace chính thức và repo chính chủ.

### 7.7 Bộ eval "giữ hiệu suất" (GĐ4)

- **Bộ việc:** 12–15 việc thật lấy từ project của bạn (pdf-translator, SCEE, archctl…): 4 coding có test, 3 research có đáp án kiểm được, 3 review bảo mật (file có lỗ hổng cài sẵn), 2 QA (viết test cho hàm có sẵn), 2 viết.
- **Cấu hình so sánh:** A `sonnet/medium` (hiện tại) · B `sonnet/high` · C `opus/medium` · D `opusplan/medium` · E = A cộng subagent rẻ (Explore và test-runner chạy haiku). Bắt đầu với A, C, D; chạy B, E nếu cần.
- **Thước đo:** tỉ lệ đạt (test pass, rubric chấm); chi phí ước tính theo giá niêm yết (`claude -p --output-format json` có trả về) dùng thay cho % hạn mức; thời gian chạy.
- **Quy tắc chọn:** lấy cấu hình **rẻ nhất** mà tỉ lệ đạt không thấp hơn cấu hình tốt nhất quá 1 việc (trên khoảng 15 việc) qua 2 lần chạy. Nếu chênh lệch nằm trong mức nhiễu thì chạy lần thứ 3.
- **Ngân sách:** 15 việc × 3 cấu hình × 2 lần = 90 lượt agent. Chia ra 3–4 ngày để không đốt hạn mức tuần, và đặt `--max-cost-usd` làm trần.
- **Chạy công bằng (sửa ngày 02/10/2026):** model làm việc ngoài agent-stack, nên không thấy `CLAUDE.md`, grader hay lời giải. Bài làm được chốt thành patch ngay khi lượt chạy kết thúc; đổi grader thì chấm lại bằng `--regrade`. Lượt hỏng được chia thành nhóm vận hành (tính là trượt) và nhóm môi trường (phải chạy lại). Script chỉ chốt cấu hình khi ma trận đủ; gộp kết quả nhiều ngày bằng `--report`.

### 7.8 Theo dõi tiến độ (#7), skill `tien-do` ✍️

**Nguyên tắc:**
- **Không tạo hệ thống quản lý thứ hai.** Đọc đúng file kế hoạch mà project đang có. Mẫu chuẩn chỉ áp dụng cho project mới.
- **Script làm phần nặng, LLM chỉ xếp hạng.** Script thu thập dữ liệu không tốn token; Claude chỉ đọc kết quả, sắp thứ tự và giải thích.
- **Chỉ đọc.** Muốn đánh dấu xong hay sửa §0 thì skill đề xuất kèm bằng chứng (commit, kết quả test); bạn duyệt rồi mới ghi.
- **Kết quả kiểm tra có hạn dùng.** `session-keeper/scripts/receipt.py` ghi mỗi lần kiểm tra kèm dấu vân tay nội dung code. `tien-do` xếp kiểm tra đang trượt vào bậc chặn đường, và nhắc chạy lại khi kết quả đạt đã cũ hơn code hiện tại. Commit mà không đổi nội dung thì biên nhận vẫn còn khớp.

**Mẫu §0 chuẩn**, rút từ `SCEE/PLAN.md`, dùng cho project mới (đặt trong `PLAN.md` ở gốc hoặc `.agent/PLAN.md`):

```markdown
## 0. Đang ở đâu, việc tiếp theo (cập nhật mỗi lần dừng phiên)
*Cập nhật <ngày>.*
- **Xong:** …
- **Đang dở:** … (kèm file, nhánh, tên phiên Claude Code liên quan)
- **Việc tiếp theo, theo thứ tự:** 1. … 2. …
- **Quyết định còn treo:** …
- **Mốc kiểm tra:** lệnh test + kết quả mong đợi (ví dụ `274 passed, 37 xfailed`)
- **Sau khi bị ngắt:** các bước kiểm tra nhanh trước khi làm tiếp
```

**Nguồn dữ liệu, theo thứ tự ưu tiên:**

| Nguồn | Lấy gì | Ghi chú |
|---|---|---|
| `PLAN.md` §0 hoặc `.agent/HANDOFF.md` | Đang dở, việc tiếp theo, quyết định treo, mốc test | Nguồn chính. |
| Checkbox trong `PLAN.md` / `PROGRESS.md` | % đã xong; giai đoạn hiện tại (giai đoạn đầu tiên còn ô trống) | Ba thư mục học dùng kiểu này. |
| git | File chưa commit (và đã để bao lâu), stash, commit chưa push, nhánh chưa merge, lần commit cuối | Project không có git thì bỏ qua. |
| TODO / FIXME | Chỉ tính trong các file bạn sửa trong 14 ngày gần nhất | Tránh nhiễu từ code bên thứ ba (XiaomiMiMo có 138 file). |
| `gh` | PR đang mở, trạng thái CI của lần chạy cuối | Chỉ khi có remote GitHub. |
| Mốc test | So kết quả lần chạy gần nhất (do skill `verify` ghi lại) với mốc trong §0 | Không tự chạy test, trừ khi bạn yêu cầu. |
| Phiên Claude Code | Tên các phiên gần đây của project, để gợi ý `claude --resume <tên>` | Chỉ đọc tên và thời gian. Không phân tích transcript, vì định dạng đó là nội bộ và hay đổi. |

**Cách xếp hạng "việc tiếp theo":**

1. **Chặn đường:** test hoặc CI đỏ, kết quả lệch mốc test, xung đột merge, file chưa commit quá 24 giờ.
2. **Dang dở:** mục "Đang dở" trong §0, mục chưa xong đầu tiên của "Việc tiếp theo", nhánh có commit chưa push, PR đang chờ bạn.
3. **Giai đoạn hiện tại:** ô chưa tick đầu tiên của giai đoạn đang làm.
4. **Nợ mới:** TODO/FIXME vừa thêm gần đây.
5. **Bị bỏ quên:** project còn việc dở mà không có hoạt động quá 14 ngày. Skill hỏi: làm tiếp, tạm dừng hay đóng?

Mỗi việc kèm gợi ý `Model · Effort · Subagent` lấy từ bảng định tuyến (7.4). Với việc kiểm chứng được, skill đề xuất luôn một câu `/goal`, ví dụ: `/goal pytest ra đúng 274 passed, 37 xfailed và git status sạch`.

**Hai chế độ:**
- `/tien-do`: project hiện tại.
- `/tien-do all`: mọi thư mục trong `~/Documents/Claude/`, gộp thành một bảng gồm project · hoạt động gần nhất · việc dang dở · việc tiếp theo · cảnh báo.

Ví dụ bản tóm tắt cho một project (minh họa, dựng từ `SCEE/PLAN.md` hiện tại; dòng cảnh báo là giả định):

```
📍 SCEE · cập nhật §0 ngày 30/09 · nhánh main · không có file chưa commit
Tiến độ: G0 ✓ · G0.5 ✓ · G1 chưa bắt đầu
Đang dở: §0 bước 2, danh sách dọn về một phiên bản (chờ bạn duyệt)
Tiếp theo:
  1. Lập danh sách dọn (06 §5–6)          · sonnet · medium
  2. Viết tài liệu thiết kế hợp nhất      · opusplan · high
Cảnh báo: mốc test 274 passed / 37 xfailed chưa được chạy lại kể từ commit 30/09
```

**Ba cách kích hoạt:**

| Cách | Chi phí | Khi nào |
|---|---|---|
| Hook `SessionStart` (startup, resume) chạy script ở chế độ `--brief` | 0 token LLM, khoảng 150 token context | Mỗi lần mở phiên trong project có file kế hoạch. Hiện 3–6 dòng "đang dở / tiếp theo" cho bạn (`systemMessage`) và cho Claude (`additionalContext`). Gộp chung với hook của 7.3 để chỉ chèn một khối. |
| Gõ `/tien-do` hoặc hỏi "làm gì tiếp?" | Khoảng 1–3k token (`sonnet · low`, chạy với `context: fork`) | Khi cần xếp hạng và giải thích. |
| Tác vụ định kỳ của desktop app, ví dụ sáng thứ Hai | 1 lượt mỗi tuần | Chạy `/tien-do all`, ghi ra `~/Documents/Claude/TIEN-DO.md` và gửi thông báo. **Bỏ ngày 03/10/2026:** mỗi project tự theo dõi. |

**Cấu trúc skill:**

```
tien-do/
├── SKILL.md              # name, description (≤ 1.024 ký tự), model: sonnet, effort: low, context: fork
├── scripts/collect.py    # Python thuần (stdlib), xuất JSON; --brief cho hook; --all cho mọi project
└── templates/PLAN-0.md   # mẫu §0 cho project mới
```

- Trong Claude Code, `SKILL.md` chèn sẵn kết quả của script bằng `` !`python3 ${CLAUDE_SKILL_DIR}/scripts/collect.py` ``. OpenCode không hỗ trợ cú pháp này, nên phần thân skill ghi thêm: "Nếu chưa thấy dữ liệu, chạy `python3 <thư mục skill>/scripts/collect.py`."
- Mỗi project có thể có cấu hình riêng (tùy chọn) trong `.agent/tien-do.json`: file nguồn, tên mục §0, lệnh test và mốc test, các thư mục loại trừ.

**Câu hỏi dẫn dắt khi bạn viết skill:**
1. Một mục "đang dở" cần những trường nào để người khác, hoặc OpenCode, làm tiếp được mà không phải hỏi lại?
2. Khi §0 và git mâu thuẫn (§0 ghi "xong" nhưng còn file chưa commit), nên tin nguồn nào, và báo cho bạn thế nào?
3. Làm sao phát hiện §0 đã cũ, ví dụ ngày cập nhật §0 sớm hơn commit gần nhất?
4. Đo bằng cách nào để biết "việc tiếp theo" mà skill đề xuất là đúng?

**Nghiệm thu:**
- Script chạy dưới 2 giây cho mỗi project và dưới 10 giây với `all`. Chế độ `--brief` không tốn token LLM.
- Trên 3 project thật (SCEE, pdf-translator, security-whitebox) trong một tuần: việc tiếp theo mà skill đề xuất khớp với lựa chọn của bạn ở ít nhất 4/5 lần kiểm.
- Phát hiện đủ bốn loại: file chưa commit, ô chưa tick của giai đoạn hiện tại, mục "đang dở" trong §0, project bị bỏ quên.
- Không bao giờ tự sửa file kế hoạch khi bạn chưa duyệt.
- Chạy được trong OpenCode qua bash.

---

### 7.9 Dùng lại tốt nhất (#1, reuse-best), skill `reuse-best` ✍️

**Nhu cầu** (bạn làm rõ ngày 02/10/2026): trước khi build hay làm gì, luôn tìm thứ có sẵn tốt nhất, như công cụ trên GitHub hoặc bài nghiên cứu SOTA.

- **Thang tìm:** tính năng sẵn có của công cụ đang dùng → code trong project → skill đã duyệt (`vetted.lock`) → công cụ và thư viện trên GitHub → bài nghiên cứu SOTA. Từ 07/10/2026 (mục 6.15): trước khi tìm, đọc ràng buộc trong file của project (phiên bản, luật phụ thuộc, cách chạy production) và viết nhu cầu thành tiêu chí bắt buộc; chỉ dừng ở một bậc khi có ứng viên đạt mọi tiêu chí bắt buộc, có bằng chứng (`file:dòng`, dòng README), còn "chạy được" hay "có sẵn trong repo" thì chưa đủ; việc lớn vẫn tìm tới bậc GitHub để đối chứng. Công sức tìm tỉ lệ với cỡ việc.
- **Script `scout.py`** (chỉ đọc, chỉ dùng thư viện chuẩn):
  - GitHub qua `gh`, có dự phòng bằng API công khai. Tìm hai lần (khớp nhất và nhiều sao nhất) rồi gộp, vì chạy thử thật cho thấy xếp theo độ khớp bỏ sót công cụ nổi tiếng. Câu tìm ra rỗng thì bỏ từ chung chung và tên ngôn ngữ rồi tìm lại một lần, vì GitHub đòi mọi từ đều khớp ("toml parser python" không ra `hukkin/tomli`).
  - `repo owner/name [owner/name …] --find "từ khóa"`: tối đa 5 repo một lần; lần phát hành (hay tag) gần nhất, issue đang mở, giấy phép và những dòng README nhắc tới từng tiêu chí, để kiểm ứng viên bằng bằng chứng chỉ với một lệnh `python3` (không cần quyền `gh` hay WebFetch). Đầu ra theo AXI (mục 6.16).
  - Bài báo qua OpenAlex, dự phòng bằng Semantic Scholar rồi arXiv. Chạy thử thật cho thấy Semantic Scholar hay trả 429 khi không có khóa, còn arXiv hay chậm.
  - Đánh dấu chỗ cần xem: repo đã lưu trữ, không có giấy phép, copyleft, lâu không cập nhật, ít sao; bài preprint, không rõ nơi đăng.
- **Luôn được nhắc:** luật chung trong `SHARED.global.md`, và router gợi ý skill này cho mọi việc thuộc nhóm "tính năng" và "kiến trúc", kèm lưu ý bỏ qua việc vặt. Có thêm luật riêng cho câu hỏi kiểu "có sẵn chưa", "SOTA".
- **Kết quả:** tối đa 5 ứng viên có bằng chứng theo từng tiêu chí, rồi quyết định dùng lại, điều chỉnh hay tự làm, ghi vào mục quyết định của file kế hoạch kèm nguồn. Có hai mục bắt buộc: "Phần còn phải làm" (tiêu chí mà lựa chọn chưa đạt) và "Cần người dùng quyết" (ràng buộc va nhau, thứ cần duyệt); quyết định không được thu hẹp nhu cầu.
- **An toàn:** thứ tìm được phải qua `vet-skill` trước khi cài; chỉ chép code khi giấy phép cho phép; câu tìm kiếm không chứa code hay thông tin riêng.

## 8. Lộ trình triển khai

Mỗi giai đoạn ghi kèm model và effort nên dùng để làm chính giai đoạn đó (tự áp dụng yêu cầu #5).

### GĐ0: Chuẩn bị và đo nền (1 buổi) · `sonnet · low`
- [ ] Trả lời các câu hỏi còn mở ở mục 10.
- [ ] Nâng cấp: `brew upgrade --cask claude-code` và `brew upgrade --cask opencode-v2`.
- [ ] Sao lưu `~/.claude/settings.json` và `~/.config/opencode/opencode.jsonc`.
- [ ] `git init` trong `agent-stack/`.
- [ ] Kiểm chứng OpenCode: `opencode models | grep -E "tuf|openai-oauth"` và `opencode run -m tuf/coder-fast "trả lời: ok"`.
- [ ] Ghi `BASELINE.md`: `/usage` (24 giờ và 7 ngày, kèm phần phân bổ), `/insights`, `/context` của một phiên điển hình.
- [ ] Bật lại cảnh báo usage của workflow (bỏ `skipWorkflowUsageWarning`).
- [ ] Đọc lại điều khoản dịch vụ trước khi dùng tiếp jcode với Claude Max và proxy openai-oauth.

**Nghiệm thu:** `BASELINE.md` có số liệu; hai công cụ chạy bản mới; OpenCode gọi được model local.

### GĐ1: Cổng kiểm duyệt (1–2 buổi) · `opus · high` (cần phán đoán bảo mật)
- [ ] `uv tool install cisco-ai-skill-scanner`
- [ ] ✍️ Viết skill `vet-skill` theo 7.6, dùng skill-creator để chạy eval.
- [ ] Tạo `vetted.lock`.
- [ ] Thử trên 3 repo: anthropics/skills (đối chứng sạch), planning-with-files, humanizer.

**Nghiệm thu:** có 3 báo cáo; mỗi skill kiểm trong ≤ 15 phút.

### GĐ2: Bền bỉ phiên, yêu cầu #3 (2–3 buổi) · `sonnet · medium`, nhờ `reviewer` xem hook
- [ ] 📦 Thử planning-with-files 1 tuần (sau khi qua GĐ1), **hoặc** ✍️ viết `session-keeper` gọn hơn theo 7.3.
- [ ] ⚙️ Viết `AGENTS.md` chung; `~/.claude/CLAUDE.md` import nó và thêm phần riêng của Claude.
- [ ] ⚙️ Statusline 5h/7d + `limits.json`; ✍️ hook cảnh báo hạn mức.
- [ ] ✍️ Hook SessionStart, PreCompact, Stop, SessionEnd.
- [ ] Diễn tập 3 kịch bản ở 7.3. Kiểm tra thêm hành vi tự chờ trong desktop app.

**Nghiệm thu:** phục hồi trong ≤ 5 lượt, không mất quyết định đã chốt; OpenCode làm tiếp đúng bước ghi trong HANDOFF.

### GĐ2b: Theo dõi tiến độ, yêu cầu #7 (1–2 buổi) · `sonnet · medium`
Làm ngay sau GĐ2, vì dùng chung file trạng thái và chung hook `SessionStart`.
- [ ] Rút mẫu §0 từ `SCEE/PLAN.md` thành `templates/PLAN-0.md`; thêm §0 cho pdf-translator và archctl.
- [ ] ✍️ Viết `scripts/collect.py` (chỉ đọc, xuất JSON) và `SKILL.md` theo 7.8.
- [ ] ⚙️ Gộp `collect.py --brief` vào hook `SessionStart` của GĐ2, để mỗi lần mở phiên chỉ chèn một khối.
- [ ] (Tùy chọn) `git init` cho ba thư mục học, để có lịch sử tiến độ và để các tín hiệu git hoạt động.
- [ ] (Tùy chọn) Bật task list trên model 5.5: `CLAUDE_CODE_ENABLE_TODO_TOOLS=1` và `CLAUDE_CODE_TASK_LIST_ID=<project>`. Đây chỉ là công cụ phụ trong phiên; nguồn sự thật vẫn là §0.
- [x] ~~(Tùy chọn) Tác vụ định kỳ chạy `/tien-do all` mỗi sáng thứ Hai.~~ Bỏ (03/10/2026): mỗi project tự theo dõi qua §0 của nó.
- [ ] (Tùy chọn) Thử plugin `project-artifact` cho SCEE.

**Nghiệm thu:** theo các tiêu chí ở cuối mục 7.8.

### GĐ3: Kho năng lực v1, yêu cầu #1 (2 buổi) · `sonnet · medium`
- [ ] Cài các mục ghi **Cài** ở mục 6, mỗi mục qua `vet-skill`: LSP (Python, C/C++), context7, playwright + webapp-testing, semgrep, các skill chọn lọc của Trail of Bits, skill lẻ của Matt Pocock, humanizer, session-report, claude-code-setup, claude-md-management; CLI gitleaks và osv-scanner.
- [ ] Tắt skill không dùng bằng `skillOverrides`; kiểm tra bằng `/skills`, `/context`, `/skill-doctor`.
- [ ] Chạy `claude-code-setup` trên một project thật.

**Nghiệm thu:** ≤ 20 skill bật toàn cục; không mô tả nào bị cắt; ≤ 4 MCP.

### GĐ4: Đội agent và eval, yêu cầu #2 (3 buổi) · `opus · high` để thiết kế eval; khi chạy eval thì dùng chính cấu hình cần đo
- [ ] ⚙️ Tạo 5 agent Claude Code và 1 agent OpenCode theo 7.2.
- [ ] ✍️ Soạn bộ 12–15 việc thật và cách chấm theo 7.7.
- [ ] Chạy cấu hình A, C, D (mỗi cái 2 lần); thêm B, E nếu cần.
- [ ] Chốt `routing-table.md` v1.

**Nghiệm thu:** bảng định tuyến có số liệu; cấu hình được chọn đạt ≥ (tốt nhất − nhiễu) và không tốn hạn mức hơn baseline. Rẻ hơn là điểm cộng, không bắt buộc.

### GĐ5: Router, yêu cầu #4 và #5 (2–3 buổi) · `sonnet · medium`
- [ ] ✍️ Viết `router-rules.json` từ `routing-table.md`.
- [ ] ✍️ Hook tầng A; thêm luật dòng ➡️ vào `CLAUDE.md`.
- [ ] Soạn 40 prompt có nhãn để đo độ chính xác của router; tùy chọn so với tầng B (model local).
- [ ] Đo kích hoạt skill bằng `claude plugin eval`.

**Nghiệm thu:** router đúng ≥ 85% trên 40 prompt; hook chạy ≤ 300 ms; skill kích hoạt đúng ≥ 85% và kích hoạt nhầm ≤ 10%.

### GĐ6: Viết tự nhiên, yêu cầu #6 (1–2 buổi) · `sonnet · medium`
- [ ] 📦 humanizer.
- [ ] ✍️ `giong-van`: gom samples, viết style-card, vi-ai-tells, SKILL.md.
- [ ] Đọc mù 5 cặp.

**Nghiệm thu:** bạn nhận ra giọng mình ở ≥ 4/5 bản; không có ý hay sự kiện nào bị bịa.

### GĐ7: Vận hành định kỳ (30 phút mỗi tháng)
- [ ] Nâng cấp hai công cụ; kiểm lại skill có bản mới (diff theo SHA).
- [ ] Chạy lại eval khi có model mới (ví dụ Sonnet 5.5 vừa ra ngày 28/09) rồi cập nhật bảng định tuyến.
- [ ] Chạy `/skill-doctor`, `/usage` (xem phân bổ), `/doctor prompt-audit`; tỉa skill không dùng.

---

## 9. Rủi ro và cách giảm

| Rủi ro | Khả năng | Ảnh hưởng | Cách giảm |
|---|---|---|---|
| Skill hoặc plugin độc hại (chuỗi cung ứng) | Trung bình | Rất cao (đã có mã độc đánh cắp dữ liệu trên macOS) | Làm GĐ1 trước mọi cài đặt; ghim SHA; đọc kỹ hook. |
| Chất lượng giảm khi dùng model rẻ | Cao nếu không đo | Cao | Eval ở GĐ4; cổng test và review; hỏng thì chạy lại ở mức cao hơn. |
| Context phình vì quá nhiều skill và MCP | Cao | Trung bình | Giới hạn 20 skill / 4 MCP; `/skill-doctor`. |
| Đổi model/effort liên tục làm mất cache | Trung bình | Trung bình (tốn hơn) | Chỉ đổi ở ranh giới việc. |
| Rò rỉ dữ liệu qua dịch vụ ngoài (Snyk, cloud sync của claude-mem) | Trung bình | Cao với code nhạy cảm | Chỉ dùng cho project không nhạy cảm; ưu tiên công cụ local. |
| Vi phạm điều khoản khi dùng OAuth gói Claude trong công cụ bên thứ ba (jcode, plugin kiểu opencode-with-claude) | Trung bình | Cao (có thể bị khóa tài khoản) | Chính sách đã đổi nhiều lần trong 2026: sửa ToS 02/2026, thực thi 04/2026, rồi có điều chỉnh 05/2026 theo báo chí. Không dùng Claude trong công cụ bên thứ ba khi chưa đọc điều khoản hiện hành. |
| Chạy không người giám sát (auto-continue + quyền rộng) | Thấp đến trung bình | Cao | Không dùng `bypassPermissions`; thêm deny rule cho lệnh nguy hiểm; dùng sandbox Bash. |
| Hook lỗi làm kẹt phiên | Trung bình | Thấp | Đặt timeout ngắn; gỡ bằng `claude --safe-mode`. |
| File kế hoạch lệch thực tế (§0 đã cũ), khiến báo cáo tiến độ sai | Trung bình | Trung bình | Script so ngày cập nhật §0 với commit gần nhất rồi cảnh báo; hook `Stop` nhắc cập nhật §0 khi đã sửa file; skill không tự đánh dấu xong. |
| Công cụ và docs thay đổi nhanh | Cao | Trung bình | GĐ7 hằng tháng; ghi phiên bản trong `vetted.lock`. |
| Model local không dùng được khi ra khỏi mạng nhà | Cao | Thấp | Dự phòng bằng Ollama trên máy hoặc model miễn phí của OpenCode Zen. |
| Dùng #6 để né detector với bài có quy định về AI | — | Cao | Giữ đúng phạm vi ở 7.5. |

---

## 10. Câu hỏi còn mở

Đã trả lời: ai viết skill (Claude viết v1), commit (có, sau mỗi giai đoạn), Jev (bỏ), phạm vi (chỉ `agent-stack/`), câu "(luôn kiểm tra" (thuộc reuse-best: trước khi build luôn tìm thứ có sẵn tốt nhất, xem 7.9).

1. ~~Gói Claude~~ **Đã trả lời (02/10/2026):** Max, nhưng có thể quay lại Pro nếu khối lượng công việc giảm. Usage credits: tắt (`get_usage` ngày 02/10: extra usage tắt, trần 100 USD/tháng, đã dùng 0). Nếu hạ xuống Pro, đo lại bằng `tools/usage_snapshot.py` và xem lại bảng định tuyến (dùng Opus ít hơn).
2. ~~Worker OpenCode~~ **Đã trả lời một phần (02/10/2026):** OpenCode đang dùng OpenRouter và model miễn phí của OpenCode. Cấu hình thật ở `~/.config/opencode/opencode.jsonc`: model mặc định `opencode/muse-spark-1.3-contributor-free`, kèm provider local `tuf` (192.168.1.13, chỉ trong mạng nhà). Theo trang OpenCode Zen, model contributor-free đổi giá rẻ lấy quyền dùng prompt và kết quả để huấn luyện model của Meta. Đã làm: `oc-worker` và `AGENTS.global.md` ghi rõ không tự rơi về model từ xa, không giao file chứa secret hay mã riêng tư. Còn mở: danh sách việc hay thư mục tuyệt đối không được gửi ra ngoài; có đổi model mặc định của OpenCode không (repo không tự sửa file đó). **Gác lại (03/10/2026):** bạn đã tự setup OpenCode riêng; chỉ làm khi bạn nhắc.
3. ~~Viết luận~~ **Đã trả lời (03/10/2026):** dùng đa dạng, nhiều mục đích, viết cả tiếng Việt và tiếng Anh. Mẫu mặc định là 5 bài văn học kinh điển mỗi ngôn ngữ, khác loại nhau (`plugin/skills/giong-van/samples/kinh-dien/`). Mỗi project viết luận có mẫu riêng trong `.agent/giong-van/samples/` và style card riêng, đúng ý style card theo từng thể loại.
4. ~~Theo dõi tiến độ~~ **Đã trả lời (03/10/2026):** không kích hoạt theo dõi toàn cục, không bản tổng hợp tuần; mỗi project tự theo dõi qua §0 của nó (hook SessionStart và `tien-do` trong project đó). `/tien-do all` chỉ chạy khi bạn hỏi. (Việc `git init` ba thư mục học vẫn để sau.)

---

## 11. Nguồn

**Docs chính thức Claude Code:** [model-config](https://code.claude.com/docs/en/model-config) · [sub-agents](https://code.claude.com/docs/en/sub-agents) · [hooks](https://code.claude.com/docs/en/hooks) · [skills](https://code.claude.com/docs/en/skills) · [costs](https://code.claude.com/docs/en/costs) · [interactive-mode (chờ hết giới hạn)](https://code.claude.com/docs/en/interactive-mode) · [sessions](https://code.claude.com/docs/en/sessions) · [memory / AGENTS.md](https://code.claude.com/docs/en/memory) · [statusline](https://code.claude.com/docs/en/statusline) · [plugin-evals](https://code.claude.com/docs/en/plugin-evals) · [changelog](https://code.claude.com/docs/en/changelog)

**Docs OpenCode:** [agents](https://opencode.ai/docs/agents/) · [skills](https://opencode.ai/docs/skills/) · [rules](https://opencode.ai/docs/rules/) · [config](https://opencode.ai/docs/config/) · [ecosystem](https://opencode.ai/docs/ecosystem/)

**Số đo chi phí và chất lượng:** hướng dẫn cost-optimization trong skill `claude-api` đi kèm Claude Code (số đo của Anthropic trên Fable 5 / Opus 5).

**An ninh skill:** [Snyk ToxicSkills](https://snyk.io/blog/toxicskills-malicious-ai-agent-skills-clawhub/) · [arXiv: Emerging Threats of the Agent Skill Ecosystem](https://arxiv.org/html/2605.28588) · [Sự cố ClawHub](https://www.termdock.com/en/blog/clawhub-malicious-skills-incident) · [ToxicSkills & ClawHavoc](https://www.agensi.io/learn/toxicskills-clawhavoc-agent-skills-security-crisis-2026) · [cisco skill-scanner](https://github.com/cisco-ai-defense/skill-scanner) · [snyk agent-scan](https://github.com/snyk/agent-scan)

**Theo dõi tiến độ:** [goal](https://code.claude.com/docs/en/goal) · [task list và session recap (interactive-mode)](https://code.claude.com/docs/en/interactive-mode) · [project-artifact (marketplace chính thức)](https://github.com/anthropics/claude-plugins-official) · [beads](https://github.com/gastownhall/beads) · [Backlog.md](https://github.com/MrLesk/Backlog.md)

**Điều khoản dịch vụ:** [WinBuzzer 02/2026](https://winbuzzer.com/2026/02/19/anthropic-bans-claude-subscription-oauth-in-third-party-apps-xcxwbn/) · [AlternativeTo](https://alternativeto.net/news/2026/2/anthropic-officially-bans-using-subscription-authentication-for-third-party-claude-use) · [BetterClaw: lệnh cấm và điều chỉnh](https://www.betterclaw.io/blog/openclaw-anthropic-subscription-ban)

**Repo và kho skill:** [anthropics/skills](https://github.com/anthropics/skills) · [claude-plugins-official](https://github.com/anthropics/claude-plugins-official) · [skills.sh](https://skills.sh) · [superpowers](https://github.com/obra/superpowers) · [mattpocock/skills](https://github.com/mattpocock/skills) · [planning-with-files](https://github.com/OthmanAdi/planning-with-files) · [claude-mem](https://github.com/thedotmack/claude-mem) · [trailofbits/skills](https://github.com/trailofbits/skills) · [humanizer](https://github.com/blader/humanizer) · [claude-code-router](https://github.com/musistudio/claude-code-router) · [OpenCode](https://github.com/anomalyco/opencode) · [jcode](https://github.com/1jehuang/jcode). Số sao lấy qua GitHub API ngày 2026-10-01.

**Rà soát nguồn chính thức của Anthropic (6.13), số liệu GitHub API ngày 2026-10-02:** [sandbox-runtime](https://github.com/anthropics/sandbox-runtime) · [defending-code-reference-harness](https://github.com/anthropics/defending-code-reference-harness) · [claude-code-security-review](https://github.com/anthropics/claude-code-security-review) · [claude-code-action](https://github.com/anthropics/claude-code-action) · [claude-plugins-community](https://github.com/anthropics/claude-plugins-community) · [knowledge-work-plugins](https://github.com/anthropics/knowledge-work-plugins) · [claude-cookbooks](https://github.com/anthropics/claude-cookbooks) · [claude-quickstarts](https://github.com/anthropics/claude-quickstarts) · [claude-agent-sdk-python](https://github.com/anthropics/claude-agent-sdk-python) · [claude-code](https://github.com/anthropics/claude-code) · [anthropics/skills](https://github.com/anthropics/skills) · [claude-plugins-official/plugins](https://github.com/anthropics/claude-plugins-official/tree/main/plugins)
