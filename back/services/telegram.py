import os
from telegram import Bot, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

class Telegram:
    def __init__(self, app):
        self.TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

        self.app = app
        self.bot = Bot(token=self.TOKEN)
        self.telegram_app = ApplicationBuilder().token(self.TOKEN).build()
        self.token_url = f'https://api.telegram.org/bot{self.TOKEN}/getUpdates'

    async def initialize(self):
        self.telegram_app.add_handler(CommandHandler("help", self.help))
        self.telegram_app.add_handler(CommandHandler("start", self.start))
        self.telegram_app.add_handler(CommandHandler("stop", self.stop))
        self.telegram_app.add_handler(CommandHandler("log_level", self.log_level))
        await self.telegram_app.initialize()
        await self.telegram_app.start()
        await self.telegram_app.updater.start_polling()
        # self.bot.send_message(chat_id=1031182213, text='hey t')

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        bot = await self.app.db.bot.find_one()

        if bot["account"]["data"]["active"]:
            await update.message.reply_text('Bot Already Running')
        else:
            bot_update = {
                "account": {
                    "active": True
                }
            }
            await self.app.database.update(bot, bot_update, 'bot')
            await update.message.reply_text('Bot Started')

    async def stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        bot = await self.app.db.bot.find_one()

        if bot["account"]["data"]["active"]:
            bot_update = {
                "account": {
                    "active": False
                }
            }
            await self.app.database.update(bot, bot_update, 'bot')
            await update.message.reply_text('Bot Stopped')
        else:
            await update.message.reply_text('Bot Already Stopped')

    async def log_level(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        bot = await self.app.db.bot.find_one()

        if bot["detail"]["data"]["log_level"] == 'ERROR':
            bot_update = {
                "detail": {
                    "log_level": 'INFO'
                }
            }
            await self.app.database.update(bot, bot_update, 'bot')
            await update.message.reply_text('Log Level: INFO')
            
        elif bot["detail"]["data"]["log_level"] == 'INFO':
            bot_update = {
                "detail": {
                    "log_level": 'ERROR'
                }
            }
            await self.app.database.update(bot, bot_update, 'bot')
            await update.message.reply_text('Log Level: ERROR')

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        # Get the chat ID of the user who sent the command
        # Send a help message to the user
        await update.message.reply_text(f'Hello {update.effective_user.first_name}')

    async def cleanup(self):
        await self.telegram_app.updater.stop()
        await self.telegram_app.stop()
        await self.telegram_app.shutdown()