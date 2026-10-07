Quyết định: tự viết bằng thư viện chuẩn, không thêm phụ thuộc.

- Cách làm: duyệt bằng `os.walk`, gom theo kích thước trước (file khác kích thước thì không thể trùng), rồi băm SHA-256 bằng `hashlib.file_digest` (Python 3.11+) hoặc đọc từng khối 1 MB với `hashlib.sha256` vì project hỗ trợ từ 3.10. Có thể so lần cuối bằng `filecmp.cmp(shallow=False)` để chắc chắn.
- Ý tưởng gom theo kích thước rồi mới băm lấy từ fdupes và jdupes; hai công cụ này là chương trình dòng lệnh, không phải thư viện, nên không gọi từ script.

Phần còn phải làm: viết `find_duplicates()` và test với vài file trùng, file rỗng và symlink.
