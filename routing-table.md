# Bảng định tuyến

> Trạng thái: **giả thuyết cho việc khó; đã có số liệu eval cho việc nhỏ** (02/10/2026, xem cuối file). Nguồn luật máy đọc: `plugin/skills/task-router/rules.json`.
> Số liệu lấy từ `python3 evals/run_eval.py --configs A,C,D --repeats 2 --yes`.

| Loại việc | Model · Effort | Subagent | Skill | Căn cứ hiện tại |
|---|---|---|---|---|
| Kiểm duyệt đồ bên thứ ba | opus · high | — | vet-skill | Rủi ro cao, cần phán đoán bảo mật |
| Review bảo mật | opus · high | agent-stack:reviewer | differential-review (nếu cài) | Rủi ro cao |
| Review code trước commit hoặc merge | opus · high | agent-stack:reviewer | — | Lỗi lọt qua thì tốn hơn nhiều |
| Debug khó, nhiều bước | opus · high | — | diagnosing-bugs (nếu cài) | Chuỗi suy luận phụ thuộc nhau |
| Kiến trúc, lập kế hoạch | opus · high | Plan | — | Sai hướng thì tốn công làm lại |
| Xem tiến độ, việc tiếp theo | sonnet · low | — | tien-do | Script làm phần nặng |
| Lưu tiến độ, bàn giao | sonnet · low | — | session-keeper | Việc ghi chép |
| Chạy và viết test | sonnet · medium | agent-stack:test-runner | tdd (nếu cài) | Có tín hiệu kiểm tra tự động |
| Nghiên cứu, so sánh | sonnet · medium | agent-stack:researcher | — | Theo số đo của Anthropic, đường cong effort gần phẳng với việc nghiên cứu |
| Refactor | sonnet · medium | — | — | Có test thì đủ |
| Tính năng thông thường | sonnet · medium | — | — | — |
| Việc cơ học hàng loạt | haiku · low | agent-stack:oc-worker | — | Kết quả kiểm tra được bằng test/diff |
| Viết văn bản | sonnet · medium | — | giong-van, humanizer | — |
| Hỏi nhanh | sonnet · low | — | — | — |

## Kết quả eval (02/10/2026)

12 việc nhỏ (sửa code, đọc tài liệu, review bảo mật mẫu, viết test, viết lại văn bản) × 2 lượt × 3 cấu hình = 72 lượt, chấm bằng test hoặc so đáp án. Tổng khoảng 7,5 USD giá niêm yết, tính vào hạn mức gói (hạn mức 5 giờ đi từ 15% lên 22%, gồm cả phần phiên khác).

| Cấu hình | Đạt | USD/việc (TB) | USD p90 | Giây/việc |
|---|---:|---:|---:|---:|
| A: sonnet · medium | 24/24 | 0,063 | 0,068 | 12 |
| C: opus · medium | 24/24 | 0,128 | 0,149 | 18 |
| D: opus · low | 24/24 | 0,121 | 0,134 | 16 |

- Với loại việc này, cả ba đều đạt hết, nên script chọn **A** (rẻ nhất). Opus tốn gấp khoảng 2 lần mà không đạt thêm việc nào. Hạ effort của Opus xuống `low` gần như không rẻ hơn (0,121 so với 0,128 USD).
- **Giới hạn của số liệu:** vì cả ba đều đạt 100%, bộ việc này không phân biệt được các cấu hình. Nó chỉ cho thấy sonnet · medium đủ cho việc nhỏ có tín hiệu kiểm tra rõ. Nó không nói gì về debug khó, kiến trúc, hay review diff thật, nên các dòng `opus · high` ở trên vẫn là giả thuyết. Muốn phân biệt, cần thêm vài việc khó hơn vào `evals/tasks/`.

## Còn chưa quyết định bằng số liệu

- Đặt `Explore` sang haiku (`explore-lite`) có làm giảm chất lượng các việc coding không? Cần so cấu hình E với A.
- Haiku (cấu hình H) có làm được việc cơ học không? Chưa chạy; khoảng 0,5 USD.
- Bảng `BASELINE.md` cho thấy 70% chi phí đến từ subagent và workflow. Đây là chỗ đáng đo tiếp.
