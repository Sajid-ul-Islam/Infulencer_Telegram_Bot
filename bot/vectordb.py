import os
import json
import re
import chromadb
from chromadb.utils import embedding_functions
from bot.config import logger

CHROMA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "chroma_db")
COLLECTION_NAME = "knowledge_base"
MODEL_NAME = "all-MiniLM-L6-v2"

_client = None
_collection = None
_embedding_fn = None

def get_embedding_function():
    global _embedding_fn
    if _embedding_fn is None:
        try:
            _embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=MODEL_NAME)
        except Exception as e:
            logger.warning(f"SentenceTransformer fallback to default: {e}")
            _embedding_fn = embedding_functions.DefaultEmbeddingFunction()
    return _embedding_fn

def get_client():
    global _client
    if _client is None:
        try:
            _client = chromadb.PersistentClient(path=CHROMA_DIR)
        except Exception as e:
            logger.error(f"Failed to init ChromaDB: {e}")
            raise
    return _client

def get_collection():
    global _collection
    if _collection is None:
        try:
            client = get_client()
            _collection = client.get_or_create_collection(
                name=COLLECTION_NAME,
                embedding_function=get_embedding_function()
            )
        except Exception as e:
            logger.error(f"Failed to get/create collection: {e}")
            raise
    return _collection

def add_document(post: dict):
    text = f"{post['title']}\n{post['content']}"
    collection = get_collection()
    post_id = post.get("id", f"doc_{hash(text)}")
    metadata = {
        "platform": post.get("platform", "unknown"),
        "url": post.get("url", ""),
        "date": post.get("date", ""),
        "title": post.get("title", ""),
        "id": post_id
    }
    try:
        collection.add(
            documents=[text],
            metadatas=[metadata],
            ids=[post_id]
        )
        logger.info(f"Added document {post_id} to vector DB")
    except Exception as e:
        logger.error(f"Failed to add document {post_id}: {e}")

def add_documents(posts: list[dict]):
    if not posts:
        return
    collection = get_collection()
    ids = []
    documents = []
    metadatas = []
    for post in posts:
        post_id = post.get("id", f"doc_{hash(post['title'] + post['content'])}")
        ids.append(post_id)
        documents.append(f"{post['title']}\n{post['content']}")
        metadatas.append({
            "platform": post.get("platform", "unknown"),
            "url": post.get("url", ""),
            "date": post.get("date", ""),
            "title": post.get("title", ""),
            "id": post_id
        })
    try:
        collection.add(documents=documents, metadatas=metadatas, ids=ids)
        logger.info(f"Added {len(posts)} documents to vector DB")
    except Exception as e:
        logger.error(f"Failed to add documents batch: {e}")

def search_vector(query: str, n_results: int = 5, where: dict = None) -> list[dict]:
    collection = get_collection()
    try:
        kwargs = {
            "query_texts": [query],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"]
        }
        if where:
            kwargs["where"] = where
        results = collection.query(**kwargs)
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
    collection = get_collection()
    try:
        all_docs = collection.get(include=["documents", "metadatas"])
        if not all_docs or not all_docs["ids"]:
            return [], []
        return all_docs["documents"], all_docs["metadatas"]
    except Exception as e:
        logger.error(f"Failed to get corpus for BM25: {e}")
        return [], []

def document_exists(post_id: str) -> bool:
    collection = get_collection()
    try:
        existing = collection.get(ids=[post_id])
        return len(existing["ids"]) > 0 if existing else False
    except Exception:
        return False

def get_document_count() -> int:
    collection = get_collection()
    try:
        return collection.count()
    except Exception:
        return 0

def delete_document(post_id: str):
    collection = get_collection()
    try:
        collection.delete(ids=[post_id])
        logger.info(f"Deleted document {post_id}")
    except Exception as e:
        logger.error(f"Failed to delete {post_id}: {e}")

def reset_collection():
    global _collection
    try:
        client = get_client()
        client.delete_collection(COLLECTION_NAME)
        _collection = None
        logger.info("Vector DB collection reset")
    except Exception as e:
        logger.error(f"Failed to reset collection: {e}")
