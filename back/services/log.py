import os
import logging
from lib import utils
import uuid
import bson

# ! https://sematext.com/blog/logging-levels/

levels = ["INFO", "ERROR"]

class Log:
    def __init__(self, app):
        TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

        self.app = app
        self.token_url = f'https://api.telegram.org/bot{TOKEN}/getUpdates'

    async def create(self, bot, user, level, source, category, message, details='', notify=True, insert=True, collection=None, itemId=None):
        log_id = uuid.uuid4()
        log = {
            "id": bson.Binary(log_id.bytes, subtype=bson.binary.UUID_SUBTYPE),
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

        if insert:
            self.app.db.log.insert_one(log)

        content = f'[{utils.current_readable_time()}]: {level} <{source}> {category}: {message} ({log_id})'
        
        print(content)

        level_included = level in levels[levels.index(bot["detail"]["data"]["log_level"]):]
        if notify and user["detail"]["data"]["chat_id"] and level_included:
            await self.notify(user, content)
    
    async def notify(self, user, content):
        try:
            await self.app.telegram.bot.send_message(chat_id=user["detail"]["data"]["chat_id"], text=content)
        except Exception as e:
            pass

