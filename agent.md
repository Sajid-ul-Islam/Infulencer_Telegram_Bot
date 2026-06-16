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
        ├─► get_faq_answer ────────► FAQ keyword lookup
        └─► get_recent_content ────► RSS feed fetcher
```

## 1. Vector Database (`bot/vectordb.py`)

- **ChromaDB** persistent vector store on disk at `./chroma_db/`
- **Embedding**: `all-MiniLM-L6-v2` via SentenceTransformers
- Documents are chunked (500 chars, 80 overlap) before embedding

### Operations
- `add_document(post)` / `add_documents(posts)` — batch insert
- `search_vector(query, n)` — cosine similarity search
- `document_exists(id)` — dedup check
- `reset_collection()` — full reindex

## 2. Hybrid Search (`bot/search.py`)

### BM25 Keyword Search
- `rank_bm25` indexes all documents
- Tokenization via regex word splitting
- `search_bm25(query, n)` — returns scored results

### Hybrid Scoring
- `hybrid_search(query, n, alpha=0.5)` — interpolates vector + BM25 scores
- `alpha` controls weight: 1.0 = pure vector, 0.0 = pure BM25

### Reranking
- Optional cross-encoder reranking via `cross-encoder/ms-marco-MiniLM-L-6-v2`
- `rerank(query, hits, top_n)` — re-scores top results with cross-attention

### Pipeline
- `search_pipeline(query)` — full end-to-end: hybrid search → rerank → format

## 3. Content Ingestion Pipeline (`bot/pipeline.py`)

### Chunking
- `RecursiveCharacterTextSplitter` from LangChain
- Default: 500 char chunks with 80 char overlap
- Separators: `\n\n` → `\n` → `. ` → ` ` → `` (character)

### Ingestion Flows
| Flow | Trigger | Action |
|---|---|---|
| Startup | `main.py` | `ingest_knowledge_base(reindex=False)` — ingest new only |
| Reindex | `/ingestkb` (admin) | `ingest_knowledge_base(reindex=True)` — full reset + reindex |
| RSS Auto | `auto_post_*` jobs | `ingest_rss_content()` — ingests latest RSS item |
| Manual | `/ingest` (admin) | Same as reindex |

## 4. Multi-Tool Agent (`bot/ai.py`)

The agent uses OpenAI-compatible function calling with 3 tools:

### Tool: `search_knowledge_base`
- Triggers the full `search_pipeline()` (hybrid search + rerank)
- Returns formatted results with platform, title, content, link

### Tool: `get_faq_answer`
- Simple keyword match against the FAQ dict
- Returns the matching FAQ response

### Tool: `get_recent_content`
- Fetches latest posts from YouTube/Medium/Substack via RSS
- Returns formatted message with links

### Agent Loop
1. System prompt + user message (+ optional history) sent to model
2. Model responds with text OR `tool_calls`
3. If `tool_calls`: execute tools, append results as `role: "tool"`, loop back
4. Up to 3 tool-calling rounds before forced final answer
5. Falls through 6 providers in cascade if any errors

## 5. Conversation Memory (`bot/memory.py`)

- Per-user in-memory history (dict[int, list[dict]])
- Stores last 10 messages (5 exchanges) per user
- History is injected into the system message context
- `/forget` command clears history

## 6. Feedback System (`bot/handlers/feedback.py`)

- Thumbs up/down inline buttons on every AI response
- Stored in Firestore `feedback` collection
- Displayed in dashboard stats and `/stats` command

## 7. Provider Cascade

| Priority | Provider | Model | Tools |
|---|---|---|---|
| 1 | OpenRouter | `gpt-4o-mini` | Full agent |
| 2 | Groq | `llama-3.1-8b-instant` | Simple |
| 3 | OpenAI | `gpt-4o-mini` | Full agent |
| 4 | Anthropic | `claude-3-haiku` | Simple |
| 5 | xAI | `grok-beta` | Simple |
| 6 | Gemini | `gemini-1.5-flash` | Simple |

## File Layout

```
bot/
├── vectordb.py       # ChromaDB persistence & operations
├── search.py         # BM25, hybrid search, reranking
├── pipeline.py       # Ingestion: chunk → embed → store
├── memory.py         # Conversation history per user
├── ai.py             # Multi-tool agent + provider cascade
├── handlers/
│   ├── feedback.py   # Thumbs up/down callbacks
│   ├── commands.py   # /ask, /forget, /ingest, etc.
│   └── messages.py   # Free-text handler with feedback buttons
```
