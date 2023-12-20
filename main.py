#telegram bot for booking tables by coworkers in a hybrid office work schedule

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext, Filters
from datetime import datetime, timedelta
import sqlite3
import logging
import os

# Path to the databases
bookings_db_path = 'data/bookings.db'
users_db_path = 'data/users.db'

# Ensure the 'data' directory for databases exists
os.makedirs(os.path.dirname(bookings_db_path), exist_ok=True)
os.makedirs(os.path.dirname(users_db_path), exist_ok=True)

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                     level=logging.INFO)
logger = logging.getLogger(__name__)

# Create a SQLite database connection
conn = sqlite3.connect(bookings_db_path)

# Create a cursor object
c = conn.cursor()

# Initialize the bookings database
bookings_conn = sqlite3.connect(bookings_db_path)
bookings_cursor = bookings_conn.cursor()
bookings_cursor.execute('''CREATE TABLE IF NOT EXISTS bookings
                           (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                            user_id TEXT, username TEXT, 
                            booking_date TEXT, table_id INTEGER)''')
bookings_conn.commit()
bookings_conn.close()

# Initialize the users database
users_conn = sqlite3.connect(users_db_path)
users_cursor = users_conn.cursor()
users_cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        user_id TEXT UNIQUE, 
        username TEXT, 
        is_admin INTEGER DEFAULT 0, 
        is_blacklisted INTEGER DEFAULT 0
    )
''')

# Insert admin record (your record) if not exists
admin_user_id = 'TELEGRAM_USERID'  # Your Telegram user ID
admin_username = 'TELEGRAM_USERNAME'  # Your Telegram username

users_cursor.execute('''
    INSERT INTO users (user_id, username, is_admin, is_blacklisted)
    VALUES (?, ?, 1, 0)
    ON CONFLICT(user_id) DO NOTHING
''', (admin_user_id, admin_username))

users_conn.commit()
users_conn.close()

def is_admin(user_id, users_db_path):
    """Check if the user is an admin."""
    users_conn = sqlite3.connect(users_db_path)
    users_cursor = users_conn.cursor()
    users_cursor.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,))
    user = users_cursor.fetchone()
    users_conn.close()
    return user and user[0]

def manage_users(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    # Check if the user is an admin
    users_conn = sqlite3.connect(users_db_path)
    users_cursor = users_conn.cursor()
    users_cursor.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,))
    user = users_cursor.fetchone()
    users_conn.close()
    
    if user and user[0]:
        # User is an admin
        message_text = "Admin User Management:\n"
        message_text += "/add_user [user_id] [username] - Add a new user\n"
        message_text += "/make_admin [user_id] - Make a user an admin\n"
        message_text += "/blacklist_user [user_id] - Blacklist a user"
        update.message.reply_text(message_text)
    else:
        update.message.reply_text("You do not have permission to manage users.")

def manage_users_interaction(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()

    user_id = str(update.effective_user.id)

    # Connect to the users database
    users_conn = sqlite3.connect(users_db_path)
    users_cursor = users_conn.cursor()

    # Check if the user is an admin
    users_cursor.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,))
    user = users_cursor.fetchone()
    users_conn.close()

    if user and user[0]:
        # User is an admin
        message_text = "Admin User Management:\n\n"
        message_text += "/add_user [user_id] [username] - Add a new user (enter username without @)\n"
        message_text += "/make_admin [user_id] - Make a user an admin\n"
        message_text += "/blacklist_user [user_id] - Blacklist a user\n"
        message_text += "/remove_user [user_id] - Remove a user\n"
        message_text += "/revoke_admin [user_id] - Revoke admin status\n"
        message_text += "/view_users - View all users and their status\n"
        message_text += "/history - View all booking history for the past 2 weeks\n"
        message_text += "/cancel_booking - Cancel a booking by it's id (ids are shown when /history command is activated)"
        query.edit_message_text(text=message_text)
    else:
        query.edit_message_text(text="You do not have permission to manage users.")

def add_user(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    # Check if the user is an admin
    if not is_admin(user_id, users_db_path):
        update.message.reply_text("You are not authorized to use this command.")
        return
    
    if len(context.args) != 2:
        update.message.reply_text("Usage: /add_user [user_id] [username]")
        return

    user_id, username = context.args
    users_conn = sqlite3.connect(users_db_path)
    users_cursor = users_conn.cursor()
    users_cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    users_conn.commit()
    users_conn.close()
    update.message.reply_text(f"User {username} added successfully.")

def remove_user(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    # Check if the user is an admin
    if not is_admin(user_id, users_db_path):
        update.message.reply_text("You are not authorized to use this command.")
        return
    
    if len(context.args) != 1:
        update.message.reply_text("Usage: /remove_user [user_id]")
        return

    user_id = context.args[0]
    users_conn = sqlite3.connect(users_db_path)
    users_cursor = users_conn.cursor()
    users_cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    users_conn.commit()
    users_conn.close()
    update.message.reply_text(f"User with ID {user_id} removed successfully.")

def make_admin(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    # Check if the user is an admin
    if not is_admin(user_id, users_db_path):
        update.message.reply_text("You are not authorized to use this command.")
        return
    
    if len(context.args) != 1:
        update.message.reply_text("Usage: /make_admin [user_id]")
        return

    user_id = context.args[0]
    users_conn = sqlite3.connect(users_db_path)
    users_cursor = users_conn.cursor()
    users_cursor.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (user_id,))
    users_conn.commit()
    users_conn.close()
    update.message.reply_text("User updated to admin successfully.")

def revoke_admin(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    # Check if the user is an admin
    if not is_admin(user_id, users_db_path):
        update.message.reply_text("You are not authorized to use this command.")
        return
   
    if len(context.args) != 1:
        update.message.reply_text("Usage: /revoke_admin [user_id]")
        return

    user_id = context.args[0]
    users_conn = sqlite3.connect(users_db_path)
    users_cursor = users_conn.cursor()
    users_cursor.execute("UPDATE users SET is_admin = 0 WHERE user_id = ?", (user_id,))
    users_conn.commit()
    users_conn.close()
    update.message.reply_text("Admin privileges revoked successfully.")

def blacklist_user(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    # Check if the user is an admin
    if not is_admin(user_id, users_db_path):
        update.message.reply_text("You are not authorized to use this command.")
        return

    if len(context.args) != 1:
        update.message.reply_text("Usage: /blacklist_user [user_id]")
        return

    user_id = context.args[0]
    users_conn = sqlite3.connect(users_db_path)
    users_cursor = users_conn.cursor()
    users_cursor.execute("UPDATE users SET is_blacklisted = 1 WHERE user_id = ?", (user_id,))
    users_conn.commit()
    users_conn.close()
    update.message.reply_text("User blacklisted successfully.")

def view_users(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    # Check if the user is an admin
    if not is_admin(user_id, users_db_path):
        update.message.reply_text("You are not authorized to use this command.")
        return

    users_conn = sqlite3.connect(users_db_path)
    users_cursor = users_conn.cursor()
    
    # Query to get all users' data
    users_cursor.execute("SELECT id, user_id, username, is_admin, is_blacklisted FROM users")
    users = users_cursor.fetchall()
    users_conn.close()

    # Formatting the message
    message_text = "List of all users:\n\n"
    for user in users:
        status = "Admin" if user[3] else ("Blacklisted" if user[4] else "User")
        username_display = f"@{user[2]}" if user[2] else "N/A"  # Display username with @ or N/A if username is None
        message_text += f"ID: {user[0]}, User ID: {user[1]}, Username: {username_display}, Status: {status}\n"

    update.message.reply_text(message_text)

def cancel_booking_by_id(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    if not is_admin(user_id, users_db_path):
        update.message.reply_text("You are not authorized to use this command.")
        return

    if len(context.args) != 1 or not context.args[0].isdigit():
        update.message.reply_text("Usage: /cancel_booking [id]")
        return

    booking_id = context.args[0]

    conn = sqlite3.connect(bookings_db_path)
    c = conn.cursor()
    c.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
    changes = conn.total_changes
    conn.commit()
    conn.close()

    if changes > 0:
        update.message.reply_text(f"Booking with ID {booking_id} cancelled successfully.")
    else:
        update.message.reply_text(f"No booking found with ID {booking_id}.")

def start(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)

    # Connect to the users database
    users_conn = sqlite3.connect(users_db_path)
    users_cursor = users_conn.cursor()

    # Check if the user exists in the users database
    users_cursor.execute("SELECT is_admin, is_blacklisted FROM users WHERE user_id = ?", (user_id,))
    user = users_cursor.fetchone()
    users_conn.close()

    if user is None:
        # If user does not exist, inform them that they need to be registered by an admin
        update.message.reply_text("You are not registered. Please contact an admin (@tebriz91) to use this bot.")
        return

    is_admin, is_blacklisted = user

    if is_blacklisted:
        update.message.reply_text("You are blacklisted and cannot use this bot.")
        return

    # Define keyboard based on user status
    keyboard = [
        [InlineKeyboardButton("Book a Table", callback_data='book_table'),
         InlineKeyboardButton("Cancel Booking", callback_data='cancel_booking')],
        [InlineKeyboardButton("View My Bookings", callback_data='view_my_bookings'),
         InlineKeyboardButton("View All Bookings", callback_data='view_all_bookings')]
    ]

    if is_admin:
        # Additional options for admin users
        keyboard.append([InlineKeyboardButton("Manage Users", callback_data='manage_users')])

    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text('Please choose an option:', reply_markup=reply_markup)

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
    elif query.data == 'view_my_bookings':
        view_my_bookings(update, context)
    elif query.data == 'view_all_bookings':
        view_all_bookings(update, context)
    # Add handling for other callback_data options

def start_booking_process(update: Update, context: CallbackContext) -> None:
    dates = generate_dates()
    keyboard = [[InlineKeyboardButton(date, callback_data=f'date_{date}')] for date in dates]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Select a date to book:", reply_markup=reply_markup)

def book_time(update: Update, context: CallbackContext) -> None:
    if 'selected_date' in context.user_data:
        booking_date = context.user_data['selected_date']
        user_id = update.effective_user.id

        conn = sqlite3.connect(bookings_db_path)
        c = conn.cursor()

        # Check if the user already has a booking for the selected date
        c.execute("SELECT table_id FROM bookings WHERE booking_date = ? AND user_id = ?", (booking_date, user_id))
        existing_booking = c.fetchone()

        # Retrieve all booked tables for the selected date
        c.execute("SELECT table_id FROM bookings WHERE booking_date = ?", (booking_date,))
        booked_tables = [row[0] for row in c.fetchall()]
        conn.close()

        if existing_booking:
            table_id = existing_booking[0]
            if update.callback_query:
                update.callback_query.edit_message_text(f"You have already booked Table {table_id} for {booking_date}. Please choose another date or cancel your existing booking.")
            else:
                update.message.reply_text(f"You have already booked Table {table_id} for {booking_date}. Please choose another date or cancel your existing booking.")
            return

        # Generate buttons for all tables, marking availability
        keyboard = [[]]
        total_tables = 6  # Assuming there are 6 tables
        for i in range(1, total_tables + 1):
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
    else:
        if update.callback_query:
            update.callback_query.edit_message_text("Please select a date first")
        else:
            update.message.reply_text("Please select a date first")

def process_booking(update: Update, context: CallbackContext, table_id: int) -> None:
    booking_date = context.user_data['selected_date']
    user_id = update.effective_user.id
    username = "@" + update.effective_user.username if update.effective_user.username else "Unknown"

    conn = sqlite3.connect(bookings_db_path)
    c = conn.cursor()

    try:
        # Check if the user already has a booking on the selected date
        c.execute("SELECT * FROM bookings WHERE booking_date = ? AND user_id = ?", (booking_date, user_id))
        if c.fetchone():
            response_text = "You have already booked a table for this date. Please choose another date or cancel your existing booking."
        else:
            # Check if the selected table is available
            c.execute("SELECT username FROM bookings WHERE booking_date = ? AND table_id = ?", (booking_date, table_id))
            existing_booking = c.fetchone()
            if existing_booking is None:
                c.execute("INSERT INTO bookings (user_id, username, booking_date, table_id) VALUES (?, ?, ?, ?)", (user_id, username, booking_date, table_id))
                conn.commit()
                response_text = f"Successfully booked Table {table_id} for {booking_date}."
            else:
                existing_username = existing_booking[0]
                response_text = f"This table is already booked for the selected day by {existing_username}. Please choose another table."
    finally:
        conn.close()

    # Respond according to the type of update
    if update.callback_query:
        update.callback_query.edit_message_text(response_text)
    else:
        update.message.reply_text(response_text)
    start(update, context)

def display_bookings_for_cancellation(update: Update, context: CallbackContext) -> None:
    logger.info("Display bookings for cancellation function called")
    user_id = update.effective_user.id
    conn = sqlite3.connect(bookings_db_path)
    c = conn.cursor()

    # Get today's date in YYYY-MM-DD format for comparison
    today = datetime.now().strftime('%Y-%m-%d')

    # Modify the query to select only today's and future bookings
    c.execute("""
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
    """, (user_id, today))
    bookings = c.fetchall()
    conn.close()

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

def cancel_booking(update: Update, context: CallbackContext) -> None:
    logger.info("Cancel booking function called")
    query = update.callback_query
    booking_id = query.data.split('_')[1]
    user_id = update.effective_user.id

    conn = sqlite3.connect(bookings_db_path)
    c = conn.cursor()
    c.execute("DELETE FROM bookings WHERE id = ? AND user_id = ?", (booking_id, user_id))
    conn.commit()
    conn.close()

    query.edit_message_text(f"Booking cancelled successfully.")
    start(update, context)

def view_my_bookings(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    conn = sqlite3.connect(bookings_db_path)
    c = conn.cursor()

    # Get today's date in YYYY-MM-DD format
    today = datetime.now().strftime('%Y-%m-%d')

    # Convert booking_date to YYYY-MM-DD format for comparison
    c.execute("""
        SELECT username, booking_date, table_id 
        FROM bookings 
        WHERE user_id = ? AND
              SUBSTR(booking_date, 7, 4) || '-' || 
              SUBSTR(booking_date, 4, 2) || '-' || 
              SUBSTR(booking_date, 1, 2) >= ?
        ORDER BY 
            SUBSTR(booking_date, 7, 4) || '-' || 
            SUBSTR(booking_date, 4, 2) || '-' || 
            SUBSTR(booking_date, 1, 2)
    """, (user_id, today))
    bookings = c.fetchall()
    conn.close()

    if bookings:
        username = bookings[0][0]  # Assuming username is the same for all bookings
        message_text = f"Your upcoming bookings ({username}):\n"
        message_text += "\n".join([f"{date}, Table: {table_id}" for _, date, table_id in bookings])
    else:
        message_text = "You have no upcoming bookings."

    if update.callback_query:
        update.callback_query.edit_message_text(message_text)
    else:
        update.message.reply_text(message_text)

def view_all_bookings(update: Update, context: CallbackContext) -> None:
    conn = sqlite3.connect(bookings_db_path)
    c = conn.cursor()

    # Sort the results by converting the date format for the next week
    today = datetime.now().strftime('%Y-%m-%d')
    week_later = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')

    c.execute("""
        SELECT booking_date, table_id, username
        FROM bookings 
        WHERE 
            SUBSTR(booking_date, 7, 4) || '-' || 
            SUBSTR(booking_date, 4, 2) || '-' || 
            SUBSTR(booking_date, 1, 2) 
            BETWEEN ? AND ?
        ORDER BY 
            SUBSTR(booking_date, 7, 4) || '-' || 
            SUBSTR(booking_date, 4, 2) || '-' || 
            SUBSTR(booking_date, 1, 2), table_id
    """, (today, week_later))
    bookings = c.fetchall()
    conn.close()

    if bookings:
        # Organize bookings by date
        bookings_by_date = {}
        for booking_date, table_id, username in bookings:
            if booking_date not in bookings_by_date:
                bookings_by_date[booking_date] = []
            bookings_by_date[booking_date].append(f"Table: {table_id}, User: {username}")

        # Format the message
        message_text = "All bookings for today and next 4 days:\n\n"
        for date, bookings_list in bookings_by_date.items():
            message_text += f"{date}\n" + "\n".join(bookings_list) + "\n\n"
    else:
        message_text = "No bookings for the next week."

    if update.callback_query:
        update.callback_query.edit_message_text(message_text)
    else:
        update.message.reply_text(message_text)

def view_booking_history(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    if not is_admin(user_id, users_db_path):
        update.message.reply_text("You are not authorized to use this command.")
        return

    conn = sqlite3.connect(bookings_db_path)
    c = conn.cursor()

    two_weeks_ago = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')

    c.execute("""
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
    """, (two_weeks_ago,))
    bookings = c.fetchall()
    conn.close()

    if bookings:
        bookings_by_date = {}
        for booking_id, booking_date, table_id, username in bookings:
            if booking_date not in bookings_by_date:
                bookings_by_date[booking_date] = []
            # Updated format: Table ID, Username, Booking ID
            bookings_by_date[booking_date].append(f"Table: {table_id}, User: {username}, ID: {booking_id}")

        message_text = "Booking history for the past two weeks:\n\n"
        for date, bookings_list in bookings_by_date.items():
            message_text += f"{date}\n" + "\n".join(bookings_list) + "\n\n"
    else:
        message_text = "No bookings in the past two weeks."

    update.message.reply_text(message_text)

def main() -> None:
    # Create Updater object and pass the bot's token
    updater = Updater("TELEGRAM_BOT_TOKEN", use_context=True)

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CallbackQueryHandler(button, pattern='^(book_table|date_|table_)'))
    dispatcher.add_handler(CallbackQueryHandler(display_bookings_for_cancellation, pattern='^cancel_booking$'))
    dispatcher.add_handler(CallbackQueryHandler(cancel_booking, pattern='^cancel_'))
    dispatcher.add_handler(CallbackQueryHandler(view_my_bookings, pattern='^view_my_bookings$'))
    dispatcher.add_handler(CallbackQueryHandler(view_all_bookings, pattern='^view_all_bookings$'))
    dispatcher.add_handler(CommandHandler("history", view_booking_history))
    dispatcher.add_handler(CallbackQueryHandler(manage_users_interaction, pattern='^manage_users$'))
    dispatcher.add_handler(CommandHandler("add_user", add_user))
    dispatcher.add_handler(CommandHandler("make_admin", make_admin))
    dispatcher.add_handler(CommandHandler("blacklist_user", blacklist_user))
    dispatcher.add_handler(CommandHandler("remove_user", remove_user))
    dispatcher.add_handler(CommandHandler("revoke_admin", revoke_admin))
    dispatcher.add_handler(CommandHandler("manage_users", manage_users))
    dispatcher.add_handler(CommandHandler("view_users", view_users))
    dispatcher.add_handler(CommandHandler("cancel_booking", cancel_booking_by_id))
    dispatcher.add_handler(CommandHandler("book", start_booking_process)) 
    dispatcher.add_handler(CommandHandler("cancel", display_bookings_for_cancellation))  # /cancel to trigger display_bookings_for_cancellation
    dispatcher.add_handler(CommandHandler("my_bookings", view_my_bookings))  # /my_bookings to trigger view_my_bookings
    dispatcher.add_handler(CommandHandler("all_bookings", view_all_bookings))  # /all_bookings to trigger view_all_bookings
    # Add other necessary handlers

    # Start the Bot
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()