"""
Rate limiting (tiêu chí 7) — sliding window 60s lưu trong Redis.
"""
import time
import uuid
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r


def check_rate_limit(key: str) -> None:
    """Giới hạn RATE_LIMIT_PER_MINUTE request / 60s cho mỗi API key."""
    if r is None:
        raise HTTPException(status_code=503, detail="Rate limiter unavailable")

    now = time.time()
    window = 60
    window_start = now - window
    redis_key = f"ratelimit:{key}"

    try:
        pipe = r.pipeline()
        pipe.zremrangebyscore(redis_key, 0, window_start)
        pipe.zcard(redis_key)
        _, current_count = pipe.execute()

        if current_count >= settings.rate_limit_per_minute:
            oldest = r.zrange(redis_key, 0, 0, withscores=True)
            retry_after = (
                max(1, int(window - (now - oldest[0][1]))) if oldest else window
            )
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )

        member = f"{now}:{uuid.uuid4().hex}"
        pipe = r.pipeline()
        pipe.zadd(redis_key, {member: now})
        pipe.expire(redis_key, window + 5)
        pipe.execute()
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Rate limiter error")
