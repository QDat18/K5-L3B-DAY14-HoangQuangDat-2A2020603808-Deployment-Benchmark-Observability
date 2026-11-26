"""
Production AI Agent — Part 6 Final Project.
"""
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import r, redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    """Format mọi log của app thành 1 JSON object hợp lệ trên mỗi dòng."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        return json.dumps(payload, ensure_ascii=False)


handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger = logging.getLogger("agent")
logger.setLevel(logging.INFO)
logger.handlers = [handler]
logger.propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        json.dumps(
            {
                "event": "startup",
                "environment": settings.environment,
                "port": settings.port,
            }
        )
    )
    yield
    logger.info(json.dumps({"event": "shutdown"}))
    if r is not None:
        try:
            r.close()
        except Exception:
            pass


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(json.dumps({"event": "unhandled_error", "path": request.url.path}))
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = None


@app.get("/health")
def health():
    """Liveness probe: luôn trả 200 khi process còn chạy."""
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness probe: 200 khi Redis sẵn sàng, 503 khi mất kết nối Redis."""
    if not redis_healthy():
        raise HTTPException(status_code=503, detail="Redis not ready")
    return {"ready": True}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    start = time.perf_counter()
    check_rate_limit(api_key)
    check_budget()

    answer = llm_ask(body.question)
    in_tokens = max(1, len(body.question.split()) * 2)
    out_tokens = max(1, len(answer.split()) * 2)
    cost = record_cost(in_tokens, out_tokens)

    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        json.dumps(
            {
                "event": "ask",
                "status": 200,
                "ms": elapsed_ms,
                "cost_usd": round(cost, 6),
            }
        )
    )
    return {"question": body.question, "answer": answer}
