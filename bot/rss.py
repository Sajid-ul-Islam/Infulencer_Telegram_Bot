import html
import httpx
import feedparser
from telegram import InlineKeyboardButton
from bot.config import logger, YOUTUBE_CHANNEL_ID, YOUTUBE_LINK, MEDIUM_USERNAME, MEDIUM_LINK, SUBSTACK_URL, FACEBOOK_LINK, FACEBOOK_RSS_URL, TWITTER_LINK, TWITTER_RSS_URL

async def extract_article_text(url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            content = response.text
    except Exception as e:
        logger.error(f"extract_article_text fetch error: {e}")
        return f"Failed to fetch {url}: {e}"
    import re
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

async def get_youtube_posts(limit=3, return_url_only=False, random_old=False):
    """Fetch latest YouTube videos"""
    try:
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={YOUTUBE_CHANNEL_ID}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(rss_url)
            feed = feedparser.parse(response.content)
            
        if feed.entries:
            if return_url_only:
                return feed.entries[0].link

            if random_old and len(feed.entries) > 1:
                import random
                entries_to_use = random.sample(feed.entries[1:], min(limit, len(feed.entries) - 1))
                message = "🎥 <b>Throwback Video:</b>\n\n"
            else:
                entries_to_use = feed.entries[:limit]
                message = "🎥 <b>Latest Videos:</b>\n\n"

            for i, entry in enumerate(entries_to_use):
                safe_title = html.escape(entry.title)
                message += f"{i+1}. <b>{safe_title}</b>\n<a href='{entry.link}'>Watch Now</a>\n\n"
            
            button = InlineKeyboardButton("View Channel 📺", url=YOUTUBE_LINK)
            return message.strip(), button, entries_to_use[0].link
    except Exception as e:
        logger.error(f"Error fetching YouTube: {e}")
    
    if return_url_only: return None
    return None, None, None

async def get_medium_posts(limit=3, return_url_only=False, random_old=False):
    """Fetch latest Medium articles"""
    try:
        rss_url = f"https://medium.com/feed/@{MEDIUM_USERNAME}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(rss_url)
            feed = feedparser.parse(response.content)
            
        if feed.entries:
            if return_url_only:
                return feed.entries[0].link

            if random_old and len(feed.entries) > 1:
                import random
                entries_to_use = random.sample(feed.entries[1:], min(limit, len(feed.entries) - 1))
                message = "📝 <b>Throwback Article:</b>\n\n"
            else:
                entries_to_use = feed.entries[:limit]
                message = "📝 <b>Latest Articles:</b>\n\n"

            for i, entry in enumerate(entries_to_use):
                safe_title = html.escape(entry.title)
                message += f"{i+1}. <b>{safe_title}</b>\n<a href='{entry.link}'>Read Now</a>\n\n"
            
            button = InlineKeyboardButton("View Profile 📝", url=MEDIUM_LINK)
            return message.strip(), button, entries_to_use[0].link
    except Exception as e:
        logger.error(f"Error fetching Medium: {e}")
    
    if return_url_only: return None
    return None, None, None

async def get_substack_posts(limit=3, return_url_only=False, random_old=False):
    """Fetch latest Substack newsletters"""
    try:
        # Substack RSS feed is always base_url/feed
        rss_url = f"{SUBSTACK_URL.rstrip('/')}/feed"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(rss_url)
            feed = feedparser.parse(response.content)
            
        if feed.entries:
            if return_url_only:
                return feed.entries[0].link

            if random_old and len(feed.entries) > 1:
                import random
                entries_to_use = random.sample(feed.entries[1:], min(limit, len(feed.entries) - 1))
                message = "📰 <b>Throwback Newsletter:</b>\n\n"
            else:
                entries_to_use = feed.entries[:limit]
                message = "📰 <b>Latest Newsletters:</b>\n\n"

            for i, entry in enumerate(entries_to_use):
                safe_title = html.escape(entry.title)
                message += f"{i+1}. <b>{safe_title}</b>\n<a href='{entry.link}'>Read Issue</a>\n\n"
            
            button = InlineKeyboardButton("Subscribe on Substack 📰", url=SUBSTACK_URL)
            return message.strip(), button, entries_to_use[0].link
    except Exception as e:
        logger.error(f"Error fetching Substack: {e}")
    
    if return_url_only: return None
    return None, None, None

async def get_facebook_posts(limit=3, return_url_only=False, random_old=False):
    """Fetch latest Facebook posts from configured RSS url"""
    if not FACEBOOK_RSS_URL:
        logger.warning("FACEBOOK_RSS_URL not configured. Skipping Facebook RSS fetch.")
        if return_url_only: return None
        return None, None, None
        
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(FACEBOOK_RSS_URL)
            feed = feedparser.parse(response.content)
            
        if feed.entries:
            if return_url_only:
                return feed.entries[0].link

            if random_old and len(feed.entries) > 1:
                import random
                entries_to_use = random.sample(feed.entries[1:], min(limit, len(feed.entries) - 1))
                message = "👍 <b>Throwback Facebook Post:</b>\n\n"
            else:
                entries_to_use = feed.entries[:limit]
                message = "👍 <b>Latest Facebook Posts:</b>\n\n"

            for i, entry in enumerate(entries_to_use):
                # Fallback to summary or description if title is too short or generic
                title = entry.title
                if not title or len(title) < 5:
                    title = entry.summary or entry.description or "New Post"
                
                # Strip HTML tags from title for clean display
                import re
                clean_title = re.sub(r'<[^>]+>', '', title)
                clean_title = re.sub(r'\s+', ' ', clean_title).strip()
                if len(clean_title) > 60:
                    clean_title = clean_title[:60] + "..."
                
                safe_title = html.escape(clean_title)
                message += f"{i+1}. <b>{safe_title}</b>\n<a href='{entry.link}'>View Post</a>\n\n"
            
            button = InlineKeyboardButton("View Facebook Page 👍", url=FACEBOOK_LINK)
            return message.strip(), button, entries_to_use[0].link
    except Exception as e:
        logger.error(f"Error fetching Facebook RSS: {e}")
    
    if return_url_only: return None
    return None, None, None

async def get_twitter_posts(limit=3, return_url_only=False, random_old=False):
    """Fetch latest Twitter/X posts from configured RSS url"""
    if not TWITTER_RSS_URL:
        logger.warning("TWITTER_RSS_URL not configured. Skipping Twitter RSS fetch.")
        if return_url_only: return None
        return None, None, None
        
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(TWITTER_RSS_URL)
            feed = feedparser.parse(response.content)
            
        if feed.entries:
            if return_url_only:
                return feed.entries[0].link

            if random_old and len(feed.entries) > 1:
                import random
                entries_to_use = random.sample(feed.entries[1:], min(limit, len(feed.entries) - 1))
                message = "🐦 <b>Throwback Tweet:</b>\n\n"
            else:
                entries_to_use = feed.entries[:limit]
                message = "🐦 <b>Latest Tweets:</b>\n\n"

            for i, entry in enumerate(entries_to_use):
                title = entry.title
                if not title or len(title) < 5:
                    title = entry.summary or entry.description or "New Tweet"
                
                # Strip HTML tags
                import re
                clean_title = re.sub(r'<[^>]+>', '', title)
                clean_title = re.sub(r'\s+', ' ', clean_title).strip()
                if len(clean_title) > 60:
                    clean_title = clean_title[:60] + "..."
                
                safe_title = html.escape(clean_title)
                message += f"{i+1}. <b>{safe_title}</b>\n<a href='{entry.link}'>View Tweet</a>\n\n"
            
            button = InlineKeyboardButton("View Twitter Page 🐦", url=TWITTER_LINK)
            return message.strip(), button, entries_to_use[0].link
    except Exception as e:
        logger.error(f"Error fetching Twitter RSS: {e}")
    
    if return_url_only: return None
    return None, None, None


async def check_and_sync_rss_manually():
    """Manually fetches latest YouTube, Medium, and Substack entries and broadcasts to channel if new."""
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

    posts_sent = 0

    # Sync YouTube
    try:
        yt_msg, yt_btn, link = await get_youtube_posts(limit=1)
        if yt_msg and link and link != bot.jobs.last_posted_youtube_url:
            reply_markup = {"inline_keyboard": [[{"text": yt_btn.text, "url": yt_btn.url}]]} if yt_btn else None
            if await send_tg_message(yt_msg, reply_markup):
                bot.jobs.last_posted_youtube_url = link
                posts_sent += 1
                logger.info(f"Manual Sync: Posted YouTube video: {link}")
    except Exception as e:
        logger.error(f"Error manually syncing YouTube: {e}")

    # Sync Medium
    try:
        med_msg, med_btn, link = await get_medium_posts(limit=1)
        if med_msg and link and link != bot.jobs.last_posted_medium_url:
            reply_markup = {"inline_keyboard": [[{"text": med_btn.text, "url": med_btn.url}]]} if med_btn else None
            if await send_tg_message(med_msg, reply_markup):
                bot.jobs.last_posted_medium_url = link
                posts_sent += 1
                logger.info(f"Manual Sync: Posted Medium article: {link}")
    except Exception as e:
        logger.error(f"Error manually syncing Medium: {e}")

    # Sync Substack
    try:
        sub_msg, sub_btn, link = await get_substack_posts(limit=1)
        if sub_msg and link and link != bot.jobs.last_posted_substack_url:
            reply_markup = {"inline_keyboard": [[{"text": sub_btn.text, "url": sub_btn.url}]]} if sub_btn else None
            if await send_tg_message(sub_msg, reply_markup):
                bot.jobs.last_posted_substack_url = link
                posts_sent += 1
                logger.info(f"Manual Sync: Posted Substack newsletter: {link}")
    except Exception as e:
        logger.error(f"Error manually syncing Substack: {e}")

    # Sync Facebook
    try:
        fb_msg, fb_btn, link = await get_facebook_posts(limit=1)
        if fb_msg and link and link != bot.jobs.last_posted_facebook_url:
            reply_markup = {"inline_keyboard": [[{"text": fb_btn.text, "url": fb_btn.url}]]} if fb_btn else None
            if await send_tg_message(fb_msg, reply_markup):
                bot.jobs.last_posted_facebook_url = link
                posts_sent += 1
                logger.info(f"Manual Sync: Posted Facebook post: {link}")
    except Exception as e:
        logger.error(f"Error manually syncing Facebook: {e}")

    # Sync Twitter
    try:
        tw_msg, tw_btn, link = await get_twitter_posts(limit=1)
        if tw_msg and link and link != bot.jobs.last_posted_twitter_url:
            reply_markup = {"inline_keyboard": [[{"text": tw_btn.text, "url": tw_btn.url}]]} if tw_btn else None
            if await send_tg_message(tw_msg, reply_markup):
                bot.jobs.last_posted_twitter_url = link
                posts_sent += 1
                logger.info(f"Manual Sync: Posted Twitter tweet: {link}")
    except Exception as e:
        logger.error(f"Error manually syncing Twitter: {e}")

    return posts_sent
