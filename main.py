import datetime
import asyncio
import os
import threading
import uvicorn
from telegram import Update, BotCommand, BotCommandScopeDefault, BotCommandScopeAllPrivateChats, BotCommandScopeAllGroupChats, BotCommandScopeChat
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, InlineQueryHandler
from bot.config import logger, TELEGRAM_TOKEN, BOT_TZ, ADMIN_ID, RENDER_EXTERNAL_URL, WEBHOOK_URL, validate_ai_keys
from bot.database import load_faqs
from bot.utils import ping_self
from bot.jobs import auto_post_youtube, auto_post_medium, auto_post_substack, auto_post_facebook, auto_post_twitter, greeting_post, weekly_digest, daily_islamic_reminder, evening_islamic_reminder, scheduled_content_hub_post, process_post_queue
from bot.pipeline import ingest_knowledge_base, ingest_duas, ingest_quran_verses
from bot.handlers.commands import (
    start, socials_command, latest, youtube, medium, substack,
    ask_command, dua_command, quran_command, forget_command, ingest_command, help_command,
    subscribe_command, unsubscribe_command, language_command, reminder_time_command, myduas_command,
    study_command, stopstudy_command, ingestdoc_command
)
from bot.handlers.admin import (
    postlatest_command, ban_command, mute_command, questions_command,
    poll_command, broadcast_command, addfaq_command, rmfaq_command,
    listfaq_command, stats_command, ingest_kb_command, ingest_duas_command, ingest_quran_kb_command, suggest_command,
    listsuggestions_command, startgiveaway_command, pickwinner_command,
    schedule_command, channelstats_command, quiz_command, checkkeys_command
)
from bot.handlers.messages import handle_message, welcome_new_members, button_callback_handler, handle_voice
from bot.handlers.inline import inline_query


async def background_init(app):
    loop = asyncio.get_event_loop()

    # Load persisted scheduled posts from Firestore into memory
    try:
        from bot.handlers.influencer import _load_pending_posts_from_firestore
        count = await loop.run_in_executor(None, _load_pending_posts_from_firestore)
        if count:
            logger.info(f"Restored {count} pending scheduled posts from Firestore.")
    except Exception as e:
        logger.warning(f"Scheduled posts load failed (non-blocking): {e}")

    try:
        await loop.run_in_executor(None, load_faqs)
        logger.info("FAQs loaded from Firestore.")
    except Exception as e:
        logger.warning(f"FAQ loading failed (non-blocking): {e}")
    # Pre-load dua categories so the menu shows real chapter names immediately
    try:
        from bot.dua_scraper import _get_category_map
        cat_map = await _get_category_map()
        logger.info(f"Loaded {len(cat_map)} dua categories from source.")
    except Exception as e:
        logger.warning(f"Dua category loading failed (non-blocking): {e}")
    try:
        await loop.run_in_executor(None, lambda: ingest_knowledge_base(reindex=False))
        logger.info("Knowledge base ingested.")
    except Exception as e:
        logger.warning(f"KB ingestion failed (non-blocking): {e}")
    try:
        dua_count = await ingest_duas(force_reindex=False)
        logger.info(f"Dua ingestion complete: {dua_count} new duas indexed.")
    except Exception as e:
        logger.warning(f"Dua ingestion failed (non-blocking): {e}")
    try:
        quran_count = await ingest_quran_verses(force_reindex=False)
        logger.info(f"Quran ingestion complete: {quran_count} new verses indexed.")
    except Exception as e:
        logger.warning(f"Quran ingestion failed (non-blocking): {e}")
    try:
        from bot.search import get_rag_status
        status = get_rag_status()
        logger.info(
            f"RAG status — duas: {status['dua_count']}, quran: {status['quran_count']}, available: {status['available']}"
        )
    except Exception as e:
        logger.warning(f"RAG status check failed: {e}")


async def post_init(application: Application):
    try:
        webhook_info = await application.bot.get_webhook_info()
        if webhook_info and webhook_info.url:
            logger.info(f"Clearing old webhook: {webhook_info.url}")
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
        BotCommand("study", "Study a specific book"),
        BotCommand("stopstudy", "Stop studying the book"),
        BotCommand("ingestpdf", "Upload a PDF as a book"),
        BotCommand("subscribe", "Get daily Islamic reminders"),
        BotCommand("unsubscribe", "Stop daily reminders"),
        BotCommand("remindertime", "Change reminder time"),
        BotCommand("myduas", "View your bookmarked duas"),
        BotCommand("language", "Set language preference")
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
            BotCommand("ingest", "Re-index main knowledge base"),
            BotCommand("startgiveaway", "Start a giveaway"),
            BotCommand("pickwinner", "Pick giveaway winner"),
            BotCommand("schedule", "Schedule a post for later"),
            BotCommand("channelstats", "Show channel & bot stats"),
            BotCommand("quiz", "Send an interactive quiz"),
            BotCommand("checkkeys", "Test API keys live"),
        ]
        try:
            await application.bot.set_my_commands(
                admin_commands, scope=BotCommandScopeChat(chat_id=int(ADMIN_ID))
            )
            logger.info("Admin bot commands menu updated for admin chat.")
        except Exception as e:
            logger.warning(f"Failed to set admin commands menu: {e}")

    asyncio.create_task(background_init(application))


def build_application() -> Application:
    """Build and configure the PTB Application with all handlers."""
    application = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("subscribe", subscribe_command))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    application.add_handler(CommandHandler("remindertime", reminder_time_command))
    application.add_handler(CommandHandler("myduas", myduas_command))
    application.add_handler(CommandHandler("socials", socials_command))
    application.add_handler(CommandHandler("latest", latest))
    application.add_handler(CommandHandler("youtube", youtube))
    application.add_handler(CommandHandler("medium", medium))
    application.add_handler(CommandHandler("substack", substack))
    application.add_handler(CommandHandler("ask", ask_command))
    application.add_handler(CommandHandler("dua", dua_command))
    application.add_handler(CommandHandler("quran", quran_command))
    application.add_handler(CommandHandler("forget", forget_command))
    application.add_handler(CommandHandler("language", language_command))
    application.add_handler(CommandHandler("study", study_command))
    application.add_handler(CommandHandler("stopstudy", stopstudy_command))
    application.add_handler(CommandHandler("ingestdoc", ingestdoc_command))
    application.add_handler(CommandHandler("ingestpdf", ingestdoc_command)) # Alias for backwards compatibility
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
    application.add_handler(CommandHandler("schedule", schedule_command))
    application.add_handler(CommandHandler("channelstats", channelstats_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("checkkeys", checkkeys_command))

    application.add_handler(InlineQueryHandler(inline_query))
    application.add_handler(CallbackQueryHandler(button_callback_handler))

    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    
    from bot.handlers.messages import handle_document_upload
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document_upload))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Schedule recurring jobs
    job_queue = application.job_queue
    job_queue.run_daily(
        daily_islamic_reminder, time=datetime.time(10, 0, tzinfo=BOT_TZ),
        days=(0, 1, 2, 3, 4, 5, 6)
    )
    job_queue.run_daily(
        evening_islamic_reminder, time=datetime.time(18, 0, tzinfo=BOT_TZ),
        days=(0, 1, 2, 3, 4, 5, 6)
    )
    job_queue.run_repeating(
        auto_post_youtube,
        interval=21600,
        first=3600
    )
    job_queue.run_repeating(
        auto_post_medium,
        interval=21600,
        first=4500
    )
    job_queue.run_repeating(
        auto_post_substack,
        interval=21600,
        first=5400
    )
    job_queue.run_repeating(
        auto_post_facebook,
        interval=21600,
        first=6300
    )
    job_queue.run_repeating(
        auto_post_twitter,
        interval=21600,
        first=7200
    )
    job_queue.run_daily(
        weekly_digest, time=datetime.time(12, 0, tzinfo=BOT_TZ),
        days=(6,)
    )

    job_queue.run_repeating(
        scheduled_content_hub_post,
        interval=21600,
        first=8100
    )

    # Queue processor runs every 15 minutes (900 seconds)
    job_queue.run_repeating(
        process_post_queue,
        interval=900,
        first=60
    )

    return application


async def async_main():
    # Build and configure the PTB application
    application = build_application()

    # Initialize the application (triggers post_init which clears old webhook, sets commands, starts background init)
    await application.initialize()

    # Expose the PTB application to the FastAPI webhook handler
    import bot.fastapi_app
    bot.fastapi_app.ptb_application = application

    # Start the update processing pipeline (no polling — updates come via webhook)
    await application.start()
    logger.info("Bot application started — waiting for webhook updates.")

    # Start the self-ping keepalive in a daemon thread
    ping_thread = threading.Thread(target=ping_self, daemon=True)
    ping_thread.start()

    # Determine the webhook URL
    webhook_url = WEBHOOK_URL
    if not webhook_url:
        external_url = RENDER_EXTERNAL_URL
        if external_url:
            webhook_url = f"{external_url.rstrip('/')}/webhook"

    # Ensure the webhook URL points to the /webhook endpoint
    if webhook_url:
        # Remove trailing slash, then append /webhook if it doesn't already end with it
        webhook_url = webhook_url.rstrip('/')
        if not webhook_url.endswith('/webhook'):
            webhook_url = f"{webhook_url}/webhook"

    # Start the FastAPI / uvicorn server in the background
    port = int(os.environ.get("PORT", 8080))
    config = uvicorn.Config("bot.fastapi_app:app", host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())

    # Wait for the server to be ready by polling /healthz
    import httpx
    health_url = f"http://127.0.0.1:{port}/healthz"
    async with httpx.AsyncClient() as client:
        for attempt in range(30):
            try:
                resp = await client.get(health_url, timeout=2)
                if resp.status_code == 200:
                    logger.info(f"FastAPI server ready after ~{attempt * 0.25}s")
                    break
            except httpx.RequestError:
                pass
            await asyncio.sleep(0.25)
        else:
            logger.warning(
                "FastAPI server did not report ready within 7.5s. "
                "Proceeding to set webhook anyway."
            )

    if webhook_url:
        try:
            await application.bot.set_webhook(
                url=webhook_url,
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True
            )
            logger.info(f"Telegram webhook set to {webhook_url}")
        except Exception as e:
            logger.error(f"Failed to set Telegram webhook: {e}")
            logger.warning("Bot will not receive updates until webhook is configured. "
                           "You can set it manually via Telegram API or restart the service.")
            # Don't exit — the server is running and can serve the dashboard
    else:
        logger.warning(
            "Neither WEBHOOK_URL nor RENDER_EXTERNAL_URL is set. "
            "The bot will not receive updates!"
        )

    # Wait for the server to finish (blocks until shutdown)
    await server_task

    # Cleanup on shutdown
    logger.info("Shutting down bot application...")
    await application.stop()
    await application.shutdown()
    logger.info("Bot application stopped.")


def main():
    # Validate AI provider keys and WhatsApp credentials immediately so diagnostics appear first in logs
    validate_ai_keys()
    from bot.config import validate_whatsapp_keys
    validate_whatsapp_keys()
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
