import httpx
import re
from typing import Dict, Any
from bot.config import logger, META_ACCESS_TOKEN
from bot.ai import get_ai_response

async def handle_meta_webhook_payload(payload: Dict[Any, Any]):
    """
    Parses generic Meta webhook payload (WhatsApp or Messenger/Instagram).
    Extracts the message, gets AI response, and sends the reply.
    """
    if "object" not in payload:
        return
        
    object_type = payload.get("object")
    
    if object_type == "whatsapp_business_account":
        await _process_whatsapp(payload)
    elif object_type in ["page", "instagram"]:
        await _process_messenger(payload)
    else:
        logger.info(f"Unknown Meta webhook object: {object_type}")

async def _process_whatsapp(payload: dict):
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            
            # This handles WhatsApp messages
            if "messages" in value:
                # The phone number ID (our bot's identity)
                phone_number_id = value.get("metadata", {}).get("phone_number_id")
                
                for message in value.get("messages", []):
                    sender_id = message.get("from")
                    
                    if message.get("type") == "text":
                        text = message.get("text", {}).get("body", "")
                        await _respond_whatsapp(phone_number_id, sender_id, text)
                    else:
                        logger.info(f"WhatsApp: ignoring non-text message type {message.get('type')}")

async def _process_messenger(payload: dict):
    for entry in payload.get("entry", []):
        for messaging_event in entry.get("messaging", []):
            sender_id = messaging_event.get("sender", {}).get("id")
            message = messaging_event.get("message", {})
            
            if "text" in message:
                text = message.get("text")
                await _respond_messenger(sender_id, text)

def strip_html_for_meta(html_text: str) -> str:
    """Removes HTML tags since Telegram output uses HTML but Meta prefers plain text or specific Markdown."""
    # Convert <br> or <p> to newlines
    text = re.sub(r'<br\s*/?>', '\n', html_text)
    text = re.sub(r'</p>', '\n', text)
    # Remove all other HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Decode basic HTML entities if necessary (optional)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    return text.strip()

async def _respond_whatsapp(phone_number_id: str, recipient_id: str, text: str):
    user_id = int(recipient_id) if recipient_id.isdigit() else None
    response_text = await get_ai_response(text, user_id=user_id, use_memory=True)
    if not response_text:
         response_text = "Sorry, I'm having trouble thinking right now!"
         
    if not META_ACCESS_TOKEN:
        logger.error("META_ACCESS_TOKEN not configured!")
        return

    url = f"https://graph.facebook.com/v21.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    clean_text = strip_html_for_meta(response_text)
    
    data = {
        "messaging_product": "whatsapp",
        "to": recipient_id,
        "text": {"body": clean_text}
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(url, headers=headers, json=data)
            if res.status_code != 200:
                logger.error(f"Failed to send WhatsApp message: {res.text}")
    except Exception as e:
        logger.error(f"Exception sending WhatsApp message: {e}")

async def _respond_messenger(recipient_id: str, text: str):
    user_id = int(recipient_id) if recipient_id.isdigit() else None
    response_text = await get_ai_response(text, user_id=user_id, use_memory=True)
    if not response_text:
         response_text = "Sorry, I'm having trouble thinking right now!"
         
    if not META_ACCESS_TOKEN:
        logger.error("META_ACCESS_TOKEN not configured!")
        return

    url = f"https://graph.facebook.com/v21.0/me/messages"
    headers = {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    
    clean_text = strip_html_for_meta(response_text)
    
    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": clean_text}
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(url, headers=headers, json=data)
            if res.status_code != 200:
                logger.error(f"Failed to send Messenger message: {res.text}")
    except Exception as e:
        logger.error(f"Exception sending Messenger message: {e}")
