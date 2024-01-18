import logging
import pytz
from datetime import datetime
import config

class Logger:
    _instance = None

    @staticmethod
    def get_logger(name=__name__, level=logging.INFO, fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt=None, tz=config.LOG_TIMEZONE):
        if Logger._instance is None:
            Logger()
        Logger._instance.logger.setLevel(level)
        Logger._instance.set_formatter(fmt, datefmt, tz)
        return Logger._instance.logger
    
    def __init__(self):
        if Logger._instance is not None:
            raise Exception("This class is a singleton!")
        else:
            Logger._instance = self
            self.logger = logging.getLogger(__name__)
            self.handler = logging.StreamHandler()
            self.logger.addHandler(self.handler)
    
    def set_formatter(self, fmt, datefmt, tz):
        timezone = pytz.timezone(tz)
        formatter = logging.Formatter(fmt, datefmt)
        formatter.converter = lambda timestamp: datetime.fromtimestamp(timestamp, timezone).timetuple()
        self.handler.setFormatter(formatter)

# Usage in other modules
# from logger import Logger
# logger_instance = Logger.get_logger(name, logging.INFO)
# logger_instance.info("This is an info message")