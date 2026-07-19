# TELEGRAM CONTENT BOT - COMPLETE GUIDE

## What This Bot Does

**Auto-Posts Your Content**
- Posts ONE piece of content daily at 9 AM from YouTube, Medium, Substack, Facebook, or Twitter
- Posts daily Islamic reminders (morning & evening)
- Weekly digest every Saturday

**AI-Powered Q&A**
- Multi-provider AI with 8 fallback providers
- Hybrid RAG search over your content + Hisnul Muslim duas + Quran
- Voice message transcription via Groq Whisper
- Per-user conversation memory

**Influencer Features**
- Content scheduling with Firestore persistence
- Interactive quizzes for channel engagement
- Channel subscriber stats
- Personalized DM onboarding for new members
- Streaks & gamification

**Admin Dashboard**
- Reply to Telegram/WhatsApp user queries directly from the dashboard
- Manage FAQs, broadcasts, polls, giveaways
- View analytics, trending topics, live logs

---

## DEPLOYMENT (Render)

### Step 1: Prepare Your Code

```bash
# Create folder
mkdir telegram-content-bot
cd telegram-content-bot

# Copy files:
# - main.py
# - bot/
# - templates/
# - requirements.txt
# - .env (filled with your values)
# - .gitignore
```

### Step 2: Create .gitignore
```
.env
__pycache__/
*.pyc
.DS_Store
venv/
chroma_db/
```

### Step 3: Push to GitHub

```bash
git init
git add .
git commit -m "Initial telegram bot"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/telegram-content-bot.git
git push -u origin main
```

### Step 4: Deploy on Render

1. Go to https://render.com
2. Click "New +" → "Web Service"
3. Select your GitHub repo
4. Fill in:
   - **Name:** `telegram-content-bot`
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python main.py`
   - **Instance Type:** Free (or Starter for better reliability)

5. Add Environment Variables:
   - Click "Environment"
   - Add at minimum:
     ```
     TELEGRAM_TOKEN=your_token_here
     CHANNEL_ID=-100123456789
     OPENROUTER_API_KEY=sk-or-v1-...
     GROQ_API_KEY=gsk_...
     FIREBASE_CREDENTIALS={"type":"service_account",...}
     DASHBOARD_PASSWORD=your_secure_password
     ```

6. Click "Create Web Service"
7. Wait for deployment

---

## Required Environment Variables

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_TOKEN` | Yes | Bot token from @BotFather |
| `CHANNEL_ID` | Yes | Telegram channel ID (starts with -100) |
| `GROUP_ID` | Optional | Telegram group ID (enables moderation features) |
| `ADMIN_ID` | Optional | Your Telegram user ID (enables admin commands) |
| `FIREBASE_CREDENTIALS` | Yes | Firebase service account JSON |
| `DASHBOARD_PASSWORD` | Yes | Password for admin dashboard (no default — must be set) |
| `OPENROUTER_API_KEY` | Yes | Primary AI provider |
| `GROQ_API_KEY` | Fallback | Fast inference + voice transcription |
| `OPENAI_API_KEY` | Fallback | OpenAI direct API |
| `ANTHROPIC_API_KEY` | Fallback | Anthropic Claude |
| `GEMINI_API_KEY` | Fallback | Google Gemini |
| `XAI_API_KEY` | Fallback | xAI Grok |
| `DEEPSEEK_API_KEY` | Fallback | DeepSeek |
| `OLLAMA_BASE_URL` | Optional | Local Ollama server URL |
| `WEBHOOK_URL` | Optional | Explicit webhook URL (falls back to RENDER_EXTERNAL_URL) |

---

## FEATURES EXPLAINED

### Content Posting (Once Daily)
The bot posts ONE piece of content to the channel daily at 9 AM:
- Picks a random platform (YouTube, Medium, Substack, Facebook, or Twitter)
- Posts the latest or a random entry from that platform
- Admin can use `/postlatest` to force-post all platforms manually

### AI Q&A System
When someone DMs the bot or asks in a group:
1. Bot receives message
2. Searches conversation memory for context
3. Uses hybrid RAG (vector + BM25) to find relevant content
4. Can call 5 tools: knowledge base, duas, Quran, FAQs, recent content
5. Falls back through 8 AI providers if one fails
6. Returns response with feedback buttons (thumbs up/down)

### Streaks & Gamification
- Users earn streaks for daily engagement (asking questions, searching duas/Quran, bookmarking)
- Streak increments if active yesterday, resets if inactive 2+ days
- View streak with `/profile`
- Firestore collection: `user_streaks`

### Admin Manual Reply
- Admin opens "Reply to Users" tab in dashboard
- Sees pending queries from Telegram and WhatsApp users
- Clicks a query, types a reply, sends it
- Reply delivered to user via Telegram Bot API or WhatsApp Meta API
- Firestore collection: `pending_queries`

### Trending Topics
- `/trending` shows popular keywords, recent questions, and popular commands
- Based on activity in the last 24 hours
- Keywords extracted from user questions with stop-word filtering

### Content Scheduling
```
/schedule "2026-07-06 14:00" "Check out my new video!"
/schedule list          # View pending posts
/schedule cancel <id>   # Cancel a scheduled post
```
Posts are persisted to Firestore and survive Render restarts.

---

## TROUBLESHOOTING

**Bot not posting to channel?**
- Check CHANNEL_ID is correct (should start with -100)
- Check bot is admin in channel with "Post Messages" permission
- Check TELEGRAM_TOKEN is valid

**AI not responding?**
- Run `/checkkeys` to test all API providers
- Ensure at least OPENROUTER_API_KEY or GROQ_API_KEY is set
- Check Render logs for provider errors

**Dashboard not accessible?**
- Ensure DASHBOARD_PASSWORD is set in environment variables
- No default password — must be explicitly configured

**Voice messages not working?**
- Ensure GROQ_API_KEY is set (uses Groq Whisper)
- Check voice transcription rate limits

**Check Logs on Render:**
- Go to your service
- Click "Logs" tab
- Look for provider status at startup

---

## LOCAL DEVELOPMENT

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # Fill in your values
python main.py
```
