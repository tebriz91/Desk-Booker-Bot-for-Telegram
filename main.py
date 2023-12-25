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
    with sqlite3.connect(bookings_db_path) as conn:
        cursor = conn.cursor()
        # Create rooms table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_name TEXT
            )
        ''')
        # Create desks table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS desks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER,
                desk_number INTEGER,
                FOREIGN KEY (room_id) REFERENCES rooms(id)
            )
        ''')
        # Update bookings table to reference desks table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER, 
                username TEXT, 
                booking_date DATE, 
                desk_id INTEGER,
                FOREIGN KEY (desk_id) REFERENCES desks(id)
            )
        ''')
        conn.commit()

# Initialize the users database
    with sqlite3.connect(users_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        user_id INTEGER UNIQUE, 
        username TEXT, 
        is_admin INTEGER DEFAULT 0, 
        is_blacklisted INTEGER DEFAULT 0
    )
''')
        # Insert admin record if not exists
        cursor.execute('''
    INSERT INTO users (user_id, username, is_admin, is_blacklisted)
    VALUES (?, ?, 1, 0)
    ON CONFLICT(user_id) DO NOTHING
''', (admin_user_id, admin_username))
        conn.commit()

def initialize_rooms_and_desks():
    with sqlite3.connect(bookings_db_path) as conn:
        cursor = conn.cursor()
        # Retrieve existing rooms
        cursor.execute("SELECT room_name FROM rooms")
        existing_rooms = [room[0] for room in cursor.fetchall()]

        for room in config.ROOMS:
            if room['name'] not in existing_rooms:
                cursor.execute("INSERT INTO rooms (room_name) VALUES (?)", (room['name'],))
                room_id = cursor.lastrowid
                for desk_number in range(1, room['desks'] + 1):
                    cursor.execute("INSERT INTO desks (room_id, desk_number) VALUES (?, ?)", (room_id, desk_number))
        conn.commit()

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
        with sqlite3.connect(users_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE user_id = ?", (user_id,))
            if not cursor.fetchone():
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
    query = update.callback_query
    query.answer()
    
    # Extract the room id from the callback data
    selected_room_id = int(query.data.split('_')[1])
    # Save the selected room id in the user's context
    context.user_data['selected_room_id'] = selected_room_id

    # Retrieve the list of available desks from the database
    desks = execute_db_query(bookings_db_path, "SELECT id, desk_number FROM desks WHERE room_id = ?", (selected_room_id,), fetch_all=True)
    if desks:
        # Create a list of buttons for each desk
        keyboard = [[InlineKeyboardButton(f"Desk {desk[1]}", callback_data=f"desk_{desk[0]}")] for desk in desks]
        # Create an inline keyboard markup with the desk buttons
        reply_markup = InlineKeyboardMarkup(keyboard)
        # Edit the message text to prompt the user to select a desk
        query.edit_message_text(text="Select a desk to book:", reply_markup=reply_markup)
    else:
        # Log that no desks data was found and inform the user
        logger.info(f"No desks data found for room id {selected_room_id}.")
        query.edit_message_text(text="No desks available to book in the selected room.")

def desk_selected(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()

    selected_desk_id = int(query.data.split('_')[1])
    booking_date = context.user_data['selected_date']

    # Check if the desk is available
    if check_desk_availability(selected_desk_id, booking_date):
        # Desk is available, proceed with booking
        user_id = update.effective_user.id
        username = "@" + update.effective_user.username if update.effective_user.username else "Unknown"
        insert_query = "INSERT INTO bookings (user_id, username, booking_date, desk_id) VALUES (?, ?, ?, ?)"
        execute_db_query(bookings_db_path, insert_query, (user_id, username, booking_date, selected_desk_id))
        response_text = f"Desk {selected_desk_id} successfully booked for {booking_date}."
    else:
        # Desk is not available
        response_text = f"Desk {selected_desk_id} is not available on {booking_date}. Please choose another desk."

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

def book_time(update: Update, context: CallbackContext) -> None:
    if 'selected_date' in context.user_data and 'selected_room_id' in context.user_data:
        booking_date = context.user_data['selected_date']
        selected_room_id = context.user_data['selected_room_id']
        user_id = update.effective_user.id

        try:
            # Retrieve the room's configuration, including the number of columns and total desks
            room_config = get_room_config(selected_room_id)  
            desk_columns = room_config['columns']

            # Query to get the booked desks for the selected date in the selected room
            query = """
                SELECT desks.id, (bookings.user_id = ?) as user_booked
                FROM desks
                LEFT JOIN bookings ON desks.id = bookings.desk_id AND bookings.booking_date = ?
                WHERE desks.room_id = ?
            """
            results = execute_db_query(bookings_db_path, query, (user_id, booking_date, selected_room_id), fetch_all=True)

            booked_desks = [desk_id for desk_id, user_booked in results if user_booked]
            already_booked = any(user_booked for _, user_booked in results)

            if already_booked:
                response_text = f"You have already booked a desk for {booking_date}. Please choose another date or cancel your existing booking."
                if update.callback_query:
                    update.callback_query.edit_message_text(response_text)
                else:
                    update.message.reply_text(response_text)
                return

            # Generate buttons for desks, with dynamic columns
            keyboard = [[]]
            for desk_id, _ in results:
                button_text = f"Desk {desk_id}"
                if desk_id in booked_desks:
                    button_text = "🚫 " + button_text
                else:
                    button_text = "✅ " + button_text

                button = InlineKeyboardButton(button_text, callback_data=f'desk_{desk_id}')
                if len(keyboard[-1]) < desk_columns:
                    keyboard[-1].append(button)
                else:
                    keyboard.append([button])

            reply_markup = InlineKeyboardMarkup(keyboard)
            if update.callback_query:
                update.callback_query.edit_message_text(f"Select a desk for {booking_date}:", reply_markup=reply_markup)
            else:
                update.message.reply_text(f"Select a desk for {booking_date}:", reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error in book_time: {e}")
            update.message.reply_text("An error occurred while processing your booking request. Please try again later.")

def get_room_config(room_id):
    """
    Fetch the room configuration based on the room ID.
    The room ID corresponds to the index of the room in the config.ROOMS list.
    """
    try:
        # Assuming the room_id corresponds to the index in the config.ROOMS list
        room_config = config.ROOMS[room_id - 1]  # Subtract 1 because list indices start at 0
        return {
            "name": room_config["name"],
            "desks": room_config["desks"],
            "columns": room_config["columns"]
        }
    except IndexError:
        logger.error(f"Invalid room ID: {room_id}")
        return None

"""
UPDATED BOOK_TIME FUNCTION

def book_time(update: Update, context: CallbackContext) -> None:
    if 'selected_room_id' in context.user_data:
        selected_room_id = context.user_data['selected_room_id']
        # Retrieve the room's configuration, including the number of columns
        room_config = get_room_config(selected_room_id)
        desk_columns = room_config['columns']

        # ... existing code to determine booked desks ...

        # Generate buttons for desks, with dynamic columns
        keyboard = [[]]
        for i in range(1, room_config['desks'] + 1):
            button_text = f"Desk {i}"
            if i in booked_desks:
                button_text = "🚫 " + button_text
            else:
                button_text = "✅ " + button_text

            button = InlineKeyboardButton(button_text, callback_data=f'desk_{i}')
            if len(keyboard[-1]) < desk_columns:
                keyboard[-1].append(button)
            else:
                keyboard.append([button])

        # ... rest of the function ...
"""

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
            SELECT id, booking_date, desk_id 
            FROM bookings 
            WHERE user_id = ? AND
                SUBSTR(booking_date, 7, 4) || '-' || 
                SUBSTR(booking_date, 4, 2) || '-' || 
                SUBSTR(booking_date, 1, 2) >= ?
            ORDER BY 
                SUBSTR(booking_date, 7, 4) || '-' || 
                SUBSTR(booking_date, 4, 2) || '-' || 
                SUBSTR(booking_date, 1, 2)
        """
        logger.info(f"Executing query: {query}")  # Log the query

        bookings = execute_db_query(bookings_db_path, query, (user_id, today), fetch_all=True)
        logger.info(f"Fetched bookings: {bookings}")  # Log fetched bookings
        
        if bookings:
            keyboard = [[InlineKeyboardButton(f"Cancel Desk {desk_id} on {booking_date}", callback_data=f'cancel_{booking_id}')] for booking_id, booking_date, desk_id in bookings]
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
def view_bookings(update: Update, context: CallbackContext, personal_only=False) -> None:
    user_id = str(update.effective_user.id)
    username = update.effective_user.username or "Unknown User"
    logger.info(f"view_bookings invoked by @{username}")

    try:
        today = datetime.now().strftime('%Y-%m-%d')
        four_days_later = (datetime.now() + timedelta(days=4)).strftime('%Y-%m-%d')

        sql_query = """
            SELECT b.booking_date, r.room_name, d.desk_number, b.username
            FROM bookings b
            INNER JOIN desks d ON b.desk_id = d.id
            INNER JOIN rooms r ON d.room_id = r.id
        """

        parameters = []

        if personal_only:
            sql_query += " WHERE b.user_id = ? "
            parameters.append(user_id)

        sql_query += """
            AND (SUBSTR(b.booking_date, 7, 4) || '-' || 
            SUBSTR(b.booking_date, 4, 2) || '-' || 
            SUBSTR(b.booking_date, 1, 2)) BETWEEN ? AND ?
            ORDER BY 
                SUBSTR(b.booking_date, 7, 4) || '-' || 
                SUBSTR(b.booking_date, 4, 2) || '-' || 
                SUBSTR(b.booking_date, 1, 2), 
                r.room_name, 
                d.desk_number
        """
        parameters += [today, four_days_later]

        bookings = execute_db_query(bookings_db_path, sql_query, tuple(parameters), fetch_all=True)

        if not bookings:
            update.message.reply_text("No bookings found.")
            return

        message_text = ""
        current_date = ""
        current_room = ""

        if personal_only:
            message_text = f"Your bookings, @{username}:\n\n"
        else:
            message_text = "All bookings for today and next 4 days:\n"

        for booking_date, room_name, desk_number, booking_username in bookings:
            if personal_only and booking_username.lstrip('@').lower() != username.lower():
                continue

            if booking_date != current_date:
                current_date = booking_date
                if not personal_only:
                    message_text += "\n"  # Add space before new date for all bookings
                message_text += f"*{booking_date}*\n"  # Add the date in bold

            if not personal_only:
                if room_name != current_room:
                    current_room = room_name
                    message_text += f"\n{room_name}\n"  # Add space before new room name
                desk_info = f"Desk: {desk_number}, {booking_username}\n"
            else:
                desk_info = f"{room_name}, Desk: {desk_number}\n"

            message_text += desk_info

        # Strip and Markdown parse mode for proper formatting
        if update.callback_query:
            update.callback_query.edit_message_text(message_text.strip(), parse_mode='Markdown')
        else:
            update.message.reply_text(message_text.strip(), parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error in view_bookings: {e}")
        update.message.reply_text("An error occurred while retrieving the bookings. Please try again later.")

def format_room_bookings(date, rooms_and_desks, personal_only, username):
    formatted_text = ""
    date_formatted = date  # Use the date as it is, since it's already in the correct format

    if personal_only:
        user_bookings_found = False
        formatted_text += f"Your bookings, @{username}:\n\n"

        for room, desks in rooms_and_desks.items():
            for desk, booking_username in desks:
                # Log the usernames being compared for debugging
                logger.info(f"Comparing @{username.lower()} with {booking_username.lower().lstrip('@')}")

                if booking_username.lower().lstrip('@') == username.lower():
                    formatted_text += f"{date_formatted}\n{room}, Desk: {desk}\n\n"
                    user_bookings_found = True

        if not user_bookings_found:
            formatted_text += "No bookings found."
    else:
        formatted_text += f"*{date_formatted}*\n\n"
        for room, desks in rooms_and_desks.items():
            formatted_text += f"{room}\n"
            for desk, booking_username in desks:
                formatted_text += f"Desk: {desk}, {booking_username}\n"
            formatted_text += "\n"

    return formatted_text

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

    # Create Updater object and pass the bot's token
    updater = Updater(config.BOT_TOKEN, use_context=True)

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # Register command handlers for various functionalities
    dispatcher.add_handler(CommandHandler("book", start_booking_process)) 
    dispatcher.add_handler(CommandHandler("cancel", display_bookings_for_cancellation))
    dispatcher.add_handler(CommandHandler("my_bookings", lambda update, context: view_bookings(update, context, personal_only=True)))
    dispatcher.add_handler(CommandHandler("all_bookings", view_bookings))
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