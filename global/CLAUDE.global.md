@~/Documents/Claude/agent-stack/global/SHARED.global.md

# Riêng Claude Code

## Bảng chọn cho dòng ➡️

Model: `sonnet` (Sonnet 5.5), `opus` (Opus 5.5), `fable` (Fable 5.2), `claude-haiku-5-5` (Haiku 5.5); effort `low` tới `max`. Dùng khi không có gợi ý `[agent-stack]` hay `[router]` (– là `không`, * là chỉ khi đã cài):

| Việc | Model·Effort | Subagent | Skill |
|---|---|---|---|
| Hỏi nhanh, sửa vài dòng, tin nhắn ngắn | sonnet·low | – | – (writing-voice khi viết tin nhắn) |
| Tìm, đọc nhiều file | giữ nguyên | Explore (explore-lite rẻ hơn) | – |
| Tính năng, lỗi có traceback rõ; refactor | có test: claude-haiku-5-5·low, trượt thì sonnet·high; refactor, không có test hay đụng ranh giới tin cậy: sonnet·high | test-runner | reuse-best nếu không tầm thường; threat-model trước khi code nếu đụng ranh giới tin cậy |
| Debug nhiều file, race, lỗi lúc được lúc không | opus·high, chưa ra thì xhigh | – | – |
| Kiểm trước khi báo xong hay commit | sonnet·high | reviewer khác model người viết khi rủi ro từ vừa (`risk.py --writer` chọn sẵn) | done-gate |
| Nghiên cứu web, so sánh công cụ | sonnet·medium | researcher | reuse-best |
| Kế hoạch việc vừa, văn bản dài; kiến trúc; quyết định khó đảo ngược | sonnet·high; opus·high; opus·xhigh | Plan | reuse-best; reader-page khi ra file |
| Review PR lớn, bảo mật (phần nhạy cảm: xhigh) | opus·high | reviewer | differential-review* |

Việc khác (Aside, bài báo, audit, Fable, cài skill) và căn cứ: `~/Documents/Claude/agent-stack/routing-table.md`. Chưa đạt thì lên bậc: hỏng vì bỏ sót thì tăng effort; đủ ngữ cảnh mà vẫn sai thì đổi model lớn hơn. Chỉ cần nghĩ sâu một lượt thì thêm `ultrathink` vào prompt.

Model trong bảng là model hợp với việc, không phải lệnh đổi ngay:

- Effort: Opus 5.5, Sonnet 5.5, Haiku 5.5, Fable 5.1 trở lên giữ prompt cache khi đổi `/effort` giữa phiên, nên ghi effort hợp việc thoải mái.
- Model: `/model` giữa phiên tốn khoảng 1 USD mỗi 250K token context; không rẻ (luật chung, mục dòng ➡️) thì giao subagent, truyền `model` và `effort` của dòng bảng vào Agent (luật này cho phép đặt `effort` cho subagent); việc cần model mạnh hơn mới làm đúng thì vẫn đổi.
- Việc dài trên 30 phút, sửa nhiều file, hợp model khác: Agent với `isolation: "worktree"`, giao và gộp lại bằng `merge_back.py` theo mục "Giao việc dài" của `~/Documents/Claude/agent-stack/plugin/skills/task-router/SKILL.md`.
- Đừng thêm skill có `model:` trong frontmatter mà không có `context: fork`: mỗi lần gọi là một lần đổi model.

## Trang HTML và Artifact

- Trang cho người đọc: nội dung theo skill `reader-page` (gồm skill Anthropic theo việc, cách đưa trang), trình bày theo `artifact-design`. Kế hoạch có từ hai phương án đáng so sánh hay từ ba quyết định cần chốt: ngoài tóm tắt trong chat, đăng trang Artifact riêng tư và đọc bình luận bằng `ArtifactComments` rồi mới làm.

## Subagent

- Subagent của agent-stack có tiền tố `agent-stack:` (như `agent-stack:reviewer`). Giao subagent việc đọc nhiều hay sinh output dài cho context chính gọn; đừng chia nhỏ việc mà một model làm liền mạch tốt hơn.
- Theo dõi việc chạy lâu: chạy `watch_change.py` (luật chung, mục Trạng thái việc) bằng Monitor để phiên thức ở mỗi dòng mới; Bash chạy nền chỉ báo khi script thoát.
