import os
import logging
import shlex
import json
from datetime import datetime, time
import feedparser
import requests
from telegram import Update
import firebase_admin
from firebase_admin import credentials, firestore
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============ CONFIGURATION ============
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
GROUP_ID = os.getenv("GROUP_ID")
ADMIN_ID = os.getenv("ADMIN_ID")
FIREBASE_CREDENTIALS = os.getenv("FIREBASE_CREDENTIALS")

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

# Your content platforms
YOUTUBE_CHANNEL_ID = "UCdFRSOdsaGPThmEsZb1tjXw"
MEDIUM_USERNAME = "b3ngali"
INSTAGRAM_HANDLE = "@bearded_bangali"
YOUTUBE_LINK = "https://www.youtube.com/@bearded_bangali"
MEDIUM_LINK = "https://medium.com/@b3ngali"
INSTAGRAM_LINK = "https://instagram.com/bearded_bangali"
TWITTER_LINK = "https://x.com/Beraded_Bengali"
FACEBOOK_LINK = "https://facebook.com/bb3ngali"

# Global state for duplicate prevention
last_posted_youtube_url = None
last_posted_medium_url = None

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

# ============ HELPER FUNCTIONS ============

def is_admin(user_id: str) -> bool:
    """Check if user is admin. Securely fails if ADMIN_ID is not configured."""
    if not ADMIN_ID:
        return False
    return str(user_id) == str(ADMIN_ID)

async def send_channel_message(context: ContextTypes.DEFAULT_TYPE, text: str):
    """Send message to your channel"""
    if not CHANNEL_ID:
        logger.warning("CHANNEL_ID not set. Skipping channel broadcast.")
        return
    try:
        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=text,
            parse_mode="HTML"
        )
        logger.info(f"Message sent to channel: {text[:50]}")
    except Exception as e:
        logger.error(f"Error sending to channel: {e}")

async def get_youtube_latest(return_url_only=False):
    """Fetch latest YouTube video"""
    try:
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={YOUTUBE_CHANNEL_ID}"
        feed = feedparser.parse(rss_url)
        
        if feed.entries:
            latest = feed.entries[0]
            title = latest.title
            link = latest.link
            
            if return_url_only:
                return link

            message = f"""
🎥 <b>New Video!</b>

<b>{title}</b>

<a href="{link}">Watch Now</a>
            """
            return message.strip(), link
    except Exception as e:
        logger.error(f"Error fetching YouTube: {e}")
    
    if return_url_only: return None
    return None, None

async def get_medium_latest(return_url_only=False):
    """Fetch latest Medium article"""
    try:
        rss_url = f"https://medium.com/feed/@{MEDIUM_USERNAME}"
        feed = feedparser.parse(rss_url)
        
        if feed.entries:
            latest = feed.entries[0]
            title = latest.title
            link = latest.link
            
            if return_url_only:
                return link

            message = f"""
📝 <b>New Article!</b>

<b>{title}</b>

<a href="{link}">Read Now</a>
            """
            return message.strip(), link
    except Exception as e:
        logger.error(f"Error fetching Medium: {e}")
    
    if return_url_only: return None
    return None, None

def get_faq_response(user_message: str) -> str:
    """Match user question to FAQ"""
    user_message_lower = user_message.lower()
    
    for keyword, response in FAQ.items():
        if keyword in user_message_lower:
            return response
    
    return (
        "Thanks for your question! 😊\n\n"
        "If you didn't find the answer, try /socials to see all my platforms!\n\n"
        "You can also ask me directly in the group!"
    )

# ============ COMMAND HANDLERS ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = f"""
👋 <b>Welcome to my content hub!</b>

I share all my latest content from my platforms here. You can also ask me questions about my content!

<b>📌 Commands:</b>
/latest - Get my latest content
/youtube - Latest video
/medium - Latest article
/socials - Links to all my platforms
/ask - Ask me a question
/help - Show all commands
    """
    await update.message.reply_text(welcome_text, parse_mode="HTML")
    logger.info(f"User {update.effective_user.id} started the bot")

async def socials_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show social media links"""
    socials_text = f"""
<b>📚 My Platforms:</b>
📺 <a href="{YOUTUBE_LINK}">YouTube</a> - Videos & Tutorials
📝 <a href="{MEDIUM_LINK}">Medium</a> - In-depth Articles
📸 <a href="{INSTAGRAM_LINK}">Instagram</a> - Behind the Scenes
🐦 <a href="{TWITTER_LINK}">X/Twitter</a> - Updates & Discussions
👍 <a href="{FACEBOOK_LINK}">Facebook</a> - Community
    """
    await update.message.reply_text(socials_text, parse_mode="HTML")

async def latest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action(ChatAction.TYPING)
    message = "🔄 <b>Fetching latest content...</b>\n\n"
    
    yt_msg, _ = await get_youtube_latest()
    if yt_msg: message += yt_msg + "\n\n"
    
    med_msg, _ = await get_medium_latest()
    if med_msg: message += med_msg + "\n\n"
    
    if yt_msg or med_msg:
        await update.message.reply_text(message, parse_mode="HTML")
    else:
        await update.message.reply_text("Currently no new content. Check back soon! 📌", parse_mode="HTML")

async def youtube(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action(ChatAction.TYPING)
    yt_msg, _ = await get_youtube_latest()
    if yt_msg:
        await update.message.reply_text(yt_msg, parse_mode="HTML")
    else:
        await update.message.reply_text(f"No videos yet. Subscribe here: {YOUTUBE_LINK}", parse_mode="HTML")

async def medium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action(ChatAction.TYPING)
    med_msg, _ = await get_medium_latest()
    if med_msg:
        await update.message.reply_text(med_msg, parse_mode="HTML")
    else:
        await update.message.reply_text(f"No articles yet. Follow me on Medium: {MEDIUM_LINK}", parse_mode="HTML")

async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ <b>Ask me anything!</b>\n\n"
        "Just type your question and I'll try to help.\n"
        "Common topics: editing, content creation, collaborations, etc.",
        parse_mode="HTML"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
<b>🤖 Available Commands:</b>
/start - Welcome message
/latest - Get all latest content
/youtube - Latest video
/medium - Latest article
/socials - Links to all my platforms
/ask - Ask me something
/help - This message

<b>💬 Just Ask!</b>
Type any question and I'll answer based on my knowledge.
    """
    await update.message.reply_text(help_text, parse_mode="HTML")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user_message = update.message.text
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    if db:
        try:
            db.collection("questions").add({
                "user_id": user_id,
                "username": username,
                "question": user_message,
                "timestamp": firestore.SERVER_TIMESTAMP
            })
        except Exception as e:
            logger.error(f"Firebase error: {e}")

    response = get_faq_response(user_message)
    await update.message.reply_text(response, parse_mode="HTML")
    logger.info(f"Answered question from {user_id}: {user_message[:50]}")

# ============ ADMIN COMMANDS ============

async def questions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission to use this command.")
        return

    if not db:
        await update.message.reply_text("Firebase is not configured.")
        return

    try:
        docs = db.collection("questions").order_by("timestamp", direction="DESCENDING").limit(10).stream()
        message = "📝 <b>Recent Questions:</b>\n\n"
        count = 0
        for doc in docs:
            row = doc.to_dict()
            dt = row.get('timestamp')
            time_str = dt.strftime('%Y-%m-%d %H:%M:%S') if dt else "Unknown time"
            message += f"👤 <b>{row.get('username')}</b> ({time_str}):\n{row.get('question')}\n\n"
            count += 1

        if count == 0:
            await update.message.reply_text("No questions found.")
            return
        
        await update.message.reply_text(message, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Firebase error: {e}")
        await update.message.reply_text("Error retrieving questions.")

async def poll_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission to use this command.")
        return

    try:
        args = shlex.split(update.message.text)[1:]
        if len(args) < 3:
            await update.message.reply_text("Usage: /poll \"Question\" \"Option 1\" \"Option 2\" ...")
            return
            
        question = args[0]
        options = args[1:]
        
        if not CHANNEL_ID:
            await update.message.reply_text("CHANNEL_ID is not configured.")
            return
            
        await context.bot.send_poll(
            chat_id=CHANNEL_ID,
            question=question,
            options=options,
            is_anonymous=True
        )
        await update.message.reply_text("✅ Poll sent to channel!")
    except ValueError:
        await update.message.reply_text("Invalid format. Make sure to use quotes around options with spaces.")
    except Exception as e:
        await update.message.reply_text(f"Error sending poll: {e}")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission to use this command.")
        return

    text = update.message.text.replace("/broadcast", "", 1).strip()
    if not text:
        await update.message.reply_text("Usage: /broadcast <message>")
        return

    await send_channel_message(context, text)
    await update.message.reply_text("✅ Broadcast sent!")

async def addfaq_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission to use this command.")
        return

    try:
        args = shlex.split(update.message.text)[1:]
        if len(args) < 2:
            await update.message.reply_text("Usage: /addfaq \"keyword or phrase\" \"Response text\"")
            return
        keyword = args[0].lower()
        response = args[1]
        save_faq(keyword, response)
        await update.message.reply_text(f"✅ FAQ saved for keyword: {keyword}")
    except ValueError:
        await update.message.reply_text("Invalid format. Use quotes around keyword and response.")

async def rmfaq_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission to use this command.")
        return

    try:
        args = shlex.split(update.message.text)[1:]
        if len(args) < 1:
            await update.message.reply_text("Usage: /rmfaq \"keyword\"")
            return
        keyword = args[0].lower()
        remove_faq(keyword)
        await update.message.reply_text(f"✅ FAQ removed for keyword: {keyword}")
    except ValueError:
        await update.message.reply_text("Invalid format.")

async def listfaq_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission to use this command.")
        return

    if not FAQ:
        await update.message.reply_text("No FAQs available.")
        return
    
    msg = "📝 <b>Current FAQs:</b>\n\n"
    for k, v in FAQ.items():
        msg += f"<b>{k}</b>: {v[:50]}...\n"
    await update.message.reply_text(msg, parse_mode="HTML")

# ============ SCHEDULED POSTING ============

async def auto_post_youtube(context: ContextTypes.DEFAULT_TYPE):
    global last_posted_youtube_url
    try:
        yt_msg, link = await get_youtube_latest()
        if yt_msg and link and link != last_posted_youtube_url:
            await send_channel_message(context, yt_msg)
            last_posted_youtube_url = link
    except Exception as e:
        logger.error(f"Error in auto_post_youtube: {e}")

async def auto_post_medium(context: ContextTypes.DEFAULT_TYPE):
    global last_posted_medium_url
    try:
        med_msg, link = await get_medium_latest()
        if med_msg and link and link != last_posted_medium_url:
            await send_channel_message(context, med_msg)
            last_posted_medium_url = link
    except Exception as e:
        logger.error(f"Error in auto_post_medium: {e}")

async def greeting_post(context: ContextTypes.DEFAULT_TYPE):
    greeting = """
✨ <b>Good Day!</b>

Welcome to my content hub! 

Find all my latest updates here. Got a question? Just DM the bot!

#Content #Creator
    """
    await send_channel_message(context, greeting)

# ============ MAIN APPLICATION ============

def main():
    load_faqs()
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("socials", socials_command))
    application.add_handler(CommandHandler("latest", latest))
    application.add_handler(CommandHandler("youtube", youtube))
    application.add_handler(CommandHandler("medium", medium))
    application.add_handler(CommandHandler("ask", ask_command))
    application.add_handler(CommandHandler("help", help_command))
    
    # Admin commands
    application.add_handler(CommandHandler("questions", questions_command))
    application.add_handler(CommandHandler("poll", poll_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("addfaq", addfaq_command))
    application.add_handler(CommandHandler("rmfaq", rmfaq_command))
    application.add_handler(CommandHandler("listfaq", listfaq_command))
    
    # Message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Scheduled jobs
    job_queue = application.job_queue
    job_queue.run_daily(auto_post_youtube, time=time(9, 0), days=(0, 1, 2, 3, 4, 5, 6))
    job_queue.run_daily(auto_post_medium, time=time(18, 0), days=(0, 1, 2, 3, 4, 5, 6))
    job_queue.run_daily(greeting_post, time=time(8, 0), days=(0, 1, 2, 3, 4, 5, 6))
    
    logger.info("Bot started successfully!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
