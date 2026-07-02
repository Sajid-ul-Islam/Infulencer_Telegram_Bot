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
from bot.search import search_duas, search_quran, format_rag_status_line, get_rag_status
from bot.handlers.feedback import FEEDBACK_POSITIVE, FEEDBACK_NEGATIVE


def build_dua_menu_text() -> str:
    return (
        "\U0001f54a <b>Search Islamic Duas</b>\n\n"
        f"{format_rag_status_line('dua')}\n\n"
        "Choose a category below, or search with:\n"
        "<code>/dua sleeping</code>\n"
        "<code>/dua travel</code>"
    )


async def build_dua_menu_keyboard() -> InlineKeyboardMarkup:
    """Builds the dua category menu from cached chapter data."""
    from bot.dua_scraper import get_cached_dua_categories
    categories = get_cached_dua_categories()
    if not categories:
        # Fallback if categories not loaded yet — just show a loading state
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("\u23f3 Loading categories...", callback_data="dua_menu_reload")]
        ])
    buttons = []
    for slug, display_name in categories:
        buttons.append([
            InlineKeyboardButton(display_name, callback_data=f"dua_cat:{slug}")
        ])
    return InlineKeyboardMarkup(buttons)


def build_quran_menu_text(page: int = 1) -> str:
    return (
        "\U0001f4dc <b>Read & Search the Quran</b>\n\n"
        f"{format_rag_status_line('quran')}\n\n"
        "Tap a Surah to read verses, or search with:\n"
        "<code>/quran yasin</code>\n"
        "<code>/quran mercy</code>\n\n"
        f"<i>Showing Surahs {max(1, (page - 1) * 14 + 1)}–{min(114, page * 14)}</i>"
    )


def build_quran_menu_keyboard(page: int = 1) -> InlineKeyboardMarkup:
    from bot.quran_scraper import SURAH_NAMES

    per_page = 14
    start = (page - 1) * per_page + 1
    end = min(page * per_page, 114)
    buttons = []
    for surah_no in range(start, end + 1):
        if surah_no not in SURAH_NAMES:
            continue
        name, arabic, english, _, _ = SURAH_NAMES[surah_no]
        buttons.append(
            [
                InlineKeyboardButton(
                    f"{surah_no}. {name} — {arabic}",
                    callback_data=f"quran_surah:{surah_no}:1",
                )
            ]
        )

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"quran_menu:{page - 1}"))
    if end < 114:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"quran_menu:{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    return InlineKeyboardMarkup(buttons)


def format_empty_rag_message(collection: str) -> str:
    status = get_rag_status()
    if not status["available"]:
        return "\u26a0\ufe0f The search index is still starting. Please try again in a minute."
    if collection == "dua":
        return (
            "\U0001f54a Duas are still being indexed in the background.\n\n"
            "Please wait a minute and tap /dua again, or ask with /ask."
        )
    return (
        "\U0001f4dc Quran verses are still being indexed in the background.\n\n"
        "Please wait a minute and tap /quran again, or ask with /ask."
    )


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
        await update.message.reply_text(
            build_dua_menu_text(),
            parse_mode="HTML",
            reply_markup=await build_dua_menu_keyboard(),
        )
        return

    await update.message.chat.send_action(ChatAction.TYPING)
    if not get_rag_status()["dua_ready"]:
        await update.message.reply_text(format_empty_rag_message("dua"), parse_mode="HTML")
        return

    result = search_duas(query)
    if not result or "No relevant duas found" in result:
        await update.message.reply_text(
            "\U0001f54a No duas found for your query. Try different keywords or tap /dua for the category menu.",
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
        await update.message.reply_text(
            build_quran_menu_text(page=1),
            parse_mode="HTML",
            reply_markup=build_quran_menu_keyboard(page=1),
        )
        return

    await update.message.chat.send_action(ChatAction.TYPING)
    if not get_rag_status()["quran_ready"]:
        await update.message.reply_text(format_empty_rag_message("quran"), parse_mode="HTML")
        return

    result = search_quran(query)
    if not result or "No relevant Quran verses found" in result:
        await update.message.reply_text(
            "\U0001f4dc No Quran verses found for your query. Try different keywords or tap /quran for the Surah menu.",
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
    from bot.database import subscribe_user, set_reminder_time

    query = clean_command_query(update.message.text, "subscribe").lower()
    time_pref = "morning"
    if query in ("morning", "evening"):
        time_pref = query

    success = subscribe_user(user_id, username)
    if success:
        set_reminder_time(user_id, time_pref)
        time_label = "morning \U0001f305" if time_pref == "morning" else "evening \U0001f31b"
        await update.message.reply_text(
            f"\u2705 <b>Subscribed!</b>\n\n"
            f"You will receive daily Islamic reminders in the <b>{time_label}</b>.\n"
            f"Each reminder includes an Ayah of the Day and a Dua of the Day.\n\n"
            f"To change your time, use:\n"
            f"<code>/subscribe morning</code> or <code>/subscribe evening</code>",
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
            "\u274c <b>Unsubscribed!</b>\n\nYou will no longer receive daily Islamic reminders.\n\n"
            "To resubscribe, use /subscribe (add <code>morning</code> or <code>evening</code> for time preference).",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text("Failed to unsubscribe. Please try again later.")


@track_usage("remindertime")
async def reminder_time_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allows users to change their reminder time without resubscribing."""
    user_id = update.effective_user.id
    query = clean_command_query(update.message.text, "remindertime").lower()

    from bot.database import get_reminder_time, set_reminder_time, get_subscribed_users

    if query in ("morning", "evening"):
        # Check if user is subscribed first
        subscribed_users = get_subscribed_users()
        if user_id not in subscribed_users:
            await update.message.reply_text(
                "\u26a0\ufe0f You are not subscribed. Use /subscribe first, or use:\n"
                f"<code>/subscribe {query}</code>",
                parse_mode="HTML",
            )
            return
        success = set_reminder_time(user_id, query)
        if success:
            time_label = "morning \U0001f305" if query == "morning" else "evening \U0001f31b"
            await update.message.reply_text(
                f"\u2705 Reminder time changed to <b>{time_label}</b>.",
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text("Failed to update reminder time. Please try again later.")
        return

    current = get_reminder_time(user_id)
    current_label = "morning \U0001f305" if current == "morning" else "evening \U0001f31b"
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("\U0001f305 Morning (10:00 AM)", callback_data="remindertime:morning")],
            [InlineKeyboardButton("\U0001f31b Evening (6:00 PM)", callback_data="remindertime:evening")],
        ]
    )
    await update.message.reply_text(
        f"\u23f0 <b>Reminder Time Preference</b>\n\n"
        f"Current: <b>{current_label}</b>\n\n"
        f"Choose when you'd like to receive your daily Islamic reminder:\n"
        f"<b>Morning</b> — Ayah + Dua at 10:00 AM\n"
        f"<b>Evening</b> — Ayah + Dua at 6:00 PM",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


@track_usage("myduas")
async def myduas_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the user's saved bookmarks with pagination."""
    user_id = update.effective_user.id
    text, markup = build_myduas_message(user_id, page=0)
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=markup)


def build_myduas_message(user_id: int, page: int = 0) -> tuple[str, InlineKeyboardMarkup]:
    """Builds the bookmark list message and keyboard. Page 0 = most recent."""
    from bot.database import get_user_bookmarks, get_bookmark_count
    per_page = 5
    bookmarks = get_user_bookmarks(user_id, limit=per_page, offset=page * per_page)
    total = get_bookmark_count(user_id)

    if not bookmarks:
        text = (
            "\U0001f516 <b>My Bookmarked Duas & Ayahs</b>\n\n"
            "You haven't saved any bookmarks yet.\n\n"
            "When browsing duas or Quran verses, tap the \U0001f516 button to save them here."
        )
        return text, InlineKeyboardMarkup([])

    lines = ["\U0001f516 <b>My Bookmarked Duas & Ayahs</b>\n"]
    buttons = []

    for i, bm in enumerate(bookmarks, start=page * per_page + 1):
        doc_type = bm.get("type", "dua")
        icon = "\U0001f54a" if doc_type == "dua" else "\U0001f4dc"
        title = bm.get("title", bm.get("item_id", ""))
        snippet = bm.get("snippet", "")[:60]
        item_id = bm.get("item_id", "")
        lines.append(f"{i}. {icon} <b>{title}</b>")
        if snippet:
            lines.append(f"   <i>{snippet}...</i>")
        # Row: View + Remove per bookmark
        buttons.append([
            InlineKeyboardButton(f"\U0001f441 View #{i}", callback_data=f"bm_view:{item_id}"),
            InlineKeyboardButton(f"\U0001f5d1 Remove", callback_data=f"bm_rm:{item_id}"),
        ])

    # Pagination
    total_pages = max(1, (total + per_page - 1) // per_page)
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"myduas_page:{page - 1}"))
    if page + 1 < total_pages:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"myduas_page:{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    lines.append(f"\n\U0001f4cb <i>Page {page + 1} of {total_pages} ({total} total)</i>")

    return "\n".join(lines), InlineKeyboardMarkup(buttons)


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
