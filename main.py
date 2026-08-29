from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext

TOKEN = "8275887470:AAHckltQmADi9oLlNTPFmSHxchgzGFwH9qQ"

def start(update: Update, context: CallbackContext):
    update.message.reply_text('Привет! Я работаю! 🤖')

updater = Updater(token=TOKEN)
updater.dispatcher.add_handler(CommandHandler("start", start))

print("✅ Бот запущен!")
updater.start_polling()
updater.idle()
