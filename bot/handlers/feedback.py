from telegram import Update
from telegram.ext import ContextTypes
from firebase_admin import firestore
from bot.config import logger
from bot.database import db

FEEDBACK_POSITIVE = "feedback:positive"
FEEDBACK_NEGATIVE = "feedback:negative"

