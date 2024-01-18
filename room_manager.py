from telegram import Update
from telegram.ext import CallbackContext
from decorators import admin_required
from db_queries import execute_db_query
from logger import Logger

logger = Logger.get_logger(__name__)

@admin_required
def add_room(update: Update, context: CallbackContext) -> None:
    if not context.args:
        update.message.reply_text("Usage: /add_room [room_name]")
        logger.info(f"Invalid add_room command usage by Admin {update.effective_user.id}")
        return

    room_name = ' '.join(context.args)
    existing_room = execute_db_query("SELECT room_id FROM rooms WHERE room_name = ?", (room_name,), fetch_one=True)

    if existing_room:
        update.message.reply_text(f"Room: '{room_name}' already exists.")
        return

    try:
        execute_db_query("INSERT INTO rooms (room_name) VALUES (?)", (room_name,))
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
    existing_room = execute_db_query("SELECT room_id FROM rooms WHERE room_id = ?", (room_id,), fetch_one=True)

    if not existing_room:
        update.message.reply_text(f"No room found with room_id {room_id}.")
        return

    existing_desk = execute_db_query("SELECT desk_id FROM desks WHERE room_id = ? AND desk_number = ?", (room_id, desk_number), fetch_one=True)

    if existing_desk:
        update.message.reply_text(f"Desk number {desk_number} already exists in room {room_id}.")
        return

    # Insert new desk into database
    try:
        execute_db_query("INSERT INTO desks (room_id, desk_number) VALUES (?, ?)", (room_id, desk_number))
        update.message.reply_text(f"Desk {desk_number} added successfully to room (room_id: {room_id}).")
        logger.info(f"Desk {desk_number} added successfully to room (room_id: {room_id}) by Admin {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error adding desk {desk_number} to room (room_id: {room_id}): {e}")
        update.message.reply_text("Failed to add desk. Please try again later.")

@admin_required
def edit_room_name(update: Update, context: CallbackContext) -> None:
    if len(context.args) < 2:
        update.message.reply_text("Usage: /edit_room_name [room_id] [new_room_name]")
        return

    room_id, new_room_name = context.args[0], ' '.join(context.args[1:])

    existing_room = execute_db_query("SELECT room_id FROM rooms WHERE room_name = ?", (new_room_name,), fetch_one=True)

    if existing_room:
        update.message.reply_text(f"Another room with the name '{new_room_name}' already exists.")
        return

    try:
        execute_db_query("UPDATE rooms SET room_name = ? WHERE room_id = ?", (new_room_name, room_id))
        update.message.reply_text(f"Room name updated successfully to '{new_room_name}'.")
        logger.info(f"Room name updated successfully to '{new_room_name}' by Admin {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error updating room name: {e}")
        update.message.reply_text("Failed to update room name. Please try again later.")

@admin_required
def edit_plan_url(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 2:
        update.message.reply_text("Usage: /edit_plan_url [room_id] [new_plan_url]")
        return

    room_id, new_plan_url = context.args
    existing_room = execute_db_query("SELECT room_id FROM rooms WHERE room_id = ?", (room_id,), fetch_one=True)

    if not existing_room:
        update.message.reply_text(f"No room found with room_id {room_id}.")
        return

    try:
        execute_db_query("UPDATE rooms SET plan_url = ? WHERE room_id = ?", (new_plan_url, room_id))
        update.message.reply_text(f"Plan URL updated successfully for room {room_id}.")
        logger.info(f"Plan URL updated successfully for room {room_id} by Admin {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error updating plan URL for room {room_id}: {e}")
        update.message.reply_text("Failed to update plan URL. Please try again later.")

@admin_required
def edit_desk_number(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 2:
        update.message.reply_text("Usage: /edit_desk_number [desk_id] [new_desk_number]")
        return

    desk_id, new_desk_number = context.args
    existing_desk = execute_db_query("SELECT desk_id FROM desks WHERE desk_id = ?", (desk_id,), fetch_one=True)

    if not existing_desk:
        update.message.reply_text(f"No desk found with desk_id {desk_id}.")
        return

    try:
        execute_db_query("UPDATE desks SET desk_number = ? WHERE desk_id = ?", (new_desk_number, desk_id))
        update.message.reply_text(f"Desk number updated successfully to {new_desk_number}.")
    except Exception as e:
        logger.error(f"Error updating desk number for desk {desk_id}: {e}")
        update.message.reply_text("Failed to update desk number. Please try again later.")

@admin_required
def remove_room(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 1:
        update.message.reply_text("Usage: /remove_room [room_id]")
        return

    room_id = context.args[0]
    existing_room = execute_db_query("SELECT room_id FROM rooms WHERE room_id = ?", (room_id,), fetch_one=True)

    if not existing_room:
        update.message.reply_text(f"No room found with room_id {room_id}.")
        return

    # Delete the room and associated desks and bookings
    try:
        execute_db_query("DELETE FROM bookings WHERE desk_id IN (SELECT desk_id FROM desks WHERE room_id = ?)", (room_id,)) # Delete bookings for all desks in the room

        execute_db_query("DELETE FROM desks WHERE room_id = ?", (room_id,)) # Delete all desks in the room

        execute_db_query("DELETE FROM rooms WHERE room_id = ?", (room_id,)) # Delete the room

        update.message.reply_text(f"Room {room_id} and all associated desks and bookings have been removed.")

        logger.info(f"Room {room_id} and all associated desks and bookings have been removed by Admin {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error removing room {room_id}: {e}")
        update.message.reply_text("Failed to remove room. Please try again later.")

@admin_required
def remove_desk(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 2:
        update.message.reply_text("Usage: /remove_desk [room_id] [desk_number]")
        return

    room_id, desk_number = context.args
    existing_room = execute_db_query("SELECT room_id FROM rooms WHERE room_id = ?", (room_id,), fetch_one=True)

    if not existing_room:
        update.message.reply_text(f"No room found with room_id {room_id}.")
        return

    existing_desk = execute_db_query("SELECT desk_id FROM desks WHERE room_id = ? AND desk_number = ?", (room_id, desk_number), fetch_one=True)

    if not existing_desk:
        update.message.reply_text(f"No desk found with desk_number {desk_number} in room {room_id}.")
        return

    # Delete the desk and associated bookings
    try:
        execute_db_query("DELETE FROM bookings WHERE desk_id = ?", (existing_desk[0],)) # Delete bookings for the desk

        execute_db_query("DELETE FROM desks WHERE desk_id = ?", (existing_desk[0],)) # Delete the desk

        update.message.reply_text(f"Desk {desk_number} in room {room_id} and all associated bookings have been removed.")

        logger.info(f"Desk {desk_number} in room {room_id} and all associated bookings have been removed by Admin {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error removing desk {desk_number} from room {room_id}: {e}")
        update.message.reply_text("Failed to remove desk. Please try again later.")

@admin_required
def set_room_availability(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 2:
        update.message.reply_text("Usage: /set_room_availability [room_id] [room_availability]")
        return

    room_id, room_availability = context.args
    
    # Check if room_availability is 0 or 1
    if room_availability not in ["0", "1"]:
        update.message.reply_text("Room availability must be 0 (unavailable) or 1 (available).")
        return

    # Check if room exists
    existing_room = execute_db_query("SELECT room_id FROM rooms WHERE room_id = ?", (room_id,), fetch_one=True)
    if not existing_room:
        update.message.reply_text(f"No room found with room_id {room_id}.")
        return

    # Update room availability
    try:
        execute_db_query("UPDATE rooms SET room_availability = ? WHERE room_id = ?", (int(room_availability), room_id))

        update.message.reply_text(f"Room availability updated successfully for room ID {room_id}.")

        logger.info(f"Room availability updated successfully for room (room_id {room_id}) by Admin {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error updating room availability for room {room_id}: {e}")
        update.message.reply_text("Failed to update room availability. Please try again later.")

@admin_required
def set_desk_availability(update: Update, context: CallbackContext) -> None:
    if len(context.args) != 2:
        update.message.reply_text("Usage: /set_desk_availability [desk_id] [desk_availability]")
        return

    desk_id, desk_availability = context.args

    if desk_availability not in ["0", "1"]:
        update.message.reply_text("Desk availability must be 0 (unavailable) or 1 (available).")
        return

    existing_desk = execute_db_query("SELECT desk_id FROM desks WHERE desk_id = ?", (desk_id,), fetch_one=True)
    if not existing_desk:
        update.message.reply_text(f"No desk found with desk_id {desk_id}.")
        return

    try:
        execute_db_query("UPDATE desks SET desk_availability = ? WHERE desk_id = ?", (int(desk_availability), desk_id))
        update.message.reply_text(f"Desk availability updated successfully for desk ID {desk_id}.")
        logger.info(f"Desk availability updated successfully for desk (desk_id {desk_id}) by Admin {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Error updating desk availability for desk {desk_id}: {e}")
        update.message.reply_text("Failed to update desk availability. Please try again later.")

@admin_required
def view_rooms(update: Update, context: CallbackContext) -> None:
    try:
        rooms = execute_db_query("SELECT room_id, room_name, room_availability, room_add_info, plan_url FROM rooms", fetch_all=True)
        message_text = "Rooms and Desks Information:\n\n"
        
        # Iterate through rooms and desks and append to message_text
        for room in rooms:

            room_id, room_name, room_availability, room_add_info, plan_url = room
            message_text += f"room_name: {room_name}\nroom_id: {room_id}, room_availability: {room_availability}, room_add_info: {room_add_info}, plan_url: {plan_url}\n\n"
            
            # Get desks for the room
            desks = execute_db_query("SELECT desk_id, desk_number, desk_availability, desk_add_info FROM desks WHERE room_id = ?", (room_id,), fetch_all=True)

            # Iterate through desks and append to message_text
            for desk in desks:
                desk_id, desk_number, desk_availability, desk_add_info = desk
                message_text += f"desk_number: {desk_number}, desk_id: {desk_id}, desk_availability: {desk_availability}, desk_add_info: {desk_add_info}\n"
            message_text += "\n"

        update.message.reply_text(message_text)
    except Exception as e:
        logger.error(f"Error in view_rooms: {e}")
        update.message.reply_text("An error occurred while retrieving room and desk information. Please try again later.")