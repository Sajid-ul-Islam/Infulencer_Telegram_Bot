import time
from collections import defaultdict
from bot.config import logger
from bot.database import db

DAILY_LIMIT = 50
WINDOW_SECONDS = 86400

_in_memory: dict[int, list[float]] = defaultdict(list)

def _get_daily_limit() -> int:
    import os
    try:
        return int(os.getenv("RATE_LIMIT_DAILY", str(DAILY_LIMIT)))
    except ValueError:
        return DAILY_LIMIT

def check_rate_limit_local(user_id: int) -> tuple[bool, int]:
    limit = _get_daily_limit()
    now = time.time()
    window_start = now - WINDOW_SECONDS
    timestamps = _in_memory[user_id]
    timestamps[:] = [t for t in timestamps if t > window_start]
    if len(timestamps) >= limit:
        return False, limit - len(timestamps)
    timestamps.append(now)
    return True, limit - len(timestamps)

def check_rate_limit_firestore(user_id: int) -> tuple[bool, int]:
    if not db:
        return check_rate_limit_local(user_id)
    try:
        from google.cloud import firestore as gf
        ref = db.collection("rate_limits").document(str(user_id))
        import datetime
        now = datetime.datetime.utcnow()
        doc = ref.get()
        if doc.exists:
            data = doc.to_dict()
            count = data.get("count", 0)
            reset_at = data.get("reset_at")
            if reset_at and reset_at < now:
                count = 0
                ref.set({"count": 0, "reset_at": now + datetime.timedelta(hours=24)})
            limit = _get_daily_limit()
            if count >= limit:
                return False, limit - count
            ref.update({"count": gf.Increment(1), "last_request": now})
            return True, limit - count - 1
        else:
            ref.set({
                "count": 1, "reset_at": now + datetime.timedelta(hours=24),
                "last_request": now, "user_id": user_id
            })
            return True, _get_daily_limit() - 1
    except Exception as e:
        logger.error(f"Rate limit FB error: {e}")
        return check_rate_limit_local(user_id)

def check_rate_limit(user_id: int) -> tuple[bool, int]:
    return check_rate_limit_firestore(user_id)

async def track_token_usage(user_id: int, provider: str, tokens: int, cost: float = 0.0):
    if not db:
        return
    try:
        from google.cloud import firestore as gf
        db.collection("token_usage").add({
            "user_id": user_id,
            "provider": provider,
            "tokens": tokens,
            "cost": cost,
            "timestamp": gf.SERVER_TIMESTAMP
        })
        ref = db.collection("user_tokens").document(str(user_id))
        ref.set({
            "total_tokens": gf.Increment(tokens),
            "total_cost": gf.Increment(cost),
            "last_provider": provider,
            "last_active": gf.SERVER_TIMESTAMP
        }, merge=True)
    except Exception as e:
        logger.error(f"Error tracking tokens: {e}")
