import os
import re
from typing import List, Dict, Tuple, Optional, Any
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

class VectorDBManager:
    """Manages connection, collection initialization, and CRUD operations for ChromaDB vector store."""
    
    def __init__(self, chroma_dir: str = CHROMA_DIR, collection_name: str = COLLECTION_NAME, model_name: str = MODEL_NAME):
        self.chroma_dir = chroma_dir
        self.collection_name = collection_name
        self.model_name = model_name
        self._client: Optional[Any] = None
        self._collection: Optional[Any] = None
        self._embedding_fn: Optional[Any] = None

    def is_available(self) -> bool:
        return _chromadb_available

    def get_embedding_function(self) -> Optional[Any]:
        if not _chromadb_available:
            return None
        if self._embedding_fn is None:
            try:
                self._embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=self.model_name)
            except Exception as e:
                logger.warning(f"SentenceTransformer fallback to default: {e}")
                self._embedding_fn = embedding_functions.DefaultEmbeddingFunction()
        return self._embedding_fn

    def get_client(self) -> Optional[Any]:
        if not _chromadb_available:
            return None
        if self._client is None:
            self._client = chromadb.PersistentClient(path=self.chroma_dir)
        return self._client

    def get_collection(self) -> Optional[Any]:
        if not _chromadb_available:
            return None
        if self._collection is None:
            client = self.get_client()
            if client:
                self._collection = client.get_or_create_collection(
                    name=self.collection_name,
                    embedding_function=self.get_embedding_function()
                )
        return self._collection

    def add_document(self, post: Dict[str, Any]) -> None:
        coll = self.get_collection()
        if not coll:
            return
        text = f"{post.get('title', '')}\n{post.get('content', '')}"
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

    def add_documents(self, posts: List[Dict[str, Any]]) -> None:
        coll = self.get_collection()
        if not coll or not posts:
            return
        ids = [p.get("id", f"doc_{hash(p.get('title', '') + p.get('content', ''))}") for p in posts]
        documents = [f"{p.get('title', '')}\n{p.get('content', '')}" for p in posts]
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

    def search_vector(self, query: str, n_results: int = 5, where: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        coll = self.get_collection()
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

    def build_bm25_corpus(self) -> Tuple[List[str], List[Dict[str, Any]]]:
        coll = self.get_collection()
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

    def document_exists(self, post_id: str) -> bool:
        coll = self.get_collection()
        if not coll:
            return False
        try:
            existing = coll.get(ids=[post_id])
            return bool(existing and len(existing["ids"]) > 0)
        except Exception:
            return False

    def get_document_count(self) -> int:
        coll = self.get_collection()
        if not coll:
            return 0
        try:
            return coll.count()
        except Exception:
            return 0

    def delete_document(self, post_id: str) -> None:
        coll = self.get_collection()
        if not coll:
            return
        try:
            coll.delete(ids=[post_id])
        except Exception as e:
            logger.error(f"delete_document failed: {e}")

    def reset_collection(self) -> None:
        client = self.get_client()
        if not client:
            return
        try:
            client.delete_collection(self.collection_name)
            self._collection = None
        except Exception as e:
            logger.error(f"reset_collection failed: {e}")

# Global instance for easy import backward-compatibility
db_manager = VectorDBManager()

def _available() -> bool:
    return db_manager.is_available()

def get_embedding_function() -> Optional[Any]:
    return db_manager.get_embedding_function()

def get_client() -> Optional[Any]:
    return db_manager.get_client()

def get_collection() -> Optional[Any]:
    return db_manager.get_collection()

def add_document(post: dict) -> None:
    db_manager.add_document(post)

def add_documents(posts: list) -> None:
    db_manager.add_documents(posts)

def search_vector(query: str, n_results: int = 5, where: dict = None) -> list:
    return db_manager.search_vector(query, n_results, where)

def build_bm25_corpus() -> tuple:
    return db_manager.build_bm25_corpus()

def document_exists(post_id: str) -> bool:
    return db_manager.document_exists(post_id)

def get_document_count() -> int:
    return db_manager.get_document_count()

def delete_document(post_id: str) -> None:
    db_manager.delete_document(post_id)

def reset_collection() -> None:
    db_manager.reset_collection()

class SemanticCacheManager(VectorDBManager):
    def __init__(self):
        super().__init__(collection_name="semantic_cache")

cache_manager = SemanticCacheManager()

def get_cached_response(query: str, threshold: float = 0.90) -> Optional[str]:
    if not cache_manager.is_available():
        return None
    try:
        hits = cache_manager.search_vector(query, n_results=1)
        if hits and hits[0]["score"] >= threshold:
            logger.info(f"Cache hit for query: {query[:50]}")
            return hits[0]["metadata"].get("response")
    except Exception as e:
        logger.error(f"Error checking semantic cache: {e}")
    return None

def cache_response(query: str, response: str) -> None:
    if not cache_manager.is_available():
        return
    try:
        coll = cache_manager.get_collection()
        if not coll:
            return
        doc_id = f"cache_{hash(query)}"
        coll.add(
            documents=[query],
            metadatas=[{"response": response}],
            ids=[doc_id]
        )
    except Exception as e:
        logger.error(f"Error saving to semantic cache: {e}")
