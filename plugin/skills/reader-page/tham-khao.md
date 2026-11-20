# reader-page: tham khảo

Đọc khi cần, không đọc mặc định. Mục 1–3 cho trang đề xuất (có thẻ `data-phuong-an`); mục 4 khi trang hợp một skill khác; mục 5 khi cần hiểu một LỖI của script.

## 1. Đối chiếu đề xuất với luật của project

- Phương án vi phạm luật cứng **không bao giờ được khuyên**. Giữ nó trên trang chỉ khi người dùng đã hỏi tới hoặc đó là lựa chọn tự nhiên mà người đọc sẽ thắc mắc; khi đó thẻ phải có dòng `data-vi-pham` nói vi phạm luật nào. Muốn chọn nó thì phải sửa luật trước, và việc sửa luật là một câu chốt riêng.
- Đề xuất của người dùng đi qua đúng bảng đó. Vi phạm thì nói thẳng trên trang và trong chat; không lặng lẽ làm theo, cũng không lặng lẽ bỏ.
- Hai luật va nhau thì nêu cả hai, đưa thành câu chốt, không tự chọn một bên.

## 2. Pattern xấu cần soát

1. **Theo code cũ.** "Code hiện tại đã làm vậy" không chứng minh cách đó đúng. Đối chiếu tiền lệ với luật; sai luật thì gọi là nợ, không nhân rộng, có thể đề xuất sửa riêng. Ví dụ: một script cũ cài gói bằng `pip install --user`; repo có luật cài vào `.venv/`, nên phương án mới không chép cách đó.
2. **Chiều theo người dùng.** Người dùng nghiêng về một phương án không làm nó tốt hơn. Ví dụ: người dùng nói "cứ dùng model rẻ cho nhanh" cho việc không có test; luật chung chỉ cho dùng model rẻ khi có kiểm tra tự động, nên trang phải nói điều đó.
3. **Chọn vì ít công.** "Ít sửa hơn", "xong nhanh hơn" không phải lý do đủ; cân chất lượng, độ bền, công bảo trì (luật chung "Chất lượng trước chi phí").
4. **Phương án bù nhìn.** Thêm phương án yếu cho khuyến nghị trông tốt. Mỗi phương án phải là thứ một người giỏi có thể chọn; chỉ có một hướng thật thì nói một hướng.
5. **Giấu rủi ro hay lặng lẽ thu hẹp.** Fallback im lặng, nuốt lỗi, bỏ một phần yêu cầu mà không nói.
6. **Đi tắt qua cổng kiểm.** Bỏ test, `--no-verify`, cài toàn cục ngoài đường đã định, dùng đồ bên thứ ba chưa kiểm duyệt, sửa file ngoài phạm vi project cho phép.

## 3. Ví dụ trước và sau (1–4 từ trang thật ngày 19/10/2026, 5 là giả định)

**1. Tóm tắt dùng mã nội bộ.** Trước: "D22 thêm trục dung lượng ν: một giá trị U lấy qua `query_hidden` theo schema hẹp mang số bit hữu hạn, và policy cho phép tới một trần." Người đọc vấp ở D22, ν, U, `query_hidden`. Sau: "Đề xuất D22 cho phép dùng một giá trị lấy từ dữ liệu không tin được, miễn là nó mang rất ít thông tin: một câu có hay không, một lựa chọn trong danh sách cố định, một ngày giờ có giới hạn. Lượng thông tin đo bằng bit, và policy đặt trần cho nó. Ta đã hẹn trước (`PLAN.md` §2): chỉ làm nếu ít nhất 5 trong 97 bài thử cần đúng tính năng này."

**2. Kết quả viết nén.** Trước: "G1 41 · G2 10 · G3 15 · G5 31; cách (ii) 4." Sau: một bảng ba cột "Nhóm bài thử · Nghĩa là gì · Số bài" (41 bài giải được ngay hôm nay, 10 bài cần thêm hàm đọc dữ liệu ẩn, 15 bài cần đo lượng thông tin, 31 bài vẫn phải hỏi người duyệt), rồi một câu: "Chỉ 4 bài thoát được bước hỏi người duyệt nhờ đề xuất này, dưới ngưỡng 5."

**3. Chỉ một ví dụ.** Trang về overlay Kustomize chỉ có một ví dụ (một patch đổi biến môi trường của `cartservice`). Sau: thêm ca thường gặp (`namePrefix: prod-` đổi `cartservice` thành `prod-cartservice`, luật gọi tên cũ không còn khớp), ca biên (`images` đổi tag, công cụ vẫn kiểm image cũ), ca hỏng (`helmCharts` nằm ngoài phần đọc được, cả bản dựng bị báo "chưa đọc được"); rồi chạy ba ca đó qua từng phương án trong bảng ví dụ × phương án.

**4. Lý do theo tiền lệ.** Trước: "Tải binary `kustomize` bản ghim sha256 vào `target/bench/`, như `helm`." "Như helm" là lý do theo code cũ. Sau: hàng ràng buộc dẫn luật của project cho phép tải công cụ đo (`file:dòng`), hoặc ghi `can-duyet` nếu không có luật nào nói tới, và câu chốt hỏi người dùng.

**5. Đề xuất vi phạm luật.** Repo `agent-stack` có luật Python chỉ dùng thư viện chuẩn (`CLAUDE.md`), nên phương án "parse HTML bằng BeautifulSoup cho chắc" bị ghi `vi-pham` trên bảng, thẻ có dòng "Vi phạm luật chỉ dùng thư viện chuẩn: không khuyên", và khuyến nghị chuyển sang `html.parser` của thư viện chuẩn.

## 4. Chi tiết skill khác

- **Trang công cụ:** skill `playground` có 6 khuôn (chỉnh thiết kế, dựng truy vấn, bản đồ khái niệm, góp ý văn bản, duyệt diff từng dòng, bản đồ code). Lấy khuôn hợp nhất, khai `data-loai="cong-cu"`, gắn `data-xuat` vào nút chép prompt, giữ sáng tối theo `artifact-design` (khuôn của nó mặc định tối).
- **Kế hoạch triển khai một hướng, đụng hơn vài file:** `/html-plan`. Trang của nó dùng runtime riêng; kiểm bằng `node <skill html-plan>/runtime/pack.mjs <trang> --lint-only` thay cho `check_page.py`, rồi `pack.mjs` để gói thành một file. Kế hoạch có từ hai phương án thì vẫn dùng khuôn của reader-page.
- **Trang tổng quan project gửi người khác, làm mới cùng link:** `project-artifact`.
- **Diff có chú thích bên lề:** khuôn `diff-review` của `playground`, hoặc tự viết theo loại báo cáo.
- Bốn plugin `playground`, `html-plan`, `project-artifact`, `frontend-design` thuộc bộ `giao-dien`, không nạp sẵn: chưa bật thì `python3 ~/Documents/Claude/agent-stack/plugin/skills/project-setup/scripts/profile.py on giao-dien --project .` (lệnh in đường dẫn SKILL.md để đọc thẳng ngay; plugin nạp đủ sau `/reload-plugins`).

## 5. Script kiểm soát thuật ngữ thế nào

- Chữ viết tắt và mã kỹ thuật phổ biến (API, URL, JSON, CI, PR, UTF-8, SHA-256…) đã được miễn sẵn; tên project của người đọc khai trong `data-tu-quen` trên phần tóm tắt. Mã có chữ số và ký hiệu Hy Lạp không miễn được.
- Tên trong `<code>` không bị soát, nhưng vẫn phải giải thích bằng lời ở lần đầu.
- `--khuon` dành cho trang mới viết theo khuôn; trang đã có CSS của khuôn cũ thì script chỉ thêm meta còn thiếu.
