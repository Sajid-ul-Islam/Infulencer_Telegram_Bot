# Goal and Context

This document serves as the guide for the **Bearded Bangali Telegram & Meta Assistant Bot** project. It outlines the project's primary objectives, architectural layout, platform integrations, database synchronization, and hosting constraints.

---

## 🎯 Project Goal

The primary goal is to maintain and expand a multi-platform virtual assistant for the **Bearded Bangali** content creator community that:
1. **Syndicates Content**: Automatically fetches new YouTube, Medium, and Substack updates via RSS feeds and broadcasts them to the Telegram channel.
2. **Answers Community Queries**: Provides accurate answers to user questions (RAG/Hybrid Search) using the creator's knowledge base, the *Hisnul Muslim* authentic Islamic dua database, and the complete Quran (6236 verses across 114 surahs).
3. **Engages Followers**: Supports interactive features (giveaways, polls, quizzes, content scheduling, inline search, suggestions, bookmarks) via Telegram and Meta (WhatsApp, Messenger, Instagram).
4. **Ensures 100% Uptime on Free Hosting**: Operates efficiently on Render's free tier using a self-pinging keep-alive mechanism to prevent containers from falling asleep.

---

## 🏗️ Architecture & Component Context

The bot is implemented in Python and runs a FastAPI/Uvicorn server alongside the `python-telegram-bot` application loop.

### 📱 1. Platform Integrations

- **Telegram Assistant**: Handled by `python-telegram-bot` (`main.py` & `bot/handlers/`).
  - [commands.py](bot/handlers/commands.py): Handles commands like `/start`, `/latest`, `/dua`, `/quran`, and `/ask`.
  - [messages.py](bot/handlers/messages.py): Direct message interactions, inline queries, group anti-spam rules, central callback router.
  - [admin.py](bot/handlers/admin.py): Administrative functions like `/postlatest`, `/broadcast`, `/stats`, `/ban`, `/schedule`, `/quiz`, `/checkkeys`, and giveaway control.
  - [influencer.py](bot/handlers/influencer.py): Content scheduling, channel stats, quiz sending.
  - [bookmarks.py](bot/handlers/bookmarks.py): Save/view/remove bookmarked duas and Quran verses.
  - [navigation.py](bot/handlers/navigation.py): Dua category browsing and Quran surah navigation via inline keyboards.
  - [user_prefs.py](bot/handlers/user_prefs.py): Language and reminder time preferences.
- **Meta (WhatsApp / Messenger / Instagram)**: 
  - FastAPI webhook endpoint at `/api/meta/webhook` in [fastapi_app.py](bot/fastapi_app.py) verifies the hub token and processes incoming messages.
  - Payloads are asynchronously passed to [meta.py](bot/handlers/meta.py) which strips HTML, requests responses from the AI Engine, and replies back via the Meta Graph API.

### 🧠 2. AI Engine & Hybrid RAG

- **Multi-Provider Cascade**: Managed in [ai.py](bot/ai.py). To ensure reliability across API quotas and transient errors, the AI engine uses a fallback structure with 8 providers:
  ```
  OpenRouter (Primary) → Groq → Gemini 2.0 → OpenAI → DeepSeek → Anthropic → xAI Grok-3 → Ollama (local)
  ```
- **API Key Validation**: On startup, `validate_ai_keys()` in [config.py](bot/config.py) checks all provider keys and logs diagnostics (✅/⚠️/🚫).
- **Vector Search (ChromaDB)**: Documents are embedded using `all-MiniLM-L6-v2` in [vectordb.py](bot/vectordb.py). Supports filtered queries for specific document scopes.
- **BM25 + Hybrid Search**: In [search.py](bot/search.py), a keyword BM25 search is combined with Vector similarity scoring (weighted by α) and reranked using a cross-encoder model to return highly relevant context.
- **Scraped Dua Database**: A dataset of 421 authentic supplications is scraped from `dua.gtaf.org` by [dua_scraper.py](bot/dua_scraper.py) and vectorized into ChromaDB.
- **Quran Database**: All 114 surahs, 6236 verses with Arabic text, word-by-word meanings, and Sahih International translation, scraped by [quran_scraper.py](bot/quran_scraper.py).
- **5-Tool Agent**: `search_knowledge_base`, `search_dua`, `search_quran`, `get_faq_answer`, `get_recent_content`, `browse_web`.

### 📂 3. Database & Memory System

- **Firebase / Firestore**: Implemented in [database.py](bot/database.py). Syncs user state, live logs, dashboard statistics, custom FAQs, suggestions, feedback responses (thumbs up/down), bookmarks, scheduled posts, and user preferences.
- **Session Memory**: In [memory.py](bot/memory.py), user conversations are cached (defaulting to the last 3 exchanges) to provide coherent multi-turn dialogue with automatic summarization.

### 📅 4. Content Scheduling

- **Firestore-Backed**: Scheduled posts persist to Firestore and survive Render restarts via startup reload in [influencer.py](bot/handlers/influencer.py).
- **Admin Commands**: `/schedule` to create, list, and cancel scheduled posts.
- **Background Processing**: Posts are checked every minute and sent when due.

### 🔖 5. Bookmarks System

- **User Bookmarks**: Save duas, Quran verses, and search results for quick access.
- **Firestore Storage**: Stored in `user_bookmarks` collection with per-user subcollections.
- **Inline Management**: View and remove bookmarks via `/myduas` command with pagination.

---

## ⚡ Render Free Tier Optimization (Keep-Alive)

Because this service is hosted on **Render's Free Tier**, it is subject to a spin-down policy:
> [!WARNING]
> Render free-tier web services spin down (go to sleep) after 15 minutes of inactivity (no incoming HTTP traffic). The next incoming request will experience a cold-start delay of 50 seconds or more, which breaks Telegram's webhook latency limits and compromises WhatsApp/Messenger webhook limits (Meta requires webhooks to respond with `200 OK` within 20 seconds).

### 🛠️ Self-Pinger Implementation
To circumvent the spin-down, the bot runs a daemon keep-alive thread:
- **Location**: `ping_self()` in [server.py](bot/server.py)
- **Interval**: Sleep for 10 minutes (`time.sleep(600)`) between requests.
- **Action**: Triggers an HTTP `GET` request to its own public URL (using `RENDER_EXTERNAL_URL`).
- **Telemetry**: Records latencies and HTTP status codes in `ping_history` to display on the SPA dashboard at [fastapi_app.py](bot/fastapi_app.py).

---

## 🚨 Guidelines for AI Developers

When working on this repository, **always adhere to the following constraints**:

1. **Keep-Alive Integrity**: Never disable or block the `ping_self()` loop. If changing the web routing in [fastapi_app.py](bot/fastapi_app.py) or [server.py](bot/server.py), ensure `/` remains accessible and responsive.
2. **Resource Constraints**: Render's free tier has CPU and RAM limits (typically 512MB RAM). Avoid loading excessively large model weights in-memory. Rerankers and sentence-transformers should use lightweight architectures (`all-MiniLM-L6-v2`).
3. **Environment Setup**: Access configurations exclusively via [config.py](bot/config.py) and ensure any new secrets are added to `.env.example` first.
4. **Fast Webhook Acknowledgement**: When handling webhooks (especially Meta payload handlers in [meta.py](bot/handlers/meta.py)), return a `200 OK` response instantly and execute AI tasks asynchronously using background tasks to prevent Meta or Telegram from retrying failed requests.
5. **Provider Fallback**: The AI cascade tries 8 providers in order. DeepSeek does not support function calling, so it receives plain completions without tools. Ollama is the final local fallback.
6. **Firestore Persistence**: Scheduled posts and bookmarks use Firestore for persistence. Always check `if db:` before Firestore operations to handle degraded mode gracefully.
