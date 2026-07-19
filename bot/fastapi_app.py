import os
import time
import json
import logging
import asyncio
import requests
import random
from datetime import datetime
from fastapi import FastAPI, Depends, Request, HTTPException, Response, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

from telegram import Update
from telegram.ext import Application as PTBApplication

from bot.config import (
    logger, DASHBOARD_PASSWORD, TELEGRAM_TOKEN, CHANNEL_ID, GROUP_ID, META_VERIFY_TOKEN
)

# Global reference to the python-telegram-bot Application instance.
# Set from main.py after building the application.
ptb_application: PTBApplication | None = None
from bot.database import (
    FAQ, save_faq, remove_faq, db, get_feedback_counts, 
    get_trending_searches, get_token_usage_stats, get_user_retention_stats
)
from bot.pipeline import get_pipeline_stats
from bot.utils import ping_history, START_TIME, memory_log_handler
from bot.rss import check_and_sync_rss_manually

app = FastAPI(title="BB Bot HUB Admin")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiter for login attempts: {ip: (attempts, first_attempt_time)}
_login_attempts: dict[str, tuple[int, float]] = {}
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_WINDOW_SECONDS = 300  # 5 minutes


def _check_login_rate_limit(ip: str) -> bool:
    """Returns True if the IP is allowed to attempt login."""
    now = time.time()
    if ip in _login_attempts:
        count, first_time = _login_attempts[ip]
        if now - first_time > _LOGIN_WINDOW_SECONDS:
            _login_attempts[ip] = (1, now)
            return True
        if count >= _LOGIN_MAX_ATTEMPTS:
            return False
        _login_attempts[ip] = (count + 1, first_time)
        return True
    _login_attempts[ip] = (1, now)
    return True


def check_auth(request: Request):
    if not DASHBOARD_PASSWORD:
        raise HTTPException(status_code=503, detail="Dashboard password not configured")
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Unauthorized")
    token = auth_header.split(" ")[1]
    if token != DASHBOARD_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True

@app.get("/healthz")
async def healthz():
    """Lightweight health check endpoint used by the startup readiness poller."""
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    with open("templates/dashboard.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/webhook")
async def telegram_webhook(request: Request):
    """
    Receive incoming Telegram updates via webhook.
    Parses the JSON payload, creates an Update object, and queues it
    for processing by the python-telegram-bot application.
    Always returns 200 OK per Telegram's requirements.
    """
    global ptb_application
    if ptb_application is None:
        logger.warning("PTB application not ready — dropping incoming update")
        return Response(status_code=200)

    try:
        data = await request.json()
        update = Update.de_json(data, ptb_application.bot)
        if update:
            await ptb_application.update_queue.put(update)
    except Exception as e:
        logger.error(f"Error processing Telegram webhook update: {e}")

    # Always respond 200 — Telegram will retry on non-200 responses
    return Response(status_code=200)

@app.get("/api/meta/webhook")
async def verify_meta_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == META_VERIFY_TOKEN:
            logger.info("Meta Webhook verified successfully!")
            return Response(content=challenge, media_type="text/plain", status_code=200)
        else:
            return Response(status_code=403)
    return Response(status_code=400)

@app.post("/api/meta/webhook")
async def receive_meta_webhook(request: Request):
    from bot.handlers.meta import handle_meta_webhook_payload
    try:
        payload = await request.json()
        # Log webhook receipt with minimal info (don't log full payload to avoid PII leaks)
        object_type = payload.get("object", "unknown")
        entries = len(payload.get("entry", []))
        logger.info(f"Meta webhook POST received — object={object_type}, entries={entries}")
        
        # Quick sanity check: WhatsApp webhooks should have 'entry' list
        if not payload.get("entry"):
            logger.warning(f"Meta webhook payload has no 'entry' list — ignoring")
            return Response(content="EVENT_RECEIVED", status_code=200)
            
        # Run in background to acknowledge Meta quickly (they require a 200 OK within 20 seconds)
        asyncio.create_task(handle_meta_webhook_payload(payload))
        return Response(content="EVENT_RECEIVED", status_code=200)
    except json.JSONDecodeError:
        raw_body = await request.body()
        logger.error(f"Meta webhook received non-JSON body: {raw_body[:200]}")
        return Response(status_code=400)
    except Exception as e:
        logger.error(f"Error handling Meta webhook: {e}")
        return Response(status_code=404)

@app.post("/api/login")
async def login(request: Request):
    if not DASHBOARD_PASSWORD:
        return JSONResponse(
            status_code=503,
            content={"error": "Dashboard password not configured. Set DASHBOARD_PASSWORD environment variable."}
        )

    client_ip = request.client.host if request.client else "unknown"
    if not _check_login_rate_limit(client_ip):
        return JSONResponse(
            status_code=429,
            content={"error": "Too many login attempts. Try again in 5 minutes."}
        )

    data = await request.json()
    password = data.get("password")
    if password == DASHBOARD_PASSWORD:
        # Reset rate limit on successful login
        _login_attempts.pop(client_ip, None)
        return {"token": DASHBOARD_PASSWORD}
    return JSONResponse(status_code=401, content={"error": "Invalid password"})

@app.get("/api/stats", dependencies=[Depends(check_auth)])
async def get_stats():
    uptime_seconds = int(time.time() - START_TIME)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    doc_count = 0
    try:
        from bot.vectordb import get_document_count
        doc_count = get_document_count()
    except Exception:
        pass

    users = 0
    if db:
        try:
            users = len(list(db.collection("users").stream()))
        except Exception:
            pass

    fb = get_feedback_counts()
    
    return {
        "uptime": uptime_str,
        "users": users,
        "vector_docs": doc_count,
        "feedback_likes": fb.get('likes', 0),
        "feedback_dislikes": fb.get('dislikes', 0),
        "pings": list(ping_history)
    }

@app.get("/api/faqs", dependencies=[Depends(check_auth)])
async def get_faqs():
    faqs = []
    if db:
        docs = db.collection("faqs").stream()
        for doc in docs:
            faqs.append({"keyword": doc.id, "response": doc.to_dict().get("response", "")})
    return {"faqs": faqs}

@app.post("/api/faqs", dependencies=[Depends(check_auth)])
async def create_faq(request: Request):
    data = await request.json()
    keyword = data.get("keyword", "").strip()
    response = data.get("response", "").strip()
    if not keyword or not response:
        raise HTTPException(status_code=400, detail="Keyword and response required")
    save_faq(keyword.lower(), response)
    return {"status": "success"}

@app.delete("/api/faqs", dependencies=[Depends(check_auth)])
async def delete_faq(keyword: str):
    if not keyword:
        raise HTTPException(status_code=400, detail="Keyword required")
    remove_faq(keyword.lower())
    return {"status": "success"}

@app.get("/api/suggestions", dependencies=[Depends(check_auth)])
async def get_suggestions():
    suggestions = []
    if db:
        docs = db.collection("suggestions").order_by("timestamp", direction="DESCENDING").limit(50).stream()
        for doc in docs:
            d = doc.to_dict()
            suggestions.append({
                "topic": d.get("topic", ""),
                "username": d.get("username", "Unknown"),
                "date": d.get("timestamp", "")
            })
    return {"suggestions": suggestions}

@app.get("/api/questions", dependencies=[Depends(check_auth)])
async def get_questions():
    questions = []
    if db:
        docs = db.collection("questions").order_by("timestamp", direction="DESCENDING").limit(50).stream()
        for doc in docs:
            d = doc.to_dict()
            questions.append({
                "question": d.get("question", ""),
                "username": d.get("username", "Unknown"),
                "date": d.get("timestamp", "")
            })
    return {"questions": questions}

@app.get("/api/analytics/activity", dependencies=[Depends(check_auth)])
async def get_activity():
    activity = []
    if db:
        docs = db.collection("activity_logs").order_by("timestamp", direction="DESCENDING").limit(100).stream()
        for doc in docs:
            d = doc.to_dict()
            activity.append({
                "action": d.get("action", ""),
                "user": d.get("username", "Unknown"),
                "details": d.get("details", ""),
                "time": d.get("timestamp", "")
            })
    return {"activity": activity}

@app.get("/api/analytics/users", dependencies=[Depends(check_auth)])
async def get_users():
    users = []
    if db:
        docs = db.collection("users").order_by("first_seen", direction="DESCENDING").limit(100).stream()
        for doc in docs:
            d = doc.to_dict()
            users.append({
                "id": doc.id,
                "username": d.get("username", "Unknown"),
                "first_seen": d.get("first_seen", ""),
                "last_interaction": d.get("last_interaction", "")
            })
    return {"users": users}

@app.get("/api/logs", dependencies=[Depends(check_auth)])
async def get_logs():
    return {"logs": list(memory_log_handler.logs)}

@app.get("/api/analytics/trending", dependencies=[Depends(check_auth)])
async def get_trending():
    return get_trending_searches()

@app.get("/api/analytics/tokens", dependencies=[Depends(check_auth)])
async def get_tokens():
    return get_token_usage_stats()

@app.get("/api/analytics/retention", dependencies=[Depends(check_auth)])
async def get_retention():
    return get_user_retention_stats()

@app.post("/api/rss/sync", dependencies=[Depends(check_auth)])
async def sync_rss():
    count = await check_and_sync_rss_manually()
    return {"status": "success", "synced": count}

@app.post("/api/moderation/ban", dependencies=[Depends(check_auth)])
async def ban_user(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID required")
    if not GROUP_ID:
        raise HTTPException(status_code=400, detail="GROUP_ID not configured")
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/banChatMember"
        res = requests.post(url, json={"chat_id": GROUP_ID, "user_id": user_id}, timeout=10)
        if res.status_code == 200:
            return {"status": "success"}
        raise HTTPException(status_code=500, detail=res.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/moderation/mute", dependencies=[Depends(check_auth)])
async def mute_user(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID required")
    if not GROUP_ID:
        raise HTTPException(status_code=400, detail="GROUP_ID not configured")
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/restrictChatMember"
        res = requests.post(url, json={
            "chat_id": GROUP_ID,
            "user_id": user_id,
            "permissions": {"can_send_messages": False}
        }, timeout=10)
        if res.status_code == 200:
            return {"status": "success"}
        raise HTTPException(status_code=500, detail=res.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/moderation/unmute", dependencies=[Depends(check_auth)])
async def unmute_user(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID required")
    if not GROUP_ID:
        raise HTTPException(status_code=400, detail="GROUP_ID not configured")
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/restrictChatMember"
        res = requests.post(url, json={
            "chat_id": GROUP_ID,
            "user_id": user_id,
            "permissions": {
                "can_send_messages": True,
                "can_send_media_messages": True,
                "can_send_polls": True,
                "can_send_other_messages": True,
                "can_add_web_page_previews": True,
                "can_invite_users": True
            }
        }, timeout=10)
        if res.status_code == 200:
            return {"status": "success"}
        raise HTTPException(status_code=500, detail=res.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/broadcast", dependencies=[Depends(check_auth)])
async def broadcast(request: Request):
    data = await request.json()
    msg = data.get("message", "").strip()
    if not msg:
        raise HTTPException(status_code=400, detail="Message required")
    if not TELEGRAM_TOKEN or not CHANNEL_ID:
        raise HTTPException(status_code=500, detail="Bot credentials or channel not configured")
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        res = requests.post(url, json={"chat_id": CHANNEL_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
        if res.status_code == 200:
            return {"status": "success"}
        raise HTTPException(status_code=500, detail=res.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/poll", dependencies=[Depends(check_auth)])
async def create_poll(request: Request):
    data = await request.json()
    question = data.get("question", "").strip()
    options = data.get("options", [])
    if not question or len(options) < 2:
        raise HTTPException(status_code=400, detail="Question and at least 2 options required")
    if not TELEGRAM_TOKEN or not CHANNEL_ID:
        raise HTTPException(status_code=500, detail="Bot credentials not configured")
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPoll"
        res = requests.post(url, json={
            "chat_id": CHANNEL_ID, "question": question, 
            "options": options, "is_anonymous": True
        }, timeout=10)
        if res.status_code == 200:
            return {"status": "success"}
        raise HTTPException(status_code=500, detail=res.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/giveaway/start", dependencies=[Depends(check_auth)])
async def start_giveaway(request: Request):
    data = await request.json()
    prize = data.get("prize", "").strip()
    if not prize:
        raise HTTPException(status_code=400, detail="Prize required")
    if not TELEGRAM_TOKEN or not CHANNEL_ID:
        raise HTTPException(status_code=500, detail="Bot credentials not configured")
    try:
        if db:
            docs = db.collection("giveaway_entries").stream()
            for doc in docs:
                doc.reference.delete()
        message = f"🎉 <b>GIVEAWAY ALERT!</b> 🎉\n\nWe are giving away: <b>{prize}</b>\n\nClick the button below to enter!"
        reply_markup = {"inline_keyboard": [[{"text": "Enter Giveaway 🎁", "callback_data": "enter_giveaway"}]]}
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        res = requests.post(url, json={
            "chat_id": CHANNEL_ID, "text": message, 
            "parse_mode": "HTML", "reply_markup": reply_markup
        }, timeout=10)
        if res.status_code == 200:
            return {"status": "success"}
        raise HTTPException(status_code=500, detail=res.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/giveaway/pick", dependencies=[Depends(check_auth)])
async def pick_giveaway():
    if not db:
        raise HTTPException(status_code=500, detail="Firebase not configured")
    try:
        docs = list(db.collection("giveaway_entries").stream())
        if not docs:
            raise HTTPException(status_code=400, detail="No entries registered yet")
        winner_doc = random.choice(docs)
        winner_data = winner_doc.to_dict()
        winner_name = winner_data.get('username', 'Unknown')
        winner_id = winner_data.get('user_id')
        announcement = (
            f"🎊 <b>GIVEAWAY WINNER!</b> 🎊\n\n"
            f"Congratulations <a href='tg://user?id={winner_id}'>{winner_name}</a>! You have won!\n"
            f"Please DM the admin to claim your prize."
        )
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        res = requests.post(url, json={"chat_id": CHANNEL_ID, "text": announcement, "parse_mode": "HTML"}, timeout=10)
        if res.status_code == 200:
            return {"winner_name": winner_name, "winner_id": winner_id}
        raise HTTPException(status_code=500, detail=res.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/content/recent", dependencies=[Depends(check_auth)])
async def get_recent_content_feeds():
    import feedparser
    import html
    import httpx
    import re
    from bot.config import (
        YOUTUBE_CHANNEL_ID, MEDIUM_USERNAME, SUBSTACK_URL, FACEBOOK_RSS_URL, TWITTER_RSS_URL
    )
    
    platforms = [
        ("youtube", f"https://www.youtube.com/feeds/videos.xml?channel_id={YOUTUBE_CHANNEL_ID}"),
        ("medium", f"https://medium.com/feed/@{MEDIUM_USERNAME}"),
        ("substack", f"{SUBSTACK_URL.rstrip('/')}/feed"),
    ]
    if FACEBOOK_RSS_URL:
        platforms.append(("facebook", FACEBOOK_RSS_URL))
    if TWITTER_RSS_URL:
        platforms.append(("twitter", TWITTER_RSS_URL))
        
    recent_posts = []
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for platform, url in platforms:
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    feed = feedparser.parse(response.content)
                    for entry in feed.entries[:5]:  # get top 5
                        title = entry.title
                        if platform in ["facebook", "twitter"] and (not title or len(title) < 5):
                            title = entry.summary or entry.description or "New Post"
                        
                        clean_title = re.sub(r'<[^>]+>', '', title)
                        clean_title = re.sub(r'\s+', ' ', clean_title).strip()
                        
                        date_str = ""
                        if hasattr(entry, "published"):
                            date_str = entry.published
                        elif hasattr(entry, "updated"):
                            date_str = entry.updated
                            
                        recent_posts.append({
                            "platform": platform,
                            "title": clean_title,
                            "link": entry.link,
                            "date": date_str
                        })
            except Exception as e:
                logger.error(f"Error fetching recent feeds for {platform}: {e}")
                
    return {"posts": recent_posts}

@app.post("/api/content/post", dependencies=[Depends(check_auth)])
async def post_content_to_channel(request: Request):
    data = await request.json()
    platform = data.get("platform")
    title = data.get("title")
    link = data.get("link")
    
    if not platform or not title or not link:
        raise HTTPException(status_code=400, detail="Platform, title, and link are required")
        
    import html
    from bot.config import YOUTUBE_LINK, MEDIUM_LINK, SUBSTACK_URL, FACEBOOK_LINK, TWITTER_LINK
    
    if platform == "youtube":
        btn_text = "Watch Video 🎥"
        emoji = "🎥"
        type_name = "Video"
    elif platform == "medium":
        btn_text = "Read Article 📝"
        emoji = "📝"
        type_name = "Article"
    elif platform == "substack":
        btn_text = "Read Issue 📰"
        emoji = "📰"
        type_name = "Newsletter"
    elif platform == "facebook":
        btn_text = "View Post 👍"
        emoji = "👍"
        type_name = "Facebook Post"
    elif platform == "twitter":
        btn_text = "View Tweet 🐦"
        emoji = "🐦"
        type_name = "Tweet"
    else:
        btn_text = "View Link 🔗"
        emoji = "🔗"
        type_name = "Content"
        
    safe_title = html.escape(title)
    message = (
        f"{emoji} <b>Featured {type_name}: {safe_title}</b>\n\n"
        f"Check out this content from the hub! 👇"
    )
    
    reply_markup = {"inline_keyboard": [[{"text": btn_text, "url": link}]]}
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        res = requests.post(url, json={
            "chat_id": CHANNEL_ID,
            "text": message,
            "parse_mode": "HTML",
            "reply_markup": reply_markup
        }, timeout=10)
        
        if res.status_code == 200:
            if platform == "youtube":
                try:
                    import asyncio
                    from bot.jobs import _transcribe_and_ingest
                    asyncio.create_task(_transcribe_and_ingest(link, None))
                except Exception as ex:
                    logger.error(f"Error starting transcription: {ex}")
            else:
                try:
                    import asyncio
                    from bot.pipeline import ingest_rss_content
                    asyncio.create_task(ingest_rss_content())
                except Exception as ex:
                    logger.error(f"Error starting ingestion: {ex}")
            return {"status": "success"}
            
        raise HTTPException(status_code=500, detail=res.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
