---
name: reader-page
description: Viết mọi file HTML cho người đọc (file .html trong project hay trang Artifact riêng tư trên claude.ai) thay cho file Markdown, để người không nhớ phiên làm việc vẫn hiểu và quyết được. Bốn loại trang - đề xuất, giải thích, báo cáo, công cụ - mỗi loại một mức kiểm. Trang đề xuất giải thích từ gốc, có ít nhất 3 ví dụ cụ thể chạy qua từng phương án, đối chiếu đề xuất với luật của project kèm nguồn, soát pattern xấu và không khuyên phương án vi phạm luật. Script kiểm trang trước khi đưa người dùng. Dùng trước khi viết hay sửa mọi file để người đọc, như kế hoạch, so sánh, báo cáo, kết quả đo, review, giải thích, hướng dẫn, trang tương tác chép kết quả về chat. Không dùng cho file bắt buộc Markdown (CLAUDE.md, SKILL.md, PLAN.md, README) hay app, dashboard, game.
when_to_use: artifact, trang artifact, file html, trang html, thay markdown, đăng trang, trang so sánh, trang phương án, trang kế hoạch, báo cáo dạng trang, kết quả đo, trang review, giải thích từ gốc, hướng dẫn, trang khó hiểu, publish artifact, comparison page, html report
---

# Trang HTML dễ hiểu

Người đọc trang là bạn sau hai tuần nghỉ, hoặc người bạn gửi link: không nhớ phiên làm việc, không biết mã nội bộ, không thấy file. Trang phải tự đứng được: đọc từ trên xuống là hiểu vấn đề, hiểu các phương án qua ví dụ cụ thể, và trả lời được câu cần chốt. Skill này lo nội dung; trình bày theo `artifact-design` (hay `frontend-design` nếu không có công cụ Artifact). Luật chung (mục "File cho người đọc viết bằng HTML") bắt mọi file cho người đọc là HTML, trừ file bắt buộc Markdown.

Khuôn: `${CLAUDE_SKILL_DIR}/mau.html`. Script kiểm: `${CLAUDE_SKILL_DIR}/scripts/check_page.py`. Tham khảo đọc khi cần: `${CLAUDE_SKILL_DIR}/tham-khao.md`. Đọc bằng Read, chạy bằng `python3` theo đúng đường dẫn tuyệt đối này; không cần `ls` thư mục skill (có thể bị chặn vì nằm ngoài thư mục làm việc). Đường dẫn chưa tuyệt đối thì thay `${CLAUDE_SKILL_DIR}` bằng `~/Documents/Claude/agent-stack/plugin/skills/reader-page`.

## Khi nào dùng

- Mọi file để người đọc: so sánh phương án, kế hoạch, báo cáo, kết quả đo, review, giải thích, hướng dẫn, trang tương tác. Sửa một trang cũ thì đưa nó về khuôn này luôn.
- Bỏ qua: file bắt buộc Markdown, app, dashboard, game. Trang dựng từ Artifact type (Docs, Slides): theo nội dung skill này, bỏ bước chạy script.
- Trang là một file `.html` tự chứa: CSS, JS, hình SVG nằm sẵn trong file, mở thẳng bằng trình duyệt, đọc được trên điện thoại (căn cứ: bài "The unreasonable effectiveness of HTML" của đội Claude Code, 05/2026).

### File vẫn giữ Markdown

- Agent hay công cụ đọc nó: `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `SKILL.md` và mọi file trong thư mục skill, file định nghĩa subagent hay lệnh, file nhớ; file trạng thái `PLAN.md`, `PROGRESS.md`, `TODO.md`, `.agent/*.md`.
- Nền tảng ngoài đòi Markdown: `README`, `CHANGELOG`, `CONTRIBUTING`, `SECURITY`, `LICENSE`, mẫu trong `.github/`, mô tả PR và issue, commit; site dựng từ Markdown (MkDocs, Docusaurus) hay project đã quy ước Markdown trong `CLAUDE.md`, `AGENTS.md`.
- Script hay test của project đọc nó như Markdown; người dùng gọi đúng tên file `.md` hay xin Markdown.
- Skill hay plugin (kể cả bên thứ ba) dặn xuất báo cáo cho người đọc bằng `.md`: vẫn viết `.html`; file trung gian agent đọc lại thì giữ định dạng skill cần. Script tự sinh báo cáo cho người đọc thì sinh `.html`, chữ từ nguồn không tin cậy qua `html.escape`. File `.md` cũ chưa đổi thì cứ để; sửa lớn thì hỏi có chuyển sang HTML không.

## Bốn loại trang

Khai loại trên `<main>`; script kiểm theo loại. Mọi loại đều bị soát thuật ngữ và chữ mẫu.

| Loại | Khai | Khi nào | Script đòi |
|---|---|---|---|
| Đề xuất | (không khai; có thẻ `data-phuong-an`) | có thứ cần chốt, kể cả kế hoạch một hướng | đủ khuôn bên dưới |
| Giải thích | `data-loai="giai-thich"` | giải thích hệ thống, khái niệm, hướng dẫn | tóm tắt, từ gốc từ 600 ký tự, 3 ví dụ |
| Báo cáo | `data-loai="bao-cao"` | kết quả đo, trạng thái, review, sự cố, kiểm duyệt | tóm tắt, nguồn (`data-phan="nguon"`) |
| Công cụ | `data-loai="cong-cu"` | trang để chỉnh rồi chép kết quả về chat | tóm tắt, nút xuất `data-xuat` |

## Dùng skill khác khi hợp việc

Chỉ dùng khi đã cài; nội dung vẫn theo skill này. Chi tiết từng skill: `tham-khao.md` mục 4.

| Việc | Dùng |
|---|---|
| Trang chỉnh bằng nút rồi chép kết quả thành prompt | `playground`, khai `data-loai="cong-cu"` |
| Kế hoạch triển khai một hướng, đụng hơn vài file, cần mockup, sơ đồ | `html-plan` |
| Trang tổng quan project gửi người khác, làm mới cùng link | `project-artifact` |
| Giao diện sản phẩm thật (landing, màn hình app) | `frontend-design` |
| Tài liệu nhiều người cùng sửa, bình luận | Claude Docs (skill `docs`) khi phiên có |
| Cây kế hoạch, tiến độ | `progress` (widget, pane Kế hoạch) |

## Đặt file và đưa cho người dùng

- Trang của phiên cần giữ: `.agent/trang/<tên>.html`. Không cần giữ: scratchpad. Tài liệu của project: đúng chỗ file `.md` lẽ ra nằm. Người dùng đã nêu tên hay chỗ thì theo đó.
- Đưa cho người dùng: `SendUserFile` với `display: "render"`, hay pane trình duyệt của app.
- Đăng Artifact khi người dùng cần link hay đọc trên máy khác. Kế hoạch có từ hai phương án đáng so sánh hoặc từ ba quyết định cần chốt: tóm tắt trong chat, hỏi một dòng "Muốn xem trang không?", chỉ làm trang khi người dùng đồng ý (người dùng nói câu trả lời dài khó hiểu, 18/11/2026). Đồng ý thì đăng trang Artifact riêng tư đặt phương án cạnh nhau và các câu cần chốt; đọc bình luận bằng `ArtifactComments` rồi mới làm, còn người dùng trả lời trong chat thì theo đó. Kế hoạch một hướng, hay phiên không có công cụ Artifact: ngắn thì giữ trong chat, dài thì viết file HTML.

## Các bước

1. **Xác định trang để làm gì.** Một câu: đọc xong, người đọc hiểu hay chốt được gì. Liệt kê điều họ phải biết trước, xếp từ gốc lên.
2. **Trang đề xuất: gom luật của project.** Đọc file có mặt: `CLAUDE.md`, `AGENTS.md`, luật toàn cục, `.agent/threat-model.md`, mục "Đã quyết" và §0 của file kế hoạch, nguyên tắc trong `README`. Ghi từng luật liên quan kèm `file:dòng`. Quyết định cũ của người dùng ghi trong kế hoạch cũng là luật. Rồi đọc `tham-khao.md` mục 1–3 (đối chiếu luật, pattern xấu, ví dụ trước và sau) và soát pattern xấu trên từng phương án, kể cả của người dùng.
3. **Viết trang bằng một lần Write** theo cấu trúc khuôn `mau.html`: chỉ `<title>`, meta viewport và `<main>`, không chép CSS, không sinh trang bằng script hay heredoc. Thay mọi "…" bằng nội dung thật, giữ `data-*` và class. Kế hoạch một hướng vẫn là đề xuất: đúng một thẻ `data-phuong-an`, kèm bảng ràng buộc và câu chốt. Trang không đề xuất thì bỏ từ "Các phương án" tới "Câu cần chốt" và khai loại; báo cáo, công cụ có thể bỏ cả từ gốc và ví dụ khi không cần.
4. **Chạy script**: `python3 ${CLAUDE_SKILL_DIR}/scripts/check_page.py --khuon <file>`. Script chèn meta viewport, font và CSS chuẩn (đổi màu, chữ thì thêm `<style>` riêng, nó đè CSS chuẩn), rồi kiểm. Bước này bắt buộc với mọi trang theo khuôn này (trang `html-plan` kiểm bằng `pack.mjs`, Artifact type bỏ bước này; trang `playground` chạy không có `--khuon` để giữ CSS riêng). Thoát 1 thì sửa từng LỖI bằng Edit rồi chạy lại tới "Đạt"; NHẮC thì cân nhắc. Lệnh bị chặn thì báo đúng lệnh và lỗi, không coi trang là xong. Script chỉ kiểm cấu trúc, không chứng minh trang dễ hiểu.
5. **Đọc thử bằng người lạ, một lần** (bắt buộc với trang đề xuất; trang khác khi dài hay gửi người khác). Giao subagent `agent-stack:cold-reader` prompt chỉ gồm đường dẫn tuyệt đối của file: không kể bối cảnh, vì người đọc thật cũng không được nghe. Chưa có subagent đó thì dùng `general-purpose`, model `sonnet`, với chỉ dẫn trong `${CLAUDE_SKILL_DIR}/../../agents/cold-reader.md`, và báo rằng con số "hiểu bao nhiêu phần trăm" có thể cao hơn thật (hook vẫn chèn yêu cầu của người dùng). Sửa một lượt, chạy lại script, không lặp tiếp.
6. **Đăng** bằng công cụ Artifact khi cần (mục "Đặt file và đưa cho người dùng"), kèm `description` một câu.
7. **Sau khi bạn chốt**, sửa trang trên từng câu: ghi lựa chọn đã chốt, lý do nếu khác khuyến nghị, bỏ chữ "cần chốt". Không để khuyến nghị cũ đứng cạnh quyết định ngược với nó.

## Khuôn trang

Thứ tự là thứ tự đọc; thuộc tính để script nhận ra.

| Phần | Đánh dấu | Viết gì |
|---|---|---|
| Tóm tắt | `data-phan="tom-tat"` | 3–5 câu cho người chưa đọc gì, không mã nội bộ, không từ nghề cần giải thích: trang về gì, trạng thái (đã làm, đã bật hay chờ chốt), khuyến nghị, bạn cần chốt gì. |
| Từ gốc | `data-phan="nen-tang"` | Hệ thống đang làm gì (sơ đồ nếu có luồng); vấn đề hôm nay qua một trường hợp thật; khái niệm cần biết, mỗi cái một câu định nghĩa, một ví dụ, cần cho phần nào. Ít nhất 600 ký tự. |
| Thuật ngữ | `data-phan="thuat-ngu"`, `<dt>` | Mọi mã nội bộ, viết tắt, ký hiệu; hoặc `<dfn>` tại chỗ, trước lần dùng đầu. Từ người đọc chắc chắn biết (tên project của họ) khai `data-tu-quen="SCEE, AgentDojo"` trên tóm tắt; mã có chữ số không miễn được. |
| Ví dụ | `data-vi-du` (ít nhất 3) | Dữ liệu thật: tên file, lệnh, vào và ra, con số, trích đoạn. Một ca thường gặp, một ca biên, một ca hỏng. Mỗi ví dụ: tình huống, điều xảy ra hôm nay, vì sao quan trọng. |
| Phương án | `data-phuong-an="A"`, `data-khuyen` | Một câu nói phương án làm gì, cách chạy, được, mất, chi phí lâu dài, đảo ngược được không. Vi phạm luật thì không khuyên và có dòng `data-vi-pham` nói vì sao. |
| Ví dụ × phương án | `data-phan="vi-du-x-phuong-an"`, ô `data-cho="A"` | Hàng là ví dụ, cột là phương án, ô là kết quả cụ thể, không phải "tốt hơn". Bắt buộc khi có từ hai phương án. |
| Ràng buộc | `data-phan="rang-buoc"`, hàng `data-rang-buoc data-nguon="file:dòng"`, ô `data-cho` + `data-ket-qua` | Hàng là luật ở bước 2, cột là phương án. Lời người dùng thì ghi "yêu cầu của bạn, <ngày>" và trích nguyên câu. Kết quả: `dat`, `vi-pham`, `can-duyet` (luật cho phép khi người dùng duyệt), `khong-lien-quan`; ô vi phạm hay cần duyệt nói vì sao. |
| Pattern xấu | `data-phan="pattern-xau"` | Từng pattern đã soát và kết quả, kể cả "không thấy". |
| Câu cần chốt | `data-cau-hoi` | Lời thường, kèm lựa chọn, khuyến nghị và lý do, chọn khác thì sao. |
| Nguồn | `data-phan="nguon"` | `file:dòng`, link, lệnh đã chạy. |

## Cách viết cho dễ hiểu

- **Cụ thể trước, khái quát sau.** Mở mỗi khái niệm bằng một trường hợp thật rồi mới nói quy tắc chung.
- **Gọi tên theo điều người đọc nhận ra**, không theo tên trong code. Mã nội bộ (HC5, D22, TM-28) thay bằng tên mô tả; buộc phải dùng thì định nghĩa trước lần đầu. Tên trong code lần đầu xuất hiện thì giải thích bằng một câu thường.
- **Không viết kiểu ghi chú nén** ("G1 41 · G2 10"). Viết thành câu, hoặc bảng có tiêu đề cột nói rõ đơn vị.
- **Con số kèm đơn vị và mốc so sánh**: "4 trên 97 bài thử, dưới ngưỡng 5 đã hẹn". Hai con số cho cùng một thứ thì nói ngay vì sao khác.
- **Rủi ro nói bằng hậu quả**: "kẻ tấn công chọn được giờ họp", không chỉ "12 bit".
- **Một ý một câu**, câu ngắn, giọng theo `writing-voice`: không mở bài sáo, không thổi phồng.
- **Không giấu khó khăn**: phương án khuyên có nhược điểm gì thì ghi ngay trên thẻ của nó.
- **Ví dụ mượn từ lĩnh vực khác** thì giải thích từ của nó ngay trong ví dụ.
- **Chưa đo thì ghi chưa biết**, không viết lại cách làm cho đầy ô. Phương án vi phạm mà vẫn hỏi thì nói vì sao vẫn hỏi.
