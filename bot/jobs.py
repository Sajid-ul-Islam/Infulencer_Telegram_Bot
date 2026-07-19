import asyncio
import datetime
import random
from typing import Optional
from urllib.parse import quote

import feedparser
import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.config import (
    logger, CHANNEL_ID, BOT_TZ,
    YOUTUBE_CHANNEL_ID, YOUTUBE_LINK, MEDIUM_USERNAME, MEDIUM_LINK,
    SUBSTACK_URL, FACEBOOK_LINK, FACEBOOK_RSS_URL, TWITTER_LINK, TWITTER_RSS_URL,
)
from bot.rss import get_youtube_posts, get_medium_posts, get_substack_posts, get_facebook_posts, get_twitter_posts
from bot.pipeline import ingest_rss_content
from bot.transcriber import transcribe_youtube

# ── Platform config for scheduled_content_hub_post ──────────────
_PLATFORM_CONFIG = {
    "youtube": {
        "rss_url": lambda: f"https://www.youtube.com/feeds/videos.xml?channel_id={YOUTUBE_CHANNEL_ID}",
        "profile_link": YOUTUBE_LINK,
        "btn_text": "Watch Video \U0001f3a5",
        "emoji": "\U0001f3a5",
        "type_name": "Video",
    },
    "medium": {
        "rss_url": lambda: f"https://medium.com/feed/@{MEDIUM_USERNAME}",
        "profile_link": MEDIUM_LINK,
        "btn_text": "Read Article \U0001f4dd",
        "emoji": "\U0001f4dd",
        "type_name": "Article",
    },
    "substack": {
        "rss_url": lambda: f"{SUBSTACK_URL.rstrip('/')}/feed",
        "profile_link": SUBSTACK_URL,
        "btn_text": "Read Issue \U0001f4f0",
        "emoji": "\U0001f4f0",
        "type_name": "Newsletter",
    },
    "facebook": {
        "rss_url": lambda: FACEBOOK_RSS_URL,
        "profile_link": FACEBOOK_LINK,
        "btn_text": "View Post \U0001f44d",
        "emoji": "\U0001f44d",
        "type_name": "Facebook Post",
        "clean_title": True,
    },
    "twitter": {
        "rss_url": lambda: TWITTER_RSS_URL,
        "profile_link": TWITTER_LINK,
        "btn_text": "View Tweet \U0001f426",
        "emoji": "\U0001f426",
        "type_name": "Tweet",
        "clean_title": True,
    },
}

# ── State ───────────────────────────────────────────────────────
last_posted_youtube_url = None
last_posted_medium_url = None
last_posted_substack_url = None
last_posted_facebook_url = None
last_posted_twitter_url = None

_recently_posted_urls: dict[str, datetime.datetime] = {}
post_queue: list[dict] = []


def queue_channel_message(text: str, reply_markup=None):
    post_queue.append({"text": text, "reply_markup": reply_markup})
    logger.info(f"Queued message for channel. Queue size: {len(post_queue)}")


async def process_post_queue(context: ContextTypes.DEFAULT_TYPE):
    if post_queue:
        post = post_queue.pop(0)
        logger.info(f"Processing queued post. Remaining: {len(post_queue)}")
        await send_channel_message(context, post["text"], reply_markup=post["reply_markup"])


async def send_channel_message(context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None):
    if not CHANNEL_ID:
        logger.warning("CHANNEL_ID not set. Skipping channel broadcast.")
    else:
        try:
            await context.bot.send_message(
                chat_id=CHANNEL_ID, text=text, parse_mode="HTML", reply_markup=reply_markup
            )
            logger.info(f"Message sent to channel: {text[:50]}")
        except Exception as e:
            logger.error(f"Error sending to channel: {e}")

    try:
        from bot.database import get_subscribed_users
        users = get_subscribed_users()
        if users:
            logger.info(f"Broadcasting to {len(users)} subscribed users...")
            sent_count = 0
            for user_id in users:
                try:
                    await context.bot.send_message(
                        chat_id=user_id, text=text, parse_mode="HTML", reply_markup=reply_markup
                    )
                    sent_count += 1
                except Exception as e:
                    logger.error(f"Failed to send to user {user_id}: {e}")
                await asyncio.sleep(0.05)
            logger.info(f"Broadcast completed. Sent to {sent_count}/{len(users)} users.")
    except Exception as e:
        logger.error(f"Error in inbox broadcast: {e}")


async def _transcribe_and_ingest(url: str, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = await transcribe_youtube(url)
        if text:
            from bot.pipeline import ingest_text_content
            await ingest_text_content(f"Transcription from {url}", text, "youtube_transcript", url)
            logger.info(f"Transcribed and ingested {len(text)} chars from {url}")
    except Exception as e:
        logger.error(f"Transcription+ingest error: {e}")


# ── Generic auto-post helper ────────────────────────────────────

async def _auto_post_platform(
    name: str,
    fetcher,
    context: ContextTypes.DEFAULT_TYPE,
    transcribe: bool = False,
):
    """Generic auto-post for any platform. Handles dedup, random fallback, and ingestion."""
    global last_posted_youtube_url, last_posted_medium_url
    global last_posted_substack_url, last_posted_facebook_url, last_posted_twitter_url

    url_attr = f"last_posted_{name}_url"
    try:
        msg, btn, link = await fetcher(limit=1)
        if msg and link:
            current_url = globals().get(url_attr)
            if link != current_url:
                reply_markup = InlineKeyboardMarkup([[btn]]) if btn else None
                queue_channel_message(msg, reply_markup=reply_markup)
                globals()[url_attr] = link
                if transcribe:
                    asyncio.create_task(_transcribe_and_ingest(link, context))
            else:
                msg, btn, random_link = await fetcher(limit=1, random_old=True)
                if msg and random_link:
                    reply_markup = InlineKeyboardMarkup([[btn]]) if btn else None
                    queue_channel_message(msg, reply_markup=reply_markup)
        await ingest_rss_content()
    except Exception as e:
        logger.error(f"Error in auto_post_{name}: {e}")


async def auto_post_youtube(context: ContextTypes.DEFAULT_TYPE):
    await _auto_post_platform("youtube", get_youtube_posts, context, transcribe=True)

async def auto_post_medium(context: ContextTypes.DEFAULT_TYPE):
    await _auto_post_platform("medium", get_medium_posts, context)

async def auto_post_substack(context: ContextTypes.DEFAULT_TYPE):
    await _auto_post_platform("substack", get_substack_posts, context)

async def auto_post_facebook(context: ContextTypes.DEFAULT_TYPE):
    await _auto_post_platform("facebook", get_facebook_posts, context)

async def auto_post_twitter(context: ContextTypes.DEFAULT_TYPE):
    await _auto_post_platform("twitter", get_twitter_posts, context)


# ── Scheduled content hub post ──────────────────────────────────

def _clean_title_for_hub(entry, clean: bool = False) -> str:
    """Extract and clean a title for the hub post."""
    title = entry.title
    if not title or len(title) < 5:
        title = getattr(entry, 'summary', None) or getattr(entry, 'description', None) or "New Post"
    if clean:
        import re
        title = re.sub(r'<[^>]+>', '', title)
        title = re.sub(r'\s+', ' ', title).strip()
        if len(title) > 80:
            title = title[:80] + "..."
    return title


async def scheduled_content_hub_post(context: ContextTypes.DEFAULT_TYPE):
    """Periodically posts latest or random content from any configured platform."""
    global _recently_posted_urls

    # Clean up urls older than 24 hours
    now = datetime.datetime.now()
    _recently_posted_urls = {k: v for k, v in _recently_posted_urls.items() if (now - v).total_seconds() < 86400}

    # Build available platforms list
    available = ["youtube", "medium", "substack"]
    if FACEBOOK_RSS_URL:
        available.append("facebook")
    if TWITTER_RSS_URL:
        available.append("twitter")
    random.shuffle(available)

    for platform in available:
        try:
            cfg = _PLATFORM_CONFIG[platform]
            rss_url = cfg["rss_url"]()
            if not rss_url:
                continue

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(rss_url)
                feed = feedparser.parse(response.content)

            if not feed.entries:
                continue

            available_entries = [e for e in feed.entries if e.link not in _recently_posted_urls]
            if not available_entries:
                continue

            mode = random.choices(["latest", "random"], weights=[0.7, 0.3], k=1)[0]
            selected_entry = available_entries[0] if mode == "latest" else random.choice(available_entries)

            title = _clean_title_for_hub(selected_entry, clean=cfg.get("clean_title", False))
            safe_title = html.escape(title)
            link = selected_entry.link

            message = (
                f"{cfg['emoji']} <b>Featured {cfg['type_name']}: {safe_title}</b>\n\n"
                f"Check out this content from the hub! \U0001f447"
            )
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(cfg["btn_text"], url=link)]])

            queue_channel_message(message, reply_markup=keyboard)
            _recently_posted_urls[link] = datetime.datetime.now()

            if platform == "youtube":
                asyncio.create_task(_transcribe_and_ingest(link, context))
            else:
                await ingest_rss_content()

            logger.info(f"Successfully posted {mode} {platform} entry to channel: {title}")
            break
        except Exception as e:
            logger.error(f"Error in scheduled_content_hub_post for {platform}: {e}")
            continue


# ── Islamic reminders ───────────────────────────────────────────

async def _pick_random_document(doc_type: str) -> Optional[dict]:
    from bot.vectordb import get_collection
    try:
        collection = get_collection()
        if not collection:
            return None
        results = collection.get(where={"type": doc_type}, include=["metadatas"], limit=100)
        if results and results.get("metadatas"):
            metas = [m for m in results["metadatas"] if m]
            if metas:
                return random.choice(metas)
    except Exception as e:
        logger.error(f"Error picking random {doc_type}: {e}")
    return None


def _build_ayah_message(ayah_meta: dict) -> str:
    surah = ayah_meta.get("surah_name", "")
    ayah = ayah_meta.get("ayah_no", "")
    arabic = ayah_meta.get("arabic", "")
    translation = ayah_meta.get("translation", "")
    return (
        f"\U0001f4dc <b>Ayah of the Day</b>\n"
        f"<b>{surah} — {ayah}</b>\n\n"
        f"{arabic}\n\n"
        f"<i>{translation}</i>"
    )


def _build_dua_message(dua_meta: dict) -> str:
    name = dua_meta.get("dua_name", dua_meta.get("title", "Dua"))
    arabic = dua_meta.get("arabic", "")
    translation = dua_meta.get("translation", "")
    transliteration = dua_meta.get("transliteration", "")
    reference = dua_meta.get("reference", "")
    parts = [f"\U0001f54a <b>Dua of the Day: {name}</b>"]
    if arabic:
        parts.append(f"\n{arabic}")
    if transliteration:
        parts.append(f"\n{transliteration}")
    if translation:
        parts.append(f"\n<i>{translation}</i>")
    if reference:
        parts.append(f"\n\nSource: {reference}")
    return "\n\n".join(parts)


def _build_reminder_keyboard(ayah_meta: Optional[dict], dua_meta: Optional[dict]) -> InlineKeyboardMarkup:
    from bot.quran_scraper import get_verse_audio_url
    buttons = []
    ayah_buttons = []
    if ayah_meta:
        surah_no = ayah_meta.get("surah_no", "")
        ayah_no = ayah_meta.get("ayah_no", "")
        if surah_no and ayah_no:
            audio_url = get_verse_audio_url(surah_no, ayah_no)
            ayah_buttons.append(InlineKeyboardButton("\u25b6\ufe0f Listen", url=audio_url))
            ayah_buttons.append(InlineKeyboardButton("\U0001f4d6 Read", url=f"https://quran.com/{surah_no}/{ayah_no}"))
    if dua_meta:
        dua_url = dua_meta.get("url", "")
        if dua_url:
            ayah_buttons.append(InlineKeyboardButton("\U0001f54a View Dua", url=dua_url))
    if ayah_buttons:
        buttons.append(ayah_buttons)

    share_url = None
    share_text = ""
    if ayah_meta:
        surah_no = ayah_meta.get("surah_no", "")
        ayah_no = ayah_meta.get("ayah_no", "")
        surah_name = ayah_meta.get("surah_name", "")
        if surah_no and ayah_no:
            share_url = f"https://quran.com/{surah_no}/{ayah_no}"
            share_text = f"Daily Islamic Reminder - {surah_name} {ayah_no}"
    if not share_url and dua_meta:
        dua_url = dua_meta.get("url", "")
        if dua_url:
            share_url = dua_url
            share_text = f"Daily Islamic Reminder - {dua_meta.get('dua_name', 'Dua')}"
    if share_url:
        buttons.append([InlineKeyboardButton(
            "\U0001f4e4 Share",
            url=f"https://t.me/share/url?url={quote(share_url)}&text={quote(share_text)}"
        )])
    return InlineKeyboardMarkup(buttons)


async def _send_reminders(time_pref: str, greeting: str):
    """Send Islamic reminders to subscribers with the given time preference."""
    from bot.database import get_subscribed_users_by_time
    try:
        users = get_subscribed_users_by_time(time_pref)
        if not users:
            logger.info(f"No {time_pref}-preference subscribers for reminder.")
            return

        ayah_meta = await _pick_random_document("quran")
        dua_meta = await _pick_random_document("dua")

        parts = [f"{greeting}\n"]
        ayah_text = _build_ayah_message(ayah_meta) if ayah_meta else ""
        if ayah_text:
            parts.append(ayah_text)
        dua_text = _build_dua_message(dua_meta) if dua_meta else ""
        if dua_text:
            parts.append(dua_text)

        if not ayah_text and not dua_text:
            parts.append(f"\U0001f4dc <b>Daily Reminder</b>\n\nMay Allah bless you today and always. \U0001f4ff")

        message = "\n\n".join(parts)
        reply_markup = _build_reminder_keyboard(ayah_meta, dua_meta)

        sent_count = 0
        for user_id in users:
            try:
                await context.bot.send_message(
                    chat_id=user_id, text=message, parse_mode="HTML", reply_markup=reply_markup
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send {time_pref} reminder to {user_id}: {e}")

        logger.info(f"Sent {time_pref} reminders to {sent_count}/{len(users)} users.")
    except Exception as e:
        logger.error(f"Error in {time_pref}_islamic_reminder: {e}")


async def daily_islamic_reminder(context: ContextTypes.DEFAULT_TYPE):
    await _send_reminders("morning", "\U0001f4f8 <b>Assalamu Alaikum!</b>")


async def evening_islamic_reminder(context: ContextTypes.DEFAULT_TYPE):
    await _send_reminders("evening", "\U0001f31b <b>Assalamu Alaikum — Evening Reminder</b>")


async def weekly_digest(context: ContextTypes.DEFAULT_TYPE):
    try:
        yt_msg, _, _ = await get_youtube_posts(limit=3)
        med_msg, _, _ = await get_medium_posts(limit=3)
        digest = f"\U0001f4ec <b>Weekly Digest</b>\n\n{yt_msg or 'No new videos'}\n\n{med_msg or 'No new articles'}"
        await send_channel_message(context, digest)
        logger.info("Weekly digest posted to channel")
    except Exception as e:
        logger.error(f"Weekly digest error: {e}")


async def greeting_post(context: ContextTypes.DEFAULT_TYPE):
    greeting = """
\u2714\ufe0f <b>Assalamu Alaikum!</b>

Welcome to my content hub! 

Find all my latest updates here. Got a question? Just DM the bot!

#Content #Creator
    """
    await send_channel_message(context, greeting)
