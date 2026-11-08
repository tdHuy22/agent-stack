Nhóm mình hay đi ăn chung, một hai người trả trước rồi chia lại. Hàm chia tiền đang ra số lẻ, ghép người nợ với người nhận lung tung, và cứ gõ tên có dấu là nó coi thành hai người khác nhau. Bạn sửa `chia_tien(khoan_tra, thanh_vien)` trong `/app/nhom/chia_tien.py` cho đúng luật dưới. Giữ nguyên tên hàm và tên tham số. Hàm trả danh sách các khoản chuyển, mỗi khoản là bộ `(người_chuyển, người_nhận, số_tiền)` với số tiền là số nguyên đồng.

Đầu vào:

- `thanh_vien`: danh sách tên (chuỗi) mọi người cùng chia đều bữa ăn, gồm cả những người đã trả. Phải có ít nhất một người, nếu không thì báo `ValueError`.
- `khoan_tra`: danh sách `(tên, số tiền)` các khoản đã trả. Một người có thể xuất hiện nhiều lần (khi đó cộng dồn lại). Số tiền là số nguyên không âm; âm thì báo `ValueError`. Tên không thuộc `thanh_vien` cũng báo `ValueError`.

Tên người gõ tay nên cùng một người có thể viết khác nhau. Hai tên là cùng một người khi giống nhau sau các bước: đổi sang NFC; bỏ khoảng trắng ở đầu và cuối, gộp các khoảng trắng liền nhau ở giữa thành một; không phân biệt chữ hoa thường; và coi hai kiểu đặt dấu thanh trên các vần `oa`, `oe`, `uy` là một (Hòa và Hoà, Thủy và Thuỷ là cùng tên). Dấu khác thì vẫn là người khác: Lan khác Lân, Hoa khác Hòa. Trong kết quả, mỗi người ghi bằng cách viết của lần xuất hiện đầu tiên trong `thanh_vien` (sau khi đổi NFC, bỏ khoảng trắng thừa như trên, giữ nguyên chữ hoa thường và cách đặt dấu người ta gõ ở đó). Các tên trùng nhau trong `thanh_vien` chỉ tính một người.

Luật chia:

1. `tong` là tổng mọi khoản đã trả; `n` là số người (sau khi gộp tên trùng).
2. Phần mỗi người phải chịu là `tong / n` làm tròn nửa lên tới nghìn đồng gần nhất (bội của 1000; đúng giữa hai bội thì lên). Dùng số nguyên cho chắc, đừng để sai số của số thực làm lệch.
3. Người đã trả nhiều nhất (tổng các khoản của người đó lớn nhất; bằng nhau thì người đứng trước trong `thanh_vien`) gánh phần lẻ: phần của riêng người đó là `tong - (n - 1) × phần`, còn mọi người khác chịu đúng `phần`. Nhờ vậy tổng phần của cả nhóm luôn đúng bằng `tong`, và phần của người này có thể không là bội của 1000.
4. Số dư của mỗi người = số đã trả trừ phần phải chịu. Số dư âm là người phải chuyển, số dư dương là người được nhận.
5. Ghép chuyển khoản theo đúng cách này, lặp đến khi hết: lấy người còn nợ nhiều nhất (hòa thì người đứng trước trong `thanh_vien`) và người còn được nhận nhiều nhất (hòa thì cũng người đứng trước), cho người nợ chuyển cho người nhận số tiền nhỏ hơn trong hai số đó, trừ vào cả hai; ai về 0 thì không xét nữa. Mỗi lần ghép ra một khoản trong danh sách kết quả, theo thứ tự ghép.

Không ai phải chuyển (tổng bằng 0 hay chỉ có một người) thì trả `[]`.

Trong `/app/nhom/test_chia_tien.py` có vài test, chạy bằng `python3 -m unittest` trong `/app/nhom`.
