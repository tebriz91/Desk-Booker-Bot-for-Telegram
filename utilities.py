import os
import asyncio
import subprocess
import csv
import zipfile
import tempfile
import shutil
from datetime import datetime
from telegram import Update
from telegram.ext import CallbackContext
import config
from logger import Logger
from db_queries import execute_db_query
from decorators import superadmin_required, admin_required, user_required

logger = Logger.get_logger(__name__)

@admin_required
async def admin_commands(update: Update, context: CallbackContext) -> None:
    message_text = "User Management:\n\n"
    message_text += "/add_user [user_id] [username] - Add a new user\n"
    message_text += "/delist_user [user_id] - Delist a user\n"
    message_text += "/remove_user [user_id] - Remove a user\n"
    message_text += "/view_users - View all users and their status\n"
    
    message_text += "\nRooms & Desks Management:\n\n"
    message_text += "/view_rooms - View all rooms and desks\n"
    message_text += "/add_room [room_name] - Add a new room\n"
    message_text += "/add_desk [room_id] [desk_number] - Add a new desk\n"
    message_text += "/set_room_availability [room_id] [room_availability] - Set room availability\n"
    message_text += "/set_desk_availability [desk_id] [desk_availability] - Set desk availability\n"
    message_text += "/remove_room [room_id] - Remove a room and associated desks and bookings\n"
    message_text += "/remove_desk [room_id] [desk_number] - Remove a desk and associated bookings\n"
    message_text += "/edit_room_name [room_id] [new_room_name] - Edit a room name\n"
    message_text += "/edit_plan_url [room_id] [new_plan_url] - Edit a room plan URL\n"
    message_text += "/edit_desk_number [desk_id] [new_desk_number] - Edit a desk number\n"
    
    message_text += "\nBookings Management:\n\n"
    message_text += "/history - View all booking history for the past 2 weeks\n"
    message_text += "/cancel_booking - Cancel a booking by its id\n"
    
    # message_text = "\nAdmin Management:\n\n"
    # message_text += "/make_admin [user_id] - Make a user an admin\n"
    # message_text += "/revoke_admin [user_id] - Revoke admin status\n"
    # message_text += "/dump_db - Create and send a database dump\n"
    
    await update.message.reply_text(message_text)

@user_required
async def help_command(update: Update, context: CallbackContext) -> None:
    message_text = (f"Contact @{config.ADMIN_USERNAME} if you need help.")
    await update.message.reply_text(message_text)

@superadmin_required
async def dump_database(update, context):
    try:
        zip_file_path, csv_dir = await dump_database_to_csv(config.DB_PATH)
        with open(zip_file_path, 'rb') as f:
            await context.bot.send_document(chat_id=update.effective_chat.id, document=f)
        os.remove(zip_file_path)  # Clean up the ZIP file after sending
        shutil.rmtree(csv_dir)    # Delete the 'csv_dump' directory
        logger.info("Database CSV dump sent and cleaned up successfully")
    except Exception as e:
        await update.message.reply_text("Failed to create database CSV dump.")
        logger.error(f"Error in dump_database command: {e}")

async def dump_database_to_csv(db_path):
    # Fetch all table names
    tables = await execute_db_query("SELECT name FROM sqlite_master WHERE type='table';", fetch_all=True)

    # Directory to store CSV files
    csv_dir = 'csv_dump'
    os.makedirs(csv_dir, exist_ok=True)

    for table in tables:
        table_name = table[0]
        csv_file_path = os.path.join(csv_dir, f"{table_name}.csv")

        # Fetch table data and column names
        data = await execute_db_query(f"SELECT * FROM {table_name}", fetch_all=True)
        column_names = await execute_db_query(f"PRAGMA table_info({table_name});", fetch_all=True)
        column_names = [col[1] for col in column_names]

        # Write data to CSV
        with open(csv_file_path, 'w', newline='', encoding='utf-8') as csv_file:
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(column_names)  # write header
            csv_writer.writerows(data)

    # Create a zip file
    zip_file_name = datetime.now().strftime("%Y-%m-%d_%H-%M-%S.zip")
    zip_file_path = os.path.join(csv_dir, zip_file_name)
    with zipfile.ZipFile(zip_file_path, 'w') as zipf:
        for root, dirs, files in os.walk(csv_dir):
            for file in files:
                if file.endswith('.csv'):
                    zipf.write(os.path.join(root, file), file)

    # Return both the path of the ZIP file and the path of the csv directory
    return zip_file_path, csv_dir

@superadmin_required
async def restore_database(update, context):
    # Set a flag in the user context to indicate that we're expecting a dump file
    context.user_data['awaiting_dump_file'] = True
    await update.message.reply_text("Please send the database dump file.")

@superadmin_required
async def handle_dump_file(update: Update, context: CallbackContext) -> None:
    user_data = context.user_data

    if user_data.get('awaiting_dump_file') and update.message.document:
        document = update.message.document
        if document.file_name.endswith('.zip'):
            user_data['awaiting_dump_file'] = False
            
            # Get basic file info
            file = await context.bot.get_file(document.file_id)

            # Create a temporary directory
            with tempfile.TemporaryDirectory() as temp_dir:
                local_file_path = os.path.join(temp_dir, document.file_name)

                # Download the file
                await file.download_to_drive(custom_path=local_file_path)

                # Extract ZIP file
                with zipfile.ZipFile(local_file_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)

                # Handle CSV files
                for filename in ['users.csv', 'rooms.csv', 'desks.csv', 'bookings.csv']:
                    csv_path = os.path.join(temp_dir, filename)
                    if os.path.exists(csv_path):
                        await handle_csv_file(filename, csv_path)

            # No need to manually clean up, tempfile handles it

            await update.message.reply_text("Database updated from ZIP file.")
        else:
            await update.message.reply_text("Please send a valid ZIP file.")
    else:
        await update.message.reply_text("No file received or not expecting a file.")

async def handle_csv_file(filename, file_path):
    # Read and process the CSV file
    # This is a placeholder for the function logic
    if filename == 'users.csv':
        await process_users_csv(file_path)
    elif filename == 'rooms.csv':
        await process_rooms_csv(file_path)
    elif filename == 'desks.csv':
        await process_desks_csv(file_path)
    elif filename == 'bookings.csv':
        await process_bookings_csv(file_path)
    else:
        logger.error(f"Unknown CSV file: {filename}")

async def process_users_csv(file_path):
    with open(file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            user_id = row['user_id']
            username = row['username']
            is_admin = row['is_admin']
            is_delisted = row['is_delisted']
            user_registration_date = row['user_registration_date']
            await execute_db_query("INSERT OR REPLACE INTO users (user_id, username, is_admin, is_delisted, user_registration_date) VALUES (?, ?, ?, ?, ?)", (user_id, username, is_admin, is_delisted, user_registration_date))

async def process_rooms_csv(file_path):
    with open(file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            room_id = row['room_id']
            room_name = row['room_name']
            room_availability = row['room_availability']
            plan_url = row['plan_url']
            room_add_info = row['room_add_info']
            await execute_db_query("INSERT OR REPLACE INTO rooms (room_id, room_name, room_availability, plan_url, room_add_info) VALUES (?, ?, ?, ?, ?)", (room_id, room_name, room_availability, plan_url, room_add_info))

async def process_desks_csv(file_path):
    with open(file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            desk_id = row['desk_id']
            room_id = row['room_id']
            desk_number = row['desk_number']
            desk_availability = row['desk_availability']
            desk_add_info = row['desk_add_info']
            await execute_db_query("INSERT OR REPLACE INTO desks (desk_id, room_id, desk_number, desk_availability, desk_add_info) VALUES (?, ?, ?, ?, ?)", (desk_id, room_id, desk_number, desk_availability, desk_add_info))

async def process_bookings_csv(file_path):
    with open(file_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            booking_id = row['booking_id']
            user_id = row['user_id']
            desk_id = row['desk_id']
            booking_date = row['booking_date']
            booking_timestamp = row['booking_timestamp']
            await execute_db_query("INSERT OR REPLACE INTO bookings (booking_id, user_id, desk_id, booking_date, booking_timestamp) VALUES (?, ?, ?, ?, ?)", (booking_id, user_id, desk_id, booking_date, booking_timestamp))