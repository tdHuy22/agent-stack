# Kết quả bench paper-anatomy (03/10/2026)

Model làm bài: sonnet · medium (Sonnet 5.5). Người chấm: opus, chấm mù A/B. Mỗi ô là **một lượt chạy**, nên có
nhiễu: cùng một bài của bản cũ được hai người chấm khác nhau cho điểm trung thực 4,2 và 4,4. Đọc các con số theo
xu hướng lặp lại qua các vòng, không theo từng ô.

## Tìm skill có sẵn trước khi sửa

Không có skill nào nên dùng thay. Ứng viên đã xem (03/10/2026): `academic-paper-review` của bytedance/deer-flow (MIT,
phản biện kiểu NeurIPS), `read-arxiv-paper` của karpathy/nanochat (đọc mã TeX từ arXiv), `reading-papers` của
Amey-Thakur/AI-SKILLS (đọc ba lượt), bộ K-Dense claude-scientific-skills (chưa đọc được nguồn). Không cái nào neo
trang/mục/công thức và tách diễn giải khỏi suy luận. Lấy ý tưởng: bảng tuyên bố–bằng chứng, cái gì/ở đâu/vì sao,
đọc ba lượt của Keshav, danh sách tái lập của Pineau, mã TeX cho công thức. Thư viện trích PDF: dùng PyMuPDF có sẵn
(Marker, Docling mạnh hơn cho công thức nhưng nặng và chưa qua `vet-skill`; GROBID cần Java và dịch vụ).

## Những gì đổi so với bản cũ

| Bản cũ | Bản mới |
|---|---|
| Neo 【§ · tr. · Hình】 không ai kiểm | `verify_anchors.py` kiểm từng neo: trang có không, mục có chứa trang đó không, Hình/Bảng/Eq có trên trang không, đoạn trích nguyên văn có nằm đúng trang không. Model sửa tới khi 0 sai |
| Số trang in dò bằng số đứng riêng ở đầu/cuối trang (dễ nhầm số bảng) | Nhãn trang khai báo trong PDF, rồi số in khi chúng lệch đều so với số trang PDF, rồi số trang PDF |
| Bản đồ mục theo mẫu chữ | Mục lục (outline) của PDF, tự lấy lại số mục; không có thì dò theo cỡ chữ; ghép số mục bị tách dòng |
| In cả bài ra stdout (bị cắt mà không báo) | Ghi `paper.txt`, đọc theo đợt `--pages`; `--find` để neo đúng trang; `--render` xuất ảnh trang để nhìn hình, công thức, bản scan |
| Chỉ chạy được ở claude.ai (`/mnt/user-data`, `pip --break-system-packages`) | Chạy ở cả claude.ai và Claude Code; thiếu thư viện thì không tự cài toàn cục |
| Ba chế độ ngầm | Hỏi hẹp, giải phẫu, phản biện; mục 6 thành bảng tuyên bố ↔ bằng chứng ↔ mức chống đỡ; `references/critical-appraisal.md` |
| — | `references/hard-pdfs.md`: scan, hai cột, công thức, bài dài, nhãn trang; thể loại "tấn công/phòng thủ" |
| — | Tự rà nội dung sau khi kiểm neo: đối chiếu lại con số, tìm lại mọi câu "bài không nói", không đoán chi tiết thí nghiệm |

## Đo bằng máy (không cần người chấm)

Bài có lớp chữ (4 bài; bài scan Biba không kiểm được bằng máy):

| Bản | Neo | Neo sai | Chi phí TB mỗi bài | Thời gian TB |
|---|---:|---:|---:|---:|
| cũ | 167 | 17 (10,2%) | 0,51 USD | 132 giây |
| mới v1 | 158 | 0 | 0,78 USD | 187 giây |
| mới v2 | 160 | 0 | 0,72 USD | 177 giây |

Neo sai của bản cũ gồm: viện dẫn mục không tồn tại, neo Bảng/Hình vào trang không có nó, trang lệch. Bản mới đắt
hơn khoảng 40–50% vì đọc theo đợt, xem ảnh trang và chạy vòng kiểm neo.

## Chấm mù

| Vòng | So | Bản mới thắng | Ý chính đủ (mới / cũ) | Kiểm chứng ngẫu nhiên đúng (mới / cũ) |
|---|---|---|---|---|
| 1 | v1 với cũ | 5/5 (đều sát nút) | 88% / 85% | 94% / 92% |
| 2 | v2 với cũ | 3/5 (Biba thắng rõ; thua sát nút StruQ, Attacker) | 88% / 84% | 83% / 86% |
| 3 | v3 với cũ, chỉ 2 bài v2 thua | 2/2 (sát nút) | 83% / 83% | 91% / 76% |

Điểm trung bình 1–5 (trung thực / độ sâu / đúng câu hỏi / kiểm chứng / dễ đọc):

| | Vòng 1 | Vòng 2 | Vòng 3 (2 bài) |
|---|---|---|---|
| mới | 4,6 / 4,8 / 4,8 / **5,0** / 4,2 | 4,0 / 4,6 / 4,6 / **5,0** / 4,2 | 4,5 / 4,5 / 5,0 / **5,0** / 4,0 |
| cũ | 4,2 / 4,4 / 4,8 / 4,0 / **4,8** | 4,4 / 4,4 / 4,6 / 4,2 / **4,8** | 3,5 / 4,0 / 4,5 / 4,0 / **4,5** |

Lặp lại qua các vòng:
- **Kiểm chứng**: bản mới 5,0 ở mọi vòng, bản cũ 4,0–4,2. Người chấm nói neo kèm trích nguyên văn giúp lật PDF kiểm nhanh.
- **Độ đầy đủ**: bản mới nhiều ý chính hơn 3–4 điểm phần trăm; có bảng tuyên bố–bằng chứng, giả định ngầm, và hay bắt được chỗ chính bài báo tự mâu thuẫn (số trong chữ khác số trong bảng).
- **Dễ đọc**: bản cũ hơn (4,8 so với 4,2) ở mọi vòng. Neo dày kèm trích tiếng Anh là cái giá của khả năng kiểm. Vòng 2 đã giảm mật độ neo nhưng điểm chưa đổi.
- **Bản scan**: bản mới v1 bỏ hẳn thẻ neo; v2 sửa (dùng 【…】, đọc cả mục khuyến nghị) và thắng rõ (12/12 ý chính so với 8/12).
- **Lỗi nội dung còn lại**: neo đúng trang không có nghĩa câu đi kèm đúng. Lỗi hay gặp: gom con số thành khoảng sai, phê bình điều bài đã giải thích ở phụ lục, đoán chi tiết thí nghiệm. v3 thêm bước tự rà ba loại này; ở vòng 3, hai bài v2 từng thua đều thắng lại, kiểm chứng ngẫu nhiên đúng 91% so với 76%. Người chấm vẫn bắt được vài phê bình quá tay, nên lỗi này giảm chứ chưa hết.

Gộp ba vòng: bản mới thắng 10/12 lần so cặp, thua 2 (đều sát nút, ở v2).

## Giới hạn

- 5 bài, mỗi ô một lượt; cả 5 bài đều thuộc mảng bảo mật AI (theo thư viện của bạn). Chưa thử bài toán thuần, y sinh, nhân văn.
- Người chấm cũng là Claude; đã chấm mù nhưng câu trả lời có dấu hiệu nhận ra được (dòng "Kiểm neo tự động", trích nguyên văn trong neo).
- Bản cũ chạy ở Claude Code với PyMuPDF có sẵn trong PATH; ở claude.ai, bản cũ chạy đúng môi trường nó được viết cho.
- Tổng chi phí bench: khoảng 11,6 USD giá niêm yết cho lượt làm bài (sonnet); người chấm (opus, subagent) tính riêng vào hạn mức.
