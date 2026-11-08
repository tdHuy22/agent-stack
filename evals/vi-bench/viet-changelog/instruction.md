Mình sắp phát hành bản 2.4.0 của SổQuỹ, app ghi chép chi tiêu cá nhân. Lịch sử commit (tiếng Anh, mới nhất ở trên cùng) nằm ở `/app/repo/git-log.txt`. Viết giúp mình ghi chú phát hành bằng tiếng Việt vào file `/app/CHANGELOG.md`, để người dùng bình thường đọc, họ không biết lập trình.

Yêu cầu:

- Chỉ ghi những gì thuộc bản 2.4.0: các commit sau dòng tag v2.3.0 cho tới dòng tag v2.4.0 trong log. Việc trước hay sau khoảng đó không ghi.
- Dòng đầu: `# Phiên bản 2.4.0 (ngày/tháng/năm)`, ngày lấy theo commit chốt bản 2.4.0.
- Chia đúng ba mục, tên đúng như sau và theo thứ tự này: "Thêm" (tính năng mới), "Sửa" (lỗi đã sửa), "Thay đổi" (cách dùng đổi khác đi, đổi tên, yêu cầu máy, chạy nhanh hơn). Mỗi mục là danh sách gạch đầu dòng, mỗi ý một dòng.
- Chỉ ghi điều người dùng nhìn thấy hay cảm nhận được. Việc nội bộ của lập trình viên thì bỏ. Thứ đã thêm rồi gỡ lại trong cùng bản thì coi như không có. Không ghi số commit, số `#`, không dùng thuật ngữ lập trình.
- Màn hình nào của app có tên tiếng Việt trong log thì dùng đúng tên đó. Nếu bản này đòi máy phải có phiên bản Android nào trở lên thì ghi rõ phiên bản đó.
- Tối đa 200 chữ (đếm theo từng tiếng).
