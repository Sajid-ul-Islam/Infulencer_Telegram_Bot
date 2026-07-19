"""Bookmark-related callback handlers for dua and Quran items."""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger("bot")


async def handle_bookmark_add(query, parts: list, user_id: int) -> None:
    """Handle bm_add:{item_id}:{doc_type} callbacks."""
    item_id = parts[1]
    doc_type = parts[2] if len(parts) > 2 else "dua"
    from bot.database import save_bookmark, is_bookmarked

    if is_bookmarked(user_id, item_id):
        await query.answer("Already bookmarked! 🔖", show_alert=True)
        return

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
        await query.answer("\U0001f516 Saved! Use /myduas to view.")
        # Record daily engagement for streaks
        try:
            from bot.database import record_daily_engagement
            record_daily_engagement(user_id)
        except Exception:
            pass
        try:
            markup = list(query.message.reply_markup.inline_keyboard) if query.message.reply_markup else []
            new_markup = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        btn.text.replace("🔖", "📋"),
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


async def handle_bookmark_remove(query, item_id: str, user_id: int) -> None:
    """Handle bm_rm:{item_id} callbacks."""
    from bot.database import remove_bookmark

    success = remove_bookmark(user_id, item_id)
    if success:
        await query.answer("🗑 Bookmark removed!")
        if query.message and query.message.reply_markup:
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
                try:
                    new_markup = InlineKeyboardMarkup([
                        [
                            InlineKeyboardButton(
                                btn.text.replace("📋", "🔖"),
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


async def handle_bookmark_view(query, item_id: str, user_id: int) -> None:
    """Handle bm_view:{item_id} callbacks."""
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
    text = f"🔖 <b>Bookmark: {title}</b>\n\n"
    if snippet:
        text += f"<i>{snippet[:1000]}</i>\n\n"
    if url:
        text += f"<a href='{url}'>🔗 View Source</a>"
    buttons = []
    if doc_type == "quran":
        from bot.quran_scraper import get_verse_audio_url
        parts = item_id.split("_")
        if len(parts) >= 3:
            try:
                bm_surah = int(parts[1])
                bm_ayah = int(parts[2])
                audio_url = get_verse_audio_url(bm_surah, bm_ayah)
                buttons.append([InlineKeyboardButton("▶️ Listen to Recitation", url=audio_url)])
            except (ValueError, IndexError):
                pass
    buttons.append([InlineKeyboardButton("🗑 Remove", callback_data=f"bm_rm:{item_id}")])
    buttons.append([InlineKeyboardButton("⬅️ Back to Bookmarks", callback_data="myduas_page:0")])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def handle_myduas_page(query, page: int, user_id: int) -> None:
    """Handle myduas_page:{page} callbacks."""
    await query.answer()
    from bot.handlers.commands import build_myduas_message
    text, markup = build_myduas_message(user_id, page=page)
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
