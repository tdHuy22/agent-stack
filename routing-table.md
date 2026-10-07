# Bảng định tuyến

> Trạng thái: đối chiếu tài liệu chính thức của Anthropic đọc ngày 04/10/2026 (trang effort, model-config của Claude Code, trang chi phí, bảng giá) và số liệu eval của chính bạn (02–04/10/2026). Nguồn luật máy đọc: `plugin/skills/task-router/rules.json` (router chỉ bắt được những loại việc nhận ra bằng từ khóa; bảng này đầy đủ hơn). Cột **Căn cứ**: **E** là số đo của bạn, **A** là tài liệu hay số đo của Anthropic, **P** là phán đoán chưa có số đo.

## 1. Thang effort

Effort là tín hiệu hành vi, không phải trần token cứng: ở mức thấp Claude vẫn suy nghĩ khi bài khó, chỉ ít hơn. Effort ảnh hưởng mọi token ra, kể cả số lần và độ dài lời gọi công cụ.

| Mức | Anthropic mô tả | Số đo (Opus 5.5, SWE-bench Pro, so với `high`) | Dùng khi | Tránh khi |
|---|---|---|---|---|
| `low` | Nhanh, rẻ nhất; hợp subagent và trao đổi nhanh mà bạn xem lại từng kết quả | 87,4% bài giải được, 0,12 USD mỗi bài giải được; thấp hơn khoảng 8 điểm, chi phí khoảng 1/3 | Sửa nhỏ, hỏi nhanh, tra cứu, tin nhắn, tiến độ | Việc nhiều bước mà không có test: model dễ bỏ bước tự kiểm |
| `medium` | Mặc định của Opus 5.5 và Sonnet 5.5 trong Claude Code; việc hằng ngày có phạm vi rõ | Thấp hơn khoảng 2,5 điểm, khoảng 70% chi phí; 92,8% với khoảng 0,22 USD mỗi bài giải được | Tính năng, refactor, test, nghiên cứu, debug có tín hiệu rõ | Không có kiểm tra tự động mà lỗi lọt qua thì đắt |
| `high` | Mặc định của Fable 5.1; việc cần kiểm kỹ, dễ có ca biên (sửa lỗi) | Mốc so sánh | Review, debug nhiều file, kế hoạch, phản biện | Việc thường lệ: tốn thêm mà không đạt thêm (eval của bạn) |
| `xhigh` | Suy luận sâu hơn; việc agent và coding dài trên 30 phút với ngân sách hàng triệu token. `/effort ultracode` là `xhigh` kèm workflow | Cao hơn khoảng 1,4 điểm, gấp khoảng 2,5 lần chi phí | Agent tự chạy lâu, review bảo mật phần nhạy cảm, quyết định kiến trúc khó đảo ngược, debug đã bế tắc ở `high` | Việc ngắn hay việc chấm được bằng test (`high` thường đã đủ) |
| `max` | Không giới hạn token; bài khó muốn Claude tự làm tới cùng, ví dụ săn lỗ hổng bảo mật. Lợi ích giảm dần và dễ nghĩ quá đà | Anthropic không công bố số | Đợt audit bảo mật cả repo, bài toán biên giới, khi bạn nói rõ "nghĩ kỹ nhất có thể" | Đầu ra có cấu trúc, việc không nặng suy luận; thử trước khi dùng rộng |

- **Một lượt cần nghĩ sâu mà không muốn đổi effort cả phiên:** thêm từ `ultrathink` vào prompt (Claude Code 2.1.203 trở lên). Các cụm "think hard", "nghĩ kỹ" không phải từ khóa.
- **Haiku 4.5 không có tham số effort.** Trong bảng ghi `haiku` không kèm mức.
- **Đặt effort:** `/effort <mức>` hay `/effort` (thanh trượt), `/effort auto` để xóa mức đã lưu, `claude --effort <mức>` cho một phiên, `CLAUDE_CODE_EFFORT_LEVEL`, `effortLevel` hay `modelSettings` trong settings, trường `effort` trong frontmatter của skill hay subagent. Đổi effort hay model giữa chừng làm mất prompt cache, nên đổi ở ranh giới giữa hai việc.

## 2. Thang leo thang

Đi từ trên xuống. Giá token (USD mỗi triệu token vào/ra): Haiku 4.5 1/5, Sonnet 5.5 2/10, Opus 5.5 4/20, Fable 5.1 10/50.

| Bậc | Cấu hình | Dùng cho | Căn cứ |
|---:|---|---|---|
| 0 | `haiku` | Việc cơ học có test hay diff kiểm được | A: Haiku cho khối lượng lớn có đầu ra kiểm được. E: việc khó chỉ đạt 4/12 và còn đắt hơn Sonnet |
| 1 | `sonnet · low` | Hỏi nhanh, sửa nhỏ, tra cứu, ghi chép | A |
| 2 | `sonnet · medium` | Mặc định cho việc rõ ràng | E: 24/24 việc nhỏ, 12/12 việc khó, rẻ nhất |
| 3 | `sonnet · high` | Việc khó hơn mà vẫn rõ đặc tả; review diff nhỏ; phản biện; văn bản dài | A: Sonnet 5.5 chuyển sang `high` cho việc khó hay dài hơn |
| 4 | `opus · medium` | Việc mơ hồ, khó; điểm khởi đầu của hầu hết agent | A: khởi đầu khuyến nghị cho agent |
| 5 | `opus · high` | Review, bảo mật, kiến trúc, debug không tái hiện được | A, P |
| 6 | `opus · xhigh` | Việc dài trên 30 phút, phần nhạy cảm, debug bế tắc | A |
| 7 | `fable · high` | Khi Opus ở effort cao vẫn chưa đạt; suy luận rất khó, dài hơi | A: Opus 5.5 mặc định ngang Fable 5.1 mặc định với khoảng 1/5 chi phí, nên chỉ lên Fable khi Opus đã thiếu |
| 8 | `opus · max` hoặc `fable · xhigh` | Audit bảo mật tự chạy tới cùng; bài toán biên giới | A |
| 9 | `fable · max` | Bài toán biên giới khi mọi bậc dưới đã thất bại | A: dành cho frontier problems |

**Lên bậc nào:**
1. Hỏng vì bỏ sót (không đọc đủ file, không chạy test, không tự kiểm lại): tăng effort, giữ model.
2. Hỏng dù đã đủ ngữ cảnh và đã cố: đổi model lớn hơn, bắt đầu lại ở effort mặc định của nó.
3. Có kiểm tra tự động thì có thể chạy ở mức thấp rồi chạy lại ca hỏng ở mức cao. Anthropic đo trên Opus 5.5: chạy hết ở `low`, ca hỏng chạy lại ở `high` đạt khoảng 97% với 0,17 USD mỗi việc; chạy hết ở `high` chỉ đạt 95,3% với 0,29 USD.
4. Không có kiểm tra tự động mà lỗi đắt: bắt đầu từ bậc 5 trở lên.
5. Nghiên cứu và knowledge work: đường cong gần phẳng (Fable 5.1 trên DeepResearch Bench II, `low` đến `high` gần như bằng điểm, chi phí từ 4,66 lên 7,12 USD). Tăng effort ở đây hầu như chỉ tốn thêm; muốn tốt hơn thì đổi model hay cách làm.

## 3. Bảng chi tiết theo việc

Cột **Bắt đầu** là cấu hình nên dùng trước; **Nếu chưa đạt** là bậc tiếp theo.

### Hỏi đáp và điều phối

| Việc | Bắt đầu | Nếu chưa đạt | Subagent | Skill | Căn cứ |
|---|---|---|---|---|---|
| Hỏi nhanh, giải thích một khái niệm | `sonnet · low` | `sonnet · medium` | — | — | A: `low` cho chat |
| Tra cú pháp, API, tham số của thư viện | `sonnet · low` | `sonnet · medium` | — | — (MCP context7) | P: tài liệu mới quan trọng hơn suy nghĩ thêm |
| Xem tiến độ, việc tiếp theo | `sonnet · low` | — | — | tien-do | P: script làm phần nặng |
| Lưu tiến độ, bàn giao | `sonnet · low` | `sonnet · medium` khi bàn giao phức tạp | — | session-keeper | P |
| Chọn model, effort | `sonnet · low` | — | — | task-router | P |
| Một lượt cần nghĩ sâu | giữ nguyên, thêm `ultrathink` | — | — | — | A |

### Tìm, đọc, nghiên cứu

| Việc | Bắt đầu | Nếu chưa đạt | Subagent | Skill | Căn cứ |
|---|---|---|---|---|---|
| Tìm vị trí code, nơi dùng một hàm | giữ nguyên | — | agent-stack:explore-lite (haiku) hoặc Explore | — | P: chỉ đọc, kết quả kiểm được |
| Đọc hiểu một vùng code lạ | `sonnet · medium` | `opus · medium` | Explore | — | P |
| Nghiên cứu web, so sánh công cụ | `sonnet · medium` | `opus · medium` (đổi model, không tăng effort) | agent-stack:researcher | reuse-best | A: đường cong effort gần phẳng |
| Nghiên cứu sâu nhiều nguồn, kết luận đắt nếu sai | `opus · medium` | `fable · low` | agent-stack:researcher | — | A: Fable 5.1 ở `low` hơn Sonnet 5 khoảng 10 điểm trên DeepResearch Bench II, đắt gấp khoảng 4 |
| Trước khi build: tìm thứ có sẵn | `sonnet · medium` | — | — | reuse-best | P |
| Đọc sâu một bài báo | `sonnet · medium` | `sonnet · high` | — | paper-anatomy | E: skill mới ở sonnet·medium thắng bản cũ 10/12 lần chấm mù |
| Phản biện bài báo (tuyên bố có đứng vững không) | `sonnet · high` | `opus · medium` | — | paper-anatomy | P: bench thấy sonnet·medium hay phê bình điều bài đã giải thích |
| Bài báo dài trên 100 trang hoặc bản scan | `sonnet · medium` | `opus · medium` | — | paper-anatomy | E: CaMeL 125 trang và Biba scan đạt ở sonnet·medium |

### Viết code

| Việc | Bắt đầu | Nếu chưa đạt | Subagent | Skill | Căn cứ |
|---|---|---|---|---|---|
| Sửa nhỏ mô tả chính xác (vài dòng, chính tả, thông báo) | `sonnet · low`, dặn chạy test | `sonnet · medium` | — | — | A: `low` cho thay đổi nhỏ; ở `low` model dễ bỏ bước tự kiểm |
| Việc cơ học hàng loạt (đổi tên, định dạng, dịch) | `haiku` | `sonnet · low` | agent-stack:oc-worker | — | A, E |
| Tính năng thông thường, đặc tả rõ | `sonnet · medium` | `sonnet · high` | — | reuse-best nếu không tầm thường | E: 6/6 |
| Tính năng nhiều ca biên (parser, định dạng, lịch, thuật toán) | `sonnet · medium` | `sonnet · high`, rồi `opus · medium` | — | tdd | E: cron và diff tối thiểu, sonnet 4/4, haiku 0/4 |
| Code đồng thời, async, khóa | `sonnet · medium` | `sonnet · high`, rồi `opus · high` | — | tdd | E: race và pool asyncio, sonnet 4/4, opus 4/4 |
| Refactor có test | `sonnet · medium` | `sonnet · high` | — | — | E: 2/2 |
| Refactor lớn, migration nhiều module, đổi API công khai | `opusplan` (Opus lập kế hoạch, Sonnet thực thi) | `opus · high` | Plan | reuse-best | A: `opusplan`; P |
| Viết test | `sonnet · medium` | `sonnet · high` | agent-stack:test-runner | tdd | E: 2/2 |
| Agent tự chạy dài (trên 30 phút, nhiều file, ít người can thiệp) | `opus · xhigh` hoặc `/effort ultracode` | `fable · high` | — | — | A: `xhigh` cho việc trên 30 phút. Cách chạy (theo `gnhf`, MIT): đặt điều kiện dừng và trần số vòng hoặc token trước khi đi ngủ, mỗi vòng một commit, vòng hỏng thì bỏ, ghi chú chung giữa các vòng vào một file; sáng ra chọn commit nào giữ |
| Việc dài hơi rất khó mà Opus ở `xhigh` vẫn chưa đạt | `fable · high` | `fable · xhigh` | — | — | A |

### Debug

| Việc | Bắt đầu | Nếu chưa đạt | Subagent | Skill | Căn cứ |
|---|---|---|---|---|---|
| Lỗi có traceback, test đỏ rõ | `sonnet · medium` | `sonnet · high` | agent-stack:test-runner | — | E |
| Lỗi nhiều file, nguyên nhân xa triệu chứng | `opus · medium` | `opus · high` | — | diagnosing-bugs | A: model lớn cho lỗi tinh vi. E: sonnet·medium đạt `debug-multifile` 2/2, có thể thử trước khi đã có test |
| Race, deadlock, lỗi lúc được lúc không | `opus · medium` | `opus · high` | — | diagnosing-bugs | E: `debug-race` mọi cấu hình trừ haiku đều đạt; P cho lỗi thật |
| Lỗi chỉ xảy ra trên production, không tái hiện, hồi quy hiệu năng | `opus · high` | `opus · xhigh` | — | diagnosing-bugs | P: không có tín hiệu kiểm nhanh |
| Đã thử hai lần ở mức cao mà vẫn chưa ra | `opus · xhigh` | `fable · high`, rồi `opus · max` | — | diagnosing-bugs | A |

### Review và bảo mật

| Việc | Bắt đầu | Nếu chưa đạt | Subagent | Skill | Căn cứ |
|---|---|---|---|---|---|
| Review diff nhỏ của mình trước commit | `sonnet · high` | `opus · high` | agent-stack:reviewer khi `risk.py` báo vừa hoặc cao | chot-viec | E: `review-diff` sonnet·medium 2/2, haiku 0/2; P: nâng lên `high` vì lỗi lọt đắt |
| Review PR lớn trước khi merge | `opus · high` | `opus · xhigh` | agent-stack:reviewer | — | P |
| Review bảo mật code thường | `opus · high` | `opus · xhigh` | agent-stack:reviewer | differential-review | P |
| Review bảo mật phần nhạy cảm (mã hóa, token, chữ ký, thanh toán, sandbox, leo thang quyền) | `opus · xhigh` | `opus · max` | agent-stack:reviewer | differential-review | A: việc bảo mật là ví dụ chính thức cho mức cao nhất |
| Audit bảo mật cả repo, săn lỗ hổng trước phát hành | `opus · max` | `fable · max` | agent-stack:reviewer | security-review | A: ví dụ chính thức của `max` |
| Kiểm duyệt skill, plugin, MCP bên thứ ba | `opus · high` | `opus · xhigh` khi có dấu hiệu lạ | — | vet-skill | P: không có kiểm tra tự động |

### Kế hoạch và kiến trúc

| Việc | Bắt đầu | Nếu chưa đạt | Subagent | Skill | Căn cứ |
|---|---|---|---|---|---|
| Kế hoạch việc vừa (vài file, vài giờ) | `sonnet · high` | `opusplan` | Plan | reuse-best | P |
| Thiết kế kiến trúc, hệ thống mới | `opus · high` hoặc `opusplan` | `opus · xhigh` | Plan | reuse-best | A: `opusplan`; P |
| Quyết định khó đảo ngược (schema dữ liệu thật, giao thức, mô hình bảo mật) | `opus · xhigh` | `fable · high` làm ý kiến thứ hai | Plan | reuse-best | P |
| Bài toán biên giới (thuật toán mới, chứng minh, tối ưu khó) | `fable · high` | `fable · max` | — | — | A |
| Bạn nói rõ "nghĩ kỹ nhất có thể, không ngại chi phí" | `opus · max` | `fable · max` | — | — | A: `max` không giới hạn token |

### Viết

| Việc | Bắt đầu | Nếu chưa đạt | Subagent | Skill | Căn cứ |
|---|---|---|---|---|---|
| Tin nhắn, email ngắn | `sonnet · low` | `sonnet · medium` | — | giong-van | A: `low` cho việc không phải code |
| Viết lại, sửa giọng | `sonnet · medium` | — | — | giong-van, humanizer | E: 2/2 |
| Văn bản dài (luận văn, báo cáo, tài liệu kỹ thuật) | `sonnet · high` | `opus · medium` | — | giong-van | P |
| Dịch tài liệu | `haiku` | `sonnet · low` | agent-stack:oc-worker | — | P |

### Vận hành

| Việc | Bắt đầu | Nếu chưa đạt | Subagent | Skill | Căn cứ |
|---|---|---|---|---|---|
| Chạy test, lint, build, tóm lỗi | giữ nguyên | — | agent-stack:test-runner | — | P |
| Chạy eval, benchmark có script | `sonnet · low` | — | — | — | P: script làm phần nặng |
| Cài skill, plugin, MCP | `opus · high` | — | — | vet-skill | P |

## 4. Số liệu chính thức của Anthropic (đọc ngày 04/10/2026)

- **Trang effort (`platform.claude.com/docs/en/build-with-claude/effort`).** Năm mức `low`, `medium`, `high`, `xhigh`, `max`. Fable 5.1, Opus 5.5 và Sonnet 5.5 hỗ trợ cả năm. Trên API, mặc định là `high`, trừ Opus 5.5 là `medium`. Sonnet 5.5: coding agentic và dùng công cụ nhiều bước thì bắt đầu ở `medium` cho việc có đặc tả rõ, `high` cho việc khó hay dài; chat thì `medium` hay `low`; chỉ dùng `xhigh` hay `max` khi eval thấy lợi. Fable 5.1: bắt đầu ở `high`, lên `xhigh` hay `max` cho việc nhạy với năng lực nhất.
- **Claude Code (`code.claude.com/docs/en/model-config`).** Mặc định trong Claude Code: Opus 5.5 và Sonnet 5.5 `medium`, Fable 5.1 `high`. Alias `opus` (Opus 5.5), `sonnet` (Sonnet 5.5), `haiku`, `fable` (Fable 5.1), `best` (Fable nếu có), `opusplan` (Opus lúc lập kế hoạch, Sonnet lúc thực thi). Từ khóa `ultrathink` tăng suy nghĩ cho một lượt.
- **Trang chi phí (`.../optimizing-for-cost-and-intelligence`).**
  - Với hầu hết agent, bắt đầu từ Opus 5.5 ở mặc định; dùng Fable 5.1 cho suy luận khó, việc agent dài hơi, hoặc khi Opus ở effort cao vẫn chưa đạt.
  - SWE-bench Pro: Opus 5.5 `medium` 92,8% với khoảng 0,22 USD mỗi bài giải được; Fable 5.1 mặc định 92,3% với 1,19 USD; Opus 5.5 `low` 87,4% với 0,12 USD.
  - Một benchmark coding nội bộ: Opus 5.5 mặc định 86,6% so với Fable 5.1 `medium` 84,2%, chưa tới một phần ba chi phí mỗi lần.
  - "Long-horizon coding" là nơi effort thật sự mua thêm độ chính xác; nghiên cứu thì gần phẳng.
- **Giá (USD mỗi triệu token vào/ra).** Fable 5.1: 10/50. Opus 5.5: 4/20 (đọc cache 0,05 lần giá vào). Sonnet 5.5: 2/10. Haiku 4.5: 1/5.
- **Hạn mức gói.** Tài liệu chính thức không công bố hệ số giữa các model trong hạn mức 5 giờ hay hạn mức tuần. Suy luận theo giá token: Opus khoảng 2 lần Sonnet, Fable khoảng 5 lần Sonnet.

## 5. Kết quả eval của bạn (02/10/2026)

12 việc nhỏ (sửa code, đọc tài liệu, review bảo mật mẫu, viết test, viết lại văn bản) × 2 lượt × 3 cấu hình = 72 lượt, chấm bằng test hoặc so đáp án. Tổng khoảng 7,5 USD giá niêm yết, tính vào hạn mức gói (hạn mức 5 giờ đi từ 15% lên 22%, gồm cả phần phiên khác).

| Cấu hình | Đạt | USD/việc (TB) | USD p90 | Giây/việc |
|---|---:|---:|---:|---:|
| A: sonnet · medium | 24/24 | 0,063 | 0,068 | 12 |
| C: opus · medium | 24/24 | 0,128 | 0,149 | 18 |
| D: opus · low | 24/24 | 0,121 | 0,134 | 16 |

- Với loại việc này, cả ba đều đạt hết, nên script chọn **A** (rẻ nhất). Opus tốn gấp khoảng 2 lần, đúng bằng tỉ lệ đơn giá, mà không đạt thêm việc nào. Hạ Opus xuống `low` gần như không rẻ hơn (0,121 so với 0,128 USD).
- **Khớp với Anthropic:** việc thường lệ thì model nhỏ làm đủ với nửa chi phí; việc khó mới cần model lớn.
- **Giới hạn của số liệu:** vì cả ba đều đạt 100%, bộ việc này không phân biệt được các cấu hình, nên nó không nói gì về debug khó, kiến trúc hay review diff thật. Các dòng `opus · high` ở trên là phán đoán kết hợp khuyến nghị của Anthropic, không phải số đo của bạn. Muốn phân biệt, cần thêm vài việc khó hơn vào `evals/tasks/`.

## 6. Việc khó hơn (03–04/10/2026)

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

## 7. Còn chưa quyết định bằng số liệu

- `xhigh`, `max` và Fable chưa được đo trên việc của bạn: mọi dòng dùng chúng là A hoặc P. Eval hiện có quá dễ để thấy lợi ích của chúng (sonnet · medium đã đạt hết); cần việc dài hơi trên 30 phút mới đo được.
- Các dòng `sonnet · high` (review diff nhỏ, phản biện, văn bản dài, kế hoạch vừa) là phán đoán: chưa so với `sonnet · medium`.

- Đặt `Explore` sang haiku (`explore-lite`) có làm giảm chất lượng các việc coding không? Cần so cấu hình E với A.
- Haiku (cấu hình H) trên việc cơ học: chưa đo. Trên việc khó: 4/12 và đắt hơn sonnet (mục trên).
- Bảng `BASELINE.md` cho thấy 70% chi phí đến từ subagent và workflow. Đây là chỗ đáng đo tiếp.
