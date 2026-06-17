import re
import httpx
import json
import asyncio
from bot.config import logger
from bot.vectordb import add_documents, document_exists, get_document_count
from bot.search import rebuild_bm25_index

DUA_SOURCE_URL = "https://dua.gtaf.org"
DUA_COLLECTION_PREFIX = "dua_"

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

_category_map_cache = None

async def _get_category_map() -> dict:
    global _category_map_cache
    if _category_map_cache:
        return _category_map_cache
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(f"{DUA_SOURCE_URL}/en/")
            response.raise_for_status()
            json_data = extract_next_data(response.text)
            if json_data:
                props = json_data.get("props", {}).get("pageProps", {})
                cat_data = props.get("chapData", [])
                if cat_data:
                    _category_map_cache = {str(c.get("id")): c.get("slug", "general") for c in cat_data}
                    if _category_map_cache:
                        return _category_map_cache
            slugs = re.findall(r'href="/en/([^/]+)/all/"', response.text)
            chap_elements = re.findall(r'data-chap-id="(\d+)"', response.text)
            if slugs and not chap_elements:
                _category_map_cache = {str(i+1): slug for i, slug in enumerate(slugs)}
            elif slugs and chap_elements:
                _category_map_cache = {chap_elements[i]: slug for i, slug in enumerate(slugs) if i < len(chap_elements)}
            return _category_map_cache or {}
    except Exception as e:
        logger.error(f"Error fetching category map: {e}")
        return {}

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
    if force_reindex:
        from bot.vectordb import get_collection
        collection = get_collection()
        existing = collection.get(include=["metadatas"])
        if existing and existing["ids"]:
            dua_ids_to_delete = [existing["ids"][i] for i, m in enumerate(existing["metadatas"]) if m and m.get("type") == "dua"]
            if dua_ids_to_delete:
                for i in range(0, len(dua_ids_to_delete), 100):
                    batch = dua_ids_to_delete[i:i+100]
                    try:
                        collection.delete(ids=batch)
                    except Exception as e:
                        logger.error(f"Error deleting batch: {e}")
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
