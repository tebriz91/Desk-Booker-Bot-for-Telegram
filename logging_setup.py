import logging
import pytz
from datetime import datetime

import config

log_timezone = config.LOG_TIMEZONE

# Configure Time Zone for logging. This allows you change the logging time zone by updating the LOG_TIMEZONE variable in your config.py file
class ConfigurableTimeZoneFormatter(logging.Formatter):
    def __init__(self, fmt=None, datefmt=None, style='%', tz=log_timezone):
        super().__init__(fmt, datefmt, style)
        self.tz = pytz.timezone(tz)

    def converter(self, timestamp):
        return datetime.fromtimestamp(timestamp, self.tz)

    def formatTime(self, record, datefmt=None):
        dt = self.converter(record.created)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()

# Enable logging
formatter = ConfigurableTimeZoneFormatter(fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler = logging.StreamHandler()
handler.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(handler)