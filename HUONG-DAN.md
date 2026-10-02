# Hướng dẫn sử dụng agent-stack

Tài liệu này dành cho người dùng hằng ngày. Thiết kế và lý do chọn từng thứ nằm ở `KE-HOACH.md`; tiến độ triển khai ở `PLAN.md` §0; những gì đã cài trên máy ở `INSTALLED.md`.

Mục lục:

1. [agent-stack làm gì](#1-agent-stack-làm-gì)
2. [Kiểm tra đã cài đúng chưa](#2-kiểm-tra-đã-cài-đúng-chưa)
3. [Một ngày làm việc](#3-một-ngày-làm-việc)
4. [Những gì tự chạy](#4-những-gì-tự-chạy)
5. [Sáu skill](#5-sáu-skill)
6. [Subagent](#6-subagent)
7. [Dùng với OpenCode](#7-dùng-với-opencode)
8. [Cài, cập nhật, gỡ](#8-cài-cập-nhật-gỡ)
9. [Bảo trì và eval](#9-bảo-trì-và-eval)
10. [Tùy chỉnh](#10-tùy-chỉnh)
11. [Khi có trục trặc](#11-khi-có-trục-trặc)
12. [Tra cứu nhanh](#12-tra-cứu-nhanh)

---

## 1. agent-stack làm gì

Bộ này giải quyết bốn chuyện hay gặp khi làm việc với Claude Code:

- **Mất tiến độ** khi hết hạn mức, crash, compact hay đổi công cụ. Trạng thái được ghi ra đĩa, ở mục §0 của `PLAN.md`, và tự nạp lại mỗi khi mở phiên.
- **Không biết làm gì tiếp** khi quay lại project sau vài ngày. Skill `tien-do` đọc §0, git và TODO rồi xếp việc theo ưu tiên.
- **Tốn hạn mức vì chọn model quá mạnh** (hoặc quá yếu). Router gợi ý model, effort, subagent và skill cho từng việc; cuối mỗi câu trả lời có dòng ➡️.
- **Cài đồ bên thứ ba thiếu kiểm tra.** Skill `vet-skill` quét skill, plugin, MCP trước khi cài và ghi kết quả vào `vetted.lock`.

Ngoài ra có hai skill phụ: `giong-van` để chỉnh văn cho đúng giọng mình, và `reuse-best` để tìm thứ có sẵn trước khi tự viết.

Mọi thứ nằm trong repo này. Các file ngoài repo (`~/.claude/CLAUDE.md`, skill của OpenCode...) chỉ là symlink trỏ về đây, nên sửa trong repo là đủ.

---

## 2. Kiểm tra đã cài đúng chưa

Mở một phiên Claude Code mới trong thư mục có `PLAN.md` (ví dụ chính repo này). Đầu phiên phải thấy:

- dòng **📍** `<tên project>: tiếp theo → <việc đầu tiên trong §0>`;
- dòng **🧭** hồ sơ project, ví dụ `🧭 tài liệu, Python, có test`.

Hai dòng này do hook SessionStart in ra. Phần đầy đủ (§0, quyết định còn treo, mốc kiểm tra, trạng thái git, skill và subagent nên dùng) được nạp vào context của Claude, bạn không thấy trực tiếp. Nếu không thấy hai dòng trên:

```bash
claude plugin list
```

```bash
tail -3 ~/Documents/Claude/agent-stack/state/sessions.jsonl
```

Lệnh đầu phải có `agent-stack@agent-stack-local` ở trạng thái bật. Lệnh sau cho biết hook có chạy không và plugin được nạp từ đâu (`plugin_root`). Thư mục không phải git repo và không có file kế hoạch thì hook im lặng; đó là hành vi đúng.

**Chỉ khi chạy `claude` trong terminal**, thanh trạng thái ở dưới cùng phải có dạng:

```
Opus 5.5 · high · ctx 23% · 5h 41% · 7d 12%
```

Màu chuyển vàng rồi đỏ khi gần ngưỡng (ctx: 60/80%, 5h: 70/90%, 7d: 70/85%). Desktop app không chạy statusline, nên ở đó không có thanh này; xem mức dùng bằng `/usage`. Cách kiểm tra statusline đã chạy: file `state/limits.json` được tạo hoặc vừa cập nhật.

---

## 3. Một ngày làm việc

Đây là cách dùng điển hình. Phần lớn chỉ cần nói tự nhiên bằng tiếng Việt; skill tự kích hoạt theo từ khóa. Muốn gọi đích danh thì gõ `/agent-stack:<tên-skill>`.

**Mở project.** Đọc dòng 📍. Nếu đã nghỉ lâu hoặc không nhớ đang làm gì, hỏi:

> làm gì tiếp?

Skill `tien-do` trả về tối đa 3 việc, kèm lý do, gợi ý model và một câu `/goal` nếu việc đầu tiên kiểm chứng được.

**Trước một việc lớn.** Nếu sắp viết một tool, tính năng hay thuật toán không tầm thường:

> có sẵn thư viện nào làm việc X chưa?

Skill `reuse-best` tìm theo thứ tự: tính năng sẵn có, code trong project, skill đã duyệt, GitHub, rồi bài nghiên cứu. Kết quả là một quyết định dùng lại, điều chỉnh hay tự làm, kèm nguồn.

**Trong lúc làm.** Để ý dòng ➡️ cuối mỗi câu trả lời:

```
➡️ Tiếp: chạy test sau khi sửa parser · Model: sonnet · Effort: medium · Subagent: agent-stack:test-runner · Skill: không
```

Đây là gợi ý cho *việc kế tiếp*. Chỉ đổi model hay effort ở ranh giới giữa hai việc, vì đổi giữa chừng làm mất prompt cache và có khi tốn hơn.

**Khi chạy kiểm tra.** Nhờ Claude chạy qua `receipt.py` để có biên nhận. Biên nhận gắn với nội dung code lúc chạy, nên phiên sau biết kết quả còn đúng hay code đã đổi.

**Khi gần hết hạn mức.** Hook sẽ nhắc (xem mục 4). Lúc đó nói:

> lưu tiến độ

Skill `session-keeper` cập nhật §0 với đã xong gì, đang dở gì, việc tiếp theo, mốc kiểm tra. Hết hạn mức thì cứ để đó; phiên sau tự đọc lại §0.

**Khi chuyển sang OpenCode.** Nói "bàn giao sang OpenCode". Claude viết `.agent/HANDOFF.md`, rồi bạn chạy `opencode` trong thư mục project và nhắn "Đọc .agent/HANDOFF.md rồi làm tiếp bước 1".

**Trước khi commit.** Nếu thay đổi chạm tới xác thực, input, đường dẫn file, secret hay cấu hình, nhờ "review trước khi commit". Subagent `agent-stack:reviewer` (opus · high, chỉ đọc) sẽ xem.

---

## 4. Những gì tự chạy

Bạn không cần gọi các thành phần dưới đây. Chúng chạy theo sự kiện của Claude Code, đều viết bằng Python thư viện chuẩn, bắt mọi lỗi và không bao giờ làm kẹt phiên.

| Thành phần | Khi nào | Làm gì |
|---|---|---|
| Hook SessionStart | Mở phiên, resume, `/clear`, sau compact | Nạp §0 và hồ sơ project vào context; in dòng 📍 và 🧭 |
| Hook UserPromptSubmit | Mỗi tin nhắn | Gợi ý `[router]` cho việc trong tin nhắn (bạn thấy dòng `🧭 router: ...` khi có luật khớp); cảnh báo hạn mức khi vượt ngưỡng |
| Hook PreCompact | Trước khi compact | Ghi sự kiện; nhắc nếu §0 đã lâu chưa cập nhật. Không chặn compact |
| Hook Stop | Cuối mỗi lượt trả lời | Nhắc cập nhật §0 khi đã có từ 3 file đổi sau lần cập nhật §0 gần nhất; nhắc tối đa 30 phút một lần |
| Hook SessionEnd | Đóng phiên | Ghi một dòng vào `state/sessions.jsonl`, để `tien-do` gợi ý `claude --resume` |
| Statusline | Liên tục, chỉ trong terminal | Hiện model, effort, ctx, 5h, 7d; ghi `state/limits.json` cho hook cảnh báo |
| Luật chung | Mọi phiên | `~/.claude/CLAUDE.md` trỏ về `global/CLAUDE.global.md`: trả lời tiếng Việt, đọc §0 trước, không nói "xong" khi chưa kiểm chứng, dòng ➡️ |
| `autoContinueAtUsageLimit` | Khi chạm hạn mức | Claude Code tự làm tiếp khi hạn mức reset |

### Cảnh báo hạn mức

- Hạn mức 5 giờ: nhắc khi đã dùng từ **90%**. Claude sẽ ghi checkpoint vào §0 trước bước dài tiếp theo.
- Hạn mức tuần: nhắc khi đã dùng từ **80%**. Claude sẽ cập nhật §0 ngay.
- Lên 95% thì nhắc thêm một lần. Mỗi ngưỡng chỉ nhắc một lần cho mỗi phiên và mỗi chu kỳ reset.

Số liệu hạn mức do statusline ghi, mà statusline chỉ chạy trong terminal. Vì vậy **desktop app không có cảnh báo hạn mức** trừ khi gần đây bạn có mở `claude` trong terminal (số liệu cũ hơn 30 phút bị bỏ qua). Trong desktop app, tự để ý mức dùng và nói "lưu tiến độ" khi thấy cần.

---

## 5. Sáu skill

Mỗi skill có thể gọi bằng lời tự nhiên hoặc gọi thẳng `/agent-stack:<tên> <tham số>`. Script đi kèm cũng chạy tay được; mọi đường dẫn dưới đây tính từ gốc repo.

### 5.1 `tien-do`: tiến độ và việc nên làm tiếp

**Khi nào:** mở lại project, hỏi "làm gì tiếp", "đang dở gì", "status", hoặc muốn xem tổng quan mọi project.

**Gọi:**

- `/agent-stack:tien-do` cho project hiện tại.
- `/agent-stack:tien-do all` cho mọi project trong `~/Documents/Claude/`.

**Kết quả:** một dòng trạng thái, tối đa 3 việc nên làm, cảnh báo (§0 cũ, file chưa commit lâu, nhánh chưa merge, kiểm tra trượt hoặc đã cũ), và câu `/goal` gợi ý. Việc được xếp theo 5 bậc: chặn đường → dang dở → giai đoạn hiện tại → nợ TODO → bị bỏ quên.

**Chạy tay** (chỉ đọc, không sửa gì):

```bash
python3 plugin/skills/tien-do/scripts/collect.py --md
```

```bash
python3 plugin/skills/tien-do/scripts/collect.py --all --md
```

Thêm `--gh` để lấy cả PR và CI trên GitHub (cần mạng, cần `gh` đã đăng nhập). `--brief` in bản rút gọn, `--json` cho máy đọc.

### 5.2 `session-keeper`: lưu, làm tiếp, bàn giao

**Khi nào:** "lưu tiến độ", "sắp hết limit", "làm tiếp việc hôm qua", "bàn giao", hoặc project chưa có file kế hoạch.

**Bốn chế độ** (`/agent-stack:session-keeper <chế độ>`):

| Chế độ | Làm gì |
|---|---|
| `luu` (mặc định) | Cập nhật §0: ngày, Xong (kèm bằng chứng), Đang dở, Việc tiếp theo, Quyết định còn treo, Mốc kiểm tra. Cho bạn xem diff trước khi commit |
| `tiep-tuc` | Đọc §0, chạy các bước "Sau khi bị ngắt", chạy lại mốc kiểm tra nếu biên nhận đã cũ, báo chỗ lệch, đề xuất bước đầu tiên |
| `ban-giao` | Chạy `luu`, rồi tạo `.agent/HANDOFF.md` có sẵn §0 và trạng thái git |
| `khoi-tao` | Tạo `.agent/PLAN.md` từ mẫu cho project chưa có file kế hoạch |

**Nguyên tắc của §0:** chỉ có một nguồn sự thật. Các file khác chỉ trỏ tới §0, không chép. Không xóa lịch sử trong file kế hoạch; chỉ cập nhật §0 và tick checkbox.

**Chạy tay:**

```bash
python3 plugin/skills/session-keeper/scripts/state.py show --project <thư mục>
```

`state.py` có ba lệnh: `show`, `init`, `handoff`.

#### Biên nhận kiểm tra (`receipt.py`)

Luật chung yêu cầu mọi lệnh kiểm chứng chạy qua `receipt.py`:

```bash
python3 plugin/skills/session-keeper/scripts/receipt.py run -- python3 -m unittest discover -s tests -t .
```

```bash
python3 plugin/skills/session-keeper/scripts/receipt.py show
```

`run` chạy lệnh và ghi lại mã thoát kèm dấu vân tay của code lúc đó. `show` liệt kê biên nhận và đánh dấu biên nhận nào đã cũ vì code đổi sau khi chạy. Tùy chọn: `--project`, `--label`, `--timeout`.

### 5.3 `task-router`: chọn model, effort, subagent, skill

**Khi nào:** "việc này nên dùng opus hay sonnet?", "effort bao nhiêu?", "có nên giao subagent không?", "làm sao tiết kiệm token".

Phần lớn thời gian bạn không cần gọi skill này: hook đã chèn gợi ý `[router]` vào mỗi tin nhắn, và dòng ➡️ dùng gợi ý đó. Gọi `/agent-stack:task-router <mô tả việc>` khi muốn hỏi riêng.

**Nguyên tắc router áp dụng:**

1. Giữ chất lượng là bắt buộc. Chỉ hạ model hay effort khi có bước kiểm tra tự động hoặc model mạnh hơn sẽ xem lại.
2. Hạ effort trước, hạ model sau.
3. Việc rủi ro cao (bảo mật, mất dữ liệu, kiến trúc, migration) luôn opus · high.
4. Việc nhiều phần độc lập hoặc sinh output dài thì giao subagent.
5. Fable chỉ cho việc tự chủ rất dài và rất khó.

**Chạy tay** (0 token, chỉ so từ khóa):

```bash
python3 plugin/skills/task-router/scripts/route.py "review bảo mật trước khi commit"
```

```bash
python3 plugin/skills/task-router/scripts/route.py --session ~/Documents/Claude/<project>
```

`--project <thư mục>` thêm skill theo loại project; `--session` in hồ sơ project như hook SessionStart, dùng cho công cụ không có hook. Bảng gợi ý hiện tại ở `routing-table.md`, luật máy đọc ở `plugin/skills/task-router/rules.json`. Cả hai còn là giả thuyết cho tới khi có số liệu eval (mục 9).

### 5.4 `vet-skill`: kiểm duyệt đồ bên thứ ba

**Khi nào:** trước khi cài bất kỳ skill, plugin, MCP hay marketplace nào; khi dán link GitHub của một skill; khi hỏi "cái này có an toàn không".

**Gọi:**

```
/agent-stack:vet-skill owner/repo
/agent-stack:vet-skill owner/repo@v1.2.0:skills/ten-skill
/agent-stack:vet-skill ~/Downloads/mot-skill
```

**Skill làm gì:** tải đúng commit vào `.vet-cache/` (không chạy mã của đích), quét dấu hiệu độc hại (tải-rồi-chạy, đọc khóa và token, prompt injection, ký tự ẩn, hook tự chạy), chạy `skill-scanner`, rồi đọc tay từng file đáng ngờ. Skill chạy ở effort high, trong context riêng, và không được sửa file.

**Kết quả:** phán quyết của script (PASS / REVIEW / FAIL), khuyến nghị (cài, có điều kiện, thử trong 1 project, không cài), những gì sẽ chạy trên máy nếu cài, rủi ro còn lại, và lệnh duyệt để **bạn tự chạy**:

```bash
python3 plugin/skills/vet-skill/scripts/vet.py approve "<khóa>" --note "<lý do>"
```

Claude không tự duyệt. PASS chỉ có nghĩa là không thấy dấu hiệu đã biết.

**Các lệnh khác của `vet.py`:**

| Lệnh | Việc |
|---|---|
| `scan <đích> [--name] [--no-scanner] [--json]` | Quét. Mã thoát 0 = PASS, 1 = REVIEW, 2 = FAIL, 3 = lỗi |
| `list` | Xem mọi mục trong `vetted.lock` và trạng thái |
| `approve <khóa> --note "..."` | Duyệt |
| `reject <khóa> --note "..."` | Từ chối |
| `note <khóa> --recommend <cài\|có-điều-kiện\|thử-1-project\|không-cài> --text "..."` | Ghi nhận xét đọc tay; giữ được qua các lần quét lại |

Báo cáo đầy đủ nằm trong `vet-reports/`. Sau khi duyệt, chạy `./install.sh --apply` để cài các mục mới (mục 8).

### 5.5 `giong-van`: chỉnh văn đúng giọng mình

**Khi nào:** "sửa lại đoạn này cho tự nhiên", "đọc như AI viết", "viết lại email này đúng giọng mình", bài luận, blog, cover letter.

**Skill làm gì:**

1. Đo điểm dấu hiệu văn AI trên 1.000 từ bằng `tells.py`.
2. Sửa nội dung trước: câu thổi phồng thay bằng số liệu có sẵn, câu chung chung bỏ đi. Không bịa sự kiện; chỗ thiếu thì hỏi bạn.
3. Sửa câu chữ: mở bài sáo, "không chỉ... mà còn", kết bài nhắc lại, nhịp câu đều đều...
4. Đưa về giọng trong `style-card.md`: xưng hô, độ dài câu, mức trang trọng, từ quen dùng.
5. Đo lại, báo tối đa 5 thay đổi chính và điểm trước/sau.

Văn tiếng Anh dùng thêm skill `humanizer` (đã cài từ vendor).

**Để skill bắt giọng tốt hơn**, đặt khoảng 5 bài tự viết, càng khác loại càng tốt (blog, email, ghi chú, bài luận), vào `plugin/skills/giong-van/samples/`, rồi nói:

```
/agent-stack:giong-van tao-style-card
```

Claude điền `style-card.md` với ví dụ trích nguyên văn và hỏi bạn duyệt từng mục. Hiện thư mục `samples/` còn trống, nên skill chỉ dựa vào danh sách dấu hiệu chung.

**Chạy tay:**

```bash
python3 plugin/skills/giong-van/scripts/tells.py bai-viet.md
```

```bash
pbpaste | python3 plugin/skills/giong-van/scripts/tells.py -
```

`--no-samples` để bỏ so với bài mẫu, `--samples <thư mục>` để dùng bộ mẫu khác.

Skill này để văn hay hơn, không phải để qua mặt công cụ phát hiện AI. Bài nộp có quy định về AI thì làm theo quy định nơi nhận.

### 5.6 `reuse-best`: tìm thứ có sẵn trước khi tự làm

**Khi nào:** trước khi viết một tool, tính năng, script hay thuật toán không tầm thường; "có sẵn chưa", "thư viện nào tốt nhất", "SOTA". Bỏ qua với sửa nhỏ.

**Gọi:** `/agent-stack:reuse-best <nhu cầu>`, ví dụ `/agent-stack:reuse-best đọc PDF scan tiếng Việt ra text, chạy offline`.

**Thứ tự tìm**, dừng ở bậc đầu tiên đáp ứng được: tính năng sẵn có của công cụ → code trong project → skill đã duyệt trong `vetted.lock` → GitHub → bài nghiên cứu. Kết quả gồm tối đa 5 ứng viên (kèm sao, lần cập nhật, giấy phép; hoặc nơi đăng, năm, trích dẫn) và quyết định có nguồn. Claude sẽ đề nghị ghi quyết định vào file kế hoạch để phiên sau khỏi tìm lại.

**Chạy tay** (có gọi mạng tới GitHub, Semantic Scholar, arXiv; chỉ dùng từ khóa chung, đừng đưa code hay thông tin riêng vào):

```bash
python3 plugin/skills/reuse-best/scripts/scout.py github "pdf ocr vietnamese" --language python
```

```bash
python3 plugin/skills/reuse-best/scripts/scout.py papers "vietnamese ocr" --since 2024
```

`github` có thêm `--limit`, `--sort {both,best-match,stars,updated}`, `--json`.

Thứ tìm được là skill, plugin hay MCP thì vẫn phải qua `vet-skill`. Repo không có giấy phép thì chỉ học ý tưởng, không chép code.

---

## 6. Subagent

Subagent chạy trong context riêng và chỉ trả về kết quả gọn, nên context chính không bị đầy bởi log dài. Gọi bằng lời ("giao cho test-runner chạy test") hoặc để Claude tự chọn theo dòng ➡️. Tên đầy đủ có tiền tố `agent-stack:`.

| Subagent | Model | Quyền | Dùng khi |
|---|---|---|---|
| `agent-stack:reviewer` | opus · high | Chỉ đọc | Review code và bảo mật trước commit hoặc PR |
| `agent-stack:researcher` | sonnet · medium | Không sửa file | Tra docs, so sánh công cụ, kiểm chứng một nhận định; trả về có dẫn nguồn |
| `agent-stack:test-runner` | haiku | Chỉ đọc, chạy lệnh | Chạy test, lint, build và chỉ trả về phần lỗi |
| `agent-stack:explore-lite` | haiku | Chỉ đọc | Tìm vị trí code, nơi dùng một hàm, cấu hình. Rẻ hơn `Explore` nhưng không suy luận sâu |
| `agent-stack:oc-worker` | haiku | Chạy lệnh | Giao việc cơ học cho OpenCode chạy model local miễn phí (mục 7) |

Subagent vẫn tính vào hạn mức. Theo `BASELINE.md`, khoảng 70% chi phí đến từ subagent và workflow, nên đừng chia nhỏ việc mà một model làm liền mạch tốt hơn.

---

## 7. Dùng với OpenCode

OpenCode đọc cùng bộ luật và skill, qua symlink:

- `~/.config/opencode/AGENTS.md` → `global/AGENTS.global.md`
- `~/.config/opencode/skills/<tên>` → skill trong `plugin/skills/` và `vendor/skills/`
- `~/.config/opencode/agents/worker.md` → `opencode/agents/worker.md`

OpenCode không có hook, nên đầu phiên Claude (hoặc model trong OpenCode) phải tự chạy:

```bash
python3 ~/Documents/Claude/agent-stack/plugin/skills/task-router/scripts/route.py --session .
```

Luật chung đã dặn việc này, nên thường không cần nhắc.

### Agent `worker`

`worker` chạy model local `tuf/coder-fast` (miễn phí, chỉ chạy được khi ở mạng nhà), được sửa file nhưng gần như không được chạy lệnh ngoài vài lệnh kiểm tra như `git diff`. Dùng cho việc cơ học: đổi tên hàng loạt, định dạng, boilerplate, dịch tài liệu, test đơn giản.

Từ Claude Code, giao qua subagent `agent-stack:oc-worker`. Nó kiểm tra `git status` sạch, gọi worker, đọc diff, chạy test; hỏng thì thử lại một lần với `tuf/gpt-oss-medium`, vẫn hỏng thì bỏ thay đổi và trả việc về phiên chính. Gọi tay:

```bash
opencode run --agent worker -m tuf/coder-fast --format json --auto "<việc + tiêu chí xong + file được phép sửa>"
```

Thêm `--standalone` nếu báo lỗi không kết nối được service.

### Làm tiếp việc của Claude trong OpenCode

1. Trong Claude Code: "bàn giao sang OpenCode".
2. Trong terminal: `cd` vào project, chạy `opencode`.
3. Nhắn: "Đọc .agent/HANDOFF.md rồi làm tiếp bước 1".

Trong OpenCode, dòng ➡️ ghi Subagent là `build`, `plan` hoặc `worker`.

---

## 8. Cài, cập nhật, gỡ

Mọi thay đổi ngoài repo đều đi qua `install.sh`. Mặc định chỉ xem trước.

```bash
./install.sh
```

```bash
./install.sh --apply
```

`--apply` sao lưu trước rồi mới sửa, và chỉ cài mục đã `approve` trong `vetted.lock`. Mã thoát 1 là có lỗi, 2 là cài chưa đủ. Mỗi lần cài thêm một mục vào `INSTALLED.md`, kèm lệnh gỡ riêng cho từng thay đổi.

Các bước có thể chọn riêng bằng `--only`, ngăn cách bằng dấu phẩy:

| Bước | Cài gì |
|---|---|
| `rules` | Symlink luật chung cho Claude Code và OpenCode |
| `plugin` | Marketplace local và plugin `agent-stack` |
| `statusline` | Khóa `statusLine` trong `~/.claude/settings.json` |
| `autocontinue` | Khóa `autoContinueAtUsageLimit` |
| `catalog` | Plugin chính thức và skill vendor đã duyệt |
| `opencode` | Symlink skill và agent cho OpenCode |

Tùy chọn khác: `--replace-existing` thay file hoặc symlink đang có (có sao lưu); `--restore-workflow-warning` bỏ khóa `skipWorkflowUsageWarning`.

### Sau khi sửa code plugin

- **CLI trong terminal** nạp plugin tại chỗ: sửa trong repo có hiệu lực từ phiên sau.
- **Desktop app** chạy bản chép trong `~/.claude/plugins/cache/`. Tăng `version` trong `plugin/.claude-plugin/plugin.json`, rồi:

```bash
./install.sh --apply --only plugin
```

Mở phiên mới để nạp lại. Bản chép tìm về repo nhờ file `plugin/.agent-stack-home`, nên script và `state/` vẫn dùng chung.

Sửa skill của OpenCode hay luật chung thì không cần cài lại, vì đó là symlink.

### Gỡ

```bash
./install.sh --rollback
```

```bash
./install.sh --rollback --apply
```

Lệnh gỡ chạy ngược mọi lần cài, mới nhất trước: gỡ plugin và marketplace, gỡ symlink, khôi phục file từ bản sao lưu, xóa thư mục do lần cài tạo ra (kể cả `vendor/`), dọn `settings.json` và cache plugin, rồi so với bản chụp trước lần cài đầu và báo những gì còn khác. Gỡ riêng một lần cài: `./install.sh --rollback state/install-logs/<tên>.json --apply`.

Lần gỡ không đụng tới `vetted.lock`, `vet-reports/`, `state/`, `.vet-cache/`, các thư mục `backups/install-*` và công cụ cài bằng brew.

---

## 9. Bảo trì và eval

### Mỗi tháng

```bash
python3 tools/maintain.py
```

Script kiểm tra: phiên bản Claude Code và OpenCode; đồ bên thứ ba đã có commit mới chưa (có thì phải kiểm duyệt lại trước khi cập nhật); test và `claude plugin validate`; độ dài mô tả skill; mức dùng 7 ngày so với `BASELINE.md`; dung lượng `.vet-cache`; công cụ dòng lệnh khuyến nghị đã cài chưa. Chỉ đọc, trừ khi thêm `--clean-cache`. `--offline` bỏ bước gọi GitHub, `--skip-tests` bỏ chạy test.

### Xem mức dùng token

```bash
python3 tools/usage_snapshot.py --days 7
```

Đọc transcript cục bộ trong `~/.claude/projects/`, không gọi mạng.

### Mốc kiểm tra của repo

```bash
python3 plugin/skills/session-keeper/scripts/receipt.py run -- /usr/bin/python3 -m unittest discover -s tests -t .
```

```bash
python3 plugin/skills/session-keeper/scripts/receipt.py run -- claude plugin validate plugin
```

```bash
python3 evals/run_eval.py --self-test
```

```bash
python3 plugin/skills/task-router/scripts/route.py --eval evals/router-prompts.jsonl
```

Test phải đạt trên cả `/usr/bin/python3` (3.9) và `python3`.

### Eval chọn cấu hình

`evals/` có 12 việc để tìm cấu hình rẻ nhất mà vẫn giữ chất lượng. Cấu hình định nghĩa trong `evals/configs.json`: A (sonnet · medium), B (sonnet · high), C (opus · medium), D (opus · low), E (A + plugin), H (haiku, chỉ đo trần dưới).

```bash
python3 evals/run_eval.py --configs A,C,D --repeats 2
```

Không có `--yes` thì chỉ in kế hoạch và chi phí ước tính. Thêm `--yes` mới chạy thật và tốn hạn mức (lần chạy trên khoảng 15 USD theo giá niêm yết). Nên đặt trần: `--max-total-usd 20 --cap-usd 1`. Model làm việc trong thư mục tạm ngoài repo, để không đọc được grader hay lời giải. Các tùy chọn không gọi model: `--report <file.jsonl>` tổng hợp kết quả đã có, `--regrade <file.jsonl>` chấm lại bằng grader mới.

Có số liệu rồi thì cập nhật `routing-table.md` và `rules.json`.

Đo xem skill có kích hoạt đúng lúc không:

```bash
claude plugin eval ~/Documents/Claude/agent-stack/plugin --runs 1 --max-cost-usd 3 --trust-plugin --no-publish
```

---

## 10. Tùy chỉnh

| Muốn đổi | Sửa ở đâu |
|---|---|
| Ngưỡng cảnh báo hạn mức | Biến môi trường `AGENT_STACK_WARN_5H` (mặc định 90) và `AGENT_STACK_WARN_7D` (mặc định 80) |
| Luật chung cho mọi project | `global/AGENTS.global.md` (dùng chung) và `global/CLAUDE.global.md` (riêng Claude Code, có bảng chọn cho dòng ➡️) |
| Luật router | `plugin/skills/task-router/rules.json`, rồi chạy lại `route.py --eval evals/router-prompts.jsonl` |
| Giọng văn | `plugin/skills/giong-van/style-card.md` và `samples/` |
| Danh sách dấu hiệu văn AI tiếng Việt | `plugin/skills/giong-van/vi-ai-tells.md` |
| Model của worker OpenCode | `opencode/agents/worker.md` |
| Mẫu PLAN và HANDOFF | `plugin/skills/session-keeper/templates/` |

Sửa xong luật router hay skill thì chạy test. Nếu dùng desktop app, nhớ tăng version và cài lại plugin (mục 8).

### Đưa project khác vào nếp

Project nào cũng dùng được agent-stack, chỉ cần có file kế hoạch. Trong project đó, nói "khởi tạo file kế hoạch" để `session-keeper` tạo `.agent/PLAN.md`. Từ phiên sau, hook sẽ nạp §0 tự động.

---

## 11. Khi có trục trặc

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không thấy dòng 📍 / 🧭 | Plugin chưa bật, hoặc thư mục không có git và file kế hoạch | `claude plugin list`; xem `tail -3 state/sessions.jsonl`; mở phiên mới |
| Desktop app chạy code plugin cũ | Bản chép trong cache chưa cập nhật | Tăng `version`, `./install.sh --apply --only plugin`, mở phiên mới |
| Không có cảnh báo hạn mức | Statusline chỉ chạy trong terminal; số liệu quá 30 phút bị bỏ | Mở `claude` trong terminal, hoặc tự theo dõi `/usage` |
| `claude -p` báo "OAuth session expired" | CLI hết phiên đăng nhập | `claude /login` trong terminal |
| Plugin pyright-lsp không chạy | Chưa có `pyright` | `brew install pyright` |
| `oc-worker` báo không kết nối được | Model local chỉ chạy ở mạng nhà, hoặc service OpenCode chưa chạy | Thêm `--standalone`, hoặc để phiên chính tự làm |
| `vet.py scan` thoát mã 3 | Lỗi mạng hoặc đích không tồn tại | Kiểm tra lại `owner/repo@ref`, thử `--no-scanner` |
| §0 lệch với thực tế | Quên lưu trước khi dừng | `/agent-stack:session-keeper tiep-tuc` để so và báo chỗ lệch |

Sau khi bị ngắt giữa chừng, chạy theo thứ tự:

```bash
git -C ~/Documents/Claude/agent-stack status
```

```bash
git -C ~/Documents/Claude/agent-stack log --oneline -5
```

```bash
python3 ~/Documents/Claude/agent-stack/plugin/skills/session-keeper/scripts/receipt.py show
```

rồi đọc §0 của `PLAN.md`. Muốn quay về trạng thái trước khi cài: `./install.sh --rollback --apply`.

---

## 12. Tra cứu nhanh

| Muốn | Nói hoặc gõ |
|---|---|
| Biết làm gì tiếp | "làm gì tiếp?" · `/agent-stack:tien-do` |
| Xem mọi project | `/agent-stack:tien-do all` |
| Lưu tiến độ | "lưu tiến độ" · `/agent-stack:session-keeper luu` |
| Làm tiếp sau khi bị ngắt | `/agent-stack:session-keeper tiep-tuc` |
| Chuyển sang OpenCode | `/agent-stack:session-keeper ban-giao` |
| Project mới chưa có kế hoạch | `/agent-stack:session-keeper khoi-tao` |
| Hỏi nên dùng model nào | `/agent-stack:task-router <việc>` |
| Kiểm tra skill/plugin trước khi cài | `/agent-stack:vet-skill <owner/repo>` |
| Sửa văn cho tự nhiên | "sửa đoạn này cho tự nhiên" · `/agent-stack:giong-van` |
| Tìm thư viện có sẵn | `/agent-stack:reuse-best <nhu cầu>` |
| Review trước commit | "review trước khi commit" (subagent `agent-stack:reviewer`) |
| Chạy test gọn | "giao test-runner chạy test" |

Các file cần biết:

| File | Nội dung |
|---|---|
| `PLAN.md` §0 | Đang ở đâu, việc tiếp theo |
| `KE-HOACH.md` | Thiết kế đầy đủ |
| `INSTALLED.md` | Đã cài gì, gỡ từng mục thế nào |
| `vetted.lock` | Đồ bên thứ ba đã kiểm duyệt và quyết định |
| `routing-table.md` | Bảng chọn model, effort, subagent, skill |
| `BASELINE.md` | Số liệu dùng token nền |
| `state/` | Trạng thái chạy: phiên, hạn mức, biên nhận, nhật ký cài (không vào git) |
