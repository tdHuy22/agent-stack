# Thông báo bên thứ ba

`agents/reviewer.md` diễn đạt lại ý từ các nguồn dưới đây. Không chép code hay nguyên văn: mọi câu được viết lại bằng tiếng Việt, rút gọn và chỉnh cho hợp với reviewer. Đọc nguồn ngày 02/10/2026.

## claude-code-security-review (MIT)

- Nguồn: https://github.com/anthropics/claude-code-security-review (`claudecode/prompts.py`, `.claude/commands/security-review.md`).
- Việc đã làm: diễn đạt lại ý. Lấy danh sách loại trừ cứng và các tiền lệ khi chấm làm bảng lọc dương tính giả (bước 5 của reviewer), cùng ý ngưỡng tin cậy (bước 4). Bỏ bớt mục không hợp và sửa vài mục (rò rỉ tài nguyên vẫn báo khi là lỗi độ đúng). Chỉ áp cho reviewer, không áp cho vet-skill.
- Bản quyền và giấy phép, đúng như LICENSE của repo gốc:

```text
MIT License

Copyright (c) 2025 Anthropic

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## defending-code-reference-harness (Apache-2.0)

- Nguồn: https://github.com/anthropics/defending-code-reference-harness (`docs/prompting.md`, `docs/best-practices.md`).
- Giấy phép: Apache License 2.0, Copyright 2026 Anthropic PBC (theo LICENSE của repo gốc). Bản đầy đủ: https://www.apache.org/licenses/LICENSE-2.0
- Việc đã làm: diễn đạt lại ý. Lấy cách mô tả hình dạng lỗi thay vì liệt kê loại lỗi, bước verifier đối kháng tách khỏi bước tìm, và việc suy mức độ từ điều kiện cần để lỗi xảy ra. Không chép code hay văn bản gốc, không dùng tên hay nhãn hiệu của tác giả.

## pr-review-toolkit và code-review (Apache-2.0)

- Nguồn: https://github.com/anthropics/claude-plugins-official, bản chép marketplace ở commit `ab024cdcfa7c`: `plugins/pr-review-toolkit/agents/silent-failure-hunter.md`, `plugins/pr-review-toolkit/agents/pr-test-analyzer.md`, `plugins/code-review/commands/code-review.md`.
- Giấy phép: Apache License 2.0 (LICENSE trong từng plugin, chưa điền tên chủ bản quyền; tác giả ghi trong plugin.json là Anthropic). Bản đầy đủ: https://www.apache.org/licenses/LICENSE-2.0
- Việc đã làm: diễn đạt lại ý. Lấy hai mục kiểm (nuốt lỗi và fallback sai; thiếu test ở nhánh lỗi), quy tắc chấm độ tin cậy 0 đến 100 và bỏ phát hiện dưới 80, và vài mục trong danh sách dương tính giả. Không chép nguyên văn.
