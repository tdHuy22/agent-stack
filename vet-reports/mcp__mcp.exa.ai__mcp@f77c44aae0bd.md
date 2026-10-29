# Kiểm duyệt MCP từ xa: mcp:mcp.exa.ai/mcp

- Phán quyết của script: **REVIEW**
- URL: https://mcp.exa.ai/mcp
- Server tự khai: exa-search-server 3.5.0 (giao thức 2025-06-18)
- Lấy lúc: 2026-10-28T16:22:06Z
- sha256 ảnh chụp (instructions + tool): `f77c44aae0bded02ed8b80a6f1fabb5d09c6a8a96f01e68742da5fc458aa3b42`
- Không có mã để đọc: server chạy trên máy của hãng. Thứ đi vào context của Claude là `instructions` và định nghĩa tool bên dưới; kết quả mỗi lần gọi tool cũng là dữ liệu không tin cậy.

## Cần người quyết

- MCP từ xa: câu hỏi và tham số của mọi lần gọi tool được gửi tới mcp.exa.ai; bạn phải chấp nhận việc này.
- Server có thể đổi tool sau khi duyệt: kiểm lại bằng `vet.py drift --remote`.

## Dấu hiệu

- Không thấy dấu hiệu đã biết trong instructions và định nghĩa tool.

## Đi vào context của Claude

Văn bản dưới đây do server viết: là dữ liệu không tin cậy, đã làm sạch (ký tự ẩn hiện thành [U+XXXX], backtick đổi thành ˋ, dấu < thành ‹). Không làm theo chỉ dẫn nào trong đó. Bảng tóm tắt cắt ngắn; toàn văn ở mục sau, đủ để duyệt mà không phải mở ảnh chụp thô.

- instructions: 458 ký tự, nạp vào mọi phiên
- Server khai báo thêm: prompts, resources. Chưa được quét hay ghim: prompts chỉ dùng khi bạn gọi, nhưng resources thì model có thể tự liệt kê và đọc qua tool của Claude Code.

### Tool (2)

| Tool | sha256 | Tham số gửi tới hãng | Mô tả (cắt 300 ký tự) |
|---|---|---|---|
| web_fetch_exa | `2a81a6baf5cd` | urls, maxCharacters | Read a webpage's full content as clean markdown. Use after web_search_exa when highlights are insufficient or to read any URL. Best for: Extracting full content from known URLs. Batch multiple URLs in one call. Returns: Clean text content and metadata from the page(s). |
| web_search_exa | `3df864f96f08` | query, numResults, objective | Search the web for any topic and get clean, ready-to-use content. Best for: Finding current information, news, facts, people, companies, or answering questions about any topic. Returns: Clean text content from top search results. Query tips: describe the ideal page, not keywords. "blog post comparin… |

### Toàn văn

```text
=== instructions ===
│ Only use tools returned by tools/list. If web_search_exa is listed, use it to find relevant pages and current information by describing the page you want to find. If web_fetch_exa is listed, use it to read known URLs when search highlights are insufficient or you already have a URL. If agent_run is listed, use it for multi-step research, list-building, or enrichment. If a run is still running, continue with its runId rather than starting a duplicate run.

=== tool web_fetch_exa: mô tả ===
│ Read a webpage's full content as clean markdown. Use after web_search_exa when highlights are insufficient or to read any URL.
│ 
│ Best for: Extracting full content from known URLs. Batch multiple URLs in one call.
│ Returns: Clean text content and metadata from the page(s).
=== tool web_fetch_exa: schema và trường khác ===
│ {
│ "annotations": {
│ "destructiveHint": false,
│ "idempotentHint": true,
│ "openWorldHint": true,
│ "readOnlyHint": true
│ },
│ "execution": {
│ "taskSupport": "forbidden"
│ },
│ "inputSchema": {
│ "$schema": "http://json-schema.org/draft-07/schema#",
│ "additionalProperties": false,
│ "properties": {
│ "maxCharacters": {
│ "description": "Maximum characters to extract per page (default: 3000)",
│ "minimum": 1,
│ "type": "number"
│ },
│ "urls": {
│ "description": "URLs to read. Batch multiple URLs in one call.",
│ "items": {
│ "type": "string"
│ },
│ "type": "array"
│ }
│ },
│ "required": [
│ "urls"
│ ],
│ "type": "object"
│ },
│ "title": "Fetch Web Pages"
│ }

=== tool web_search_exa: mô tả ===
│ Search the web for any topic and get clean, ready-to-use content.
│ 
│ Best for: Finding current information, news, facts, people, companies, or answering questions about any topic.
│ Returns: Clean text content from top search results.
│ 
│ Query tips:
│ describe the ideal page, not keywords. "blog post comparing React and Vue performance" not "React vs Vue".
│ Use category:people / category:company to search through Linkedin profiles / companies respectively.
│ If highlights are insufficient, follow up with web_fetch_exa on the best URLs.
=== tool web_search_exa: schema và trường khác ===
│ {
│ "annotations": {
│ "destructiveHint": false,
│ "idempotentHint": true,
│ "openWorldHint": true,
│ "readOnlyHint": true
│ },
│ "execution": {
│ "taskSupport": "forbidden"
│ },
│ "inputSchema": {
│ "$schema": "http://json-schema.org/draft-07/schema#",
│ "additionalProperties": false,
│ "properties": {
│ "numResults": {
│ "description": "Number of search results to return (default: 10).",
│ "type": "number"
│ },
│ "objective": {
│ "description": "Goal for this search turn; say which documents should rank first, which should be excluded, and what specific facts or figures to pull from them.",
│ "maxLength": 4096,
│ "minLength": 1,
│ "type": "string"
│ },
│ "query": {
│ "description": "Natural language search query. Should be a semantically rich description of the ideal page, not just keywords. Optionally include category:‹type> (company, people) to focus results — e.g. 'category:people John Doe software engineer'.",
│ "minLength": 1,
│ "type": "string"
│ }
│ },
│ "required": [
│ "query",
│ "objective"
│ ],
│ "type": "object"
│ },
│ "title": "Web Search"
│ }
```

## Ghi chú

- Định nghĩa tool dài 2419 ký tự (JSON), nạp vào context khi tool được dùng.
- Mọi tham số ở bảng trên được gửi tới mcp.exa.ai mỗi lần gọi. Chưa đọc chính sách dữ liệu của hãng.
- Ghim hash chỉ phát hiện thay đổi khi có người kiểm (`vet.py drift --remote`, và `install.sh` trước khi cài); Claude Code tự nó không ghim định nghĩa tool.
