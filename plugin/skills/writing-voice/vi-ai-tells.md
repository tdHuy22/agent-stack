# Dấu hiệu văn AI trong tiếng Việt và cách sửa

Danh sách này để sửa văn cho hay hơn. Một dấu hiệu đơn lẻ không chứng minh văn do AI viết; người thật cũng dùng các cách viết này. Vấn đề nằm ở chỗ chúng xuất hiện dày đặc và làm văn rỗng. Nhóm có dấu ✱ được `scripts/tells.py` dò tự động.

Sửa nội dung trước, câu chữ sau. Chính nhóm biên tập Wikipedia lưu ý rằng chỉ xóa dấu hiệu bề mặt thì văn khó bị phát hiện hơn, chứ không hay hơn.

## Mở bài và kết bài

| Dấu hiệu | Ví dụ | Sửa |
|---|---|---|
| ✱ Mở bằng bối cảnh chung chung | "Trong bối cảnh chuyển đổi số hiện nay…", "Ngày nay, …", "Hãy cùng khám phá…" | Vào thẳng ý chính, hoặc mở bằng một chi tiết cụ thể. |
| ✱ Kết bằng tóm tắt lại toàn bài | "Tóm lại, …", "Nhìn chung, …", "Như vậy, có thể thấy…" | Kết bằng điều người đọc nên làm hoặc nên nhớ, hoặc không cần đoạn kết. |
| ✱ Kết bằng "thách thức và triển vọng" | "Mặc dù còn nhiều thách thức…", "tương lai đầy hứa hẹn", "tiềm năng to lớn" | Nói cụ thể khó khăn nào và bước tiếp theo là gì, hoặc bỏ đoạn này. |
| Câu hỏi tu từ rồi tự trả lời | "Vậy điều gì làm nên khác biệt? Đó chính là…" | Nói thẳng câu trả lời. |

## Cấu trúc khuôn mẫu

| Dấu hiệu | Ví dụ | Sửa |
|---|---|---|
| ✱ "Không chỉ… mà còn…" | "Công cụ này không chỉ nhanh mà còn chính xác." | "Công cụ này nhanh và chính xác." Hoặc chỉ giữ ý quan trọng hơn. |
| "Không phải X, mà là Y" để tạo kịch tính | "Đây không phải là một công cụ, mà là một người bạn đồng hành." | Nói Y là gì, bằng chi tiết. |
| Bộ ba tính từ hoặc danh từ | "nhanh chóng, hiệu quả và tiện lợi" | Giữ một từ đúng nhất, kèm bằng chứng. |
| ✱ Mệnh đề đuôi bình luận | "…, góp phần nâng cao nhận thức", "…, qua đó khẳng định vị thế", "…, từ đó mở ra cơ hội" | Tách thành câu riêng, nói rõ ai làm gì và bằng chứng nào; nếu chỉ là lời bình chung chung thì bỏ. |
| ✱ Né chữ "là" | "đóng vai trò là cầu nối", "được xem là", "là minh chứng cho", "đánh dấu một bước tiến" | "X là Y", hoặc một động từ cụ thể: "X nối hai nhóm". |
| ✱ Danh từ hóa dày đặc | "Việc sử dụng AI giúp việc học…", "sự phát triển", "việc nâng cao" | Dùng động từ có chủ ngữ: "Nhóm dùng AI để…". |
| ✱ Câu nối rỗng | "Điều này cho thấy…", "Đáng chú ý là…", "Bên cạnh đó, …" mở nhiều đoạn liền nhau | Bỏ câu nối, để hai ý tự nối với nhau. |
| ✱ Nhịp câu đều đều | Mọi câu dài xấp xỉ nhau, mọi đoạn đều ba câu | Xen câu rất ngắn với câu dài. |

## Từ ngữ thổi phồng và sáo

| Dấu hiệu | Ví dụ | Sửa |
|---|---|---|
| ✱ Thổi phồng | "đóng vai trò vô cùng quan trọng", "không thể phủ nhận", "mang lại giá trị to lớn", "đa dạng và phong phú", "giải pháp toàn diện" | Thay bằng số liệu hoặc ví dụ có thật trong văn gốc, hoặc bỏ đi. |
| ✱ Ẩn dụ sáo | "hành trình", "khám phá", "chìa khóa", "bức tranh toàn cảnh" | Gọi đúng tên sự việc: "quá trình học", "cách làm". |
| ✱ Trạng từ đệm | "một cách hiệu quả", "một cách sâu sắc", "một cách toàn diện" | Bỏ. Động từ tốt không cần trạng từ đệm. |
| Mơ hồ hóa ý kiến | "Nhiều chuyên gia cho rằng…", "Có ý kiến cho rằng…" | Nêu ai, ở đâu; không có nguồn thì nói đó là ý của mình. |

## Phần chatbot bị dán sót

Nhóm này gần như chỉ AI để lại, nên `tells.py` cho trọng số cao nhất.

| Dấu hiệu | Ví dụ | Sửa |
|---|---|---|
| ✱ Lời chatbot nói với người dùng | "Chắc chắn rồi!", "Dưới đây là phiên bản đã chỉnh sửa", "Hy vọng thông tin này hữu ích", "Nếu bạn cần thêm…, hãy cho mình biết" | Xóa. |
| ✱ Chỗ trống chưa điền | "[Tên của bạn]", "[Tên công ty]", "[Ngày]" | Điền thông tin thật hoặc xóa. |
| ✱ Mã trích dẫn của chatbot | `oaicite`, `turn0search0`, `utm_source=chatgpt.com`, `[cite: 1]` | Xóa; nếu cần nguồn, chèn đường dẫn thật. |

## Định dạng

| Dấu hiệu | Sửa |
|---|---|
| ✱ Quá nhiều dấu gạch ngang dài (—) | Dùng dấu phẩy, dấu hai chấm, hoặc tách câu. |
| ✱ In đậm rải khắp đoạn văn | Chỉ in đậm thứ người đọc phải thấy ngay. |
| ✱ Emoji trong tiêu đề và gạch đầu dòng | Bỏ trong văn bản trang trọng. |
| Gạch đầu dòng cho thứ lẽ ra là một đoạn văn | Viết thành đoạn khi các ý có quan hệ nhân quả. |
| Tiêu đề viết hoa mọi chữ cái đầu | Chỉ viết hoa chữ đầu câu và tên riêng. |

## So với bài mẫu của bạn ✱

Khi `samples/` có bài bạn tự viết (tổng cộng từ 500 từ), `tells.py` so bản nháp với chúng:

- Từ hay gặp ở văn AI mà bạn hiếm khi dùng (dưới 1 lần trên 1.000 từ trong bài mẫu), nhưng bản nháp dùng từ 2 lần trở lên. Có tính điểm.
- Xưng hô khác bài mẫu, ví dụ bài mẫu gần như luôn xưng "mình" mà bản nháp xưng "tôi". Có tính điểm.
- Cụm lặp lại từ 3 lần trở lên mà bài mẫu không có. Không tính điểm, vì nhiều khi đó chỉ là từ của chủ đề; đọc lại để tự quyết.

Danh sách cố định không biết bạn viết thế nào. So với chính bài của bạn thì biết: một từ bình thường với người khác vẫn có thể lạ với giọng bạn.

## Giữ chất người, giữ chất Việt

- Chi tiết cụ thể do chính người viết đưa ra (tên lớp, con số, sự cố có thật) đáng giá hơn mọi câu bóng bẩy. Chỉ dùng chi tiết có trong văn gốc.
- Ý kiến có chủ đích ("mình nghĩ cách này sai, vì…") tốt hơn câu cân bằng mọi phía.
- Người thật hay lặp lại một từ ("nói", "làm"); văn AI thì cứ đổi sang từ đồng nghĩa. Lặp lại một từ đúng là bình thường.
- Giữ thành ngữ, cách nói, cách xưng hô và lối lập luận quen thuộc của người viết. Không ép văn theo khuôn tiếng Anh, như câu chủ đề ở đầu mỗi đoạn hay "Thứ nhất, thứ hai" máy móc, nếu người viết không viết thế.
- Từ quen miệng, cách xưng hô và độ dài câu của người viết lấy từ `style-card.md`.

## Nguồn

- [Wikipedia: Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing), WikiProject AI Cleanup. Nguồn của các nhóm: mệnh đề đuôi bình luận, né chữ "là", kết bài thách thức và triển vọng, phần chatbot bị dán sót. Trang cũng có mục "dấu hiệu không đáng tin" và "dấu hiệu của người viết thật".
- [Reinhart và cộng sự, PNAS 2025](https://arxiv.org/html/2410.16107v1): model đã instruction-tune dùng mệnh đề phân từ nhiều gấp 2–5 lần người và danh từ hóa nhiều gấp 1,5–2 lần.
- [Kobak và cộng sự, Science Advances 2025](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12219543/): đo từ dùng nhiều bất thường bằng cách so với văn người làm mốc. Danh sách từ tiếng Anh ở [GitHub](https://github.com/berenslab/llm-excess-vocab).
- [Russell, Karpinska, Iyyer, ACL 2025](https://aclanthology.org/2025.acl-long.267): người hay dùng LLM để viết nhận ra văn AI kể cả sau khi đã "humanize"; người thật lặp từ, AI đổi từ đồng nghĩa.
- [Paech và cộng sự, Antislop, ICLR 2026](https://arxiv.org/abs/2510.15061): lập hồ sơ cụm từ lặp của từng model bằng cách so với văn người.
- [Wang và cộng sự, Findings of EMNLP 2025](https://arxiv.org/html/2509.14543v1): bắt chước giọng từ vài bài mẫu; thêm bài ngoài khoảng 5 bài gần như không giúp thêm.
- [Agarwal, Naaman, Vashistha, CHI 2025](https://arxiv.org/abs/2409.11360): gợi ý của AI kéo người viết về lối viết phương Tây.
- [Anthropic, Prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices), mục "Control the format of responses": nói điều cần làm thay vì điều cấm, và viết prompt theo định dạng muốn nhận.
