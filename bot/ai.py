import json
import httpx
from bot.config import (
    logger, XAI_API_KEY, GEMINI_API_KEY, ANTHROPIC_API_KEY,
    GROQ_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY,
    YOUTUBE_LINK, MEDIUM_LINK, INSTAGRAM_LINK, TWITTER_LINK, FACEBOOK_LINK
)
from bot.database import FAQ, db, track_activity
from bot.search import search_pipeline, search_duas
from bot.rss import get_youtube_posts, get_medium_posts, get_substack_posts
from bot.memory import get_history, add_to_history
from bot.vectordb import get_document_count

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": "Searches the creator's past posts (YouTube, Medium, Instagram) to answer specific questions about gear, opinions, setup, or past content using semantic search.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query (e.g. 'camera setup', 'editing software', 'productivity tips')"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_faq_answer",
            "description": "Looks up a quick answer from the frequently asked questions database. Use this for common questions about the creator.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The user's question to match against FAQ keywords"
                    }
                },
                "required": ["question"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_content",
            "description": "Fetches the latest posts from a specific content platform.",
            "parameters": {
                "type": "object",
                "properties": {
                    "platform": {
                        "type": "string",
                        "enum": ["youtube", "medium", "substack"],
                        "description": "The platform to fetch content from"
                    }
                },
                "required": ["platform"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_dua",
            "description": "Searches the Hisnul Muslim dua (Islamic supplication) database. Use this when users ask for specific duas, Islamic prayers, or supplications for various situations (sleeping, travel, food, sickness, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query for the dua (e.g. 'dua for sleeping', 'prayer for travel', 'supplication for food')"
                    }
                },
                "required": ["query"]
            }
        }
    }
]

def get_system_prompt(user_id: int = None) -> str:
    faq_context = json.dumps(FAQ, indent=2)
    doc_count = get_document_count()
    return f"""
You are the official Telegram assistant for Bearded Bangali, a tech and lifestyle content creator.
Your job is to answer questions enthusiastically and politely using the tools available to you.

Rules:
- If the user greets you with "Salam" or any variation, you MUST reply with "Walikumus Salam".
- Use the search_knowledge_base tool when users ask about specific gear, setups, opinions, or past content.
- Use the search_dua tool when users ask for Islamic duas, supplications, prayers, or Hisnul Muslim content. Always include the Arabic, transliteration, translation, and source when answering duas.
- Use the get_faq_answer tool for common quick questions.
- Use the get_recent_content tool when users ask for the latest videos, articles, or newsletters.
- Always maintain a polite, respectful tone.
- Keep answers concise (1-3 sentences max) unless the user asks for details.
- Do not invent facts about the creator. Use tools to find real information.

Knowledge Base Stats:
- {doc_count} documents indexed in the vector database
- {len(FAQ)} FAQ entries available

Current FAQs/Facts:
{faq_context}

Social Media Links:
- YouTube: {YOUTUBE_LINK}
- Medium: {MEDIUM_LINK}
- Instagram: {INSTAGRAM_LINK}
- X/Twitter: {TWITTER_LINK}
- Facebook: {FACEBOOK_LINK}
"""

async def execute_tool(tool_name: str, arguments: dict) -> str:
    if tool_name == "search_knowledge_base":
        query = arguments.get("query", "")
        if not query:
            return "No query provided."
        return search_pipeline(query)
    elif tool_name == "search_dua":
        query = arguments.get("query", "")
        if not query:
            return "No query provided."
        return search_duas(query)
    elif tool_name == "get_faq_answer":
        question = arguments.get("question", "").lower()
        for keyword, response in FAQ.items():
            if keyword in question:
                return f"FAQ Match: {response}"
        return "No FAQ match found for this question."
    elif tool_name == "get_recent_content":
        platform = arguments.get("platform", "").lower()
        if platform == "youtube":
            msg, btn, link = await get_youtube_posts(limit=3)
        elif platform == "medium":
            msg, btn, link = await get_medium_posts(limit=3)
        elif platform == "substack":
            msg, btn, link = await get_substack_posts(limit=3)
        else:
            return f"Unknown platform: {platform}"
        return msg or f"No recent {platform} content found."
    return f"Unknown tool: {tool_name}"

async def call_agent_with_tools(api_key: str, base_url: str, model: str, messages: list, max_tool_rounds: int = 3) -> str:
    if not api_key:
        return None
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    if "openrouter.ai" in base_url:
        headers["HTTP-Referer"] = "https://t.me/BeardedBangaliBot"
        headers["X-Title"] = "Bearded Bangali Bot"
    payload = {
        "messages": messages,
        "model": model,
        "temperature": 0.7,
        "tools": TOOLS,
        "tool_choice": "auto"
    }
    for round_num in range(max_tool_rounds):
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(base_url, headers=headers, json=payload)
                response.raise_for_status()
                message = response.json()["choices"][0]["message"]
                if not message.get("tool_calls"):
                    return message.get("content", "")
                messages.append({
                    "role": "assistant",
                    "content": message.get("content") or None,
                    "tool_calls": message["tool_calls"]
                })
                for tool_call in message["tool_calls"]:
                    func_name = tool_call["function"]["name"]
                    try:
                        args = json.loads(tool_call["function"]["arguments"])
                    except json.JSONDecodeError:
                        args = {}
                    tool_result = await execute_tool(func_name, args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": str(tool_result)[:2000]
                    })
                payload["messages"] = messages
        except Exception as e:
            logger.error(f"Error in agent loop ({base_url}, round {round_num}): {e}")
            return None
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            payload.pop("tools", None)
            payload.pop("tool_choice", None)
            final_response = await client.post(base_url, headers=headers, json=payload)
            final_response.raise_for_status()
            return final_response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"Error in final agent call ({base_url}): {e}")
        return None

async def call_openai_compatible(api_key: str, base_url: str, model: str, user_message: str, use_tools: bool = True) -> str:
    if not api_key:
        return None
    messages = [
        {"role": "system", "content": get_system_prompt().strip()},
        {"role": "user", "content": user_message}
    ]
    if use_tools:
        return await call_agent_with_tools(api_key, base_url, model, messages)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    if "openrouter.ai" in base_url:
        headers["HTTP-Referer"] = "https://t.me/BeardedBangaliBot"
        headers["X-Title"] = "Bearded Bangali Bot"
    payload = {
        "messages": messages,
        "model": model,
        "temperature": 0.7
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(base_url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"Error calling {base_url}: {e}")
        return None

async def get_anthropic_response(user_message: str) -> str:
    if not ANTHROPIC_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": "claude-3-haiku-20240307",
                    "max_tokens": 300,
                    "system": get_system_prompt().strip(),
                    "messages": [{"role": "user", "content": user_message}]
                }
            )
            response.raise_for_status()
            return response.json()["content"][0]["text"]
    except Exception as e:
        logger.error(f"Error calling Anthropic API: {e}")
        return None

async def get_gemini_response(user_message: str) -> str:
    if not GEMINI_API_KEY:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "system_instruction": {"parts": {"text": get_system_prompt().strip()}},
        "contents": [{"role": "user", "parts": [{"text": user_message}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 300}
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        logger.error(f"Error calling Gemini API: {e}")
        return None

async def get_ai_response(user_message: str, user_id: int = None, use_memory: bool = True) -> str:
    if use_memory and user_id:
        history = get_history(user_id, max_exchanges=3)
        if history:
            context_messages = [{"role": "system", "content": get_system_prompt(user_id).strip()}]
            for msg in history:
                context_messages.append(msg)
            context_messages.append({"role": "user", "content": user_message})
            messages = context_messages
        else:
            messages = None
    else:
        messages = None
    provider_chain = [
        ("OpenRouter", lambda: call_agent_with_tools(
            OPENROUTER_API_KEY,
            "https://openrouter.ai/api/v1/chat/completions",
            "openai/gpt-4o-mini",
            messages or [{"role": "system", "content": get_system_prompt(user_id).strip()}, {"role": "user", "content": user_message}]
        ) if OPENROUTER_API_KEY else None),
        ("Groq", lambda: call_openai_compatible(GROQ_API_KEY, "https://api.groq.com/openai/v1/chat/completions", "llama-3.1-8b-instant", user_message, use_tools=False)),
        ("OpenAI", lambda: call_agent_with_tools(
            OPENAI_API_KEY,
            "https://api.openai.com/v1/chat/completions",
            "gpt-4o-mini",
            messages or [{"role": "system", "content": get_system_prompt(user_id).strip()}, {"role": "user", "content": user_message}]
        ) if OPENAI_API_KEY else None),
        ("Anthropic", lambda: get_anthropic_response(user_message)),
        ("xAI", lambda: call_openai_compatible(XAI_API_KEY, "https://api.x.ai/v1/chat/completions", "grok-beta", user_message)),
        ("Gemini", lambda: get_gemini_response(user_message))
    ]
    for name, fn in provider_chain:
        try:
            res = await fn()
            if res:
                if use_memory and user_id:
                    add_to_history(user_id, "user", user_message)
                    add_to_history(user_id, "assistant", res)
                return res
            logger.info(f"{name} failed or returned empty. Trying next...")
        except Exception as e:
            logger.error(f"{name} errored: {e}")
    return None

def get_faq_response(user_message: str) -> str:
    user_message_lower = user_message.lower()
    if any(word in user_message_lower for word in ["salam", "assalam", "salam alaikum"]):
        return "Walikumus Salam! 😊\nHow can I help you today? Type /help to see what I can do."
    for keyword, response in FAQ.items():
        if keyword in user_message_lower:
            return response
    return None
