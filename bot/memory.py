import json
import logging
from collections import defaultdict
from typing import Optional

logger = logging.getLogger("bot")

MAX_HISTORY = 10

# In-memory cache for fast access
_chat_histories: dict[int, list[dict]] = defaultdict(list)
_loaded_users: set[int] = set()


def _get_db():
    """Get Firestore DB instance, returns None if not configured."""
    try:
        from bot.database import db
        return db
    except ImportError:
        return None


def _load_from_firestore(user_id: int) -> list[dict]:
    """Load conversation history from Firestore for a user."""
    db = _get_db()
    if not db:
        return []
    try:
        doc = db.collection("chat_histories").document(str(user_id)).get()
        if doc.exists:
            data = doc.to_dict()
            messages = data.get("messages", [])
            logger.debug(f"Loaded {len(messages)} messages for user {user_id}")
            return messages
        return []
    except Exception as e:
        logger.error(f"Error loading history from Firestore for {user_id}: {e}")
        return []


def _save_to_firestore(user_id: int, messages: list[dict]) -> None:
    """Save conversation history to Firestore for a user."""
    db = _get_db()
    if not db:
        return
    try:
        # Keep only the last MAX_HISTORY * 2 messages to avoid huge docs
        trimmed = messages[-(MAX_HISTORY * 2):]
        db.collection("chat_histories").document(str(user_id)).set({
            "user_id": user_id,
            "messages": trimmed,
            "message_count": len(trimmed),
        })
    except Exception as e:
        logger.error(f"Error saving history to Firestore for {user_id}: {e}")


def _ensure_loaded(user_id: int) -> None:
    """Ensure user history is loaded from Firestore into cache."""
    if user_id not in _loaded_users:
        _chat_histories[user_id] = _load_from_firestore(user_id)
        _loaded_users.add(user_id)


def add_to_history(user_id: int, role: str, content: str) -> None:
    """Add a message to the user's conversation history."""
    _ensure_loaded(user_id)
    _chat_histories[user_id].append({"role": role, "content": content})
    # Persist to Firestore asynchronously to avoid blocking the event loop
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.run_in_executor(None, _save_to_firestore, user_id, _chat_histories[user_id])
        else:
            _save_to_firestore(user_id, _chat_histories[user_id])
    except Exception:
        pass


def get_history(user_id: int, max_exchanges: int = 3) -> list[dict]:
    """Get recent conversation history for a user."""
    _ensure_loaded(user_id)
    history = _chat_histories.get(user_id, [])
    return history[-(max_exchanges * 2):]


def clear_history(user_id: int) -> None:
    """Clear a user's conversation history from cache and Firestore."""
    if user_id in _chat_histories:
        del _chat_histories[user_id]
    _loaded_users.discard(user_id)
    db = _get_db()
    if db:
        def _delete():
            try:
                db.collection("chat_histories").document(str(user_id)).delete()
            except Exception as e:
                logger.error(f"Error clearing Firestore history for {user_id}: {e}")
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.run_in_executor(None, _delete)
            else:
                _delete()
        except Exception:
            pass


def get_history_count(user_id: int) -> int:
    """Get the number of exchanges (pairs of user+assistant messages)."""
    _ensure_loaded(user_id)
    return len(_chat_histories.get(user_id, [])) // 2
