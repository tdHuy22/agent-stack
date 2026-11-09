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
| `tblite` | `openthoughts/openthoughts-tblite` | 100 (60 nhãn medium/hard/extreme vào job lớn) | `latest` lúc `data` chạy; `data` ghi mã băm nội dung vào `datasets/tblite.lock.json`, lần sau tải khác thì dừng. Đặt `TBLITE_REF` để ghim digest |
| `swerebench` | `swe-rebench/swe-rebench-leaderboard` (860 việc Python, image dựng sẵn) | 25 của tháng mới nhất, vào cả pilot lẫn job lớn | digest `sha256:ebe7444e…` (ghi trong `harbor_bench.py`, lấy từ trang registry của inspect_harbor) cộng mã băm nội dung |

- `harbor_bench.py` gọi `harbor download "<bộ>@<ref>" --export`, gom thư mục việc thành `datasets/<khóa>/<tên việc>` (cấu trúc xuất khác nhau không sao: tìm mọi thư mục có `task.toml`), rồi chạy job trên thư mục cục bộ đó. Nhờ vậy mọi bước kiểm (an toàn, tháng của việc) đọc đúng file sẽ chạy.
- SWE-rebench: ngày tạo của từng việc nằm trong `tests/config.json` (`created_at`) của việc. `tuf.sh pick` lấy tháng mới nhất có ít nhất 25 việc sạch rồi rút bằng `random.Random(20261106).sample` và ghi `tasks-swerebench.txt` kèm mã băm bộ việc, đếm theo tháng. **File này hiện chưa có tên việc**, vì phiên dựng không tải được bộ việc; làm bước `pick` ở dưới trước khi chạy pilot.
- Việc có file compose: Harbor chạy `docker compose` với `--project-directory <việc>/environment`, nên compose của việc đọc được file trên TUF qua đường dẫn tương đối cố định (`env_file: ../../../../.env` tới khóa trong `~/harbor-eval/.env`, `secrets`/`configs` với `file:` tới `~/.ssh/…`, `build.context`, `include`, `extends`, `volumes_from`, `driver_opts`…), và YAML có quá nhiều cách viết cho cùng một việc để lọc bằng mẫu chữ. Vì vậy **mọi việc có file compose bị loại**: tên chứa `compose` với đuôi `.yml`/`.yaml` ở bất kỳ đâu, hay bất kỳ `.yml`/`.yaml` nào trong `environment/`. `data` và `vet` in số việc bị loại và tên (kèm `datasets/<khóa>.rejected.txt` có sha256 của từng file) để bạn biết bộ việc bị bớt bao nhiêu. Việc nào bạn đã đọc tay và muốn giữ thì thêm dòng `<tên việc> <sha256 file compose>` vào `compose-allow.txt` (mỗi file compose một dòng; file đổi nội dung thì băm đổi và việc lại bị loại). Bản commit của danh sách đó trống. Dockerfile và `task.toml` vẫn qua các kiểm cũ (mục An toàn).
- Lời giải mẫu: bước `oracle` chạy lời giải mẫu trên đúng bộ việc của pilot. `filter` chỉ giữ cho job lớn việc mà lời giải mẫu đạt ít nhất một lần (mục Chọn việc); `compare --oracle` cũng loại việc chưa đạt lần nào. Bản cũ ghi 27 việc TBLite chỉ in "no solution written"; chưa kiểm trên bản Hub hiện tại, `oracle` sẽ lộ ra.
- Tên việc: Harbor đặt `task_name` trong `result.json` theo `[task] name` (dạng `org/tên` với gói Hub), còn thư mục xuất và `task_names` của job dùng tên ngắn. `load_trials` cắt phần `org/`, nên `compare`, `pilot-report` và lời giải mẫu dùng cùng một tên (có test với `org/abc`).

## Bộ tiếng Việt

Bộ thứ ba `vi` là 30 bài tiếng Việt tự viết trong `evals/vi-bench/`; cách viết và tự kiểm nằm ở [`../vi-bench/README.md`](../vi-bench/README.md). Bộ này không tải từ Hub. `tuf.sh sync` đưa bản của HEAD lên máy Linux, rồi `tuf.sh data vi` gom bài vào `datasets/vi` và ghim mã băm theo commit; mã băm này vào meta của từng job. `select` lấy cả bộ, giống SWE-rebench. Pilot và lời giải mẫu tự chạy cả bộ khi đã gom. `tuf.sh compare` in thêm một bảng riêng cho các bài trong `tasks-vi.txt`.

## Chọn việc: theo độ khó công bố, không theo kết quả của bản nào

Chọn việc theo kết quả của một bản (ví dụ pilot bản trơn) làm lệch phép so cỡ vài điểm: việc "plain đạt" bị loại là việc plain đã chắc đạt, nên chênh lệch còn lại nghiêng về một phía. Vì vậy job lớn lấy việc theo nhãn độ khó mà bộ đo công bố, không dựa vào lượt chạy nào:

- **TBLite:** mọi việc có nhãn `medium`, `hard` hay `extreme`. OpenThoughts gắn nhãn theo tỉ lệ đạt của Haiku 4.5 (easy ≥70%: 40 việc; medium 40–69%: 26; hard 10–39%: 26; extreme <10%: 8, theo README của bộ). Việc `easy` bị bỏ vì ở đó mọi cấu hình đạt gần hết nên không phân biệt được. Dự kiến 60 việc.
- **SWE-rebench:** cả 25 việc đã chọn ở `tasks-swerebench.txt` (nhãn độ khó của adapter SWE-rebench không có nghĩa, nên không lọc).
- `tuf.sh select` chạy trên TUF (nhãn nằm trong `task.toml` của việc đã tải) và ghi `tasks-candidates.txt` về Mac. `task_difficulty()` tìm khóa `difficulty` trong `task.toml` (bảng `[metadata]`, `[task]`, gốc, rồi tìm sâu), rồi nhãn nằm trong `tags`, rồi các file JSON nhỏ cạnh `task.toml`. **Chưa thấy file `task.toml` thật của TBLite**, nên đoạn đọc nhãn là phỏng đoán linh hoạt: nếu không đọc được nhãn nào, `select` dừng với lỗi và bảo xem một `task.toml` thật rồi sửa hàm; việc không có nhãn bị bỏ và được liệt kê.
- **Lọc theo lời giải mẫu** (bạn chốt 07/11/2026): `tuf.sh filter` gộp mọi lần chạy lời giải mẫu trên TUF (`jobs/*-oracle`) và ghi `tasks-main.txt`: chỉ việc ứng viên mà lời giải mẫu đạt ít nhất một lần. Việc lời giải mẫu chạy mà trượt (21 việc TBLite chỉ in "no solution written", vài việc môi trường hỏng sẵn) bị bỏ, vì ở đó không cấu hình nào đạt được và việc chỉ làm loãng phép so. Việc chưa chấm được lần nào (chỉ hỏng vì Docker) vào `tasks-recheck.txt`; chạy `tuf.sh oracle recheck --yes` rồi `filter` lại. Đây là lọc theo chính việc (grader và môi trường), không theo kết quả của cấu hình nào, nên không làm lệch phép so. Lần chạy oracle phải cùng mã băm bộ việc với nhau và với bộ việc hiện tại, không thì `filter` từ chối.
- Job lớn: 4 cấu hình × `tasks-main.txt` × N lần (`--attempts N`, mặc định 1). Số lượt = việc × 4 × N.

**Pilot giờ chỉ để đo chi phí mỗi lượt và độ bão hòa.** Bản `plain` chạy một lần trên toàn bộ việc (TBLite 100 + SWE-rebench 25). `tuf.sh pilot-report` (sau `fetch pilot`) in tỉ lệ đạt và chi phí trung vị theo nhãn độ khó, và ước chi phí job lớn. Nhóm nào bão hòa (từ 95% đạt, ít nhất 5 lượt) thì `pilot-report` chỉ **in gợi ý**; `tasks-main.txt` không đổi, bạn quyết định có bỏ nhóm đó không.

## Docker sập giữa job: thử lại và dựng image lần lượt

Ca 07/11/2026 trên tuf: lần chạy lời giải mẫu thứ ba có 37 trên 123 lượt hỏng vì containerd hay dockerd sập (4 lần trong khoảng 35 phút), phần lớn lúc 3 lượt cùng dựng image. Nguyên nhân gốc chưa rõ (RAM đã kiểm nhiều lần không lỗi). Hai chốt trong cấu hình job, như nhau cho mọi cấu hình:

- **Thử lại tối đa 2 lần** lượt hỏng vì hạ tầng (`RETRY` trong `harbor_bench.py`): chỉ bốn loại ngoại lệ `RuntimeError` (lệnh docker compose hỏng), `EnvironmentStartTimeoutError`, `AgentSetupTimeoutError`, `AgentInstallError` (cài Claude Code hỏng cả lần cài lại đi thẳng, xem dưới); không bao giờ theo điểm. Harbor so đúng tên lớp, nên agent thoát lỗi (`NonZeroAgentExitCodeError`) không được thử lại. Lỗi API (hạn mức, quá tải) cũng không. Lượt hỏng giữa lúc agent đang làm thì lần chạy lại tốn thêm hạn mức, tối đa 1 USD mỗi lượt. Harbor xóa thư mục lượt hỏng trước khi thử lại; `tuf.sh status` đếm số lần thử lại từ `job.log`.
- **Cài lại một lần khi bước cài của Harbor hỏng** (`_Probed.install` trong `agent_stack_agents.py`, cả bốn cấu hình): chờ 30 giây, hoàn tất dpkg dở, gỡ proxy apt-cacher-ng, xóa phần tải dở (giữ danh sách gói), cài lại đi thẳng; vẫn hỏng thì báo `AgentInstallError` để Harbor chạy lại cả lượt. Ca 08/11/2026: apt-cacher-ng giữ file `InRelease` ghép lẫn hai bản (180 byte đầu của bản mới, phần còn lại và chữ ký của bản cũ, cùng độ dài), apt báo `BADSIG`, 13/25 lượt đầu pilot hỏng trước khi gọi model. Kiểm bộ đệm: chép `InRelease` trong `/var/cache/apt-cacher-ng/*/dists/*/` ra rồi `gpgv --keyring /usr/share/keyrings/debian-archive-keyring.gpg` trong một container Debian.
- **Dựng image lần lượt** (`serial_build_env.py`, nạp qua `environment.import_path`): cả job chỉ một lệnh `docker compose build` chạy một lúc; agent và chấm điểm vẫn chạy 3 lượt song song. Không giữ sẵn image được: 25 image nền SWE-rebench nặng khoảng 41 GB nén, ổ còn 15 GB, và BuildKit tự dọn cache khi ổ còn dưới 28 GB. Giờ chờ tới lượt dựng tính vào hạn dựng của Harbor, nên hệ số hạn dựng là 4.
- **Watcher tự dọn cache dựng** khi ổ còn dưới 30 GB (`HARBOR_MIN_FREE_GB`): `docker builder prune` cho cache không dùng trong 30 phút qua (giữ cache mới để các lượt cùng việc dựng lại nhanh); ổ dưới 2/3 ngưỡng (20 GB) thì dọn mọi cache không dùng. Mỗi lần dọn ghi một dòng vào `jobs/<tên>.watch.log`. Ca 09/11/2026 11:30: image SWE-rebench 5,9 GB mỗi việc làm cache mới tích 14 GB trong chưa tới 30 phút, ổ xuống 17 GB mà lần dọn theo tuổi xóa 0 B; `docker builder prune -f` không lọc xóa được 14 GB. Ca 09/11/2026: cache tích 7,8 GB sau 110 lượt, BuildKit không tự dọn kịp, ổ đầy khi một lượt đang dựng image và 3 container đang chạy, Harbor dừng cả job (`OSError: No space left on device`). `oracle`, `pilot`, `run`, `resume` cũng từ chối khởi chạy khi ổ còn dưới ngưỡng đó (`--force` bỏ qua).
- **Chạy tiếp job dừng giữa chừng** (`tuf.sh resume <tên> --yes`): `harbor jobs resume` bỏ qua lượt đã có `result.json` và chạy lại lượt bị hủy (`CancelledError`). Job giữ bản chép agent-stack của nó (`jobs/<tên>.payload`), nên kết quả không lẫn hai commit; log nối thêm vào log cũ. Lệnh đó của Harbor không có `--env-file`, nên `harbor_bench.py resume-exec` nạp `.env` bằng đúng hàm `harbor run --env-file` dùng (`load_dotenv`, override) rồi gọi harbor, vẫn sau `env -i` của `run_harbor.sh`. Job lời giải mẫu (`<tên>-oracle`) không nạp `.env`. Harbor che giá trị env có tên giống khóa thành `****` khi lưu `config.json` (cả của job lẫn từng lượt; `CLAUDE_FORCE_OAUTH` bị che vì chứa OAUTH), nên `resume-exec` ghi lại giá trị từ `configs/<tên>.json` trước khi gọi harbor (ca 09/11/2026: không khôi phục thì Harbor dừng với "cannot parse '****' as bool"). Lượt có `result.json` rỗng (Harbor bị giết lúc đang ghi) được dời sang `jobs/<tên>.incomplete/`.
- **Dọn ổ** (`tuf.sh prune --yes`): container và image Harbor bỏ lại khi Docker sập giữa lượt, image `swerebench/sweb.eval*`, và cache dựng. Ổ trên 28 GB trống thì BuildKit không dọn cache giữa chừng, nên 4 cấu hình của một việc (Harbor xếp chúng liền nhau) dùng chung một lần kéo image nền.

## Làm theo thứ tự này (từ Mac, ở gốc repo)

| Bước | Lệnh | Tốn gì |
|---|---|---|
| 0. Cài Harbor đã ghim vào `~/harbor-eval/.venv`; tạo `.env` rỗng chmod 600 | `evals/harbor/tuf.sh setup` | không |
| 1. Bạn đặt khóa vào `.env` (mục "Khóa đăng nhập" dưới) | tự làm | không |
| 2. Đưa bản chép (3 biến thể), agent, script, danh sách việc lên TUF | `evals/harbor/tuf.sh sync` | không |
| 3. Tải hai bộ việc, ghim mã băm, loại việc vi phạm (kể cả có file compose chưa duyệt) | `evals/harbor/tuf.sh data` | mạng, ổ đĩa |
| 4. Chọn 25 việc SWE-rebench, ghi `tasks-swerebench.txt` | `evals/harbor/tuf.sh pick`, commit | không |
| 5. Sinh `tasks-candidates.txt` từ nhãn độ khó | `evals/harbor/tuf.sh select`, đọc, commit, rồi `evals/harbor/tuf.sh sync` lại | không |
| 6. Kiểm sẵn sàng (phiên bản, `.env`, ổ, cấu hình) | `evals/harbor/tuf.sh check` | không |
| 7. Lời giải mẫu: kiểm grader và Docker (không nạp `.env`) | `evals/harbor/tuf.sh oracle --yes` | CPU, mạng của TUF; không gọi model |
| 7b. Lọc: `tasks-main.txt` = việc lời giải mẫu đạt; việc chưa chấm được vào `tasks-recheck.txt` | `tuf.sh filter`, đọc, commit, `tuf.sh sync`; còn việc chờ thì `tuf.sh oracle recheck --yes` rồi `filter` lại | không |
| 8. Pilot: in số lượt và trần chi phí (không `--yes` thì chỉ in) | `evals/harbor/tuf.sh pilot --yes` | hạn mức Claude: 125 lượt, trần 125 USD niêm yết |
| 9. Theo dõi | `evals/harbor/tuf.sh status pilot` | không |
| 10. Kéo về (cả `pilot` lẫn `pilot-oracle`), xem chi phí và độ bão hòa | `tuf.sh fetch pilot`, `tuf.sh pilot-report` | không |
| 11. Job lớn | `evals/harbor/tuf.sh run main --attempts 2 --yes` | hạn mức Claude: việc × 4 × N lượt |
| 12. Khi đã có vài lượt xong: kiểm luật thật sự được nạp ở 4 lượt của một việc (mục "Kiểm luật được nạp") | `tuf.sh fetch main`, đọc transcript | không |
| 13. Khi job xong: kéo về, so | `tuf.sh fetch main`, `tuf.sh compare main` | không |

- `oracle`, `pilot`, `run`, `resume` chạy nền trên TUF, thoát ssh thì job vẫn chạy. Cùng với `data`, `sync` và `prune`, các lệnh này từ chối khi có job đang chạy (`jobs/*.pid` còn sống; không có `--force`), và từ chối khi TUF đang bận: còn container khác, một tiến trình khác dùng trên 1 nhân (như llama-server của bench pi-agent), GPU bận từ 20%, tải 1 phút quá 1/4 số nhân, hay RAM trống dưới 12 GB. Thêm `--force` để chạy bất chấp.
- Mỗi lúc chạy 3 việc (TUF có 15 GB RAM). Việc SWE-rebench khai tới 8 GB mỗi việc; giới hạn đó là trần, không phải mức chiếm thường xuyên.
- Job trùng tên đã có thì lệnh từ chối. Xóa `jobs/<tên>` cùng `.payload`, `.meta.json`, `.log`, `.pid`, hay đổi tên.
- `run` chép bản chép sang `jobs/<tên>.payload` và job dùng bản đó, nên `sync` giữa lúc job đang chạy không đổi được job. `jobs/<tên>.meta.json` ghi phiên bản đã ghim (Harbor, Claude Code, commit bản chép, mã băm bộ việc, nhãn độ khó từng việc, và `pip freeze` của venv Harbor). `compare` từ chối gộp khi khác phiên bản, nhưng chỉ **cảnh báo** khi `pip freeze` khác (phụ thuộc của Harbor chưa ghim băm).

## Khóa đăng nhập (bước của bạn)

Claude Code trong container dùng gói Max của bạn qua một khóa dài hạn. Agent không được nhập hay đọc khóa, nên bước này bạn tự làm. Dùng khóa riêng cho đợt đo và thu hồi ngay khi đo xong (bạn đã chấp nhận rủi ro khóa nằm trong môi trường container lúc chạy; xem TM-73).

1. Trên Mac, chạy `claude setup-token` và làm theo hướng dẫn để nhận khóa (dạng `sk-ant-oat01-…`).
2. Trên TUF, mở `~/harbor-eval/.env`, thêm đúng một dòng `CLAUDE_CODE_OAUTH_TOKEN=<khóa>`, rồi `chmod 600 ~/harbor-eval/.env`.

Harbor nạp **cả** `.env` vào môi trường của nó (`load_dotenv(..., override=True)` trong `cli/jobs.py`), rồi môi trường đó đi vào lệnh `docker compose` (`environments/docker/docker.py`). Nên:
- `.env` chỉ được có đúng khóa đó. `tuf.sh pilot`, `run` từ chối khi có dòng nào khác (in số dòng và tên biến, không in giá trị), khi quyền rộng hơn 600, hay khi có `.env.local` (Harbor tự nạp file đó ở thư mục hiện tại). `check` báo cùng các điều này.
- `oracle` không nạp `.env` (không có `--env-file`): lời giải mẫu không cần khóa.
- Harbor chạy qua `run_harbor.sh`, tức `env -i` với danh sách cho phép (`PATH`, `HOME`, `USER`, `LANG`, `TMPDIR`, `DOCKER_*`, `XDG_RUNTIME_DIR`, `*_PROXY`, `AGENT_STACK_PAYLOAD`, `PYTHONPATH`), để biến lạ của phiên ssh (khóa dịch vụ khác trong `.bashrc`…) không lọt vào lệnh compose. Danh sách này chưa thử với Harbor thật (chỉ với harbor giả trong test): nếu `harbor run` báo thiếu biến, thêm tên biến vào danh sách trong `run_harbor.sh`.

Cấu hình job chỉ đặt `CLAUDE_FORCE_OAUTH=1`; Harbor đọc khóa từ `.env` qua `--env-file`. Script không bao giờ in giá trị khóa.

## An toàn (threat model TM-73 đến TM-77 trong `.agent/threat-model.md`)

| Mã | Chốt chặn | Nơi kiểm |
|---|---|---|
| TM-73 khóa lộ | Khóa chỉ ở `.env` chmod 600 trên TUF, và `.env` không có khóa nào khác; `oracle` không nạp `.env`; Harbor chạy với môi trường lọc. `export` che mọi chuỗi `sk-ant-…` (cả `sk-ant-oat01-…`), giá trị của `CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, **và giá trị khóa thật đọc từ `.env` cùng các dạng base64 của nó** (ở cả ba độ lệch), trong mọi file xuất; không theo symlink; quét lại sau khi che (mọi file, kể cả nhị phân) và dừng, xóa bản chép nếu còn. Mac quét lại bằng đúng mẫu đó (`harbor_bench.py residual`) cho cả job lẫn job oracle: chuỗi ngắn như `sk-ant-xxx` trong một repo không làm xóa bản kéo về. Đoạn log mà `status` in ra qua `scrub` (che khóa, bỏ ký tự điều khiển). Không chặn được việc đo gửi khóa ra mạng lúc chạy | `ExportTests`, `TufBehaviourTests` |
| TM-74 việc đo vi phạm | **Mặc định từ chối mọi việc có file compose** (xem mục Bộ việc; danh sách duyệt tay `compose-allow.txt` theo tên việc và sha256). Dockerfile và `task.toml` vẫn kiểm: `docker.sock`, `--security=insecure`, `--network=host`, symlink trỏ ra ngoài, và `${…}` trong `env`/`headers` của `task.toml` (Harbor mở biến của máy chủ như khóa đăng nhập vào container). `data` loại việc vi phạm; `pilot`/`run` kiểm lại đúng các việc sẽ chạy và dừng nếu còn | `VetTests` |
| TM-75 phiên bản | Harbor `0.25.0` cài từ wheel đã kiểm sha256; Claude Code `2.1.311` trong cấu hình job; bộ việc ghim mã băm. `compare` từ chối gộp lượt khác phiên bản Claude Code (đọc từ sự kiện init của chính lượt chạy), khác commit bản chép, hay khác nội dung bộ việc; cảnh báo khi `pip freeze` khác | `CompareTests`, `TufScriptTests` |
| TM-76 bản chép | Chỉ `.agent-stack-root plugin global routing-table.md vetted.lock`; `build-payload` kiểm lại: không `.agent/`, `PLAN.md`, `state/`, `.env*`, `.git`, symlink… | `PayloadTests` |
| TM-77 hạn mức | `--max-budget-usd 1` mỗi lượt; `plan` in số lượt và trần chi phí, lệnh chỉ chạy khi có `--yes`; `watch` chạy nền cùng job, dừng cả nhóm tiến trình khi lượt lỗi hạn mức hay rate limit vượt 3; sau khi khởi động, script kiểm cả harbor lẫn watcher còn sống, không thì dừng job; `compare` đếm các lượt này | `WatchTests`, `StatusTests`, `TufBehaviourTests` |

**Dừng job:** `tuf.sh stop <tên>` gửi SIGTERM cho cả nhóm tiến trình, chờ 20 giây rồi liệt kê container còn chạy (script không tự dừng container, vì có thể của người khác; dừng bằng `docker stop <tên>`). `tuf.sh status` hiện số lượt lỗi hạn mức, harbor và watcher còn sống không (cảnh báo khi watcher đã chết), và đoạn cuối log đã lọc. `jobs/<tên>.stopped` xuất hiện khi `watch` đã tự dừng job.

## Dung lượng

TUF còn khoảng 46 GB ổ trống. Image SWE-rebench nặng (mỗi việc một image riêng, vài GB). Harbor dọn container, volume và image dựng cục bộ sau mỗi lượt (`environment.delete`, mặc định bật; cấu hình job đặt rõ), nhưng image gốc `swerebench/sweb.eval…` kéo từ Docker Hub vẫn nằm lại. `tuf.sh check` báo ổ trống và từ chối coi là ổn dưới 30 GB (ngưỡng khởi chạy, xem trên); `tuf.sh prune --yes` xóa các image đó khi không có container nào chạy (kéo lại khi chạy tiếp). 25 việc SWE-rebench chỉ cần 25 image.

## Đọc kết quả

`compare` in cho từng bản: tỉ lệ đạt; token vào, cache, ra; chi phí và chi phí mỗi lượt đạt; thời gian; số lần gọi subagent (riêng subagent của agent-stack) và skill; lượt lỗi, lượt chạm trần ngân sách, lượt bỏ vì hạ tầng (kèm lỗi hạn mức/rate limit); lượt thiếu hook. Rồi năm phép so cặp trên tập việc chung của mọi bản, mỗi phép có số việc kém hơn, tốt hơn và p của kiểm dấu chính xác trên các việc lệch nhau. Với một lượt mỗi việc đó chính là McNemar chính xác (báo cáo ghi "McNemar chính xác"); với nhiều lượt mỗi việc, so tỉ lệ đạt từng việc rồi đếm việc hơn, kém, bỏ việc bằng nhau (báo cáo ghi "kiểm dấu chính xác theo tỉ lệ đạt từng việc"); cùng một hàm tính:

- `stack`, `nohooks`, `noagents` so với `plain`: bật agent-stack có tốt hơn không, và bản bớt một phần có khác không.
- `stack` so với `nohooks`, và `stack` so với `noagents`: hook, hay subagent, có đóng góp thêm không.
- p chưa hiệu chỉnh; `compare` in luôn ngưỡng Bonferroni cho năm phép.

Cách tính:
- **Một** lượt không có điểm (môi trường hỏng) hay hỏng vì hạ tầng (hết hạn mức, rate limit, quá tải, xác thực, mạng, sai tên model, lỗi 5xx, lỗi API không phân loại được) ở bất kỳ bản nào loại cả việc khỏi mọi phép so, dù các lượt còn lại của việc đó chấm được (kể cả khi `--attempts` từ 2). Harbor vẫn chấm sau các lỗi này nên chúng có điểm 0; không loại thì việc ở ranh giới hết hạn mức nghiêng về một phía.
- Việc có container thiếu python3 từ 3.9 bị loại khỏi tập chung (hook của bản 2 và 4 không chạy). Số lượt thiếu hook được in để biết đã loại bao nhiêu.
- Lượt hết giờ hay chạm trần ngân sách mà grader vẫn chấm tính như kết quả thật, vì chậm hơn hay tốn hơn cũng là một cái giá.
- Kiểm tính đúng định nghĩa của từng bản: sự kiện init của Claude Code (plugin nạp chưa, subagent của agent-stack có hiện không) và `agent-stack-env.txt` do agent ghi (có `hooks.json`, `agents/`, CLAUDE.md cấp người dùng không). Lệch thì `compare` in ⚠️; bản trơn thấy agent-stack thì kết quả không dùng được.
- `bản bỏ hook` và `bản bỏ subagent` được xác nhận bằng cấu trúc thật trong container, không chỉ bằng tên.
- Sức mạnh thống kê: 20 cặp chỉ thấy chênh lệch lớn; chênh 10 điểm cần khoảng 160–235 cặp. Chạy thêm lần (`--attempts`) để bớt nhiễu.

## Đo được, không đo được

- **Đo được** (có mặt ở mọi việc): chữ luật chung và mô tả skill, subagent nạp vào mỗi lần gọi model; hook UserPromptSubmit, PreToolUse, SessionStart, Stop; việc agent có tự gọi skill hay subagent không và gọi bao nhiêu; chi phí, token, thời gian.
- **Chỉ đo được ở một phần:**
  - Cổng chốt việc ở hook Stop (đòi chạy `done-gate`, biên nhận, reviewer) chỉ bật khi thư mục làm việc của Claude Code là repo có thay đổi. SWE-rebench là repo (image đặt repo ở `/testbed`; thư mục làm việc mặc định của Harbor trong image đó chưa kiểm); TBLite phần lớn không phải repo. Nhắc nhở §0 cần `PLAN.md`, nên hầu như không bật ở cả hai.
  - Hook cần `python3` từ 3.9. Image SWE-rebench thường chỉ có Python trong môi trường conda; `compare` và `select` dùng `agent-stack-env.txt` (đo trong container, cùng shell mà Claude Code chạy hook) để biết việc nào hook không chạy.
- **Không đo được (làm số của bản có agent-stack thấp đi hay không liên quan):**
  - Hook `pretool_guard` của agent-stack hỏi trước lệnh không đảo ngược được (`rm -r`, `git push`, `git reset --hard`…) rồi "chờ bạn đồng ý". Bench chạy không người, nên lệnh như vậy bị chặn và agent không có ai trả lời: số của ba bản có hook (stack, noagents) có thể thấp hơn vì chuyện này chứ không vì luật hay skill; bản nohooks không bị. Việc có `rm -r` trong lời giải là hiếm, nhưng đọc các việc "kém hơn" của hai bản có hook xem có dính cổng này không.
  - Lợi ích nối tiếp công việc giữa các phiên (§0, `LAST-TURN.md`, bàn giao) vì mỗi việc chỉ một phiên; lợi ích khi người dùng ở bên cạnh trả lời câu hỏi và duyệt (bench chạy không người, chế độ `bypassPermissions`); chi phí lập kế hoạch và tìm hiểu dự án của người dùng.
- Bản `noagents` bỏ đúng các subagent do agent-stack khai (`reviewer`, `researcher`, `test-runner`, `explore-lite`, `cold-reader`); subagent có sẵn của Claude Code vẫn dùng được, và luật chung vẫn nhắc tên subagent của agent-stack. Nên độ chênh giữa `stack` và `noagents` đo giá trị của các subagent đó cộng với tác động của việc luật nhắc tới thứ không có.
- Chi phí USD là số Claude Code tự ước theo giá niêm yết. Chạy bằng gói thuê bao thì số đó dùng để so các bản, không phải tiền thật.
- Bốn bản dùng cùng model nhưng không cùng prompt hệ thống: bản có agent-stack chạy thêm CLAUDE.md và mô tả skill, nên token vào luôn nhiều hơn. Đó chính là phần "đắt hơn" cần đối chiếu với "tốt hơn".

## Kiểm luật được nạp (ở những lượt đầu của job lớn)

Claude Code của Harbor đọc CLAUDE.md cấp người dùng ở `$CLAUDE_CONFIG_DIR` (Harbor đặt `<logs>/sessions`), không phải `~/.claude`. Agent chép luật vào cả hai nơi và ghi `config_claude_md` và `user_claude_md` vào `agent-stack-env.txt`; `compare` lệch thì báo. Để chứng minh luật thật sự vào prompt, ở 4 lượt của một việc (một lượt mỗi bản): mở transcript của lượt `agent-stack` (`jobs/<tên>/<lượt>/agent/sessions/projects/…/*.jsonl`, hay `claude-code.txt`) và tìm một câu của `SHARED.global.md` (ví dụ "Chất lượng trước chi phí"); lượt `plain` thì không được có câu đó. Sự kiện init trong `claude-code.txt` cũng phải liệt kê plugin `agent-stack` ở ba bản và không ở bản trơn.

## Đã kiểm và chưa kiểm

Đã đọc code Harbor ở tag [v0.25.0](https://github.com/laude-institute/harbor/tree/v0.25.0) (bản ổn định mới nhất trên PyPI, 25/10/2026; sau đó chỉ có bản dev):
- `src/harbor/agents/installed/claude_code.py`: `ClaudeCode` kế thừa `BaseInstalledAgent`. `_resolve_auth_env` và `_should_force_oauth`: có `CLAUDE_FORCE_OAUTH` thì bỏ `ANTHROPIC_API_KEY` và dùng `CLAUDE_CODE_OAUTH_TOKEN`; thiếu khóa thì báo lỗi. `check_model_credentials` kiểm tương tự trước khi xếp lượt. Nên bản 0.25.0 dùng được khóa gói thuê bao đúng như bản cũ, không cần lùi bản. (Bản mới đòi `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` chỉ khi không đặt `CLAUDE_FORCE_OAUTH`.)
- `ClaudeCode.run` gọi `self.build_cli_flags()` (định nghĩa ở `base.py`, biên dịch từ chú thích `Cli(...)` của `ClaudeCodeOptions`: `--effort`, `--max-budget-usd`, `--permission-mode=bypassPermissions`…), đặt `CLAUDE_CONFIG_DIR=<logs>/sessions`, ghi log stream-json vào `<logs>/claude-code.txt`. `install` cài Claude Code bằng bootstrap.sh với đúng `version`.
- `base.py`: `exec_as_agent`, `exec_as_root`; `agents/base.py`: `environment_logs_dir`; `environments/base.py`: `upload_dir`; `AgentConfig.kwargs` bị kiểm nghiêm (`extra="forbid"`) nên chỉ `version`, `reasoning_effort`, `max_budget_usd` được dùng; `AgentInfo.version` ghi phiên bản vào `result.json`.
- `cli/jobs.py`: `harbor run` có `-c/--config`, `--env-file`, `-q`, `-y`, `--print-config`. Harbor cũng tự nạp `.env.local` ở thư mục hiện tại (không dùng ở đây, đừng tạo file đó).
- `models/job/config.py`: `DatasetConfig` nhận `path` + `task_names`; `JobConfig` có `n_concurrent_trials`, `retry`, `environment`.
- Theo hai reviewer (đối chiếu v0.25.0), `cli/jobs.py` nạp `.env` bằng `load_dotenv(override=True)` và `docker.py` đưa `os.environ` vào compose, với `--project-directory <việc>/environment`; `models/task/task.py` đặt `task_name = config.task.name`. Chính tôi đã thấy `load_dotenv` và `.env.local` trong `cli/jobs.py`; các chi tiết còn lại chưa tự đọc lại.
- Hook của agent-stack: chạy thật cả 8 hook bằng `/usr/bin/python3` 3.9.6, kết quả giống hệt Python 3.11; test dùng `ast.parse(feature_version=(3, 9))` trên `plugin/hooks` và `plugin/lib` (không `match`, không `tomllib`). Python 3.8 chưa kiểm (máy không có), nên ngưỡng ghi là 3.9.
- Registry: tên bộ việc `openthoughts/openthoughts-tblite` (100 việc) và `swe-rebench/swe-rebench-leaderboard` (860 việc), `harbor download` có `--export` và `--output-dir` (docs Harbor, trang registry).

**Chưa kiểm được** (phiên dựng không chạy Harbor, không tải gì, không ssh):
- Chưa chạy lần nào, kể cả `harbor run` thật: cấu hình job chưa qua `JobConfig` (có `tuf.sh check` và `validate-config` để kiểm trên TUF), lớp agent chưa được import cùng Harbor (test chỉ đọc cú pháp).
- Cấu trúc thư mục `harbor download --export` cho bộ việc, và việc `download` nhận được `@sha256:…`: `flatten` chấp nhận mọi độ sâu, còn ref sai thì `data` lỗi ngay.
- Claude Code `2.1.311` có tải được bằng bootstrap.sh, và các tên trường của log stream-json mà `compare` đọc (`claude_code_version`, `plugins`, `agents` trong sự kiện init; `Task`/`Agent`/`Skill` trong `tool_use`; `error_max_budget_usd` trong `result`). Thiếu trường thì thống kê tương ứng trống, không sai.
- Tên lỗi `ApiRateLimitError`… là của `base.py` v0.25.0 (đã đọc). Việc sự cố hạn mức của gói Max sinh ra đúng các lỗi này chưa thấy.
- Image SWE-rebench có `python3` trong PATH của shell agent hay không: chỉ lộ ra ở pilot.
- Nhãn độ khó của TBLite nằm ở đâu trong `task.toml` (xem mục Chọn việc); và `env -i` với danh sách cho phép trong `run_harbor.sh` có đủ cho Harbor thật không.
- `ssh` thật: test dùng `ssh` giả chạy cục bộ (có `cat |` để stdin là ống) và harbor giả; kiểm hành vi của script, không kiểm Docker hay Harbor.
- 25 việc SWE-rebench: chưa chọn (xem trên).

## File

- `agent_stack_agents.py`: bốn lớp agent Harbor, kế thừa agent `claude-code` có sẵn. Chạy trong venv của Harbor trên TUF, nên là ngoại lệ của luật "chỉ thư viện chuẩn"; bộ test của repo không import nó.
- `harbor_bench.py`: bản chép, cấu hình job, kiểm việc, chọn việc, `watch`, `export`, `select`, `compare`. Chỉ dùng thư viện chuẩn (cần Python 3.11 cho `tomllib`); test ở `tests/test_harbor_bench.py`.
- `tuf.sh`: các bước ở bảng trên, chạy qua ssh (`HARBOR_HOST`, mặc định `tuf`; `HARBOR_DIR`, mặc định `harbor-eval`).
- `run_harbor.sh`: chạy `harbor run` với môi trường lọc; `compose-allow.txt`: việc có compose đã duyệt tay.
- `tasks-swerebench.txt`: 25 việc SWE-rebench (do `tuf.sh pick` ghi). `tasks-candidates.txt`: việc ứng viên từ nhãn độ khó (do `tuf.sh select` ghi). `tasks-main.txt`: ứng viên mà lời giải mẫu đạt ít nhất một lần, cho job lớn; `tasks-recheck.txt`: ứng viên chưa chấm được lần nào (cả hai do `tuf.sh filter` ghi). `serial_build_env.py`: môi trường Docker dựng image lần lượt.
