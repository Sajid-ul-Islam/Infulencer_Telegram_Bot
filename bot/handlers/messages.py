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
    if not update.message or not update.message.text: return
    user_message = update.message.text
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name

    if update.message.chat.type in ["group", "supergroup"]:
        if ("http://" in user_message.lower() or "https://" in user_message.lower()) and not is_admin(user_id):
            try:
                await update.message.delete()
                await context.bot.send_message(
                    chat_id=update.message.chat_id,
                    text=f"\u26a0\ufe0f @{username}, external links are not allowed in this group!"
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
            track_activity(user_id, username, "ask_agent")
        except Exception as e:
            logger.error(f"Firebase error: {e}")
    else:
        track_activity(user_id, username, "ask_agent")

    should_use_ai = False
    if update.message.chat.type == "private":
        should_use_ai = True
    elif update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id:
        should_use_ai = True
    elif context.bot.username and f"@{context.bot.username}" in user_message:
        should_use_ai = True

    if should_use_ai:
        await update.message.chat.send_action(ChatAction.TYPING)
        response = await get_ai_response(user_message, user_id=user_id, use_memory=True)
        if not response:
            response = get_faq_response(user_message)
            if not response:
                response = "Walaikum Assalam! \U0001f60a How can I help you today? Type /help to see what I can do."
        else:
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("\U0001f44d", callback_data=f"{FEEDBACK_POSITIVE}:{update.message.message_id}"),
                    InlineKeyboardButton("\U0001f44e", callback_data=f"{FEEDBACK_NEGATIVE}:{update.message.message_id}")
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
    for member in update.message.new_chat_members:
        if member.is_bot: continue
        welcome_text = (
            f"\U0001f44b Assalamu Alaikum and welcome to the community, <a href='tg://user?id={member.id}'>{member.first_name}</a>!\n\n"
            f"Feel free to ask questions here, or check out the latest content by typing /youtube."
        )
        await update.message.reply_text(welcome_text, parse_mode="HTML")

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if FEEDBACK_POSITIVE in query.data or FEEDBACK_NEGATIVE in query.data:
        feedback_type = "positive" if FEEDBACK_POSITIVE in query.data else "negative"
        user_id = query.from_user.id
        username = query.from_user.first_name
        original_text = query.message.text or ""
        save_feedback(user_id, username, feedback_type, query.message.message_id, original_text)
        if feedback_type == "positive":
            await query.answer("Thanks for the feedback! \U0001f44d")
            await query.edit_message_text(
                text=original_text + "\n\n\U0001f44d Thanks for the feedback!",
                parse_mode="HTML"
            )
        else:
            await query.answer("Sorry about that! I'll improve. \U0001f44e")
            await query.edit_message_text(
                text=original_text + "\n\n\U0001f44e Noted! I'll work on getting better.",
                parse_mode="HTML"
            )
        return

    if query.data == "enter_giveaway":
        if not db:
            await query.answer("Database not configured.", show_alert=True)
            return
        user_id = query.from_user.id
        username = query.from_user.first_name
        track_activity(user_id, username, f"callback:{query.data}")
        try:
            doc_ref = db.collection("giveaway_entries").document(str(user_id))
            doc = doc_ref.get()
            if doc.exists:
                await query.answer("You have already entered! Good luck! \U0001f340", show_alert=True)
            else:
                doc_ref.set({
                    "user_id": user_id,
                    "username": username,
                    "timestamp": firestore.SERVER_TIMESTAMP
                })
                await query.answer("\U0001f389 You have successfully entered the giveaway!", show_alert=True)
        except Exception as e:
            logger.error(f"Giveaway entry error: {e}")
            await query.answer("An error occurred. Please try again.", show_alert=True)
            return

    if query.data.startswith("dua_cat:"):
        category_slug = query.data.split(":", 1)[1]
        await query.answer(f"Searching {category_slug} duas...")
        from bot.search import search_duas_by_category, get_rag_status
        from bot.handlers.commands import (
            build_dua_menu_keyboard,
            build_dua_menu_text,
            format_empty_rag_message,
        )

        if not get_rag_status()["dua_ready"]:
            await query.edit_message_text(format_empty_rag_message("dua"), parse_mode="HTML")
            return

        from bot.dua_scraper import get_cached_dua_categories
        cat_name = category_slug
        for slug, display in get_cached_dua_categories():
            if slug == category_slug:
                cat_name = display
                break

        result, metas = search_duas_by_category(category_slug)
        buttons = []
        if metas:
            # Bookmark row: one button per dua if space permits, or a single "Bookmark all"
            bm_row = []
            for meta in metas[:3]:  # Max 3 bookmark buttons per row
                item_id = meta.get("id", "")
                dua_name = meta.get("dua_name", "Dua")
                if item_id:
                    bm_row.append(InlineKeyboardButton(
                        f"\U0001f516 {dua_name[:20]}",
                        callback_data=f"bm_add:{item_id}:dua"
                    ))
            if bm_row:
                buttons.append(bm_row[:2])  # Split into rows of 2 if needed
                if len(bm_row) > 2:
                    buttons.append(bm_row[2:])
        buttons.append([InlineKeyboardButton("⬅️ Back to Dua Menu", callback_data="dua_menu")])

        if not result or "No duas found" in result:
            await query.edit_message_text(
                f"\U0001f54a No duas found for this category.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
        else:
            import html
            message_text = f"\U0001f54a <b>{html.escape(cat_name)}</b>\n\n{html.escape(result)}"
            if len(message_text) > 4000:
                result_parts = result.split("\n\n---\n\n")
                safe_result = html.escape("\n\n---\n\n".join(result_parts[:1]))
                message_text = f"\U0001f54a <b>{html.escape(cat_name)}</b>\n\n{safe_result}\n\n<i>...[Results too long to display fully]</i>"

            try:
                await query.edit_message_text(
                    message_text,
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(buttons),
                )
            except Exception as e:
                logger.error(f"Error editing dua message: {e}")
                await query.edit_message_text("An error occurred while displaying the results. Please try a different query.")
        return

    if query.data == "dua_menu":
        from bot.handlers.commands import build_dua_menu_keyboard, build_dua_menu_text
        await query.answer()
        await query.edit_message_text(
            build_dua_menu_text(),
            parse_mode="HTML",
            reply_markup=await build_dua_menu_keyboard(),
        )
        return

    if query.data == "dua_menu_reload":
        from bot.handlers.commands import build_dua_menu_keyboard, build_dua_menu_text
        await query.answer("Loading categories...")
        await query.edit_message_text(
            build_dua_menu_text(),
            parse_mode="HTML",
            reply_markup=await build_dua_menu_keyboard(),
        )
        return

    if query.data.startswith("quran_menu"):
        from bot.handlers.commands import build_quran_menu_keyboard, build_quran_menu_text
        page = 1
        if ":" in query.data:
            page = max(1, int(query.data.split(":")[1]))
        await query.answer()
        await query.edit_message_text(
            build_quran_menu_text(page=page),
            parse_mode="HTML",
            reply_markup=build_quran_menu_keyboard(page=page),
        )
        return

    if query.data.startswith("quran_surah:"):
        parts = query.data.split(":")
        surah_no = int(parts[1])
        page = int(parts[2])
        await query.answer("Fetching verses...")
        from bot.search import get_surah_verses, get_rag_status
        from bot.handlers.commands import format_empty_rag_message, build_quran_menu_keyboard

        if not get_rag_status()["quran_ready"]:
            await query.edit_message_text(format_empty_rag_message("quran"), parse_mode="HTML")
            return

        result, metas, has_next, has_prev = get_surah_verses(surah_no, page=page, limit=5)
        
        buttons = []
        # Audio + Bookmark buttons for displayed verses
        if metas:
            from bot.quran_scraper import get_verse_audio_url
            # Audio row: one "Listen" button per verse
            audio_row = []
            bm_row = []
            for meta in metas[:5]:
                item_id = meta.get("id", "")
                ayah_no = meta.get("ayah_no", "")
                # Audio button
                audio_url = get_verse_audio_url(surah_no, ayah_no)
                audio_row.append(InlineKeyboardButton(
                    f"\u25b6\ufe0f {ayah_no}",
                    url=audio_url
                ))
                # Bookmark button
                if item_id:
                    bm_row.append(InlineKeyboardButton(
                        f"\U0001f516 {ayah_no}",
                        callback_data=f"bm_add:{item_id}:quran"
                    ))
            if audio_row:
                # Split audio buttons into rows of ~3
                for i in range(0, len(audio_row), 3):
                    buttons.append(audio_row[i:i+3])
            if bm_row:
                for i in range(0, len(bm_row), 3):
                    buttons.append(bm_row[i:i+3])

        nav_buttons = []
        if has_prev:
            nav_buttons.append(InlineKeyboardButton("⬅️ Prev 5", callback_data=f"quran_surah:{surah_no}:{page-1}"))
        if has_next:
            nav_buttons.append(InlineKeyboardButton("Next 5 ➡️", callback_data=f"quran_surah:{surah_no}:{page+1}"))
        
        if nav_buttons:
            buttons.append(nav_buttons)
        buttons.append([InlineKeyboardButton("⬅️ Back to Quran Menu", callback_data="quran_menu:1")])
            
        reply_markup = InlineKeyboardMarkup(buttons)
        
        import html
        message_text = f"\U0001f4dc <b>Quran Surah {surah_no} (Page {page})</b>\n\n{html.escape(result)}"
        
        if len(message_text) > 4000:
             result_parts = result.split("\n\n---\n\n")
             safe_result = html.escape("\n\n---\n\n".join(result_parts[:2]))
             message_text = f"\U0001f4dc <b>Quran Surah {surah_no} (Page {page})</b>\n\n{safe_result}\n\n<i>...[Verses too long, please use Next]</i>"
             
        try:
            await query.edit_message_text(message_text, parse_mode="HTML", reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error editing quran message: {e}")
            await query.edit_message_text("An error occurred while displaying the verses.")
        return

    if query.data.startswith("setlang:"):
        lang_code = query.data.split(":")[1]
        user_id = query.from_user.id
        from bot.database import set_user_language
        success = set_user_language(user_id, lang_code)
        if success:
            lang_name = "Bengali 🇧🇩" if lang_code == "bn" else "English 🇬🇧"
            await query.answer(f"Language set to {lang_name}")
            await query.edit_message_text(f"✅ Language preference successfully set to {lang_name}.")
        else:
            await query.answer("Failed to set language", show_alert=True)
        return

    if query.data.startswith("remindertime:"):
        time_pref = query.data.split(":")[1]
        if time_pref not in ("morning", "evening"):
            await query.answer("Invalid time preference.", show_alert=True)
            return
        user_id = query.from_user.id
        from bot.database import set_reminder_time, get_subscribed_users
        subscribed = get_subscribed_users()
        if user_id not in subscribed:
            await query.answer("Please /subscribe first!", show_alert=True)
            return
        success = set_reminder_time(user_id, time_pref)
        if success:
            label = "morning 🌅" if time_pref == "morning" else "evening 🌛"
            await query.answer(f"Reminder time changed to {label}!")
            await query.edit_message_text(
                f"✅ Reminder time successfully set to <b>{label}</b>.\n\n"
                f"You'll receive your daily Ayah + Dua at the selected time.",
                parse_mode="HTML",
            )
        else:
            await query.answer("Failed to update time. Try again.", show_alert=True)
        return

    # ── Bookmark callbacks ──────────────────────────────────────────

    if query.data.startswith("bm_add:"):
        parts = query.data.split(":")
        item_id = parts[1]
        doc_type = parts[2] if len(parts) > 2 else "dua"
        user_id = query.from_user.id
        from bot.database import save_bookmark, is_bookmarked

        if is_bookmarked(user_id, item_id):
            await query.answer("Already bookmarked! \U0001f516", show_alert=True)
            return

        # Fetch metadata from vector DB to build a nice bookmark
        from bot.vectordb import get_collection
        title = ""
        snippet = ""
        url = ""
        try:
            collection = get_collection()
            if collection:
                docs = collection.get(ids=[item_id], include=["metadatas"])
                if docs and docs.get("metadatas") and docs["metadatas"][0]:
                    meta = docs["metadatas"][0]
                    if doc_type == "dua":
                        title = meta.get("dua_name", meta.get("title", "Dua"))
                        snippet = meta.get("arabic", "") or meta.get("translation", "")
                        url = meta.get("url", "")
                    else:
                        surah = meta.get("surah_name", "")
                        ayah = meta.get("ayah_no", "")
                        title = f"{surah} {ayah}"
                        snippet = meta.get("arabic", "") or meta.get("translation", "")
                        surah_no = meta.get("surah_no", "")
                        if surah_no:
                            url = f"https://quran.com/{surah_no}/{ayah}"
        except Exception as e:
            logger.error(f"Error fetching bookmark metadata: {e}")

        if not title:
            title = item_id

        success = save_bookmark(user_id, item_id, doc_type, title, snippet, url)
        if success:
            await query.answer(f"\U0001f516 Saved! Use /myduas to view.")
            # Update the button text to show it's bookmarked
            try:
                markup = list(query.message.reply_markup.inline_keyboard) if query.message.reply_markup else []
                new_markup = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(
                            btn.text.replace("\U0001f516", "\U0001f4cb"),
                            callback_data=btn.callback_data.replace("bm_add:", "bm_rm:")
                        ) if btn.callback_data and btn.callback_data.startswith(f"bm_add:{item_id}") else btn
                        for btn in row
                    ]
                    for row in markup
                ])
                await query.edit_message_reply_markup(reply_markup=new_markup)
            except Exception:
                pass
        else:
            await query.answer("Failed to save bookmark. Try again.", show_alert=True)
        return

    if query.data.startswith("bm_rm:"):
        item_id = query.data.split(":", 1)[1]
        user_id = query.from_user.id
        from bot.database import remove_bookmark

        success = remove_bookmark(user_id, item_id)
        if success:
            await query.answer("\U0001f5d1 Bookmark removed!")
            # If viewing bookmarks, refresh the list
            if query.message and query.message.reply_markup:
                # Check if we're in myduas view
                markup = list(query.message.reply_markup.inline_keyboard)
                has_myduas = any(
                    btn.callback_data and btn.callback_data.startswith("myduas_page")
                    for row in markup for btn in row
                )
                if has_myduas:
                    from bot.handlers.commands import build_myduas_message
                    text, kmarkup = build_myduas_message(user_id, page=0)
                    await query.edit_message_text(text, parse_mode="HTML", reply_markup=kmarkup)
                else:
                    # Just update button
                    try:
                        new_markup = InlineKeyboardMarkup([
                            [
                                InlineKeyboardButton(
                                    btn.text.replace("\U0001f4cb", "\U0001f516"),
                                    callback_data=btn.callback_data.replace("bm_rm:", "bm_add:")
                                ) if btn.callback_data and btn.callback_data.startswith(f"bm_rm:{item_id}") else btn
                                for btn in row
                            ]
                            for row in markup
                        ])
                        await query.edit_message_reply_markup(reply_markup=new_markup)
                    except Exception:
                        pass
        else:
            await query.answer("Failed to remove bookmark.", show_alert=True)
        return

    if query.data.startswith("bm_view:"):
        item_id = query.data.split(":", 1)[1]
        user_id = query.from_user.id
        from bot.database import get_user_bookmarks
        bms = get_user_bookmarks(user_id, limit=100)
        bm = next((b for b in bms if b.get("item_id") == item_id), None)
        if not bm:
            await query.answer("Bookmark not found!", show_alert=True)
            return
        await query.answer()
        doc_type = bm.get("type", "dua")
        title = bm.get("title", item_id)
        snippet = bm.get("snippet", "")
        url = bm.get("url", "")
        text = f"\U0001f516 <b>Bookmark: {title}</b>\n\n"
        if snippet:
            text += f"<i>{snippet[:1000]}</i>\n\n"
        if url:
            text += f"<a href='{url}'>\U0001f517 View Source</a>"
        buttons = []
        # Add audio button for quran bookmarks
        if doc_type == "quran":
            from bot.quran_scraper import get_verse_audio_url
            # Extract surah_no and ayah_no from item_id (format: quran_{surah}_{ayah})
            parts = item_id.split("_")
            if len(parts) >= 3:
                try:
                    bm_surah = int(parts[1])
                    bm_ayah = int(parts[2])
                    audio_url = get_verse_audio_url(bm_surah, bm_ayah)
                    buttons.append([InlineKeyboardButton("\u25b6\ufe0f Listen to Recitation", url=audio_url)])
                except (ValueError, IndexError):
                    pass
        buttons.append([InlineKeyboardButton("\U0001f5d1 Remove", callback_data=f"bm_rm:{item_id}")])
        buttons.append([InlineKeyboardButton("⬅️ Back to Bookmarks", callback_data="myduas_page:0")])
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
        return

    if query.data.startswith("myduas_page:"):
        await query.answer()
        page = int(query.data.split(":")[1])
        user_id = query.from_user.id
        from bot.handlers.commands import build_myduas_message
        text, markup = build_myduas_message(user_id, page=page)
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
        return
