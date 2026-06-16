from telegram import Update
from telegram.ext import ContextTypes
from firebase_admin import firestore
from bot.config import logger
from bot.database import db

FEEDBACK_POSITIVE = "feedback:positive"
FEEDBACK_NEGATIVE = "feedback:negative"

async def feedback_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    username = query.from_user.first_name
    original_message_id = query.message.message_id
    original_text = query.message.text or ""
    try:
        if db:
            feedback_type = "positive" if FEEDBACK_POSITIVE in data else "negative"
            db.collection("feedback").add({
                "user_id": user_id,
                "username": username,
                "type": feedback_type,
                "message_id": original_message_id,
                "original_text": original_text[:200],
                "timestamp": firestore.SERVER_TIMESTAMP
            })
        if FEEDBACK_POSITIVE in data:
            await query.edit_message_text(
                text=original_text + "\n\n👍 Thanks for the feedback!",
                parse_mode="HTML"
            )
        elif FEEDBACK_NEGATIVE in data:
            await query.edit_message_text(
                text=original_text + "\n\n👎 Sorry that wasn't helpful. I'll improve!",
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Error saving feedback: {e}")
