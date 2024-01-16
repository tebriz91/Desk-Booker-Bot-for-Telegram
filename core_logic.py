from telegram import Update
from telegram.ext import CallbackContext
import logging_setup

from database import execute_db_query # revise this line later
import config

admin_user_id = config.ADMIN_USER_ID
logger = logging_setup.logger

def is_admin(user_id):
    # Check if the user is an admin. Superadmin's admin status is unchangeable.
    if user_id == admin_user_id:
        return True
        
    query = "SELECT is_admin FROM users WHERE user_id = ?"
    try:
        result = execute_db_query(query, (user_id,), fetch_one=True)
        return result and result[0]
    except Exception as e:
        logger.error(f"Error checking admin status for user {user_id}: {e}")
        return False  # Default to non-admin in case of an error

def admin_required(func):
    def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = str(update.effective_user.id)
        logger.info(f"Admin command '{func.__name__}' invoked by {user_id}")
        if not is_admin(user_id):
            update.message.reply_text("You are not authorized to use this command.")
            return
        return func(update, context, *args, **kwargs)
    return wrapper

def user_required(func):
    def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = str(update.effective_user.id)
        result = execute_db_query("SELECT user_id FROM users WHERE user_id = ?", (user_id,), fetch_one=True)
        if not result:
            logger.info(f"Unregistered user with ID {user_id} invoked command '{func.__name__}'")
            update.message.reply_text(f"You need to be registered to use this command. Use /start to send your information to the admin for registration.")
            return
        return func(update, context, *args, **kwargs)
    return wrapper