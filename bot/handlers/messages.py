from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction
from firebase_admin import firestore
from bot.config import logger, is_admin
from bot.database import db
from bot.ai import get_grok_response, get_faq_response

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user_message = update.message.text
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    # 🛡️ Anti-Spam Link Protection for Groups
    if update.message.chat.type in ["group", "supergroup"]:
        if ("http://" in user_message.lower() or "https://" in user_message.lower()) and not is_admin(user_id):
            try:
                await update.message.delete()
                await context.bot.send_message(
                    chat_id=update.message.chat_id,
                    text=f"⚠️ @{username}, external links are not allowed in this group!"
                )
                return
            except Exception as e:
                logger.error(f"Could not delete spam message: {e}")

    if db:
        try:
            db.collection("questions").add({
                "user_id": user_id,
                "username": username,
                "question": user_message,
                "timestamp": firestore.SERVER_TIMESTAMP
            })
        except Exception as e:
            logger.error(f"Firebase error: {e}")

    # Smart filtering for Grok AI
    should_use_ai = False
    
    # 1. Direct message (Private chat)
    if update.message.chat.type == "private":
        should_use_ai = True
        
    # 2. Reply to bot's message
    elif update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id:
        should_use_ai = True
        
    # 3. Mentioned explicitly
    elif context.bot.username and f"@{context.bot.username}" in user_message:
        should_use_ai = True
        
    if should_use_ai:
        await update.message.chat.send_action(ChatAction.TYPING)
        response = await get_grok_response(user_message)
        if not response:
            response = get_faq_response(user_message)
            if not response:
                response = "Walaikum Assalam! 😊 How can I help you today? Type /help to see what I can do."
    else:
        # Silent FAQ check for groups
        response = get_faq_response(user_message)

    if response:
        await update.message.reply_text(response, parse_mode="HTML", reply_to_message_id=update.message.message_id)
        logger.info(f"Answered question from {user_id}: {user_message[:50]}")

async def welcome_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.is_bot: continue
        welcome_text = (
            f"👋 Assalamu Alaikum and welcome to the community, <a href='tg://user?id={member.id}'>{member.first_name}</a>!\n\n"
            f"Feel free to ask questions here, or check out the latest content by typing /youtube."
        )
        await update.message.reply_text(welcome_text, parse_mode="HTML")

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    if query.data == "enter_giveaway":
        if not db:
            await query.answer("Database not configured.", show_alert=True)
            return
            
        user_id = query.from_user.id
        username = query.from_user.first_name
        
        try:
            doc_ref = db.collection("giveaway_entries").document(str(user_id))
            doc = doc_ref.get()
            if doc.exists:
                await query.answer("You have already entered! Good luck! 🍀", show_alert=True)
            else:
                doc_ref.set({
                    "user_id": user_id,
                    "username": username,
                    "timestamp": firestore.SERVER_TIMESTAMP
                })
                await query.answer("🎉 You have successfully entered the giveaway!", show_alert=True)
        except Exception as e:
            logger.error(f"Giveaway entry error: {e}")
            await query.answer("An error occurred. Please try again.", show_alert=True)
