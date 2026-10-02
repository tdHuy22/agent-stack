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

## Hạn mức và điểm ma sát (02/10/2026)

### `/usage`

Đọc lại bằng công cụ `get_usage` của app tối 02/10/2026, không phải bản chép từ màn hình `/usage` (mình không thấy lần bạn chạy `/usage` trong transcript).

- Gói: **Max**. Usage credits (extra usage): tắt, trần 100 USD/tháng, đã dùng 0.
- Hạn mức 5 giờ: 12% (đặt lại sau 4 giờ 21 phút). Hạn mức tuần, mọi model: 22% (đặt lại 08/10). Hạn mức tuần riêng Fable: 0%.
- Cửa sổ ngữ cảnh của phiên đo: 11% của 1M token. Gồm Messages 4%, System tools 3%, MCP tools 2% (khoảng 19,8k), Skills 1% (khoảng 7,1k), System prompt và Memory files dưới 1%.
- **Chưa có:** phân bổ theo skill/subagent/MCP của màn hình `/usage`. Bạn dán số đó vào đây nếu cần.

### `/insights`

- Phạm vi: 30 phiên (22 phiên được phân tích), 144 tin nhắn, 97 giờ, 15 commit, từ 12/09 đến 02/10/2026. Tính trên mọi project của máy này, không riêng `agent-stack`. Báo cáo đầy đủ: `~/.claude/usage-data/report-2026-10-02-220350.html`.
- Điểm ma sát chính:
  1. Sửa lần đầu chỉ làm một phần việc rồi báo xong (script dọn phiên chỉ xóa `.jsonl`; tính năng mới không khớp `Component.capability`; một lần `git checkout` làm mất test vừa viết).
  2. Khuyên chắc chắn khi chưa kiểm môi trường của bạn (hướng dẫn kiểm statusline trong khi desktop app không chạy statusline; nói pyright, gitleaks, osv-scanner là cần thiết trong khi chỉ là tùy chọn).
  3. Đổi hệ thống hoặc nội dung công khai trước khi nêu rủi ro và cách hoàn tác (thiết lập headless gây lỗi khởi động lại; README lộ thông tin cá nhân), và một lần làm việc khác thay vì trả lời câu hỏi có/không.
- Điểm mạnh được ghi nhận: file kế hoạch làm bộ nhớ giữa các phiên; nghiên cứu song song kèm agent kiểm chứng độc lập; đo thay vì đoán.
- Báo cáo gợi ý (chưa làm): skill `/checkpoint` (gần với `session-keeper`), hook chặn `git checkout`, `git restore`, `git reset --hard` khi có việc chưa commit, và luật "trả lời câu hỏi có/không trước khi làm" trong CLAUDE.md.
