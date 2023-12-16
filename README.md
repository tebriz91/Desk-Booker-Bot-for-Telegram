# Desk Booker for Hybrid Workspaces

## Introduction

This Telegram bot, **Desk Booker**, is designed to facilitate desk booking in a hybrid office environment. It's ideal for office workers who work in a hybrid mode and need to book desks on days they plan to be in the office. The bot integrates seamlessly with Telegram, making it easy for coworkers to manage their bookings.

![Text](/assets/images/screencast.gif?raw=true)

## Features
- **Desk Booking**: Book a desk for a specific date.
- **View Bookings**: Check your upcoming bookings or view all bookings.
- **Admin Management**: Admin users can manage users, make admins, blacklist users, and view booking history.
- **Data Storage**: Uses SQLite databases to store user and booking information.

## Prerequisites

- Python 3.x
- python-telegram-bot 13.4.1 library
- SQLite3

## Setup and Installation

1. Clone the repository:
```bash
git clone https://github.com/tebriz91/Desk-Booker-Bot-for-Telegram
```
2. Install dependencies:
```bash
pip install python-telegram-bot sqlite3
```
3. Set up your Telegram bot:
- Create a new bot via BotFather on Telegram.
- Obtain your unique bot token.
4. Configure the bot:
- Replace TELEGRAM_BOT_TOKEN in the main() function with your bot token.
- Set your Telegram user ID and username in the admin_user_id and admin_username variables for admin access.
5. Start the bot:
```bash
python main.py
```

## Usage

### Commands

- **/start**: Start interacting with the bot.
- **/book_table**: Book a desk for a specific date.
- **/view_my_bookings**: View your upcoming bookings.
- **/view_all_bookings**: View all desk bookings.
- **/manage_users**: Access user management options (Admin only).
- **/add_user**: Add a new user (Admin only).
- **/make_admin**: Grant admin privileges to a user (Admin only).
- **/blacklist_user**: Blacklist a user (Admin only).
- **/remove_user**: Remove a user from the system (Admin only).
- **/revoke_admin**: Revoke admin privileges (Admin only).
- **/view_users**: View all users and their status (Admin only).
- **/history**: View all booking history for the past 2 weeks (Admin only).
- **/cancel_booking**: Cancel a booking by its ID (Admin only).

### Inline Buttons

- Users can interact with the bot using inline buttons for a seamless experience.
- Admins have additional inline buttons for user and booking management.

## Database Structure

- bookings.db: Stores booking details.
- users.db: Stores user information and admin status.

## Logging

The bot uses logging to track activities and errors.

## Contributing
Feel free to fork the repository, make changes, and create a pull request. Contributions are welcome!

## License

[MIT License](https://github.com/git/git-scm.com/blob/main/MIT-LICENSE.txt)
