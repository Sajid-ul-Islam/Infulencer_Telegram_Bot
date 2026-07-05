# Agentic RAG Architecture

This document details the upgraded **Agentic Retrieval-Augmented Generation (RAG)** system.

## Architecture Overview

```
User Message
  │
  ├─► Conversation Memory (bot/memory.py)
  │     └─► Last 3 exchanges per user
  │
  ├─► AI Router (bot/ai.py :: get_ai_response)
  │     ├─► OpenRouter (primary) ─── multi-tool agent
  │     ├─► Groq (fallback) ──────── simple completion
  │     ├─► Gemini 2.0 (fallback) ── simple completion
  │     ├─► OpenAI (fallback) ────── multi-tool agent
  │     ├─► DeepSeek (fallback) ──── simple completion
  │     ├─► Anthropic (fallback) ─── simple completion
  │     ├─► xAI/Grok-3 (fallback) ─ simple completion
  │     └─► Ollama (local final) ── simple completion
  │
  └─► Multi-Tool Agent Loop (bot/ai.py :: get_ai_response)
        ├─► search_knowledge_base ──► Vector + BM25 hybrid search
        ├─► search_dua ─────────────► Hisnul Muslim dua vector search
        ├─► search_quran ───────────► Quran verse search (114 surahs, 6236 verses)
        ├─► get_faq_answer ────────► FAQ keyword lookup
        └─► get_recent_content ────► RSS feed fetcher
```

## 1. Vector Database (`bot/vectordb.py`)

- **ChromaDB** persistent vector store on disk at `./chroma_db/`
- **Embedding**: `all-MiniLM-L6-v2` via SentenceTransformers
- Supports `where` filters for type-scoped queries (e.g. `{"type": "dua"}`)
- In-memory fallback (`InMemoryDocStore`) when ChromaDB unavailable
- Semantic caching for repeated queries

### Operations
- `add_document(post)` / `add_documents(posts)` — batch insert
- `search_vector(query, n, where)` — cosine similarity search with optional filter
- `document_exists(id)` — dedup check
- `get(ids, where)` — ChromaDB-compatible document retrieval
- `reset_collection()` — full reindex
- `get_cached_response(query)` / `cache_response(query, response)` — semantic cache

## 2. Hybrid Search (`bot/search.py`)

### BM25 Keyword Search
- `rank_bm25` indexes all documents
- Tokenization via regex word splitting
- `search_bm25(query, n)` — returns scored results

### Hybrid Scoring
- `hybrid_search(query, n, alpha=0.5)` — interpolates vector + BM25 scores

### Reranking
- Optional cross-encoder reranking via `cross-encoder/ms-marco-MiniLM-L-6-v2`

### Dua Search
- `search_duas(query)` — searches only `type="dua"` documents with vector + fallback BM25
- Returns formatted results with Arabic, transliteration, translation, source

### Quran Search
- `search_quran(query)` — searches only `type="quran"` documents
- Returns Arabic text, word-by-word meanings, and Sahih International translation
- Covers all 114 surahs, 6236 verses

## 3. Content Ingestion Pipeline (`bot/pipeline.py`)

### Chunking
- `RecursiveCharacterTextSplitter` from LangChain (500 chars, 80 overlap)

### Ingestion Flows
| Flow | Trigger | Action |
|---|---|---|
| Startup | `main.py` | `ingest_knowledge_base(reindex=False)` + `ingest_duas()` + `ingest_quran_verses()` |
| Reindex | `/ingestkb` (admin) | `ingest_knowledge_base(reindex=True)` |
| RSS Auto | `auto_post_*` jobs | `ingest_rss_content()` |
| Dua Ingest | `/ingestduas` (admin) | `ingest_all_duas(force_reindex=True)` |
| Quran Ingest | `/ingestquran` (admin) | `ingest_quran_verses(force_reindex=True)` |
| Text Ingest | `ingest_text_content()` | Standalone text ingestion (e.g. YouTube transcripts) |
| Manual KB | `/ingest` (admin) | Same as reindex |

## 4. Hisnul Muslim Dua Database (`bot/dua_scraper.py`)

- Scrapes **421 authentic duas** from https://dua.gtaf.org
- Data per dua: Arabic (with diacritics), transliteration, English translation, hadith source reference
- Each dua stored as a single vector DB document with `type: "dua"` metadata
- Automatic background ingestion on startup
- Deduplicates by dua ID — only ingests new/changed entries

### Categories (15 total)
Morning & Evening, Sleeping, Prayer, Nature, Food & Drink, Social, Family, Travel, Refuge, Sickness, Gratitude, Purification, Provision, Hajj, Ramadan & Fasting

## 5. Quran Database (`bot/quran_scraper.py`)

- All **114 surahs, 6236 verses** with Arabic text and English translation
- Each verse includes: Arabic text, word-by-word meanings, Sahih International translation
- Stored as vector DB documents with `type: "quran"` metadata
- Navigable via inline keyboard (`/quran` command)

## 6. Multi-Tool Agent (`bot/ai.py`)

The agent uses OpenAI-compatible function calling with 5 tools:

### Tool: `search_knowledge_base`
- Hybrid search over creator's content (YouTube, Medium, Instagram posts)

### Tool: `search_dua`
- Vector search over Hisnul Muslim dua database
- Returns Arabic, transliteration, translation, source reference
- Triggered when users ask for Islamic supplications

### Tool: `search_quran`
- Vector search over Quran database
- Returns Arabic text, word-by-word meanings, and translation
- Triggered when users ask about Quran verses or Islamic topics

### Tool: `get_faq_answer`
- Simple keyword match against the FAQ dict

### Tool: `get_recent_content`
- Fetches latest posts from YouTube/Medium/Substack via RSS

### Tool: `browse_web`
- Fetches full text content from a URL for current events/news

### Agent Loop
1. System prompt + user message (+ optional history) sent to model
2. Model responds with text OR `tool_calls`
3. If `tool_calls`: execute tools, append results as `role: "tool"`, loop back
4. Up to 3 tool-calling rounds before forced final answer

## 7. Conversation Memory (`bot/memory.py`)

- Per-user in-memory history (last 5 exchanges)
- `/forget` command clears history
- Automatic summarization when history exceeds limit

## 8. Feedback System (`bot/handlers/feedback.py`)

- Thumbs up/down inline buttons on every AI response
- Stored in Firestore `feedback` collection

## 9. Bookmarks (`bot/handlers/bookmarks.py`)

- Save duas, Quran verses, and search results
- Stored in Firestore `user_bookmarks` collection
- Paginated view via `/myduas` command

## 10. Content Scheduling (`bot/handlers/influencer.py`)

- Schedule posts to channel at specific times
- Persisted to Firestore `scheduled_posts` collection
- Survives Render restarts via startup reload
- Processed every minute by background job

## 11. Provider Cascade

| Priority | Provider | Model | Tools | Notes |
|---|---|---|---|---|
| 1 | OpenRouter | `gpt-4o-mini` | Full agent (5 tools) | Primary — best reliability |
| 2 | Groq | `llama-3.1-8b-instant` | Simple | Fast inference + Whisper |
| 3 | Gemini | `gemini-2.0-flash` | Simple | Google's latest |
| 4 | OpenAI | `gpt-4o-mini` | Full agent (5 tools) | Direct API fallback |
| 5 | DeepSeek | `deepseek-chat` | Simple | Cost-effective reasoning |
| 6 | Anthropic | `claude-3-haiku` | Simple | Claude fallback |
| 7 | xAI | `grok-3` | Simple | Grok fallback |
| 8 | Ollama | `llama3.2:3b` | Simple | Local fallback (optional) |

## File Layout

```
bot/
├── vectordb.py       # ChromaDB persistence & operations
├── search.py         # BM25, hybrid search, reranking, dua/quran search
├── pipeline.py       # Ingestion: chunk → embed → store
├── memory.py         # Conversation history per user
├── dua_scraper.py    # Hisnul Muslim dua scraper & ingester
├── quran_scraper.py  # Quran data scraper & ingester
├── ai.py             # Multi-tool agent + 8-provider cascade
├── config.py         # Environment config + startup validation
├── database.py       # Firebase CRUD
├── handlers/
│   ├── admin.py       # Admin command handlers
│   ├── bookmarks.py   # Bookmark add/remove/view callbacks
│   ├── commands.py    # /ask, /dua, /quran, /forget, /ingest, etc.
│   ├── feedback.py    # Thumbs up/down callbacks
│   ├── influencer.py  # Scheduling, quizzes, channel stats
│   ├── inline.py      # Inline query handler
│   ├── messages.py    # Free-text handler + central callback router
│   ├── meta.py        # Meta (WhatsApp/Messenger/Instagram) handler
│   ├── navigation.py  # Dua category + Quran surah navigation
│   └── user_prefs.py  # Language & reminder time preferences
```
