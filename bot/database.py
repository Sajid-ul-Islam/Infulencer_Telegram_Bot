import json
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
    except Exception as e:
        logger.error(f"Error initializing Firebase: {e}")

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
        return
    try:
        docs = db.collection("faqs").stream()
        for doc in docs:
            FAQ[doc.id] = doc.to_dict().get("response", "")
        logger.info("Loaded FAQs from Firestore.")
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
