# Hướng dẫn sử dụng agent-stack

Tài liệu này dành cho người dùng hằng ngày. Thiết kế và lý do chọn từng thứ nằm ở `KE-HOACH.md`; tiến độ triển khai ở `PLAN.md` §0; những gì đã cài trên máy ở `INSTALLED.md`.

Mục lục:

1. [agent-stack làm gì](#1-agent-stack-làm-gì)
2. [Kiểm tra đã cài đúng chưa](#2-kiểm-tra-đã-cài-đúng-chưa)
3. [Một ngày làm việc](#3-một-ngày-làm-việc)
4. [Những gì tự chạy](#4-những-gì-tự-chạy)
5. [Tám skill](#5-tám-skill)
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

Ngoài ra có bốn skill phụ: `giong-van` để chỉnh văn cho đúng giọng mình, `reuse-best` để tìm thứ có sẵn trước khi tự viết, `mo-hinh-de-doa` để làm threat model ngắn trước khi code chức năng đụng ranh giới tin cậy, và `chot-viec` để agent tự kiểm trước khi báo xong.

Mọi thứ nằm trong repo này. Các file ngoài repo (`~/.claude/CLAUDE.md`, skill của OpenCode...) chỉ là symlink trỏ về đây, nên sửa trong repo là đủ.

---

## 2. Kiểm tra đã cài đúng chưa

Mở một phiên Claude Code mới trong thư mục có `PLAN.md` (ví dụ chính repo này). Đầu phiên phải thấy:

- dòng **📍** `<tên project>: tiếp theo → <việc đầu tiên trong §0>`;
- dòng **🧭** hồ sơ project, ví dụ `🧭 tài liệu, Python, có test`;
- dòng **🕘** `Lượt cuối (<giờ ngày>): tiếp → <việc tiếp theo>`, khi project đã có lượt cuối do hook Stop ghi (mục 4).

Các dòng này do hook SessionStart in ra. Phần đầy đủ (§0, quyết định còn treo, mốc kiểm tra, trạng thái git, skill và subagent nên dùng) được nạp vào context của Claude, bạn không thấy trực tiếp. Nếu không thấy hai dòng trên:

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

Skill `reuse-best` tìm theo thứ tự: tính năng sẵn có, code trong project, skill đã duyệt, GitHub, rồi bài nghiên cứu. Kết quả là một quyết định dùng lại, điều chỉnh hay tự làm, kèm nguồn, phần còn phải tự làm, và những điểm cần bạn quyết.

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
| Hook SessionStart | Mở phiên, resume, `/clear`, sau compact | Nạp §0, hồ sơ project và lượt cuối (`.agent/LAST-TURN.md`, rút gọn khoảng 500 ký tự) vào context; in dòng 📍, 🧭 và 🕘. Resume lại đúng phiên đã ghi lượt cuối thì không nạp lượt cuối, vì phiên đó còn nguyên hội thoại. Lúc mở phiên mới: báo plugin lệch bản đã kiểm duyệt; với MCP từ xa đã cài, báo kết quả lần kiểm nền trước và mỗi ngày khởi một lần kiểm nền mới (chạy tách phiên, hook không chờ; tắt bằng `AGENT_STACK_NO_BACKGROUND=1`) |
| Hook UserPromptSubmit | Mỗi tin nhắn | Gợi ý `[router]` cho việc trong tin nhắn (bạn thấy dòng `🧭 router: ...` khi có luật khớp; không gợi ý cho tin do hệ thống tạo như báo cáo của subagent); cảnh báo hạn mức khi vượt ngưỡng; lưu yêu cầu gần nhất (đã che khóa, tối đa 1200 ký tự; bỏ qua lệnh `/ ! #` và tin do hệ thống tạo, kể cả báo cáo của subagent quay về phiên chính; sau một tin quá ngắn như "ok" vẫn nhớ yêu cầu đầy đủ trước đó) vào `state/last-request/` cho hook SubagentStart; ghi lúc bắt đầu lượt và dấu của §0 lúc đó vào `state/turns/` cho hook Stop (mọi tin, kể cả tin do hệ thống tạo) |
| Hook PreToolUse | Trước mỗi lệnh Bash và mỗi lần ghi, sửa file (khoảng 20 ms) | Chặn cài plugin, skill, MCP chưa qua `vet-skill` và chưa được duyệt trong `vetted.lock` (nhắc Claude chạy `vet-skill`); hỏi bạn trước khi thêm marketplace lạ; hỏi bạn trước `git checkout` hay `git switch` làm đổi HEAD hoặc ghi đè file khi cây có thay đổi chưa commit; chặn ghi báo cáo `*DIFFERENTIAL_REVIEW*.md` vào chỗ git không bỏ qua; khi router thấy lượt này làm chức năng đụng ranh giới tin cậy mà chưa có threat model, chặn lần sửa file mã nguồn đầu tiên để Claude chạy `mo-hinh-de-doa` trước (chỉ một lần mỗi lượt); khi Claude tạo tag git (`git tag <tên>`, kể cả `-a`, `-s`, `-f`) hay chạy `gh release create`, chặn lần đầu để Claude hỏi bạn đã audit cả repo chưa (Semgrep rồi `claude-security`); bạn trả lời xong thì Claude chạy lại được. Không dùng hộp hỏi vì ở auto mode hộp hỏi của hook từng được duyệt mà bạn không thấy (10/10/2026) |
| Hook SubagentStart | Mỗi khi sinh subagent hoặc chạy skill `context: fork` | Đưa vào đầu context của chúng yêu cầu gần nhất của bạn và 1 đến 2 việc đầu trong §0 (tối đa khoảng 1500 ký tự), vì chúng không thấy hội thoại |
| Hook PreCompact | Trước khi compact | Ghi sự kiện; nhắc nếu §0 đã lâu chưa cập nhật. Không chặn compact |
| Hook Stop | Cuối mỗi lượt trả lời trọn vẹn (không chạy khi bạn bấm dừng giữa chừng) | Ghi `.agent/LAST-TURN.md` trong project: yêu cầu, câu trả lời cuối (đã che khóa, tối đa 1.500 ký tự), việc tiếp theo lấy từ dòng ➡️, file đổi trong lượt, §0 đã cập nhật chưa. File chỉ nằm trên máy: hook thêm nó vào `.git/info/exclude` nên không hiện trong `git status`. Nếu lượt đổi code có mức rủi ro từ vừa trở lên (chấm bằng `risk.py` của `chot-viec`, chỉ trên file lượt này đổi, kể cả file đã commit trong lượt) mà chưa chạy `chot-viec`, hook chặn một lần để Claude chạy `chot-viec`. `chot-viec` lo luôn threat model, review theo mức rủi ro và §0. Còn lại, nếu lượt có đổi file mà §0 vẫn như lúc bắt đầu lượt, hook chặn một lần để Claude cập nhật §0 rồi mới kết thúc. Mỗi lần chặn tốn thêm một lượt model; lần dừng thứ hai không chặn nữa. Thư mục không phải git repo và không có file kế hoạch thì hook không ghi gì |
| Hook SessionEnd | Đóng phiên | Ghi một dòng vào `state/sessions.jsonl`, để `tien-do` gợi ý `claude --resume` |
| Statusline | Liên tục, chỉ trong terminal | Hiện model, effort, ctx, 5h, 7d; ghi `state/limits.json` cho hook cảnh báo |
| Luật chung | Mọi phiên | `~/.claude/CLAUDE.md` trỏ về `global/CLAUDE.global.md`, file này import `global/SHARED.global.md`: trả lời tiếng Việt, đọc §0 trước, không nói "xong" khi chưa kiểm chứng, dòng ➡️ |
| `autoContinueAtUsageLimit` | Khi chạm hạn mức | Claude Code tự làm tiếp khi hạn mức reset |

**Giới hạn của hook PreToolUse.** Hook so chuỗi lệnh với mẫu, nên nó là lớp nhắc cho Claude chứ không phải ranh giới bảo mật. Lệnh viết vòng (qua biến, script trung gian) vẫn lọt; ngược lại, một lệnh chỉ in ra chuỗi giống lệnh cài (ví dụ `echo "claude plugin install ..."`) cũng bị chặn. Ranh giới thật là quyền của Claude Code, việc bạn duyệt, và bước kiểm lệch lúc mở phiên: plugin cài ngoài catalog bị báo là chưa qua vet. Hook không chặn lệnh bạn tự gõ trong terminal.

### Cảnh báo hạn mức

- Hạn mức 5 giờ: nhắc khi đã dùng từ **90%**. Claude sẽ ghi checkpoint vào §0 trước bước dài tiếp theo.
- Hạn mức tuần: nhắc khi đã dùng từ **80%**. Claude sẽ cập nhật §0 ngay.
- Lên 95% thì nhắc thêm một lần. Mỗi ngưỡng chỉ nhắc một lần cho mỗi phiên và mỗi chu kỳ reset.

Số liệu hạn mức do statusline ghi, mà statusline chỉ chạy trong terminal. Vì vậy **desktop app không có cảnh báo hạn mức** trừ khi gần đây bạn có mở `claude` trong terminal (số liệu cũ hơn 30 phút bị bỏ qua). Trong desktop app, tự để ý mức dùng và nói "lưu tiến độ" khi thấy cần.

---

## 5. Tám skill

Mỗi skill có thể gọi bằng lời tự nhiên hoặc gọi thẳng `/agent-stack:<tên> <tham số>`. Script đi kèm cũng chạy tay được; mọi đường dẫn dưới đây tính từ gốc repo.

### 5.1 `tien-do`: tiến độ và việc nên làm tiếp

**Khi nào:** mở lại project, hỏi "làm gì tiếp", "đang dở gì", "status", hoặc muốn xem tổng quan mọi project.

**Gọi:**

- `/agent-stack:tien-do` cho project hiện tại.
- `/agent-stack:tien-do all` cho mọi project trong `~/Documents/Claude/`. Chỉ chạy khi bạn hỏi: không có tác vụ định kỳ hay bản tổng hợp tuần, mỗi project tự theo dõi qua §0 của nó (bạn quyết 03/10/2026).

**Kết quả:** một dòng trạng thái, tối đa 3 việc nên làm, cảnh báo (§0 cũ, file chưa commit lâu, nhánh chưa merge, kiểm tra trượt hoặc đã cũ), và câu `/goal` gợi ý. Việc được xếp theo 5 bậc: chặn đường → dang dở → giai đoạn hiện tại → nợ TODO → bị bỏ quên.

**Chạy tay** (chỉ đọc project, không sửa gì trong project; chỉ ghi một snapshot nhỏ vào `state/` của agent-stack để lần sau báo "Đổi từ lần trước"):

```bash
python3 plugin/skills/tien-do/scripts/collect.py --md
```

```bash
python3 plugin/skills/tien-do/scripts/collect.py --all --md
```

Thêm `--gh` để lấy cả PR và CI trên GitHub (cần mạng, cần `gh` đã đăng nhập). `--brief` in bản rút gọn, `--json` cho máy đọc. Thêm `--no-snapshot` nếu chỉ xem thử và không muốn dời mốc "lần trước" (`--brief` và hook không so, không ghi). Từ lần báo thứ hai cho cùng một project, kết quả có mục "Đổi từ lần trước": commit mới, việc mới xong, việc mới phát sinh, việc biến mất; không có gì đổi thì đúng một dòng.

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
/agent-stack:vet-skill https://mcp.exa.ai/mcp
```

**Skill làm gì:** tải đúng commit vào `.vet-cache/` (không chạy mã của đích), quét dấu hiệu độc hại (tải-rồi-chạy, đọc khóa và token, prompt injection, ký tự ẩn, hook tự chạy), chạy `skill-scanner` và `SkillSpector` (máy quét thứ hai, chỉ đẩy lên REVIEW; cài một lần bằng `python3 plugin/skills/vet-skill/scripts/vet.py spector --setup`), rồi đọc tay từng file đáng ngờ. Skill chạy ở effort high, trong context riêng, và không được sửa file.

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
| `drift [--remote]` | So plugin đã cài với bản đã kiểm (hook SessionStart chạy bản không mạng). `--remote` thêm MCP từ xa: lấy lại định nghĩa tool, so hash đã duyệt, và báo MCP scope user không qua catalog |

Báo cáo đầy đủ nằm trong `vet-reports/`. Sau khi duyệt, chạy `./install.sh --apply` để cài các mục mới (mục 8).

**Bản vá cục bộ** (từ 10/10/2026). Khi plugin đã duyệt có lỗi mà upstream chưa sửa, có thể vá trong agent-stack thay vì chờ. File vá nằm trong `patches/<tên plugin>/`. Mục của plugin trong `vetted.lock` ghi `local_patches`: đường dẫn file vá, sha256 của nó, sha256 từng file sau khi vá, lý do và link upstream. `install.sh` xuất đúng commit đã duyệt vào `vendor/`, kiểm sha256 file vá, áp bằng `git apply`, rồi so tập file bị đổi với lock; lệch chỗ nào thì không chép, không cài. Kiểm lệch chấp nhận file đã vá khi khớp đúng sha256 trong lock. Bản vá chỉ được sửa nội dung file văn bản, tạo file thường hay xóa file; symlink, đổi quyền chạy, đổi tên hay file nhị phân bị từ chối. Vet lại cùng commit thì giữ bản vá; vet commit mới thì bỏ, và `vet.py` cảnh báo trong tóm tắt, báo cáo và lúc duyệt, để bạn kiểm upstream đã sửa chưa; đã sửa thì chỉ cần vet commit đó, chưa thì làm lại bản vá. Hiện có một bản vá: `static-analysis`, lỗi Semgrep bỏ qua file khi gốc repo có file trùng glob (trailofbits/skills#297).

**MCP server từ xa** (từ 10/10/2026). Đích là URL `https://`. Không có mã để đọc, nên `scan` chụp `instructions` và định nghĩa tool (thứ đi vào context của Claude), quét tool poisoning và ký tự ẩn, rồi ghim sha256 vào `vetted.lock`. Kết quả không bao giờ tự PASS, vì câu hỏi và tham số luôn đi tới hãng. Trong `catalog.json`, loại `mcp-remote` được `install.sh` cài bằng `claude mcp add -s user --transport http`, chỉ khi URL khớp bản đã duyệt, không trùng tên server bạn đã có, và định nghĩa tool lấy lại ngay lúc cài còn khớp hash đã duyệt. Claude Code không tự ghim định nghĩa tool, nên hook SessionStart kiểm lệch MCP đã cài tối đa một lần mỗi ngày: nó khởi `vet.py drift --save-state` chạy nền (chỉ gửi `initialize` và `tools/list` tới đúng các server đã duyệt), không chờ, rồi báo ở phiên sau nếu có tool đổi, thêm hay mất. Tắt bằng biến môi trường `AGENT_STACK_NO_BACKGROUND=1`. Kiểm ngay thì chạy `vet.py drift --remote`.

**Phân tích động (tùy chọn).** `scan` không chạy mã của đích. Khi một script đáng ngờ mà đọc tay chưa kết luận được, `vet.py dynamic` chạy MỘT lệnh bạn chọn trong sandbox-runtime của Anthropic: không mạng, ghi chỉ trong bản chép tạm, đọc được phần lớn hệ thống trừ HOME thật, `/Volumes` và keychain, môi trường sạch (không token). HOME của lệnh là một HOME giả rải sẵn 12 file mồi (khóa SSH, token AWS, GitHub, npm... giả) và chặn ghi vào chúng: file nào bị đọc lộ ra qua atime, mồi bị xóa hay thay lộ qua bản chụp trước/sau, nội dung mồi bị chép ra file hay đầu ra cũng bị phát hiện. Tiến trình nền còn sót bị dò và diệt.

```bash
python3 plugin/skills/vet-skill/scripts/vet.py dynamic --setup     # một lần; cần Node; cài vào .cache/srt, bản ghim, --ignore-scripts
python3 plugin/skills/vet-skill/scripts/vet.py dynamic "<khóa>" -- python3 scripts/x.py --help
```

Kết luận **KHÔNG THẤY GÌ** (mã thoát 0; không có nghĩa là an toàn), **CẦN ĐỌC** (1) hoặc **ĐÁNG NGỜ** (2). Giới hạn: chỉ phủ các nhánh code đã chạy; log vi phạm của macOS làm mất khoảng một nửa sự kiện khi tiến trình thoát nhanh (đo được) nên file mồi và dấu rò rỉ mới là bằng chứng mạnh (không tuyệt đối); mã có chủ ý né (nhận ra sandbox, chờ lâu, mã hóa dữ liệu, đọc mồi bằng clonefile `cp -c` (không làm atime nhảy), truy vấn keychain qua dịch vụ hệ thống mà sandbox-runtime cho phép) vẫn qua mặt được; sandbox giảm rủi ro chứ không phải ranh giới tuyệt đối. Không chạy lệnh cài đặt của đích. `--real-home` giữ HOME thật thay cho HOME giả. Cần macOS (Seatbelt) hoặc Linux có bubblewrap (phần mồi qua atime mới kiểm trên macOS).

### 5.5 `giong-van`: chỉnh văn đúng giọng mình

**Khi nào:** "sửa lại đoạn này cho tự nhiên", "đọc như AI viết", "viết lại email này đúng giọng mình", bài luận, blog, cover letter.

**Skill làm gì:**

1. Đo điểm dấu hiệu văn AI trên 1.000 từ bằng `tells.py`.
2. Sửa nội dung trước: câu thổi phồng thay bằng số liệu có sẵn, câu chung chung bỏ đi. Không bịa sự kiện; chỗ thiếu thì hỏi bạn.
3. Sửa câu chữ: mở bài sáo, "không chỉ... mà còn", kết bài nhắc lại, nhịp câu đều đều...
4. Đưa về giọng trong `style-card.md`: xưng hô, độ dài câu, mức trang trọng, từ quen dùng.
5. Đo lại, báo tối đa 5 thay đổi chính và điểm trước/sau.

Văn tiếng Anh cũng dùng `giong-van` (có nhóm dấu hiệu tiếng Anh trong `tells.py`). Skill `humanizer` của vendor đã gỡ ngày 08/10/2026 vì A/B không thấy nó giúp thêm, và xoá khỏi `catalog.json`, `vetted.lock` ngày 09/10/2026; muốn dùng lại thì phải chạy lại `vet-skill`.

**Bài mẫu.** `tells.py` so bản nháp với bài mẫu cùng ngôn ngữ, chọn theo thứ tự:

1. Mẫu riêng của project viết luận: `.agent/giong-van/samples/` trong project đó.
2. Bài bạn tự viết, dùng chung: đặt thẳng vào `plugin/skills/giong-van/samples/` (không đưa vào git).
3. Văn mẫu kinh điển: `plugin/skills/giong-van/samples/kinh-dien/`, 5 bài tiếng Việt và 5 bài tiếng Anh thuộc phạm vi công cộng (danh sách và nguồn trong `README.md` ở đó). Bộ này không phải giọng của bạn, nên script không so cách xưng hô.

**Mỗi project viết luận**, đặt 3–5 bài cùng thể loại vào `.agent/giong-van/samples/` của project, rồi nói trong project đó:

```
/agent-stack:giong-van tao-style-card
```

Claude điền style card riêng của project (`.agent/giong-van/style-card.md`) với ví dụ trích nguyên văn và hỏi bạn duyệt từng mục. Project chưa có mẫu thì skill so với văn kinh điển và nhắc chỗ đặt mẫu.

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

**Cách làm.** Trước khi tìm, skill đọc ràng buộc trong file của project (phiên bản Python hay Node, luật về phụ thuộc, CI, cách chạy production), rồi viết nhu cầu thành tiêu chí bắt buộc và nên có. **Thứ tự tìm:** tính năng sẵn có của công cụ → code trong project → skill đã duyệt trong `vetted.lock` → GitHub → bài nghiên cứu. Chỉ dừng ở một bậc khi có ứng viên đạt mọi tiêu chí bắt buộc, có bằng chứng (`file:dòng` với code trong project, dòng README với thư viện ngoài); "chạy được" hay "có sẵn trong repo" thì chưa đủ.

**Kết quả** gồm tối đa 5 ứng viên chấm theo từng tiêu chí (kèm sao, lần cập nhật, giấy phép; hoặc nơi đăng, năm, trích dẫn), quyết định có nguồn, mục **Phần còn phải làm** (tiêu chí mà lựa chọn chưa đạt) và mục **Cần người dùng quyết** (ràng buộc va nhau, thứ cần duyệt). Quyết định không được thu hẹp nhu cầu của bạn. Claude sẽ đề nghị ghi quyết định vào file kế hoạch để phiên sau khỏi tìm lại.

**Chạy tay** (có gọi mạng tới GitHub, OpenAlex, Semantic Scholar, arXiv; chỉ dùng từ khóa chung, đừng đưa code hay thông tin riêng vào):

```bash
python3 plugin/skills/reuse-best/scripts/scout.py github "pdf ocr vietnamese" --language python
```

```bash
python3 plugin/skills/reuse-best/scripts/scout.py papers "vietnamese ocr" --since 2024
```

```bash
python3 plugin/skills/reuse-best/scripts/scout.py repo lycheeverse/lychee tcort/markdown-link-check --find "fragment, retry, ignore"
```

`github` có thêm `--limit`, `--sort {both,best-match,stars,updated}`, `--json`. GitHub đòi mọi từ trong câu tìm đều khớp, nên câu ra rỗng được nới dần: bỏ từ chung chung và tên ngôn ngữ, rồi bỏ từ cuối. Tốt nhất dùng tên khái niệm ngắn (`toml parser`) và để tên ngôn ngữ ở `--language`. `repo` kiểm tối đa 5 repo một lần: lần phát hành (hay tag) gần nhất, issue đang mở, giấy phép và những dòng README nhắc tới từng từ khóa của `--find`, kèm số dòng; `--max-lines` in thêm dòng khớp, `--readme-chars` in đầu README. Kết quả nào cũng mở đầu bằng một dòng tổng và kết thúc bằng dòng "Tiếp:" là lệnh nên chạy tiếp; chạy `scout.py` không tham số thì in cách dùng.

Thứ tìm được là skill, plugin hay MCP thì vẫn phải qua `vet-skill`. Repo không có giấy phép thì chỉ học ý tưởng, không chép code.

### 5.7 `chot-viec`: cổng kiểm trước khi báo xong

**Khi nào:** vừa xong một tính năng, bản sửa lỗi hay refactor; "chốt việc", "kiểm lại trước khi commit", "sẵn sàng commit chưa". Câu hỏi tiến độ kiểu "xong chưa" không kích hoạt nó. Luật chung dặn Claude tự chạy nó sau mỗi thay đổi không tầm thường, và hook Stop buộc chạy nó khi lượt đổi code có mức rủi ro từ vừa trở lên mà Claude quên (xem mục 4).

**Gọi:** `/agent-stack:chot-viec` (thêm `--base main` để so với nhánh khác thay vì HEAD).

**Làm gì:** nêu lại ý định và tiêu chí xong; tách file thuộc việc này khỏi file người khác đổi; chấm mức rủi ro của diff; chạy mốc kiểm tra qua `receipt.py` và tái hiện thay đổi đúng như bạn sẽ dùng; review ở context mới (mức thấp: tự đọc diff; vừa: `agent-stack:reviewer` chạy sonnet; cao: reviewer chạy opus · high); tự sửa lỗi máy móc, còn lỗi đụng tới ý định thì hỏi bạn; rà README và tài liệu; báo cáo ngắn kèm phần bạn nên đọc. Chỉ commit khi bạn hoặc luật project yêu cầu, không bao giờ push.

**Chạy tay** phần chấm rủi ro (chỉ đọc):

```bash
python3 plugin/skills/chot-viec/scripts/risk.py
```

Điểm cộng khi đụng phần nhạy cảm (xác thực, secret, mã hóa, thanh toán, quyền, sandbox), schema, hook, cài đặt, phụ thuộc, file chỉ dẫn cho agent; khi dòng thêm vào có dấu hiệu secret, chạy lệnh qua shell, xóa file, tải rồi chạy mã, SQL ghép chuỗi; khi thay đổi lớn, đổi code mà không đổi test, hoặc bớt test. Đây là gợi ý thô để quyết review sâu tới đâu, không thay review.

Ý tưởng lấy từ pipeline `no-mistakes` của Kun Chen (video "L8 Principal's Agentic Engineering Workflow", MIT). Phần tự push, mở PR và trông CI không lấy.

`risk.py` còn liệt kê **ranh giới tin cậy bị đụng** trong file mã nguồn: input từ bên ngoài (route, `request.files`…), xác thực, gọi ra ngoài (`requests`, `fetch`…), dữ liệu nhạy cảm, dependency mới, chạy lệnh hay đường dẫn từ input. Đụng ranh giới thì ít nhất mức vừa, và `chot-viec` cần một mục trong `.agent/threat-model.md` (xem 5.8) để đưa từng chốt chặn cho reviewer kiểm. Mức cao và đụng phần bảo mật thì chạy thêm `differential-review` (Trail of Bits) trên diff rồi để reviewer lọc dương tính giả.

### 5.8 `mo-hinh-de-doa`: threat model trước khi code

**Khi nào:** sắp làm chức năng đụng ranh giới tin cậy: nhận input từ bên ngoài, xác thực hay phân quyền, gọi dịch vụ ngoài, lưu hay truyền dữ liệu nhạy cảm, thêm dependency, chạy lệnh. Router gợi ý nó (luật `feature-boundary`) khi bạn nhờ làm tính năng đăng nhập, upload, webhook, thanh toán…; luật chung dặn chạy trước khi code; nếu Claude vẫn bắt đầu sửa file mã nguồn mà chưa có threat model, hook PreToolUse chặn lần sửa đầu tiên và nhắc chạy skill này. Sửa giao diện, sửa chữ, refactor không đổi luồng dữ liệu thì bỏ qua.

**Gọi:** `/agent-stack:mo-hinh-de-doa` hoặc nói "threat model chức năng này".

**Làm gì:** đọc ít (chỉ phần code sắp chạm và chốt chặn có sẵn), vẽ luồng 3–6 dòng, hỏi sáu câu STRIDE cho mỗi ranh giới, giữ tối đa 5 mối đe dọa có khả năng cao nhất, mỗi mối kèm actor, surface, asset và chốt chặn phải có (kiểm được trong code hay test). Ghi vào `.agent/threat-model.md` của project với ID `TM-n` và trạng thái `cần làm`, `đã có` hay `chấp nhận rủi ro`. Project có skill threat model riêng (ví dụ `security-whitebox`, nơi bạn tự viết skill khi học) thì dùng skill đó.

**Ba bước bảo mật theo mức rủi ro:** threat model trước khi code (skill này) → review từng thay đổi theo mức rủi ro (`chot-viec`) → audit cả repo một lần trước phát hành: quét Semgrep (`static-analysis`) trước, rồi `claude-security` tìm phần Semgrep bỏ sót; cả hai cài toàn cục từ 10/10/2026. Bước 1 và 2 tự chạy: luật chung và router bảo Claude làm, khi router thấy việc đụng ranh giới tin cậy mà chưa có threat model thì hook PreToolUse chặn lần sửa mã nguồn đầu tiên, hook Stop chặn khi lượt đổi code rủi ro từ vừa mà chưa chạy `chot-viec`. Bước 3 chỉ chạy khi bạn yêu cầu ("audit cả repo", `/static-analysis:semgrep`, `/claude-security`), nhưng có nhắc: khi Claude tạo tag git hay chạy `gh release create`, hook PreToolUse chặn lần đầu để Claude hỏi bạn đã audit chưa, bạn trả lời xong thì Claude chạy lại được (từ 10/10/2026); sau `git push` hay khi tạo PR, `claude-security` in lời gợi ý quét. Tag bạn tự tạo trong terminal thì không có nhắc, vì hook chỉ thấy lệnh Claude chạy. Không chạy đủ cả ba cho mọi chức năng: phần lớn chi phí của một lần review là cố định, nên chạy cho cả chức năng sửa giao diện thì tốn mà không tìm được gì.

Ý lấy từ skill `threat-model` của `anthropics/defending-code-reference-harness` (Apache-2.0): phép thử "sửa một dòng là hết thì là lỗi, không phải mối đe dọa" và tên cột của bảng. Bản đó mô hình hóa cả codebase bằng nhiều subagent; bản này gọn cho từng chức năng.

### 5.9 `goi-mcp`: gọi MCP từ xa theo việc, không cài

**Khi nào:** hỏi về một repo GitHub công khai (DeepWiki), hay cần tìm web sâu hơn khi Exa chưa đủ (Parallel). Claude tự gọi khi việc hợp; bạn cũng gọi được bằng `/agent-stack:goi-mcp <câu hỏi>`.

**Vì sao không cài thẳng như Exa:** server cài vào Claude Code thì `instructions` của nó nạp vào mọi phiên (DeepWiki 3.458 ký tự, phần lớn nói về tool không dùng được; Parallel 1.587). Qua skill thì phiên thường chỉ tốn một dòng mô tả.

**Script làm gì:** `plugin/skills/goi-mcp/scripts/call.py <server> <tool> --args '<json>'`. Chỉ gọi server có trong `catalog.json` với scope `skill` và đã duyệt trong `vetted.lock`. Mỗi lần gọi, lấy định nghĩa tool trong cùng phiên và so sha256 với bản đã duyệt; lệch thì không gọi. Từ chối tham số trông như khóa hay token. Bỏ tham số theo dõi (`session_id`, `model_name` của Parallel). In kết quả giữa hai dòng mốc có mã ngẫu nhiên mỗi lần gọi, đã làm sạch ký tự ẩn; đó là dữ liệu, không phải chỉ dẫn. `call.py list` xem server và tool gọi được.

---

## 6. Subagent

Subagent chạy trong context riêng và chỉ trả về kết quả gọn, nên context chính không bị đầy bởi log dài. Gọi bằng lời ("giao cho test-runner chạy test") hoặc để Claude tự chọn theo dòng ➡️. Tên đầy đủ có tiền tố `agent-stack:`.

| Subagent | Model | Quyền | Dùng khi |
|---|---|---|---|
| `agent-stack:reviewer` | opus · high | Chỉ đọc | Review code và bảo mật trước commit hoặc PR |
| `agent-stack:researcher` | sonnet · medium | Không sửa file | Tra docs, so sánh công cụ, kiểm chứng một nhận định; trả về có dẫn nguồn |
| `agent-stack:test-runner` | Haiku 5.5 · low | Chỉ đọc, chạy lệnh | Chạy test, lint, build và chỉ trả về phần lỗi |
| `agent-stack:explore-lite` | Haiku 5.5 · low | Chỉ đọc | Tìm vị trí code, nơi dùng một hàm, cấu hình. Rẻ hơn `Explore` nhưng không suy luận sâu |
| `agent-stack:oc-worker` | Haiku 5.5 · low | Chạy lệnh | Giao việc cơ học cho OpenCode chạy model local `tuf/*` trong mạng nhà (mục 7); không tự rơi về model từ xa |

Subagent vẫn tính vào hạn mức. Theo `BASELINE.md`, khoảng 70% chi phí đến từ subagent và workflow, nên đừng chia nhỏ việc mà một model làm liền mạch tốt hơn.

**Subagent không thấy hội thoại.** Subagent và skill chạy `context: fork` (`vet-skill`, `reuse-best`, `tien-do`) có context riêng: không thấy yêu cầu của bạn, các tin nhắn trước hay task của phiên, chỉ thấy prompt mà Claude giao cho chúng. Hai lớp bù lại:

- **Hook SubagentStart** (mục 4) đưa yêu cầu gần nhất của bạn và việc tiếp theo trong §0 vào đầu context của chúng, như dữ liệu bối cảnh chứ không phải chỉ dẫn mới. Hook chỉ có hiệu lực sau khi plugin được cập nhật và bạn mở phiên mới (mục 8). Chỉ lấy yêu cầu của đúng phiên này, không đoán theo thư mục. Đã kiểm chạy thật ngày 03/10/2026 bằng `claude -p`: hai subagent liên tiếp trong một phiên đều nhận đúng yêu cầu của người dùng. Kiểm lại bất cứ lúc nào bằng `grep subagent-start state/events.jsonl | tail -3` (dòng đạt có `"request": true`).
- **Prompt giao việc phải tự đủ.** Luật chung dặn Claude ghi rõ yêu cầu gốc, mục tiêu, ràng buộc, file liên quan, tiêu chí xong và định dạng trả về. Mỗi agent và skill đều ghi nó cần gì; thiếu thì nó nói rõ phần thiếu ở dòng đầu báo cáo thay vì đoán.

---

## 7. Dùng với OpenCode

OpenCode đọc cùng bộ luật và skill, qua symlink:

- `~/.config/opencode/AGENTS.md` → `global/AGENTS.global.md`, file ghép từ luật chung `SHARED.global.md` và phần riêng OpenCode `OPENCODE.global.md` (OpenCode không hiểu `@import`)
- `~/.config/opencode/skills/<tên>` → skill trong `plugin/skills/` (và `vendor/skills/` nếu bạn cài lại skill vendor)
- `~/.config/opencode/agents/worker.md` → `opencode/agents/worker.md`

OpenCode không có hook, nên đầu phiên Claude (hoặc model trong OpenCode) phải tự chạy:

```bash
python3 ~/Documents/Claude/agent-stack/plugin/skills/task-router/scripts/route.py --session .
```

Lệnh này in hồ sơ project, gợi ý skill và lượt cuối (`.agent/LAST-TURN.md`) do hook Stop của Claude Code ghi. Phần riêng OpenCode của luật (`OPENCODE.global.md`) đã dặn việc này, nên thường không cần nhắc. OpenCode không có hook Stop, nên lượt làm trong OpenCode không được ghi lại.

### Agent `worker`

`worker` chạy model local `tuf/coder-fast` (miễn phí, chỉ chạy được khi ở mạng nhà), được sửa file nhưng gần như không được chạy lệnh ngoài vài lệnh kiểm tra như `git diff`. Dùng cho việc cơ học: đổi tên hàng loạt, định dạng, boilerplate, dịch tài liệu, test đơn giản.

Từ Claude Code, giao qua subagent `agent-stack:oc-worker`. Nó kiểm tra `git status` sạch, gọi worker, đọc diff, chạy test; hỏng thì thử lại một lần với `tuf/gpt-oss-medium`, vẫn hỏng thì bỏ thay đổi và trả việc về phiên chính. Gọi tay:

```bash
opencode run --agent worker -m tuf/coder-fast --format json --auto "<việc + tiêu chí xong + file được phép sửa>"
```

Thêm `--standalone` nếu báo lỗi không kết nối được service.

### Quyền riêng tư với model từ xa

Model chạy qua OpenRouter hay model miễn phí của OpenCode nhận toàn bộ prompt và nội dung file. Riêng `opencode/muse-spark-1.3-contributor-free` (đang là model mặc định trong `~/.config/opencode/opencode.jsonc` của máy này) đổi giá rẻ lấy quyền dùng prompt và kết quả để huấn luyện model của Meta, theo trang OpenCode Zen (02/10/2026). Vì vậy luật chung và `oc-worker` quy định: không giao file chứa secret, dữ liệu cá nhân hay mã riêng tư cho model từ xa; nếu model local `tuf` không dùng được (ngoài mạng nhà), dừng và hỏi bạn thay vì tự rơi về model từ xa. Muốn đổi model mặc định của OpenCode thì sửa `opencode.jsonc` (repo này không tự sửa).

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
| `tools` | Công cụ dòng lệnh mà mục đã duyệt cần (khóa `brew` trong `catalog.json`, hiện là `semgrep` cho `static-analysis`), cài bằng Homebrew; gỡ được bằng `--rollback` |
| `catalog` | Plugin chính thức, plugin và skill bên thứ ba đã duyệt; bên thứ ba được chép đúng commit đã kiểm vào `vendor/` (không theo HEAD), mục scope project chỉ được chép rồi in lệnh cài trong project |
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
python3 plugin/skills/session-keeper/scripts/receipt.py run -- python3 -m unittest discover -s tests -t .
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

Test chạy bằng `python3` (3.11 của pyenv), cũng là Python mà app dùng để gọi hook. Không chạy trên `/usr/bin/python3` (3.9 của hệ thống macOS).

### Eval chọn cấu hình

`evals/` có 12 việc để tìm cấu hình rẻ nhất mà vẫn giữ chất lượng. Cấu hình định nghĩa trong `evals/configs.json`: A (sonnet · medium), B (sonnet · high), C (opus · medium), D (opus · low), E (A + plugin), H (alias `haiku`, tức Haiku 4.5, chỉ đo trần dưới), H5L, H5M, HM (Haiku 5.5 · low, medium, max), S (A + superpowers chép ở `vendor/plugins/superpowers`; A/B 10/10/2026: đạt 20/20 như A, tốn hơn 14%, nên không bật toàn cục, xem `routing-table.md` mục 8).

```bash
python3 evals/run_eval.py --configs A,C,D --repeats 2
```

Không có `--yes` thì chỉ in kế hoạch và chi phí ước tính. Thêm `--yes` mới chạy thật và tốn hạn mức (lần chạy trên khoảng 15 USD theo giá niêm yết). Nên đặt trần: `--max-total-usd 20 --cap-usd 1`. Model làm việc trong thư mục tạm ngoài repo, để không đọc được grader hay lời giải. Các tùy chọn không gọi model: `--report <file.jsonl>` tổng hợp kết quả đã có, `--regrade <file.jsonl>` chấm lại bằng grader mới.

Có số liệu rồi thì cập nhật `routing-table.md` và `rules.json`.

Đo lợi ích của một plugin bên thứ ba: thêm vào `evals/configs.json` một cấu hình có `"plugins": ["<thư mục trong repo>"]`, rồi so với A trên các việc plugin đó nhắm tới. Cấu hình có plugin chạy với `stream-json`, nên bảng kết quả có thêm dòng "gọi skill ở n/m lượt". Skill có mà không được gọi thì chênh lệch chỉ là nhiễu. Không hơn A thì đừng bật skill đó: skill tốn token mỗi lần nạp mô tả, và có skill làm kết quả tệ đi.

**Skill vendor, kết quả 07/10/2026:** cấu hình V (A + 5 skill vendor) và A cùng đạt 20/20 trên 10 việc (gồm 3 việc debug, diff rất khó), V không gọi skill lượt nào. Ngày 08/10/2026 đã gỡ hẳn: plugin và marketplace `agent-stack-vendor-local`, 5 symlink OpenCode, thư mục `vendor/` và cấu hình V. Ngày 09/10/2026 xoá luôn khỏi `catalog.json` và `vetted.lock`; muốn dùng lại thì chạy lại `vet-skill`. Chi tiết ở `routing-table.md` mục 8.

**Kết quả lần chạy ngày 02/10/2026** (72 lượt, khoảng 7,5 USD giá niêm yết): A, C và D đều đạt 24/24; A rẻ nhất (0,063 USD mỗi việc, so với 0,128 và 0,121). Vì cả ba đều đạt hết, bộ việc này chưa phân biệt được các cấu hình: nó chỉ cho thấy sonnet · medium đủ cho việc nhỏ có tín hiệu kiểm tra rõ. Muốn đo debug khó hay review diff thật, cần thêm việc khó hơn vào `evals/tasks/`. Chi tiết và khuyến nghị chính thức của Anthropic nằm ở `routing-table.md`.

Đo xem skill có kích hoạt đúng lúc không:

```bash
claude plugin eval ~/Documents/Claude/agent-stack/plugin --runs 1 --max-cost-usd 3 --trust-plugin --no-publish
```

Trần 3 USD chỉ đủ khoảng 11 trên 13 ca; chạy nốt phần còn lại bằng `--case <tên>`. Lần ngày 02/10/2026: 10/10 ca cần kích hoạt đều gọi đúng skill, 3/3 ca không được kích hoạt đều sạch. Cột Δ chỉ cho biết skill chạy khi có plugin, chưa đo chất lượng việc skill làm.

---

## 10. Tùy chỉnh

| Muốn đổi | Sửa ở đâu |
|---|---|
| Ngưỡng cảnh báo hạn mức | Biến môi trường `AGENT_STACK_WARN_5H` (mặc định 90) và `AGENT_STACK_WARN_7D` (mặc định 80) |
| Luật chung cho mọi project | `global/SHARED.global.md` (dùng chung), `global/CLAUDE.global.md` (riêng Claude Code, có bảng chọn cho dòng ➡️), `global/OPENCODE.global.md` (riêng OpenCode). Sửa SHARED hay OPENCODE xong thì chạy `python3 tools/build_rules.py` để ghép lại `global/AGENTS.global.md` cho OpenCode; quên thì test báo |
| Luật router | `plugin/skills/task-router/rules.json`, rồi chạy lại `route.py --eval evals/router-prompts.jsonl` |
| Giọng văn | `plugin/skills/giong-van/style-card.md` và `samples/` (chung); `.agent/giong-van/` trong từng project viết luận |
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
| Plugin pyright-lsp không chạy trong project đã bật | Chưa có `pyright` | `brew install pyright` |
| Muốn bật LSP cho một project | LSP chỉ bật theo project; hồ sơ project lúc mở phiên đề xuất ở project lớn | Trong project đó: `claude plugin enable pyright-lsp@claude-plugins-official --scope local` (chỉ còn LSP cho Python; `clangd-lsp` cho C/C++ đã xoá ngày 10/10/2026) |
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
| Threat model trước khi code | "threat model chức năng này" · `/agent-stack:mo-hinh-de-doa` |
| Kiểm trước khi báo xong hay commit | "chốt việc", "kiểm lại trước khi commit" · `/agent-stack:chot-viec` |
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
