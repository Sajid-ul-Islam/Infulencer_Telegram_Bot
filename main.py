import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from bot.config import logger, TELEGRAM_TOKEN, BOT_TZ
from bot.database import load_faqs
from bot.server import start_server_threads
from bot.jobs import auto_post_youtube, auto_post_medium, greeting_post
from bot.handlers.commands import start, socials_command, latest, youtube, medium, ask_command, help_command
from bot.handlers.admin import (
    postlatest_command, ban_command, mute_command, questions_command,
    poll_command, broadcast_command, addfaq_command, rmfaq_command,
    listfaq_command, stats_command, suggest_command, listsuggestions_command,
    startgiveaway_command, pickwinner_command
)
from bot.handlers.messages import handle_message, welcome_new_members, button_callback_handler

def main():
    start_server_threads()

    load_faqs()
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Basic commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("socials", socials_command))
    application.add_handler(CommandHandler("latest", latest))
    application.add_handler(CommandHandler("youtube", youtube))
    application.add_handler(CommandHandler("medium", medium))
    application.add_handler(CommandHandler("ask", ask_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("suggest", suggest_command))
    
    # Admin commands
    application.add_handler(CommandHandler("postlatest", postlatest_command))
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("mute", mute_command))
    application.add_handler(CommandHandler("questions", questions_command))
    application.add_handler(CommandHandler("poll", poll_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("addfaq", addfaq_command))
    application.add_handler(CommandHandler("rmfaq", rmfaq_command))
    application.add_handler(CommandHandler("listfaq", listfaq_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("listsuggestions", listsuggestions_command))
    application.add_handler(CommandHandler("startgiveaway", startgiveaway_command))
    application.add_handler(CommandHandler("pickwinner", pickwinner_command))
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    
    # Message handlers
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Scheduled jobs
    job_queue = application.job_queue
    job_queue.run_daily(auto_post_youtube, time=datetime.time(9, 0, tzinfo=BOT_TZ), days=(0, 1, 2, 3, 4, 5, 6))
    job_queue.run_daily(auto_post_medium, time=datetime.time(18, 0, tzinfo=BOT_TZ), days=(0, 1, 2, 3, 4, 5, 6))
    job_queue.run_daily(greeting_post, time=datetime.time(8, 0, tzinfo=BOT_TZ), days=(0, 1, 2, 3, 4, 5, 6))
    
    logger.info("Bot started successfully!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
