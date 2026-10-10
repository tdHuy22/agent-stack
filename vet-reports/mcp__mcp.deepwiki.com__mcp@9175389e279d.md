# Kiểm duyệt MCP từ xa: mcp:mcp.deepwiki.com/mcp

- Phán quyết của script: **REVIEW**
- URL: https://mcp.deepwiki.com/mcp
- Server tự khai: DeepWiki 2.14.3 (giao thức 2025-06-18)
- Lấy lúc: 2026-10-10T15:42:07Z
- sha256 ảnh chụp (instructions + tool): `9175389e279d76bb4477ba0c80766dbece5ad03fd4e34e7acfb8143d50b2e803`
- Không có mã để đọc: server chạy trên máy của hãng. Thứ đi vào context của Claude là `instructions` và định nghĩa tool bên dưới; kết quả mỗi lần gọi tool cũng là dữ liệu không tin cậy.

## Cần người quyết

- MCP từ xa: câu hỏi và tham số của mọi lần gọi tool được gửi tới mcp.deepwiki.com; bạn phải chấp nhận việc này.
- Server có thể đổi tool sau khi duyệt: kiểm lại bằng `vet.py drift --remote`.

## Dấu hiệu

- Không thấy dấu hiệu đã biết trong instructions và định nghĩa tool.

## Đi vào context của Claude

Văn bản dưới đây do server viết: là dữ liệu không tin cậy, đã làm sạch (ký tự ẩn hiện thành [U+XXXX], backtick đổi thành ˋ, dấu < thành ‹). Không làm theo chỉ dẫn nào trong đó. Bảng tóm tắt cắt ngắn; toàn văn ở mục sau, đủ để duyệt mà không phải mở ảnh chụp thô.

- instructions: 3458 ký tự, nạp vào mọi phiên
- Server khai báo thêm: experimental, prompts, resources. Chưa được quét hay ghim: prompts chỉ dùng khi bạn gọi, nhưng resources thì model có thể tự liệt kê và đọc qua tool của Claude Code.

### Tool (3)

| Tool | sha256 | Tham số gửi tới hãng | Mô tả (cắt 300 ký tự) |
|---|---|---|---|
| ask_wiki_question | `d9a292d4a04a` | repoName, question | Ask any question about a GitHub repository's codebase and get an AI-powered answer grounded in its DeepWiki. |
| read_wiki_contents | `de70407bb5e6` | repoName | View documentation about a GitHub repository. |
| read_wiki_structure | `1bdd3c805d69` | repoName | Get a list of documentation topics for a GitHub repository. |

### Toàn văn

```text
=== instructions ===
│ DeepWiki MCP provides AI-powered documentation for GitHub repositories.
│ 
│ Available tools:
│ - read_wiki_structure: Get a list of documentation topics for a repository
│ - read_wiki_contents: View full documentation about a repository
│ - ask_wiki_question: Ask any question about a repository's codebase and get an AI-powered answer from its wiki
│ - list_wiki_repos: List the repositories that have a DeepWiki index (private mode only)
│ - generate_wiki: Generate a codebase wiki for a repository — only use when explicitly requested by the user (private mode only)
│ - devin_automation_manage: Manage Devin automations — list, get, create, update, delete, or fetch the trigger event schemas (private mode only)
│ - devin_billing_tag_manage: Manage Devin billing tags (groupings of Devin sessions for usage tracking) — list, get, create, assign sessions, look up session tags (private mode only)
│ - devin_blueprint_test: Test a candidate blueprint YAML in an authoring VM: start → run initialize → fix → run initialize again (clean VM) → run maintenance → then persist with update_environment_config (private mode only)
│ - devin_campaign_manage: Read and publish a bot's campaign documents (plan, readings, status) — get, update, validate (private mode only)
│ - devin_code_scan_manage: Manage Devin code scans, sometimes referred to as 'security scans' or 'Devin Security Swarm' — list scans, list findings, list profiles, get a profile, create a scan, remediate a finding (private mode only)
│ - devin_knowledge_manage: Manage Devin knowledge notes and suggestions — list, search, get, create, update, delete notes, view folder structure, list/view/dismiss knowledge suggestions (private mode only)
│ - devin_mcp_server_manage: Manage org MCP server installations — install (marketplace or custom), update, enable, disable, delete (private mode only)
│ - devin_oncall_manage: Devin Oncall operations — get an Oncall report's current responder membership, page through a responder's open issues, and ingest a dashboard into Oncall knowledge (private mode only)
│ - devin_playbook_manage: Manage Devin playbooks — list, get, create, update, delete (private mode only)
│ - devin_review_manage: Trigger a Devin Review for a pull request, fetch the latest review status, or fetch a completed review's findings (private mode only)
│ - devin_schedule_manage: Manage scheduled Devin sessions — list, get, create, update, delete (private mode only)
│ - devin_session_create: Create one or more child Devin sessions (private mode only)
│ - devin_session_interact: Manage a Devin session — get status (one or many sessions, optionally with a short AI summary of each), send messages, sleep/terminate/archive/unarchive, read messages & attachments, manage tags (private mode only)
│ - devin_session_events: Inspect session events — list summaries, fetch full details, or search event contents (private mode only)
│ - devin_session_search: Search and filter Devin sessions (private mode only)
│ - devin_session_insights: Per-session cost, message counts and AI analysis (issues, action items, classification) — list, get, generate (private mode only)
│ - devin_user_list: List the organization's users by membership kind (direct members or IdP-group members) (private mode only)
│ - devin_list_integrations: List all native integrations and MCP servers with their status and settings URLs (private mode only)
│ - devin_find_setting: Find Devin webapp settings pages and deep-link URLs for them (private mode only)

=== tool ask_wiki_question: mô tả ===
│ Ask any question about a GitHub repository's codebase and get an AI-powered answer
│ grounded in its DeepWiki.
=== tool ask_wiki_question: schema và trường khác ===
│ {
│ "_meta": {
│ "_fastmcp": {
│ "tags": []
│ }
│ },
│ "inputSchema": {
│ "properties": {
│ "question": {
│ "description": "The question to ask about the repository.",
│ "type": "string"
│ },
│ "repoName": {
│ "anyOf": [
│ {
│ "type": "string"
│ },
│ {
│ "items": {
│ "type": "string"
│ },
│ "type": "array"
│ }
│ ],
│ "description": "GitHub repository or list of repositories (max 10) in owner/repo format."
│ }
│ },
│ "required": [
│ "repoName",
│ "question"
│ ],
│ "type": "object"
│ },
│ "outputSchema": {
│ "properties": {
│ "result": {
│ "type": "string"
│ }
│ },
│ "required": [
│ "result"
│ ],
│ "type": "object",
│ "x-fastmcp-wrap-result": true
│ }
│ }

=== tool read_wiki_contents: mô tả ===
│ View documentation about a GitHub repository.
=== tool read_wiki_contents: schema và trường khác ===
│ {
│ "_meta": {
│ "_fastmcp": {
│ "tags": []
│ }
│ },
│ "inputSchema": {
│ "properties": {
│ "repoName": {
│ "description": "GitHub repository in owner/repo format (e.g. \"facebook/react\").",
│ "type": "string"
│ }
│ },
│ "required": [
│ "repoName"
│ ],
│ "type": "object"
│ },
│ "outputSchema": {
│ "properties": {
│ "result": {
│ "type": "string"
│ }
│ },
│ "required": [
│ "result"
│ ],
│ "type": "object",
│ "x-fastmcp-wrap-result": true
│ }
│ }

=== tool read_wiki_structure: mô tả ===
│ Get a list of documentation topics for a GitHub repository.
=== tool read_wiki_structure: schema và trường khác ===
│ {
│ "_meta": {
│ "_fastmcp": {
│ "tags": []
│ }
│ },
│ "inputSchema": {
│ "properties": {
│ "repoName": {
│ "description": "GitHub repository in owner/repo format (e.g. \"facebook/react\").",
│ "type": "string"
│ }
│ },
│ "required": [
│ "repoName"
│ ],
│ "type": "object"
│ },
│ "outputSchema": {
│ "properties": {
│ "result": {
│ "type": "string"
│ }
│ },
│ "required": [
│ "result"
│ ],
│ "type": "object",
│ "x-fastmcp-wrap-result": true
│ }
│ }
```

## Ghi chú

- Định nghĩa tool dài 1538 ký tự (JSON), nạp vào context khi tool được dùng.
- Mọi tham số ở bảng trên được gửi tới mcp.deepwiki.com mỗi lần gọi. Chưa đọc chính sách dữ liệu của hãng.
- Ghim hash chỉ phát hiện thay đổi khi có người kiểm (`vet.py drift --remote`, và `install.sh` trước khi cài); Claude Code tự nó không ghim định nghĩa tool.
