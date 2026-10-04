# Bảng định tuyến

> Trạng thái: **đã đối chiếu với khuyến nghị chính thức của Anthropic và số liệu eval của chính bạn** (02/10/2026, xem hai mục cuối). Nguồn luật máy đọc: `plugin/skills/task-router/rules.json`. Các dòng không có kiểm tra tự động vẫn là phán đoán, chưa có số đo.

| Loại việc | Model · Effort | Subagent | Skill | Căn cứ hiện tại |
|---|---|---|---|---|
| Kiểm duyệt đồ bên thứ ba | opus · high | — | vet-skill | Không có kiểm tra tự động, bỏ sót thì đắt |
| Review bảo mật | opus · high | agent-stack:reviewer | differential-review (nếu cài) | Như trên. `xhigh` hay `max` chỉ khi có số đo thấy lợi ích |
| Review code trước commit hoặc merge | opus · high | agent-stack:reviewer | — | Lỗi lọt qua thì tốn hơn nhiều |
| Debug khó, nhiều bước | opus · medium, **nâng lên high nếu lần đầu chưa ra** | — | diagnosing-bugs (nếu cài) | Có tái hiện hoặc test làm tín hiệu; `medium` là mặc định chính thức của Opus 5.5 |
| Kiến trúc, lập kế hoạch | opus · high (hoặc opusplan) | Plan | — | Không có kiểm tra tự động; `opusplan` là cách chính thức để Opus lập kế hoạch, Sonnet thực thi |
| Xem tiến độ, việc tiếp theo | sonnet · low | — | tien-do | Script làm phần nặng |
| Lưu tiến độ, bàn giao | sonnet · low | — | session-keeper | Việc ghi chép |
| Chạy và viết test | sonnet · medium | agent-stack:test-runner | tdd (nếu cài) | Có tín hiệu kiểm tra tự động. Eval (`qa-write-tests`): sonnet·medium đạt 2/2 |
| Nghiên cứu, so sánh | sonnet · medium | agent-stack:researcher | — | Đường cong effort của việc nghiên cứu gần phẳng (Anthropic) |
| Refactor | sonnet · medium | — | — | Có test thì đủ. Eval (`code-refactor-dup`): sonnet·medium đạt 2/2 |
| Tính năng thông thường | sonnet · medium | — | — | Eval (3 việc `code-*`): sonnet·medium đạt 6/6, rẻ khoảng một nửa Opus |
| Việc cơ học hàng loạt | haiku · low | agent-stack:oc-worker | — | Kết quả kiểm tra được bằng test hoặc diff |
| Viết văn bản | sonnet · medium | — | giong-van, humanizer | Eval (`write-vn-rewrite`): cả ba cấu hình đạt 2/2 |
| Hỏi nhanh | sonnet · low | — | — | `low` hợp với chat và tìm kiếm (Anthropic) |

## Quy tắc leo thang

1. **Bắt đầu ở mức rẻ nhất đủ sức.** Việc rõ ràng, mô tả được chính xác: sonnet · medium. Việc mơ hồ hoặc khó: opus · medium.
2. **Có kiểm tra tự động (test, lint, build, biên nhận) thì dùng nó làm tín hiệu.** Kiểm tra hỏng thì làm lại cùng model ở effort cao hơn (medium lên high).
3. **Hỏng vì bỏ sót file, không chạy test, không tự kiểm lại: nâng effort.** Hỏng dù đã đủ ngữ cảnh và đã cố hết sức: đổi sang model lớn hơn (sonnet lên opus).
4. **Không có kiểm tra tự động mà lỗi đắt: opus · high ngay từ đầu.** Không đổi giữa chừng một cuộc trò chuyện, vì đổi model làm mất cache.

## Số liệu chính thức của Anthropic (đọc ngày 02/10/2026)

- **Claude Code (`code.claude.com/docs/en/model-config`).**
  - Model mặc định là Opus 5.5 trên Pro, Max, Team, Enterprise và API; alias `sonnet` là Sonnet 5.5; `opusplan` dùng Opus lúc lập kế hoạch rồi Sonnet lúc thực thi.
  - Effort mặc định là `high` ở mọi model hỗ trợ effort, trừ Opus 5.5 và Sonnet 5.5 mặc định `medium` (Opus 4.7 mặc định `xhigh`).
  - Đặt bằng `/effort`, `claude --effort`, hoặc biến `CLAUDE_CODE_EFFORT_LEVEL`. Khóa `effortLevel` cấp cao nhất trong settings người dùng **không** áp cho Opus 5.5; dùng `/effort` hoặc `/model` để lưu mức riêng cho từng model.
- **Bài "Choosing a Claude model and effort level in Claude Code" (07/07/2026).**
  - Dùng effort mặc định của model và chỉnh theo kiểu việc bạn hay làm, không chỉnh từng việc.
  - Model nhỏ cho việc thường lệ (sửa mô tả được chính xác, đổi cơ học, hỏi về code đã có trong ngữ cảnh); model lớn cho việc mơ hồ hoặc khó (lỗi tinh vi, miền lạ, quyết định kiến trúc).
  - Sai dù đủ ngữ cảnh và đã cố: chọn model lớn hơn. Sai vì bỏ file, không chạy test, không kiểm lại: chọn effort cao hơn.
  - Việc thường lệ thì cả hai model đều làm đúng, model lớn chỉ tốn thêm token và đơn giá. Việc nhiều bước khó thì model nhỏ phải mò nhiều vòng, nên tổng chi phí mỗi việc có thể không rẻ hơn.
- **Trang chi phí (`platform.claude.com/docs/en/about-claude/models/optimizing-for-cost-and-intelligence`).**
  - Với hầu hết agent: bắt đầu từ Opus 5.5 ở `medium`; Opus 5.5 ở mặc định ngang Fable 5.1 ở mặc định trên bộ SWE-bench Pro con, với khoảng một phần năm chi phí mỗi việc giải được.
  - Coding dài hơi (SWE-bench Pro, Opus 5.5, so với `high`): `medium` thấp hơn khoảng 2,5 điểm với khoảng 70% chi phí; `low` thấp hơn khoảng 8 điểm với khoảng một phần ba; `xhigh` cao hơn khoảng 1,4 điểm với 2,5 lần chi phí.
  - Chạy ở `low` rồi chạy lại ca hỏng ở `high`: khoảng 97% đạt với khoảng 0,17 USD mỗi việc, so với 95,3% và 0,29 USD khi chạy tất cả ở `high`. Bắt đầu từ `medium` thì khoảng 97% với khoảng 0,24 USD.
  - Nghiên cứu và knowledge work: đường cong gần phẳng (số đo trên Fable 5), `low` hay `medium` thường đủ.
- **Sonnet 5.5 (tài liệu API).** Bắt đầu ở `medium` cho agentic coding và việc nhiều bước dùng công cụ; `low` cho chat, sinh nội dung, phân loại, trích xuất, tìm kiếm. Ở `low`, model dễ bỏ bước tự kiểm tra, nên yêu cầu nó chạy kiểm tra thật khi sửa code. Chỉ dùng `xhigh` hay `max` khi có số đo thấy lợi ích.
- **Giá API (USD mỗi triệu token, vào/ra), cùng cửa sổ ngữ cảnh 1M.** Sonnet 5.5: 2 / 10. Opus 5.5: 4 / 20.
- **Hạn mức gói.** Tài liệu chính thức không công bố hệ số khác nhau giữa Opus 5.5 và Sonnet 5.5 trong hạn mức 5 giờ hay hạn mức tuần. Có blog bên thứ ba nói Opus tốn khoảng 5 lần, mình chưa kiểm được. Nếu bạn quay về Pro, suy luận hợp lý là để sonnet · medium làm mặc định và dành Opus cho việc khó (`opusplan`), nhưng đó là suy luận của mình, chưa có nguồn chính thức.

## Kết quả eval của bạn (02/10/2026)

12 việc nhỏ (sửa code, đọc tài liệu, review bảo mật mẫu, viết test, viết lại văn bản) × 2 lượt × 3 cấu hình = 72 lượt, chấm bằng test hoặc so đáp án. Tổng khoảng 7,5 USD giá niêm yết, tính vào hạn mức gói (hạn mức 5 giờ đi từ 15% lên 22%, gồm cả phần phiên khác).

| Cấu hình | Đạt | USD/việc (TB) | USD p90 | Giây/việc |
|---|---:|---:|---:|---:|
| A: sonnet · medium | 24/24 | 0,063 | 0,068 | 12 |
| C: opus · medium | 24/24 | 0,128 | 0,149 | 18 |
| D: opus · low | 24/24 | 0,121 | 0,134 | 16 |

- Với loại việc này, cả ba đều đạt hết, nên script chọn **A** (rẻ nhất). Opus tốn gấp khoảng 2 lần, đúng bằng tỉ lệ đơn giá, mà không đạt thêm việc nào. Hạ Opus xuống `low` gần như không rẻ hơn (0,121 so với 0,128 USD).
- **Khớp với Anthropic:** việc thường lệ thì model nhỏ làm đủ với nửa chi phí; việc khó mới cần model lớn.
- **Giới hạn của số liệu:** vì cả ba đều đạt 100%, bộ việc này không phân biệt được các cấu hình, nên nó không nói gì về debug khó, kiến trúc hay review diff thật. Các dòng `opus · high` ở trên là phán đoán kết hợp khuyến nghị của Anthropic, không phải số đo của bạn. Muốn phân biệt, cần thêm vài việc khó hơn vào `evals/tasks/`.

## Việc khó hơn (03/10/2026)

6 việc mới trong `evals/tasks/`: `debug-multifile`, `debug-race`, `review-diff`, `code-cron-next` (khó), `code-async-pool`, `code-unified-diff` (rất khó). Mỗi việc chấm bằng test ẩn hoặc kịch bản chạy thật; các lời giải sai điển hình đều bị chấm trượt.

| Cấu hình | Đạt | USD/việc (TB) | Giây/việc |
|---|---:|---:|---:|
| A: sonnet · medium | 12/12 | 0,116 | 32 |
| C: opus · medium | 12/12 | 0,254 | 60 |
| D: opus · low | 12/12 | 0,215 | 40 |
| H: haiku · medium | 4/12 | 0,191 | 127 |

- Sonnet · medium, opus · medium và opus · low đều đạt hết, kể cả hai việc "rất khó" (pool asyncio an toàn khi hủy tác vụ, diff tối thiểu khớp `diff -u`). Script chọn **A**: opus tốn gấp khoảng 2 lần mà không đạt thêm việc nào. Việc tự chứa, có đặc tả rõ, chấm được bằng test thì sonnet đủ; muốn tách sonnet với opus cần việc dài hơi (nhiều giờ, codebase lớn, đặc tả mơ hồ).
- Lần chạy đầu D trượt 2 lượt diff vì grader bắt nhầm chữ "difflib" trong docstring; đã sửa grader (chỉ bắt `import`) và chấm lại mọi lượt bằng `--regrade`.
- Haiku trượt cron (nhận dạng bị cấm, chậm), review diff (bỏ sót lỗi thu tiền hai lần, 2/2 lượt), pool asyncio và diff (0/4); chỉ đạt hai việc debug. Và **đắt hơn** sonnet vì mò nhiều vòng (0,191 so với 0,116 USD; ở hai việc rất khó là 0,33 so với 0,18). Khớp khuyến nghị của Anthropic: model nhỏ làm việc nhiều bước khó không rẻ hơn. Haiku chỉ hợp việc cơ học có kiểm tra tự động.

## Còn chưa quyết định bằng số liệu

- Đặt `Explore` sang haiku (`explore-lite`) có làm giảm chất lượng các việc coding không? Cần so cấu hình E với A.
- Haiku (cấu hình H) trên việc cơ học: chưa đo. Trên việc khó: 4/12 và đắt hơn sonnet (mục trên).
- Bảng `BASELINE.md` cho thấy 70% chi phí đến từ subagent và workflow. Đây là chỗ đáng đo tiếp.
