---
name: task-router
description: Gợi ý nên dùng model nào (sonnet, opus, haiku, fable), effort nào (low đến max), subagent nào và skill nào cho một việc, để giữ chất lượng mà không tốn thừa hạn mức. Dùng khi người dùng hỏi việc này nên dùng model gì, effort bao nhiêu, có nên giao cho subagent không, hoặc muốn tiết kiệm token mà không giảm chất lượng.
when_to_use: chọn model, chọn effort, nên dùng opus hay sonnet, giao subagent, tiết kiệm token, tiết kiệm hạn mức, routing
argument-hint: "<mô tả việc>"
model: sonnet
effort: low
---

# Chọn model, effort, subagent và skill cho một việc

Việc cần gợi ý: `$ARGUMENTS`

## Bước 1: gợi ý theo luật (0 token)

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/route.py" "<mô tả việc>"
```

Nếu biến `${CLAUDE_SKILL_DIR}` không được thay bằng đường dẫn thật (ví dụ trong OpenCode), dùng `~/Documents/Claude/agent-stack/plugin/skills/task-router/scripts/route.py`.

## Bước 2: điều chỉnh theo các nguyên tắc sau

Luật từ khóa chỉ là điểm xuất phát. Sau đó cân nhắc thêm:

1. **Giữ chất lượng là bắt buộc, rẻ hơn chỉ là điểm cộng.** Chỉ khuyên dùng model rẻ hơn hoặc effort thấp hơn khi việc có bước kiểm tra tự động (test, linter, schema), hoặc khi kết quả sẽ được một model mạnh hơn xem lại.
2. **Hạ effort trước, hạ model sau.** Model mạnh ở effort thấp thường giữ chất lượng tốt hơn model yếu ở effort cao.
3. **Việc có rủi ro cao** (bảo mật, mất dữ liệu, kiến trúc, migration) thì dùng opus · high, kể cả khi trông có vẻ nhỏ. Phần nhạy cảm nhất (mã hóa, token, thanh toán, sandbox, quyết định khó đảo ngược) và việc agent tự chạy trên 30 phút thì opus · xhigh. `max` chỉ cho đợt audit bảo mật tự chạy tới cùng, bài toán biên giới, hoặc khi người dùng nói rõ muốn nghĩ kỹ nhất: lợi ích giảm dần và dễ nghĩ quá đà.
4. **Việc nhiều phần độc lập** (đọc nhiều file, chạy test, việc cơ học hàng loạt) thì giao cho subagent, để output dài không làm đầy context chính.
5. **Chỉ đổi model hoặc effort ở ranh giới giữa hai việc.** Đổi giữa chừng làm mất prompt cache, nên có thể tốn hơn.
6. **Leo thang theo thang trong `routing-table.md`:** sonnet · low → medium → high → opus · medium → high → xhigh → fable · high → opus · max hoặc fable · xhigh → fable · max. Hỏng vì bỏ sót thì tăng effort; đủ ngữ cảnh mà vẫn sai thì đổi model lớn hơn.
7. Fable chỉ dành cho việc mà Opus ở effort cao vẫn chưa đạt: Opus 5.5 mặc định giải ngang Fable 5.1 mặc định với khoảng 1/5 chi phí. Tùy gói, Fable có thể bị tính vào usage credits.
8. **Haiku không có tham số effort**: ghi `haiku`, không ghi mức. Chỉ cần nghĩ sâu cho một lượt thì khuyên thêm `ultrathink` vào prompt thay vì đổi effort cả phiên.

## Kết quả trả về

Một dòng, đúng định dạng:

`➡️ Model: <...> · Effort: <...> · Subagent: <tên|không> · Skill: <tên|không> · Lý do: <tối đa 15 từ>`

Sau đó, nếu cần, thêm tối đa 2 câu về điều kiện để dùng được mức rẻ hơn (ví dụ "nếu có test bao phủ thì haiku đủ").

Bảng đầy đủ kèm căn cứ từng dòng (số đo của người dùng, tài liệu Anthropic, hay phán đoán) ở `routing-table.md`. Khi có số liệu eval mới (`evals/run_eval.py`), cập nhật `rules.json` và `routing-table.md` cùng lúc.
