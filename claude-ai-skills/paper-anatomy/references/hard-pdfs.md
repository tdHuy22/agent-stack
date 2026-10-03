# PDF khó: scan, hai cột, công thức, bài dài, thiếu thư viện

Đọc khi `extract_paper.py` cảnh báo, khi văn bản trích ra đọc thấy lộn xộn, hoặc khi bài nặng hình và công thức.

## Thiếu thư viện đọc PDF

Script thử lần lượt PyMuPDF, pypdf, lệnh `pdftotext`. Không có cái nào thì nó dừng và báo.
- **Sandbox dùng một lần** (như máy ảo của claude.ai): `pip install pymupdf` rồi chạy lại.
- **Máy của người dùng** (như Claude Code): không tự cài toàn cục khi chưa hỏi. Đề nghị cài vào một venv riêng,
  hoặc đọc PDF bằng công cụ đọc file sẵn có (Read của Claude Code đọc PDF theo trang, tối đa khoảng 20 trang mỗi
  lần, thấy cả hình). Khi đó dùng `tr.PDF<i>` cho mọi neo và ghi ở đầu bản phân tích "không kiểm neo tự động".

## PDF scan (báo cáo nói "gần như toàn ảnh")

Văn bản trích ra rỗng hoặc rác. Đừng đoán nội dung.
1. Xuất ảnh vài trang đầu: `--render 1-4 --dpi 80 --out <thư-mục>` rồi mở từng PNG. Trang bìa, mục lục, tóm tắt
   cho biết cấu trúc và trang nào cần đọc kỹ.
2. Đọc tiếp theo đợt 4–6 trang. Với tài liệu dài (báo cáo kỹ thuật cũ thường 50–150 trang), đọc kỹ phần định
   nghĩa, mô hình, và **mọi mục kết luận, khuyến nghị, tóm lược** (mục lục cho biết chúng ở đâu; tác giả thường
   chốt ở đó cái nào họ khuyên dùng và vì sao); các trang còn lại xem nhanh ở dpi thấp để biết có gì, và ghi rõ
   trong mục 0 phần nào đã đọc kỹ.
3. Chỗ chữ mờ hay viết tay: ghi "đọc không chắc" thay vì đoán. Công thức trên bản scan: chép lại theo những gì
   thấy được và nói rõ đó là bản chép.
4. Neo: vẫn dùng thẻ 【§… · tr.…】 như mọi bài. Số trang: số in trên giấy nếu thấy rõ trên ảnh (ghi một lần độ
   lệch so với trang PDF, ví dụ "trang PDF = số in + 7"), không thì `tr.PDF<i>`. Bỏ dấu vết nguyên văn, vì script
   không kiểm được chữ trên ảnh.
5. Nếu môi trường có OCR (`tesseract`, `pytesseract`) thì có thể OCR để tìm kiếm cho nhanh, nhưng vẫn nhìn ảnh
   cho các đoạn trung tâm vì OCR làm sai ký hiệu và số.

## Hai cột và thứ tự chữ

Script giữ thứ tự chữ theo luồng của PDF, thường đúng với bài LaTeX. Dấu hiệu lộn: câu bị cắt ngang rồi nối với
câu của cột kia, chú thích hình chen vào giữa đoạn. Khi đó xuất ảnh trang đó và đọc theo ảnh.

## Công thức và hình

- Văn bản trích làm mất chỉ số trên dưới, ký hiệu Hy Lạp, phân số. Trước khi giải thích một công thức trung tâm,
  xuất trang đó ra ảnh và đọc công thức trên ảnh. Ghi công thức lại bằng LaTeX hoặc Unicode cho rõ.
- Bài trên arXiv: mã nguồn TeX (`https://arxiv.org/e-print/<id>`, file nén) cho công thức chính xác tuyệt đối.
  Chỉ dùng để đối chiếu công thức; neo vẫn theo trang PDF. Tải file cần người dùng đồng ý nếu môi trường yêu cầu.
- Hình kiến trúc: xem ảnh trước khi mô tả. Mô tả theo luồng (đầu vào → khối → đầu ra), gọi đúng tên khối như
  trong hình, neo `Hình N`. Chỉ đọc chú thích thì nói rõ.

## Bài dài (trên khoảng 40 trang) và phụ lục

- Đọc hết thân bài tới tài liệu tham khảo; bản đồ của script cho biết trang bắt đầu tài liệu tham khảo.
- Phụ lục: đọc kỹ phần chứa chứng minh của định lý trung tâm, thiết lập thí nghiệm, bảng số liệu đầy đủ, và
  bất cứ phần nào bản phân tích trích. Phụ lục chỉ chứa prompt, ví dụ đầu ra hay log thì lướt và ghi là đã lướt.
- Đọc theo đợt bằng `--pages`. Ghi chú ngắn sau mỗi đợt (ý chính, trang) để không phải đọc lại.

## Nhãn trang

- Script ưu tiên nhãn khai báo trong PDF (kỷ yếu, tạp chí: số như 36005), sau đó số in trên trang nếu các số
  này lệch đều so với số trang PDF, cuối cùng là số trang PDF. Bản đồ ghi rõ cách nào được dùng.
- Bài trích từ một tập kỷ yếu: số in khác số trang PDF. Người đọc mở file PDF sẽ thấy số in, nên neo theo số in.

## Bài không phải tiếng Anh

Dấu vết chép nguyên văn theo ngôn ngữ của bài. Thuật ngữ: giữ thuật ngữ gốc của bài, chú giải tiếng Việt, và nếu
biết thì thêm thuật ngữ tiếng Anh chuẩn [ngoài bài].
