import json
import httpx
from bot.config import logger, XAI_API_KEY, YOUTUBE_LINK, MEDIUM_LINK, INSTAGRAM_LINK, TWITTER_LINK, FACEBOOK_LINK
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
        # Simple scoring based on term presence
        score = sum(1 for word in query_lower.split() if word in post["content"].lower() or word in post["title"].lower())
        if score > 0:
            results.append((score, post))
            
    # Sort by score descending and take top 2
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

async def get_grok_response(user_message: str) -> str:
    """Get dynamic response from xAI's Grok API with Tool Calling (Agentic RAG)"""
    if not XAI_API_KEY:
        return None
        
    system_prompt = f"""
You are the official Telegram assistant for Bearded Bangali, a tech and lifestyle content creator.
Your job is to answer questions enthusiastically and politely using the following context.
If the user greets you with "Salam" or any variation, you MUST reply with "Walikumus Salam". Otherwise, always maintain a polite, respectful tone.
Do not invent facts about him. Keep answers concise (1-3 sentences max).

If a user asks a specific question about his past content, gear, or opinions, YOU MUST USE the `search_knowledge_base` tool to retrieve his actual past posts before answering.

Current known FAQs/Facts:
{json.dumps(FAQ, indent=2)}

Social Media Links:
- YouTube: {YOUTUBE_LINK}
- Medium: {MEDIUM_LINK}
- Instagram: {INSTAGRAM_LINK}
- X/Twitter: {TWITTER_LINK}
- Facebook: {FACEBOOK_LINK}
"""
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_knowledge_base",
                "description": "Searches the creator's past YouTube, Medium, and Instagram posts to answer specific questions about their gear, opinions, or past content.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query (e.g. 'camera setup', 'editing software', 'final cut')"
                        }
                    },
                    "required": ["query"]
                }
            }
        }
    ]

    messages = [
        {"role": "system", "content": system_prompt.strip()},
        {"role": "user", "content": user_message}
    ]

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # First Call to Grok
            response = await client.post(
                "https://api.x.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {XAI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "messages": messages,
                    "model": "grok-beta",
                    "tools": tools,
                    "tool_choice": "auto",
                    "stream": False,
                    "temperature": 0.7
                }
            )
            response.raise_for_status()
            data = response.json()
            message = data["choices"][0]["message"]
            
            # Check if Grok wants to use a tool
            if message.get("tool_calls"):
                messages.append(message) # Append the assistant's tool call message
                
                for tool_call in message["tool_calls"]:
                    if tool_call["function"]["name"] == "search_knowledge_base":
                        args = json.loads(tool_call["function"]["arguments"])
                        search_result = search_knowledge_base(args["query"])
                        
                        # Provide the tool result back to Grok
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": search_result
                        })
                
                # Second Call to Grok to get the final answer
                final_response = await client.post(
                    "https://api.x.ai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {XAI_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "messages": messages,
                        "model": "grok-beta",
                        "stream": False,
                        "temperature": 0.7
                    }
                )
                final_response.raise_for_status()
                final_data = final_response.json()
                return final_data["choices"][0]["message"]["content"]
            
            # If no tool was called, return the direct response
            return message.get("content")
            
    except Exception as e:
        logger.error(f"Error calling Grok API: {e}")
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
