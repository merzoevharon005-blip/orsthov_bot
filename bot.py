import os
import random
import math
import time
import telebot
import threading
import re
import json
import pathlib
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("Не задан BOT_TOKEN")

# --- СПИСОК АДМИНОВ ---
ADMIN_IDS = [8211650013, 6940877915] 

# --- НАСТРОЙКА ХРАНЕНИЯ ДАННЫХ ---
DATA_DIR = pathlib.Path("/app/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = DATA_DIR / "database.json"

data = {
    "players": {}, "promos": {}, "activations": [], "history": [], "transfers": []
}

def load_data():
    global data
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                print("✅ База данных загружена.")
        except Exception as e:
            print(f"⚠️ Ошибка загрузки: {e}")

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

load_data()
bot = telebot.TeleBot(TOKEN)

mines_games = {}
crash_games = {}

# --- БАЗОВЫЕ ФУНКЦИИ ---
def get_balance(user_id):
    uid = str(user_id)
    if uid not in data["players"]: return 0
    return data["players"][uid].get("balance", 0)

def add_balance(user_id, amount):
    uid = str(user_id)
    if uid not in data["players"]:
        data["players"][uid] = {"username": "Player", "balance": 0, "last_bonus": 0}
    data["players"][uid]["balance"] += amount
    save_data()

def register_user(user):
    uid = str(user.id)
    if uid not in data["players"]:
        data["players"][uid] = {
            "username": user.username or user.first_name, 
            "balance": 1000,
            "last_bonus": 0
        }
        save_data()

def get_history_roulette():
    if not data["history"]: return "История пуста."
    res = []
    for item in data["history"][-15:]:
        num, color = item["number"], item["color"]
        sym = "🟢" if color == "green" else ("🔴" if color == "red" else "⚫️")
        res.append(f"{sym}{num}")
    return " ".join(res)

def main_menu():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("💣 MINES", callback_data="game_mines"),
        InlineKeyboardButton("🚀 CRASH", callback_data="game_crash"),
        InlineKeyboardButton("🎰 РУЛЕТКА", callback_data="game_roulette"),
        InlineKeyboardButton("🎡 КОЛЕСО", callback_data="game_wheel"),
        InlineKeyboardButton("👤 ПРОФИЛЬ", callback_data="profile"),
        InlineKeyboardButton("🎁 БОНУС", callback_data="bonus_menu"),
        InlineKeyboardButton("❓ ПОМОЩЬ", callback_data="help_menu"),
        InlineKeyboardButton("⭐ ДОНАТ", callback_data="donate_menu"),
        InlineKeyboardButton("🏆 ТОП", callback_data="top_menu")
    )
    return kb

# --- СТАРТ ---
@bot.message_handler(commands=["start"])
def start(message):
    register_user(message.from_user)
    bot.send_message(message.chat.id, f"🎰 ДОБРО ПОЖАЛОВАТЬ В MON1 CASINO!\n\n🪙 Твой баланс: {get_balance(message.from_user.id)} Mon1Coin\n\nВыбирай игру:", reply_markup=main_menu())

# --- КОЛЕСО ФОРТУНЫ (КНОПКА) ---
@bot.callback_query_handler(func=lambda call: call.data == "game_wheel")
def wheel_menu(call):
    user_id = call.from_user.id
    if get_balance(user_id) < 100:
        bot.answer_callback_query(call.id, "❌ Для игры нужно минимум 100 Mon1Coin!", show_alert=True)
        return
    
    bot.answer_callback_query(call.id)
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🎡 КРУТИТЬ (100 🪙)", callback_data="spin_wheel"))
    bot.edit_message_text(f"🎡 **КОЛЕСО ФОРТУНЫ**\n\nСтавка: 100 🪙\nТвой баланс: {get_balance(user_id)}\n\nНажми кнопку, чтобы испытать удачу!", 
                          call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode="Markdown")

# --- ФУНКЦИЯ ЗАПУСКА КОЛЕСА ---
def spin_wheel_logic(user_id, chat_id, bet, msg_id=None):
    if get_balance(user_id) < bet:
        if msg_id: return bot.edit_message_text("❌ Недостаточно средств!", chat_id, msg_id)
        else: return bot.send_message(chat_id, "❌ Недостаточно средств!")
    
    add_balance(user_id, -bet)
    
    sectors = [
        (-0.5, 2, "💀 x0.5 (потеряли половину)"),     
        (-1, 3, "💀 x0 (потеряли всё)"),   
        (0, 10, "😐 x0 (возврат)"),        
        (0.5, 15, "🪙 x0.5"),     
        (1, 20, "🪙 x1"),   
        (2, 20, "💰 x2"),   
        (5, 15, "💰 x5"),   
        (10, 10, "💎 x10"), 
        (50, 4, "🔥 x50"),  
        (-2, 1, "☠️ x2 (штраф)"),   
    ]
    
    total_weight = sum(weight for _, weight, _ in sectors)
    rand_val = random.randint(1, total_weight)
    current_weight = 0
    
    result_text = ""
    multiplier = 0
    for mult_val, weight, text in sectors:
        current_weight += weight
        if rand_val <= current_weight:
            result_text = text
            multiplier = mult_val
            break
            
    change = int(bet * multiplier)
    
    if change > 0:
        add_balance(user_id, change)
        msg = f"🎡 Колесо крутится...\n\n🎉 Выпало: **{result_text}**!\nВаш выигрыш: +{change} 🪙\nБаланс: {get_balance(user_id)}"
    elif change < 0:
        add_balance(user_id, change) 
        msg = f"🎡 Колесо крутится...\n\n💀 Выпало: **{result_text}**!\nВы потеряли: {abs(change)} 🪙\nБаланс: {get_balance(user_id)}"
    else:
        add_balance(user_id, bet)
        msg = f"🎡 Колесо крутится...\n\n😐 Выпало: **{result_text}**!\nСтавка возвращена.\nБаланс: {get_balance(user_id)}"

    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("⬅️ В МЕНЮ", callback_data="back"))
    
    if msg_id:
        bot.edit_message_text(msg, chat_id, msg_id, reply_markup=kb, parse_mode="Markdown")
    else:
        bot.send_message(chat_id, msg, reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "spin_wheel")
def spin_wheel(call):
    spin_wheel_logic(call.from_user.id, call.message.chat.id, 100, call.message.message_id)

# --- ЕЖЕДНЕВНЫЙ БОНУС ---
@bot.callback_query_handler(func=lambda call: call.data == "bonus_menu")
@bot.message_handler(func=lambda message: message.text.lower().strip() in ["бонус", "bonus"])
def daily_bonus(event):
    if isinstance(event, telebot.types.CallbackQuery):
        user_id = event.from_user.id
        chat_id = event.message.chat.id
        bot.answer_callback_query(event.id)
    else:
        user_id = event.from_user.id
        chat_id = event.chat.id

    uid = str(user_id)
    if uid not in data["players"]:
        register_user(event.from_user)
        if uid not in data["players"]:
            data["players"][uid] = {"username": "Player", "balance": 1000, "last_bonus": 0}

    current_time = int(time.time())
    last_bonus = data["players"][uid].get("last_bonus", 0)
    cooldown = 24 * 60 * 60

    if current_time - last_bonus < cooldown:
        remaining = cooldown - (current_time - last_bonus)
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        bot.send_message(chat_id, f"⏳ Вы уже получали бонус!\nСледующий через: **{hours} ч. {minutes} мин.**", parse_mode="Markdown")
        return

    bonus_amount = random.randint(1000, 2000)
    add_balance(user_id, bonus_amount)
    
    data["players"][uid]["last_bonus"] = current_time
    save_data()

    bot.send_message(chat_id, f"🎁 **ЕЖЕДНЕВНЫЙ БОНУС!**\n\nВы получили: **+{bonus_amount} Mon1Coin** 🪙\nТекущий баланс: {get_balance(user_id)}", parse_mode="Markdown")

# --- ВАЙП БАЛАНСОВ ---
@bot.message_handler(commands=['wipe'])
def admin_wipe(message):
    if message.from_user.id not in ADMIN_IDS:
        return bot.reply_to(message, "❌ У вас нет прав.")
    
    count = 0
    for uid, pdata in data["players"].items():
        if pdata.get("balance", 0) > 1000:
            pdata["balance"] = 1000
            count += 1
            
    save_data()
    bot.reply_to(message, f"♻️ **Экономика очищена!**\nБалансы {count} игроков сброшены до 1000 Mon1Coin.", parse_mode="Markdown")

# --- ПОМОЩЬ ---
@bot.callback_query_handler(func=lambda call: call.data == "help_menu")
def help_callback(call):
    bot.answer_callback_query(call.id)
    send_help_text(call.message.chat.id)

@bot.message_handler(func=lambda message: message.text.lower().strip() in ["помощь", "help"])
def help_message(message):
    send_help_text(message.chat.id)

def send_help_text(chat_id):
    help_text = (
        "📖 **ПОЛНАЯ ИНСТРУКЦИЯ MON1 CASINO**\n\n"
        "🪙 **Валюта:** Mon1Coin\n\n"
        "**👤 БАЗОВЫЕ КОМАНДЫ**\n"
        "`б` или `баланс` — баланс\n"
        "`профиль` — ваш ID\n\n"
        "**🎁 БОНУС**\n"
        "`бонус` — получить от 1000 до 2000 🪙 раз в 24 часа\n\n"
        "**📜 ИСТОРИЯ**\n"
        "`лог` — последние 15 чисел рулетки\n"
        "`история` — история ваших переводов\n\n"
        "**💸 ПЕРЕВОДЫ**\n"
        "`перевод 100 @username`\n\n"
        "**🎁 ПРОМОКОДЫ**\n"
        "Просто напишите код.\n\n"
        "**🎮 БЫСТРЫЙ ЗАПУСК**\n"
        "`мины 1000` — сапер\n"
        "`краш 500` — краш\n"
        "`колесо 100` — колесо фортуны\n\n"
        "**🎰 РУЛЕТКА**\n"
        "`1000 на 1 на 5 на 7`\n"
        "`500 на red`\n"
        "`300 на 11-14`\n\n"
        "**👑 АДМИН**\n"
        "`/createpromo КОД СУММА АКТИВАЦИИ`\n"
        "`/give ID СУММА`\n"
        "`/reset ID`\n"
        "`/wipe` — сбросить балансы всех до 1000"
    )
    try:
        bot.send_message(chat_id, help_text, parse_mode="Markdown")
    except Exception as e:
        print(f"Ошибка отправки помощи: {e}")

# --- ТОП ---
@bot.callback_query_handler(func=lambda call: call.data == "top_menu")
def top_callback(call):
    bot.answer_callback_query(call.id)
    send_top_text(call.message.chat.id, call.message.message_id)

@bot.message_handler(func=lambda message: message.text.lower().strip() in ["топ", "top"])
def top_message(message):
    send_top_text(message.chat.id, None)

def send_top_text(chat_id, msg_id=None):
    sorted_players = sorted(data["players"].items(), key=lambda x: x[1].get("balance", 0), reverse=True)
    text = "🏆 **ТОП-10 БОГАЧЕЙ**\n\n"
    for i, (uid, pdata) in enumerate(sorted_players[:10], 1):
        name = pdata.get("username", "Unknown")
        bal = pdata.get("balance", 0)
        text += f"{i}. @{name} — {bal} 🪙\n"
        
    if msg_id:
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=main_menu(), parse_mode="Markdown")
    else:
        bot.send_message(chat_id, text, parse_mode="Markdown")

# --- CRASH ---
@bot.callback_query_handler(func=lambda call: call.data == "game_crash")
def crash_menu(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "🚀 Введите ставку в чат.\nПример: `краш 1000`", parse_mode="Markdown")

def start_crash_game(user_id, chat_id, bet, msg_id=None):
    if get_balance(user_id) < bet: return bot.send_message(chat_id, "❌ Недостаточно Mon1Coin!")
    add_balance(user_id, -bet)
    crash_point = round(random.uniform(1.1, 100.0), 2)
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
        if g["current"] < 10: g["current"] = round(g["current"] + 0.1, 2)
        elif g["current"] < 50: g["current"] = round(g["current"] + 0.5, 2)
        else: g["current"] = round(g["current"] + 1.0, 2)
        
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

# --- АДМИНСКИЕ КОМАНДЫ ---
@bot.message_handler(commands=['give'])
def admin_give(message):
    if message.from_user.id not in ADMIN_IDS: return bot.reply_to(message, "❌ У вас нет прав.")
    try:
        args = message.text.split()[1:]
        target_id = str(int(args[0])); amount = int(args[1])
        if target_id not in data["players"]: data["players"][target_id] = {"username": "Player", "balance": 0, "last_bonus": 0}
        data["players"][target_id]["balance"] += amount; save_data()
        bot.reply_to(message, f"✅ Выдано {amount} 🪙 игроку {target_id}.")
    except: bot.reply_to(message, "❌ Формат: `/give ID СУММА`", parse_mode="Markdown")

@bot.message_handler(commands=['reset'])
def admin_reset(message):
    if message.from_user.id not in ADMIN_IDS: return bot.reply_to(message, "❌ У вас нет прав.")
    try:
        target_id = str(int(message.text.split()[1]))
        if target_id in data["players"]:
            data["players"][target_id]["balance"] = 0; save_data()
            bot.reply_to(message, f"♻️ Баланс игрока {target_id} аннулирован.")
        else: bot.reply_to(message, "❌ Игрок не найден.")
    except: bot.reply_to(message, "❌ Формат: `/reset ID`", parse_mode="Markdown")

@bot.message_handler(commands=['createpromo'])
def create_promo(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        args = message.text.split()[1:]
        code, amount, uses = args[0].upper(), int(args[1]), int(args[2])
        data["promos"][code] = {"amount": amount, "uses_left": uses}; save_data()
        bot.reply_to(message, f"✅ Промокод `{code}` создан!\nНаграда: {amount} 🪙\nАктиваций: {uses}", parse_mode="Markdown")
    except: bot.reply_to(message, "❌ Формат: `/createpromo КОД СУММА АКТИВАЦИИ`", parse_mode="Markdown")

# --- ДОНАТ ЗВЕЗДАМИ ---
@bot.callback_query_handler(func=lambda call: call.data == "donate_menu")
def donate_menu(call):
    bot.answer_callback_query(call.id)
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("⭐ 50 Звезд (5000 Mon1Coin)", callback_data="pay_50"),
        InlineKeyboardButton("⭐ 100 Звезд (12000 Mon1Coin)", callback_data="pay_100"),
        InlineKeyboardButton("⭐ 250 Звезд (35000 Mon1Coin)", callback_data="pay_250")
    )
    bot.edit_message_text("💖 **Поддержите проект!**\n\nВыберите пакет доната.", call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_"))
def send_donate_invoice(call):
    stars = int(call.data.split("_")[1]); coins = {50: 5000, 100: 12000, 250: 35000}[stars]
    bot.answer_callback_query(call.id)
    bot.send_invoice(chat_id=call.message.chat.id, title="Поддержка Monix Casino", description=f"Вы получите {coins} Mon1Coin 🪙", invoice_payload=f"donate_{stars}_{coins}", provider_token="", currency="XTR", prices=[LabeledPrice(label="Поддержка", amount=stars)])

@bot.pre_checkout_query_handler(func=lambda query: True)
def process_pre_checkout(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def process_successful_payment(message):
    payload = message.successful_payment.invoice_payload
    if payload.startswith("donate_"):
        coins = int(payload.split("_")[2]); add_balance(message.from_user.id, coins)
        bot.send_message(message.chat.id, f"🎉 **Спасибо за донат!**\n+{coins} Mon1Coin 🪙", parse_mode="Markdown")

# --- ОСТАЛЬНЫЕ ИГРЫ ---
@bot.callback_query_handler(func=lambda call: call.data == "profile")
def profile(call):
    bot.answer_callback_query(call.id)
    bot.edit_message_text(f"👤 Твой профиль\n\n🪙 Баланс: {get_balance(call.from_user.id)} Mon1Coin", call.message.chat.id, call.message.message_id, reply_markup=main_menu())

@bot.callback_query_handler(func=lambda call: call.data == "back")
def back(call):
    bot.edit_message_text("🎰 ГЛАВНОЕ МЕНЮ", call.message.chat.id, call.message.message_id, reply_markup=main_menu())

# --- MINES ---
MULTIPLIERS = {2: 1.10, 3: 1.15, 5: 1.25, 9: 1.45}
@bot.callback_query_handler(func=lambda call: call.data == "game_mines")
def mines_menu(call):
    bot.answer_callback_query(call.id); bot.send_message(call.message.chat.id, "💣 Введите ставку и количество мин.\nПример: `мины 1000 3`", parse_mode="Markdown")

def start_mines_game(user_id, chat_id, bet, bombs, msg_id=None):
    if get_balance(user_id) < bet: return bot.send_message(chat_id, "❌ Недостаточно Mon1Coin!")
    if bombs not in MULTIPLIERS: return bot.send_message(chat_id, "❌ Доступно мин: 2, 3, 5 или 9.")
    add_balance(user_id, -bet); mines_games[user_id] = {"bet": bet, "bombs": bombs, "mines": set(random.sample(range(25), bombs)), "opened": set(), "finished": False}
    text = mines_text(user_id); kb = mines_kb(user_id)
    if msg_id: bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)
    else: bot.send_message(chat_id, text, reply_markup=kb)

def mines_text(user_id):
    g = mines_games[user_id]; opened = len(g["opened"]); mult = MULTIPLIERS[g["bombs"]] ** opened if opened > 0 else 1.0; reward = math.floor(g["bet"] * mult)
    return f"💣 MINES\nСтавка: {g['bet']} 🪙\nМин: {g['bombs']}\nОткрыто: {opened}\n📈 Множитель: x{mult:.2f}\n🎁 Забрать: {reward} 🪙"

def mines_kb(user_id):
    g = mines_games[user_id]; kb = InlineKeyboardMarkup(row_width=5)
    for r in range(5):
        row = []
        for c in range(5):
            i = r*5 + c; sym = "💎" if i in g["opened"] else ("💣" if g["finished"] and i in g["mines"] else ("▫️" if g["finished"] else "❔"))
            row.append(InlineKeyboardButton(sym, callback_data=f"mcell_{i}"))
        kb.row(*row)
    if not g["finished"] and g["opened"]: kb.row(InlineKeyboardButton("⭐ ЗАБРАТЬ", callback_data="mcashout"))
    return kb

@bot.callback_query_handler(func=lambda call: call.data.startswith("mcell_") or call.data == "mcashout")
def mines_play(call):
    user_id = call.from_user.id; g = mines_games.get(user_id)
    if not g or g["finished"]: return
    if call.data == "mcashout":
        reward = math.floor(g["bet"] * (MULTIPLIERS[g["bombs"]] ** len(g["opened"]))); add_balance(user_id, reward); g["finished"] = True
        bot.edit_message_text(f"🏆 Ты забрал {reward} 🪙!", call.message.chat.id, call.message.message_id, reply_markup=mines_kb(user_id)); return
    idx = int(call.data.split("_")[1])
    if idx in g["mines"]: g["finished"] = True; bot.edit_message_text(f"💥 МИНА!\nТы потерял {g['bet']} 🪙.", call.message.chat.id, call.message.message_id, reply_markup=mines_kb(user_id))
    else: g["opened"].add(idx); bot.edit_message_text(mines_text(user_id), call.message.chat.id, call.message.message_id, reply_markup=mines_kb(user_id))

# --- РУЛЕТКА ---
@bot.callback_query_handler(func=lambda call: call.data == "game_roulette")
def roul_menu(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, f"🎰 **РУЛЕТКА**\n\n📜 Последние 15: {get_history_roulette()}\n\nФормат: `1000 на 1 на 5 на 7`\nЦвет: `500 на red`\nДиапазон: `300 на 11-14`\nЧет/Нечет: `100 на чет` / `100 на нечет`", parse_mode="Markdown")

# --- ОБРАБОТЧИК ТЕКСТА ---
@bot.message_handler(content_types=['text'])
def handle_all_text(message):
    if message.text.startswith('/'): return
    text = message.text.lower().strip(); parts = text.split(); user_id = message.from_user.id
    
    if text in ["б", "баланс", "профиль", "п", "лог", "топ", "top", "помощь", "help", "бонус", "bonus"]: return

    if parts[0] in ["колесо", "wheel"] and len(parts) >= 2:
        try:
            bet = int(parts[1])
            spin_wheel_logic(user_id, message.chat.id, bet)
        except ValueError:
            bot.reply_to(message, "❌ Формат: `колесо 100` (где 100 - сумма ставки)")
        return

    if parts[0] in ["мины", "mines"] and len(parts) >= 2:
        try: start_mines_game(user_id, message.chat.id, int(parts[1]), int(parts[2]) if len(parts) > 2 else 3)
        except: bot.reply_to(message, "❌ Формат: `мины 1000 3`")
        return
    if parts[0] in ["краш", "crash"] and len(parts) >= 2:
        try: start_crash_game(user_id, message.chat.id, int(parts[1]))
        except: bot.reply_to(message, "❌ Формат: `краш 1000`")
        return
    if parts[0] in ["перевод", "перевести", "пей"] and len(parts) >= 3:
        try:
            amount = int(parts[1]); target = parts[2].replace("@", "")
            if amount <= 0 or get_balance(user_id) < amount: return bot.reply_to(message, "❌ Недостаточно средств!")
            target_id = None
            for uid, pdata in data["players"].items():
                if pdata.get("username", "").lower() == target.lower(): target_id = uid; break
            if not target_id: return bot.reply_to(message, "❌ Получатель не найден.")
            if target_id == str(user_id): return bot.reply_to(message, "❌ Нельзя перевести себе!")
            add_balance(user_id, -amount); add_balance(int(target_id), amount)
            data["transfers"].append({"sender_id": user_id, "sender_name": message.from_user.username or message.from_user.first_name, "receiver_id": int(target_id), "receiver_name": target, "amount": amount, "date": time.strftime("%Y-%m-%d")})
            save_data()
            bot.reply_to(message, f"✅ Переведено {amount} 🪙 пользователю @{target}!")
            try: bot.send_message(int(target_id), f"💸 Вам перевели {amount} 🪙!")
            except: pass
            return
        except: return bot.reply_to(message, "❌ Неверный формат перевода.")

    if len(parts) == 1 and len(text) > 3 and text.isalnum():
        code = text.upper()
        if code in data["promos"]:
            promo = data["promos"][code]
            if promo["uses_left"] <= 0: return bot.reply_to(message, "❌ Промокод не работает.")
            if [str(user_id), code] in data["activations"]: return bot.reply_to(message, "❌ Вы уже активировали этот промокод!")
            add_balance(user_id, promo["amount"]); promo["uses_left"] -= 1; data["activations"].append([str(user_id), code]); save_data()
            return bot.reply_to(message, f"🎉 Промокод активирован! +{promo['amount']} 🪙")

    if " на " in text and len(parts) >= 3:
        try:
            bet = int(parts[0])
            if bet <= 0: return
            targets = [parts[i] for i in range(2, len(parts)) if parts[i] != "на"]
            if not targets: return bot.reply_to(message, "❌ Вы не указали на что ставить.")
            total_cost = bet * len(targets)
            if get_balance(user_id) < total_cost: return bot.reply_to(message, f"❌ Недостаточно средств! Нужно {total_cost} 🪙")
            add_balance(user_id, -total_cost)
            
            win_num = random.randint(0, 36); win_color = "green" if win_num == 0 else ("red" if 1 <= win_num <= 18 else "black")
            sym = {"green": "🟢", "red": "🔴", "black": "⚫️"}[win_color]
            data["history"].append({"number": win_num, "color": win_color})
            if len(data["history"]) > 100: data["history"] = data["history"][-100:]
            save_data()
            
            total_win = 0; results = []
            for target in targets:
                win = False; mult = 0
                if "-" in target:
                    try:
                        start, end = map(int, target.split("-"))
                        if start <= win_num <= end: count = end - start + 1; mult = max(1, math.floor(37 / count)); win = True
                    except: pass
                elif target.isdigit():
                    if int(target) == win_num: win, mult = True, 36
                elif target in ["red", "к", "кр", "красное"]:
                    if win_color == "red": win, mult = True, 2
                elif target in ["black", "ч", "чёрное", "черное"]:
                    if win_color == "black": win, mult = True, 2
                elif target in ["green", "з", "зеро"]:
                    if win_color == "green": win, mult = True, 36
                elif target in ["even", "чет"]:
                    if win_num != 0 and win_num % 2 == 0: win, mult = True, 2
                elif target in ["odd", "нечет"]:
                    if win_num % 2 != 0: win, mult = True, 2
                if win: reward = bet * mult; total_win += reward; results.append(f"✅ {bet} на {target} (x{mult}) -> +{reward} 🪙")
                else: results.append(f"❌ {bet} на {target} -> проигрыш")
            add_balance(user_id, total_win)
            bot.reply_to(message, f"🎰 Выпало: {sym} **{win_num}**\n\n" + "\n".join(results) + f"\n\n💰
