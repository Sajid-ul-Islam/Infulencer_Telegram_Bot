"""
Meta platform handler (WhatsApp, Messenger, Instagram).
Processes incoming webhook payloads and routes to the appropriate handler.

For WhatsApp: routes to the comprehensive WhatsApp handler which mirrors
all Telegram bot features (content, duas, Quran, AI, bookmarks, subscriptions, etc.)
"""
import asyncio
import httpx
from typing import Dict, Any
from bot.config import logger, META_ACCESS_TOKEN, META_VERIFY_TOKEN
from bot.whatsapp_utils import strip_html
from bot.handlers.whatsapp import handle_whatsapp_message, handle_interactive_reply


async def handle_meta_webhook_payload(payload: Dict[Any, Any]):
    """
    Parses generic Meta webhook payload (WhatsApp or Messenger/Instagram).
    Routes messages to the appropriate handler.
    """
    if "object" not in payload:
        return

    object_type = payload.get("object")

    if object_type == "whatsapp_business_account":
        logger.info(f"WhatsApp webhook received — entries={len(payload.get('entry', []))}")
        await _process_whatsapp(payload)
    elif object_type in ["page", "instagram"]:
        logger.info(f"Messenger/Instagram webhook received")
        await _process_messenger(payload)
    else:
        logger.info(f"Unknown Meta webhook object: {object_type}")


async def _process_whatsapp(payload: dict):
    """
    Process incoming WhatsApp messages and interactive replies.
    Routes to the comprehensive WhatsApp handler which mirrors all Telegram features.
    """
    for entry in payload.get("entry", []):
        entry_id = entry.get("id", "unknown")
        for change in entry.get("changes", []):
            value = change.get("value", {})

            # Check if this is a message or status update
            if "messages" in value:
                phone_number_id = value.get("metadata", {}).get("phone_number_id")
                logger.debug(f"WhatsApp messages for phone_number_id={phone_number_id} — count={len(value['messages'])}")

                # Validate phone_number_id
                if not phone_number_id:
                    logger.error(f"Missing phone_number_id in webhook payload — Meta may have changed the payload format")
                    continue

                for message in value.get("messages", []):
                    sender_id = message.get("from")
                    msg_id = message.get("id", "")
                    msg_type = message.get("type", "")

                    # ── Text messages ──
                    if msg_type == "text":
                        text = message.get("text", {}).get("body", "")
                        logger.info(f"WhatsApp text from {sender_id}: {text[:80]}")

                        # Route to the comprehensive WhatsApp handler
                        try:
                            asyncio.create_task(
                                handle_whatsapp_message(
                                    phone_number_id=phone_number_id,
                                    sender_id=sender_id,
                                    text=text,
                                    message_id=msg_id,
                                )
                            )
                        except Exception as e:
                            logger.error(f"Error handling WhatsApp text: {e}")

                    # ── Interactive replies (list selection, button click) ──
                    elif msg_type == "interactive":
                        interactive = message.get("interactive", {})
                        interactive_type = interactive.get("type", "")

                        if interactive_type == "list_reply":
                            list_reply = interactive.get("list_reply", {})
                            logger.info(f"WhatsApp list reply from {sender_id}: {list_reply.get('id')}")
                            try:
                                asyncio.create_task(
                                    handle_interactive_reply(
                                        phone_number_id=phone_number_id,
                                        sender_id=sender_id,
                                        interactive_type="list_reply",
                                        payload=list_reply,
                                        message_id=msg_id,
                                    )
                                )
                            except Exception as e:
                                logger.error(f"Error handling list reply: {e}")

                        elif interactive_type == "button_reply":
                            button_reply = interactive.get("button_reply", {})
                            logger.info(f"WhatsApp button reply from {sender_id}: {button_reply.get('id')}")
                            try:
                                asyncio.create_task(
                                    handle_interactive_reply(
                                        phone_number_id=phone_number_id,
                                        sender_id=sender_id,
                                        interactive_type="button_reply",
                                        payload=button_reply,
                                        message_id=msg_id,
                                    )
                                )
                            except Exception as e:
                                logger.error(f"Error handling button reply: {e}")

                    # ── Voice messages ──
                    elif msg_type == "voice":
                        logger.info(f"WhatsApp voice message from {sender_id}")
                        audio_id = message.get("voice", {}).get("id", "")
                        try:
                            asyncio.create_task(
                                _handle_whatsapp_voice(
                                    phone_number_id, sender_id, audio_id, msg_id
                                )
                            )
                        except Exception as e:
                            logger.error(f"Error handling voice: {e}")

                    # ── Document / Image messages ──
                    elif msg_type in ("document", "image"):
                        logger.info(f"WhatsApp {msg_type} from {sender_id} — ignoring for now")
                        try:
                            asyncio.create_task(
                                _send_whatsapp_plain(
                                    phone_number_id, sender_id,
                                    "📄 I received your file. I can't process uploaded documents on WhatsApp yet. "
                                    "Please send text or voice messages, and I'll be happy to help!",
                                    msg_id,
                                )
                            )
                        except Exception as e:
                            logger.error(f"Error handling media: {e}")

                    else:
                        logger.info(f"WhatsApp: ignoring message type {msg_type}")

            # ── Status updates (read receipts, etc.) ──
            elif "statuses" in value:
                for status in value.get("statuses", []):
                    status_type = status.get("status", "")
                    # Silently acknowledge status updates
                    logger.debug(f"WhatsApp status update: {status_type}")


async def _process_messenger(payload: dict):
    """Process Messenger/Instagram messages via the existing messaging loop."""
    for entry in payload.get("entry", []):
        for messaging_event in entry.get("messaging", []):
            sender_id = messaging_event.get("sender", {}).get("id")
            message = messaging_event.get("message", {})

            if "text" in message:
                text = message.get("text")
                await _respond_messenger(sender_id, text)


async def _handle_whatsapp_voice(
    phone_number_id: str, sender_id: str, audio_id: str, message_id: str = None
):
    """
    Download a WhatsApp voice message, transcribe it, and respond via AI.
    """
    if not META_ACCESS_TOKEN:
        logger.error("META_ACCESS_TOKEN not configured for voice processing")
        return

    # 1. Get the media URL
    media_url = f"https://graph.facebook.com/v21.0/{audio_id}"
    headers = {"Authorization": f"Bearer {META_ACCESS_TOKEN}"}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            media_resp = await client.get(media_url, headers=headers)
            if media_resp.status_code != 200:
                logger.error(f"Failed to get media URL: {media_resp.text}")
                await _send_whatsapp_plain(
                    phone_number_id, sender_id,
                    "Sorry, I couldn't process that voice message.",
                    message_id,
                )
                return

            media_data = media_resp.json()
            download_url = media_data.get("url", "")

            if not download_url:
                logger.error("No download URL in media response")
                return

            # 2. Download the audio
            audio_resp = await client.get(download_url, headers=headers)
            if audio_resp.status_code != 200:
                logger.error(f"Failed to download audio: {audio_resp.text}")
                return

            # 3. Save to temp file and transcribe
            import tempfile
            import os

            with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as tmp:
                tmp.write(audio_resp.content)
                tmp_path = tmp.name

            from bot.transcriber import transcribe_voice
            text = await transcribe_voice(tmp_path)
            os.unlink(tmp_path)

            if not text:
                await _send_whatsapp_plain(
                    phone_number_id, sender_id,
                    "Sorry, I couldn't understand the voice message.",
                    message_id,
                )
                return

            # 4. Get AI response
            from bot.ai import get_ai_response
            from bot.database import track_activity

            # WhatsApp sender IDs are phone numbers; use numeric portion if possible
            wa_user_id = None
            clean_id = sender_id.lstrip("+")
            if clean_id.isdigit():
                wa_user_id = int(clean_id)
            track_activity(wa_user_id or 0, sender_id, "whatsapp_voice")

            response = await get_ai_response(text, user_id=wa_user_id)

            if response:
                clean = strip_html(response)
                await _send_whatsapp_plain(
                    phone_number_id, sender_id,
                    f"🎤 *Transcribed:* {text}\n\n{clean}",
                    message_id,
                )
            else:
                await _send_whatsapp_plain(
                    phone_number_id, sender_id,
                    f"🎤 *Transcribed:* {text}",
                    message_id,
                )

    except Exception as e:
        logger.error(f"WhatsApp voice processing error: {e}")
        await _send_whatsapp_plain(
            phone_number_id, sender_id,
            "Sorry, I had trouble processing that voice message.",
            message_id,
        )


async def _send_whatsapp_plain(
    phone_number_id: str, recipient_id: str, text: str, message_id: str = None
):
    """Send a plain text WhatsApp message directly (no interactive)."""
    from bot.whatsapp_utils import send_whatsapp_message, send_read_receipt
    if message_id:
        asyncio.create_task(send_read_receipt(phone_number_id, message_id))
    await send_whatsapp_message(phone_number_id, recipient_id, text)


async def _respond_messenger(recipient_id: str, text: str):
    """Legacy Messenger response handler — basic AI responses only."""
    from bot.ai import get_ai_response

    user_id = int(recipient_id) if recipient_id.isdigit() else None
    response_text = await get_ai_response(text, user_id=user_id, use_memory=True)
    if not response_text:
        response_text = "Sorry, I'm having trouble thinking right now!"

    if not META_ACCESS_TOKEN:
        logger.error("META_ACCESS_TOKEN not configured!")
        return

    url = "https://graph.facebook.com/v21.0/me/messages"
    headers = {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    clean_text = strip_html(response_text)

    data = {
        "recipient": {"id": recipient_id},
        "message": {"text": clean_text},
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(url, headers=headers, json=data)
            if res.status_code != 200:
                logger.error(f"Failed to send Messenger message: {res.text}")
    except Exception as e:
        logger.error(f"Exception sending Messenger message: {e}")
