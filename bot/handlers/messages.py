"""Message handlers: free text, voice, welcome, and central callback router."""
import os
import tempfile
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ChatAction
from firebase_admin import firestore
from bot.config import logger, is_admin, RATE_LIMIT_VOICE_DAILY
from bot.database import db, track_activity, save_feedback, check_usage, increment_usage
from bot.ai import get_ai_response, get_faq_response
from bot.handlers.feedback import FEEDBACK_POSITIVE, FEEDBACK_NEGATIVE
from bot.transcriber import transcribe_voice


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle free-text messages: AI responses in DM, FAQ in groups."""
    if not update.message or not update.message.text:
        return
    user_message = update.message.text
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name

    # Anti-spam: delete links in group chats
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

    # Log question to Firestore
    if db:
        try:
            db.collection("questions").add({
                "user_id": user_id,
                "username": username,
                "question": user_message,
                "timestamp": firestore.SERVER_TIMESTAMP
            })
            track_activity(user_id, username, "ask_agent")
            # Store pending query for admin reply dashboard
            try:
                from bot.fastapi_app import store_pending_query
                store_pending_query(user_id, username, user_message, "telegram")
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Firebase error: {e}")
    else:
        track_activity(user_id, username, "ask_agent")

    # Determine if AI should respond
    should_use_ai = False
    cleaned_query = user_message.strip()
    
    # Check trigger prefixes in group chats
    is_group = update.message.chat.type in ["group", "supergroup"]
    starts_with_prefix = False
    
    if is_group:
        msg_lower = user_message.strip().lower()
        if msg_lower.startswith("?"):
            starts_with_prefix = True
            cleaned_query = user_message.strip()[1:].strip()
        elif msg_lower.startswith("bot "):
            starts_with_prefix = True
            cleaned_query = user_message.strip()[4:].strip()
        elif msg_lower.startswith("ai "):
            starts_with_prefix = True
            cleaned_query = user_message.strip()[3:].strip()
        elif msg_lower.startswith("question "):
            starts_with_prefix = True
            cleaned_query = user_message.strip()[9:].strip()

    if update.message.chat.type == "private":
        should_use_ai = True
    elif update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id:
        should_use_ai = True
    elif context.bot.username and f"@{context.bot.username}" in user_message:
        should_use_ai = True
        cleaned_query = user_message.replace(f"@{context.bot.username}", "").strip()
    elif is_group and starts_with_prefix:
        should_use_ai = True

    if should_use_ai:
        await update.message.chat.send_action(ChatAction.TYPING)
        response = await get_ai_response(cleaned_query, user_id=user_id, use_memory=True)
        if not response:
            response = get_faq_response(cleaned_query)
            if not response:
                response = "I'm sorry, I am currently unable to process your request. Please try again later."
        else:
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("👍", callback_data=f"{FEEDBACK_POSITIVE}:{update.message.message_id}"),
                    InlineKeyboardButton("👎", callback_data=f"{FEEDBACK_NEGATIVE}:{update.message.message_id}")
                ]
            ])
            if response:
                await update.message.reply_text(
                    response, parse_mode="HTML",
                    reply_to_message_id=update.message.message_id,
                    reply_markup=keyboard
                )
                logger.info(f"Answered question from {user_id}: {user_message[:50]}")
            return
    else:
        response = get_faq_response(user_message)

    if response:
        await update.message.reply_text(response, parse_mode="HTML", reply_to_message_id=update.message.message_id)
        logger.info(f"Answered question from {user_id}: {user_message[:50]}")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice messages: transcribe via Groq Whisper, then AI respond."""
    if not update.message or not update.message.voice:
        return
    user_id = update.effective_user.id
    username = update.effective_user.first_name

    allowed, remaining = check_usage(user_id, "voice_transcriptions", RATE_LIMIT_VOICE_DAILY)
    if not allowed:
        await update.message.reply_text(
            f"You've reached today's voice transcription limit ({RATE_LIMIT_VOICE_DAILY}). Try again tomorrow."
        )
        return

    await update.message.chat.send_action(ChatAction.TYPING)
    file = await context.bot.get_file(update.message.voice.file_id)
    suffix = ".ogg"
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            await file.download_to_drive(tmp.name)
            tmp_path = tmp.name
        text = await transcribe_voice(tmp_path)
        os.unlink(tmp_path)
    except Exception as e:
        logger.error(f"Voice transcription error: {e}")
        await update.message.reply_text("Sorry, I couldn't transcribe that voice message.")
        return

    if not text:
        await update.message.reply_text("Sorry, I couldn't understand the voice message.")
        return

    increment_usage(user_id, "voice_transcriptions")
    track_activity(user_id, username, "voice_message")

    response = await get_ai_response(text, user_id=user_id)
    if response:
        await update.message.reply_text(f"🎤 <i>Transcribed:</i> {text}\n\n{response}", parse_mode="HTML")
    else:
        await update.message.reply_text(f"🎤 Transcribed: {text}", parse_mode="HTML")


async def welcome_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome new group members with a greeting and command hints."""
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        welcome_text = (
            f"👋 Assalamu Alaikum and welcome to the community, "
            f"<a href='tg://user?id={member.id}'>{member.first_name}</a>!\n\n"
            f"Feel free to ask questions here, or check out the latest content by typing /youtube."
        )
        await update.message.reply_text(welcome_text, parse_mode="HTML")

        # Send a personalized DM to new members (influencer onboarding)
        try:
            dm_text = (
                f"👋 Assalamu Alaikum {member.first_name}!\n\n"
                f"Welcome to the <b>Bearded Bangali</b> community! 🎉\n\n"
                f"I'm your personal assistant bot. Here's what I can do:\n\n"
                f"🤖 <b>Ask me anything</b> — just type your question\n"
                f"📺 <b>/latest</b> — See the newest content\n"
                f"🤲 <b>/dua</b> — Search Hisnul Muslim duas\n"
                f"📖 <b>/quran</b> — Browse the Quran\n"
                f"🔔 <b>/subscribe</b> — Get daily Islamic reminders\n\n"
                f"Type /help to see all commands!"
            )
            await context.bot.send_message(chat_id=member.id, text=dm_text, parse_mode="HTML")
        except Exception as e:
            # User may have privacy settings blocking DMs — that's fine
            logger.debug(f"Could not DM new member {member.id}: {e}")


async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Central callback router — delegates to focused handler modules."""
    query = update.callback_query
    user_id = query.from_user.id

    data = query.data or ""

    # ── Feedback (thumbs up/down) ──────────────────────────────
    if FEEDBACK_POSITIVE in data or FEEDBACK_NEGATIVE in data:
        feedback_type = "positive" if FEEDBACK_POSITIVE in data else "negative"
        username = query.from_user.first_name
        original_text = query.message.text or ""
        save_feedback(user_id, username, feedback_type, query.message.message_id, original_text)
        if feedback_type == "positive":
            await query.answer("Thanks for the feedback! 👍")
            await query.edit_message_text(
                text=original_text + "\n\n👍 Thanks for the feedback!",
                parse_mode="HTML"
            )
        else:
            await query.answer("Sorry about that! I'll improve. 👎")
            await query.edit_message_text(
                text=original_text + "\n\n👎 Noted! I'll work on getting better.",
                parse_mode="HTML"
            )
        return

    # ── Study Book ──────────────────────────────────────────────
    if data.startswith("studybook:"):
        book_name = data.split(":", 1)[1]
        from bot.database import set_study_mode
        success = set_study_mode(user_id, book_name)
        if success:
            await query.answer(f"Study mode active for '{book_name}'")
            await query.edit_message_text(
                f"\U0001f4da <b>Study mode enabled: {book_name}</b>\n\n"
                f"You are now studying this book. Any questions you ask will be answered using its content. "
                f"Send /stopstudy when you are done.",
                parse_mode="HTML"
            )
        else:
            await query.answer("Failed to set study mode.", show_alert=True)
        return

    # ── Giveaway entry ─────────────────────────────────────────
    if data == "enter_giveaway":
        if not db:
            await query.answer("Database not configured.", show_alert=True)
            return
        username = query.from_user.first_name
        track_activity(user_id, username, f"callback:{data}")
        try:
            doc_ref = db.collection("giveaway_entries").document(str(user_id))
            doc = doc_ref.get()
            if doc.exists:
                await query.answer("You have already entered! Good luck! 🍀", show_alert=True)
            else:
                doc_ref.set({
                    "user_id": user_id,
                    "username": username,
                    "timestamp": firestore.SERVER_TIMESTAMP
                })
                await query.answer("🎉 You have successfully entered the giveaway!", show_alert=True)
        except Exception as e:
            logger.error(f"Giveaway entry error: {e}")
            await query.answer("An error occurred. Please try again.", show_alert=True)
        return

    # ── Bookmark callbacks ──────────────────────────────────────
    if data.startswith("bm_add:"):
        from bot.handlers.bookmarks import handle_bookmark_add
        await handle_bookmark_add(query, data.split(":"), user_id)
        return

    if data.startswith("bm_rm:"):
        from bot.handlers.bookmarks import handle_bookmark_remove
        await handle_bookmark_remove(query, data.split(":", 1)[1], user_id)
        return

    if data.startswith("bm_view:"):
        from bot.handlers.bookmarks import handle_bookmark_view
        await handle_bookmark_view(query, data.split(":", 1)[1], user_id)
        return

    if data.startswith("myduas_page:"):
        from bot.handlers.bookmarks import handle_myduas_page
        await handle_myduas_page(query, int(data.split(":")[1]), user_id)
        return

    # ── Dua navigation ─────────────────────────────────────────
    if data.startswith("dua_cat:"):
        from bot.handlers.navigation import handle_dua_category
        await handle_dua_category(query, data.split(":", 1)[1])
        return

    if data == "dua_menu":
        from bot.handlers.navigation import handle_dua_menu
        await handle_dua_menu(query)
        return

    if data == "dua_menu_reload":
        from bot.handlers.navigation import handle_dua_menu_reload
        await handle_dua_menu_reload(query)
        return

    # ── Quran navigation ───────────────────────────────────────
    if data.startswith("quran_menu"):
        from bot.handlers.navigation import handle_quran_menu
        page = 1
        if ":" in data:
            page = max(1, int(data.split(":")[1]))
        await handle_quran_menu(query, page)
        return

    if data.startswith("quran_surah:"):
        parts = data.split(":")
        surah_no = int(parts[1])
        page = int(parts[2])
        from bot.handlers.navigation import handle_quran_surah
        await handle_quran_surah(query, surah_no, page)
        return

    # ── User preferences ───────────────────────────────────────
    if data.startswith("setlang:"):
        from bot.handlers.user_prefs import handle_set_language
        await handle_set_language(query, data.split(":")[1])
        return

    if data.startswith("remindertime:"):
        from bot.handlers.user_prefs import handle_reminder_time
        await handle_reminder_time(query, data.split(":")[1])
        return

    logger.warning(f"Unhandled callback data: {data}")

async def handle_document_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detect raw document uploads and guide the user on how to ingest them."""
    doc = update.message.document
    if doc and doc.file_name:
        import os
        ext = os.path.splitext(doc.file_name)[1].lower()
        allowed_exts = ['.pdf', '.docx', '.pptx', '.xlsx', '.csv', '.txt']
        if ext in allowed_exts:
            await update.message.reply_text(
                f"📄 I received your document: <b>{doc.file_name}</b>\n\n"
                "If you want to add this to my AI knowledge base so users can study it, simply reply to your document message above with:\n\n"
                "`/ingestdoc Document Name`",
                parse_mode="HTML"
            )
