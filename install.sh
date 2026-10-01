#!/bin/sh
# Kích hoạt agent-stack. Mặc định chỉ xem trước; thêm --apply để thực hiện, --rollback để hoàn tác.
exec python3 "$(dirname "$0")/tools/install.py" "$@"
