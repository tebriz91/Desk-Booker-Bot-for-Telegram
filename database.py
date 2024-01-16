import sqlite3
import os
import threading

import config
import rooms_config
import logging_setup

db_path = config.DB_PATH
admin_user_id = config.ADMIN_USER_ID
admin_username = config.ADMIN_USERNAME
logger = logging_setup.logger

# Ensure the 'data' directory for databases exists
os.makedirs(os.path.dirname(db_path), exist_ok=True)

db_lock = threading.Lock() # Global lock object that will be used to control access to the database for write operations

def initialize_database():
    # Initialize database
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        # Create Rooms table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rooms (
                room_id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_name TEXT NOT NULL,
                room_availability INTEGER NOT NULL DEFAULT 1,
                plan_url TEXT,
                room_add_info TEXT
            )
        ''')

        # Create Desks table
        cursor.execute('''
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
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER UNIQUE,
                username TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0,
                is_delisted INTEGER DEFAULT 0,
                user_registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create Bookings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                booking_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                desk_id INTEGER NOT NULL,
                booking_date DATE NOT NULL,
                booking_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (desk_id) REFERENCES desks(desk_id) ON DELETE CASCADE
            )
        ''')

        conn.commit()

def initialize_admin_user():
    admin_user_exists = execute_db_query("SELECT user_id FROM users WHERE user_id = ?", (admin_user_id,), fetch_one=True)
    if not admin_user_exists:
        execute_db_query("INSERT INTO users (user_id, username, is_admin) VALUES (?, ?, 1)", (admin_user_id, admin_username))
        logger.info(f"Admin user {admin_username} added to the database.")

# Updated execute_db_query function
def execute_db_query(query, parameters=(), fetch_one=False, fetch_all=False):
    try:
        with db_lock:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(query, parameters)
                if fetch_one:
                    return cursor.fetchone()
                elif fetch_all:
                    return cursor.fetchall()
                else:
                    conn.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        raise
    result = cursor.fetchall()
    return result or []