import json
import httpx
import asyncio
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any

from bot.config import (
    logger, XAI_API_KEY, GEMINI_API_KEY, ANTHROPIC_API_KEY,
    GROQ_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY,
    OLLAMA_BASE_URL, OLLAMA_MODEL,
    YOUTUBE_LINK, MEDIUM_LINK, INSTAGRAM_LINK, TWITTER_LINK, FACEBOOK_LINK
)
from bot.database import FAQ, track_token_usage
from bot.search import search_pipeline, search_duas, search_quran
from bot.rss import get_youtube_posts, get_medium_posts, get_substack_posts, extract_article_text
from bot.memory import get_history, add_to_history
from bot.vectordb import get_document_count

LANG_PROMPTS: Dict[str, str] = {
    "en": "You are the official Telegram assistant for Bearded Bangali, a tech and lifestyle content creator. Answer in English.",
    "bn": "আপনি হলেন Bearded Bangali-এর অফিসিয়াল টেলিগ্রাম অ্যাসিস্ট্যান্ট। দয়া করে বাংলায় উত্তর দিন।",
}

TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "browse_web",
            "description": "Fetches the full text content from a given URL. Use this when users ask about current events, recent news, or any topic that requires fetching external web content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch and extract text content from"
                    }
                },
                "required": ["url"]
            }
        }
    },
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
    },
    {
        "type": "function",
        "function": {
            "name": "search_quran",
            "description": "Searches the Quran (all 114 surahs, 6236 verses) with Arabic text, word-by-word meanings, and Sahih International translation. Use this when users ask about specific Quran verses, surahs, or topics in the Quran.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query (e.g. 'ayat al-kursi', 'surah yasin', 'verse about mercy', 'quran on patience')"
                    }
                },
                "required": ["query"]
            }
        }
    }
]

def get_system_prompt(user_id: Optional[int] = None, lang: str = "en") -> str:
    faq_context = json.dumps(FAQ, indent=2)
    doc_count = get_document_count()
    base = f"""
Rules:
- If the user greets you with "Salam" or any variation, you MUST reply with "Walikumus Salam".
- Use the search_knowledge_base tool when users ask about specific gear, setups, opinions, or past content.
- Use the search_dua tool when users ask for Islamic duas, supplications, prayers, or Hisnul Muslim content. Always include the Arabic, transliteration, translation, and source when answering duas.
- Use the search_quran tool when users ask about Quran verses, surahs, or Islamic topics from the Quran. Always include the Arabic and translation when quoting verses.
- Use the get_faq_answer tool for common quick questions.
- Use the get_recent_content tool when users ask for the latest videos, articles, or newsletters.
- Use the browse_web tool when users ask about current events, recent news, or any topic requiring external web content.
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
    lang_prompt = LANG_PROMPTS.get(lang, LANG_PROMPTS["en"])
    return lang_prompt + "\n" + base

async def execute_tool(tool_name: str, arguments: dict) -> str:
    if tool_name == "browse_web":
        url = arguments.get("url", "")
        if not url:
            return "No URL provided."
        return await extract_article_text(url)
    elif tool_name == "search_knowledge_base":
        query = arguments.get("query", "")
        if not query:
            return "No query provided."
        return search_pipeline(query)
    elif tool_name == "search_dua":
        query = arguments.get("query", "")
        if not query:
            return "No query provided."
        return search_duas(query)
    elif tool_name == "search_quran":
        query = arguments.get("query", "")
        if not query:
            return "No query provided."
        return search_quran(query)
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

async def call_agent_with_tools(api_key: str, base_url: str, model: str, messages: list, max_tool_rounds: int = 3, user_id: Optional[int] = None, provider: str = "AI") -> Optional[str]:
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
                data = response.json()
                message = data["choices"][0]["message"]
                
                usage = data.get("usage", {})
                tokens = usage.get("total_tokens", 0)
                if user_id and tokens > 0:
                    asyncio.create_task(track_token_usage(user_id, provider, tokens, tokens * 0.0000005))
                
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
            
            # Self-RAG Reflection Step
            if any(m.get("role") == "tool" for m in messages):
                reflection_msg = {
                    "role": "system",
                    "content": "Self-Reflection: You have retrieved data using tools. Before answering, evaluate if this data fully and accurately answers the user's question. If it does, generate a comprehensive answer based ONLY on the retrieved data. If it doesn't, state clearly what information is missing or answer based on what is available without hallucinating."
                }
                messages.append(reflection_msg)
                payload["messages"] = messages
                
            final_response = await client.post(base_url, headers=headers, json=payload)
            final_response.raise_for_status()
            final_data = final_response.json()
            
            usage = final_data.get("usage", {})
            tokens = usage.get("total_tokens", 0)
            if user_id and tokens > 0:
                asyncio.create_task(track_token_usage(user_id, provider, tokens, tokens * 0.0000005))
                
            return final_data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"Error in final agent call ({base_url}): {e}")
        return None

async def call_openai_compatible(api_key: str, base_url: str, model: str, user_message: str, system_prompt: str, use_tools: bool = True, user_id: Optional[int] = None, provider: str = "AI", messages: Optional[List[Dict[str, Any]]] = None) -> Optional[str]:
    msgs = messages or [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]
    if use_tools:
        return await call_agent_with_tools(api_key, base_url, model, msgs, user_id=user_id, provider=provider)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    if "openrouter.ai" in base_url:
        headers["HTTP-Referer"] = "https://t.me/BeardedBangaliBot"
        headers["X-Title"] = "Bearded Bangali Bot"
    payload = {
        "messages": msgs,
        "model": model,
        "temperature": 0.7
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(base_url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            
            usage = data.get("usage", {})
            tokens = usage.get("total_tokens", 0)
            if user_id and tokens > 0:
                asyncio.create_task(track_token_usage(user_id, provider, tokens, tokens * 0.0000005))
                
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"Error calling {base_url}: {e}")
        return None

# ============ AI STRATEGY PROVIDERS ============

class BaseAIProvider(ABC):
    """Abstract Strategy interface defining standard API structure for cascading AI nodes."""
    
    def __init__(self, name: str, api_key: Optional[str], model: str):
        self.name = name
        self.api_key = api_key
        self.model = model

    @abstractmethod
    async def generate_response(self, user_message: str, system_prompt: str, messages: Optional[List[Dict[str, Any]]] = None, user_id: Optional[int] = None) -> Optional[str]:
        """Core execution pipeline representing LLM call."""
        pass

class OpenRouterAIProvider(BaseAIProvider):
    def __init__(self) -> None:
        super().__init__("OpenRouter", OPENROUTER_API_KEY, "openai/gpt-4o-mini")
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"

    async def generate_response(self, user_message: str, system_prompt: str, messages: Optional[List[Dict[str, Any]]] = None, user_id: Optional[int] = None) -> Optional[str]:
        if not self.api_key:
            return None
        msgs = messages or [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}]
        return await call_agent_with_tools(self.api_key, self.base_url, self.model, msgs, user_id=user_id, provider=self.name)

class OpenAIProvider(BaseAIProvider):
    def __init__(self) -> None:
        super().__init__("OpenAI", OPENAI_API_KEY, "gpt-4o-mini")
        self.base_url = "https://api.openai.com/v1/chat/completions"

    async def generate_response(self, user_message: str, system_prompt: str, messages: Optional[List[Dict[str, Any]]] = None, user_id: Optional[int] = None) -> Optional[str]:
        if not self.api_key:
            return None
        msgs = messages or [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}]
        return await call_agent_with_tools(self.api_key, self.base_url, self.model, msgs, user_id=user_id, provider=self.name)

class GroqAIProvider(BaseAIProvider):
    def __init__(self) -> None:
        super().__init__("Groq", GROQ_API_KEY, "llama-3.1-8b-instant")
        self.base_url = "https://api.groq.com/openai/v1/chat/completions"

    async def generate_response(self, user_message: str, system_prompt: str, messages: Optional[List[Dict[str, Any]]] = None, user_id: Optional[int] = None) -> Optional[str]:
        if not self.api_key:
            return None
        return await call_openai_compatible(self.api_key, self.base_url, self.model, user_message, system_prompt, use_tools=False, user_id=user_id, provider=self.name, messages=messages)

class xAIProvider(BaseAIProvider):
    def __init__(self) -> None:
        super().__init__("xAI", XAI_API_KEY, "grok-beta")
        self.base_url = "https://api.x.ai/v1/chat/completions"

    async def generate_response(self, user_message: str, system_prompt: str, messages: Optional[List[Dict[str, Any]]] = None, user_id: Optional[int] = None) -> Optional[str]:
        if not self.api_key:
            return None
        return await call_openai_compatible(self.api_key, self.base_url, self.model, user_message, system_prompt, use_tools=True, user_id=user_id, provider=self.name, messages=messages)

class AnthropicAIProvider(BaseAIProvider):
    def __init__(self) -> None:
        super().__init__("Anthropic", ANTHROPIC_API_KEY, "claude-3-haiku-20240307")

    async def generate_response(self, user_message: str, system_prompt: str, messages: Optional[List[Dict[str, Any]]] = None, user_id: Optional[int] = None) -> Optional[str]:
        if not self.api_key:
            return None
        anthropic_messages = []
        if messages:
            for m in messages:
                if m["role"] in ["user", "assistant"]:
                    anthropic_messages.append({"role": m["role"], "content": m["content"]})
        if not anthropic_messages:
            anthropic_messages = [{"role": "user", "content": user_message}]
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "max_tokens": 300,
                        "system": system_prompt,
                        "messages": anthropic_messages
                    }
                )
                response.raise_for_status()
                data = response.json()
                usage = data.get("usage", {})
                tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                if user_id and tokens > 0:
                    asyncio.create_task(track_token_usage(user_id, self.name, tokens, tokens * 0.000001))
                return data["content"][0]["text"]
        except Exception as e:
            logger.error(f"Error calling Anthropic API: {e}")
            return None

class GeminiAIProvider(BaseAIProvider):
    def __init__(self) -> None:
        super().__init__("Gemini", GEMINI_API_KEY, "gemini-1.5-flash")

    async def generate_response(self, user_message: str, system_prompt: str, messages: Optional[List[Dict[str, Any]]] = None, user_id: Optional[int] = None) -> Optional[str]:
        if not self.api_key:
            return None
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        gemini_contents = []
        if messages:
            for m in messages:
                if m["role"] in ["user", "assistant"]:
                    role = "user" if m["role"] == "user" else "model"
                    gemini_contents.append({"role": role, "parts": [{"text": m["content"]}]})
        if not gemini_contents:
            gemini_contents = [{"role": "user", "parts": [{"text": user_message}]}]
        payload = {
            "system_instruction": {"parts": {"text": system_prompt}},
            "contents": gemini_contents,
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 300}
        }
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                usage = data.get("usageMetadata", {})
                tokens = usage.get("totalTokenCount", 0)
                if user_id and tokens > 0:
                    asyncio.create_task(track_token_usage(user_id, self.name, tokens, tokens * 0.0000001))
                return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
            return None

class OllamaAIProvider(BaseAIProvider):
    def __init__(self) -> None:
        super().__init__("Ollama", "ollama_placeholder", OLLAMA_MODEL)
        self.base_url = OLLAMA_BASE_URL.rstrip("/")

    async def generate_response(self, user_message: str, system_prompt: str, messages: Optional[List[Dict[str, Any]]] = None, user_id: Optional[int] = None) -> Optional[str]:
        if not self.base_url:
            return None
        ollama_messages = messages or [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                payload = {
                    "model": self.model,
                    "messages": ollama_messages,
                    "stream": False,
                    "options": {"temperature": 0.7}
                }
                endpoint = f"{self.base_url}/v1/chat/completions" if "v1" not in self.base_url else f"{self.base_url}/chat/completions"
                response = await client.post(endpoint, json=payload)
                response.raise_for_status()
                data = response.json()
                usage = data.get("usage", {})
                tokens = usage.get("total_tokens", 0)
                if not tokens:
                    tokens = data.get("prompt_eval_count", 0) + data.get("eval_count", 0)
                if user_id and tokens > 0:
                    asyncio.create_task(track_token_usage(user_id, self.name, tokens, 0.0))
                return data.get("message", {}).get("content") or data.get("response", "")
        except Exception as e:
            logger.warning(f"Ollama unavailable ({self.base_url}): {e}")
            return None

# ============ EXPORTED ENGINE ACTIONS ============

def _detect_lang(text: str) -> str:
    bengali_chars = sum(1 for c in text if ord(c) in range(0x0980, 0x09FF))
    return "bn" if bengali_chars > 3 else "en"

# Initialize strategy providers as module-level constants
ALL_PROVIDERS: List[BaseAIProvider] = [
    OpenRouterAIProvider(),
    GroqAIProvider(),
    OpenAIProvider(),
    AnthropicAIProvider(),
    xAIProvider(),
    GeminiAIProvider(),
    OllamaAIProvider()
]

ACTIVE_PROVIDERS: List[BaseAIProvider] = [
    p for p in ALL_PROVIDERS if p.api_key or (p.name == "Ollama" and p.base_url)
]

async def summarize_history(history: list) -> str:
    if not history or not ACTIVE_PROVIDERS:
        return ""
    provider = ACTIVE_PROVIDERS[0]
    
    text = "\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in history if msg.get("role") in ["user", "assistant", "system"]])
    system_prompt = "You are a helpful assistant. Summarize the following conversation in 2-3 short sentences. Focus on the main topics discussed, user preferences, and any important context."
    
    try:
        res = await provider.generate_response(text, system_prompt, messages=None, user_id=None)
        return res or ""
    except Exception as e:
        logger.error(f"Error summarizing history: {e}")
        return ""

async def get_ai_response(user_message: str, user_id: Optional[int] = None, use_memory: bool = True) -> Optional[str]:
    from bot.vectordb import get_cached_response, cache_response
    lang = _detect_lang(user_message)
    system_prompt = get_system_prompt(user_id, lang=lang).strip()
    messages = None
    
    history = []
    if use_memory and user_id:
        history = get_history(user_id, max_exchanges=3)
        
    # Semantic Caching
    if not history:
        cached = get_cached_response(user_message)
        if cached:
            if use_memory and user_id:
                add_to_history(user_id, "user", user_message)
                add_to_history(user_id, "assistant", cached)
            return cached

    if history:
        messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": user_message}]
            
    for provider in ACTIVE_PROVIDERS:
        try:
            res = await provider.generate_response(user_message, system_prompt, messages, user_id)
            if res:
                if use_memory and user_id:
                    from bot.memory import chat_histories, MAX_HISTORY
                    add_to_history(user_id, "user", user_message)
                    add_to_history(user_id, "assistant", res)
                    
                    history_len = len(chat_histories.get(user_id, []))
                    if history_len > MAX_HISTORY * 2:
                        summary = await summarize_history(chat_histories[user_id])
                        if summary:
                            chat_histories[user_id] = [{"role": "system", "content": f"Previous conversation summary: {summary}"}]
                
                # Cache the response for standalone queries
                if not history:
                    cache_response(user_message, res)
                    
                return res
            logger.info(f"{provider.name} failed or returned empty. Trying next...")
        except Exception as e:
            logger.error(f"{provider.name} strategy error: {e}")
            
    return None

def get_faq_response(user_message: str) -> Optional[str]:
    user_message_lower = user_message.lower()
    if any(word in user_message_lower for word in ["salam", "assalam", "salam alaikum"]):
        return "Walikumus Salam! 😊\nHow can I help you today? Type /help to see what I can do."
    for keyword, response in FAQ.items():
        if keyword in user_message_lower:
            return response
    return None
