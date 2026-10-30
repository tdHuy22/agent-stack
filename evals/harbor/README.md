# Bench: agent-stack có làm Claude Code tệ đi không

So Claude Code **có** và **không có** agent-stack trên cùng một bộ việc coding có grader tự động, chạy trong Docker trên máy TUF bằng [Harbor](https://pypi.org/project/harbor/) 0.25. Bộ việc lấy từ OpenThoughts-TBLite (100 việc kiểu Terminal-Bench, đã hiệu chỉnh độ khó).

## Hai bản được so

| | Bản trơn (`claude-code-plain`) | Bản có agent-stack (`claude-code-agent-stack`) |
|---|---|---|
| Model, effort | Sonnet 5.5, medium | như bên trái |
| Claude Code | 2.1.308 | như bên trái |
| CLAUDE.md cấp người dùng | không có | `global/CLAUDE.global.md`, nhập `global/SHARED.global.md`, như `~/.claude/CLAUDE.md` trên Mac |
| Plugin | không có | agent-stack (hook, skill, subagent), nạp bằng `--plugin-dir` |

- Bản có agent-stack chép repo, đúng commit lúc `sync` (`git archive HEAD`), vào `$HOME/Documents/Claude/agent-stack` trong container. Nhờ vậy mọi đường dẫn ghi trong luật đều trỏ đúng như trên Mac.
- Hai bản chạy chung một job. Harbor xen kẽ lượt của hai bên, nên tải máy hay giờ trong ngày không làm lệch về một phía.
- Biến `AGENT_STACK_NO_BACKGROUND=1` chỉ tắt việc chạy nền lúc mở phiên: kiểm MCP và tự kéo agent-stack trên cloud. Cả hai chỉ gọi mạng, không đổi gì model thấy.

## Bản này đo được gì, không đo được gì

- **Đo được** những thứ có mặt ở mọi việc:
  - chữ luật chung và mô tả skill, subagent nạp vào mỗi lần gọi model;
  - các hook UserPromptSubmit, PreToolUse, SessionStart;
  - việc agent có tự gọi skill hay subagent không.
- **Ít hoặc không đo được:**
  - Cổng chốt việc và nhắc §0 ở hook Stop dựa vào git và file kế hoạch. Phần lớn container không có git repo hay `PLAN.md`, nên hai cổng này hầu như không bật.
  - Lợi ích nối tiếp công việc giữa các phiên (§0, `LAST-TURN.md`, bàn giao) nằm ngoài bench vì mỗi việc chỉ có một phiên.
- Hook cần `python3`. `tasks-pilot.txt` chỉ chọn những việc mà image có sẵn Python, nên không phải cài thêm gì vào môi trường của việc.
- Chi phí USD là số Claude Code tự ước theo giá niêm yết. Chạy bằng gói thuê bao thì số đó dùng để so hai bản, không phải tiền thật.

## Bộ việc

`tasks-pilot.txt` có 20 việc: 10 dễ, 10 vừa, rút ngẫu nhiên có hạt giống cố định (xem đầu file). Muốn chạy bộ khác thì tạo `tasks-<TÊN>.txt` rồi chạy `sync`; tên file chính là TÊN job.

- 27 việc của TBLite không có lời giải mẫu (`solve.sh` chỉ in "no solution written"), nên không ai kiểm được grader của chúng. Bộ thử không lấy các việc này.
- Bước `oracle` chạy lời giải mẫu trên đúng bộ việc của job. Việc nào lời giải mẫu không đạt thì `compare` tự loại.

## Một lần trước khi chạy (bước của bạn)

Claude Code trong container dùng gói thuê bao của bạn qua một token dài hạn. Agent không được nhập hay đọc token, nên bước này bạn tự làm:

1. Trên Mac, chạy lệnh sau và làm theo hướng dẫn để nhận token:

   ```bash
   claude setup-token
   ```

2. Trên TUF, mở file `~/harbor-eval/.env`, thêm dòng `CLAUDE_CODE_OAUTH_TOKEN=<token>`, rồi khoá quyền đọc:

   ```bash
   nano ~/harbor-eval/.env
   ```

   ```bash
   chmod 600 ~/harbor-eval/.env
   ```

Token chỉ nằm trong `.env` trên TUF. Cấu hình job chỉ đặt `CLAUDE_FORCE_OAUTH=1`; Harbor đọc token từ `.env` qua `--env-file`.

## Chạy (từ Mac, ở gốc repo)

| Bước | Lệnh | Tốn gì |
|---|---|---|
| Đưa bản chép, agent, cấu hình lên TUF | `evals/harbor/tuf.sh sync` | không |
| Kiểm sẵn sàng, không chạy container | `evals/harbor/tuf.sh check` | không |
| Lời giải mẫu: kiểm grader và Docker | `evals/harbor/tuf.sh oracle` | CPU của TUF vài phút, không gọi model |
| Chạy hai bản | `evals/harbor/tuf.sh run` | hạn mức Claude: 40 lượt ở bộ thử |
| Xem tiến độ | `evals/harbor/tuf.sh status` | không |
| Kéo kết quả về `.tmp/harbor-jobs/` | `evals/harbor/tuf.sh fetch` | không |
| So ghép cặp | `evals/harbor/tuf.sh compare` | không |

- `oracle` và `run` chạy nền trên TUF, nên thoát ssh thì job vẫn chạy.
- Hai lệnh này từ chối khi TUF đang bận: còn container khác, một tiến trình khác dùng trên 1 nhân (như llama-server của bench pi-agent), GPU bận từ 20%, tải 1 phút quá 1/4 số nhân, hay RAM trống dưới 12 GB. Thêm `--force` để chạy bất chấp.
- Mỗi lúc chạy 3 việc. TUF có 15 GB RAM, mỗi việc được cấp tới 4 GB.
- Job trùng tên đã có trên TUF thì lệnh cũng từ chối, để không chạy chồng lên kết quả cũ.

- `run` chép bản chép agent-stack sang `jobs/<TÊN>.payload` trên TUF và job dùng bản đó, nên `sync` giữa lúc job đang chạy không đổi được job; commit của bản chép nằm trong `jobs/<TÊN>.payload/.payload-commit`.
- `fetch` chạy `harbor_bench.py export` trên TUF: chỉ chép `result.json`, log Claude Code, `reward.txt`, và che token `sk-ant-…` trước khi kéo về (model có thể chạy `env` trong container). Bản cũ trên Mac bị xoá trước, để hai lần chạy không trộn vào nhau.

## Đọc kết quả

`compare` (hay `harbor_bench.py compare <job> --oracle <job-oracle>`) in ra:

- tỉ lệ đạt của từng bản;
- số việc mà bản có agent-stack kém hơn và tốt hơn, kèm p của kiểm định McNemar chính xác;
- token, chi phí, thời gian (trung vị và tổng), số lượt lỗi;
- số lượt bản có agent-stack thật sự nạp plugin. Con số này đọc từ sự kiện init của Claude Code. Nếu bản trơn cũng thấy agent-stack thì hai bản không tách nhau, và kết quả không dùng được.

Cách tính:
- Lượt không có điểm (môi trường hỏng), hay hỏng vì hạ tầng (hết hạn mức, rate limit, quá tải, xác thực, mạng, sai tên model), bị loại cả cặp. Harbor vẫn chấm sau các lỗi này nên chúng có điểm 0. Nếu không loại, việc ở ranh giới hết hạn mức sẽ nghiêng về bản trơn, vì trong mỗi việc bản trơn chạy trước.
- Bản có agent-stack ghi `.agent/LAST-TURN.md` và `.agent/.gitignore` vào thư mục việc (hành vi thật của hook). Grader nào kiểm danh sách file thì có thể chấm trượt vì chuyện này: đọc từng việc "kém hơn" để biết.
- Lượt hết giờ mà grader vẫn chấm thì tính như kết quả thật, vì chậm hơn cũng là một cái giá.
- 20 cặp chỉ đủ thấy chênh lệch lớn. Muốn thấy chênh 10 điểm cần khoảng 160–235 cặp: chạy thêm việc, hoặc thêm `--attempts` khi sinh cấu hình. Bộ thử dùng để kiểm đường ống chạy đúng và để ước chi phí cho lượt lớn.

## File

- `agent_stack_agents.py`: hai lớp agent Harbor, kế thừa agent `claude-code` có sẵn. Chạy trong venv của Harbor trên TUF, nên là ngoại lệ của luật "chỉ thư viện chuẩn"; bộ test của repo không import file này.
- `harbor_bench.py`: sinh cấu hình job (JSON) và so kết quả. Chỉ dùng thư viện chuẩn; test ở `tests/test_harbor_bench.py`.
- `tuf.sh`: các bước ở bảng trên, chạy qua ssh (`HARBOR_HOST`, mặc định `tuf`; `HARBOR_DIR`, mặc định `harbor-eval`).
- `tasks-pilot.txt`: bộ việc thử.
