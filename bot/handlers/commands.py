from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ChatAction
from bot.config import YOUTUBE_LINK, MEDIUM_LINK, INSTAGRAM_LINK, TWITTER_LINK, FACEBOOK_LINK, SUBSTACK_URL
from bot.rss import get_youtube_posts, get_medium_posts, get_substack_posts
from bot.ai import get_ai_response
from bot.database import track_activity
from bot.memory import clear_history, get_history_count
from bot.pipeline import ingest_knowledge_base, ingest_rss_content, get_pipeline_stats
from bot.handlers.feedback import FEEDBACK_POSITIVE, FEEDBACK_NEGATIVE

def track_usage(command_name):
    def decorator(func):
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            if update.effective_user:
                user_id = update.effective_user.id
                username = update.effective_user.username or update.effective_user.first_name
                track_activity(user_id, username, command_name)
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator

@track_usage("start")
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = """
\U0001f44b <b>Assalamu Alaikum! Welcome to my content hub!</b>

I share all my latest content from my platforms here. You can also ask me questions about my content!

<b>\U0001f4cc Commands:</b>
/latest - Get my latest content
/youtube - Latest video
/medium - Latest article
/substack - Latest newsletter
/socials - Links to all my platforms
/ask - Ask me a question (with memory!)
/forget - Clear our conversation history
/help - Show all commands
    """
    await update.message.reply_text(welcome_text, parse_mode="HTML")

@track_usage("socials")
async def socials_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    socials_text = f"""
<b>\U0001f4da My Platforms:</b>
\U0001f4fa <a href="{YOUTUBE_LINK}">YouTube</a> - Videos & Tutorials
\U0001f4dd <a href="{MEDIUM_LINK}">Medium</a> - In-depth Articles
\U0001f4f0 <a href="{SUBSTACK_URL}">Substack</a> - Newsletters
\U0001f4f8 <a href="{INSTAGRAM_LINK}">Instagram</a> - Behind the Scenes
\U0001f426 <a href="{TWITTER_LINK}">X/Twitter</a> - Updates & Discussions
\U0001f44d <a href="{FACEBOOK_LINK}">Facebook</a> - Community
    """
    await update.message.reply_text(socials_text, parse_mode="HTML")

@track_usage("latest")
async def latest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action(ChatAction.TYPING)
    message = "\U0001f504 <b>Fetching latest content...</b>\n\n"
    buttons = []

    yt_msg, yt_btn, _ = await get_youtube_posts(limit=2)
    if yt_msg:
        message += yt_msg + "\n\n"
        if yt_btn: buttons.append([yt_btn])

    med_msg, med_btn, _ = await get_medium_posts(limit=2)
    if med_msg:
        message += med_msg + "\n\n"
        if med_btn: buttons.append([med_btn])

    sub_msg, sub_btn, _ = await get_substack_posts(limit=2)
    if sub_msg:
        message += sub_msg + "\n\n"
        if sub_btn: buttons.append([sub_btn])

    if yt_msg or med_msg or sub_msg:
        reply_markup = InlineKeyboardMarkup(buttons) if buttons else None
        await update.message.reply_text(message, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Currently no new content. Check back soon! \U0001f4cc", parse_mode="HTML")

@track_usage("youtube")
async def youtube(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action(ChatAction.TYPING)
    yt_msg, yt_btn, _ = await get_youtube_posts(limit=3)
    if yt_msg:
        reply_markup = InlineKeyboardMarkup([[yt_btn]]) if yt_btn else None
        await update.message.reply_text(yt_msg, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await update.message.reply_text(f"No videos yet. Subscribe here: {YOUTUBE_LINK}", parse_mode="HTML")

@track_usage("medium")
async def medium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action(ChatAction.TYPING)
    med_msg, med_btn, _ = await get_medium_posts(limit=3)
    if med_msg:
        reply_markup = InlineKeyboardMarkup([[med_btn]]) if med_btn else None
        await update.message.reply_text(med_msg, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await update.message.reply_text(f"No articles yet. Follow me on Medium: {MEDIUM_LINK}", parse_mode="HTML")

@track_usage("substack")
async def substack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action(ChatAction.TYPING)
    sub_msg, sub_btn, _ = await get_substack_posts(limit=3)
    if sub_msg:
        reply_markup = InlineKeyboardMarkup([[sub_btn]]) if sub_btn else None
        await update.message.reply_text(sub_msg, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await update.message.reply_text(f"No newsletters yet. Subscribe here: {SUBSTACK_URL}", parse_mode="HTML")

@track_usage("ask")
async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.replace("/ask", "", 1).strip()
    if not query:
        await update.message.reply_text(
            "\u2753 <b>Ask me anything!</b>\n\n"
            "Usage: /ask <your question>\n"
            "Example: /ask What camera do you use?\n\n"
            "I now have conversation memory - I'll remember context from our chat!",
            parse_mode="HTML"
        )
        return

    await update.message.chat.send_action(ChatAction.TYPING)
    user_id = update.effective_user.id
    response = await get_ai_response(query, user_id=user_id, use_memory=True)
    if not response:
        response = "I'm having trouble thinking right now. Please try again later!"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\U0001f44d", callback_data=f"{FEEDBACK_POSITIVE}:{update.message.message_id}"),
            InlineKeyboardButton("\U0001f44e", callback_data=f"{FEEDBACK_NEGATIVE}:{update.message.message_id}")
        ]
    ])
    await update.message.reply_text(response, parse_mode="HTML", reply_markup=keyboard)

@track_usage("forget")
async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    count = get_history_count(user_id)
    clear_history(user_id)
    await update.message.reply_text(
        f"\U0001f9f9 Conversation history cleared! I've forgotten our previous {count} exchanges.",
        parse_mode="HTML"
    )

@track_usage("ingest")
async def ingest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from bot.config import is_admin
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("\u26d4 You don't have permission to use this command.")
        return
    await update.message.reply_text("\U0001f504 Re-indexing knowledge base...")
    count = ingest_knowledge_base(reindex=True)
    stats = get_pipeline_stats()
    await update.message.reply_text(
        f"\u2705 Knowledge base ingested!\n\n"
        f"Chunks indexed: {stats['vector_documents']}\n"
        f"Source entries: {stats['kb_entries']}",
        parse_mode="HTML"
    )

@track_usage("help")
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
<b>\U0001f916 Available Commands:</b>
/start - Welcome message
/latest - Get all latest content
/youtube - Latest video
/medium - Latest article
/substack - Latest newsletter
/socials - Links to all my platforms
/ask - Ask me something (with memory!)
/forget - Clear our conversation memory
/suggest - Suggest a topic
/help - This message

<b>\U0001f4ac Just Ask!</b>
Type any question and I'll answer using my knowledge base with AI.
I remember our conversation context now!
    """
    await update.message.reply_text(help_text, parse_mode="HTML")
