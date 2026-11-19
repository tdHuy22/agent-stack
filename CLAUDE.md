# agent-stack: chỉ dẫn khi làm việc trong repo này

Repo này là nguồn sự thật cho bộ công cụ cá nhân dùng với Claude Code: skill, subagent, hook, statusline, luật chung. Thiết kế đầy đủ ở `KE-HOACH.md`. Tiến độ triển khai ở `PLAN.md`: **đọc mục §0 của `PLAN.md` trước khi làm gì khác.**

## Phạm vi (luật cứng)

- Chỉ tạo hoặc sửa file bên trong `agent-stack/`.
- Không sửa các project khác trong `~/Documents/Claude/`. Nếu cần đọc chúng, chỉ đọc, và lệnh git phải có `--no-optional-locks`.
- Không sửa `~/.claude/`, `~/.agents/` hay cài gì toàn cục (`brew`, `npm -g`, `uv tool`). Mọi kích hoạt toàn cục đi qua `install.sh`, và chỉ chạy khi người dùng duyệt.
- Gói Python bên thứ ba cài vào `.venv/` trong repo, với `UV_CACHE_DIR=.cache/uv`.
- Đồ bên thứ ba (skill, plugin, MCP) phải qua skill `vet-skill` và có dòng trong `vetted.lock` trước khi dùng.

## Code

- Python chỉ dùng thư viện chuẩn, chạy bằng `python3` (Python 3.11 của pyenv). App gọi hook bằng chính `python3` này: mọi bản plugin đã cài chỉ có `cpython-311.pyc` (kiểm 09/10/2026). Không chạy hay kiểm trên `/usr/bin/python3` (3.9 của hệ thống macOS).
- Hook chỉ import thư viện chung `plugin/lib`, lib chỉ import lib: phần dùng chung dời vào `plugin/lib`, không import script của skill. Chỗ cũ nằm trong `ARCH_BASELINE` của `tests/test_static.py`, chỉ được bớt (archctl chưa thấy import sau `sys.path.insert`, nên luật này là test Python).
- TypeScript chỉ dùng cho lớp giao diện (mod) `plugin/hooks/ui.tsx`, kiểu ở `plugin/types/`, test ở `plugin/tests/*.test.tsx`. Không dùng gói npm nào. Logic vẫn nằm ở script Python; module chỉ gọi script qua `$.process.run` rồi vẽ. API mod còn early access: kiểm bằng binary của app (`tools/claude_app.py`), không bằng `claude` trong PATH (brew stable, có thể cũ hơn app).
- Hook phải nhanh và không bao giờ làm kẹt phiên: bắt mọi lỗi, thoát mã 0, không in gì khi không có việc cần báo.
- File tạm nằm trong `.tmp/`. Trạng thái chạy nằm trong `state/`. Cả hai không đưa vào git.
- Ngoại lệ:
  - Khi người dùng chạy eval thật (`run_eval.py --yes`), thư mục làm việc của model nằm trong thư mục tạm của hệ điều hành, để model không đọc được `CLAUDE.md`, grader hay lời giải. Script tự xóa thư mục đó sau khi chấm.
  - Test mô phỏng bản chép plugin nằm ngoài repo (như `~/.claude/plugins/cache`) dùng thư mục tạm của hệ điều hành và tự xóa.
  - `checks.py` (done-gate) chép file vừa đổi vào thư mục tạm của hệ điều hành cho gitleaks quét, và để file `.class` của `javac` ở đó, rồi tự xóa: script chạy ở mọi project (cùng lý do với `receipt.py fails-before`).
  - `receipt.py fails-before` dựng code trước bản sửa trong thư mục tạm của hệ điều hành rồi tự xóa, vì lệnh chạy ở mọi project, và `.tmp/` của project khác có thể chưa bị git bỏ qua (bạn chọn 04/11/2026).
  - `mutation.py` (done-gate) chép repo vào thư mục tạm của hệ điều hành cho mutmut chạy, rồi tự xóa, kể cả khi quá giờ: mutmut sửa file tại chỗ và nạp `mutmut_config.py` của thư mục đang chạy (TM-129). mutmut nằm trong `.venv-mutmut/` của repo (bạn duyệt 16/11/2026), cài bằng `mutation.py setup`.
- Docstring và chú thích viết tiếng Việt, ngắn. Tên biến và hàm viết tiếng Anh.

## Skill

- `name` viết kebab-case, tối đa 64 ký tự. `description` tối đa 1.024 ký tự (giới hạn của chuẩn Agent Skills).
- Đặt use-case lên đầu `description`. Thêm `when_to_use` nếu cần thêm từ khóa kích hoạt.

## Mốc kiểm tra

- `python3 -m unittest discover -s tests -t .` phải đạt (Python 3.11).
  Chạy song song: `python3 plugin/skills/session-keeper/scripts/narrow.py full` (mặc định số nhân hiệu năng): cùng tập test, mỗi module một tiến trình; mảnh trượt được chạy lại một mình một lần, đạt thì vẫn tính đạt và tên mảnh nằm ở dòng cuối. Không bắt lỗi rò trạng thái giữa các module (`os.environ`, `sys.modules`, cwd), nên trước khi cài toàn cục (`install.sh --apply`) chạy lệnh tuần tự một lần. Tự kiểm đủ số test discover nạp được; chạy qua `receipt.py run` nằm cùng thư mục với `narrow.py` thì là biên nhận cả bộ.
- `"$(python3 tools/claude_app.py)" plugin validate plugin` phải ra `Validation passed`.
- `"$(python3 tools/claude_app.py)" plugin test plugin` phải đạt (test của mod; `tests/test_ui_mod.py` cũng gọi lệnh này).
- File mới thì `git add` trước lần chạy bộ test cuối: vài test so với file git đang theo dõi (`tests/test_cloud_setup.py` so `tools/cloud-files.txt`), nên file chưa add không làm lộ chỗ lệch. Thêm file vào `plugin/`, `global/` thì tạo lại `tools/cloud-files.txt` theo dòng `# Tạo lại` của nó.

## Git

- Làm trên nhánh `main`. Commit sau mỗi giai đoạn, với thông điệp nói rõ giai đoạn. Không push.
