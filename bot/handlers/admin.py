import shlex
import random
import asyncio
import datetime
from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from firebase_admin import firestore
from bot.config import logger, is_admin, CHANNEL_ID, BOT_TZ
from bot.database import db, FAQ, save_faq, remove_faq, track_activity, get_feedback_counts
from bot.jobs import send_channel_message, auto_post_youtube, auto_post_medium, auto_post_substack, auto_post_facebook, auto_post_twitter
from bot.pipeline import ingest_knowledge_base, ingest_duas, ingest_quran_verses, get_pipeline_stats
from bot.vectordb import get_document_count
from bot.handlers.commands import clean_command_query

async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
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
    if not update.message:
        return
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
    if not update.message:
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission to use this command.")
        return

    await update.message.reply_text("🔄 Broadcasting latest content to channel...")
    await auto_post_youtube(context)
    await auto_post_medium(context)
    await auto_post_substack(context)
    await auto_post_facebook(context)
    await auto_post_twitter(context)
    await update.message.reply_text("✅ Done!")

async def questions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
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
    if not update.message:
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission to use this command.")
        return

    try:
        args = shlex.split(clean_command_query(update.message.text, "poll"))
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
    if not update.message:
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission to use this command.")
        return

    text = clean_command_query(update.message.text, "broadcast")
    if not text:
        await update.message.reply_text("Usage: /broadcast <message>")
        return

    await send_channel_message(context, text)
    await update.message.reply_text("✅ Broadcast sent!")

async def addfaq_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission to use this command.")
        return

    try:
        args = shlex.split(clean_command_query(update.message.text, "addfaq"))
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
    if not update.message:
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission to use this command.")
        return

    try:
        args = shlex.split(clean_command_query(update.message.text, "rmfaq"))
        if len(args) < 1:
            await update.message.reply_text("Usage: /rmfaq \"keyword\"")
            return
        keyword = args[0].lower()
        remove_faq(keyword)
        await update.message.reply_text(f"✅ FAQ removed for keyword: {keyword}")
    except ValueError:
        await update.message.reply_text("Invalid format.")

async def listfaq_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
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

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission.")
        return

    db_available = db is not None

    faq_count = len(FAQ)
    doc_count = get_document_count()
    feedback_counts = get_feedback_counts()
    pipeline_stats = get_pipeline_stats()

    stats = (
        "📊 <b>Admin Dashboard Stats:</b>\n\n"
        f"📚 Active Custom FAQs: <b>{faq_count}</b>\n"
        f"🧠 Vector DB Documents: <b>{doc_count}</b>\n"
        f"📦 KB Source Entries: <b>{pipeline_stats['kb_entries']}</b>\n"
        f"👍 Feedback Positive: <b>{feedback_counts['positive']}</b>\n"
        f"👎 Feedback Negative: <b>{feedback_counts['negative']}</b>\n"
    )

    if db_available:
        try:
            q_count = len(list(db.collection("questions").stream()))
            s_count = len(list(db.collection("suggestions").stream()))
            g_count = len(list(db.collection("giveaway_entries").stream()))
            stats += (
                f"\n<b>Firestore Stats:</b>\n"
                f"❓ Total Questions: <b>{q_count}</b>\n"
                f"💡 Total Suggestions: <b>{s_count}</b>\n"
                f"🎁 Giveaway Entries: <b>{g_count}</b>"
            )
        except Exception as e:
            logger.error(f"Error fetching Firestore stats: {e}")
            stats += "\n\n⚠️ Error fetching Firestore stats."

    await update.message.reply_text(stats, parse_mode="HTML")

async def ingest_kb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission to use this command.")
        return
    await update.message.reply_text("🔄 Re-indexing knowledge base into vector DB...")
    count = ingest_knowledge_base(reindex=True)
    pipeline_stats = get_pipeline_stats()
    await update.message.reply_text(
        f"✅ Knowledge base ingested!\n\n"
        f"📦 Chunks indexed: <b>{pipeline_stats['vector_documents']}</b>\n"
        f"📄 Source entries: <b>{pipeline_stats['kb_entries']}</b>",
        parse_mode="HTML"
    )

async def ingest_duas_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission to use this command.")
        return
    await update.message.reply_text("🔄 Re-indexing all duas from Hisnul Muslim source (this may take a minute)...")
    count = await ingest_duas(force_reindex=True)
    await update.message.reply_text(
        f"✅ Duas re-indexed! {count} novas imported into vector DB.",
        parse_mode="HTML"
    )

async def ingest_quran_kb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission to use this command.")
        return
    await update.message.reply_text("🔄 Re-indexing all Quran verses (this may take a few minutes)...")
    count = await ingest_quran_verses(force_reindex=True)
    await update.message.reply_text(
        f"✅ Quran re-indexed! {count} verses imported into vector DB.",
        parse_mode="HTML"
    )

async def suggest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    track_activity(update.effective_user.id, update.effective_user.first_name, "suggest")
    suggestion = clean_command_query(update.message.text, "suggest")
    if not suggestion:
        await update.message.reply_text(
            "💡 <b>Suggestion Box</b>\n\n"
            "Have an idea for a geopolitics topic or video? Let me know!\n"
            "Usage: /suggest <your idea>",
            parse_mode="HTML"
        )
        return
        
    if db:
        try:
            db.collection("suggestions").add({
                "user_id": update.effective_user.id,
                "username": update.effective_user.first_name,
                "suggestion": suggestion,
                "timestamp": firestore.SERVER_TIMESTAMP
            })
            await update.message.reply_text("✅ Your suggestion has been saved! Thank you for contributing.")
        except Exception as e:
            logger.error(f"Error saving suggestion: {e}")
            await update.message.reply_text("Sorry, there was an error saving your suggestion.")
    else:
        await update.message.reply_text("Database is currently disabled.")

async def listsuggestions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission.")
        return
        
    if not db:
        await update.message.reply_text("Database not configured.")
        return
        
    try:
        docs = db.collection("suggestions").order_by("timestamp", direction="DESCENDING").limit(10).stream()
        message = "💡 <b>Latest Geopolitics Suggestions:</b>\n\n"
        count = 0
        for doc in docs:
            row = doc.to_dict()
            message += f"👤 <b>{row.get('username')}</b>:\n{row.get('suggestion')}\n\n"
            count += 1
            
        if count == 0:
            await update.message.reply_text("No suggestions found.")
            return
            
        await update.message.reply_text(message, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error listing suggestions: {e}")
        await update.message.reply_text("Error retrieving suggestions.")

async def startgiveaway_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission.")
        return

    prize = clean_command_query(update.message.text, "startgiveaway")
    if not prize:
        await update.message.reply_text("Usage: /startgiveaway <Prize Name>")
        return

    if db:
        try:
            docs = db.collection("giveaway_entries").stream()
            for doc in docs:
                doc.reference.delete()
        except Exception as e:
            logger.error(f"Error clearing old giveaways: {e}")

    message = (
        f"🎁 <b>GIVEAWAY ALERT!</b> 🎁\n\n"
        f"We are giving away: <b>{prize}</b>\n\n"
        f"Click the button below to enter!"
    )
    
    keyboard = [[InlineKeyboardButton("Enter Giveaway 🎉", callback_data="enter_giveaway")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if CHANNEL_ID:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=message, parse_mode="HTML", reply_markup=reply_markup)
        await update.message.reply_text("✅ Giveaway posted to channel!")
    else:
        await update.message.reply_text(message, parse_mode="HTML", reply_markup=reply_markup)

async def pickwinner_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission.")
        return

    if not db:
        await update.message.reply_text("Database not configured.")
        return

    try:
        docs = list(db.collection("giveaway_entries").stream())
        if not docs:
            await update.message.reply_text("No one has entered the giveaway yet!")
            return
            
        winner_doc = random.choice(docs)
        winner_data = winner_doc.to_dict()
        winner_name = winner_data.get('username', 'Unknown')
        winner_id = winner_data.get('user_id')
        
        announcement = (
            f"🎊 <b>GIVEAWAY WINNER!</b> 🎊\n\n"
            f"Congratulations <a href='tg://user?id={winner_id}'>{winner_name}</a>! You have won the giveaway!\n"
            f"Please DM the admin to claim your prize."
        )
        
        if CHANNEL_ID:
            await context.bot.send_message(chat_id=CHANNEL_ID, text=announcement, parse_mode="HTML")
            await update.message.reply_text("✅ Winner announced in channel!")
        else:
            await update.message.reply_text(announcement, parse_mode="HTML")
            
    except Exception as e:
        logger.error(f"Error picking winner: {e}")
        await update.message.reply_text("Error picking winner.")


async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Schedule a message to be sent to the channel at a specific time.
    Usage: /schedule "2026-07-06 14:00" "Your message here"
    """
    if not update.message:
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission.")
        return

    if not CHANNEL_ID:
        await update.message.reply_text("CHANNEL_ID is not configured.")
        return

    from bot.handlers.influencer import schedule_post, list_scheduled_posts, cancel_scheduled_post

    text = clean_command_query(update.message.text, "schedule").strip()

    # Sub-commands: list, cancel
    if text == "list" or text == "":
        posts = list_scheduled_posts()
        if not posts:
            await update.message.reply_text(
                "📅 <b>No scheduled posts.</b>\n\n"
                "Usage: /schedule \"YYYY-MM-DD HH:MM\" \"Your message\"\n"
                "/schedule list — View pending posts\n"
                "/schedule cancel <post_id> — Cancel a post",
                parse_mode="HTML"
            )
            return
        msg = "📅 <b>Scheduled Posts:</b>\n\n"
        for p in posts:
            msg += f"🆔 <code>{p['id']}</code>\n"
            msg += f"🕐 {p['send_at'][:16]}\n"
            msg += f"📝 {p['text'][:80]}{'...' if len(p['text']) > 80 else ''}\n\n"
        await update.message.reply_text(msg, parse_mode="HTML")
        return

    if text.startswith("cancel"):
        parts = text.split(None, 1)
        if len(parts) < 2:
            await update.message.reply_text("Usage: /schedule cancel <post_id>")
            return
        post_id = parts[1].strip()
        if cancel_scheduled_post(post_id):
            await update.message.reply_text(f"✅ Scheduled post {post_id} cancelled.")
        else:
            await update.message.reply_text(f"❌ No scheduled post found with ID: {post_id}")
        return

    # Schedule a new post
    try:
        args = shlex.split(text)
        if len(args) < 2:
            await update.message.reply_text(
                "Usage: /schedule \"YYYY-MM-DD HH:MM\" \"Your message\"\n\n"
                "Example: /schedule \"2026-07-06 14:00\" \"Check out my new video!\"",
                parse_mode="HTML"
            )
            return

        time_str = args[0]
        message_text = args[1]

        try:
            send_at = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M")
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid time format. Use: <code>YYYY-MM-DD HH:MM</code>\n"
                "Example: <code>2026-07-06 14:00</code>",
                parse_mode="HTML"
            )
            return

        # Make timezone-aware
        send_at = send_at.replace(tzinfo=BOT_TZ)

        if send_at <= datetime.datetime.now(BOT_TZ):
            await update.message.reply_text("❌ The scheduled time must be in the future.")
            return

        post = schedule_post(message_text, send_at)
        await update.message.reply_text(
            f"✅ <b>Post scheduled!</b>\n\n"
            f"🆔 ID: <code>{post['id']}</code>\n"
            f"🕐 Sends at: {send_at.strftime('%Y-%m-%d %H:%M %Z')}\n"
            f"📝 Message: {message_text[:100]}{'...' if len(message_text) > 100 else ''}",
            parse_mode="HTML"
        )
    except ValueError:
        await update.message.reply_text("Invalid format. Use quotes around the message.")
    except Exception as e:
        logger.error(f"Error scheduling post: {e}")
        await update.message.reply_text(f"Error scheduling post: {e}")


async def channelstats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show channel subscriber count and bot status stats."""
    if not update.message:
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission.")
        return

    from bot.handlers.influencer import get_channel_member_count, list_scheduled_posts

    member_count = get_channel_member_count()
    scheduled = list_scheduled_posts()

    # Gather Firestore stats
    questions_count = 0
    suggestions_count = 0
    feedback_counts = {"positive": 0, "negative": 0}
    if db:
        try:
            questions_count = len(list(db.collection("questions").stream()))
            suggestions_count = len(list(db.collection("suggestions").stream()))
            feedback_counts = get_feedback_counts()
        except Exception:
            pass

    doc_count = get_document_count()

    msg = (
        f"📊 <b>Channel & Bot Stats</b>\n\n"
        f"📢 <b>Channel Subscribers:</b> {member_count if member_count else 'N/A'}\n"
        f"📅 <b>Scheduled Posts:</b> {len(scheduled)}\n"
        f"🧠 <b>Vector DB Documents:</b> {doc_count}\n"
        f"❓ <b>Questions Asked:</b> {questions_count}\n"
        f"💡 <b>Suggestions:</b> {suggestions_count}\n"
        f"👍 <b>Feedback:</b> +{feedback_counts.get('positive', 0)} / -{feedback_counts.get('negative', 0)}"
    )
    await update.message.reply_text(msg, parse_mode="HTML")


async def checkkeys_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test all AI provider API keys on-demand and show status."""
    if not update.message:
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission.")
        return

    from bot.config import (
        OPENROUTER_API_KEY, GROQ_API_KEY, OPENAI_API_KEY,
        ANTHROPIC_API_KEY, GEMINI_API_KEY, XAI_API_KEY, DEEPSEEK_API_KEY,
        OLLAMA_BASE_URL, TELEGRAM_TOKEN, CHANNEL_ID, ADMIN_ID,
        _is_valid_key as is_valid_key
    )
    from bot.database import db

    status_msg = await update.message.reply_text("🔑 Testing API keys... this may take ~30s")

    providers = [
        ("OpenRouter", "openrouter/openai/gpt-4o-mini", OPENROUTER_API_KEY),
        ("Groq", "groq/llama-3.1-8b-instant", GROQ_API_KEY),
        ("OpenAI", "openai/gpt-4o-mini", OPENAI_API_KEY),
        ("Anthropic", "anthropic/claude-3-haiku-20240307", ANTHROPIC_API_KEY),
        ("Gemini", "gemini/gemini-2.0-flash", GEMINI_API_KEY),
        ("xAI", "xai/grok-3", XAI_API_KEY),
        ("DeepSeek", "deepseek/deepseek-chat", DEEPSEEK_API_KEY),
    ]

    import litellm

    async def test_provider(name, model, api_key):
        if not api_key or not is_valid_key(api_key):
            return f"  {name}: ⏭️ SKIPPED (no valid key)"
        try:
            kwargs = {
                "model": model,
                "messages": [{"role": "user", "content": "Reply OK"}],
                "api_key": api_key,
                "max_tokens": 5,
                "temperature": 0,
            }
            resp = await litellm.acompletion(**kwargs)
            tokens = resp.usage.total_tokens if resp.usage else 0
            return f"  {name}: ✅ WORKING (model={model.split('/')[-1]}, tokens={tokens})"
        except Exception as e:
            err = str(e)[:100]
            return f"  {name}: ❌ FAILED — {err}"

    # Test all providers in parallel
    tasks = [test_provider(name, model, key) for name, model, key in providers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Test infrastructure
    infra_lines = []
    infra_lines.append("\n🏗️ <b>Infrastructure:</b>")
    infra_lines.append(f"  Telegram Token: {'✅ SET' if TELEGRAM_TOKEN else '❌ MISSING'}")
    infra_lines.append(f"  Channel ID: {'✅ SET' if CHANNEL_ID else '⚠️ NOT SET'}")
    infra_lines.append(f"  Admin ID: {'✅ SET' if ADMIN_ID else '⚠️ NOT SET'}")
    infra_lines.append(f"  Firebase: {'✅ Connected' if db else '❌ NOT CONNECTED'}")
    infra_lines.append(f"  Ollama (local): {'✅ URL set' if OLLAMA_BASE_URL else '⏭️ Not configured'}")

    # Build final message
    ai_lines = []
    ai_lines.append("🤖 <b>AI Provider Status:</b>")
    for r in results:
        if isinstance(r, Exception):
            ai_lines.append(f"  ❌ ERROR: {r}")
        else:
            ai_lines.append(r)

    msg = "\n".join(ai_lines) + "\n" + "\n".join(infra_lines)

    try:
        await status_msg.edit_text(msg, parse_mode="HTML")
    except Exception:
        # Telegram has a 4096 char limit for messages
        # Truncate if too long
        if len(msg) > 4000:
            msg = msg[:4000] + "\n... (truncated)"
        await status_msg.edit_text(msg, parse_mode="HTML")


async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send an interactive quiz to the channel.
    Usage: /quiz "Question" "Option1" "Option2" "Option3" [correct_index] "Explanation"
    correct_index is 1-based (default: 1 if omitted).
    """
    if not update.message:
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission.")
        return

    if not CHANNEL_ID:
        await update.message.reply_text("CHANNEL_ID is not configured.")
        return

    from bot.handlers.influencer import send_quiz_to_channel

    text = clean_command_query(update.message.text, "quiz").strip()
    if not text:
        await update.message.reply_text(
            "📝 <b>Send a Quiz</b>\n\n"
            "Usage: /quiz \"Question\" \"Option 1\" \"Option 2\" \"Option 3\" \"Explanation\"\n\n"
            "The correct answer is always the <b>first option</b>.\n"
            "Example: /quiz \"Capital of France?\" \"Paris\" \"London\" \"Berlin\" \"Paris is the capital of France.\"",
            parse_mode="HTML"
        )
        return

    try:
        args = shlex.split(text)
        if len(args) < 3:
            await update.message.reply_text(
                "❌ Need at least: /quiz \"Question\" \"Option 1\" \"Option 2\"",
                parse_mode="HTML"
            )
            return

        question = args[0]
        options = args[1:]
        explanation = ""

        # Last arg is explanation if there are 4+ args and it's not a short option
        if len(options) > 2:
            # Check if the last arg looks like an explanation (longer than typical option)
            if len(options[-1]) > 30 or len(options) >= 4:
                explanation = options.pop()

        if len(options) < 2:
            await update.message.reply_text("❌ Need at least 2 options.")
            return

        if len(options) > 10:
            await update.message.reply_text("❌ Maximum 10 options allowed.")
            return

        # Correct answer is always the first option (index 0)
        correct_index = 0

        success = await send_quiz_to_channel(
            context, question, options, correct_index, explanation
        )
        if success:
            await update.message.reply_text(
                f"✅ Quiz sent to channel!\n\n"
                f"❓ {question}\n"
                f"✅ Correct answer: {options[correct_index]}",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text("❌ Failed to send quiz to channel.")
    except ValueError:
        await update.message.reply_text("Invalid format. Make sure to use quotes around options with spaces.")
    except Exception as e:
        logger.error(f"Error sending quiz: {e}")
        await update.message.reply_text(f"Error sending quiz: {e}")
