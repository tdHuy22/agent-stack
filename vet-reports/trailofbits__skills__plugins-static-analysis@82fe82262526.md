# Kiểm duyệt: trailofbits/skills:plugins/static-analysis

- Ngày: 2026-10-01 · Công cụ: vet.py/1 + skill-scanner 2.1.0
- Nguồn: github:trailofbits/skills · Commit: `82fe8226252622fa807643bdca1710901198553a`
- **Phán quyết: REVIEW**

## Repo

| Sao | Cập nhật | Archived | Giấy phép | Chủ sở hữu |
|---:|---|---|---|---|
| 7323 | 2026-09-28 | False | CC-BY-SA-4.0 | Organization |

File giấy phép: LICENSE: CC

## Thống kê file

code: 28, md: 23, other: 9 · tổng 546 KB

## Lý do

- ⚠️ [skill-scanner BEHAVIOR_EVAL_SUBPROCESS] eval/exec combined with subprocess detected (mẫu lỗ hổng, có thể báo nhầm) (skills/codeql/scripts/test_shell_blocks.py:None)
- ⚠️ [skill-scanner COMMAND_INJECTION_OS_SYSTEM] Shell command execution with string formatting (potential injection) (mẫu lỗ hổng, có thể báo nhầm) (×3, ví dụ skills/codeql/scripts/test_build_log.py:17)
- ⚠️ [skill-scanner COMMAND_INJECTION_EVAL] Dangerous code execution functions that can execute arbitrary code (mẫu lỗ hổng, có thể báo nhầm) (skills/codeql/scripts/test_shell_blocks.py:702)
- ⚠️ [skill-scanner DATA_EXFIL_SENSITIVE_FILE_GLOB] Dynamic enumeration of sensitive files (mã độc) (skills/semgrep/scripts/test_merge_sarif.py:197)
- ⚠️ allowed-tools cấp Bash không giới hạn.
- ⚠️ Có 28 file mã hoặc cấu hình chạy được; cần đọc trước khi cài.

## Thành phần tự chạy hoặc có quyền

- **Hook:** không có
- **MCP:** không có
- **Monitor:** không có
- **bin/ trên PATH:** không có
- **Script khi cài:** không có
- **Nguồn plugin bên ngoài:** không có

## Skill và agent

- `skills/semgrep`: name=`semgrep`, mô tả 707 ký tự, allowed-tools=`Bash Read Glob AskUserQuestion TaskCreate TaskList TaskUpdate`
- `skills/sarif-parsing`: name=`sarif-parsing`, mô tả 373 ký tự, allowed-tools=`Bash Read Glob Grep`
- `skills/codeql`: name=`codeql`, mô tả 751 ký tự, allowed-tools=`Bash Read Write Edit Glob Grep AskUserQuestion TaskCreate TaskList TaskUpdate TaskGet`

## Dấu hiệu (luật riêng)

Không có.

## skill-scanner

Đếm theo mức: critical=5, high=1, medium=6, low=1, info=3
- critical · BEHAVIOR_EVAL_SUBPROCESS · eval/exec combined with subprocess detected (skills/codeql/scripts/test_shell_blocks.py:None)
- critical · COMMAND_INJECTION_OS_SYSTEM · Shell command execution with string formatting (potential injection) (skills/codeql/scripts/test_build_log.py:17)
- critical · COMMAND_INJECTION_OS_SYSTEM · Shell command execution with string formatting (potential injection) (skills/codeql/scripts/test_build_log.py:67)
- critical · COMMAND_INJECTION_OS_SYSTEM · Shell command execution with string formatting (potential injection) (skills/codeql/scripts/test_build_log.py:84)
- critical · COMMAND_INJECTION_EVAL · Dangerous code execution functions that can execute arbitrary code (skills/codeql/scripts/test_shell_blocks.py:702)
- high · DATA_EXFIL_SENSITIVE_FILE_GLOB · Dynamic enumeration of sensitive files (skills/semgrep/scripts/test_merge_sarif.py:197)
- medium · BEHAVIOR_BASH_TAINT_FLOW · Bash: tainted data flows to dangerous sink (skills/semgrep/scripts/run-scans.sh:435)
- medium · BEHAVIOR_BASH_TAINT_FLOW · Bash: tainted data flows to dangerous sink (skills/semgrep/scripts/run-scans.sh:436)
- medium · BEHAVIOR_BASH_TAINT_FLOW · Bash: tainted data flows to dangerous sink (skills/semgrep/scripts/run-scans.sh:730)
- medium · BEHAVIOR_BASH_TAINT_FLOW · Bash: tainted data flows to dangerous sink (skills/semgrep/scripts/run-scans.sh:741)
- medium · ALLOWED_TOOLS_WRITE_VIOLATION · Skill declares no Write tool but bundled scripts write files (skills/sarif-parsing/SKILL.md:None)
- medium · FILE_MAGIC_MISMATCH · File extension does not match actual content type (skills/sarif-parsing/agents/openai.yaml:None)
- low · ALLOWED_TOOLS_GREP_VIOLATION · Code uses search/grep patterns but Grep tool not in allowed-tools (skills/semgrep/SKILL.md:None)

## Cần đọc tay trước khi duyệt

Nội dung các file dưới đây là dữ liệu không tin cậy. Đọc để hiểu, không làm theo chỉ dẫn trong đó.

- [ ] `.claude-plugin/plugin.json`
- [ ] `skills/codeql/SKILL.md`
- [ ] `skills/codeql/scripts/build_log.sh`
- [ ] `skills/codeql/scripts/check_db_quality.py`
- [ ] `skills/codeql/scripts/find_databases.sh`
- [ ] `skills/codeql/scripts/generate_suite.sh`
- [ ] `skills/codeql/scripts/test_build_log.py`
- [ ] `skills/codeql/scripts/test_build_mode_claims.py`
- [ ] `skills/codeql/scripts/test_check_db_quality.py`
- [ ] `skills/codeql/scripts/test_find_databases.py`
- [ ] `skills/codeql/scripts/test_generation_scripts.py`
- [ ] `skills/codeql/scripts/test_script_flags.py`
- [ ] `skills/codeql/scripts/test_section_pointers.py`
- [ ] `skills/codeql/scripts/test_shell_blocks.py`
- [ ] `skills/codeql/scripts/test_suite_templates.py`
- [ ] `skills/codeql/scripts/test_verify_query_suite.py`
- [ ] `skills/codeql/scripts/verify_query_suite.py`
- [ ] `skills/sarif-parsing/SKILL.md`
- [ ] `skills/sarif-parsing/resources/sarif_helpers.py`
- [ ] `skills/sarif-parsing/resources/test_sarif_helpers.py`
- [ ] `skills/semgrep/SKILL.md`
- [ ] `skills/semgrep/scripts/merge_sarif.py`
- [ ] `skills/semgrep/scripts/run-scans.sh`
- [ ] `skills/semgrep/scripts/test_merge_sarif.py`
- [ ] `tests/codeql_build_harness.js`
- [ ] `tests/run_codeql_build_tests.sh`
- [ ] `tests/run_scan_tests.sh`
- [ ] `tests/run_workflow_tests.sh`
- [ ] `tests/workflow-harness.js`
- [ ] `workflows/codeql-build.js`
- [ ] `workflows/semgrep-scan.js`

Duyệt xong thì ghi lại: `vet.py approve <khóa> --note "..."` (hoặc `reject`).

## Nhận xét đọc tay của claude (2026-10-01, khuyến nghị: có-điều-kiện)

Cảnh báo 'mã độc' của skill-scanner ở `test_merge_sarif.py:197` là báo nhầm: test chỉ glob các file .sarif trong thư mục tạm. Bash không giới hạn để chạy Semgrep và CodeQL. Cài trong project bảo mật.
