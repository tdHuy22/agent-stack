---
name: paper-anatomy
description: >-
  Đọc sâu và "giải phẫu" một bài báo khoa học (PDF) bất kể lĩnh vực — KHÔNG phải tóm tắt,
  mà làm lộ ra cốt lõi, tinh hoa (ý tưởng then chốt), triết lý/giả định nền, kiến trúc và
  phương pháp đề xuất, với MỌI nhận định được neo về đúng mục/trang/hình/công thức gốc để
  kiểm chứng. Hãy dùng skill này bất cứ khi nào người dùng tải lên một bài báo/PDF học thuật
  và muốn "hiểu cốt lõi", "hiểu sâu", "nắm tinh hoa/triết lý/kiến trúc/phương pháp", "đọc kỹ",
  "phân tích", "giải phẫu/mổ xẻ", "không cần tóm tắt", hay hỏi "bài này thật sự đề xuất gì /
  vì sao nó hoạt động". Kích hoạt cả khi họ không nói đúng chữ "skill" — chỉ cần đưa paper và
  muốn hiểu thấu đáo thay vì một bản tóm tắt ngắn.
---

# Paper Anatomy — Giải phẫu bài báo khoa học

## Tinh thần (vì sao skill này tồn tại)

Tóm tắt làm bài báo *ngắn lại* và do đó đánh mất chi tiết. Mục tiêu ở đây ngược lại: **làm bài báo
dễ hiểu hơn mà không làm nó nông đi**. Một bản tóm tắt cho biết bài *nói gì*; một bản giải phẫu cho
biết bài *vì sao hoạt động*, *ý tưởng then chốt là gì*, *các mảnh ghép vào nhau ra sao*, và *thế giới
quan ngầm nào* chống đỡ nó. Người dùng muốn cầm được cái lõi — và muốn **kiểm chứng được** từng điều
ta nói bằng cách lật về đúng trang gốc.

Hai cam kết xuyên suốt:
1. **Trung thực với văn bản gốc.** Không bịa, không phóng đại. Mọi khẳng định về nội dung bài đều
   neo vào vị trí cụ thể trong bài. Cái gì bài không nói rõ thì gọi đúng tên là *suy luận của người
   phân tích*.
2. **Sâu, không nén.** Viết bằng văn xuôi giải thích, dựng lại cơ chế tới mức người đọc "thấy được
   bánh răng quay", chứ không liệt kê gạch đầu dòng cho có.

## Ngôn ngữ trình bày

**Song ngữ**: viết bằng tiếng Việt, **giữ nguyên thuật ngữ gốc** ở lần nhắc đầu kèm chú giải tiếng
Việt trong ngoặc — ví dụ: "cơ chế chú ý (attention)", "đối ngẫu (duality)". Giữ nguyên ký hiệu toán,
tên biến, tên mô hình, tên định lý. Không dịch ép những thuật ngữ đã thành chuẩn quốc tế.

## Quy ước trích dẫn (BẮT BUỘC dùng nhất quán)

Sau mỗi nhận định về nội dung bài, gắn một thẻ neo:

> 【§<mục> · tr.<trang> · <neo phụ nếu có>】

- `§<mục>`: số/tên mục như trong bài (vd `§3.2`, `§Method`, `§II-B`).
- `tr.<trang>`: số trang **in trên giấy** (con số người đọc thấy khi mở PDF). Nếu không dò được số in,
  ghi `tr.PDF<i>` (trang vật lý thứ i) và nói rõ một lần ở đầu rằng đang dùng trang PDF.
- Neo phụ khi liên quan: `Hình 2`, `Bảng 1`, `Eq.(4)`, `Thuật toán 1`, `Định lý 3`, `Bổ đề 2`.

Ví dụ: 【§3.1 · tr.5 · Eq.(4)】, 【§Results · tr.8 · Bảng 2】.

Phân biệt rõ ba mức (ghi nhãn khi cần thiết):
- *[nguyên văn]* — trích trực tiếp, **rất ngắn** (< 15 từ), trong ngoặc kép. Ưu tiên diễn giải thay
  vì trích nguyên văn; thẻ neo mới là thứ quan trọng, không phải chép lại câu chữ.
- *[diễn giải]* — ta nói lại bằng lời mình ý của tác giả (mặc định).
- *[suy luận]* — nhận định do người phân tích rút ra, bài không phát biểu thẳng. Luôn đánh dấu.

Nếu một điều **không có trong bài** hoặc bài viết mơ hồ → nói thẳng là không tìm thấy / chưa rõ.
Tuyệt đối không lấp chỗ trống bằng kiến thức chung rồi gán cho bài.

## Quy trình

### Bước 0 — Trích xuất ĐẦY ĐỦ bài báo theo trang
Tìm PDF trong `/mnt/user-data/uploads/`. Trước khi đọc, đọc skill `pdf-reading` nếu cần kỹ thuật
trích xuất nâng cao. Để có biểu diễn neo-trang sạch (dùng lại cho trích dẫn), chạy script kèm theo:

```bash
pip install pymupdf --break-system-packages   # nếu chưa có
python scripts/extract_paper.py "/mnt/user-data/uploads/<ten-file>.pdf"
```

Script in ra: báo cáo (số trang, có phải scan không), **bản đồ mục → trang**, và **toàn văn theo
trang** với mốc `===== PAGE i/N (printed: <nhãn>) =====`. Dùng nhãn `printed` làm số trang khi trích
dẫn. Nếu báo cáo cảnh báo PDF là **scan ảnh** (ít text), OCR trước bằng skill `pdf` rồi chạy lại —
đừng đoán nội dung từ ảnh chưa OCR.

Đọc **toàn bộ** văn bản trích ra, không bỏ trang. Đây là khâu "trích xuất đầy đủ" mà người dùng yêu cầu.

### Bước 1 — Nhận diện thể loại bài
"Kiến trúc" và "phương pháp" nghĩa khác nhau giữa bài lý thuyết, thực nghiệm, hệ thống, khảo sát,
quan điểm/nhân văn, hay dataset. Đọc `references/paper-genres.md` để chỉnh trục phân tích cho đúng
ngành. Ghi rõ bài thuộc (các) thể loại nào và **đâu là đóng góp chính theo lời tác giả** (neo trang).

### Bước 2 — Dựng bản đồ trong đầu trước khi viết
Trước khi viết ra, hãy chắc đã trả lời được cho chính mình:
- Bài coi *vấn đề thật sự* là gì? Khung hóa nó kiểu gì? 【neo】
- Đóng góp trung tâm là gì? 【neo】
- Nếu chỉ được nói **một ý** khiến phương pháp này chạy được, đó là ý nào? (tinh hoa) 【neo】
- "Ván cược" ngầm — giả định không hiển nhiên mà nếu đúng thì cách làm này mới đáng giá — là gì?
- Phương pháp vận hành ra sao, từng bước? Bỏ bước nào thì hỏng? 【neo】
- Bằng chứng nào chống đỡ, và ranh giới hiệu lực ở đâu? 【neo】

### Bước 3 — Viết bản giải phẫu (mẫu mặc định bên dưới)

### Bước 4 — Trình bày LINH HOẠT
- Câu hỏi hẹp ("ý cốt lõi và phương pháp là gì?") → trả lời tập trung đúng phần đó, vẫn neo trang.
  Không nhất thiết bê cả mẫu đầy đủ ra.
- Yêu cầu giải phẫu toàn diện, hoặc bài dài/đậm đặc → dùng mẫu đầy đủ. Nếu kết quả dài, **hỏi** người
  dùng có muốn xuất ra file không, hoặc chủ động đề nghị: file `.md` (mặc định) để dễ lưu/đọc lại,
  hoặc `.docx` nếu cần trang trọng (khi đó dùng skill `docx`). Lưu vào `/mnt/user-data/outputs/` và
  gọi `present_files`. Phân tích ngắn–vừa thì để thẳng trong khung chat.

## Mẫu giải phẫu mặc định

Điều chỉnh tiêu đề cho hợp thể loại; bỏ mục không liên quan; **đừng** biến nó thành gạch đầu dòng
rỗng — mỗi mục cần văn xuôi giải thích thật sự.

```
# Giải phẫu: <Tên bài> — <tác giả, năm> 〔venue nếu có〕

## 0. Thẻ định danh & bản đồ
Thể loại; bài toán/lĩnh vực; bản đồ mục → trang (để bạn tra cứu). Một câu định vị bài.

## 1. Cốt lõi (core)
Đóng góp trung tâm là gì, phát biểu rõ ràng, đúng như tác giả tuyên bố. 【neo】

## 2. Tinh hoa (the key insight)
MỘT (hoặc vài) ý then chốt khiến cách làm này hoạt động — cái "aha". Giải thích vì sao chính ý này
là bản lề, và điều gì sẽ sụp nếu thiếu nó. 【neo】

## 3. Triết lý & giả định nền
Bài khung hóa vấn đề thế nào, ngầm coi gì là hiển nhiên, lấy gì làm tiêu chí "tốt" (nhanh? tổng quát?
khả diễn giải? tối ưu?), thuộc/chống lại truyền thống nào, và đặt "ván cược" gì. Tách bạch [diễn giải]
với [suy luận]. 【neo cho phần có căn cứ văn bản】

## 4. Kiến trúc
Các thành phần và cách chúng ghép lại (mô tả để người đọc vẽ được sơ đồ/biểu đồ phụ thuộc trong đầu).
Tùy thể loại: khối mô hình & luồng dữ liệu / chuỗi định nghĩa→bổ đề→định lý / thiết kế nghiên cứu /
mạch lập luận. 【neo, dẫn Hình/Bảng/Eq】

## 5. Phương pháp đề xuất (chi tiết tới cơ chế)
Tái dựng phương pháp **từng bước**: đầu vào → các bước → đầu ra; công thức/thuật toán/quy trình chính
diễn giải dễ hiểu; vì sao mỗi lựa chọn thiết kế được chọn. Đủ để người đọc hình dung cách tái lập. 【neo】

## 6. Bằng chứng & giới hạn (nếu có)
Bài chứng minh tuyên bố bằng gì (thí nghiệm/chứng minh/lập luận), kết quả chính, và ranh giới hiệu lực
+ hạn chế tác giả thừa nhận. 【neo】

## 7. Bản đồ trích dẫn
Bảng tra nhanh: nhận định/khái niệm quan trọng ↔ vị trí gốc, để bạn tự kiểm.
```

## Tự kiểm trước khi gửi
- Mọi khẳng định về nội dung bài đã có thẻ neo chưa? Có thẻ nào trỏ tới trang/mục tôi **chưa thực sự
  đọc** trong văn bản trích không? (nếu có → bỏ hoặc sửa)
- Đã tách rõ [diễn giải] và [suy luận] chưa?
- Có vô tình tụt xuống thành tóm tắt nông không? Mục Tinh hoa & Phương pháp đã đủ sâu chưa?
- Trích nguyên văn có chỗ nào ≥ 15 từ không? (rút ngắn / chuyển thành diễn giải)
- Thuật ngữ gốc đã giữ và chú giải song ngữ chưa?
