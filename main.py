from dotenv import load_dotenv
load_dotenv()

from telegram.ext import Updater, CommandHandler, CallbackQueryHandler

import config

from db_initializer import initialize_database, initialize_admin_user

from user_manager import start_command, add_user, remove_user, make_admin, revoke_admin, delist_user, list_user, view_users

from room_manager import add_room, add_desk, edit_room_name, edit_plan_url, edit_desk_number, remove_room, remove_desk, set_room_availability, set_desk_availability, view_rooms

from booking_manager import start_booking_process, date_selected, room_selected, desk_selected, cancel_button, cancel_booking, display_bookings_for_cancellation, cancel_booking_by_id, view_my_bookings, view_all_bookings, view_booking_history

from utilities import admin_commands, help_command, dump_database

def main():
    initialize_database()
    initialize_admin_user()

    updater = Updater(config.BOT_TOKEN, use_context=True)
    
    # Register handlers
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler('start', start_command))
    dispatcher.add_handler(CommandHandler('add_user', add_user))
    dispatcher.add_handler(CommandHandler('remove_user', remove_user))
    dispatcher.add_handler(CommandHandler('make_admin', make_admin))
    dispatcher.add_handler(CommandHandler('revoke_admin', revoke_admin))
    dispatcher.add_handler(CommandHandler('delist_user', delist_user))
    dispatcher.add_handler(CommandHandler('list_user', list_user))
    dispatcher.add_handler(CommandHandler('view_users', view_users))
    dispatcher.add_handler(CommandHandler('add_room', add_room))
    dispatcher.add_handler(CommandHandler('add_desk', add_desk))
    dispatcher.add_handler(CommandHandler('edit_room_name', edit_room_name))
    dispatcher.add_handler(CommandHandler('edit_plan_url', edit_plan_url))
    dispatcher.add_handler(CommandHandler('edit_desk_number', edit_desk_number))
    dispatcher.add_handler(CommandHandler('set_room_availability', set_room_availability))
    dispatcher.add_handler(CommandHandler('set_desk_availability', set_desk_availability))
    dispatcher.add_handler(CommandHandler('remove_room', remove_room))
    dispatcher.add_handler(CommandHandler('remove_desk', remove_desk))
    dispatcher.add_handler(CommandHandler('view_rooms', view_rooms))
    dispatcher.add_handler(CommandHandler('book', start_booking_process))
    dispatcher.add_handler(CommandHandler("cancel", display_bookings_for_cancellation))
    dispatcher.add_handler(CommandHandler("cancel_booking", cancel_booking_by_id))
    dispatcher.add_handler(CommandHandler("my_bookings", view_my_bookings))
    dispatcher.add_handler(CommandHandler("all_bookings", view_all_bookings))
    dispatcher.add_handler(CommandHandler("history", view_booking_history))
    dispatcher.add_handler(CommandHandler('admin', admin_commands))
    dispatcher.add_handler(CommandHandler('help', help_command))
    dispatcher.add_handler(CommandHandler('dump_db', dump_database))

    # Register CallbackQueryHandler for handling button presses
    dispatcher.add_handler(CallbackQueryHandler(date_selected, pattern='^date_'))
    dispatcher.add_handler(CallbackQueryHandler(room_selected, pattern='^room_'))
    dispatcher.add_handler(CallbackQueryHandler(desk_selected, pattern='^desk_'))
    dispatcher.add_handler(CallbackQueryHandler(cancel_button, pattern='^cancelbutton'))
    dispatcher.add_handler(CallbackQueryHandler(cancel_booking, pattern='^cancel_'))
    dispatcher.add_handler(CallbackQueryHandler(display_bookings_for_cancellation, pattern='^cancel_booking$'))
    dispatcher.add_handler(CallbackQueryHandler(start_command, pattern='^add_user '))

    # Start the bot
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()