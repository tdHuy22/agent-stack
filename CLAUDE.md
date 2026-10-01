# agent-stack: chỉ dẫn khi làm việc trong repo này

Repo này là nguồn sự thật cho bộ công cụ cá nhân dùng với Claude Code và OpenCode: skill, subagent, hook, statusline, luật chung. Thiết kế đầy đủ ở `KE-HOACH.md`. Tiến độ triển khai ở `PLAN.md`: **đọc mục §0 của `PLAN.md` trước khi làm gì khác.**

## Phạm vi (luật cứng)

- Chỉ tạo hoặc sửa file bên trong `agent-stack/`.
- Không sửa các project khác trong `~/Documents/Claude/`. Nếu cần đọc chúng, chỉ đọc, và lệnh git phải có `--no-optional-locks`.
- Không sửa `~/.claude/`, `~/.config/opencode/`, `~/.agents/` hay cài gì toàn cục (`brew`, `npm -g`, `uv tool`). Mọi kích hoạt toàn cục đi qua `install.sh`, và chỉ chạy khi người dùng duyệt.
- Gói Python bên thứ ba cài vào `.venv/` trong repo, với `UV_CACHE_DIR=.cache/uv`.
- Đồ bên thứ ba (skill, plugin, MCP) phải qua skill `vet-skill` và có dòng trong `vetted.lock` trước khi dùng.

## Code

- Python chỉ dùng thư viện chuẩn, và phải chạy được trên Python 3.9 (`/usr/bin/python3` của macOS). Hook có thể được gọi bằng Python này.
- Hook phải nhanh và không bao giờ làm kẹt phiên: bắt mọi lỗi, thoát mã 0, không in gì khi không có việc cần báo.
- File tạm nằm trong `.tmp/`. Trạng thái chạy nằm trong `state/`. Cả hai không đưa vào git.
- Docstring và chú thích viết tiếng Việt, ngắn. Tên biến và hàm viết tiếng Anh.

## Skill

- `name` viết kebab-case, tối đa 64 ký tự. `description` tối đa 1.024 ký tự, để OpenCode cũng đọc được.
- Đặt use-case lên đầu `description`. Thêm `when_to_use` nếu cần thêm từ khóa kích hoạt.

## Mốc kiểm tra

- `python3 -m unittest discover -s tests -t .` phải đạt, trên cả `/usr/bin/python3` (3.9) và `python3`.
- `claude plugin validate plugin` phải ra `Validation passed`.

## Git

- Làm trên nhánh `trien-khai-v1`. Commit sau mỗi giai đoạn, với thông điệp nói rõ giai đoạn. Không push.
