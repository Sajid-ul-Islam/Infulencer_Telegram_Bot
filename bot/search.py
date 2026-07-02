import re
from typing import List, Dict, Tuple, Optional, Any
from rank_bm25 import BM25Okapi
from bot.vectordb import search_vector, build_bm25_corpus
from bot.config import logger

_bm25_index: Optional[BM25Okapi] = None
_bm25_docs: List[str] = []
_bm25_metadatas: List[Dict[str, Any]] = []

def _tokenize(text: str) -> List[str]:
    """Tokenizes input text into a list of lowercase alphanumeric words."""
    return re.findall(r'\w+', text.lower())

def _rebuild_bm25() -> None:
    """Builds the BM25 index corpus from vector database records."""
    global _bm25_index, _bm25_docs, _bm25_metadatas
    docs, metadatas = build_bm25_corpus()
    if docs:
        tokenized = [_tokenize(d) for d in docs]
        _bm25_index = BM25Okapi(tokenized)
        _bm25_docs = docs
        _bm25_metadatas = metadatas
    else:
        _bm25_index = None
        _bm25_docs = []
        _bm25_metadatas = []

def search_bm25(query: str, n_results: int = 5) -> List[Dict[str, Any]]:
    """Performs exact BM25 keyword matching search over the corpus."""
    if _bm25_index is None:
        _rebuild_bm25()
    if _bm25_index is None:
        return []
    tokenized_query = _tokenize(query)
    scores = _bm25_index.get_scores(tokenized_query)
    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:n_results]
    hits = []
    for idx in top_indices:
        if scores[idx] > 0:
            hits.append({
                "id": _bm25_metadatas[idx].get("id", f"bm25_{idx}"),
                "text": _bm25_docs[idx],
                "metadata": _bm25_metadatas[idx],
                "score": float(scores[idx])
            })
    return hits

def hybrid_search(query: str, n_results: int = 5, alpha: float = 0.5) -> List[Dict[str, Any]]:
    """Combines vector search and BM25 search scores into a single ranked list."""
    vector_hits = search_vector(query, n_results=n_results * 2)
    bm25_hits = search_bm25(query, n_results=n_results * 2)
    combined = {}
    for hit in vector_hits:
        doc_id = hit["id"]
        combined[doc_id] = {"alpha": alpha, "vector_score": hit["score"], "bm25_score": 0.0, "hit": hit}
    for hit in bm25_hits:
        doc_id = hit["id"]
        if doc_id in combined:
            combined[doc_id]["bm25_score"] = hit["score"]
        else:
            combined[doc_id] = {"alpha": alpha, "vector_score": 0.0, "bm25_score": hit["score"], "hit": hit}
    rescored = []
    for doc_id, data in combined.items():
        combined_score = data["alpha"] * data["vector_score"] + (1 - data["alpha"]) * data["bm25_score"]
        data["hit"]["score"] = combined_score
        rescored.append(data["hit"])
    rescored.sort(key=lambda x: x["score"], reverse=True)
    return rescored[:n_results]

_cross_encoder = None

def _get_cross_encoder():
    """Lazy-loaded singleton for the cross-encoder model to avoid reloading on every search."""
    global _cross_encoder
    if _cross_encoder is None:
        from sentence_transformers import CrossEncoder
        _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", max_length=512)
    return _cross_encoder


def rerank(query: str, hits: List[Dict[str, Any]], top_n: int = 3) -> List[Dict[str, Any]]:
    """Reranks search results using a cross-encoder model for improved accuracy."""
    if not hits:
        return []
    try:
        model = _get_cross_encoder()
        pairs = [[query, hit["text"][:512]] for hit in hits]
        scores = model.predict(pairs)
        for i, hit in enumerate(hits):
            hit["score"] = float(scores[i])
        hits.sort(key=lambda x: x["score"], reverse=True)
    except Exception as e:
        logger.warning(f"Cross-encoder reranking unavailable: {e}")
    return hits[:top_n]

def search_pipeline(query: str, n_results: int = 5, use_rerank: bool = True) -> str:
    """Executes the hybrid search and reranking query pipeline for past content."""
    hits = hybrid_search(query, n_results=n_results)
    if not hits:
        return "No relevant past content found for this query."
    if use_rerank and len(hits) > 1:
        hits = rerank(query, hits, top_n=min(3, len(hits)))
    formatted = []
    for hit in hits:
        meta = hit.get("metadata", {})
        formatted.append(
            f"Platform: {meta.get('platform', 'unknown')}\n"
            f"Title: {meta.get('title', 'untitled')}\n"
            f"Content: {hit['text']}\n"
            f"Link: {meta.get('url', '')}"
        )
    return "\n\n---\n\n".join(formatted)

def search_duas(query: str, n_results: int = 5, use_rerank: bool = True) -> str:
    """Executes the RAG search pipeline scoped for Hisnul Muslim duas."""
    hits = search_vector(query, n_results=n_results * 2, where={"type": "dua"})
    if not hits:
        bm25_hits = search_bm25(query, n_results=n_results * 2)
        hits = [h for h in bm25_hits if h.get("metadata", {}) and h.get("metadata", {}).get("type") == "dua"]
    if not hits:
        return "No relevant duas found for this query."
    if use_rerank and len(hits) > 1:
        hits = rerank(query, hits, top_n=min(3, len(hits)))
    formatted = []
    for hit in hits:
        meta = hit.get("metadata", {})
        dua_name = meta.get("dua_name", meta.get("title", "Dua"))
        category = meta.get("category", "")
        formatted.append(
            f"Dua: {dua_name}\n"
            f"Category: {category}\n\n"
            f"Arabic:\n{meta.get('arabic', '')}\n\n"
            f"Transliteration:\n{meta.get('transliteration', '')}\n\n"
            f"Translation:\n{meta.get('translation', '')}\n\n"
            f"Source: {meta.get('reference', '')}\n"
            f"URL: {meta.get('url', '')}"
        )
    return "\n\n---\n\n".join(formatted)

def search_quran(query: str, n_results: int = 5, use_rerank: bool = True) -> str:
    """Executes the RAG search pipeline scoped for Quran verses."""
    hits = search_vector(query, n_results=n_results * 2, where={"type": "quran"})
    if not hits:
        bm25_hits = search_bm25(query, n_results=n_results * 2)
        hits = [h for h in bm25_hits if h.get("metadata", {}) and h.get("metadata", {}).get("type") == "quran"]
    if not hits:
        return "No relevant Quran verses found for this query."
    if use_rerank and len(hits) > 1:
        hits = rerank(query, hits, top_n=min(3, len(hits)))
    formatted = []
    for hit in hits:
        meta = hit.get("metadata", {})
        formatted.append(
            f"Surah: {meta.get('surah_name', '')} ({meta.get('surah_no', '')}) — {meta.get('surah_name_english', '')}\n"
            f"Ayah: {meta.get('ayah_no', '')} ({meta.get('verse_key', '')})\n"
            f"Juz: {meta.get('juz', '')} | Page: {meta.get('page', '')}\n\n"
            f"Arabic:\n{meta.get('arabic', '')}\n\n"
            f"Translation:\n{meta.get('translation', '')}"
        )
    return "\n\n---\n\n".join(formatted)

def rebuild_bm25_index() -> None:
    """Public proxy function to trigger BM25 rebuild."""
    _rebuild_bm25()

def get_rag_status() -> dict:
    """Returns availability and indexed counts for dua/quran RAG collections."""
    from bot import vectordb
    if not vectordb._available():
        return {
            "available": False,
            "dua_count": 0,
            "quran_count": 0,
            "dua_ready": False,
            "quran_ready": False,
        }
    dua_count = vectordb.count_by_type("dua")
    quran_count = vectordb.count_by_type("quran")
    return {
        "available": True,
        "dua_count": dua_count,
        "quran_count": quran_count,
        "dua_ready": dua_count > 0,
        "quran_ready": quran_count > 0,
    }

def format_rag_status_line(collection: str) -> str:
    status = get_rag_status()
    if not status["available"]:
        return "\u26a0\ufe0f Search index is starting up. Please try again in a moment."
    if collection == "dua":
        count = status["dua_count"]
        if count > 0:
            return f"\u2705 <b>{count}</b> duas indexed and ready"
        return "\u23f3 Duas are still being indexed. Categories may take a minute to populate."
    count = status["quran_count"]
    if count > 0:
        return f"\u2705 <b>{count}</b> Quran verses indexed and ready"
    return "\u23f3 Quran verses are still being indexed. Surah browsing may take a minute."

def search_duas_by_category(category_slug: str, max_results: int = 5) -> tuple[str, list]:
    """Retrieves duas filtered by exact category slug (e.g., 'morning-and-evening').
    Uses ChromaDB metadata filtering for exact matches rather than fuzzy vector search.
    Returns (formatted_text, metadata_list) for bookmark button building.
    Results are sorted by dua_id for consistent ordering."""
    from bot.vectordb import get_collection
    try:
        collection = get_collection()
        if not collection:
            return "Search index is not available.", []
        results = collection.get(
            where={"type": "dua", "category": category_slug},
            include=["metadatas"],
            limit=max_results * 2
        )
        if not results or not results.get("metadatas"):
            return "No duas found in this category.", []
        metas = [m for m in results["metadatas"] if m]
        if not metas:
            return "No duas found in this category.", []
        # Sort by dua_id for consistent ordering
        metas.sort(key=lambda m: m.get("dua_id", 0))
        displayed = metas[:max_results]
        formatted = []
        for meta in displayed:
            dua_name = meta.get("dua_name", meta.get("title", "Dua"))
            formatted.append(
                f"Dua: {dua_name}\n"
                f"Arabic:\n{meta.get('arabic', '')}\n\n"
                f"Transliteration:\n{meta.get('transliteration', '')}\n\n"
                f"Translation:\n{meta.get('translation', '')}\n\n"
                f"Source: {meta.get('reference', '')}\n"
                f"URL: {meta.get('url', '')}"
            )
        result_text = "\n\n---\n\n".join(formatted)
        total = len(metas)
        if total > max_results:
            result_text += f"\n\n<i>...and {total - max_results} more duas in this category. Use /dua {category_slug} for more.</i>"
        return result_text, displayed
    except Exception as e:
        logger.error(f"Error fetching duas by category: {e}")
        return "An error occurred while fetching category duas.", []


def get_surah_verses(surah_no: int, page: int = 1, limit: int = 5) -> tuple[str, list, bool, bool]:
    """Fetches a paginated list of verses for a specific Surah from the database.
    Returns (formatted_text, page_metadatas, has_next, has_prev)."""
    from bot.vectordb import get_collection
    try:
        collection = get_collection()
        results = collection.get(where={"surah_no": surah_no}, include=["metadatas"])
        if not results or not results.get("metadatas"):
            return "No verses found for this Surah in the database.", [], False, False
        
        metas = [m for m in results["metadatas"] if m and m.get("type") == "quran"]
        metas.sort(key=lambda x: x.get("ayah_no", 0))
        
        total_verses = len(metas)
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        
        page_metas = metas[start_idx:end_idx]
        
        if not page_metas:
            return "No verses found on this page.", [], False, False
            
        formatted = []
        for meta in page_metas:
            formatted.append(
                f"Surah: {meta.get('surah_name', '')} ({meta.get('surah_no', '')})\n"
                f"Ayah: {meta.get('ayah_no', '')}\n\n"
                f"Arabic:\n{meta.get('arabic', '')}\n\n"
                f"Translation:\n{meta.get('translation', '')}"
            )
            
        has_next = end_idx < total_verses
        has_prev = page > 1
        
        return "\n\n---\n\n".join(formatted), page_metas, has_next, has_prev
    except Exception as e:
        logger.error(f"Error fetching surah verses: {e}")
        return "An error occurred fetching verses.", [], False, False
