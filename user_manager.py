from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from db_queries import execute_db_query
from decorators import admin_required
import config
from logger import Logger

logger = Logger.get_logger(__name__)

last_start_command = {}  # Global variable to track the last usage of /start command by each user

def start_command(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = update.effective_user.id
    username = update.effective_user.username
    current_time = datetime.now()

    # Handle the admin's response for adding a new user
    if query and query.data.startswith('add_user '):
        _, new_user_id, new_username = query.data.split(maxsplit=2)

        # Logic for adding the user to the database
        try:
            execute_db_query("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (new_user_id, new_username))
            query.edit_message_text(f"User @{new_username} (user_id: {new_user_id}) added successfully.")
            logger.info(f"User added: @{new_username} (user_id: {new_user_id}) by Admin {user_id}")
        except Exception as e:
            logger.error(f"Error adding user @{new_username} (ID: {new_user_id}): {e}")
            query.edit_message_text("Failed to add user. Please try again later.")
        return

    # Logic for preventing frequent /start command usage
    timeout = 15  # Timeout in seconds
    last_time = last_start_command.get(user_id, None)

    if last_time and (current_time - last_time).total_seconds() < timeout:
        reply_text = f"You must wait {timeout} seconds before using the /start command again."
        if update.message:
            update.message.reply_text(reply_text)
        elif query:
            query.answer(reply_text)
        return

    # Update the last command time for the user
    last_start_command[user_id] = current_time

    # Check if the user is already registered
    existing_user = execute_db_query("SELECT user_id FROM users WHERE user_id = ?", (user_id,), fetch_one=True)

    if existing_user:
        logger.info(f"User @{username} (user_id: {user_id}) invoked /start command.")
        reply_text = "You are already registered."
        if update.message:
            update.message.reply_text(reply_text)
        elif query:
            query.answer(reply_text)
        return

    if not username:
        reply_text = "You must have a Telegram username to use this bot."
        if update.message:
            update.message.reply_text(reply_text)
        elif query:
            query.answer(reply_text)
        return

    # Send user info to the superadmin
    try:
        keyboard = [[InlineKeyboardButton("Add User", callback_data=f"add_user {user_id} {username}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        context.bot.send_message(chat_id=config.ADMIN_USER_ID, text=f"New user alert!\n\nUser ID: {user_id}\nUsername: @{username}\n\nClick the button below to add them.", reply_markup=reply_markup)
        if update.message:
            update.message.reply_text("Your information has been sent to the admin for registration.")
        elif query:
            query.answer("Your information has been sent to the admin for registration.")
        logger.info(f"New user @{username} (user_id: {user_id}) sent to Admin {config.ADMIN_USER_ID} for registration.")

    except Exception as e:
        logger.error(f"Error sending user info to Admin {config.ADMIN_USER_ID}: {e}")
        reply_text = "Failed to send your information to the admin. Please try again later."
        if update.message:
            update.message.reply_text(reply_text)
        elif query:
            query.answer(reply_text)

@admin_required
def add_user(update: Update, context: CallbackContext):
    if len(context.args) != 2:
        update.message.reply_text("Usage: /add_user [user_id] [username]")
        return

    new_user_id, username = context.args

    # Check if the user already exists
    existing_user = execute_db_query("SELECT user_id FROM users WHERE user_id = ?", (new_user_id,), fetch_one=True)
    if existing_user:
        update.message.reply_text(f"User with user_id {new_user_id} already exists.")
        return

    # Check if the username is valid
    try:
        execute_db_query("INSERT INTO users (user_id, username) VALUES (?, ?)", (new_user_id, username))
        update.message.reply_text(f"User @{username} (user_id: {new_user_id}) added successfully.")
        logger.info(f"User added: @{username} (user_id: {new_user_id}) by Admin {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error adding user @{username} (ID: {new_user_id}): {e}")
        update.message.reply_text("Failed to add user. Please try again later.")

@admin_required
def remove_user(update: Update, context: CallbackContext):
    if len(context.args) != 1:
        update.message.reply_text("Usage: /remove_user [user_id]")
        return

    user_id_to_remove = context.args[0]

    # Prevent removing superadmin
    if user_id_to_remove == config.ADMIN_USER_ID:
        update.message.reply_text("Superadmin cannot be removed.")
        return

    # Check if the user exists
    existing_user = execute_db_query("SELECT user_id FROM users WHERE user_id = ?", (user_id_to_remove,), fetch_one=True)
    if not existing_user:
        update.message.reply_text(f"No user found with user_id {user_id_to_remove}.")
        return

    # Logic for removing the user from the database
    try:
        execute_db_query("DELETE FROM users WHERE user_id = ?", (user_id_to_remove,))
        update.message.reply_text(f"User with ID {user_id_to_remove} removed successfully.")
        logger.info(f"User with ID {user_id_to_remove} removed successfully by Admin {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error removing user with ID {user_id_to_remove}: {e}")
        update.message.reply_text("Failed to remove user. Please try again later.")

@admin_required
def make_admin(update: Update, context: CallbackContext):
    if len(context.args) != 1:
        update.message.reply_text("Usage: /make_admin [user_id]")
        return

    user_id_to_admin = context.args[0]

    # Check if the user exists
    existing_user = execute_db_query("SELECT user_id FROM users WHERE user_id = ?", (user_id_to_admin,), fetch_one=True)
    if not existing_user:
        update.message.reply_text(f"No user found with user_id {user_id_to_admin}.")
        return

    # Logic for making the user an admin
    try:
        execute_db_query("UPDATE users SET is_admin = 1 WHERE user_id = ?", (user_id_to_admin,))
        update.message.reply_text("User updated to admin successfully.")
        logger.info(f"User (user_id: {user_id_to_admin}) made an admin successfully by Admin {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error making user with ID {user_id_to_admin} an admin: {e}")
        update.message.reply_text("Failed to update user to admin. Please try again later.")

@admin_required
def revoke_admin(update: Update, context: CallbackContext):
    if len(context.args) != 1:
        update.message.reply_text("Usage: /revoke_admin [user_id]")
        return

    user_id_to_revoke = context.args[0]

    # Prevent revoking superadmin privileges
    if user_id_to_revoke == config.ADMIN_USER_ID:
        update.message.reply_text("Superadmin privileges cannot be revoked.")
        return

    existing_user = execute_db_query("SELECT user_id FROM users WHERE user_id = ?", (user_id_to_revoke,), fetch_one=True)
    if not existing_user:
        update.message.reply_text(f"No user found with user_id {user_id_to_revoke}.")
        return

    try:
        execute_db_query("UPDATE users SET is_admin = 0 WHERE user_id = ?", (user_id_to_revoke,))
        update.message.reply_text("Admin privileges revoked successfully.")
        logger.info(f"Admin privileges revoked from user with ID {user_id_to_revoke} by Admin {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error revoking admin rights from user with ID {user_id_to_revoke}: {e}")
        update.message.reply_text("Failed to revoke admin privileges. Please try again later.")

@admin_required
def delist_user(update: Update, context: CallbackContext):
    if len(context.args) != 1:
        update.message.reply_text("Usage: /delist_user [user_id]")
        return

    user_id_to_delist = context.args[0]

    existing_user = execute_db_query("SELECT user_id FROM users WHERE user_id = ?", (user_id_to_delist,), fetch_one=True)
    if not existing_user:
        update.message.reply_text(f"No user found with user_id {user_id_to_delist}.")
        return

    try:
        execute_db_query("UPDATE users SET is_delisted = 1 WHERE user_id = ?", (user_id_to_delist,))
        update.message.reply_text("User delisted successfully.")
        logger.info(f"User with ID {user_id_to_delist} delisted successfully by Admin {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error delisting user with ID {user_id_to_delist}: {e}")
        update.message.reply_text("Failed to delist user. Please try again later.")

@admin_required
def list_user(update: Update, context: CallbackContext):
    if len(context.args) != 1:
        update.message.reply_text("Usage: /list_user [user_id]")
        return

    user_id_to_list = context.args[0]

    existing_user = execute_db_query("SELECT user_id FROM users WHERE user_id = ?", (user_id_to_list,), fetch_one=True)
    if not existing_user:
        update.message.reply_text(f"No user found with user_id {user_id_to_list}.")
        return

    try:
        execute_db_query("UPDATE users SET is_delisted = 0 WHERE user_id = ?", (user_id_to_list,))
        update.message.reply_text("User listed successfully.")
        logger.info(f"User with ID {user_id_to_list} listed successfully by Admin {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error listing user with ID {user_id_to_list}: {e}")
        update.message.reply_text("Failed to list user. Please try again later.")

@admin_required
def view_users(update: Update, context: CallbackContext):
    try:
        users = execute_db_query("SELECT user_id, username, is_admin, is_delisted FROM users", fetch_all=True)
        if users:
            message_text = "List of all users:\n\n"
            for user in users:
                status = "Admin" if user[2] else ("Delisted" if user[3] else "User")
                username_display = f"@{user[1]}" if user[1] else "N/A"
                message_text += f"user_id: {user[0]}, {username_display}, status: {status}\n"
        else:
            message_text = "No users found."
        update.message.reply_text(message_text)
        logger.info(f"Admin {update.effective_user.id} viewed user list.")
    except Exception as e:
        logger.error(f"Error viewing users: {e}")
        update.message.reply_text("Failed to retrieve the user list. Please try again later.")