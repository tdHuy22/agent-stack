# agent-stack

Bộ công cụ cá nhân cho Claude Code và OpenCode. Cách dùng hằng ngày ở `HUONG-DAN.md`. Thiết kế ở `KE-HOACH.md`, tiến độ ở `PLAN.md` (mục §0), số liệu nền ở `BASELINE.md`.

## Có gì

| Thành phần | Vị trí | Việc |
|---|---|---|
| `vet-skill` | `plugin/skills/vet-skill` | Kiểm duyệt skill, plugin, MCP của bên thứ ba: ghim commit, dò dấu hiệu độc hại, chạy skill-scanner, ghi `vetted.lock` |
| `session-keeper` | `plugin/skills/session-keeper` | Giữ trạng thái trên đĩa (mục §0 của PLAN.md, HANDOFF.md) để làm tiếp sau khi hết hạn mức, crash hoặc đổi sang OpenCode; `receipt.py` ghi kết quả kiểm tra gắn với nội dung code |
| `tien-do` | `plugin/skills/tien-do` | Tiến độ, việc dang dở, việc nên làm tiếp (5 bậc ưu tiên); `--all` cho mọi project |
| `task-router` | `plugin/skills/task-router` | Gợi ý model, effort, subagent, skill cho một việc, tính cả hồ sơ project (loại code, test, CI, code nhạy cảm) và việc tiếp theo trong §0; `route.py --session` cho công cụ không có hook như OpenCode |
| `giong-van` | `plugin/skills/giong-van` | Chỉnh văn theo giọng người viết, bỏ dấu hiệu văn AI (`tells.py`) |
| `reuse-best` | `plugin/skills/reuse-best` | Trước khi build: đọc ràng buộc của project, tìm thứ có sẵn tốt nhất trên GitHub và trong nghiên cứu SOTA (`scout.py`), kiểm từng tiêu chí bằng bằng chứng, rồi quyết định dùng lại hay tự làm và nêu phần còn phải làm |
| `mo-hinh-de-doa` | `plugin/skills/mo-hinh-de-doa` | Threat model ngắn trước khi code, chỉ khi chức năng đụng ranh giới tin cậy; ghi tối đa 5 mối đe dọa kèm chốt chặn vào `.agent/threat-model.md` để reviewer kiểm lúc chốt việc |
| `chot-viec` | `plugin/skills/chot-viec` | Cổng kiểm trước khi báo xong hay commit: ý định, mức rủi ro của diff (`risk.py`, cả ranh giới tin cậy bị đụng), kiểm chứng có biên nhận, review ở context mới theo mức rủi ro, rà tài liệu, báo cáo kèm phần bạn nên đọc |
| Hook | `plugin/hooks` | SessionStart nạp §0 và lượt cuối; UserPromptSubmit cảnh báo hạn mức, gợi ý router, lưu yêu cầu gần nhất và lúc bắt đầu lượt; SubagentStart đưa yêu cầu đó và việc tiếp theo cho subagent; PreCompact; PreToolUse chặn cài đồ chưa vet, hỏi trước `git checkout` trên cây bẩn, nhắc threat model trước khi code, nhắc audit cả repo khi tạo tag hay bản phát hành; Stop ghi `.agent/LAST-TURN.md` sau mỗi lượt, buộc chạy `chot-viec` khi lượt đổi code có rủi ro và nhờ Claude cập nhật §0 khi lượt có đổi file; SessionEnd |
| Agent | `plugin/agents` | reviewer, researcher, test-runner, explore-lite, oc-worker (tên có tiền tố `agent-stack:`) |
| Agent OpenCode | `opencode/agents/worker.md` | Worker chạy model local, chỉ được chạy lệnh kiểm tra |
| Statusline | `statusline/statusline.py` | model · effort · ctx · 5h · 7d |
| Luật chung | `global/` | `SHARED.global.md` (chung), `CLAUDE.global.md` (riêng Claude Code, import SHARED), `OPENCODE.global.md` (riêng OpenCode); `AGENTS.global.md` là file ghép cho OpenCode, sinh bằng `tools/build_rules.py`. Chỉ được link khi cài |
| Eval | `evals/` | 18 việc để chọn cấu hình rẻ nhất mà vẫn giữ chất lượng; bộ đo riêng cho skill (`suite:reuse-best`, 4 việc có bẫy) so hai phiên bản plugin |
| Công cụ | `tools/` | `usage_snapshot.py`, `install.py`, `maintain.py` |

## Dùng thử mà không thay đổi gì trên máy

```bash
claude --plugin-dir ~/Documents/Claude/agent-stack/plugin
```

## Kích hoạt toàn cục

```bash
./install.sh            # xem trước, không sửa gì
./install.sh --apply    # thực hiện: sao lưu trước, chỉ cài mục đã approve; mã thoát 1 = có lỗi, 2 = cài chưa đủ
./install.sh --rollback --apply
```

## Sau khi sửa code plugin

CLI trong terminal nạp plugin tại chỗ, nên sửa trong repo có hiệu lực từ phiên sau. Desktop app chạy bản chép trong `~/.claude/plugins/cache/`, nên cần cập nhật bản chép: tăng `version` trong `plugin/.claude-plugin/plugin.json`, rồi:

```bash
./install.sh --apply --only plugin   # chạy cả claude plugin update; mở phiên mới để nạp lại
```

Mọi thứ đã cài được ghi trong `INSTALLED.md` (kèm lệnh gỡ từng mục). Gỡ toàn bộ: `./install.sh --rollback --apply`.

## Kiểm tra

```bash
python3 -m unittest discover -s tests -t .
claude plugin validate plugin
python3 evals/run_eval.py --self-test
python3 tools/maintain.py          # mỗi tháng
```
