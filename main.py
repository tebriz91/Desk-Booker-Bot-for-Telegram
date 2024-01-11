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
total_tables = config.TOTAL_TABLES
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
# Initialize the bookings database
    with sqlite3.connect(bookings_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS bookings
                           (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                            user_id TEXT, username TEXT, 
                            booking_date TEXT, table_id INTEGER)''')
        conn.commit()

# Initialize the users database
    with sqlite3.connect(users_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        user_id TEXT UNIQUE, 
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

def execute_db_query(database_path, query, parameters=(), fetch_one=False, fetch_all=False):
    try:
        with sqlite3.connect(database_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, parameters)
            conn.commit()

            if fetch_one:
                return cursor.fetchone()
            if fetch_all:
                return cursor.fetchall()
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
    
    except sqlite3.Error as e:
        logging.error(f"Database error in start_booking_process: {e}")
        update.message.reply_text("An error occurred. Please try again later.")

def book_time(update: Update, context: CallbackContext) -> None:
    if 'selected_date' in context.user_data:
        booking_date = context.user_data['selected_date']
        user_id = update.effective_user.id

        try:
            query = """
                SELECT table_id, (user_id = ?) as user_booked
                FROM bookings
                WHERE booking_date = ?
            """
            results = execute_db_query(bookings_db_path, query, (user_id, booking_date), fetch_all=True)

            booked_tables = []
            already_booked = False
            for table_id, user_booked in results:
                if user_booked:
                    already_booked = True
                    break
                booked_tables.append(table_id)

            if already_booked:
                response_text = f"You have already booked a table for {booking_date}. Please choose another date or cancel your existing booking."
                if update.callback_query:
                    update.callback_query.edit_message_text(response_text)
                else:
                    update.message.reply_text(response_text)
                return

            # Generate buttons for all tables, marking availability
            keyboard = [[]]
            for i in range(1, config.TOTAL_TABLES + 1):
                button_text = f"Table {i}"
                if i in booked_tables:
                    button_text = "🚫 " + button_text
                else:
                    button_text = "✅ " + button_text

                button = InlineKeyboardButton(button_text, callback_data=f'table_{i}')
                if len(keyboard[-1]) < 3:
                    keyboard[-1].append(button)
                else:
                    keyboard.append([button])

            reply_markup = InlineKeyboardMarkup(keyboard)
            if update.callback_query:
                update.callback_query.edit_message_text(f"Select a table for {booking_date}:", reply_markup=reply_markup)
            else:
                update.message.reply_text(f"Select a table for {booking_date}:", reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error in book_time: {e}")
            update.message.reply_text("An error occurred while processing your booking request. Please try again later.")

def process_booking(update: Update, context: CallbackContext, table_id: int) -> None:
    booking_date = context.user_data['selected_date']
    user_id = update.effective_user.id
    username = "@" + update.effective_user.username if update.effective_user.username else "Unknown"

    try:
        # Check if the user already has a booking on the selected date
        check_query = "SELECT * FROM bookings WHERE booking_date = ? AND user_id = ?"
        existing_booking = execute_db_query(bookings_db_path, check_query, (booking_date, user_id), fetch_one=True)
        
        if existing_booking:
            response_text = "You have already booked a table for this date. Please choose another date or cancel your existing booking."
        else:
            # Check if the selected table is available
            availability_query = "SELECT username FROM bookings WHERE booking_date = ? AND table_id = ?"
            existing_table_booking = execute_db_query(bookings_db_path, availability_query, (booking_date, table_id), fetch_one=True)

            if existing_table_booking is None:
                insert_query = "INSERT INTO bookings (user_id, username, booking_date, table_id) VALUES (?, ?, ?, ?)"
                execute_db_query(bookings_db_path, insert_query, (user_id, username, booking_date, table_id))
                response_text = f"Successfully booked Table {table_id} for {booking_date}."
            else:
                existing_username = existing_table_booking[0]
                response_text = f"This table is already booked for the selected day by {existing_username}. Please choose another table."

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
        # Get today's date in YYYY-MM-DD format for comparison
        today = datetime.now().strftime('%Y-%m-%d')

        # Modify the query to select only today's and future bookings
        query = """
            SELECT id, booking_date, table_id 
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
        bookings = execute_db_query(bookings_db_path, query, (user_id, today), fetch_all=True)

        if bookings:
            keyboard = [[InlineKeyboardButton(f"Cancel Table {table_id} on {booking_date}", callback_data=f'cancel_{booking_id}')] for booking_id, booking_date, table_id in bookings]
            reply_markup = InlineKeyboardMarkup(keyboard)
            # Check if the function is triggered by a callback query or a regular command
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

    try:
        # Define the time range
        today = datetime.now().strftime('%Y-%m-%d')
        next_four_workdays = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')

        # Adjust the query based on whether to show personal or all bookings
        if personal_only:
            sql_query = """
                SELECT booking_date, table_id 
                FROM bookings 
                WHERE user_id = ? AND
                      SUBSTR(booking_date, 7, 4) || '-' || 
                      SUBSTR(booking_date, 4, 2) || '-' || 
                      SUBSTR(booking_date, 1, 2) BETWEEN ? AND ?
                ORDER BY SUBSTR(booking_date, 7, 4) || '-' || 
                         SUBSTR(booking_date, 4, 2) || '-' || 
                         SUBSTR(booking_date, 1, 2), table_id
            """
            parameters = (user_id, today, next_four_workdays)
        else:
            sql_query = """
                SELECT booking_date, table_id, username
                FROM bookings 
                WHERE 
                    SUBSTR(booking_date, 7, 4) || '-' || 
                    SUBSTR(booking_date, 4, 2) || '-' || 
                    SUBSTR(booking_date, 1, 2) BETWEEN ? AND ?
                ORDER BY SUBSTR(booking_date, 7, 4) || '-' || 
                         SUBSTR(booking_date, 4, 2) || '-' || 
                         SUBSTR(booking_date, 1, 2), table_id
            """
            parameters = (today, next_four_workdays)

        bookings = execute_db_query(bookings_db_path, sql_query, parameters, fetch_all=True)

        # Group bookings by date
        bookings_by_date = {}
        for booking in bookings:
            booking_date = booking[0]
            table_id = booking[1]
            username = booking[2] if not personal_only else "You"
            if booking_date not in bookings_by_date:
                bookings_by_date[booking_date] = []
            bookings_by_date[booking_date].append(f"Table: {table_id}" if personal_only else f"Table: {table_id}, User: {username}")

        # Format and send the response
        if bookings:
            message_text = "Your Bookings:\n\n" if personal_only else "All Bookings:\n\n"
            for date, bookings_list in bookings_by_date.items():
                if personal_only:
                    bookings_str = ', '.join(bookings_list)  # Concatenate all bookings for the same date
                    message_text += f"{date}, {bookings_str}\n"  # Display date and bookings on the same line
                else:
                    message_text += f"{date}\n" + "\n".join(bookings_list) + "\n\n"
        else:
            message_text = "No bookings found."

        if update.callback_query:
            update.callback_query.edit_message_text(message_text)
        else:
            update.message.reply_text(message_text)
    except Exception as e:
        logger.error(f"Error in view_bookings: {e}")
        update.message.reply_text("An error occurred while retrieving the bookings. Please try again later.")

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
    # Initialize databases
    initialize_databases()

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
    dispatcher.add_handler(CallbackQueryHandler(button, pattern='^(book_table|date_|table_)'))
    dispatcher.add_handler(CallbackQueryHandler(cancel_booking, pattern='^cancel_'))
    dispatcher.add_handler(CallbackQueryHandler(display_bookings_for_cancellation, pattern='^cancel_booking$'))

    # Start the Bot
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()