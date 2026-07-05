import asyncio
from typing import Optional
from urllib.parse import quote
from telegram import InlineKeyboardMarkup
from telegram.ext import ContextTypes
from bot.config import logger, CHANNEL_ID, BOT_TZ
from bot.rss import get_youtube_posts, get_medium_posts, get_substack_posts, get_facebook_posts
from bot.pipeline import ingest_rss_content
from bot.transcriber import transcribe_youtube

last_posted_youtube_url = None
last_posted_medium_url = None
last_posted_substack_url = None
last_posted_facebook_url = None

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
            asyncio.create_task(_transcribe_and_ingest(link, context))
        await ingest_rss_content()
    except Exception as e:
        logger.error(f"Error in auto_post_youtube: {e}")

async def _transcribe_and_ingest(url: str, context: ContextTypes.DEFAULT_TYPE):
    try:
        text = await transcribe_youtube(url)
        if text:
            from bot.pipeline import ingest_text_content
            await ingest_text_content(f"Transcription from {url}", text, "youtube_transcript", url)
            logger.info(f"Transcribed and ingested {len(text)} chars from {url}")
    except Exception as e:
        logger.error(f"Transcription+ingest error: {e}")

async def weekly_digest(context: ContextTypes.DEFAULT_TYPE):
    try:
        yt_msg, _, _ = await get_youtube_posts(limit=3)
        med_msg, _, _ = await get_medium_posts(limit=3)
        digest = f"📬 <b>Weekly Digest</b>\n\n{yt_msg or 'No new videos'}\n\n{med_msg or 'No new articles'}"
        await send_channel_message(context, digest)
        logger.info("Weekly digest posted to channel")
    except Exception as e:
        logger.error(f"Weekly digest error: {e}")

async def greeting_post(context: ContextTypes.DEFAULT_TYPE):
    greeting = """
✔️ <b>Assalamu Alaikum!</b>

Welcome to my content hub! 

Find all my latest updates here. Got a question? Just DM the bot!

#Content #Creator
    """
    await send_channel_message(context, greeting)

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

async def auto_post_facebook(context: ContextTypes.DEFAULT_TYPE):
    global last_posted_facebook_url
    try:
        fb_msg, fb_btn, link = await get_facebook_posts(limit=1)
        if fb_msg and link and link != last_posted_facebook_url:
            reply_markup = InlineKeyboardMarkup([[fb_btn]]) if fb_btn else None
            await send_channel_message(context, fb_msg, reply_markup=reply_markup)
            last_posted_facebook_url = link
        await ingest_rss_content()
    except Exception as e:
        logger.error(f"Error in auto_post_facebook: {e}")

async def _pick_random_document(doc_type: str) -> Optional[dict]:
    """Picks a random document of the given type from the vector DB."""
    from bot.vectordb import get_collection
    import random
    try:
        collection = get_collection()
        if not collection:
            return None
        results = collection.get(
            where={"type": doc_type},
            include=["metadatas"],
            limit=100
        )
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
    # Audio + Read more links
    ayah_buttons = []
    if ayah_meta:
        surah_no = ayah_meta.get("surah_no", "")
        ayah_no = ayah_meta.get("ayah_no", "")
        if surah_no and ayah_no:
            # Listen button
            audio_url = get_verse_audio_url(surah_no, ayah_no)
            ayah_buttons.append(
                InlineKeyboardButton(
                    "\u25b6\ufe0f Listen",
                    url=audio_url
                )
            )
            # Read button
            ayah_buttons.append(
                InlineKeyboardButton(
                    "\U0001f4d6 Read",
                    url=f"https://quran.com/{surah_no}/{ayah_no}"
                )
            )
    if dua_meta:
        dua_url = dua_meta.get("url", "")
        if dua_url:
            ayah_buttons.append(
                InlineKeyboardButton(
                    "\U0001f54a View Dua",
                    url=dua_url
                )
            )
    if ayah_buttons:
        buttons.append(ayah_buttons)
    # Share button — only show if we have at least one source to link
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
        buttons.append([
            InlineKeyboardButton(
                "\U0001f4e4 Share",
                url=f"https://t.me/share/url?url={quote(share_url)}&text={quote(share_text)}"
            )
        ])
    return InlineKeyboardMarkup(buttons)


async def daily_islamic_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Sends morning Islamic reminder (ayah + dua) to morning-preference subscribers."""
    from bot.database import get_subscribed_users_by_time
    try:
        users = get_subscribed_users_by_time("morning")
        if not users:
            logger.info("No morning-preference subscribers for daily reminder.")
            return

        ayah_meta = await _pick_random_document("quran")
        dua_meta = await _pick_random_document("dua")

        parts = ["\U0001f4f8 <b>Assalamu Alaikum!</b>\n"]
        ayah_text = _build_ayah_message(ayah_meta) if ayah_meta else ""
        if ayah_text:
            parts.append(ayah_text)
        dua_text = _build_dua_message(dua_meta) if dua_meta else ""
        if dua_text:
            parts.append(dua_text)

        if not ayah_text and not dua_text:
            parts.append(
                "\U0001f4dc <b>Daily Reminder</b>\n\n"
                "May Allah bless you today and always. \U0001f4ff"
            )

        message = "\n\n".join(parts)
        reply_markup = _build_reminder_keyboard(ayah_meta, dua_meta)

        sent_count = 0
        for user_id in users:
            try:
                await context.bot.send_message(
                    chat_id=user_id, text=message, parse_mode="HTML",
                    reply_markup=reply_markup
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send morning reminder to {user_id}: {e}")

        logger.info(f"Sent morning reminders to {sent_count}/{len(users)} users.")
    except Exception as e:
        logger.error(f"Error in daily_islamic_reminder: {e}")


async def evening_islamic_reminder(context: ContextTypes.DEFAULT_TYPE):
    """Sends evening Islamic reminder (ayah + dua) to evening-preference subscribers."""
    from bot.database import get_subscribed_users_by_time
    try:
        users = get_subscribed_users_by_time("evening")
        if not users:
            logger.info("No evening-preference subscribers for evening reminder.")
            return

        ayah_meta = await _pick_random_document("quran")
        dua_meta = await _pick_random_document("dua")

        parts = ["\U0001f31b <b>Assalamu Alaikum — Evening Reminder</b>\n"]
        ayah_text = _build_ayah_message(ayah_meta) if ayah_meta else ""
        if ayah_text:
            parts.append(ayah_text)
        dua_text = _build_dua_message(dua_meta) if dua_meta else ""
        if dua_text:
            parts.append(dua_text)

        if not ayah_text and not dua_text:
            parts.append(
                "\U0001f31b <b>Evening Reminder</b>\n\n"
                "May Allah bless your evening. \U0001f4ff"
            )

        message = "\n\n".join(parts)
        reply_markup = _build_reminder_keyboard(ayah_meta, dua_meta)

        sent_count = 0
        for user_id in users:
            try:
                await context.bot.send_message(
                    chat_id=user_id, text=message, parse_mode="HTML",
                    reply_markup=reply_markup
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send evening reminder to {user_id}: {e}")

        logger.info(f"Sent evening reminders to {sent_count}/{len(users)} users.")
    except Exception as e:
        logger.error(f"Error in evening_islamic_reminder: {e}")


recently_posted_urls = []

async def scheduled_content_hub_post(context: ContextTypes.DEFAULT_TYPE):
    """Periodically posts latest or random content from YouTube, Medium, or Substack every 2 hours."""
    global recently_posted_urls
    
    import random
    import feedparser
    import html
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from bot.config import YOUTUBE_CHANNEL_ID, MEDIUM_USERNAME, SUBSTACK_URL, YOUTUBE_LINK, MEDIUM_LINK, FACEBOOK_LINK, FACEBOOK_RSS_URL
    
    # Select random platform
    platforms = ["youtube", "medium", "substack"]
    if FACEBOOK_RSS_URL:
        platforms.append("facebook")
    random.shuffle(platforms)
    
    # We will try platforms until one succeeded
    for platform in platforms:
        try:
            if platform == "youtube":
                rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={YOUTUBE_CHANNEL_ID}"
                profile_link = YOUTUBE_LINK
                btn_text = "Watch Video 🎥"
                emoji = "🎥"
                type_name = "Video"
            elif platform == "medium":
                rss_url = f"https://medium.com/feed/@{MEDIUM_USERNAME}"
                profile_link = MEDIUM_LINK
                btn_text = "Read Article 📝"
                emoji = "📝"
                type_name = "Article"
            elif platform == "substack":
                rss_url = f"{SUBSTACK_URL.rstrip('/')}/feed"
                profile_link = SUBSTACK_URL
                btn_text = "Read Issue 📰"
                emoji = "📰"
                type_name = "Newsletter"
            else:  # facebook
                rss_url = FACEBOOK_RSS_URL
                profile_link = FACEBOOK_LINK
                btn_text = "View Post 👍"
                emoji = "👍"
                type_name = "Facebook Post"
                
            # Parse feed
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(rss_url)
                feed = feedparser.parse(response.content)
                
            if not feed.entries:
                continue
                
            # Choose mode: latest (70% weight) or random from feed (30% weight)
            mode = random.choices(["latest", "random"], weights=[0.7, 0.3], k=1)[0]
            
            selected_entry = None
            if mode == "latest":
                selected_entry = feed.entries[0]
            else:
                # Try to find a random entry not recently posted
                available_entries = [e for e in feed.entries if e.link not in recently_posted_urls]
                if available_entries:
                    selected_entry = random.choice(available_entries)
                else:
                    selected_entry = feed.entries[0]
                    
            if not selected_entry:
                continue
                
            if platform == "facebook":
                title_text = selected_entry.title
                if not title_text or len(title_text) < 5:
                    title_text = selected_entry.summary or selected_entry.description or "New Post"
                import re
                clean_title = re.sub(r'<[^>]+>', '', title_text)
                clean_title = re.sub(r'\s+', ' ', clean_title).strip()
                if len(clean_title) > 80:
                    clean_title = clean_title[:80] + "..."
                title = html.escape(clean_title)
            else:
                title = html.escape(selected_entry.title)
                
            link = selected_entry.link
            
            # Format message
            message = (
                f"{emoji} <b>Featured {type_name}: {title}</b>\n\n"
                f"Check out this content from the hub! 👇"
            )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(btn_text, url=link)]
            ])
            
            await send_channel_message(context, message, reply_markup=keyboard)
            
            # Add to recently posted tracking
            recently_posted_urls.append(link)
            if len(recently_posted_urls) > 15:
                recently_posted_urls.pop(0)
                
            # If it was youtube, trigger transcription/ingest
            if platform == "youtube":
                asyncio.create_task(_transcribe_and_ingest(link, context))
            else:
                await ingest_rss_content()
                
            logger.info(f"Successfully posted {mode} {platform} entry to channel: {title}")
            break  # Succeeded posting, stop trying other platforms
            
        except Exception as e:
            logger.error(f"Error in scheduled_content_hub_post for {platform}: {e}")
            continue
