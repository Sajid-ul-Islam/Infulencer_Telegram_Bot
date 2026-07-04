# Goal and Context

This document serves as the guide for the **Bearded Bangali Telegram & Meta Assistant Bot** project. It outlines the project's primary objectives, architectural layout, platform integrations, database synchronization, and hosting constraints.

---

## 🎯 Project Goal

The primary goal is to maintain and expand a multi-platform virtual assistant for the **Bearded Bangali** content creator community that:
1. **Syndicates Content**: Automatically fetches new YouTube, Medium, and Substack updates via RSS feeds and broadcasts them to the Telegram channel.
2. **Answers Community Queries**: Provides accurate answers to user questions (RAG/Hybrid Search) using the creator's knowledge base and the *Hisnul Muslim* authentic Islamic dua database.
3. **Engages Followers**: Supports interactive features (giveaways, polls, inline search, suggestions) via Telegram and Meta (WhatsApp, Messenger, Instagram).
4. **Ensures 100% Uptime on Free Hosting**: Operates efficiently on Render's free tier using a self-pinging keep-alive mechanism to prevent containers from falling asleep.

---

## 🏗️ Architecture & Component Context

The bot is implemented in Python and runs a FastAPI/Uvicorn server alongside the `python-telegram-bot` application loop.

### 📱 1. Platform Integrations

- **Telegram Assistant**: Handled by `python-telegram-bot` (`main.py` & `bot/handlers/`).
  - [commands.py](file:///h:/Repo/Infulencer_Telegram_Bot/bot/handlers/commands.py): Handles commands like `/start`, `/latest`, `/dua`, and `/ask`.
  - [messages.py](file:///h:/Repo/Infulencer_Telegram_Bot/bot/messages.py): Direct message interactions, inline queries, group anti-spam rules.
  - [admin.py](file:///h:/Repo/Infulencer_Telegram_Bot/bot/handlers/admin.py): Administrative functions like `/postlatest`, `/broadcast`, `/stats`, `/ban`, and giveaway control.
- **Meta (WhatsApp / Messenger / Instagram)**: 
  - FastAPI webhook endpoint at `/api/meta/webhook` in [fastapi_app.py](file:///h:/Repo/Infulencer_Telegram_Bot/bot/fastapi_app.py#L48-L73) verifies the hub token and processes incoming messages.
  - Payloads are asynchronously passed to [meta.py](file:///h:/Repo/Infulencer_Telegram_Bot/bot/handlers/meta.py) which strips HTML, requests responses from the AI Engine, and replies back via the Meta Graph API.

### 🧠 2. AI Engine & Hybrid RAG

- **Multi-Provider Cascade**: Managed in [ai.py](file:///h:/Repo/Infulencer_Telegram_Bot/bot/ai.py). To ensure reliability across API quotas and transient errors, the AI engine uses a fallback structure:
  $$\text{OpenRouter (Primary)} \rightarrow \text{Groq} \rightarrow \text{OpenAI} \rightarrow \text{Anthropic} \rightarrow \text{xAI (Grok)} \rightarrow \text{Gemini (Final)}$$
- **Vector Search (ChromaDB)**: Documents are embedded using `all-MiniLM-L6-v2` in [vectordb.py](file:///h:/Repo/Infulencer_Telegram_Bot/bot/vectordb.py). Supports filtered queries for specific document scopes.
- **BM25 + Hybrid Search**: In [search.py](file:///h:/Repo/Infulencer_Telegram_Bot/bot/search.py), a keyword BM25 search is combined with Vector similarity scoring (weighted by $\alpha$) and reranked using a cross-encoder model to return highly relevant context.
- **Scraped Dua Database**: A dataset of 421 authentic supplications is scraped from `dua.gtaf.org` by [dua_scraper.py](file:///h:/Repo/Infulencer_Telegram_Bot/bot/dua_scraper.py) and vectorized into ChromaDB.

### 📂 3. Database & Memory System

- **Firebase / Firestore**: Implemented in [database.py](file:///h:/Repo/Infulencer_Telegram_Bot/bot/database.py). Syncs user state, live logs, dashboard statistics, custom FAQs, suggestions, and feedback responses (thumbs up/down).
- **Session Memory**: In [memory.py](file:///h:/Repo/Infulencer_Telegram_Bot/bot/memory.py), user conversations are cached (defaulting to the last 3 exchanges) to provide coherent multi-turn dialogue.

---

## ⚡ Render Free Tier Optimization (Keep-Alive)

Because this service is hosted on **Render's Free Tier**, it is subject to a spin-down policy:
> [!WARNING]
> Render free-tier web services spin down (go to sleep) after 15 minutes of inactivity (no incoming HTTP traffic). The next incoming request will experience a cold-start delay of 50 seconds or more, which breaks Telegram's webhook latency limits and compromises WhatsApp/Messenger webhook limits (Meta requires webhooks to respond with `200 OK` within 20 seconds).

### 🛠️ Self-Pinger Implementation
To circumvent the spin-down, the bot runs a daemon keep-alive thread:
- **Location**: `ping_self()` in [server.py](file:///h:/Repo/Infulencer_Telegram_Bot/bot/server.py#L62-L85)
- **Interval**: Sleep for 10 minutes (`time.sleep(600)`) between requests.
- **Action**: Triggers an HTTP `GET` request to its own public URL (using `RENDER_EXTERNAL_URL`).
- **Telemetry**: Records latencies and HTTP status codes in `ping_history` to display on the SPA dashboard at [fastapi_app.py](file:///h:/Repo/Infulencer_Telegram_Bot/bot/fastapi_app.py#L44-L46).

---

## 🚨 Guidelines for AI Developers

When working on this repository, **always adhere to the following constraints**:

1. **Keep-Alive Integrity**: Never disable or block the `ping_self()` loop. If changing the web routing in [fastapi_app.py](file:///h:/Repo/Infulencer_Telegram_Bot/bot/fastapi_app.py) or [server.py](file:///h:/Repo/Infulencer_Telegram_Bot/bot/server.py), ensure `/` remains accessible and responsive.
2. **Resource Constraints**: Render's free tier has CPU and RAM limits (typically 512MB RAM). Avoid loading excessively large model weights in-memory. Rerankers and sentence-transformers should use lightweight architectures (`all-MiniLM-L6-v2`).
3. **Environment Setup**: Access configurations exclusively via [config.py](file:///h:/Repo/Infulencer_Telegram_Bot/bot/config.py) and ensure any new secrets are added to `.env.example` first.
4. **Fast Webhook Acknowledgement**: When handling webhooks (especially Meta payload handlers in [meta.py](file:///h:/Repo/Infulencer_Telegram_Bot/bot/handlers/meta.py)), return a `200 OK` response instantly and execute AI tasks asynchronously using background tasks to prevent Meta or Telegram from retrying failed requests.
