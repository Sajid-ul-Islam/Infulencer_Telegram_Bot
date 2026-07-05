"""Influencer management features: content queue, engagement tracking, and broadcast tools."""
import logging
import datetime
from typing import Optional
from bot.config import logger, CHANNEL_ID, TELEGRAM_TOKEN, BOT_TZ

logger = logging.getLogger("bot")


def _telegram_api(method: str, payload: dict) -> dict:
    """Synchronous Telegram API call helper."""
    import requests
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"
    try:
        res = requests.post(url, json=payload, timeout=15)
        return {"ok": res.status_code == 200, "result": res.json() if res.status_code == 200 else res.text}
    except Exception as e:
        logger.error(f"Telegram API error ({method}): {e}")
        return {"ok": False, "error": str(e)}


# ── Content Queue (Firestore-backed) ────────────────────────────
# In-memory cache for fast reads; every write goes through Firestore
# so posts survive Render free-tier restarts.
_scheduled_posts: list[dict] = []


def _load_pending_posts_from_firestore() -> int:
    """Load all pending scheduled posts from Firestore into the in-memory cache.
    Called once at startup so the queue is available immediately.
    Returns the number of posts loaded.
    """
    from bot.database import get_pending_scheduled_posts
    try:
        posts = get_pending_scheduled_posts()
        if not posts:
            return 0
        _scheduled_posts.clear()
        for post in posts:
            _scheduled_posts.append({
                "id": post["id"],
                "text": post.get("text", ""),
                "send_at": post.get("send_at", ""),
                "parse_mode": post.get("parse_mode", "HTML"),
                "status": post.get("status", "scheduled"),
            })
        if _scheduled_posts:
            logger.info(f"Loaded {len(_scheduled_posts)} pending scheduled posts from Firestore.")
        return len(_scheduled_posts)
    except Exception as e:
        logger.error(f"Failed to load scheduled posts from Firestore: {e}")
        return 0


def schedule_post(text: str, send_at: datetime.datetime, parse_mode: str = "HTML") -> dict:
    """Schedule a message for later delivery to the channel. Persists to Firestore."""
    import uuid
    post_id = f"sp_{uuid.uuid4().hex[:12]}"
    send_at_iso = send_at.isoformat()

    from bot.database import save_scheduled_post
    saved = save_scheduled_post(post_id, text, send_at_iso, parse_mode)
    if not saved:
        logger.warning(f"Failed to persist scheduled post {post_id} to Firestore (saved locally only)")

    post = {
        "id": post_id,
        "text": text,
        "send_at": send_at_iso,
        "parse_mode": parse_mode,
        "status": "scheduled",
    }
    _scheduled_posts.append(post)
    return post


def list_scheduled_posts() -> list[dict]:
    """Return all currently scheduled posts."""
    return [p for p in _scheduled_posts if p["status"] == "scheduled"]


def cancel_scheduled_post(post_id: str) -> bool:
    """Cancel a scheduled post by ID. Updates Firestore."""
    for post in _scheduled_posts:
        if post["id"] == post_id and post["status"] == "scheduled":
            post["status"] = "cancelled"
            from bot.database import update_scheduled_post_status
            update_scheduled_post_status(post_id, "cancelled")
            return True
    return False


async def process_due_posts(bot) -> int:
    """Check and send any posts whose send_at time has passed. Returns count sent."""
    from bot.database import update_scheduled_post_status
    now = datetime.datetime.now(BOT_TZ)
    sent = 0
    for post in _scheduled_posts:
        if post["status"] != "scheduled":
            continue
        send_at = datetime.datetime.fromisoformat(post["send_at"])
        # Make timezone-aware if naive
        if send_at.tzinfo is None:
            send_at = send_at.replace(tzinfo=BOT_TZ)
        if now >= send_at:
            try:
                await bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=post["text"],
                    parse_mode=post.get("parse_mode", "HTML"),
                )
                # Update Firestore first to avoid re-sending on restart
                update_scheduled_post_status(post["id"], "sent")
                post["status"] = "sent"
                sent += 1
                logger.info(f"Sent scheduled post {post['id']}")
            except Exception as e:
                logger.error(f"Failed to send scheduled post {post['id']}: {e}")
                update_scheduled_post_status(post["id"], "failed")
                post["status"] = "failed"
    return sent


# ── Channel Stats ───────────────────────────────────────────────
def get_channel_member_count() -> int:
    """Fetch the current subscriber count of the channel."""
    if not CHANNEL_ID:
        return 0
    result = _telegram_api("getChatMemberCount", {"chat_id": CHANNEL_ID})
    if result.get("ok"):
        return result["result"].get("result", 0)
    return 0


# ── Enhanced Broadcast ──────────────────────────────────────────
async def send_scheduled_broadcast(context, text: str, send_at: datetime.datetime) -> dict:
    """Queue a broadcast for the channel at a specific time."""
    post = schedule_post(text, send_at)
    return {
        "status": "scheduled",
        "post_id": post["id"],
        "send_at": post["send_at"],
    }


async def send_poll_to_channel(context, question: str, options: list[str], is_anonymous: bool = True) -> bool:
    """Send a poll to the configured channel."""
    if not CHANNEL_ID:
        return False
    try:
        await context.bot.send_poll(
            chat_id=CHANNEL_ID,
            question=question,
            options=options,
            is_anonymous=is_anonymous,
        )
        return True
    except Exception as e:
        logger.error(f"Error sending poll: {e}")
        return False


async def send_quiz_to_channel(context, question: str, options: list[str], correct_index: int, explanation: str = "") -> bool:
    """Send a quiz to the channel — great for engagement."""
    if not CHANNEL_ID:
        return False
    try:
        await context.bot.send_poll(
            chat_id=CHANNEL_ID,
            question=question,
            options=options,
            is_anonymous=True,
            type="quiz",
            correct_option_id=correct_index,
            explanation=explanation,
        )
        return True
    except Exception as e:
        logger.error(f"Error sending quiz: {e}")
        return False
