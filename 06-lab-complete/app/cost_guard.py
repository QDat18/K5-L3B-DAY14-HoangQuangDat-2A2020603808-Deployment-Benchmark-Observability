"""
Cost guard (tiêu chí 8) — cộng dồn chi phí LLM vào Redis.
"""
import time
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _daily_cost_key() -> str:
    return f"cost:daily:{time.strftime('%Y-%m-%d', time.gmtime())}"


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Vượt DAILY_BUDGET_USD → HTTP 402."""
    if r is None:
        return
    try:
        val = r.get(_daily_cost_key())
        current_cost = float(val) if val is not None else 0.0
    except Exception:
        return

    if current_cost >= settings.daily_budget_usd:
        raise HTTPException(status_code=402, detail="Daily budget exceeded")


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí request vào Redis và trả về chi phí."""
    cost = (
        (input_tokens / 1000.0) * PRICE_INPUT_PER_1K
        + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K
    )
    if r is not None:
        try:
            key = _daily_cost_key()
            r.incrbyfloat(key, cost)
            r.expire(key, 86400 * 2)
        except Exception:
            pass
    return cost
