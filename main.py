
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext, Filters
from datetime import datetime, timedelta
import sqlite3
import logging
import os

# Path to the database
db_path = 'data/bookings.db'

# Ensure the 'data' directory exists
os.makedirs(os.path.dirname(db_path), exist_ok=True)

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                     level=logging.INFO)
logger = logging.getLogger(__name__)

# Create a SQLite database connection
conn = sqlite3.connect(db_path)

# Create a cursor object
c = conn.cursor()

# Modify the existing CREATE TABLE statement to include the username column
c.execute('''CREATE TABLE IF NOT EXISTS bookings
             (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, username TEXT, booking_date TEXT, table_id INTEGER)''')

# If you have an existing table, you might need to run this
# c.execute('''ALTER TABLE bookings ADD COLUMN username TEXT''')

# Commit the changes to the DB
conn.commit()

def start(update: Update, context: CallbackContext) -> None:
    keyboard = [
        [InlineKeyboardButton("Book a Table", callback_data='book_table'),
         InlineKeyboardButton("Cancel Booking", callback_data='cancel_booking')],
        [InlineKeyboardButton("View My Bookings", callback_data='view_my_bookings'),
        InlineKeyboardButton("View All Bookings", callback_data='view_all_bookings')]
    ]
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
    # Add handling for other callback_data options (cancel_booking, view_my_bookings, view_all_bookings)

def display_bookings_for_cancellation(update: Update, context: CallbackContext) -> None:
    logger.info("Display bookings for cancellation function called")
    user_id = update.effective_user.id
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT id, booking_date, table_id FROM bookings WHERE user_id = ?", (user_id,))
    bookings = c.fetchall()
    conn.close()

    if bookings:
        keyboard = [[InlineKeyboardButton(f"Cancel Table {table_id} on {booking_date}", callback_data=f'cancel_{booking_id}')] for booking_id, booking_date, table_id in bookings]
        reply_markup = InlineKeyboardMarkup(keyboard)
        update.callback_query.message.reply_text("Select a booking to cancel:", reply_markup=reply_markup)
    else:
        update.callback_query.message.reply_text("You have no bookings to cancel.")

def cancel_booking(update: Update, context: CallbackContext) -> None:
    logger.info("Cancel booking function called")
    query = update.callback_query
    booking_id = query.data.split('_')[1]
    user_id = update.effective_user.id

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("DELETE FROM bookings WHERE id = ? AND user_id = ?", (booking_id, user_id))
    conn.commit()
    conn.close()

    query.edit_message_text(f"Booking cancelled successfully.")
    start(update, context)

def book_time(update: Update, context: CallbackContext) -> None:
    if 'selected_date' in context.user_data:
        booking_date = context.user_data['selected_date']

        # Create two rows of buttons
        keyboard = [
            [InlineKeyboardButton(f"Table {i+1}", callback_data=f'table_{i+1}') for i in range(3)],  # First row
            [InlineKeyboardButton(f"Table {i+1}", callback_data=f'table_{i+1}') for i in range(3, 6)]  # Second row
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if update.message:
            update.message.reply_text(f"Select a table for {booking_date}:", reply_markup=reply_markup)
        elif update.callback_query:
            update.callback_query.message.reply_text(f"Select a table for {booking_date}:", reply_markup=reply_markup)
    else:
        response_text = "Please select a date first"
        if update.message:
            update.message.reply_text(response_text)
        elif update.callback_query:
            update.callback_query.message.reply_text(response_text)
        start(update, context)

def process_booking(update: Update, context: CallbackContext, table_id: int) -> None:
    booking_date = context.user_data['selected_date']
    user_id = update.effective_user.id
    username = "@" + update.effective_user.username if update.effective_user.username else "Unknown"

    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    try:
        # Check if the user already has a booking on the selected date
        c.execute("SELECT * FROM bookings WHERE booking_date = ? AND user_id = ?", (booking_date, user_id))
        if c.fetchone():
            response_text = "You have already booked a table for this date. Please choose another date or cancel your existing booking."
        else:
            # Check if the selected table is available
            c.execute("SELECT * FROM bookings WHERE booking_date = ? AND table_id = ?", (booking_date, table_id))
            if c.fetchone() is None:
                c.execute("INSERT INTO bookings (user_id, username, booking_date, table_id) VALUES (?, ?, ?, ?)", (user_id, username, booking_date, table_id))
                conn.commit()
                response_text = f"Successfully booked Table {table_id} for {booking_date}"
            else:
                response_text = "This table is already booked for the selected day. Please choose another table."
    finally:
        conn.close()

    # Respond according to the type of update
    if update.message:
        update.message.reply_text(response_text)
    elif update.callback_query:
        update.callback_query.message.reply_text(response_text)
    start(update, context)

def view_my_bookings(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Sort the results by converting the date format
    c.execute("""
        SELECT username, booking_date, table_id 
        FROM bookings 
        WHERE user_id = ?
        ORDER BY 
            SUBSTR(booking_date, 7, 4) || '-' || 
            SUBSTR(booking_date, 4, 2) || '-' || 
            SUBSTR(booking_date, 1, 2)
    """, (user_id,))
    bookings = c.fetchall()
    conn.close()

    if bookings:
        message_text = "Your bookings:\n" + "\n".join([f"User: {username}, Date: {date}, Table: {table_id}" for username, date, table_id in bookings])
    else:
        message_text = "You have no bookings."

    update.callback_query.message.reply_text(message_text)

def view_all_bookings(update: Update, context: CallbackContext) -> None:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Sort the results by converting the date format for the next week
    today = datetime.now().strftime('%Y-%m-%d')
    week_later = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')

    c.execute("""
        SELECT username, booking_date, table_id 
        FROM bookings 
        WHERE 
            SUBSTR(booking_date, 7, 4) || '-' || 
            SUBSTR(booking_date, 4, 2) || '-' || 
            SUBSTR(booking_date, 1, 2) 
            BETWEEN ? AND ?
        ORDER BY 
            SUBSTR(booking_date, 7, 4) || '-' || 
            SUBSTR(booking_date, 4, 2) || '-' || 
            SUBSTR(booking_date, 1, 2)
    """, (today, week_later))
    bookings = c.fetchall()
    conn.close()

    if bookings:
        message_text = "All bookings for the next week:\n" + "\n".join(
            [f"Date: {date}, User: {username}, Table: {table_id}" for username, date, table_id in bookings])            
    else:
        message_text = "No bookings for the next week."

    update.callback_query.message.reply_text(message_text)


def main() -> None:
    # Create Updater object and pass the bot's token
    updater = Updater("TOKEN", use_context=True)

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # Add handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CallbackQueryHandler(button, pattern='^(book_table|date_|table_)'))
    dispatcher.add_handler(CallbackQueryHandler(display_bookings_for_cancellation, pattern='^cancel_booking$'))
    dispatcher.add_handler(CallbackQueryHandler(cancel_booking, pattern='^cancel_'))
    dispatcher.add_handler(CallbackQueryHandler(view_my_bookings, pattern='^view_my_bookings$'))
    dispatcher.add_handler(CallbackQueryHandler(view_all_bookings, pattern='^view_all_bookings$'))
    # Add other necessary handlers

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT
    updater.idle()

if __name__ == '__main__':
    main()
