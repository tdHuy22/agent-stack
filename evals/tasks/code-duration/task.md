Viết hàm `parse_duration(text)` trong `duration.py`, trả về số giây (int).
Định dạng: một hoặc nhiều cặp số + đơn vị, theo thứ tự lớn tới nhỏ, đơn vị là `d`, `h`, `m`, `s`.
Ví dụ: `"1h30m"` → 5400, `"45s"` → 45, `"2d"` → 172800, `"1d2h3m4s"` → 93784.
Cho phép khoảng trắng giữa các cặp (`"1h 30m"`). Chuỗi rỗng, đơn vị lạ, đơn vị lặp lại,
sai thứ tự (`"30m1h"`) hoặc số âm phải ném `ValueError`.
