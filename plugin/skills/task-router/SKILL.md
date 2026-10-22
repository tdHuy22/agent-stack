---
name: task-router
description: Gợi ý nên dùng model nào (sonnet, opus, haiku, fable), effort nào (low đến max), subagent nào và skill nào cho một việc, để giữ chất lượng mà không tốn thừa hạn mức. Dùng khi người dùng hỏi việc này nên dùng model gì, effort bao nhiêu, có nên giao cho subagent không, hoặc muốn tiết kiệm token mà không giảm chất lượng.
when_to_use: chọn model, chọn effort, nên dùng opus hay sonnet, giao subagent, tiết kiệm token, tiết kiệm hạn mức, routing
argument-hint: "<mô tả việc>"
model: sonnet
effort: low
context: fork
---

# Chọn model, effort, subagent và skill cho một việc

Việc cần gợi ý: `$ARGUMENTS`

## Bước 1: gợi ý theo luật (0 token)

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/route.py" "<mô tả việc>"
```

Nếu biến `${CLAUDE_SKILL_DIR}` không được thay bằng đường dẫn thật (ví dụ khi đọc thẳng file này ngoài plugin), dùng `~/Documents/Claude/agent-stack/plugin/skills/task-router/scripts/route.py`.

## Bước 2: điều chỉnh theo các nguyên tắc sau

Luật từ khóa chỉ là điểm xuất phát. Sau đó cân nhắc thêm:

1. **Giữ chất lượng là bắt buộc, rẻ hơn chỉ là điểm cộng.** Chỉ khuyên dùng model rẻ hơn hoặc effort thấp hơn khi việc có bước kiểm tra tự động (test, linter, schema), hoặc khi kết quả sẽ được một model mạnh hơn xem lại.
2. **Hạ effort trước, hạ model sau.** Model mạnh ở effort thấp thường giữ chất lượng tốt hơn model yếu ở effort cao.
3. **Việc có rủi ro cao** (bảo mật, mất dữ liệu, kiến trúc, migration) thì dùng opus · high, kể cả khi trông có vẻ nhỏ. Phần nhạy cảm nhất (mã hóa, token, thanh toán, sandbox, quyết định khó đảo ngược) và việc agent tự chạy trên 30 phút thì opus · xhigh. `max` chỉ cho đợt audit bảo mật tự chạy tới cùng, bài toán biên giới, hoặc khi người dùng nói rõ muốn nghĩ kỹ nhất: lợi ích giảm dần và dễ nghĩ quá đà.
4. **Việc nhiều phần độc lập** (đọc nhiều file, chạy test, việc cơ học hàng loạt) thì giao cho subagent, để output dài không làm đầy context chính.
5. **Effort đổi thoải mái, model chỉ đổi khi rẻ.** Opus 5.5, Sonnet 5.5, Haiku 5.5, Fable 5.1 giữ prompt cache khi đổi effort giữa phiên (tài liệu prompt caching của Claude Code). Đổi model thì phải ghi lại cả context vào cache của model mới: phiên có 250K token context tốn khoảng 1 USD giá niêm yết mỗi lần. Chỉ khuyên `/model` khi rẻ: đầu phiên, sau `/clear` hay `/compact`, context dưới 40K token, hoặc đã nghỉ quá 1 giờ (cache hết hạn). Còn lại khuyên giữ model và giao phần việc cho subagent với `model`, `effort` hợp việc; việc dài trên 30 phút, sửa nhiều file thì thêm `isolation: "worktree"` rồi gộp bằng `merge_back.py` (xem dưới). Việc cần model mạnh hơn mới làm đúng thì vẫn đổi: chất lượng trước chi phí.
6. **Leo thang theo thang trong `routing-table.md`:** sonnet · low → medium → high → opus · medium → high → xhigh → fable · high → opus · max hoặc fable · xhigh → fable · max. Hỏng vì bỏ sót thì tăng effort; đủ ngữ cảnh mà vẫn sai thì đổi model lớn hơn.
7. Fable chỉ dành cho việc mà Opus ở effort cao vẫn chưa đạt: Opus 5.5 mặc định giải ngang Fable 5.1 mặc định với khoảng 1/5 chi phí. Tùy gói, Fable có thể bị tính vào usage credits.
8. **Luôn dùng model mới nhất**: `sonnet` (Sonnet 5.5), `opus` (Opus 5.5), `fable` (Fable 5.1), và `claude-haiku-5-5` thay cho alias `haiku` (alias này còn trỏ Haiku 4.5, không có effort). Haiku 5.5 có effort `low` tới `max`, mặc định `medium`. Eval 08/10/2026: ở `low` nó đạt 9/9 việc code, debug có test (18/18 lượt, kể cả việc rất khó) với khoảng 1/10 chi phí sonnet · medium, effort cao hơn không đạt thêm; nhưng viết văn tiếng Việt yếu. Nên khuyên `claude-haiku-5-5 · low` cho việc có test hay kiểm tra tự động, kèm đường lên `sonnet · medium` khi test trượt; việc không có cách kiểm tự động, viết văn, review, kiến trúc thì giữ sonnet hay opus. Chỉ cần nghĩ sâu cho một lượt thì khuyên thêm `ultrathink` vào prompt thay vì đổi effort cả phiên.
9. **Skill vendor** (`tdd`, `diagnosing-bugs`, `humanizer`, `handoff`, `grill-me`) đã xoá khỏi danh mục ngày 09/10/2026, sau khi A/B 20 lượt cho thấy chúng không giúp đạt thêm việc nào và không được gọi lần nào. Đừng gợi ý chúng.

## Giao việc dài cho subagent trên nhánh riêng

Khi việc dài, tách bạch, cần model khác model của phiên chính:

1. Gọi Agent với `model`, `effort` theo gợi ý và `isolation: "worktree"`. Prompt giao việc phải tự đủ (yêu cầu gốc, file liên quan, tiêu chí xong, lệnh test), dặn subagent commit trong worktree khi xong và không sửa file kế hoạch (`PLAN.md`, `.agent/`) hay cấu hình agent (`.claude/`, `CLAUDE.md`, `AGENTS.md`): phiên chính cập nhật §0 sau khi gộp. Worktree mặc định tách từ nhánh mặc định của repo, không từ HEAD: phiên chính đang ở nhánh khác thì báo người dùng trước.
2. Subagent xong thì chạy, từ cây làm việc chính:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/merge_back.py" --worktree <đường dẫn hay nhánh> --test "<lệnh test>" [--commit "<thông điệp>"]
   ```

   Script ghim commit đầu nhánh, rồi chỉ tự gộp đúng commit đó khi test đạt trong worktree, gộp được bằng fast-forward, nhánh không dời commit trong lúc test, diff không đụng file nhạy cảm (`.claude/`, `.github/`, hook, `CLAUDE.md`, `AGENTS.md`, `.mcp.json`, file kế hoạch, `.agent/`, symlink, submodule...) và không trùng file chưa commit của phiên chính; gộp xong xoá worktree và nhánh. Chạy script là chạy toàn bộ mã của nhánh (test, `conftest.py`) dưới quyền người dùng, ngoài vòng duyệt từng lệnh: chỉ dùng cho nhánh do subagent của chính phiên tạo. Mã thoát 2 nghĩa là cần người dùng quyết: báo lại lý do script in ra, đừng tự gộp bằng tay. Không bao giờ push.
3. Gộp xong, chạy lại mốc kiểm tra của project ở cây làm việc chính (qua `receipt.py` nếu project dùng nó).

## Kết quả trả về

Một dòng, đúng định dạng:

`➡️ Model: <...> · Effort: <...> · Subagent: <tên|không> · Skill: <tên|không> · Lý do: <tối đa 15 từ>`

Sau đó, nếu cần, thêm tối đa 2 câu về điều kiện để dùng được mức rẻ hơn (ví dụ "nếu có test bao phủ thì claude-haiku-5-5 · low đủ").

Bảng đầy đủ kèm căn cứ từng dòng (số đo của người dùng, tài liệu Anthropic, hay phán đoán) ở `routing-table.md`. Khi có số liệu eval mới (`evals/run_eval.py`), cập nhật `rules.json` và `routing-table.md` cùng lúc.
