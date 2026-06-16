import shlex
import random
from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from firebase_admin import firestore
from bot.config import logger, is_admin, CHANNEL_ID
from bot.database import db, FAQ, save_faq, remove_faq, track_activity, get_feedback_counts
from bot.jobs import send_channel_message, auto_post_youtube, auto_post_medium, auto_post_substack
from bot.pipeline import ingest_knowledge_base, ingest_duas, ingest_quran_verses, get_pipeline_stats
from bot.vectordb import get_document_count

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
    await auto_post_substack(context)
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

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    track_activity(update.effective_user.id, update.effective_user.first_name, "suggest")
    suggestion = update.message.text.replace("/suggest", "", 1).strip()
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
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ You don't have permission.")
        return

    prize = update.message.text.replace("/startgiveaway", "", 1).strip()
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
