# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Nguyễn Tiến Tuân
- **MSSV:** 2A202602595
- **Lớp:** K4-L3A
- **Repository URL:** https://github.com/t00-tuannguyen/K4-L3-DAY13-NguyenTienTuan-2A202602595-Monitoring-LLMOps
- **Commit SHA cuối:**
- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1`
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-2A202602595`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/01-pytest.png` |
| Log validator | `evidence/02-log-validator.png` |
| Dashboard validator | `evidence/03-dashboard-validator.png` |
| Structured log | `evidence/04-structured-log.png` |
| PII redaction | `evidence/05-pii-redaction.png` |
| Trace list | `evidence/06-trace-list.png` |
| Trace waterfall | `evidence/07-trace-waterfall.png` |
| Trace metadata | `evidence/08-trace-metadata.png` |
| Prompt versions | `evidence/09-prompt-versions.png` |
| Prompt rollback | `evidence/10-prompt-rollback.png` |
| Dashboard runtime | `evidence/11-dashboard-overview.png` |
| Incident metric | `evidence/12-incident-metric.png` |
| Incident log | `evidence/13-incident-log.png` |
| Incident trace | `evidence/14-incident-trace.png` |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 — 20/21 record thiếu `correlation_id`, 20 record thiếu enrichment, 0 correlation ID hợp lệ ([output](evidence/baseline-validate-logs.txt)) | 100/100 ([output](evidence/02-log-validator.txt)) | Baseline: middleware chưa sinh/bind ID (`MISSING`), `main.py` chưa bind context. Cuối: đạt sau CP1 |
| `validate_dashboard.py` | HỢP LỆ 6/6 panel ([output](evidence/baseline-validate-dashboard.txt)) | HỢP LỆ 6/6 ([output](evidence/03-dashboard-validator.txt)) + [dashboard runtime](evidence/11-dashboard-overview.png) | Baseline chỉ có contract; cuối có dashboard runtime 6 panel với threshold |
| `pytest` | 22 passed ([output](evidence/baseline-pytest.txt)) | 33 passed ([output](evidence/01-pytest.txt)) | Thêm 11 test cho PII, middleware, child observations |
| Số traces hợp lệ | 10 traces trong Langfuse, nhưng 0 hợp lệ: mỗi trace chỉ có 1 observation `lab-agent-run`, `correlation_id=MISSING`, `prompt_source=local-fallback` | 65 trace gốc trong project; ~55 trace tạo sau CP2 có đủ `retrieval` + `llm-generate`, `correlation_id` thật ([list](evidence/06-trace-list.png)); từ 15:32 prompt lấy từ Langfuse | Baseline chưa có child observation và chưa tạo prompt `day13-chat` |
| Số PII leak | 0 (validator) | 0 trong log; trace không lưu input thô ([ảnh](evidence/08b-trace-generation-no-input.png)) | Baseline: `summarize_text()` đã scrub `message_preview` nhưng `scrub_event` chưa được đăng ký. Cuối: scrub đệ quy mọi field trước khi ghi |
| Latency P95 / TTFT P95 | 3305 ms / 55 ms (P50 1989 ms, P99 3605 ms, n=10) | ~160 ms / 55 ms ở trạng thái bình thường sau khi tạo prompt (P95 cả cửa sổ 60 phút là 6325 ms vì gồm incident practice `rag_slow`) | Baseline vượt SLO 3000 ms vì prompt `day13-chat` chưa tồn tại, mỗi request chờ timeout 2 s rồi fallback |
| Retrieval success rate | 100% (10/10) | 100% ở trạng thái bình thường; 85.5% trong cửa sổ có incident practice `tool_fail` | Dashboard bắt được sự cố practice |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** `CorrelationIdMiddleware` (`app/middleware.py`) gọi `clear_contextvars()` ở đầu mỗi request để không rò context từ request trước. Nếu header `x-request-id` khớp `^req-[0-9a-f]{8}$` thì dùng lại, ngược lại sinh `req-<8-hex>` từ `uuid4`. ID được bind vào structlog contextvars, lưu ở `request.state` để truyền vào `LabAgent.run` (trace metadata), và trả lại qua header `x-request-id` cùng `x-response-time-ms`. Header không đúng format bị thay bằng ID mới để client không chèn được giá trị tùy ý vào log.
- **Các metadata được ghi vào structured log:** `app/main.py` bind `user_id_hash` (SHA-256 cắt 12 ký tự, không ghi user_id thô), `session_id`, `feature`, `model`, `env` trước log `request_received`, nên mọi log trong request (`request_received`, `response_sent`, `request_failed`) đều mang đủ context cùng `ts`, `level`, `service`, `event`, `correlation_id`.
- **Cách bảo đảm PII được scrub trước khi ghi:** `scrub_event` được đăng ký trong processor chain *trước* `JsonlFileProcessor` và `JSONRenderer`, nên dữ liệu bị che trước khi serialize hoặc ghi file. Scrubber duyệt đệ quy mọi field dạng chuỗi (kể cả dict/list lồng trong `payload`), không chỉ `payload` và `event`. `app/pii.py` có pattern cho email, thẻ thanh toán, CCCD 12 số, SĐT Việt Nam (`0…`/`+84…`, có dấu cách/chấm/gạch) và hộ chiếu Việt Nam; pattern thẻ chạy trước CCCD và SĐT để chuỗi 16 số không bị pattern khác cắt vụn.
- **Cách kiểm chứng kết quả:** 32 tests pass, gồm test mới trong `tests/test_pii.py` và `tests/test_correlation_middleware.py` (sinh/nhận/thay ID, header phản hồi, log đủ context, 2 request có 2 ID khác nhau, không lộ email). Sau khi đổi tên log baseline thành `data/logs.baseline.jsonl` và chạy lại `load_test.py --concurrency 5`, `validate_logs.py` đạt **100/100** với 0 PII leak ([output](evidence/02-log-validator.txt)). Hai request thử `req-0000cafe` (email, SĐT giả) và `req-0000f00d` (thẻ, CCCD, hộ chiếu giả) được ghi thành `[REDACTED_EMAIL]`, `[REDACTED_PHONE_VN]`, `[REDACTED_CREDIT_CARD]`, `[REDACTED_CCCD]`, `[REDACTED_PASSPORT_VN]` ([ảnh](evidence/05-pii-redaction.png), [log](evidence/05-pii-redaction.txt)). Structured log đầy đủ của request `req-9924b043`: [ảnh](evidence/04-structured-log.png), [log](evidence/04-structured-log.txt).

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** app dùng key của project cá nhân trong `.env` (không commit). Mỗi trace có metadata `correlation_id` trùng với `correlation_id` trong `data/logs.jsonl` và header `x-request-id` do chính tôi gửi hoặc nhận, ví dụ `req-de34fe49`, `req-0e602120`.
- **Cấu trúc root/retrieval/generation observations:** ([trace list](evidence/06-trace-list.png), [waterfall](evidence/07-trace-waterfall.png)) `lab-agent-run` (type `agent`, root, `@observe` trên `LabAgent.run`) có hai con: `retrieval` (type `retriever`, metadata `doc_count`, `query_preview` đã scrub) và `llm-generate` (type `generation`, `model=claude-sonnet-4-5`, `prompt` là managed prompt từ Langfuse, `usage_details` input/output, `cost_details` input/output/total theo giá $3/$15 mỗi 1M token, metadata `ttft_ms`). Cả hai child dùng `capture_input=False` để prompt đã compile (chứa câu hỏi thô) không bị gửi lên Langfuse; output chỉ gửi bản `summarize_text` đã scrub. Đã kiểm tra qua Langfuse API: ví dụ trace `f3d665c2…` có `retrieval` và `llm-generate` với `parentObservationId` là root, usage 28/178 token, cost $0.002754. Test mới trong `tests/test_agent_prompt_trace.py` kiểm tra generation nhận đủ model, prompt, usage và cost.
- **Cách nối trace với log:** middleware truyền `correlation_id` vào `LabAgent.run`; `propagate_attributes(metadata={"correlation_id": ...})` gắn nó vào mọi observation của trace. Từ một dòng log, lọc trace trên Langfuse theo metadata `correlation_id`; `user_id` trên trace là `user_id_hash`, giống field trong log. Ví dụ: [log của `req-0000b005`](evidence/08-log-req-0000b005.jsonl) ↔ trace `23dc6619dd19a93f529983277e2adc0a` có metadata `correlation_id=req-0000b005`, `user 2a2006df8771` ([metadata](evidence/08-trace-metadata.png), [export từ API](evidence/08-trace-metadata.json), [generation không lưu input thô](evidence/08b-trace-generation-no-input.png)). Ảnh metadata trên Langfuse UI hiện prompt name/label/version/source của observation; `correlation_id` được propagate ở cấp trace nên được chứng minh bằng bản export từ Langfuse API (`GET /api/public/v2/observations`), trong đó cả 3 observation đều có `correlation_id=req-0000b005`. Public key trong ảnh đã được che.
- **Prompt name:** `day13-chat` (text prompt trong project Langfuse cá nhân; [v1](evidence/09a-prompt-v1-baseline.png), [v2](evidence/09b-prompt-v2-candidate.png))
- **Version/label baseline:** version 1, labels `production` + `baseline`; nội dung `Feature={{feature}} / Docs={{docs}} / Question={{message}}`
- **Version/label candidate:** version 2, label `candidate`; thêm dòng `Answer in at most 3 sentences.` (prompt dài hơn nên `tokens_in` tăng từ 33 lên 41 với cùng input)
- **Trace ID của mỗi version:** cùng input `Explain monitoring`, chạy server với `LANGFUSE_PROMPT_LABEL=baseline` rồi `candidate`:
  - baseline → `req-0000baa1` → trace `ac1ff9d3680100ca422783abf584ff82`: `prompt_source=langfuse`, `prompt_label=baseline`, `prompt_version=1`, generation liên kết prompt `day13-chat` v1, usage 33/125
  - candidate → `req-0000ca02` → trace `bfb5644a8ba8f61e9783ac9ba4f99fee`: `prompt_source=langfuse`, `prompt_label=candidate`, `prompt_version=2`, generation liên kết prompt `day13-chat` v2, usage 41/139
- **Cách promote và rollback `production`:** app giữ `LANGFUSE_PROMPT_LABEL=production`, nên chỉ cần chuyển label trên Langfuse, không cần sửa code hay restart.
  - **Promote** (≈ 08:40 UTC): gắn `production` cho v2, label tự rời khỏi v1 ([ảnh](evidence/10a-prompt-promote-v2.png)). Request `req-b2ad70f3` → trace `0504fc38379cf148b949495228420dd6` và `req-a002c164` → trace `88c0664ffe0627b896b85780b7460b55` đều có `prompt_label=production`, `prompt_version=2` (`tokens_in` 41).
  - **Rollback** (08:43:25 UTC): gắn lại `production` cho v1 ([ảnh](evidence/10b-prompt-rollback-v1.png)). Request `req-0000b005` → trace `23dc6619dd19a93f529983277e2adc0a` và `req-0000b006` → trace `7070f76c0e103b2f0fb20234f6089c10` quay về `prompt_version=1` (`tokens_in` 33).
  - **Độ trễ khi đổi label:** 4 request `req-0000b001`–`b004` (08:44:20–08:45:15) vẫn dùng v2 dù API Langfuse đã trả `production -> 1`. SDK cache prompt 60 s (`cache_ttl_seconds=60`); khi cache hết hạn nó vẫn trả bản cũ và làm mới ở chế độ nền (stale-while-revalidate). Trong sự cố thật, rollback prompt cần tính thêm khoảng 1–2 phút trước khi mọi request nhận version mới; muốn nhanh hơn thì giảm TTL hoặc restart service.

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** [`scripts/build_dashboard.py`](../scripts/build_dashboard.py) đọc `data/logs.jsonl` và lấy panel, đơn vị, threshold, time range 60 phút từ [`config/dashboard.yaml`](../config/dashboard.yaml), rồi xuất PNG 2×3: (1) latency P50/P95/P99 + TTFT P95, line SLO 3000 ms; (2) traffic request/phút, line ≥ 1; (3) error rate % + retrieval success % + breakdown `error_type`, line 2%; (4) cost theo phút + lũy kế, line budget $2.5; (5) tokens in/out lũy kế, line 50,000; (6) quality mean, line 0.75. Contract và dashboard dùng cùng file YAML nên threshold không bị lệch. [Ảnh runtime](evidence/11-dashboard-overview.png) (60 phút, 14:52–15:52, 69 request) cho thấy dashboard phản ứng đúng với incident practice: `rag_slow` lúc 15:06–15:13 đẩy P95 lên 4–8 s, vượt đường SLO 3000 ms; `tool_fail` lúc 15:07 làm error rate lên ~31% (`RuntimeError`) và retrieval success xuống ~70%, dưới guardrail 90%; cost, tokens và quality vẫn trong ngưỡng. Sau khi tạo prompt trên Langfuse (~15:40), P95 giảm còn ~160 ms vì không còn timeout 2 s khi fetch prompt.
- **SLO và lý do chọn:** giữ SLO `fast_successful_requests` là 99.5% request trả `response_sent` với latency ≤ 3000 ms trong 28 ngày ([`config/slo.yaml`](../config/slo.yaml)). Baseline P95 3305 ms chủ yếu do timeout fetch prompt khi prompt chưa tồn tại; phần xử lý thật chỉ khoảng 150–200 ms, TTFT P95 55 ms. Ngưỡng 3000 ms vẫn còn khoảng dư cho network và Langfuse, nhưng bắt được `rag_slow` (+2.5 s). Chọn 99.5% thay vì 99.9% vì app phụ thuộc Langfuse Cloud bên ngoài.
- **Cách tính error budget:** budget = 100% − 99.5% = 0.5% số request. Ở 1 request/phút, 28 ngày có 40,320 request, nên được phép tối đa khoảng 201 request lỗi hoặc chậm hơn 3 s. Burn rate = tỷ lệ bad hiện tại / 0.5%: burn 14.4 trong 1 giờ (P1) tiêu khoảng 2% budget, burn 6 trong 6 giờ là P2.
- **Ba alert và runbook tương ứng:** ([`config/alert_rules.yaml`](../config/alert_rules.yaml), [`docs/alerts.md`](../docs/alerts.md)) (1) `high_latency_p95`: P95 > 3000 ms trong 5m, P2; (2) `high_error_rate`: error rate > 2% trong 5m, P1; (3) `cost_budget_burn`: cost 1 giờ > $0.21 (gấp 2 lần budget ngày $2.5/24) trong 15m, P2. Cả ba gửi Slack `#day13-l3a-oncall`, runbook đi theo thứ tự dashboard → lọc log lấy `correlation_id` → trace → mitigation.

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1` (cohort K4, seed 1311, `affected_feature=monitoring`, `latency_threshold_ms=2000`). File tải từ release `Challenge` của repo đề bài, lưu nguyên văn tại `config/challenge.json` (đã `.gitignore`, không commit).
- **Khoảng thời gian điều tra:** 2026-09-29 09:06:36–09:06:52 UTC (16:06:36–16:06:52 giờ Việt Nam). Trước sự cố: 10 request `qa`/`summary` lúc 09:06:36–09:06:38. Chạy `inject_incident.py` lúc 09:06:38, rồi `load_test.py --challenge --concurrency 5` lúc 09:06:38–09:06:51. Mitigation lúc 09:09:57, xác nhận hồi phục lúc 09:11:46.
- **Triệu chứng từ metrics:** ([ảnh](evidence/12-incident-metric.png), vẽ bằng `scripts/incident_view.py`) `response_sent.latency_ms` của feature `monitoring` tăng lên P95 **2667 ms**, 5/5 request vượt ngưỡng challenge 2000 ms; ngay trước đó `qa`/`summary` có P95 161 ms. **TTFT P95 không đổi (55 ms)**, error rate 0%, retrieval success 100%, tokens/cost/quality bình thường. Kết luận từ metrics: request chậm nhưng không lỗi, và phần chậm nằm trước bước LLM. Phía client, request chậm tới 8–13 s vì 5 request bị xử lý tuần tự (endpoint `async def chat` gọi `agent.run` đồng bộ nên chặn event loop), mỗi request hoàn thành cách nhau ~2.67 s.
- **Log line và correlation ID liên quan:** `req-743e0bb0` ([log](evidence/13-incident-log.jsonl), [ảnh](evidence/13-incident-log.png)): `request_received` lúc 09:06:38.268 với `feature=monitoring`, `session_id=k4-l3a-challenge-s05`, `message_preview="Describe how to prove a slow span is the root cause."`; `response_sent` lúc 09:06:40.936 với `latency_ms=2667`, `ttft_ms=55`, `tool_name=retrieval`, `tool_success=true`. 4 request challenge còn lại (`req-82f0de71`, `req-9cb20d78`, `req-167f9864`, `req-34175fda`) có cùng mẫu 2660–2665 ms.
- **Trace ID và span gây ảnh hưởng:** trace `e043ea7a2d538997b123863522720cf5` có metadata `correlation_id=req-743e0bb0` ([export](evidence/14-incident-trace.json), [ảnh](evidence/14-incident-trace.png)). `lab-agent-run` 2.668 s = span con **`retrieval` 2.506 s** (09:06:38.268 → 09:06:40.774, ~94%) + `llm-generate` 0.162 s (bình thường). Trước sự cố, `retrieval` ~0–1 ms. Cả 5 trace challenge đều có `retrieval` 2.502–2.506 s.
- **Root cause:** bước RAG retrieval (vector store) chậm thêm ~2.5 s cho mỗi request (incident `rag_slow`: `app/mock_rag.py` ngủ 2.5 s trước khi trả docs). Retrieval vẫn thành công nên không sinh lỗi, chỉ làm tăng latency; LLM, prompt và token đều bình thường. Metric (latency tăng, TTFT không đổi), log (`latency_ms` 2667, `ttft_ms` 55, `tool_success=true`) và trace (span `retrieval` 2.5 s) cùng chỉ về retrieval.
- **Fix action:** mitigation tức thời là tắt nguồn gây chậm (`python scripts/inject_incident.py --disable` lúc 09:09:57, tương đương rollback hoặc failover vector store). Xác nhận: chạy lại 5 query challenge lúc 09:11:46, cả 5 xong trong ~0.8 s phía client, `retrieval` về ~0 ms. Lần chạy lại đầu tiên lúc 09:09:58 còn 3 request 3.5–5.3 s, nhưng trace cho thấy `retrieval` đã ~0 ms; thời gian nằm ở bước fetch prompt từ Langfuse (2 request `prompt_source=local-fallback`), là vấn đề riêng do Langfuse Cloud phản hồi chậm lúc đó, không phải incident.
- **Preventive measure:**
  1. **Timeout + fallback cho retrieval:** đặt timeout ~500 ms cho vector store; quá hạn thì trả lời với context rỗng hoặc cache (có flag `degraded`) thay vì chờ 2.5 s.
  2. **Alert theo ngưỡng thật và theo span:** `high_latency_p95` hiện đặt ở 3000 ms nên **không bắt được** sự cố này (P95 2667 ms). Cần thêm alert P95 `latency_ms` > 2000 ms theo từng `feature` trong 5 phút, và alert trên latency của span `retrieval` (ví dụ P95 > 500 ms), vì TTFT bình thường + latency cao là dấu hiệu retrieval chậm.
  3. **Thêm span cho prompt fetch:** bước `resolve_prompt` chưa có observation riêng nên khi Langfuse chậm, thời gian chỉ hiện là khoảng trống trong `lab-agent-run`; thêm span giúp khoanh vùng ngay.
  4. **Không chặn event loop:** chạy `agent.run` trong threadpool (hoặc đổi endpoint thành `def`) để một dependency chậm không làm các request khác xếp hàng (client thấy 8–13 s thay vì 2.7 s).

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:**
  Mỗi câu hỏi gửi vào chatbot đi qua hai bước: **tìm tài liệu liên quan** (retrieval), rồi **nhờ AI viết câu trả lời** (generation). Ban đầu hệ thống chỉ ghi lại tổng thời gian của cả câu hỏi, giống như chỉ biết "đơn hàng giao mất 3 ngày" mà không biết chậm ở kho hay ở khâu vận chuyển. Tôi quyết định ghi lại **riêng từng bước**, mỗi bước có thời gian, số token và chi phí. Nhờ vậy, khi hệ thống chậm có thể chỉ ra ngay bước nào có lỗi.
  Tôi cũng chủ động **không gửi nguyên văn câu hỏi của người dùng** lên công cụ theo dõi (Langfuse), vì câu hỏi có thể chứa email, số điện thoại hay số thẻ. Công cụ chỉ nhận các con số (thời gian, token, chi phí) và một bản tóm tắt đã che thông tin cá nhân.
  *(Kỹ thuật: dùng `@observe(as_type="retriever"/"generation", capture_input=False)`, giữ được các test có sẵn.)*

- **Một lỗi/blocker đã gặp:**
  1. **Hệ thống chậm dù phần AI rất nhanh.** Lúc bắt đầu, mỗi câu trả lời mất khoảng 2–3 giây (P95 3305 ms), vượt mục tiêu 3 giây, trong khi phần AI giả lập chỉ mất khoảng 0,15 giây.
  2. **Đổi prompt nhưng hệ thống không đổi theo ngay.** Khi chuyển prompt đang dùng từ bản 2 về bản 1 (rollback), trong gần 2 phút sau đó hệ thống vẫn dùng bản 2.

- **Cách tìm nguyên nhân và xử lý:**
  1. Xem chi tiết một request thì thấy mỗi lần trả lời, hệ thống đều hỏi Langfuse "prompt đang dùng là bản nào", nhưng prompt đó **chưa được tạo**, nên nó chờ hết 2 giây rồi mới dùng bản dự phòng. Giống như gọi điện cho một số không có người nghe, chờ hết chuông mới tự xử lý. **Cách xử lý:** tạo prompt trên Langfuse. Thời gian trả lời giảm từ khoảng 3 giây xuống **0,16 giây**.
  2. Kiểm tra trên Langfuse thì prompt đã đổi về bản 1 ngay lập tức, nên vấn đề nằm ở phía ứng dụng. Ứng dụng **nhớ tạm (cache) prompt trong 60 giây** để khỏi phải hỏi lại liên tục; khi hết hạn nó vẫn dùng bản cũ thêm một lượt trong lúc lấy bản mới. **Bài học:** khi cần quay về prompt cũ gấp, phải tính thêm 1–2 phút chờ, hoặc khởi động lại ứng dụng để có hiệu lực ngay.

- **Cách hiểu luồng Metrics → Logs → Traces:**
  Có thể hình dung như khám bệnh:
  - **Metrics (chỉ số tổng)** giống **đo nhiệt độ**: biết là đang sốt và sốt từ lúc nào, nhưng chưa biết vì sao.
  - **Logs (nhật ký từng request)** giống **hồ sơ từng lần khám**: tìm đúng những lần khám có vấn đề. Mỗi request có một mã riêng (`correlation_id`) để tra cứu.
  - **Traces (chi tiết từng bước)** giống **chụp X-quang**: thấy chính xác bộ phận nào có vấn đề.

  **Áp dụng vào sự cố challenge:**
  - **Metrics:** các câu hỏi thuộc nhóm "monitoring" chậm lên khoảng **2,7 giây** (bình thường 0,16 giây), vượt ngưỡng 2 giây. Tốc độ bắt đầu trả lời của AI vẫn bình thường, nên nghi là phần chậm nằm trước bước AI.
  - **Logs:** request `req-743e0bb0` mất 2667 ms, không báo lỗi.
  - **Traces:** trace của chính request đó cho thấy bước **tìm tài liệu mất 2,5 giây**, chiếm khoảng 94% tổng thời gian, còn bước AI chỉ 0,16 giây.

  **Kết luận:** kho tài liệu (vector store) phản hồi chậm. Chỉ kết luận khi cả ba nguồn cùng chỉ về một nguyên nhân.

- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:**
  - **Prompt version:** prompt là "lời dặn" gửi cho AI. Đánh số phiên bản giống lưu các bản nháp của một văn bản: biết mỗi câu trả lời dùng bản nào, so sánh được hai bản với cùng một câu hỏi (bản 2 dài hơn một dòng nên tốn thêm khoảng 8 token mỗi lần), và **quay lại bản cũ chỉ bằng một cú bấm**, không cần sửa code.
  - **Token/cost:** AI tính tiền theo lượng chữ đọc vào và viết ra (token). Theo dõi theo từng câu hỏi giúp phát hiện sớm khi prompt hoặc câu trả lời dài bất thường làm chi phí tăng vọt.
  - **SLO:** một **cam kết chất lượng đo được**, ví dụ "99,5% câu hỏi được trả lời trong vòng 3 giây". Phần 0,5% còn lại là **"hạn mức được phép lỗi" (error budget)**: nếu 1 phút có 1 câu hỏi thì 28 ngày được phép tối đa khoảng 201 câu chậm hoặc lỗi. Challenge cho thấy ngưỡng cảnh báo phải sát với yêu cầu thật: cảnh báo đặt ở 3 giây sẽ **bỏ lỡ** sự cố 2,7 giây, trong khi yêu cầu của challenge là 2 giây.

- **Điều quan trọng nhất đã học:**
  Hệ thống phải được **"lắp camera" trước khi có sự cố**: mỗi request có mã tra cứu riêng, từng bước được ghi lại, và thông tin cá nhân được che trước khi lưu. Khi sự cố xảy ra, nhờ những thứ đã chuẩn bị sẵn này, tôi tìm ra nguyên nhân trong vài phút thay vì phải đoán.

- **Hạn chế hoặc phần chưa hoàn thành, nếu có:**
  1. **Dashboard là ảnh chụp tĩnh:** phải chạy lệnh để vẽ lại, chưa tự cập nhật mỗi 30 giây.
  2. **Bước "hỏi Langfuse lấy prompt" chưa được ghi riêng:** khi Langfuse chậm, trên trace chỉ thấy một khoảng trống, chưa gọi đúng tên bước.
  3. **Các request bị xếp hàng chờ nhau:** khi 5 câu hỏi đến cùng lúc, ứng dụng xử lý lần lượt từng câu, nên người dùng cuối phải chờ 8–13 giây thay vì 2,7 giây. Đây là thiết kế có sẵn của code mẫu, tôi chưa sửa.
  4. **Cảnh báo chưa được chỉnh theo bài học từ challenge:** chưa thêm cảnh báo 2 giây cho từng nhóm câu hỏi và cảnh báo riêng khi bước tìm tài liệu chậm.
  5. **Ảnh trên giao diện Langfuse không hiện mã `correlation_id`:** phần nối trace với log được chứng minh bằng dữ liệu xuất từ API của Langfuse.

## 9. Checklist trước khi nộp

- [ ] Kết quả và evidence thuộc commit SHA cuối.
- [ ] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [ ] Incident evidence nối đúng metric → log → trace.
- [ ] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [ ] Repository chạy lại được theo README.
- [ ] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs.
