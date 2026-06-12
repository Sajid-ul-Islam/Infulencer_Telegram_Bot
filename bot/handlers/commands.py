from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ChatAction
from bot.config import YOUTUBE_LINK, MEDIUM_LINK, INSTAGRAM_LINK, TWITTER_LINK, FACEBOOK_LINK
from bot.rss import get_youtube_posts, get_medium_posts
from bot.ai import get_grok_response

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = f"""
👋 <b>Assalamu Alaikum! Welcome to my content hub!</b>

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
    buttons = []
    
    yt_msg, yt_btn, _ = await get_youtube_posts(limit=2)
    if yt_msg: 
        message += yt_msg + "\n\n"
        if yt_btn: buttons.append([yt_btn])
    
    med_msg, med_btn, _ = await get_medium_posts(limit=2)
    if med_msg: 
        message += med_msg + "\n\n"
        if med_btn: buttons.append([med_btn])
    
    if yt_msg or med_msg:
        reply_markup = InlineKeyboardMarkup(buttons) if buttons else None
        await update.message.reply_text(message, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Currently no new content. Check back soon! 📌", parse_mode="HTML")

async def youtube(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action(ChatAction.TYPING)
    yt_msg, yt_btn, _ = await get_youtube_posts(limit=3)
    if yt_msg:
        reply_markup = InlineKeyboardMarkup([[yt_btn]]) if yt_btn else None
        await update.message.reply_text(yt_msg, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await update.message.reply_text(f"No videos yet. Subscribe here: {YOUTUBE_LINK}", parse_mode="HTML")

async def medium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action(ChatAction.TYPING)
    med_msg, med_btn, _ = await get_medium_posts(limit=3)
    if med_msg:
        reply_markup = InlineKeyboardMarkup([[med_btn]]) if med_btn else None
        await update.message.reply_text(med_msg, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await update.message.reply_text(f"No articles yet. Follow me on Medium: {MEDIUM_LINK}", parse_mode="HTML")

async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.replace("/ask", "", 1).strip()
    if not query:
        await update.message.reply_text(
            "❓ <b>Ask me anything!</b>\n\n"
            "Usage: /ask <your question>\n"
            "Example: /ask What camera do you use?",
            parse_mode="HTML"
        )
        return
        
    await update.message.chat.send_action(ChatAction.TYPING)
    response = await get_grok_response(query)
    if not response:
        response = "I'm having trouble thinking right now. Please try again later!"
        
    await update.message.reply_text(response, parse_mode="HTML")

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
