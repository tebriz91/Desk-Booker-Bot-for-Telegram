import sqlite3
import threading
import config
from logger import Logger

# Global lock for database operations
db_lock = threading.Lock()

# Logger instance
logger = Logger.get_logger(__name__)

def execute_db_query(query, parameters=(), fetch_one=False, fetch_all=False):
    db_path = config.DB_PATH
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
    return cursor.fetchall() if not (fetch_one or fetch_all) else None

# Usage in other modules:
# from db_queries import execute_db_query
# execute_db_query("SELECT * FROM rooms")