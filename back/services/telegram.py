import os
from telegram import Bot, Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

class Telegram:
    def __init__(self, app):
        TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

        self.app = app
        self.token_url = f'https://api.telegram.org/bot{TOKEN}/getUpdates'

        # self.bot = Bot(token=TOKEN)

        self.bot = ApplicationBuilder().token(TOKEN).build()
        self.bot.add_handler(CommandHandler("help", self.help))
        self.bot.run_polling()


    # async def notify(self, user):
    #     await self.bot.send_message(chat_id=user["chatId"], text='Hello, this is a notification!')


    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        # Get the chat ID of the user who sent the command
        # Send a help message to the user
        await update.message.reply_text(f'Hello {update.effective_user.first_name}')