# Day 14 Lab - Mission Answers

> **Họ tên:** Hoàng Quang Đạt  
> **MSSV:** 2A2020603808  

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns tìm được trong `01-localhost-vs-production/develop/app.py`

1. **Hardcode secrets trong source code (`app.py` dòng 17–18):**
   - `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`.
   - Khi push lên Git, toàn bộ API key và mật khẩu DB bị lộ ngay lập tức. Ở `production/app.py` (dòng 24), cấu hình được đọc từ `config.py` qua biến môi trường.
2. **Không có config management theo môi trường (`app.py` dòng 21–22):**
   - `DEBUG = True`, `MAX_TOKENS = 500` được gán cứng trong code thay vì dùng biến môi trường (12-Factor App).
3. **Dùng `print()` để log và log lộ secret (`app.py` dòng 33–34, 38):**
   - `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` làm lộ API key ra stdout và khó parse khi thu thập log tập trung.
   - `production/app.py` (dòng 28–31, 111–122) dùng `logging` định dạng JSON có cấu trúc và tuyệt đối không log secret.
4. **Không có health check / readiness endpoint (`app.py` chỉ có `/` và `/ask`):**
   - Cloud platform hoặc load balancer không biết app còn sống hay đã sẵn sàng nhận traffic để restart hoặc route request.
   - `production/app.py` có `GET /health` (dòng 135–149) và `GET /ready` (dòng 152–161).
5. **Bind `localhost`, hardcode `port=8000` và bật `reload=True` (`app.py` dòng 49–54):**
   - `host="localhost"` chỉ nhận kết nối từ chính máy đó, không nhận traffic từ ngoài container.
   - `port=8000` cố định không tương thích với nền tảng cloud tự cấp `PORT` qua biến môi trường.
   - `reload=True` gây tốn tài nguyên và không ổn định trên production.
   - `production/app.py` (dòng 194–199) đọc `settings.host` (`0.0.0.0`), `settings.port` (từ `PORT`), và chỉ bật `reload` khi `settings.debug` là `True`.
6. **Không xử lý Graceful Shutdown (`app.py`):**
   - Khi nhận `SIGTERM`, process tắt đột ngột có thể cắt ngang request đang xử lý. `production/app.py` dùng `lifespan` (dòng 39–68) và `signal.signal(signal.SIGTERM, handle_sigterm)` (dòng 189).

### Exercise 1.2: Kết quả chạy bản `develop`

Lệnh test (theo lưu ý K5, gửi `question` qua query parameter):
```bash
curl -i -s -X POST "http://localhost:8000/ask?question=Hello"
```

Kết quả trả về:
```http
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 08:21:49 GMT
server: uvicorn
content-length: 126
content-type: application/json

{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

### Exercise 1.3: Bảng so sánh `develop` vs `production`

| Feature | Develop (`develop/app.py`) | Production (`production/app.py`) | Tại sao quan trọng? |
| --- | --- | --- | --- |
| **Config & Secrets** | Hardcode `OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG`, `MAX_TOKENS` trực tiếp trong code | Đọc từ biến môi trường qua `config.py` (`settings`) | Tránh lộ secret lên Git; dễ đổi cấu hình giữa dev/staging/prod mà không cần sửa code |
| **Health check** | Không có `/health` hay `/ready` | Có `GET /health` (liveness) và `GET /ready` (readiness, trả 503 khi chưa sẵn sàng) | Giúp platform/Docker/LB tự phát hiện app treo để restart hoặc ngừng đẩy traffic vào instance chưa sẵn sàng |
| **Logging** | Dùng `print(...)`, có in cả `OPENAI_API_KEY` | Structured JSON logging (`logging` + `json.dumps`), không log secret | Log aggregator (Loki, Datadog...) parse và lọc được dễ dàng, đảm bảo an toàn thông tin nhạy cảm |
| **Shutdown** | Tắt đột ngột, không bắt signal | Dùng FastAPI `lifespan` + bắt `SIGTERM` để hoàn tất request đang chạy | Tránh mất request hoặc lỗi 502 cho người dùng khi deploy/restart container |
| **Network & Debug** | `host="localhost"`, `port=8000`, `reload=True` | `host="0.0.0.0"`, `port` từ env `PORT`, `reload=settings.debug` | `0.0.0.0` mới nhận được kết nối từ ngoài container; cloud platform cấp port động qua `PORT` |

---


## Part 2: Docker

### Exercise 2.1: Câu hỏi về `02-docker/develop/Dockerfile`

1. **Base image là gì?** `python:3.11` (bản full Python distribution, dung lượng lớn).
2. **Working directory là gì?** `/app` (`WORKDIR /app`).
3. **Tại sao `COPY requirements.txt` phải đứng trước `COPY . .` / `COPY app.py`?**
   - Để tận dụng **Docker layer cache**. `requirements.txt` ít thay đổi hơn source code; nếu đặt `COPY requirements.txt` và `RUN pip install` trước, khi chỉ sửa `app.py` thì Docker dùng lại cache của bước cài thư viện thay vì phải `pip install` lại từ đầu.
4. **CMD vs ENTRYPOINT khác nhau thế nào?**
   - `ENTRYPOINT` định nghĩa lệnh chính luôn được thực thi khi container khởi chạy (khó bị ghi đè nếu không truyền `--entrypoint`).
   - `CMD` cung cấp lệnh hoặc tham số mặc định cho `ENTRYPOINT`, và dễ dàng bị ghi đè khi truyền thêm tham số vào `docker run <image> <command>`.

### Exercise 2.2: Kết quả chạy container `my-agent:develop`

Lệnh test (theo lưu ý K5, gửi `question` qua query):
```bash
curl -i -s -X POST "http://localhost:8000/ask?question=What+is+Docker?"
```

Kết quả:
```http
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 08:23:49 GMT
server: uvicorn
content-length: 103
content-type: application/json

{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

### Exercise 2.3: So sánh kích thước image (Multi-stage build)

Đo bằng `docker images my-agent` sau khi build từ gốc repo:
- **Develop (`my-agent:develop`):** `1.67GB` (~`1,670 MB`)
- **Production (`my-agent:advanced`):** `240MB`
- **Chênh lệch:** Giảm khoảng **`85.6%`** (`1,430 MB`)
- **Giải thích:**
  - **Stage 1 (`builder`):** dùng `python:3.11-slim`, cài `gcc`, `libpq-dev` và `pip install --user` các package vào `/root/.local`.
  - **Stage 2 (`runtime`):** khởi tạo từ `python:3.11-slim` sạch, chỉ `COPY --from=builder` thư mục `/root/.local` (các package đã biên dịch) và source code, chạy dưới non-root user `appuser`. Không mang theo `gcc`, `libpq-dev`, apt cache hay base image `python:3.11` nặng nề nên dung lượng giảm mạnh.

### Exercise 2.4: Docker Compose stack

Sơ đồ kiến trúc các service trong `02-docker/production/docker-compose.yml` (cùng nằm trong network `internal`):
```text
Client (localhost:80)
   │
   ▼
[ nginx ] (ports 80:80, 443:443 — Reverse Proxy / Load Balancer)
   │
   ▼
[ agent ] (port 8000 internal, phụ thuộc redis & qdrant healthy)
   ├──▶ [ redis ]  (redis:7-alpine, port 6379 — Cache & Rate limiting)
   └──▶ [ qdrant ] (qdrant/qdrant:v1.9.0, port 6333 — Vector DB)
```

Kết quả test qua Nginx:
- `GET http://localhost/health` → `200 OK`:
  `{"status":"ok","uptime_seconds":7.1,"version":"2.0.0","timestamp":"2026-11-26T08:24:23.244936"}`
- `POST http://localhost/ask` (JSON `{"question":"Explain microservices"}`) → `200 OK`:
  `{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}`

---

## Part 4: API Security

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop`)

Chạy server với `AGENT_API_KEY=secret-key-123 python app.py`:

1. **Không có API key → `401 Unauthorized`:**
```http
HTTP/1.1 401 Unauthorized
date: Thu, 26 Nov 2026 08:25:55 GMT
server: uvicorn
content-length: 67
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```

2. **Có `X-API-Key: secret-key-123` → `200 OK`:**
```http
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 08:25:55 GMT
server: uvicorn
content-length: 122
content-type: application/json

{"question":"hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

### Exercise 4.2 & 4.3: JWT Auth & Rate Limiting (`04-api-gateway/production`)

- Lấy token từ `POST /auth/token` với tài khoản `student` / `demo123` (giới hạn 10 request/phút): `Authorization: Bearer eyJhbGciOiJIUzI...` (đã che token).
- Chạy vòng lặp 12 request liên tiếp tới `POST /ask`:
  - Request 1 → 10: `200 OK`
  - Request 11 → 12: `429 Too Many Requests`

**Output `curl -i` request #1 (`200 OK`):**
```http
HTTP/1.1 200 OK
date: Thu, 26 Nov 2026 08:26:14 GMT
server: uvicorn
content-length: 177
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"test","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","usage":{"requests_remaining":9,"budget_remaining_usd":1.6e-05}}
```

**Output `curl -i` request #11 (`429 Too Many Requests`):**
```http
HTTP/1.1 429 Too Many Requests
date: Thu, 26 Nov 2026 08:26:17 GMT
server: uvicorn
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795681637
retry-after: 57
content-length: 98
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":57}}
```

### Exercise 4.4: Cách làm Cost Guard & Vì sao cần cả Rate Limit và Cost Guard

- **Cách hoạt động (`cost_guard.py`):**
  1. **Trước khi gọi LLM (`check_budget`):** Kiểm tra tổng chi phí toàn hệ thống (`global_daily_budget_usd`) — nếu vượt trả `503`; sau đó kiểm tra chi phí trong ngày của user (`daily_budget_usd`) — nếu vượt trả **`402 Payment Required`**. Khi đạt ngưỡng cảnh báo (ví dụ 80%), ghi log `WARNING`.
  2. **Sau khi gọi LLM (`record_usage`):** Tính chi phí thực tế từ số `input_tokens` và `output_tokens` theo đơn giá model rồi cộng dồn vào usage của user và global trong ngày (trong production lưu trên Redis để stateless giữa các instance).
- **Vì sao cần cả hai:**
  - **Rate Limit** bảo vệ **tốc độ** (số request/phút), chống spam/DDoS làm quá tải server.
  - **Cost Guard** bảo vệ **tiền** (ngân sách USD theo token), vì một user vẫn có thể gửi ít request (dưới rate limit) nhưng mỗi request có prompt/output rất dài gây tốn nhiều tiền LLM.

---

## Part 5: Scaling & Reliability

### Exercise 5.1–5.5: Health Check, Graceful Shutdown & Stateless Scaling (`05-scaling-reliability/`)

1. **Phân biệt Liveness (`/health`) và Readiness (`/ready`):**
   - **`/health` (Liveness probe):** Kiểm tra process của agent còn sống hay không (không bị treo/deadlock). Luôn trả `200` khi process còn chạy, kể cả khi Redis/DB tạm thời mất kết nối (tránh platform restart container liên tục một cách vô ích).
   - **`/ready` (Readiness probe):** Kiểm tra agent đã sẵn sàng nhận traffic chưa (đã khởi tạo xong và kết nối được tới Redis/dependencies). Trả `503` khi mất kết nối Redis để Load Balancer tạm ngừng đẩy request mới vào instance đó.

2. **Vì sao state trong RAM bị hỏng khi chạy nhiều instance (và giải pháp Stateless + Redis):**
   - Khi scale lên 3 instance sau Load Balancer (Nginx), các request trong cùng một phiên chat được điều phối sang các container khác nhau (round-robin). Nếu lịch sử hội thoại, rate limit hay cost counter lưu trong RAM cục bộ của từng container, instance B sẽ không thấy dữ liệu của instance A → mất lịch sử chat, sai rate limit và sai tổng chi phí.
   - **Giải pháp:** Thiết kế agent **stateless**, đẩy toàn bộ shared state (session history, rate limit, cost guard) vào **Redis** dùng chung.

3. **Kết quả chạy `05-scaling-reliability/production/` với `--scale agent=3` (`POST /chat` qua cổng `8080`):**
   - Chạy `docker compose -p k5-day14-scaling up -d --build --scale agent=3` và `python test_stateless.py`:
     - 5 request trong cùng session `bb79b943-b04c-48c9-ada1-07e99e8ea7ee` được phục vụ luân phiên bởi cả 3 instance: `{'instance-8aeb9d', 'instance-9e1440', 'instance-c8704b'}`.
     - Khi gọi `GET /chat/{session_id}/history`, Redis trả về đầy đủ **10 messages** (5 câu hỏi + 5 câu trả lời), chứng minh session được giữ nguyên vẹn dù request đi qua các instance khác nhau.

---

## Part 3: Cloud Deployment

### Exercise 3.1 / 3.2: Deploy `06-lab-complete/` lên Cloud (Render)
- **Public URL:** `https://k5-l3b-day14-hoangquangdat-2a2020603808.onrender.com`
- **Nền tảng:** Render (Web Service Docker + Render Key Value Redis)
- **Kết quả 4 lệnh tự kiểm CP6:**
  - `GET /health` → `200`
  - `GET /ready` → `200` (`{"ready":true}`)
  - `POST /ask` (không có `X-API-Key`) → `401`
  - `POST /ask` (có `X-API-Key`) → `200`
- **Screenshots:** `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png`

### So sánh `railway.toml` vs `render.yaml`

| Tiêu chí | `railway.toml` (Railway) | `render.yaml` (Render Blueprint) |
| --- | --- | --- |
| **Định dạng & phạm vi** | TOML, cấu hình cho **1 service** trong thư mục deploy | YAML (Infrastructure-as-Code), khai báo được **nhiều service + database/Redis** cùng lúc |
| **Khai báo build & healthcheck** | `[build] builder = "DOCKERFILE"`, `[deploy] healthcheckPath = "/health"` | `services[].runtime: docker`, `healthCheckPath: /health` |
| **Biến môi trường & Secret** | Thường đặt qua Dashboard hoặc `railway variables set`, không khai báo trực tiếp trong `railway.toml` | Khai báo sẵn trong `envVars:` với `generateValue: true` (tự sinh secret) hoặc `sync: false` (nhập trên dashboard) |
| **Lý do khác biệt** | Railway ưu tiên CLI/Dashboard nhanh gọn theo từng service | Render Blueprint quản lý toàn bộ stack (web + Redis + env) tập trung trong 1 file YAML |

### Exercise 3.3: Cloud Run CI/CD Pipeline (`03-cloud-deployment/production-cloud-run/`)

Từ `cloudbuild.yaml` và `service.yaml`, pipeline CI/CD chạy tự động khi push lên nhánh `main` qua 4 bước:
1. **`test`:** Dùng image `python:3.11-slim` cài `requirements.txt` + `pytest` và chạy `pytest tests/ -v`.
2. **`build`:** Dùng `gcr.io/cloud-builders/docker` build image gắn tag `$COMMIT_SHA` và `latest` (tận dụng `--cache-from`).
3. **`push`:** Đẩy tất cả tag image lên Google Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **`deploy`:** Dùng `gcloud run deploy` triển khai lên Cloud Run (`asia-southeast1`), cấu hình autoscale (`min-instances=1` tránh cold start, `max-instances=10`), tài nguyên (`512Mi` RAM, `1` CPU), inject secret từ Secret Manager, và `service.yaml` bổ sung `livenessProbe` (`/health`) + `startupProbe` (`/ready`).

---

## AI Log

- **Công cụ sử dụng:** Antigravity (trợ lý AI trong IDE).
- **Nội dung hỏi & nhận hỗ trợ:**
  1. **Part 1–5:** Chạy các ví dụ mẫu theo lưu ý K5, tổng hợp output `curl -i`, đo dung lượng Docker image và giải thích cơ chế stateless/security/scaling.
  2. **Part 6 (`06-lab-complete/`):** Gợi ý cài đặt `config.py`, `redis_client.py`, `auth.py`, `rate_limiter.py` (sliding window Redis), `cost_guard.py`, `main.py` (JSON logging, `/health`, `/ready`, `/ask`), `Dockerfile` multi-stage, `docker-compose.yml`, `railway.toml`, `render.yaml`.
  3. **Part 7 (`benchmark-observability/`):** Hỗ trợ chạy `load_test.py`, `run_eval.py`, bổ sung `KNOWLEDGE_BASE` cho 2 câu `security-02` và `scaling-03`, sửa lỗi path `/app/.local` trong `production/Dockerfile` của stack observability và tổng hợp số liệu từ JSON/CSV vào `BENCHMARK_REPORT.md`.
- **Tự kiểm tra:**
  - Tự chạy `check_production_ready.py` (đạt 42/42 checks trên Windows; cần chạy trên WSL2 Ubuntu để kiểm tra `SIGTERM` cho `PASS 12/12`).
  - Tự deploy lên Render và kiểm tra 4 lệnh CP6 trên URL public (`200 / 200 / 401 / 200`).
  - Đối chiếu toàn bộ số liệu trong `BENCHMARK_REPORT.md` khớp 100% với các file trong `reports/` và `benchmark-results/`.
