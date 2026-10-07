Quyết định: chưa chốt được, cần bạn chọn, vì ba ràng buộc của project va nhau.

- tomllib (thư viện chuẩn) chỉ có từ Python 3.11, mà project phải chạy trên Python 3.9 (requires-python, CI và CONTRIBUTING.md).
- tomli (MIT, bản backport của tomllib) giải quyết được, nhưng CONTRIBUTING.md cấm thêm gói ngoài vì máy build không có mạng.

Các lựa chọn:
1. Chép nguyên tomli (một gói thuần Python, giấy phép MIT) vào repo dưới `tools/_vendor/`: vẫn chạy offline, nhưng là đưa code bên thứ ba vào repo, nên cần bạn đồng ý.
2. Đổi `release.toml` sang JSON hoặc INI để đọc bằng `json` hoặc `configparser` của thư viện chuẩn.
3. Nâng yêu cầu lên Python 3.11 rồi dùng tomllib: phải đổi máy build và CI.

Phần còn phải làm sau khi bạn chọn: viết `load_config()` trong tools/release.py và thêm test chạy trên cả 3.9 lẫn 3.12.
