# API v2

## Xác thực
Gửi token qua header `Authorization: Bearer <token>`.

## Giới hạn
Mỗi token được tối đa 120 request mỗi phút. Server trả về header `X-RateLimit-Remaining`
cho biết số request còn lại trong phút hiện tại, và `X-RateLimit-Reset` là thời điểm reset (epoch).
Khi vượt giới hạn, server trả về mã 429 kèm header `Retry-After`.
