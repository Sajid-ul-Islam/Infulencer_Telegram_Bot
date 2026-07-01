import json
from typing import Optional
import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud import firestore as google_firestore
from bot.config import logger, FIREBASE_CREDENTIALS, YOUTUBE_LINK, MEDIUM_LINK, INSTAGRAM_LINK, TWITTER_LINK, FACEBOOK_LINK

db = None
if FIREBASE_CREDENTIALS:
    try:
        cred_dict = json.loads(FIREBASE_CREDENTIALS)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        list(db.collections(page_size=1))
    except Exception as e:
        logger.error(f"Error initializing Firebase — Firestore disabled: {e}")
        db = None

FAQ = {
    "how do you": "Check my YouTube channel for tutorials! Visit: " + YOUTUBE_LINK,
    "edit": "I use Adobe Premiere Pro for video editing. Tutorial coming soon!",
    "content": "I create content about tech and lifestyle. Subscribe to Medium for deep dives: " + MEDIUM_LINK,
    "collab": "For collaboration inquiries, DM me on Instagram: " + INSTAGRAM_LINK,
    "upload": "I upload new videos every week",
    "subscribe": "Subscribe to all my platforms:\n" +
                 f"\U0001f4fa YouTube: {YOUTUBE_LINK}\n" +
                 f"\U0001f4dd Medium: {MEDIUM_LINK}\n" +
                 f"\U0001f4f8 Instagram: {INSTAGRAM_LINK}\n" +
                 f"\U0001f426 X: {TWITTER_LINK}\n" +
                 f"\U0001f44d Facebook: {FACEBOOK_LINK}",
}

def load_faqs():
    if not db:
        logger.info("Firebase DB not configured — FAQs disabled.")
        return
    try:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(lambda: list(db.collection("faqs").stream()))
            docs = future.result(timeout=15)
            for doc in docs:
                FAQ[doc.id] = doc.to_dict().get("response", "")
            logger.info(f"Loaded {len(docs)} FAQs from Firestore.")
    except concurrent.futures.TimeoutError:
        logger.error("Firestore FAQ query timed out after 15s")
    except Exception as e:
        logger.error(f"Error loading FAQs: {e}")

def save_faq(keyword: str, response: str):
    FAQ[keyword] = response
    if db:
        try:
            db.collection("faqs").document(keyword).set({"response": response})
        except Exception as e:
            logger.error(f"Error saving FAQ to Firestore: {e}")

def remove_faq(keyword: str):
    if keyword in FAQ:
        del FAQ[keyword]
    if db:
        try:
            db.collection("faqs").document(keyword).delete()
        except Exception as e:
            logger.error(f"Error removing FAQ from Firestore: {e}")

def track_activity(user_id: int, username: str, command_name: str):
    if not db:
        logger.info(f"[Activity Log] User {username} ({user_id}): {command_name}")
        return
    try:
        db.collection("activity_logs").add({
            "user_id": user_id,
            "username": username,
            "command": command_name,
            "timestamp": google_firestore.SERVER_TIMESTAMP
        })
        user_ref = db.collection("users").document(str(user_id))
        user_ref.set({
            "username": username,
            "last_active": google_firestore.SERVER_TIMESTAMP,
            "total_clicks": google_firestore.Increment(1),
            f"commands.{command_name.replace('.', '_')}": google_firestore.Increment(1)
        }, merge=True)
    except Exception as e:
        logger.error(f"Error logging activity: {e}")

def save_feedback(user_id: int, username: str, feedback_type: str, message_id: int, original_text: str):
    if not db:
        logger.info(f"[Feedback] {username}: {feedback_type}")
        return
    try:
        db.collection("feedback").add({
            "user_id": user_id,
            "username": username,
            "type": feedback_type,
            "message_id": message_id,
            "original_text": original_text[:500],
            "timestamp": google_firestore.SERVER_TIMESTAMP
        })
    except Exception as e:
        logger.error(f"Error saving feedback: {e}")

def check_usage(user_id: int, usage_type: str = "ai_calls", limit: int = 50) -> tuple[bool, int]:
    if not db:
        return True, limit
    try:
        import datetime
        from google.cloud import firestore as gf
        ref = db.collection("usage").document(f"{user_id}_{usage_type}")
        now = datetime.datetime.utcnow()
        doc = ref.get()
        if doc.exists:
            data = doc.to_dict()
            count = data.get("count", 0)
            reset_at = data.get("reset_at")
            if reset_at and reset_at < now:
                count = 0
                ref.set({"count": 0, "reset_at": now + datetime.timedelta(hours=24)})
            if count >= limit:
                return False, limit - count
            return True, limit - count
        ref.set({
            "count": 0, "reset_at": now + datetime.timedelta(hours=24),
            "user_id": user_id, "type": usage_type
        })
        return True, limit
    except Exception as e:
        logger.error(f"check_usage error: {e}")
        return True, limit

def increment_usage(user_id: int, usage_type: str = "ai_calls"):
    if not db:
        return
    try:
        from google.cloud import firestore as gf
        import datetime
        ref = db.collection("usage").document(f"{user_id}_{usage_type}")
        now = datetime.datetime.utcnow()
        doc = ref.get()
        if doc.exists:
            data = doc.to_dict()
            reset_at = data.get("reset_at")
            if reset_at and reset_at < now:
                ref.set({"count": 1, "reset_at": now + datetime.timedelta(hours=24)})
            else:
                ref.update({"count": gf.Increment(1)})
        else:
            ref.set({
                "count": 1, "reset_at": now + datetime.timedelta(hours=24),
                "user_id": user_id, "type": usage_type
            })
    except Exception as e:
        logger.error(f"increment_usage error: {e}")

def get_trending_searches(limit: int = 10) -> list[dict]:
    if not db:
        return []
    try:
        docs = db.collection("activity_logs").order_by("timestamp", direction="DESCENDING").limit(500).stream()
        cmd_counts = {}
        for doc in docs:
            d = doc.to_dict()
            cmd = d.get("command", "")
            if cmd:
                cmd_counts[cmd] = cmd_counts.get(cmd, 0) + 1
        sorted_cmds = sorted(cmd_counts.items(), key=lambda x: x[1], reverse=True)[:limit]
        return [{"command": cmd, "count": count} for cmd, count in sorted_cmds]
    except Exception as e:
        logger.error(f"get_trending_searches error: {e}")
        return []

def get_token_usage_stats() -> dict:
    if not db:
        return {"total_tokens": 0, "by_provider": {}, "total_cost": 0}
    try:
        docs = db.collection("token_usage").stream()
        total = 0
        by_provider = {}
        total_cost = 0
        for doc in docs:
            d = doc.to_dict()
            tokens = d.get("tokens", 0)
            total += tokens
            cost = d.get("cost", 0)
            total_cost += cost
            provider = d.get("provider", "unknown")
            by_provider[provider] = by_provider.get(provider, 0) + tokens
        return {
            "total_tokens": total,
            "by_provider": by_provider,
            "total_cost": round(total_cost, 4)
        }
    except Exception as e:
        logger.error(f"get_token_usage_stats error: {e}")
        return {"total_tokens": 0, "by_provider": {}, "total_cost": 0}

def get_user_retention_stats() -> dict:
    if not db:
        return {"total_users": 0, "active_7d": 0, "active_30d": 0}
    try:
        import datetime
        users = list(db.collection("users").stream())
        total = len(users)
        now = datetime.datetime.utcnow()
        active_7d = 0
        active_30d = 0
        for user_doc in users:
            d = user_doc.to_dict()
            last = d.get("last_active")
            if last:
                if (now - last).days < 7:
                    active_7d += 1
                if (now - last).days < 30:
                    active_30d += 1
        return {
            "total_users": total,
            "active_7d": active_7d,
            "active_30d": active_30d
        }
    except Exception as e:
        logger.error(f"get_user_retention_stats error: {e}")
        return {"total_users": 0, "active_7d": 0, "active_30d": 0}

def get_feedback_counts() -> dict:
    if not db:
        return {"positive": 0, "negative": 0, "total": 0}
    try:
        pos_docs = list(db.collection("feedback").where("type", "==", "positive").stream())
        neg_docs = list(db.collection("feedback").where("type", "==", "negative").stream())
        return {
            "positive": len(pos_docs),
            "negative": len(neg_docs),
            "total": len(pos_docs) + len(neg_docs)
        }
    except Exception as e:
        logger.error(f"Error getting feedback counts: {e}")
        return {"positive": 0, "negative": 0, "total": 0}

async def track_token_usage(user_id: int, provider: str, tokens: int, cost: float = 0.0):
    if not db:
        logger.info(f"[Token Usage - DryRun] User {user_id}: {tokens} tokens ({provider})")
        return
    try:
        db.collection("token_usage").add({
            "user_id": user_id,
            "provider": provider,
            "tokens": tokens,
            "cost": cost,
            "timestamp": google_firestore.SERVER_TIMESTAMP
        })
        ref = db.collection("user_tokens").document(str(user_id))
        ref.set({
            "total_tokens": google_firestore.Increment(tokens),
            "total_cost": google_firestore.Increment(cost),
            "last_provider": provider,
            "last_active": google_firestore.SERVER_TIMESTAMP
        }, merge=True)
        logger.info(f"Logged token usage for {user_id}: {tokens} tokens ({provider})")
    except Exception as e:
        logger.error(f"Error tracking tokens: {e}")

def subscribe_user(user_id: int, username: str) -> bool:
    if not db:
        return False
    try:
        db.collection("subscriptions").document(str(user_id)).set({
            "user_id": user_id,
            "username": username,
            "timestamp": google_firestore.SERVER_TIMESTAMP
        })
        return True
    except Exception as e:
        logger.error(f"Error subscribing user {user_id}: {e}")
        return False

def unsubscribe_user(user_id: int) -> bool:
    if not db:
        return False
    try:
        db.collection("subscriptions").document(str(user_id)).delete()
        return True
    except Exception as e:
        logger.error(f"Error unsubscribing user {user_id}: {e}")
        return False

def get_subscribed_users() -> list[int]:
    if not db:
        return []
    try:
        docs = db.collection("subscriptions").stream()
        return [doc.to_dict().get("user_id") for doc in docs if doc.to_dict().get("user_id")]
    except Exception as e:
        logger.error(f"Error getting subscribed users: {e}")
        return []

def set_user_language(user_id: int, lang_code: str) -> bool:
    if not db:
        return False
    try:
        db.collection("users").document(str(user_id)).set({
            "language": lang_code,
            "last_active": google_firestore.SERVER_TIMESTAMP
        }, merge=True)
        return True
    except Exception as e:
        logger.error(f"Error setting user language for {user_id}: {e}")
        return False

def get_user_language(user_id: int) -> Optional[str]:
    if not db:
        return None
    try:
        doc = db.collection("users").document(str(user_id)).get()
        if doc.exists:
            return doc.to_dict().get("language")
        return None
    except Exception as e:
        logger.error(f"Error getting user language for {user_id}: {e}")
        return None
