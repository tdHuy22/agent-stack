---
name: project-setup
description: Đánh giá một project rồi đề xuất cấu hình riêng cho agent-stack trong `.agent/stack.json`, file do hook đọc, model không đọc. File gồm từ khóa riêng kèm mức nghĩ, từ khóa router cần bỏ qua, thư mục lõi tính rủi ro cao, mức sàn theo vùng và theo cỡ project, công cụ kiểm có sẵn, mức quy trình. Mỗi mục kèm bằng chứng; người dùng duyệt từng mục rồi mới ghi. Chạy trong phiên của chính project cần cấu hình, đọc cả project một lần (Explore đọc rộng). Dùng khi bắt đầu dùng agent-stack ở một project, khi router gợi ý sai mức ở project đó, khi lúc mở phiên báo hồ sơ project đã đổi hay có đề xuất từ nhật ký router, hoặc khi người dùng nói cấu hình project, stack.json, project-setup. Không dùng để sửa luật chung của agent-stack.
when_to_use: cấu hình project, cấu hình riêng cho project, stack.json, project-setup, router gợi ý sai ở project này, mức sàn, từ khóa riêng, hồ sơ project đổi, đề xuất cho stack.json
---

# Cấu hình riêng của project (`.agent/stack.json`)

File này chỉ chứa "núm chỉnh", không chứa văn cho model đọc. Hook và router đọc file và nâng mức gợi ý; model không đọc nên không tốn token. Lý do không sinh văn: file chỉ dẫn do model viết làm tăng chi phí mà không tăng tỉ lệ giải việc (trang kế hoạch agent-stack theo project, ý 1). Luật miền thật sự cần model đọc thì đặt ở `.claude/rules/` có `paths:`, không đặt ở đây.

Script: `S=~/Documents/Claude/agent-stack/plugin/skills/project-setup/scripts/stack.py`, chạy `python3 $S <lệnh>` từ thư mục project.

## 1. Chọn phiên

- Chạy trong phiên của chính project, bằng model của phiên (Opus high), không giao subagent cả việc.
- Chạy `python3 $S scan` trước. Nếu `scan` báo project lớn hay mới, hoặc yêu cầu còn mơ hồ, khuyên người dùng mở phiên này bằng Fable high (bảng Fable ở `routing-table.md`). Không đổi model giữa phiên.
- Việc đọc cả project chỉ làm một lần. Sau đó chỉ làm lại phần mà dòng mở phiên báo hồ sơ đã đổi, hay phần mà `learn` có đề xuất.

## 2. Thu bằng chứng

1. `python3 $S scan` cho các số đo sau:
   - cỡ project;
   - cụm từ của router gặp nhiều trong code (ứng viên `ignore`, ví dụ "schema" ở 185 dòng vì là tên trường);
   - công cụ có trên máy;
   - ứng viên thư mục lõi, thư mục hay đổi;
   - file quyết định và nhật ký;
   - nên dùng archctl không;
   - sàn theo cỡ.
2. Giao subagent `Explore` (đọc rộng, chỉ đọc) đọc các file quyết định và nhật ký mà `scan` liệt kê. Prompt tự đủ, gồm:
   - loại việc đã khó hay đã hỏng trong project (lỗi lặp, quyết định khó đảo ngược, phần an toàn);
   - từ người dùng hay gõ khi nói về các phần đó (ví dụ "rò nhãn", "luật quyết định");
   - thư mục chứa các phần đó.
   Explore trả về kèm `file:dòng`.
3. Tự kiểm vài chỗ Explore trích trước khi dùng làm bằng chứng.

## 3. Đề xuất từng mục, người dùng duyệt từng mục

In mỗi mục một khối: mã mục, nội dung, lý do, bằng chứng (số đếm, `file:dòng`), và mục này siết hay nới. Gom thành một danh sách cho người dùng chọn. Chỉ ghi mục người dùng đã duyệt trong chat. Ghi từng mục bằng:

```bash
python3 $S apply --item '{"kind":"keyword","phrase":"rò nhãn","model":"opus","effort":"xhigh","reason":"…","evidence":"…"}'
```

| kind | Trường | Tác dụng |
|---|---|---|
| `keyword` | `phrase`, `model`, `effort` | câu có cụm này: router không gợi ý dưới mức đó |
| `ignore` | `phrase` | router bỏ qua cụm này khi chấm (nới; cụm của luật bảo mật bị từ chối) |
| `area` | `name`, `paths`, `words`, `model`, `effort` | `paths`: done-gate tính diff đụng tới là rủi ro cao; `words`: router nâng lên mức đó |
| `floor` | `group` (debug, feature, architecture, review, code, protected), `model`, `effort` | mức sàn theo nhóm luật, theo cỡ và độ phức tạp của project |
| `tool` | `name` (tên trong danh mục của `checks.py`) | done-gate tính công cụ khai mà máy thiếu là thiếu (mã 2) |
| `process` | `min_risk` (thap, vua, cao) | mức rủi ro tối thiểu của mọi thay đổi |

Quy định khi ghi:
- Mức chỉ nhận haiku, sonnet, opus với low..xhigh (không nhận fable, max). Từ khóa và vùng chỉ để nâng nên tối thiểu là sonnet · medium.
- Mỗi mục phải có `reason`, `evidence`; `date` tự điền.
- Cuối cùng chạy `python3 $S apply --fingerprint` để ghi dấu vân tay hồ sơ (ngôn ngữ, có test, có code bảo mật, có archctl). Lúc mở phiên, hook so dấu này với hồ sơ hiện tại và nhắc khi lệch.

Ngoài `stack.json`:
- Đề xuất effort mặc định của project là `effortLevel` trong `.claude/settings.local.json` (không commit), người dùng duyệt.
- `scan` khuyên dùng archctl khi project có từ hai ngôn ngữ hay hai thành phần trở lên, hoặc có docker-compose. Khi đó đề xuất `archctl init --from-code`; người dùng tự chạy hay duyệt.

## 4. Siết tự do, nới cần người dùng

- **Siết** (thêm từ khóa, nâng mức, thêm vùng, sàn, công cụ, nâng `min_risk`) có tác dụng ngay.
- **Nới** (hạ mức, bỏ mục, bớt đường dẫn, thêm `ignore`, hạ `min_risk`) ghi vào file được, nhưng chưa có tác dụng. Hook dùng bản chụp cấu hình đã duyệt trên máy này, lấy mức cao hơn.
- Muốn mục nới có tác dụng:
  1. Đưa người dùng mã mục (`python3 $S check` liệt kê dòng ⏸ chờ duyệt).
  2. Người dùng trả lời một tin có "duyệt <mã mục>" (ví dụ "duyệt ignore:schema"). Câu có phủ định hay loại trừ (không, đừng, trừ, nhưng) hay có từ lạ sau "duyệt" không được tính. Duyệt cả danh sách: người dùng nhắn "duyệt hết <mã>" với mã mà `check` in ra, rồi chạy `approve all:<mã>`; danh sách đổi thì mã đổi.
  3. Chạy `python3 $S approve <mã mục>`. Hook chặn lệnh này nếu tin vừa gửi không nêu đúng mục.
- Không ghi thẳng vào `state/stack-approved/`.
- Bản chụp nằm trên máy. Máy mới, hay bản chụp bị mất, thì file hiện tại được dùng như lần đầu gặp: phần siết có tác dụng ngay, `ignore` phải duyệt lại. Mất bản chụp thì lúc mở phiên báo trong 7 ngày.

## 5. Học từ nhật ký

- Hook ghi mỗi tin một dòng vào `state/route-log.jsonl`: gợi ý của router và effort đang dùng.
- `python3 $S learn` so gợi ý với mức thật đã cần, theo ba loại bằng chứng:
  - người dùng nâng hay hạ `/effort` ở tin sau;
  - test trượt sau một gợi ý rẻ;
  - review tìm ra lỗi mức cao.
- Cùng luật, cùng cụm, cùng chiều lệch lặp từ 3 lần trở lên thì thành đề xuất. Đề xuất siết vẫn đưa người dùng duyệt như mục 3; đề xuất nới đi đường duyệt ở mục 4.
- Lúc mở phiên, hook chỉ báo số đề xuất.

## Không làm

- Không ghi mục nào người dùng chưa duyệt.
- Không chép nội dung `stack.json` vào `CLAUDE.md` hay file luật.
- Không sửa project khác ngoài project của phiên.
