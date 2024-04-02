import os
from telegram import Bot

class Telegram:
    def __init__(self, app):
        TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

        self.app = app
        self.bot = Bot(token=TOKEN)
        self.token_url = f'https://api.telegram.org/bot{TOKEN}/getUpdates'

    async def notify(self, user):
        await self.bot.send_message(chat_id=user["chatId"], text='Hello, this is a notification!')