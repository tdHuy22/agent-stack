#!/bin/bash
# Bộ bài tiếng Việt của agent-stack: mọi bài dùng đúng file này (selftest.py kiểm). Chấm bằng tests/check.py, chỉ thư viện
# chuẩn, không cài gì, không gọi mạng. Ghi reward.json: "reward" (1 đạt, 0 trượt) cộng các chỉ số phụ mà check.py ghi vào
# vi-metrics.json (như số dấu hiệu văn AI ở nhóm viet-); chỉ số phụ không đổi reward. Xóa vi-metrics.json cũ trước khi chấm
# để file do agent để lại không lọt vào kết quả.
mkdir -p /logs/verifier
rm -f /logs/verifier/vi-metrics.json
if python3 /tests/check.py; then r=1; else r=0; fi
python3 - "$r" <<'PY'
import json, math, pathlib, sys
m = pathlib.Path("/logs/verifier/vi-metrics.json")
try:
    extra = json.loads(m.read_text(encoding="utf-8")) if m.is_file() else {}
except ValueError:
    extra = {}
out = {k: v for k, v in (extra if isinstance(extra, dict) else {}).items()
       if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and k != "reward"}
out["reward"] = int(sys.argv[1])
pathlib.Path("/logs/verifier/reward.json").write_text(json.dumps(out))
PY
