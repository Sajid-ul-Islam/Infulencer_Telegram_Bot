# Bearded Bangali Telegram Bot

The official Telegram Assistant for the Bearded Bangali content creator community. Built with `python-telegram-bot`, ChromaDB vector search, Firebase, and a Multi-AI Cascading Engine.

## Features

- **Multi-Platform Content Syndication**: Automatically fetches and posts latest YouTube, Medium, and Substack content to Telegram channel.
- **Agentic RAG with Hybrid Search**: ChromaDB vector DB + BM25 keyword index + cross-encoder reranking for accurate answers from past content.
- **Hisnul Muslim Dua Database**: 421 authentic Islamic duas scraped from https://dua.gtaf.org, vectorized for semantic search. Ask about any dua via the AI or `/dua` command.
- **Multi-Tool AI Agent**: 4 tools available — `search_knowledge_base`, `search_dua`, `get_faq_answer`, `get_recent_content`. Up to 3 tool-calling rounds per response.
- **6-Provider AI Fallback**: OpenRouter (primary) -> Groq -> OpenAI -> Anthropic -> xAI -> Gemini.
- **Conversation Memory**: Per-user chat history remembered across messages. Clear with `/forget`.
- **Feedback System**: Thumbs up/down on every AI response, stored in Firestore.
- **Firebase Sync**: FAQs, questions, suggestions, feedback, giveaway entries, and activity logs stored in Firestore.
- **Admin Dashboard**: Full SPA web dashboard at `/` with analytics, FAQ management, broadcasting, polls, giveaways, and live logs.
- **Anti-Spam**: Automatic link deletion in group chats.
- **Render Keep-Alive**: HTTP server + self-pinger to prevent Render free-tier sleep.

## Quick Start

1. Copy `.env.example` to `.env` and fill in your values (Telegram token, API keys, etc.)
2. Install dependencies: `pip install -r requirements.txt`
3. Run: `python main.py`

The first startup will:
- Ingest `knowledge_base.json` content into ChromaDB
- Begin background ingestion of Hisnul Muslim duas from https://dua.gtaf.org (420+ duas)

## Commands

| Command | Description |
|---|---|
| `/start` | Welcome message |
| `/latest` | Get all latest content |
| `/youtube` | Latest YouTube video |
| `/medium` | Latest Medium article |
| `/substack` | Latest Substack newsletter |
| `/socials` | All platform links |
| `/ask <question>` | Ask the AI (with memory + feedback) |
| `/dua <query>` | Search Hisnul Muslim duas |
| `/forget` | Clear conversation history |
| `/suggest <topic>` | Suggest a topic |
| `/help` | Show all commands |

### Admin Commands

| Command | Description |
|---|---|
| `/postlatest` | Force broadcast new content to channel |
| `/ban` | Ban a user (reply to message) |
| `/mute` | Mute a user (reply to message) |
| `/questions` | View recent user questions |
| `/poll "Q" "Op1" "Op2"` | Send poll to channel |
| `/broadcast <msg>` | Send channel announcement |
| `/addfaq "key" "resp"` | Add custom FAQ |
| `/rmfaq "key"` | Remove FAQ |
| `/listfaq` | List all FAQs |
| `/stats` | View community + vector DB + feedback stats |
| `/ingestkb` | Re-index knowledge base into vector DB |
| `/ingestduas` | Re-index all duas from source |
| `/listsuggestions` | View topic suggestions |
| `/startgiveaway <Prize>` | Start a giveaway |
| `/pickwinner` | Draw giveaway winner |

## Project Structure

```
bot/
├── ai.py              # Multi-tool agent + 6-provider cascade
├── config.py          # Environment config
├── database.py        # Firebase CRUD
├── dua_scraper.py     # Hisnul Muslim scraper & ingester
├── jobs.py            # Scheduled content posting
├── memory.py          # Conversation history
├── pipeline.py        # Content ingestion pipeline
├── rss.py             # RSS feed parsers
├── search.py          # BM25, hybrid search, dua search
├── server.py          # Admin web dashboard
├── vectordb.py        # ChromaDB vector store
├── handlers/
│   ├── admin.py       # Admin command handlers
│   ├── commands.py    # User command handlers
│   ├── feedback.py    # Feedback callbacks
│   └── messages.py    # Free-text handler
main.py                # Entry point
requirements.txt       # Dependencies
knowledge_base.json    # Static KB source
agent.md               # Agentic RAG docs
skill.md               # Bot skills docs
```

## Dependencies

- `python-telegram-bot[job-queue]` — Telegram framework
- `chromadb` — Vector database
- `sentence-transformers` — Text embeddings
- `rank-bm25` — Keyword search
- `langchain-text-splitters` — Text chunking
- `firebase-admin` — Firebase/Firestore
- `feedparser` + `httpx` — RSS fetching
- `python-dotenv` — Environment management
