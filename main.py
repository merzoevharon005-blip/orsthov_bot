import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = "8275887470:AAHckltQmADi9oLlNTPFmSHxchgzGFwH9qQ"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Привет! Я работаю! 🤖')

async def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    
    print("✅ Бот запущен!")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
