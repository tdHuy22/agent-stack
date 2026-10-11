---
name: session-keeper
description: Lưu và khôi phục trạng thái công việc, để không mất tiến độ khi hết hạn mức, crash, compact hoặc khi đổi sang OpenCode. Cập nhật mục §0 "Đang ở đâu, việc tiếp theo" trong PLAN.md, viết .agent/HANDOFF.md khi bàn giao, và chạy các bước kiểm tra sau khi bị ngắt. Dùng khi người dùng nói lưu tiến độ, dừng phiên, sắp hết limit, bàn giao, handoff, làm tiếp việc dở, resume, hoặc khi project chưa có file kế hoạch.
when_to_use: lưu lại, checkpoint, save progress, hết hạn mức, usage limit, chuyển sang OpenCode, mở lại phiên, tiếp tục từ hôm qua, tạo PLAN.md
argument-hint: "[luu | tiep-tuc | ban-giao | khoi-tao]"
---

# Giữ trạng thái công việc trên đĩa

Nguyên tắc: **trạng thái nằm trên đĩa, không nằm trong context.** Nguồn sự thật là mục §0 của file kế hoạch, thường là `PLAN.md` ở gốc project hoặc `.agent/PLAN.md`. Hook SessionStart của agent-stack tự nạp lại §0 mỗi khi mở phiên, resume, `/clear` hoặc sau compact.

Ngoài §0, hook Stop tự ghi `.agent/LAST-TURN.md` sau mỗi lượt (yêu cầu, câu trả lời cuối đã che khóa, việc tiếp theo, file đổi) và hook SessionStart nạp nó vào phiên mới. Đây là bản máy ghi, không thay §0: đừng sửa tay, đừng chép nó vào §0. Khi lượt có đổi file mà §0 chưa đổi, hook Stop nhờ cập nhật §0 trước khi kết thúc lượt; lúc đó chỉ sửa §0 cho khớp việc vừa làm, ngắn gọn, rồi dừng.

Script hỗ trợ: `python3 "${CLAUDE_SKILL_DIR}/scripts/state.py" <lệnh> --project <thư mục>`. Chạy mốc kiểm tra qua `python3 "${CLAUDE_SKILL_DIR}/scripts/receipt.py" run --project <thư mục> -- <lệnh>`: script ghi biên nhận gắn với nội dung code, để phiên sau biết kết quả còn đúng hay đã cũ (`receipt.py show` để xem; `forget <tên>` xoá một biên nhận, `prune` xoá biên nhận trượt của test đã bị xoá khỏi project). Nếu biến `${CLAUDE_SKILL_DIR}` không được thay bằng đường dẫn thật (ví dụ trong OpenCode), dùng `~/Documents/Claude/agent-stack/plugin/skills/session-keeper/scripts/state.py`.

Chế độ lấy theo `$ARGUMENTS`. Nếu không có, suy ra từ lời người dùng.

## `luu`: lưu tiến độ (mặc định)

1. Chạy `state.py show` để xem §0 hiện tại và trạng thái git.
2. Sửa mục §0 trong file kế hoạch, giữ nguyên định dạng. Viết cụ thể đến mức người khác làm tiếp được mà không phải hỏi:
   - **Cập nhật** = ngày hôm nay, dạng `*Cập nhật DD/MM/YYYY.*`
   - **Xong:** kết quả kèm bằng chứng (commit, kết quả test).
   - **Đang dở:** việc gì, ở file nào, nhánh nào, còn thiếu gì.
   - **Việc tiếp theo, theo thứ tự:** danh sách đánh số; mỗi bước bắt đầu bằng một động từ.
   - **Quyết định còn treo:** điều cần người dùng chốt.
   - **Mốc kiểm tra:** lệnh và kết quả mong đợi, đúng với lần chạy gần nhất. Chạy lệnh đó qua `receipt.py run` để có biên nhận.
3. Cho người dùng xem diff của §0. Chỉ commit khi project cho phép (xem CLAUDE.md của project) hoặc khi người dùng yêu cầu.

## `tiep-tuc`: làm tiếp sau khi bị ngắt

1. Chạy `state.py show`.
2. Làm các bước trong "Sau khi bị ngắt". Nếu không có, chạy `git status` và `receipt.py show`, rồi chạy lại mốc kiểm tra qua `receipt.py run` nếu biên nhận đã cũ hoặc chưa có.
3. So kết quả với §0. Báo ngay nếu có gì lệch: test khác mốc, file chưa commit lạ, hay §0 cũ hơn commit gần nhất.
4. Đề xuất bước tiếp theo đầu tiên. Đợi người dùng đồng ý nếu bước đó sửa nhiều file.

## `ban-giao`: bàn giao sang phiên hoặc công cụ khác

1. Chạy `luu` trước.
2. Chạy `state.py handoff`. Script tạo `.agent/HANDOFF.md`, điền sẵn §0 và trạng thái git.
3. Điền các chỗ `<!-- điền -->`: mục tiêu, các quyết định đã chốt kèm lý do.
4. Nói cho người dùng cách làm tiếp. OpenCode: chạy `opencode` trong thư mục project rồi nhắn "Đọc .agent/HANDOFF.md rồi làm tiếp bước 1".

## `khoi-tao`: project chưa có file kế hoạch

1. Chạy `state.py init`. Script tạo `.agent/PLAN.md` từ mẫu và từ chối nếu project đã có file kế hoạch.
2. Điền §0 dựa trên những gì đã biết trong cuộc trò chuyện. Hỏi người dùng nếu chưa rõ mục tiêu hay mốc kiểm tra.

## Không làm

- Không chép §0 sang file khác. Các file khác chỉ trỏ tới §0.
- Không xóa lịch sử trong file kế hoạch. Chỉ cập nhật §0 và tick checkbox kèm ngày.
- Việc mới ghi thành ô `- [ ]` dưới tiêu đề mốc của nó ở §1 (mốc mới thì thêm tiêu đề `###`), kèm nhãn `@ban`, `@cho`, `@usd` khi việc cần người dùng, chờ bên ngoài hay tốn tiền. Như vậy `tien-do/scripts/plan_tree.py` dựng được cây để chọn việc tiếp theo.
- Không ghi "xong" khi chưa có bằng chứng.
