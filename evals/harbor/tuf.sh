#!/bin/sh
# Dựng và chạy bench "Claude Code có và không có agent-stack" (4 cấu hình, TBLite và SWE-rebench) trên TUF qua ssh.
# Chạy từ máy Mac, ở gốc repo agent-stack. Xem evals/harbor/README.md.
#
#   tuf.sh setup                      cài Harbor đã ghim vào ~/harbor-eval/.venv, tạo .env rỗng chmod 600 (lần đầu)
#   tuf.sh sync [--force]             đưa lên TUF: ba bản chép agent-stack, agent Harbor, script, danh sách việc
#   tuf.sh data [vi] [--force]        tải hai bộ việc từ Hub và gom bộ tiếng Việt (đã sync), ghim mã băm, loại việc vi phạm
#                                     kiểm an toàn (kể cả có file compose); `data vi` chỉ gom lại bộ tiếng Việt
#   tuf.sh pick                       chọn 25 việc SWE-rebench tháng mới nhất, ghi evals/harbor/tasks-swerebench.txt
#   tuf.sh select                     sinh evals/harbor/tasks-candidates.txt từ nhãn độ khó (không đọc kết quả nào)
#   tuf.sh check                      kiểm mọi thứ đã sẵn sàng (phiên bản, .env, ổ đĩa, cấu hình); không chạy container
#   tuf.sh oracle [TÊN] [--yes] [--force]
#                                     chạy lời giải mẫu (container, không gọi model, không nạp .env): trên tasks-<TÊN>.txt
#                                     nếu có (oracle recheck: tasks-recheck.txt), không thì trên bộ việc của pilot
#   tuf.sh filter                     gộp mọi lần chạy lời giải mẫu, ghi tasks-main.txt (việc lời giải mẫu đạt ít nhất một
#                                     lần, lấy từ tasks-candidates.txt) và tasks-recheck.txt (chưa chấm được vì hạ tầng)
#   tuf.sh pilot [--yes] [--force]    pilot: bản plain trên mọi việc, 1 lần: đo chi phí và độ bão hòa (gọi model)
#   tuf.sh pilot-report [--attempts N] in tỉ lệ đạt, chi phí theo nhãn độ khó của pilot đã kéo về (chỉ gợi ý)
#   tuf.sh run [TÊN] [--attempts N] [--yes] [--force]
#                                     job lớn: 4 cấu hình × tasks-main.txt × N lần (gọi model)
#   tuf.sh status [TÊN]               tiến độ, harbor và watcher còn sống không, số lượt lỗi hạn mức
#   tuf.sh stop [TÊN]                 dừng job (SIGTERM cả nhóm tiến trình) và liệt kê container còn lại
#   tuf.sh fetch [TÊN]                kéo kết quả về .tmp/harbor-jobs/ (khóa bị che trên TUF trước khi kéo, quét lại trên Mac)
#   tuf.sh compare [TÊN]              so ghép cặp kết quả đã kéo về
#   tuf.sh prune [--yes]              dọn ổ: container, image, network Harbor bỏ lại khi Docker sập, swerebench/sweb.eval*,
#                                     và toàn bộ cache dựng của Docker (kéo, dựng lại khi chạy)
#
# TÊN mặc định: pilot cho oracle và pilot; main cho các lệnh còn lại. oracle, pilot, run, data, sync, prune từ chối khi có job
# đang chạy, và khi TUF đang bận (có container khác, tải hay RAM cao) trừ khi thêm --force; pilot, run, oracle chỉ chạy thật
# khi có --yes (không có thì chỉ in số lượt và trần chi phí). Chạy nền trên TUF: thoát ssh thì job vẫn chạy.
set -eu

HOST=${HARBOR_HOST:-tuf}
REMOTE=${HARBOR_DIR:-harbor-eval}          # tương đối với $HOME trên TUF
HARBOR_VERSION=0.25.0                      # ghim (TM-75); khớp HARBOR_VERSION trong harbor_bench.py
HARBOR_WHEEL_SHA256=51923ac567fc57b03279e93468b105f689628bcac2cd3d541d4e44aa5c0ec309
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
STAGE="$REPO/.tmp/harbor-sync"
LOCAL_JOBS="$REPO/.tmp/harbor-jobs/jobs"
PY=.venv/bin/python
HB="$PY agent-stack/harbor_bench.py"
WATCH_INTERVAL=${HARBOR_WATCH_INTERVAL:-60}

cmd=${1:-}; [ $# -gt 0 ] && shift
NAME=; FORCE=0; YES=0; ATTEMPTS=1
while [ $# -gt 0 ]; do
  case "$1" in
    --force) FORCE=1 ;;
    --yes) YES=1 ;;
    --attempts) [ $# -ge 2 ] || { echo "--attempts cần một số" >&2; exit 2; }; ATTEMPTS=$2; shift ;;
    -*) echo "Không hiểu cờ $1" >&2; exit 2 ;;
    *) NAME=$1 ;;
  esac
  shift
done
case "$ATTEMPTS" in ''|*[!0-9]*|0) echo "--attempts phải là số nguyên từ 1" >&2; exit 2 ;; esac
case "$cmd" in
  pilot|pilot-report) [ -z "$NAME" ] || [ "$NAME" = pilot ] || { echo "Job pilot không đổi tên được" >&2; exit 2; }; NAME=pilot ;;
  oracle) NAME=${NAME:-pilot} ;;
  *) NAME=${NAME:-main} ;;
esac
case "$NAME" in *[!A-Za-z0-9_-]*|'') echo "Tên job chỉ gồm chữ, số, - và _" >&2; exit 2 ;; esac

remote() { ssh "$HOST" "cd \"\$HOME/$REMOTE\" && $1"; }
rsh() { ssh "$HOST" "cd \"\$HOME/$REMOTE\" && sh -s"; }   # script ở stdin

# Bận: có container đang chạy, một tiến trình khác dùng trên 1 nhân (như llama-server của bench pi-agent), GPU bận từ
# 20%, tải 1 phút quá 1/4 số nhân, hay RAM trống dưới 12 GB (3 container × tới 4 GB; TUF có 15 GB).
BUSY_CHECK='n=$(docker ps -q | wc -l); load=$(cut -d" " -f1 /proc/loadavg); cores=$(nproc);
mem=$(awk "/MemAvailable/{print int(\$2/1048576)}" /proc/meminfo);
top=$(ps -eo pcpu=,comm= --sort=-pcpu | grep -v " ps$" | head -1); topcpu=$(echo "$top" | awk "{print int(\$1)}");
gpu=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null | head -1); gpu=${gpu:-0};
echo "container đang chạy: $n · tải: $load / $cores nhân · RAM trống: ${mem} GB · tiến trình nặng nhất: $(echo $top) · GPU: ${gpu}%";
awk -v n="$n" -v l="$load" -v c="$cores" -v m="$mem" -v p="$topcpu" -v g="$gpu" "BEGIN{exit !(n>0 || l>c/4 || m<12 || p>100 || g>=20)}" && echo BUSY || true'

refuse_if_busy() {
  out=$(ssh "$HOST" "$BUSY_CHECK")
  echo "$out" | grep -v '^BUSY$'
  if echo "$out" | grep -q '^BUSY$' && [ "$FORCE" -ne 1 ]; then
    echo "TUF đang bận: chưa chạy. Chờ việc kia xong, hoặc thêm --force nếu chắc chắn." >&2
    exit 3
  fi
}

# Có job còn sống (jobs/*.pid trỏ tới tiến trình đang chạy) thì không đổi bộ việc, bản chép hay image dưới chân nó. Không có --force.
refuse_if_running() {
  running=$(ssh "$HOST" "cd \"\$HOME/$REMOTE\" 2>/dev/null && for p in jobs/*.pid; do [ -f \"\$p\" ] || continue; kill -0 \"\$(cat \"\$p\")\" 2>/dev/null && echo \"\$p\"; done; true")
  if [ -n "$running" ]; then
    echo "Còn job đang chạy ($(echo $running)): chờ xong hay chạy tuf.sh stop trước." >&2
    exit 3
  fi
}

# TM-73: Harbor nạp CẢ file .env vào os.environ (load_dotenv override=True), rồi os.environ đi vào lệnh docker compose. Nên .env chỉ
# được có đúng một khóa, và không được có .env.local (Harbor tự nạp file đó ở thư mục hiện tại). In lý do, không bao giờ in giá trị.
env_problems() {
  ssh "$HOST" "cd \"\$HOME/$REMOTE\" && sh -s" <<'EOF'
[ -e .env.local ] && echo "có file .env.local (Harbor tự nạp): xóa nó"
[ -f .env ] || exit 0
# python-dotenv coi \r đơn là hết dòng còn grep thì không: một dòng có \r có thể giấu khóa thứ hai
if grep -q "$(printf '\r')" .env; then echo ".env có ký tự CR (xuống dòng kiểu Windows hay Mac cũ): lưu lại chỉ với LF"; fi
other=$(grep -vE '^[[:space:]]*(#|$)' .env | grep -v '^CLAUDE_CODE_OAUTH_TOKEN=' | wc -l | tr -d ' ')
if [ "$other" -gt 0 ]; then
  names=$(grep -vE '^[[:space:]]*(#|$)' .env | grep -v '^CLAUDE_CODE_OAUTH_TOKEN=' | grep -oE '^[A-Za-z_][A-Za-z0-9_]*=' | tr -d '=' | tr '\n' ' ')
  echo ".env có $other dòng ngoài CLAUDE_CODE_OAUTH_TOKEN (tên biến: ${names:-không đọc được}): chỉ để đúng một khóa đó"
fi
exit 0
EOF
}

# Script chỉ kiểm có dòng và quyền file, không bao giờ in giá trị.
require_token() {
  remote 'grep -q "^CLAUDE_CODE_OAUTH_TOKEN=." .env 2>/dev/null' || {
    echo "Chưa có CLAUDE_CODE_OAUTH_TOKEN trong ~/$REMOTE/.env trên TUF (bước của bạn, xem README.md)." >&2; exit 1; }
  perm=$(remote 'stat -c %a .env')
  [ "$perm" = 600 ] || { echo "~/$REMOTE/.env có quyền $perm: chạy chmod 600 ~/$REMOTE/.env trên TUF rồi thử lại." >&2; exit 1; }
  problems=$(env_problems)
  [ -z "$problems" ] || { echo "$problems" >&2; exit 1; }
}

# Tạo cấu hình, kiểm an toàn từng việc (TM-74) và in số lượt, trần chi phí (TM-77). $1: pilot|main|oracle, $2: tên job.
prepare_job() {
  kind=$1; job=$2
  # Harbor tự nạp .env.local ở mọi job, kể cả oracle (không qua require_token)
  if remote "test -e .env.local"; then echo "Có ~/$REMOTE/.env.local (Harbor tự nạp vào mọi job): xóa nó." >&2; exit 1; fi
  remote "test -f agent-stack/payload/full/.agent-stack-root" || { echo "Chưa sync: chạy tuf.sh sync" >&2; exit 1; }
  remote "test -d datasets/tblite && test -d datasets/swerebench" || { echo "Chưa có bộ việc: chạy tuf.sh data" >&2; exit 1; }
  if remote "test -e jobs/$job"; then
    echo "jobs/$job đã có trên TUF. Xoá nó (cùng jobs/$job.payload, .meta.json, .log, .pid), hay đổi TÊN." >&2; exit 1
  fi
  case "$kind" in
    # run <TÊN> dùng đúng tasks-<TÊN>.txt (run main: tasks-main.txt; run probe: tasks-probe.txt). Không rơi về
    # tasks-main.txt khi thiếu file: lượt thử nhỏ mà lặng lẽ thành job lớn thì tốn hạn mức.
    main) list="agent-stack/tasks-$job.txt"
      remote "test -f $list" 2>/dev/null || { echo "Chưa có $(basename "$list") trên TUF: tạo evals/harbor/$(basename "$list"), commit rồi tuf.sh sync." >&2; exit 1; }
      tasks_arg="--tasks $list"
      remote "grep -qv '^#' $list" 2>/dev/null || { echo "Chưa có $(basename "$list"): chạy tuf.sh select rồi sync." >&2; exit 1; } ;;
    oracle) list="agent-stack/tasks-$NAME.txt"
      if remote "test -f $list" 2>/dev/null; then
        remote "grep -qv '^#' $list" 2>/dev/null || { echo "$(basename "$list") không có việc nào: không có gì để chạy." >&2; exit 1; }
        tasks_arg="--tasks $list"
      else
        tasks_arg=""
        remote "grep -qv '^#' agent-stack/tasks-swerebench.txt" 2>/dev/null || { echo "Chưa có tasks-swerebench.txt: chạy tuf.sh pick." >&2; exit 1; }
      fi ;;
    *) tasks_arg=""
      remote "grep -qv '^#' agent-stack/tasks-swerebench.txt" 2>/dev/null || { echo "Chưa có tasks-swerebench.txt: chạy tuf.sh pick." >&2; exit 1; } ;;
  esac
  rsh <<EOF
set -e
mkdir -p configs jobs
$HB make-configs --kind $kind --name $job --root . $tasks_arg --swerebench agent-stack/tasks-swerebench.txt --attempts $ATTEMPTS --out configs/$job.json >/dev/null
$HB vet-config configs/$job.json --root . --allow agent-stack/compose-allow.txt
$HB plan configs/$job.json --root .
EOF
}

launch_job() {  # $1: tên job, $2: token (nạp .env: chỉ job gọi model) hay none (lời giải mẫu: không nạp gì)
  job=$1; mode=$2
  [ "$mode" = token ] && require_token
  refuse_if_running
  refuse_if_busy
  # Bản chép agent-stack của job nằm riêng trong jobs/<job>.payload: sync giữa chừng không đổi được job đang chạy, và
  # commit của bản chép đi cùng kết quả. Phần chạy nền tách phiên để ssh trả về ngay; harbor và watch ghi pid vào .pid.
  # run_harbor.sh chạy harbor với môi trường lọc. Sau khi khởi động, kiểm cả harbor lẫn watcher còn sống, không thì dừng job.
  rsh <<EOF
set -e
$HB validate-config configs/$job.json
rm -rf jobs/$job.payload && cp -R agent-stack/payload jobs/$job.payload
$HB meta configs/$job.json --out jobs/$job.meta.json --payload jobs/$job.payload --root .
rm -f jobs/$job.pid jobs/$job.watch.pid
AGENT_STACK_PAYLOAD="\$PWD/jobs/$job.payload" PYTHONPATH="\$PWD/agent-stack" nohup setsid sh -c 'echo \$\$ > jobs/$job.pid; exec sh agent-stack/run_harbor.sh configs/$job.json $mode' > jobs/$job.log 2>&1 < /dev/null &
# chờ file pid tới 20 giây (lần 06/11 chờ cứng 2 giây thì file chưa kịp có, job bị coi là chết và dừng oan)
i=0; hpid=""
while [ \$i -lt 20 ] && [ -z "\$hpid" ]; do sleep 1; i=\$((i+1)); hpid=\$(cat jobs/$job.pid 2>/dev/null || true); done
nohup setsid $PY agent-stack/harbor_bench.py watch jobs/$job --pid "\$hpid" --interval $WATCH_INTERVAL > jobs/$job.watch.log 2>&1 < /dev/null &
wpid=\$!
echo "\$wpid" > jobs/$job.watch.pid
sleep 1
if [ -z "\$hpid" ] || ! kill -0 "\$hpid" 2>/dev/null || ! kill -0 "\$wpid" 2>/dev/null; then
  [ -z "\$hpid" ] || kill -s TERM -- "-\$hpid" 2>/dev/null || true
  echo "✗ harbor hay watcher không chạy sau khi khởi động: đã dừng job. Xem ~/$REMOTE/jobs/$job.log và $job.watch.log" >&2
  exit 1
fi
echo "Đã chạy nền job $job (PID \$hpid, watcher \$wpid), agent-stack commit \$(cat jobs/$job.payload/full/.payload-commit). Log: ~/$REMOTE/jobs/$job.log"
EOF
}

case "$cmd" in
  setup)
    # Wheel của Harbor được kiểm sha256 trước khi cài; phụ thuộc của nó thì pip/uv tự giải (chưa ghim băm; pip freeze vào meta của job).
    ssh "$HOST" 'sh -s' <<EOF
set -e
PATH="\$HOME/.local/bin:\$PATH"
command -v uv >/dev/null 2>&1 || { echo "Cần uv trên TUF (https://docs.astral.sh/uv/)" >&2; exit 1; }
mkdir -p "\$HOME/$REMOTE" && cd "\$HOME/$REMOTE"
[ -x .venv/bin/python ] || uv venv --seed --python 3.12 .venv
mkdir -p wheel && .venv/bin/pip download --no-deps --dest wheel "harbor==$HARBOR_VERSION" >/dev/null
echo "$HARBOR_WHEEL_SHA256  wheel/harbor-$HARBOR_VERSION-py3-none-any.whl" | sha256sum -c -
.venv/bin/pip install "wheel/harbor-$HARBOR_VERSION-py3-none-any.whl"
[ -e .env ] || { umask 077; : > .env; }
chmod 600 .env
.venv/bin/python -c "import importlib.metadata as m; print('Harbor', m.version('harbor'))"
echo "Xong. Việc của bạn: đặt CLAUDE_CODE_OAUTH_TOKEN=<khóa> vào ~/$REMOTE/.env, chỉ khóa đó (xem README.md)."
EOF
    ;;
  sync)
    refuse_if_running
    refuse_if_busy
    dirty=$(git -C "$REPO" status --porcelain -- plugin global routing-table.md vetted.lock .agent-stack-root evals/vi-bench)
    if [ -n "$dirty" ] && [ "$FORCE" -ne 1 ]; then
      echo "plugin/, global/ hay evals/vi-bench/ còn thay đổi chưa commit; bản chép lấy từ HEAD nên sẽ không có chúng:" >&2
      echo "$dirty" >&2; echo "Commit trước, hoặc thêm --force." >&2; exit 1
    fi
    rm -rf "$STAGE"; mkdir -p "$STAGE/src"
    # TM-76: chỉ danh sách cho phép vào bản chép; build-payload dựng thêm bản nohooks, noagents và tự kiểm lại.
    git -C "$REPO" archive HEAD .agent-stack-root plugin global routing-table.md vetted.lock | tar -x -C "$STAGE/src"
    commit=$(git -C "$REPO" rev-parse --short HEAD)
    python3 "$HERE/harbor_bench.py" build-payload "$STAGE/src" "$STAGE/payload" --commit "$commit"
    rm -rf "$STAGE/src"
    # Bộ tiếng Việt cũng lấy từ HEAD (đúng bản đã commit), để mã băm trong meta của job ứng với một commit.
    mkdir -p "$STAGE/vi-src"
    git -C "$REPO" archive HEAD evals/vi-bench | tar -x -C "$STAGE/vi-src"
    mv "$STAGE/vi-src/evals/vi-bench" "$STAGE/vi-bench" && rm -rf "$STAGE/vi-src"
    cp "$HERE/agent_stack_agents.py" "$HERE/serial_build_env.py" "$HERE/harbor_bench.py" "$HERE/run_harbor.sh" \
      "$HERE/compose-allow.txt" "$STAGE/"
    for f in "$HERE"/tasks-*.txt; do [ -f "$f" ] && cp "$f" "$STAGE/"; done
    COPYFILE_DISABLE=1 tar --no-xattrs -C "$STAGE" -cf - . | ssh "$HOST" "mkdir -p \"\$HOME/$REMOTE\" && cd \"\$HOME/$REMOTE\" && rm -rf agent-stack && mkdir -p agent-stack && tar -xf - -C agent-stack"
    echo "Đã đưa lên $HOST:~/$REMOTE/agent-stack: agent-stack commit $commit (full, nohooks, noagents), $(ls "$STAGE" | grep -c '^tasks-') file danh sách việc, $(ls "$STAGE/vi-bench" | grep -c -- '-') bài tiếng Việt (gom bằng tuf.sh data vi)"
    ;;
  data)
    refuse_if_running
    refuse_if_busy
    only_vi=0; [ "$NAME" = vi ] && only_vi=1
    rsh <<EOF
set -e
mkdir -p datasets
[ "$only_vi" -eq 1 ] || $HB datasets | while IFS="\$(printf '\t')" read -r key name ref; do
  echo "== \$key: \$name@\$ref"
  rm -rf "datasets/.dl-\$key" "datasets/\$key.new"
  .venv/bin/harbor download "\$name@\$ref" --export --output-dir "datasets/.dl-\$key"
  $HB flatten "datasets/.dl-\$key" --out "datasets/\$key.new"
  # ghim mã băm TRƯỚC khi loại việc: lần sau tải lại mà khác thì dừng
  $HB lock "datasets/\$key.new" --name "\$key" --ref "\$ref" --lock "datasets/\$key.lock.json"
  # việc có file compose chưa duyệt (compose-allow.txt) và mọi việc vi phạm khác bị loại; in số lượng và tên
  $HB vet "datasets/\$key.new" --drop --allow agent-stack/compose-allow.txt
  rm -rf "datasets/\$key" "datasets/.dl-\$key"
  mv "datasets/\$key.new" "datasets/\$key"
  [ -f "datasets/\$key.new.rejected.txt" ] && mv "datasets/\$key.new.rejected.txt" "datasets/\$key.rejected.txt" || true
done
# Bộ tiếng Việt: gom từ bản sync (agent-stack/vi-bench), ghim mã băm mới theo commit của bản sync (bộ tự viết đổi theo
# commit nên ghi lại lock thay vì đối chiếu), rồi kiểm an toàn như hai bộ kia.
if [ -d agent-stack/vi-bench ]; then
  echo "== vi: bộ tiếng Việt từ commit \$(cat agent-stack/payload/full/.payload-commit)"
  rm -rf datasets/vi.new datasets/vi.lock.json
  $HB flatten agent-stack/vi-bench --out datasets/vi.new
  $HB lock datasets/vi.new --name vi --ref "\$(cat agent-stack/payload/full/.payload-commit)" --lock datasets/vi.lock.json
  $HB vet datasets/vi.new --drop --allow agent-stack/compose-allow.txt
  rm -rf datasets/vi && mv datasets/vi.new datasets/vi
  [ -f datasets/vi.new.rejected.txt ] && mv datasets/vi.new.rejected.txt datasets/vi.rejected.txt || true
elif [ "$only_vi" -eq 1 ]; then
  echo "Chưa có agent-stack/vi-bench trên TUF: commit evals/vi-bench rồi tuf.sh sync" >&2; exit 1
fi
echo "Xong. Kiểm: tuf.sh check"
EOF
    ;;
  pick)
    tmp="$HERE/.tasks-swerebench.new"
    remote "$HB pick-swerebench datasets/swerebench --n 25" > "$tmp" || { rm -f "$tmp"; echo "pick-swerebench lỗi (xem thông báo ở trên)" >&2; exit 1; }
    grep -vc '^#' "$tmp" | grep -qx 25 || { rm -f "$tmp"; echo "Không chọn được 25 việc" >&2; exit 1; }
    mv "$tmp" "$HERE/tasks-swerebench.txt"
    echo "Đã ghi $HERE/tasks-swerebench.txt: commit nó rồi chạy tuf.sh sync"
    ;;
  select)
    # Nhãn độ khó nằm trong task.toml của từng việc trên TUF, nên chạy ở đó; danh sách ghi về Mac để commit.
    tmp="$HERE/.tasks-candidates.new"
    remote "$HB select datasets --swerebench agent-stack/tasks-swerebench.txt" > "$tmp" || { rm -f "$tmp"; echo "select lỗi (xem thông báo ở trên)" >&2; exit 1; }
    mv "$tmp" "$HERE/tasks-candidates.txt"
    echo "Đã ghi $HERE/tasks-candidates.txt: đọc, commit, tuf.sh sync, rồi tuf.sh filter"
    ;;
  filter)
    # Kết quả lời giải mẫu nằm trên TUF (jobs/*-oracle), nên lọc ở đó; hai danh sách ghi về Mac để commit.
    refuse_if_running
    rsh <<EOF
set -e
test -f agent-stack/tasks-candidates.txt || { echo "Chưa có tasks-candidates.txt trên TUF: commit nó rồi tuf.sh sync" >&2; exit 1; }
jobs=""
for j in jobs/*-oracle; do [ -d "\$j" ] && jobs="\$jobs \$j"; done
[ -n "\$jobs" ] || { echo "Chưa có lần chạy lời giải mẫu nào: tuf.sh oracle --yes" >&2; exit 1; }
rm -rf jobs/.filter && mkdir -p jobs/.filter
$HB filter-oracle --candidates agent-stack/tasks-candidates.txt --root . --out-main jobs/.filter/main.txt --out-recheck jobs/.filter/recheck.txt \$jobs
EOF
    for f in main recheck; do
      remote "cat jobs/.filter/$f.txt" > "$HERE/.tasks-$f.new" || { rm -f "$HERE"/.tasks-*.new; echo "Không đọc được kết quả lọc" >&2; exit 1; }
    done
    mv "$HERE/.tasks-main.new" "$HERE/tasks-main.txt"
    mv "$HERE/.tasks-recheck.new" "$HERE/tasks-recheck.txt"
    echo "Đã ghi $HERE/tasks-main.txt và tasks-recheck.txt: đọc, commit rồi tuf.sh sync"
    ;;
  check)
    ssh "$HOST" "cd \"\$HOME/$REMOTE\" && sh -s -- '$HARBOR_VERSION' '$REMOTE'" <<'EOF'
want=$1; rdir=$2
PY=.venv/bin/python; HB="$PY agent-stack/harbor_bench.py"
test -f agent-stack/payload/full/.agent-stack-root || { echo "✗ chưa sync"; exit 1; }
echo "✓ bản chép agent-stack: commit $(cat agent-stack/payload/full/.payload-commit) (full, nohooks, noagents)"
v=$($PY -c 'import importlib.metadata as m; print(m.version("harbor"))' 2>/dev/null || true)
if [ "$v" = "$want" ]; then echo "✓ Harbor $v (đã ghim)"; else echo "✗ Harbor '$v' khác bản ghim $want: chạy tuf.sh setup"; fi
PYTHONPATH="$PWD/agent-stack" $PY -c 'import agent_stack_agents as m; print("✓ agent Harbor import được:", ", ".join(c.name() for c in (m.ClaudeCodePlain, m.ClaudeCodeAgentStack, m.ClaudeCodeAgentStackNoHooks, m.ClaudeCodeAgentStackNoAgents)))' || echo "✗ import agent_stack_agents lỗi"
PYTHONPATH="$PWD/agent-stack" $PY -c 'import serial_build_env as m; print("✓ môi trường dựng lần lượt import được:", m.SerialBuildDockerEnvironment.__mro__[1].__name__)' || echo "✗ import serial_build_env lỗi"
for ds in tblite swerebench vi; do
  if [ -d datasets/$ds ]; then
    echo "✓ bộ việc $ds: $(ls datasets/$ds | wc -l) việc, mã băm $(sed -n 's/.*"sha256": "\(.\{12\}\).*/\1/p' datasets/$ds.lock.json)"
    if [ -f datasets/$ds.rejected.txt ]; then echo "· $ds: $(wc -l < datasets/$ds.rejected.txt) việc bị loại khi kiểm an toàn (datasets/$ds.rejected.txt)"; fi
  else echo "✗ chưa có datasets/$ds: chạy tuf.sh data"; fi
done
if grep -q '^CLAUDE_CODE_OAUTH_TOKEN=.' .env 2>/dev/null; then
  perm=$(stat -c %a .env)
  if [ "$perm" = 600 ]; then echo "✓ có CLAUDE_CODE_OAUTH_TOKEN trong .env (quyền 600)"
  else echo "✗ .env có quyền $perm, rộng hơn 600: chmod 600 ~/$rdir/.env (pilot và run sẽ từ chối)"; fi
else echo "· chưa có CLAUDE_CODE_OAUTH_TOKEN trong ~/$rdir/.env (bước của bạn; oracle vẫn chạy được)"; fi
if [ -f .env ]; then
  other=$(grep -vE '^[[:space:]]*(#|$)' .env | grep -v '^CLAUDE_CODE_OAUTH_TOKEN=' | wc -l | tr -d ' ')
  if [ "$other" -gt 0 ]; then echo "✗ .env có $other dòng ngoài CLAUDE_CODE_OAUTH_TOKEN: Harbor nạp cả file vào môi trường; pilot và run sẽ từ chối"; fi
fi
if [ -e .env.local ]; then echo "✗ có file .env.local: Harbor tự nạp nó; xóa đi (pilot và run sẽ từ chối)"; fi
if docker info >/dev/null 2>&1; then echo "✓ Docker chạy được"; else echo "✗ Docker không chạy được"; fi
free=$(df -BG --output=avail "$HOME" | tail -1 | tr -dc 0-9)
echo "· ổ còn trống: ${free} GB (image SWE-rebench nặng; Harbor gỡ image dựng cục bộ sau mỗi lượt nhưng image gốc swerebench/* còn lại: tuf.sh prune)"
if [ "$free" -lt 25 ]; then echo "✗ ổ còn dưới 25 GB: dọn trước khi chạy"; fi
docker system df 2>/dev/null | sed 's/^/· /' || true
for c in configs/*.json; do
  [ -f "$c" ] || continue
  PYTHONPATH="$PWD/agent-stack" $HB validate-config "$c" || true
done
EOF
    out=$(ssh "$HOST" "$BUSY_CHECK"); echo "$out" | grep -v '^BUSY$' | sed 's/^/· /'
    echo "$out" | grep -q '^BUSY$' && echo "· TUF đang bận: oracle, pilot và run sẽ từ chối tới khi rảnh" || echo "✓ TUF đang rảnh"
    ;;
  oracle)
    # Danh sách là tasks-$NAME.txt; tên job là $NAME-oracle, hay $NAME2-oracle, $NAME3-oracle… khi tên đó đã dùng (chạy
    # recheck lần hai mà không xóa kết quả lần đầu, vì filter gộp mọi jobs/*-oracle).
    job="$NAME-oracle"; k=2
    while remote "test -e jobs/$job"; do job="$NAME$k-oracle"; k=$((k+1)); done
    prepare_job oracle "$job"
    [ "$YES" -eq 1 ] || { echo "Chưa chạy. Thêm --yes để chạy lời giải mẫu (không gọi model)."; exit 0; }
    launch_job "$job" none
    ;;
  pilot)
    prepare_job pilot pilot
    [ "$YES" -eq 1 ] || { echo "Chưa chạy. Thêm --yes để chạy pilot (gọi model, tính vào hạn mức)."; exit 0; }
    launch_job pilot token
    ;;
  pilot-report)
    [ -d "$LOCAL_JOBS/pilot" ] || { echo "Chưa có $LOCAL_JOBS/pilot: chạy tuf.sh fetch pilot" >&2; exit 1; }
    if [ -f "$HERE/tasks-main.txt" ]; then
      python3 "$HERE/harbor_bench.py" pilot-report "$LOCAL_JOBS/pilot" --main-tasks "$HERE/tasks-main.txt" --attempts "$ATTEMPTS"
    else
      python3 "$HERE/harbor_bench.py" pilot-report "$LOCAL_JOBS/pilot" --attempts "$ATTEMPTS"
    fi
    ;;
  run)
    [ "$NAME" != pilot ] || { echo "Tên pilot dành cho lệnh pilot" >&2; exit 2; }
    prepare_job main "$NAME"
    [ "$YES" -eq 1 ] || { echo "Chưa chạy. Thêm --yes để chạy job lớn (gọi model, tính vào hạn mức)."; exit 0; }
    launch_job "$NAME" token
    ;;
  status)
    for job in "$NAME-oracle" "$NAME"; do
      remote "test -e jobs/$job.log" || continue
      echo "== $job"
      remote "$HB status jobs/$job"
      # đoạn log in ra là dữ liệu không tin cậy (mã trong container có thể ghi ký tự điều khiển hay khóa): lọc trên Mac
      remote "tail -c 2000 jobs/$job.log" | python3 "$HERE/harbor_bench.py" scrub | grep -v '^[[:space:]]*$' | tail -3 || true
    done
    ;;
  stop)
    rsh <<EOF
pid=\$(cat jobs/$NAME.pid 2>/dev/null) || { echo "Không thấy jobs/$NAME.pid" >&2; exit 1; }
if kill -0 "\$pid" 2>/dev/null; then
  kill -s TERM -- "-\$pid" && echo "Đã gửi SIGTERM cho nhóm tiến trình của job $NAME (PID \$pid); chờ 20 giây…"
  sleep 20
else
  echo "Job $NAME không còn chạy."
fi
left=\$(docker ps --format '{{.Names}}' | tr '\n' ' ')
[ -z "\$left" ] || echo "Container còn chạy: \$left — tự dừng bằng: docker stop <tên> (script không dừng container của người khác)"
EOF
    ;;
  fetch)
    mkdir -p "$LOCAL_JOBS"
    # Che khóa ngay trên TUF (harbor_bench.py export, kèm khóa thật trong .env cả dạng base64) rồi mới kéo về; xóa bản cũ trên
    # Mac để không trộn hai lần chạy. Mac quét lại bằng đúng mẫu của export (residual), cho cả job lẫn job oracle.
    exp="jobs/.export-$NAME-$$"
    remote "jobs=''; for j in jobs/$NAME jobs/$NAME-oracle; do [ -d \$j ] && jobs=\"\$jobs \$j\"; done; \
      [ -n \"\$jobs\" ] || { echo 'Chưa có jobs/$NAME trên TUF' >&2; exit 1; }; \
      $HB export \$jobs --out $exp --env-file .env >&2"
    rm -rf "$LOCAL_JOBS/$NAME" "$LOCAL_JOBS/$NAME-oracle"
    remote "tar -C $exp -czf - . && rm -rf $exp" | tar -xzf - -C "$LOCAL_JOBS"
    if ! python3 "$HERE/harbor_bench.py" residual "$LOCAL_JOBS/$NAME" "$LOCAL_JOBS/$NAME-oracle" >/dev/null; then
      rm -rf "$LOCAL_JOBS/$NAME" "$LOCAL_JOBS/$NAME-oracle"
      echo "✗ Còn khóa trong bản kéo về: đã xóa. Báo lỗi này, đừng chạy tiếp." >&2; exit 1
    fi
    echo "Đã kéo về $LOCAL_JOBS/"
    ;;
  compare)
    [ -d "$LOCAL_JOBS/$NAME" ] || { echo "Chưa có $LOCAL_JOBS/$NAME: chạy tuf.sh fetch $NAME" >&2; exit 1; }
    oracle_arg=""; [ -d "$LOCAL_JOBS/$NAME-oracle" ] && oracle_arg="--oracle $LOCAL_JOBS/$NAME-oracle"
    # shellcheck disable=SC2086
    python3 "$HERE/harbor_bench.py" compare "$LOCAL_JOBS/$NAME" $oracle_arg
    # Riêng bộ tiếng Việt: cùng phép so, chỉ trên các bài trong tasks-vi.txt (bỏ qua khi job không có bài nào trong đó)
    if [ -f "$HERE/tasks-vi.txt" ]; then
      echo; echo "== Riêng bộ tiếng Việt (tasks-vi.txt)"
      # shellcheck disable=SC2086
      python3 "$HERE/harbor_bench.py" compare "$LOCAL_JOBS/$NAME" $oracle_arg --tasks "$HERE/tasks-vi.txt" || true
    fi
    ;;
  prune)
    refuse_if_running
    refuse_if_busy
    rsh <<EOF
n=\$(docker ps -q | wc -l)
[ "\$n" -eq 0 ] || { echo "Còn \$n container đang chạy: chưa xóa image" >&2; exit 1; }
# Harbor đặt tên container, image của lượt là <việc>__<7 ký tự>__env-…; khi Docker sập giữa lượt, chúng ở lại.
ctrs=\$(docker ps -a --format '{{.Names}}' | grep -E '__[a-z0-9]{7}__env-' || true)
imgs=\$(docker images --format '{{.Repository}}:{{.Tag}}' | grep -E '^swerebench/sweb\.eval|__[a-z0-9]{7}__env-' || true)
echo "Container Harbor bỏ lại (kèm network của chúng): \$(echo "\$ctrs" | grep -c . || true) · image (swerebench/sweb.eval*, image dựng của Harbor): \$(echo "\$imgs" | grep -c . || true) · \$(docker system df --format '{{.Type}}: {{.Size}}' | grep -i 'build cache' || true)"
if [ "$YES" -eq 1 ]; then
  [ -z "\$ctrs" ] || echo "\$ctrs" | xargs docker rm -f >/dev/null || true
  [ -z "\$imgs" ] || echo "\$imgs" | xargs docker rmi >/dev/null || true
  nets=\$(docker network ls --format '{{.Name}}' | grep -E '__[a-z0-9]{7}__env_default\$' || true)
  [ -z "\$nets" ] || echo "\$nets" | xargs docker network rm >/dev/null || true
  docker builder prune -a -f | tail -1
  echo "Ổ còn trống: \$(df -BG --output=avail "\$HOME" | tail -1 | tr -dc 0-9) GB"
else echo "Chưa xóa. Thêm --yes."; fi
EOF
    ;;
  *) sed -n '2,/^set -eu/{/^set -eu/!p;}' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
