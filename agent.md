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
  │     ├─► OpenAI (fallback) ────── multi-tool agent
  │     ├─► Anthropic (fallback) ─── simple completion
  │     ├─► xAI/Grok (fallback) ──── simple completion
  │     └─► Gemini (final) ──────── simple completion
  │
  └─► Multi-Tool Agent Loop (bot/ai.py :: call_agent_with_tools)
        ├─► search_knowledge_base ──► Vector + BM25 hybrid search
        ├─► search_dua ─────────────► Hisnul Muslim dua vector search
        ├─► get_faq_answer ────────► FAQ keyword lookup
        └─► get_recent_content ────► RSS feed fetcher
```

## 1. Vector Database (`bot/vectordb.py`)

- **ChromaDB** persistent vector store on disk at `./chroma_db/`
- **Embedding**: `all-MiniLM-L6-v2` via SentenceTransformers
- Supports `where` filters for type-scoped queries (e.g. `{"type": "dua"}`)

### Operations
- `add_document(post)` / `add_documents(posts)` — batch insert
- `search_vector(query, n, where)` — cosine similarity search with optional filter
- `document_exists(id)` — dedup check
- `reset_collection()` — full reindex

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

## 3. Content Ingestion Pipeline (`bot/pipeline.py`)

### Chunking
- `RecursiveCharacterTextSplitter` from LangChain (500 chars, 80 overlap)

### Ingestion Flows
| Flow | Trigger | Action |
|---|---|---|
| Startup | `main.py` | `ingest_knowledge_base(reindex=False)` + `ingest_duas()` |
| Reindex | `/ingestkb` (admin) | `ingest_knowledge_base(reindex=True)` |
| RSS Auto | `auto_post_*` jobs | `ingest_rss_content()` |
| Dua Ingest | `/ingestduas` (admin) | `ingest_all_duas(force_reindex=True)` |
| Manual KB | `/ingest` (admin) | Same as reindex |

## 4. Hisnul Muslim Dua Database (`bot/dua_scraper.py`)

- Scrapes **421 authentic duas** from https://dua.gtaf.org
- Data per dua: Arabic (with diacritics), transliteration, English translation, hadith source reference
- Each dua stored as a single vector DB document with `type: "dua"` metadata
- Automatic background ingestion on startup
- Deduplicates by dua ID — only ingests new/changed entries

### Categories (15 total)
Morning & Evening, Sleeping, Prayer, Nature, Food & Drink, Social, Family, Travel, Refuge, Sickness, Gratitude, Purification, Provision, Hajj, Ramadan & Fasting

## 5. Multi-Tool Agent (`bot/ai.py`)

The agent uses OpenAI-compatible function calling with 4 tools:

### Tool: `search_knowledge_base`
- Hybrid search over creator's content (YouTube, Medium, Instagram posts)

### Tool: `search_dua`
- Vector search over Hisnul Muslim dua database
- Returns Arabic, transliteration, translation, source reference
- Triggered when users ask for Islamic supplications

### Tool: `get_faq_answer`
- Simple keyword match against the FAQ dict

### Tool: `get_recent_content`
- Fetches latest posts from YouTube/Medium/Substack via RSS

### Agent Loop
1. System prompt + user message (+ optional history) sent to model
2. Model responds with text OR `tool_calls`
3. If `tool_calls`: execute tools, append results as `role: "tool"`, loop back
4. Up to 3 tool-calling rounds before forced final answer

## 6. Conversation Memory (`bot/memory.py`)

- Per-user in-memory history (last 5 exchanges)
- `/forget` command clears history

## 7. Feedback System (`bot/handlers/feedback.py`)

- Thumbs up/down inline buttons on every AI response
- Stored in Firestore `feedback` collection

## 8. Provider Cascade

| Priority | Provider | Model | Tools |
|---|---|---|---|
| 1 | OpenRouter | `gpt-4o-mini` | Full agent (4 tools) |
| 2 | Groq | `llama-3.1-8b-instant` | Simple |
| 3 | OpenAI | `gpt-4o-mini` | Full agent (4 tools) |
| 4 | Anthropic | `claude-3-haiku` | Simple |
| 5 | xAI | `grok-beta` | Simple |
| 6 | Gemini | `gemini-1.5-flash` | Simple |

## File Layout

```
bot/
├── vectordb.py       # ChromaDB persistence & operations
├── search.py         # BM25, hybrid search, reranking, dua search
├── pipeline.py       # Ingestion: chunk → embed → store
├── memory.py         # Conversation history per user
├── dua_scraper.py    # Hisnul Muslim dua scraper & ingester
├── ai.py             # Multi-tool agent + provider cascade
├── handlers/
│   ├── feedback.py   # Thumbs up/down callbacks
│   ├── commands.py   # /ask, /dua, /forget, /ingest, etc.
│   └── messages.py   # Free-text handler with feedback buttons
```
