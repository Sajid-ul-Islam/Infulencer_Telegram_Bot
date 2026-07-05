"""User preference callback handlers (language, reminder time)."""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger("bot")


async def handle_set_language(query, lang_code: str) -> None:
    """Handle setlang:{lang_code} callbacks."""
    user_id = query.from_user.id
    from bot.database import set_user_language
    success = set_user_language(user_id, lang_code)
    if success:
        lang_name = "Bengali 🇧🇩" if lang_code == "bn" else "English 🇬🇧"
        await query.answer(f"Language set to {lang_name}")
        await query.edit_message_text(f"✅ Language preference successfully set to {lang_name}.")
    else:
        await query.answer("Failed to set language", show_alert=True)


async def handle_reminder_time(query, time_pref: str) -> None:
    """Handle remindertime:{time_pref} callbacks."""
    if time_pref not in ("morning", "evening"):
        await query.answer("Invalid time preference.", show_alert=True)
        return
    user_id = query.from_user.id
    from bot.database import set_reminder_time, get_subscribed_users
    subscribed = get_subscribed_users()
    if user_id not in subscribed:
        await query.answer("Please /subscribe first!", show_alert=True)
        return
    success = set_reminder_time(user_id, time_pref)
    if success:
        label = "morning 🌅" if time_pref == "morning" else "evening 🌛"
        await query.answer(f"Reminder time changed to {label}!")
        await query.edit_message_text(
            f"✅ Reminder time successfully set to <b>{label}</b>.\n\n"
            f"You'll receive your daily Ayah + Dua at the selected time.",
            parse_mode="HTML",
        )
    else:
        await query.answer("Failed to update time. Try again.", show_alert=True)
