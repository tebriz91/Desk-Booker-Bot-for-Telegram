import aiosqlite
import asyncio
import config
from logger import Logger

# Global lock for database operations
db_lock = asyncio.Lock()

# Logger instance
logger = Logger.get_logger(__name__)

async def execute_db_query(query, parameters=(), fetch_one=False, fetch_all=False):
    db_path = config.DB_PATH
    try:
        async with db_lock:
            async with aiosqlite.connect(db_path) as conn:
                cursor = await conn.cursor()
                await cursor.execute(query, parameters)
                if fetch_one:
                    return await cursor.fetchone()
                elif fetch_all:
                    return await cursor.fetchall()
                else:
                    await conn.commit()
    except aiosqlite.Error as e:
        logger.error(f"Database error: {e}")
        raise
    return None # return None if fetch_one or fetch_all is not True

# Usage in other modules:
# from db_queries import execute_db_query
# await execute_db_query("SELECT * FROM)