# Bảng định tuyến

> Trạng thái: **giả thuyết**, chưa có số liệu eval. Nguồn luật máy đọc: `plugin/skills/task-router/rules.json`.
> Cập nhật bảng này sau khi chạy `python3 evals/run_eval.py --configs A,C,D --repeats 2 --yes`.

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

## Sẽ quyết định bằng số liệu

- Phiên chính dùng `sonnet · medium` (A), `opus · medium` (C) hay `opus · low` (D)?
- Đặt `Explore` sang haiku (`explore-lite`) có làm giảm chất lượng các việc coding không? Cần so cấu hình E với A.
- Bảng `BASELINE.md` cho thấy 70% chi phí đến từ subagent và workflow. Đây là chỗ đáng đo trước tiên.
