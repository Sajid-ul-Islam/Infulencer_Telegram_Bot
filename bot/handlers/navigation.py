"""Dua and Quran browsing/navigation callback handlers."""
import html
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger("bot")


async def handle_dua_category(query, category_slug: str) -> None:
    """Handle dua_cat:{slug} callbacks."""
    await query.answer(f"Searching {category_slug} duas...")
    from bot.search import search_duas_by_category, get_rag_status
    from bot.handlers.commands import format_empty_rag_message

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
        bm_row = []
        for meta in metas[:3]:
            item_id = meta.get("id", "")
            dua_name = meta.get("dua_name", "Dua")
            if item_id:
                bm_row.append(InlineKeyboardButton(
                    f"🔖 {dua_name[:20]}",
                    callback_data=f"bm_add:{item_id}:dua"
                ))
        if bm_row:
            buttons.append(bm_row[:2])
            if len(bm_row) > 2:
                buttons.append(bm_row[2:])
    buttons.append([InlineKeyboardButton("⬅️ Back to Dua Menu", callback_data="dua_menu")])

    if not result or "No duas found" in result:
        await query.edit_message_text(
            "🤲 No duas found for this category.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
    else:
        message_text = f"🤲 <b>{html.escape(cat_name)}</b>\n\n{html.escape(result)}"
        if len(message_text) > 4000:
            result_parts = result.split("\n\n---\n\n")
            safe_result = html.escape("\n\n---\n\n".join(result_parts[:1]))
            message_text = f"🤲 <b>{html.escape(cat_name)}</b>\n\n{safe_result}\n\n<i>...[Results too long to display fully]</i>"

        try:
            await query.edit_message_text(
                message_text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
        except Exception as e:
            logger.error(f"Error editing dua message: {e}")
            await query.edit_message_text("An error occurred while displaying the results. Please try a different query.")


async def handle_dua_menu(query) -> None:
    """Handle dua_menu callback — return to dua category menu."""
    from bot.handlers.commands import build_dua_menu_keyboard, build_dua_menu_text
    await query.answer()
    await query.edit_message_text(
        build_dua_menu_text(),
        parse_mode="HTML",
        reply_markup=await build_dua_menu_keyboard(),
    )


async def handle_dua_menu_reload(query) -> None:
    """Handle dua_menu_reload — re-fetch categories."""
    from bot.handlers.commands import build_dua_menu_keyboard, build_dua_menu_text
    await query.answer("Loading categories...")
    await query.edit_message_text(
        build_dua_menu_text(),
        parse_mode="HTML",
        reply_markup=await build_dua_menu_keyboard(),
    )


async def handle_quran_menu(query, page: int = 1) -> None:
    """Handle quran_menu:{page} callbacks."""
    from bot.handlers.commands import build_quran_menu_keyboard, build_quran_menu_text
    await query.answer()
    await query.edit_message_text(
        build_quran_menu_text(page=page),
        parse_mode="HTML",
        reply_markup=build_quran_menu_keyboard(page=page),
    )


async def handle_quran_surah(query, surah_no: int, page: int) -> None:
    """Handle quran_surah:{surah_no}:{page} callbacks."""
    await query.answer("Fetching verses...")
    from bot.search import get_surah_verses, get_rag_status
    from bot.handlers.commands import format_empty_rag_message

    if not get_rag_status()["quran_ready"]:
        await query.edit_message_text(format_empty_rag_message("quran"), parse_mode="HTML")
        return

    result, metas, has_next, has_prev = get_surah_verses(surah_no, page=page, limit=5)

    buttons = []
    if metas:
        from bot.quran_scraper import get_verse_audio_url
        audio_row = []
        bm_row = []
        for meta in metas[:5]:
            item_id = meta.get("id", "")
            ayah_no = meta.get("ayah_no", "")
            audio_url = get_verse_audio_url(surah_no, ayah_no)
            audio_row.append(InlineKeyboardButton(
                f"▶️ {ayah_no}",
                url=audio_url
            ))
            if item_id:
                bm_row.append(InlineKeyboardButton(
                    f"🔖 {ayah_no}",
                    callback_data=f"bm_add:{item_id}:quran"
                ))
        if audio_row:
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
    message_text = f"📜 <b>Quran Surah {surah_no} (Page {page})</b>\n\n{html.escape(result)}"

    if len(message_text) > 4000:
        result_parts = result.split("\n\n---\n\n")
        safe_result = html.escape("\n\n---\n\n".join(result_parts[:2]))
        message_text = f"📜 <b>Quran Surah {surah_no} (Page {page})</b>\n\n{safe_result}\n\n<i>...[Verses too long, please use Next]</i>"

    try:
        await query.edit_message_text(message_text, parse_mode="HTML", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error editing quran message: {e}")
        await query.edit_message_text("An error occurred while displaying the verses.")
