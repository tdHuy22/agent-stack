"""Cache báo cáo trong Redis, dùng chung cho mọi worker."""
import json
import os

import redis

client = redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))


def cached_report(report_id: int) -> dict:
    key = f"report:{report_id}"
    hit = client.get(key)
    if hit:
        return json.loads(hit)
    report = {"id": report_id, "rows": []}
    client.setex(key, 300, json.dumps(report))
    return report
