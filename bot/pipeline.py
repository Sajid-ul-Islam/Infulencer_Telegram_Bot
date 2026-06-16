import json
import os
from langchain_text_splitters import RecursiveCharacterTextSplitter
from bot.config import logger
from bot.vectordb import add_documents, document_exists, get_document_count, reset_collection
from bot.rss import get_youtube_posts, get_medium_posts, get_substack_posts
from bot.search import rebuild_bm25_index

KB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "knowledge_base.json")

def chunk_text(text: str, chunk_size: int = 500, chunk_overlap: int = 80) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    return splitter.split_text(text)

def chunk_document(post: dict, chunk_size: int = 500, chunk_overlap: int = 80) -> list[dict]:
    chunks = chunk_text(f"{post['title']}\n{post['content']}", chunk_size, chunk_overlap)
    result = []
    for i, chunk in enumerate(chunks):
        chunk_id = f"{post['id']}_chunk_{i}"
        result.append({
            "id": chunk_id,
            "platform": post.get("platform", "unknown"),
            "title": post.get("title", ""),
            "content": chunk,
            "url": post.get("url", ""),
            "date": post.get("date", ""),
            "original_id": post.get("id", "")
        })
    return result

def load_knowledge_base() -> list[dict]:
    try:
        with open(KB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading knowledge_base.json: {e}")
        return []

def ingest_knowledge_base(reindex: bool = False):
    posts = load_knowledge_base()
    if not posts:
        logger.warning("Knowledge base is empty, nothing to ingest")
        return 0
    if reindex:
        reset_collection()
        rebuild_bm25_index()
    new_count = 0
    chunks_to_add = []
    for post in posts:
        post_id = post.get("id", "")
        if not reindex and post_id and document_exists(post_id):
            continue
        chunks = chunk_document(post)
        for chunk in chunks:
            chunks_to_add.append({
                "id": chunk["id"],
                "platform": chunk["platform"],
                "title": chunk["title"],
                "content": chunk["content"],
                "url": chunk["url"],
                "date": chunk["date"]
            })
            new_count += 1
    if chunks_to_add:
        add_documents(chunks_to_add)
        rebuild_bm25_index()
        logger.info(f"Ingested {new_count} chunks from {len(posts)} posts")
    else:
        logger.info("No new content to ingest")
    return new_count

async def ingest_rss_content():
    ingested = 0
    platforms = [
        ("youtube", get_youtube_posts),
        ("medium", get_medium_posts),
        ("substack", get_substack_posts)
    ]
    for platform_name, fetcher in platforms:
        try:
            msg, btn, url = await fetcher(limit=1)
            if url and not document_exists(f"{platform_name}_latest"):
                post = {
                    "id": f"{platform_name}_latest",
                    "platform": platform_name.capitalize(),
                    "title": f"Latest {platform_name} post",
                    "content": msg or f"New {platform_name} content published",
                    "url": url,
                    "date": ""
                }
                chunks = chunk_document(post)
                chunks_to_add = []
                for chunk in chunks:
                    chunks_to_add.append({
                        "id": chunk["id"],
                        "platform": chunk["platform"],
                        "title": chunk["title"],
                        "content": chunk["content"],
                        "url": chunk["url"],
                        "date": chunk["date"]
                    })
                if chunks_to_add:
                    add_documents(chunks_to_add)
                    ingested += 1
                    logger.info(f"Ingested latest {platform_name} post from RSS")
        except Exception as e:
            logger.error(f"Failed to ingest {platform_name} RSS: {e}")
    if ingested:
        rebuild_bm25_index()
    return ingested

async def ingest_duas(force_reindex: bool = False) -> int:
    from bot.dua_scraper import ingest_all_duas
    count = await ingest_all_duas(force_reindex=force_reindex)
    return count

def get_pipeline_stats() -> dict:
    dua_count = 0
    try:
        from bot.vectordb import get_client
        client = get_client()
        collection = client.get_collection("knowledge_base")
        all_docs = collection.get(include=["metadatas"])
        if all_docs and all_docs["metadatas"]:
            dua_count = sum(1 for m in all_docs["metadatas"] if m.get("type") == "dua")
    except Exception:
        pass
    return {
        "vector_documents": get_document_count(),
        "kb_entries": len(load_knowledge_base()),
        "dua_count": dua_count
    }
