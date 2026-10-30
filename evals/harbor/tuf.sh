#!/bin/sh
# Dựng và chạy bench "Claude Code có và không có agent-stack" trên TUF qua ssh. Chạy từ máy Mac, ở gốc repo
# agent-stack. Xem evals/harbor/README.md.
#
#   tuf.sh sync [--force]          đưa lên TUF: bản chép agent-stack (git archive HEAD), agent Harbor, cấu hình job
#   tuf.sh check                   kiểm mọi thứ đã sẵn sàng; không chạy container nào
#   tuf.sh oracle [TÊN] [--force]  chạy lời giải mẫu trên bộ việc (container, không gọi model)
#   tuf.sh run [TÊN] [--force]     chạy hai bản Claude Code (container, gọi model: tính vào hạn mức)
#   tuf.sh status [TÊN]            tiến độ job
#   tuf.sh fetch [TÊN]             kéo kết quả về .tmp/harbor-jobs/
#   tuf.sh compare [TÊN]           so ghép cặp kết quả đã kéo về
#
# TÊN mặc định là pilot (bộ việc evals/harbor/tasks-pilot.txt). oracle và run chạy nền trên TUF (thoát ssh vẫn chạy),
# và từ chối khi TUF đang bận (có container khác, tải hay RAM cao) trừ khi thêm --force.
set -eu

HOST=${HARBOR_HOST:-tuf}
REMOTE=${HARBOR_DIR:-harbor-eval}          # tương đối với $HOME trên TUF
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
STAGE="$REPO/.tmp/harbor-sync"

cmd=${1:-}; [ $# -gt 0 ] && shift
NAME=pilot; FORCE=0
for a in "$@"; do
  case "$a" in
    --force) FORCE=1 ;;
    -*) echo "Không hiểu cờ $a" >&2; exit 2 ;;
    *) NAME=$a ;;
  esac
done
case "$NAME" in *[!A-Za-z0-9_-]*|'') echo "Tên job chỉ gồm chữ, số, - và _" >&2; exit 2 ;; esac

remote() { ssh "$HOST" "cd \"\$HOME/$REMOTE\" && $1"; }

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

start_job() {  # $1: file cấu hình, $2: tên job, $3: có cần token không
  cfg=$1; job=$2
  remote "test -f agent-stack/configs/$cfg" || { echo "Chưa có agent-stack/configs/$cfg trên TUF: chạy tuf.sh sync" >&2; exit 1; }
  if remote "test -e jobs/$job"; then
    echo "jobs/$job đã có trên TUF. Xoá nó (cùng jobs/$job.payload, jobs/$job.log), hay đổi TÊN (tạo evals/harbor/tasks-<TÊN>.txt rồi sync)." >&2; exit 1
  fi
  envflag=""
  if [ "$3" = token ]; then
    remote 'grep -q "^CLAUDE_CODE_OAUTH_TOKEN=." .env 2>/dev/null' || {
      echo "Chưa có CLAUDE_CODE_OAUTH_TOKEN trong ~/$REMOTE/.env trên TUF (bước của bạn, xem README.md)." >&2; exit 1; }
    envflag="--env-file .env"
  fi
  refuse_if_busy
  # Bản chép agent-stack của job nằm riêng trong jobs/<job>.payload: sync giữa chừng không đổi được job đang chạy,
  # và commit của bản chép đi cùng kết quả. Phần chạy nền nằm trong { … & } để ssh trả về ngay.
  remote "mkdir -p jobs && rm -rf jobs/$job.payload && cp -R agent-stack/payload jobs/$job.payload && { \
    AGENT_STACK_PAYLOAD=\"\$PWD/jobs/$job.payload\" PYTHONPATH=\"\$PWD/agent-stack\" nohup setsid \
    .venv/bin/harbor run -c agent-stack/configs/$cfg $envflag -q -y > jobs/$job.log 2>&1 < /dev/null & } && \
    echo \"Đã chạy nền job $job (PID \$!), agent-stack commit \$(cat jobs/$job.payload/.payload-commit). Log: ~/$REMOTE/jobs/$job.log\""
}

case "$cmd" in
  sync)
    dirty=$(git -C "$REPO" status --porcelain -- plugin global routing-table.md vetted.lock .agent-stack-root)
    if [ -n "$dirty" ] && [ "$FORCE" -ne 1 ]; then
      echo "plugin/ hay global/ còn thay đổi chưa commit; bản chép lấy từ HEAD nên sẽ không có chúng:" >&2
      echo "$dirty" >&2; echo "Commit trước, hoặc thêm --force." >&2; exit 1
    fi
    rm -rf "$STAGE"; mkdir -p "$STAGE/payload" "$STAGE/configs"
    git -C "$REPO" archive HEAD .agent-stack-root plugin global routing-table.md vetted.lock | tar -x -C "$STAGE/payload"
    git -C "$REPO" rev-parse --short HEAD > "$STAGE/payload/.payload-commit"
    cp "$HERE/agent_stack_agents.py" "$HERE/harbor_bench.py" "$STAGE/"
    for f in "$HERE"/tasks-*.txt; do
      n=$(basename "$f" .txt); n=${n#tasks-}
      python3 "$HERE/harbor_bench.py" make-configs --tasks "$f" --name "$n" --out "$STAGE/configs" >/dev/null
    done
    COPYFILE_DISABLE=1 tar --no-xattrs -C "$STAGE" -cf - . | ssh "$HOST" "rm -rf \"\$HOME/$REMOTE/agent-stack\" && mkdir -p \"\$HOME/$REMOTE/agent-stack\" && tar -xf - -C \"\$HOME/$REMOTE/agent-stack\""
    echo "Đã đưa lên $HOST:~/$REMOTE/agent-stack: agent-stack commit $(cat "$STAGE/payload/.payload-commit"), cấu hình: $(ls "$STAGE/configs" | tr '\n' ' ')"
    ;;
  check)
    remote 'set -e
      test -f agent-stack/payload/.agent-stack-root || { echo "✗ chưa sync"; exit 1; }
      echo "✓ bản chép agent-stack: commit $(cat agent-stack/payload/.payload-commit)"
      PYTHONPATH="$PWD/agent-stack" .venv/bin/python -c "import agent_stack_agents as m; print(\"✓ agent Harbor import được:\", m.ClaudeCodePlain.name(), \"và\", m.ClaudeCodeAgentStack.name())"
      for c in agent-stack/configs/*.json; do
        PYTHONPATH="$PWD/agent-stack" .venv/bin/harbor run -c "$c" --print-config >/dev/null 2>&1 && echo "✓ cấu hình hợp lệ: $c" || { echo "✗ cấu hình lỗi: $c"; PYTHONPATH="$PWD/agent-stack" .venv/bin/harbor run -c "$c" --print-config 2>&1 | tail -5; }
      done
      if grep -q "^CLAUDE_CODE_OAUTH_TOKEN=." .env 2>/dev/null; then
        perm=$(stat -c %a .env); echo "✓ có CLAUDE_CODE_OAUTH_TOKEN trong .env (quyền $perm$( [ "$perm" = 600 ] || echo ", nên chmod 600"))"
      else echo "· chưa có CLAUDE_CODE_OAUTH_TOKEN trong ~/'"$REMOTE"'/.env (bước của bạn; oracle vẫn chạy được)"; fi
      docker info >/dev/null 2>&1 && echo "✓ Docker chạy được" || echo "✗ Docker không chạy được"
      echo "· ổ còn trống: $(df -h "$HOME" | awk "NR==2{print \$4}")"'
    out=$(remote "$BUSY_CHECK"); echo "$out" | grep -v '^BUSY$' | sed 's/^/· /'
    echo "$out" | grep -q '^BUSY$' && echo "· TUF đang bận: oracle và run sẽ từ chối tới khi rảnh" || echo "✓ TUF đang rảnh"
    ;;
  oracle) start_job "$NAME-oracle.json" "$NAME-oracle" none ;;
  run)    start_job "$NAME.json" "$NAME" token ;;
  status)
    for job in "$NAME-oracle" "$NAME"; do
      remote "test -e jobs/$job.log" || continue
      echo "== $job: $(remote "ls jobs/$job/*/result.json 2>/dev/null | wc -l") lượt đã có kết quả"
      remote "tail -c 2000 jobs/$job.log | tr '\r' '\n' | grep -v '^\s*$' | tail -3"
    done
    ;;
  fetch)
    mkdir -p "$REPO/.tmp/harbor-jobs"
    # Che token ngay trên TUF (harbor_bench.py export) rồi mới kéo về; xoá bản cũ trên Mac để không trộn hai lần chạy.
    exp="jobs/.export-$NAME-$$"
    remote "jobs=''; for j in jobs/$NAME jobs/$NAME-oracle; do [ -d \$j ] && jobs=\"\$jobs \$j\"; done; \
      [ -n \"\$jobs\" ] || { echo 'Chưa có jobs/$NAME trên TUF' >&2; exit 1; }; \
      .venv/bin/python agent-stack/harbor_bench.py export \$jobs --out $exp >&2"
    rm -rf "$REPO/.tmp/harbor-jobs/jobs/$NAME" "$REPO/.tmp/harbor-jobs/jobs/$NAME-oracle"
    mkdir -p "$REPO/.tmp/harbor-jobs/jobs"
    remote "tar -C $exp -czf - . && rm -rf $exp" | tar -xzf - -C "$REPO/.tmp/harbor-jobs/jobs"
    echo "Đã kéo về $REPO/.tmp/harbor-jobs/jobs/"
    ;;
  compare)
    base="$REPO/.tmp/harbor-jobs/jobs"
    [ -d "$base/$NAME" ] || { echo "Chưa có $base/$NAME: chạy tuf.sh fetch $NAME" >&2; exit 1; }
    if [ -d "$base/$NAME-oracle" ]; then
      python3 "$HERE/harbor_bench.py" compare "$base/$NAME" --oracle "$base/$NAME-oracle"
    else
      python3 "$HERE/harbor_bench.py" compare "$base/$NAME"
    fi
    ;;
  *) sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
