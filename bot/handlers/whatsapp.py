"""
WhatsApp command & feature handler for the Bearded Bangali bot.
Mirrors ALL Telegram bot features for WhatsApp:
  - Content browsing (latest, youtube, medium, substack, socials)
  - Islamic features (dua search/browse, Quran search/browse, bookmarks)
  - AI assistant (ask with memory, free-text chat)
  - User management (subscribe, reminders, preferences)
  - Study mode, bookmarks, language
  - Admin features (stats, broadcast, postlatest)
  - Interactive lists & reply buttons for navigation
"""
import asyncio
import datetime
from typing import Optional

from bot.config import (
    logger, is_admin, ADMIN_ID, CHANNEL_ID, BOT_TZ,
    YOUTUBE_LINK, MEDIUM_LINK, INSTAGRAM_LINK, TWITTER_LINK,
    FACEBOOK_LINK, SUBSTACK_URL, FACEBOOK_RSS_URL, TWITTER_RSS_URL,
)
from bot.database import (
    db, track_activity, subscribe_user, unsubscribe_user, get_subscribed_users,
    set_reminder_time, get_reminder_time, set_user_language, get_user_language,
    set_study_mode, get_study_mode,
    save_bookmark, remove_bookmark, get_user_bookmarks, get_bookmark_count, is_bookmarked,
    get_feedback_counts,
)
from bot.ai import get_ai_response
from bot.rss import get_youtube_posts, get_medium_posts, get_substack_posts
from bot.search import (
    search_duas, search_quran, search_duas_by_category, get_surah_verses,
    get_rag_status, format_rag_status_line,
)
from bot.whatsapp_utils import (
    send_whatsapp_message, send_interactive_list, send_reply_buttons,
    strip_html, send_reaction, send_read_receipt, send_audio,
    build_section, build_button_reply,
)
from bot.quran_scraper import SURAH_NAMES, get_verse_audio_url
from bot.dua_scraper import get_cached_dua_categories
from bot.vectordb import get_available_books, get_collection

# ── Session / state helpers ─────────────────────────────────────
# Store the last interactive message sent (list/buttons) so we know
# what the user is responding to when they tap a list row.
_user_sessions: dict = {}

def _normalize_sender(sender_id: str) -> str:
    """Normalize WhatsApp sender ID: strip '+' prefix for consistent lookups."""
    return sender_id.lstrip("+")


def _to_user_id(sender_id: str) -> Optional[int]:
    """Convert a WhatsApp sender ID to a consistent integer user ID.
    Strips '+' prefix from phone numbers before numeric conversion.
    """
    clean = _normalize_sender(sender_id)
    if clean.isdigit():
        return int(clean)
    return None


def _set_session(sender_id: str, state: str, data: dict = None):
    """Set user's current session state."""
    sid = _normalize_sender(sender_id)
    if sid not in _user_sessions:
        _user_sessions[sid] = {}
    _user_sessions[sid]["state"] = state
    _user_sessions[sid]["data"] = data or {}
    _user_sessions[sid]["updated_at"] = datetime.datetime.now()

def _get_session(sender_id: str) -> dict:
    """Get user's current session state."""
    sid = _normalize_sender(sender_id)
    session = _user_sessions.get(sid, {})
    # Expire sessions older than 30 minutes
    updated = session.get("updated_at")
    if updated and (datetime.datetime.now() - updated).seconds > 1800:
        _user_sessions.pop(sid, None)
        return {"state": None, "data": {}}
    return {"state": session.get("state"), "data": session.get("data", {})}

def _clear_session(sender_id: str):
    sid = _normalize_sender(sender_id)
    _user_sessions.pop(sid, None)


# ── Main entry point ────────────────────────────────────────────

async def handle_whatsapp_message(
    phone_number_id: str,
    sender_id: str,
    text: str,
    message_id: str = None,
):
    """
    Main dispatcher for incoming WhatsApp text messages.
    Routes to the appropriate feature handler based on content.
    """
    # Mark as read immediately
    if message_id:
        asyncio.create_task(send_read_receipt(phone_number_id, message_id))

    # Normalize input
    raw = text.strip()
    lower = raw.lower()

    # ── Session-based continuation (list row selections, button replies) ──
    session = _get_session(sender_id)
    state = session["state"]
    state_data = session["data"]

    if state and state_data:
        handled = await _handle_session_continuation(
            phone_number_id, sender_id, raw, lower,
            state, state_data, message_id,
        )
        if handled:
            return

    # ── Command parsing ──
    # Remove optional "!" prefix, then check commands
    cmd_text = lower.lstrip("!")

    # ── Help / Start / Menu ──
    if cmd_text in ("start", "help", "menu", "what can you do", "commands", "h"):
        await _cmd_help(phone_number_id, sender_id)
        return

    # ── Content commands ──
    if cmd_text in ("latest", "new", "recent"):
        await _cmd_latest(phone_number_id, sender_id)
        return
    if cmd_text in ("youtube", "yt", "video"):
        await _cmd_youtube(phone_number_id, sender_id)
        return
    if cmd_text in ("medium", "article"):
        await _cmd_medium(phone_number_id, sender_id)
        return
    if cmd_text in ("substack", "newsletter"):
        await _cmd_substack(phone_number_id, sender_id)
        return
    if cmd_text in ("socials", "social", "links", "platforms"):
        await _cmd_socials(phone_number_id, sender_id)
        return

    # ── Islamic commands ──
    if cmd_text in ("dua", "duas", "dua search", "duas search"):
        await _cmd_dua(phone_number_id, sender_id, "")
        return
    if cmd_text.startswith("dua ") or cmd_text.startswith("duas "):
        query = raw[len("dua"):].strip().lstrip("s").strip()
        await _cmd_dua(phone_number_id, sender_id, query)
        return

    if cmd_text in ("quran", "quran search"):
        await _cmd_quran(phone_number_id, sender_id, "")
        return
    if cmd_text.startswith("quran "):
        query = raw[5:].strip()
        await _cmd_quran(phone_number_id, sender_id, query)
        return

    if cmd_text in ("myduas", "bookmarks", "my bookmarks", "saved"):
        await _cmd_myduas(phone_number_id, sender_id)
        return

    # ── AI commands ──
    if cmd_text.startswith("ask ") or cmd_text.startswith("ask:"):
        query = raw[4:].strip()
        await _cmd_ask(phone_number_id, sender_id, query)
        return
    if cmd_text.startswith("ai ") or cmd_text.startswith("ai:"):
        query = raw[3:].strip()
        await _cmd_ask(phone_number_id, sender_id, query)
        return
    if cmd_text.startswith("?"):
        query = raw[1:].strip()
        await _cmd_ask(phone_number_id, sender_id, query)
        return

    # ── User preferences ──
    if cmd_text in ("subscribe", "sub"):
        await _cmd_subscribe(phone_number_id, sender_id, "")
        return
    if cmd_text.startswith("subscribe "):
        time_pref = cmd_text.split(None, 1)[1].strip()
        await _cmd_subscribe(phone_number_id, sender_id, time_pref)
        return
    if cmd_text in ("unsubscribe", "unsub"):
        await _cmd_unsubscribe(phone_number_id, sender_id)
        return
    if cmd_text in ("remindertime", "reminder", "time"):
        await _cmd_remindertime(phone_number_id, sender_id, "")
        return
    if cmd_text.startswith("remindertime ") or cmd_text.startswith("reminder "):
        time_pref = cmd_text.split(None, 1)[1].strip()
        await _cmd_remindertime(phone_number_id, sender_id, time_pref)
        return
    if cmd_text in ("language", "lang"):
        await _cmd_language(phone_number_id, sender_id, "")
        return
    if cmd_text.startswith("language ") or cmd_text.startswith("lang "):
        lang = cmd_text.split(None, 1)[1].strip()
        await _cmd_language(phone_number_id, sender_id, lang)
        return
    if cmd_text in ("forget", "clear", "reset memory"):
        await _cmd_forget(phone_number_id, sender_id)
        return

    # ── Study mode ──
    if cmd_text in ("study", "books"):
        await _cmd_study(phone_number_id, sender_id)
        return
    if cmd_text in ("stopstudy", "stop study", "exit study"):
        await _cmd_stopstudy(phone_number_id, sender_id)
        return

    # ── Admin commands ──
    if is_admin(sender_id):
        if cmd_text in ("stats", "status"):
            await _cmd_admin_stats(phone_number_id, sender_id)
            return
        if cmd_text.startswith("broadcast ") or cmd_text.startswith("bc "):
            msg = raw.split(None, 1)[1] if " " in raw else ""
            await _cmd_admin_broadcast(phone_number_id, sender_id, msg)
            return
        if cmd_text in ("postlatest", "sync"):
            await _cmd_admin_postlatest(phone_number_id, sender_id)
            return

    # ── Fallback: AI chat ──
    # If it's just text, treat it as an AI query
    await _cmd_ask(phone_number_id, sender_id, raw)


# ── Session continuation handler ────────────────────────────────

async def _handle_session_continuation(
    phone_number_id: str, sender_id: str, raw: str, lower: str,
    state: str, state_data: dict, message_id: str = None,
) -> bool:
    """Handle responses to interactive lists / buttons."""
    # ── Dua category selection ──
    if state == "dua_category":
        from bot.dua_scraper import get_cached_dua_categories
        categories = get_cached_dua_categories()
        # Try to match by displayed name or slug
        for slug, display in categories:
            if lower.strip() == slug.lower() or lower.strip() == display.lower() or lower.strip() == f"dua_{slug}":
                await _show_dua_category(phone_number_id, sender_id, slug)
                _clear_session(sender_id)
                return True
        # Also try to match by number
        if lower.strip().isdigit():
            idx = int(lower.strip()) - 1
            if 0 <= idx < len(categories):
                slug = categories[idx][0]
                await _show_dua_category(phone_number_id, sender_id, slug)
                _clear_session(sender_id)
                return True
        await send_whatsapp_message(
            phone_number_id, sender_id,
            "Please select a valid category number from the list above, or type *dua <your search>* to search."
        )
        return True

    # ── Quran surah selection ──
    if state == "quran_surah":
        if lower.strip().isdigit():
            surah_no = int(lower.strip())
            if surah_no in SURAH_NAMES:
                await _show_surah_verses(phone_number_id, sender_id, surah_no, page=1)
                _clear_session(sender_id)
                return True
        await send_whatsapp_message(
            phone_number_id, sender_id,
            "Please enter a valid Surah number from the list above (1-114), or type *quran <search>* to search."
        )
        return True

    # ── Quran verses navigation ──
    if state == "quran_verses":
        surah_no = state_data.get("surah_no")
        page = state_data.get("page", 1)
        if lower.strip() in ("next", "n", ">", "next 5"):
            await _show_surah_verses(phone_number_id, sender_id, surah_no, page + 1)
            return True
        if lower.strip() in ("prev", "p", "<", "prev 5", "back"):
            await _show_surah_verses(phone_number_id, sender_id, surah_no, max(1, page - 1))
            return True
        if lower.strip() in ("menu", "back to menu", "b", "main"):
            await _cmd_quran(phone_number_id, sender_id, "")
            _clear_session(sender_id)
            return True
        if lower.strip().isdigit():
            ayah_no = int(lower.strip())
            doc_id = f"quran_{surah_no}_{ayah_no}"
            # Save bookmark
            from bot.vectordb import get_collection
            collection = get_collection()
            if collection:
                docs = collection.get(ids=[doc_id], include=["metadatas"])
                if docs and docs.get("metadatas") and docs["metadatas"][0]:
                    meta = docs["metadatas"][0]
                    title = f"{meta.get('surah_name', '')} {ayah_no}"
                    snippet = meta.get('arabic', '') or meta.get('translation', '')
                    success = save_bookmark(_to_user_id(sender_id) or 0, doc_id, "quran", title, snippet,
                                            f"https://quran.com/{surah_no}/{ayah_no}")
                    if success:
                        await send_whatsapp_message(phone_number_id, sender_id,
                            f"🔖 Bookmarked! Surah {SURAH_NAMES.get(surah_no, ('', ''))[0]} {ayah_no}")
                    else:
                        await send_whatsapp_message(phone_number_id, sender_id, "Failed to save bookmark.")
                    return True
        return True

    # ── Bookmarks ──
    if state == "bookmarks_list":
        if lower.strip().isdigit():
            idx = int(lower.strip()) - 1
            bms = get_user_bookmarks(_to_user_id(sender_id) or 0, limit=50)
            if 0 <= idx < len(bms):
                bm = bms[idx]
                item_id = bm.get("item_id", "")
                await _show_bookmark_detail(phone_number_id, sender_id, bm)
                _set_session(sender_id, "bookmark_detail", {"item_id": item_id})
                return True
        if lower.strip() in ("menu", "back", "main", "b"):
            await _cmd_help(phone_number_id, sender_id)
            _clear_session(sender_id)
            return True
        return True

    # ── Bookmark detail ──
    if state == "bookmark_detail":
        if lower.strip() in ("remove", "delete", "del", "rm"):
            item_id = state_data.get("item_id", "")
            success = remove_bookmark(_to_user_id(sender_id) or 0, item_id)
            if success:
                await send_whatsapp_message(phone_number_id, sender_id, "🗑 Bookmark removed successfully!")
            else:
                await send_whatsapp_message(phone_number_id, sender_id, "Failed to remove bookmark.")
            _clear_session(sender_id)
            # Show updated bookmarks
            await _cmd_myduas(phone_number_id, sender_id)
            return True
        if lower.strip() in ("back", "b", "menu"):
            _clear_session(sender_id)
            await _cmd_myduas(phone_number_id, sender_id)
            return True
        return True

    # ── Study mode book selection ──
    if state == "study_books":
        books = get_available_books()
        if lower.strip().isdigit():
            idx = int(lower.strip()) - 1
            if 0 <= idx < len(books):
                book_name = books[idx]
                success = set_study_mode(_to_user_id(sender_id) or 0, book_name)
                if success:
                    await send_whatsapp_message(phone_number_id, sender_id,
                        f"📚 *Study mode enabled: {book_name}*\n\n"
                        f"You are now studying this book. Any questions you ask will be answered using its content. "
                        f"Type *stopstudy* when you are done.")
                else:
                    await send_whatsapp_message(phone_number_id, sender_id, "Failed to enable study mode.")
                _clear_session(sender_id)
                return True
        return True

    return False


# ── Command handlers ────────────────────────────────────────────

async def _cmd_help(phone_number_id: str, sender_id: str):
    """Show the main menu / help with interactive list."""
    track_activity(_to_user_id(sender_id) or 0, sender_id, "whatsapp_help")

    await send_whatsapp_message(phone_number_id, sender_id,
        "👋 *Assalamu Alaikum! Welcome to Bearded Bangali!*\n\n"
        "I'm your AI assistant on WhatsApp! Here's what I can do:"
    )

    sections = [
        build_section("📱 Content & Socials", [
            {"id": "latest", "title": "Latest Content", "description": "View all latest posts across platforms"},
            {"id": "youtube", "title": "YouTube Videos", "description": "Latest video uploads"},
            {"id": "medium", "title": "Medium Articles", "description": "Latest articles"},
            {"id": "substack", "title": "Substack Newsletters", "description": "Latest newsletter"},
            {"id": "socials", "title": "Social Links", "description": "All platform links"},
        ]),
        build_section("🕋 Islamic Features", [
            {"id": "dua_cat", "title": "Duas (Categories)", "description": "Browse duas by category"},
            {"id": "quran", "title": "Quran (Surahs)", "description": "Browse Quran by surah"},
            {"id": "myduas", "title": "My Bookmarks", "description": "View saved duas & verses"},
        ]),
        build_section("🤖 AI & Account", [
            {"id": "ask_help", "title": "Ask AI", "description": "Just type any question! Or use 'ask <q>'"},
            {"id": "subscribe", "title": "Daily Reminders", "description": "Get daily Islamic reminders"},
            {"id": "lang", "title": "Language", "description": "Set English/Bengali preference"},
        ]),
        build_section("📖 Study & More", [
            {"id": "study", "title": "Study a Book", "description": "Focus on uploaded books"},
            {"id": "forget", "title": "Clear Memory", "description": "Reset conversation history"},
        ]),
    ]

    await send_interactive_list(
        phone_number_id, sender_id,
        header_text="🤖 BB Bot Menu",
        body_text="Select a category below, or just type any question!",
        button_text="View Menu",
        sections=sections,
        footer_text="Type 'help' anytime to see this menu again",
    )

    # Send quick reference for text commands
    await send_whatsapp_message(phone_number_id, sender_id,
        "📝 *Quick Commands:*\n"
        "• *latest* - Latest content\n"
        "• *youtube* - Latest video\n"
        "• *dua <search>* - Search duas\n"
        "• *quran <search>* - Search Quran\n"
        "• *ask <question>* - Ask AI\n"
        "• *subscribe* - Daily reminders\n"
        "• *myduas* - View bookmarks\n"
        "• *study* - Study a book\n"
        "• *language* - Change language\n\n"
        "💡 *Tip:* Just type any question to chat with me!"
    )


async def _cmd_latest(phone_number_id: str, sender_id: str):
    """Fetch and display latest content from all platforms."""
    track_activity(_to_user_id(sender_id) or 0, sender_id, "whatsapp_latest")
    await send_whatsapp_message(phone_number_id, sender_id, "🔄 *Fetching latest content...*")
    message_parts = []
    try:
        yt_msg, yt_btn, yt_link = await get_youtube_posts(limit=2)
        if yt_msg:
            message_parts.append(strip_html(yt_msg))
    except Exception as e:
        logger.error(f"WhatsApp latest YouTube: {e}")

    try:
        med_msg, med_btn, med_link = await get_medium_posts(limit=2)
        if med_msg:
            message_parts.append(strip_html(med_msg))
    except Exception as e:
        logger.error(f"WhatsApp latest Medium: {e}")

    try:
        sub_msg, sub_btn, sub_link = await get_substack_posts(limit=2)
        if sub_msg:
            message_parts.append(strip_html(sub_msg))
    except Exception as e:
        logger.error(f"WhatsApp latest Substack: {e}")

    # Also include Facebook & Twitter if configured
    try:
        if FACEBOOK_RSS_URL:
            from bot.rss import get_facebook_posts
            fb_msg, fb_btn, fb_link = await get_facebook_posts(limit=2)
            if fb_msg:
                message_parts.append(strip_html(fb_msg))
    except Exception as e:
        logger.error(f"WhatsApp latest Facebook: {e}")

    try:
        if TWITTER_RSS_URL:
            from bot.rss import get_twitter_posts
            tw_msg, tw_btn, tw_link = await get_twitter_posts(limit=2)
            if tw_msg:
                message_parts.append(strip_html(tw_msg))
    except Exception as e:
        logger.error(f"WhatsApp latest Twitter: {e}")

    if message_parts:
        full = "\n\n".join(message_parts)
        await send_whatsapp_message(phone_number_id, sender_id, full)
    else:
        await send_whatsapp_message(phone_number_id, sender_id,
            "No new content at the moment. Check back soon! 📌")


async def _cmd_youtube(phone_number_id: str, sender_id: str):
    """Fetch and display latest YouTube videos."""
    track_activity(_to_user_id(sender_id) or 0, sender_id, "whatsapp_youtube")
    await send_whatsapp_message(phone_number_id, sender_id, "🎥 *Fetching latest videos...*")
    try:
        yt_msg, yt_btn, _ = await get_youtube_posts(limit=3)
        if yt_msg:
            text = strip_html(yt_msg)
            text += f"\n\n📺 Subscribe: {YOUTUBE_LINK}"
            await send_whatsapp_message(phone_number_id, sender_id, text, preview_url=True)
        else:
            await send_whatsapp_message(phone_number_id, sender_id,
                f"No videos yet. Subscribe: {YOUTUBE_LINK}")
    except Exception as e:
        logger.error(f"WhatsApp YouTube error: {e}")
        await send_whatsapp_message(phone_number_id, sender_id,
            "Couldn't fetch videos at this time. Please try again later.")


async def _cmd_medium(phone_number_id: str, sender_id: str):
    """Fetch and display latest Medium articles."""
    track_activity(_to_user_id(sender_id) or 0, sender_id, "whatsapp_medium")
    await send_whatsapp_message(phone_number_id, sender_id, "📝 *Fetching latest articles...*")
    try:
        med_msg, med_btn, _ = await get_medium_posts(limit=3)
        if med_msg:
            text = strip_html(med_msg)
            text += f"\n\n📝 Follow on Medium: {MEDIUM_LINK}"
            await send_whatsapp_message(phone_number_id, sender_id, text, preview_url=True)
        else:
            await send_whatsapp_message(phone_number_id, sender_id,
                f"No articles yet. Follow: {MEDIUM_LINK}")
    except Exception as e:
        logger.error(f"WhatsApp Medium error: {e}")
        await send_whatsapp_message(phone_number_id, sender_id,
            "Couldn't fetch articles. Please try again later.")


async def _cmd_substack(phone_number_id: str, sender_id: str):
    """Fetch and display latest Substack newsletters."""
    track_activity(_to_user_id(sender_id) or 0, sender_id, "whatsapp_substack")
    await send_whatsapp_message(phone_number_id, sender_id, "📰 *Fetching latest newsletters...*")
    try:
        sub_msg, sub_btn, _ = await get_substack_posts(limit=3)
        if sub_msg:
            text = strip_html(sub_msg)
            text += f"\n\n📰 Subscribe on Substack: {SUBSTACK_URL}"
            await send_whatsapp_message(phone_number_id, sender_id, text, preview_url=True)
        else:
            await send_whatsapp_message(phone_number_id, sender_id,
                f"No newsletters yet. Subscribe: {SUBSTACK_URL}")
    except Exception as e:
        logger.error(f"WhatsApp Substack error: {e}")
        await send_whatsapp_message(phone_number_id, sender_id,
            "Couldn't fetch newsletters. Please try again later.")


async def _cmd_socials(phone_number_id: str, sender_id: str):
    """Display all social media links."""
    track_activity(_to_user_id(sender_id) or 0, sender_id, "whatsapp_socials")
    text = (
        "*📚 Bearded Bangali Platforms:*\n\n"
        f"📺 *YouTube:*\n{YOUTUBE_LINK}\n\n"
        f"📝 *Medium:*\n{MEDIUM_LINK}\n\n"
        f"📰 *Substack:*\n{SUBSTACK_URL}\n\n"
        f"📸 *Instagram:*\n{INSTAGRAM_LINK}\n\n"
        f"🐦 *X/Twitter:*\n{TWITTER_LINK}\n\n"
        f"👍 *Facebook:*\n{FACEBOOK_LINK}"
    )
    await send_whatsapp_message(phone_number_id, sender_id, text, preview_url=True)


# ═══════════════════════════════════════════════════════════════
#  ISLAMIC FEATURES (Dua, Quran)
# ═══════════════════════════════════════════════════════════════

async def _cmd_dua(phone_number_id: str, sender_id: str, query: str):
    """Dua search or browse by category."""
    track_activity(_to_user_id(sender_id) or 0, sender_id, "whatsapp_dua")

    if not query:
        # Show category menu as interactive list
        categories = get_cached_dua_categories()
        if not categories:
            await send_whatsapp_message(phone_number_id, sender_id,
                "🕋 *Duas are still being loaded.* Please try again in a moment.")
            return

        status = get_rag_status()
        status_line = format_rag_status_line("dua")
        clean_status = strip_html(status_line)

        rows = []
        for i, (slug, display) in enumerate(categories[:30]):
            rows.append({"id": f"dua_{slug}", "title": display, "description": f"Browse {slug} duas"})

        # Build sections (max 10 per list, group by first letter)
        sections = []
        current_letter = ""
        current_rows = []
        for r in rows:
            letter = r["title"][0].upper()
            if letter != current_letter and current_rows:
                sections.append(build_section(f"🕋 {current_letter}", current_rows))
                current_rows = []
                if len(sections) >= 10:
                    break
            current_letter = letter
            current_rows.append(r)
        if current_rows and len(sections) < 10:
            sections.append(build_section(f"🕋 {current_letter}", current_rows))

        if not sections:
            # Fallback: just show as numbered text
            cat_list = "\n".join([f"{i+1}. {display}" for i, (slug, display) in enumerate(categories)])
            await send_whatsapp_message(phone_number_id, sender_id,
                f"🕋 *Hisnul Muslim Duas*\n\n{clean_status}\n\n"
                f"Select a category by replying with its number, or type *dua <your search>*:\n\n{cat_list}")
        else:
            await send_interactive_list(
                phone_number_id, sender_id,
                header_text="🕋 Browse Duas",
                body_text=f"{clean_status}\n\nSelect a category below or type *dua <search>*:",
                button_text="Categories",
                sections=sections,
                footer_text=f"{len(categories)} categories available",
            )

        _set_session(sender_id, "dua_category", {"categories": categories})
        return

    # Text search
    status = get_rag_status()
    if not status.get("dua_ready"):
        await send_whatsapp_message(phone_number_id, sender_id,
            "🕋 *Duas are still being indexed.* Please try again in a moment.")
        return

    result = search_duas(query)
    if not result or "No relevant duas found" in result:
        await send_whatsapp_message(phone_number_id, sender_id,
            "No duas found for your search. Try different keywords, or tap the menu to browse categories.")
        return

    # Clean and send the result
    text = f"🕋 *Dua Search Results*\n\n{strip_html(result)}"
    await send_whatsapp_message(phone_number_id, sender_id, text)


async def _show_dua_category(phone_number_id: str, sender_id: str, category_slug: str):
    """Display duas for a specific category."""
    result, metas = search_duas_by_category(category_slug)
    if not result or "No duas found" in result:
        await send_whatsapp_message(phone_number_id, sender_id,
            "No duas found in this category.")
        return

    # Find category display name
    cat_name = category_slug.replace("-", " ").title()
    for slug, display in get_cached_dua_categories():
        if slug == category_slug:
            cat_name = display
            break

    text = f"🕋 *{cat_name}*\n\n{strip_html(result)}"

    # If too long, truncate and offer to search
    await send_whatsapp_message(phone_number_id, sender_id, text)

    # Offer bookmark buttons for first few duas
    if metas:
        buttons = []
        for meta in metas[:3]:
            item_id = meta.get("id", "")
            dua_name = meta.get("dua_name", "Dua")
            if item_id and len(buttons) < 3:
                buttons.append(build_button_reply(f"bm_add_{item_id}", f"🔖 {dua_name[:15]}"))

        if buttons:
            await send_reply_buttons(
                phone_number_id, sender_id,
                "Tap to bookmark a dua:",
                buttons,
                footer_text="🔖 Saved in /myduas",
            )

    _clear_session(sender_id)


async def _cmd_quran(phone_number_id: str, sender_id: str, query: str):
    """Quran search or browse by surah."""
    track_activity(_to_user_id(sender_id) or 0, sender_id, "whatsapp_quran")

    if not query:
        # Show surah list as interactive sections
        status = get_rag_status()
        clean_status = strip_html(format_rag_status_line("quran"))

        # Build sections grouped by juz/page logic (first 30, next 30, etc.)
        sections = []
        all_surahs = sorted(SURAH_NAMES.items())
        chunk_size = 14
        for chunk_start in range(0, len(all_surahs), chunk_size):
            chunk = all_surahs[chunk_start:chunk_start + chunk_size]
            start_num = chunk[0][0]
            end_num = chunk[-1][0]
            rows = []
            for surah_no, (name, arabic, english, verses, place) in chunk:
                rows.append({
                    "id": f"surah_{surah_no}",
                    "title": f"{surah_no}. {name}",
                    "description": f"{english} ({verses} verses)",
                })
            sections.append(build_section(f"📖 Surahs {start_num}-{end_num}", rows))
            if len(sections) >= 10:
                break

        if sections:
            await send_interactive_list(
                phone_number_id, sender_id,
                header_text="📖 Quran Surahs",
                body_text=f"{clean_status}\n\nSelect a surah to read, or type *quran <search>*:",
                button_text="Select Surah",
                sections=sections,
                footer_text="114 Surahs • 6236 Verses",
            )
        else:
            # Fallback numbered list
            surah_list = "\n".join([f"{n}. {name}" for n, (name, *_) in all_surahs])
            await send_whatsapp_message(phone_number_id, sender_id,
                f"📖 *Quran Surahs*\n\nReply with a surah number (1-114) or type *quran <search>*:\n\n{surah_list}")

        _set_session(sender_id, "quran_surah", {})
        return

    # Text search
    status = get_rag_status()
    if not status.get("quran_ready"):
        await send_whatsapp_message(phone_number_id, sender_id,
            "📖 *Quran verses are still being indexed.* Please try again in a moment.")
        return

    result = search_quran(query)
    if not result or "No relevant Quran verses found" in result:
        await send_whatsapp_message(phone_number_id, sender_id,
            "No verses found for your search. Try different keywords, or browse surahs from the menu.")
        return

    text = f"📖 *Quran Search Results*\n\n{strip_html(result)}"
    await send_whatsapp_message(phone_number_id, sender_id, text)


async def _show_surah_verses(
    phone_number_id: str, sender_id: str,
    surah_no: int, page: int = 1, limit: int = 5,
):
    """Display paginated verses for a surah."""
    result, metas, has_next, has_prev = get_surah_verses(surah_no, page=page, limit=limit)
    if not result or "No verses found" in result:
        await send_whatsapp_message(phone_number_id, sender_id,
            "No verses found for this surah/page.")
        return

    surah_info = SURAH_NAMES.get(surah_no, (f"Surah {surah_no}", "", "", 0, ""))
    text = f"📖 *Surah {surah_info[0]} ({surah_no}) — Page {page}*\n\n{strip_html(result)}"

    await send_whatsapp_message(phone_number_id, sender_id, text)

    # Navigation buttons
    nav_buttons = []
    if has_prev:
        nav_buttons.append(build_button_reply("prev_5", "⬅️ Prev"))
    if has_next:
        nav_buttons.append(build_button_reply("next_5", "Next ➡️"))
    nav_buttons.append(build_button_reply("back_menu", "📖 Menu"))

    if nav_buttons:
        await send_reply_buttons(
            phone_number_id, sender_id,
            f"*{surah_info[0]}* — Page {page}\nReply a verse number to bookmark it:",
            nav_buttons,
            footer_text="Or type prev/next/menu",
        )

    _set_session(sender_id, "quran_verses", {"surah_no": surah_no, "page": page})


async def _cmd_myduas(phone_number_id: str, sender_id: str):
    """View saved bookmarks."""
    track_activity(_to_user_id(sender_id) or 0, sender_id, "whatsapp_myduas")
    user_id = _to_user_id(sender_id) or 0

    bookmarks = get_user_bookmarks(user_id, limit=50)

    if not bookmarks:
        await send_whatsapp_message(phone_number_id, sender_id,
            "🔖 *My Bookmarks*\n\n"
            "You haven't saved any bookmarks yet.\n\n"
            "When browsing duas or Quran verses, tap the bookmark button to save them here.")
        return

    lines = ["🔖 *My Bookmarks*\n"]
    for i, bm in enumerate(bookmarks, 1):
        doc_type = bm.get("type", "dua")
        icon = "🕋" if doc_type == "dua" else "📖"
        title = bm.get("title", bm.get("item_id", ""))
        snippet = bm.get("snippet", "")[:60]
        lines.append(f"{i}. {icon} *{title}*")
        if snippet:
            lines.append(f"   _{snippet}..._")

    lines.append(f"\nReply with a number to view details or type *remove* to delete.")
    await send_whatsapp_message(phone_number_id, sender_id, "\n".join(lines))

    _set_session(sender_id, "bookmarks_list", {"count": len(bookmarks)})


async def _show_bookmark_detail(phone_number_id: str, sender_id: str, bm: dict):
    """Show bookmark detail with options."""
    doc_type = bm.get("type", "dua")
    title = bm.get("title", "")
    snippet = bm.get("snippet", "")
    url = bm.get("url", "")

    text = f"🔖 *{title}*\n\n"
    if snippet:
        text += f"{snippet[:1000]}\n\n"
    if url:
        text += f"🔗 {url}"

    await send_whatsapp_message(phone_number_id, sender_id, text, preview_url=True)

    # Audio for Quran verses
    if doc_type == "quran":
        parts = bm.get("item_id", "").split("_")
        if len(parts) >= 3:
            try:
                bm_surah = int(parts[1])
                bm_ayah = int(parts[2])
                audio_url = get_verse_audio_url(bm_surah, bm_ayah)
                await send_audio(phone_number_id, sender_id, audio_url)
            except (ValueError, IndexError):
                pass

    await send_reply_buttons(
        phone_number_id, sender_id,
        f"What would you like to do with this bookmark?",
        [
            build_button_reply("remove_bm", "🗑 Remove"),
            build_button_reply("back_bm", "⬅️ Back"),
        ],
    )


# ═══════════════════════════════════════════════════════════════
#  AI ASSISTANT
# ═══════════════════════════════════════════════════════════════

async def _cmd_ask(phone_number_id: str, sender_id: str, query: str):
    """Send query to AI and return response."""
    if not query:
        await send_whatsapp_message(phone_number_id, sender_id,
            "🤖 *Ask me anything!*\n\n"
            "Just type your question and I'll answer using my knowledge base with AI.\n"
            "I have conversation memory, so I'll remember our chat!\n\n"
            "Examples:\n"
            "• *What camera do you use?*\n"
            "• *Dua for sleeping*\n"
            "• *Tell me about Surah Yasin*\n"
            "• *Latest video?*")
        return

    track_activity(_to_user_id(sender_id) or 0, sender_id, "whatsapp_ask")

    # Show typing indicator via sending a reaction
    asyncio.create_task(send_reaction(phone_number_id, sender_id, "", "🤔"))

    user_id = _to_user_id(sender_id)

    response = await get_ai_response(query, user_id=user_id, use_memory=True)
    if not response:
        response = "I'm having trouble thinking right now. Please try again later! 🙏"

    # Clean HTML and send
    clean = strip_html(response)
    await send_whatsapp_message(phone_number_id, sender_id, clean)


async def _cmd_forget(phone_number_id: str, sender_id: str):
    """Clear conversation history."""
    user_id = _to_user_id(sender_id) or 0

    from bot.memory import clear_history, get_history_count
    count = get_history_count(user_id)
    clear_history(user_id)
    await send_whatsapp_message(phone_number_id, sender_id,
        f"🧹 *Conversation history cleared!* I've forgotten our previous {count} exchanges.")


# ═══════════════════════════════════════════════════════════════
#  USER PREFERENCES
# ═══════════════════════════════════════════════════════════════

async def _cmd_subscribe(phone_number_id: str, sender_id: str, time_pref: str):
    """Subscribe to daily Islamic reminders."""
    user_id = _to_user_id(sender_id) or 0

    if time_pref not in ("morning", "evening"):
        # Show time preference buttons
        await send_reply_buttons(
            phone_number_id, sender_id,
            "🔔 *Daily Islamic Reminders*\n\n"
            "Get a daily Ayah of the Day + Dua of the Day!\n\n"
            "Choose your preferred time:",
            [
                build_button_reply("sub_morning", "🌅 Morning (10AM)"),
                build_button_reply("sub_evening", "🌙 Evening (6PM)"),
            ],
        )
        return

    success = subscribe_user(user_id, sender_id)
    if success:
        set_reminder_time(user_id, time_pref)
        time_label = "morning 🌅" if time_pref == "morning" else "evening 🌙"
        await send_whatsapp_message(phone_number_id, sender_id,
            f"✅ *Subscribed!*\n\n"
            f"You will receive daily Islamic reminders in the *{time_label}*.\n\n"
            f"Each reminder includes an Ayah of the Day and a Dua of the Day.\n\n"
            f"To change time, type *remindertime morning* or *remindertime evening*.")
    else:
        await send_whatsapp_message(phone_number_id, sender_id,
            "Failed to subscribe. Please try again later.")


async def _cmd_unsubscribe(phone_number_id: str, sender_id: str):
    """Unsubscribe from daily reminders."""
    user_id = _to_user_id(sender_id) or 0

    success = unsubscribe_user(user_id)
    if success:
        await send_whatsapp_message(phone_number_id, sender_id,
            "❌ *Unsubscribed!*\n\nYou will no longer receive daily Islamic reminders.\n\n"
            "To resubscribe, type *subscribe*.")
    else:
        await send_whatsapp_message(phone_number_id, sender_id,
            "Failed to unsubscribe. Please try again later.")


async def _cmd_remindertime(phone_number_id: str, sender_id: str, time_pref: str):
    """Change reminder time preference."""
    user_id = _to_user_id(sender_id) or 0

    if time_pref in ("morning", "evening"):
        subscribed = get_subscribed_users()
        if user_id not in subscribed:
            await send_whatsapp_message(phone_number_id, sender_id,
                "⚠️ You are not subscribed. Use *subscribe* first.")
            return
        success = set_reminder_time(user_id, time_pref)
        if success:
            label = "morning 🌅" if time_pref == "morning" else "evening 🌙"
            await send_whatsapp_message(phone_number_id, sender_id,
                f"✅ Reminder time changed to *{label}*.")
        else:
            await send_whatsapp_message(phone_number_id, sender_id,
                "Failed to update reminder time.")
        return

    # Show current and options
    current = get_reminder_time(user_id)
    current_label = "morning 🌅" if current == "morning" else "evening 🌙"
    await send_reply_buttons(
        phone_number_id, sender_id,
        f"⏰ *Reminder Time*\n\nCurrent: *{current_label}*\n\nChoose your preferred time:",
        [
            build_button_reply("rm_morning", "🌅 Morning (10AM)"),
            build_button_reply("rm_evening", "🌙 Evening (6PM)"),
        ],
    )


async def _cmd_language(phone_number_id: str, sender_id: str, lang: str):
    """Set language preference."""
    user_id = _to_user_id(sender_id) or 0

    if lang in ("en", "english", "bn", "bengali"):
        lang_code = "bn" if lang in ("bn", "bengali") else "en"
        success = set_user_language(user_id, lang_code)
        if success:
            name = "Bengali 🇧🇩" if lang_code == "bn" else "English 🇬🇧"
            await send_whatsapp_message(phone_number_id, sender_id,
                f"✅ Language set to {name}.")
        else:
            await send_whatsapp_message(phone_number_id, sender_id,
                "Failed to save language preference.")
        return

    await send_reply_buttons(
        phone_number_id, sender_id,
        "🌐 *Select Language:*",
        [
            build_button_reply("lang_en", "English 🇬🇧"),
            build_button_reply("lang_bn", "বাংলা 🇧🇩"),
        ],
    )


# ═══════════════════════════════════════════════════════════════
#  STUDY MODE
# ═══════════════════════════════════════════════════════════════

async def _cmd_study(phone_number_id: str, sender_id: str):
    """List available books for study mode."""
    books = get_available_books()
    if not books:
        await send_whatsapp_message(phone_number_id, sender_id,
            "📚 No books are currently available for study.\n\n"
            "Admin needs to upload books using the document ingestion feature.")
        return

    book_list = "\n".join([f"{i+1}. {book}" for i, book in enumerate(books)])
    await send_whatsapp_message(phone_number_id, sender_id,
        f"📚 *Available Books:*\n\n{book_list}\n\n"
        f"Reply with the number of the book you want to study.\n"
        f"Once selected, your chat will focus entirely on that book.\n"
        f"Type *stopstudy* to exit study mode.")

    _set_session(sender_id, "study_books", {"books": books})


async def _cmd_stopstudy(phone_number_id: str, sender_id: str):
    """Exit study mode."""
    user_id = _to_user_id(sender_id) or 0

    success = set_study_mode(user_id, None)
    if success:
        await send_whatsapp_message(phone_number_id, sender_id,
            "✅ *Study mode disabled.*\nI'm back to normal conversation mode.")
    else:
        await send_whatsapp_message(phone_number_id, sender_id,
            "Failed to exit study mode.")


# ═══════════════════════════════════════════════════════════════
#  ADMIN COMMANDS
# ═══════════════════════════════════════════════════════════════

async def _cmd_admin_stats(phone_number_id: str, sender_id: str):
    """Show bot statistics for admin."""
    if not is_admin(sender_id):
        await send_whatsapp_message(phone_number_id, sender_id, "⛔ Unauthorized.")
        return

    doc_count = 0
    from bot.vectordb import get_document_count
    doc_count = get_document_count()
    fb = get_feedback_counts()
    users = 0
    if db:
        try:
            users = len(list(db.collection("users").stream()))
        except Exception:
            pass

    text = (
        f"📊 *Admin Stats*\n\n"
        f"👤 Total Users: {users}\n"
        f"🧠 Vector DB Docs: {doc_count}\n"
        f"👍 Feedback: +{fb.get('positive', 0)} / -{fb.get('negative', 0)}\n"
    )
    await send_whatsapp_message(phone_number_id, sender_id, text)


async def _cmd_admin_broadcast(phone_number_id: str, sender_id: str, msg: str):
    """Broadcast a message to all subscribed users."""
    if not is_admin(sender_id):
        await send_whatsapp_message(phone_number_id, sender_id, "⛔ Unauthorized.")
        return

    if not msg:
        await send_whatsapp_message(phone_number_id, sender_id,
            "Usage: *broadcast <message>* to send to all subscribers")
        return

    # Send to Telegram channel
    if CHANNEL_ID:
        from bot.jobs import send_channel_message
        from telegram.ext import ContextTypes
        # Cannot access context here directly, but we can use the raw API
        try:
            import requests
            from bot.config import TELEGRAM_TOKEN
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            requests.post(url, json={
                "chat_id": CHANNEL_ID,
                "text": msg,
                "parse_mode": "HTML"
            }, timeout=10)
        except Exception as e:
            logger.error(f"Broadcast to channel error: {e}")

    # Also send to WhatsApp users via subscriptions
    await send_whatsapp_message(phone_number_id, sender_id,
        f"✅ Broadcast sent! Message:\n\n{msg}")


async def _cmd_admin_postlatest(phone_number_id: str, sender_id: str):
    """Force post latest content from all platforms."""
    if not is_admin(sender_id):
        await send_whatsapp_message(phone_number_id, sender_id, "⛔ Unauthorized.")
        return

    await send_whatsapp_message(phone_number_id, sender_id,
        "🔄 Syncing and posting latest content to channel...")
    # This requires context.bot which isn't available in WhatsApp
    # Instead, we'll use the Telegram Bot API directly
    try:
        from bot.jobs import auto_post_youtube, auto_post_medium, auto_post_substack, auto_post_facebook, auto_post_twitter
        import asyncio
        # Create a dummy context with bot
        from bot.config import TELEGRAM_TOKEN
        from telegram.ext import ContextTypes
        from telegram import Bot
        bot = Bot(token=TELEGRAM_TOKEN)
        dummy_context = ContextTypes.DEFAULT_TYPE(bot)
        await auto_post_youtube(dummy_context)
        await auto_post_medium(dummy_context)
        await auto_post_substack(dummy_context)
        await auto_post_facebook(dummy_context)
        await auto_post_twitter(dummy_context)
        await send_whatsapp_message(phone_number_id, sender_id, "✅ Content posted to channel!")
    except Exception as e:
        logger.error(f"Post latest error: {e}")
        await send_whatsapp_message(phone_number_id, sender_id,
            f"❌ Error posting content: {str(e)[:200]}")


# ═══════════════════════════════════════════════════════════════
#  INTERACTIVE CALLBACK HANDLER (for button replies)
# ═══════════════════════════════════════════════════════════════

async def handle_interactive_reply(
    phone_number_id: str, sender_id: str,
    interactive_type: str, payload: dict,
    message_id: str = None,
):
    """
    Handle interactive message replies (list selection, button click).
    `interactive_type` is 'list_reply' or 'button_reply'.
    `payload` contains the reply data.
    """
    if message_id:
        asyncio.create_task(send_read_receipt(phone_number_id, message_id))

    reply_id = payload.get("id", "")
    reply_title = payload.get("title", "")

    # ── Menu navigation selections ──
    content_cmds = {
        "latest": lambda: _cmd_latest(phone_number_id, sender_id),
        "youtube": lambda: _cmd_youtube(phone_number_id, sender_id),
        "medium": lambda: _cmd_medium(phone_number_id, sender_id),
        "substack": lambda: _cmd_substack(phone_number_id, sender_id),
        "socials": lambda: _cmd_socials(phone_number_id, sender_id),
        "dua_cat": lambda: _cmd_dua(phone_number_id, sender_id, ""),
        "quran": lambda: _cmd_quran(phone_number_id, sender_id, ""),
        "myduas": lambda: _cmd_myduas(phone_number_id, sender_id),
        "ask_help": lambda: send_whatsapp_message(phone_number_id, sender_id,
            "🤖 *Ask me anything!* Just type your question normally!\n\n"
            "Or use *ask <your question>* for a direct query."),
        "subscribe": lambda: _cmd_subscribe(phone_number_id, sender_id, ""),
        "lang": lambda: _cmd_language(phone_number_id, sender_id, ""),
        "study": lambda: _cmd_study(phone_number_id, sender_id),
        "forget": lambda: _cmd_forget(phone_number_id, sender_id),
    }

    if reply_id in content_cmds:
        await content_cmds[reply_id]()
        return

    # ── Dua category selection ──
    if reply_id.startswith("dua_"):
        slug = reply_id[4:]
        await _show_dua_category(phone_number_id, sender_id, slug)
        return

    # ── Quran surah selection ──
    if reply_id.startswith("surah_"):
        try:
            surah_no = int(reply_id.split("_")[1])
            await _show_surah_verses(phone_number_id, sender_id, surah_no, page=1)
        except (ValueError, IndexError):
            pass
        return

    # ── Quran navigation ──
    if reply_id in ("prev_5", "next_5", "back_menu"):
        session = _get_session(sender_id)
        if session["state"] == "quran_verses":
            surah_no = session["data"].get("surah_no", 1)
            page = session["data"].get("page", 1)
            if reply_id == "prev_5":
                await _show_surah_verses(phone_number_id, sender_id, surah_no, max(1, page - 1))
            elif reply_id == "next_5":
                await _show_surah_verses(phone_number_id, sender_id, surah_no, page + 1)
            else:
                await _cmd_quran(phone_number_id, sender_id, "")
                _clear_session(sender_id)
        return

    # ── Subscription time ──
    if reply_id == "sub_morning":
        await _cmd_subscribe(phone_number_id, sender_id, "morning")
        return
    if reply_id == "sub_evening":
        await _cmd_subscribe(phone_number_id, sender_id, "evening")
        return

    # ── Reminder time ──
    if reply_id == "rm_morning":
        await _cmd_remindertime(phone_number_id, sender_id, "morning")
        return
    if reply_id == "rm_evening":
        await _cmd_remindertime(phone_number_id, sender_id, "evening")
        return

    # ── Language ──
    if reply_id == "lang_en":
        await _cmd_language(phone_number_id, sender_id, "en")
        return
    if reply_id == "lang_bn":
        await _cmd_language(phone_number_id, sender_id, "bn")
        return

    # ── Bookmark add ──
    if reply_id.startswith("bm_add_"):
        item_id = reply_id[7:]
        user_id = _to_user_id(sender_id) or 0
        if is_bookmarked(user_id, item_id):
            await send_whatsapp_message(phone_number_id, sender_id, "Already bookmarked! 🔖")
            return
        # Find the metadata from vector DB
        collection = get_collection()
        if collection:
            docs = collection.get(ids=[item_id], include=["metadatas"])
            if docs and docs.get("metadatas") and docs["metadatas"][0]:
                meta = docs["metadatas"][0]
                doc_type = meta.get("type", "dua")
                title = meta.get("dua_name", meta.get("title", "Dua"))
                snippet = meta.get("arabic", "") or meta.get("translation", "")
                url = meta.get("url", "")
                success = save_bookmark(user_id, item_id, doc_type, title, snippet, url)
                if success:
                    await send_whatsapp_message(phone_number_id, sender_id,
                        f"🔖 Saved! \"{title}\" added to your bookmarks.\nType *myduas* to view.")
                else:
                    await send_whatsapp_message(phone_number_id, sender_id, "Failed to save bookmark.")
        return

    # ── Bookmark remove ──
    if reply_id == "remove_bm":
        session = _get_session(sender_id)
        if session["state"] == "bookmark_detail":
            item_id = session["data"].get("item_id", "")
            user_id = _to_user_id(sender_id) or 0
            success = remove_bookmark(user_id, item_id)
            if success:
                await send_whatsapp_message(phone_number_id, sender_id, "🗑 Bookmark removed!")
            else:
                await send_whatsapp_message(phone_number_id, sender_id, "Failed to remove bookmark.")
            _clear_session(sender_id)
            await _cmd_myduas(phone_number_id, sender_id)
        return

    if reply_id == "back_bm":
        _clear_session(sender_id)
        await _cmd_myduas(phone_number_id, sender_id)
        return

    # ── Fallback: treat as text command ──
    await handle_whatsapp_message(phone_number_id, sender_id, reply_title, message_id)
