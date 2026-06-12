# Bot Skills & Logic Flow ⚙️

This file documents the specialized skills the bot possesses.

## 1. Content Syndication
- **YouTube RSS**: Uses `feedparser` to parse the XML feed at `https://www.youtube.com/feeds/videos.xml?channel_id={YOUTUBE_CHANNEL_ID}`.
- **Medium RSS**: Uses `feedparser` to parse the XML feed at `https://medium.com/feed/@{MEDIUM_USERNAME}`.
- **Substack RSS**: Uses `feedparser` to parse the XML feed at `{SUBSTACK_URL}/feed`.
- **Auto-Posting**: The `python-telegram-bot` JobQueue schedules daily checks at 09:00 (YouTube), 14:00 (Substack), and 18:00 (Medium). If the top fetched URL does not match `last_posted_url`, it broadcasts to the configured `CHANNEL_ID`.

## 2. Dynamic Firebase Storage
The bot integrates with Google Cloud Firestore via `firebase-admin` to maintain state across Render reboots.
- **Collections:**
  - `faqs`: Custom trigger words and responses added by the admin via `/addfaq`.
  - `questions`: A log of every question users ask the bot.
  - `suggestions`: Community suggestions for geopolitics topics submitted via `/suggest`.
  - `giveaway_entries`: Temporary collection for giveaway participants.

## 3. Community Moderation
- **Anti-Spam**: In Supergroups, the bot automatically deletes any message containing `http://` or `https://` unless the sender is the configured `ADMIN_ID`.
- **Mute/Ban**: The admin can quickly moderate the chat by replying to a user's message with `/ban` or `/mute`.

## 4. Render Keep-Alive System
Render spins down free tiers after 15 minutes of inactivity. To bypass this:
- **Dummy Server**: A lightweight `HTTPServer` runs on port `8080` in a background thread to satisfy Render's port-binding requirement.
- **Self-Pinger**: A background thread reads `RENDER_EXTERNAL_URL` and sends a GET request to itself every 10 minutes to prevent the container from sleeping.
