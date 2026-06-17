import datetime
import asyncio
from telegram import Update, BotCommand, BotCommandScopeDefault, BotCommandScopeAllPrivateChats, BotCommandScopeAllGroupChats, BotCommandScopeChat
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, InlineQueryHandler
from bot.config import logger, TELEGRAM_TOKEN, BOT_TZ, ADMIN_ID
from bot.database import load_faqs
from bot.server import start_server_threads
from bot.jobs import auto_post_youtube, auto_post_medium, auto_post_substack, greeting_post, weekly_digest
from bot.pipeline import ingest_knowledge_base, ingest_duas, ingest_quran_verses
from bot.handlers.commands import (
    start, socials_command, latest, youtube, medium, substack,
    ask_command, dua_command, quran_command, forget_command, ingest_command, help_command
)
from bot.handlers.admin import (
    postlatest_command, ban_command, mute_command, questions_command,
    poll_command, broadcast_command, addfaq_command, rmfaq_command,
    listfaq_command, stats_command, ingest_kb_command, ingest_duas_command, ingest_quran_kb_command, suggest_command,
    listsuggestions_command, startgiveaway_command, pickwinner_command
)
from bot.handlers.messages import handle_message, welcome_new_members, button_callback_handler, handle_voice
from bot.handlers.inline import inline_query

async def background_init(app):
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, load_faqs)
        logger.info("FAQs loaded from Firestore.")
    except Exception as e:
        logger.warning(f"FAQ loading failed (non-blocking): {e}")
    try:
        await loop.run_in_executor(None, lambda: ingest_knowledge_base(reindex=False))
        logger.info("Knowledge base ingested.")
    except Exception as e:
        logger.warning(f"KB ingestion failed (non-blocking): {e}")
    try:
        await ingest_duas(force_reindex=False)
    except Exception as e:
        logger.warning(f"Dua ingestion failed (non-blocking): {e}")
    try:
        await ingest_quran_verses(force_reindex=False)
    except Exception as e:
        logger.warning(f"Quran ingestion failed (non-blocking): {e}")

async def post_init(application: Application):
    try:
        webhook_info = await application.bot.get_webhook_info()
        if webhook_info and webhook_info.url:
            logger.info(f"Clearing webhook: {webhook_info.url}")
            await application.bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        logger.warning(f"Webhook cleanup: {e}")
    commands = [
        BotCommand("start", "Welcome message"),
        BotCommand("help", "Show all commands"),
        BotCommand("ask", "Ask me anything (with memory)"),
        BotCommand("latest", "Get all latest content"),
        BotCommand("youtube", "Latest video"),
        BotCommand("medium", "Latest article"),
        BotCommand("substack", "Latest newsletter"),
        BotCommand("quran", "Search Quran verses"),
        BotCommand("dua", "Search Hisnul Muslim duas"),
        BotCommand("socials", "Links to all my platforms"),
        BotCommand("suggest", "Suggest a topic idea"),
        BotCommand("forget", "Clear conversation history"),
    ]
    try:
        await application.bot.set_my_commands(commands, scope=BotCommandScopeDefault())
        await application.bot.set_my_commands(commands, scope=BotCommandScopeAllPrivateChats())
        await application.bot.set_my_commands(commands, scope=BotCommandScopeAllGroupChats())
        logger.info("Bot commands menu updated for default, private, and group scopes.")
    except Exception as e:
        logger.error(f"Failed to set bot commands menu (non-blocking): {e}")

    # Set up custom admin commands menu if ADMIN_ID is set
    if ADMIN_ID and str(ADMIN_ID).strip().isdigit():
        admin_commands = [
            BotCommand("stats", "Show admin stats"),
            BotCommand("questions", "List recent user questions"),
            BotCommand("listsuggestions", "List geopolitics topic suggestions"),
            BotCommand("postlatest", "Broadcast latest posts from platforms"),
            BotCommand("broadcast", "Send a message to group & channel"),
            BotCommand("addfaq", "Add a new custom FAQ"),
            BotCommand("rmfaq", "Remove a custom FAQ"),
            BotCommand("listfaq", "List all custom FAQs"),
            BotCommand("ingestkb", "Re-index creator knowledge base"),
            BotCommand("ingestduas", "Re-index Hisnul Muslim duas"),
            BotCommand("ingestquran", "Re-index Quran verses"),
            BotCommand("startgiveaway", "Start a giveaway"),
            BotCommand("pickwinner", "Pick giveaway winner"),
        ]
        try:
            await application.bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=int(ADMIN_ID)))
            logger.info("Admin bot commands menu updated for admin chat.")
        except Exception as e:
            logger.warning(f"Failed to set admin commands menu: {e}")

    asyncio.create_task(background_init(application))

def main():
    start_server_threads()

    application = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("socials", socials_command))
    application.add_handler(CommandHandler("latest", latest))
    application.add_handler(CommandHandler("youtube", youtube))
    application.add_handler(CommandHandler("medium", medium))
    application.add_handler(CommandHandler("substack", substack))
    application.add_handler(CommandHandler("ask", ask_command))
    application.add_handler(CommandHandler("dua", dua_command))
    application.add_handler(CommandHandler("quran", quran_command))
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
    application.add_handler(CommandHandler("ingestduas", ingest_duas_command))
    application.add_handler(CommandHandler("ingestquran", ingest_quran_kb_command))
    application.add_handler(CommandHandler("listsuggestions", listsuggestions_command))
    application.add_handler(CommandHandler("startgiveaway", startgiveaway_command))
    application.add_handler(CommandHandler("pickwinner", pickwinner_command))

    application.add_handler(InlineQueryHandler(inline_query))
    application.add_handler(CallbackQueryHandler(button_callback_handler))

    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    job_queue = application.job_queue
    job_queue.run_daily(auto_post_youtube, time=datetime.time(9, 0, tzinfo=BOT_TZ), days=(0, 1, 2, 3, 4, 5, 6))
    job_queue.run_daily(auto_post_medium, time=datetime.time(18, 0, tzinfo=BOT_TZ), days=(0, 1, 2, 3, 4, 5, 6))
    job_queue.run_daily(auto_post_substack, time=datetime.time(14, 0, tzinfo=BOT_TZ), days=(0, 1, 2, 3, 4, 5, 6))
    job_queue.run_daily(greeting_post, time=datetime.time(8, 0, tzinfo=BOT_TZ), days=(0, 1, 2, 3, 4, 5, 6))
    job_queue.run_daily(weekly_digest, time=datetime.time(12, 0, tzinfo=BOT_TZ), days=(6,))

    logger.info("Bot started successfully!")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
