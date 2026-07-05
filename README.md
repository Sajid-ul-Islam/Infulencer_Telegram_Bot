# Bearded Bangali Telegram Bot

The official Telegram Assistant for the Bearded Bangali content creator community. Built with `python-telegram-bot`, ChromaDB vector search, Firebase, and a Multi-AI Cascading Engine.

## Features

- **Multi-Platform Content Syndication**: Automatically fetches and posts latest YouTube, Medium, and Substack content to Telegram channel.
- **Agentic RAG with Hybrid Search**: ChromaDB vector DB + BM25 keyword index + cross-encoder reranking for accurate answers from past content.
- **Hisnul Muslim Dua Database**: 421 authentic Islamic duas scraped from https://dua.gtaf.org, vectorized for semantic search. Ask about any dua via the AI or `/dua` command.
- **Quran Search**: All 114 surahs, 6236 verses with Arabic text, word-by-word meanings, and Sahih International translation. Search via `/quran` or the AI agent.
- **Multi-Tool AI Agent**: 6 tools available — `search_knowledge_base`, `search_dua`, `search_quran`, `get_faq_answer`, `get_recent_content`, `browse_web`. Up to 3 tool-calling rounds per response.
- **8-Provider AI Fallback**: OpenRouter (primary) → Groq → Gemini 2.0 → OpenAI → DeepSeek → Anthropic → xAI Grok-3 → Ollama (local).
- **Conversation Memory**: Per-user chat history remembered across messages. Clear with `/forget`.
- **Bookmarks**: Save duas, Quran verses, and search results for quick access. Manage via `/myduas`.
- **Content Scheduling**: Schedule posts to the channel at specific times. Persists to Firestore to survive Render restarts.
- **Feedback System**: Thumbs up/down on every AI response, stored in Firestore.
- **Firebase Sync**: FAQs, questions, suggestions, feedback, giveaway entries, bookmarks, scheduled posts, and activity logs stored in Firestore.
- **Admin Dashboard**: Full SPA web dashboard at `/` with analytics, FAQ management, broadcasting, polls, giveaways, moderation, and live logs.
- **Anti-Spam**: Automatic link deletion in group chats for non-admins.
- **Personalized Onboarding**: New group members receive a DM with command hints and welcome message.
- **Render Keep-Alive**: HTTP server + self-pinger to prevent Render free-tier sleep.

## Quick Start

1. Copy `.env.example` to `.env` and fill in your values (Telegram token, API keys, etc.)
2. Install dependencies: `pip install -r requirements.txt`
3. Run: `python main.py`

The first startup will:
- Validate AI provider keys and log diagnostics
- Ingest `knowledge_base.json` content into ChromaDB
- Begin background ingestion of Hisnul Muslim duas from https://dua.gtaf.org (420+ duas)
- Ingest Quran verses (6236 verses across 114 surahs)
- Load pending scheduled posts from Firestore

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
| `/quran <query>` | Search Quran verses |
| `/myduas` | View your bookmarked duas |
| `/forget` | Clear conversation history |
| `/suggest <topic>` | Suggest a topic |
| `/subscribe` | Get daily Islamic reminders |
| `/unsubscribe` | Stop daily reminders |
| `/remindertime` | Set reminder time (morning/evening) |
| `/language` | Set preferred language (EN/BN) |
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
| `/ingestquran` | Re-index Quran verses |
| `/listsuggestions` | View topic suggestions |
| `/startgiveaway <Prize>` | Start a giveaway |
| `/pickwinner` | Draw giveaway winner |
| `/schedule "YYYY-MM-DD HH:MM" "msg"` | Schedule a channel post |
| `/schedule list` | View scheduled posts |
| `/schedule cancel <id>` | Cancel a scheduled post |
| `/channelstats` | Show channel subscriber count & bot stats |
| `/quiz "Q" "Op1" "Op2" "Op3" "Explanation"` | Send interactive quiz |
| `/checkkeys` | Test all AI provider API keys live |

## Project Structure

```
bot/
├── ai.py              # Multi-tool agent + 8-provider cascade
├── config.py          # Environment config + startup validation
├── database.py        # Firebase CRUD (FAQs, bookmarks, scheduled posts, etc.)
├── dua_scraper.py     # Hisnul Muslim scraper & ingester
├── fastapi_app.py     # FastAPI webhook handler + dashboard API
├── jobs.py            # Scheduled content posting
├── memory.py          # Conversation history
├── pipeline.py        # Content ingestion pipeline
├── quran_scraper.py   # Quran data scraper & ingester
├── rss.py             # RSS feed parsers
├── search.py          # BM25, hybrid search, dua/quran search
├── server.py          # Admin web dashboard (SPA)
├── transcriber.py     # Voice transcription via Groq Whisper
├── vectordb.py        # ChromaDB vector store
├── handlers/
│   ├── admin.py       # Admin command handlers
│   ├── bookmarks.py   # Bookmark add/remove/view callbacks
│   ├── commands.py    # User command handlers
│   ├── feedback.py    # Feedback callbacks
│   ├── influencer.py  # Scheduling, quizzes, channel stats
│   ├── inline.py      # Inline query handler
│   ├── messages.py    # Free-text handler + central callback router
│   ├── meta.py        # Meta (WhatsApp/Messenger/Instagram) handler
│   ├── navigation.py  # Dua category + Quran surah navigation
│   └── user_prefs.py  # Language & reminder time preferences
main.py                # Entry point
requirements.txt       # Dependencies
knowledge_base.json    # Static KB source
agent.md               # Agentic RAG docs
skill.md               # Bot skills docs
```

## Provider Cascade

| Priority | Provider | Model | Tools | Notes |
|---|---|---|---|---|
| 1 | OpenRouter | `gpt-4o-mini` | Full agent (5 tools) | Primary — best reliability |
| 2 | Groq | `llama-3.1-8b-instant` | Simple | Fast inference + Whisper transcription |
| 3 | Gemini | `gemini-2.0-flash` | Simple | Google's latest |
| 4 | OpenAI | `gpt-4o-mini` | Full agent (5 tools) | Direct API fallback |
| 5 | DeepSeek | `deepseek-chat` | Simple | Cost-effective reasoning |
| 6 | Anthropic | `claude-3-haiku` | Simple | Claude fallback |
| 7 | xAI | `grok-3` | Simple | Grok fallback |
| 8 | Ollama | `llama3.2:3b` | Simple | Local fallback (optional) |

## Dependencies

- `python-telegram-bot[job-queue]` — Telegram framework
- `chromadb` — Vector database
- `sentence-transformers` — Text embeddings
- `rank-bm25` — Keyword search
- `langchain-text-splitters` — Text chunking
- `firebase-admin` — Firebase/Firestore
- `feedparser` + `httpx` — RSS fetching
- `litellm` — Multi-provider AI routing
- `python-dotenv` — Environment management
