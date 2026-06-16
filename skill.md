# Bot Skills & Logic Flow

This file documents the specialized skills the bot possesses.

## 1. Content Syndication
- **YouTube RSS**: Uses `feedparser` to parse `https://www.youtube.com/feeds/videos.xml?channel_id={YOUTUBE_CHANNEL_ID}`.
- **Medium RSS**: Parses `https://medium.com/feed/@{MEDIUM_USERNAME}`.
- **Substack RSS**: Parses `{SUBSTACK_URL}/feed`.
- **Auto-Posting**: JobQueue schedules daily checks at 09:00 (YouTube), 14:00 (Substack), 18:00 (Medium). If new content detected, broadcasts to channel.
- **Auto-Ingest**: Each RSS auto-post also triggers `ingest_rss_content()` which chunks and embeds the new content into the vector DB.

## 2. Agentic RAG with Hybrid Search
- **Vector DB**: ChromaDB with `all-MiniLM-L6-v2` embeddings for semantic search.
- **Keyword Search**: BM25 index (`rank-bm25`) for exact term matching.
- **Hybrid Search**: Interpolated scores (alpha=0.5) from vector + BM25 results.
- **Reranking**: Optional cross-encoder reranking for precision.
- **Chunking**: LangChain `RecursiveCharacterTextSplitter` (500 chars, 80 overlap).

## 3. Hisnul Muslim Dua Database
- **Source**: https://dua.gtaf.org — 421 authentic Islamic duas (supplications).
- **Data**: Each dua includes Arabic text (with diacritics), transliteration, English translation, and hadith source reference.
- **Categories**: 15 categories covering Morning & Evening, Sleeping, Prayer, Food & Drink, Travel, Sickness, Hajj, Ramadan, and more.
- **Search**: Both the AI agent (via `search_dua` tool) and the `/dua` command can search the dua database.
- **Ingestion**: Automatically scraped and indexed on startup; deduplicates by dua ID.

## 4. Multi-Tool AI Agent
The bot uses OpenAI-compatible function calling with 4 tools:
- `search_knowledge_base` — hybrid RAG search over creator content
- `search_dua` — vector search over Hisnul Muslim duas
- `get_faq_answer` — FAQ keyword lookup
- `get_recent_content` — RSS fetcher for latest posts

The agent can call multiple tools in sequence, up to 3 rounds, before generating the final response.

## 5. Conversation Memory
Per-user chat history stored in-memory (last 5 exchanges). Users can clear with `/forget`. Memory is injected into the system prompt for context-aware conversations.

## 6. Feedback System
Thumbs up/down inline buttons on every AI response. Feedback stored in Firestore `feedback` collection. Displayed in dashboard and `/stats`.

## 7. Dynamic Firebase Storage
Integrates with Google Cloud Firestore via `firebase-admin`.
- **Collections**: `faqs`, `questions`, `suggestions`, `giveaway_entries`, `activity_logs`, `users`, `feedback`

## 8. Community Moderation
- **Anti-Spam**: In Supergroups, auto-deletes messages with `http://` or `https://` from non-admins.
- **Mute/Ban**: Admin can reply with `/ban` or `/mute`.

## 9. Render Keep-Alive System
- **Dummy Server**: Lightweight HTTPServer on port 8080.
- **Self-Pinger**: GET request to `RENDER_EXTERNAL_URL` every 10 minutes.
