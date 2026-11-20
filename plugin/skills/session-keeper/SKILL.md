---
name: session-keeper
description: Lưu và khôi phục trạng thái công việc, để không mất tiến độ khi hết hạn mức, crash, compact hoặc khi đổi sang phiên khác. Cập nhật mục §0 "Đang ở đâu, việc tiếp theo" trong PLAN.md, viết .agent/HANDOFF.md khi bàn giao, và chạy các bước kiểm tra sau khi bị ngắt. Có khuôn kế hoạch phiên và bước spec theo lát cho việc từ mức vừa (spec "khi … thì …", test viết trước ở context mới rồi khóa). Dùng khi người dùng nói lưu tiến độ, dừng phiên, sắp hết limit, bàn giao, handoff, làm tiếp việc dở, resume, lập kế hoạch phiên, viết spec, hoặc khi project chưa có file kế hoạch.
when_to_use: lưu lại, checkpoint, save progress, hết hạn mức, usage limit, bàn giao phiên, mở lại phiên, tiếp tục từ hôm qua, tạo PLAN.md, spec theo lát, viết spec, khi … thì …, test viết trước, khóa đỏ
argument-hint: "[luu | tiep-tuc | ban-giao | khoi-tao | ke-hoach | spec]"
---

# Giữ trạng thái công việc trên đĩa

Nguyên tắc: **trạng thái nằm trên đĩa, không nằm trong context.** Nguồn sự thật là mục §0 của file kế hoạch, thường là `PLAN.md` ở gốc project hoặc `.agent/PLAN.md`. Hook SessionStart của agent-stack tự nạp lại §0 mỗi khi mở phiên, resume, `/clear` hoặc sau compact.

Ngoài §0, hook của agent-stack tự ghi `.agent/LAST-TURN.md` của thư mục làm việc: lúc bạn gửi tin (trạng thái đang chạy), khi lượt xong (yêu cầu, câu trả lời cuối đã che khóa, việc tiếp theo, file đổi), và khi lỗi API kết thúc lượt (hook StopFailure). Thư mục không phải project cũng được ghi; thư mục chung như home hay thư mục gom nhiều project thì ghi vào `state/last-turn/`. Hook SessionStart nạp bản ghi vào phiên mới, kể cả khi lượt cuối chưa xong (kèm file đã đổi từ lúc đó) và một dòng cho mỗi phiên khác trong 24 giờ; bản không mang chữ ký HMAC của máy này thì bỏ qua. Đây là bản máy ghi, không thay §0: đừng sửa tay, đừng chép nó vào §0. Khi lượt có đổi file mà §0 chưa đổi, hook Stop nhờ cập nhật §0 trước khi kết thúc lượt; lúc đó chỉ sửa §0 cho khớp việc vừa làm, ngắn gọn, rồi dừng.

Script hỗ trợ: `python3 "${CLAUDE_SKILL_DIR}/scripts/state.py" <lệnh> --project <thư mục>`. Chạy mốc kiểm tra qua `python3 "${CLAUDE_SKILL_DIR}/scripts/receipt.py" run --project <thư mục> -- <lệnh>`: script ghi biên nhận gắn với nội dung code, để phiên sau biết kết quả còn đúng hay đã cũ; sửa tài liệu sau bước kiểm (§0, README) không làm cũ (`receipt.py show` để xem; `forget <tên>` xoá một biên nhận, `prune` xoá biên nhận trượt của test đã bị xoá khỏi project; `fails-before`, `lock`, `locks`, `unlock`: bước 4 của done-gate). Nếu biến `${CLAUDE_SKILL_DIR}` không được thay bằng đường dẫn thật (ví dụ khi đọc thẳng file này ngoài plugin), dùng `~/Documents/Claude/agent-stack/plugin/skills/session-keeper/scripts/state.py` (và `receipt.py`, `watch_change.py` cùng thư mục `scripts/`).

Bộ test thu hẹp: đang làm thì chạy `python3 "${CLAUDE_SKILL_DIR}/scripts/narrow.py" run` (cùng thư mục với `receipt.py`) thay cả bộ (chỉ test chạm file vừa đổi; `narrow.py status` báo vết cũ hay chưa có thì `narrow.py record` trước). Gọi trực tiếp, không bọc trong `sh -c` hay `make`. Biên nhận thu hẹp (`scope: narrow`) không thay biên nhận cả bộ: cả bộ chạy đúng một lần trước commit qua `receipt.py run`, mutation một lần lúc cuối (done-gate). Mốc là `python3 -m unittest discover -s tests -t .` thì trước commit chạy được `receipt.py run -- python3 <narrow.py> full`: cùng tập test, mỗi module một tiến trình, mảnh trượt chạy lại một lần; không bắt lỗi rò trạng thái giữa module.

Máy xa (TUF): `receipt.py run --host <tên> -- <lệnh>` chạy lệnh qua SSH trên máy có trong `state/remote-hosts.json` của agent-stack (ngoài git; tên máy không bao giờ lấy từ file trong repo), trên đúng HEAD cộng thay đổi chưa commit của file đang theo dõi; file chưa track (không bị ignore) thì từ chối. Dùng để chạy test dài hay song song nhiều hơn máy này mà không chiếm máy. Biên nhận `scope: remote` chỉ để tham khảo: không thay biên nhận trên máy này (hook Stop không tính, kể cả `narrow.py full`), vì máy xa khác hệ điều hành (TUF trượt sẵn 8 test do khác Linux/macOS). Mã 2: từ chối trước khi gọi SSH; 255: lỗi SSH, mạng; 124: quá giờ.

Chế độ lấy theo `$ARGUMENTS`. Nếu không có, suy ra từ lời người dùng.

## `luu`: lưu tiến độ (mặc định)

1. Chạy `state.py show` để xem §0 hiện tại và trạng thái git.
2. Sửa mục §0 trong file kế hoạch, giữ nguyên định dạng. Viết cụ thể đến mức người khác làm tiếp được mà không phải hỏi:
   - **Cập nhật** = ngày hôm nay, dạng `*Cập nhật DD/MM/YYYY.*`
   - **Xong:** kết quả kèm bằng chứng (commit, kết quả test), vài dòng mỗi mục, ngày ở dòng đầu (`Xong (29/10/2026): …`) để `state.py trim` biết mục nào mới nhất; chi tiết để ở commit.
   - **Đang dở:** việc gì, ở file nào, nhánh nào, còn thiếu gì.
   - **Tiêu chí xong** (việc, ngày, nguồn: lời bạn, bạn xác nhận hay agent tự ghi): 2–4 tiêu chí của việc đang làm, ghi trước khi code, mỗi tiêu chí là một lệnh phải đạt hay một cặp đầu vào và đầu ra. Skill done-gate so kết quả với chính các tiêu chí này; xong việc thì chuyển vào mục Xong (đạt n/n) và xóa dòng này. Lấy nguyên lời người dùng khi có. Việc từ mức vừa mà tiêu chí do agent tự suy thì hỏi người dùng xác nhận rồi mới code. Đổi tiêu chí giữa chừng thì hỏi; không sửa tiêu chí cho khớp cái đã làm.
   - **Việc tiếp theo, theo thứ tự:** danh sách đánh số; mỗi bước bắt đầu bằng một động từ.
   - **Quyết định còn treo:** điều cần người dùng chốt.
   - **Mốc kiểm tra:** lệnh và kết quả mong đợi, đúng với lần chạy gần nhất. Chạy lệnh đó qua `receipt.py run` để có biên nhận.
3. §0 dài hơn khoảng 12K ký tự (progress và hook SessionStart cảnh báo) thì chạy `state.py trim`.
4. Cho người dùng xem diff của §0. Chỉ commit khi project cho phép (xem CLAUDE.md của project) hoặc khi người dùng yêu cầu.

## `tiep-tuc`: làm tiếp sau khi bị ngắt

1. Chạy `state.py show`.
2. Làm các bước trong "Sau khi bị ngắt". Nếu không có, chạy `git status` và `receipt.py show`, rồi chạy lại mốc kiểm tra qua `receipt.py run` nếu biên nhận đã cũ hoặc chưa có.
3. So kết quả với §0. Báo ngay nếu có gì lệch: test khác mốc, file chưa commit lạ, hay §0 cũ hơn commit gần nhất.
4. Đề xuất bước tiếp theo đầu tiên. Đợi người dùng đồng ý nếu bước đó sửa nhiều file.

## `ban-giao`: bàn giao sang phiên hoặc công cụ khác

1. Chạy `luu` trước.
2. Chạy `state.py handoff`. Script tạo `.agent/HANDOFF.md`, điền sẵn §0 và trạng thái git.
3. Điền các chỗ `<!-- điền -->`: mục tiêu, các quyết định đã chốt kèm lý do. Bản vá (`.patch`) xuất cho phiên khác đặt trong `.agent/` (thư mục con ban-giao): ở đó nó không bị tính là code, nên không làm cũ biên nhận hay đội mức rủi ro.
4. Nói cho người dùng cách làm tiếp: mở phiên mới trong thư mục project (hook tự nạp file); công cụ không có hook thì nhắn "Đọc .agent/HANDOFF.md rồi làm tiếp bước 1".

## `khoi-tao`: project chưa có file kế hoạch

1. Chạy `state.py init`. Script tạo `.agent/PLAN.md` từ mẫu và từ chối nếu project đã có file kế hoạch.
2. Điền §0 dựa trên những gì đã biết trong cuộc trò chuyện. Hỏi người dùng nếu chưa rõ mục tiêu hay mốc kiểm tra.

## `ke-hoach`: khuôn kế hoạch phiên (dài một màn hình)

Dùng khi phiên làm một việc cỡ vừa trở lên (một giai đoạn, một tính năng, một lỗi khó); câu hỏi nhanh thì không. Dòng 🧭 lúc mở phiên gợi ý vào plan mode (Shift+Tab hay `/plan`) khi §0 có việc tiếp theo. Plan mode không cho sửa file tới khi người dùng duyệt, nên duyệt kế hoạch là duyệt tiêu chí xong trước khi code. Model lập kế hoạch là model của phiên (phiên thiết kế dùng Fable high: dừng ở spec, test khóa và §0, code làm ở một phiên Opus mới); không dùng `opusplan`. Khuôn, mỗi mục một đề mục `##`, tên đúng như dưới (hook ExitPlanMode tìm theo tên):

1. `## Việc của phiên`: 1–3 câu, kèm điều không làm nếu dễ nhầm.
2. `## Tiêu chí xong`: 2–4 mục đánh số, mỗi mục một lệnh phải đạt hay một cặp đầu vào và đầu ra. Lấy từ §0 hay đề xuất; tiêu chí do agent đề xuất thì ghi "(đề xuất, chờ bạn xác nhận)". Duyệt xong, hook ghi mục này vào §0 nếu §0 chưa có tiêu chí.
3. `## Các bước`: bảng việc, model · effort, subagent cho từng bước (theo task-router; không đổi model giữa phiên, bước cần model khác thì giao subagent).
4. `## Lệnh kiểm chứng`: các lệnh để trong khối mã, chạy qua `receipt.py run`.
5. `## Ngoài phạm vi`: việc tách ra phiên khác hay để sau.
6. `## Điểm dừng`: khi nào cập nhật §0, chạy done-gate, commit; chỗ nào phải hỏi người dùng.
7. `## Spec` (việc từ mức vừa): các dòng `- Sn: Khi … thì …` của lát sắp làm (mục `spec` dưới). Duyệt kế hoạch là duyệt các dòng này: hook ghi chúng vào sổ duyệt, nguồn "kế hoạch".

Kế hoạch đủ tiêu chí và lệnh kiểm thì viết ngay; thiếu hai mục đó thì hook nhắc ngay sau khi duyệt. Done-gate cuối phiên so kết quả với đúng các tiêu chí này.

## `spec`: spec theo lát (việc từ mức vừa)

Spec là vài câu nói phần mềm phải làm gì, dạng "khi … thì …", chỉ cho phần sắp làm (một lát), không cho cả hệ thống. Test viết từ spec trước khi có code, ở context mới, rồi bị khóa để người viết code không sửa được. Mức thấp (sửa chữ, tài liệu, thay đổi nhỏ) bỏ qua mục này. Script: `python3 "${CLAUDE_SKILL_DIR}/scripts/spec.py" check|page|status --project <thư mục>` (biến chưa được thay thì dùng `~/Documents/Claude/agent-stack/plugin/skills/session-keeper/scripts/spec.py`).

1. **Viết spec** vào `.agent/spec/<slug>.txt` (slug kebab-case): 2–8 dòng `Sn: Khi|Nếu|Trong khi … thì …`, số thứ tự tăng dần, dòng `#` là chú thích. Mỗi dòng một hành vi người dùng thấy, kiểm được bằng test, kể cả nhánh bị từ chối. Chỉ ghi thêm ở cuối: sửa hay xóa dòng có sẵn là nới, phải người dùng duyệt.
2. **Duyệt**: mức vừa thì đặt các dòng vào mục `## Spec` của kế hoạch phiên; người dùng duyệt kế hoạch là hook ghi bản duyệt, rồi chép nguyên chữ (cả số thứ tự) vào file spec. Mức cao: sau khi viết file, chạy `spec.py page <slug>`, đưa trang `.agent/trang/<slug>-spec.html` cho người dùng (`SendUserFile`, `display: "render"`); nói nguyên văn câu `duyệt spec <mã>` (dòng `spec.py page` in ra; nhiều lát thì `duyệt spec <mã1> <mã2>`) và dặn gửi thành một tin riêng khi agent đã dừng lượt, rồi dừng lượt: tin gửi giữa lượt có thể không qua hook, câu thêm chữ khác không được ghi. Hook `prompt_submit` ghi bản duyệt; câu gần đúng thì hook báo câu cần gõ, không ghi. Không tự ghi sổ duyệt (`state/spec-approvals.json`): hook chặn, và bánh cóc chỉ tính bản duyệt có dấu khớp từng dòng.
3. **Test viết trước, ở context mới**: giao subagent `agent-stack:test-writer` với model theo dòng "Người viết test đề nghị" của `risk.py` (mức vừa: sonnet · medium; mức cao: khác họ người viết code, Opus viết thì sonnet · high, Fable, Sonnet hay Haiku viết thì opus · high). Prompt tự đủ: các dòng spec kèm slug, giao diện đã chốt (lệnh, hàm, đầu vào, đầu ra, mã thoát), file test được viết, lệnh chạy test. Mỗi test mang dấu `spec:<slug>#Sn`; test phải trượt vì tính năng chưa có, không vì lỗi trong chính test.
4. **Khóa đỏ, trước khi viết code**: `python3 <receipt.py> lock --red --level <vua|cao> --tests <file test…> -- <lệnh test>`. Mã 1: test đạt ngay trên code hiện tại, chưa phải test viết trước; mã 3: đã có file code đổi so với base (file đổi từ lát trước thì nêu bằng `--allow <file>`, được ghi vào bằng chứng; file trạng thái trong `.agent/` như `stack.json`, bản vá bàn giao không tính là code, trừ file có đuôi mã nguồn). Lệnh test phải chạy trong thư mục con thì thêm `--cwd <thư mục>` (cả `run`, `fails-before`, `lock`); không có `--cwd` thì lệnh chạy ở gốc project. File spec đổi trong lát được khóa cùng.
5. **Viết code** cho test xanh, không sửa test (hook nhắc ở mức vừa, chặn ở mức cao). Thêm dòng spec hay thêm test là siết: dùng Edit hay Write (lệnh shell ghi vào file khóa luôn bị chặn), rồi khóa lại (`receipt.py lock -- <lệnh test>`; test nối thêm gọi ký hiệu mới thì commit gốc thiếu import, lock vẫn ghi phần thêm và ghi kết luận vào sổ) và xin duyệt lại dòng mới (dòng thêm chưa duyệt: bánh cóc 🔴 ở mức cao, 🟡 ở mức khác; test thêm chưa khóa lại: 🟡).
6. **Xanh**: `python3 <receipt.py> run -- <lệnh test>` đạt và `spec.py check` thoát mã 0 (mỗi dòng có test mang dấu, test đó đã khóa).
7. **Dọn sau khi xanh**: chạy skill `simplify` của Claude Code, dặn chỉ sửa file không phải test và không đổi hành vi; xong thì chạy lại lệnh test khóa và mốc kiểm tra qua `receipt.py run`.
8. **Mức cao**: done-gate chạy `mutation.py` một lần lúc cuối trên dòng vừa đổi (chỉ để báo, không chặn).

## Theo dõi việc chạy lâu

Việc chạy lâu (job, CI, máy đo): không dùng vòng hẹn giờ đánh thức phiên chính. Chạy nền `python3 ~/Documents/Claude/agent-stack/plugin/skills/session-keeper/scripts/watch_change.py --every 300 --until <xong> --max-hours <giờ> -- <lệnh kiểm>`: script chỉ in khi trạng thái đổi; lệnh kiểm phải ra kết quả ổn định (không có đồng hồ chạy). Claude Code: chạy script bằng Monitor để phiên thức ở mỗi dòng mới; Bash chạy nền chỉ báo khi script thoát.

## Không làm

- Không chép §0 sang file khác. Các file khác chỉ trỏ tới §0.
- Không xóa lịch sử trong file kế hoạch. Chỉ cập nhật §0 và tick checkbox kèm ngày. Lịch sử cũ thì dời, không xóa: `state.py trim` chuyển mục Xong ngoài 3 mục mới nhất (theo ngày ghi trong mục), bước đã gạch hay ✅ của "Việc tiếp theo" và mốc đã xong hết sang `.agent/NHAT-KY.md` (đợt mới nhất ở trên; `--dry-run` để xem trước). Mục không ghi ngày thì script từ chối, chạy lại với `--newest-first` hay `--newest-last`; mục hay bước nhắc mốc kiểm tra thì giữ lại, và nếu dời xong mà mốc kiểm tra đổi thì script từ chối (ghi mốc vào dòng `- **Mốc kiểm tra:**` của §0 rồi chạy lại); lịch sử không nằm dưới nhãn **Xong** thì rút gọn tay. Agent đọc §0 mỗi phiên, nên §0 phình to là tốn token mỗi phiên.
- Việc mới ghi thành ô `- [ ]` dưới tiêu đề mốc của nó ở §1 (mốc mới thì thêm tiêu đề `###`), kèm nhãn `@ban`, `@cho`, `@usd` khi việc cần người dùng, chờ bên ngoài hay tốn tiền. Như vậy `progress/scripts/plan_tree.py` dựng được cây để chọn việc tiếp theo.
- Không ghi "xong" khi chưa có bằng chứng.
