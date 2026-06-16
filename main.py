import datetime
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from bot.config import logger, TELEGRAM_TOKEN, BOT_TZ
from bot.database import load_faqs
from bot.server import start_server_threads
from bot.jobs import auto_post_youtube, auto_post_medium, auto_post_substack, greeting_post
from bot.pipeline import ingest_knowledge_base
from bot.handlers.commands import (
    start, socials_command, latest, youtube, medium, substack,
    ask_command, forget_command, ingest_command, help_command
)
from bot.handlers.admin import (
    postlatest_command, ban_command, mute_command, questions_command,
    poll_command, broadcast_command, addfaq_command, rmfaq_command,
    listfaq_command, stats_command, ingest_kb_command, suggest_command,
    listsuggestions_command, startgiveaway_command, pickwinner_command
)
from bot.handlers.messages import handle_message, welcome_new_members, button_callback_handler

async def post_init(application: Application):
    commands = [
        BotCommand("start", "Welcome message"),
        BotCommand("latest", "Get my latest content"),
        BotCommand("youtube", "Latest video"),
        BotCommand("medium", "Latest article"),
        BotCommand("substack", "Latest newsletter"),
        BotCommand("socials", "Links to all my platforms"),
        BotCommand("ask", "Ask me a question (with memory)"),
        BotCommand("forget", "Clear conversation history"),
        BotCommand("suggest", "Suggest a geopolitics topic"),
        BotCommand("help", "Show all commands")
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands menu updated.")

def main():
    start_server_threads()

    load_faqs()
    ingest_knowledge_base(reindex=False)
    logger.info("Knowledge base ingested into vector DB on startup.")

    application = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("socials", socials_command))
    application.add_handler(CommandHandler("latest", latest))
    application.add_handler(CommandHandler("youtube", youtube))
    application.add_handler(CommandHandler("medium", medium))
    application.add_handler(CommandHandler("substack", substack))
    application.add_handler(CommandHandler("ask", ask_command))
    application.add_handler(CommandHandler("forget", forget_command))
    application.add_handler(CommandHandler("ingest", ingest_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("suggest", suggest_command))

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
    application.add_handler(CommandHandler("ingestkb", ingest_kb_command))
    application.add_handler(CommandHandler("listsuggestions", listsuggestions_command))
    application.add_handler(CommandHandler("startgiveaway", startgiveaway_command))
    application.add_handler(CommandHandler("pickwinner", pickwinner_command))

    application.add_handler(CallbackQueryHandler(button_callback_handler))

    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    job_queue = application.job_queue
    job_queue.run_daily(auto_post_youtube, time=datetime.time(9, 0, tzinfo=BOT_TZ), days=(0, 1, 2, 3, 4, 5, 6))
    job_queue.run_daily(auto_post_medium, time=datetime.time(18, 0, tzinfo=BOT_TZ), days=(0, 1, 2, 3, 4, 5, 6))
    job_queue.run_daily(auto_post_substack, time=datetime.time(14, 0, tzinfo=BOT_TZ), days=(0, 1, 2, 3, 4, 5, 6))
    job_queue.run_daily(greeting_post, time=datetime.time(8, 0, tzinfo=BOT_TZ), days=(0, 1, 2, 3, 4, 5, 6))

    logger.info("Bot started successfully!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
