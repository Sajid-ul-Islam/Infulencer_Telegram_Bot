import json
import firebase_admin
from firebase_admin import credentials, firestore
from bot.config import logger, FIREBASE_CREDENTIALS, YOUTUBE_LINK, MEDIUM_LINK, INSTAGRAM_LINK, TWITTER_LINK, FACEBOOK_LINK

# Initialize Firebase
db = None
if FIREBASE_CREDENTIALS:
    try:
        cred_dict = json.loads(FIREBASE_CREDENTIALS)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
    except Exception as e:
        logger.error(f"Error initializing Firebase: {e}")

# ============ FAQ RESPONSES ============
# In-memory FAQ storage (will sync with Firestore if enabled)
FAQ = {
    "how do you": "Check my YouTube channel for tutorials! Visit: " + YOUTUBE_LINK,
    "edit": "I use Adobe Premiere Pro for video editing. Tutorial coming soon!",
    "content": "I create content about tech and lifestyle. Subscribe to Medium for deep dives: " + MEDIUM_LINK,
    "collab": "For collaboration inquiries, DM me on Instagram: " + INSTAGRAM_LINK,
    "upload": "I upload new videos every week",
    "subscribe": "Subscribe to all my platforms:\n" +
                 f"📺 YouTube: {YOUTUBE_LINK}\n" +
                 f"📝 Medium: {MEDIUM_LINK}\n" +
                 f"📸 Instagram: {INSTAGRAM_LINK}\n" +
                 f"🐦 X: {TWITTER_LINK}\n" +
                 f"👍 Facebook: {FACEBOOK_LINK}",
}

def load_faqs():
    """Load FAQs from Firebase into memory"""
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
    """Save an FAQ to Firebase"""
    FAQ[keyword] = response
    if db:
        try:
            db.collection("faqs").document(keyword).set({"response": response})
        except Exception as e:
            logger.error(f"Error saving FAQ to Firestore: {e}")

def remove_faq(keyword: str):
    """Remove an FAQ from Firebase and memory"""
    if keyword in FAQ:
        del FAQ[keyword]
    if db:
        try:
            db.collection("faqs").document(keyword).delete()
        except Exception as e:
            logger.error(f"Error removing FAQ from Firestore: {e}")
