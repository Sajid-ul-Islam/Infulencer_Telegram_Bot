import os
import logging
import datetime
from zoneinfo import ZoneInfo

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("bot")

# ============ CONFIGURATION ============
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
GROUP_ID = os.getenv("GROUP_ID")
ADMIN_ID = os.getenv("ADMIN_ID")
FIREBASE_CREDENTIALS = os.getenv("FIREBASE_CREDENTIALS")
XAI_API_KEY = os.getenv("XAI_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
TIMEZONE_STR = os.getenv("TIMEZONE", "UTC")

try:
    BOT_TZ = ZoneInfo(TIMEZONE_STR)
except Exception:
    BOT_TZ = datetime.timezone.utc

# Your content platforms (loaded from .env, with fallbacks)
YOUTUBE_CHANNEL_ID = os.getenv("YOUTUBE_CHANNEL_ID", "UCdFRSOdsaGPThmEsZb1tjXw")
MEDIUM_USERNAME = os.getenv("MEDIUM_USERNAME", "b3ngali")
INSTAGRAM_HANDLE = os.getenv("INSTAGRAM_HANDLE", "@bearded_bangali")

YOUTUBE_LINK = os.getenv("YOUTUBE_LINK", "https://www.youtube.com/@bearded_bangali")
MEDIUM_LINK = os.getenv("MEDIUM_LINK", "https://medium.com/@b3ngali")
SUBSTACK_URL = os.getenv("SUBSTACK_URL", "https://beardedbangali.substack.com")
INSTAGRAM_LINK = os.getenv("INSTAGRAM_LINK", "https://instagram.com/bearded_bangali")
TWITTER_LINK = os.getenv("TWITTER_LINK", "https://x.com/Beraded_Bengali")
FACEBOOK_LINK = os.getenv("FACEBOOK_LINK", "https://facebook.com/bb3ngali")

def is_admin(user_id: str) -> bool:
    """Check if user is admin. Securely fails if ADMIN_ID is not configured."""
    if not ADMIN_ID:
        return False
    return str(user_id) == str(ADMIN_ID)
