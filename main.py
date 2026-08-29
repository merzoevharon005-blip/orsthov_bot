from flask import Flask
import os
import threading
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

app = Flask(__name__)
TOKEN = "8275887470:AAHckltQmADi9oLlNTPFmSHxchgzGFwH9qQ"

@app.route('/')
def home():
    return "Бот работает!"

@app.route('/health')
def health():
    return "OK"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Привет! Я бот и работаю на Render! 🤖')

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Напиши /start чтобы начать')

def run_bot():
    if not TOKEN:
        print("ОШИБКА: Токен не найден!")
        return
    app_bot = ApplicationBuilder().token(TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("help", help))
    print("✅ Бот успешно запущен и слушает команды!")
    app_bot.run_polling()

if __name__ == '__main__':
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)
