from dotenv import load_dotenv
load_dotenv()

import asyncio

from telegram.ext import CommandHandler, CallbackQueryHandler, ApplicationBuilder

import config

from db_initializer import initialize_database, initialize_admin_user

from user_manager import start_command, add_user, remove_user, make_admin, revoke_admin, delist_user, list_user, view_users

from room_manager import add_room, add_desk, edit_room_name, edit_plan_url, edit_desk_number, remove_room, remove_desk, set_room_availability, set_desk_availability, view_rooms

from booking_manager import start_booking_process, date_selected, room_selected, desk_selected, cancel_button, cancel_booking, display_bookings_for_cancellation, cancel_booking_by_id, view_my_bookings, view_all_bookings, view_booking_history

from utilities import admin_commands, help_command, dump_database

def main():
    # Create a new event loop and set it as the current one
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Asynchronously initialize the database and admin user
    loop.create_task(initialize_database())
    loop.create_task(initialize_admin_user())

    # Create an instance of Application
    application = ApplicationBuilder().token(config.BOT_TOKEN).build()
    
    # Register handlers
    application.add_handler(CommandHandler('start', start_command))
    application.add_handler(CommandHandler('start', start_command))
    application.add_handler(CommandHandler('add_user', add_user))
    application.add_handler(CommandHandler('remove_user', remove_user))
    application.add_handler(CommandHandler('make_admin', make_admin))
    application.add_handler(CommandHandler('revoke_admin', revoke_admin))
    application.add_handler(CommandHandler('delist_user', delist_user))
    application.add_handler(CommandHandler('list_user', list_user))
    application.add_handler(CommandHandler('view_users', view_users))
    application.add_handler(CommandHandler('add_room', add_room))
    application.add_handler(CommandHandler('add_desk', add_desk))
    application.add_handler(CommandHandler('edit_room_name', edit_room_name))
    application.add_handler(CommandHandler('edit_plan_url', edit_plan_url))
    application.add_handler(CommandHandler('edit_desk_number', edit_desk_number))
    application.add_handler(CommandHandler('set_room_availability', set_room_availability))
    application.add_handler(CommandHandler('set_desk_availability', set_desk_availability))
    application.add_handler(CommandHandler('remove_room', remove_room))
    application.add_handler(CommandHandler('remove_desk', remove_desk))
    application.add_handler(CommandHandler('view_rooms', view_rooms))
    application.add_handler(CommandHandler('book', start_booking_process))
    application.add_handler(CommandHandler("cancel", display_bookings_for_cancellation))
    application.add_handler(CommandHandler("cancel_booking", cancel_booking_by_id))
    application.add_handler(CommandHandler("my_bookings", view_my_bookings))
    application.add_handler(CommandHandler("all_bookings", view_all_bookings))
    application.add_handler(CommandHandler("history", view_booking_history))
    application.add_handler(CommandHandler('admin', admin_commands))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('dump_db', dump_database))

    # Register CallbackQueryHandler for handling button presses
    application.add_handler(CallbackQueryHandler(date_selected, pattern='^date_'))
    application.add_handler(CallbackQueryHandler(room_selected, pattern='^room_'))
    application.add_handler(CallbackQueryHandler(desk_selected, pattern='^desk_'))
    application.add_handler(CallbackQueryHandler(cancel_button, pattern='^cancelbutton'))
    application.add_handler(CallbackQueryHandler(cancel_booking, pattern='^cancel_'))
    application.add_handler(CallbackQueryHandler(display_bookings_for_cancellation, pattern='^cancel_booking$'))
    application.add_handler(CallbackQueryHandler(start_command, pattern='^add_user '))

    # Start the bot
    application.run_polling()

if __name__ == '__main__':
    main()