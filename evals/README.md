# Bộ eval "giữ hiệu suất"

Mục đích: chọn cấu hình model và effort **rẻ nhất mà vẫn giữ chất lượng**, bằng số liệu trên việc giống việc thật của bạn, thay vì đoán.

| Nhóm | Việc | Cách chấm |
|---|---|---|
| Coding | `code-off-by-one`, `code-add-flag`, `code-refactor-dup`, `code-duration` (khó) | Chạy test, kể cả test ẩn; chặn việc sửa file test |
| Đọc tài liệu | `doc-ratelimit`, `doc-multihop`, `doc-decisions` | So đáp án; bẫy số liệu cũ và owner cũ |
| Review bảo mật | `sec-sqli`, `sec-path-traversal`, `sec-secrets` | Phải nêu đúng lỗ hổng; báo nhầm hàm an toàn thì trượt |
| QA | `qa-write-tests` | Mutation: bộ test phải bắt được ít nhất 2 trong 3 lỗi cấy |
| Viết | `write-vn-rewrite` | Giữ đủ 5 sự kiện, xưng "mình", điểm dấu hiệu văn AI (`tells.py`) giảm ít nhất 60% |
| Debug khó (03/10/2026) | `debug-multifile`: 4 nguyên nhân ở 4 file, test có sẵn chỉ lộ 1; `debug-race`: race, deadlock khi khóa không thứ tự, tự chuyển cho chính mình | Test ẩn theo SPEC; sửa thiếu file nào cũng trượt. Race: chạy tải nặng trong tiến trình con có hạn giờ, đo song song, không cho khóa chung |
| Review diff thật (03/10/2026) | `review-diff`: PR có 4 lỗi đưa vào và 3 thay đổi đúng trông đáng ngờ | Phải nêu đủ 4 lỗi theo dạng `LỖI n: file:hàm — …`; nêu thay đổi đúng là lỗi thì trượt |
| Đặc tả nhiều ca biên (03/10/2026) | `code-cron-next` (khó), `code-async-pool` và `code-unified-diff` (rất khó) | Cron: luật OR ngày/thứ, 29/2, không bao giờ khớp, < 0,5 giây. Pool asyncio: 8 kịch bản hủy, hết giờ, kết nối hỏng, `close()`. Diff: tối thiểu (so LCS), áp lại ra đúng file, khớp `diff -u` ở 13 ca chuẩn, 5.000 dòng < 2 giây |
| Debug rất khó (07/10/2026) | `debug-ttl-cache`: đệm TTL+LRU có 8 lỗi chồng nhau theo đặc tả dài, test có sẵn chỉ lộ vài lỗi; `debug-flaky-rank`: bảng xếp hạng đổi theo `PYTHONHASHSEED` + 4 lỗi ở 3 file | Grader theo đặc tả, đồng hồ giả; flaky-rank chạy 8 hạt giống và so với đáp án tính tay |

Mỗi việc có lời giải mẫu trong `solution/`. Lệnh `--self-test` kiểm rằng grader chấm trượt bản chưa sửa và chấm đạt bản lời giải. Lệnh này không gọi model, không tốn gì.

## Chạy

```bash
python3 evals/run_eval.py --self-test                          # miễn phí
python3 evals/run_eval.py --configs A,C,D --repeats 2          # chỉ in kế hoạch + ước tính
python3 evals/run_eval.py --configs A,C,D --repeats 2 --yes    # chạy thật, tính vào hạn mức
```

- Cấu hình nằm trong `configs.json`: A sonnet·medium, B sonnet·high, C opus·medium, D opus·low, E = A + plugin, H haiku (chỉ để đo trần dưới), V = A + plugin vendor (`vendor/`, không nằm trong git).
- Cấu hình có plugin (`"plugin": true` hoặc `"plugins": [...]`) được phép gọi `Skill` và chạy với `--output-format stream-json --verbose`; mỗi lượt ghi `skills_used`, và bảng tổng hợp có dòng "gọi skill ở n/m lượt". So V với A cho biết skill vendor có giúp thật không; skill không được gọi thì chênh lệch chỉ là nhiễu. Từ 07/10/2026, E cũng được gọi `Skill` (trước đó skill của plugin bị từ chối quyền); E chạy thật lần đầu cùng ngày, với bộ đo `reuse-best` ở cuối file.
- Mỗi lượt chạy trong thư mục tạm của hệ điều hành, **ngoài agent-stack**, nên model không đọc được `CLAUDE.md` của repo, grader (`check.py`) hay lời giải. Nếu `--work-root` nằm trong repo hoặc dưới một thư mục có `CLAUDE.md`/`AGENTS.md`, script từ chối chạy.
- Chạy với `--setting-sources project` (không nạp hook cá nhân) và `--no-session-persistence`. File `evals/results/<thời điểm>.meta.json` ghi điều kiện chạy: commit, phiên bản CLI và plugin, dấu vân tay từng việc, và có `~/.claude/CLAUDE.md` hay không.
- Bài làm được chốt ngay khi lượt chạy kết thúc: patch nằm trong `evals/results/<thời điểm>/`, câu trả lời nằm trong file JSONL (không đưa vào git). Thư mục tạm bị xóa sau khi chấm, trừ khi có `--keep-workdirs`.
- Cần đăng nhập Claude Code ở terminal trước (`claude /login`).
- Nên chia lượt chạy ra vài ngày để không đốt hạn mức tuần. `--max-total-usd` đặt trần.

## Đọc kết quả

Quy tắc chọn: lấy cấu hình rẻ nhất trong các cấu hình có tỉ lệ đạt không thấp hơn cấu hình tốt nhất quá 1 việc. Hai cấu hình sát nhau thì chạy thêm lượt lặp trước khi chốt. Chốt xong thì ghi vào `routing-table.md` và cập nhật `plugin/skills/task-router/rules.json`.

Script chỉ chốt khi ma trận đủ:
- mọi cấu hình có cùng số lượt cho mọi việc;
- không lượt nào hỏng vì môi trường (chưa đăng nhập, hết hạn mức);
- mọi lượt dùng cùng đề bài và cùng grader.

Lượt hỏng vì vận hành (hết giờ, chạm trần chi phí) vẫn tính là trượt và được đếm riêng ở cột "Lỗi vận hành".

```bash
python3 evals/run_eval.py --report evals/results/*.jsonl   # gộp các lần chạy ở nhiều ngày
python3 evals/run_eval.py --regrade evals/results/X.jsonl  # đổi grader thì chấm lại bài đã chốt trước khi so
```

Self-test chỉ chứng minh grader đúng. Nó không phải số liệu về model.

Hạn chế: 18 việc là ít, và do Claude soạn. Hãy thêm vài việc lấy từ chính công việc của bạn (dữ liệu giả, đặt trong `evals/tasks/`), vì số liệu chỉ đáng tin khi bộ việc giống việc thật.

## Bộ đo riêng cho skill

Việc có `"suite": "<tên>"` trong `meta.json` thuộc bộ đo riêng của một skill. `--tasks all` không chạy các việc này, vì chúng không dùng để chọn cấu hình; chạy bằng `--tasks suite:<tên>`. Self-test và `--regrade` vẫn tính cả bộ đo.

So hai phiên bản của một skill:

```bash
mkdir -p .tmp/plugin-head && git archive HEAD plugin | tar -x -C .tmp/plugin-head --strip-components 1
cp plugin/.agent-stack-home .tmp/plugin-head/
python3 evals/run_eval.py --configs E --tasks suite:reuse-best --repeats 3 --plugin-root .tmp/plugin-head --tag cu --save-streams --yes
python3 evals/run_eval.py --configs E --tasks suite:reuse-best --repeats 3 --tag moi --save-streams --yes
python3 evals/run_eval.py --report evals/results/<cũ>.jsonl evals/results/<mới>.jsonl
python3 evals/trace_stats.py evals/results/<cũ>.jsonl evals/results/<mới>.jsonl
```

- `--plugin-root` nạp agent-stack từ thư mục khác và phải đi kèm `--tag`, để tên cấu hình thành `E@cu`, `E@moi`. Mỗi lượt ghi dấu vân tay nội dung plugin; cùng một tên cấu hình mà khác dấu thì bảng tổng hợp báo, không gộp nhầm. Đừng sửa `plugin/` khi đang chạy.
- `--save-streams` lưu luồng sự kiện của từng lượt vào `evals/results/<thời điểm>/`. Dòng kết quả có thêm `skill_outputs`, là báo cáo mà skill trả về, để biết lỗi nằm ở skill hay ở bước phiên chính tóm tắt lại.
- `trace_stats.py` đo quá trình, không gọi model: lệnh bị chặn quyền, lệnh shell ghép, số lần tìm GitHub và số lần ra rỗng, số lần kiểm repo, số chỗ skill tự nhận "chưa kiểm".
- Với bộ đo skill, bảng tổng hợp có thêm bảng việc × cấu hình và không áp quy tắc chọn cấu hình rẻ nhất.
- Self-test và `--regrade` dùng thư mục tạm riêng cho mỗi lượt, nên hai phiên chạy test cùng lúc không xóa thư mục của nhau.

### Bộ `reuse-best` (07/10/2026)

| Việc | Bẫy | Đạt khi câu trả lời cuối |
|---|---|---|
| `reuse-gap` | `tools/md_links.py` có docstring nói kiểm cả anchor, nhưng `anchor_exists` là TODO luôn trả True; link ngoài bị bỏ qua | nhắc `md_links.py`, nói nó chưa thật sự kiểm anchor, có so với công cụ ngoài |
| `reuse-constraint` | Python 3.9 và luật cấm gói ngoài nằm trong `pyproject.toml`, CI và `CONTRIBUTING.md`; đề bài không nhắc | nêu tomllib cần 3.11, project chạy 3.9, và luật không thêm gói ngoài |
| `reuse-scale` | `app/ratelimit.py` đếm trong bộ nhớ; production chạy 4 worker × 3 replica và đã có Redis | nhắc limiter có sẵn, nói nó sai khi chạy nhiều tiến trình, đi tới Redis |
| `reuse-stdlib` | đối chứng: thư viện chuẩn là đủ | chọn hashlib hay filecmp, không chốt cài gói ngoài |

Grader chấm theo ý, không theo chữ: `tests/test_eval_suites.py` thử mỗi grader với câu đúng viết kiểu khác (phải đạt) và câu sai có đủ từ khóa (phải trượt).

Kết quả ngày 07/10/2026, cấu hình E, mỗi phiên bản 12 lượt (4 việc × 3), tổng 9,87 USD giá niêm yết cho cả các đợt thăm dò (bản 0.5.2 là `scout.py` theo nguyên tắc AXI, `KE-HOACH.md` mục 6.16):

| Trung bình mỗi lượt | Bản cũ (0.5.0) | 0.5.1 | 0.5.2 |
|---|---:|---:|---:|
| Đạt | 12/12 | 12/12 | 12/12 |
| USD | 0,203 | 0,218 | 0,198 |
| Giây | 45 | 55 | 46 |
| Lệnh shell ghép | 6,3 | 0 | 0,1 |
| Lệnh bị chặn quyền | 3,6 | 0,2 | 0 |
| Lần tìm GitHub ra rỗng | 1,1 | 0,4 | 0 |
| Lần gọi `scout.py repo` | 0 | 2,7 | 0,9 |
| Số repo được kiểm bằng README | 0 | 2,6 | 2,2 |
| Chỗ skill tự nhận "chưa kiểm", "theo hiểu biết" | 2,6 | 1,2 | 1,0 |

Bản cũ đạt hết, nghĩa là bốn bẫy chưa phân biệt được hai bản ở đầu ra; khác biệt nằm ở quá trình và ở bằng chứng. Ví dụ với `reuse-gap`, bản cũ không kiểm được lychee có kiểm anchor không nên chọn tự viết phần slug heading, còn bản mới đọc được dòng README nói về `--include-fragments` và chọn lychee cho cả anchor lẫn link ngoài. Grader đã qua review đối kháng. Trên bộ câu thử lúc review, bản đầu cho lọt 10 trên 27 câu sai (phần lớn là câu của model tin docstring hay chép lại đề) và chấm oan 8 trên 26 câu đúng. Bản sửa đầu tiên, khi chấm lại bài thật, lại chấm oan 3 lượt vì coi chữ "còn" ("anchor_exists còn TODO") là chữ nối. Mọi câu đó nay nằm trong `tests/test_eval_suites.py`. Đợt 0.5.2 lộ thêm một lượt bị chấm oan ở `reuse-stdlib` (câu quyết định nói "bằng thư viện chuẩn", chữ SHA-256 nằm xa); đã sửa. Mọi bài đã chốt được chấm lại bằng grader cuối (`--regrade`) và đọc soát đúng câu mà grader dựa vào.
