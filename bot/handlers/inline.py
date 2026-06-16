from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ContextTypes
from bot.config import logger, INLINE_MAX_RESULTS
from bot.vectordb import search_vector
from bot.search import search_bm25

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

def _search_wrapped(query: str, doc_type: str, n: int = 3) -> list[dict]:
    hits = search_vector(query, n_results=n * 2, where={"type": doc_type})
    if hits:
        return hits[:n]
    bm25 = search_bm25(query, n_results=n * 2)
    return [h for h in bm25 if h.get("metadata", {}).get("type") == doc_type][:n]

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

    for r in _search_wrapped(query, "quran"):
        rid = f"q_{r.get('id', '0')}"
        if rid in seen:
            continue
        seen.add(rid)
        meta = r["metadata"]
        surah = meta.get("surah_name", meta.get("surah", str(meta.get("surah_no", ""))))
        verse = meta.get("ayah_no", meta.get("verse", ""))
        arabic = meta.get("arabic", "")
        translation = meta.get("translation", meta.get("bangla", ""))
        text = f"📖 {arabic}\n\n{translation}\n\n— {surah} {verse}"
        results.append(InlineQueryResultArticle(
            id=rid,
            title=f"Quran {surah}:{verse}",
            description=translation[:80],
            input_message_content=InputTextMessageContent(text)
        ))

    for r in _search_wrapped(query, "dua"):
        rid = f"d_{r.get('id', '0')}"
        if rid in seen:
            continue
        seen.add(rid)
        meta = r["metadata"]
        text = meta.get("arabic", "") or meta.get("text", meta.get("bangla", ""))
        en = meta.get("english", meta.get("translation", ""))
        desc = (en or text)[:80]
        results.append(InlineQueryResultArticle(
            id=rid,
            title=f"🤲 Dua: {desc}",
            description=desc,
            input_message_content=InputTextMessageContent(text)
        ))

    for r in _search_wrapped(query, "kb"):
        rid = f"kb_{r.get('id', '0')}"
        if rid in seen:
            continue
        seen.add(rid)
        content = r.get("text", "")[:200]
        meta = r.get("metadata", {})
        title = meta.get("title", content[:60])
        results.append(InlineQueryResultArticle(
            id=rid,
            title=f"📚 KB: {title[:60]}",
            description=content[:80],
            input_message_content=InputTextMessageContent(content or "No content")
        ))

    if not results:
        results.append(InlineQueryResultArticle(
            id="no_results",
            title="No results found",
            description="Try a different search term",
            input_message_content=InputTextMessageContent(f"Sorry, no results for '{query}'.")
        ))

    await update.inline_query.answer(results[:INLINE_MAX_RESULTS], cache_time=30, is_personal=True)
