# Deployment Information

## Public URL
https://k5-l3b-day14-hoangquangdat-2a2020603808.onrender.com

## Platform
Render (Web Service — Docker runtime, `06-lab-complete/`) + Render Key Value (Redis)

## Test Commands

### Health & Readiness Check
```bash
curl -sS -o /dev/null -w '%{http_code}\n' "https://k5-l3b-day14-hoangquangdat-2a2020603808.onrender.com/health"
# Expected: 200

curl -sS -o /dev/null -w '%{http_code}\n' "https://k5-l3b-day14-hoangquangdat-2a2020603808.onrender.com/ready"
# Expected: 200
```

### API Test (without & with authentication)
```bash
# Without API key -> 401
curl -sS -o /dev/null -w '%{http_code}\n' \
  -X POST "https://k5-l3b-day14-hoangquangdat-2a2020603808.onrender.com/ask" \
  -H "Content-Type: application/json" \
  -d '{"question":"Hello"}'
# Expected: 401

# With API key -> 200
curl -X POST "https://k5-l3b-day14-hoangquangdat-2a2020603808.onrender.com/ask" \
  -H "X-API-Key: YOUR_AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test", "question": "Hello"}'
# Expected: 200
```

## Environment Variables Set
- `PORT` (cấp tự động bởi Render)
- `ENVIRONMENT` (`production`)
- `REDIS_URL` (Internal Redis URL từ Render Key Value)
- `AGENT_API_KEY` (đặt trên Render Dashboard, không lưu trong code)

## Screenshots
- [Deployment dashboard](screenshots/dashboard.jpg)
- [Service running](screenshots/running.jpg)
- [Test results](screenshots/test.jpg)

