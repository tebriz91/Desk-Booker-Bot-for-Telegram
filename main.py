from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext
from datetime import datetime, timedelta
import traceback
import sqlite3
import logging
import time
import pytz
import os
import threading
import config
import rooms_config

# Use the configurations
admin_user_id = config.ADMIN_USER_ID
admin_username = config.ADMIN_USERNAME
db_path = config.DB_PATH
log_timezone = config.LOG_TIMEZONE

db_lock = threading.Lock() # Global lock object that will be used to control access to the database for write operations

# Configure Time Zone for logging. This allows you change the logging time zone by updating the LOG_TIMEZONE variable in your config.py file
class ConfigurableTimeZoneFormatter(logging.Formatter):
    def __init__(self, fmt=None, datefmt=None, style='%', tz=log_timezone):
        super().__init__(fmt, datefmt, style)
        self.tz = pytz.timezone(tz)

    def converter(self, timestamp):
        return datetime.fromtimestamp(timestamp, self.tz)

    def formatTime(self, record, datefmt=None):
        dt = self.converter(record.created)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()

# Enable logging
formatter = ConfigurableTimeZoneFormatter(fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(handler)

# Ensure the 'data' directory for databases exists
os.makedirs(os.path.dirname(db_path), exist_ok=True)

# Global dictionary to store last command time for each user
last_start_command = {}

def initialize_database():
    # Initialize database
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # Create Rooms table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rooms (
                room_id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_name TEXT NOT NULL,
                room_availability INTEGER NOT NULL DEFAULT 1,
                plan_url TEXT,
                room_add_info TEXT
            )
        ''')

        # Create Desks table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS desks (
                desk_id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL,
                desk_number INTEGER NOT NULL,
                desk_availability INTEGER NOT NULL DEFAULT 1,
                desk_add_info TEXT,
                FOREIGN KEY (room_id) REFERENCES rooms(room_id) ON DELETE SET NULL
            )
        ''')

        # Create Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER UNIQUE,
                username TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0,
                is_delisted INTEGER DEFAULT 0,
                user_registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create Bookings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                booking_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                desk_id INTEGER NOT NULL,
                booking_date DATE NOT NULL,
                booking_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (desk_id) REFERENCES desks(desk_id) ON DELETE CASCADE
            )
        ''')

        conn.commit()

def initialize_admin_user():
    admin_user_exists = execute_db_query("SELECT user_id FROM users WHERE user_id = ?", (admin_user_id,), fetch_one=True)
    if not admin_user_exists:
        execute_db_query("INSERT INTO users (user_id, username, is_admin) VALUES (?, ?, 1)", (admin_user_id, admin_username))
        logger.info(f"Admin user {admin_username} added to the database.")

# Updated execute_db_query function
def execute_db_query(query, parameters=(), fetch_one=False, fetch_all=False):
    try:
        with db_lock:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(query, parameters)
                if fetch_one:
                    return cursor.fetchone()
                elif fetch_all:
                    return cursor.fetchall()
                else:
                    conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        raise
    result = cursor.fetchall()
    return result or []

def is_admin(user_id):
    """Check if the user is an admin. Superadmin's admin status is unchangeable."""
    
    # Superadmin check
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

def start(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = update.effective_user.id
    username = update.effective_user.username
    current_time = datetime.now()

    # Handle 'Add User' button press
    if query and query.data.startswith('add_user '):
        # Extract user ID and username from the callback data
        _, new_user_id, new_username = query.data.split(maxsplit=2)

        # Logic to add the user
        try:
            execute_db_query("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (new_user_id, new_username))
            query.edit_message_text(f"User @{new_username} (user_id: {new_user_id}) added successfully.")
            logger.info(f"User added: @{new_username} (user_id: {new_user_id}) by Admin {user_id}")
        except Exception as e:
            logger.error(f"Error adding user @{new_username} (ID: {new_user_id}): {e}")
            query.edit_message_text("Failed to add user. Please try again later.")

        return

    # Time out in seconds (e.g., 300 seconds = 5 minutes)
    timeout = 300

    # Check if the user is already registered
    existing_user = execute_db_query("SELECT user_id FROM users WHERE user_id = ?", (user_id,), fetch_one=True)
    if existing_user:
        logger.info(f"User @{username} (ID: {user_id}) invoked /start command")
        update.message.reply_text("You are already registered.")
        return

    # Check if the user has used the start command recently
    last_time = last_start_command.get(user_id)
    if last_time and (current_time - last_time).total_seconds() < timeout:
        update.message.reply_text("Please wait before using the /start command again.")
        return

    # Update the last command time
    last_start_command[user_id] = current_time

    # Send user info to the admin
    try:
        keyboard = [[InlineKeyboardButton("Add User", callback_data=f"add_user {user_id} {username}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        context.bot.send_message(
            chat_id=admin_user_id,
            text=f"New user alert!\n\nUser ID: {user_id}\nUsername: @{username}\n\nClick the button below to add them.",
            reply_markup=reply_markup
        )
        update.message.reply_text("Your information has been sent to the admin for registration.")
    except Exception as e:
        logger.error(f"Error notifying admin: {e}")
        update.message.reply_text("Failed to send your information to the admin. Please try again later.")

@admin_required
def admin_commands(update: Update, context: CallbackContext) -> None:
    message_text = "Admin User Management:\n\n"
    message_text += "/add_user [user_id] [username] - Add a new user\n"
    message_text += "/make_admin [user_id] - Make a user an admin\n"
    message_text += "/delist_user [user_id] - Delist a user\n"
    message_text += "/remove_user [user_id] - Remove a user\n"
    message_text += "/revoke_admin [user_id] - Revoke admin status\n"
    message_text += "/view_users - View all users and their status\n"
    message_text += "/history - View all booking history for the past 2 weeks\n"
    message_text += "/cancel_booking - Cancel a booking by its id\n"
    message_text += "/view_rooms - View all rooms and desks\n"
    message_text += "/set_room_availability [room_id] [room_availability] - Set room availability\n"
    message_text += "/set_desk_availability [desk_id] [desk_availability] - Set desk availability\n"
    message_text += "/add_room [room_name] - Add a new room\n"
    message_text += "/add_desk [room_id] [desk_number] - Add a new desk\n"
    message_text += "/remove_room [room_id] - Remove a room\n"
    message_text += "/remove_desk [room_id] [desk_number] - Remove a desk\n"
    message_text += "/edit_room_name [room_id] [new_room_name] - Edit a room name\n"
    message_text += "/edit_plan_url [room_id] [new_plan_url] - Edit a room plan URL\n"
    message_text += "/edit_desk_number [desk_id] [new_desk_number] - Edit a desk number\n"
    message_text += "/initialize_rooms_config - Initialize rooms and desks\n"
    
    update.message.reply_text(message_text)

@user_required
def help_command(update: Update, context: CallbackContext) -> None:
    message_text = (f"Contact @{admin_username} if you need help.")

    update.message.reply_text(message_text)

@admin_required
def initialize_rooms_config(update: Update, context: CallbackContext) -> None:
    try:
        rooms_config.initialize_rooms_and_desks()  # Call your function to initialize rooms and desks
        update.message.reply_text("Rooms and desks have been initialized successfully.")
    except Exception as e:
        logger.error(f"Error in initializing rooms and desks: {e}")
        update.message.reply_text("Failed to initialize rooms and desks. Please try again later.")

@admin_required
def add_room(update: Update, context: CallbackContext) -> None:
    if not context.args:
        update.message.reply_text("Usage: /add_room [room_name]")
        logger.info(f"Invalid add_room command usage by Admin {update.effective_user.id}")
        return

    room_name = ' '.join(context.args)

    # Check if the room name already exists
    existing_room = execute_db_query("SELECT room_id FROM rooms WHERE room_name = ?", (room_name,), fetch_one=True)
    if existing_room:
        update.message.reply_text(f"Room: '{room_name}' already exists.")
        return

    query = "INSERT INTO rooms (room_name) VALUES (?)"
    try:
        execute_db_query(query, (room_name,))
        update.message.reply_text(f"Room '{room_name}' added successfully.")
        logger.info(f"Room: '{room_name}' added successfully by Admin {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error adding room '{room_name}': {e}")
        update.message.reply_text("Failed to add room. Please try again later.")

@admin_required
def add_desk(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 2:
        update.message.reply_text("Usage: /add_desk [room_id] [desk_number]")
        return

    room_id, desk_number = context.args

    # Check if the room exists
    if not execute_db_query("SELECT room_id FROM rooms WHERE room_id = ?", (room_id,), fetch_one=True):
        update.message.reply_text(f"No room found with room_id {room_id}.")
        return

    # Check if the desk number already exists in the room
    if execute_db_query("SELECT desk_id FROM desks WHERE room_id = ? AND desk_number = ?", (room_id, desk_number), fetch_one=True):
        update.message.reply_text(f"Desk number {desk_number} already exists in the room (room_id {room_id}).")
        return

    try:
        execute_db_query("INSERT INTO desks (room_id, desk_number) VALUES (?, ?)", (room_id, desk_number))
        update.message.reply_text(f"Desk {desk_number} added successfully to room (room_id {room_id}).")
    except Exception as e:
        logger.error(f"Error adding desk {desk_number} to the room (room_id {room_id}): {e}")
        update.message.reply_text("Failed to add desk. Please try again later.")

@admin_required
def edit_room_name(update: Update, context: CallbackContext) -> None:
    if len(context.args) < 2:
        update.message.reply_text("Usage: /edit_room_name [room_id] [new_room_name]")
        return

    room_id, new_room_name = context.args[0], ' '.join(context.args[1:])

    # Check if new room name already exists
    if execute_db_query("SELECT room_id FROM rooms WHERE room_name = ?", (new_room_name,), fetch_one=True):
        update.message.reply_text(f"Another room with the name '{new_room_name}' already exists.")
        return

    # Update room name
    try:
        execute_db_query("UPDATE rooms SET room_name = ? WHERE room_id = ?", (new_room_name, room_id))
        update.message.reply_text(f"Room (room_id {room_id}) name updated successfully to '{new_room_name}'.")
    except Exception as e:
        logger.error(f"Error updating room name: {e}")
        update.message.reply_text("Failed to update room name. Please try again later.")

@admin_required
def edit_plan_url(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 2:
        update.message.reply_text("Usage: /edit_plan_url [room_id] [new_plan_url]")
        return

    room_id, new_plan_url = context.args

    # Check if the room exists
    if not execute_db_query("SELECT room_id FROM rooms WHERE room_id = ?", (room_id,), fetch_one=True):
        update.message.reply_text(f"No room found with room_id {room_id}.")
        return

    # Update plan URL
    try:
        execute_db_query("UPDATE rooms SET plan_url = ? WHERE room_id = ?", (new_plan_url, room_id))
        update.message.reply_text(f"Plan URL updated successfully for room (room_id {room_id}).")
    except Exception as e:
        logger.error(f"Error updating plan URL for room (room_id {room_id}): {e}")
        update.message.reply_text("Failed to update plan URL. Please try again later.")

@admin_required
def edit_desk_number(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 2:
        update.message.reply_text("Usage: /edit_desk_number [desk_id] [new_desk_number]")
        return

    desk_id, new_desk_number = context.args

    # Check if the desk exists and get its room_id
    desk_info = execute_db_query("SELECT room_id FROM desks WHERE desk_id = ?", (desk_id,), fetch_one=True)
    if not desk_info:
        update.message.reply_text(f"No desk found with desk_id {desk_id}.")
        return

    room_id = desk_info[0]

    # Check if new desk number already exists in the same room
    if execute_db_query("SELECT desk_id FROM desks WHERE room_id = ? AND desk_number = ?", (room_id, new_desk_number), fetch_one=True):
        update.message.reply_text(f"Desk (desk_number {new_desk_number}) already exists in room (room_id{room_id}).")
        return

    # Update desk number
    try:
        execute_db_query("UPDATE desks SET desk_number = ? WHERE desk_id = ?", (new_desk_number, desk_id))
        update.message.reply_text(f"Desk number updated successfully to {new_desk_number} for desk (desk_id {desk_id}).")
    except Exception as e:
        logger.error(f"Error updating desk number for desk (desk_id {desk_id}): {e}")
        update.message.reply_text("Failed to update desk number. Please try again later.")

@admin_required
def remove_room(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 1:
        update.message.reply_text("Usage: /remove_room [room_id]")
        return

    room_id = context.args[0]

    # Check if the room exists
    if not execute_db_query("SELECT room_id FROM rooms WHERE room_id = ?", (room_id,), fetch_one=True):
        update.message.reply_text(f"No room found with room_id {room_id}.")
        return

    try:
        # Delete the room and associated desks and bookings
        execute_db_query("DELETE FROM bookings WHERE desk_id IN (SELECT desk_id FROM desks WHERE room_id = ?)", (room_id,))
        execute_db_query("DELETE FROM desks WHERE room_id = ?", (room_id,))
        execute_db_query("DELETE FROM rooms WHERE room_id = ?", (room_id,))
        update.message.reply_text(f"Room (room_id {room_id}) and all associated desks and bookings have been removed.")
    except Exception as e:
        logger.error(f"Error removing room (room_id {room_id}): {e}")
        update.message.reply_text("Failed to remove room. Please try again later.")

@admin_required
def remove_desk(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 2:
        update.message.reply_text("Usage: /remove_desk [room_id] [desk_number]")
        return

    room_id, desk_number = context.args

    # Check if the desk exists
    desk = execute_db_query("SELECT desk_id FROM desks WHERE room_id = ? AND desk_number = ?", (room_id, desk_number), fetch_one=True)
    if not desk:
        update.message.reply_text(f"No desk with desk_number {desk_number} found in room (room_id {room_id}).")
        return

    try:
        # Delete the desk and associated bookings
        execute_db_query("DELETE FROM bookings WHERE desk_id = ?", (desk[0],))
        execute_db_query("DELETE FROM desks WHERE desk_id = ?", (desk[0],))
        update.message.reply_text(f"Desk {desk_number} in room (room_id {room_id}) and all associated bookings have been removed.")
    except Exception as e:
        logger.error(f"Error removing desk {desk_number} from room (room_id {room_id}): {e}")
        update.message.reply_text("Failed to remove desk. Please try again later.")

@admin_required
def add_user(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 2:
        update.message.reply_text("Usage: /add_user [user_id] [username]")
        logger.info(f"Invalid add_user command usage by {update.effective_user.id}")
        return

    new_user_id, username = context.args
    
    # Check if the user already exists
    existing_user = execute_db_query("SELECT user_id FROM users WHERE user_id = ?", (new_user_id,), fetch_one=True)
    if existing_user:
        update.message.reply_text(f"User with user_id {new_user_id} already exists.")
        return

    query = "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)"
    try:
        execute_db_query(query, (new_user_id, username))
        update.message.reply_text(f"User @{username} (user_id: {new_user_id}) added successfully.")
        logger.info(f"User added: @{username} (user_id: {new_user_id}) by Admin {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error adding user {username} (ID: {new_user_id}): {e}")
        update.message.reply_text("Failed to add user. Please try again later.")

@admin_required
def remove_user(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 1:
        update.message.reply_text("Usage: /remove_user [user_id]")
        logger.info(f"Invalid remove_user command usage by Admin {update.effective_user.id}")
        return

    remove_user_id = context.args[0]
    
    # Prevent removing superadmin
    if remove_user_id == admin_user_id:
        update.message.reply_text("Superadmin cannot be removed.")
        return

    # Check if the user exists
    existing_user = execute_db_query("SELECT user_id FROM users WHERE user_id = ?", (remove_user_id,), fetch_one=True)
    if not existing_user:
        update.message.reply_text(f"No user found with user_id {remove_user_id}.")
        return
    
    query = "DELETE FROM users WHERE user_id = ?"
    try:
        execute_db_query(query, (remove_user_id,))
        update.message.reply_text(f"User with ID {remove_user_id} removed successfully.")
        logger.info(f"User with ID {remove_user_id} removed successfully by Admin {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error removing user with ID {remove_user_id}: {e}")
        update.message.reply_text("Failed to remove user. Please try again later.")

@admin_required
def make_admin(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 1:
        update.message.reply_text("Usage: /make_admin [user_id]")
        logger.info(f"Invalid make_admin command usage by Admin {update.effective_user.id}")
        return

    user_id_to_admin = context.args[0]
    
    # Check if the user exists
    existing_user = execute_db_query("SELECT user_id FROM users WHERE user_id = ?", (user_id_to_admin,), fetch_one=True)
    if not existing_user:
        update.message.reply_text(f"No user found with user_id {user_id_to_admin}.")
        return
    
    query = "UPDATE users SET is_admin = 1 WHERE user_id = ?"
    try:
        execute_db_query(query, (user_id_to_admin,))
        update.message.reply_text("User updated to admin successfully.")
        logger.info(f"User with ID {user_id_to_admin} made an admin successfully by Admin {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error making user with ID {user_id_to_admin} an admin: {e}")
        update.message.reply_text("Failed to update user to admin. Please try again later.")

@admin_required
def revoke_admin(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 1:
        update.message.reply_text("Usage: /revoke_admin [user_id]")
        logger.info(f"Invalid revoke_admin command usage by Admin {update.effective_user.id}")
        return

    user_id_to_revoke = context.args[0]
    
    # Prevent revoking superadmin privileges
    if user_id_to_revoke == admin_user_id:
        update.message.reply_text("Superadmin privileges cannot be revoked.")
        return

    # Check if the user exists
    existing_user = execute_db_query("SELECT user_id FROM users WHERE user_id = ?", (user_id_to_revoke,), fetch_one=True)
    if not existing_user:
        update.message.reply_text(f"No user found with user_id {user_id_to_revoke}.")
        return
    
    query = "UPDATE users SET is_admin = 0 WHERE user_id = ?"
    try:
        execute_db_query(query, (user_id_to_revoke,))
        update.message.reply_text("Admin privileges revoked successfully.")
        logger.info(f"Admin privileges revoked from user with ID {user_id_to_revoke} by Admin {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error revoking admin rights from user with ID {user_id_to_revoke}: {e}")
        update.message.reply_text("Failed to revoke admin privileges. Please try again later.")

@admin_required
def delist_user(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 1:
        update.message.reply_text("Usage: /delist_user [user_id]")
        logger.info(f"Invalid delist_user command usage by Admin {update.effective_user.id}")
        return

    user_id_to_delist = context.args[0]
    
    # Check if the user exists
    existing_user = execute_db_query("SELECT user_id FROM users WHERE user_id = ?", (user_id_to_delist,), fetch_one=True)
    if not existing_user:
        update.message.reply_text(f"No user found with user_id {user_id_to_delist}.")
        return
    
    query = "UPDATE users SET is_delisted = 1 WHERE user_id = ?"
    try:
        execute_db_query(query, (user_id_to_delist,))
        update.message.reply_text("User delisted successfully.")
        logger.info(f"User with ID {user_id_to_delist} delisted successfully by Admin {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error delisting user with ID {user_id_to_delist}: {e}")
        update.message.reply_text("Failed to delist user. Please try again later.")

@admin_required
def list_user(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 1:
        update.message.reply_text("Usage: /list_user [user_id]")
        logger.info(f"Invalid list_user command usage by Admin {update.effective_user.id}")
        return

    user_id_to_list = context.args[0]
    
    # Check if the user exists
    existing_user = execute_db_query("SELECT user_id FROM users WHERE user_id = ?", (user_id_to_list,), fetch_one=True)
    if not existing_user:
        update.message.reply_text(f"No user found with user_id {user_id_to_list}.")
        return

    query = "UPDATE users SET is_delisted = 0 WHERE user_id = ?"
    try:
        execute_db_query(query, (user_id_to_list,))
        update.message.reply_text("User listed successfully.")
        logger.info(f"User with ID {user_id_to_list} listed successfully by Admin {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error listing user with ID {user_id_to_list}: {e}")
        update.message.reply_text("Failed to list user. Please try again later.")

@admin_required
def view_users(update: Update, context: CallbackContext) -> None:
    query = "SELECT user_id, username, is_admin, is_delisted FROM users"
    try:
        users = execute_db_query(query, fetch_all=True)  # Make sure to fetch all records

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
        logger.error(f"Error viewing users by Admin {update.effective_user.id}: {e}")
        update.message.reply_text("Failed to retrieve the user list. Please try again later.")

@admin_required
def cancel_booking_by_id(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 1 or not context.args[0].isdigit():
        update.message.reply_text("Usage: /cancel_booking [booking_id]")
        logger.info(f"Invalid cancel_booking command usage by Admin {update.effective_user.id}")
        return

    booking_id = context.args[0]
    
    # Check if the booking exists
    existing_booking = execute_db_query("SELECT booking_id FROM bookings WHERE booking_id = ?", (booking_id,), fetch_one=True)
    if not existing_booking:
        update.message.reply_text(f"No booking found with booking_id: {booking_id}.")
        return
    
    query = "DELETE FROM bookings WHERE booking_id = ?"
    try:
        execute_db_query(query, (booking_id,))
        update.message.reply_text(f"Booking (booking_id: {booking_id}) cancelled successfully.")
        logger.info(f"Booking (booking_id: {booking_id}) cancelled successfully by Admin {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error cancelling booking (booking_id: {booking_id}) by Admin {update.effective_user.id}: {e}")
        update.message.reply_text("Failed to cancel the booking. Please try again later.")

@admin_required
def view_rooms(update: Update, context: CallbackContext) -> None:
    """Fetches and displays room and desk data from the database."""
    try:
        # Fetch room data
        rooms_query = "SELECT room_id, room_name, room_availability, room_add_info, plan_url FROM rooms"
        rooms = execute_db_query(rooms_query, fetch_all=True)

        message_text = "Rooms and Desks Information:\n\n"
        for room_id, room_name, room_availability, room_add_info, plan_url in rooms:
            # Fetch desk data for each room
            desks_query = "SELECT desk_id, desk_number, desk_availability, desk_add_info FROM desks WHERE room_id = ?"
            desks = execute_db_query(desks_query, (room_id,), fetch_all=True)

            # Format room data
            message_text += f"room_name: {room_name}, room_id: {room_id}, room_availability: {room_availability}, room_add_info: {room_add_info}, plan_url: {plan_url}\n"

            # Format desk data
            for desk_id, desk_number, desk_availability, desk_add_info in desks:
                message_text += f"desk_number: {desk_number}, desk_id: {desk_id}, desk_availability: {desk_availability}, desk_add_info: {desk_add_info}\n"
            message_text += "\n"

        update.message.reply_text(message_text)
    except Exception as e:
        logger.error(f"Error in view_rooms: {e}")
        update.message.reply_text("An error occurred while retrieving room and desk information. Please try again later.")

@admin_required
def set_room_availability(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 2:
        update.message.reply_text("Usage: /set_room_availability [room_id] [room_availability]")
        return

    room_id, room_availability = context.args
    try:
        # Validate room_availability
        if room_availability not in ["0", "1"]:
            update.message.reply_text("Room availability must be 0 (unavailable) or 1 (available).")
            return

        # Check if the room exists
        room_exists = execute_db_query("SELECT room_id FROM rooms WHERE room_id = ?", (room_id,), fetch_one=True)
        if not room_exists:
            update.message.reply_text(f"No room found with room_id {room_id}.")
            return

        room_availability = int(room_availability)
        update_query = "UPDATE rooms SET room_availability = ? WHERE room_id = ?"
        execute_db_query(update_query, (room_availability, room_id))
        update.message.reply_text(f"Room availability updated successfully for room ID {room_id}.")
    except Exception as e:
        logger.error(f"Error updating room availability: {e}")
        update.message.reply_text("Failed to update room availability. Please try again later.")

@admin_required
def set_desk_availability(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 2:
        update.message.reply_text("Usage: /set_desk_availability [desk_id] [desk_availability]")
        return

    desk_id, desk_availability = context.args
    try:
        # Validate desk_availability
        if desk_availability not in ["0", "1"]:
            update.message.reply_text("Desk availability must be 0 (unavailable) or 1 (available).")
            return

        # Check if the desk exists
        desk_exists = execute_db_query("SELECT desk_id FROM desks WHERE desk_id = ?", (desk_id,), fetch_one=True)
        if not desk_exists:
            update.message.reply_text(f"No desk found with desk_id {desk_id}.")
            return

        desk_availability = int(desk_availability)
        update_query = "UPDATE desks SET desk_availability = ? WHERE desk_id = ?"
        execute_db_query(update_query, (desk_availability, desk_id))
        update.message.reply_text(f"Desk availability updated successfully for desk ID {desk_id}.")
    except Exception as e:
        logger.error(f"Error updating desk availability: {e}")
        update.message.reply_text("Failed to update desk availability. Please try again later.")

def generate_dates():
    dates = []
    current_date = datetime.now()
    while len(dates) < 5:  # to get next 5 working days
        if current_date.weekday() < 5:  # 0-4 corresponds to Monday-Friday
            formatted_date = current_date.strftime('%d.%m.%Y (%a)')
            dates.append(formatted_date)
        current_date += timedelta(days=1)
    return dates

def button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()

    if query.data == 'cancelbutton':
        query.edit_message_text("Process cancelled.")
        return

    if query.data == 'book_table':
        dates = generate_dates()
        keyboard = [[InlineKeyboardButton(date, callback_data=f'date_{date}')] for date in dates]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(text="Select a date:", reply_markup=reply_markup)
    elif query.data.startswith('date_'):
        selected_date = query.data.split('_')[1]
        context.user_data['selected_date'] = selected_date
    elif query.data.startswith('table_'):
        table_id = int(query.data.split('_')[1])
        process_booking(update, context, table_id)
    # Add handling for other callback_data options

@user_required
def start_booking_process(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)

    # Check if the user is delisted
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_delisted FROM users WHERE user_id = ?", (user_id,))
            is_delisted = cursor.fetchone()[0]

        if is_delisted:
            update.message.reply_text("You are delisted and cannot use this bot.")
            return

        # Generate booking dates and create keyboard markup
        dates = generate_dates()
        keyboard = [[InlineKeyboardButton(date, callback_data=f'date_{date}')] for date in dates]
        
        # Add a Cancel button
        keyboard.append([InlineKeyboardButton("Cancel", callback_data='cancelbutton')])        
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.message.reply_text("Select a date to book:", reply_markup=reply_markup)
        # The room options should not be sent here. They will be sent after a date is selected.

    except sqlite3.Error as e:
        logging.error(f"Database error in start_booking_process: {e}")
        update.message.reply_text("An error occurred. Please try again later.")

def date_selected(update: Update, context: CallbackContext) -> None:
    try:
        query = update.callback_query
        query.answer()

        # Extract the date from the callback data
        selected_date = query.data.split('_')[1]
        # Save the selected date in the user's context
        context.user_data['selected_date'] = selected_date

        user_id = str(update.effective_user.id)

        # Check if user has already booked for the selected date
        existing_booking_query = "SELECT booking_id FROM bookings WHERE user_id = ? AND booking_date = ?" 
        existing_booking = execute_db_query(existing_booking_query, (user_id, selected_date))

        if existing_booking:
            # Inform user they have already booked a desk for this date
            query.edit_message_text(f"You have already booked a desk for {selected_date}. Please choose another date or cancel your existing booking.")
            return

        # Retrieve the list of available rooms from the database
        rooms = execute_db_query("SELECT room_id, room_name FROM rooms", fetch_all=True)
        if rooms:
            # Create a list of buttons for each room
            keyboard = [[InlineKeyboardButton(room[1], callback_data=f"room_{room[0]}")] for room in rooms]
            
            # Add a Cancel button
            keyboard.append([InlineKeyboardButton("Cancel", callback_data='cancelbutton')])

            # Create an inline keyboard markup with the room buttons
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Edit the message text to prompt the user to select a room
            query.edit_message_text(text="Select a room to book:", reply_markup=reply_markup)
        else:
            # Log that no rooms data was found and inform the user
            logger.info("No rooms data found.")
            query.edit_message_text(text="No rooms available to book.")
    except Exception as e:
        # Log any exceptions that occur and inform the user
        logger.error(f"Error in date_selected: {e}")
        query.edit_message_text("An error occurred. Please try again.")

def room_selected(update: Update, context: CallbackContext) -> None:
    update.callback_query.answer()

    selected_room_id = int(update.callback_query.data.split('_')[1])
    context.user_data['selected_room_id'] = selected_room_id
    booking_date = context.user_data['selected_date']

    # Get the room name and plan URL. Only select available rooms
    room_query = """
        SELECT room_name, plan_url FROM rooms 
        WHERE room_id = ? AND room_availability = 1
    """
    room_result = execute_db_query(room_query, (selected_room_id,), fetch_one=True)    
    
    if not room_result:
        update.callback_query.edit_message_text("Selected room is not available. Please choose another room.")
        return

    room_name, plan_url = room_result
    plan_url= plan_url if plan_url else "https://your-default-image-url.jpg"
    text_with_image_link = f"Select a desk to book in {room_name} according to the [room plan]({plan_url}):"

    # Retrieve available desks in the selected room
    desk_query = """
        SELECT d.desk_id, d.desk_number, 
            CASE WHEN b.booking_id IS NOT NULL THEN 1 ELSE 0 END as is_booked
        FROM desks d
        LEFT JOIN bookings b ON d.desk_id = b.desk_id AND b.booking_date = ?
        WHERE d.room_id = ? AND d.desk_availability = 1
    """
    desks = execute_db_query(desk_query, (booking_date, selected_room_id), fetch_all=True)

    if desks:
        keyboard = [[InlineKeyboardButton(f"{'✅' if is_booked == 0 else '🚫'} Desk {desk_number}", callback_data=f'desk_{desk_id}')]
                    for desk_id, desk_number, is_booked in desks]
        
        # Add a Cancel button
        keyboard.append([InlineKeyboardButton("Cancel", callback_data='cancelbutton')])

        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.callback_query.edit_message_text(text=text_with_image_link, reply_markup=reply_markup, parse_mode='MarkdownV2')
    else:
        update.callback_query.edit_message_text(text="No desks available to book in the selected room.")

def desk_selected(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()

    selected_desk_id = int(query.data.split('_')[1])
    booking_date = context.user_data['selected_date']

    # Retrieve the desk number from the database
    desk_number_query = "SELECT desk_number FROM desks WHERE desk_id = ?"
    desk_number_result = execute_db_query(desk_number_query, (selected_desk_id,), fetch_one=True)
    desk_number = desk_number_result[0] if desk_number_result else "Unknown"

    # Check if the desk is available
    if check_desk_availability(selected_desk_id, booking_date):
        # Desk is available, proceed with booking
        user_id = update.effective_user.id
        insert_query = "INSERT INTO bookings (user_id, booking_date, desk_id) VALUES (?, ?, ?)"
        execute_db_query(insert_query, (user_id, booking_date, selected_desk_id))
        response_text = f"Desk {desk_number} successfully booked for {booking_date}."
    else:
        # Desk is not available
        response_text = f"Desk {desk_number} is not available on {booking_date}. Please choose another desk."

    query.edit_message_text(response_text)

def check_desk_availability(desk_id, booking_date):
    # Check if the selected desk is already booked on the given date
    availability_query = "SELECT booking_id FROM bookings WHERE desk_id = ? AND booking_date = ?"
    try:
        result = execute_db_query(availability_query, (desk_id, booking_date), fetch_one=True)
        return result is None  # If there's no result, the desk is available
    except Exception as e:
        logger.error(f"Error checking desk availability: {e}")
        # In case of an error, you may want to handle it appropriately
        return False

def process_booking(update: Update, context: CallbackContext, desk_id: int) -> None:
    booking_date = context.user_data['selected_date']
    user_id = update.effective_user.id
    username = "@" + update.effective_user.username if update.effective_user.username else "Unknown"

    try:
        # Check if the user already has a booking on the selected date
        check_query = "SELECT * FROM bookings WHERE booking_date = ? AND user_id = ?"
        existing_booking = execute_db_query(db_path, check_query, (booking_date, user_id), fetch_one=True)
        
        if existing_booking:
            response_text = "You have already booked a desk for this date. Please choose another date or cancel your existing booking."
        else:
            # Check if the selected desk is available
            availability_query = "SELECT username FROM bookings WHERE booking_date = ? AND desk_id = ?"
            existing_desk_booking = execute_db_query(db_path, availability_query, (booking_date, desk_id), fetch_one=True)

            if existing_desk_booking is None:
                insert_query = "INSERT INTO bookings (user_id, username, booking_date, desk_id) VALUES (?, ?, ?, ?)"
                execute_db_query(db_path, insert_query, (user_id, username, booking_date, desk_id))
                response_text = f"Successfully booked Desk {desk_id} for {booking_date}."
            else:
                existing_username = existing_desk_booking[0]
                response_text = f"This desk is already booked for the selected day by {existing_username}. Please choose another desk."

        # Respond according to the type of update
        if update.callback_query:
            update.callback_query.edit_message_text(response_text)
        else:
            update.message.reply_text(response_text)
    except Exception as e:
        logger.error(f"Error in process_booking: {e}")
        update.message.reply_text("An error occurred w hile processing your booking. Please try again later.")

@user_required
def display_bookings_for_cancellation(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        query = """
            SELECT b.booking_id, SUBSTR(b.booking_date, 1, 10) as formatted_date, d.desk_number
            FROM bookings b
            JOIN desks d ON b.desk_id = d.desk_id
            WHERE b.user_id = ? AND
                  strftime('%Y-%m-%d', SUBSTR(b.booking_date, 7, 4) || '-' || 
                  SUBSTR(b.booking_date, 4, 2) || '-' || 
                  SUBSTR(b.booking_date, 1, 2)) >= strftime('%Y-%m-%d', ?)
            ORDER BY strftime('%Y-%m-%d', SUBSTR(b.booking_date, 7, 4) || '-' || 
                     SUBSTR(b.booking_date, 4, 2) || '-' || 
                     SUBSTR(b.booking_date, 1, 2))
        """
        
        bookings = execute_db_query(query, (user_id, today), fetch_all=True)
        
        if bookings:
            keyboard = [[InlineKeyboardButton(f"Cancel Desk {desk_number} on {formatted_date}", callback_data=f'cancel_{booking_id}')] 
                        for booking_id, formatted_date, desk_number in bookings]
            
            # Add a Cancel button
            keyboard.append([InlineKeyboardButton("Cancel", callback_data='cancelbutton')])

            reply_markup = InlineKeyboardMarkup(keyboard)
            response_text = "Select a booking to cancel:" if bookings else "You have no upcoming bookings to cancel."
            if update.callback_query:
                update.callback_query.edit_message_text(response_text, reply_markup=reply_markup)
            else:
                update.message.reply_text(response_text, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error in display_bookings_for_cancellation: {e}")
        update.message.reply_text("An error occurred while retrieving bookings for cancellation. Please try again later.")

def cancel_booking(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    booking_id = query.data.split('_')[1]
    user_id = update.effective_user.id

    try:
        # Execute the delete query using the centralized database function
        delete_query = "DELETE FROM bookings WHERE booking_id = ? AND user_id = ?"
        execute_db_query(delete_query, (booking_id, user_id))

        # Inform the user about the successful cancellation
        query.edit_message_text(f"Booking cancelled successfully.")
    except Exception as e:
        logger.error(f"Error in cancel_booking: {e}")
        query.edit_message_text("Failed to cancel the booking. Please try again later.")

@user_required
def view_my_bookings(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    username = update.effective_user.username or "Unknown User"

    # Define the time range
    today = datetime.now().strftime('%d.%m.%Y (%a)')
    next_four_workdays = (datetime.now() + timedelta(days=7)).strftime('%d.%m.%Y (%a)')

    try:
        sql_query = """
            SELECT b.booking_date, r.room_name, d.desk_number
            FROM bookings b
            INNER JOIN desks d ON b.desk_id = d.desk_id
            INNER JOIN rooms r ON d.room_id = r.room_id
            WHERE b.user_id = ? AND 
                  b.booking_date BETWEEN ? AND ?
            ORDER BY b.booking_date
        """
        bookings = execute_db_query(sql_query, (user_id, today, next_four_workdays), fetch_all=True)

        if bookings:
            message_text = f"Your bookings, @{username}:\n\n"
            for booking_date, room_name, desk_number in bookings:
                message_text += f"*{booking_date}*: {room_name}, Desk {desk_number}\n"
        else:
            message_text = "You have no bookings."

        update.message.reply_text(message_text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in view_my_bookings: {e}")
        update.message.reply_text("An error occurred while retrieving your bookings. Please try again later.")

@user_required
def view_all_bookings(update: Update, context: CallbackContext) -> None:
    # Define the time range
    today = datetime.now().strftime('%d.%m.%Y (%a)')
    next_four_workdays = (datetime.now() + timedelta(days=7)).strftime('%d.%m.%Y (%a)')

    try:
        bookings_query = """
            SELECT b.booking_date, r.room_name, d.desk_number, b.user_id
            FROM bookings b
            INNER JOIN desks d ON b.desk_id = d.desk_id
            INNER JOIN rooms r ON d.room_id = r.room_id
            WHERE b.booking_date BETWEEN ? AND ?
            ORDER BY b.booking_date, r.room_name, d.desk_number
        """
        bookings = execute_db_query(bookings_query, (today, next_four_workdays), fetch_all=True)

        users_query = "SELECT user_id, username FROM users"
        users = execute_db_query(users_query, fetch_all=True)
        user_dict = {user[0]: user[1] for user in users}

        if bookings:
            organized_bookings = {}
            for booking_date, room_name, desk_number, user_id in bookings:
                user_name = user_dict.get(user_id, "Unknown User")
                date_room_key = (booking_date, room_name)
                if date_room_key not in organized_bookings:
                    organized_bookings[date_room_key] = []
                organized_bookings[date_room_key].append(f"Desk {desk_number}, @{user_name}")

            message_text = "All bookings:\n\n"
            last_date = None
            for (booking_date, room_name), desks in organized_bookings.items():
                if last_date != booking_date:
                    if last_date is not None:
                        message_text += "\n"  # Add extra newline for separation between dates
                    message_text += f"*{booking_date}*:\n\n"
                    last_date = booking_date
                    first_room = True
                else:
                    first_room = False

                if not first_room:
                    message_text += "\n"  # Separate different rooms on the same date
                message_text += f"{room_name}:\n" + "\n".join(desks) + "\n"
        else:
            message_text = "There are no bookings."

        update.message.reply_text(message_text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in view_all_bookings: {e}")
        update.message.reply_text("An error occurred while retrieving bookings. Please try again later.")

@admin_required
def view_booking_history(update: Update, context: CallbackContext) -> None:
    two_weeks_ago = (datetime.now() - timedelta(days=14)).strftime('%d.%m.%Y (%a)')
    next_four_workdays = (datetime.now() + timedelta(days=7)).strftime('%d.%m.%Y (%a)')

    try:
        # Fetch users from the database
        users_query = "SELECT user_id, username FROM users"
        users = execute_db_query(users_query, fetch_all=True)
        user_dict = {user[0]: user[1] for user in users}

        # Fetch bookings from the database
        bookings_query = """
            SELECT b.booking_id, b.booking_date, r.room_name, d.desk_number, b.user_id
            FROM bookings b
            INNER JOIN desks d ON b.desk_id = d.desk_id
            INNER JOIN rooms r ON d.room_id = r.room_id
            WHERE b.booking_date BETWEEN ? AND ?
            ORDER BY b.booking_date, r.room_name, d.desk_number
        """
        
        bookings = execute_db_query(bookings_query, (two_weeks_ago, next_four_workdays), fetch_all=True)

        users_query = "SELECT user_id, username FROM users"
        users = execute_db_query(users_query, fetch_all=True)
        user_dict = {user[0]: user[1] for user in users}

        if bookings:
            organized_bookings = {}
            for booking_id, booking_date, room_name, desk_number, user_id in bookings:
                user_name = user_dict.get(user_id, "Unknown User")
                date_room_key = (booking_date, room_name)
                if date_room_key not in organized_bookings:
                    organized_bookings[date_room_key] = []
                organized_bookings[date_room_key].append(f"Desk {desk_number}, @{user_name}, id: {booking_id}")

            message_text = "Booking history:\n\n"
            last_date = None
            for (booking_date, room_name), desks in organized_bookings.items():
                if last_date != booking_date:
                    if last_date is not None:
                        message_text += "\n"  # Add extra newline for separation between dates
                    message_text += f"*{booking_date}*:\n\n"
                    last_date = booking_date
                    first_room = True
                else:
                    first_room = False

                if not first_room:
                    message_text += "\n"  # Separate different rooms on the same date
                message_text += f"{room_name}:\n" + "\n".join(desks) + "\n"
        else:
            message_text = "There are no bookings."

        update.message.reply_text(message_text, parse_mode='Markdown')
        logger.info(f"Admin {update.effective_user.id} viewed booking history.")
    except Exception as e:
        logger.error(f"Error viewing booking history by Admin {update.effective_user.id}: {e}")
        update.message.reply_text("An error occurred while retrieving the booking history.")

def main() -> None:
    initialize_database()  # Make sure tables are created
    initialize_admin_user()  # Add this line to initialize the admin user

    # Create Updater object and pass the bot's token
    updater = Updater(config.BOT_TOKEN, use_context=True)

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # Register command handlers for various functionalities
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("book", start_booking_process)) 
    dispatcher.add_handler(CommandHandler("cancel", display_bookings_for_cancellation))
    dispatcher.add_handler(CommandHandler("my_bookings", view_my_bookings))
    dispatcher.add_handler(CommandHandler("all_bookings", view_all_bookings))
    dispatcher.add_handler(CommandHandler("history", view_booking_history))
    dispatcher.add_handler(CommandHandler("add_user", add_user))
    dispatcher.add_handler(CommandHandler("remove_user", remove_user))
    dispatcher.add_handler(CommandHandler("make_admin", make_admin))
    dispatcher.add_handler(CommandHandler("revoke_admin", revoke_admin))
    dispatcher.add_handler(CommandHandler("delist_user", delist_user))
    dispatcher.add_handler(CommandHandler("list_user", list_user))
    dispatcher.add_handler(CommandHandler("view_users", view_users))
    dispatcher.add_handler(CommandHandler("cancel_booking", cancel_booking_by_id))
    dispatcher.add_handler(CommandHandler("view_rooms", view_rooms))
    dispatcher.add_handler(CommandHandler("set_room_availability", set_room_availability))
    dispatcher.add_handler(CommandHandler("set_desk_availability", set_desk_availability))
    dispatcher.add_handler(CommandHandler("add_room", add_room))
    dispatcher.add_handler(CommandHandler("add_desk", add_desk))
    dispatcher.add_handler(CommandHandler("edit_room_name", edit_room_name))
    dispatcher.add_handler(CommandHandler("edit_plan_url", edit_plan_url))
    dispatcher.add_handler(CommandHandler("edit_desk_number", edit_desk_number))
    dispatcher.add_handler(CommandHandler("remove_room", remove_room))
    dispatcher.add_handler(CommandHandler("remove_desk", remove_desk))
    dispatcher.add_handler(CommandHandler("initialize_rooms_config", initialize_rooms_config))
    dispatcher.add_handler(CommandHandler("admin", admin_commands))
    dispatcher.add_handler(CommandHandler("help", help_command))
    
    # Register CallbackQueryHandler for handling callback queries from inline keyboards
    dispatcher.add_handler(CallbackQueryHandler(date_selected, pattern='^date_'))
    dispatcher.add_handler(CallbackQueryHandler(room_selected, pattern='^room_'))
    dispatcher.add_handler(CallbackQueryHandler(desk_selected, pattern='^desk_'))
    dispatcher.add_handler(CallbackQueryHandler(button, pattern='^(book_table|date_|table_|cancelbutton)'))
    dispatcher.add_handler(CallbackQueryHandler(cancel_booking, pattern='^cancel_'))
    dispatcher.add_handler(CallbackQueryHandler(display_bookings_for_cancellation, pattern='^cancel_booking$'))
    dispatcher.add_handler(CallbackQueryHandler(start, pattern='^add_user '))

    # Start the Bot
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()