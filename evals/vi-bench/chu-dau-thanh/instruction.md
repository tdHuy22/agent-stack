Tòa soạn nhận bài từ nhiều cộng tác viên, người viết "hoà", người viết "hòa", và báo in ra lẫn lộn hai kiểu. Chủ bút chốt dùng kiểu mới (hòa, khỏe, thủy). Viết hàm `chuan_hoa_dau(van_ban)` trong `/app/dau_thanh.py` (file đang có bản làm tạm bằng bảng thay thế, thiếu rất nhiều chữ): nhận một đoạn văn bản bất kỳ, trả về văn bản đã đổi dấu thanh kiểu cũ sang kiểu mới. Giữ nguyên tên hàm và tên file.

Hai kiểu chỉ khác nhau ở chỗ đặt dấu thanh (huyền, sắc, hỏi, ngã, nặng) của vần `oa`, `oe`, `uy`: kiểu cũ đặt lên chữ cái thứ hai (hoà, khoẻ, thuỷ), kiểu mới đặt lên chữ cái thứ nhất (hòa, khỏe, thủy).

Luật:

1. "Chữ" là một dãy chữ cái liên tiếp. Chữ số, dấu cách, gạch nối, gạch dưới, dấu câu, xuống dòng đều ngăn cách các chữ. Xét từng chữ.
2. Chỉ đổi khi vần của chữ đúng là `oa`, `oe` hoặc `uy`, nghĩa là chữ kết thúc ngay sau hai chữ cái đó (không có phụ âm cuối, không có nguyên âm nào theo sau) và dấu thanh đang nằm trên chữ cái thứ hai. Đổi bằng cách chuyển dấu thanh sang chữ cái thứ nhất; các chữ cái còn lại và dấu mũ, móc, trăng không đổi. Chữ không có dấu thanh, hoặc đã ở kiểu mới, giữ nguyên.
3. Mọi trường hợp khác giữ nguyên, ví dụ chữ có phụ âm cuối (toán, hoàn, huỳnh) và chữ có thêm nguyên âm (ngoài, xoáy, khoèo).
4. Ngoại lệ `qu`: chữ cái u đứng ngay sau q là một phần của phụ âm đầu "qu", không phải nguyên âm của vần. Vì vậy "quý", "quỷ", "quỳ", "quỹ", "quỵ" có vần chỉ là `y` và giữ nguyên.
5. Giữ nguyên hoa thường của từng chữ cái ("HOÀ" thành "HÒA", "Thuỷ" thành "Thủy"). Văn bản vào có thể gõ dấu kiểu dựng sẵn hoặc kiểu tách rời (chữ cái và dấu là hai ký tự riêng). Kết quả luôn ở dạng dựng sẵn (NFC). Mọi thứ khác trong văn bản (tiếng Anh, số, dấu câu, xuống dòng) giữ nguyên.

Ví dụ:
- `chuan_hoa_dau("Chúc bạn khoẻ, hoà thuận")` -> `"Chúc bạn khỏe, hòa thuận"`
- `chuan_hoa_dau("Quý khách xem thuỷ điện Hoà Bình")` -> `"Quý khách xem thủy điện Hòa Bình"`
- `chuan_hoa_dau("toán hoàn ngoài")` -> `"toán hoàn ngoài"`
