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
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")  # Get from environment
CHANNEL_ID = os.getenv("CHANNEL_ID")  # Your channel ID (e.g., -100123456789)
GROUP_ID = os.getenv("GROUP_ID")  # Optional: Your group ID for Q&A
ADMIN_ID = os.getenv("ADMIN_ID")  # Optional: Your personal User ID for admin commands
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

# Your content platforms (update with your actual URLs)
YOUTUBE_CHANNEL_ID = "UCdFRSOdsaGPThmEsZb1tjXw"  # Get from YouTube channel URL
MEDIUM_USERNAME = "b3ngali"
INSTAGRAM_HANDLE = "@bearded_bangali"
YOUTUBE_LINK = "https://www.youtube.com/@bearded_bangali"
MEDIUM_LINK = "https://medium.com/@b3ngali"
INSTAGRAM_LINK = "https://instagram.com/bearded_bangali"
TWITTER_LINK = "https://x.com/Beraded_Bengali"
FACEBOOK_LINK = "https://facebook.com/bb3ngali"

# ============ FAQ RESPONSES ============
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

# ============ HELPER FUNCTIONS ============

async def send_channel_message(context: ContextTypes.DEFAULT_TYPE, text: str):
    """Send message to your channel"""
    try:
        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=text,
            parse_mode="HTML"
        )
        logger.info(f"Message sent to channel: {text[:50]}")
    except Exception as e:
        logger.error(f"Error sending to channel: {e}")

async def get_youtube_latest():
    """Fetch latest YouTube video"""
    try:
        # Using YouTube RSS feed
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={YOUTUBE_CHANNEL_ID}"
        feed = feedparser.parse(rss_url)
        
        if feed.entries:
            latest = feed.entries[0]
            title = latest.title
            link = latest.link
            
            message = f"""
🎥 <b>New Video!</b>

<b>{title}</b>

<a href="{link}">Watch Now</a>
            """
            return message.strip()
    except Exception as e:
        logger.error(f"Error fetching YouTube: {e}")
    
    return None

async def get_medium_latest():
    """Fetch latest Medium article"""
    try:
        rss_url = f"https://medium.com/feed/@{MEDIUM_USERNAME}"
        feed = feedparser.parse(rss_url)
        
        if feed.entries:
            latest = feed.entries[0]
            title = latest.title
            link = latest.link
            
            message = f"""
📝 <b>New Article!</b>

<b>{title}</b>

<a href="{link}">Read Now</a>
            """
            return message.strip()
    except Exception as e:
        logger.error(f"Error fetching Medium: {e}")
    
    return None

def get_faq_response(user_message: str) -> str:
    """Match user question to FAQ"""
    user_message_lower = user_message.lower()
    
    for keyword, response in FAQ.items():
        if keyword in user_message_lower:
            return response
    
    # Default response if no match
    return (
        "Thanks for your question! 😊\n\n"
        "If you didn't find the answer, here are all my platforms:\n\n"
        f"📺 <b>YouTube:</b> {YOUTUBE_LINK}\n"
        f"📝 <b>Medium:</b> {MEDIUM_LINK}\n"
        f"📸 <b>Instagram:</b> {INSTAGRAM_LINK}\n"
        f"🐦 <b>X/Twitter:</b> {TWITTER_LINK}\n"
        f"👍 <b>Facebook:</b> {FACEBOOK_LINK}\n\n"
        "You can also ask me directly in the group!"
    )

# ============ COMMAND HANDLERS ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message when someone starts the bot"""
    welcome_text = f"""
👋 <b>Welcome to my content hub!</b>

I share all my latest content from my platforms here. You can also ask me questions about my content!

<b>📚 My Platforms:</b>
📺 <a href="{YOUTUBE_LINK}">YouTube</a> - Videos & Tutorials
📝 <a href="{MEDIUM_LINK}">Medium</a> - In-depth Articles
📸 <a href="{INSTAGRAM_LINK}">Instagram</a> - Behind the Scenes
🐦 <a href="{TWITTER_LINK}">X/Twitter</a> - Updates & Discussions
👍 <a href="{FACEBOOK_LINK}">Facebook</a> - Community

<b>📌 Commands:</b>
/latest - Get my latest content
/youtube - Latest video
/medium - Latest article
/ask - Ask me a question
/help - Show all commands
    """
    
    await update.message.reply_text(welcome_text, parse_mode="HTML")
    logger.info(f"User {update.effective_user.id} started the bot")

async def latest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get latest content from all platforms"""
    await update.message.chat.send_action(ChatAction.TYPING)
    
    message = "🔄 <b>Fetching latest content...</b>\n\n"
    
    # Get latest YouTube
    yt = await get_youtube_latest()
    if yt:
        message += yt + "\n\n"
    
    # Get latest Medium
    med = await get_medium_latest()
    if med:
        message += med + "\n\n"
    
    if yt or med:
        await update.message.reply_text(message, parse_mode="HTML")
    else:
        await update.message.reply_text(
            "Currently no new content. Check back soon! 📌",
            parse_mode="HTML"
        )

async def youtube(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get latest YouTube video"""
    await update.message.chat.send_action(ChatAction.TYPING)
    
    yt = await get_youtube_latest()
    if yt:
        await update.message.reply_text(yt, parse_mode="HTML")
    else:
        await update.message.reply_text(
            f"No videos yet. Subscribe here: {YOUTUBE_LINK}",
            parse_mode="HTML"
        )

async def medium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get latest Medium article"""
    await update.message.chat.send_action(ChatAction.TYPING)
    
    med = await get_medium_latest()
    if med:
        await update.message.reply_text(med, parse_mode="HTML")
    else:
        await update.message.reply_text(
            f"No articles yet. Follow me on Medium: {MEDIUM_LINK}",
            parse_mode="HTML"
        )

async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prompt user to ask a question"""
    await update.message.reply_text(
        "❓ <b>Ask me anything!</b>\n\n"
        "Just type your question and I'll try to help.\n"
        "Common topics: editing, content creation, collaborations, etc.",
        parse_mode="HTML"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all available commands"""
    help_text = """
<b>🤖 Available Commands:</b>

/start - Welcome message
/latest - Get all latest content
/youtube - Latest video
/medium - Latest article
/ask - Ask me something
/help - This message

<b>💬 Just Ask!</b>
Type any question and I'll answer based on my knowledge.

<b>Popular Questions:</b>
• How do you edit videos?
• Can we collaborate?
• When do you upload?
• How do I subscribe?
    """
    await update.message.reply_text(help_text, parse_mode="HTML")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular messages (questions)"""
    user_message = update.message.text
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    # Save to database
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

    # Get FAQ response
    response = get_faq_response(user_message)
    
    await update.message.reply_text(response, parse_mode="HTML")
    logger.info(f"Answered question from {user_id}: {user_message[:50]}")

async def questions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View recent questions (Admin only)"""
    user_id = str(update.effective_user.id)
    if ADMIN_ID and user_id != ADMIN_ID:
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
    """Create a poll in the channel (Admin only)"""
    user_id = str(update.effective_user.id)
    if ADMIN_ID and user_id != ADMIN_ID:
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
        await update.message.reply_text(f"✅ Poll sent to channel!")
        logger.info(f"Poll sent to channel by {user_id}")
    except ValueError:
        await update.message.reply_text("Invalid format. Make sure to use quotes around options with spaces.")
    except Exception as e:
        logger.error(f"Error sending poll: {e}")
        await update.message.reply_text(f"Error sending poll: {e}")

# ============ SCHEDULED POSTING ============

async def auto_post_youtube(context: ContextTypes.DEFAULT_TYPE):
    """Auto-post latest YouTube video to channel (runs daily)"""
    try:
        yt = await get_youtube_latest()
        if yt:
            await send_channel_message(context, yt)
    except Exception as e:
        logger.error(f"Error in auto_post_youtube: {e}")

async def auto_post_medium(context: ContextTypes.DEFAULT_TYPE):
    """Auto-post latest Medium article to channel (runs daily)"""
    try:
        med = await get_medium_latest()
        if med:
            await send_channel_message(context, med)
    except Exception as e:
        logger.error(f"Error in auto_post_medium: {e}")

async def greeting_post(context: ContextTypes.DEFAULT_TYPE):
    """Post daily greeting to channel"""
    greeting = f"""
✨ <b>Good Day!</b>

Welcome to my content hub! 

Find all my latest updates here. Got a question? Just DM the bot!

#Content #Creator
    """
    await send_channel_message(context, greeting)

# ============ MAIN APPLICATION ============

def main():
    """Start the bot"""
    # Create application
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("latest", latest))
    application.add_handler(CommandHandler("youtube", youtube))
    application.add_handler(CommandHandler("medium", medium))
    application.add_handler(CommandHandler("ask", ask_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("questions", questions_command))
    application.add_handler(CommandHandler("poll", poll_command))
    
    # Message handler (for Q&A)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Scheduled jobs (auto-posting)
    job_queue = application.job_queue
    
    # Post latest YouTube daily at 9 AM
    job_queue.run_daily(auto_post_youtube, time=time(9, 0), days=(0, 1, 2, 3, 4, 5, 6))
    
    # Post latest Medium daily at 6 PM
    job_queue.run_daily(auto_post_medium, time=time(18, 0), days=(0, 1, 2, 3, 4, 5, 6))
    
    # Post greeting daily at 8 AM
    job_queue.run_daily(greeting_post, time=time(8, 0), days=(0, 1, 2, 3, 4, 5, 6))
    
    logger.info("Bot started successfully!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
