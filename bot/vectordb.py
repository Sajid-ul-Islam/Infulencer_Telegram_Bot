import os
import json
import re
from typing import List, Dict, Tuple, Optional, Any
from bot.config import logger

# Path for the lightweight document store JSON file
DOCUMENTS_STORE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "documents_store.json"
)

_METADATA_SKIP_KEYS = frozenset({"content", "id"})
_METADATA_MAX_STR_LEN = 4000


def _build_document_text(post: Dict[str, Any]) -> str:
    content = post.get("content", "")
    title = post.get("title", post.get("dua_name", ""))
    if content and title:
        return f"{title}\n{content}"
    return content or title or ""


def _sanitize_metadata(post: Dict[str, Any], post_id: str) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {
        "platform": post.get("platform", "unknown"),
        "url": post.get("url", ""),
        "date": post.get("date", ""),
        "title": post.get("title", post.get("dua_name", "")),
        "id": post_id,
    }
    for key, value in post.items():
        if key in _METADATA_SKIP_KEYS or key in metadata or value is None:
            continue
        if isinstance(value, bool):
            metadata[key] = value
        elif isinstance(value, int):
            metadata[key] = value
        elif isinstance(value, float):
            metadata[key] = value
        elif isinstance(value, str):
            metadata[key] = value[:_METADATA_MAX_STR_LEN]
        else:
            metadata[key] = str(value)[:_METADATA_MAX_STR_LEN]
    return metadata


class InMemoryDocStore:
    """Lightweight in-memory document store persisted to a JSON file.

    Replaces ChromaDB entirely — no ML models, no vector search.
    For search, use BM25 (keyword-based) via bot/search.py.
    """

    def __init__(self, persist_path: str = DOCUMENTS_STORE_PATH):
        self.persist_path = persist_path
        # Each entry: {"id": str, "text": str, "metadata": dict}
        self._documents: List[Dict[str, Any]] = []
        self._loaded = False
        self._load_from_disk()

    # ── Persistence ──────────────────────────────────────────────

    def _load_from_disk(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not os.path.exists(self.persist_path):
            logger.info("No existing document store found — starting fresh.")
            return
        try:
            with open(self.persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._documents = data if isinstance(data, list) else []
            logger.info(f"Loaded {len(self._documents)} documents from store.")
        except Exception as e:
            logger.warning(f"Failed to load document store: {e}")
            self._documents = []

    def _save_to_disk(self) -> None:
        try:
            with open(self.persist_path, "w", encoding="utf-8") as f:
                json.dump(self._documents, f, ensure_ascii=False, default=str)
        except Exception as e:
            logger.error(f"Failed to save document store: {e}")

    # ── Public API (mirrors old ChromaDB-backed surface) ─────────

    def add_document(self, post: Dict[str, Any]) -> None:
        text = _build_document_text(post)
        post_id = post.get("id", f"doc_{hash(text)}")
        metadata = _sanitize_metadata(post, post_id)
        self._documents.append({"id": post_id, "text": text, "metadata": metadata})
        self._save_to_disk()

    def add_documents(self, posts: List[Dict[str, Any]]) -> None:
        if not posts:
            return
        for post in posts:
            text = _build_document_text(post)
            post_id = post.get("id", f"doc_{hash(text)}")
            metadata = _sanitize_metadata(post, post_id)
            self._documents.append({"id": post_id, "text": text, "metadata": metadata})
        self._save_to_disk()
        logger.info(f"Added {len(posts)} documents to store (total: {len(self._documents)})")

    def delete_by_id_prefix(self, prefix: str) -> int:
        before = len(self._documents)
        self._documents = [d for d in self._documents if not d["id"].startswith(prefix)]
        removed = before - len(self._documents)
        if removed > 0:
            self._save_to_disk()
        return removed

    def count_by_type(self, doc_type: str) -> int:
        return sum(1 for d in self._documents if d["metadata"].get("type") == doc_type)

    def get_document_count(self) -> int:
        return len(self._documents)

    def document_exists(self, post_id: str) -> bool:
        return any(d["id"] == post_id for d in self._documents)

    def delete_document(self, post_id: str) -> None:
        self._documents = [d for d in self._documents if d["id"] != post_id]
        self._save_to_disk()

    def reset_collection(self) -> None:
        self._documents.clear()
        self._save_to_disk()

    def build_bm25_corpus(self) -> Tuple[List[str], List[Dict[str, Any]]]:
        texts = [d["text"] for d in self._documents]
        metadatas = [d["metadata"] for d in self._documents]
        return texts, metadatas

    def search_vector(self, query: str, n_results: int = 5,
                      where: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """BM25-only mode — vector search returns empty results.
        All search is handled by the hybrid search in bot/search.py which falls
        back to BM25 when vector results are empty."""
        return []

    def get(self, ids: Optional[List[str]] = None,
            where: Optional[Dict[str, Any]] = None,
            include: Optional[List[str]] = None,
            limit: Optional[int] = None) -> Dict[str, Any]:
        """ChromaDB-compatible get() interface — filters documents by ID or metadata.
        Returns dict with 'ids', 'documents', 'metadatas' keys.
        """
        filtered = list(self._documents)

        if ids:
            id_set = set(ids)
            filtered = [d for d in filtered if d["id"] in id_set]

        if where:
            for key, value in where.items():
                filtered = [d for d in filtered if d["metadata"].get(key) == value]

        if limit and limit > 0:
            filtered = filtered[:limit]

        return {
            "ids": [d["id"] for d in filtered],
            "documents": [d["text"] for d in filtered] if include and "documents" in include else [],
            "metadatas": [d["metadata"] for d in filtered] if include and "metadatas" in include
                         else ([{}] * len(filtered) if include else []),
        }

    def query_documents(self, where: Optional[Dict[str, Any]] = None,
                        include: Optional[List[str]] = None,
                        limit: Optional[int] = None) -> Dict[str, Any]:
        """Alias for get() — filters documents by metadata.
        Returns dict with 'ids', 'documents', 'metadatas' keys.
        """
        return self.get(where=where, include=include, limit=limit)


# ── Global singleton ─────────────────────────────────────────────
_doc_store = InMemoryDocStore()


# ── Backward-compatible module-level API ─────────────────────────

def _available() -> bool:
    """Always available — no external dependencies."""
    return True


def get_embedding_function() -> None:
    return None


def get_client() -> None:
    return None


def get_collection() -> Optional[InMemoryDocStore]:
    """Returns the doc store for direct queries (used by search_duas_by_category, etc.)."""
    return _doc_store


def add_document(post: dict) -> None:
    _doc_store.add_document(post)


def add_documents(posts: list) -> None:
    _doc_store.add_documents(posts)


def search_vector(query: str, n_results: int = 5, where: dict = None) -> list:
    return _doc_store.search_vector(query, n_results, where)


def build_bm25_corpus() -> tuple:
    return _doc_store.build_bm25_corpus()


def document_exists(post_id: str) -> bool:
    return _doc_store.document_exists(post_id)


def get_document_count() -> int:
    return _doc_store.get_document_count()


def delete_document(post_id: str) -> None:
    _doc_store.delete_document(post_id)


def reset_collection() -> None:
    _doc_store.reset_collection()


def delete_by_id_prefix(prefix: str) -> int:
    return _doc_store.delete_by_id_prefix(prefix)


def count_by_type(doc_type: str) -> int:
    return _doc_store.count_by_type(doc_type)


def query_documents(where: Optional[Dict[str, Any]] = None,
                    include: Optional[List[str]] = None,
                    limit: Optional[int] = None) -> Dict[str, Any]:
    """Exposes InMemoryDocStore.query_documents() for direct metadata queries."""
    return _doc_store.query_documents(where=where, include=include, limit=limit)


# ── Semantic Cache (disabled — no ML models) ────────────────────

def get_cached_response(query: str, threshold: float = 0.90) -> Optional[str]:
    return None


def cache_response(query: str, response: str) -> None:
    pass
