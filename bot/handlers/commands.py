import re
import html
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ChatAction
from bot.config import logger, YOUTUBE_LINK, MEDIUM_LINK, INSTAGRAM_LINK, TWITTER_LINK, FACEBOOK_LINK, SUBSTACK_URL
from bot.rss import get_youtube_posts, get_medium_posts, get_substack_posts
from bot.ai import get_ai_response
from bot.database import track_activity
from bot.memory import clear_history, get_history_count
from bot.pipeline import ingest_knowledge_base, ingest_rss_content, get_pipeline_stats
from bot.search import search_duas, search_quran
from bot.handlers.feedback import FEEDBACK_POSITIVE, FEEDBACK_NEGATIVE


def clean_command_query(text: str, command: str) -> str:
    pattern = re.compile(rf"^/{command}(?:@[\w_]+)?\s*", re.IGNORECASE)
    return pattern.sub("", text).strip()


def track_usage(command_name):
    def decorator(func):
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            if not update.message:
                return
            if update.effective_user:
                user_id = update.effective_user.id
                username = update.effective_user.username or update.effective_user.first_name
                track_activity(user_id, username, command_name)
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator


@track_usage("start")
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "\U0001f44b <b>Assalamu Alaikum! Welcome to my content hub!</b>\n\n"
        "I share all my latest content from my platforms here. "
        "You can also ask me questions, search Islamic duas, or explore the Quran!\n\n"
        "<b>\U0001f4cc Commands:</b>\n"
        "/latest - Get my latest content\n"
        "/youtube - Latest video\n"
        "/medium - Latest article\n"
        "/substack - Latest newsletter\n"
        "/socials - Links to all my platforms\n"
        "/ask - Ask me a question (with memory!)\n"
        "/dua - Search Hisnul Muslim duas\n"
        "/quran - Search Quran verses\n"
        "/forget - Clear our conversation history\n"
        "/help - Show all commands"
    )
    await update.message.reply_text(welcome_text, parse_mode="HTML")


@track_usage("socials")
async def socials_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    socials_text = (
        "<b>\U0001f4da My Platforms:</b>\n"
        f"\U0001f4fa <a href=\"{YOUTUBE_LINK}\">YouTube</a> - Videos &amp; Tutorials\n"
        f"\U0001f4dd <a href=\"{MEDIUM_LINK}\">Medium</a> - In-depth Articles\n"
        f"\U0001f4f0 <a href=\"{SUBSTACK_URL}\">Substack</a> - Newsletters\n"
        f"\U0001f4f8 <a href=\"{INSTAGRAM_LINK}\">Instagram</a> - Behind the Scenes\n"
        f"\U0001f426 <a href=\"{TWITTER_LINK}\">X/Twitter</a> - Updates &amp; Discussions\n"
        f"\U0001f44d <a href=\"{FACEBOOK_LINK}\">Facebook</a> - Community"
    )
    await update.message.reply_text(socials_text, parse_mode="HTML")


@track_usage("latest")
async def latest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action(ChatAction.TYPING)
    message = "\U0001f504 <b>Fetching latest content...</b>\n\n"
    buttons = []

    yt_msg, yt_btn, _ = await get_youtube_posts(limit=2)
    if yt_msg:
        message += yt_msg + "\n\n"
        if yt_btn:
            buttons.append([yt_btn])

    med_msg, med_btn, _ = await get_medium_posts(limit=2)
    if med_msg:
        message += med_msg + "\n\n"
        if med_btn:
            buttons.append([med_btn])

    sub_msg, sub_btn, _ = await get_substack_posts(limit=2)
    if sub_msg:
        message += sub_msg + "\n\n"
        if sub_btn:
            buttons.append([sub_btn])

    if yt_msg or med_msg or sub_msg:
        reply_markup = InlineKeyboardMarkup(buttons) if buttons else None
        await update.message.reply_text(message, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await update.message.reply_text(
            "Currently no new content. Check back soon! \U0001f4cc",
            parse_mode="HTML",
        )


@track_usage("youtube")
async def youtube(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action(ChatAction.TYPING)
    yt_msg, yt_btn, _ = await get_youtube_posts(limit=3)
    if yt_msg:
        reply_markup = InlineKeyboardMarkup([[yt_btn]]) if yt_btn else None
        await update.message.reply_text(yt_msg, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await update.message.reply_text(
            f"No videos yet. Subscribe here: {YOUTUBE_LINK}", parse_mode="HTML"
        )


@track_usage("medium")
async def medium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action(ChatAction.TYPING)
    med_msg, med_btn, _ = await get_medium_posts(limit=3)
    if med_msg:
        reply_markup = InlineKeyboardMarkup([[med_btn]]) if med_btn else None
        await update.message.reply_text(med_msg, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await update.message.reply_text(
            f"No articles yet. Follow me on Medium: {MEDIUM_LINK}", parse_mode="HTML"
        )


@track_usage("substack")
async def substack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action(ChatAction.TYPING)
    sub_msg, sub_btn, _ = await get_substack_posts(limit=3)
    if sub_msg:
        reply_markup = InlineKeyboardMarkup([[sub_btn]]) if sub_btn else None
        await update.message.reply_text(sub_msg, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await update.message.reply_text(
            f"No newsletters yet. Subscribe here: {SUBSTACK_URL}", parse_mode="HTML"
        )


@track_usage("ask")
async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = clean_command_query(update.message.text, "ask")
    if not query:
        await update.message.reply_text(
            "\u2753 <b>Ask me anything!</b>\n\n"
            "Usage: /ask <your question>\n"
            "Example: /ask What camera do you use?\n\n"
            "I now have conversation memory - I'll remember context from our chat!",
            parse_mode="HTML",
        )
        return

    await update.message.chat.send_action(ChatAction.TYPING)
    user_id = update.effective_user.id
    response = await get_ai_response(query, user_id=user_id, use_memory=True)
    if not response:
        response = "I'm having trouble thinking right now. Please try again later!"

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "\U0001f44d",
                    callback_data=f"{FEEDBACK_POSITIVE}:{update.message.message_id}",
                ),
                InlineKeyboardButton(
                    "\U0001f44e",
                    callback_data=f"{FEEDBACK_NEGATIVE}:{update.message.message_id}",
                ),
            ]
        ]
    )
    await update.message.reply_text(response, parse_mode="HTML", reply_markup=keyboard)


@track_usage("dua")
async def dua_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = clean_command_query(update.message.text, "dua")
    if not query:
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Special Duas", callback_data="dua_cat:Special")],
                [InlineKeyboardButton("Best time for dua reminder", callback_data="dua_cat:Time")],
                [InlineKeyboardButton("Quranic Duas", callback_data="dua_cat:Quran")],
                [InlineKeyboardButton("Event Duas", callback_data="dua_cat:Event")],
            ]
        )
        await update.message.reply_text(
            "\U0001f54a <b>Search Islamic Duas</b>\n\n"
            "Choose a category below, or search specifically using:\n"
            "Usage: /dua <search query>\n"
            "Example: /dua dua for sleeping",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        return

    await update.message.chat.send_action(ChatAction.TYPING)
    result = search_duas(query)
    if not result or "No relevant duas found" in result:
        await update.message.reply_text(
            "\U0001f54a No duas found for your query. Try different keywords or ask the AI directly with /ask.",
            parse_mode="HTML",
        )
        return

    message_text = f"\U0001f54a <b>Hisnul Muslim Search Results</b>\n\n{html.escape(result)}"

    if len(message_text) > 4000:
        result_parts = result.split("\n\n---\n\n")
        safe_result = html.escape("\n\n---\n\n".join(result_parts[:1]))
        message_text = (
            f"\U0001f54a <b>Hisnul Muslim Search Results</b>\n\n{safe_result}"
            "\n\n<i>...[Results too long to display fully]</i>"
        )

    try:
        await update.message.reply_text(message_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error sending dua response: {e}")
        await update.message.reply_text(
            "An error occurred while displaying the results. Please try a different query."
        )


@track_usage("quran")
async def quran_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = clean_command_query(update.message.text, "quran")
    if not query:
        from bot.quran_scraper import SURAH_NAMES

        buttons = []
        for i in range(105, 115):
            if i in SURAH_NAMES:
                name = SURAH_NAMES[i][0]
                arabic = SURAH_NAMES[i][1]
                buttons.append(
                    [
                        InlineKeyboardButton(
                            f"{i}. {name} - {arabic}",
                            callback_data=f"quran_surah:{i}:1",
                        )
                    ]
                )
        keyboard = InlineKeyboardMarkup(buttons)
        await update.message.reply_text(
            "\U0001f4dc <b>Read the Quran</b>\n\n"
            "Select a Surah below (last 10 Surahs), or search for a specific verse/Surah:\n"
            "Usage: /quran <search query>\n"
            "Example: /quran Surah Yasin",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        return

    await update.message.chat.send_action(ChatAction.TYPING)
    result = search_quran(query)
    if not result or "No relevant Quran verses found" in result:
        await update.message.reply_text(
            "\U0001f4dc No Quran verses found for your query. Try different keywords or ask the AI directly with /ask.",
            parse_mode="HTML",
        )
        return

    message_text = f"\U0001f4dc <b>Quran Search Results</b>\n\n{html.escape(result)}"
    if len(message_text) > 4000:
        result_parts = result.split("\n\n---\n\n")
        safe_result = html.escape("\n\n---\n\n".join(result_parts[:1]))
        message_text = (
            f"\U0001f4dc <b>Quran Search Results</b>\n\n{safe_result}"
            "\n\n<i>...[Results too long to display fully]</i>"
        )

    try:
        await update.message.reply_text(message_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error sending quran response: {e}")
        await update.message.reply_text(
            "An error occurred while displaying the results. Please try a different query."
        )


@track_usage("forget")
async def forget_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    count = get_history_count(user_id)
    clear_history(user_id)
    await update.message.reply_text(
        f"\U0001f9f9 Conversation history cleared! I've forgotten our previous {count} exchanges.",
        parse_mode="HTML",
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
        f"Chunks indexed: <b>{stats['vector_documents']}</b>\n"
        f"Source entries: <b>{stats['kb_entries']}</b>",
        parse_mode="HTML",
    )


@track_usage("help")
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "<b>\U0001f916 Available Commands:</b>\n"
        "/start - Welcome message\n"
        "/latest - Get all latest content\n"
        "/youtube - Latest video\n"
        "/medium - Latest article\n"
        "/substack - Latest newsletter\n"
        "/socials - Links to all my platforms\n"
        "/ask - Ask me something (with memory!)\n"
        "/dua - Search Hisnul Muslim duas\n"
        "/quran - Search Quran verses\n"
        "/forget - Clear our conversation memory\n"
        "/language - Set language preference (English/Bengali)\n"
        "/suggest - Suggest a topic\n"
        "/help - This message\n\n"
        "<b>\U0001f4ac Just Ask!</b>\n"
        "Type any question and I'll answer using my knowledge base with AI.\n"
        "I remember our conversation context now!"
    )
    await update.message.reply_text(help_text, parse_mode="HTML")


@track_usage("subscribe")
async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    from bot.database import subscribe_user

    success = subscribe_user(user_id, username)
    if success:
        await update.message.reply_text(
            "\u2705 <b>Subscribed!</b>\n\nYou will now receive daily Islamic reminders (Duas and Quran Verses).",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text("Failed to subscribe. Please try again later.")


@track_usage("unsubscribe")
async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    from bot.database import unsubscribe_user

    success = unsubscribe_user(user_id)
    if success:
        await update.message.reply_text(
            "\u274c <b>Unsubscribed!</b>\n\nYou will no longer receive daily Islamic reminders.",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text("Failed to unsubscribe. Please try again later.")


@track_usage("language")
async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = clean_command_query(update.message.text, "language").lower()
    user_id = update.effective_user.id
    from bot.database import set_user_language

    if query in ["en", "bn", "english", "bengali"]:
        lang_code = "bn" if query in ["bn", "bengali"] else "en"
        success = set_user_language(user_id, lang_code)
        if success:
            lang_name = "Bengali \U0001f1e7\U0001f1e9" if lang_code == "bn" else "English \U0001f1ec\U0001f1e7"
            await update.message.reply_text(f"\u2705 Language preference set to {lang_name}.")
        else:
            await update.message.reply_text("\u274c Failed to save language preference.")
        return

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("English \U0001f1ec\U0001f1e7", callback_data="setlang:en")],
            [InlineKeyboardButton("Bengali \U0001f1e7\U0001f1e9", callback_data="setlang:bn")],
        ]
    )
    await update.message.reply_text(
        "\U0001f310 <b>Select your preferred language:</b>",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
