# 📱 TELEGRAM CONTENT BOT - COMPLETE GUIDE

## What This Bot Does

✅ **Auto-Posts Your Content**
- Fetches latest YouTube videos daily
- Fetches latest Medium articles daily
- Posts to your Telegram channel automatically
- Posts daily greeting to channel

✅ **Answers Questions**
- Followers ask questions via DM or group
- Bot responds with FAQ answers
- Includes links to all your platforms

✅ **Multiple Commands**
- /latest - Get all latest content
- /youtube - Get latest video
- /medium - Get latest article
- /ask - Ask a question
- /help - Show all commands

---

## 🚀 DEPLOYMENT (Render)

### Step 1: Prepare Your Code

```bash
# Create folder
mkdir telegram-content-bot
cd telegram-content-bot

# Copy files:
# - telegram_bot.py
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
   - **Start Command:** `python telegram_bot.py`
   - **Instance Type:** Free (or Starter for better reliability)

5. Add Environment Variables:
   - Click "Environment"
   - Add:
     ```
     TELEGRAM_TOKEN=your_token_here
     CHANNEL_ID=-100123456789
     ```

6. Click "Create Web Service"
7. Wait for deployment ✅

---

## 🎯 CUSTOMIZE THE BOT

### 1. Update Your Platform Links

Open `telegram_bot.py` and find this section:

```python
# Your content platforms (update with your actual URLs)
YOUTUBE_CHANNEL_ID = "UCxxxxxxxxxxxxxx"
MEDIUM_USERNAME = "your_username"
INSTAGRAM_HANDLE = "@your_instagram"
YOUTUBE_LINK = "https://www.youtube.com/@your_channel"
MEDIUM_LINK = "https://medium.com/@your_username"
INSTAGRAM_LINK = "https://instagram.com/your_handle"
TWITTER_LINK = "https://x.com/your_handle"
FACEBOOK_LINK = "https://facebook.com/your_page"
```

### 2. Add/Edit FAQ Responses

Find this section:

```python
FAQ = {
    "how do you": "Your answer here",
    "edit": "I use Adobe Premiere Pro...",
    "content": "I create content about...",
    "collab": "For collaboration...",
    # Add more here
}
```

**Example:**
```python
FAQ = {
    "how do you edit": "I use Adobe Premiere Pro and Davinci Resolve",
    "what camera": "I use Sony A6700",
    "merch": "Check my shop at: [link]",
    "sponsorship": "DM me on Instagram for brand deals",
}
```

### 3. Customize Welcome Message

Find `async def start()` function and edit the welcome text.

### 4. Change Auto-Post Times

Find this section:

```python
# Post latest YouTube daily at 9 AM
job_queue.run_daily(auto_post_youtube, time=(9, 0), days=(0, 1, 2, 3, 4, 5, 6))

# Post latest Medium daily at 6 PM
job_queue.run_daily(auto_post_medium, time=(18, 0), days=(0, 1, 2, 3, 4, 5, 6))

# Post greeting daily at 8 AM
job_queue.run_daily(greeting_post, time=(8, 0), days=(0, 1, 2, 3, 4, 5, 6))
```

Times are in 24-hour format. Example:
- `(9, 0)` = 9:00 AM
- `(14, 30)` = 2:30 PM
- `(18, 0)` = 6:00 PM

**Days:** 0=Monday, 1=Tuesday, ... 6=Sunday

### 5. Add More Platforms

To add Instagram or Twitter posts:

```python
async def get_instagram_latest():
    """Fetch latest Instagram post"""
    # You'd need to use Instagram API or web scraping
    pass

# Then add to auto-posting:
job_queue.run_daily(auto_post_instagram, time=(19, 0))
```

---

## 📊 FEATURES EXPLAINED

### Auto-Posting
The bot checks for new content from:
- **YouTube:** Uses RSS feed (checks daily)
- **Medium:** Uses RSS feed (checks daily)
- Posts automatically to your channel

### Q&A System
When someone DMs the bot:
1. Bot receives message
2. Searches FAQ for matching keywords
3. Returns relevant answer
4. If no match, shows all platform links

### Commands
Users can type:
```
/start       → Welcome + all links
/latest      → All latest content
/youtube     → Latest video
/medium      → Latest article
/ask         → Prompt to ask question
/help        → All commands
```

---

## 🔧 TROUBLESHOOTING

**Bot not posting to channel?**
- Check CHANNEL_ID is correct (should start with -100)
- Check bot is admin in channel with "Post Messages" permission
- Check TELEGRAM_TOKEN is valid

**Bot not receiving messages?**
- Ensure bot is in group/channel
- Check bot username is correct in Telegram

**Auto-posting not working?**
- Check YOUTUBE_CHANNEL_ID and MEDIUM_USERNAME are correct
- Check RSS feeds are valid (visit them in browser)
- Check Render logs for errors

**Check Logs on Render:**
- Go to your service
- Click "Logs" tab
- See what's happening

---

## 📈 NEXT STEPS

### Basic (Done Now)
✅ Bot created
✅ Auto-posts YouTube/Medium
✅ Answers questions

### Intermediate (Add Later)
- [ ] Add Instagram auto-posting (requires API)
- [ ] Add Twitter/X posting
- [ ] Store user questions in database
- [ ] Create user polls/surveys

### Advanced
- [ ] AI-powered Q&A (use Claude API!)
- [ ] Database of all your content
- [ ] Analytics dashboard
- [ ] Patreon/membership integration
- [ ] Product store integration

---

## 💡 EXAMPLE CUSTOMIZATION

Here's an example if you write about economics:

```python
FAQ = {
    "economics": "I write about economic trends and analysis. Read my articles: " + MEDIUM_LINK,
    "gdp": "GDP analysis posts coming soon! Subscribe to Medium.",
    "inflation": "Economic inflation is caused by...",
    "interview": "For interview requests, contact me on: " + TWITTER_LINK,
    "data": "I use World Bank data and FRED API. Sources in all articles.",
    "collab": "Let's collaborate! DM on Instagram: " + INSTAGRAM_LINK,
}
```

---

## ✨ YOU'RE ALL SET!

Your bot is now:
- ✅ Running 24/7 on Render
- ✅ Auto-posting your content
- ✅ Answering follower questions
- ✅ Connecting all your platforms

Monitor it anytime from your Render dashboard. Update the code and just push to GitHub—Render auto-deploys!

Questions? Check Render logs or test locally first:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python telegram_bot.py
```
