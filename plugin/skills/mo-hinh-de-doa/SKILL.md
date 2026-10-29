---
name: mo-hinh-de-doa
description: Threat model ngắn cho MỘT chức năng, làm TRƯỚC khi viết code, chỉ khi chức năng đụng ranh giới tin cậy (nhận input từ bên ngoài, xác thực hay phân quyền, gọi dịch vụ ngoài, lưu hay truyền dữ liệu nhạy cảm, thêm dependency, chạy mã hay lệnh, đường dẫn file lấy từ input). Ra tối đa 5 mối đe dọa kèm chốt chặn phải có, ghi vào `.agent/threat-model.md` để lúc chốt việc reviewer kiểm từng chốt chặn. Dùng khi router hay `risk.py` báo đụng ranh giới tin cậy, khi người dùng nói threat model, mô hình đe dọa, STRIDE, hoặc trước khi làm đăng nhập, upload, webhook, API, thanh toán, tích hợp dịch vụ ngoài. Bỏ qua với sửa giao diện, sửa chữ, refactor không đổi luồng dữ liệu; không dùng để audit cả repo.
when_to_use: threat model, mô hình đe dọa, STRIDE, trust boundary, ranh giới tin cậy, attack surface, bề mặt tấn công, trước khi code tính năng đăng nhập, upload, webhook, thanh toán
---

# Mô hình đe dọa nhanh

Mục tiêu: tìm lỗi thiết kế khi còn rẻ để sửa, tức là trước khi code, trong vài phút. Đây không phải audit cả repo; việc đó làm một lần trước khi phát hành.

## 0. Có cần không

- Project có skill threat model riêng (`.claude/skills/threat-model/SKILL.md`, ví dụ project học `security-whitebox`): dùng skill đó và dừng ở đây.
- Chức năng không đụng mục nào dưới đây thì nói một dòng "Không đụng ranh giới tin cậy, bỏ qua threat model" rồi làm tiếp:
  1. input từ bên ngoài process: người dùng, mạng, file người khác đưa, tham số do người khác đặt;
  2. xác thực, phân quyền, phiên đăng nhập, token;
  3. gọi ra ngoài: HTTP, webhook, email, dịch vụ đám mây, model LLM;
  4. lưu, ghi log hay truyền dữ liệu nhạy cảm: secret, dữ liệu cá nhân, thanh toán;
  5. thêm hoặc nâng dependency, plugin, skill bên thứ ba;
  6. chạy mã hay lệnh, giải tuần tự hóa, template, đường dẫn file lấy từ input.

## 1. Vẽ luồng, đọc ít

Chỉ đọc phần code mà chức năng sẽ chạm và các chốt chặn có sẵn của project (hàm kiểm quyền, làm sạch input, cấu hình, luật trong `CLAUDE.md`). Không quét cả codebase. Viết 3–6 dòng: dữ liệu vào từ đâu, qua ranh giới tin cậy nào, tới đâu (DB, file, lệnh, dịch vụ ngoài), và tài sản cần bảo vệ là gì.

## 2. Tìm mối đe dọa

Với mỗi ranh giới, hỏi sáu câu (STRIDE):

| Loại | Câu hỏi |
|---|---|
| Giả mạo | Ai đó tự nhận là người hay dịch vụ khác được không? |
| Sửa trái phép | Dữ liệu, file, tham số bị sửa trên đường đi hay ở chỗ lưu được không? |
| Chối bỏ | Chỉ khi có hành động cần truy vết (tiền, quyền, xóa): có ghi lại ai làm không? |
| Lộ thông tin | Secret, dữ liệu người khác, lỗi chi tiết có lọt ra log, phản hồi, URL không? |
| Từ chối dịch vụ | Chỉ khi mỗi yêu cầu tốn tài nguyên đắt (gọi LLM, xử lý file lớn): có giới hạn không? |
| Leo thang quyền | Input có biến thành lệnh, truy vấn, đường dẫn, hay quyền cao hơn không? |

Giữ tối đa 5 mối có khả năng xảy ra cao nhất. Mối đe dọa là thứ vẫn đúng dù code viết cẩn thận, ví dụ "người dùng A đọc được hóa đơn của B nếu không kiểm chủ sở hữu". Lỗi cụ thể sửa một dòng là hết thì không phải mối đe dọa; để nó cho bước review. Phép thử này lấy ý từ skill `threat-model` của `anthropics/defending-code-reference-harness` (Apache-2.0).

Mỗi mối ghi:
- actor: người dùng ẩn danh, người dùng đã đăng nhập, người dùng khác (tenant khác), quản trị, dịch vụ bên ngoài, mã bên thứ ba, người trong nội bộ;
- surface: file, hàm, endpoint, lệnh nơi mối đe dọa đi vào;
- asset: thứ bị hại;
- chốt chặn phải có: cụ thể và kiểm được trong code hay test, ví dụ "lọc theo `owner_id = user.id` ở truy vấn hóa đơn, test người khác nhận 404". Không viết chung chung như "kiểm input".

## 3. Ghi lại

Thêm một mục vào cuối `.agent/threat-model.md` của project (tạo file nếu chưa có, giữ các mục cũ). File gom mọi chức năng cũ nên đừng đọc cả file: lấy ID lớn nhất bằng `grep -o 'TM-[0-9]*' .agent/threat-model.md | sort -t- -k2 -n | tail -1`, rồi nối mục mới bằng `cat >> .agent/threat-model.md <<'EOF'`:

```markdown
## <ngày YYYY-MM-DD> · <tên chức năng>
Luồng: <3–6 dòng ở bước 1>

| ID | Mối đe dọa | Actor | Surface | Asset | Chốt chặn phải có | Trạng thái |
|---|---|---|---|---|---|---|
| TM-1 | … | … | `app/invoice.py` | hóa đơn của người khác | … | cần làm |
```

- ID tăng dần trong cả file, không dùng lại số cũ.
- Trạng thái: `cần làm`; `đã có` kèm `file:dòng` và test; `chấp nhận rủi ro` kèm lý do và việc người dùng đã đồng ý.
- Không ghi secret hay dữ liệu thật vào file này.

## 4. Dùng kết quả

- Làm chốt chặn cùng lúc với chức năng. Viết test cho nhánh bị từ chối của ít nhất chốt chặn quan trọng nhất.
- Mối đe dọa cần đánh đổi (bỏ tính năng, chấp nhận rủi ro, tốn thêm hạ tầng) thì hỏi người dùng, đừng tự chọn.
- Khi chốt việc, skill `chot-viec` đưa các mục của chức năng này cho reviewer kiểm từng chốt chặn. Có bằng chứng thì sửa trạng thái thành `đã có` kèm `file:dòng`.
- Báo người dùng ngắn gọn: số mối đe dọa, chốt chặn sẽ làm, điểm cần họ quyết.

## Giới hạn

Bản rút gọn để chạy cho từng chức năng. Nó không thấy lỗi do nhiều chức năng ghép lại, cấu hình triển khai hay dependency cũ; những lỗi đó để cho đợt audit cả repo trước phát hành.
