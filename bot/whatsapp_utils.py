"""
WhatsApp API utility functions for the Bearded Bangali bot.
Provides helpers for sending text messages, interactive lists, reply buttons, and media
via the Meta Cloud API (Graph v21.0+).
"""
import re
import httpx

from bot.config import logger, META_ACCESS_TOKEN

# ── Cleanup helpers ─────────────────────────────────────────────

def strip_html(text: str) -> str:
    """Strip HTML tags and decode entities for WhatsApp plain-text delivery."""
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'</p>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&#39;', "'")
    return text.strip()


def truncate_text(text: str, max_chars: int = 4096) -> str:
    """Truncate text to WhatsApp's message length limit."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 3] + "..."


# ── Core send helpers ───────────────────────────────────────────

async def send_whatsapp_message(
    phone_number_id: str,
    recipient_id: str,
    text: str,
    preview_url: bool = False,
) -> bool:
    """Send a plain text message via the WhatsApp Cloud API."""
    if not META_ACCESS_TOKEN:
        logger.error("META_ACCESS_TOKEN not configured!")
        return False

    url = f"https://graph.facebook.com/v21.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    clean = strip_html(text)
    clean = truncate_text(clean)
    data = {
        "messaging_product": "whatsapp",
        "to": recipient_id,
        "type": "text",
        "text": {"body": clean, "preview_url": preview_url},
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(url, headers=headers, json=data)
            if res.status_code not in (200, 201):
                logger.error(f"WhatsApp send error: {res.status_code} {res.text}")
                return False
            return True
    except Exception as e:
        logger.error(f"WhatsApp send exception: {e}")
        return False


async def send_interactive_list(
    phone_number_id: str,
    recipient_id: str,
    header_text: str,
    body_text: str,
    button_text: str,
    sections: list,
    footer_text: str = "",
) -> bool:
    """Send an interactive list message (up to 10 sections, 30 rows each)."""
    if not META_ACCESS_TOKEN:
        return False

    url = f"https://graph.facebook.com/v21.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": recipient_id,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "header": {"type": "text", "text": truncate_text(strip_html(header_text), 60)},
            "body": {"text": truncate_text(strip_html(body_text), 1024)},
            "action": {
                "button": truncate_text(strip_html(button_text), 20),
                "sections": sections[:10],  # WhatsApp max 10 sections
            },
        },
    }
    if footer_text:
        payload["interactive"]["footer"] = {
            "text": truncate_text(strip_html(footer_text), 60)
        }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(url, headers=headers, json=payload)
            if res.status_code not in (200, 201):
                logger.error(f"WhatsApp list error: {res.status_code} {res.text}")
                return False
            return True
    except Exception as e:
        logger.error(f"WhatsApp list exception: {e}")
        return False


async def send_reply_buttons(
    phone_number_id: str,
    recipient_id: str,
    body_text: str,
    buttons: list,
    header_text: str = "",
    footer_text: str = "",
) -> bool:
    """Send interactive reply buttons (max 3 buttons)."""
    if not META_ACCESS_TOKEN:
        return False

    url = f"https://graph.facebook.com/v21.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    interactive = {
        "type": "button",
        "body": {"text": truncate_text(strip_html(body_text), 1024)},
        "action": {
            "buttons": [
                {
                    "type": "reply",
                    "reply": {
                        "id": b["id"][:256],
                        "title": strip_html(b["title"])[:20],
                    },
                }
                for b in buttons[:3]
            ]
        },
    }
    if header_text:
        interactive["header"] = {
            "type": "text",
            "text": truncate_text(strip_html(header_text), 60),
        }
    if footer_text:
        interactive["footer"] = {
            "text": truncate_text(strip_html(footer_text), 60),
        }

    payload = {
        "messaging_product": "whatsapp",
        "to": recipient_id,
        "type": "interactive",
        "interactive": interactive,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(url, headers=headers, json=payload)
            if res.status_code not in (200, 201):
                logger.error(f"WhatsApp buttons error: {res.status_code} {res.text}")
                return False
            return True
    except Exception as e:
        logger.error(f"WhatsApp buttons exception: {e}")
        return False


async def send_image(
    phone_number_id: str,
    recipient_id: str,
    image_url: str,
    caption: str = "",
) -> bool:
    """Send an image message."""
    if not META_ACCESS_TOKEN:
        return False
    url = f"https://graph.facebook.com/v21.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {
        "messaging_product": "whatsapp",
        "to": recipient_id,
        "type": "image",
        "image": {"link": image_url, "caption": truncate_text(strip_html(caption), 1024)},
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(url, headers=headers, json=data)
            return res.status_code in (200, 201)
    except Exception as e:
        logger.error(f"WhatsApp image error: {e}")
        return False


async def send_audio(
    phone_number_id: str,
    recipient_id: str,
    audio_url: str,
) -> bool:
    """Send an audio message."""
    if not META_ACCESS_TOKEN:
        return False
    url = f"https://graph.facebook.com/v21.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {
        "messaging_product": "whatsapp",
        "to": recipient_id,
        "type": "audio",
        "audio": {"link": audio_url},
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(url, headers=headers, json=data)
            return res.status_code in (200, 201)
    except Exception as e:
        logger.error(f"WhatsApp audio error: {e}")
        return False


async def send_document(
    phone_number_id: str,
    recipient_id: str,
    document_url: str,
    caption: str = "",
    filename: str = "",
) -> bool:
    """Send a document message."""
    if not META_ACCESS_TOKEN:
        return False
    url = f"https://graph.facebook.com/v21.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    doc = {"link": document_url}
    if filename:
        doc["filename"] = filename
    if caption:
        doc["caption"] = truncate_text(strip_html(caption), 1024)

    data = {
        "messaging_product": "whatsapp",
        "to": recipient_id,
        "type": "document",
        "document": doc,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(url, headers=headers, json=data)
            return res.status_code in (200, 201)
    except Exception as e:
        logger.error(f"WhatsApp document error: {e}")
        return False


async def send_reaction(
    phone_number_id: str,
    recipient_id: str,
    message_id: str,
    emoji: str,
) -> bool:
    """React to a WhatsApp message with an emoji."""
    if not META_ACCESS_TOKEN:
        return False
    url = f"https://graph.facebook.com/v21.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {
        "messaging_product": "whatsapp",
        "to": recipient_id,
        "type": "reaction",
        "reaction": {"message_id": message_id, "emoji": emoji},
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(url, headers=headers, json=data)
            return res.status_code in (200, 201)
    except Exception as e:
        logger.error(f"WhatsApp reaction error: {e}")
        return False


async def send_read_receipt(phone_number_id: str, message_id: str) -> bool:
    """Mark a message as read."""
    if not META_ACCESS_TOKEN:
        return False
    url = f"https://graph.facebook.com/v21.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    data = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, headers=headers, json=data)
            return res.status_code in (200, 201)
    except Exception as e:
        logger.error(f"WhatsApp read receipt error: {e}")
        return False


# ── Section builders for list messages ──────────────────────────

def build_section(title: str, rows: list) -> dict:
    """Build a list section with row items.
    Each row: {"id": "unique_id", "title": "Item Title", "description": "Short desc"}
    """
    return {
        "title": strip_html(title)[:24],
        "rows": [
            {
                "id": r["id"][:256],
                "title": strip_html(r["title"])[:24],
                "description": strip_html(r.get("description", ""))[:72],
            }
            for r in rows[:30]
        ],
    }


def build_button_reply(id: str, title: str) -> dict:
    """Build a button reply object."""
    return {"id": id, "title": title}
