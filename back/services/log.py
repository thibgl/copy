import os
import logging
from lib import utils
from telegram import Bot

# ! https://sematext.com/blog/logging-levels/

class Log:
    def __init__(self, app):
        TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

        self.app = app
        self.bot = Bot(token=TOKEN)
        self.token_url = f'https://api.telegram.org/bot{TOKEN}/getUpdates'

    async def create(self, user, level, source, category, message, details='', notify=True, collection=None, itemId=None):
        log = {
            "userId": user["_id"],
            "createdAt": utils.current_time(),
            "level": level,
            "notification": notify,
            "source": source,
            "category": category,
            "message": message,
            "details": details
        }

        if collection and itemId:
            log = log | {"collection": collection, "itemId": itemId}

        self.app.db.log.insert_one(log)

        content = f'[{utils.current_readable_time()}]: {level} <{source}> {category}: {message}'

        print(content)

        if notify and user["chatId"]:
            await self.notify(user, content)
    
    async def notify(self, user, content):
        await self.bot.send_message(chat_id=user["chatId"], text=content)
