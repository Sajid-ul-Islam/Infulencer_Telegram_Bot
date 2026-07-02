import httpx
import asyncio
from bot.config import logger
from bot.vectordb import add_documents, document_exists, delete_by_id_prefix, count_by_type
from bot.search import rebuild_bm25_index

API_BASE = "https://data.gtaf.org/api"
API_KEY = "0ClaywbaDD4osAg3HSAAqo3DExgGEudk"
TRANSLATION_ID = 1

QURAN_COLLECTION_PREFIX = "quran_"

SURAH_NAMES = {
    1: ("Al-Fatiha", "الفاتحة", "The Opening", 7, "Meccan"),
    2: ("Al-Baqarah", "البقرة", "The Cow", 286, "Medinan"),
    3: ("Aal-Imran", "آل عمران", "Family of Imran", 200, "Medinan"),
    4: ("An-Nisa", "النساء", "The Women", 176, "Medinan"),
    5: ("Al-Maidah", "المائدة", "The Table Spread", 120, "Medinan"),
    6: ("Al-An'am", "الأنعام", "The Cattle", 165, "Meccan"),
    7: ("Al-A'raf", "الأعراف", "The Heights", 206, "Meccan"),
    8: ("Al-Anfal", "الأنفال", "The Spoils of War", 75, "Medinan"),
    9: ("At-Tawbah", "التوبة", "The Repentance", 129, "Medinan"),
    10: ("Yunus", "يونس", "Jonah", 109, "Meccan"),
    11: ("Hud", "هود", "Hud", 123, "Meccan"),
    12: ("Yusuf", "يوسف", "Joseph", 111, "Meccan"),
    13: ("Ar-Ra'd", "الرعد", "The Thunder", 43, "Medinan"),
    14: ("Ibrahim", "ابراهيم", "Abraham", 52, "Meccan"),
    15: ("Al-Hijr", "الحجر", "The Rocky Tract", 99, "Meccan"),
    16: ("An-Nahl", "النحل", "The Bee", 128, "Meccan"),
    17: ("Al-Isra", "الإسراء", "The Night Journey", 111, "Meccan"),
    18: ("Al-Kahf", "الكهف", "The Cave", 110, "Meccan"),
    19: ("Maryam", "مريم", "Mary", 98, "Meccan"),
    20: ("Ta-Ha", "طه", "Ta-Ha", 135, "Meccan"),
    21: ("Al-Anbiya", "الأنبياء", "The Prophets", 112, "Meccan"),
    22: ("Al-Hajj", "الحج", "The Pilgrimage", 78, "Medinan"),
    23: ("Al-Mu'minun", "المؤمنون", "The Believers", 118, "Meccan"),
    24: ("An-Nur", "النور", "The Light", 64, "Medinan"),
    25: ("Al-Furqan", "الفرقان", "The Criterion", 77, "Meccan"),
    26: ("Ash-Shu'ara", "الشعراء", "The Poets", 227, "Meccan"),
    27: ("An-Naml", "النمل", "The Ant", 93, "Meccan"),
    28: ("Al-Qasas", "القصص", "The Stories", 88, "Meccan"),
    29: ("Al-Ankabut", "العنكبوت", "The Spider", 69, "Meccan"),
    30: ("Ar-Rum", "الروم", "The Romans", 60, "Meccan"),
    31: ("Luqman", "لقمان", "Luqman", 34, "Meccan"),
    32: ("As-Sajdah", "السجدة", "The Prostration", 30, "Meccan"),
    33: ("Al-Ahzab", "الأحزاب", "The Combined Forces", 73, "Medinan"),
    34: ("Saba", "سبأ", "Sheba", 54, "Meccan"),
    35: ("Fatir", "فاطر", "Originator", 45, "Meccan"),
    36: ("Ya-Sin", "يس", "Ya-Sin", 83, "Meccan"),
    37: ("As-Saffat", "الصافات", "Those Who Set The Ranks", 182, "Meccan"),
    38: ("Sad", "ص", "Sad", 88, "Meccan"),
    39: ("Az-Zumar", "الزمر", "The Groups", 75, "Meccan"),
    40: ("Ghafir", "غافر", "The Forgiver", 85, "Meccan"),
    41: ("Fussilat", "فصلت", "Explained in Detail", 54, "Meccan"),
    42: ("Ash-Shura", "الشورى", "The Consultation", 53, "Meccan"),
    43: ("Az-Zukhruf", "الزخرف", "The Gold Adornments", 89, "Meccan"),
    44: ("Ad-Dukhan", "الدخان", "The Smoke", 59, "Meccan"),
    45: ("Al-Jathiyah", "الجاثية", "The Kneeling", 37, "Meccan"),
    46: ("Al-Ahqaf", "الأحقاف", "The Wind-Curved Sandhills", 35, "Meccan"),
    47: ("Muhammad", "محمد", "Muhammad", 38, "Medinan"),
    48: ("Al-Fath", "الفتح", "The Victory", 29, "Medinan"),
    49: ("Al-Hujurat", "الحجرات", "The Rooms", 18, "Medinan"),
    50: ("Qaf", "ق", "Qaf", 45, "Meccan"),
    51: ("Adh-Dhariyat", "الذاريات", "The Winnowing Winds", 60, "Meccan"),
    52: ("At-Tur", "الطور", "The Mount", 49, "Meccan"),
    53: ("An-Najm", "النجم", "The Star", 62, "Meccan"),
    54: ("Al-Qamar", "القمر", "The Moon", 55, "Meccan"),
    55: ("Ar-Rahman", "الرحمن", "The Most Gracious", 78, "Medinan"),
    56: ("Al-Waqi'ah", "الواقعة", "The Inevitable", 96, "Meccan"),
    57: ("Al-Hadid", "الحديد", "The Iron", 29, "Medinan"),
    58: ("Al-Mujadilah", "المجادلة", "The Pleading Woman", 22, "Medinan"),
    59: ("Al-Hashr", "الحشر", "The Gathering", 24, "Medinan"),
    60: ("Al-Mumtahanah", "الممتحنة", "The Examined Woman", 13, "Medinan"),
    61: ("As-Saff", "الصف", "The Row", 14, "Medinan"),
    62: ("Al-Jumu'ah", "الجمعة", "Friday", 11, "Medinan"),
    63: ("Al-Munafiqun", "المنافقون", "The Hypocrites", 11, "Medinan"),
    64: ("At-Taghabun", "التغابن", "The Mutual Disillusion", 18, "Medinan"),
    65: ("At-Talaq", "الطلاق", "The Divorce", 12, "Medinan"),
    66: ("At-Tahrim", "التحريم", "The Prohibition", 12, "Medinan"),
    67: ("Al-Mulk", "الملك", "The Kingdom", 30, "Meccan"),
    68: ("Al-Qalam", "القلم", "The Pen", 52, "Meccan"),
    69: ("Al-Haqqah", "الحاقة", "The Reality", 52, "Meccan"),
    70: ("Al-Ma'arij", "المعارج", "The Ascending Stairways", 44, "Meccan"),
    71: ("Nuh", "نوح", "Noah", 28, "Meccan"),
    72: ("Al-Jinn", "الجن", "The Jinn", 28, "Meccan"),
    73: ("Al-Muzzammil", "المزمل", "The Enshrouded One", 20, "Meccan"),
    74: ("Al-Muddaththir", "المدثر", "The Cloaked One", 56, "Meccan"),
    75: ("Al-Qiyamah", "القيامة", "The Resurrection", 40, "Meccan"),
    76: ("Al-Insan", "الانسان", "The Man", 31, "Medinan"),
    77: ("Al-Mursalat", "المرسلات", "The Emissaries", 50, "Meccan"),
    78: ("An-Naba", "النبأ", "The Great News", 40, "Meccan"),
    79: ("An-Nazi'at", "النازعات", "Those Who Pull Out", 46, "Meccan"),
    80: ("Abasa", "عبس", "He Frowned", 42, "Meccan"),
    81: ("At-Takwir", "التكوير", "The Overthrowing", 29, "Meccan"),
    82: ("Al-Infitar", "الانفطار", "The Cleaving", 19, "Meccan"),
    83: ("Al-Mutaffifin", "المطففين", "The Defrauding", 36, "Meccan"),
    84: ("Al-Inshiqaq", "الانشقاق", "The Sundering", 25, "Meccan"),
    85: ("Al-Buruj", "البروج", "The Mansions of the Stars", 22, "Meccan"),
    86: ("At-Tariq", "الطارق", "The Nightcommer", 17, "Meccan"),
    87: ("Al-A'la", "الأعلى", "The Most High", 19, "Meccan"),
    88: ("Al-Ghashiyah", "الغاشية", "The Overwhelming", 26, "Meccan"),
    89: ("Al-Fajr", "الفجر", "The Dawn", 30, "Meccan"),
    90: ("Al-Balad", "البلد", "The City", 20, "Meccan"),
    91: ("Ash-Shams", "الشمس", "The Sun", 15, "Meccan"),
    92: ("Al-Layl", "الليل", "The Night", 21, "Meccan"),
    93: ("Ad-Duha", "الضحى", "The Morning Brightness", 11, "Meccan"),
    94: ("Ash-Sharh", "الشرح", "The Relief", 8, "Meccan"),
    95: ("At-Tin", "التين", "The Fig", 8, "Meccan"),
    96: ("Al-Alaq", "العلق", "The Clot", 19, "Meccan"),
    97: ("Al-Qadr", "القدر", "The Power", 5, "Meccan"),
    98: ("Al-Bayyinah", "البينة", "The Clear Proof", 8, "Medinan"),
    99: ("Az-Zalzalah", "الزلزلة", "The Earthquake", 8, "Medinan"),
    100: ("Al-Adiyat", "العاديات", "The Chargers", 11, "Meccan"),
    101: ("Al-Qari'ah", "القارعة", "The Calamity", 11, "Meccan"),
    102: ("At-Takathur", "التكاثر", "The Rivalry in Worldly Increase", 8, "Meccan"),
    103: ("Al-Asr", "العصر", "The Declining Day", 3, "Meccan"),
    104: ("Al-Humazah", "الهمزة", "The Traducer", 9, "Meccan"),
    105: ("Al-Fil", "الفيل", "The Elephant", 5, "Meccan"),
    106: ("Quraysh", "قريش", "Quraysh", 4, "Meccan"),
    107: ("Al-Ma'un", "الماعون", "The Small Kindnesses", 7, "Meccan"),
    108: ("Al-Kawthar", "الكوثر", "The Abundance", 3, "Meccan"),
    109: ("Al-Kafirun", "الكافرون", "The Disbelievers", 6, "Meccan"),
    110: ("An-Nasr", "النصر", "The Divine Support", 3, "Medinan"),
    111: ("Al-Masad", "المسد", "The Palm Fiber", 5, "Meccan"),
    112: ("Al-Ikhlas", "الإخلاص", "The Sincerity", 4, "Meccan"),
    113: ("Al-Falaq", "الفلق", "The Daybreak", 5, "Meccan"),
    114: ("An-Nas", "الناس", "Mankind", 6, "Meccan"),
}

async def _api_get(path: str, params: dict = None):
    headers = {"api-key": API_KEY, "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        url = f"{API_BASE}{path}"
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()

async def fetch_surah_verses(surah_no: int) -> list[dict]:
    data = await _api_get("/quran/verses/", {"chapter_id": surah_no})
    return data.get("results", [])

async def fetch_surah_translation(surah_no: int, translation_id: int = TRANSLATION_ID) -> dict:
    data = await _api_get(f"/quran/translations/{translation_id}/", {"chapter_id": surah_no})
    results = data.get("results", [])
    return {r["verse_key"]: r["text"] for r in results}

def build_ayah_document(surah_no: int, verse_data: dict, translation_text: str) -> dict:
    verse_key = verse_data["verse_key"]
    ayah_no = verse_data["no"]
    arabic = verse_data["text_uthmani"]
    words = verse_data.get("words", [])
    word_details = []
    for w in words:
        w_trans = w.get("translation", "")
        w_translit = w.get("transliteration", "")
        w_text = w.get("text_uthmani", "")
        if w_trans or w_translit:
            word_details.append(f"{w_text}  — {w_translit} : {w_trans}")
    word_by_word = "\n".join(word_details) if word_details else ""
    surah_info = SURAH_NAMES.get(surah_no, (f"Surah {surah_no}", "", "", 0, ""))
    content_parts = [
        f"Surah: {surah_info[0]} ({surah_no}) — {surah_info[2]}",
        f"Ayah: {ayah_no}",
        f"Revelation: {surah_info[4]}",
        f"Key: {verse_key}",
        "",
        f"Arabic:\n{arabic}",
    ]
    if word_by_word:
        content_parts.append(f"\nWord-by-Word:\n{word_by_word}")
    content_parts.append(f"\nTranslation (Sahih International):\n{translation_text}")
    content = "\n".join(content_parts)
    doc_id = f"{QURAN_COLLECTION_PREFIX}{surah_no}_{ayah_no}"
    return {
        "id": doc_id,
        "type": "quran",
        "surah_no": surah_no,
        "surah_name": surah_info[0],
        "surah_name_arabic": surah_info[1],
        "surah_name_english": surah_info[2],
        "ayah_no": ayah_no,
        "verse_key": verse_key,
        "juz": verse_data.get("juz_number", 0),
        "page": verse_data.get("page_number", 0),
        "arabic": arabic,
        "translation": translation_text,
        "revelation_type": surah_info[4],
        "content": content
    }

async def ingest_quran(force_reindex: bool = False, progress_callback=None) -> int:
    indexed_count = count_by_type("quran")
    if force_reindex or indexed_count == 0:
        deleted = delete_by_id_prefix(QURAN_COLLECTION_PREFIX)
        if deleted:
            logger.info(f"Removed {deleted} stale Quran documents before re-indexing")
        force_reindex = True

    new_count = 0
    batch = []
    surahs_processed = 0
    total_surahs = len(SURAH_NAMES)
    for surah_no in sorted(SURAH_NAMES.keys()):
        try:
            verses = await fetch_surah_verses(surah_no)
            if not verses:
                logger.warning(f"No verses for surah {surah_no}")
                continue
            translations = await fetch_surah_translation(surah_no)
            for verse in verses:
                verse_key = verse["verse_key"]
                doc_id = f"{QURAN_COLLECTION_PREFIX}{surah_no}_{verse['no']}"
                if not force_reindex and document_exists(doc_id):
                    continue
                translation_text = translations.get(verse_key, "")
                doc = build_ayah_document(surah_no, verse, translation_text)
                batch.append(doc)
                new_count += 1
                if len(batch) >= 20:
                    add_documents(batch)
                    batch = []
            surahs_processed += 1
            if progress_callback:
                progress_callback(surahs_processed, total_surahs)
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"Error processing surah {surah_no}: {e}")
    if batch:
        add_documents(batch)
    if new_count > 0:
        rebuild_bm25_index()
    logger.info(f"Ingested {new_count} new Quran verses from {surahs_processed} surahs")
    return new_count

async def get_quran_stats() -> dict:
    quran_count = 0
    try:
        from bot.vectordb import get_client
        client = get_client()
        collection = client.get_collection("knowledge_base")
        all_docs = collection.get(include=["metadatas"])
        if all_docs and all_docs["metadatas"]:
            quran_count = sum(1 for m in all_docs["metadatas"] if m and m.get("type") == "quran")
    except Exception:
        pass
    return {"indexed_verses": quran_count, "total_surahs": 114}
