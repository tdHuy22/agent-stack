# Văn mẫu kinh điển

Mỗi ngôn ngữ 5 bài, mỗi bài một tác giả và một thể loại, để `tells.py` có văn của người viết thật làm mốc khi project chưa có mẫu riêng. Đầu mỗi file có tên bài, tác giả, năm, thể loại, nơi in, link Wikisource kèm mã phiên bản (`oldid`) và căn cứ thuộc phạm vi công cộng; `tells.py` bỏ phần đầu này khi so từ vựng.

## Tiếng Việt (`vi/`, khoảng 14.100 từ)

| Năm | Tác giả | Bài | Thể loại | Ghi chú |
|---|---|---|---|---|
| 1925 | Phan Châu Trinh | Đạo đức và luân lý Đông Tây | diễn thuyết nghị luận | trích phần đầu, khoảng 3.900 trên 11.000 từ; giữ chính tả và lỗi in của bản in Sài Gòn 1926 |
| 1938 | Thạch Lam | Hai đứa trẻ | truyện ngắn trữ tình | toàn văn |
| 1939 | Ngô Tất Tố | Tắt đèn, chương XVIII và XIX | tiểu thuyết hiện thực, nhiều đối thoại | có đoạn sách giáo khoa trích với tên "Tức nước vỡ bờ" |
| 1943 | Nam Cao | Lão Hạc | truyện ngắn, kể ở ngôi thứ nhất | toàn văn |
| 1945 | Hồ Chí Minh | Tuyên ngôn Độc lập | văn chính luận | bỏ danh sách ký tên; giữ chính tả có gạch nối của bản in thời đó |

Luật Việt Nam bảo hộ quyền tác giả suốt đời tác giả và 50 năm sau năm tác giả mất. Năm tác giả trên mất trong các năm 1926, 1942, 1951, 1954 và 1969, nên mọi bài đã hết hạn bảo hộ ở Việt Nam. Tuyên ngôn Độc lập còn là văn kiện nhà nước.

## Tiếng Anh (`en/`, khoảng 13.800 từ)

| Năm | Tác giả | Bài | Thể loại | Ghi chú |
|---|---|---|---|---|
| 1625 | Francis Bacon | Of Studies | tiểu luận châm ngôn | bản Harvard Classics 1909, bỏ hai lời giải nghĩa trong ngoặc vuông của người biên tập |
| 1729 | Jonathan Swift | A Modest Proposal | tiểu luận trào phúng | toàn văn |
| 1822 | William Hazlitt | On Going a Journey | tiểu luận tản mạn (familiar essay) | toàn văn |
| 1914 | James Joyce | Araby | truyện ngắn | toàn văn |
| 1925 | Virginia Woolf | Modern Fiction | tiểu luận phê bình văn học | toàn văn |

Ba bài đầu đã thuộc phạm vi công cộng ở mọi nơi. Bài của Joyce in năm 1914 và bài của Woolf in năm 1925, nên đã hết hạn ở Mỹ. Hai tác giả mất năm 1941, nên cũng đã hết hạn ở nơi bảo hộ đời tác giả cộng 70 năm (từ 2012) và ở Việt Nam (từ 1992).

## Cách dùng

- Tham khảo cách người viết thật thay đổi độ dài câu, dùng chi tiết cụ thể thay cho lời bình chung chung, mở và kết bài. Không bắt chước giọng riêng của một tác giả.
- Mỗi project viết luận nên có mẫu riêng trong `.agent/giong-van/samples/`. Khi có, `tells.py` so với mẫu đó thay vì bộ này.
- Muốn đổi bài, thay file và giữ khối thông tin ở đầu (`title`, `author`, `year`, `genre`, `source`, `license`). Test `tests/test_giong_van.py` kiểm tra mỗi ngôn ngữ đủ 5 bài và đủ các trường này.
