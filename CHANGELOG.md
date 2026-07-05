# Changelog

All notable changes to the Bearded Bangali Telegram Bot are documented here.

## [Unreleased] — July 5, 2026

### 🚀 New Features

#### AI Provider Improvements
- **8-Provider AI Cascade**: Expanded from 6 to 8 providers for better reliability
  - OpenRouter (primary) → Groq → **Gemini 2.0** → OpenAI → **DeepSeek** → Anthropic → **xAI Grok-3** → Ollama
- **Updated xAI model** from `grok-2` to `grok-3`
- **Updated Gemini model** from `gemini-1.5-flash` to `gemini-2.0-flash`
- **Added DeepSeek** as a new fallback provider (`deepseek/deepseek-chat`)
- **DeepSeek tool calling fix**: DeepSeek doesn't support function calling, so TOOLS are excluded when that provider is active

#### Admin Commands
- **`/checkkeys`** — Test all AI provider API keys live from Telegram, shows ✅/❌/⏭️ status for each provider + infrastructure check
- **`/schedule`** — Schedule posts to channel at specific times with sub-commands: `list`, `cancel <id>`
- **`/channelstats`** — Show channel subscriber count, scheduled posts, vector DB docs, questions, suggestions, and feedback stats
- **`/quiz`** — Send interactive quizzes to the channel with multiple choice options and explanations

#### Content Scheduling
- **Firestore-backed scheduled posts** — Posts persist to Firestore and survive Render free-tier restarts
- **Startup reload** — Pending posts are restored from Firestore on bot restart
- **Race condition fix** — Firestore status is updated before in-memory status to prevent re-sends on restart

#### Influencer Features
- **Channel member count API** — Get subscriber count via Telegram API
- **Enhanced broadcast** — Supports polls and quizzes via admin commands

#### User Features
- **Personalized DM onboarding** — New group members receive a welcome DM with command hints
- **Quran search** — All 114 surahs, 6236 verses with Arabic text, word-by-word meanings, and Sahih International translation
- **Bookmarks system** — Save duas, Quran verses, and search results for quick access via `/myduas`
- **Dua category navigation** — Browse duas by category with inline keyboards
- **Quran surah navigation** — Browse Quran by surah with page navigation

### 🐛 Bug Fixes

#### Critical
- **Added `ingest_text_content()`** to `bot/pipeline.py` — Was completely missing, causing YouTube transcription+ingest to crash
- **Added `get()` method** to `InMemoryDocStore` in `bot/vectordb.py` — ChromaDB-compatible backwards-compat that fixes daily Islamic reminders and bookmark metadata lookups
- **Fixed `_is_valid_key` import** in `checkkeys_command` — Changed from non-existent `is_valid_key` to `_is_valid_key as is_valid_key` from `bot.config`
- **Fixed missing `asyncio` import** in `bot/handlers/admin.py` — Added module-level import needed for `asyncio.gather` in `checkkeys_command`
- **Fixed syntax error** in `checkkeys_command` — `return` and `from` import were concatenated on the same line

#### Improvements
- **Improved AI assistant error logging** in `bot/ai.py` — Now logs exactly which providers were attempted vs skipped when all fail
- **API key validation on startup** — `validate_ai_keys()` runs at startup and logs clear diagnostics (✅/⚠️/🚫) for all 8 providers

### 🧹 Code Cleanup

#### Dead Code Removal
- **Removed unused `ABC`, `abstractmethod` imports** from `bot/ai.py`
- **Removed duplicate Firebase status line** in `checkkeys_command`
- **Removed unused `content` variable** in `test_provider` function
- **Removed unused imports** (`RECOMMENDED_MODELS`, `FIREBASE_CREDENTIALS`, `get_channel_member_count`) from `checkkeys_command`
- **Deleted duplicate `Goal and Contextl.md`** file (typo filename)

#### Handler Refactoring
- **Created `bot/handlers/bookmarks.py`** — Extracted bookmark add/remove/view/pagination callbacks from messages.py
- **Created `bot/handlers/navigation.py`** — Extracted dua category browsing and Quran surah navigation callbacks
- **Created `bot/handlers/user_prefs.py`** — Extracted language setting and reminder time preference callbacks
- **Created `bot/handlers/influencer.py`** — Content scheduling, channel stats, quiz sending, scheduled post processing
- **Slimmed down `messages.py`** — `button_callback_handler` now delegates to the new focused modules

### 📝 Documentation

- **Updated `README.md`** — Added new features, 8-provider cascade, all commands, updated project structure
- **Updated `DEPLOYMENT_GUIDE.md`** — Added all env vars, new commands, content scheduling, quizzes, troubleshooting
- **Updated `agent.md`** — Updated architecture diagram, added `search_quran` tool, new file layout
- **Updated `Goal and Context.md`** — Added content scheduling, bookmarks, API key validation, provider cascade
- **Updated `skill.md`** — Added Quran database, bookmarks, scheduling, quizzes, onboarding, validation
- **Created `CHANGELOG.md`** — This file

### 🔧 Configuration

- **Added `DEEPSEEK_API_KEY`** to `bot/config.py` and `validate_ai_keys()`
- **Added `_is_valid_key()` helper** to `bot/config.py` (mirrors `ai.is_valid_key()` to avoid circular imports)
- **Added `validate_ai_keys()` function** to `bot/config.py` for startup diagnostics
- **Added `GROUP_ID` documentation** — Clarified that anti-spam works without GROUP_ID, but moderation features need it

### 📦 Firestore Collections Added

- `user_bookmarks` — Per-user bookmark subcollections for duas, Quran verses, and search results
- `scheduled_posts` — Persisted scheduled posts with status tracking (scheduled/sent/failed/cancelled)

---

## Previous Versions

See git history for changes prior to this session.
