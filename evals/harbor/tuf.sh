#!/bin/sh
# Dựng và chạy bench "Claude Code có và không có agent-stack" (4 cấu hình, TBLite và SWE-rebench) trên TUF qua ssh.
# Chạy từ máy Mac, ở gốc repo agent-stack. Xem evals/harbor/README.md.
#
#   tuf.sh setup                      cài Harbor đã ghim vào ~/harbor-eval/.venv, tạo .env rỗng chmod 600 (lần đầu)
#   tuf.sh sync [--force]             đưa lên TUF: ba bản chép agent-stack, agent Harbor, script, danh sách việc
#   tuf.sh data                       tải hai bộ việc, ghim mã băm, loại việc vi phạm kiểm an toàn
#   tuf.sh pick                       chọn 25 việc SWE-rebench tháng mới nhất, ghi evals/harbor/tasks-swerebench.txt
#   tuf.sh check                      kiểm mọi thứ đã sẵn sàng (phiên bản, quyền .env, ổ đĩa, cấu hình); không chạy container
#   tuf.sh oracle [TÊN] [--force]     chạy lời giải mẫu trên bộ việc của pilot (container, không gọi model)
#   tuf.sh pilot [--yes] [--force]    pilot: bản plain trên mọi việc, 1 lần (gọi model: tính vào hạn mức)
#   tuf.sh select [--limit N]         đọc kết quả pilot đã kéo về, ghi evals/harbor/tasks-main.txt (sau đó sync lại)
#   tuf.sh run [TÊN] [--attempts N] [--yes] [--force]
#                                     job lớn: 4 cấu hình × tasks-main.txt × N lần (gọi model)
#   tuf.sh status [TÊN]               tiến độ và số lượt lỗi hạn mức
#   tuf.sh stop [TÊN]                 dừng job (SIGTERM cả nhóm tiến trình) và liệt kê container còn lại
#   tuf.sh fetch [TÊN]                kéo kết quả về .tmp/harbor-jobs/ (khóa bị che trên TUF trước khi kéo)
#   tuf.sh compare [TÊN]              so ghép cặp kết quả đã kéo về
#   tuf.sh prune [--yes]              xóa image swerebench/sweb.eval* đã kéo về (giải phóng ổ; kéo lại khi chạy)
#
# TÊN mặc định: pilot cho oracle và pilot; main cho các lệnh còn lại. pilot, oracle và run từ chối khi TUF đang bận (có
# container khác, tải hay RAM cao) trừ khi thêm --force, và chỉ chạy thật khi có --yes (không có thì chỉ in số lượt và trần
# chi phí). Chạy nền trên TUF: thoát ssh thì job vẫn chạy.
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

cmd=${1:-}; [ $# -gt 0 ] && shift
NAME=; FORCE=0; YES=0; ATTEMPTS=1; LIMIT=
while [ $# -gt 0 ]; do
  case "$1" in
    --force) FORCE=1 ;;
    --yes) YES=1 ;;
    --attempts) [ $# -ge 2 ] || { echo "--attempts cần một số" >&2; exit 2; }; ATTEMPTS=$2; shift ;;
    --limit) [ $# -ge 2 ] || { echo "--limit cần một số" >&2; exit 2; }; LIMIT=$2; shift ;;
    -*) echo "Không hiểu cờ $1" >&2; exit 2 ;;
    *) NAME=$1 ;;
  esac
  shift
done
case "$ATTEMPTS" in ''|*[!0-9]*|0) echo "--attempts phải là số nguyên từ 1" >&2; exit 2 ;; esac
case "$LIMIT" in *[!0-9]*) echo "--limit phải là số nguyên" >&2; exit 2 ;; esac
case "$cmd" in
  pilot) [ -z "$NAME" ] || [ "$NAME" = pilot ] || { echo "Job pilot không đổi tên được" >&2; exit 2; }; NAME=pilot ;;
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
  out=$(remote "$BUSY_CHECK")
  echo "$out" | grep -v '^BUSY$'
  if echo "$out" | grep -q '^BUSY$' && [ "$FORCE" -ne 1 ]; then
    echo "TUF đang bận: chưa chạy. Chờ việc kia xong, hoặc thêm --force nếu chắc chắn." >&2
    exit 3
  fi
}

# TM-73: khóa chỉ ở ~/harbor-eval/.env (bạn tự đặt). Script chỉ kiểm có dòng và quyền file, không bao giờ in giá trị.
require_token() {
  remote 'grep -q "^CLAUDE_CODE_OAUTH_TOKEN=." .env 2>/dev/null' || {
    echo "Chưa có CLAUDE_CODE_OAUTH_TOKEN trong ~/$REMOTE/.env trên TUF (bước của bạn, xem README.md)." >&2; exit 1; }
  perm=$(remote 'stat -c %a .env')
  [ "$perm" = 600 ] || { echo "~/$REMOTE/.env có quyền $perm: chạy chmod 600 ~/$REMOTE/.env trên TUF rồi thử lại." >&2; exit 1; }
}

# Tạo cấu hình, kiểm an toàn từng việc (TM-74) và in số lượt, trần chi phí (TM-77). $1: pilot|main|oracle, $2: tên job.
prepare_job() {
  kind=$1; job=$2
  remote "test -f agent-stack/payload/full/.agent-stack-root" || { echo "Chưa sync: chạy tuf.sh sync" >&2; exit 1; }
  remote "test -d datasets/tblite && test -d datasets/swerebench" || { echo "Chưa có bộ việc: chạy tuf.sh data" >&2; exit 1; }
  if remote "test -e jobs/$job"; then
    echo "jobs/$job đã có trên TUF. Xoá nó (cùng jobs/$job.payload, .meta.json, .log, .pid), hay đổi TÊN." >&2; exit 1
  fi
  case "$kind" in
    main) tasks_arg="--tasks agent-stack/tasks-main.txt"
      remote "grep -q . agent-stack/tasks-main.txt" 2>/dev/null || { echo "Chưa có tasks-main.txt: chạy pilot, fetch, select rồi sync." >&2; exit 1; } ;;
    *) tasks_arg=""
      remote "grep -qv '^#' agent-stack/tasks-swerebench.txt" 2>/dev/null || { echo "Chưa có tasks-swerebench.txt: chạy tuf.sh pick." >&2; exit 1; } ;;
  esac
  rsh <<EOF
set -e
mkdir -p configs jobs
$HB make-configs --kind $kind --name $job $tasks_arg --swerebench agent-stack/tasks-swerebench.txt --attempts $ATTEMPTS --out configs/$job.json >/dev/null
$HB vet-config configs/$job.json --root .
$HB plan configs/$job.json --root .
EOF
}

launch_job() {  # $1: tên job, $2: có cần khóa không (token|none)
  job=$1
  [ "$2" = token ] && require_token
  refuse_if_busy
  # Bản chép agent-stack của job nằm riêng trong jobs/<job>.payload: sync giữa chừng không đổi được job đang chạy, và
  # commit của bản chép đi cùng kết quả. Phần chạy nền tách phiên để ssh trả về ngay; harbor và watch ghi pid vào .pid.
  rsh <<EOF
set -e
$HB validate-config configs/$job.json
rm -rf jobs/$job.payload && cp -R agent-stack/payload jobs/$job.payload
$HB meta configs/$job.json --out jobs/$job.meta.json --payload jobs/$job.payload --root .
AGENT_STACK_PAYLOAD="\$PWD/jobs/$job.payload" PYTHONPATH="\$PWD/agent-stack" nohup setsid sh -c 'echo \$\$ > jobs/$job.pid; exec .venv/bin/harbor run -c configs/$job.json --env-file .env -q -y' > jobs/$job.log 2>&1 < /dev/null &
sleep 2
nohup setsid $PY agent-stack/harbor_bench.py watch jobs/$job --pid "\$(cat jobs/$job.pid)" > jobs/$job.watch.log 2>&1 < /dev/null &
echo "Đã chạy nền job $job (PID \$(cat jobs/$job.pid)), agent-stack commit \$(cat jobs/$job.payload/full/.payload-commit). Log: ~/$REMOTE/jobs/$job.log"
EOF
}

case "$cmd" in
  setup)
    # Wheel của Harbor được kiểm sha256 trước khi cài; phụ thuộc của nó thì pip/uv tự giải (chưa ghim băm).
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
echo "Xong. Việc của bạn: đặt CLAUDE_CODE_OAUTH_TOKEN=<khóa> vào ~/$REMOTE/.env (xem README.md)."
EOF
    ;;
  sync)
    dirty=$(git -C "$REPO" status --porcelain -- plugin global routing-table.md vetted.lock .agent-stack-root)
    if [ -n "$dirty" ] && [ "$FORCE" -ne 1 ]; then
      echo "plugin/ hay global/ còn thay đổi chưa commit; bản chép lấy từ HEAD nên sẽ không có chúng:" >&2
      echo "$dirty" >&2; echo "Commit trước, hoặc thêm --force." >&2; exit 1
    fi
    rm -rf "$STAGE"; mkdir -p "$STAGE/src"
    # TM-76: chỉ danh sách cho phép vào bản chép; build-payload dựng thêm bản nohooks, noagents và tự kiểm lại.
    git -C "$REPO" archive HEAD .agent-stack-root plugin global routing-table.md vetted.lock | tar -x -C "$STAGE/src"
    commit=$(git -C "$REPO" rev-parse --short HEAD)
    python3 "$HERE/harbor_bench.py" build-payload "$STAGE/src" "$STAGE/payload" --commit "$commit"
    rm -rf "$STAGE/src"
    cp "$HERE/agent_stack_agents.py" "$HERE/harbor_bench.py" "$STAGE/"
    for f in "$HERE"/tasks-*.txt; do [ -f "$f" ] && cp "$f" "$STAGE/"; done
    COPYFILE_DISABLE=1 tar --no-xattrs -C "$STAGE" -cf - . | ssh "$HOST" "mkdir -p \"\$HOME/$REMOTE\" && cd \"\$HOME/$REMOTE\" && rm -rf agent-stack && mkdir -p agent-stack && tar -xf - -C agent-stack"
    echo "Đã đưa lên $HOST:~/$REMOTE/agent-stack: agent-stack commit $commit (full, nohooks, noagents), $(ls "$STAGE" | grep -c '^tasks-') file danh sách việc"
    ;;
  data)
    rsh <<EOF
set -e
mkdir -p datasets
$HB datasets | while IFS="\$(printf '\t')" read -r key name ref; do
  echo "== \$key: \$name@\$ref"
  rm -rf "datasets/.dl-\$key" "datasets/\$key.new"
  .venv/bin/harbor download "\$name@\$ref" --export --output-dir "datasets/.dl-\$key"
  $HB flatten "datasets/.dl-\$key" --out "datasets/\$key.new"
  # ghim mã băm TRƯỚC khi loại việc: lần sau tải lại mà khác thì dừng
  $HB lock "datasets/\$key.new" --name "\$key" --ref "\$ref" --lock "datasets/\$key.lock.json"
  $HB vet "datasets/\$key.new" --drop
  rm -rf "datasets/\$key" "datasets/.dl-\$key"
  mv "datasets/\$key.new" "datasets/\$key"
  [ -f "datasets/\$key.new.rejected.txt" ] && mv "datasets/\$key.new.rejected.txt" "datasets/\$key.rejected.txt" || true
done
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
  check)
    ssh "$HOST" "cd \"\$HOME/$REMOTE\" && sh -s -- '$HARBOR_VERSION' '$REMOTE'" <<'EOF'
want=$1; rdir=$2
PY=.venv/bin/python; HB="$PY agent-stack/harbor_bench.py"
test -f agent-stack/payload/full/.agent-stack-root || { echo "✗ chưa sync"; exit 1; }
echo "✓ bản chép agent-stack: commit $(cat agent-stack/payload/full/.payload-commit) (full, nohooks, noagents)"
v=$($PY -c 'import importlib.metadata as m; print(m.version("harbor"))' 2>/dev/null || true)
if [ "$v" = "$want" ]; then echo "✓ Harbor $v (đã ghim)"; else echo "✗ Harbor '$v' khác bản ghim $want: chạy tuf.sh setup"; fi
PYTHONPATH="$PWD/agent-stack" $PY -c 'import agent_stack_agents as m; print("✓ agent Harbor import được:", ", ".join(c.name() for c in (m.ClaudeCodePlain, m.ClaudeCodeAgentStack, m.ClaudeCodeAgentStackNoHooks, m.ClaudeCodeAgentStackNoAgents)))' || echo "✗ import agent_stack_agents lỗi"
for ds in tblite swerebench; do
  if [ -d datasets/$ds ]; then
    echo "✓ bộ việc $ds: $(ls datasets/$ds | wc -l) việc, mã băm $(sed -n 's/.*"sha256": "\(.\{12\}\).*/\1/p' datasets/$ds.lock.json)"
  else echo "✗ chưa có datasets/$ds: chạy tuf.sh data"; fi
done
if grep -q '^CLAUDE_CODE_OAUTH_TOKEN=.' .env 2>/dev/null; then
  perm=$(stat -c %a .env)
  if [ "$perm" = 600 ]; then echo "✓ có CLAUDE_CODE_OAUTH_TOKEN trong .env (quyền 600)"
  else echo "✗ .env có quyền $perm, rộng hơn 600: chmod 600 ~/$rdir/.env (pilot và run sẽ từ chối)"; fi
else echo "· chưa có CLAUDE_CODE_OAUTH_TOKEN trong ~/$rdir/.env (bước của bạn; oracle vẫn chạy được)"; fi
if grep -q '^ANTHROPIC_API_KEY=.' .env 2>/dev/null; then echo "· .env có ANTHROPIC_API_KEY: bản này đặt CLAUDE_FORCE_OAUTH nên khóa đó bị bỏ qua"; fi
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
    out=$(remote "$BUSY_CHECK"); echo "$out" | grep -v '^BUSY$' | sed 's/^/· /'
    echo "$out" | grep -q '^BUSY$' && echo "· TUF đang bận: oracle, pilot và run sẽ từ chối tới khi rảnh" || echo "✓ TUF đang rảnh"
    ;;
  oracle)
    prepare_job oracle "$NAME-oracle"
    [ "$YES" -eq 1 ] || { echo "Chưa chạy. Thêm --yes để chạy lời giải mẫu (không gọi model)."; exit 0; }
    launch_job "$NAME-oracle" none
    ;;
  pilot)
    prepare_job pilot pilot
    [ "$YES" -eq 1 ] || { echo "Chưa chạy. Thêm --yes để chạy pilot (gọi model, tính vào hạn mức)."; exit 0; }
    launch_job pilot token
    ;;
  run)
    [ "$NAME" != pilot ] || { echo "Tên pilot dành cho lệnh pilot" >&2; exit 2; }
    prepare_job main "$NAME"
    [ "$YES" -eq 1 ] || { echo "Chưa chạy. Thêm --yes để chạy job lớn (gọi model, tính vào hạn mức)."; exit 0; }
    launch_job "$NAME" token
    ;;
  select)
    base="$LOCAL_JOBS"
    [ -d "$base/pilot" ] || { echo "Chưa có $base/pilot: chạy tuf.sh fetch pilot" >&2; exit 1; }
    oracle_arg=""
    [ -d "$base/pilot-oracle" ] && oracle_arg="--oracle $base/pilot-oracle"
    limit_arg=""
    [ -n "$LIMIT" ] && limit_arg="--limit-per-dataset $LIMIT"
    # shellcheck disable=SC2086
    python3 "$HERE/harbor_bench.py" select "$base/pilot" $oracle_arg $limit_arg --out "$HERE/tasks-main.txt"
    echo "Đọc $HERE/tasks-main.txt, commit nó rồi chạy tuf.sh sync."
    ;;
  status)
    for job in "$NAME-oracle" "$NAME"; do
      remote "test -e jobs/$job.log" || continue
      echo "== $job"
      remote "$HB status jobs/$job; tail -c 2000 jobs/$job.log | tr '\r' '\n' | grep -v '^\s*\$' | tail -3"
    done
    ;;
  stop)
    rsh <<EOF
pid=\$(cat jobs/$NAME.pid 2>/dev/null) || { echo "Không thấy jobs/$NAME.pid" >&2; exit 1; }
if kill -0 "\$pid" 2>/dev/null; then
  kill -TERM -- "-\$pid" && echo "Đã gửi SIGTERM cho nhóm tiến trình của job $NAME (PID \$pid); chờ 20 giây…"
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
    # Che khóa ngay trên TUF (harbor_bench.py export) rồi mới kéo về; xóa bản cũ trên Mac để không trộn hai lần chạy.
    exp="jobs/.export-$NAME-$$"
    remote "jobs=''; for j in jobs/$NAME jobs/$NAME-oracle; do [ -d \$j ] && jobs=\"\$jobs \$j\"; done; \
      [ -n \"\$jobs\" ] || { echo 'Chưa có jobs/$NAME trên TUF' >&2; exit 1; }; \
      $HB export \$jobs --out $exp >&2"
    rm -rf "$LOCAL_JOBS/$NAME" "$LOCAL_JOBS/$NAME-oracle"
    remote "tar -C $exp -czf - . && rm -rf $exp" | tar -xzf - -C "$LOCAL_JOBS"
    if grep -rIl 'sk-ant-' "$LOCAL_JOBS/$NAME" >/dev/null 2>&1; then
      rm -rf "$LOCAL_JOBS/$NAME" "$LOCAL_JOBS/$NAME-oracle"
      echo "✗ Còn chuỗi giống khóa trong bản kéo về: đã xóa. Báo lỗi này, đừng chạy tiếp." >&2; exit 1
    fi
    echo "Đã kéo về $LOCAL_JOBS/"
    ;;
  compare)
    [ -d "$LOCAL_JOBS/$NAME" ] || { echo "Chưa có $LOCAL_JOBS/$NAME: chạy tuf.sh fetch $NAME" >&2; exit 1; }
    if [ -d "$LOCAL_JOBS/$NAME-oracle" ]; then
      python3 "$HERE/harbor_bench.py" compare "$LOCAL_JOBS/$NAME" --oracle "$LOCAL_JOBS/$NAME-oracle"
    else
      python3 "$HERE/harbor_bench.py" compare "$LOCAL_JOBS/$NAME"
    fi
    ;;
  prune)
    rsh <<EOF
n=\$(docker ps -q | wc -l)
[ "\$n" -eq 0 ] || { echo "Còn \$n container đang chạy: chưa xóa image" >&2; exit 1; }
imgs=\$(docker images --format '{{.Repository}}:{{.Tag}}' | grep '^swerebench/sweb.eval' || true)
echo "Image swerebench/sweb.eval*: \$(echo "\$imgs" | grep -c . || true)"
if [ "$YES" -eq 1 ]; then [ -z "\$imgs" ] || echo "\$imgs" | xargs docker rmi; else echo "Chưa xóa. Thêm --yes."; fi
EOF
    ;;
  *) sed -n '2,/^set -eu/{/^set -eu/!p;}' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
