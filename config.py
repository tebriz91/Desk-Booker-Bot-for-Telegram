import os

# Bot Configuration
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Database Configuration
DB_PATH = os.getenv('DB_PATH', 'data/database.db')

# Admin Configuration
ADMIN_USER_ID = os.getenv('ADMIN_USER_ID')
ADMIN_USERNAME = os.getenv('ADMIN_USERNAME')

# Logging Time Zone Configuration
LOG_TIMEZONE = os.getenv('LOG_TIMEZONE', 'default_timezone')

# Date Generation Configuration
NUM_DAYS = int(os.getenv('NUM_DAYS', '5'))
EXCLUDE_WEEKENDS = os.getenv('EXCLUDE_WEEKENDS', 'True') == 'True'
COUNTRY_CODE = os.getenv('COUNTRY_CODE')  # Defaults to None if not set