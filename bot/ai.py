import re
import json
import asyncio
from typing import List, Dict, Optional, Any

from bot.config import (
    logger, XAI_API_KEY, GEMINI_API_KEY, ANTHROPIC_API_KEY,
    GROQ_API_KEY, OPENAI_API_KEY, OPENROUTER_API_KEY, DEEPSEEK_API_KEY,
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

import time
import litellm

FAILED_PROVIDERS = {}

def is_valid_key(key: Optional[str]) -> bool:
    if not key:
        return False
    val = key.strip().lower()
    if val in ("", "none", "null"):
        return False
    if any(x in val for x in ("your_", "placeholder", "key_here", "token_here", "your-")):
        return False
    return True

def _detect_lang(text: str) -> str:
    bengali_chars = sum(1 for c in text if ord(c) in range(0x0980, 0x09FF))
    return "bn" if bengali_chars > 3 else "en"

def contains_arabic(text: str) -> bool:
    if not text: return False
    return any("\u0600" <= c <= "\u06FF" for c in text)

def validate_arabic_text(final_response: str, tools_output: str) -> str:
    if not contains_arabic(final_response):
        return final_response
        
    arabic_pattern = re.compile(r'[\u0600-\u06FF\s]+')
    res_blocks = arabic_pattern.findall(final_response)
    
    tool_arabic = ''.join([c for c in tools_output if "\u0600" <= c <= "\u06FF" or c.isspace()])
    tool_clean = re.sub(r'\s+', '', tool_arabic)
    
    if not tool_clean:
        return final_response + "\n\n⚠️ *Warning: The bot generated Arabic text that was not found in the verified database. Please verify.*"
        
    for block in res_blocks:
        block_clean = re.sub(r'\s+', '', block)
        if block_clean and block_clean not in tool_clean:
            return final_response + "\n\n⚠️ *Warning: The Arabic text above might contain inaccuracies or formatting differences compared to the verified source. Please verify.*"
            
    return final_response

async def summarize_history(history: list) -> str:
    if not history:
        return ""
    text = "\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in history if msg.get("role") in ["user", "assistant", "system"]])
    system_prompt = "You are a helpful assistant. Summarize the following conversation in 2-3 short sentences. Focus on the main topics discussed, user preferences, and any important context."
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": text}]
    
    models = [
        ("openrouter/openai/gpt-4o-mini", OPENROUTER_API_KEY),
        ("groq/llama-3.1-8b-instant", GROQ_API_KEY),
        ("gemini/gemini-2.0-flash", GEMINI_API_KEY),
        ("openai/gpt-4o-mini", OPENAI_API_KEY),
        ("deepseek/deepseek-chat", DEEPSEEK_API_KEY),
        ("anthropic/claude-3-haiku-20240307", ANTHROPIC_API_KEY),
        ("xai/grok-3", XAI_API_KEY)
    ]
    
    if is_valid_key(OLLAMA_BASE_URL):
        models.append((f"ollama/{OLLAMA_MODEL}", None))
        
    for model_name, api_key in models:
        if api_key and not is_valid_key(api_key):
            continue
        try:
            kwargs = {
                "model": model_name,
                "messages": messages
            }
            if api_key:
                kwargs["api_key"] = api_key
            else:
                kwargs["api_base"] = OLLAMA_BASE_URL
                
            res = await litellm.acompletion(**kwargs)
            return res.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"Error summarizing history with {model_name}: {e}")
            
    return ""

async def get_ai_response(user_message: str, user_id: Optional[int] = None, use_memory: bool = True) -> Optional[str]:
    from bot.vectordb import get_cached_response, cache_response
    from bot.database import get_user_language
    
    pref_lang = get_user_language(user_id) if user_id else None
    lang = pref_lang or _detect_lang(user_message)
    
    system_prompt = get_system_prompt(user_id, lang=lang).strip()
    
    history = []
    if use_memory and user_id:
        from bot.memory import _chat_histories, MAX_HISTORY, get_history, add_to_history
        history = get_history(user_id, max_exchanges=3)
        
    # Semantic Caching
    if not history:
        cached = get_cached_response(user_message)
        if cached:
            if use_memory and user_id:
                add_to_history(user_id, "user", user_message)
                add_to_history(user_id, "assistant", cached)
            return cached

    messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": user_message}]
            
    models = [
        ("openrouter/openai/gpt-4o-mini", OPENROUTER_API_KEY, "OpenRouter"),
        ("groq/llama-3.1-8b-instant", GROQ_API_KEY, "Groq"),
        ("gemini/gemini-2.0-flash", GEMINI_API_KEY, "Gemini"),
        ("openai/gpt-4o-mini", OPENAI_API_KEY, "OpenAI"),
        ("deepseek/deepseek-chat", DEEPSEEK_API_KEY, "DeepSeek"),
        ("anthropic/claude-3-haiku-20240307", ANTHROPIC_API_KEY, "Anthropic"),
        ("xai/grok-3", XAI_API_KEY, "xAI")
    ]
    
    if is_valid_key(OLLAMA_BASE_URL):
        models.append((f"ollama/{OLLAMA_MODEL}", "dummy_key", "Ollama"))
        
    final_res = None
    attempted_providers = []
    skipped_providers = []
    
    for model_name, api_key, provider_name in models:
        if provider_name != "Ollama" and not is_valid_key(api_key):
            skipped_providers.append(provider_name)
            continue
            
        # Circuit breaker
        if model_name in FAILED_PROVIDERS:
            fail_time, fail_count = FAILED_PROVIDERS[model_name]
            if fail_count >= 3:
                if time.time() - fail_time < 300: # 5 minutes cooldown
                    logger.warning(f"Circuit breaker active for {model_name}. Skipping.")
                    continue
                else:
                    FAILED_PROVIDERS.pop(model_name, None)
                    
        try:
            logger.info(f"Attempting inference with {model_name}")
            attempted_providers.append(provider_name)
            
            # Copy the messages list so that if this provider fails, the mutation doesn't affect subsequent providers
            provider_messages = list(messages)
            
            # Allow up to 3 tool rounds
            for _ in range(3):
                kwargs = {
                    "model": model_name,
                    "messages": provider_messages,
                    "temperature": 0.7
                }
                if api_key and provider_name != "Ollama":
                    kwargs["api_key"] = api_key
                if provider_name == "Ollama":
                    kwargs["api_base"] = OLLAMA_BASE_URL
                    kwargs["tools"] = TOOLS
                elif provider_name == "DeepSeek":
                    # DeepSeek deepseek-chat does not support function calling
                    pass
                else:
                    kwargs["tools"] = TOOLS
                    
                response = await litellm.acompletion(**kwargs)
                message = response.choices[0].message
                
                # Track tokens
                usage = response.usage
                if usage and user_id:
                    tokens = getattr(usage, 'total_tokens', 0)
                    if tokens > 0:
                        asyncio.create_task(track_token_usage(user_id, provider_name, tokens, tokens * 0.0000005))
                
                tool_calls = getattr(message, 'tool_calls', None)
                if not tool_calls:
                    final_res = message.content
                    break
                    
                provider_messages.append(message.model_dump(exclude_none=True))
                
                for tool_call in tool_calls:
                    func_name = tool_call.function.name
                    try:
                        args = json.loads(tool_call.function.arguments)
                    except Exception:
                        args = {}
                    
                    tool_result = await execute_tool(func_name, args)
                    
                    provider_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": func_name,
                        "content": str(tool_result)[:2000]
                    })
                    
            if final_res is None: # means it looped 3 times and still returned tool calls
                provider_messages.append({
                    "role": "system",
                    "content": "Self-Reflection: You have retrieved data using tools. Before answering, evaluate if this data fully and accurately answers the user's question. If it does, generate a comprehensive answer based ONLY on the retrieved data. If it doesn't, state clearly what information is missing or answer based on what is available without hallucinating."
                })
                kwargs_final = {
                    "model": model_name,
                    "messages": provider_messages,
                    "temperature": 0.7
                }
                if api_key and provider_name != "Ollama":
                    kwargs_final["api_key"] = api_key
                if provider_name == "Ollama":
                    kwargs_final["api_base"] = OLLAMA_BASE_URL
                final_response = await litellm.acompletion(**kwargs_final)
                final_res = final_response.choices[0].message.content
                
            FAILED_PROVIDERS.pop(model_name, None) # Success, reset failure
            
            if final_res:
                tool_outputs = " ".join([m.get("content", "") for m in provider_messages if m.get("role") == "tool"])
                final_res = validate_arabic_text(final_res, tool_outputs)
                
                if use_memory and user_id:
                    add_to_history(user_id, "user", user_message)
                    add_to_history(user_id, "assistant", final_res)
                    
                    history_len = len(_chat_histories.get(user_id, []))
                    if history_len > MAX_HISTORY * 2:
                        summary = await summarize_history(_chat_histories[user_id])
                        if summary:
                            _chat_histories[user_id] = [{"role": "system", "content": f"Previous conversation summary: {summary}"}]
                
                if not history:
                    cache_response(user_message, final_res)
                    
                return final_res
                
        except Exception as e:
            logger.error(f"{model_name} failed: {e}")
            fail_time, fail_count = FAILED_PROVIDERS.get(model_name, (time.time(), 0))
            FAILED_PROVIDERS[model_name] = (time.time(), fail_count + 1)
            
    # All providers failed or were skipped — log detailed diagnostics
    logger.error(
        f"AI assistant: all providers exhausted for user {user_id}. "
        f"Attempted: {[p for p in attempted_providers]}, "
        f"Skipped (no valid key): {skipped_providers}"
    )
    return None

def get_faq_response(user_message: str) -> Optional[str]:
    user_message_lower = user_message.lower()
    for keyword, response in FAQ.items():
        if keyword in user_message_lower:
            return response
    return None
