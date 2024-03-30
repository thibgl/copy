from lib import utils

class Log:
    def __init__(self, app):
        self.app = app

    def create(self, user, source, subject, message, notify=True, collection=None, itemId=None):
        log = {
            "userId": user["_id"],
            "createdAt": utils.current_time(),
            "notification": notify,
            "source": source,
            "subject": subject,
            "message": message,
        }

        if collection and itemId:
            log = log | {"collection": collection, "itemId": itemId}

        self.app.db.log.insert_one(log)

        content = f'[{utils.current_readable_time()}]: Ajusted Position: LOG'

        print(content)

        if notify and user["chatId"]:
            self.app.telegram.send_message(content)