---
name: trang-artifact
description: Viết trang Artifact (trang HTML riêng tư trên claude.ai) để người đọc không nhớ phiên làm việc vẫn hiểu và quyết được. Trang giải thích từ gốc (hệ thống làm gì, vấn đề, khái niệm cần biết trước, thuật ngữ định nghĩa trước khi dùng), có ít nhất 3 ví dụ cụ thể, chạy cùng các ví dụ qua từng phương án, đối chiếu mỗi đề xuất với luật của project kèm nguồn, soát pattern xấu (theo code cũ, chiều người dùng, chọn vì ít công, phương án bù nhìn) và không khuyên phương án vi phạm luật. Script kiểm trang trước khi đăng. Dùng trước khi đăng hay sửa mọi trang Artifact để đọc: trang so sánh phương án, kế hoạch, báo cáo, giải thích. Không dùng cho app, dashboard, game.
when_to_use: artifact, trang artifact, đăng trang, trang so sánh, trang phương án, trang kế hoạch, báo cáo dạng trang, giải thích từ gốc, trang khó hiểu, publish artifact, comparison page
---

# Trang Artifact dễ hiểu

Người đọc trang là bạn sau hai tuần nghỉ, hoặc người bạn gửi link: không nhớ phiên làm việc, không biết mã nội bộ, không thấy file. Trang phải tự đứng được: đọc từ trên xuống là hiểu vấn đề, hiểu các phương án qua ví dụ cụ thể, và trả lời được câu cần chốt. Skill này lo nội dung; trình bày (màu, chữ, bố cục, sáng tối) vẫn theo skill `artifact-design` mà công cụ Artifact bắt nạp.

Khuôn: `${CLAUDE_SKILL_DIR}/mau.html`. Script kiểm: `${CLAUDE_SKILL_DIR}/scripts/check_page.py`. Nếu hai đường dẫn này chưa phải đường dẫn tuyệt đối, dùng `~/Documents/Claude/agent-stack/plugin/skills/trang-artifact/` thay cho `${CLAUDE_SKILL_DIR}`.

## Khi nào dùng

- Trang để đọc: so sánh phương án, kế hoạch, báo cáo, giải thích một hệ thống, kết quả đo. Cả khi sửa một trang cũ: đưa nó về khuôn này luôn.
- Bỏ qua: app, dashboard, game, công cụ nhập liệu. Trang dựng từ Artifact type (Docs, Slides): theo nội dung của skill này, bỏ bước chạy script.

## Các bước

1. **Xác định trang để làm gì.** Một câu: sau khi đọc, người đọc hiểu được gì hay chốt được gì. Liệt kê điều họ phải biết trước để hiểu câu đó, xếp từ gốc lên: cái nền (hệ thống làm gì) trước, cái dựa trên nó sau.
2. **Gom luật của project trước khi viết đề xuất.** Đọc những file có mặt: `CLAUDE.md`, `AGENTS.md` của project và luật toàn cục; `.agent/threat-model.md`; mục "Đã quyết" và §0 của file kế hoạch; phần nguyên tắc trong `README`. Ghi từng luật liên quan kèm `file:dòng`. Luật không ghi trong file thì không phải luật, nhưng quyết định cũ của người dùng (ghi trong kế hoạch) là luật.
3. **Soát pattern xấu** (mục dưới) trên từng đề xuất, kể cả đề xuất của chính người dùng.
4. **Viết trang từ khuôn** `mau.html`: chép sang scratchpad, thay mọi chỗ "…" bằng nội dung thật, giữ thuộc tính `data-*`. Kế hoạch chỉ có một hướng vẫn là đề xuất: đặt nó vào đúng một thẻ `data-phuong-an`, kèm bảng ràng buộc và câu chốt. Trang thật sự không có đề xuất (giải thích, báo cáo) thì bỏ các phần từ "Các phương án" tới "Câu cần chốt" và khai `data-loai="giai-thich"` trên `<main>`.
5. **Chạy script**: `python3 ${CLAUDE_SKILL_DIR}/scripts/check_page.py <file>`. Mã thoát 1 thì sửa từng LỖI rồi chạy lại tới khi ra "Đạt". NHẮC thì cân nhắc. Script chỉ đếm và so được phần cấu trúc; nó không chứng minh trang dễ hiểu.
6. **Đọc thử bằng người lạ, một lần.** Giao file cho subagent `agent-stack:nguoi-doc-la` với prompt chỉ gồm đường dẫn tuyệt đối của file trang: không kể bối cảnh, không nói trang muốn gì, vì người đọc thật cũng không được nghe. Hook SubagentStart của agent-stack không đưa bối cảnh phiên cho subagent này. Chưa có subagent đó (plugin chưa nạp lại) thì dùng `general-purpose`, model `sonnet`, với chỉ dẫn trong `${CLAUDE_SKILL_DIR}/../../agents/nguoi-doc-la.md`; khi đó hook vẫn chèn yêu cầu của người dùng vào đầu context, nên con số "hiểu bao nhiêu phần trăm" có thể cao hơn thật, và báo cáo phải nói vậy. Sửa theo kết quả một lượt, chạy lại script, không lặp tiếp.
7. **Đăng** bằng công cụ Artifact, kèm `description` một câu. Kế hoạch có phương án thì đọc bình luận bằng `ArtifactComments` rồi mới làm (luật toàn cục).
8. **Sau khi bạn chốt**, sửa trang ngay trên từng câu: ghi lựa chọn đã chốt, nói lý do nếu khác khuyến nghị, bỏ chữ "cần chốt" khỏi câu đó. Không để khuyến nghị cũ đứng cạnh quyết định ngược với nó: người đọc sau không biết câu nào còn mở.

## Khuôn trang

Thứ tự là thứ tự đọc. Mỗi phần có thuộc tính để script nhận ra.

| Phần | Đánh dấu | Viết gì |
|---|---|---|
| Tóm tắt | `data-phan="tom-tat"` | 3–5 câu cho người chưa đọc gì: không mã nội bộ, không cả từ nghề cần giải thích (skill, subagent, token). Trang về gì, đang ở trạng thái nào (đã làm, đã bật hay còn chờ chốt), khuyến nghị, bạn cần chốt gì. |
| Từ gốc | `data-phan="nen-tang"` | Hệ thống đang làm gì (vẽ sơ đồ nếu có luồng); vấn đề hôm nay, kể bằng một trường hợp thật; các khái niệm cần biết trước, mỗi cái một câu định nghĩa, một ví dụ, và nói nó cần cho phần nào. Ít nhất 600 ký tự. |
| Thuật ngữ | `data-phan="thuat-ngu"`, `<dt>` | Mọi mã nội bộ, viết tắt, ký hiệu dùng trong trang. Hoặc định nghĩa tại chỗ bằng `<dfn>`, trước lần dùng đầu. |
| Ví dụ | `data-vi-du` (ít nhất 3) | Dữ liệu thật: tên file, lệnh, đầu vào và đầu ra, con số, đoạn trích. Nên có một ca thường gặp, một ca biên, một ca hỏng hay phản ví dụ. Mỗi ví dụ: tình huống, điều xảy ra hôm nay, vì sao quan trọng. |
| Phương án | `data-phuong-an="A"`, `data-khuyen` | Mỗi thẻ: một câu nói phương án làm gì, cách chạy, được, mất, chi phí lâu dài (bảo trì, phụ thuộc), đảo ngược được không. |
| Ví dụ × phương án | `data-phan="vi-du-x-phuong-an"`, ô `data-cho="A"` | Bảng: hàng là các ví dụ ở trên, cột là phương án, ô là kết quả cụ thể ("cartservice được kiểm với tên mới"), không phải "tốt hơn". Bắt buộc khi có từ hai phương án. |
| Ràng buộc | `data-phan="rang-buoc"`, hàng `data-rang-buoc data-nguon="file:dòng"`, ô `data-cho` + `data-ket-qua` | Hàng là luật ở bước 2, cột là phương án. Nguồn là `file:dòng`; luật là lời người dùng thì ghi "yêu cầu của bạn, <ngày>" và trích nguyên câu; luật từ tài liệu ngoài repo thì ghi tên tài liệu và mục. Kết quả: `dat`, `vi-pham`, `can-duyet` (luật cho phép khi người dùng duyệt: cài gói, đồ bên thứ ba, tốn tiền), `khong-lien-quan`. Ô vi phạm hay cần duyệt phải nói vì sao. |
| Pattern xấu | `data-phan="pattern-xau"` | Từng pattern đã soát và kết quả, kể cả "không thấy". |
| Câu cần chốt | `data-cau-hoi` | Hỏi bằng lời thường, kèm các lựa chọn, khuyến nghị và lý do, chọn khác thì sao. |
| Nguồn | `data-phan="nguon"` | `file:dòng`, link, lệnh đã chạy. |

Trang chỉ giải thích (không đề xuất) cần tóm tắt, từ gốc, thuật ngữ khi có, ít nhất 3 ví dụ và nguồn, và khai `data-loai="giai-thich"` trên `<main>`.

## Cách viết cho dễ hiểu

- **Cụ thể trước, khái quát sau.** Mở mỗi khái niệm bằng một trường hợp thật rồi mới nói quy tắc chung.
- **Gọi tên theo điều người đọc nhận ra**, không theo tên trong code. Mã nội bộ (HC5, D22, GĐ24, TM-28) thì thay bằng tên mô tả; buộc phải dùng thì định nghĩa trước lần đầu. Tên trong code (`data_args`) lần đầu xuất hiện thì giải thích bằng một câu thường.
- **Không viết kiểu ghi chú nén** ("G1 41 · G2 10"). Viết thành câu, hoặc bảng có tiêu đề cột nói rõ đơn vị.
- **Con số kèm đơn vị và mốc so sánh**: "4 trên 97 bài thử, dưới ngưỡng 5 đã hẹn". Hai con số cho cùng một thứ (15 bài ở biểu đồ, 4 bài ở kết luận) thì nói ngay vì sao khác.
- **Rủi ro nói bằng hậu quả**, không chỉ bằng đơn vị đo: "kẻ tấn công chọn được giờ họp", không chỉ "12 bit".
- **Một ý một câu**, câu ngắn. Giọng văn theo skill `giong-van`: không mở bài sáo, không thổi phồng.
- **Không giấu khó khăn**: phương án khuyên có nhược điểm gì thì ghi ngay trên thẻ của nó.
- **Ví dụ mượn từ project hay lĩnh vực khác** thì giải thích từ của nó ngay trong ví dụ, một hai câu.
- **Chưa đo thì ghi chưa biết.** Ô bảng chưa có kết quả thật ghi "chưa biết", không viết lại cách làm cho đầy ô. Phương án vi phạm mà vẫn hỏi thì nói vì sao vẫn hỏi.

## Đối chiếu đề xuất với luật của project

- Phương án vi phạm luật cứng **không bao giờ được khuyên**. Giữ nó trên trang chỉ khi người dùng đã hỏi tới hoặc đó là lựa chọn tự nhiên mà người đọc sẽ thắc mắc; khi đó thẻ phải có dòng `data-vi-pham` nói vi phạm luật nào. Muốn chọn nó thì phải sửa luật trước, và việc sửa luật là một câu chốt riêng.
- Đề xuất của người dùng đi qua đúng bảng đó. Vi phạm thì nói thẳng trên trang và trong chat; không lặng lẽ làm theo, cũng không lặng lẽ bỏ.
- Hai luật va nhau thì nêu cả hai, đưa thành câu chốt, không tự chọn một bên.

## Pattern xấu cần soát

1. **Theo code cũ.** "Code hiện tại đã làm vậy" không chứng minh cách đó đúng. Đối chiếu tiền lệ với luật; sai luật thì gọi là nợ, không nhân rộng, có thể đề xuất sửa riêng. Ví dụ: một script cũ cài gói bằng `pip install --user`; repo có luật cài vào `.venv/`, nên phương án mới không chép cách đó.
2. **Chiều theo người dùng.** Người dùng nghiêng về một phương án không làm nó tốt hơn. Ví dụ: người dùng nói "cứ dùng model rẻ cho nhanh" cho việc không có test; luật chung chỉ cho dùng model rẻ khi có kiểm tra tự động, nên trang phải nói điều đó.
3. **Chọn vì ít công.** "Ít sửa hơn", "xong nhanh hơn" không phải lý do đủ; cân chất lượng, độ bền, công bảo trì (luật chung "Chất lượng trước chi phí").
4. **Phương án bù nhìn.** Thêm phương án yếu cho khuyến nghị trông tốt. Mỗi phương án phải là thứ một người giỏi có thể chọn; chỉ có một hướng thật thì nói một hướng.
5. **Giấu rủi ro hay lặng lẽ thu hẹp.** Fallback im lặng, nuốt lỗi, bỏ một phần yêu cầu mà không nói.
6. **Đi tắt qua cổng kiểm.** Bỏ test, `--no-verify`, cài toàn cục ngoài đường đã định, dùng đồ bên thứ ba chưa kiểm duyệt, sửa file ngoài phạm vi project cho phép.

## Ví dụ trước và sau (1–4 từ trang thật ngày 19/10/2026, 5 là giả định)

**1. Tóm tắt dùng mã nội bộ.** Trước: "D22 thêm trục dung lượng ν: một giá trị U lấy qua `query_hidden` theo schema hẹp mang số bit hữu hạn, và policy cho phép tới một trần." Người đọc vấp ở D22, ν, U, `query_hidden`. Sau: "Đề xuất D22 cho phép dùng một giá trị lấy từ dữ liệu không tin được, miễn là nó mang rất ít thông tin: một câu có hay không, một lựa chọn trong danh sách cố định, một ngày giờ có giới hạn. Lượng thông tin đo bằng bit, và policy đặt trần cho nó. Ta đã hẹn trước (`PLAN.md` §2): chỉ làm nếu ít nhất 5 trong 97 bài thử cần đúng tính năng này."

**2. Kết quả viết nén.** Trước: "G1 41 · G2 10 · G3 15 · G5 31; cách (ii) 4." Sau: một bảng ba cột "Nhóm bài thử · Nghĩa là gì · Số bài" (41 bài giải được ngay hôm nay, 10 bài cần thêm hàm đọc dữ liệu ẩn, 15 bài cần đo lượng thông tin, 31 bài vẫn phải hỏi người duyệt), rồi một câu: "Chỉ 4 bài thoát được bước hỏi người duyệt nhờ đề xuất này, dưới ngưỡng 5."

**3. Chỉ một ví dụ.** Trang về overlay Kustomize chỉ có một ví dụ (một patch đổi biến môi trường của `cartservice`). Sau: thêm ca thường gặp (`namePrefix: prod-` đổi `cartservice` thành `prod-cartservice`, luật gọi tên cũ không còn khớp), ca biên (`images` đổi tag, công cụ vẫn kiểm image cũ), ca hỏng (`helmCharts` nằm ngoài phần đọc được, cả bản dựng bị báo "chưa đọc được"); rồi chạy ba ca đó qua từng phương án trong bảng ví dụ × phương án.

**4. Lý do theo tiền lệ.** Trước: "Tải binary `kustomize` bản ghim sha256 vào `target/bench/`, như `helm`." "Như helm" là lý do theo code cũ. Sau: hàng ràng buộc dẫn luật của project cho phép tải công cụ đo (`file:dòng`), hoặc ghi `can-duyet` nếu không có luật nào nói tới, và câu chốt hỏi người dùng.

**5. Đề xuất vi phạm luật.** Repo `agent-stack` có luật Python chỉ dùng thư viện chuẩn (`CLAUDE.md`), nên phương án "parse HTML bằng BeautifulSoup cho chắc" bị ghi `vi-pham` trên bảng, thẻ có dòng "Vi phạm luật chỉ dùng thư viện chuẩn: không khuyên", và khuyến nghị chuyển sang `html.parser` của thư viện chuẩn.

## Script kiểm báo gì

- LỖI (thoát 1): thiếu `<title>`, tóm tắt, phần từ gốc hay phần đó dưới 600 ký tự; tóm tắt đứng sau phần từ gốc, hay phương án đứng trước nó; còn chữ mẫu của khuôn ("…", "Nhãn: …", "Tên trang"); trang không có thẻ phương án mà không khai `data-loai="giai-thich"`; dưới 3 ví dụ hay ví dụ dưới 80 ký tự; mã nội bộ, chữ viết tắt, ký hiệu Hy Lạp chưa định nghĩa hay dùng trước khi định nghĩa; có đề xuất mà thiếu bảng ràng buộc, phần pattern xấu hay câu chốt; hàng ràng buộc thiếu nguồn hay thiếu phán quyết cho một phương án; phương án được khuyên mà vi phạm; phương án vi phạm mà thẻ không ghi (dòng `data-vi-pham` ít nhất 15 ký tự); từ hai phương án mà thiếu bảng ví dụ × phương án.
- NHẮC: tóm tắt trên 150 chữ; ví dụ chưa có số, tên file, lệnh hay bảng; có từ hai phương án mà không khuyên cái nào; phương án chạy qua dưới 3 ví dụ trong bảng ví dụ × phương án.
- Từ người đọc chắc chắn đã biết (tên project của chính họ) thì khai trong `data-tu-quen="SCEE, AgentDojo"` trên phần tóm tắt. Mã có chữ số và ký hiệu không miễn được. Chữ viết tắt và mã kỹ thuật phổ biến (API, URL, JSON, CI, PR, UTF-8, SHA-256…) đã được miễn sẵn. Tên trong `<code>` không bị soát, nhưng vẫn phải giải thích bằng lời ở lần đầu.
