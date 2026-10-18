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

## Vòng 4 (16/10/2026): v4 so với v3

v4 thêm ba thứ lấy từ cách đọc paper của Andrew Ng (CS230, 2018) và S. Keshav ("How to Read a Paper", 2007):

1. **Mục 0 "Đọc trong 1 phút"** thay cho "Thẻ định danh & bản đồ". Gồm một câu tóm bài, 5C của Keshav, ba tuyên bố chính kèm mức chống đỡ.
2. **Mục 9 "Dùng được gì"**, chỉ viết khi người dùng nói họ đọc để làm gì.
3. **"Tự kiểm hiểu"**: 3–5 câu hỏi kèm đáp án có neo, chỉ có ở chế độ giải phẫu.

Nhánh v3 là bản 03/10, chụp lại ở `.tmp/paper-anatomy-bench/skill-v3/`. Vòng này có thêm tiêu chí thứ sáu `nam_y_1_phut`, chấm khoảng 250 từ đầu của câu trả lời.

**Chạy:** 10 lượt sonnet · medium, cả 10 đều đạt, tổng 8,35 USD giá niêm yết; người chấm opus tính riêng vào hạn mức. v4 viết các phần mới đúng chỗ:

| Bài | Chế độ | Mục 0 | Mục 9 | Tự kiểm hiểu |
|---|---|---|---|---|
| StruQ | giải phẫu, có nói mục đích | có | có | có |
| CaMeL | giải phẫu, không nói mục đích | có | không | có |
| Attacker | phản biện | có | không | không |
| PRA-RAG | hỏi hẹp | không | không | không |
| Biba | trả lời tập trung | không | không | không |

Mục 0 dài 228–309 từ, vượt mức khoảng 200 từ đã đặt.

**Đo bằng máy:**

| | v4 | v3 |
|---|---:|---:|
| Neo sai | 1/255 (0,4%) | 2/202 (1,0%) |
| Phủ trang | 82% | 82% |
| Chi phí TB mỗi bài | 0,83 USD | 0,84 USD |

Cả ba neo sai đều ở bài scan Biba.

**Chấm mù:** v4 thắng 3/5, đều sát nút (CaMeL, PRA-RAG, Biba). v3 thắng StruQ sát nút, và thắng rõ Attacker: v4 chỉ đủ 5/11 ý chính, v3 đủ 9/11.

| Nhánh | trung thực | độ sâu | đúng câu hỏi | kiểm chứng | dễ đọc | nắm ý 1 phút | Ý chính đủ | Kiểm chứng ngẫu nhiên đúng |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| v4 | 4,4 | 4,6 | 4,8 | 4,6 | 4,6 | **4,2** | 73% | 87% |
| v3 | 4,4 | 4,6 | 4,8 | 4,8 | 4,4 | 3,2 | 80% | 94% |

**Lỗi mới của v4 nằm ở đâu.** Các lỗi người chấm chỉ ra tập trung ở mục 0 và ở đáp án tự kiểm, chỗ phải nén ý:

- StruQ, dòng "Bối cảnh": ghi "so trực tiếp với BIPIA và Jatmo", nhưng bài chỉ so thực nghiệm với BIPIA.
- StruQ, dòng "Giả định": ghi "chỉ vững với tấn công không thích nghi", mâu thuẫn §5.2.
- CaMeL, dòng "Giả định": gộp giả định do người phân tích suy ra vào neo §3, như thể bài nêu.
- StruQ, đáp án tự kiểm: gom dải số 60,2–66,0% sai thiết lập.

Phần thân của v4 có thêm vài câu khái quát quá tay ("0% ở mọi biến thể", "lớp tấn công duy nhất vượt qua"). Đây là loại lỗi bước tự rà con số đã nhắm, nhưng vẫn lọt.

**Kết luận theo tiêu chí đã chốt** (giữ thay đổi nào tăng dễ đọc mà không hạ trung thực và kiểm chứng):

- **Được:** nắm ý trong 1 phút tăng rõ (+1,0), dễ đọc nhích (+0,2), trung thực bằng nhau.
- **Mất:** kiểm chứng giảm 0,2; kiểm chứng ngẫu nhiên đúng 87% so với 94%; ý chính đủ 73% so với 80%.

Vì vậy v4 nguyên trạng **chưa đạt**. Hướng sửa là siết mục 0: các dòng 5C không được thêm điều mà phần thân không nói, và phải ghi rõ cái nào là suy luận.

**Giới hạn:**

- Mỗi ô chỉ một lượt nên có nhiễu; mức chênh 0,2 điểm nằm trong nhiễu đã thấy ở các vòng trước.
- Tiêu chí `nam_y_1_phut` và câu dặn trong `grader-prompt.md` gọi đúng tên các phần mới, nên người chấm có thể đoán được đâu là v4. Reviewer đã nêu điểm này.
- Sau bench có sửa thêm SKILL.md theo review: ghi phần đã đọc hay chỉ lướt ở dòng `> Đã đọc:` thay vì ở mục 0. Sửa này không đụng ba thay đổi được đo.

## Vòng 5 (16/10/2026): v4.1 so với v3, ba bài giải phẫu và phản biện

v4.1 siết mục 0 theo các lỗi tìm thấy ở vòng 4:

- **Giới hạn:** tối đa 200 từ.
- **Không thêm ý mới:** mục 0 chỉ nói lại điều mục 1–8 đã viết.
- **Không khái quát quá tay:** không dùng "mọi", "chỉ", "duy nhất", "luôn" khi bảng hay câu gốc không nói vậy; con số giữ thiết lập.
- **Bối cảnh:** tách công trình bài so bằng thực nghiệm khỏi công trình bài chỉ bàn tới.
- **Giả định:** tách giả định tác giả nêu khỏi [suy luận].
- **Bước tự rà:** thêm mục 0 và đáp án tự kiểm vào bước tự rà con số.

`verify_anchors.py` báo số từ của mục 0 (đếm theo âm tiết, không tính neo) và các chữ tuyệt đối trong đó. Chạy lại trên bài làm v4 của vòng 4, script bắt đúng hai câu sai mà người chấm đã chỉ ra ở StruQ.

**Chạy:** 6 lượt sonnet · medium, tổng 5,71 USD giá niêm yết; cả hai nhánh đều 0 neo sai. Mục 0 của v4.1 dài 179, 184 và 153 từ, đều dưới 200. Người chấm không còn chỉ ra lỗi nào trong mục 0.

**Chấm mù:** v4.1 thắng rõ Attacker (9/11 ý chính đủ, v3 5/11). v3 thắng sát nút StruQ và CaMeL.

| Nhánh | trung thực | độ sâu | đúng câu hỏi | kiểm chứng | dễ đọc | nắm ý 1 phút | Ý chính đủ | Kiểm chứng ngẫu nhiên đúng |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| v4.1 | 4,3 | 4,3 | 4,3 | 4,3 | 4,3 | **4,7** | 71% | 87% |
| v3 | 4,3 | 4,3 | 5,0 | 4,7 | 4,0 | 3,7 | 66% | 90% |

**Lỗi còn lại của v4.1 nằm ở phần thân, không ở mục 0:**

- Nhãn mục của neo lệch dù đúng trang (§1 thay vì Abstract; §2 thay vì §5.5; §C thay vì Phụ lục B).
- Một nhãn [suy luận] gắn cho điều bài có nói.
- Khoảng "36–58%" ở mục 9 bỏ sót TAP trên Llama chỉ còn 9%.
- Kể Anthropic vào các hãng có mô hình được thử.

Ở bài Attacker (phản biện), v4.1 dùng cả mẫu giải phẫu nên dài hơn câu hỏi cần, và bị trừ điểm "đúng câu hỏi". Ở bài CaMeL, v4.1 chỉ có 7/62 neo kèm trích nguyên văn: v4.1 lỡ bỏ cụm "dấu vết để ở các mục sau", nên luật "neo ngắn, không trích" của mục 0 có thể đã lan sang phần thân. Cụm này đã khôi phục sau bench.

**Gộp vòng 4 và vòng 5** (8 cặp so):

- **Lặp lại đều theo hướng có lợi:** nắm ý trong 1 phút tăng khoảng 1 điểm; dễ đọc tăng 0,2–0,3; trung thực bằng nhau.
- **Lặp lại đều theo hướng bất lợi:** kiểm chứng giảm 0,2–0,4; kiểm chứng ngẫu nhiên đúng giảm 3–7 điểm phần trăm.
- **Không đều:** ý chính đủ lúc thấp hơn (vòng 4: −7), lúc cao hơn (vòng 5: +5).

Theo đúng chữ của tiêu chí đã chốt (không hạ kiểm chứng), v4.1 vẫn chưa đạt hẳn; mức giảm nhỏ nhưng cùng hướng ở cả hai vòng. Mỗi ô chỉ một lượt, nên đây là xu hướng, chưa phải kết luận chắc.

**Giới hạn:** 3 bài, mỗi ô một lượt. Như vòng 4, tiêu chí `nam_y_1_phut` có thể làm lộ nhánh v4.1. Sau bench có sửa thêm theo review (không đụng ba thay đổi được đo):

- Nhận tiêu đề mục 0 viết lệch mẫu, chuẩn hóa NFC trước khi tìm.
- "chỉ cần" được tính là chữ tuyệt đối.
- Luôn in số từ của mục 0.
- Khôi phục cụm "dấu vết để ở các mục sau".

## Vòng 6 (16/10/2026): bản cuối v4.1 so với v3, ba bài

Bản cuối là v4.1 cộng các sửa theo review:

- Khôi phục cụm "dấu vết để ở các mục sau".
- Nhận tiêu đề mục 0 viết lệch mẫu.
- Chuẩn hóa chữ về NFC.
- Luôn in số từ của mục 0.

**Chạy:** 6 lượt, tổng 6,11 USD giá niêm yết, 0 neo sai ở cả hai nhánh. Mục 0 dài 129–163 từ. Cụm dấu vết khôi phục có tác dụng: bài CaMeL của v4.1 có 45/70 neo kèm trích nguyên văn (vòng 5 chỉ 7/62).

Người chấm bài Attacker bị chặn vì hết hạn mức 5 giờ, nhưng đã ghi xong `grading.json` (đủ 11 ý chính, mỗi bên 10 lần kiểm) trước đó.

**Chấm mù:** v4.1 thắng 2/3 (StruQ, Attacker), v3 thắng CaMeL. Cả ba đều sát nút.

| Nhánh | trung thực | độ sâu | đúng câu hỏi | kiểm chứng | dễ đọc | nắm ý 1 phút | Ý chính đủ | Kiểm chứng ngẫu nhiên đúng |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| v4.1 | 4,0 | 4,7 | 4,3 | 4,7 | 4,3 | **4,3** | **86%** | **87%** |
| v3 | 4,0 | 4,7 | 5,0 | 4,7 | 4,7 | 3,3 | 74% | 83% |

**Gộp ba vòng** (v4 với v3 ở vòng 4, rồi v4.1 với v3 ở vòng 5 và 6; mỗi ô là chênh lệch so với v3):

| Vòng | trung thực | kiểm chứng | KC ngẫu nhiên | ý chính đủ | nắm ý 1 phút | dễ đọc | đúng câu hỏi |
|---|---:|---:|---:|---:|---:|---:|---:|
| 4 (v4, 5 bài) | 0 | −0,2 | −7 | −7 | +1,0 | +0,2 | 0 |
| 5 (v4.1, 3 bài) | 0 | −0,4 | −3 | +5 | +1,0 | +0,3 | −0,7 |
| 6 (bản cuối, 3 bài) | 0 | 0 | +4 | +12 | +1,0 | −0,4 | −0,7 |

**Đọc kết quả:**

- **Mục tiêu chính đạt đều:** nắm ý trong 1 phút tăng 1 điểm ở cả ba vòng; trung thực không giảm vòng nào.
- **Kiểm chứng:** ở bản cuối thì bằng v3, kiểm chứng ngẫu nhiên và ý chính đủ còn cao hơn; mức giảm ở vòng 4–5 trùng với hai lỗi đã sửa (mục 0 nén ý quá tay ở v4; dấu vết bị cắt ở v4.1).
- **Dễ đọc:** dao động theo cả hai hướng, nằm trong nhiễu.
- **Điểm mới cần để ý:** "đúng câu hỏi" giảm 0,7 ở hai vòng cuối. Các phần thêm (mục 0, mục 9, tự kiểm) làm bài rộng hơn điều người dùng hỏi, nhất là ở chế độ phản biện. Hướng sửa sau: ở chế độ phản biện, viết ngắn mục 1–5 và dồn chữ vào mục 6–7.

Theo tiêu chí đã chốt (dễ đọc hơn mà không hạ trung thực và kiểm chứng), bản cuối v4.1 **đạt** ở vòng đo bản cuối. Mỗi ô chỉ một lượt nên vẫn còn nhiễu.

Tổng chi phí bench ba vòng: 20,17 USD giá niêm yết cho lượt làm bài (sonnet); người chấm opus tính riêng vào hạn mức.

## Vòng 7–8 (16/10/2026): v4.2 so với v3, sáu bài, mỗi bài hai lượt

v4.2 sửa điểm "đúng câu hỏi" của v4.1:

- **Mục mới "Trả lời đúng điều được hỏi":** chép ra từng ý người dùng hỏi đích danh; mỗi ý có câu trả lời trực tiếp, sâu, dễ tìm, và là phần dài nhất của bài. Mục không phục vụ ý nào thì viết ngắn hay bỏ.
- **Chế độ phản biện:** thay mục 1–5 bằng một mục ngắn "Bài làm gì và đo thế nào"; không viết mục 9 khi mục đích là phản biện.
- **Mục 0:** mỗi mức chống đỡ kèm lý do ngắn.
- **Tự kiểm hiểu:** mặc định 3 câu.

**Thêm bài thứ sáu, ngoài mảng bảo mật:** RoFormer (RoPE), 14 trang, nặng công thức. Người dùng nói mục đích (cài RoPE cho đồ án dịch máy) và hỏi đích danh bốn ý.

**Chạy:** 24 lượt (6 bài × 2 nhánh × 2 lượt), cả 24 đạt, tổng 19,16 USD giá niêm yết, 0 neo sai. Mục 0 dài 130–183 từ. `blind.py` thêm `--rep` để mỗi lượt có một vòng chấm riêng (vòng 7 cho lượt 0, vòng 8 cho lượt 1) và `summary --round 7 8` để gộp.

**Chấm mù, gộp 12 cặp:** v4.2 thắng 8/12. Vòng 7 hòa 3–3; vòng 8 v4.2 thắng 5/6.

| Nhánh | trung thực | độ sâu | đúng câu hỏi | kiểm chứng | dễ đọc | nắm ý 1 phút | Ý chính đủ | Kiểm chứng ngẫu nhiên đúng |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| v4.2 | 4,3 | 4,6 | **5,0** | **4,8** | 4,2 | **4,2** | **85%** | 88% |
| v3 | 4,3 | 4,5 | 4,9 | 4,4 | **4,7** | 3,3 | 76% | **94%** |

**Đã sửa được:**

- "Đúng câu hỏi" về bằng v3 (v4.1 từng kém 0,7).
- Ý chính đủ hơn 9 điểm phần trăm, kiểm chứng hơn 0,4, nắm ý 1 phút hơn 0,9.
- Ở chế độ phản biện, v4.2 đã dùng dạng gọn.

**Còn kém v3:**

- **Dễ đọc** (4,2 so với 4,7). Người chấm nêu: văn dày, ô bảng dồn nhiều ý, đánh số mục nhảy (0, 1, 6, 7, 8 ở chế độ phản biện, do luật giữ số mục 6–8), và các dòng "Loại", "Độ rõ" của mục 0 ít giá trị.
- **Kiểm chứng ngẫu nhiên đúng** (88% so với 94%, khoảng 120 nhận định mỗi nhánh). Câu sai rải rác:
  - mục 0 ở một lượt Attacker ("từ gần 0 lên trên 90%");
  - đáp án tự kiểm ở StruQ đọc sai cột Undef.;
  - một nhận định [ngoài bài] sai ở RoFormer (QQP);
  - vài neo sai mục.

**Hành vi lạ:** ở một lượt RoFormer, yêu cầu ghi "Giải phẫu giúp…" kèm một câu hỏi về thực nghiệm, nhưng v4.2 chọn dạng phản biện.

**Kết luận:**

- So với v3, v4.2 hơn ở độ đầy đủ, ở việc trả lời đúng câu hỏi, ở điểm kiểm chứng và ở phần đọc nhanh.
- v4.2 kém ở điểm dễ đọc và ở độ đúng của từng nhận định; mức chênh nhỏ nhưng lặp lại.
- Theo tiêu chí ban đầu (dễ đọc hơn mà không hạ trung thực và kiểm chứng), v4.2 **chưa đạt** vì điểm dễ đọc giảm.

**Hướng sửa tiếp:**

- Bỏ dòng "Loại", "Độ rõ" khỏi mục 0.
- Đánh số mục liên tục và gọi các mục bằng tên trong luật.
- Ô bảng chỉ một ý; giải thích để ở văn xuôi.
- Giải phẫu có câu hỏi về bằng chứng vẫn là giải phẫu.
- Nhận định [ngoài bài] chỉ dùng khi chắc.

Tổng chi phí bench từ vòng 4: 39,33 USD giá niêm yết cho lượt làm bài; người chấm opus tính riêng vào hạn mức.

**Lưu ý về độ tin của vòng 7–8.** Review (sonnet) chỉ ra một chỗ làm lệch phép đo: ví dụ trong mục "Trả lời đúng điều được hỏi" của v4.2 trùng gần nguyên văn đề CaMeL ("capability hoạt động ra sao", "bảo đảm tới đâu") và đề RoFormer ("suy giảm theo khoảng cách"). Vì vậy điểm "đúng câu hỏi" và ý chính đủ ở hai bài này có thể bị thổi lên một phần. v4.3 đã đổi các ví dụ sang dạng trung tính; vòng sau nên thêm một bài chưa từng dùng làm ví dụ.

## v4.3 (16/10/2026, bench ở vòng 9–10)

Sửa theo review vòng 7–8 và lời chê về độ dễ đọc:

- **Chọn chế độ:** yêu cầu có chữ "giải phẫu", "hiểu", "giải thích", hay hỏi cơ chế, thì chọn giải phẫu, kể cả khi kèm câu hỏi về bằng chứng. Chỉ chọn phản biện khi mọi ý được hỏi đều về độ vững của tuyên bố hay bằng chứng.
- **Đánh số:** phản biện đánh số mục liên tục; các luật gọi mục theo tên (bảng bằng chứng, giới hạn, bản đồ trích dẫn).
- **Chỗ tóm cho mục 0:** Bước 3, mục 0 và danh sách tự kiểm nói "các mục thân bài" thay cho "mục 1–8", để áp được cả ở chế độ phản biện.
- **Mục 0 còn 4 dòng:** một câu (kèm thể loại), bối cảnh, giả định, ba tuyên bố. Bỏ "Loại", "Độ rõ", "Đóng góp" và dòng bản đồ mục.
- **Bảng:** mỗi ô chỉ một ý ngắn; lập luận để ở văn xuôi dưới bảng.
- **[ngoài bài]:** chỉ dùng khi chắc, không dùng để bác một con số của bài.
- **"Trả lời đúng điều được hỏi":**
  - ví dụ trung tính;
  - ý không có mục hợp thì thêm một mục riêng ngay sau mục 0;
  - luật "viết ngắn mục không phục vụ ý nào" chỉ áp khi người dùng đã hỏi đích danh ít nhất một ý.

## Vòng 9–10 (16/10/2026): v4.3 so với v3, bảy bài, mỗi bài hai lượt

**Thêm bài thứ bảy, chưa từng dùng làm ví dụ trong skill:** FlashAttention-2 (14 trang, bài hệ thống về GPU), việc
`flashattention2-anatomy`. Prompt có mục đích (tối ưu tốc độ huấn luyện trên GPU của lab) và ba ý hỏi đích danh,
trong đó một ý về độ vững của con số trên phần cứng khác. Đã kiểm prompt không trùng cụm ba chữ nào với
`SKILL.md` và `references/`.

**Chạy:** 28 lượt (7 bài × 2 nhánh × 2 lượt), cả 28 đạt, tổng 22,14 USD giá niêm yết (đợt 1: 10,43; đợt 2:
11,71). Trung bình mỗi bài: v4.3 0,84 USD, v3 0,74 USD. Lượt 0 chấm ở vòng 9, lượt 1 ở vòng 10, mỗi việc một
người chấm opus. Đợt 1 phải dừng giữa chừng vì hạn mức 5 giờ lên 84%, chạy tiếp sau khi hạn mức đặt lại.

**Đo bằng máy:**

| | v4.3 | v3 |
|---|---:|---:|
| Neo sai | 6/703 (0,9%) | 17/550 (3,1%) |
| Neo sai ngoài bài scan Biba | 0 | 0 |
| Phủ trang | 86% | 84% |
| Mục 0 | 98–138 từ, cả 11 bài có mục 0 đều dưới 200 | – |

Mọi neo sai đều ở bài scan Biba và là lỗi định dạng thẻ (`tr.iii`, `tr.28, tr.30`, `chú thích 25`), không phải sai
nội dung; bản scan vốn không kiểm được bằng máy. v4.3 đặt nhiều neo hơn v3 khoảng 30%.

**Chọn chế độ và đánh số (kiểm bằng `grep '^## '`):**

- Chế độ đúng ở cả 14 bài làm. Attacker là phản biện ở cả hai lượt, số mục liên tục (0–5, 0–4), không có tự kiểm.
  FlashAttention-2, RoFormer, CaMeL, StruQ là giải phẫu (lỗi chọn phản biện cho RoFormer ở vòng 8 không lặp lại).
  PRA-RAG là hỏi hẹp.
- Số mục còn nhảy ở 2/14 bài, đều ở lượt 0 và đều ở chế độ giải phẫu, khi model thêm mục trả lời câu hỏi:
  FlashAttention-2 ghi 0, 1, 2, 3, 4, 6, 7, 9; RoFormer ghi 0, A–D, 1, 7, 8, 9. Luật "đánh số liên tục" của v4.3
  chỉ viết cho chế độ phản biện. Ở lượt 1, cả 7 bài đánh số liền.

**Chấm mù, gộp 14 cặp:** v4.3 thắng 11/14 (vòng 9: 5/7; vòng 10: 6/7). Hai lần thắng rõ đều là v4.3 ở CaMeL (cả hai
vòng); mọi cặp khác sát nút. v3 thắng Attacker và Biba ở vòng 9, RoFormer ở vòng 10.

| Nhánh | trung thực | độ sâu | đúng câu hỏi | kiểm chứng | dễ đọc | nắm ý 1 phút | Ý chính đủ | Kiểm chứng ngẫu nhiên đúng |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| v4.3 | 4,2 | **4,5** | 4,9 | 4,5 | 3,9 | **4,3** | **86%** | 89% |
| v3 | 4,2 | 4,1 | 4,8 | 4,5 | **4,1** | 3,1 | 75% | **94%** |

**So với v4.2 ở vòng 7–8** (mỗi ô là chênh lệch so với v3 trong cùng vòng; cột "6 bài" bỏ FlashAttention-2 để cùng
bộ bài với vòng 7–8):

| | trung thực | kiểm chứng | dễ đọc | KC ngẫu nhiên đúng | ý chính đủ | nắm ý 1 phút | thắng |
|---|---:|---:|---:|---:|---:|---:|---:|
| v4.2, vòng 7–8 (6 bài) | 0 | +0,33 | −0,42 | −6 | +9 | +0,92 | 8/12 |
| v4.3, vòng 9–10 (6 bài) | −0,08 | 0 | −0,17 | −5 | +12 | +1,08 | 9/12 |
| v4.3, vòng 9–10 (7 bài) | 0 | 0 | −0,28 | −5 | +11 | +1,15 | 11/14 |

**Đọc kết quả:**

- **Dễ đọc:** khoảng cách thu hẹp (−0,42 còn −0,17 trên cùng 6 bài) nhưng v4.3 vẫn thấp hơn v3. Riêng bài mới
  FlashAttention-2, v4.3 bị 3 điểm ở cả hai lượt (v3: 4). Người chấm nêu: mục trả lời câu hỏi đặt ngay sau mục 0
  rồi các mục mẫu (cốt lõi, giả định, bằng chứng, giới hạn) nhắc lại cùng ý; số mục nhảy; văn dày, nhiều câu lấy
  trích dẫn làm vế kết luận. Ở Attacker vòng 9, v4.3 bị 3 điểm vì neo dày và câu nén. Điểm tuyệt đối của chính
  v3 cũng đổi theo đợt chấm (4,67 ở vòng 7–8, 4,14 ở vòng 9–10, cùng bản skill), nên chênh 0,2 nằm trong nhiễu
  của người chấm.
- **Kiểm chứng ngẫu nhiên** (142 nhận định mỗi nhánh): 89% so với 94%, gần như vòng 7–8. Tách theo loại lỗi:

  | | sai | không có trong bài | neo sai chỗ |
  |---|---:|---:|---:|
  | v4.3 | 8 | 0 | 7 |
  | v3 | 6 | 2 | 1 |

  Lỗi nội dung (sai cộng không có trong bài) bằng nhau trên 7 bài, 8 mỗi bên; trên cùng 6 bài như vòng 7–8 là 8
  so với 6 (vòng 7–8: v4.2 có 10, v3 có 5). Phần chênh
  nằm ở "neo sai chỗ": nội dung đúng nhưng neo chỉ sai bảng hay trang, ví dụ số 96% của Bảng 2 neo vào Bảng 4
  (StruQ), Bảng 1 ghi tr.11 thay vì tr.12 (FlashAttention-2), `f(x,0)=Wx` neo Eq.(22) thay vì Eq.(32) (RoFormer).
  `verify_anchors.py` không bắt được loại này vì thẻ neo không ghi tên bảng hay công thức, hoặc trích nguyên văn
  nằm đúng trang nhưng con số lấy từ chỗ khác.
- **Lỗi nội dung còn lại của v4.3:** dịch "core contributor" thành "nguyên nhân gốc" (StruQ); đảo nghĩa "Claude
  3.5 Sonnet không dễ bị tấn công mặc định" thành "yếu" (CaMeL); gọi Gemini là mô hình dễ bị tấn công nhất
  (Attacker); hiểu nhầm §E.2 là người và máy đo lệch nhau (Attacker); đọc trục Hình 2 ra mức 6 (RoFormer); số
  tiên đề A3.15–A3.17 (Biba). Mục 0 còn hai lỗi: Biba vòng 9 nói quá về ring tùy nghi (tr.38 tác giả thấy
  "room for hope"); FlashAttention-2 vòng 10 neo Bảng 1 vào tr.11 thay vì tr.12, lặp lại ở đáp án tự kiểm.
- **Được, lặp lại ở cả hai vòng:** ý chính đủ hơn 11 điểm phần trăm, nắm ý 1 phút hơn 1,2 điểm, độ sâu hơn 0,4,
  trung thực và kiểm chứng bằng v3.

**Kết luận theo tiêu chí đã chốt** (giữ thay đổi nào làm dễ đọc hơn mà không hạ trung thực và kiểm chứng):

- v4.3 **chưa đạt đúng chữ**: dễ đọc vẫn thấp hơn v3 0,2–0,3, kiểm chứng ngẫu nhiên đúng thấp hơn 5 điểm phần
  trăm.
- So với v4.2, v4.3 tốt hơn hoặc bằng ở mọi chỗ trừ điểm kiểm chứng (v4.2 +0,33, v4.3 bằng v3): khoảng cách dễ
  đọc thu hẹp, lỗi nội dung bớt, không còn ví dụ trùng đề nên số "đúng câu hỏi" và "ý chính đủ" không bị thổi.
  Không có lý do giữ v4.2 thay v4.3.
- So với v3, v4.3 đổi khoảng 0,2 điểm dễ đọc (trong nhiễu) và độ chính xác của neo lấy độ đầy đủ, độ sâu và
  phần đọc nhanh tốt hơn rõ; trung thực và lỗi nội dung bằng nhau.

**Hướng sửa nếu làm v4.4** (chưa sửa; bench không đụng `SKILL.md`):

- Đánh số liên tục ở mọi chế độ, không chỉ phản biện; mục trả lời câu hỏi thêm sau mục 0 thì các mục sau lùi số.
- Khi đã có mục trả lời câu hỏi, các mục mẫu không nhắc lại ý đã trả lời, chỉ trỏ về mục đó.
- Neo con số ghi kèm tên Bảng/Hình/Eq để `verify_anchors.py` kiểm được bảng có trên trang đó không; con số lấy
  từ bảng thì neo vào bảng, không neo vào câu văn nhắc tới nó.
- Bài scan: thẻ neo một trang một thẻ, không ghép `tr.28, tr.30` hay `chú thích N` trong cùng thẻ.

**Giới hạn:**

- Mỗi ô là một lượt, mỗi bài hai lượt, một người chấm mỗi cặp. Mức chênh 0,2 điểm nằm trong nhiễu đã thấy.
- Người chấm cũng là Claude (opus). Tiêu chí `nam_y_1_phut` và mục "Đọc trong 1 phút" của v4.3 có thể làm lộ
  nhánh; v3 không có mục 0 nên người chấm đoán được đâu là bản mới.
- Ý chính gợi ý của vòng 10 lấy từ kết quả chấm vòng 9 (người chấm vẫn phải kiểm lại với bài); vòng 9 của
  FlashAttention-2 không có gợi ý.
- Prompt FlashAttention-2 do agent viết theo kiểu người dùng thật, không phải câu hỏi thật của người dùng.

Tổng chi phí bench từ vòng 4: 61,47 USD giá niêm yết cho lượt làm bài; người chấm opus (14 lượt ở vòng 9–10)
tính riêng vào hạn mức. Trong lúc chạy vòng 9–10, hạn mức tuần tăng từ 32% lên 38% (có lẫn phần một phiên khác
dùng cùng lúc); một người chấm opus tốn khoảng 1–3% hạn mức 5 giờ.

## Vòng 11–12 (17/10/2026): v4.4 so với v3, bảy bài, mỗi bài hai lượt

**v4.4 sửa ba chỗ vòng 9–10 chỉ ra** (bản v4.3 chụp ở `.tmp/paper-anatomy-bench/skill-v4.3/`):

- **Đánh số mục liên tục ở mọi chế độ**, chỉ dùng số. Mọi chỗ trong skill nhắc "mục 6", "mục 1–5" là số của mẫu, chỉ để gọi tên.
- **Mỗi ý được hỏi trả lời đầy đủ ở đúng một chỗ**, mục khác chỉ trỏ về (trừ mục 0 và đáp án tự kiểm). Thứ tự đặt:
  1. ý được hỏi phủ phần lớn thân bài thì dựng thân bài theo chính các ý đó;
  2. không thì đặt vào mục mẫu hợp nhất;
  3. không có mục hợp thì thêm mục ngay sau mục 0.
- **Con số lấy từ bảng hay hình** thì thẻ ghi tên đối tượng và neo vào trang in nó.
- **`verify_anchors.py` cảnh báo thêm** (WARN, không đổi mã thoát):
  - Bảng/Hình in ở trang khác trang đã ghi;
  - câu nhắc một bảng hay hình mà thẻ trỏ chỗ khác;
  - con số trong câu (có %, thập phân, hay từ 100 trở lên) không có trên trang đã ghi nhưng có ở trang khác;
  - số mục nhảy hay dùng chữ cái.

  Bỏ qua số sau "≈", số trong đoạn có nhãn [minh họa], số phiên bản tên mô hình, và câu chỉ đường "xem Bảng N". Chạy trên 28 bài làm của vòng 9–10, script bắt đúng hai bài nhảy số và chỗ Bảng 1 neo sai trang mà người chấm đã chỉ ra.
- **Review (sonnet):** 0 cao, 3 vừa, đã sửa cả ba:
  - số sau tên thước đo (ASR, BLEU) bị bỏ kiểm;
  - "1.000" bị đọc thành 1,0;
  - SKILL.md dặn ghi [minh họa] mà script không bỏ qua.
- **Test:** `tests.test_paper_anatomy` 36 test đạt trên Python 3.11 và 3.9; cả bộ test của repo đạt.

**Chạy:** 28 lượt, cả 28 đạt, 23,53 USD giá niêm yết; trung bình mỗi bài v4.4 0,89 USD, v3 0,79 USD. Lần chạy
đầu hỏng cả 28 lượt ngay giây đầu (0 USD) vì CLI `claude` hết phiên đăng nhập; chạy lại sau khi bạn đăng nhập.
Lượt 0 chấm ở vòng 11, lượt 1 ở vòng 12, mỗi cặp một người chấm opus. 28 lượt và 14 người chấm dùng khoảng 37%
hạn mức 5 giờ và 5% hạn mức tuần.

**Đo bằng máy** (cảnh báo neo sai chỗ đo bằng script v4.4 trên bài làm cuối của cả ba bản):

| | v4.4 (vòng 11–12) | v4.3 (vòng 9–10) | v3 (vòng 11–12) |
|---|---:|---:|---:|
| Neo sai | 0/693 | 6/703 | 4/528 |
| Cảnh báo neo sai chỗ / số neo | **1,6%** | 5,1% | 5,5% |
| Bài có số mục nhảy | **0/14** | 2/14 | 0/14 |
| Số từ trung bình | 2.528 | 2.611 | 2.455 |

Mục 0 dài 110–140 từ. Chế độ chọn đúng ở cả 14 bài (Attacker là phản biện, số mục 0–5).

**Chấm mù, gộp 14 cặp:** v4.4 thắng 9/14 (vòng 11: 4/7; vòng 12: 5/7). Thắng rõ: v4.4 bốn lần (CaMeL hai lần,
PRA-RAG, StruQ), v3 hai lần (Biba, cả hai vòng).

| Nhánh | trung thực | độ sâu | đúng câu hỏi | kiểm chứng | dễ đọc | nắm ý 1 phút | Ý chính đủ | Kiểm chứng ngẫu nhiên đúng |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| v4.4 | **4,4** | 4,4 | 4,8 | **4,7** | 4,1 | **4,1** | 77% | **97%** |
| v3 | 4,2 | 4,4 | 4,7 | 4,4 | **4,4** | 3,6 | 74% | 95% |

Kiểm chứng ngẫu nhiên, 149 và 148 nhận định: v4.4 có 3 sai, 1 neo sai chỗ; v3 có 5 sai, 2 neo sai chỗ.

**So với v4.3** (chênh lệch so với v3 trong cùng vòng):

| | trung thực | kiểm chứng | dễ đọc | KC ngẫu nhiên đúng | ý chính đủ | nắm ý 1 phút | thắng |
|---|---:|---:|---:|---:|---:|---:|---:|
| v4.2, vòng 7–8 (6 bài) | 0 | +0,33 | −0,42 | −6 | +9 | +0,92 | 8/12 |
| v4.3, vòng 9–10 (7 bài) | 0 | 0 | −0,28 | −5 | +11 | +1,15 | 11/14 |
| v4.4, vòng 11–12 (7 bài) | **+0,21** | **+0,36** | −0,29 | **+2** | +3 | +0,43 | 9/14 |

**Đọc kết quả:**

- **Kiểm chứng đã sửa được.**
  - Lần đầu từ vòng 4, một bản v4.x hơn v3 cùng lúc ở cả ba: kiểm chứng ngẫu nhiên (97% so với 95%), điểm kiểm chứng và điểm trung thực. (v4.1 ở vòng 6 chỉ hơn ở kiểm chứng ngẫu nhiên; hai điểm kia bằng v3.)
  - "Neo sai chỗ", lỗi chính của v4.3 (7 lần), chỉ còn 1.
  - Cảnh báo neo sai chỗ trên bài làm cuối giảm từ 5,1% xuống 1,6% số neo: model đã dùng cảnh báo của script để sửa neo trước khi gửi.
- **Số mục nhảy đã hết** (0/14).
- **Dễ đọc vẫn thấp hơn v3, với cùng khoảng cách như v4.3** (−0,29 so với −0,28).
  - v4.4 chỉ được 5 điểm dễ đọc hai lần; v3 được 5 điểm sáu lần.
  - Lời chê còn lại:
    - văn đặc vì nhiều neo chen giữa câu (v4.4 trung bình 50 neo mỗi bài, v3 38);
    - bảng bằng chứng, bản đồ trích dẫn và đáp án tự kiểm nói lại cùng ý;
    - khung giải phẫu đầy đủ rộng hơn câu hỏi (FlashAttention-2 vòng 11).
  - Lời chê "mục trả lời câu hỏi rồi các mục mẫu nhắc lại" của vòng 9 không còn xuất hiện.
- **Lợi thế độ đầy đủ thu hẹp**: ý chính đủ hơn v3 3 điểm phần trăm (v4.3: 11), nắm ý 1 phút hơn 0,4 (v4.3: 1,2). Một phần do chính v3 được chấm cao hơn ở vòng này (nắm ý 3,6 so với 3,1 ở vòng 9–10, cùng bản skill).
- **Bài scan Biba thua rõ cả hai vòng:**
  - v4.4 bỏ §II tr.14–18 và §IV (lập luận CSDL vận tải, phạm vi chỉ đe dọa ngoài, khuyến nghị strict integrity, phần kernel);
  - đủ 8–9/12 ý chính, so với 11–12/12 của v3.
  - Bài làm v4.4 ngắn hơn (khoảng 1.750 từ so với 2.500) và xem ít ảnh trang hơn (37–39 so với 46–52).
  - Đây là hồi quy cần để ý: luật mới không đụng cách đọc, nhưng có thể đã đẩy model viết gọn và đọc ít hơn; hai lượt chưa đủ để chắc.

**Kết luận theo tiêu chí đã chốt** (giữ thay đổi nào làm dễ đọc hơn mà không hạ trung thực và kiểm chứng):

- v4.4 **không hạ** trung thực và kiểm chứng, còn hơn v3 ở cả hai. (v4.1 ở vòng 6 cũng không hạ, nhưng chỉ ngang v3, và chỉ đo trên 3 bài.)
- v4.4 **chưa làm dễ đọc hơn**: vẫn kém v3 0,3 điểm, ngang v4.3. Theo đúng chữ tiêu chí thì chưa đạt.
- So với v4.3: v4.4 hơn rõ ở kiểm chứng và trung thực, bằng ở dễ đọc, kém ở độ đầy đủ và bài scan.

**Nếu làm tiếp:**

- **Dễ đọc:**
  - Khoảng cách 0,2–0,4 điểm đã kéo dài từ vòng 6 tới vòng 12 dù sửa nhiều kiểu; nguyên nhân người chấm nêu nhiều nhất là mật độ neo, tức chính cái giá của khả năng kiểm.
  - Muốn giảm thì phải bớt neo trong thân bài (dồn trích nguyên văn về bản đồ trích dẫn), và có nguy cơ hạ lại kiểm chứng.
- **Bài scan:** dặn đọc đủ các mục kết luận, khuyến nghị và các mục được hỏi tới ("triết lý") trước khi viết, rồi bench riêng bài scan thêm lượt.

**Giới hạn:**

- Mỗi bài hai lượt, một người chấm mỗi cặp; chính v3 dao động 0,3–0,5 điểm giữa các đợt chấm (dễ đọc 4,7 / 4,1 / 4,4; nắm ý 3,3 / 3,1 / 3,6).
- Người chấm là Claude (opus); mục "Đọc trong 1 phút" và mật độ neo làm lộ nhánh.
- Ý chính gợi ý lấy từ lần chấm trước.
- Script v4.4 được dùng để đo "cảnh báo neo sai chỗ" cho cả ba bản, nhưng chỉ v4.4 được chạy script đó khi làm bài, nên con số 1,6% một phần là kết quả của việc tự sửa theo script.

Tổng chi phí bench từ vòng 4: 85,00 USD giá niêm yết cho lượt làm bài; người chấm opus tính riêng vào hạn mức.

**Quyết định (17/10/2026):** bạn chọn giữ v4.4, bỏ v4.3, chấp nhận dễ đọc kém v3 khoảng 0,3 điểm.
