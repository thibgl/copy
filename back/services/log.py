from lib import utils

class Log:
    def __init__(self, app):
        self.app = app

    def create(self, user, source, subject, message, notify=True):
        self.app.db.log.insert_one({
            "userId": user["_id"],
            "createdAt": utils.current_time(),
            "notification": notify,
            "source": source,
            "subject": subject,
            "message": message,
        })

        content = f'[{utils.current_readable_time()}]: Ajusted Position: LOG'
        print(content)

        if notify:
            self.app.telegram.send_message(content)