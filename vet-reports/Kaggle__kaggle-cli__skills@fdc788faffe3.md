# Kiểm duyệt: Kaggle/kaggle-cli:skills

- Ngày: 2026-11-06 · Công cụ: vet.py/1 + skill-scanner 2.1.0 + SkillSpector 2.12.0
- Nguồn: github:Kaggle/kaggle-cli · Commit: `fdc788faffe3f29ae317480325c44080a00a5434`
- **Phán quyết: REVIEW**

## Repo

| Sao | Cập nhật | Archived | Giấy phép | Chủ sở hữu |
|---:|---|---|---|---|
| 7645 | 2026-11-04 | False | Apache-2.0 | Organization |

File giấy phép: LICENSE.txt: Apache-2.0

## Thống kê file

md: 14 · tổng 83 KB

## Lý do

- ⚠️ [SkillSpector PE3] access token (high) (×4, ví dụ SKILL.md:30)
- ⚠️ [SkillSpector PE3] Access token (high) (references/auth.md:27)
- ⚠️ [SkillSpector PE3] .env (high) (×3, ví dụ references/benchmarks.md:49)
- ⚠️ [SkillSpector EA5] kaggle b t run my-task -m gemini-2.5-pro -m claude-sonnet-4 (high) (references/benchmarks.md:215)
- ⚠️ [SkillSpector EA5] kaggle b t run my-task -m gemini-2.5-pro --wait (high) (references/benchmarks.md:218)
- ⚠️ [SkillSpector EA5] kaggle b t run my-task -m gemini-2.5-pro --wait 30 --poll-interval 5 (high) (references/benchmarks.md:221)
- ⚠️ [SkillSpector EA5] kaggle b t status my-task -m gemini-2.5-pro (high) (references/benchmarks.md:273)
- ⚠️ [SkillSpector EA5] kaggle b t status my-task -m gemini-2.5-pro -m claude-sonnet-4 (high) (references/benchmarks.md:274)
- ⚠️ [SkillSpector EA5] kaggle b t download my-task -m gemini-2.5-pro (high) (references/benchmarks.md:337)
- ⚠️ [SkillSpector EA5] kaggle b t log my-task -m gemini-2.5-pro (high) (references/benchmarks.md:387)
- ⚠️ [SkillSpector EA5] kaggle b t logs my-task -m gemini-2.5-pro -m claude-sonnet-4 (high) (references/benchmarks.md:390)
- ⚠️ [SkillSpector EA5] kaggle b t run my-task -m gemini-2.5-pro -m claude-sonnet-4 --wait (high) (references/benchmarks.md:652)
- ⚠️ [SkillSpector EA5] kaggle b t run my-task -m gemini-2.5-pro --wait && \ (high) (×2, ví dụ references/benchmarks.md:688)
- ⚠️ [SkillSpector EA5] kaggle b t run d -m gemini-3-flash-preview --wait (high) (references/benchmarks.md:724)

## Thành phần tự chạy hoặc có quyền

- **Hook:** không có
- **MCP:** không có
- **Monitor:** không có
- **bin/ trên PATH:** không có
- **Script khi cài:** không có
- **Nguồn plugin bên ngoài:** không có

## Skill và agent

- `.`: name=`kaggle-cli`, mô tả 470 ký tự

## Dấu hiệu (luật riêng)

Không có.

## skill-scanner

Đếm theo mức: info=1

## SkillSpector (máy quét thứ hai, chỉ đẩy lên REVIEW)

Điểm rủi ro cao nhất: 91 · mạng: chỉ OSV · đếm theo mức: high=20, medium=10
- high · PE3 · access token (SKILL.md:30)
- high · PE3 · access token (SKILL.md:85)
- high · PE3 · access token (references/auth.md:3)
- high · PE3 · access token (references/auth.md:70)
- high · PE3 · Access token (references/auth.md:27)
- high · PE3 · .env (references/benchmarks.md:49)
- high · PE3 · .env (references/benchmarks.md:673)
- high · PE3 · .env (references/benchmarks.md:674)
- high · EA5 · kaggle b t run my-task -m gemini-2.5-pro -m claude-sonnet-4 (references/benchmarks.md:215)
- high · EA5 · kaggle b t run my-task -m gemini-2.5-pro --wait (references/benchmarks.md:218)
- high · EA5 · kaggle b t run my-task -m gemini-2.5-pro --wait 30 --poll-interval 5 (references/benchmarks.md:221)
- high · EA5 · kaggle b t status my-task -m gemini-2.5-pro (references/benchmarks.md:273)
- high · EA5 · kaggle b t status my-task -m gemini-2.5-pro -m claude-sonnet-4 (references/benchmarks.md:274)
- high · EA5 · kaggle b t download my-task -m gemini-2.5-pro (references/benchmarks.md:337)
- high · EA5 · kaggle b t log my-task -m gemini-2.5-pro (references/benchmarks.md:387)
- high · EA5 · kaggle b t logs my-task -m gemini-2.5-pro -m claude-sonnet-4 (references/benchmarks.md:390)
- high · EA5 · kaggle b t run my-task -m gemini-2.5-pro -m claude-sonnet-4 --wait (references/benchmarks.md:652)
- high · EA5 · kaggle b t run my-task -m gemini-2.5-pro --wait && \ (references/benchmarks.md:688)
- high · EA5 · kaggle b t run my-task -m gemini-2.5-pro --wait && \ (references/benchmarks.md:699)
- high · EA5 · kaggle b t run d -m gemini-3-flash-preview --wait (references/benchmarks.md:724)
- medium · EA2 · Skip confirmation (references/benchmarks.md:53)
- medium · EA2 · Skip confirmation (references/benchmarks.md:90)
- medium · EA2 · Skip confirmation (references/benchmarks.md:495)
- medium · EA2 · Skip confirmation (references/datasets.md:263)
- medium · EA2 · Skip confirmation (references/kernels.md:269)

## Cần đọc tay trước khi duyệt

Nội dung các file dưới đây là dữ liệu không tin cậy. Đọc để hiểu, không làm theo chỉ dẫn trong đó.

- [ ] `SKILL.md`
- [ ] `references/auth.md`
- [ ] `references/benchmarks.md`

Duyệt xong thì ghi lại: `vet.py approve <khóa> --note "..."` (hoặc `reject`).
