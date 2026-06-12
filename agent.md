# Agentic RAG Architecture 🧠

This document details the **Agentic Retrieval-Augmented Generation (RAG)** system powering the Bearded Bangali Bot.

## Overview
Instead of giving generic answers, the bot acts as an intelligent "Agent" that can autonomously decide when to use Tools (Functions) to search a local knowledge base before answering.

## 1. The Knowledge Base (`knowledge_base.json`)
A static JSON file acting as a mock vector database. It contains past posts, gear details, and opinions. 
*Format:* `[{"platform": "YouTube", "title": "...", "content": "...", "url": "..."}]`

## 2. The Tool (`search_knowledge_base`)
The AI models are provided with a tool definition `search_knowledge_base`. 
When a user asks: *"What camera do you use?"*, the AI:
1. Recognizes it doesn't know the answer off the top of its head.
2. Halts generation and calls the `search_knowledge_base` tool with the query `camera`.
3. The Python backend searches `knowledge_base.json` and returns the exact camera model.
4. The AI reads this return value and generates a fluent, personalized answer!

## 3. The Ultimate AI Router (`get_ai_response`)
Because AI APIs can experience downtime or run out of credits, the bot uses a cascading router.
It attempts to execute the Agentic RAG flow on the following models in order:
1. **OpenRouter** (`openai/gpt-4o-mini`)
2. **Groq** (`llama-3.1-8b-instant`) - *Tool calling disabled for raw speed*
3. **OpenAI** (`gpt-4o-mini`)
4. **Anthropic** (`claude-3-haiku-20240307`) - *System prompt stringified*
5. **xAI** (`grok-beta`)
6. **Google Gemini** (`gemini-1.5-flash`) - *System prompt stringified*

If an API throws an exception (e.g., `httpx.HTTPError`), the router silently catches it and attempts the exact same prompt on the next provider.

## 4. Smart Filtering
To save tokens and API costs:
- **Direct Messages (DMs):** The AI answers every single message.
- **Group Chats:** The AI stays silent to save tokens. It only wakes up if a user explicitly tags `@bot_username` or replies directly to a message sent by the bot. Otherwise, it falls back to a silent Regex/FAQ check.
