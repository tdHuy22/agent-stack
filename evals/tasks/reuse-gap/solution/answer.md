Quyết định: dùng lại lychee (lycheeverse/lychee, Apache-2.0/MIT) qua lycheeverse/lychee-action trong CI, thay cho tools/md_links.py.

- tools/md_links.py có sẵn trong repo nhưng chỉ bắt được link tới file không tồn tại. Hàm anchor_exists() là hàm giả: còn TODO và luôn trả True, nên link deploy.md#canary hỏng mà vẫn qua. Link ngoài thì bị bỏ qua hoàn toàn.
- lychee kiểm cả link tới file, anchor (cờ --include-fragments) và link ngoài, có --max-retries và file .lycheeignore cho danh sách bỏ qua.

Phần còn phải làm: thêm bước lychee vào .github/workflows/docs.yml, tạo .lycheeignore, rồi bỏ md_links.py hoặc chỉ giữ để chạy tay.
