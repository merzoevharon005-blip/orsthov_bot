
import os
import sqlite3
import random
import telebot

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 8211650013

bot = telebot.TeleBot(TOKEN)

# База данных
db = sqlite3.connect("mon.db", check_same_thread=False)
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS players (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    balance INTEGER DEFAULT 1000
)
""")
db.commit()


def register_user(user):
    cursor.execute(
        "INSERT OR IGNORE INTO players (user_id, username) VALUES (?, ?)",
        (user.id, user.username or user.first_name)
    )
    db.commit()


@bot.message_handler(commands=['start'])
def start(message):
    register_user(message.from_user)
    bot.reply_to(
        message,
        "🎮 Добро пожаловать в MONIX GAME!\n\n"
        "Команды:\n"
        "/profile — профиль\n"
        "/balance — баланс\n"
        "/top — топ игроков\n"
        "/guess — угадай число"
    )


@bot.message_handler(commands=['profile'])
def profile(message):
    register_user(message.from_user)
    cursor.execute(
        "SELECT balance FROM players WHERE user_id = ?",
        (message.from_user.id,)
    )
    balance = cursor.fetchone()[0]

    bot.reply_to(
        message,
        f"👤 Твой профиль\n\n"
        f"🆔 ID: {message.from_user.id}\n"
        f"💰 Баланс: {balance} монет"
    )


@bot.message_handler(commands=['balance'])
def balance(message):
    register_user(message.from_user)
    cursor.execute(
        "SELECT balance FROM players WHERE user_id = ?",
        (message.from_user.id,)
    )
    amount = cursor.fetchone()[0]
    bot.reply_to(message, f"💰 Твой баланс: {amount} монет")


@bot.message_handler(commands=['give'])
def give(message):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        _, user_id, amount = message.text.split()
        user_id = int(user_id)
        amount = int(amount)

        if amount <= 0:
            bot.reply_to(message, "❌ Сумма должна быть больше нуля")
            return

        cursor.execute(
            "UPDATE players SET balance = balance + ? WHERE user_id = ?",
            (amount, user_id)
        )
        db.commit()

        if cursor.rowcount:
            bot.reply_to(message, f"✅ Выдано {amount} монет игроку {user_id}")
        else:
            bot.reply_to(message, "❌ Игрок не найден")

    except ValueError:
        bot.reply_to(message, "Использование: /give ID СУММА")


@bot.message_handler(commands=['top'])
def top(message):
    cursor.execute(
        "SELECT username, balance FROM players ORDER BY balance DESC LIMIT 10"
    )
    players = cursor.fetchall()

    text = "🏆 ТОП-10 MONIX GAME\n\n"

    for i, player in enumerate(players, 1):
        text += f"{i}. {player[0]} — {player[1]} монет\n"

    bot.reply_to(message, text)


@bot.message_handler(commands=['guess'])
def guess(message):
    number = random.randint(1, 5)
    bot.reply_to(message, "🎲 Угадай число от 1 до 5!")

    bot.register_next_step_handler(
        message,
        lambda msg: check_guess(msg, number)
    )


def check_guess(message, number):
    try:
        answer = int(message.text)

        if answer == number:
            cursor.execute(
                "UPDATE players SET balance = balance + 100 WHERE user_id = ?",
                (message.from_user.id,)
            )
            db.commit()
            bot.reply_to(message, "🎉 Правильно! Ты выиграл 100 монет!")
        else:
            bot.reply_to(message, f"❌ Не угадал! Было число {number}")

    except ValueError:
        bot.reply_to(message, "Введи число от 1 до 5")


print("MONIX GAME запущен!")
bot.infinity_polling()
