# Changelog

All notable changes to the Bearded Bangali Telegram Bot are documented here.

## [Unreleased] — July 19, 2026

### 🚀 New Features

#### Admin Manual Reply (Dashboard)
- **"Reply to Users" tab** in admin dashboard — view and reply to Telegram/WhatsApp user queries directly from the web UI
- **Pending queries inbox** — unanswered questions stored in Firestore `pending_queries` collection
- **Send replies via Telegram or WhatsApp** — admin types a reply, bot sends it to the user via the correct platform API
- **Query history** — view all past queries with status (pending/answered/dismissed)
- **Dismiss without reply** — admin can dismiss queries that don't need a response

#### User Engagement Features
- **`/trending` command** — shows popular topics, recent questions, and trending commands from the last 24 hours
- **`/profile` command** — shows user stats: name, language, member duration, questions asked, bookmarks, streak
- **Streaks & gamification** — tracks daily engagement streaks (longest + current), auto-resets if inactive 2+ days
- **Streak recording** — automatic on: AI questions, dua search, Quran search, bookmarking

#### Dashboard Security
- **Rate limiting on login** — max 5 login attempts per IP per 5 minutes
- **Required password** — `DASHBOARD_PASSWORD` must be set (no default "admin")
- **503 when unconfigured** — dashboard returns error if no password is set

### 🔧 Code Quality & Performance

#### Non-Blocking Firestore Calls
- **`memory.py` async** — `_ensure_loaded()`, `get_history()`, `add_to_history()`, `clear_history()`, `get_history_count()` are now all async
- **No event loop blocking** — Firestore reads use `await loop.run_in_executor()` instead of blocking

#### RSS Code Refactoring
- **`rss.py` DRY** — created generic `_fetch_rss_feed()` and `_build_rss_message()` functions
- **`jobs.py` DRY** — created generic `_auto_post_platform()` function and `_PLATFORM_CONFIG` dict
- **Merged reminder functions** — `daily_islamic_reminder` and `evening_islamic_reminder` use shared `_send_reminders()`
- **Code reduction** — rss.py -28%, jobs.py -40%

#### Posting Schedule
- **Once daily content post** — picks ONE piece of content from a random platform at 9 AM (was 5+ posts/day)
- **Islamic reminders unchanged** — morning + evening still active
- **Admin manual post** — `/postlatest` still works for force-broadcasting all platforms

### 📦 Firestore Collections Added

- `pending_queries` — user queries awaiting admin reply (Telegram + WhatsApp)
- `user_streaks` — daily engagement streaks (current + longest + last_active)

### 📝 Documentation

- Updated `README.md` — new commands, features, posting schedule
- Updated `CHANGELOG.md` — this file
- Updated `DEPLOYMENT_GUIDE.md` — new env vars, features, posting schedule
- Updated `Goal and Context.md` — updated goals and architecture
- Updated `skill.md` — new skills (streaks, trending, admin reply)
- Updated `agent.md` — updated architecture and file layout

---

## Previous Versions

See git history for changes prior to this session.
