Bộ gõ trên máy của phòng hành chính bị lỗi một thời gian, nên nhiều văn bản còn sót chữ gõ Telex thô ("Tooi ddang hocj tieengs Vieetj" lẽ ra là "Tôi đang học tiếng Việt"). Viết hàm `sua_telex(van_ban)` trong `/app/telex.py` (đang có bản làm tạm, mới đổi được vài cặp phím): nhận một đoạn văn bản, trả về văn bản đã đổi chữ Telex thô thành chữ tiếng Việt. Giữ nguyên tên hàm và tên file.

Luật:

1. Trước khi xử lý, đổi văn bản về dạng dựng sẵn (NFC); kết quả cũng ở dạng NFC. "Chữ" là một dãy chữ cái liên tiếp; chữ số, dấu cách, dấu câu (kể cả dấu nháy và gạch nối), xuống dòng ngăn cách các chữ, và mọi thứ ngoài chữ giữ nguyên. Chỉ xét chữ gồm toàn chữ cái ASCII (a-z, A-Z); chữ nào có ký tự khác (đã có dấu, như "Việtj", hay chữ ngoài tiếng Việt) giữ nguyên hoàn toàn.
2. Danh sách từ giữ nguyên nằm trong file `tu_giu.txt` cạnh `telex.py`: mỗi dòng một từ (tiếng Anh, tên riêng…), so không phân biệt hoa thường, dòng trống bỏ qua. Chữ có trong danh sách giữ nguyên. Đọc danh sách từ file, không ghi sẵn vào code (người ta sẽ sửa file).
3. Chữ ASCII còn lại đổi theo luật Telex, theo thứ tự sau.
   a. Phím dấu thanh: nếu chữ cái cuối của chữ là `s` (sắc), `f` (huyền), `r` (hỏi), `x` (ngã) hoặc `j` (nặng), và phần còn lại có ít nhất một chữ `a e i o u y`, thì bỏ chữ cái cuối đó và đặt dấu thanh tương ứng lên một nguyên âm (luật đặt ở mục d). Nếu phần còn lại không có nguyên âm nào thì chữ cái cuối chỉ là một chữ cái bình thường, không đổi gì ("ms", "xs", "s").
   b. Phím dấu mũ, móc, trăng, gạch ngang, quét phần còn lại từ trái sang phải, mỗi lần đổi một cặp hai chữ cái liền nhau (cặp không chồng lên nhau): `aa` thành `â`, `aw` thành `ă`, `ee` thành `ê`, `oo` thành `ô`, `ow` thành `ơ`, `uw` thành `ư`, `dd` thành `đ`. Vì vậy "ươ" gõ là `uwow`. Không có cách gõ tắt nào khác, và chữ `w` không thuộc cặp nào thì giữ nguyên.
   c. Hoa thường: chữ gốc là một trong ba kiểu, toàn thường, TOÀN HOA, hoặc chỉ chữ cái đầu hoa (Vieetj); kết quả giữ đúng kiểu đó ("VIEETJ" thành "VIỆT", "Vieetj" thành "Việt", "Ddaats" thành "Đất").
   d. Đặt dấu thanh (kiểu mới). Nguyên âm tiếng Việt là `a ă â e ê i o ô ơ u ư y`. Chữ cái `u` sau `q` không tính là nguyên âm (qu là phụ âm đầu), chữ cái `i` sau `g` cũng không tính khi ngay sau nó còn một nguyên âm khác (gi là phụ âm đầu: "giá", nhưng "gì" thì i là nguyên âm). Cụm nguyên âm là dãy nguyên âm liền nhau đầu tiên của chữ sau khi bỏ phụ âm đầu. Dấu thanh đặt lên:
      - nguyên âm mang dấu mũ, móc, trăng (`ă â ê ô ơ ư`) cuối cùng của cụm, nếu cụm có chữ như vậy (tiếng, được, người, muốn, yếu, khuyến);
      - ngược lại, nếu cụm chỉ có một nguyên âm thì lên nó;
      - ngược lại, nếu cụm có hai nguyên âm: lên nguyên âm thứ hai nếu sau cụm còn chữ cái (phụ âm cuối: toàn, hoạt), lên nguyên âm thứ nhất nếu cụm nằm ở cuối chữ (hòa, mùa, của, bài, thủy);
      - ngược lại (ba nguyên âm không có dấu mũ, móc, trăng): lên nguyên âm giữa (ngoài, xoáy).

Ví dụ (danh sách từ giữ nguyên có `Windows`):
- `sua_telex("Tooi ddang hocj tieengs Vieetj")` -> `"Tôi đang học tiếng Việt"`
- `sua_telex("Haf Nooij, nguwowif Windows")` -> `"Hà Nội, người Windows"`
- `sua_telex("quaf giaos ddaats")` -> `"quà giáo đất"`
