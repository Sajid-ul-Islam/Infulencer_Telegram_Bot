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
        
        # Verify credentials instantly via direct HTTP token refresh before initializing Firebase
        from google.oauth2 import service_account
        import google.auth.transport.requests
        scopes = ['https://www.googleapis.com/auth/cloud-platform']
        google_creds = service_account.Credentials.from_service_account_info(cred_dict, scopes=scopes)
        req = google.auth.transport.requests.Request()
        google_creds.refresh(req)
        
        # If token refresh succeeded, credentials are valid! Now initialize Firebase admin client
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        client_instance = firestore.client()
        
        # Verify Cloud Firestore API is enabled and accessible by performing a lightweight query
        client_instance.collection("faqs").limit(1).get()
        
        db = client_instance
        logger.info("Firebase Firestore connection verified and initialized successfully.")
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


def set_reminder_time(user_id: int, time_pref: str) -> bool:
    """Sets the user's reminder time preference: 'morning' or 'evening'."""
    if time_pref not in ("morning", "evening"):
        return False
    if not db:
        return False
    try:
        db.collection("subscriptions").document(str(user_id)).set({
            "reminder_time": time_pref
        }, merge=True)
        return True
    except Exception as e:
        logger.error(f"Error setting reminder time for {user_id}: {e}")
        return False


def get_reminder_time(user_id: int) -> str:
    """Returns the user's reminder time preference, defaulting to 'morning'."""
    if not db:
        return "morning"
    try:
        doc = db.collection("subscriptions").document(str(user_id)).get()
        if doc.exists:
            return doc.to_dict().get("reminder_time", "morning")
        return "morning"
    except Exception as e:
        logger.error(f"Error getting reminder time for {user_id}: {e}")
        return "morning"


def get_subscribed_users_by_time(time_pref: str) -> list[int]:
    """Returns user IDs of subscribed users with a specific time preference.
    'morning' returns users with reminder_time='morning' or unset (default).
    'evening' returns only users with reminder_time='evening'."""
    if not db:
        return []
    try:
        docs = db.collection("subscriptions").stream()
        users = []
        for doc in docs:
            data = doc.to_dict()
            user_id = data.get("user_id")
            if not user_id:
                continue
            user_time = data.get("reminder_time", "morning")
            if time_pref == "morning":
                if user_time == "morning":
                    users.append(user_id)
            else:
                if user_time == "evening":
                    users.append(user_id)
        return users
    except Exception as e:
        logger.error(f"Error getting subscribed users by time: {e}")
        return []


SCHEDULED_POSTS_COLLECTION = "scheduled_posts"


def save_scheduled_post(post_id: str, text: str, send_at: str, parse_mode: str = "HTML") -> bool:
    """Persist a scheduled post to Firestore."""
    if not db:
        return False
    try:
        db.collection(SCHEDULED_POSTS_COLLECTION).document(post_id).set({
            "text": text,
            "send_at": send_at,
            "parse_mode": parse_mode,
            "status": "scheduled",
            "created_at": google_firestore.SERVER_TIMESTAMP,
        })
        return True
    except Exception as e:
        logger.error(f"Error saving scheduled post {post_id}: {e}")
        return False


def update_scheduled_post_status(post_id: str, status: str) -> bool:
    """Update the status of a scheduled post (sent, failed, cancelled)."""
    if not db:
        return False
    try:
        db.collection(SCHEDULED_POSTS_COLLECTION).document(post_id).update({
            "status": status,
        })
        return True
    except Exception as e:
        logger.error(f"Error updating scheduled post {post_id}: {e}")
        return False


def get_pending_scheduled_posts() -> list[dict]:
    """Load all posts with status='scheduled' from Firestore.
    Note: Requires a composite index on (status, send_at) in the scheduled_posts collection.
    Firestore auto-creates this on first query, but if it fails, create it manually in the Firebase console.
    """
    if not db:
        return []
    try:
        docs = (
            db.collection(SCHEDULED_POSTS_COLLECTION)
            .where("status", "==", "scheduled")
            .order_by("send_at")
            .stream()
        )
        posts = []
        for doc in docs:
            data = doc.to_dict()
            data["id"] = doc.id
            posts.append(data)
        return posts
    except Exception as e:
        logger.error(f"Error loading scheduled posts: {e}")
        return []


def delete_scheduled_post(post_id: str) -> bool:
    """Delete a scheduled post from Firestore."""
    if not db:
        return False
    try:
        db.collection(SCHEDULED_POSTS_COLLECTION).document(post_id).delete()
        return True
    except Exception as e:
        logger.error(f"Error deleting scheduled post {post_id}: {e}")
        return False


BOOKMARKS_COLLECTION = "user_bookmarks"

def save_bookmark(user_id: int, item_id: str, doc_type: str, title: str, snippet: str, url: str = "") -> bool:
    """Saves a bookmark. item_id is the unique ID from the vector DB (e.g. 'dua_42', 'quran_1_1')."""
    if not db:
        return False
    try:
        doc_ref = db.collection(BOOKMARKS_COLLECTION).document(str(user_id)).collection("items").document(item_id)
        doc_ref.set({
            "user_id": user_id,
            "item_id": item_id,
            "type": doc_type,
            "title": title,
            "snippet": snippet[:300],
            "url": url,
            "saved_at": google_firestore.SERVER_TIMESTAMP
        })
        return True
    except Exception as e:
        logger.error(f"Error saving bookmark for {user_id}: {e}")
        return False


def remove_bookmark(user_id: int, item_id: str) -> bool:
    """Removes a bookmark by item_id for the given user."""
    if not db:
        return False
    try:
        db.collection(BOOKMARKS_COLLECTION).document(str(user_id)).collection("items").document(item_id).delete()
        return True
    except Exception as e:
        logger.error(f"Error removing bookmark {item_id} for {user_id}: {e}")
        return False


def get_user_bookmarks(user_id: int, limit: int = 10, offset: int = 0) -> list[dict]:
    """Returns a paginated list of bookmarks for the user, newest first."""
    if not db:
        return []
    try:
        docs = (
            db.collection(BOOKMARKS_COLLECTION)
            .document(str(user_id))
            .collection("items")
            .order_by("saved_at", direction="DESCENDING")
            .limit(limit)
            .offset(offset)
            .stream()
        )
        return [doc.to_dict() for doc in docs]
    except Exception as e:
        logger.error(f"Error getting bookmarks for {user_id}: {e}")
        return []


def is_bookmarked(user_id: int, item_id: str) -> bool:
    """Checks if a specific item is already bookmarked by the user."""
    if not db:
        return False
    try:
        doc = db.collection(BOOKMARKS_COLLECTION).document(str(user_id)).collection("items").document(item_id).get()
        return doc.exists
    except Exception as e:
        logger.error(f"Error checking bookmark {item_id} for {user_id}: {e}")
        return False


def get_bookmark_count(user_id: int) -> int:
    """Returns the total number of bookmarks for the user."""
    if not db:
        return 0
    try:
        docs = db.collection(BOOKMARKS_COLLECTION).document(str(user_id)).collection("items").stream()
        return len(list(docs))
    except Exception as e:
        logger.error(f"Error counting bookmarks for {user_id}: {e}")
        return 0
