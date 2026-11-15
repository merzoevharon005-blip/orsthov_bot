import os
import sqlite3
import random
import math
import time
import telebot
import threading
import re
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("Не задан BOT_TOKEN")

ADMIN_ID = 8211650013 # ЗАМЕНИТЕ НА СВОЙ ID!

bot = telebot.TeleBot(TOKEN)
db = sqlite3.connect("mon.db", check_same_thread=False)
cursor = db.cursor()

# --- БАЗА ДАННЫХ ---
cursor.execute("CREATE TABLE IF NOT EXISTS players (user_id INTEGER PRIMARY KEY, username TEXT, balance INTEGER DEFAULT 1000)")
cursor.execute("CREATE TABLE IF NOT EXISTS promos (code TEXT PRIMARY KEY, amount INTEGER, uses_left INTEGER)")
cursor.execute("CREATE TABLE IF NOT EXISTS promo_activations (user_id INTEGER, code TEXT, PRIMARY KEY (user_id, code))")
cursor.execute("""
CREATE TABLE IF NOT EXISTS roulette_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number INTEGER,
    color TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")
# Новая таблица для истории переводов
cursor.execute("""
CREATE TABLE IF NOT EXISTS transfers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id INTEGER,
    sender_name TEXT,
    receiver_id INTEGER,
    receiver_name TEXT,
    amount INTEGER,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")
db.commit()

mines_games = {}
crash_games = {}
roulette_sessions = {}

# --- БАЗОВЫЕ ФУНКЦИИ ---
def get_balance(user_id):
    cursor.execute("SELECT balance FROM players WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    return res[0] if res else 0

def add_balance(user_id, amount):
    cursor.execute("UPDATE players SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    db.commit()

def register_user(user):
    cursor.execute("INSERT OR IGNORE INTO players (user_id, username) VALUES (?, ?)", (user.id, user.username or user.first_name))
    db.commit()

def get_history_roulette():
    cursor.execute("SELECT number, color FROM roulette_history ORDER BY id DESC LIMIT 15")
    history = cursor.fetchall()
    if not history: return "История пуста."
    res = []
    for num, color in history:
        sym = "🟢" if color == "green" else ("🔴" if color == "red" else "⚫️")
        res.append(f"{sym}{num}")
    return " ".join(res)

def main_menu():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("💣 MINES", callback_data="game_mines"),
        InlineKeyboardButton("🚀 CRASH", callback_data="game_crash"),
        InlineKeyboardButton("🎰 РУЛЕТКА", callback_data="game_roulette"),
        InlineKeyboardButton("👤 ПРОФИЛЬ", callback_data="profile"),
        InlineKeyboardButton("❓ ПОМОЩЬ", callback_data="help_menu")
    )
    return kb

# --- СТАРТ И ПОМОЩЬ ---
@bot.message_handler(commands=["start"])
def start(message):
    register_user(message.from_user)
    bot.send_message(message.chat.id, 
        f"🎰 ДОБРО ПОЖАЛОВАТЬ В MON1 CASINO!\n\n"
        f"🪙 Твой баланс: {get_balance(message.from_user.id)} Mon1Coin\n\n"
        f"Выбирай игру или напиши `помощь`:", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda call: call.data == "help_menu")
@bot.message_handler(func=lambda message: message.text.lower().strip() in ["помощь", "help"])
def send_help(message_or_call):
    if isinstance(message_or_call, telebot.types.CallbackQuery):
        chat_id = message_or_call.message.chat.id
        bot.answer_callback_query(message_or_call.id)
    else:
        chat_id = message_or_call.chat.id

    help_text = (
        "📖 **ПОЛНАЯ ИНСТРУКЦИЯ MON1 CASINO**\n\n"
        "🪙 **Валюта:** Mon1Coin\n\n"
        "**👤 БАЗОВЫЕ КОМАНДЫ**\n"
        "`б` или `баланс` — баланс\n"
        "`профиль` — ваш ID и баланс\n\n"
        "**📜 ИСТОРИЯ**\n"
        "`лог` — последние 15 чисел рулетки\n"
        "`история` — история ваших переводов\n\n"
        "**💸 ПЕРЕВОДЫ**\n"
        "`перевод 100 @username` — перевести монеты\n\n"
        "**🎁 ПРОМОКОДЫ**\n"
        "Просто напишите код (например: `MONIX`).\n\n"
        "**🎮 БЫСТРЫЙ ЗАПУСК ИГР**\n"
        "`мины 1000` — сапер со ставкой 1000\n"
        "`мины 500 5` — сапер (500, 5 мин)\n"
        "`краш 500` — краш со ставкой 500\n\n"
        "**🎰 РУЛЕТКА (МУЛЬТИСТАВКИ)**\n"
        "Пишите ставки: `100 5, 200 10-15, 50 red`.\n"
        "Затем напишите **`го`**, чтобы крутить.\n"
        "Отмена — `отмена`.\n\n"
        "**👑 ДЛЯ АДМИНА**\n"
        "`/createpromo КОД СУММА АКТИВАЦИИ`"
    )
    bot.send_message(chat_id, help_text, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "profile")
def profile(call):
    bot.answer_callback_query(call.id)
    bot.edit_message_text(f"👤 Твой профиль\n\n🪙 Баланс: {get_balance(call.from_user.id)} Mon1Coin", 
                          call.message.chat.id, call.message.message_id, reply_markup=main_menu())

@bot.callback_query_handler(func=lambda call: call.data == "back")
def back(call):
    bot.edit_message_text("🎰 ГЛАВНОЕ МЕНЮ\n\nВыбирай игру:", call.message.chat.id, call.message.message_id, reply_markup=main_menu())

# --- MINES ---
MULTIPLIERS = {2: 1.10, 3: 1.15, 5: 1.25, 9: 1.45}

@bot.callback_query_handler(func=lambda call: call.data == "game_mines")
def mines_menu(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "💣 Введите ставку и количество мин в чат.\nПример: `мины 1000 3` (ставка 1000, 3 мины).", parse_mode="Markdown")

def start_mines_game(user_id, chat_id, bet, bombs, msg_id=None):
    if get_balance(user_id) < bet:
        return bot.send_message(chat_id, "❌ Недостаточно Mon1Coin!")
    if bombs not in MULTIPLIERS:
        return bot.send_message(chat_id, "❌ Доступно мин: 2, 3, 5 или 9.")
    
    add_balance(user_id, -bet)
    mines_games[user_id] = {
        "bet": bet, "bombs": bombs, "mines": set(random.sample(range(25), bombs)),
        "opened": set(), "finished": False
    }
    text = mines_text(user_id)
    kb = mines_kb(user_id)
    if msg_id: bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
    else: bot.send_message(chat_id, text, reply_markup=kb)

def mines_text(user_id):
    g = mines_games[user_id]
    opened = len(g["opened"])
    mult = MULTIPLIERS[g["bombs"]] ** opened if opened > 0 else 1.0
    reward = math.floor(g["bet"] * mult)
    return f"💣 MINES\nСтавка: {g['bet']} 🪙\nМин: {g['bombs']}\nОткрыто: {opened}\n📈 Множитель: x{mult:.2f}\n🎁 Забрать: {reward} 🪙"

def mines_kb(user_id):
    g = mines_games[user_id]
    kb = InlineKeyboardMarkup(row_width=5)
    for r in range(5):
        row = []
        for c in range(5):
            i = r*5 + c
            sym = "💎" if i in g["opened"] else ("💣" if g["finished"] and i in g["mines"] else ("▫️" if g["finished"] else "❔"))
            row.append(InlineKeyboardButton(sym, callback_data=f"mcell_{i}"))
        kb.row(*row)
    if not g["finished"] and g["opened"]:
        kb.row(InlineKeyboardButton("⭐ ЗАБРАТЬ", callback_data="mcashout"))
    return kb

@bot.callback_query_handler(func=lambda call: call.data.startswith("mcell_") or call.data == "mcashout")
def mines_play(call):
    user_id = call.from_user.id
    g = mines_games.get(user_id)
    if not g or g["finished"]: return

    if call.data == "mcashout":
        mult = MULTIPLIERS[g["bombs"]] ** len(g["opened"])
        reward = math.floor(g["bet"] * mult)
        add_balance(user_id, reward)
        g["finished"] = True
        bot.edit_message_text(f"🏆 Ты забрал {reward} 🪙!", call.message.chat.id, call.message.message_id, reply_markup=mines_kb(user_id))
        return

    idx = int(call.data.split("_")[1])
    if idx in g["mines"]:
        g["finished"] = True
        bot.edit_message_text(f"💥 МИНА!\nТы потерял {g['bet']} 🪙.", call.message.chat.id, call.message.message_id, reply_markup=mines_kb(user_id))
    else:
        g["opened"].add(idx)
        bot.edit_message_text(mines_text(user_id), call.message.chat.id, call.message.message_id, reply_markup=mines_kb(user_id))

# --- CRASH ---
@bot.callback_query_handler(func=lambda call: call.data == "game_crash")
def crash_menu(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "🚀 Введите ставку в чат.\nПример: `краш 1000`", parse_mode="Markdown")

def start_crash_game(user_id, chat_id, bet, msg_id=None):
    if get_balance(user_id) < bet:
        return bot.send_message(chat_id, "❌ Недостаточно Mon1Coin!")
    
    add_balance(user_id, -bet)
    crash_point = round(random.uniform(1.1, 5.0), 2)
    crash_games[user_id] = {"bet": bet, "crash_point": crash_point, "current": 1.0, "active": True}
    
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("💰 ЗАБРАТЬ", callback_data="crash_cashout"))
    text = f"🚀 CRASH\nСтавка: {bet} 🪙\nКоэффициент: x1.00\n\nУспей забрать!"
    
    if msg_id: msg = bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
    else: msg = bot.send_message(chat_id, text, reply_markup=kb)
        
    threading.Thread(target=crash_loop, args=(user_id, chat_id, msg.message_id)).start()

def crash_loop(user_id, chat_id, msg_id):
    time.sleep(1)
    while True:
        g = crash_games.get(user_id)
        if not g or not g["active"]: break
        g["current"] = round(g["current"] + 0.1, 2)
        
        if g["current"] >= g["crash_point"]:
            g["active"] = False
            bot.edit_message_text(f"💥 КРАШ на x{g['crash_point']:.2f}!\nТы потерял {g['bet']} 🪙.", chat_id, msg_id, reply_markup=None)
            break
        try:
            bot.edit_message_text(f"🚀 CRASH\nСтавка: {g['bet']} 🪙\nКоэффициент: x{g['current']:.2f}\n\nУспей забрать!", 
                                  chat_id, msg_id, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("💰 ЗАБРАТЬ", callback_data="crash_cashout")))
        except Exception: pass
        time.sleep(1)

@bot.callback_query_handler(func=lambda call: call.data == "crash_cashout")
def crash_cashout(call):
    g = crash_games.get(call.from_user.id)
    if not g or not g["active"]: return
    g["active"] = False
    reward = math.floor(g["bet"] * g["current"])
    add_balance(call.from_user.id, reward)
    bot.edit_message_text(f"🏆 Ты забрал на x{g['current']:.2f}!\n+{reward} 🪙", call.message.chat.id, call.message.message_id)

# --- РУЛЕТКА ---
@bot.callback_query_handler(func=lambda call: call.data == "game_roulette")
def roul_menu(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, 
        f"🎰 **РУЛЕТКА**\n\n"
        f"📜 Последние 15: {get_history_roulette()}\n\n"
        "Делайте ставки через запятую:\n"
        "`100 5, 200 10-15, 50 red`\n\n"
        "Затем напишите **`го`**, чтобы крутить.\n"
        "Отмена — `отмена`.", parse_mode="Markdown")

def process_roulette_session(user_id, chat_id):
    session = roulette_sessions[user_id]
    win_num = random.randint(0, 36)
    if win_num == 0: win_color = "green"
    elif 1 <= win_num <= 18: win_color = "red"
    else: win_color = "black"
    
    sym = {"green": "🟢", "red": "🔴", "black": "⚫️"}[win_color]
    cursor.execute("INSERT INTO roulette_history (number, color) VALUES (?, ?)", (win_num, win_color))
    db.commit()
    
    total_win = 0
    results = []

    for bet_data in session["bets"]:
        bet, target = bet_data
        win = False
        mult = 0
        
        if "-" in target:
            try:
                start, end = map(int, target.split("-"))
                if start <= win_num <= end:
                    count = end - start + 1
                    mult = max(1, math.floor(37 / count))
                    win = True
            except: pass
        elif target.isdigit():
            if int(target) == win_num: win, mult = True, 36
        elif target in ["red", "к", "кр", "красное"]:
            if win_color == "red": win, mult = True, 2
        elif target in ["black", "ч", "чёрное", "черное"]:
            if win_color == "black": win, mult = True, 2
        elif target in ["green", "з", "зеро"]:
            if win_color == "green": win, mult = True, 36
            
        if win:
            reward = bet * mult
            total_win += reward
            results.append(f"✅ {bet} на {target} (x{mult}) -> +{reward} 🪙")
        else:
            results.append(f"❌ {bet} на {target} -> проигрыш")

    add_balance(user_id, total_win)
    res_text = "\n".join(results) if results else "Ставок не было."
    
    bot.send_message(chat_id, 
        f"🎰 Барабан остановился: {sym} **{win_num}**\n\n"
        f"{res_text}\n\n"
        f"💰 Итого выигрыш: **+{total_win} 🪙**\n"
        f"🪙 Ваш баланс: {get_balance(user_id)}\n\n"
        f"📜 История: {get_history_roulette()}", parse_mode="Markdown")

# --- АДМИНКА ---
@bot.message_handler(commands=['createpromo'])
def create_promo(message):
    if message.from_user.id != ADMIN_ID: return
    try:
        args = message.text.split()[1:]
        code, amount, uses = args[0].upper(), int(args[1]), int(args[2])
        cursor.execute("INSERT OR REPLACE INTO promos (code, amount, uses_left) VALUES (?, ?, ?)", (code, amount, uses))
        db.commit()
        bot.reply_to(message, f"✅ Промокод `{code}` создан!\nНаграда: {amount} 🪙\nАктиваций: {uses}", parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Формат: `/createpromo КОД СУММА АКТИВАЦИИ`", parse_mode="Markdown")

# --- ОБРАБОТЧИК ТЕКСТА ---
@bot.message_handler(content_types=['text'])
def handle_all_text(message):
    if message.text.startswith('/'): return
    text = message.text.lower().strip()
    parts = text.split()
    user_id = message.from_user.id
    
    # 1. Баланс и профиль
    if text in ["б", "баланс"]:
        bot.reply_to(message, f"🪙 Твой баланс: {get_balance(user_id)} Mon1Coin")
        return
    if text in ["профиль", "п"]:
        bot.reply_to(message, f"👤 ID: {user_id}\n🪙 Баланс: {get_balance(user_id)} Mon1Coin")
        return

    # 2. Логи и История
    if text == "лог":
        bot.reply_to(message, f"📜 **Последние 15 чисел рулетки:**\n{get_history_roulette()}", parse_mode="Markdown")
        return
        
    if text == "история":
        cursor.execute("SELECT sender_id, sender_name, receiver_name, amount, timestamp FROM transfers WHERE sender_id = ? OR receiver_id = ? ORDER BY id DESC LIMIT 10", (user_id, user_id))
        transfers = cursor.fetchall()
        if not transfers:
            bot.reply_to(message, "📭 У вас пока нет истории переводов.")
            return
            
        hist_text = "📜 **История ваших переводов (последние 10):**\n\n"
        for s_id, s_name, r_name, amount, ts in transfers:
            date_str = ts.split()[0] # Просто дата
            if s_id == user_id:
                hist_text += f"📤 {date_str}: Вы перевели **{amount}** 🪙 для @{r_name}\n"
            else:
                hist_text += f"📥 {date_str}: Вам перевел **{amount}** 🪙 от @{s_name}\n"
        bot.reply_to(message, hist_text, parse_mode="Markdown")
        return

    # 3. Быстрый запуск игр
    if parts[0] in ["мины", "mines"] and len(parts) >= 2:
        try: start_mines_game(user_id, message.chat.id, int(parts[1]), int(parts[2]) if len(parts) > 2 else 3)
        except: bot.reply_to(message, "❌ Формат: `мины 1000 3`")
        return
        
    if parts[0] in ["краш", "crash"] and len(parts) >= 2:
        try: start_crash_game(user_id, message.chat.id, int(parts[1]))
        except: bot.reply_to(message, "❌ Формат: `краш 1000`")
        return

    # 4. Переводы
    if parts[0] in ["перевод", "перевести", "пей"] and len(parts) >= 3:
        try:
            amount = int(parts[1])
            target = parts[2].replace("@", "")
            if amount <= 0 or get_balance(user_id) < amount: return bot.reply_to(message, "❌ Недостаточно средств!")
            cursor.execute("SELECT user_id, username FROM players WHERE LOWER(username) = LOWER(?)", (target,))
            receiver = cursor.fetchone()
            if not receiver: return bot.reply_to(message, "❌ Получатель не найден.")
            receiver_id, receiver_name = receiver
            if receiver_id == user_id: return bot.reply_to(message, "❌ Нельзя перевести себе!")
            
            add_balance(user_id, -amount)
            add_balance(receiver_id, amount)
            
            # ЗАПИСЬ В ИСТОРИЮ
            cursor.execute("INSERT INTO transfers (sender_id, sender_name, receiver_id, receiver_name, amount) VALUES (?, ?, ?, ?, ?)",
                           (user_id, message.from_user.username or message.from_user.first_name, receiver_id, receiver_name, amount))
            db.commit()
            
            bot.reply_to(message, f"✅ Переведено {amount} 🪙 пользователю @{receiver_name}!")
            try: bot.send_message(receiver_id, f"💸 Вам перевели {amount} 🪙 от @{message.from_user.username or message.from_user.first_name}!")
            except: pass
            return
        except Exception as e: return bot.reply_to(message, "❌ Неверный формат перевода.")

    # 5. Промокоды
    if len(parts) == 1 and len(text) > 3 and text.isalnum():
        code = text.upper()
        cursor.execute("SELECT amount, uses_left FROM promos WHERE code = ?", (code,))
        promo = cursor.fetchone()
        if promo:
            amount, uses_left = promo
            if uses_left <= 0: return bot.reply_to(message, "❌ Промокод не работает.")
            cursor.execute("SELECT 1 FROM promo_activations WHERE user_id = ? AND code = ?", (user_id, code))
            if cursor.fetchone(): return bot.reply_to(message, "❌ Вы уже активировали этот промокод!")
            add_balance(user_id, amount)
            cursor.execute("UPDATE promos SET uses_left = uses_left - 1 WHERE code = ?", (code,))
            cursor.execute("INSERT INTO promo_activations (user_id, code) VALUES (?, ?)", (user_id, code))
            db.commit()
            return bot.reply_to(message, f"🎉 Промокод активирован! +{amount} 🪙")

    # 6. Рулетка (сессия)
    if text == "го":
        if user_id in roulette_sessions and roulette_sessions[user_id]["bets"]:
            process_roulette_session(user_id, message.chat.id)
            del roulette_sessions[user_id]
        else: bot.reply_to(message, "❌ У вас нет активных ставок. Напишите ставки, затем `го`.")
        return

    if text == "отмена":
        if user_id in roulette_sessions:
            del roulette_sessions[user_id]
            bot.reply_to(message, "✅ Сессия ставок очищена.")
        return

    # Поиск ставок
    potential_bets = re.findall(r'(\d+)\s+([a-zA-Zа-яА-Я0-9\-]+)', text)
    if potential_bets:
        if user_id not in roulette_sessions: roulette_sessions[user_id] = {"bets": []}
        added = []
        for bet_str, target in potential_bets:
            bet = int(bet_str)
            if bet <= 0: continue
            if get_balance(user_id) < bet: 
                bot.reply_to(message, f"❌ Недостаточно средств для ставки {bet}!")
                continue
            add_balance(user_id, -bet)
            roulette_sessions[user_id]["bets"].append((bet, target))
            added.append(f"{bet} на {target}")
        if added:
            bot.reply_to(message, f"✅ Добавлено: {len(added)}\nНапишите **`го`**, чтобы крутить! (Баланс: {get_balance(user_id)})", parse_mode="Markdown")
        return

print("MON1 CASINO запущен!")
bot.infinity_polling(skip_pending=True)
