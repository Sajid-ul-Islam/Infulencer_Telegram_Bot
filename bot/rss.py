import html
import httpx
import feedparser
from telegram import InlineKeyboardButton
from bot.config import logger, YOUTUBE_CHANNEL_ID, YOUTUBE_LINK, MEDIUM_USERNAME, MEDIUM_LINK

async def get_youtube_posts(limit=3, return_url_only=False):
    """Fetch latest YouTube videos"""
    try:
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={YOUTUBE_CHANNEL_ID}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(rss_url)
            feed = feedparser.parse(response.content)
            
        if feed.entries:
            if return_url_only:
                return feed.entries[0].link

            message = "🎥 <b>Latest Videos:</b>\n\n"
            for i, entry in enumerate(feed.entries[:limit]):
                safe_title = html.escape(entry.title)
                message += f"{i+1}. <b>{safe_title}</b>\n<a href='{entry.link}'>Watch Now</a>\n\n"
            
            button = InlineKeyboardButton("View Channel 📺", url=YOUTUBE_LINK)
            return message.strip(), button, feed.entries[0].link
    except Exception as e:
        logger.error(f"Error fetching YouTube: {e}")
    
    if return_url_only: return None
    return None, None, None

async def get_medium_posts(limit=3, return_url_only=False):
    """Fetch latest Medium articles"""
    try:
        rss_url = f"https://medium.com/feed/@{MEDIUM_USERNAME}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(rss_url)
            feed = feedparser.parse(response.content)
            
        if feed.entries:
            if return_url_only:
                return feed.entries[0].link

            message = "📝 <b>Latest Articles:</b>\n\n"
            for i, entry in enumerate(feed.entries[:limit]):
                safe_title = html.escape(entry.title)
                message += f"{i+1}. <b>{safe_title}</b>\n<a href='{entry.link}'>Read Now</a>\n\n"
            
            button = InlineKeyboardButton("View Profile 📝", url=MEDIUM_LINK)
            return message.strip(), button, feed.entries[0].link
    except Exception as e:
        logger.error(f"Error fetching Medium: {e}")
    
    if return_url_only: return None
    return None, None, None
