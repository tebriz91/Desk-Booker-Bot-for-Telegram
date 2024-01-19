from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from datetime import datetime, timedelta
import pytz  # If handling different time zones
import holidays  # If considering public holidays set COUNTRY_CODE in config.py
import config
from logger import Logger
from decorators import user_required, admin_required
from db_queries import execute_db_query

logger = Logger.get_logger(__name__)

def generate_dates(num_days=config.NUM_DAYS, exclude_weekends=config.EXCLUDE_WEEKENDS, timezone=config.LOG_TIMEZONE, country_code=config.COUNTRY_CODE):
    """
    Generates a list of dates from the current date.

    :param num_days: Number of dates to generate.
    :param exclude_weekends: Exclude weekends if True.
    :param timezone: Time zone for date generation.
    :param country_code: Country code for public holidays (Optional).
    :return: List of formatted date strings.
    """
    dates = []
    current_date = datetime.now(pytz.timezone(timezone))

    while len(dates) < num_days:
        if exclude_weekends and current_date.weekday() >= 5:  # Skip weekends (5 and 6 corresponds to Saturday-Sunday)
            current_date += timedelta(days=1) # Add one day to the current date
            continue

        # Check for public holidays (optional)
        if country_code and current_date in holidays.CountryHoliday(country_code):  # Skip public holidays
            current_date += timedelta(days=1)
            continue
        
        formatted_date = current_date.strftime('%d.%m.%Y (%a)') # Format the date as DD.MM.YYYY (Day)

        dates.append(formatted_date) # Add the formatted date to the list of dates

        current_date += timedelta(days=1) # Add one day to the current date

        # Output the list of dates: ['DD.MM.YYYY (Day)', 'DD.MM.YYYY (Day)', ...]

    return dates

async def cancel_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == 'cancelbutton':
        await query.edit_message_text("Process cancelled.")
        return

@user_required
async def start_booking_process(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)

    try:
        # Check if user is delisted
        is_delisted_result = await execute_db_query(
            "SELECT is_delisted FROM users WHERE user_id = ?",
            (user_id,),
            fetch_one=True
        )

        if is_delisted_result and is_delisted_result[0]:
            await update.message.reply_text("You are delisted and cannot use this bot.")
            return

        # Generate booking dates and create keyboard markup
        dates = generate_dates()
        keyboard = [[InlineKeyboardButton(date, callback_data=f'date_{date}')] for date in dates]

        # Add a Cancel button
        keyboard.append([InlineKeyboardButton("Cancel", callback_data='cancelbutton')])

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text("Select a date to book:", reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Database error in start_booking_process: {e}")
        await update.message.reply_text("An error occurred. Please try again later.")

async def date_selected(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    # Extract the date from the callback data
    selected_date = query.data.split('_')[1]
    # Save the selected date in the user's context
    context.user_data['selected_date'] = selected_date

    user_id = str(update.effective_user.id)

    try:
        # Check if user has already booked for the selected date
        existing_booking = await execute_db_query(
            "SELECT booking_id FROM bookings WHERE user_id = ? AND booking_date = ?",
            (user_id, selected_date),
            fetch_one=True
        )

        # Inform user they have already booked a desk for this date
        if existing_booking:
            await query.edit_message_text("You have already booked a desk for this date. Choose another date or cancel the existing booking.")
            return

        # Retrieve the list of available rooms from the database
        rooms = await execute_db_query(
            "SELECT room_id, room_name FROM rooms WHERE room_availability = 1",
            fetch_all=True
        )

        if rooms:
            # Create a list of buttons for each room
            keyboard = [[InlineKeyboardButton(room[1], callback_data=f'room_{room[0]}')] for room in rooms]

            # Add a Cancel button
            keyboard.append([InlineKeyboardButton("Cancel", callback_data='cancelbutton')])

            # Create an inline keyboard markup with the room buttons
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Edit the message text to prompt the user to select a room
            await query.edit_message_text(text="Select a room to book:", reply_markup=reply_markup)
        else:
            # Log that no rooms data was found and inform the user
            logger.info("No rooms data found.")
            await query.edit_message_text("No rooms available to book.")
    except Exception as e:
        logger.error(f"Error in date_selected: {e}")
        await query.edit_message_text("An error occurred. Please try again.")

async def room_selected(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    selected_room_id = int(query.data.split('_')[1]) # Extract the room ID from the callback data (from the selected room button)

    context.user_data['selected_room_id'] = selected_room_id
    booking_date = context.user_data['selected_date']

    try: # Retrieve the room name and plan URL. Only select available rooms
        room_result = await execute_db_query(
            "SELECT room_name, plan_url FROM rooms WHERE room_id = ? AND room_availability = 1",
            (selected_room_id,),
            fetch_one=True
        )

        if not room_result:
            await query.edit_message_text("Selected room is not available. Please choose another room.")
            return

        room_name, plan_url = room_result # Unpack the tuple into variables for convenience (room_name, plan_url)

        text_with_image_link = f"Select a desk in {room_name} according to the [room plan]({plan_url}):" # MarkdownV2 format

        desks = await execute_db_query("""
            SELECT d.desk_id, d.desk_number, 
                CASE WHEN b.booking_id IS NOT NULL THEN 1 ELSE 0 END as is_booked
            FROM desks d
            LEFT JOIN bookings b ON d.desk_id = b.desk_id AND b.booking_date = ?
            WHERE d.room_id = ? AND d.desk_availability = 1
        """,
            (booking_date, selected_room_id,),
            fetch_all=True
        ) # Retrieve the list of available desks from the database

        if desks:

            keyboard = [[InlineKeyboardButton(f"{'✅' if is_booked == 0 else '🚫'} Desk {desk_number}", callback_data=f'desk_{desk_id}')]
                        for desk_id, desk_number, is_booked in desks]
            
            # Add a Cancel button
            keyboard.append([InlineKeyboardButton("Cancel", callback_data='cancelbutton')])

            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(text=text_with_image_link, reply_markup=reply_markup, parse_mode='MarkdownV2')
        else:
            await query.edit_message_text("No desks available in the selected room.")
    except Exception as e:
        logger.error(f"Error in room_selected: {e}")
        await query.edit_message_text("An error occurred. Please try again.")

async def desk_selected(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    selected_desk_id = int(query.data.split('_')[1])
    booking_date = context.user_data['selected_date']

    # Retrieve the desk number from the database
    desk_number_query = "SELECT desk_number FROM desks WHERE desk_id = ?"
    desk_number_result = await execute_db_query(desk_number_query, (selected_desk_id,), fetch_one=True)
    desk_number = desk_number_result[0] if desk_number_result else "Unknown"

    # Check if the desk is available
    try:
        if await check_desk_availability(selected_desk_id, booking_date):
            # Desk is available, proceed with booking
            user_id = update.effective_user.id
            await execute_db_query(
                "INSERT INTO bookings (user_id, booking_date, desk_id) VALUES (?, ?, ?)",
                (user_id, booking_date, selected_desk_id)
            )
            response_text = f"Desk {desk_number} successfully booked for {booking_date}."
        else:
            # Desk is not available
            response_text = f"Desk {desk_number} is not available on {booking_date}. Please choose another desk."

        await query.edit_message_text(response_text)

    except Exception as e:
        logger.error(f"Error in desk_selected: {e}")
        response_text = "An error occurred. Please try again."

async def check_desk_availability(desk_id, booking_date):
    try:
        result = await execute_db_query(
            "SELECT booking_id FROM bookings WHERE desk_id = ? AND booking_date = ?",
            (desk_id, booking_date),
            fetch_one=True
        )
        return result is None
    except Exception as e:
        logger.error(f"Error checking desk availability: {e}")
        return False

@user_required
async def display_bookings_for_cancellation(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id

    today = datetime.now().strftime('%d.%m.%Y (%a)') # format the date as 'DD.MM.YYYY (Day)' (as stored in the database)

    try:
        bookings = await execute_db_query("""
            SELECT b.booking_id, b.booking_date, d.desk_number
            FROM bookings b
            JOIN desks d ON b.desk_id = d.desk_id
            WHERE b.user_id = ? AND b.booking_date >= ?
            ORDER BY b.booking_date
        """, (user_id, today), fetch_all=True)

        if bookings:
            
            # Create a list of buttons for each booking
            keyboard = [[InlineKeyboardButton(f"Cancel Desk {desk_number} on {booking_date}", callback_data=f'cancel_{booking_id}')] 
                        for booking_id, booking_date, desk_number in bookings]
            
            # Add a Cancel button
            keyboard.append([InlineKeyboardButton("Cancel", callback_data='cancelbutton')])

            reply_markup = InlineKeyboardMarkup(keyboard)
            response_text = "Select a booking to cancel."
        else:
            response_text = "You have no upcoming bookings to cancel."

        await update.message.reply_text(response_text, reply_markup=reply_markup if bookings else None)
    except Exception as e:
        logger.error(f"Error in display_bookings_for_cancellation: {e}")
        await update.message.reply_text("An error occurred while retrieving bookings for cancellation. Please try again later.")

async def cancel_booking(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    booking_id = query.data.split('_')[1]
    user_id = update.effective_user.id

    try:
        await execute_db_query("DELETE FROM bookings WHERE booking_id = ? AND user_id = ?", (booking_id, user_id))
        await query.edit_message_text(f"Booking cancelled successfully.")
    except Exception as e:
        logger.error(f"Error in cancel_booking: {e}")
        await query.edit_message_text("Failed to cancel the booking. Please try again later.")

@admin_required
async def cancel_booking_by_id(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /cancel_booking [booking_id]")
        logger.info(f"Invalid cancel_booking command usage by Admin {update.effective_user.id}")
        return

    booking_id = context.args[0]

    # Check if the booking exists
    existing_booking = await execute_db_query("SELECT booking_id FROM bookings WHERE booking_id = ?", (booking_id,), fetch_one=True)
    if not existing_booking:
        await update.message.reply_text(f"No booking found with booking_id: {booking_id}.")
        return
    
    # Execute the delete query using the centralized database function
    try:
        await execute_db_query("DELETE FROM bookings WHERE booking_id = ?", (booking_id,))
        await update.message.reply_text(f"Booking (booking_id: {booking_id}) cancelled successfully.")
        logger.info(f"Admin {update.effective_user.id} cancelled booking (booking_id: {booking_id}).")
    except Exception as e:
        logger.error(f"Error cancelling booking (booking_id: {booking_id}): {e}")
        await update.message.reply_text("Failed to cancel the booking. Please try again later.")

@user_required
async def view_my_bookings(update: Update, context: CallbackContext) -> None:
    user_id = str(update.effective_user.id)
    username = update.effective_user.username or "Unknown User"

    # Define the time range
    today = datetime.now().strftime('%d.%m.%Y (%a)')
    
    try:
        query = """
            SELECT b.booking_date, r.room_name, d.desk_number
            FROM bookings b
            INNER JOIN desks d ON b.desk_id = d.desk_id
            INNER JOIN rooms r ON d.room_id = r.room_id
            WHERE b.user_id = ? AND b.booking_date >= ?
            ORDER BY b.booking_date
        """
        bookings = await execute_db_query(query, (user_id, today), fetch_all=True)

        if bookings:
            message_text = f"Your bookings, @{username}:\n\n"
            for booking_date, room_name, desk_number in bookings:
                message_text += f"*{booking_date}*: {room_name}, Desk {desk_number}\n"
        else:
            message_text = "You have no bookings."

        await update.message.reply_text(message_text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in view_my_bookings: {e}")
        await update.message.reply_text("An error occurred while retrieving your bookings. Please try again later.")

@user_required
async def view_all_bookings(update: Update, context: CallbackContext) -> None:
    # Define the time range
    today = datetime.now().strftime('%d.%m.%Y (%a)')

    try:
        query = """
            SELECT b.booking_date, r.room_name, d.desk_number, b.user_id
            FROM bookings b
            INNER JOIN desks d ON b.desk_id = d.desk_id
            INNER JOIN rooms r ON d.room_id = r.room_id
            WHERE b.booking_date >= ?
            ORDER BY b.booking_date, r.room_name, d.desk_number
        """
        bookings = await execute_db_query(query, (today,), fetch_all=True)

        users_query = "SELECT user_id, username FROM users"
        users = await execute_db_query(users_query, fetch_all=True)
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

        await update.message.reply_text(message_text, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in view_all_bookings: {e}")
        await update.message.reply_text("An error occurred while retrieving bookings. Please try again later.")

@admin_required
async def view_booking_history(update: Update, context: CallbackContext) -> None:
    two_weeks_ago = (datetime.now() - timedelta(days=14)).strftime('%d.%m.%Y (%a)')

    try:
        # Fetch users from the database
        users_query = "SELECT user_id, username FROM users"
        users = await execute_db_query(users_query, fetch_all=True)
        user_dict = {user[0]: user[1] for user in users}

        # Fetch bookings from the database
        bookings_query = """
            SELECT b.booking_id, b.booking_date, r.room_name, d.desk_number, b.user_id
            FROM bookings b
            INNER JOIN desks d ON b.desk_id = d.desk_id
            INNER JOIN rooms r ON d.room_id = r.room_id
            WHERE b.booking_date >= ?
            ORDER BY b.booking_date, r.room_name, d.desk_number
        """
        
        bookings = await execute_db_query(bookings_query, (two_weeks_ago,), fetch_all=True)

        users_query = "SELECT user_id, username FROM users"
        users = await execute_db_query(users_query, fetch_all=True)
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

        await update.message.reply_text(message_text, parse_mode='Markdown')
        logger.info(f"Admin {update.effective_user.id} viewed booking history.")
    except Exception as e:
        logger.error(f"Error viewing booking history by Admin {update.effective_user.id}: {e}")
        await update.message.reply_text("An error occurred while retrieving the booking history.")