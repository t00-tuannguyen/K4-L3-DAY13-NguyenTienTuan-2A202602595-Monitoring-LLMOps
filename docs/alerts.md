# Alert và Runbook

Mỗi alert dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ. Rule nằm tại [`config/alert_rules.yaml`](../config/alert_rules.yaml), SLO tại [`config/slo.yaml`](../config/slo.yaml).

Quy trình chung cho mọi alert: **Metrics → Logs → Traces**. Mở dashboard để xác định khoảng thời gian, lọc `data/logs.jsonl` lấy `correlation_id`, rồi tìm trace trên Langfuse có metadata `correlation_id` giống vậy.

## Alert 1: high_latency_p95

- Tên: `high_latency_p95`
- Severity: P2
- Duration: 5m
- Kênh thông báo: Slack `#day13-l3a-oncall`
- SLI/SLO liên quan: `fast_successful_requests`, tức 99.5% request có `response_sent` với `latency_ms <= 3000` trong 28 ngày
- Điều kiện và thời gian duy trì: P95 của `response_sent.latency_ms` > 3000 ms liên tục 5 phút
- Ảnh hưởng tới người dùng: câu trả lời chậm hơn 3 s và error budget của SLO đang bị tiêu
- Ba bước kiểm tra đầu tiên:
  1. Dashboard panel **Latency**: P95 tăng từ lúc nào, P50 có tăng theo không (chậm toàn bộ hay chỉ tail), TTFT P95 có đổi không (TTFT bình thường mà latency cao thì phần chậm nằm trước hoặc sau LLM).
  2. Lấy các request chậm nhất trong khoảng đó:
     `python -c "import json;[print(r['correlation_id'],r['latency_ms']) for r in map(json.loads,open('data/logs.jsonl')) if r.get('event')=='response_sent' and r['latency_ms']>3000]"`
  3. Mở trace trên Langfuse theo `correlation_id`, so sánh thời gian của span `retrieval`, `llm-generate` và phần còn lại của `lab-agent-run`. Kiểm tra thêm metadata `prompt_source`: nếu là `local-fallback` thì Langfuse prompt fetch đang timeout (2 s).
- Mitigation tạm thời:
  - Nếu `retrieval` chậm: tắt hoặc bỏ qua retrieval và trả lời bằng fallback, giảm timeout của vector store.
  - Nếu prompt fetch fallback: kiểm tra prompt `day13-chat` và label còn tồn tại, key Langfuse còn hợp lệ.
  - Nếu `llm-generate` chậm: chuyển sang model nhỏ hơn hoặc giảm `max_tokens`.
- Owner: nguyentientuan (on-call LLMOps)

## Alert 2: high_error_rate

- Tên: `high_error_rate`
- Severity: P1
- Duration: 5m
- Kênh thông báo: Slack `#day13-l3a-oncall`
- SLI/SLO liên quan: `fast_successful_requests` và guardrail `error_rate_pct_max: 2`, `retrieval_success_rate_pct_min: 90`
- Điều kiện và thời gian duy trì: `count(request_failed) / count(request_received)` > 2% liên tục 5 phút
- Ảnh hưởng tới người dùng: người dùng nhận HTTP 500, không có câu trả lời
- Ba bước kiểm tra đầu tiên:
  1. Dashboard panel **Errors**: error rate và breakdown `error_type`; retrieval success giảm cùng lúc thì lỗi nằm ở bước retrieval.
  2. Lọc log lỗi: `grep '"request_failed"' data/logs.jsonl | tail`, đọc `error_type`, `tool_name`, `payload.detail` và lấy `correlation_id`.
  3. Mở trace có cùng `correlation_id`: observation nào có level `ERROR` (ví dụ `retrieval` với `RuntimeError: Vector store timeout`).
- Mitigation tạm thời:
  - Lỗi retrieval: trả lời bằng fallback không có context thay vì trả 500, và bật retry có backoff.
  - Lỗi từ LLM provider: chuyển sang model hoặc provider dự phòng.
  - Rollback deploy hoặc prompt label `production` gần nhất nếu lỗi bắt đầu ngay sau khi thay đổi.
- Owner: nguyentientuan (on-call LLMOps)

## Alert 3: cost_budget_burn

- Tên: `cost_budget_burn`
- Severity: P2
- Duration: 15m
- Kênh thông báo: Slack `#day13-l3a-oncall`
- SLI/SLO liên quan: guardrail `daily_cost_usd_max: 2.5` (≈ 0.104 USD/giờ); alert khi tốc độ tiêu gấp 2 lần, tức > 0.21 USD/giờ
- Điều kiện và thời gian duy trì: `sum(response_sent.cost_usd)` trong cửa sổ 1 giờ > 0.21 USD, duy trì 15 phút
- Ảnh hưởng tới người dùng: chưa ảnh hưởng trực tiếp, nhưng nếu kéo dài sẽ vượt budget ngày và buộc phải rate-limit hoặc tắt tính năng
- Ba bước kiểm tra đầu tiên:
  1. Dashboard panel **Cost** và **Tokens**: cost tăng do traffic tăng (panel Traffic cũng tăng) hay do mỗi request đắt hơn (`tokens_out` mỗi request tăng).
  2. Lọc log có token cao: `python -c "import json;[print(r['correlation_id'],r['tokens_in'],r['tokens_out'],r['cost_usd']) for r in map(json.loads,open('data/logs.jsonl')) if r.get('event')=='response_sent' and r['tokens_out']>300]"`
  3. Mở trace theo `correlation_id`, xem `usage_details`/`cost_details` của `llm-generate` và `prompt_version`: prompt version mới có làm câu trả lời dài hơn không.
- Mitigation tạm thời:
  - Đặt `max_tokens` cho output.
  - Rollback label `production` về prompt version trước nếu version mới gây tăng output.
  - Rate-limit theo `user_id_hash` nếu một user gây phần lớn traffic.
- Owner: nguyentientuan (on-call LLMOps)
