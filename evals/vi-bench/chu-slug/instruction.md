Trang tin của công ty đang sinh đường dẫn bài viết từ tiêu đề, và URL ra toàn dấu hỏi với ký tự lạ. Viết lại hàm `tao_slug(tieu_de, toi_da=60)` trong `/app/slug.py`: nhận tiêu đề (chuỗi), trả về slug. Giữ nguyên tên hàm, tên file và tham số.

Luật tạo slug, làm lần lượt:

1. Chuyển sang chữ thường. Tiêu đề có thể gõ dấu kiểu dựng sẵn hoặc kiểu tách rời (chữ cái và dấu là hai ký tự riêng), cả hai phải cho cùng kết quả.
2. Bỏ hết dấu: dấu thanh, dấu mũ, móc, trăng (`ă â ê ô ơ ư` thành `a a e o o u`), và cả dấu của chữ không phải tiếng Việt (như `é` trong "café" thành `e`). Riêng `đ` thành `d`.
3. Dấu nháy đơn, cả thẳng (`'`) lẫn cong (`’` `‘`), bị xóa hẳn, không để lại khoảng trống: "O'Brien" thành "obrien".
4. Mọi dãy ký tự còn lại không phải chữ cái a-z hay chữ số 0-9 (khoảng trắng, dấu câu, gạch dưới, ký hiệu, chữ của hệ chữ khác như chữ Hán, dấu chấm trong số) thu thành đúng một dấu gạch nối `-`. Không để gạch nối ở đầu hay cuối, không để hai gạch nối liền nhau.
5. `toi_da` là số ký tự tối đa của slug. Nếu slug dài hơn, cắt ở ranh giới giữa hai từ (tại dấu gạch nối): giữ nhiều từ nhất có thể sao cho độ dài không vượt `toi_da`, không bao giờ cắt giữa một từ và không để lại gạch nối cuối. Chỉ khi ngay từ đầu tiên đã dài hơn `toi_da` thì mới cắt cứng từ đó ở đúng `toi_da` ký tự.
6. Nếu kết quả rỗng (tiêu đề không còn chữ hay số nào) thì trả về `"bai-viet"`.

Ví dụ:
- `tao_slug("Đường Điện Biên Phủ")` -> `"duong-dien-bien-phu"`
- `tao_slug("Quán cà phê O'Brien – Hà Nội!")` -> `"quan-ca-phe-obrien-ha-noi"`
- `tao_slug("Mùa thu ở Hà Nội", 11)` -> `"mua-thu-o"`
