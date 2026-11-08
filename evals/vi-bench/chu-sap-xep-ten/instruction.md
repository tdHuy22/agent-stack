Danh sách lớp in ra đang sai thứ tự, phụ huynh hỏi suốt. Sửa hàm `sap_xep(ds)` trong `/app/danh_sach.py`: nhận một list họ tên, trả list mới đã xếp theo thứ tự từ điển tiếng Việt như sổ điểm ở trường.

Luật xếp:

1. Xếp theo tên (chữ cuối cùng của họ tên) trước. Trùng tên thì xét tiếp họ và đệm, từ trái sang phải, chữ nào cũng so bằng luật số 2.
2. So hai chữ: trước hết so lần lượt từng chữ cái theo bảng chữ cái tiếng Việt
   `a ă â b c d đ e ê g h i k l m n o ô ơ p q r s t u ư v x y`.
   Nếu một chữ là phần đầu của chữ kia (như "Anh" và "Anhh") thì chữ ngắn đứng trước. Nếu chữ cái giống hệt nhau thì so dấu thanh theo thứ tự: không dấu, huyền, sắc, hỏi, ngã, nặng.
3. Không phân biệt hoa thường. Hai họ tên giống hệt nhau theo luật trên thì giữ thứ tự như trong list đầu vào.

Dữ liệu lấy từ nhiều nguồn: có tên gõ dấu kiểu tách rời (chữ cái và dấu là hai ký tự riêng), có khoảng trắng thừa. Trả về đúng các chuỗi gốc như đầu vào, không sửa chuỗi nào. Họ tên chỉ gồm chữ tiếng Việt và khoảng trắng.
