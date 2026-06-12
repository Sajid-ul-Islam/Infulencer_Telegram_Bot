import os
import logging
import shlex
import json
from datetime import datetime, time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import feedparser
import requests
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions
import firebase_admin
from firebase_admin import credentials, firestore
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction
import httpx

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============ CONFIGURATION ============
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
GROUP_ID = os.getenv("GROUP_ID")
ADMIN_ID = os.getenv("ADMIN_ID")
FIREBASE_CREDENTIALS = os.getenv("FIREBASE_CREDENTIALS")
XAI_API_KEY = os.getenv("XAI_API_KEY")

# Initialize Firebase
db = None
if FIREBASE_CREDENTIALS:
    try:
        cred_dict = json.loads(FIREBASE_CREDENTIALS)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
    except Exception as e:
        logger.error(f"Error initializing Firebase: {e}")

# Your content platforms
YOUTUBE_CHANNEL_ID = "UCdFRSOdsaGPThmEsZb1tjXw"
MEDIUM_USERNAME = "b3ngali"
INSTAGRAM_HANDLE = "@bearded_bangali"
YOUTUBE_LINK = "https://www.youtube.com/@bearded_bangali"
MEDIUM_LINK = "https://medium.com/@b3ngali"
INSTAGRAM_LINK = "https://instagram.com/bearded_bangali"
TWITTER_LINK = "https://x.com/Beraded_Bengali"
FACEBOOK_LINK = "https://facebook.com/bb3ngali"

# Global state for duplicate prevention
last_posted_youtube_url = None
last_posted_medium_url = None

# Load Mock Knowledge Base for RAG
try:
    with open("knowledge_base.json", "r", encoding="utf-8") as f:
        KNOWLEDGE_BASE = json.load(f)
except Exception as e:
    logger.error(f"Error loading knowledge base: {e}")
    KNOWLEDGE_BASE = []

# ============ FAQ RESPONSES ============
# In-memory FAQ storage (will sync with Firestore if enabled)
FAQ = {
    "how do you": "Check my YouTube channel for tutorials! Visit: " + YOUTUBE_LINK,
    "edit": "I use Adobe Premiere Pro for video editing. Tutorial coming soon!",
    "content": "I create content about tech and lifestyle. Subscribe to Medium for deep dives: " + MEDIUM_LINK,
    "collab": "For collaboration inquiries, DM me on Instagram: " + INSTAGRAM_LINK,
    "upload": "I upload new videos every week",
    "subscribe": "Subscribe to all my platforms:\n" +
                 f"📺 YouTube: {YOUTUBE_LINK}\n" +
                 f"📝 Medium: {MEDIUM_LINK}\n" +
                 f"📸 Instagram: {INSTAGRAM_LINK}\n" +
                 f"🐦 X: {TWITTER_LINK}\n" +
                 f"👍 Facebook: {FACEBOOK_LINK}",
}

def load_faqs():
    """Load FAQs from Firebase into memory"""
    if not db:
        return
    try:
        docs = db.collection("faqs").stream()
        for doc in docs:
            FAQ[doc.id] = doc.to_dict().get("response", "")
        logger.info("Loaded FAQs from Firestore.")
    except Exception as e:
        logger.error(f"Error loading FAQs: {e}")

def save_faq(keyword: str, response: str):
    """Save an FAQ to Firebase"""
    FAQ[keyword] = response
    if db:
        try:
            db.collection("faqs").document(keyword).set({"response": response})
        except Exception as e:
            logger.error(f"Error saving FAQ to Firestore: {e}")

def remove_faq(keyword: str):
    """Remove an FAQ from Firebase and memory"""
    if keyword in FAQ:
        del FAQ[keyword]
    if db:
        try:
            db.collection("faqs").document(keyword).delete()
        except Exception as e:
            logger.error(f"Error removing FAQ from Firestore: {e}")

# ============ HELPER FUNCTIONS ============

def is_admin(user_id: str) -> bool:
    """Check if user is admin. Securely fails if ADMIN_ID is not configured."""
    if not ADMIN_ID:
        return False
    return str(user_id) == str(ADMIN_ID)

async def send_channel_message(context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None):
    """Send message to your channel"""
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

async def get_youtube_posts(limit=3, return_url_only=False):
    """Fetch latest YouTube videos"""
    try:
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={YOUTUBE_CHANNEL_ID}"
        feed = feedparser.parse(rss_url)
        
        if feed.entries:
            if return_url_only:
                return feed.entries[0].link

            message = "🎥 <b>Latest Videos:</b>\n\n"
            for i, entry in enumerate(feed.entries[:limit]):
                message += f"{i+1}. <b>{entry.title}</b>\n<a href='{entry.link}'>Watch Now</a>\n\n"
            
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
        feed = feedparser.parse(rss_url)
        
        if feed.entries:
            if return_url_only:
                return feed.entries[0].link

            message = "📝 <b>Latest Articles:</b>\n\n"
            for i, entry in enumerate(feed.entries[:limit]):
                message += f"{i+1}. <b>{entry.title}</b>\n<a href='{entry.link}'>Read Now</a>\n\n"
            
            button = InlineKeyboardButton("View Profile 📝", url=MEDIUM_LINK)
            return message.strip(), button, feed.entries[0].link
    except Exception as e:
        logger.error(f"Error fetching Medium: {e}")
    
    if return_url_only: return None
    return None, None, None

def search_knowledge_base(query: str) -> str:
    """Mock vector search using basic keyword matching"""
    query_lower = query.lower()
    results = []
    for post in KNOWLEDGE_BASE:
        # Simple scoring based on term presence
        score = sum(1 for word in query_lower.split() if word in post["content"].lower() or word in post["title"].lower())
        if score > 0:
            results.append((score, post))
            
    # Sort by score descending and take top 2
    results.sort(key=lambda x: x[0], reverse=True)
    top_results = results[:2]
    
    if not top_results:
        return "No relevant past posts found for this query."
        
    formatted_results = []
    for _, post in top_results:
        formatted_results.append(
            f"Platform: {post['platform']}\nTitle: {post['title']}\nContent: {post['content']}\nLink: {post['url']}"
        )
    return "\n\n---\n\n".join(formatted_results)

async def get_grok_response(user_message: str) -> str:
    """Get dynamic response from xAI's Grok API with Tool Calling (Agentic RAG)"""
    if not XAI_API_KEY:
        return None
        
    system_prompt = f"""
You are the official Telegram assistant for Bearded Bangali, a tech and lifestyle content creator.
Your job is to answer questions enthusiastically and politely using the following context.
Do not invent facts about him. Keep answers concise (1-3 sentences max).

If a user asks a specific question about his past content, gear, or opinions, YOU MUST USE the `search_knowledge_base` tool to retrieve his actual past posts before answering.

Current known FAQs/Facts:
{json.dumps(FAQ, indent=2)}

Social Media Links:
- YouTube: {YOUTUBE_LINK}
- Medium: {MEDIUM_LINK}
- Instagram: {INSTAGRAM_LINK}
- X/Twitter: {TWITTER_LINK}
- Facebook: {FACEBOOK_LINK}
"""
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_knowledge_base",
                "description": "Searches the creator's past YouTube, Medium, and Instagram posts to answer specific questions about their gear, opinions, or past content.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query (e.g. 'camera setup', 'editing software', 'final cut')"
                        }
                    },
                    "required": ["query"]
                }
            }
        }
    ]

    messages = [
        {"role": "system", "content": system_prompt.strip()},
        {"role": "user", "content": user_message}
    ]

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # First Call to Grok
            response = await client.post(
                "https://api.x.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {XAI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "messages": messages,
                    "model": "grok-beta",
                    "tools": tools,
                    "tool_choice": "auto",
                    "stream": False,
                    "temperature": 0.7
                }
            )
            response.raise_for_status()
            data = response.json()
            message = data["choices"][0]["message"]
            
            # Check if Grok wants to use a tool
            if message.get("tool_calls"):
                messages.append(message) # Append the assistant's tool call message
                
                for tool_call in message["tool_calls"]:
                    if tool_call["function"]["name"] == "search_knowledge_base":
                        args = json.loads(tool_call["function"]["arguments"])
                        search_result = search_knowledge_base(args["query"])
                        
                        # Provide the tool result back to Grok
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": search_result
                        })
                
                # Second Call to Grok to get the final answer
                final_response = await client.post(
                    "https://api.x.ai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {XAI_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "messages": messages,
                        "model": "grok-beta",
                        "stream": False,
                        "temperature": 0.7
                    }
                )
                final_response.raise_for_status()
                final_data = final_response.json()
                return final_data["choices"][0]["message"]["content"]
            
            # If no tool was called, return the direct response
            return message.get("content")
            
    except Exception as e:
        logger.error(f"Error calling Grok API: {e}")
        return None

def get_faq_response(user_message: str) -> str:
    """Match user question to FAQ"""
    user_message_lower = user_message.lower()
    
    for keyword, response in FAQ.items():
        if keyword in user_message_lower:
            return response
    
    return (
        "Thanks for your question! 😊\n\n"
        "If you didn't find the answer, try /socials to see all my platforms!\n\n"
        "You can also ask me directly in the group!"
    )

# ============ COMMAND HANDLERS ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = f"""
👋 <b>Welcome to my content hub!</b>

I share all my latest content from my platforms here. You can also ask me questions about my content!

<b>📌 Commands:</b>
/latest - Get my latest content
/youtube - Latest video
/medium - Latest article
/socials - Links to all my platforms
/ask - Ask me a question
/help - Show all commands
    """
    await update.message.reply_text(welcome_text, parse_mode="HTML")
    logger.info(f"User {update.effective_user.id} started the bot")

async def socials_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show social media links"""
    socials_text = f"""
<b>📚 My Platforms:</b>
📺 <a href="{YOUTUBE_LINK}">YouTube</a> - Videos & Tutorials
📝 <a href="{MEDIUM_LINK}">Medium</a> - In-depth Articles
📸 <a href="{INSTAGRAM_LINK}">Instagram</a> - Behind the Scenes
🐦 <a href="{TWITTER_LINK}">X/Twitter</a> - Updates & Discussions
👍 <a href="{FACEBOOK_LINK}">Facebook</a> - Community
    """
    await update.message.reply_text(socials_text, parse_mode="HTML")

async def latest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action(ChatAction.TYPING)
    message = "🔄 <b>Fetching latest content...</b>\n\n"
    buttons = []
    
    yt_msg, yt_btn, _ = await get_youtube_posts(limit=2)
    if yt_msg: 
        message += yt_msg + "\n\n"
        if yt_btn: buttons.append([yt_btn])
    
    med_msg, med_btn, _ = await get_medium_posts(limit=2)
    if med_msg: 
        message += med_msg + "\n\n"
        if med_btn: buttons.append([med_btn])
    
    if yt_msg or med_msg:
        reply_markup = InlineKeyboardMarkup(buttons) if buttons else None
        await update.message.reply_text(message, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Currently no new content. Check back soon! 📌", parse_mode="HTML")

async def youtube(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action(ChatAction.TYPING)
    yt_msg, yt_btn, _ = await get_youtube_posts(limit=3)
    if yt_msg:
        reply_markup = InlineKeyboardMarkup([[yt_btn]]) if yt_btn else None
        await update.message.reply_text(yt_msg, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await update.message.reply_text(f"No videos yet. Subscribe here: {YOUTUBE_LINK}", parse_mode="HTML")

async def medium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.chat.send_action(ChatAction.TYPING)
    med_msg, med_btn, _ = await get_medium_posts(limit=3)
    if med_msg:
        reply_markup = InlineKeyboardMarkup([[med_btn]]) if med_btn else None
        await update.message.reply_text(med_msg, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await update.message.reply_text(f"No articles yet. Follow me on Medium: {MEDIUM_LINK}", parse_mode="HTML")

async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❓ <b>Ask me anything!</b>\n\n"
        "Just type your question and I'll try to help.\n"
        "Common topics: editing, content creation, collaborations, etc.",
        parse_mode="HTML"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
<b>🤖 Available Commands:</b>
/start - Welcome message
/latest - Get all latest content
/youtube - Latest video
/medium - Latest article
/socials - Links to all my platforms
/ask - Ask me something
/help - This message

<b>💬 Just Ask!</b>
Type any question and I'll answer based on my knowledge.
    """
    await update.message.reply_text(help_text, parse_mode="HTML")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user_message = update.message.text
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    # 🛡️ Anti-Spam Link Protection for Groups
    if update.message.chat.type in ["group", "supergroup"]:
        if ("http://" in user_message.lower() or "https://" in user_message.lower()) and not is_admin(user_id):
            try:
                await update.message.delete()
                await context.bot.send_message(
                    chat_id=update.message.chat_id,
                    text=f"⚠️ @{username}, external links are not allowed in this group!"
                )
                return
            except Exception as e:
                logger.error(f"Could not delete spam message: {e}")

    if db:
        try:
            db.collection("questions").add({
                "user_id": user_id,
                "username": username,
                "question": user_message,
                "timestamp": firestore.SERVER_TIMESTAMP
            })
        except Exception as e:
            logger.error(f"Firebase error: {e}")

    await update.message.chat.send_action(ChatAction.TYPING)

    response = await get_grok_response(user_message)
    if not response:
        response = get_faq_response(user_message)

    await update.message.reply_text(response, parse_mode="HTML", reply_to_message_id=update.message.message_id)
    logger.info(f"Answered question from {user_id}: {user_message[:50]}")

# ============ ADMIN COMMANDS ============

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("You must reply to the user's message to ban them.")
        return
        
    target_user_id = update.message.reply_to_message.from_user.id
    target_username = update.message.reply_to_message.from_user.first_name
    
    try:
        await context.bot.ban_chat_member(chat_id=update.message.chat_id, user_id=target_user_id)
        await update.message.reply_text(f"🔨 {target_username} has been permanently banned from the group.")
    except Exception as e:
        await update.message.reply_text(f"Failed to ban user: {e}")

async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    
    if not update.message.reply_to_message:
        await update.message.reply_text("You must reply to the user's message to mute them.")
        return
        
    target_user_id = update.message.reply_to_message.from_user.id
    target_username = update.message.reply_to_message.from_user.first_name
    
    try:
        await context.bot.restrict_chat_member(
            chat_id=update.message.chat_id, 
            user_id=target_user_id,
            permissions=ChatPermissions(can_send_messages=False)
        )
        await update.message.reply_text(f"🔇 {target_username} has been muted and can no longer send messages.")
    except Exception as e:
        await update.message.reply_text(f"Failed to mute user: {e}")

async def postlatest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission to use this command.")
        return

    await update.message.reply_text("🔄 Broadcasting latest content to channel...")
    await auto_post_youtube(context)
    await auto_post_medium(context)
    await update.message.reply_text("✅ Done!")

async def questions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission to use this command.")
        return

    if not db:
        await update.message.reply_text("Firebase is not configured.")
        return

    try:
        docs = db.collection("questions").order_by("timestamp", direction="DESCENDING").limit(10).stream()
        message = "📝 <b>Recent Questions:</b>\n\n"
        count = 0
        for doc in docs:
            row = doc.to_dict()
            dt = row.get('timestamp')
            time_str = dt.strftime('%Y-%m-%d %H:%M:%S') if dt else "Unknown time"
            message += f"👤 <b>{row.get('username')}</b> ({time_str}):\n{row.get('question')}\n\n"
            count += 1

        if count == 0:
            await update.message.reply_text("No questions found.")
            return
        
        await update.message.reply_text(message, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Firebase error: {e}")
        await update.message.reply_text("Error retrieving questions.")

async def poll_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission to use this command.")
        return

    try:
        args = shlex.split(update.message.text)[1:]
        if len(args) < 3:
            await update.message.reply_text("Usage: /poll \"Question\" \"Option 1\" \"Option 2\" ...")
            return
            
        question = args[0]
        options = args[1:]
        
        if not CHANNEL_ID:
            await update.message.reply_text("CHANNEL_ID is not configured.")
            return
            
        await context.bot.send_poll(
            chat_id=CHANNEL_ID,
            question=question,
            options=options,
            is_anonymous=True
        )
        await update.message.reply_text("✅ Poll sent to channel!")
    except ValueError:
        await update.message.reply_text("Invalid format. Make sure to use quotes around options with spaces.")
    except Exception as e:
        await update.message.reply_text(f"Error sending poll: {e}")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission to use this command.")
        return

    text = update.message.text.replace("/broadcast", "", 1).strip()
    if not text:
        await update.message.reply_text("Usage: /broadcast <message>")
        return

    await send_channel_message(context, text)
    await update.message.reply_text("✅ Broadcast sent!")

async def addfaq_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission to use this command.")
        return

    try:
        args = shlex.split(update.message.text)[1:]
        if len(args) < 2:
            await update.message.reply_text("Usage: /addfaq \"keyword or phrase\" \"Response text\"")
            return
        keyword = args[0].lower()
        response = args[1]
        save_faq(keyword, response)
        await update.message.reply_text(f"✅ FAQ saved for keyword: {keyword}")
    except ValueError:
        await update.message.reply_text("Invalid format. Use quotes around keyword and response.")

async def rmfaq_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission to use this command.")
        return

    try:
        args = shlex.split(update.message.text)[1:]
        if len(args) < 1:
            await update.message.reply_text("Usage: /rmfaq \"keyword\"")
            return
        keyword = args[0].lower()
        remove_faq(keyword)
        await update.message.reply_text(f"✅ FAQ removed for keyword: {keyword}")
    except ValueError:
        await update.message.reply_text("Invalid format.")

async def listfaq_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission to use this command.")
        return

    if not FAQ:
        await update.message.reply_text("No FAQs available.")
        return
    
    msg = "📝 <b>Current FAQs:</b>\n\n"
    for k, v in FAQ.items():
        msg += f"<b>{k}</b>: {v[:50]}...\n"
    await update.message.reply_text(msg, parse_mode="HTML")

# ============ SCHEDULED POSTING ============

async def auto_post_youtube(context: ContextTypes.DEFAULT_TYPE):
    global last_posted_youtube_url
    try:
        yt_msg, yt_btn, link = await get_youtube_posts(limit=1)
        if yt_msg and link and link != last_posted_youtube_url:
            reply_markup = InlineKeyboardMarkup([[yt_btn]]) if yt_btn else None
            await send_channel_message(context, yt_msg, reply_markup=reply_markup)
            last_posted_youtube_url = link
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
    except Exception as e:
        logger.error(f"Error in auto_post_medium: {e}")

async def greeting_post(context: ContextTypes.DEFAULT_TYPE):
    greeting = """
✨ <b>Good Day!</b>

Welcome to my content hub! 

Find all my latest updates here. Got a question? Just DM the bot!

#Content #Creator
    """
    await send_channel_message(context, greeting)

# ============ EVENT HANDLERS ============

async def welcome_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.is_bot: continue
        welcome_text = (
            f"👋 Welcome to the community, <a href='tg://user?id={member.id}'>{member.first_name}</a>!\n\n"
            f"Feel free to ask questions here, or check out the latest content by typing /youtube."
        )
        await update.message.reply_text(welcome_text, parse_mode="HTML")

# ============ MAIN APPLICATION ============

async def post_init(application: Application):
    """Set the bot's command menu visible to followers."""
    await application.bot.set_my_commands([
        ("start", "Welcome message"),
        ("latest", "Get all latest content"),
        ("youtube", "Latest video"),
        ("medium", "Latest article"),
        ("socials", "Links to all my platforms"),
        ("ask", "Ask me something"),
        ("help", "Show all commands")
    ])
    logger.info("Bot commands menu configured successfully.")

def start_dummy_server():
    """Starts a dummy HTTP server to satisfy Render's Web Service port binding requirement."""
    port = int(os.environ.get("PORT", 8080))
    class DummyHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Bot is running!")
        # Suppress logging to keep the console clean
        def log_message(self, format, *args):
            pass
            
    server = HTTPServer(('0.0.0.0', port), DummyHandler)
    server.serve_forever()

def main():
    # Start the dummy server in a background thread
    server_thread = threading.Thread(target=start_dummy_server, daemon=True)
    server_thread.start()
    logger.info("Dummy web server started to keep Render happy!")

    load_faqs()
    application = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("socials", socials_command))
    application.add_handler(CommandHandler("latest", latest))
    application.add_handler(CommandHandler("youtube", youtube))
    application.add_handler(CommandHandler("medium", medium))
    application.add_handler(CommandHandler("ask", ask_command))
    application.add_handler(CommandHandler("help", help_command))
    
    # Admin commands
    application.add_handler(CommandHandler("postlatest", postlatest_command))
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("mute", mute_command))
    application.add_handler(CommandHandler("questions", questions_command))
    application.add_handler(CommandHandler("poll", poll_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("addfaq", addfaq_command))
    application.add_handler(CommandHandler("rmfaq", rmfaq_command))
    application.add_handler(CommandHandler("listfaq", listfaq_command))
    
    # Message handlers
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Scheduled jobs
    job_queue = application.job_queue
    job_queue.run_daily(auto_post_youtube, time=time(9, 0), days=(0, 1, 2, 3, 4, 5, 6))
    job_queue.run_daily(auto_post_medium, time=time(18, 0), days=(0, 1, 2, 3, 4, 5, 6))
    job_queue.run_daily(greeting_post, time=time(8, 0), days=(0, 1, 2, 3, 4, 5, 6))
    
    logger.info("Bot started successfully!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
