from telegram import InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.config import logger, CHANNEL_ID
from bot.rss import get_youtube_posts, get_medium_posts, get_substack_posts
from bot.pipeline import ingest_rss_content

last_posted_youtube_url = None
last_posted_medium_url = None
last_posted_substack_url = None

async def send_channel_message(context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None):
    if not CHANNEL_ID:
        logger.warning("CHANNEL_ID not set. Skipping channel broadcast.")
        return
    try:
        await context.bot.send_message(
            chat_id=CHANNEL_ID,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup
        )
        logger.info(f"Message sent to channel: {text[:50]}")
    except Exception as e:
        logger.error(f"Error sending to channel: {e}")

async def auto_post_youtube(context: ContextTypes.DEFAULT_TYPE):
    global last_posted_youtube_url
    try:
        yt_msg, yt_btn, link = await get_youtube_posts(limit=1)
        if yt_msg and link and link != last_posted_youtube_url:
            reply_markup = InlineKeyboardMarkup([[yt_btn]]) if yt_btn else None
            await send_channel_message(context, yt_msg, reply_markup=reply_markup)
            last_posted_youtube_url = link
        await ingest_rss_content()
    except Exception as e:
        logger.error(f"Error in auto_post_youtube: {e}")

async def auto_post_medium(context: ContextTypes.DEFAULT_TYPE):
    global last_posted_medium_url
    try:
        med_msg, med_btn, link = await get_medium_posts(limit=1)
        if med_msg and link and link != last_posted_medium_url:
            reply_markup = InlineKeyboardMarkup([[med_btn]]) if med_btn else None
            await send_channel_message(context, med_msg, reply_markup=reply_markup)
            last_posted_medium_url = link
        await ingest_rss_content()
    except Exception as e:
        logger.error(f"Error in auto_post_medium: {e}")

async def auto_post_substack(context: ContextTypes.DEFAULT_TYPE):
    global last_posted_substack_url
    try:
        sub_msg, sub_btn, link = await get_substack_posts(limit=1)
        if sub_msg and link and link != last_posted_substack_url:
            reply_markup = InlineKeyboardMarkup([[sub_btn]]) if sub_btn else None
            await send_channel_message(context, sub_msg, reply_markup=reply_markup)
            last_posted_substack_url = link
        await ingest_rss_content()
    except Exception as e:
        logger.error(f"Error in auto_post_substack: {e}")

async def greeting_post(context: ContextTypes.DEFAULT_TYPE):
    greeting = """
\u2728 <b>Assalamu Alaikum!</b>

Welcome to my content hub! 

Find all my latest updates here. Got a question? Just DM the bot!

#Content #Creator
    """
    await send_channel_message(context, greeting)
