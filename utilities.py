from telegram import Update
from telegram.ext import CallbackContext
import config
from decorators import admin_required, user_required

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
    
    update.message.reply_text(message_text)

@user_required
def help_command(update: Update, context: CallbackContext) -> None:
    message_text = (f"Contact @{config.ADMIN_USERNAME} if you need help.")
    update.message.reply_text(message_text)