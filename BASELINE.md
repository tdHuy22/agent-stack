# BASELINE: số liệu nền trước khi triển khai

> Đo ngày 2026-10-01, trước mọi thay đổi. Dùng để so sánh sau mỗi giai đoạn.
> Đo lại: `python3 tools/usage_snapshot.py --days 7` (thêm `--json` nếu cần số thô).

## Phiên bản và cấu hình

| Mục | Giá trị |
|---|---|
| Claude Code CLI (Homebrew cask) | 2.1.267. Bản mới nhất khoảng 2.1.286. |
| Claude Code trong desktop app | Khoảng 2.1.284 (suy từ đường dẫn bundled-skills) |
| OpenCode | v2.0.12 (cask `opencode-v2`). Cấu hình đọc được cả provider `tuf` lẫn `openai-oauth`. |
| Model mặc định trong `~/.claude/settings.json` | `sonnet` |
| Skill / agent / hook cá nhân | 0 / 0 / 1 (hook SessionStart của jcode) |
| Plugin đã cài | 0 (đã thêm marketplace chính thức) |
| Workflows | Bật, đã tắt cảnh báo usage (`skipWorkflowUsageWarning: true`) |

## Mức dùng token (ước tính từ transcript cục bộ)

### 7 ngày (2026-09-24 → 2026-10-01)

Ước tính theo giá niêm yết API, tính từ transcript cục bộ trên máy này. Không phải hóa đơn gói thuê bao, và không gồm phần dùng trên claude.ai hay máy khác.

| Model | Lượt gọi | Input | Cache write | Cache read | Output | USD ước tính | Tỉ trọng |
|---|---:|---:|---:|---:|---:|---:|---:|
| `claude-opus-5-5` | 5103 | 10.2k | 32.4M | 935.9M | 3.1M | 442.06 | 81% |
| `claude-sonnet-5-5` | 2248 | 4.5k | 13.9M | 230.5M | 2.4M | 105.24 | 19% |

- Tổng ước tính: **547.30 USD** trên 7351 lượt gọi model.
- Phiên: 13, ngày có hoạt động: 8.
- Phần của subagent và workflow: **70%** chi phí ước tính.
- Tỉ lệ token đầu vào đọc từ cache: **96%**.
- Project tốn nhiều nhất: SCEE (89%), Claude (4%), 2026-09-28_bao-cao-nen (2%), scee (2%), papers (1%).

### 30 ngày (2026-09-01 → 2026-10-01)

Ước tính theo giá niêm yết API, tính từ transcript cục bộ trên máy này. Không phải hóa đơn gói thuê bao, và không gồm phần dùng trên claude.ai hay máy khác.

| Model | Lượt gọi | Input | Cache write | Cache read | Output | USD ước tính | Tỉ trọng |
|---|---:|---:|---:|---:|---:|---:|---:|
| `claude-opus-5-5` | 5103 | 10.2k | 32.4M | 935.9M | 3.1M | 442.06 | 61% |
| `claude-opus-5` | 625 | 1.2k | 6.9M | 185.4M | 716.4k | 179.68 | 25% |
| `claude-sonnet-5-5` | 2248 | 4.5k | 13.9M | 230.5M | 2.4M | 105.24 | 14% |

- Tổng ước tính: **726.98 USD** trên 7976 lượt gọi model.
- Phiên: 19, ngày có hoạt động: 17.
- Phần của subagent và workflow: **53%** chi phí ước tính.
- Tỉ lệ token đầu vào đọc từ cache: **96%**.
- Project tốn nhiều nhất: SCEE (67%), tdhuy22 (15%), llama.cpp (5%), Claude (3%), llm-bench-20260918 (2%).

## Nhận xét

1. **70% chi phí 7 ngày đến từ subagent và workflow.** Đòn bẩy lớn nhất để giảm chi phí nằm ở model mà subagent/workflow dùng, không phải ở phiên chính. Nhưng phải đo chất lượng trước khi đổi (GĐ4), theo nguyên tắc giữ chất lượng là bắt buộc.
2. **`settings.json` đặt `sonnet` nhưng 81% chi phí là Opus 5.5.** Các phiên trong desktop app hoặc các workflow đang chạy Opus. Subagent mặc định kế thừa model của phiên chính, nên phiên chính chạy Opus kéo theo subagent cũng chạy Opus.
3. **96% token đầu vào đọc từ cache.** Caching đang hiệu quả. Đổi model hay effort giữa chừng sẽ kéo tỉ lệ này xuống, nên router chỉ gợi ý đổi ở ranh giới việc.
4. **SCEE chiếm 89% (7 ngày).** Bộ việc để eval ở GĐ4 nên mô phỏng kiểu việc của SCEE (đọc tài liệu dài, viết, review), nhưng dùng dữ liệu giả nằm trong `agent-stack/evals/`, không đụng vào SCEE.

## Bạn cần tự điền (lệnh tương tác, mình không chạy được)

- [ ] `/usage`: % hạn mức 5 giờ = …, % hạn mức tuần = …, phân bổ theo skill/subagent/MCP = …
- [ ] `/insights`: các điểm ma sát chính = …
