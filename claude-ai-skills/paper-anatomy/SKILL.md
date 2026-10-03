---
name: paper-anatomy
description: >-
  Đọc sâu và "giải phẫu" một bài báo khoa học (PDF, link arXiv, cả bản scan) ở mọi lĩnh vực: KHÔNG tóm tắt,
  mà làm lộ cốt lõi, ý tưởng then chốt, giả định nền, kiến trúc, phương pháp tới mức cơ chế, và bằng chứng
  thật sự chống đỡ từng tuyên bố. Mọi nhận định neo về đúng mục/trang/hình/công thức gốc và được kiểm tự
  động bằng script. Dùng khi người dùng đưa một paper và muốn "hiểu cốt lõi", "hiểu sâu", "đọc kỹ", "phân
  tích", "giải phẫu/mổ xẻ", "không cần tóm tắt", hỏi "bài này thật sự đề xuất gì", "vì sao nó hoạt động",
  "kiến trúc/phương pháp ra sao", "claim có đứng vững không", "bằng chứng có đủ không", "điểm yếu ở đâu",
  hoặc hỏi một câu hẹp về một bài cụ thể (một định lý, một bảng, một bước). Kích hoạt cả khi họ không nhắc
  chữ "skill": chỉ cần đưa paper và muốn hiểu thấu đáo thay vì một bản tóm tắt ngắn.
---

# Paper Anatomy: giải phẫu bài báo khoa học

## Tinh thần

Tóm tắt làm bài báo *ngắn lại* và vì thế mất chi tiết. Ở đây làm ngược lại: **làm bài báo dễ hiểu hơn mà
không làm nó nông đi**. Tóm tắt cho biết bài *nói gì*; giải phẫu cho biết bài *vì sao hoạt động*, *ý then chốt
là gì*, *các mảnh ghép vào nhau ra sao*, *thế giới quan ngầm nào* chống đỡ nó, và *bằng chứng thật sự chứng
minh được tới đâu*.

Ba cam kết:
1. **Trung thực với văn bản gốc.** Không bịa, không phóng đại. Cái gì bài không nói rõ thì gọi đúng tên là
   suy luận của người phân tích, hoặc nói thẳng "bài không nói".
2. **Sâu, không nén.** Viết văn xuôi giải thích, dựng lại cơ chế tới mức người đọc "thấy bánh răng quay", đủ
   để hình dung cách tái lập. Gạch đầu dòng rỗng là dấu hiệu đang tóm tắt.
3. **Kiểm được, không chỉ neo được.** Neo sai trang còn tệ hơn không neo, vì nó mượn uy tín của bài gốc cho
   một điều bài không nói. Vì vậy neo được viết sao cho script kiểm được, và được kiểm trước khi gửi.

## Chọn chế độ

| Người dùng muốn | Chế độ | Đầu ra |
|---|---|---|
| Hỏi một điểm cụ thể ("Định lý 2 nói gì", "vì sao Bảng 3 tốt hơn", "bước 2 của phương pháp làm gì") | **Hỏi hẹp** | Trả lời tập trung (thường 300–1.200 từ), vẫn neo và kiểm neo; cuối bài đề nghị giải phẫu đầy đủ nếu họ muốn |
| Hiểu sâu cả bài | **Giải phẫu** (mặc định) | Mẫu đầy đủ, mục 0–8 |
| Hỏi tuyên bố có đứng vững không, bằng chứng đủ không, điểm yếu | **Phản biện** | Mẫu đầy đủ, mục 6–7 mở rộng theo `references/critical-appraisal.md` |

Hỏi hẹp không có nghĩa là đọc hẹp: vẫn đọc phần tóm tắt, mở đầu, phương pháp và toàn bộ phần liên quan, vì
một định lý hay một bảng chỉ hiểu đúng khi biết giả thiết và cách đo của nó.

## Ngôn ngữ

Viết tiếng Việt, **giữ thuật ngữ gốc** ở lần nhắc đầu kèm chú giải tiếng Việt trong ngoặc, ví dụ "cơ chế chú
ý (attention)". Giữ nguyên ký hiệu toán, tên biến, tên mô hình, tên định lý. Không dịch ép thuật ngữ đã thành
chuẩn quốc tế. Người dùng viết bằng ngôn ngữ khác thì theo ngôn ngữ của họ.

## Thẻ neo

Sau mỗi nhận định về nội dung bài, gắn một thẻ:

> 【§<mục> · tr.<trang> · <đối tượng> · "<dấu vết>"】

- `§<mục>`: số mục như trong bài (`§3.2`, `§II-B`, `§A.1`); mục không đánh số thì dùng tên (`§Abstract`,
  `§Phụ lục B`).
- `tr.<trang>`: nhãn trang theo bản đồ của script. Script tự chọn nhãn: nhãn khai báo trong PDF (ví dụ số trang
  kỷ yếu 36005), số in trên trang, hoặc số trang PDF khi không dò được. Ghi một lần ở đầu bản phân tích là
  đang dùng loại nào. Muốn chỉ rõ trang PDF thì viết `tr.PDF7`. Neo vào **trang nơi điều đó được nói**, không
  phải trang đầu của mục.
- `<đối tượng>` khi liên quan: `Hình 2`, `Bảng 1`, `Eq.(4)`, `Thuật toán 1`, `Định lý 3`, `Bổ đề 2`.
- `"<dấu vết>"`: 4–10 từ **chép nguyên văn** (giữ ngôn ngữ gốc) từ đúng trang đó, đủ để người đọc Ctrl+F và để
  script so khớp. Dùng cho ý trung tâm: tuyên bố đóng góp, tinh hoa, bước then chốt của phương pháp, con số,
  dòng của bảng tuyên bố–bằng chứng. Chép từ `paper.txt` hoặc từ kết quả `--find`, không chép theo trí nhớ:
  script so từng chữ (chỉ bỏ qua hoa thường, dấu câu, xuống dòng).

**Mật độ neo.** Neo phục vụ người đọc, không được lấn át bài viết. Đặt thẻ ở cuối câu hoặc cuối đoạn, không chen
giữa câu. Một đoạn thường chỉ cần một thẻ có dấu vết cho ý trung tâm của nó; các ý phụ trong cùng đoạn dùng thẻ
ngắn (`【§4.3 · tr.7】`) hoặc gộp chung. Bài mà câu nào cũng kèm một đoạn trích tiếng Anh thì khó đọc.

**Bản scan.** Vẫn dùng đúng dạng thẻ 【…】, chỉ bỏ dấu vết (script không kiểm được chữ trên ảnh). Ghi một lần ở đầu
bài số trang theo loại nào (số in đọc được trên ảnh, kèm độ lệch so với trang PDF, hoặc `tr.PDF<i>`).

Ví dụ: 【§3.1 · tr.5 · Eq.(4) · "we normalize the scores by the key dimension"】, 【§Results · tr.8 · Bảng 2】.

Nhãn phân loại (ghi khi không hiển nhiên):
- *[diễn giải]*: nói lại ý tác giả bằng lời mình. Đây là mặc định, không cần ghi.
- *[suy luận]*: điều người phân tích rút ra, bài không phát biểu thẳng. Luôn ghi.
- *[minh họa]*: ví dụ, sơ đồ hay phép tính tay do người phân tích dựng để giải thích. Luôn ghi.
- *[ngoài bài]*: kiến thức lấy từ ngoài bài (công trình sau, bối cảnh ngành). Dùng ít, tách hẳn khỏi phần nói
  về bài, không bao giờ gán cho tác giả.

Trích nguyên văn ngoài thẻ neo thì ngắn (dưới 15 từ), trong ngoặc kép. Ưu tiên diễn giải.

## Viết cho dễ đọc

Người dùng đọc để hiểu, không phải để duyệt danh sách trích dẫn. Mỗi đoạn mở bằng ý chính rồi mới giải thích.
Đoạn ngắn, mỗi đoạn một ý. In đậm ít, chỉ cho khái niệm then chốt. Dùng bảng khi so sánh nhiều thứ theo cùng
tiêu chí, sơ đồ chữ khi mô tả luồng. Thuật ngữ gốc kèm chú giải ở lần đầu, sau đó dùng một cách gọi nhất quán.

## Quy trình

### Bước 0: lấy văn bản theo trang

1. Tìm PDF. Trên claude.ai: `/mnt/user-data/uploads/`. Trong Claude Code: đường dẫn người dùng đưa, hoặc thư
   mục hiện tại. Người dùng đưa link arXiv: tải PDF về (môi trường nào cần hỏi trước thì hỏi). Bài nặng công
   thức trên arXiv có thể lấy thêm mã TeX để đối chiếu công thức, xem `references/hard-pdfs.md`.
2. Chạy script nằm cạnh file SKILL.md này, ghi vào một thư mục làm việc tạm (không bày ra thư mục dự án của
   người dùng):

   ```bash
   python3 <thư-mục-skill>/scripts/extract_paper.py "<file.pdf>" --out <thư-mục-làm-việc>
   ```

   Script in báo cáo (thư viện dùng được, PDF có phải scan không, trang hai cột), **bản đồ mục → trang**, chỉ
   mục Hình/Bảng/Thuật toán/Định lý/công thức đánh số, và ghi `paper.txt` (toàn văn có mốc
   `===== PAGE i/N · tr.<nhãn> =====`), `pages.json` (cho bước kiểm neo), `outline.txt` (bản đồ).
3. **Đọc toàn văn theo đợt**: `--pages 1-6`, rồi `--pages 7-12`… (hoặc đọc `paper.txt` theo khúc) cho tới hết
   phần thân bài. Đừng in cả bài một lần: đầu ra quá dài bị cắt mà không báo, và trang bị cắt coi như chưa đọc.
   Dù phải đọc chọn lọc (bài rất dài, bản scan, câu hỏi hẹp), luôn đọc tóm tắt, mở đầu, và các mục kết luận,
   thảo luận, giới hạn, khuyến nghị: tác giả thường nói rõ nhất ở đó điều họ thật sự tin và điều họ không bảo đảm.
4. Bài dài (khoảng trên 40 trang): đọc hết thân bài tới phần tài liệu tham khảo. Phụ lục: xem bản đồ, đọc kỹ
   phần nào chứa chứng minh, thiết lập thí nghiệm hay số liệu mà bản phân tích dựa vào; phần còn lại lướt theo
   tiêu đề. Ghi rõ trong mục 0 phần nào đã đọc kỹ, phần nào chỉ lướt.
5. **Hình và công thức**: văn bản trích ra làm hỏng ký hiệu toán và không chứa nội dung sơ đồ. Trước khi mô
   tả hình kiến trúc hay giải thích một công thức trung tâm, xuất trang đó ra ảnh rồi nhìn:
   `--render 4 --out <thư-mục-làm-việc>` rồi mở file PNG. Chỉ đọc chú thích mà chưa xem hình thì nói rõ.
6. Script báo **PDF scan**, thiếu thư viện, hay văn bản lộn xộn: làm theo `references/hard-pdfs.md`. Tóm tắt:
   scan thì xuất ảnh trang và đọc bằng mắt, bắt đầu từ trang bìa và mục lục rồi tới trang cần; thiếu thư viện
   trên máy người dùng thì không tự cài toàn cục, dùng công cụ đọc PDF sẵn có và nói rõ không kiểm neo tự động.

Dùng `--find "cụm từ"` bất cứ lúc nào cần biết một ý nằm ở trang nào. Đó là cách nhanh nhất để neo đúng.

### Bước 1: nhận diện thể loại

"Kiến trúc" và "phương pháp" nghĩa khác nhau giữa bài lý thuyết, thực nghiệm, hệ thống, phương pháp mới, khảo
sát, quan điểm, dữ liệu, tấn công/phòng thủ. Đọc `references/paper-genres.md` để chỉnh trục phân tích và biết
loại bằng chứng nào cần soi. Ghi thể loại và **đóng góp chính theo lời tác giả** (có neo).

### Bước 2: dựng bản đồ trước khi viết

Tự trả lời được những câu sau (có neo) rồi mới viết:
- Bài coi *vấn đề thật sự* là gì, và khung hóa nó ra sao?
- Đóng góp trung tâm là gì? Liệt kê các **tuyên bố** của tác giả ở tóm tắt, mở đầu và kết luận: lát nữa từng
  tuyên bố phải được nối với bằng chứng.
- Nếu chỉ được nói **một ý** khiến cách làm này chạy được, đó là ý nào? Bỏ nó đi thì cái gì sụp? (tinh hoa)
- **Cái mới thật sự** so với công trình trước là gì: mượn gì, thêm gì, khác ở đâu? (xem phần related work)
- "Ván cược" ngầm: giả định không hiển nhiên mà nếu đúng thì cách làm này mới đáng giá?
- Phương pháp vận hành từng bước ra sao? Bỏ bước nào thì hỏng?
- Bằng chứng nào chống đỡ từng tuyên bố, và ranh giới hiệu lực ở đâu?

Một câu trả lời chỉ nhắc lại *cái gì* ("bài dùng kết nối tắt") chưa phải tinh hoa. Tinh hoa giải thích *vì sao*
ở mức cơ chế. Ví dụ với ResNet: mạng sâu hơn có lỗi *huấn luyện* cao hơn, nên vấn đề không phải quá khớp mà là
khó tối ưu; kết nối tắt đổi việc học ánh xạ H(x) thành học phần dư F(x) = H(x) − x, nên một lớp "thừa" chỉ cần
đẩy F về 0 thay vì học đúng ánh xạ đồng nhất. Câu như vậy cho biết điều gì sẽ sụp nếu bỏ ý đó đi.

### Bước 3: viết

Chế độ giải phẫu và phản biện dùng mẫu bên dưới. Chế độ hỏi hẹp trả lời thẳng câu hỏi, cùng chuẩn neo.

### Bước 4: kiểm neo (bắt buộc khi có `pages.json`)

Lưu bản nháp vào `<thư-mục-làm-việc>/analysis.md`, rồi chạy:

```bash
python3 <thư-mục-skill>/scripts/verify_anchors.py <thư-mục-làm-việc>/analysis.md --pages <thư-mục-làm-việc>/pages.json
```

Script báo từng thẻ sai: trang không có, mục không chứa trang đó, Hình/Bảng/Eq không có trên trang, dấu vết
không nằm trên trang (kèm trang đúng nếu tìm thấy, hoặc báo không có ở đâu trong bài, tức là chép sai hay
đang diễn giải). Nó cũng báo trích dài quá 15 từ, và (chỉ để tham khảo) đoạn văn dài không có neo.

Sửa **mọi** dòng FAIL: tra lại bằng `--find`, sửa trang hay dấu vết, hoặc bỏ nhận định nếu bài không nói vậy.
Xem từng WARN. Chạy lại tới khi không còn FAIL.

Script chỉ kiểm **vị trí**, không kiểm điều bạn diễn giải có đúng không. Neo đúng trang vẫn có thể đi kèm một
câu sai. Vì vậy, sau khi script sạch, tự rà nội dung theo ba loại câu hay sai nhất:
1. **Con số và khoảng số**: đối chiếu lại từng con số với bảng hay đoạn gốc. Khoảng "từ x đến y" phải tính từ
   đúng các ô của bảng, kèm thiết lập (mô hình, tập dữ liệu, chế độ) mà nó áp dụng.
2. **Câu phủ định về bài** ("bài không nói…", "thiếu…", "không báo…", "mâu thuẫn…"): tìm lại bằng `--find` vài
   từ khóa trong cả bài, kể cả phụ lục và chú thích bảng. Bài có nói thì sửa hoặc bỏ câu đó.
3. **Chi tiết thí nghiệm** (số lần chạy, seed, ngân sách, phần cứng): chỉ ghi khi bài nêu; bài không nêu thì nói
   "bài không nêu", đừng đoán. Ghi kết quả lần chạy cuối thành **một dòng ngắn** ở đầu bản phân
tích (ví dụ "Kiểm neo tự động: 41 neo, 0 sai"). Không giải thích cảnh báo hay quy trình kiểm trong bài gửi
người dùng: đó là việc của bước này, không phải nội dung người dùng cần đọc.

### Bước 5: trình bày

- Phân tích ngắn đến vừa: để trong khung chat.
- Giải phẫu đầy đủ hoặc bài dài: đề nghị xuất file `.md` (mặc định) hoặc `.docx` (dùng skill `docx`). Trên
  claude.ai lưu vào `/mnt/user-data/outputs/` và gọi `present_files`; trong Claude Code ghi vào nơi người dùng
  muốn, không thì để trong chat.

## Mẫu giải phẫu

Đổi tiêu đề cho hợp thể loại, bỏ mục không liên quan. Mỗi mục là văn xuôi giải thích thật sự.

```
# Giải phẫu: <Tên bài> (<tác giả>, <năm>) 〔venue nếu có〕
> Đã đọc: <trang đọc kỹ; phần chỉ lướt>. Số trang theo: <nhãn in / trang PDF>. Kiểm neo tự động: <N> neo, <N> sai.

## 0. Thẻ định danh & bản đồ
Thể loại; bài toán và lĩnh vực; một câu định vị bài; bản đồ mục → trang rút gọn.

## 1. Cốt lõi
Vấn đề thật sự và đóng góp trung tâm, đúng như tác giả tuyên bố.

## 2. Tinh hoa
Ý then chốt ở mức cơ chế, vì sao nó là bản lề, bỏ đi thì cái gì sụp (dựa vào ablation nếu có).
Cái mới thật sự so với công trình trước: mượn gì, thêm gì.

## 3. Triết lý & giả định nền
Cách khung hóa vấn đề, tiêu chí "tốt" (nhanh, tổng quát, an toàn, khả diễn giải…), truyền thống mà bài
theo hay chống lại. Giả định: tách giả định tác giả nêu (có neo) với giả định ngầm [suy luận]. Ván cược.

## 4. Kiến trúc
Các thành phần và cách ghép, luồng dữ liệu hoặc chuỗi phụ thuộc logic, để người đọc vẽ được sơ đồ. Có thể kèm
sơ đồ chữ [minh họa], dựng từ hình đã xem. Tùy thể loại: khối mô hình / định nghĩa → bổ đề → định lý /
thiết kế nghiên cứu / mạch lập luận / mô hình mối đe dọa.

## 5. Phương pháp chi tiết
Tái dựng từng bước: đầu vào → các bước → đầu ra. Công thức chính giải nghĩa từng ký hiệu. Vì sao mỗi lựa chọn
thiết kế được chọn. Một ví dụ chạy tay [minh họa] trên đầu vào nhỏ khi phương pháp có tính toán. Bảng ký hiệu
nếu bài nặng toán.

## 6. Bằng chứng: tuyên bố ↔ bằng chứng
| Tuyên bố của tác giả | Bằng chứng (ở đâu) | Mức chống đỡ | Lưu ý |
Mức: mạnh / vừa / yếu / chưa có. Con số chép đúng từ bảng, kèm thiết lập và thước đo của nó.

## 7. Giới hạn & câu hỏi mở
Giới hạn tác giả thừa nhận (neo). Giới hạn người phân tích thấy [suy luận], mỗi cái theo: cái gì, ở đâu,
vì sao quan trọng. Khả năng tái lập: mã, dữ liệu, siêu tham số, số lần chạy. Câu hỏi muốn hỏi tác giả.

## 8. Bản đồ trích dẫn
| Khái niệm / nhận định | Vị trí | Dấu vết |
```

## Tự kiểm trước khi gửi

- Lần chạy `verify_anchors.py` cuối cùng có 0 FAIL, và dòng kết quả đã ghi ở đầu? (Không có `pages.json` thì
  ghi rõ "không kiểm neo tự động" và lý do.)
- Tuyên bố đóng góp, tinh hoa, các bước then chốt và mọi con số đều có neo kèm dấu vết? Và ngược lại, có đoạn
  nào bị neo dày tới mức khó đọc?
- Đã đọc kết luận, thảo luận, giới hạn và khuyến nghị của tác giả chưa?
- Có trang nào tôi trích mà thực ra chưa đọc? Phần chỉ lướt đã ghi ở mục 0 chưa?
- Hình nào tôi mô tả mà chưa xem ảnh? Công thức nào tôi giải thích từ văn bản trích bị vỡ ký hiệu?
- Con số và khoảng số có đúng thước đo, đúng thiết lập, đúng đơn vị như trong bảng (đã đối chiếu lại, không
  chép theo trí nhớ)?
- [suy luận], [minh họa], [ngoài bài] đã tách khỏi điều bài nói?
- Mỗi chỗ tôi nói bài "không nói", "thiếu" hay "mâu thuẫn": đã tìm trong cả bài, kể cả phụ lục, chưa?
- Tinh hoa và phương pháp đã ở mức *vì sao* và *cơ chế*, đủ để hình dung cách tái lập, hay mới ở mức *cái gì*?
- Thuật ngữ gốc đã giữ và chú giải song ngữ?
