import os
from telegram import Bot

class Telegram:
    def __init__(self, app):
        self.app = app
        self.bot = Bot(token=os.environ.get('TELEGRAM_BOT_TOKEN'))

    def notify(self, user):
        self.bot.send_message(chat_id=user["chatId"], text='Hello, this is a notification!')