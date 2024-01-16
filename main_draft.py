"""
from telegram.ext import Updater
import config  # Import your bot's configuration

from handlers import register_handlers  # Import the register function

def main():
    updater = Updater(config.BOT_TOKEN, use_context=True)
    register_handlers(updater.dispatcher)  # Register all bot handlers
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
"""