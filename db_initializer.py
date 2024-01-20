import aiosqlite
import asyncio
import os
import config
from logger import Logger
from db_queries import execute_db_query

# Logger instance
logger = Logger.get_logger(__name__)

async def initialize_database():
    db_path = config.DB_PATH
    # Ensure the 'data' directory for databases exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    # Initialize database
    async with aiosqlite.connect(db_path) as conn:
        cursor = await conn.cursor()
        
        # Create Rooms table
        await cursor.execute('''
            CREATE TABLE IF NOT EXISTS rooms (
                room_id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_name TEXT NOT NULL,
                room_availability INTEGER NOT NULL DEFAULT 1,
                plan_url TEXT,
                room_add_info TEXT
            )
        ''')

        # Create Desks table
        await cursor.execute('''
            CREATE TABLE IF NOT EXISTS desks (
                desk_id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id INTEGER NOT NULL,
                desk_number INTEGER NOT NULL,
                desk_availability INTEGER NOT NULL DEFAULT 1,
                desk_add_info TEXT,
                FOREIGN KEY (room_id) REFERENCES rooms(room_id) ON DELETE SET NULL
            )
        ''')

        # Create Users table
        await cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER UNIQUE,
                username TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0,
                is_delisted INTEGER DEFAULT 0,
                user_registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create Bookings table
        await cursor.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                booking_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                desk_id INTEGER NOT NULL,
                booking_date DATE NOT NULL,
                booking_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (desk_id) REFERENCES desks(desk_id) ON DELETE CASCADE
            )
        ''')

        await conn.commit()

async def initialize_superadmin_user():
    admin_user_id = config.ADMIN_USER_ID
    admin_username = config.ADMIN_USERNAME
    admin_user_exists = await execute_db_query("SELECT user_id FROM users WHERE user_id = ?", (admin_user_id,), fetch_one=True)
    if not admin_user_exists:
        await execute_db_query("INSERT INTO users (user_id, username, is_admin) VALUES (?, ?, 1)", (admin_user_id, admin_username))
        logger.info(f"Admin user {admin_username} added to the database.")