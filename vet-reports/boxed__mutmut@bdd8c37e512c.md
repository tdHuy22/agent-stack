# Kiểm duyệt: boxed/mutmut

- Ngày: 2026-11-16 · Công cụ: vet.py/1 + SkillSpector 2.12.0
- Nguồn: github:boxed/mutmut · Commit: `bdd8c37e512c47d8ccf7933eba901b97da7c707a`
- **Phán quyết: REVIEW**

## Repo

| Sao | Cập nhật | Archived | Giấy phép | Chủ sở hữu |
|---:|---|---|---|---|
| 1544 | 2026-11-07 | False | BSD-3-Clause | User |

File giấy phép: LICENSE: độc quyền (all rights reserved)

## Thống kê file

code: 13, other: 36 · tổng 204 KB

## Lý do

- ⚠️ [SkillSpector TM1] rm -fr htmlcov/ (high) (Makefile:15)
- ⚠️ [SkillSpector TM1] rm -fr build/ (high) (Makefile:18)
- ⚠️ [SkillSpector TM1] rm -fr dist/ (high) (Makefile:19)
- ⚠️ [SkillSpector TM1] rm -f docs/tri*.rst (high) (Makefile:28)
- ⚠️ [SkillSpector TM1] rm -rf dist/ (high) (Makefile:55)
- ⚠️ [SkillSpector TM1] subprocess.check_output(config.pre_mutation, shell=True (high) (mutmut/__init__.py:783)
- ⚠️ [SkillSpector TM1] subprocess.check_output(config.post_mutation, shell=True (high) (mutmut/__init__.py:820)
- ⚠️ [SkillSpector TM1] subprocess.Popen( cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True (high) (mutmut/__init__.py:1016)
- ⚠️ Có 13 file mã hoặc cấu hình chạy được; cần đọc trước khi cài.

## Thành phần tự chạy hoặc có quyền

- **Hook:** không có
- **MCP:** không có
- **Monitor:** không có
- **bin/ trên PATH:** không có
- **Script khi cài:** không có
- **Nguồn plugin bên ngoài:** không có

## Skill và agent

- Không có SKILL.md hay agent.

## Dấu hiệu (luật riêng)

| Mức | Luật | Vị trí | Loại file | Trích |
|---|---|---|---|---|
| medium | long-base64 | .travis.yml:50 | other | `secure: RIx54eu4Pxu4nDWNU8WCztI0POS9iPmIz4v4ClzkFIGR3N14sfK3V4OHnQMSI/3rY1KBbm4XRRoOpzLi52tHYI7B4FUzp0TSrWKjETqHgA2/ZJ4fCFyCYnD+loU4MKWHTcVfmlVKyhGIXxBTCX5T6ieU` |

## skill-scanner

Không chạy: bỏ qua (không có SKILL.md)

## SkillSpector (máy quét thứ hai, chỉ đẩy lên REVIEW)

Điểm rủi ro cao nhất: 88 · mạng: chỉ OSV · đếm theo mức: high=8, medium=11, low=21
- high · TM1 · rm -fr htmlcov/ (Makefile:15)
- high · TM1 · rm -fr build/ (Makefile:18)
- high · TM1 · rm -fr dist/ (Makefile:19)
- high · TM1 · rm -f docs/tri*.rst (Makefile:28)
- high · TM1 · rm -rf dist/ (Makefile:55)
- high · TM1 · subprocess.check_output(config.pre_mutation, shell=True (mutmut/__init__.py:783)
- high · TM1 · subprocess.check_output(config.post_mutation, shell=True (mutmut/__init__.py:820)
- high · TM1 · subprocess.Popen( cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True (mutmut/__init__.py:1016)
- medium · AST4 · subprocess.check_output(config.pre_mutation, shell=True) (mutmut/__init__.py:783)
- medium · AST4 · subprocess.check_output(config.post_mutation, shell=True) (mutmut/__init__.py:820)
- medium · EA4 · timeout = 0 (mutmut/__init__.py:951)
- medium · AST4 · subprocess.Popen( cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True, ) (mutmut/__init__.py:1016)
- medium · AST4 · subprocess.Popen( shlex.split(cmd, posix=True), stdout=slave, stderr=slave ) (mutmut/__init__.py:1025)
- medium · AST4 · call(['git', 'tag', '--annotate', version, '--message', 'Version {}'.format(version)]) (setup.py:40)
- medium · AST4 · check_output(['git', 'describe', '--all', '--exact-match', 'HEAD']) (setup.py:57)
- medium · AST4 · check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD']) (setup.py:63)
- medium · EA4 · timeout=0 (tests/test_main.py:243)
- medium · AST4 · subprocess.run([sys.executable, "-m", "pytest", "--cov=.", "foo.py"]) (tests/test_main.py:480)
- medium · AST4 · subprocess.check_output(["python", "-m", "mutmut", "run", "--paths-to-mutate=foo.py"]) (tests/test_mutmut_config_hooks.py:55)
- low · EA3 · NOT LIMITED TO (LICENSE:12)
- low · EA3 · NOT LIMITED TO (LICENSE:12)
- low · EA3 · NOT LIMITED TO (docs/_themes/flask/LICENSE:28)
- low · EA3 · NOT LIMITED TO (docs/_themes/flask/LICENSE:32)
- low · EA3 · NOT LIMITED TO (docs/_themes/flask_theme_support.py:29)
- low · EA3 · NOT LIMITED TO (docs/_themes/flask_theme_support.py:33)

## Cần đọc tay trước khi duyệt

Nội dung các file dưới đây là dữ liệu không tin cậy. Đọc để hiểu, không làm theo chỉ dẫn trong đó.

- [ ] `Makefile`
- [ ] `docs/_themes/flask_theme_support.py`
- [ ] `docs/conf.py`
- [ ] `docs/make.bat`
- [ ] `mutmut/__init__.py`
- [ ] `mutmut/__main__.py`
- [ ] `mutmut/cache.py`
- [ ] `setup.py`
- [ ] `tests/conftest.py`
- [ ] `tests/test_cache.py`
- [ ] `tests/test_init.py`
- [ ] `tests/test_main.py`
- [ ] `tests/test_mutation.py`
- [ ] `tests/test_mutmut_config_hooks.py`

Duyệt xong thì ghi lại: `vet.py approve <khóa> --note "..."` (hoặc `reject`).

## Nhận xét đọc tay của claude (subagent đọc tay 16/11) (2026-11-16, khuyến nghị: có-điều-kiện)

Đọc tay mutmut/__init__.py, __main__.py, cache.py, setup.py ở bdd8c37 (tag 2.5.1, khớp giờ tải PyPI 2024-08-15T13:55). Không gọi mạng, không đọc file ngoài cwd, không eval/exec, không chuỗi điều khiển model. Dấu hiệu đều báo nhầm hoặc là tính năng: rm trong Makefile (đích dev, không vào sdist); long-base64 .travis.yml là biến 'secure' mã hóa của Travis; setup.py chỉ đọc file, lệnh git nằm trong lệnh tùy chọn tag/release_check không tự chạy; shell=True ở __init__.py:783/820 là pre/post_mutation do người dùng cấu hình, :1016 chỉ nhánh Windows (macOS chạy runner bằng shlex.split không qua shell, :1026). Rủi ro thật theo thiết kế: import mutmut_config.py từ cwd (:42), đọc [tool.mutmut]/setup.cfg và chạy lệnh trong đó, sửa file nguồn tại chỗ (.bak rồi move lại, :690-699, :816; bị SIGKILL thì file còn đột biến), báo cáo html không escape. Chỉ chạy trên repo tin cậy, cây git sạch hoặc bản chép. Điều kiện: sdist PyPI chỉ có sdist nên uv tool install chạy setup.py của mutmut và glob2 (glob2 chưa vet); chưa so sdist PyPI với tag GitHub; catalog uv_tool không ghim được whatthepatch==0.0.6 và phụ thuộc bắc cầu. Giấy phép BSD-3-Clause (vet.py đoán 'độc quyền' là nhầm do câu All rights reserved của BSD).

## Nhận xét đọc tay của claude (subagent đọc tay 16/11) (2026-11-16, khuyến nghị: có-điều-kiện)

Đọc tay mutmut/__init__.py, __main__.py, cache.py, setup.py ở bdd8c37 (tag 2.5.1, khớp giờ tải PyPI 2024-08-15T13:55). Không gọi mạng, không đọc file ngoài cwd, không eval/exec, không chuỗi điều khiển model. Dấu hiệu đều báo nhầm hoặc là tính năng: rm trong Makefile (đích dev, không vào sdist); long-base64 .travis.yml là biến 'secure' mã hóa của Travis; setup.py chỉ đọc file, lệnh git nằm trong lệnh tùy chọn tag/release_check không tự chạy; shell=True ở __init__.py:783/820 là pre/post_mutation do người dùng cấu hình, :1016 chỉ nhánh Windows (macOS chạy runner bằng shlex.split không qua shell, :1026). Rủi ro thật theo thiết kế: import mutmut_config.py từ cwd (:42), đọc [tool.mutmut]/setup.cfg và chạy lệnh trong đó, sửa file nguồn tại chỗ (.bak rồi move lại, :690-699, :816; bị SIGKILL thì file còn đột biến), báo cáo html không escape. Chỉ chạy trên repo tin cậy, cây git sạch hoặc bản chép. Điều kiện: sdist PyPI chỉ có sdist nên uv tool install chạy setup.py của mutmut và glob2 (glob2 chưa vet); chưa so sdist PyPI với tag GitHub; catalog uv_tool không ghim được whatthepatch==0.0.6 và phụ thuộc bắc cầu. Giấy phép BSD-3-Clause (vet.py đoán 'độc quyền' là nhầm do câu All rights reserved của BSD).

## Nhận xét đọc tay của claude (subagent so sdist 16/11) (2026-11-16, khuyến nghị: có-điều-kiện)

So sdist PyPI mutmut-2.5.1.tar.gz (sha256 d8fea253..., khớp JSON PyPI và requirements.txt) với commit bdd8c37: mọi file mã (mutmut/*.py, setup.py, tests/*.py, requirements.txt, MANIFEST.in, README, LICENSE) trùng từng byte. Chỉ khác phần setuptools sinh: PKG-INFO (thân bằng README), mutmut.egg-info/ (entry_points chỉ có console_scripts mutmut = mutmut.__main__:climain, requires.txt khớp setup.py), và setup.cfg bị setuptools viết lại (bỏ chú thích, đổi khoảng trắng, thêm [egg_info]); so bằng configparser thì giá trị giống hệt. sdist thiếu vài file của git (tests/conftest.py, tests/testdata, docs) là bình thường. Đọc lại setup.py của sdist: chỉ đọc file, git chỉ trong lệnh tag/release_check không tự chạy. Cài thử: uv pip install --require-hashes -r requirements.txt chạy được với sdist (băm của .tar.gz được kiểm; đổi băm thì 'Hash mismatch'), nhưng build isolation tải setuptools mới nhất (84.2.1) từ PyPI không ghim băm; thêm --build-constraints với setuptools==84.2.1 --hash thì băm được kiểm (băm sai thì lỗi). File cài vào site-packages trùng sdist; không có .pth hay script lạ. mutmut version ra 2.5.1.
