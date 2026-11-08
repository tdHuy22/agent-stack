#!/bin/sh
# Chạy `harbor run` với môi trường lọc (TM-73): Harbor đưa os.environ vào lệnh docker compose, nên không để biến lạ của phiên
# ssh (token, khóa dịch vụ khác) lọt vào. Chỉ giữ biến cần để Harbor, Docker và Python chạy.
# Dùng: run_harbor.sh CONFIG.json token|none   (token: nạp ./.env qua --env-file; none: lời giải mẫu, không nạp gì)
#       run_harbor.sh jobs/TÊN resume-token|resume-none   chạy tiếp job dừng giữa chừng (`harbor jobs resume`)
set -eu
cfg=${1:?thiếu cấu hình}
mode=${2:?thiếu token|none}
set --
for v in PATH HOME USER LOGNAME LANG LC_ALL TMPDIR DOCKER_HOST DOCKER_CONFIG DOCKER_CONTEXT XDG_RUNTIME_DIR XDG_CACHE_HOME \
         HTTP_PROXY HTTPS_PROXY NO_PROXY http_proxy https_proxy no_proxy AGENT_STACK_PAYLOAD PYTHONPATH; do
  eval "val=\${$v-}"
  [ -z "$val" ] || set -- "$@" "$v=$val"
done
case "$mode" in
  token) exec env -i "$@" .venv/bin/harbor run -c "$cfg" --env-file .env -q -y ;;
  none) exec env -i "$@" .venv/bin/harbor run -c "$cfg" -q -y ;;
  # `harbor jobs resume` không có --env-file: harbor_bench.py nạp .env bằng đúng hàm của Harbor rồi exec harbor
  resume-token) exec env -i "$@" .venv/bin/python agent-stack/harbor_bench.py resume-exec "$cfg" --env-file .env ;;
  resume-none) exec env -i "$@" .venv/bin/python agent-stack/harbor_bench.py resume-exec "$cfg" ;;
  *) echo "chế độ không hợp lệ: $mode" >&2; exit 2 ;;
esac
