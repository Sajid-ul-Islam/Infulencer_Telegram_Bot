# Bearded Bangali Telegram Bot 🤖

The official, highly advanced Telegram Assistant for the Bearded Bangali content creator community. Built with `python-telegram-bot`, Firebase, and an ultimate Multi-AI Cascading Engine!

## ✨ Features
- **Multi-Platform Polling**: Automatically fetches and posts the latest videos from YouTube and articles from Medium.
- **Smart Agentic RAG**: Answers user questions intelligently using your actual past content as context.
- **Ultimate AI Fallback Router**: Ensures 100% AI uptime by cascading through 6 providers: OpenRouter, Groq, OpenAI, Anthropic, xAI (Grok), and Google Gemini.
- **Firebase Sync**: Safely stores custom FAQs, user questions, suggestions, and giveaway entries in the cloud.
- **Anti-Spam**: Prevents users from posting external links in the community group.
- **Render Uptime**: Contains a dummy HTTP server and self-pinging background thread to bypass Render's sleep limits.

## 🚀 Setup & Deployment
1. Rename `.env.example` to `.env`.
2. Get your `TELEGRAM_TOKEN` from [@BotFather](https://t.me/BotFather).
3. Get API keys for your preferred AI providers (OpenRouter, Groq, OpenAI, Anthropic, xAI, Gemini).
4. Export your Firebase Service Account JSON and set it as `FIREBASE_CREDENTIALS` (as a flat string).
5. Deploy to Render via the provided `render.yaml` or `Dockerfile`.

## 📌 Commands
- `/start` - Welcome message
- `/latest` - Fetch all latest content
- `/youtube` - Fetch latest video
- `/medium` - Fetch latest article
- `/substack` - Fetch latest newsletter
- `/socials` - Links to all platforms
- `/ask <question>` - Ask the AI a question
- `/suggest <topic>` - Suggest a geopolitics topic

**Admin Commands:**
- `/postlatest` - Force broadcast new content to the channel
- `/ban` - Ban a user (reply to message)
- `/mute` - Mute a user (reply to message)
- `/questions` - View recent user questions
- `/poll "Q" "Op1" "Op2"` - Send a poll to the channel
- `/broadcast <msg>` - Send an announcement
- `/addfaq "keyword" "response"` - Add a custom silent FAQ
- `/stats` - View community statistics
- `/startgiveaway <Prize>` - Start a giveaway
- `/pickwinner` - Randomly pick a giveaway winner
