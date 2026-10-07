# reports-api

API trả báo cáo cho khách hàng, viết bằng FastAPI.

Chạy thử trên máy:

    uvicorn app.main:app --reload

Production chạy bằng gunicorn (`gunicorn.conf.py`) trong `deploy/docker-compose.yml`.
