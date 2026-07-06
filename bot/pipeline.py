import json
import os
from langchain_text_splitters import RecursiveCharacterTextSplitter
from bot.config import logger
from bot import vectordb
from bot.rss import get_youtube_posts, get_medium_posts, get_substack_posts
from bot.search import rebuild_bm25_index

KB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "knowledge_base.json")

_vdb_available = vectordb._available()

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
    if not _vdb_available:
        logger.info("Vector DB unavailable — skipping knowledge base ingestion")
        return 0
    posts = load_knowledge_base()
    if not posts:
        logger.warning("Knowledge base is empty, nothing to ingest")
        return 0
    if reindex:
        vectordb.reset_collection()
        rebuild_bm25_index()
    new_count = 0
    chunks_to_add = []
    for post in posts:
        post_id = post.get("id", "")
        if not reindex and post_id and vectordb.document_exists(post_id):
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
        vectordb.add_documents(chunks_to_add)
        rebuild_bm25_index()
        logger.info(f"Ingested {new_count} chunks from {len(posts)} posts")
    else:
        logger.info("No new content to ingest")
    return new_count

async def ingest_rss_content():
    if not _vdb_available:
        return 0
    ingested = 0
    platforms = [
        ("youtube", get_youtube_posts),
        ("medium", get_medium_posts),
        ("substack", get_substack_posts)
    ]
    for platform_name, fetcher in platforms:
        try:
            msg, btn, url = await fetcher(limit=1)
            if url and not vectordb.document_exists(f"{platform_name}_latest"):
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
                    vectordb.add_documents(chunks_to_add)
                    ingested += 1
        except Exception as e:
            logger.error(f"Failed to ingest {platform_name}: {e}")
    if ingested:
        rebuild_bm25_index()
    return ingested

async def ingest_duas(force_reindex: bool = False) -> int:
    if not _vdb_available:
        logger.info("Vector DB unavailable — skipping dua ingestion")
        return 0
    try:
        from bot.dua_scraper import ingest_all_duas
        return await ingest_all_duas(force_reindex=force_reindex)
    except Exception as e:
        logger.error(f"Dua ingestion failed: {e}")
        return 0

async def ingest_quran_verses(force_reindex: bool = False) -> int:
    if not _vdb_available:
        logger.info("Vector DB unavailable — skipping Quran ingestion")
        return 0
    try:
        from bot.quran_scraper import ingest_quran
        return await ingest_quran(force_reindex=force_reindex)
    except Exception as e:
        logger.error(f"Quran ingestion failed: {e}")
        return 0

async def ingest_text_content(title: str, content: str, platform: str, url: str = "") -> int:
    """Ingest raw text content (e.g. YouTube transcription) into the document store."""
    if not _vdb_available or not content:
        return 0
    import hashlib
    content_hash = hashlib.md5(content.encode()).hexdigest()[:12]
    post_id = f"{platform}_transcript_{content_hash}"
    if vectordb.document_exists(post_id):
        logger.info(f"Transcript already indexed: {post_id}")
        return 0
    post = {
        "id": post_id,
        "platform": platform.replace("_", " ").title(),
        "title": title,
        "content": content[:10000],
        "url": url,
        "date": "",
    }
    chunks = chunk_document(post)
    chunks_to_add = [{
        "id": c["id"], "platform": c["platform"], "title": c["title"],
        "content": c["content"], "url": c["url"], "date": c["date"]
    } for c in chunks]
    if chunks_to_add:
        vectordb.add_documents(chunks_to_add)
        rebuild_bm25_index()
        logger.info(f"Ingested {len(chunks_to_add)} chunks from {platform} transcript: {title}")
        return len(chunks_to_add)
    return 0


def get_pipeline_stats() -> dict:
    if not _vdb_available:
        return {"vector_documents": 0, "kb_entries": len(load_knowledge_base()), "dua_count": 0, "quran_count": 0}
    return {
        "vector_documents": vectordb.get_document_count(),
        "kb_entries": len(load_knowledge_base()),
        "dua_count": vectordb.count_by_type("dua"),
        "quran_count": vectordb.count_by_type("quran"),
    }

async def ingest_pdf(file_path: str, book_name: str, progress_callback=None) -> int:
    """Extracts text from a PDF and ingests it as a book into the document store."""
    if not _vdb_available:
        return 0
    try:
        if progress_callback: await progress_callback("⏳ Opening PDF...")
        import fitz
        import re
        doc = fitz.open(file_path)
        full_text = ""
        
        if progress_callback: await progress_callback(f"📖 Extracting text from {len(doc)} pages...")
        for page in doc:
            full_text += page.get_text() + "\n"
        
        full_text = re.sub(r'\n+', '\n', full_text)
        
        post = {
            "id": f"book_{book_name.replace(' ', '_').lower()}",
            "title": book_name,
            "content": full_text,
            "platform": "pdf",
            "url": ""
        }
        
        if progress_callback: await progress_callback("✂️ Chunking extracted text...")
        chunks = chunk_document(post, chunk_size=800, chunk_overlap=150)
        
        chunks_to_add = []
        for i, chunk in enumerate(chunks):
            chunks_to_add.append({
                "id": f"book_{book_name.replace(' ', '_').lower()}_{i}",
                "type": "book",
                "book_name": book_name,
                "title": book_name,
                "content": chunk["content"],
                "platform": "pdf",
                "url": ""
            })
            
        if chunks_to_add:
            if progress_callback: await progress_callback(f"🧠 Indexing {len(chunks_to_add)} chunks into knowledge base...")
            from bot import vectordb
            vectordb.add_documents(chunks_to_add)
            rebuild_bm25_index()
            logger.info(f"Ingested {len(chunks_to_add)} chunks for book: {book_name}")
            return len(chunks_to_add)
        return 0
    except Exception as e:
        logger.error(f"Error ingesting PDF {file_path}: {e}")
        return 0
