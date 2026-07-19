import re
import html
import random
import httpx
import feedparser
from typing import Optional, Tuple
from telegram import InlineKeyboardButton
from bot.config import (
    logger, YOUTUBE_CHANNEL_ID, YOUTUBE_LINK, MEDIUM_USERNAME, MEDIUM_LINK,
    SUBSTACK_URL, FACEBOOK_LINK, FACEBOOK_RSS_URL, TWITTER_LINK, TWITTER_RSS_URL
)


async def extract_article_text(url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            content = response.text
    except Exception as e:
        logger.error(f"extract_article_text fetch error: {e}")
        return f"Failed to fetch {url}: {e}"
    content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)
    content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL)
    content = re.sub(r'<nav[^>]*>.*?</nav>', '', content, flags=re.DOTALL)
    content = re.sub(r'<footer[^>]*>.*?</footer>', '', content, flags=re.DOTALL)
    content = re.sub(r'<header[^>]*>.*?</header>', '', content, flags=re.DOTALL)
    content = re.sub(r'<[^>]+>', '', content)
    content = re.sub(r'\s+', ' ', content).strip()
    lines = [line.strip() for line in content.split('\n') if line.strip()]
    text = '\n'.join(lines)
    if len(text) > 3000:
        text = text[:3000] + "..."
    return text or f"No readable content found at {url}"


def _clean_title(entry) -> str:
    """Extract and clean a title from an RSS entry, handling short/generic titles."""
    title = entry.title
    if not title or len(title) < 5:
        title = getattr(entry, 'summary', None) or getattr(entry, 'description', None) or "New Post"
    clean = re.sub(r'<[^>]+>', '', title)
    clean = re.sub(r'\s+', ' ', clean).strip()
    if len(clean) > 60:
        clean = clean[:60] + "..."
    return clean


async def _fetch_rss_feed(
    rss_url: str,
    limit: int = 3,
    return_url_only: bool = False,
    random_old: bool = False,
    clean_titles: bool = False,
) -> Optional[Tuple]:
    """Generic RSS feed fetcher. Returns (message, button, first_link) or None.

    Args:
        rss_url: The RSS feed URL to fetch.
        limit: Number of entries to return.
        return_url_only: If True, return only the first entry's URL.
        random_old: If True, skip the first entry and pick randomly from the rest.
        clean_titles: If True, strip HTML and truncate long titles (for Facebook/Twitter).
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(rss_url)
            feed = feedparser.parse(response.content)

        if not feed.entries:
            return None

        if return_url_only:
            return feed.entries[0].link

        if random_old and len(feed.entries) > 1:
            entries_to_use = random.sample(feed.entries[1:], min(limit, len(feed.entries) - 1))
        else:
            entries_to_use = feed.entries[:limit]

        return entries_to_use, clean_titles
    except Exception as e:
        logger.error(f"Error fetching RSS feed {rss_url}: {e}")
        return None


def _build_rss_message(
    entries: list,
    emoji: str,
    latest_label: str,
    throwback_label: str,
    action_text: str,
    is_random: bool,
    clean_titles: bool = False,
) -> str:
    """Build a formatted message from RSS entries."""
    label = throwback_label if is_random else latest_label
    message = f"{emoji} <b>{label}</b>\n\n"
    for i, entry in enumerate(entries):
        if clean_titles:
            title = html.escape(_clean_title(entry))
        else:
            title = html.escape(entry.title)
        message += f"{i+1}. <b>{title}</b>\n<a href='{entry.link}'>{action_text}</a>\n\n"
    return message.strip()


# ── Platform-specific wrappers ──────────────────────────────────

async def get_youtube_posts(limit=3, return_url_only=False, random_old=False):
    """Fetch latest YouTube videos."""
    result = await _fetch_rss_feed(
        f"https://www.youtube.com/feeds/videos.xml?channel_id={YOUTUBE_CHANNEL_ID}",
        limit=limit, return_url_only=return_url_only, random_old=random_old,
    )
    if result is None:
        if return_url_only:
            return None
        return None, None, None
    if return_url_only:
        return result
    entries, _ = result
    message = _build_rss_message(entries, "\U0001f3a5", "Latest Videos", "Throwback Video", "Watch Now", random_old)
    button = InlineKeyboardButton("View Channel \U0001f4fa", url=YOUTUBE_LINK)
    return message, button, entries[0].link


async def get_medium_posts(limit=3, return_url_only=False, random_old=False):
    """Fetch latest Medium articles."""
    result = await _fetch_rss_feed(
        f"https://medium.com/feed/@{MEDIUM_USERNAME}",
        limit=limit, return_url_only=return_url_only, random_old=random_old,
    )
    if result is None:
        if return_url_only:
            return None
        return None, None, None
    if return_url_only:
        return result
    entries, _ = result
    message = _build_rss_message(entries, "\U0001f4dd", "Latest Articles", "Throwback Article", "Read Now", random_old)
    button = InlineKeyboardButton("View Profile \U0001f4dd", url=MEDIUM_LINK)
    return message, button, entries[0].link


async def get_substack_posts(limit=3, return_url_only=False, random_old=False):
    """Fetch latest Substack newsletters."""
    result = await _fetch_rss_feed(
        f"{SUBSTACK_URL.rstrip('/')}/feed",
        limit=limit, return_url_only=return_url_only, random_old=random_old,
    )
    if result is None:
        if return_url_only:
            return None
        return None, None, None
    if return_url_only:
        return result
    entries, _ = result
    message = _build_rss_message(entries, "\U0001f4f0", "Latest Newsletters", "Throwback Newsletter", "Read Issue", random_old)
    button = InlineKeyboardButton("Subscribe on Substack \U0001f4f0", url=SUBSTACK_URL)
    return message, button, entries[0].link


async def get_facebook_posts(limit=3, return_url_only=False, random_old=False):
    """Fetch latest Facebook posts from configured RSS url."""
    if not FACEBOOK_RSS_URL:
        logger.warning("FACEBOOK_RSS_URL not configured. Skipping Facebook RSS fetch.")
        if return_url_only:
            return None
        return None, None, None
    result = await _fetch_rss_feed(
        FACEBOOK_RSS_URL,
        limit=limit, return_url_only=return_url_only, random_old=random_old,
        clean_titles=True,
    )
    if result is None:
        if return_url_only:
            return None
        return None, None, None
    if return_url_only:
        return result
    entries, _ = result
    message = _build_rss_message(entries, "\U0001f44d", "Latest Facebook Posts", "Throwback Facebook Post", "View Post", random_old, clean_titles=True)
    button = InlineKeyboardButton("View Facebook Page \U0001f44d", url=FACEBOOK_LINK)
    return message, button, entries[0].link


async def get_twitter_posts(limit=3, return_url_only=False, random_old=False):
    """Fetch latest Twitter/X posts from configured RSS url."""
    if not TWITTER_RSS_URL:
        logger.warning("TWITTER_RSS_URL not configured. Skipping Twitter RSS fetch.")
        if return_url_only:
            return None
        return None, None, None
    result = await _fetch_rss_feed(
        TWITTER_RSS_URL,
        limit=limit, return_url_only=return_url_only, random_old=random_old,
        clean_titles=True,
    )
    if result is None:
        if return_url_only:
            return None
        return None, None, None
    if return_url_only:
        return result
    entries, _ = result
    message = _build_rss_message(entries, "\U0001f426", "Latest Tweets", "Throwback Tweet", "View Tweet", random_old, clean_titles=True)
    button = InlineKeyboardButton("View Twitter Page \U0001f426", url=TWITTER_LINK)
    return message, button, entries[0].link


# ── Manual sync ─────────────────────────────────────────────────

async def check_and_sync_rss_manually():
    """Manually fetches latest entries from all platforms and broadcasts to channel if new."""
    import bot.jobs
    from bot.config import TELEGRAM_TOKEN, CHANNEL_ID

    async def send_tg_message(text, reply_markup=None):
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": CHANNEL_ID, "text": text, "parse_mode": "HTML"}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload)
            return res.status_code == 200

    platforms = [
        ("YouTube", get_youtube_posts, "last_posted_youtube_url"),
        ("Medium", get_medium_posts, "last_posted_medium_url"),
        ("Substack", get_substack_posts, "last_posted_substack_url"),
        ("Facebook", get_facebook_posts, "last_posted_facebook_url"),
        ("Twitter", get_twitter_posts, "last_posted_twitter_url"),
    ]

    posts_sent = 0
    for name, fetcher, attr in platforms:
        try:
            msg, btn, link = await fetcher(limit=1)
            if msg and link and link != getattr(bot.jobs, attr):
                reply_markup = {"inline_keyboard": [[{"text": btn.text, "url": btn.url}]]} if btn else None
                if await send_tg_message(msg, reply_markup):
                    setattr(bot.jobs, attr, link)
                    posts_sent += 1
                    logger.info(f"Manual Sync: Posted {name}: {link}")
        except Exception as e:
            logger.error(f"Error manually syncing {name}: {e}")

    return posts_sent
