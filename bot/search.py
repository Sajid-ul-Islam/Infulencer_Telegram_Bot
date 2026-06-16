import re
from rank_bm25 import BM25Okapi
from bot.vectordb import search_vector, build_bm25_corpus
from bot.config import logger

_bm25_index = None
_bm25_docs = []
_bm25_metadatas = []

def _tokenize(text: str) -> list[str]:
    return re.findall(r'\w+', text.lower())

def _rebuild_bm25():
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

def search_bm25(query: str, n_results: int = 5) -> list[dict]:
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

def hybrid_search(query: str, n_results: int = 5, alpha: float = 0.5) -> list[dict]:
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

def rerank(query: str, hits: list[dict], top_n: int = 3) -> list[dict]:
    if not hits:
        return []
    try:
        from sentence_transformers import CrossEncoder
        model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", max_length=512)
        pairs = [[query, hit["text"][:512]] for hit in hits]
        scores = model.predict(pairs)
        for i, hit in enumerate(hits):
            hit["score"] = float(scores[i])
        hits.sort(key=lambda x: x["score"], reverse=True)
    except Exception as e:
        logger.warning(f"Cross-encoder reranking unavailable: {e}")
    return hits[:top_n]

def search_pipeline(query: str, n_results: int = 5, use_rerank: bool = True) -> str:
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

def rebuild_bm25_index():
    _rebuild_bm25()
