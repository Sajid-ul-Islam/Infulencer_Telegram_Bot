import os
import json
import re
from bot.config import logger

try:
    import chromadb
    from chromadb.utils import embedding_functions
    _chromadb_available = True
except ImportError:
    _chromadb_available = False
    logger.warning("chromadb not installed — vector search disabled, BM25 fallback only")

CHROMA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "chroma_db")
COLLECTION_NAME = "knowledge_base"
MODEL_NAME = "all-MiniLM-L6-v2"

_client = None
_collection = None
_embedding_fn = None

def _available():
    return _chromadb_available

def get_embedding_function():
    global _embedding_fn
    if not _chromadb_available:
        return None
    if _embedding_fn is None:
        try:
            _embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=MODEL_NAME)
        except Exception as e:
            logger.warning(f"SentenceTransformer fallback to default: {e}")
            _embedding_fn = embedding_functions.DefaultEmbeddingFunction()
    return _embedding_fn

def get_client():
    global _client
    if not _chromadb_available:
        return None
    if _client is None:
        _client = chromadb.PersistentClient(path=CHROMA_DIR)
    return _client

def get_collection():
    global _collection
    if not _chromadb_available:
        return None
    if _collection is None:
        client = get_client()
        _collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=get_embedding_function()
        )
    return _collection

def add_document(post: dict):
    coll = get_collection()
    if not coll:
        return
    text = f"{post['title']}\n{post['content']}"
    post_id = post.get("id", f"doc_{hash(text)}")
    metadata = {
        "platform": post.get("platform", "unknown"),
        "url": post.get("url", ""),
        "date": post.get("date", ""),
        "title": post.get("title", ""),
        "id": post_id
    }
    try:
        coll.add(documents=[text], metadatas=[metadata], ids=[post_id])
    except Exception as e:
        logger.error(f"add_document failed: {e}")

def add_documents(posts: list[dict]):
    coll = get_collection()
    if not coll or not posts:
        return
    ids = [p.get("id", f"doc_{hash(p['title'] + p['content'])}") for p in posts]
    documents = [f"{p['title']}\n{p['content']}" for p in posts]
    metadatas = [{
        "platform": p.get("platform", "unknown"),
        "url": p.get("url", ""),
        "date": p.get("date", ""),
        "title": p.get("title", ""),
        "id": ids[i]
    } for i, p in enumerate(posts)]
    try:
        coll.add(documents=documents, metadatas=metadatas, ids=ids)
        logger.info(f"Added {len(posts)} documents to vector DB")
    except Exception as e:
        logger.error(f"add_documents batch failed: {e}")

def search_vector(query: str, n_results: int = 5, where: dict = None) -> list[dict]:
    coll = get_collection()
    if not coll:
        return []
    try:
        kwargs = {
            "query_texts": [query],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"]
        }
        if where:
            kwargs["where"] = where
        results = coll.query(**kwargs)
        hits = []
        if results and results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                hits.append({
                    "id": doc_id,
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "score": 1.0 - (results["distances"][0][i] if results.get("distances") else 0)
                })
        return hits
    except Exception as e:
        logger.error(f"Vector search failed: {e}")
        return []

def build_bm25_corpus():
    coll = get_collection()
    if not coll:
        return [], []
    try:
        all_docs = coll.get(include=["documents", "metadatas"])
        if not all_docs or not all_docs["ids"]:
            return [], []
        return all_docs["documents"], all_docs["metadatas"]
    except Exception as e:
        logger.error(f"build_bm25_corpus failed: {e}")
        return [], []

def document_exists(post_id: str) -> bool:
    coll = get_collection()
    if not coll:
        return False
    try:
        existing = coll.get(ids=[post_id])
        return bool(existing and len(existing["ids"]) > 0)
    except Exception:
        return False

def get_document_count() -> int:
    coll = get_collection()
    if not coll:
        return 0
    try:
        return coll.count()
    except Exception:
        return 0

def delete_document(post_id: str):
    coll = get_collection()
    if not coll:
        return
    try:
        coll.delete(ids=[post_id])
    except Exception as e:
        logger.error(f"delete_document failed: {e}")

def reset_collection():
    global _collection
    client = get_client()
    if not client:
        return
    try:
        client.delete_collection(COLLECTION_NAME)
        _collection = None
    except Exception as e:
        logger.error(f"reset_collection failed: {e}")
