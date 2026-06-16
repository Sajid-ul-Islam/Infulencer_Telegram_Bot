from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ContextTypes
from bot.config import logger, INLINE_MAX_RESULTS
from bot.ai import search_knowledge_base, search_dua, search_quran

TOPICS = {
    "iman": "ঈমান (Faith)",
    "salah": "সালাত (Prayer)",
    "zakat": "যাকাত (Charity)",
    "roza": "রোজা (Fasting)",
    "hajj": "হজ্জ (Pilgrimage)",
    "nikah": "বিয়ে (Marriage)",
    "talaq": "তালাক (Divorce)",
    "business": "ব্যবসা (Business)",
    "halal": "হালাল-হারাম (Halal-Haram)"
}

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query.strip().lower()
    if not query:
        results = [
            InlineQueryResultArticle(
                id=key,
                title=label,
                input_message_content=InputTextMessageContent(f"/{key}")
            )
            for key, label in TOPICS.items()
        ]
        await update.inline_query.answer(results, cache_time=60, is_personal=True)
        return

    results = []
    seen = set()

    try:
        quran_results = search_quran(query)
        for r in quran_results[:3]:
            rid = f"q_{r.get('id', r['metadata'].get('surah', '0'))}"
            if rid in seen:
                continue
            seen.add(rid)
            surah_num = r["metadata"].get("surah", "")
            verse_num = r["metadata"].get("verse", "")
            arabic = r["metadata"].get("arabic", "")
            bangla = r["metadata"].get("bangla", "")
            text = f"📖 {arabic}\n\n{bangla}\n\n— সূরা {surah_num}, আয়াত {verse_num}"
            results.append(InlineQueryResultArticle(
                id=rid,
                title=f"Quran {surah_num}:{verse_num}",
                description=bangla[:80],
                input_message_content=InputTextMessageContent(text)
            ))
    except Exception as e:
        logger.error(f"Inline Quran error: {e}")

    try:
        dua_results = search_dua(query)
        for r in dua_results[:3]:
            rid = f"d_{r.get('id', r['metadata'].get('source', '0'))}"
            if rid in seen:
                continue
            seen.add(rid)
            text = r["metadata"].get("text", "") or r["metadata"].get("bangla", "")
            en = r["metadata"].get("english", "")
            desc = (en or text)[:80]
            results.append(InlineQueryResultArticle(
                id=rid,
                title=f"🤲 Dua: {desc}",
                description=desc,
                input_message_content=InputTextMessageContent(text)
            ))
    except Exception as e:
        logger.error(f"Inline Dua error: {e}")

    try:
        kb_results = search_knowledge_base(query)
        for r in kb_results[:3]:
            rid = f"kb_{r.get('id', '0')}"
            if rid in seen:
                continue
            seen.add(rid)
            content = r.get("content", "")[:200]
            results.append(InlineQueryResultArticle(
                id=rid,
                title=f"📚 KB: {content[:60]}",
                description=content[:80],
                input_message_content=InputTextMessageContent(content)
            ))
    except Exception as e:
        logger.error(f"Inline KB error: {e}")

    if not results:
        results.append(InlineQueryResultArticle(
            id="no_results",
            title="No results found",
            description="Try a different search term",
            input_message_content=InputTextMessageContent(f"Sorry, no results for '{query}'.")
        ))

    await update.inline_query.answer(results[:INLINE_MAX_RESULTS], cache_time=30, is_personal=True)
