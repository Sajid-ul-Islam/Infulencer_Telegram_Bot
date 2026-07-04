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
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "")  # e.g. http://localhost:11434
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
TIMEZONE_STR = os.getenv("TIMEZONE", "UTC")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "admin")

META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "my_secret_verify_token")

RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")  # Explicit webhook URL; falls back to RENDER_EXTERNAL_URL + /webhook

RATE_LIMIT_DAILY = int(os.getenv("RATE_LIMIT_DAILY", "50"))
RATE_LIMIT_VOICE_DAILY = int(os.getenv("RATE_LIMIT_VOICE_DAILY", "20"))
INLINE_MAX_RESULTS = int(os.getenv("INLINE_MAX_RESULTS", "10"))

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
