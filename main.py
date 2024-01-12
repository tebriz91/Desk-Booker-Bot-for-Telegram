from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext
from datetime import datetime, timedelta
import traceback
import sqlite3
import logging
import time
import pytz
import os
import config

# Use the configurations
admin_user_id = config.ADMIN_USER_ID
admin_username = config.ADMIN_USERNAME
bookings_db_path = config.BOOKINGS_DB_PATH
users_db_path = config.USERS_DB_PATH
log_timezone = config.LOG_TIMEZONE

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
os.makedirs(os.path.dirname(bookings_db_path), exist_ok=True)
os.makedirs(os.path.dirname(users_db_path), exist_ok=True)

# Function to initialize databases
def initialize_databases():
    # Initialize bookings database
    with sqlite3.connect(bookings_db_path) as conn:
        cursor = conn.cursor()

        # Create Rooms table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_name TEXT NOT NULL,
                is_available INTEGER NOT NULL DEFAULT 1,
                additional_info TEXT
            )
        ''')

        # Create Desks table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS desks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL,
                desk_number INTEGER NOT NULL,
                is_available INTEGER NOT NULL DEFAULT 1,
                additional_info TEXT,
                FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE SET NULL
            )
        ''')

        # Create Bookings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                desk_id INTEGER NOT NULL,
                booking_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (desk_id) REFERENCES desks(id) ON DELETE CASCADE
            )
        ''')
        conn.commit()

    # Initialize users database
    with sqlite3.connect(users_db_path) as conn:
        cursor = conn.cursor()

        # Create Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                username TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0,
                is_blacklisted INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()

def initialize_rooms_and_desks():
    with sqlite3.connect(bookings_db_path) as conn:
        cursor = conn.cursor()
        # Retrieve existing rooms
        cursor.execute("SELECT room_name FROM rooms")
        existing_rooms = {room[0] for room in cursor.fetchall()}

        for room in config.ROOMS:
            room_name = room['name']
            room_info = room.get('additional_info', None)
            is_available = 1 if room.get('is_available', True) else 0

            if room_name not in existing_rooms:
                # Insert new room
                cursor.execute("INSERT INTO rooms (room_name, is_available, additional_info) VALUES (?, ?, ?)", 
                               (room_name, is_available, room_info))
                room_id = cursor.lastrowid

                # Insert desks for this room
                for desk_number in range(1, room['desks'] + 1):
                    desk_info = room.get('desk_additional_info', {}).get(desk_number, None)
                    cursor.execute("INSERT INTO desks (room_id, desk_number, is_available, additional_info) VALUES (?, ?, ?, ?)", 
                                   (room_id, desk_number, is_available, desk_info))
        conn.commit()

def initialize_admin_user():
    admin_user_exists = execute_db_query(users_db_path, "SELECT id FROM users WHERE user_id = ?", (config.ADMIN_USER_ID,), fetch_one=True)
    if not admin_user_exists:
        execute_db_query(users_db_path, "INSERT INTO users (user_id, username, is_admin) VALUES (?, ?, 1)", (config.ADMIN_USER_ID, config.ADMIN_USERNAME))
        logger.info(f"Admin user {config.ADMIN_USERNAME} added to the database.")

def execute_db_query(database_path, query, parameters=(), fetch_one=False, fetch_all=False):
    try:
        with sqlite3.connect(database_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, parameters)
            if fetch_one:
                return cursor.fetchone()
            elif fetch_all:
                result = cursor.fetchall()
                logger.info(f"Fetched {len(result)} records: {result}")
                return result
            else:
                conn.commit()
                return cursor.rowcount  # Return the number of rows affected
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        raise

def is_admin(user_id, users_db_path):
    """Check if the user is an admin."""
    query = "SELECT is_admin FROM users WHERE user_id = ?"
    try:
        result = execute_db_query(users_db_path, query, (user_id,), fetch_one=True)
        return result and result[0]
    except Exception as e:
        logger.error(f"Error checking admin status for user {user_id}: {e}")
        return False  # Default to non-admin in case of an error

def admin_required(func):
    def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = str(update.effective_user.id)
        logger.info(f"Admin command '{func.__name__}' invoked by {user_id}")
        if not is_admin(user_id, users_db_path):
            update.message.reply_text("You are not authorized to use this command.")
            return
        return func(update, context, *args, **kwargs)
    return wrapper

def user_required(func):
    def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = str(update.effective_user.id)
        result = execute_db_query(users_db_path, "SELECT id FROM users WHERE user_id = ?", (user_id,), fetch_one=True)
        if not result:
            logger.info(f"Unregistered user with ID {user_id} invoked command '{func.__name__}'")
            update.message.reply_text(f"You need to be registered to use this command. Please contact an admin: @{admin_username}.")
            return
        return func(update, context, *args, **kwargs)
    return wrapper

@admin_required
def manage_users(update: Update, context: CallbackContext) -> None:
    # User is an admin
    message_text = "Admin User Management:\n\n"
    message_text += "/add_user [user_id] [username] - Add a new user\n"
    message_text += "/make_admin [user_id] - Make a user an admin\n"
    message_text += "/blacklist_user [user_id] - Blacklist a user\n"
    message_text += "/remove_user [user_id] - Remove a user\n"
    message_text += "/revoke_admin [user_id] - Revoke admin status\n"
    message_text += "/view_users - View all users and their status\n"
    message_text += "/history - View all booking history for the past 2 weeks\n"
    message_text += "/cancel_booking - Cancel a booking by its id"
    
    update.message.reply_text(message_text)

@admin_required
def add_user(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 2:
        update.message.reply_text("Usage: /add_user [user_id] [username]")
        logger.info(f"Invalid add_user command usage by {update.effective_user.id}")
        return

    new_user_id, username = context.args
    query = "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)"
    try:
        execute_db_query(users_db_path, query, (new_user_id, username))
        update.message.reply_text(f"User {username} added successfully.")
        logger.info(f"User added: {username} (ID: {new_user_id}) by Admin {update.effective_user.id}")
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
    query = "DELETE FROM users WHERE user_id = ?"
    try:
        execute_db_query(users_db_path, query, (remove_user_id,))
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
    query = "UPDATE users SET is_admin = 1 WHERE user_id = ?"
    try:
        execute_db_query(users_db_path, query, (user_id_to_admin,))
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
    query = "UPDATE users SET is_admin = 0 WHERE user_id = ?"
    try:
        execute_db_query(users_db_path, query, (user_id_to_revoke,))
        update.message.reply_text("Admin privileges revoked successfully.")
        logger.info(f"Admin privileges revoked from user with ID {user_id_to_revoke} by Admin {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error revoking admin rights from user with ID {user_id_to_revoke}: {e}")
        update.message.reply_text("Failed to revoke admin privileges. Please try again later.")

@admin_required
def blacklist_user(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 1:
        update.message.reply_text("Usage: /blacklist_user [user_id]")
        logger.info(f"Invalid blacklist_user command usage by Admin {update.effective_user.id}")
        return

    user_id_to_blacklist = context.args[0]
    query = "UPDATE users SET is_blacklisted = 1 WHERE user_id = ?"
    try:
        execute_db_query(users_db_path, query, (user_id_to_blacklist,))
        update.message.reply_text("User blacklisted successfully.")
        logger.info(f"User with ID {user_id_to_blacklist} blacklisted successfully by Admin {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error blacklisting user with ID {user_id_to_blacklist}: {e}")
        update.message.reply_text("Failed to blacklist user. Please try again later.")

@admin_required
def view_users(update: Update, context: CallbackContext) -> None:
    query = "SELECT id, user_id, username, is_admin, is_blacklisted FROM users"
    try:
        users = execute_db_query(users_db_path, query, fetch_all=True)

        message_text = "List of all users:\n\n"
        for user in users:
            status = "Admin" if user[3] else ("Blacklisted" if user[4] else "User")
            username_display = f"@{user[2]}" if user[2] else "N/A"
            message_text += f"ID: {user[0]}, User ID: {user[1]}, Username: {username_display}, Status: {status}\n"

        update.message.reply_text(message_text)
        logger.info(f"Admin {update.effective_user.id} viewed user list.")
    except Exception as e:
        logger.error(f"Error viewing users by Admin {update.effective_user.id}: {e}")
        update.message.reply_text("Failed to retrieve the user list. Please try again later.")

@admin_required
def cancel_booking_by_id(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 1 or not context.args[0].isdigit():
        update.message.reply_text("Usage: /cancel_booking [id]")
        logger.info(f"Invalid cancel_booking command usage by Admin {update.effective_user.id}")
        return

    booking_id = context.args[0]
    query = "DELETE FROM bookings WHERE id = ?"
    try:
        execute_db_query(bookings_db_path, query, (booking_id,))
        update.message.reply_text(f"Booking with ID {booking_id} cancelled successfully.")
        logger.info(f"Booking with ID {booking_id} cancelled successfully by Admin {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error cancelling booking with ID {booking_id} by Admin {update.effective_user.id}: {e}")
        update.message.reply_text("Failed to cancel the booking. Please try again later.")

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

    if query.data == 'book_table':
        dates = generate_dates()
        keyboard = [[InlineKeyboardButton(date, callback_data=f'date_{date}')] for date in dates]
        reply_markup = InlineKeyboardMarkup(keyboard)
        query.edit_message_text(text="Select a date:", reply_markup=reply_markup)
    elif query.data.startswith('date_'):
        selected_date = query.data.split('_')[1]
        context.user_data['selected_date'] = selected_date
        book_time(update, context)
    elif query.data.startswith('table_'):
        table_id = int(query.data.split('_')[1])
        process_booking(update, context, table_id)
    # Add handling for other callback_data options

@user_required
def start_booking_process(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)

    # Check if the user is blacklisted
    try:
        with sqlite3.connect(users_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_blacklisted FROM users WHERE user_id = ?", (user_id,))
            is_blacklisted = cursor.fetchone()[0]

        if is_blacklisted:
            update.message.reply_text("You are blacklisted and cannot use this bot.")
            return

        # Generate booking dates and create keyboard markup
        dates = generate_dates()
        keyboard = [[InlineKeyboardButton(date, callback_data=f'date_{date}')] for date in dates]
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
        existing_booking_query = "SELECT id FROM bookings WHERE user_id = ? AND booking_date = ?"
        existing_booking = execute_db_query(bookings_db_path, existing_booking_query, (user_id, selected_date), fetch_one=True)

        if existing_booking:
            # Inform user they have already booked a desk for this date
            query.edit_message_text(f"You have already booked a desk for {selected_date}. Please choose another date or cancel your existing booking.")
            return

        # Retrieve the list of available rooms from the database
        rooms = execute_db_query(bookings_db_path, "SELECT id, room_name FROM rooms", fetch_all=True)
        if rooms:
            # Create a list of buttons for each room
            keyboard = [[InlineKeyboardButton(room[1], callback_data=f"room_{room[0]}")] for room in rooms]
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

    # Retrieve the list of available desks from the database
    desk_query = """
        SELECT desks.id, desk_number, (SELECT COUNT(*) FROM bookings WHERE desk_id = desks.id AND booking_date = ?) as is_booked
        FROM desks
        WHERE desks.room_id = ?
    """
    desks = execute_db_query(bookings_db_path, desk_query, (booking_date, selected_room_id), fetch_all=True)

    if desks:
        keyboard = [[InlineKeyboardButton(f"{'✅' if not is_booked else '🚫'} Desk {desk_number}", callback_data=f'desk_{desk_id}')]
                    for desk_id, desk_number, is_booked in desks]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.callback_query.edit_message_text(text="Select a desk to book:", reply_markup=reply_markup)
    else:
        update.callback_query.edit_message_text(text="No desks available to book in the selected room.")

def desk_selected(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()

    selected_desk_id = int(query.data.split('_')[1])
    booking_date = context.user_data['selected_date']

    # Retrieve the desk number from the database
    desk_number_query = "SELECT desk_number FROM desks WHERE id = ?"
    desk_number_result = execute_db_query(bookings_db_path, desk_number_query, (selected_desk_id,), fetch_one=True)
    desk_number = desk_number_result[0] if desk_number_result else "Unknown"

    # Check if the desk is available
    if check_desk_availability(selected_desk_id, booking_date):
        # Desk is available, proceed with booking
        user_id = update.effective_user.id
        insert_query = "INSERT INTO bookings (user_id, booking_date, desk_id) VALUES (?, ?, ?)"
        execute_db_query(bookings_db_path, insert_query, (user_id, booking_date, selected_desk_id))
        response_text = f"Desk {desk_number} successfully booked for {booking_date}."
    else:
        # Desk is not available
        response_text = f"Desk {desk_number} is not available on {booking_date}. Please choose another desk."

    query.edit_message_text(response_text)

def check_desk_availability(desk_id, booking_date):
    # Check if the selected desk is already booked on the given date
    availability_query = "SELECT id FROM bookings WHERE desk_id = ? AND booking_date = ?"
    try:
        result = execute_db_query(bookings_db_path, availability_query, (desk_id, booking_date), fetch_one=True)
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
        existing_booking = execute_db_query(bookings_db_path, check_query, (booking_date, user_id), fetch_one=True)
        
        if existing_booking:
            response_text = "You have already booked a desk for this date. Please choose another date or cancel your existing booking."
        else:
            # Check if the selected desk is available
            availability_query = "SELECT username FROM bookings WHERE booking_date = ? AND desk_id = ?"
            existing_desk_booking = execute_db_query(bookings_db_path, availability_query, (booking_date, desk_id), fetch_one=True)

            if existing_desk_booking is None:
                insert_query = "INSERT INTO bookings (user_id, username, booking_date, desk_id) VALUES (?, ?, ?, ?)"
                execute_db_query(bookings_db_path, insert_query, (user_id, username, booking_date, desk_id))
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
        update.message.reply_text("An error occurred while processing your booking. Please try again later.")

@user_required
def display_bookings_for_cancellation(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id

    try:
        today = datetime.now().strftime('%d.%m.%Y')
        logger.info(f"Today's date for comparison: {today}")  # Log the today's date

        query = """
            SELECT b.id, b.booking_date, d.desk_number
            FROM bookings b
            JOIN desks d ON b.desk_id = d.id
            WHERE b.user_id = ? AND
                SUBSTR(b.booking_date, 7, 4) || '-' || 
                SUBSTR(b.booking_date, 4, 2) || '-' || 
                SUBSTR(b.booking_date, 1, 2) >= ?
            ORDER BY 
                SUBSTR(b.booking_date, 7, 4) || '-' || 
                SUBSTR(b.booking_date, 4, 2) || '-' || 
                SUBSTR(b.booking_date, 1, 2)
        """
        logger.info(f"Executing query: {query}")  # Log the query

        bookings = execute_db_query(bookings_db_path, query, (user_id, today), fetch_all=True)
        logger.info(f"Fetched bookings: {bookings}")  # Log fetched bookings

        if bookings:
            keyboard = [[InlineKeyboardButton(f"Cancel Desk {desk_number} on {booking_date}", callback_data=f'cancel_{booking_id}')] 
                        for booking_id, booking_date, desk_number in bookings]
            reply_markup = InlineKeyboardMarkup(keyboard)
            if update.callback_query:
                update.callback_query.edit_message_text("Select a booking to cancel:", reply_markup=reply_markup)
            else:
                update.message.reply_text("Select a booking to cancel:", reply_markup=reply_markup)
        else:
            update.message.reply_text("You have no upcoming bookings to cancel.")
    except Exception as e:
        logger.error(f"Error in display_bookings_for_cancellation: {e}")
        update.message.reply_text("An error occurred while retrieving bookings for cancellation. Please try again later.")

def cancel_booking(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    booking_id = query.data.split('_')[1]
    user_id = update.effective_user.id

    try:
        # Execute the delete query using the centralized database function
        delete_query = "DELETE FROM bookings WHERE id = ? AND user_id = ?"
        execute_db_query(bookings_db_path, delete_query, (booking_id, user_id))

        # Inform the user about the successful cancellation
        query.edit_message_text(f"Booking cancelled successfully.")
    except Exception as e:
        logger.error(f"Error in cancel_booking: {e}")
        query.edit_message_text("Failed to cancel the booking. Please try again later.")

@user_required
def view_my_bookings(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    username = update.effective_user.username or "Unknown User"

    try:
        # Define the query to fetch the user's bookings
        sql_query = """
            SELECT b.booking_date, r.room_name, d.desk_number
            FROM bookings b
            INNER JOIN desks d ON b.desk_id = d.id
            INNER JOIN rooms r ON d.room_id = r.id
            WHERE b.user_id = ?
            ORDER BY SUBSTR(b.booking_date, 7, 4) || '-' || 
                     SUBSTR(b.booking_date, 4, 2) || '-' || 
                     SUBSTR(b.booking_date, 1, 2)
        """
        bookings = execute_db_query(bookings_db_path, sql_query, (user_id,), fetch_all=True)

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
    try:
        # Query to get bookings
        bookings_query = """
            SELECT b.booking_date, r.room_name, d.desk_number, b.user_id
            FROM bookings b
            INNER JOIN desks d ON b.desk_id = d.id
            INNER JOIN rooms r ON d.room_id = r.id
            ORDER BY SUBSTR(b.booking_date, 7, 4) || '-' || 
                     SUBSTR(b.booking_date, 4, 2) || '-' || 
                     SUBSTR(b.booking_date, 1, 2), 
                     r.room_name, d.desk_number
        """
        bookings = execute_db_query(bookings_db_path, bookings_query, fetch_all=True)

        # Query to get user names
        users_query = "SELECT user_id, username FROM users"
        users = execute_db_query(users_db_path, users_query, fetch_all=True)
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
            current_date = ""
            for (booking_date, room_name), desks in organized_bookings.items():
                if current_date != booking_date:
                    current_date = booking_date
                    message_text += f"*{booking_date}*:\n\n"  # Bold the date
                message_text += f"{room_name}:\n" + "\n".join(desks) + "\n\n"
        else:
            message_text = "There are no bookings."

        update.message.reply_text(message_text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in view_all_bookings: {e}")
        update.message.reply_text("An error occurred while retrieving bookings. Please try again later.")

@admin_required
def view_booking_history(update: Update, context: CallbackContext) -> None:
    two_weeks_ago = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')

    try:
        sql_query = """
            SELECT id, booking_date, table_id, username
            FROM bookings 
            WHERE 
                SUBSTR(booking_date, 7, 4) || '-' || 
                SUBSTR(booking_date, 4, 2) || '-' || 
                SUBSTR(booking_date, 1, 2) >= ?
            ORDER BY 
                SUBSTR(booking_date, 7, 4) || '-' || 
                SUBSTR(booking_date, 4, 2) || '-' || 
                SUBSTR(booking_date, 1, 2), table_id
        """
        bookings = execute_db_query(bookings_db_path, sql_query, (two_weeks_ago,), fetch_all=True)

        if bookings:
            bookings_by_date = {}
            for booking_id, booking_date, table_id, username in bookings:
                if booking_date not in bookings_by_date:
                    bookings_by_date[booking_date] = []
                bookings_by_date[booking_date].append(f"Table: {table_id}, User: {username}, ID: {booking_id}")

            message_text = "Booking history for the past two weeks:\n\n"
            for date, bookings_list in bookings_by_date.items():
                message_text += f"{date}\n" + "\n".join(bookings_list) + "\n\n"
        else:
            message_text = "No bookings in the past two weeks."

        update.message.reply_text(message_text)
        logger.info(f"Admin {update.effective_user.id} viewed booking history.")
    except Exception as e:
        logger.error(f"Error viewing booking history by Admin {update.effective_user.id}: {e}")
        update.message.reply_text("An error occurred while retrieving the booking history.")

def main() -> None:
    initialize_databases()  # Make sure tables are created
    initialize_rooms_and_desks()  # Make sure rooms and desks are populated
    initialize_admin_user()  # Add this line to initialize the admin user

    # Create Updater object and pass the bot's token
    updater = Updater(config.BOT_TOKEN, use_context=True)

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # Register command handlers for various functionalities
    dispatcher.add_handler(CommandHandler("book", start_booking_process)) 
    dispatcher.add_handler(CommandHandler("cancel", display_bookings_for_cancellation))
    dispatcher.add_handler(CommandHandler("my_bookings", view_my_bookings))
    dispatcher.add_handler(CommandHandler("all_bookings", view_all_bookings))
    dispatcher.add_handler(CommandHandler("history", view_booking_history))
    dispatcher.add_handler(CommandHandler("add_user", add_user))
    dispatcher.add_handler(CommandHandler("remove_user", remove_user))
    dispatcher.add_handler(CommandHandler("make_admin", make_admin))
    dispatcher.add_handler(CommandHandler("revoke_admin", revoke_admin))
    dispatcher.add_handler(CommandHandler("blacklist_user", blacklist_user))
    dispatcher.add_handler(CommandHandler("view_users", view_users))
    dispatcher.add_handler(CommandHandler("cancel_booking", cancel_booking_by_id))
    dispatcher.add_handler(CommandHandler("admin", manage_users))
    
    # Register CallbackQueryHandler for handling callback queries from inline keyboards
    dispatcher.add_handler(CallbackQueryHandler(date_selected, pattern='^date_'))
    dispatcher.add_handler(CallbackQueryHandler(room_selected, pattern='^room_'))
    dispatcher.add_handler(CallbackQueryHandler(desk_selected, pattern='^desk_'))
    dispatcher.add_handler(CallbackQueryHandler(button, pattern='^(book_table|date_|table_)'))
    dispatcher.add_handler(CallbackQueryHandler(cancel_booking, pattern='^cancel_'))
    dispatcher.add_handler(CallbackQueryHandler(display_bookings_for_cancellation, pattern='^cancel_booking$'))

    # Start the Bot
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()