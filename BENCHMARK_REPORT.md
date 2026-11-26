# Benchmark & Observability Report — Day 14

> Copy file này thành `BENCHMARK_REPORT.md` trong repo của bạn và điền đầy đủ.
> Mọi con số phải lấy từ report JSON / CSV / screenshot thật, không ước lượng.

**Họ tên:** Hoàng Quang Đạt — 2A2020603808  
**Ngày chạy:** 2026-11-26  
**Môi trường:** Windows 11, Python 3.14.7, Docker Desktop 29.8.0 (WSL2)

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | ≤ 500 ms | 95% người dùng nhận phản hồi trong nửa giây (trải nghiệm chat mượt mà), bỏ qua ~3% tail latency |
| Error rate `/ask` | ≤ 2.0 % | Cho phép error budget 2% để chịu được lỗi upstream mock LLM ngẫu nhiên (1%) mà không báo động giả |
| Accuracy trên golden dataset | ≥ 80 % | Đảm bảo agent v2 trả lời chính xác phần lớn câu hỏi trọng tâm; ở bản fix cuối nâng gate lên 100% không regression |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.60 | 190.4 | 218.9 | 1667.6 | 0.67% | ✅ PASS |
| 10 | 37.61 | 192.5 | 446.3 | 1702.1 | 1.00% | ✅ PASS |
| 50 | 99.87 | 203.1 | 503.8 | 1700.3 | 1.00% | ❌ FAIL (p95 > 500ms) |
| 100 | 38.97 | 634.3 | 4869.1 | 5629.2 | 1.00% | ❌ FAIL (p95 > 500ms) |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

Không tăng tuyến tính mãi: từ `c=1` → `10` → `50`, RPS tăng mạnh (`4.60` → `37.61` → `99.87 req/s`) nhờ xử lý bất đồng bộ (`async/await`). Nhưng đến `c=100`, RPS **tụt xuống `38.97 req/s`** và `p50` nhảy từ `203.1 ms` lên `634.3 ms`, `p95` vọt lên `4869.1 ms` vì 1 worker uvicorn bị bão hoà (saturation) khi hàng đợi request đồng thời quá lớn.

### 2.2 Tail latency

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 205.8 | 432.5 | 464.9 |
| 0.03 (mặc định) | 232.3 | 455.6 | 1695.6 |
| 0.1 | 329.3 | 1687.7 | 1714.5 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

`p99` (và `p95` khi tỉ lệ chậm tăng lên `10%`) nhạy nhất với request chậm: khi `MOCK_SLOW_RATE` tăng từ `0` lên `0.03`, `avg` chỉ tăng nhẹ từ `205.8 ms` lên `232.3 ms` (vẫn tưởng bình thường), nhưng `p99` nhảy vọt gần 4 lần từ `464.9 ms` lên `1695.6 ms`. Vì vậy SLO phải đặt theo `p95`/`p99` để không che giấu trải nghiệm tệ của nhóm người dùng gặp tail latency.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.35% (1/23) | 91.30% (21/23) | 100.0% (23/23) |
| Avg tokens / câu | 56.3 | 109.3 | 113.5 |
| Tổng cost (USD) | $0.000393 | $0.000764 | $0.000789 |
| Cost / câu đúng (USD) | $0.00039255 | $0.00003639 | $0.00003430 |
| Quality gate | FAIL | PASS (≥ 80%) | PASS (≥ 100%, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Thêm entry `(["jwt", "xác thực"], ...)` vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` (và đồng bộ sang `production/utils/mock_llm.py`) giải thích JWT có chữ ký số và thời gian hết hạn |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Thêm entry `(["kubernetes", "hpa", "chỉ số"], ...)` vào `KNOWLEDGE_BASE` mô tả Kubernetes HPA scale theo CPU, memory và custom metrics |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2 (và cách dùng exit code chặn merge trong CI):**

- **Trade-off:** v2 có thêm bước retrieval (~20ms) và nhồi context vào prompt nên `avg_tokens` gần gấp đôi (`113.5` vs `56.3`) và `total_cost` cao hơn v1 (`$0.000789` vs `$0.000393`), `p50` cũng nhỉnh hơn (`200.0 ms` vs `171.4 ms`). Tuy nhiên accuracy tăng từ `4.35%` lên `100.0%`, kéo **cost / câu đúng** giảm hơn 11 lần (`$0.00003430` so với `$0.00039255`).
- **Dùng exit code chặn merge trong CI:** Trong GitHub Actions (hoặc GitLab CI), chạy bước `python eval/run_eval.py --min-accuracy 0.9 --baseline reports/eval_v2.json`. Nếu accuracy thấp hơn ngưỡng hoặc có bất kỳ câu nào bị regression so với baseline, `run_eval.py` trả **exit code khác 0 (`1`)**, khiến job CI fail và chặn không cho merge Pull Request vào `main`.

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (`screenshots/grafana-dashboard.png`)
- [x] Một trace chậm trong Jaeger (`screenshots/jaeger-slow-trace.png`)
- [x] Một trace lỗi trong Jaeger (`screenshots/jaeger-error-trace.png`)
- [x] Trang Alerts của Prometheus với ít nhất 2 alert đang **firing** (`screenshots/prometheus-alert-firing.png`)

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` | ~1 phút 5 giây (scrape + `for: 1m`) | Error Rate (`5xx`) trên Grafana |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` | ~2 phút 10 giây (scrape + `for: 2m`) | Latency `p95` / `p99` trên Grafana |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` (và có thể `AgentHighLatencyP95`) | ~2 phút (`for: 2m`, do giá đắt hơn ~16 lần) | LLM Cost Burn Rate (`$/hour`) |
| D | `docker pause` 1 instance | `AgentInstanceDown` | ~30 giây (`up{job="agent"} == 0`, `for: 30s`) | Up Instances / Target Health |
| E | `AGENT_VERSION=v1` | Không có alert nào | — | Không thấy trên panel hạ tầng |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

`AGENT_VERSION=v1` vẫn trả HTTP `200 OK` nhanh và không lỗi hạ tầng, nên các alert Golden Signals (latency, error rate, `up`) đều im lặng. Để phát hiện sự cố suy giảm chất lượng (quality regression) trên production, cần:
1. Chạy **Eval chất lượng** (`run_eval.py` trên golden dataset) trong CI/CD trước khi deploy để chặn merge khi accuracy giảm.
2. Theo dõi **online quality metrics** (tỉ lệ thumbs-up/down của user, tỉ lệ `retrieved=true` trong log/metric, hoặc LLM-as-a-judge sampling trên traffic thật) và gắn nhãn `agent_version` trên dashboard để phát hiện ngay sau khi rollout.

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất tìm được:

- `trace_id`: `2046a3b500080ef0be6252c8fff04bf2`
- Tổng thời gian: `1668.2 ms`
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (~1645 ms, ~98.6% tổng thời gian; còn `agent.retrieve_context` chỉ mất `23.3 ms`)
- Dòng log tương ứng (grep theo `trace_id`):

```json
{"ts": "2026-11-26T09:19:29.055916+00:00", "level": "INFO", "service": "observable-agent", "instance": "38d54e419cc3", "event": "http_request", "trace_id": "2046a3b500080ef0be6252c8fff04bf2", "span_id": "6dc111076212f8ab", "request_id": "58d5ff228d93", "method": "POST", "route": "/ask", "status": 200, "ms": 1668.2}
```

Trace lỗi (`status: 503`):
- `trace_id`: `3f9de0dab0c3078c84f9484b2b0fabb3` (`109.0 ms`, lỗi upstream mock LLM 503)

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số liệu từ `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv` (dòng `Aggregated` / `POST /ask`):

| Số instance | RPS (Aggregated) | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 63.88 (`POST /ask`: 58.04) | 190 | 530 (`POST /ask`: 800) | 1700 | 55 (0.91%) |
| 3 | 66.26 (`POST /ask`: 60.31) | 190 | 220 (`POST /ask`: 220) | 1700 | 85 (1.07%) |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

Scale từ 1 lên 3 instance **cải thiện rất rõ p95**: p95 của `POST /ask` giảm từ **800 ms xuống còn 220 ms** (giảm gần 4 lần) vì CPU/event loop không còn bị nghẽn hàng đợi khi 100 user gửi đồng thời. Tuy nhiên `p99` vẫn giữ ở **1700 ms** và `Failures` vẫn ~1% vì nút thắt của p99 nằm ở **upstream LLM** (`MOCK_SLOW_RATE=0.03` và `MOCK_ERROR_RATE=0.01`) — việc thêm instance agent không làm LLM trả lời nhanh hơn ở nhóm 3% request chậm.

---

## 6. Kết luận

- 3 điều học được về benchmark & observability:
  1. Không đánh giá hiệu năng bằng `average` latency — phải dùng `p95`/`p99` và load test ở nhiều mức concurrency để thấy điểm bão hoà và tail latency.
  2. Eval trên golden dataset với baseline + exit code giúp chặn regression trước khi merge, và đánh giá hiệu quả bằng `cost / câu đúng` phản ánh đúng giá trị hơn `cost / câu`.
  3. Ba trụ cột Metrics (Prometheus/Grafana) + Traces (OpenTelemetry/Jaeger) + Structured JSON Logs (`trace_id`) liên kết chặt chẽ giúp đi từ triệu chứng ("p95 tăng") tới nguyên nhân gốc ("span nào chậm, log nào lỗi") trong vài giây.
- Nếu đưa agent này lên production thật, sẽ thêm các metric / alert:
  - Alert theo **error budget burn rate** (multi-window) thay vì chỉ ngưỡng tĩnh 1 phút.
  - Metric & alert cho **Redis latency / connection errors**, **rate-limit 429 ratio**, và **token usage theo từng tenant/API key**.
