# Bot Skills & Logic Flow

This file documents the specialized skills the bot possesses.

## 1. Content Syndication
- **YouTube RSS**: Uses `feedparser` to parse `https://www.youtube.com/feeds/videos.xml?channel_id={YOUTUBE_CHANNEL_ID}`.
- **Medium RSS**: Parses `https://medium.com/feed/@{MEDIUM_USERNAME}`.
- **Substack RSS**: Parses `{SUBSTACK_URL}/feed`.
- **Daily Content Post**: Once daily at 9 AM, picks ONE piece of content from a random platform and posts to channel. Avoids spamming the channel with multiple posts.
- **Admin Manual Post**: Admin can use `/postlatest` to force-broadcast latest content from all platforms.
- **Auto-Ingest**: Each auto-post also triggers `ingest_rss_content()` which chunks and embeds the new content into the vector DB.
- **YouTube Transcription**: Videos are transcribed via Groq Whisper and ingested as searchable text content.

## 2. Agentic RAG with Hybrid Search
- **Vector DB**: ChromaDB with `all-MiniLM-L6-v2` embeddings for semantic search.
- **Keyword Search**: BM25 index (`rank-bm25`) for exact term matching.
- **Hybrid Search**: Interpolated scores (alpha=0.5) from vector + BM25 results.
- **Reranking**: Optional cross-encoder reranking for precision.
- **Chunking**: LangChain `RecursiveCharacterTextSplitter` (500 chars, 80 overlap).
- **Semantic Caching**: Repeated queries return cached responses for speed.

## 3. Hisnul Muslim Dua Database
- **Source**: https://dua.gtaf.org — 421 authentic Islamic duas (supplications).
- **Data**: Each dua includes Arabic text (with diacritics), transliteration, English translation, and hadith source reference.
- **Categories**: 15 categories covering Morning & Evening, Sleeping, Prayer, Food & Drink, Travel, Sickness, Hajj, Ramadan, and more.
- **Search**: Both the AI agent (via `search_dua` tool) and the `/dua` command can search the dua database.
- **Navigation**: Inline keyboard browsing by category with chapter names.
- **Bookmarks**: Users can save favorite duas for quick access via `/myduas`.
- **Ingestion**: Automatically scraped and indexed on startup; deduplicates by dua ID.

## 4. Quran Database
- **Coverage**: All 114 surahs, 6236 verses with Arabic text and English translation.
- **Data**: Each verse includes Arabic text, word-by-word meanings, and Sahih International translation.
- **Search**: Both the AI agent (via `search_quran` tool) and the `/quran` command can search the Quran.
- **Navigation**: Inline keyboard browsing by surah with page navigation.
- **Bookmarks**: Users can save favorite verses for quick access via `/myduas`.
- **Ingestion**: Automatically indexed on startup; deduplicates by verse ID.

## 5. Multi-Tool AI Agent
The bot uses OpenAI-compatible function calling with 5 tools:
- `search_knowledge_base` — hybrid RAG search over creator content
- `search_dua` — vector search over Hisnul Muslim duas
- `search_quran` — vector search over Quran verses
- `get_faq_answer` — FAQ keyword lookup
- `get_recent_content` — RSS fetcher for latest posts
- `browse_web` — fetch full text from URLs for current events

The agent can call multiple tools in sequence, up to 3 rounds, before generating the final response.

## 6. Provider Cascade
8 AI providers with automatic fallback:
1. **OpenRouter** (primary) — full agent with tools
2. **Groq** — fast inference + Whisper voice transcription
3. **Gemini 2.0** — Google's latest model
4. **OpenAI** — direct API fallback with tools
5. **DeepSeek** — cost-effective reasoning (no tool calling)
6. **Anthropic** — Claude fallback
7. **xAI Grok-3** — Grok fallback
8. **Ollama** — local fallback (optional)

Circuit breaker: Providers that fail 3 times are skipped for 5 minutes.

## 7. Conversation Memory
Per-user chat history stored in-memory (last 5 exchanges). Users can clear with `/forget`. Memory is injected into the system prompt for context-aware conversations. Automatic summarization when history exceeds limit.

## 8. Feedback System
Thumbs up/down inline buttons on every AI response. Feedback stored in Firestore `feedback` collection. Displayed in dashboard and `/stats`.

## 9. Bookmarks System
- **Save**: Users can bookmark duas, Quran verses, and search results.
- **Storage**: Firestore `user_bookmarks` collection with per-user subcollections.
- **View**: Paginated view via `/myduas` command.
- **Remove**: Inline button to remove individual bookmarks.

## 10. Content Scheduling
- **Schedule**: Admin can schedule posts to channel at specific times via `/schedule`.
- **Persistence**: Posts stored in Firestore `scheduled_posts` collection.
- **Survival**: Posts survive Render restarts via startup reload.
- **Processing**: Background job checks every minute for due posts.
- **Cancellation**: Admin can cancel scheduled posts via `/schedule cancel <id>`.

## 11. Interactive Quizzes
- **Send**: Admin can send quizzes to channel via `/quiz`.
- **Format**: Telegram quiz with correct answer always as first option.
- **Explanation**: Optional explanation text shown after answer.

## 12. Dynamic Firebase Storage
Integrates with Google Cloud Firestore via `firebase-admin`.
- **Collections**: `faqs`, `questions`, `suggestions`, `giveaway_entries`, `activity_logs`, `users`, `feedback`, `subscriptions`, `token_usage`, `user_tokens`, `usage`, `user_bookmarks`, `scheduled_posts`

## 13. Community Moderation
- **Anti-Spam**: In Supergroups, auto-deletes messages with `http://` or `https://` from non-admins.
- **Mute/Ban**: Admin can reply with `/ban` or `/mute`.
- **Dashboard Moderation**: Ban/mute/unmute via web dashboard API endpoints.

## 14. Personalized Onboarding
- **Welcome Message**: New group members receive a greeting in the group.
- **DM Onboarding**: New members receive a personalized DM with command hints and welcome text.
- **Privacy-Aware**: Gracefully handles users with privacy settings blocking DMs.

## 15. API Key Validation
- **Startup Check**: `validate_ai_keys()` runs at startup and logs diagnostics.
- **Emoji Indicators**: ✅ for configured, ⚠️ for missing, 🚫 for none configured.
- **Live Testing**: `/checkkeys` command tests all providers live from Telegram.

## 16. Render Keep-Alive System
- **Dummy Server**: Lightweight HTTPServer on port 8080.
- **Self-Pinger**: GET request to `RENDER_EXTERNAL_URL` every 10 minutes.
- **FastAPI**: Webhook handler + dashboard API served via uvicorn.
