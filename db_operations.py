import sqlite3
import os
import subprocess
import config
from logger import Logger

# Logger instance
logger = Logger.get_logger(__name__)

def create_database_dump(db_path, output_file):
    """
    Creates a dump of the SQLite database.

    :param db_path: Path to the SQLite database file.
    :param output_file: Path where the dump file will be saved.
    :return: Path to the output dump file.
    """
    try:
        # Use the full command in a single string
        command = f"sqlite3 {db_path} .dump > {output_file}"
        subprocess.run(command, check=True, shell=True, stderr=subprocess.PIPE)

        logger.info(f"Database dump created successfully at {output_file}")
        return output_file
    except subprocess.CalledProcessError as e:
        logger.error(f"Error creating database dump: {e.stderr.decode()}")
        return None

def clean_up_dump_file(dump_file):
    """
    Deletes the database dump file.

    :param dump_file: Path to the dump file to be deleted.
    """
    try:
        if os.path.exists(dump_file):
            os.remove(dump_file)
            logger.info(f"Database dump file {dump_file} deleted successfully")
    except Exception as e:
        logger.error(f"Error deleting dump file {dump_file}: {e}")
