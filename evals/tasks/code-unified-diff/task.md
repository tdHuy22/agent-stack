Viết hàm `unified_diff(a, b, a_name="a", b_name="b", context=3)` trong `udiff.py`. `a`, `b` là toàn văn hai file
(chuỗi). Hàm trả về chuỗi unified diff đúng định dạng của `diff -u` (GNU/BSD), hoặc chuỗi rỗng nếu hai file giống hệt.

- Dòng đầu `--- <a_name>`, dòng hai `+++ <b_name>`, rồi các hunk. Mọi dòng của kết quả kết thúc bằng `\n`.
- Bộ dòng thêm và bớt phải **tối thiểu**: tổng số dòng `-` và `+` bằng len(a) + len(b) − 2 × (độ dài dãy con chung
  dài nhất, tính theo dòng).
- Mỗi nhóm thay đổi có tối đa `context` dòng ngữ cảnh trước và sau. Hai nhóm cách nhau không quá 2 × `context` dòng
  không đổi thì gộp vào cùng một hunk. Trong mỗi nhóm thay đổi, mọi dòng `-` đứng trước mọi dòng `+`.
- Tiêu đề hunk `@@ -l,s +l,s @@`: bỏ `,s` khi s = 1; khi s = 0 thì l là số dòng ngay trước chỗ thay đổi
  (ví dụ `@@ -0,0 +1,3 @@` khi a rỗng, `@@ -5,0 +6,2 @@` khi chèn 2 dòng sau dòng 5 với `context=0`).
- Dòng cuối của một file không có ký tự xuống dòng ở cuối được coi là khác với cùng nội dung có xuống dòng; khi
  dòng đó xuất hiện trong diff thì ngay sau nó là dòng `\ No newline at end of file`.
- Không dùng `difflib` hay gọi chương trình ngoài. Hai file 5.000 dòng khác nhau khoảng 100 chỗ phải xong dưới 2 giây.
