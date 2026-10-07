# PLAN: triển khai agent-stack

**Đây là nguồn sự thật DUY NHẤT về tiến độ triển khai.** Thiết kế chi tiết ở `KE-HOACH.md`; file này chỉ ghi đang ở đâu và việc gì tiếp theo.

## 0. Đang ở đâu, việc tiếp theo (cập nhật mỗi lần dừng phiên)
*Cập nhật 07/10/2026.*

- **Xong:**
  - GĐ0 đến GĐ11 và mọi việc sau đó nằm trên `main` (nhánh `trien-khai-v1` đã gộp và xoá ngày 03/10/2026); chưa push.
  - Plugin `agent-stack` 0.4.3, **đã cập nhật toàn cục** lúc 22:26 ngày 03/10/2026 theo lệnh của bạn (nhật ký `state/install-logs/20261003-222654.json`; `claude plugin list` báo 0.4.3, bản cache khớp `plugin/`): 6 skill, 5 agent, 6 hook. **Đã cập nhật toàn cục lên 0.4.2** lúc 21:07 ngày 03/10/2026 theo lệnh của bạn (nhật ký `state/install-logs/20261003-210751.json`): `claude plugin list` báo 0.4.2, bản cache giống hệt `plugin/` (diff rỗng), `vet.py drift` chạy từ bản cache báo 3 plugin chính thức khớp; hook SessionStart của bản cache, thử với bản chép `context7` bị sửa trong `.tmp/`, hiện cảnh báo lệch trên Python 3.9 và 3.11. Phiên mở trước 21:07 vẫn chạy 0.4.1. Trước đó, 0.4.1 lúc 10:11 (0.4.0 lúc 09:25): `claude plugin list` báo 0.4.1, bản cache khớp nguồn từng file, có bản sửa lỗi báo cáo subagent bị lưu nhầm thành yêu cầu của bạn và bị router gợi ý nhầm. Chuỗi yêu cầu, subagent, báo cáo quay về, subagent thứ hai chạy thử trên file đã cài (Python 3.9 và 3.11): đạt. Các phiên desktop mở trước 10:11 vẫn chạy 0.4.0.
  - Bên thứ ba: 24 mục đã kiểm duyệt: 21 duyệt, 3 từ chối, không còn mục chờ. Ngày 03/10/2026 bạn quyết ba mục cuối theo khuyến nghị: `sandbox-runtime` duyệt có điều kiện (chỉ dùng cục bộ trong `.cache/srt`), `claude-security` duyệt có điều kiện (chỉ gọi tay, cài theo project khi cần; chưa cài), `plugin-dev` từ chối. Duyệt không có nghĩa là đã cài.
  - Bộ eval 12 việc đã chạy thật ngày 02/10/2026 (72 lượt, khoảng 7,5 USD giá niêm yết, tính vào hạn mức gói): sonnet·medium, opus·medium và opus·low đều đạt 24/24; sonnet rẻ nhất (0,063 USD/việc, so với 0,128 và 0,121). Bộ việc chưa phân biệt được các cấu hình (xem `routing-table.md`). Đo kích hoạt skill bằng `claude plugin eval` (13 ca, 3,67 USD): 10/10 ca cần kích hoạt đều gọi đúng skill, 3/3 ca không được kích hoạt đều sạch. 317 test đạt trên Python 3.9 và 3.11.
  - Bảng định tuyến đã đối chiếu với khuyến nghị chính thức của Anthropic (Claude Code, bài chọn model và effort, trang chi phí): `routing-table.md`. Chỉ một dòng đổi: debug khó bắt đầu ở opus·medium rồi nâng lên high nếu chưa ra; các dòng opus·high còn lại giữ vì không có kiểm tra tự động.
  - **Đã cài toàn cục** lúc 15:19 ngày 02/10/2026, theo đồng ý của bạn trong chat. Nhật ký: `state/install-logs/20261002-151930.json`, `…152532.json`, `…153032.json`, `20261002-221518.json` (context7), `20261003-092531.json` (cập nhật plugin 0.4.0), `20261003-101141.json` (cập nhật plugin 0.4.1). Mọi thay đổi và lệnh gỡ từng mục nằm trong `INSTALLED.md`; gỡ toàn bộ: `./install.sh --rollback --apply`.
  - Kiểm chứng sau khi cài:
    - 7 plugin đều bật lúc cài, file khớp bản đã kiểm duyệt. Ngày 03/10/2026, lần `/doctor` lúc 09:57 tắt năm plugin; lần `/doctor` buổi chiều gỡ hẳn ba plugin trùng chức năng theo đồng ý của bạn (`claude-md-management` trùng `/doctor`, `/init` và bộ nhớ tự động; `session-report` trùng `tools/usage_snapshot.py`; `claude-code-setup` trùng hồ sơ project và `reuse-best`) và đổi scope của chúng trong `catalog.json` thành `on-demand` để `install.sh` không cài lại. Đang bật: `agent-stack`, `agent-stack-vendor`, `context7`. Cài nhưng tắt ở scope user: `pyright-lsp`, `clangd-lsp` (không trùng gì); từ tối 03/10 chỉ bật riêng từng project khi router đề xuất (xem mục "Quyết định của bạn tối 03/10/2026");
    - CLI nạp plugin tại chỗ, đã thấy `plugin_root` trong `state/sessions.jsonl`;
    - desktop app chạy bản chép trong cache, tìm về repo nhờ `plugin/.agent-stack-home`.
  - **Rà soát nguồn chính thức của Anthropic và việc a đến e** (02/10/2026; chi tiết ở `KE-HOACH.md` §6.13):
    - (a) `vet.py dynamic` (`sandbox-runtime` đã duyệt có điều kiện ngày 03/10/2026: chỉ dùng cục bộ): chạy MỘT lệnh của đối tượng trong sandbox-runtime (cài cô lập `.cache/srt`, `--ignore-scripts`, theo `tools/srt/package-lock.json`): không mạng, chỉ đọc ghi trong bản chép tạm, HOME thật bị chặn. Phát hiện chắc chắn bằng HOME giả rải 12 file mồi (đọc qua atime, rò rỉ qua dấu riêng); log vi phạm của macOS chỉ là phần thêm vì đo được nó mất khoảng một nửa sự kiện khi tiến trình thoát nhanh. Sửa hai luật quét báo nhầm (socat, CI). Mới kiểm trên macOS. **Review độc lập trước khi gộp** (agent `reviewer`, opus·high, 02/10/2026) tìm ra 1 lỗi cao, 6 trung bình, 6 thấp; đã sửa hết và thêm test: ghi vào `/tmp/claude` (srt tự mở), né bằng tên tiến trình, mồi bị đặt lại thời gian hay xóa, FIFO làm treo bước quét, tiến trình nền, lệnh không chạy được mà vẫn báo "không thấy gì", hạ bậc `.github/` quá rộng, che khóa còn sót, PLAN.md vào context như chỉ dẫn. Review lượt hai (0 cao, 3 trung bình, 6 thấp) cũng đã sửa: script ở gốc HOME từng mở cả HOME để đọc, giả chim hoàng yến qua tên người dùng proxy, kho vi phạm của srt chỉ giữ 100 sự kiện cuối (nay báo khi tràn), diệt nhầm tiến trình (nay chỉ tiến trình bắt đầu sau lúc chạy), PEM nuốt cả câu. Giới hạn còn lại đã ghi: truy vấn keychain qua dịch vụ hệ thống (không chặn được `security` bằng cấu hình), đọc mồi bằng clonefile `cp -c` không làm atime nhảy, mã nhận ra sandbox vẫn né được.
    - (b) `plugin-dev`: script kiểm hook của nó lỗi thời (đòi `matcher` mà `claude plugin validate` không đòi); `session_end.py` chạy 29 đến 68 ms nên giữ `timeout: 2`. Không cài; đã từ chối ngày 03/10/2026.
    - (c) `reviewer.md`: hình dạng lỗi, verifier phản biện, ngưỡng tin cậy 80, bảng lọc dương tính giả; `plugin/NOTICES.md` ghi nguồn MIT và Apache-2.0.
    - (d) `tien-do`: mục "Đổi từ lần trước" qua snapshot trong `state/tien-do/`.
    - (e) `claude-security`: đã vet và duyệt có điều kiện ngày 03/10/2026 (chỉ gọi tay, theo project); chưa cài.
  - **Skill và agent chạy context riêng không thấy hội thoại** (bạn nêu 02/10): hook SubagentStart đưa yêu cầu gần nhất của bạn (che khóa, tối đa 1200 ký tự) và 1 đến 2 việc đầu §0 vào đầu context của chúng; mọi agent và skill fork ghi rõ cần gì và thiếu thì nói rõ; luật chung dặn giao việc bằng prompt tự đủ. **Đã chạy thử bản đã cài ngoài phiên** (file trong cache, thư mục trạng thái tạm, Python 3.9 và 3.11): thoát 0, không in lỗi, khóa giả bị che, ngữ cảnh 747 ký tự (trần 1500), sự kiện `subagent-start` có `"request": true`. **Đã kiểm chạy thật** ngày 03/10/2026 bằng `claude -p` (CLI nạp plugin tại chỗ từ `plugin/`; hai lượt, khoảng 0,34 USD giá niêm yết): SubagentStart chạy, session_id khớp UserPromptSubmit, và subagent trích ra được yêu cầu của bạn (dấu ngẫu nhiên không có trong prompt giao việc). **Lỗi tìm thấy nhờ chạy thật, đã sửa ở 0.4.1:** báo cáo của subagent quay về phiên chính như một tin của người dùng (`<agent-message …>`, `[Subagent hand-back]`), nên bị lưu thành "yêu cầu gần nhất" (subagent thứ hai nhận nhầm báo cáo của subagent trước) và router gợi ý nhầm `tien-do`; nay bị coi là tin tự động. Chạy lại với hai subagent liên tiếp: cả hai nhận đúng yêu cầu. **App desktop đã kiểm trong phiên thật** lúc 15:03 ngày 03/10/2026 (phép thử `[PT-697887]`, phiên `69b1fb8a…`): `plugin_root` của phiên trong `state/sessions.jsonl` là bản cache `…/agent-stack/0.4.1`; `state/events.jsonl` có dòng `subagent-start` của phiên với `agent_type` `agent-stack:explore-lite`, `"request": true`, `"plan": true`, 1214 ký tự; subagent chép nguyên văn yêu cầu của bạn kèm mã phép thử và tìm đúng `plugin/hooks/subagent_start.py:72`. Báo cáo quay về không ghi đè yêu cầu: `state/last-request/` (quyền 0600) giữ tin tiếp theo của bạn, còn yêu cầu phép thử nằm ở mục `earlier`.
  - **Quyền riêng tư OpenCode**: model mặc định `opencode/muse-spark-1.3-contributor-free` dùng prompt và kết quả để huấn luyện model của Meta (trang OpenCode Zen). Luật chung và `oc-worker` ghi: không tự rơi về model từ xa, không giao secret hay mã riêng tư. Ngày 03/10/2026 bạn cho biết đã tự setup OpenCode riêng và không cần repo quan tâm: đây không còn là việc chờ bạn quyết; luật chung và `oc-worker` giữ nguyên.
  - **Kiểm lệch plugin so với bản đã vet** (03/10/2026, plugin 0.4.2 trong repo): marketplace chính thức tự cập nhật (lúc 10:00 03/10 `context7`, `session-report` đổi nhãn từ `ab024cd` sang `d182ca4`; file vẫn giống hệt bản đã kiểm). Lệnh mới `vet.py drift` (chỉ đọc) so sha256 từng file plugin đã cài với `.vet-cache` qua `catalog.json` và `vetted.lock`; hook SessionStart chạy nó khi mở phiên mới và chỉ báo khi lệch. Chạy thật trên máy: 3 plugin chính thức khớp, 0,14 giây. 327 test đạt trên Python 3.9 và 3.11, `claude plugin validate plugin` đạt (có biên nhận). Giới hạn: cấu hình của plugin `strict: false` nằm trong `marketplace.json` nên không được so.
  - **Quyết định của bạn tối 03/10/2026** (plugin 0.4.3 trong repo; 343 test đạt trên Python 3.9 và 3.11, `claude plugin validate plugin` đạt, có biên nhận):
    - Bỏ việc cấp quyền MCP `context7`: nó đã kết nối được trong phiên desktop, không cần `/mcp`.
    - LSP chỉ bật theo project. `catalog.json` để `pyright-lsp`, `clangd-lsp` ở scope `project`, nên `install.sh` không bật toàn cục. Hồ sơ project lúc mở phiên (router) đề xuất bật riêng cho project (`claude plugin enable … --scope local`, kèm lệnh cài `pyright` hay `clangd` nếu thiếu) khi project có từ 150 file Python hoặc 30 file C/C++, hoặc có cấu hình kiểm kiểu hay biên dịch (`pyrightconfig.json`, `[tool.mypy]`, `CMakeLists.txt`…), và plugin chưa bật. Chạy thật trên máy: chỉ `XiaomiMiMo/verl` (730 file, có `[tool.mypy]`) và `XiaomiMiMo/MiMo-V2.6-RL-oss` (5.653 file) được đề xuất; `agent-stack` (69), `SCEE` (55), `pdf-translator` (24), `archctl` thì không. `maintain.py` thôi nhắc cài `pyright`, `clangd` toàn cục.
    - Viết luận dùng cả tiếng Việt và tiếng Anh. `giong-van` có 5 bài văn học kinh điển mỗi ngôn ngữ, thuộc phạm vi công cộng, lấy từ Wikisource kèm mã phiên bản (`plugin/skills/giong-van/samples/kinh-dien/`, danh sách trong `README.md` ở đó). Mỗi project viết luận có mẫu riêng trong `.agent/giong-van/samples/` và style card riêng `.agent/giong-van/style-card.md`. `tells.py` chọn mẫu cùng ngôn ngữ theo thứ tự: của project, bài tự viết trong `samples/`, rồi văn kinh điển; với văn kinh điển thì không so cách xưng hô.
    - Không kích hoạt theo dõi tiến độ toàn cục, không bản tổng hợp tuần: mỗi project tự theo dõi qua §0 của nó (hook SessionStart và `tien-do` trong project đó). `tien-do all` vẫn chạy được khi bạn hỏi.
  - **Skill `paper-anatomy` nâng cấp** (03/10/2026, theo yêu cầu của bạn; nguồn ở `claude-ai-skills/paper-anatomy/`, không nằm trong plugin vì claude.ai đồng bộ nó thành `anthropic-skills:paper-anatomy`). Tìm skill có sẵn trước (deer-flow `academic-paper-review`, nanochat `read-arxiv-paper`, AI-SKILLS `reading-papers`, K-Dense): không cái nào thay được, chỉ lấy ý tưởng. Thêm `verify_anchors.py` (kiểm từng neo: trang, mục, Hình/Bảng/Eq, trích nguyên văn), viết lại `extract_paper.py` (nhãn trang khai báo trong PDF, outline, `--pages`, `--find`, `--render`), chế độ hỏi hẹp/giải phẫu/phản biện, `references/critical-appraisal.md`, `references/hard-pdfs.md`, bước tự rà con số và câu "bài không nói". PyMuPDF và pypdf cài vào `.venv` (không cài toàn cục). **Bench bằng sonnet trên 5 bài trong Zotero của bạn, chấm mù bằng opus** (`claude-ai-skills/paper-anatomy-bench/RESULTS.md`): bản mới thắng 10/12 lần so cặp qua ba vòng (đều sát nút trừ bài scan Biba); điểm kiểm chứng 5,0 so với 4,0–4,2; neo sai do máy kiểm 0/318 so với 17/167 (10,2%); dễ đọc kém hơn (4,0–4,2 so với 4,5–4,8); đắt hơn khoảng 45% (0,72–0,78 so với 0,51 USD/bài). Tổng chi phí bench khoảng 11,6 USD giá niêm yết cho lượt làm bài, cộng người chấm opus.
  - **Eval thêm 6 việc khó** (commit `7f01c16`): `debug-multifile`, `debug-race`, `review-diff`, `code-cron-next`, `code-async-pool`, `code-unified-diff`; self-test 18/18. Chạy thật (04/10/2026 có thêm C, D): sonnet·medium 12/12 (0,116 USD/việc), opus·medium 12/12 (0,254), opus·low 12/12 (0,215), haiku 4/12 và đắt hơn sonnet (0,191). Script chọn A. Ghi ở `routing-table.md`. Tổng khoảng 9 USD giá niêm yết.
  - **Bảng định tuyến mịn hơn, effort từ low tới max** (04/10/2026, theo yêu cầu của bạn; plugin 0.4.4, **đã cập nhật toàn cục** lúc 08:23 ngày 04/10/2026 theo lệnh của bạn, nhật ký `state/install-logs/20261004-082347.json`; `claude plugin list` báo 0.4.4, bản cache khớp `plugin/`, hook router từ bản cache chạy đúng trên Python 3.9 và 3.11). Đối chiếu tài liệu chính thức đọc lại 04/10/2026 (trang effort, model-config, chi phí, bảng giá): `xhigh` cho việc agent trên 30 phút (+1,4 điểm, 2,5 lần chi phí so với `high`), `max` cho bài khó tự làm tới cùng như săn lỗ hổng (lợi ích giảm dần), Haiku không có effort, `ultrathink` cho một lượt. `routing-table.md` viết lại: thang effort, thang leo thang 10 bậc, 47 dòng việc trong 8 nhóm, mỗi dòng có cấu hình bắt đầu, bậc tiếp theo và căn cứ (E/A/P). `rules.json` từ 15 lên 32 luật, có luật tinh chỉnh (`refines`, `only_refine`) để "thanh toán" một mình không bị đẩy lên review bảo mật `xhigh`; router đúng 88/88 câu có nhãn (thêm 35 câu, có ca dễ nhầm). Bảng ➡️ trong `global/CLAUDE.global.md` (symlink sang `~/.claude/CLAUDE.md`, có hiệu lực ngay) thay bằng 22 dòng.
  - **Áp dụng ý từ video của Kun Chen** (07/10/2026, theo yêu cầu của bạn; GĐ12, chi tiết và nguồn ở `KE-HOACH.md` mục 6.14; plugin 0.5.0 trong repo, **chưa cập nhật trên máy**). Luật chung thêm 5 ý (chọn theo chất lượng không theo công làm, tái hiện lỗi end-to-end trước, chạy `chot-viec` trước khi báo xong, ghi bài học vào file nhớ project, skill cần số liệu eval). Hai file luật có hiệu lực ngay ở phiên mới vì là symlink. Skill mới `chot-viec` với `risk.py`. Eval có cấu hình V để đo skill vendor, ghi skill nào được gọi. Router 33 luật, 97/97. Review độc lập (agent `reviewer`, opus · high) tìm 2 lỗi vừa, 2 thấp, đều đã sửa kèm test: `finish-gate` cướp câu hỏi tiến độ; `risk.py --base` sai ref thì âm thầm ra diff rỗng; repo chưa commit bỏ sót phần sửa sau `git add`; `meta.json` ghi sai tool của cấu hình có plugin. 382 test đạt trên Python 3.9 và 3.11, `claude plugin validate plugin` đạt, self-test eval đạt (có biên nhận).
  - **Tách luật OpenCode, rút gọn luật toàn cục** (07/10/2026, theo yêu cầu của bạn; GĐ13). Claude Code nạp `global/SHARED.global.md` (import ở dòng đầu `CLAUDE.global.md`) và `CLAUDE.global.md`; OpenCode nạp `global/AGENTS.global.md`, nay là file ghép `SHARED` + `OPENCODE.global.md` bằng `tools/build_rules.py` (test báo nếu quên ghép). Không đổi symlink hay cấu hình OpenCode, nên không cần cài lại. Claude Code nạp 8.924 thay vì 10.190 byte (−12%), OpenCode 5.683 thay vì 5.922 (−4%). Không mất luật: script đối chiếu (22/22 dòng bảng, mọi tên lệnh, file và khái niệm) và review độc lập (opus · high, 69 luật); review bắt 2 chỗ, đã sửa: câu riêng tư bị hẹp lại chỉ còn OpenRouter và model free, và đường dự phòng đọc thẳng `SKILL.md` bị chuyển nhầm sang phần OpenCode (Claude cần nó khi plugin trên máy cũ hơn repo). Phiên `claude -p` thật (haiku, 0,03 USD) thấy luật chung qua import và không thấy phần OpenCode.
  - **Sửa `reuse-best` sau eval có bẫy** (07/10/2026, theo yêu cầu của bạn; GĐ14, chi tiết ở `KE-HOACH.md` mục 6.15; plugin 0.5.1 trong repo, **chưa cập nhật trên máy**). Tái hiện trước khi sửa: bản cũ đạt 12/12 trên 4 việc có bẫy, nên 4 rủi ro mình nêu trước đó (dừng ở thứ đủ dùng, đề bài mỏng, hụt phạm vi, đọc nông) không tái hiện được. Lỗi thật tìm được nhờ lưu luồng sự kiện: không kiểm chứng được ứng viên (`gh`, WebFetch bị chặn), lệnh shell ghép bị chặn, câu tìm GitHub kèm tên ngôn ngữ ra rỗng. Đã sửa: `scout.py repo` (phát hành hay tag, issue, dòng README theo từng tiêu chí), tìm lại khi câu tìm ra rỗng, `SKILL.md` viết lại (một lệnh đơn mỗi lần, đọc ràng buộc của project, tiêu chí bắt buộc, chỉ dừng khi có bằng chứng, mục "Phần còn phải làm" và "Cần người dùng quyết"), một câu trong luật chung. Bản mới cũng đạt 12/12, lệnh bị chặn 3,6 → 0,2, kiểm repo 0 → 2,7 lần mỗi lượt, đắt hơn 7%. Review độc lập (opus · high): 0 cao, 4 vừa (grader cho lọt 10/27 câu sai, chấm oan 8/26 câu đúng), 2 thấp; đã sửa hết, chấm lại mọi bài đã chốt. Eval tổng 7,49 USD giá niêm yết. 417 test đạt trên Python 3.9 và 3.11 (có biên nhận).
  - **Gộp kết quả phiên "Video review và áp dụng": AXI cho `scout.py`** (07/10/2026, theo yêu cầu của bạn; GĐ15, chi tiết ở `KE-HOACH.md` mục 6.16; plugin 0.5.2 trong repo, **chưa cập nhật trên máy**). Ý AXI còn treo của phiên đó ("chưa rà lại các script cũ") áp vào `scout.py`: dòng tổng trước, dòng "Tiếp:" có lệnh chạy được ngay, `repo` kiểm tối đa 5 repo một lần, không in README khi đã có `--find`, câu tìm rỗng thì bỏ thêm từ cuối, chạy không tham số thì in cách dùng. Eval 12 lượt: đạt 12/12, 0,198 USD và 46 giây mỗi lượt (0.5.1: 0,218 USD, 55 giây; bản cũ: 0,203 USD, 45 giây), 0 lệnh bị chặn, 0 lần tìm ra rỗng, vẫn kiểm 2,2 repo mỗi lượt bằng 0,9 lần gọi. Một lượt bị grader chấm oan, đã sửa grader và chấm lại cả năm đợt. Review (sonnet): không lỗi đạt ngưỡng, ba nhận xét nhỏ đã sửa. 421 test đạt trên Python 3.9 và 3.11 (có biên nhận). Eval đợt này 2,38 USD.
- **Đang dở:** không có việc đang sửa dở. `KE-HOACH.md` còn 2 dòng đổi từ trước phiên này (gỡ Phi-4-mini, ngày 05/10/2026) chưa commit; mình không đưa vào commit của GĐ12, GĐ13 và GĐ14. Mục "Bộ duyệt web" trong §0 là của một phiên khác, cũng chưa commit.
- **Việc tiếp theo, theo thứ tự (đều cần bạn):**
  1. Cập nhật plugin trên máy lên 0.5.2 để app desktop có `chot-viec` và `reuse-best` bản mới: `./install.sh --apply --only plugin`, rồi mở phiên mới. Sau đó, nếu đồng ý tốn khoảng 3,4 USD hạn mức: chạy A/B skill vendor `python3 evals/run_eval.py --configs A,V --tasks debug-multifile,debug-race,code-duration,code-cron-next,code-async-pool,qa-write-tests,write-vn-rewrite --repeats 2 --yes`; skill nào không hơn A thì cân nhắc tắt.
  2. Khi bắt đầu một project viết luận: đặt 3–5 bài mẫu cùng thể loại vào `.agent/giong-van/samples/` của project, rồi nhờ Claude chạy `giong-van tao-style-card` cho project đó.
  3. Tùy chọn, không cài cũng không hỏng gì: `brew install gitleaks osv-scanner` (không code nào gọi).
  4. Cập nhật skill `paper-anatomy` trên claude.ai: tải `.tmp/dist/paper-anatomy.skill` (tạo lại bằng `python3 claude-ai-skills/package.py paper-anatomy`) lên Settings → Capabilities → Skills, thay bản cũ cùng tên. Claude Code nhận bản mới ở lần đồng bộ sau.
  5. Push khi bạn muốn: `git push` (mình không tự push). Repo chưa có remote nào, nên cần `git remote add origin <url>` trước.
- **Quyết định còn treo:**
  - **Gác lại (bạn nói 03/10/2026: không cần quan tâm OpenCode vì đã setup riêng; chỉ làm khi bạn nhắc).** Có thêm eval bằng model free trên OpenRouter qua OpenCode không. Mục đích là đo xem worker OpenCode và phương án dự phòng khi hết hạn mức có giữ chất lượng không; việc này không thay eval Claude. Nếu làm, cần bạn:
    - tạo key OpenRouter và đặt vào biến môi trường (mình không nhập key);
    - quyết định có nạp 10 USD không (mức 1.000 request mỗi ngày, so với 50 khi chưa nạp);
    - chọn 2–3 model free có gọi tool, hoặc để `reuse-best` chọn theo benchmark.
    - Phần mình làm: thêm cấu hình `opencode run -m openrouter/<model>:free`, cách ly khỏi cấu hình toàn cục của OpenCode, giới hạn dưới 20 request mỗi phút, và `--resume`.
    - Bạn cho biết OpenCode đang dùng OpenRouter và model free của OpenCode (02/10/2026); chưa rõ key đã nằm trong biến môi trường chưa. Lưu ý quyền riêng tư ở trên: model free có thể dùng dữ liệu để huấn luyện.
    - Câu còn mở ở `KE-HOACH.md` mục 10 (việc hay thư mục tuyệt đối không gửi cho model từ xa) chỉ cần khi dùng model từ xa qua OpenCode, nên gác lại cùng mục này.
- **Mốc kiểm tra:** chạy qua `python3 plugin/skills/session-keeper/scripts/receipt.py run -- <lệnh>` để có biên nhận.
  - `/usr/bin/python3 -m unittest discover -s tests -t .` và với `python3` → `Ran 421 tests … OK (skipped=1)`; test bị bỏ qua cần PyMuPDF, chạy bằng `.venv/bin/python -m unittest tests.test_paper_anatomy`
  - `claude plugin validate plugin` → `Validation passed`
  - `python3 evals/run_eval.py --self-test` → 22 dấu ✓ (18 việc chọn cấu hình, 4 việc của bộ `suite:reuse-best`)
  - `python3 plugin/skills/task-router/scripts/route.py --eval evals/router-prompts.jsonl` → 97/97
- **Sau khi bị ngắt:** chạy `git -C ~/Documents/Claude/agent-stack status`, `git log --oneline -5`, `python3 plugin/skills/session-keeper/scripts/receipt.py show` và `claude plugin list`, rồi đọc `INSTALLED.md` và mục này.

## 1. Giai đoạn

### GĐ0: Chuẩn bị và đo nền
- [x] Khung repo, `.gitignore`, `CLAUDE.md`, `README.md`, `PLAN.md`.
- [x] Sao lưu `~/.claude/settings.json` và `~/.config/opencode/opencode.jsonc` vào `backups/2026-10-01/` (không đưa vào git).
- [x] Kiểm chứng OpenCode bằng `opencode debug config`: đọc được cả `tuf` lẫn `openai-oauth`.
- [x] `tools/usage_snapshot.py` kèm test; viết `BASELINE.md`.
- [x] Bỏ Jev khỏi kế hoạch; ghi các quyết định đã chốt vào đầu `KE-HOACH.md`.
- [x] Claude Code CLI đã tự nâng lên 2.1.285 trong lúc triển khai (≥ 2.1.277, đọc được `AGENTS.md`). OpenCode 2.0.21.
- [x] **Bạn làm:** điền số liệu `/usage` và `/insights` vào `BASELINE.md`. Xong 02/10/2026: số liệu ở `BASELINE.md` (phần `/usage` đọc lại bằng `get_usage`, chưa có phân tích theo skill/subagent/MCP).

### GĐ1: Cổng kiểm duyệt
- [x] Cài `cisco-ai-skill-scanner==2.1.0` vào `.venv` (Apache-2.0; kéo theo nhiều thư viện nặng như litellm, openai, fastapi, nên cài cô lập).
- [x] Skill `vet-skill`: `scripts/vet.py` + `scripts/redflags.py` + test (FAIL khi có dấu hiệu mã độc trong code, REVIEW khi cần người đọc).
- [x] Kiểm duyệt 3 repo, ghi `vetted.lock` và `vet-reports/`:
  - humanizer: REVIEW → Claude đọc tay, khuyến nghị cài.
  - webapp-testing: REVIEW → Claude đọc tay, khuyến nghị cài khi cần.
  - planning-with-files: REVIEW → không cài cả repo (507 file, 17 hook), dùng `session-keeper` tự viết thay thế.
- [x] **Bạn làm:** đọc báo cáo, rồi chạy `vet.py approve <khóa> --note "..."` cho mục bạn đồng ý. Xong 02/10/2026: 21 mục đã có quyết định (19 duyệt, 2 từ chối, 0 chờ).

### GĐ2: Bền bỉ phiên (#3)
- [x] Plugin `plugin/` + `.claude-plugin/plugin.json`; `claude plugin validate plugin` → passed.
- [x] `global/AGENTS.global.md`, `global/CLAUDE.global.md`. Mẫu PLAN/HANDOFF nằm trong `plugin/skills/session-keeper/templates/`.
- [x] Hook: SessionStart (nạp §0), UserPromptSubmit (cảnh báo hạn mức), PreCompact, Stop (chỉ nhắc, không thêm lượt), SessionEnd (ghi phiên). Chống chạy trùng bằng file đánh dấu O_EXCL.
- [x] `statusline/statusline.py` ghi `state/limits.json`.
- [x] Skill `session-keeper` + `scripts/state.py` (show / init / handoff).
- [x] Test hook bằng dữ liệu giả, trên Python 3.9 và 3.11.
- [x] Chạy thử 1 phiên `claude -p --plugin-dir`: hook chạy đúng và context chèn vào đúng. Bước gọi model bị lỗi vì **CLI ở terminal hết phiên đăng nhập**.
- [x] **Bạn làm:** chạy `claude /login` ở terminal, rồi thử `claude --plugin-dir ~/Documents/Claude/agent-stack/plugin` trong một thư mục có PLAN.md. Xong 02/10/2026: `claude -p` đáp bình thường; plugin đã cài toàn cục, `plugin_root` đã ghi trong `state/sessions.jsonl`.

### GĐ2b: Theo dõi tiến độ (#7)
- [x] Skill `tien-do` + `scripts/collect.py` + test. Xếp hạng 5 bậc; chế độ `--all` cho mọi project; tùy chọn `--gh` lấy PR/CI.
- [x] Gộp bản tóm tắt vào hook SessionStart (thêm dòng "Chặn đường" và các cảnh báo nhanh, không gọi mạng).
- [x] Chạy thử trên chính agent-stack. Đã sửa hai lỗi lộ ra: TODO trong tài liệu và TODO nằm trong chuỗi ký tự bị tính nhầm.
- [x] **Không kích hoạt** (bạn quyết 03/10/2026: mỗi project tự theo dõi qua §0 của nó, không theo dõi toàn cục, không bản tổng hợp tuần). Lệnh vẫn dùng được khi bạn hỏi: `python3 plugin/skills/tien-do/scripts/collect.py --all --md` để xem tổng quan mọi project. Lệnh chỉ đọc project (chỉ ghi snapshot vào `state/` của agent-stack; thêm `--no-snapshot` để không ghi); mình không tự chạy vì bạn dặn không đụng vào project khác.

### GĐ3: Danh mục v1
- [x] Kiểm duyệt 18 mục mới (ghim đúng commit mà marketplace chính thức dùng) + 3 mục cũ. Claude đã đọc tay và ghi nhận xét vào `vetted.lock`: 11 cài, 7 có điều kiện hoặc chỉ dùng trong project, 1 thử trong 1 project, 2 không cài (semgrep plugin, planning-with-files).
- [x] Tinh chỉnh luật sau khi chạy thật: mẫu trong chú thích hạ một bậc; U+200B trước code fence là lành; bắt `allowed-tools` tự duyệt sẵn lệnh tải-rồi-chạy; nhận xét đọc tay giữ được qua các lần quét lại.
- [x] Sửa lỗi của chính repo: mã nguồn từng chứa ký tự vô hình thật (do escape bị giải mã khi ghi file). Có test vệ sinh chặn lỗi này.
- [x] `catalog.json` + `tools/install.py` (`install.sh`): mặc định chỉ xem trước; chỉ cài mục bạn đã `approve`; skill chỉ có chỉ dẫn được chép đúng commit đã kiểm vào `vendor/`; có `--rollback`. Test chạy trên HOME giả.
- [x] **Bạn làm:** đọc các báo cáo trong `vet-reports/`, rồi `python3 plugin/skills/vet-skill/scripts/vet.py approve <khóa> --note "..."` cho mục đồng ý. Xong 02/10/2026: 8 mục còn lại đã duyệt (xem dòng trên).
- [x] **Bạn làm:** xem trước bằng `./install.sh`, rồi `./install.sh --apply` khi đồng ý (thêm `--restore-workflow-warning` để bật lại cảnh báo usage). Xong lượt đầu 02/10/2026 (cờ `--restore-workflow-warning` chưa dùng, `skipWorkflowUsageWarning` vẫn `true`). Trong 8 mục duyệt sau đó, `context7` đã cài ở phạm vi user (xem mục 7 ở trên).

### GĐ4: Đội agent và eval
- [x] Agent Claude Code (trong plugin, tên có tiền tố `agent-stack:`): reviewer (opus·high, chỉ đọc), researcher (sonnet·medium), test-runner (haiku), explore-lite (haiku, không ghi đè Explore có sẵn), oc-worker (haiku, điều phối OpenCode).
- [x] Agent OpenCode `worker` (tuf/coder-fast): đã xác minh OpenCode v2 nạp được (theo symlink file) và áp đúng luật quyền (`shell` chặn hết trừ lệnh kiểm tra, `webfetch` chặn).
- [x] Bộ eval 11 việc trong `evals/` + `run_eval.py`: grader tự kiểm bằng lời giải mẫu; test chống grader dễ dãi; mặc định chỉ in kế hoạch.
- [x] **Bạn duyệt ngân sách** (ước tính khoảng 13,6 USD theo giá niêm yết, tức khoảng 66 lượt, tính vào hạn mức), rồi: `claude /login`, sau đó `python3 evals/run_eval.py --configs A,C,D --repeats 2 --yes`. Xong 02/10/2026: chạy thành ba đợt A, C, D; thực tế khoảng 7,5 USD.
- Ghi chú: máy `tuf` (192.168.1.13) đang không kết nối được, nên oc-worker chỉ chạy khi ở mạng nhà.
- Ghi chú: OpenCode v2.0.x trả về danh sách skill rỗng qua API, kể cả với skill tối giản. Phương án dự phòng: `AGENTS.global.md` ghi đường dẫn của từng skill để agent tự đọc.
- Ghi chú: OpenCode v2 báo các thiết lập `reasoning` và `temperature` kiểu cũ của provider `tuf` trong `opencode.jsonc` đang bị bỏ qua. Bạn có thể dọn khi tiện; mình không sửa file của bạn.

### GĐ5: Router (#4, #5)
- [x] Skill `task-router`: `rules.json` (14 luật lúc đầu; 32 luật từ 04/10/2026, effort từ low tới max), `route.py`. Đã nối vào hook UserPromptSubmit: chỉ gợi ý khi có việc nên làm (đổi model/effort, skill, subagent), mỗi luật nhắc tối đa một lần mỗi giờ trong một phiên, bỏ qua lệnh `/` và câu ngắn. Đã nối vào `tien-do`.
- [x] Bộ 47 prompt có nhãn (`evals/router-prompts.jsonl`): đúng 47/47. **Lưu ý thiên lệch:** Claude viết cả luật lẫn prompt, nên hãy thêm prompt thật của bạn.
- [x] `routing-table.md` (giả thuyết, chờ số liệu eval).
- [x] `plugin/evals/`: 10 case đo kích hoạt skill (7 nên kích hoạt, 3 không nên).
- [x] **Bạn làm (tốn một ít hạn mức):** `claude plugin eval ~/Documents/Claude/agent-stack/plugin --runs 1 --max-cost-usd 3 --trust-plugin --no-publish`. Dùng `--no-publish` để báo cáo chỉ nằm trên máy. Xong 02/10/2026: 13 ca, 3,67 USD giá niêm yết. 10/10 ca cần kích hoạt đều gọi đúng skill, 3/3 ca không được kích hoạt đều sạch. Cột Δ chỉ cho biết skill chạy khi có plugin, chưa đo skill làm việc tốt đến đâu.

### GĐ6: Viết tự nhiên (#6)
- [x] Skill `giong-van` (chế độ chỉnh văn và chế độ `tao-style-card`): giữ nguyên ý, không bịa sự kiện, nêu rõ phạm vi (không nhằm qua mặt công cụ phát hiện AI).
- [x] `scripts/tells.py`: dò dấu hiệu văn AI tiếng Việt và tiếng Anh, nhịp câu đều, lạm dụng gạch dài, in đậm, emoji; cho điểm trên 1.000 từ để so trước và sau.
- [x] `vi-ai-tells.md` (danh sách có ví dụ và cách sửa), `style-card.md` (mẫu chờ điền), `samples/` (không đưa vào git).
- [x] Việc eval thứ 12 `write-vn-rewrite` + case đo kích hoạt `writing-rewrite`.
- [x] Nâng cấp theo nghiên cứu (02/10/2026; nguồn ở cuối `vi-ai-tells.md`): `tells.py` thêm mệnh đề đuôi bình luận, né chữ "là", kết bài "thách thức và triển vọng", phần chatbot bị dán sót, mật độ "việc/sự + động từ"; so với bài mẫu của bạn (từ bạn hiếm dùng, xưng hô, cụm lặp lại); chuẩn hóa Unicode NFC; sửa lỗi báo sai số dòng. `SKILL.md` viết lại theo lối khẳng định: sửa nội dung trước, giữ chất Việt, trả về đúng định dạng của văn gốc, 5 bài mẫu là đủ.
- [x] Thay theo bạn (03/10/2026): 5 bài văn học kinh điển mỗi ngôn ngữ (Việt, Anh) trong `samples/kinh-dien/` làm mẫu mặc định; mỗi project viết luận có mẫu riêng trong `.agent/giong-van/samples/` và style card riêng. Còn lại, khi có project viết luận: thêm mẫu rồi nhờ Claude chạy `giong-van tao-style-card` cho project đó và duyệt từng mục.

### GĐ7: Vận hành
- [x] `tools/maintain.py`: phiên bản, đồ bên thứ ba có commit mới (so với commit đã kiểm), test và validate, ngân sách mô tả skill, mức dùng 7 ngày so với nền, dọn cache. Chạy mỗi tháng: `python3 tools/maintain.py`.

### GĐ8: Dùng lại tốt nhất (#1, reuse-best)
- [x] Ghi rõ ý của câu "(luôn kiểm tra" theo lời bạn (02/10/2026): trước khi build hay làm gì, luôn tìm thứ có sẵn tốt nhất như công cụ trên GitHub hoặc bài nghiên cứu SOTA. Cập nhật `KE-HOACH.md` (N3, mục 7.9, mục 10).
- [x] Skill `reuse-best` (sonnet · medium, chạy trong context riêng) và `scripts/scout.py`: GitHub qua `gh` (tìm theo độ khớp và theo sao rồi gộp), bài báo qua OpenAlex rồi Semantic Scholar rồi arXiv; đánh dấu repo đã lưu trữ, không giấy phép, copyleft, lâu không cập nhật, và bài preprint. Đã chạy thử thật với GitHub và OpenAlex.
- [x] Luôn được nhắc: luật trong `AGENTS.global.md`, dòng mới trong bảng chọn model của `CLAUDE.global.md`, router gợi ý cho mọi việc "tính năng" và "kiến trúc" kèm lưu ý bỏ qua việc vặt, cộng luật riêng cho câu hỏi kiểu "có sẵn chưa", "SOTA". Bộ prompt có nhãn: 53/53.
- [x] 2 case đo kích hoạt mới trong `plugin/evals/` và 1 grader chặn kích hoạt nhầm với việc vặt. 12 test mới.
- [x] **Bạn làm (tốn một ít hạn mức):** chạy `claude plugin eval` (xem GĐ5) để đo skill có tự kích hoạt đúng lúc không. Xong 02/10/2026: 13 ca, 3,67 USD giá niêm yết. 10/10 ca cần kích hoạt đều gọi đúng skill, 3/3 ca không được kích hoạt đều sạch. Cột Δ chỉ cho biết skill chạy khi có plugin, chưa đo skill làm việc tốt đến đâu.

### GĐ9: Sửa sau lần rà soát yêu cầu (02/10/2026)
- [x] A. Biên nhận kiểm tra: `session-keeper/scripts/receipt.py` chạy lệnh kiểm tra và ghi kết quả gắn với dấu vân tay nội dung code (commit mà không đổi nội dung thì vẫn khớp). `tien-do` xếp kiểm tra đang trượt vào bậc chặn đường và nhắc chạy lại khi kết quả đạt đã cũ; tín hiệu này trước đó không bao giờ hoạt động. Không viết skill `verify` riêng, vì Claude Code đã có `/verify`.
- [x] B. Eval chạy ngoài repo: model không thấy `CLAUDE.md`, grader hay lời giải; script từ chối chạy nếu thấy file chỉ dẫn ở thư mục cha. Bài làm được chốt thành patch, có `--regrade` và `--report`, chia nhóm lỗi vận hành và lỗi môi trường, chỉ chốt cấu hình khi ma trận đủ, ghi điều kiện chạy vào `.meta.json`.
- [x] C. `install.py` in tổng kết: mã thoát 1 khi có lỗi, 2 khi cài chưa đủ. Sửa thêm lỗi cũ do test mới lộ ra: hai bước cùng sửa `settings.json` thì bản sao lưu sau ghi đè bản đầu, làm hoàn tác sai.
- [x] D. `maintain.py` báo các CLI khuyến nghị chưa cài (gitleaks, osv-scanner); việc cài ghi ở §0. Từ 03/10/2026 không nhắc `pyright`, `clangd` toàn cục nữa: chỉ cần ở project được router đề xuất bật LSP.
- [x] E. Bước `autocontinue` trong `install.py` đặt `autoContinueAtUsageLimit = true`, chỉ khi bạn chưa tự đặt.
- [x] 25 test mới.

### GĐ10: Chọn skill theo project, gợi ý sau mỗi câu trả lời (#4 + #5, 02/10/2026)
- [x] Mô tả plugin (cả `plugin.json` lẫn marketplace) nhắc đủ các phần; phiên bản 0.3.0. (Kiểm chứng khi cài ngày 02/10/2026: CLI trong terminal nạp plugin tại chỗ từ `agent-stack/plugin`, còn desktop app chạy bản chép trong `~/.claude/plugins/cache/`. Bản chép tìm về repo nhờ file `plugin/.agent-stack-home` do `install.py` ghi. Sau khi sửa plugin: tăng `version`, chạy `./install.sh --apply --only plugin` (gồm `claude plugin update`), rồi mở phiên mới.)
- [x] Dòng ➡️ ở cuối mọi câu trả lời, có thêm trường Skill. Luật trong `AGENTS.global.md` áp cho cả Claude Code và OpenCode; bảng chọn của Claude Code có thêm cột Skill.
- [x] Hồ sơ project (`agentstack.project_profile`): loại code, có test, có CI, có Docker, có code nhạy cảm bảo mật. Chỉ dựng cho git repo hoặc thư mục có file kế hoạch; lưu tạm 6 giờ.
- [x] Hook mở phiên gợi ý skill hợp với project (phân biệt skill đã có và skill chờ bạn duyệt), subagent nên dùng, và cách làm việc tiếp theo trong §0. Git repo chưa có file kế hoạch cũng nhận gợi ý.
- [x] Mỗi tin nhắn: "làm tiếp" được định tuyến theo §0; loại project bổ sung skill cho luật đang khớp. 6 test mới.
- [x] Sửa sau lần rà soát thứ ba:
  - `KE-HOACH.md` từng ghi sai rằng tự làm tiếp ở giới hạn 5 giờ được bật mặc định; thực tế khóa này mặc định chưa đặt.
  - Tài liệu từng ghi skill OpenCode được link vào `~/.agents/skills/`, trong khi `install.py` link vào `~/.config/opencode/skills/`.
  - Lộ trình trong mục tóm tắt và README đã cập nhật.
  - OpenCode không có hook, nên luật chung dặn chạy `route.py --session` ở câu trả lời đầu tiên của phiên.
  - Có test chặn tài liệu nói khác code ở hai điểm trên. 5 test mới.

### GĐ11: Cài toàn cục (02/10/2026)
- [x] Trước khi cài:
  - Kiểm tra bản marketplace chính thức trên máy: commit khác bản đã kiểm duyệt, nhưng file của 5 plugin sắp cài giống hệt từng byte.
  - Kiểm tra các file và thư mục sắp bị sửa.
- [x] Sửa `install.py` để ghi lại và gỡ được sạch:
  - `INSTALLED.md` ghi mọi lần cài;
  - `--rollback` gỡ mọi lần cài, mới nhất trước;
  - `vendor/` có marketplace riêng và không đưa vào git;
  - mỗi lần gỡ xóa đúng các thư mục do lần cài tạo;
  - chụp cấu hình trước khi cài, rồi dọn `enabledPlugins`, `extraKnownMarketplaces`, cache và dữ liệu plugin khi gỡ.
- [x] Lỗi lộ ra khi làm, đã sửa và có test:
  - hai lần chạy cùng một giây ghi đè bản chụp;
  - lệnh gỡ chọn nhầm nhật ký cũ vì sắp theo tên file;
  - lần cài sau xóa bản ghi lần trước;
  - lệnh "đã có" bị ghi như một thay đổi.
- [x] Ghi quyết định của bạn vào `vetted.lock` (bạn đồng ý trong chat, mình gõ lệnh), rồi chạy `./install.sh --apply`: 28 thay đổi, 0 lỗi.
- [x] Kiểm chứng sau khi cài:
  - cả 7 plugin đều bật;
  - file của plugin đã cài khớp bản đã kiểm duyệt (chỉ thêm file `.in_use` do Claude Code tạo);
  - phiên `claude -p` cho thấy CLI nạp plugin tại chỗ;
  - desktop app chạy bản chép trong cache, nên thêm file `plugin/.agent-stack-home` để bản chép tìm về repo, và bước `plugin update`.
- [x] Có một phiên SCEE được resume lúc 15:24, trước khi có file trỏ. Hook của phiên đó ghi trạng thái vào `~/.claude/plugins/data/agent-stack-inline`. Hook chỉ đọc SCEE, không sửa gì; thư mục đó sẽ được dọn khi gỡ.

### GĐ12: Áp dụng ý từ video của Kun Chen (07/10/2026)
Quyết định và nguồn: `KE-HOACH.md` mục 6.14.
- [x] Luật chung thêm 5 ý: chọn giải pháp theo chất lượng, không theo công làm; sửa lỗi phải tái hiện end-to-end trước; chạy `chot-viec` trước khi báo xong; đề nghị ghi bài học vào file nhớ project; skill hứa làm agent giỏi hơn cần số liệu eval. Viết gọn chỗ khác nên hai file luật chỉ tăng từ 9.240 lên 10.190 byte.
- [x] `CLAUDE.global.md`: kế hoạch có từ hai phương án hoặc ba quyết định thì đăng trang Artifact riêng tư để bình luận; dòng bảng ➡️ cho việc kiểm trước commit dùng `chot-viec`.
- [x] Skill `chot-viec` (theo ý `no-mistakes`): ý định, phạm vi, `risk.py` chấm rủi ro, kiểm chứng có biên nhận cộng tái hiện như người dùng, review ở context mới theo mức rủi ro, rà tài liệu, báo cáo, commit có điều kiện, không push. 19 test.
- [x] Eval: cấu hình V (A + plugin vendor), cho phép `Skill`, đọc `stream-json` để ghi skill nào được gọi, bảng có dòng "gọi skill ở n/m lượt". Lượt khói thật (haiku, 0,03 USD) xác nhận plugin nạp được và skill được ghi nhận. `meta.json` ghi tool và định dạng output theo từng cấu hình. 4 test.
- [x] Router: luật `finish-gate`, skill `chot-viec` cho `code-review-small`, ghi chú cách chạy qua đêm cho `long-agent` (theo `gnhf`); 97/97 câu, gồm 5 câu âm (hỏi tiến độ, test, bài luận "xong chưa" không được rơi vào `finish-gate`). Ca eval kích hoạt `finish-gate` và grader không kích hoạt.
- [x] `reuse-best`: sao chỉ đo độ phổ biến; đừng ước công tự viết theo tốc độ của người.
- [ ] Chạy thật A/B vendor (khoảng 3,4 USD giá niêm yết, cần bạn đồng ý): `python3 evals/run_eval.py --configs A,V --tasks debug-multifile,debug-race,code-duration,code-cron-next,code-async-pool,qa-write-tests,write-vn-rewrite --repeats 2 --yes`.
- [ ] Cập nhật plugin trên máy lên 0.5.0 (cần bạn đồng ý): `./install.sh --apply --only plugin`.

### GĐ13: Tách luật OpenCode, rút gọn luật toàn cục (07/10/2026)
- [x] `global/SHARED.global.md` (luật chung), `global/OPENCODE.global.md` (riêng OpenCode và công cụ không có hook), `global/CLAUDE.global.md` import SHARED; `global/AGENTS.global.md` là file ghép cho OpenCode, sinh bằng `tools/build_rules.py` (`--check` để kiểm). Symlink và cấu hình OpenCode giữ nguyên.
- [x] Viết gọn từng luật, giữ đủ 69 luật cũ theo góc nhìn từng công cụ: Claude Code nạp 8.924 thay vì 10.190 byte, OpenCode 5.683 thay vì 5.922.
- [x] Đường dự phòng "chưa thấy skill thì đọc thẳng `SKILL.md`" ở luật chung, vì plugin Claude Code trên máy có thể cũ hơn repo.
- [x] `tests/test_global_rules.py` (8 test): file ghép khớp nguồn, Claude chỉ import SHARED, Claude không nạp phần OpenCode, OpenCode nạp đủ cả hai.
- [x] HUONG-DAN: câu kích hoạt `chot-viec` không còn "xong chưa" (khớp router sau lần sửa của GĐ12).

### GĐ14: Sửa `reuse-best` sau eval có bẫy (07/10/2026)
- [x] Bộ đo `suite:reuse-best`: 4 việc có bẫy (`reuse-gap`, `reuse-constraint`, `reuse-scale`, `reuse-stdlib`); grader chấm theo ý, thử với 26 câu đúng và 27 câu sai trong `tests/test_eval_suites.py`.
- [x] Harness: việc thuộc `"suite"` không lẫn vào bộ chọn cấu hình; `--plugin-root` + `--tag` để so hai phiên bản plugin; dấu vân tay plugin mỗi lượt, tính trước khi chạy, và cảnh báo khi một cấu hình lẫn hai phiên bản; `--save-streams`, `skill_outputs`; bảng việc × cấu hình; self-test và regrade dùng thư mục tạm riêng; tên bộ đo sai thì báo lỗi.
- [x] `evals/trace_stats.py`: đo quá trình (lệnh ghép, lệnh bị chặn, tìm ra rỗng, kiểm repo, chỗ "chưa kiểm") từ luồng sự kiện đã lưu.
- [x] Tái hiện trước khi sửa: bản cũ (0.5.0) đạt 12/12; lỗi thật nằm ở quá trình, không ở 4 rủi ro giả định.
- [x] `scout.py`: lệnh `repo` (phát hành hay tag, issue đang mở, giấy phép, dòng README theo từ khóa), tìm lại khi câu tìm ra rỗng, báo rõ repo không tồn tại thay vì giống lỗi mạng, chặn tên repo giống cờ dòng lệnh.
- [x] `SKILL.md` viết lại; luật chung thêm một câu (phần nhu cầu chưa đáp ứng không được lặng lẽ bỏ); `HUONG-DAN.md`, `README.md`, `evals/README.md`, `KE-HOACH.md` mục 6.15 và 7.9 khớp code; plugin 0.5.1.
- [x] Đợt chạy sạch trên bản cuối: 12/12, bảng so sánh ở `evals/README.md`. Review độc lập: 6 phát hiện, đã sửa hết.
- [ ] Cập nhật plugin trên máy: gộp vào mục 0.5.2 của GĐ15.

### GĐ15: Gộp kết quả phiên "Video review và áp dụng": AXI cho `scout.py` (07/10/2026)
- [x] `scout.py` theo AXI: dòng tổng trước, dòng "Tiếp:", `repo` nhiều repo một lần (tối đa 5), `--max-lines`, README chỉ in khi xem một repo không có `--find`, nới câu tìm thêm bước bỏ từ cuối, chạy không tham số in cách dùng, đầu vào sai thoát mã 2.
- [x] `SKILL.md`: kiểm ứng viên đầu bảng trong một lệnh, gộp tiêu chí vào một `--find`, làm theo dòng "Tiếp:"; plugin 0.5.2.
- [x] Eval 12 lượt (`E@axi`): 12/12, rẻ và nhanh hơn 0.5.1, ngang bản cũ; bảng ở `evals/README.md`. Grader `reuse-stdlib` sửa một chỗ chấm oan; chấm lại năm đợt.
- [x] Review độc lập (sonnet): 0 lỗi đạt ngưỡng, 3 nhận xét nhỏ đã sửa.
- [ ] Cập nhật plugin trên máy lên 0.5.2 (cần bạn đồng ý): `./install.sh --apply --only plugin`.
