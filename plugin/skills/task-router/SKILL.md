---
name: task-router
description: Gợi ý nên dùng model nào (sonnet, opus, haiku, fable), effort nào (low đến max), subagent nào và skill nào cho một việc, để giữ chất lượng mà không tốn thừa hạn mức. Dùng khi người dùng hỏi việc này nên dùng model gì, effort bao nhiêu, có nên giao cho subagent không, hoặc muốn tiết kiệm token mà không giảm chất lượng.
when_to_use: chọn model, chọn effort, nên dùng opus hay sonnet, giao subagent, tiết kiệm token, tiết kiệm hạn mức, routing
argument-hint: "<mô tả việc>"
---

# Chọn model, effort, subagent và skill cho một việc

Việc cần gợi ý: `$ARGUMENTS` (trống thì là việc người dùng vừa nêu).

## Bước 1: chạy router, giữ nguyên dòng nó in

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/route.py" --line <<'VIEC'
<mô tả việc>
VIEC
```

`<mô tả việc>` (qua stdin để shell không chạy backtick hay `$` trong chữ) là nguyên văn việc sẽ làm, bỏ câu hỏi chọn model và lời dặn cách trả lời ("trả lời ngắn" làm khớp nhầm luật viết tin nhắn). Script in sẵn dòng trả lời theo luật: giữ nguyên Model, Effort, Subagent, Skill của dòng đó. Chỉ khi script báo không khớp luật nào mới chọn theo bảng mặc định ở dưới.

Nếu biến `${CLAUDE_SKILL_DIR}` không được thay bằng đường dẫn thật (ví dụ khi đọc thẳng file này ngoài plugin), dùng `~/Documents/Claude/agent-stack/plugin/skills/task-router/scripts/route.py`.

Thêm `--project <thư mục>` để tính hồ sơ project và `.agent/stack.json` của project đó. File này do skill `project-setup` sinh, gồm:
- từ khóa riêng kèm mức;
- từ khóa bỏ qua (chỉ có tác dụng khi người dùng đã duyệt);
- vùng lõi;
- mức sàn theo nhóm luật.

Router không bao giờ gợi ý dưới mức sàn của project. Câu khớp từ khóa riêng mà không khớp luật nào thì ra luật `project-keyword`.

Router chỉ so chữ của người dùng: bỏ khối nhắc của hệ thống đứng đầu tin, thẻ `<ide_*>`, phần dán và khối code.

### Lớp model (chỉ khi chấm bước kế hoạch)

Khi lớp từ khóa không chắc (không khớp luật nào, hai luật đứng đầu bằng điểm mà khác mức, hay câu dài chỉ khớp một chữ), router có thể hỏi một model nhỏ qua `claude -p` (`plugin/lib/routemodel.py`). Model chỉ đọc câu, nhãn hồ sơ project và cụm bỏ qua đã duyệt có trong câu, rồi trả đúng một id luật. Mức, subagent, skill vẫn do luật quyết, và mức sàn của project vẫn áp sau cùng. Model không hạ được gợi ý của lớp từ khóa; nó chỉ được chọn luật không ở mức fable hay max.

Cấu hình ở mục `model_layer` của `rules.json`. Số đo ngày 15/11/2026 ở `.agent/trang/router-model-gd5.html`, đo lại bằng `evals/router_model_eval.py`.
- Đang bật cho đúng một lúc: sau khi người dùng duyệt kế hoạch phiên. Hook `plan_steps.py` chấm từng bước bằng Sonnet 5.5·low, một lần gọi cho cả nhóm, chờ tối đa 7 giây. Nó chỉ báo bước khai mức dưới sàn của project, hay bước bảo mật khai dưới gợi ý.
- Tin nhắn và việc tiếp theo trong §0 không dùng lớp model. Lý do: độ trễ vượt 3 giây, và ở §0 model làm gợi ý tệ đi.
- Tắt cho một phiên: `AGENT_STACK_ROUTER_MODEL=off`.

## Bước 2: nguyên tắc đằng sau luật

Dùng để giải thích, chọn khi router không khớp, hay khi người dùng hỏi thêm điều kiện (ví dụ cấu hình rẻ hơn); không dùng để đổi dòng router đã in:

1. **Giữ chất lượng là bắt buộc, rẻ hơn chỉ là điểm cộng.** Chỉ khuyên dùng model rẻ hơn hoặc effort thấp hơn khi việc có bước kiểm tra tự động (test, linter, schema), hoặc khi kết quả sẽ được một model mạnh hơn xem lại.
2. **Hạ effort trước, hạ model sau.** Model mạnh ở effort thấp thường giữ chất lượng tốt hơn model yếu ở effort cao.
3. **Việc có rủi ro cao** (review bảo mật, mất dữ liệu, kiến trúc, migration) thì dùng opus · high, kể cả khi trông có vẻ nhỏ. Viết tính năng đụng ranh giới tin cậy (đăng nhập, upload, webhook, thanh toán) thì sonnet · high, chạy threat-model trước; bước review sau đó mới lên opus. Phần nhạy cảm nhất (mã hóa, token, thanh toán, sandbox, quyết định khó đảo ngược) thì opus · xhigh. Việc agent tự chạy trên 30 phút: mở phiên mới bằng Fable high (mục 7); phiên đã chạy sẵn bằng Opus thì opus · xhigh, đừng đổi model giữa phiên. `max` chỉ cho đợt audit bảo mật tự chạy tới cùng, bài toán biên giới, hoặc khi người dùng nói rõ muốn nghĩ kỹ nhất: lợi ích giảm dần và dễ nghĩ quá đà.
4. **Việc nhiều phần độc lập** (đọc nhiều file, chạy test, việc cơ học hàng loạt) thì giao cho subagent, để output dài không làm đầy context chính.
5. **Effort đổi thoải mái, model chỉ đổi khi rẻ.** Opus 5.5, Sonnet 5.5, Haiku 5.5, Fable 5.1 trở lên giữ prompt cache khi đổi effort giữa phiên (tài liệu prompt caching của Claude Code). Đổi model thì phải ghi lại cả context vào cache của model mới: phiên có 250K token context tốn khoảng 1 USD giá niêm yết mỗi lần. Chỉ khuyên `/model` khi rẻ: đầu phiên, sau `/clear` hay `/compact`, context dưới 40K token, hoặc đã nghỉ quá 1 giờ (cache hết hạn). Còn lại khuyên giữ model và giao phần việc cho subagent với `model`, `effort` hợp việc; việc dài trên 30 phút, sửa nhiều file thì thêm `isolation: "worktree"` rồi gộp bằng `merge_back.py` (xem dưới). Việc cần model mạnh hơn mới làm đúng thì vẫn đổi: chất lượng trước chi phí. Claude Code cho phép đặt `effort` cho subagent khi gọi Agent.
6. **Leo thang theo thang trong `routing-table.md`:** sonnet · low → medium → high → opus · medium → high → xhigh → fable · high → opus · max hoặc fable · xhigh → fable · max. Hỏng vì bỏ sót thì tăng effort; đủ ngữ cảnh mà vẫn sai thì đổi model lớn hơn. Code và debug không có test bắt đầu ở `high` (sonnet · high; việc mơ hồ hay nhiều file thì opus · high; người dùng chốt 10/11/2026); việc có test, hỏi nhanh, việc tri thức giữ mức trong bảng.
7. **Fable** (chính sách bạn duyệt 13/11/2026, mục "Chính sách Fable" của `routing-table.md`): phiên thường ngày dùng Opus 5.5 vì Opus 5.5 mặc định giải ngang Fable 5.1 mặc định với khoảng 1/5 chi phí (Fable 5.2, từ 09/11/2026, rẻ hơn 20% nhưng mỗi token vẫn gấp đôi Opus). Fable `high` làm subagent khi Opus ở `high` rồi `xhigh` đã hỏng hai lần trên một việc tách riêng được, và làm ý kiến thứ hai cho quyết định khó đảo ngược. Mở phiên mới bằng Fable high cho phiên thiết kế (project mới, tính năng lớn, yêu cầu mơ hồ): phiên dừng ở spec, test khóa và §0, còn code làm ở một phiên Opus mới. Việc tự chạy dài hơn 30 phút thì mở phiên bằng Fable high, giao phần đọc và phần có test cho subagent Sonnet hay Haiku. Bảo mật và audit không dùng Fable (bộ lọc an toàn của nó hay tự chuyển model). Không đổi model giữa phiên đang dài (mục 5). Không đo Fable bằng benchmark vì rất đắt: chỉ đo từ lần dùng thật qua `usage_report.py` và nhật ký review. Tùy gói, Fable có thể bị tính vào usage credits.
8. **Luôn dùng model mới nhất**: `sonnet` (Sonnet 5.5), `opus` (Opus 5.5), `fable` (Fable 5.2), và `claude-haiku-5-5` (alias `haiku` cũng ra Haiku 5.5 từ CLI 2.1.293, kiểm 10/11/2026; ghi ID đầy đủ để đúng cả trên bản cũ). Haiku 5.5 có effort `low` tới `max`, mặc định `medium`. Eval 08/10/2026: ở `low` nó đạt 9/9 việc code, debug có test (18/18 lượt, kể cả việc rất khó) với khoảng 1/10 chi phí sonnet · medium, effort cao hơn không đạt thêm; nhưng viết văn tiếng Việt yếu. Nên khuyên `claude-haiku-5-5 · low` cho việc có test hay kiểm tra tự động, kèm đường lên `sonnet · high` khi test trượt; việc không có cách kiểm tự động, viết văn, review, kiến trúc thì giữ sonnet hay opus. Chỉ cần nghĩ sâu cho một lượt thì khuyên thêm `ultrathink` vào prompt thay vì đổi effort cả phiên.
9. **Skill vendor** (`tdd`, `diagnosing-bugs`, `humanizer`, `handoff`, `grill-me`) đã xoá khỏi danh mục ngày 09/10/2026, sau khi A/B 20 lượt cho thấy chúng không giúp đạt thêm việc nào và không được gọi lần nào. Đừng gợi ý chúng.
10. **Skill có `model:` trong frontmatter phải có `context: fork`.** Thiếu `context: fork` thì mỗi lần gọi skill là một lần đổi model của cả phiên (tốn cache như mục 5). Đừng thêm skill như vậy, kể cả skill bên thứ ba.

## Giao việc dài cho subagent trên nhánh riêng

Khi việc dài, tách bạch, cần model khác model của phiên chính:

1. Gọi Agent với `model`, `effort` theo gợi ý và `isolation: "worktree"`. Prompt giao việc phải tự đủ (yêu cầu gốc, file liên quan, tiêu chí xong, lệnh test), dặn subagent commit trong worktree khi xong và không sửa file kế hoạch (`PLAN.md`, `.agent/`) hay cấu hình agent (`.claude/`, `CLAUDE.md`, `AGENTS.md`): phiên chính cập nhật §0 sau khi gộp. Worktree mặc định tách từ nhánh mặc định của repo, không từ HEAD: phiên chính đang ở nhánh khác thì báo người dùng trước.
2. Subagent xong thì chạy, từ cây làm việc chính:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/merge_back.py" --worktree <đường dẫn hay nhánh> --test "<lệnh test>" [--commit "<thông điệp>"]
   ```

   Script ghim commit đầu nhánh, rồi chỉ tự gộp đúng commit đó khi test đạt trong worktree, gộp được bằng fast-forward, nhánh không dời commit trong lúc test, diff không đụng file nhạy cảm (`.claude/`, `.github/`, hook, `CLAUDE.md`, `AGENTS.md`, `.mcp.json`, file kế hoạch, `.agent/`, symlink, submodule...) và không trùng file chưa commit của phiên chính; gộp xong xoá worktree và nhánh. Chạy script là chạy toàn bộ mã của nhánh (test, `conftest.py`) dưới quyền người dùng, ngoài vòng duyệt từng lệnh: chỉ dùng cho nhánh do subagent của chính phiên tạo. Mã thoát 2 nghĩa là cần người dùng quyết: báo lại lý do script in ra, đừng tự gộp bằng tay. Không bao giờ push.
3. Gộp xong, chạy lại mốc kiểm tra của project ở cây làm việc chính (qua `receipt.py` nếu project dùng nó).

## Bảng mặc định cho dòng ➡️

Dùng khi không có gợi ý `[agent-stack]` hay `[router]` (luật chung, mục dòng ➡️). Model: `sonnet` (Sonnet 5.5), `opus` (Opus 5.5), `fable` (Fable 5.2), `claude-haiku-5-5` (Haiku 5.5); effort `low` tới `max`. Trong bảng, – là `không`, * là chỉ khi đã cài. Dòng ➡️ chỉ ghi `· Model · Effort` khi khác cái đang chạy (khuyên đổi), `· Subagent`, `· Skill` khi ô không phải –; không có việc tiếp theo thì không in dòng:

| Việc | Model·Effort | Subagent | Skill |
|---|---|---|---|
| Hỏi nhanh, sửa vài dòng, tin nhắn ngắn | sonnet·low | – | – (writing-voice khi viết tin nhắn) |
| Tìm, đọc nhiều file | giữ nguyên | Explore (explore-lite rẻ hơn) | – |
| Tính năng, lỗi có traceback rõ; refactor | có test: claude-haiku-5-5·low, trượt thì sonnet·high; refactor, không có test hay đụng ranh giới tin cậy: sonnet·high | test-runner | reuse-best nếu không tầm thường; threat-model trước khi code nếu đụng ranh giới tin cậy |
| Debug nhiều file, race, lỗi lúc được lúc không | opus·high, chưa ra thì xhigh | – | – |
| Kiểm trước khi báo xong hay commit | sonnet·high | reviewer khác model người viết theo mức rủi ro (`risk.py --writer` chọn sẵn) | done-gate |
| Nghiên cứu web, so sánh công cụ | sonnet·medium | researcher | reuse-best |
| Kế hoạch việc vừa, văn bản dài; kiến trúc; quyết định khó đảo ngược | sonnet·high; opus·high; opus·xhigh | Plan | reuse-best; reader-page khi ra file |
| Review PR lớn, bảo mật (phần nhạy cảm: xhigh) | opus·high | reviewer | differential-review* |

Việc khác (Aside, bài báo, audit, Fable, cài skill) và căn cứ: `~/Documents/Claude/agent-stack/routing-table.md`. Chưa đạt thì lên bậc theo mục 6 ở trên: hỏng vì bỏ sót thì tăng effort; đủ ngữ cảnh mà vẫn sai thì đổi model lớn hơn. Chỉ cần nghĩ sâu một lượt thì thêm `ultrathink` vào prompt (mục 8).

## Kết quả trả về

Dòng router in ra (không khớp luật thì tự viết theo bảng), đúng định dạng:

`➡️ Model: <...> · Effort: <...> · Subagent: <tên|không> · Skill: <tên|không> · Lý do: <tối đa 15 từ>`

Sau đó, nếu cần, thêm tối đa 2 câu về điều kiện để dùng được mức rẻ hơn (ví dụ "nếu có test bao phủ thì claude-haiku-5-5 · low đủ").

Bảng đầy đủ kèm căn cứ từng dòng (số đo của người dùng, tài liệu Anthropic, hay phán đoán) ở `routing-table.md`. Khi có số liệu eval mới (`evals/run_eval.py`), cập nhật `rules.json` và `routing-table.md` cùng lúc.
