import json
import httpx
from bot.config import (
    logger, XAI_API_KEY, GEMINI_API_KEY, ANTHROPIC_API_KEY, 
    GROQ_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY,
    YOUTUBE_LINK, MEDIUM_LINK, INSTAGRAM_LINK, TWITTER_LINK, FACEBOOK_LINK
)
from bot.database import FAQ

# Load Mock Knowledge Base for RAG
try:
    with open("knowledge_base.json", "r", encoding="utf-8") as f:
        KNOWLEDGE_BASE = json.load(f)
except Exception as e:
    logger.error(f"Error loading knowledge base: {e}")
    KNOWLEDGE_BASE = []

def search_knowledge_base(query: str) -> str:
    """Mock vector search using basic keyword matching"""
    query_lower = query.lower()
    results = []
    for post in KNOWLEDGE_BASE:
        score = sum(1 for word in query_lower.split() if word in post["content"].lower() or word in post["title"].lower())
        if score > 0:
            results.append((score, post))
            
    results.sort(key=lambda x: x[0], reverse=True)
    top_results = results[:2]
    
    if not top_results:
        return "No relevant past posts found for this query."
        
    formatted_results = []
    for _, post in top_results:
        formatted_results.append(
            f"Platform: {post['platform']}\nTitle: {post['title']}\nContent: {post['content']}\nLink: {post['url']}"
        )
    return "\n\n---\n\n".join(formatted_results)

def get_system_prompt() -> str:
    return f"""
You are the official Telegram assistant for Bearded Bangali, a tech and lifestyle content creator.
Your job is to answer questions enthusiastically and politely using the following context.
If the user greets you with "Salam" or any variation, you MUST reply with "Walikumus Salam". Otherwise, always maintain a polite, respectful tone.
Do not invent facts about him. Keep answers concise (1-3 sentences max).

Current known FAQs/Facts:
{json.dumps(FAQ, indent=2)}

Social Media Links:
- YouTube: {YOUTUBE_LINK}
- Medium: {MEDIUM_LINK}
- Instagram: {INSTAGRAM_LINK}
- X/Twitter: {TWITTER_LINK}
- Facebook: {FACEBOOK_LINK}
"""

async def call_openai_compatible(api_key: str, base_url: str, model: str, user_message: str, use_tools: bool = True) -> str:
    """Unified handler for OpenRouter, Groq, OpenAI, and xAI using OpenAI format"""
    if not api_key:
        return None
        
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_knowledge_base",
                "description": "Searches the creator's past YouTube, Medium, and Instagram posts to answer specific questions about their gear, opinions, or past content.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The search query (e.g. 'camera setup', 'editing software')"}
                    },
                    "required": ["query"]
                }
            }
        }
    ]

    messages = [
        {"role": "system", "content": get_system_prompt().strip()},
        {"role": "user", "content": user_message}
    ]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # OpenRouter specific headers
    if "openrouter.ai" in base_url:
        headers["HTTP-Referer"] = "https://t.me/BeardedBangaliBot"
        headers["X-Title"] = "Bearded Bangali Bot"

    payload = {
        "messages": messages,
        "model": model,
        "temperature": 0.7
    }
    
    if use_tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # First Call
            response = await client.post(base_url, headers=headers, json=payload)
            response.raise_for_status()
            message = response.json()["choices"][0]["message"]
            
            # Check if it wants to use a tool
            if message.get("tool_calls"):
                messages.append(message)
                for tool_call in message["tool_calls"]:
                    if tool_call["function"]["name"] == "search_knowledge_base":
                        args = json.loads(tool_call["function"]["arguments"])
                        search_result = search_knowledge_base(args["query"])
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": search_result
                        })
                
                # Second Call
                payload["messages"] = messages
                payload.pop("tools", None)
                payload.pop("tool_choice", None)
                
                final_response = await client.post(base_url, headers=headers, json=payload)
                final_response.raise_for_status()
                return final_response.json()["choices"][0]["message"]["content"]
            
            return message.get("content")
            
    except Exception as e:
        logger.error(f"Error calling {base_url}: {e}")
        return None

async def get_anthropic_response(user_message: str) -> str:
    """Fallback to Anthropic Claude"""
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
                    "max_tokens": 200,
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
    """Fallback to Google Gemini API"""
    if not GEMINI_API_KEY:
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    payload = {
        "system_instruction": {"parts": {"text": get_system_prompt().strip()}},
        "contents": [{"role": "user", "parts": [{"text": user_message}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 200}
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        logger.error(f"Error calling Gemini API: {e}")
        return None

async def get_ai_response(user_message: str) -> str:
    """Ultimate Router: Cascades through 6 AI providers!"""
    
    # 1. OpenRouter (Primary)
    if OPENROUTER_API_KEY:
        res = await call_openai_compatible(OPENROUTER_API_KEY, "https://openrouter.ai/api/v1/chat/completions", "openai/gpt-4o-mini", user_message)
        if res: return res
        logger.info("OpenRouter failed. Falling back to Groq...")

    # 2. Groq (Fast Fallback)
    if GROQ_API_KEY:
        res = await call_openai_compatible(GROQ_API_KEY, "https://api.groq.com/openai/v1/chat/completions", "llama-3.1-8b-instant", user_message, use_tools=False)
        if res: return res
        logger.info("Groq failed. Falling back to OpenAI...")

    # 3. OpenAI (Solid Fallback)
    if OPENAI_API_KEY:
        res = await call_openai_compatible(OPENAI_API_KEY, "https://api.openai.com/v1/chat/completions", "gpt-4o-mini", user_message)
        if res: return res
        logger.info("OpenAI failed. Falling back to Anthropic...")

    # 4. Anthropic (Haiku Fallback)
    if ANTHROPIC_API_KEY:
        res = await get_anthropic_response(user_message)
        if res: return res
        logger.info("Anthropic failed. Falling back to xAI...")

    # 5. xAI (Grok Fallback)
    if XAI_API_KEY:
        res = await call_openai_compatible(XAI_API_KEY, "https://api.x.ai/v1/chat/completions", "grok-beta", user_message)
        if res: return res
        logger.info("xAI failed. Falling back to Gemini...")

    # 6. Gemini (Final Fallback)
    if GEMINI_API_KEY:
        res = await get_gemini_response(user_message)
        if res: return res
        logger.info("Gemini failed. No AI models available!")

    return None

def get_faq_response(user_message: str) -> str:
    """Match user question to FAQ"""
    user_message_lower = user_message.lower()
    
    if any(word in user_message_lower for word in ["salam", "assalam", "salam alaikum"]):
        return "Walikumus Salam! 😊\nHow can I help you today? Type /help to see what I can do."
        
    for keyword, response in FAQ.items():
        if keyword in user_message_lower:
            return response
    
    return None
