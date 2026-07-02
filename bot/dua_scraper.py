import re
import httpx
import json
import asyncio
from bot.config import logger
from bot.vectordb import add_documents, document_exists, delete_by_id_prefix, count_by_type
from bot.search import rebuild_bm25_index

DUA_SOURCE_URL = "https://dua.gtaf.org"
DUA_COLLECTION_PREFIX = "dua_"

# Module-level category cache populated at startup or on first access.
# Each entry: (slug, display_name)
_dua_categories: list = []
_dua_categories_loaded: bool = False
# Separate cache for chap_id → slug mapping (preserves real API IDs)
_chap_id_to_slug: dict = {}

def extract_next_data(html: str) -> dict:
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*type="application/json"[^>]*>({.*?})</script>', html, re.DOTALL)
    if not match:
        return None
    return json.loads(match.group(1))

async def discover_dua_ids() -> list[int]:
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(f"{DUA_SOURCE_URL}/en/")
            response.raise_for_status()
            json_data = extract_next_data(response.text)
            if not json_data:
                logger.error("Could not extract __NEXT_DATA__ from homepage")
                return []
            props = json_data.get("props", {}).get("pageProps", {})
            dua_list = props.get("duaResponse", {}).get("data", [])
            if not dua_list:
                links = re.findall(r'href="(/en/dua/(\d+))"', response.text)
                ids = sorted(set(int(d[1]) for d in links))
                if ids:
                    return ids
                logger.error("Could not discover dua IDs from homepage")
                return []
            ids = sorted(set(int(d.get("id", 0)) for d in dua_list if d.get("id")))
            if ids:
                return ids
            links = re.findall(r'href="(/en/dua/(\d+))"', response.text)
            ids = sorted(set(int(d[1]) for d in links))
            return ids if ids else []
    except Exception as e:
        logger.error(f"Error discovering dua IDs: {e}")
        return []

async def _get_category_map() -> dict:
    """Fetches chapter category data and populates the _dua_categories cache.
    Returns {chap_id: slug} mapping for use during dua ingestion."""
    global _dua_categories, _dua_categories_loaded, _chap_id_to_slug
    if _dua_categories_loaded and _chap_id_to_slug:
        return dict(_chap_id_to_slug)
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(f"{DUA_SOURCE_URL}/en/")
            response.raise_for_status()
            json_data = extract_next_data(response.text)
            if json_data:
                props = json_data.get("props", {}).get("pageProps", {})
                cat_data = props.get("chapData", [])
                if cat_data:
                    _dua_categories.clear()
                    _chap_id_to_slug.clear()
                    seen_slugs = set()
                    for c in cat_data:
                        slug = c.get("slug", "")
                        chap_id = c.get("id")
                        if slug and slug not in seen_slugs:
                            seen_slugs.add(slug)
                            display = c.get("chapname", slug.replace("-", " ").title())
                            _dua_categories.append((slug, display))
                        if chap_id is not None:
                            _chap_id_to_slug[str(chap_id)] = slug
                    if _dua_categories:
                        _dua_categories_loaded = True
                        return dict(_chap_id_to_slug)
            slugs = re.findall(r'href="/en/([^/]+)/all/"', response.text)
            if slugs:
                _dua_categories.clear()
                _chap_id_to_slug.clear()
                seen_slugs = set()
                for i, slug in enumerate(slugs):
                    if slug not in seen_slugs:
                        seen_slugs.add(slug)
                        display = slug.replace("-", " ").title()
                        _dua_categories.append((slug, display))
                    _chap_id_to_slug[str(i + 1)] = slug
                _dua_categories_loaded = True
                return dict(_chap_id_to_slug)
            return {}
    except Exception as e:
        logger.error(f"Error fetching category map: {e}")
        return {}

def get_cached_dua_categories() -> list:
    """Returns cached list of (slug, display_name) tuples.
    Returns empty list if categories haven't been loaded yet."""
    return list(_dua_categories)

async def fetch_dua(dua_id: int) -> dict:
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(f"{DUA_SOURCE_URL}/en/dua/{dua_id}")
            response.raise_for_status()
            json_data = extract_next_data(response.text)
            if not json_data:
                return None
            props = json_data.get("props", {}).get("pageProps", {})
            dua_meta = props.get("dua", {})
            segments = props.get("duaDetailsList", [])
            if not dua_meta or not segments:
                return None
            chap_id = dua_meta.get("chap_id")
            chapname = dua_meta.get("chapname", "")
            category_map = await _get_category_map()
            category = category_map.get(str(chap_id), "general")
            arabic_parts = []
            translations = []
            transliterations = []
            references = set()
            for seg in segments:
                if seg.get("arabic"):
                    arabic_parts.append(seg["arabic"])
                if seg.get("translations"):
                    translations.append(seg["translations"])
                if seg.get("transliteration"):
                    transliterations.append(seg["transliteration"])
                if seg.get("reference"):
                    references.add(seg["reference"])
            return {
                "id": f"{DUA_COLLECTION_PREFIX}{dua_id}",
                "type": "dua",
                "dua_id": dua_id,
                "dua_name": dua_meta.get("duaname", f"Dua #{dua_id}"),
                "category": category,
                "chapname": chapname,
                "arabic": "\n".join(arabic_parts),
                "transliteration": "\n".join(transliterations),
                "translation": "\n".join(translations),
                "reference": " | ".join(sorted(references)),
                "url": f"{DUA_SOURCE_URL}/en/dua/{dua_id}",
                "content": (
                    f"Dua: {dua_meta.get('duaname', f'Dua #{dua_id}')}\n"
                    f"Category: {category}\n\n"
                    f"Arabic:\n{chr(10).join(arabic_parts)}\n\n"
                    f"Transliteration:\n{chr(10).join(transliterations)}\n\n"
                    f"Translation:\n{chr(10).join(translations)}\n\n"
                    f"Source: {' | '.join(sorted(references))}"
                )
            }
    except Exception as e:
        logger.error(f"Error fetching dua {dua_id}: {e}")
        return None

async def get_dua_stats() -> dict:
    dua_count = 0
    try:
        all_docs = []
        from bot.vectordb import get_client
        client = get_client()
        collection = client.get_collection("knowledge_base")
        all_docs = collection.get(include=["metadatas"])
        if all_docs and all_docs["metadatas"]:
            dua_count = sum(1 for m in all_docs["metadatas"] if m and m.get("type") == "dua")
    except Exception:
        pass
    return {"indexed_duas": dua_count}

async def ingest_all_duas(force_reindex: bool = False, progress_callback=None) -> int:
    ids = await discover_dua_ids()
    if not ids:
        logger.warning("No dua IDs discovered")
        return 0
    logger.info(f"Discovered {len(ids)} duas")

    indexed_count = count_by_type("dua")
    if force_reindex or indexed_count == 0:
        deleted = delete_by_id_prefix(DUA_COLLECTION_PREFIX)
        if deleted:
            logger.info(f"Removed {deleted} stale dua documents before re-indexing")
        force_reindex = True

    new_count = 0
    batch = []
    for i, dua_id in enumerate(ids):
        doc_id = f"{DUA_COLLECTION_PREFIX}{dua_id}"
        if not force_reindex and document_exists(doc_id):
            continue
        dua = await fetch_dua(dua_id)
        if not dua:
            continue
        batch.append(dua)
        new_count += 1
        if len(batch) >= 10:
            add_documents(batch)
            batch = []
        if progress_callback and (i + 1) % 50 == 0:
            progress_callback(i + 1, len(ids))
        await asyncio.sleep(0.1)
    if batch:
        add_documents(batch)
    if new_count > 0:
        rebuild_bm25_index()
    logger.info(f"Ingested {new_count} new duas")
    return new_count
