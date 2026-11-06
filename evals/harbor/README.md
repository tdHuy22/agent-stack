# Bench: bật agent-stack có làm Claude Code tốt hơn, hay chỉ đắt hơn

So bốn cấu hình Claude Code trên cùng bộ việc coding có grader tự động, chạy trong Docker trên máy Linux `tuf` bằng [Harbor](https://pypi.org/project/harbor/) (khung chạy benchmark của nhóm Terminal-Bench). Hai bộ việc: OpenThoughts-TBLite (100 việc kiểu Terminal-Bench) và SWE-rebench (việc sửa lỗi thật trong repo Python, tháng mới nhất để model không nhớ đáp án).

Bench này chưa chạy lần nào. Phần đã kiểm và phần chưa kiểm nằm ở mục cuối.

## Bốn cấu hình

Cùng model `anthropic/claude-sonnet-5-5`, effort `medium`, cùng phiên bản Claude Code (ghim `2.1.311`, bản đang chạy trên Mac ngày 06/11/2026). Cả bốn đều dùng được tool Agent và subagent mặc định của Claude Code: bench không chặn tool nào.

| | CLAUDE.md cấp người dùng | Plugin agent-stack | Hook | Subagent riêng của agent-stack |
|---|---|---|---|---|
| 1. `claude-code-plain` | không (xóa nếu image lỡ có) | không | – | – |
| 2. `claude-code-agent-stack` | `global/CLAUDE.global.md` | nạp bằng `--plugin-dir` | đủ | đủ (`reviewer`, `researcher`, `test-runner`, `explore-lite`, `cold-reader`) |
| 3. `claude-code-agent-stack-nohooks` | như 2 | như 2 | **không**: bản chép bỏ `plugin/hooks/hooks.json` | đủ |
| 4. `claude-code-agent-stack-noagents` | như 2 | như 2 | đủ | **không**: bản chép bỏ thư mục `plugin/agents/` |

- Định nghĩa bản 4: bỏ các subagent do agent-stack khai báo. Subagent có sẵn của Claude Code (`general-purpose`, `Explore`…) vẫn dùng được, và luật chung vẫn nhắc tới subagent của agent-stack (model sẽ thấy tên mà không gọi được; đó là một phần của việc "bỏ agents").
- Bản 3 bỏ đúng một file vì `plugin/.claude-plugin/plugin.json` không có trường `hooks` (Claude Code tìm hook ở `hooks/hooks.json`) và không skill hay subagent nào khai hook riêng trong frontmatter. Hai điều này có test (`tests/test_harbor_bench.py`). Script hook vẫn nằm đó, chỉ không được gọi.
- Ba bản có agent-stack chép repo, đúng commit lúc `sync`, vào `$HOME/Documents/Claude/agent-stack` trong container, nên mọi đường dẫn ghi trong luật trỏ đúng như trên Mac. Bản 3 và 4 dựng lúc `sync` từ cùng bản chép đó (`harbor_bench.py build-payload`); `plugin/` thật không bị sửa.
- Cả bốn nằm chung một job. Harbor xen kẽ lượt của các bản, nên tải máy hay giờ trong ngày không lệch về một phía.
- `AGENT_STACK_NO_BACKGROUND=1` (chỉ ở ba bản có agent-stack) tắt việc chạy nền lúc mở phiên: kiểm MCP và tự kéo agent-stack trên cloud. Cả hai chỉ gọi mạng, không đổi gì model thấy.
- Mỗi lượt có `--max-budget-usd 1`. Bản tốn hơn chạm trần sớm hơn: lượt chạm trần tính là kết quả thật của bản đó và được đếm riêng.

## Bộ việc

| Khóa | Bộ trên Harbor Hub | Việc | Ghim |
|---|---|---|---|
| `tblite` | `openthoughts/openthoughts-tblite` | 100 | `latest` lúc `data` chạy; `data` ghi mã băm nội dung vào `datasets/tblite.lock.json`, lần sau tải khác thì dừng. Đặt `TBLITE_REF` để ghim digest |
| `swerebench` | `swe-rebench/swe-rebench-leaderboard` (860 việc Python, image dựng sẵn) | 25 của tháng mới nhất | digest `sha256:ebe7444e…` (ghi trong `harbor_bench.py`, lấy từ trang registry của inspect_harbor) cộng mã băm nội dung |

- `harbor_bench.py` gọi `harbor download "<bộ>@<ref>" --export`, gom thư mục việc thành `datasets/<khóa>/<tên việc>` (cấu trúc xuất khác nhau không sao: tìm mọi thư mục có `task.toml`), rồi chạy job trên thư mục cục bộ đó. Nhờ vậy mọi bước kiểm (an toàn, tháng của việc) đọc đúng file sẽ chạy.
- SWE-rebench: ngày tạo của từng việc nằm trong `tests/config.json` (`created_at`) của việc. `tuf.sh pick` lấy tháng mới nhất có ít nhất 25 việc sạch rồi rút bằng `random.Random(20261106).sample` và ghi `tasks-swerebench.txt` kèm mã băm bộ việc, đếm theo tháng. **File này hiện chưa có tên việc**, vì phiên dựng không tải được bộ việc; làm bước `pick` ở dưới trước khi chạy pilot.
- Lời giải mẫu: bước `oracle` chạy lời giải mẫu trên đúng bộ việc của pilot. Việc nào lời giải mẫu không đạt thì `compare` và `select` tự loại. Bản cũ ghi 27 việc TBLite chỉ in "no solution written"; chưa kiểm trên bản Hub hiện tại, `oracle` sẽ lộ ra.

## Chọn việc: pilot rồi select

Chạy bốn cấu hình trên 125 việc là quá nhiều, và phần lớn việc cho cùng kết quả ở mọi cấu hình (ai cũng đạt, hay không ai đạt) nên không trả lời được câu hỏi. Vì vậy:

1. `pilot`: bản `plain` chạy một lần trên toàn bộ việc (TBLite 100 + SWE-rebench 25).
2. `select` đọc kết quả pilot, ghi `tasks-main.txt` gồm "việc phân biệt". Tiêu chí tự đề xuất, bạn đọc và sửa được:
   - Loại: lượt hỏng vì hạ tầng hay không có điểm; lời giải mẫu không đạt; container không có python3 từ 3.9 (hook không chạy được thì bản 2 và 4 không còn đúng định nghĩa).
   - Một lượt mỗi việc, chi phí (Claude Code tự ước) làm thước đo công sức, so với trung vị của từng bộ: **đạt mà tốn ít công** là "chắc đạt", **trượt mà tốn nhiều công** là "chắc trượt"; cả hai bị loại. Giữ đạt mà tốn công, và trượt mà tốn ít công (agent bỏ sớm hay hiểu sai: dễ đổi kết quả giữa các lần chạy).
   - Từ hai lượt mỗi việc trở lên: giữ việc có tỉ lệ đạt giữa 0 và 1 (không tính hai đầu).
   - Điểm yếu: một lượt chỉ cho tín hiệu mỏng, và giữ lại việc "trượt rẻ" có thể giữ cả việc grader hỏng. Nên chạy `oracle` trước `select`; `--limit N` giới hạn số việc mỗi bộ (rút có hạt cố định) nếu job lớn quá đắt.
3. Job lớn: 4 cấu hình × `tasks-main.txt` × N lần (`--attempts N`, mặc định 1). Số lượt = việc × 4 × N.

## Làm theo thứ tự này (từ Mac, ở gốc repo)

| Bước | Lệnh | Tốn gì |
|---|---|---|
| 0. Cài Harbor đã ghim vào `~/harbor-eval/.venv`; tạo `.env` rỗng chmod 600 | `evals/harbor/tuf.sh setup` | không |
| 1. Bạn đặt khóa vào `.env` (mục "Khóa đăng nhập" dưới) | tự làm | không |
| 2. Đưa bản chép (3 biến thể), agent, script, danh sách việc lên TUF | `evals/harbor/tuf.sh sync` | không |
| 3. Tải hai bộ việc, ghim mã băm, loại việc vi phạm kiểm an toàn | `evals/harbor/tuf.sh data` | mạng, ổ đĩa |
| 4. Chọn 25 việc SWE-rebench, ghi `tasks-swerebench.txt` | `evals/harbor/tuf.sh pick`, commit, rồi `sync` lại | không |
| 5. Kiểm sẵn sàng (phiên bản, quyền `.env`, ổ, cấu hình) | `evals/harbor/tuf.sh check` | không |
| 6. Lời giải mẫu: kiểm grader và Docker | `evals/harbor/tuf.sh oracle --yes` | CPU, mạng của TUF; không gọi model |
| 7. Pilot: in số lượt và trần chi phí (không `--yes` thì chỉ in) | `evals/harbor/tuf.sh pilot --yes` | hạn mức Claude: 125 lượt, trần 125 USD niêm yết |
| 8. Theo dõi | `evals/harbor/tuf.sh status pilot` | không |
| 9. Kéo về (cả `pilot` lẫn `pilot-oracle`), chọn việc | `tuf.sh fetch pilot`, `tuf.sh select`, commit, `tuf.sh sync` | không |
| 10. Job lớn | `evals/harbor/tuf.sh run main --attempts 2 --yes` | hạn mức Claude: việc × 4 × N lượt |
| 11. Kéo về, so | `tuf.sh fetch main`, `tuf.sh compare main` | không |

- `oracle`, `pilot`, `run` chạy nền trên TUF, thoát ssh thì job vẫn chạy. Ba lệnh này từ chối khi TUF đang bận: còn container khác, một tiến trình khác dùng trên 1 nhân (như llama-server của bench pi-agent), GPU bận từ 20%, tải 1 phút quá 1/4 số nhân, hay RAM trống dưới 12 GB. Thêm `--force` để chạy bất chấp.
- Mỗi lúc chạy 3 việc (TUF có 15 GB RAM). Việc SWE-rebench khai tới 8 GB mỗi việc; giới hạn đó là trần, không phải mức chiếm thường xuyên.
- Job trùng tên đã có thì lệnh từ chối. Xóa `jobs/<tên>` cùng `.payload`, `.meta.json`, `.log`, `.pid`, hay đổi tên.
- `run` chép bản chép sang `jobs/<tên>.payload` và job dùng bản đó, nên `sync` giữa lúc job đang chạy không đổi được job. `jobs/<tên>.meta.json` ghi phiên bản đã ghim (Harbor, Claude Code, commit bản chép, mã băm bộ việc).

## Khóa đăng nhập (bước của bạn)

Claude Code trong container dùng gói Max của bạn qua một khóa dài hạn. Agent không được nhập hay đọc khóa, nên bước này bạn tự làm. Dùng khóa riêng cho đợt đo và thu hồi ngay khi đo xong (bạn đã chấp nhận rủi ro khóa nằm trong môi trường container lúc chạy; xem TM-73).

1. Trên Mac, chạy `claude setup-token` và làm theo hướng dẫn để nhận khóa (dạng `sk-ant-oat01-…`).
2. Trên TUF, mở `~/harbor-eval/.env`, thêm dòng `CLAUDE_CODE_OAUTH_TOKEN=<khóa>`. Rồi `chmod 600 ~/harbor-eval/.env`. `tuf.sh pilot` và `run` từ chối nếu quyền rộng hơn 600; `check` báo.

Cấu hình job chỉ đặt `CLAUDE_FORCE_OAUTH=1`; Harbor đọc khóa từ `.env` qua `--env-file`. Script không bao giờ in giá trị khóa.

## An toàn (threat model TM-73 đến TM-77 trong `.agent/threat-model.md`)

| Mã | Chốt chặn | Nơi kiểm |
|---|---|---|
| TM-73 khóa lộ | Khóa chỉ ở `.env` chmod 600 trên TUF. `export` che mọi chuỗi `sk-ant-…` (cả `sk-ant-oat01-…`) và giá trị của `CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN` trong **mọi** file xuất; không theo symlink (mã trong container có thể đặt symlink vào thư mục log); kiểm lại sau khi che và dừng nếu còn; `fetch` kiểm lần nữa trên Mac. Không chặn được việc đo gửi khóa ra mạng lúc chạy | `ExportTests` |
| TM-74 việc đo vi phạm | `harbor_bench.py vet` từ chối: `privileged`, `network_mode`/`pid`/`ipc`/`uts: host`, `cap_add`, `devices`, `seccomp/apparmor=unconfined`, `docker.sock`, gắn đường dẫn tuyệt đối, `~`, `..` hay biến ngoài thư mục việc, `--security=insecure`, symlink trỏ ra ngoài, và `${…}` trong `env`/`headers` của `task.toml` (Harbor mở biến của máy chủ như khóa đăng nhập vào container). `data` loại việc vi phạm; `pilot`/`run` kiểm lại đúng các việc sẽ chạy và dừng nếu còn | `VetTests` |
| TM-75 phiên bản | Harbor `0.25.0` cài từ wheel đã kiểm sha256; Claude Code `2.1.311` trong cấu hình job; bộ việc ghim mã băm. `compare` từ chối gộp lượt khác phiên bản Claude Code (đọc từ sự kiện init của chính lượt chạy), khác commit bản chép, hay khác nội dung bộ việc | `CompareTests`, `TufScriptTests` |
| TM-76 bản chép | Chỉ `.agent-stack-root plugin global routing-table.md vetted.lock`; `build-payload` kiểm lại: không `.agent/`, `PLAN.md`, `state/`, `.env*`, `evals/` ở gốc, `.git`… | `PayloadTests` |
| TM-77 hạn mức | `--max-budget-usd 1` mỗi lượt; `plan` in số lượt và trần chi phí, lệnh chỉ chạy khi có `--yes`; `watch` chạy nền cùng job, dừng cả nhóm tiến trình khi lượt lỗi hạn mức hay rate limit vượt 3; `compare` đếm các lượt này | `WatchTests`, `TufScriptTests` |

**Dừng job:** `tuf.sh stop <tên>` gửi SIGTERM cho cả nhóm tiến trình, chờ 20 giây rồi liệt kê container còn chạy (script không tự dừng container, vì có thể của người khác; dừng bằng `docker stop <tên>`). `tuf.sh status` hiện số lượt lỗi hạn mức. `jobs/<tên>.stopped` xuất hiện khi `watch` đã tự dừng job.

## Dung lượng

TUF còn khoảng 46 GB ổ trống. Image SWE-rebench nặng (mỗi việc một image riêng, vài GB). Harbor dọn container, volume và image dựng cục bộ sau mỗi lượt (`environment.delete`, mặc định bật; cấu hình job đặt rõ), nhưng image gốc `swerebench/sweb.eval…` kéo từ Docker Hub vẫn nằm lại. `tuf.sh check` báo ổ trống và từ chối coi là ổn dưới 25 GB; `tuf.sh prune --yes` xóa các image đó khi không có container nào chạy (kéo lại khi chạy tiếp). 25 việc SWE-rebench chỉ cần 25 image.

## Đọc kết quả

`compare` in cho từng bản: tỉ lệ đạt; token vào, cache, ra; chi phí và chi phí mỗi lượt đạt; thời gian; số lần gọi subagent (riêng subagent của agent-stack) và skill; lượt lỗi, lượt chạm trần ngân sách, lượt bỏ vì hạ tầng (kèm lỗi hạn mức/rate limit); lượt thiếu hook. Rồi năm phép so cặp trên tập việc chung của mọi bản, mỗi phép có số việc kém hơn, tốt hơn và p của McNemar chính xác:

- `stack`, `nohooks`, `noagents` so với `plain`: bật agent-stack có tốt hơn không, và bản bớt một phần có khác không.
- `stack` so với `nohooks`, và `stack` so với `noagents`: hook, hay subagent, có đóng góp thêm không.
- p chưa hiệu chỉnh; `compare` in luôn ngưỡng Bonferroni cho năm phép.

Cách tính:
- Việc có lượt không có điểm (môi trường hỏng) hay hỏng vì hạ tầng (hết hạn mức, rate limit, quá tải, xác thực, mạng, sai tên model, lỗi 5xx) bị loại cả việc ở mọi bản. Harbor vẫn chấm sau các lỗi này nên chúng có điểm 0; không loại thì việc ở ranh giới hết hạn mức nghiêng về một phía.
- Việc có container thiếu python3 từ 3.9 bị loại khỏi tập chung (hook của bản 2 và 4 không chạy). Số lượt thiếu hook được in để biết đã loại bao nhiêu.
- Lượt hết giờ hay chạm trần ngân sách mà grader vẫn chấm tính như kết quả thật, vì chậm hơn hay tốn hơn cũng là một cái giá.
- Nhiều lượt mỗi việc (`--attempts`) thì so tỉ lệ đạt theo việc (hơn, kém, bằng).
- Kiểm tính đúng định nghĩa của từng bản: sự kiện init của Claude Code (plugin nạp chưa, subagent của agent-stack có hiện không) và `agent-stack-env.txt` do agent ghi (có `hooks.json`, `agents/`, CLAUDE.md cấp người dùng không). Lệch thì `compare` in ⚠️; bản trơn thấy agent-stack thì kết quả không dùng được.
- `bản bỏ hook` và `bản bỏ subagent` được xác nhận bằng cấu trúc thật trong container, không chỉ bằng tên.
- Sức mạnh thống kê: 20 cặp chỉ thấy chênh lệch lớn; chênh 10 điểm cần khoảng 160–235 cặp. Chạy thêm lần (`--attempts`) để bớt nhiễu.

## Đo được, không đo được

- **Đo được** (có mặt ở mọi việc): chữ luật chung và mô tả skill, subagent nạp vào mỗi lần gọi model; hook UserPromptSubmit, PreToolUse, SessionStart, Stop; việc agent có tự gọi skill hay subagent không và gọi bao nhiêu; chi phí, token, thời gian.
- **Chỉ đo được ở một phần:**
  - Cổng chốt việc ở hook Stop (đòi chạy `done-gate`, biên nhận, reviewer) chỉ bật khi thư mục làm việc của Claude Code là repo có thay đổi. SWE-rebench là repo (image đặt repo ở `/testbed`; thư mục làm việc mặc định của Harbor trong image đó chưa kiểm); TBLite phần lớn không phải repo. Nhắc nhở §0 cần `PLAN.md`, nên hầu như không bật ở cả hai.
  - Hook cần `python3` từ 3.9. Image SWE-rebench thường chỉ có Python trong môi trường conda; `compare` và `select` dùng `agent-stack-env.txt` (đo trong container, cùng shell mà Claude Code chạy hook) để biết việc nào hook không chạy.
- **Không đo được:** lợi ích nối tiếp công việc giữa các phiên (§0, `LAST-TURN.md`, bàn giao) vì mỗi việc chỉ một phiên; lợi ích khi người dùng ở bên cạnh trả lời câu hỏi và duyệt (bench chạy không người, chế độ `bypassPermissions`); chi phí lập kế hoạch và tìm hiểu dự án của người dùng.
- Chi phí USD là số Claude Code tự ước theo giá niêm yết. Chạy bằng gói thuê bao thì số đó dùng để so các bản, không phải tiền thật.
- Bốn bản dùng cùng model nhưng không cùng prompt hệ thống: bản có agent-stack chạy thêm CLAUDE.md và mô tả skill, nên token vào luôn nhiều hơn. Đó chính là phần "đắt hơn" cần đối chiếu với "tốt hơn".

## Đã kiểm và chưa kiểm

Đã đọc code Harbor ở tag [v0.25.0](https://github.com/laude-institute/harbor/tree/v0.25.0) (bản ổn định mới nhất trên PyPI, 25/10/2026; sau đó chỉ có bản dev):
- `src/harbor/agents/installed/claude_code.py`: `ClaudeCode` kế thừa `BaseInstalledAgent`. `_resolve_auth_env` và `_should_force_oauth`: có `CLAUDE_FORCE_OAUTH` thì bỏ `ANTHROPIC_API_KEY` và dùng `CLAUDE_CODE_OAUTH_TOKEN`; thiếu khóa thì báo lỗi. `check_model_credentials` kiểm tương tự trước khi xếp lượt. Nên bản 0.25.0 dùng được khóa gói thuê bao đúng như bản cũ, không cần lùi bản. (Bản mới đòi `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` chỉ khi không đặt `CLAUDE_FORCE_OAUTH`.)
- `ClaudeCode.run` gọi `self.build_cli_flags()` (định nghĩa ở `base.py`, biên dịch từ chú thích `Cli(...)` của `ClaudeCodeOptions`: `--effort`, `--max-budget-usd`, `--permission-mode=bypassPermissions`…), đặt `CLAUDE_CONFIG_DIR=<logs>/sessions`, ghi log stream-json vào `<logs>/claude-code.txt`. `install` cài Claude Code bằng bootstrap.sh với đúng `version`.
- `base.py`: `exec_as_agent`, `exec_as_root`; `agents/base.py`: `environment_logs_dir`; `environments/base.py`: `upload_dir`; `AgentConfig.kwargs` bị kiểm nghiêm (`extra="forbid"`) nên chỉ `version`, `reasoning_effort`, `max_budget_usd` được dùng; `AgentInfo.version` ghi phiên bản vào `result.json`.
- `cli/jobs.py`: `harbor run` có `-c/--config`, `--env-file`, `-q`, `-y`, `--print-config`. Harbor cũng tự nạp `.env.local` ở thư mục hiện tại (không dùng ở đây, đừng tạo file đó).
- `models/job/config.py`: `DatasetConfig` nhận `path` + `task_names`; `JobConfig` có `n_concurrent_trials`, `retry`, `environment`.
- Hook của agent-stack: chạy thật cả 8 hook bằng `/usr/bin/python3` 3.9.6, kết quả giống hệt Python 3.11; test dùng `ast.parse(feature_version=(3, 9))` trên `plugin/hooks` và `plugin/lib` (không `match`, không `tomllib`). Python 3.8 chưa kiểm (máy không có), nên ngưỡng ghi là 3.9.
- Registry: tên bộ việc `openthoughts/openthoughts-tblite` (100 việc) và `swe-rebench/swe-rebench-leaderboard` (860 việc), `harbor download` có `--export` và `--output-dir` (docs Harbor, trang registry).

**Chưa kiểm được** (phiên dựng không chạy Harbor, không tải gì, không ssh):
- Chưa chạy lần nào, kể cả `harbor run` thật: cấu hình job chưa qua `JobConfig` (có `tuf.sh check` và `validate-config` để kiểm trên TUF), lớp agent chưa được import cùng Harbor (test chỉ đọc cú pháp).
- Cấu trúc thư mục `harbor download --export` cho bộ việc, và việc `download` nhận được `@sha256:…`: `flatten` chấp nhận mọi độ sâu, còn ref sai thì `data` lỗi ngay.
- Claude Code `2.1.311` có tải được bằng bootstrap.sh, và các tên trường của log stream-json mà `compare` đọc (`claude_code_version`, `plugins`, `agents` trong sự kiện init; `Task`/`Agent`/`Skill` trong `tool_use`; `error_max_budget_usd` trong `result`). Thiếu trường thì thống kê tương ứng trống, không sai.
- Tên lỗi `ApiRateLimitError`… là của `base.py` v0.25.0 (đã đọc). Việc sự cố hạn mức của gói Max sinh ra đúng các lỗi này chưa thấy.
- Image SWE-rebench có `python3` trong PATH của shell agent hay không: chỉ lộ ra ở pilot.
- 25 việc SWE-rebench: chưa chọn (xem trên).

## File

- `agent_stack_agents.py`: bốn lớp agent Harbor, kế thừa agent `claude-code` có sẵn. Chạy trong venv của Harbor trên TUF, nên là ngoại lệ của luật "chỉ thư viện chuẩn"; bộ test của repo không import nó.
- `harbor_bench.py`: bản chép, cấu hình job, kiểm việc, chọn việc, `watch`, `export`, `select`, `compare`. Chỉ dùng thư viện chuẩn (cần Python 3.11 cho `tomllib`); test ở `tests/test_harbor_bench.py`.
- `tuf.sh`: các bước ở bảng trên, chạy qua ssh (`HARBOR_HOST`, mặc định `tuf`; `HARBOR_DIR`, mặc định `harbor-eval`).
- `tasks-swerebench.txt`: 25 việc SWE-rebench cho pilot (do `tuf.sh pick` ghi). `tasks-main.txt`: việc phân biệt cho job lớn (do `tuf.sh select` ghi).
