import os
import random
import math
import time
import telebot
import threading
import json
import pathlib
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("Не задан BOT_TOKEN")

ADMIN_IDS = [8211650013, 6940877915] 
DATA_DIR = pathlib.Path("/app/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = DATA_DIR / "database.json"

data = {
    "players": {}, "promos": {}, "activations": [], "history": [], 
    "clans": {}, "next_id": 1, "active_games": {}
}

def load_data():
    global data
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                for key in loaded:
                    data[key] = loaded[key]
        except Exception as e:
            print(f"⚠️ Ошибка загрузки: {e}")

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

load_data()

# --- МИГРАЦИЯ ---
def migrate_data():
    global data
    changed = False
    current_max = max([p.get("short_id", 0) for p in data["players"].values() if isinstance(p.get("short_id"), int)], default=0)
    if data.get("next_id", 1) <= current_max:
        data["next_id"] = current_max + 1
        
    for uid, pdata in data["players"].items():
        if "short_id" not in pdata or pdata["short_id"] == 0:
            pdata["short_id"] = data["next_id"]
            data["next_id"] += 1
            changed = True
        if "bank" not in pdata:
            pdata["bank"] = 0; pdata["deposit"] = 0; pdata["deposit_start"] = 0; changed = True
        if "biz_territory" not in pdata:
            pdata["biz_territory"] = 0
            pdata["biz_building"] = 1
            pdata["biz_tax"] = 0
            pdata["biz_last_collect"] = int(time.time())
            changed = True
            
    if changed: save_data()

migrate_data()
bot = telebot.TeleBot(TOKEN)
MULT = {2: 1.10, 3: 1.15, 5: 1.25, 9: 1.45}

BIZ_TERRITORY_COST = {0: 10000, 1: 50000, 2: 250000, 3: 1000000, 4: 5000000, 5: 25000000}
BIZ_BUILDING_COST = {1: 20000, 2: 100000, 3: 500000, 4: 2000000, 5: 10000000}

# --- БАЗА ---
def get_balance(user_id):
    return data["players"].get(str(user_id), {}).get("balance", 0)

def get_nick(user_id):
    return data["players"].get(str(user_id), {}).get("username", "Player")

def get_user_short_id(user_id):
    return data["players"].get(str(user_id), {}).get("short_id", "0")

def get_user_by_short_id(short_id):
    for uid, pdata in data["players"].items():
        if str(pdata.get("short_id")) == str(short_id): return uid
    return None

def get_user_by_username(username):
    username = username.replace("@", "").lower()
    for uid, pdata in data["players"].items():
        if pdata.get("username", "").lower() == username: return uid
    return None

def add_balance(user_id, amount):
    uid = str(user_id)
    if uid not in data["players"]: register_user_by_id(uid)
    data["players"][uid]["balance"] += amount
    save_data()

def register_user(user):
    uid = str(user.id)
    if uid not in data["players"]:
        sid = data["next_id"]; data["next_id"] += 1
        data["players"][uid] = {
            "username": user.username or user.first_name, "balance": 1000, 
            "last_bonus": 0, "short_id": sid, "clan_id": None, "role": "none",
            "bank": 0, "deposit": 0, "deposit_start": 0, 
            "biz_territory": 0, "biz_building": 1, "biz_tax": 0, "biz_last_collect": int(time.time())
        }
        save_data()

def register_user_by_id(uid):
    if uid not in data["players"]:
        sid = data["next_id"]; data["next_id"] += 1
        data["players"][uid] = {
            "username": "Player", "balance": 1000, "last_bonus": 0, 
            "short_id": sid, "clan_id": None, "role": "none",
            "bank": 0, "deposit": 0, "deposit_start": 0,
            "biz_territory": 0, "biz_building": 1, "biz_tax": 0, "biz_last_collect": int(time.time())
        }
        save_data()

# --- СТАРТ ---
@bot.message_handler(commands=["start"])
def start(message):
    register_user(message.from_user)
    bot.send_message(message.chat.id, 
        f"🎰 **MON1 CASINO RPG**\n\n🪙 Баланс: {get_balance(message.from_user.id)}\n\n"
        "**Игры:**\n`мины 1000 3`\n`краш 1000`\n`1000 на 5`\n\n"
        "**Бизнес:**\n`мой бизнес`\n\n"
        "**Инфо:** `помощь` | `чаты`", parse_mode="Markdown")

# --- ЧАТЫ И КАНАЛ ---
@bot.message_handler(func=lambda m: m.text.lower().strip() == "чаты")
def chats_cmd(message):
    text = (
        "💬 **Наши чаты и канал**\n\n"
        "📢 **Канал:** https://t.me/mon1bots\n"
        "💬 **Чат:** https://t.me/mon1not\n\n"
        "Подписывайтесь, чтобы не пропустить обновления и общаться с другими игроками!"
    )
    bot.reply_to(message, text, parse_mode="Markdown")

# --- БИЗНЕС (МЕНЮ) ---
@bot.message_handler(func=lambda m: m.text.lower().strip() == "мой бизнес")
def my_business(message):
    uid = str(message.from_user.id)
    p = data["players"].get(uid, {})
    t_lvl = p.get("biz_territory", 0)
    if t_lvl == 0:
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🏗 Построить бизнес", callback_data="biz_build"))
        return bot.reply_to(message, f"🏢 У вас нет бизнеса.\nНажмите кнопку ниже, чтобы купить первый уровень за {BIZ_TERRITORY_COST[0]} 🪙.", reply_markup=kb)
    show_biz_menu(message.chat.id, uid, None)

def show_biz_menu(chat_id, uid, msg_id):
    p = data["players"].get(uid, {})
    t_lvl = p.get("biz_territory", 0); b_lvl = p.get("biz_building", 1); tax = p.get("biz_tax", 0)
    last_collect = p.get("biz_last_collect", int(time.time())); now = int(time.time())
    
    income_per_hour = (t_lvl * 1000) * (1 + (b_lvl - 1) * 0.1)
    seconds_passed = min(now - last_collect, 86400) 
    earned = int((seconds_passed / 3600) * income_per_hour)
    
    text = (
        f"🏢 **Информация о вашем бизнесе**\n\n"
        f"🧱 Территория: {t_lvl} м²\n⬆️ Для след. уровня: {BIZ_TERRITORY_COST.get(t_lvl, 'MAX')} 🪙\n\n"
        f"🏢 Здание: ур. {b_lvl}\n⬆️ Для след. уровня: {BIZ_BUILDING_COST.get(b_lvl, 'MAX')} 🪙\n\n"
        f"📈 Доход в час: {int(income_per_hour)} 🪙\n"
        f"💸 Налоги: {tax} 🪙\n"
        f"💰 Накоплено: **{earned} 🪙**"
    )
    kb = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("💰 Собрать доход", callback_data="biz_collect"),
        InlineKeyboardButton("🧱 Увеличить Терр.", callback_data="biz_terr"),
        InlineKeyboardButton("🏢 Увеличить Здание", callback_data="biz_build_up"),
        InlineKeyboardButton("💸 Оплатить налоги", callback_data="biz_tax")
    )
    if msg_id: bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb, parse_mode="Markdown")
    else: bot.send_message(chat_id, text, reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("biz_"))
def biz_callback(call):
    uid = str(call.from_user.id); action = call.data.split("_")[1]
    if action == "build":
        if get_balance(uid) < BIZ_TERRITORY_COST[0]: return bot.answer_callback_query(call.id, "❌ Недостаточно средств!", show_alert=True)
        add_balance(uid, -BIZ_TERRITORY_COST[0]); data["players"][uid]["biz_territory"] = 1; save_data()
        bot.answer_callback_query(call.id, "✅ Бизнес построен!"); show_biz_menu(call.message.chat.id, uid, call.message.message_id)
    elif action == "collect":
        p = data["players"].get(uid, {}); t_lvl = p.get("biz_territory", 0); b_lvl = p.get("biz_building", 1); tax = p.get("biz_tax", 0)
        if tax > 0: return bot.answer_callback_query(call.id, f"❌ Сначала оплатите налоги ({tax} 🪙)!", show_alert=True)
        earned = int((min(int(time.time()) - p.get("biz_last_collect", int(time.time())), 86400) / 3600) * (t_lvl * 1000) * (1 + (b_lvl - 1) * 0.1))
        if earned <= 0: return bot.answer_callback_query(call.id, "⏳ Вы пока ничего не заработали.", show_alert=True)
        tax_owed = int((t_lvl * 1000) * (1 + (b_lvl - 1) * 0.1) * 5)
        data["players"][uid]["biz_tax"] = tax_owed; add_balance(uid, earned); data["players"][uid]["biz_last_collect"] = int(time.time()); save_data()
        bot.answer_callback_query(call.id, f"💰 Собрано {earned} 🪙! Налог: {tax_owed} 🪙", show_alert=True); show_biz_menu(call.message.chat.id, uid, call.message.message_id)
    elif action == "terr":
        p = data["players"].get(uid, {}); t_lvl = p.get("biz_territory", 0)
        if t_lvl >= 5: return bot.answer_callback_query(call.id, "🧱 Максимальный уровень!", show_alert=True)
        cost = BIZ_TERRITORY_COST.get(t_lvl, 0)
        if get_balance(uid) < cost: return bot.answer_callback_query(call.id, f"❌ Нужно {cost} 🪙!", show_alert=True)
        add_balance(uid, -cost); data["players"][uid]["biz_territory"] += 1; save_data()
        bot.answer_callback_query(call.id, "✅ Территория увеличена!"); show_biz_menu(call.message.chat.id, uid, call.message.message_id)
    elif action == "build_up":
        p = data["players"].get(uid, {}); b_lvl = p.get("biz_building", 1)
        if b_lvl >= 5: return bot.answer_callback_query(call.id, "🏢 Максимальный уровень!", show_alert=True)
        cost = BIZ_BUILDING_COST.get(b_lvl, 0)
        if get_balance(uid) < cost: return bot.answer_callback_query(call.id, f"❌ Нужно {cost} 🪙!", show_alert=True)
        add_balance(uid, -cost); data["players"][uid]["biz_building"] += 1; save_data()
        bot.answer_callback_query(call.id, "✅ Здание улучшено!"); show_biz_menu(call.message.chat.id, uid, call.message.message_id)
    elif action == "tax":
        p = data["players"].get(uid, {}); tax = p.get("biz_tax", 0)
        if tax <= 0: return bot.answer_callback_query(call.id, "✅ У вас нет долгов.", show_alert=True)
        if get_balance(uid) < tax: return bot.answer_callback_query(call.id, f"❌ Нужно {tax} 🪙!", show_alert=True)
        add_balance(uid, -tax); data["players"][uid]["biz_tax"] = 0; save_data()
        bot.answer_callback_query(call.id, "✅ Налоги оплачены!"); show_biz_menu(call.message.chat.id, uid, call.message.message_id)

# --- БАНК И ДЕПОЗИТ ---
@bot.message_handler(func=lambda m: m.text.lower().strip() == "банк")
def bank_info(message):
    uid = str(message.from_user.id); p = data["players"].get(uid, {})
    bank_sum = p.get("bank", 0); dep_sum = p.get("deposit", 0); dep_start = p.get("deposit_start", 0); now = int(time.time()); cooldown = 3 * 86400
    dep_status = "Нет"
    if dep_sum > 0:
        passed = now - dep_start
        if passed >= cooldown: dep_status = f"✅ {dep_sum} 🪙 (Можно снять!)"
        else: dep_status = f"⏳ {dep_sum} 🪙 (Снять через {(cooldown - passed)//3600} ч.)"
    msg = f"🏦 **БАНК**\n\n👤 Владелец: {get_nick(uid)}\n💰 Обычный счет: {bank_sum} 🪙\n\n💎 **Депозит:**\n{dep_status}\n📈 Доходность: 10% (раз в 3 дня)\n\nКоманды:\n`банк положить СУММА` / `банк снять СУММА`\n`депозит положить СУММА` / `депозит снять`"
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text.lower().startswith("банк положить"))
def bank_deposit(message):
    uid = str(message.from_user.id)
    try:
        amount = int(message.text.split()[2])
        if amount <= 0 or get_balance(uid) < amount: return bot.reply_to(message, "❌ Недостаточно средств.")
        add_balance(uid, -amount); data["players"][uid]["bank"] += amount; save_data()
        bot.reply_to(message, f"✅ Вложено в банк: {amount} 🪙")
    except: bot.reply_to(message, "❌ `банк положить 1000`")

@bot.message_handler(func=lambda m: m.text.lower().startswith("банк снять"))
def bank_withdraw(message):
    uid = str(message.from_user.id)
    try:
        amount = int(message.text.split()[2])
        if amount <= 0 or data["players"][uid].get("bank", 0) < amount: return bot.reply_to(message, "❌ Недостаточно средств в банке.")
        data["players"][uid]["bank"] -= amount; add_balance(uid, amount); save_data()
        bot.reply_to(message, f"✅ Снято из банка: {amount} 🪙")
    except: bot.reply_to(message, "❌ `банк снять 1000`")

@bot.message_handler(func=lambda m: m.text.lower().startswith("депозит положить"))
def make_deposit(message):
    uid = str(message.from_user.id); p = data["players"].get(uid, {})
    try:
        amount = int(message.text.split()[2])
        if amount <= 0 or get_balance(uid) < amount: return bot.reply_to(message, "❌ Недостаточно средств.")
        if p.get("deposit", 0) > 0 and (int(time.time()) - p.get("deposit_start", 0) < 3 * 86400): return bot.reply_to(message, "❌ У вас уже есть активный депозит. Дождитесь окончания 3 дней.")
        add_balance(uid, -amount); data["players"][uid]["deposit"] = amount; data["players"][uid]["deposit_start"] = int(time.time()); save_data()
        bot.reply_to(message, f"✅ Депозит открыт на {amount} 🪙.\nПроценты (10%) начислятся через 3 дня.")
    except: bot.reply_to(message, "❌ `депозит положить 1000`")

@bot.message_handler(func=lambda m: m.text.lower().strip() == "депозит снять")
def withdraw_deposit(message):
    uid = str(message.from_user.id); p = data["players"].get(uid, {})
    dep_sum = p.get("deposit", 0); dep_start = p.get("deposit_start", 0)
    if dep_sum <= 0: return bot.reply_to(message, "❌ У вас нет активного депозита.")
    if int(time.time()) - dep_start < 3 * 86400:
        rem = 3 * 86400 - (int(time.time()) - dep_start)
        return bot.reply_to(message, f"⏳ Депозит закрыт. Снять можно через {rem//3600} ч. {(rem%3600)//60} мин.")
    interest = int(dep_sum * 0.10); total = dep_sum + interest
    add_balance(uid, total); data["players"][uid]["deposit"] = 0; data["players"][uid]["deposit_start"] = 0; save_data()
    bot.reply_to(message, f"🏦 **Депозит закрыт!**\nВклад: {dep_sum} 🪙\nПроценты: +{interest} 🪙\nИтого: **{total} 🪙**", parse_mode="Markdown")

# --- ПЕРЕВОДЫ ---
@bot.message_handler(func=lambda m: m.text.lower().startswith("перевод"))
def transfer_cmd(message):
    uid = str(message.from_user.id)
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user; target_uid = str(target_user.id)
        try: amount = int(message.text.split()[1])
        except: return bot.reply_to(message, "❌ `перевод 1000` (в ответ на сообщение)")
        if amount <= 0 or get_balance(uid) < amount: return bot.reply_to(message, "❌ Недостаточно средств.")
        if target_uid == uid: return bot.reply_to(message, "❌ Нельзя перевести себе.")
        if target_uid not in data["players"]: register_user(target_user)
        add_balance(uid, -amount); add_balance(target_uid, amount)
        return bot.reply_to(message, f"✅ Переведено {amount} 🪙 игроку {get_nick(target_uid)}.")
    else:
        try:
            parts = message.text.split(); amount = int(parts[1]); target_name = parts[2]
            if amount <= 0 or get_balance(uid) < amount: return bot.reply_to(message, "❌ Недостаточно средств.")
            target_uid = get_user_by_username(target_name)
            if not target_uid or target_uid == uid: return bot.reply_to(message, "❌ Игрок не найден.")
            add_balance(uid, -amount); add_balance(target_uid, amount)
            bot.reply_to(message, f"✅ Переведено {amount} 🪙 игроку {get_nick(target_uid)}.")
        except: bot.reply_to(message, "❌ `перевод 1000 ник` или ответьте на сообщение")

# --- ИГРЫ (КРАШ ЗАМЕДЛЕН) ---
@bot.message_handler(func=lambda m: m.text.lower().startswith("мины"))
def start_mines(message):
    uid = str(message.from_user.id)
    try:
        parts = message.text.split(); bet = int(parts[1]); bmb = int(parts[2]) if len(parts) > 2 else 3
        if bet <= 0 or get_balance(uid) < bet: return bot.reply_to(message, "❌ Недостаточно средств.")
        if bmb not in MULT: return bot.reply_to(message, "❌ Мин: 2, 3, 5, 9.")
        add_balance(uid, -bet); gid = str(random.randint(10000, 99999))
        data["active_games"][gid] = {"type": "mines", "user": uid, "bet": bet, "mines": random.sample(range(25), bmb), "opened": [], "bombs": bmb}
        save_data()
        bot.reply_to(message, f"💣 **МИНЫ** (Игра #{gid})\nСтавка: {bet} 🪙\nМин: {bmb}", reply_markup=mines_kb(gid), parse_mode="Markdown")
    except: bot.reply_to(message, "❌ `мины 1000 3`")

def mines_kb(gid):
    g = data["active_games"].get(gid)
    if not g: return None
    kb = InlineKeyboardMarkup(row_width=5)
    for r in range(5):
        kb.row(*[InlineKeyboardButton("💎" if (r*5+c) in g["opened"] else "❔", callback_data=f"m_{gid}_{r*5+c}") for c in range(5)])
    kb.row(InlineKeyboardButton("⭐ ЗАБРАТЬ", callback_data=f"mcash_{gid}"))
    return kb

@bot.callback_query_handler(func=lambda call: call.data.startswith("m_"))
def mines_play(call):
    _, gid, cell = call.data.split("_"); cell = int(cell); uid = str(call.from_user.id); g = data["active_games"].get(gid)
    if not g or g["user"] != uid or cell in g["opened"]: return bot.answer_callback_query(call.id, "❌ Ошибка.")
    if cell in g["mines"]:
        del data["active_games"][gid]; save_data()
        kb = InlineKeyboardMarkup(row_width=5)
        for r in range(5):
            kb.row(*[InlineKeyboardButton("💣" if (r*5+c) in g["mines"] else "💎", callback_data="ignore") for c in range(5)])
        bot.edit_message_text(f"💥 **МИНА!** Потеряно {g['bet']} 🪙.", call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode="Markdown")
        return
    g["opened"].append(cell); mult = MULT[g["bombs"]] ** len(g["opened"]); reward = math.floor(g["bet"] * mult); save_data()
    bot.edit_message_text(f"💣 **МИНЫ**\nСтавка: {g['bet']} 🪙\nОткрыто: {len(g['opened'])}\nМнож: x{mult:.2f}\nЗабрать: {reward} 🪙", call.message.chat.id, call.message.message_id, reply_markup=mines_kb(gid), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("mcash_"))
def mines_cashout(call):
    gid = call.data.split("_")[1]; uid = str(call.from_user.id); g = data["active_games"].get(gid)
    if not g or g["user"] != uid or not g["opened"]: return
    reward = math.floor(g["bet"] * (MULT[g["bombs"]] ** len(g["opened"])))
    add_balance(uid, reward); del data["active_games"][gid]; save_data()
    bot.edit_message_text(f"🏆 **Забрано!** +{reward} 🪙", call.message.chat.id, call.message.message_id, reply_markup=None, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text.lower().startswith("краш"))
def start_crash(message):
    uid = str(message.from_user.id)
    try:
        bet = int(message.text.split()[1])
        if bet <= 0 or get_balance(uid) < bet: return bot.reply_to(message, "❌ Недостаточно средств.")
        add_balance(uid, -bet); gid = str(random.randint(10000, 99999))
        data["active_games"][gid] = {"type": "crash", "user": uid, "bet": bet, "crash_point": round(random.uniform(1.1, 10.0), 2), "current": 1.0, "active": True}
        save_data()
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("💰 ЗАБРАТЬ", callback_data=f"ccash_{gid}"))
        msg = bot.reply_to(message, f"🚀 **CRASH**\nСтавка: {bet}\nКоэф: x1.00", reply_markup=kb)
        threading.Thread(target=crash_loop, args=(gid, uid, msg.chat.id, msg.message_id)).start()
    except: bot.reply_to(message, "❌ `краш 1000`")

def crash_loop(gid, uid, chat_id, msg_id):
    time.sleep(1)
    while True:
        g = data["active_games"].get(gid)
        if not g or not g["active"]: break
        
        # ИЗМЕНЕНИЕ: Рост замедлен в 3 раза (было 0.1, стало 0.03)
        g["current"] = round(g["current"] + 0.03, 2); save_data()
        
        if g["current"] >= g["crash_point"] or random.random() < 0.1:
            g["active"] = False; save_data()
            try: bot.edit_message_text(f"💥 **КРАШ на x{g['current']:.2f}!**\nПотеряно {g['bet']} 🪙.", chat_id, msg_id, reply_markup=None, parse_mode="Markdown")
            except: pass
            del data["active_games"][gid]; save_data(); break
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("💰 ЗАБРАТЬ", callback_data=f"ccash_{gid}"))
        try: bot.edit_message_text(f"🚀 **CRASH**\nСтавка: {g['bet']}\nКоэф: x{g['current']:.2f}", chat_id, msg_id, reply_markup=kb, parse_mode="Markdown")
        except: pass
        time.sleep(1)

@bot.callback_query_handler(func=lambda call: call.data.startswith("ccash_"))
def crash_cashout(call):
    gid = call.data.split("_")[1]; uid = str(call.from_user.id); g = data["active_games"].get(gid)
    if not g or g["user"] != uid or not g["active"]: return
    g["active"] = False; reward = math.floor(g["bet"] * g["current"]); add_balance(uid, reward); del data["active_games"][gid]; save_data()
    bot.edit_message_text(f"🏆 **Забрано на x{g['current']:.2f}!** +{reward} 🪙", call.message.chat.id, call.message.message_id, reply_markup=None, parse_mode="Markdown")

@bot.message_handler(func=lambda m: " на " in m.text.lower() and m.text.lower().split()[0].isdigit())
def roulette(message):
    uid = str(message.from_user.id); t = message.text.lower().strip(); p = t.split()
    try:
        bet = int(p[0]); targets = [p[i] for i in range(2, len(p)) if p[i] != "на"]; cost = bet * len(targets)
        if cost <= 0 or get_balance(uid) < cost: return bot.reply_to(message, f"❌ Нужно {cost} 🪙.")
        add_balance(uid, -cost); wn = random.randint(0, 36); wc = "green" if wn == 0 else ("red" if 1 <= wn <= 18 else "black"); sym = {"green": "🟢", "red": "🔴", "black": "⚫️"}[wc]
        tw = 0; res = []
        for x in targets:
            win, mlt = False, 0
            if "-" in x:
                try: s, e = map(int, x.split("-")); mlt = max(1, math.floor(37 / (e - s + 1))) if s <= wn <= e else 0
                except: pass
            elif x.isdigit():
                if int(x) == wn: win, mlt = True, 36
            elif x in ["red", "к", "кр"]: 
                if wc == "red": win, mlt = True, 2
            elif x in ["black", "ч"]:
                if wc == "black": win, mlt = True, 2
            elif x in ["green", "з"]:
                if wc == "green": win, mlt = True, 36
            elif x in ["even", "чет"]:
                if wn != 0 and wn % 2 == 0: win, mlt = True, 2
            elif x in ["odd", "нечет"]:
                if wn % 2 != 0: win, mlt = True, 2
            if win: r = bet * mlt; tw += r; res.append(f"✅ {bet} на {x} (+{r})")
            else: res.append(f"❌ {bet} на {x}")
        add_balance(uid, tw); bot.reply_to(message, f"🎰 {sym} **{wn}**\n" + "\n".join(res) + f"\n💰 Итог: {tw} 🪙", parse_mode="Markdown")
    except: bot.reply_to(message, "❌ `1000 на 5`")

# --- КЛАНЫ ---
@bot.message_handler(func=lambda m: m.text.lower().strip() in ["мой клан", "клан"])
def my_clan_info(message):
    uid = str(message.from_user.id); p = data["players"].get(uid, {})
    if not p.get("clan_id"): return bot.reply_to(message, "🛡 У вас нет клана.\n`создать клан ИМЯ` (5000)\n`вступить клан ID`", parse_mode="Markdown")
    cid = str(p["clan_id"]); clan = data["clans"].get(cid)
    if not clan: return bot.reply_to(message, "❌ Клан удален.")
    members = [f"{m.get('username')} ({m.get('role')})" for m in data["players"].values() if m.get("clan_id") == cid]
    text = f"🛡 **Клан: {clan['name']}**\n🆔 ID: `{cid}`\n👑 Создатель: {clan['owner_name']}\n👥 Участники: {len(members)}/15\n💰 Казна: {clan.get('treasury', 0)} 🪙\n\nВаша роль: **{p.get('role', 'игрок').upper()}**\n\n" + "\n".join(members)
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text.lower().strip() == "топ кланов")
def clans_top(message):
    if not data["clans"]: return bot.reply_to(message, "Нет кланов.")
    sorted_clans = sorted(data["clans"].items(), key=lambda x: x[1].get("treasury", 0), reverse=True)[:10]
    text = "🏆 **ТОП КЛАНОВ**\n\n" + "".join([f"{i}. {c['name']} — {c.get('treasury',0)} 🪙 (ID: {cid})\n" for i, (cid, c) in enumerate(sorted_clans, 1)])
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text.lower().startswith("создать клан"))
def create_clan(message):
    uid = str(message.from_user.id)
    if data["players"][uid].get("clan_id"): return bot.reply_to(message, "❌ Вы уже в клане.")
    if get_balance(uid) < 5000: return bot.reply_to(message, "❌ Нужно 5000 🪙.")
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3: return bot.reply_to(message, "❌ `создать клан ИМЯ`", parse_mode="Markdown")
    cid = str(random.randint(1000, 9999))
    while cid in data["clans"]: cid = str(random.randint(1000, 9999))
    add_balance(uid, -5000); data["clans"][cid] = {"name": parts[2][:15], "owner_id": uid, "owner_name": get_nick(uid), "treasury": 0}
    data["players"][uid]["clan_id"] = cid; data["players"][uid]["role"] = "создатель"; save_data()
    bot.reply_to(message, f"✅ Клан **{parts[2][:15]}** создан! ID: `{cid}`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text.lower().startswith("вступить клан"))
def join_clan(message):
    uid = str(message.from_user.id)
    if data["players"][uid].get("clan_id"): return bot.reply_to(message, "❌ Вы уже в клане.")
    parts = message.text.split()
    if len(parts) < 3 or parts[2] not in data["clans"]: return bot.reply_to(message, "❌ Клан не найден.")
    cid = parts[2]
    if len([m for m in data["players"].values() if m.get("clan_id") == cid]) >= 15: return bot.reply_to(message, "❌ Клан полон (15).")
    data["players"][uid]["clan_id"] = cid; data["players"][uid]["role"] = "игрок"; save_data()
    bot.reply_to(message, f"✅ Вы вступили в **{data['clans'][cid]['name']}**!", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text.lower().startswith("пополнить казну"))
def add_treasury(message):
    uid = str(message.from_user.id); cid = data["players"][uid].get("clan_id")
    if not cid: return bot.reply_to(message, "❌ Вы не в клане.")
    try:
        amount = int(message.text.split()[2])
        if amount <= 0 or get_balance(uid) < amount: return bot.reply_to(message, "❌ Ошибка суммы.")
        add_balance(uid, -amount); data["clans"][cid]["treasury"] = data["clans"][cid].get("treasury", 0) + amount; save_data()
        bot.reply_to(message, f"✅ Казна пополнена на {amount} 🪙!")
    except: bot.reply_to(message, "❌ `пополнить казну 1000`")

@bot.message_handler(func=lambda m: m.text.lower().strip() == "выйти из клана")
def leave_clan(message):
    uid = str(message.from_user.id); cid = data["players"][uid].get("clan_id")
    if not cid: return bot.reply_to(message, "❌ Вы не в клане.")
    if data["players"][uid].get("role") == "создатель":
        members = [m for m in data["players"].items() if m[1].get("clan_id") == cid and m[0] != uid]
        if members:
            new_owner = random.choice(members); data["players"][new_owner[0]]["role"] = "создатель"; data["clans"][cid]["owner_id"] = new_owner[0]; data["clans"][cid]["owner_name"] = get_nick(new_owner[0])
        else: del data["clans"][cid]
    data["players"][uid]["clan_id"] = None; data["players"][uid]["role"] = "none"; save_data()
    bot.reply_to(message, "✅ Вы покинули клан.")

# --- РОЛИ ---
def has_perm(uid, act):
    role = data["players"][uid].get("role", "none")
    if role == "создатель": return True
    if role == "заместитель" and act in ["rename", "appoint", "kick"]: return True
    if role == "модер" and act == "rename": return True
    return False

@bot.message_handler(func=lambda m: m.text.lower().startswith("переименовать клан"))
def rename_clan(message):
    uid = str(message.from_user.id)
    if not has_perm(uid, "rename"): return bot.reply_to(message, "❌ Нет прав.")
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3: return bot.reply_to(message, "❌ `переименовать клан ИМЯ`")
    cid = data["players"][uid]["clan_id"]; data["clans"][cid]["name"] = parts[2][:15]; save_data()
    bot.reply_to(message, "✅ Клан переименован!")

@bot.message_handler(func=lambda m: m.text.lower().startswith("назначить"))
def appoint(message):
    uid = str(message.from_user.id)
    if not has_perm(uid, "appoint"): return bot.reply_to(message, "❌ Нет прав.")
    try:
        parts = message.text.split(); role, target = parts[1].lower(), parts[2].replace("@", "")
        if role not in ["модер", "заместитель"]: raise ValueError
        cid = data["players"][uid]["clan_id"]
        t_uid = next((u for u, p in data["players"].items() if p.get("username", "").lower() == target.lower() and p.get("clan_id") == cid), None)
        if not t_uid: return bot.reply_to(message, "❌ Игрок не найден.")
        data["players"][t_uid]["role"] = role; save_data()
        bot.reply_to(message, f"✅ {target} назначен {role}.")
    except: bot.reply_to(message, "❌ `назначить РОЛЬ ник`")

@bot.message_handler(func=lambda m: m.text.lower().startswith("кикнуть"))
def kick(message):
    uid = str(message.from_user.id)
    if not has_perm(uid, "kick"): return bot.reply_to(message, "❌ Нет прав.")
    try:
        target = message.text.split()[1].replace("@", ""); cid = data["players"][uid]["clan_id"]
        t_uid = next((u for u, p in data["players"].items() if p.get("username", "").lower() == target.lower() and p.get("clan_id") == cid), None)
        if not t_uid: return bot.reply_to(message, "❌ Игрок не найден.")
        data["players"][t_uid]["clan_id"] = None; data["players"][t_uid]["role"] = "none"; save_data()
        bot.reply_to(message, f"✅ {target} кикнут.")
    except: bot.reply_to(message, "❌ `кикнуть ник`")

# --- ПОМОЩЬ ---
@bot.message_handler(func=lambda m: m.text.lower().strip() == "помощь")
def help_cmd(message):
    text = (
        "📖 **ИНСТРУКЦИЯ**\n\n"
        "**👤 БАЗОВЫЕ**\n`б`, `профиль`, `бонус`\n`сменить ник ИМЯ`\n`чаты` — канал и чат\n\n"
        "**🏢 БИЗНЕС**\n`мой бизнес` — меню\n\n"
        "**🏦 БАНК**\n`банк` — инфо\n`банк положить СУММА`\n`банк снять СУММА`\n`депозит положить СУММА` (10% за 3 дня)\n`депозит снять`\n\n"
        "**💸 ПЕРЕВОД**\n`перевод СУММА ник`\n(или ответьте на сообщение: `перевод СУММА`)\n\n"
        "**🎮 ИГРЫ**\n`мины СУММА МИНЫ`\n`краш СУММА`\n`СУММА на ЦИФРА`\n\n"
        "**🛡 КЛАНЫ**\n`создать клан ИМЯ` (5000)\n`вступить клан ID`\n`мой клан`, `топ кланов`\n`пополнить казну СУММА`\n`выйти из клана`\n\n"
        "**👑 УПРАВЛЕНИЕ**\n`переименовать клан ИМЯ`\n`назначить РОЛЬ ник`\n`кикнуть ник`\n\n"
        "**💳 ДОНАТ**\n1 ⭐ = 500 Mon1Coin\n`/donate`\n\n"
        "**⚙️ АДМИН**\n`/give ИГРОВОЙ_ID СУММА`\n`/reset ИГРОВОЙ_ID`\n`/wipe`\n`/createpromo КОД СУММА ЮЗЫ`\n\n"
        "📢 **Канал:** @mon1bots\n💬 **Чат:** @mon1not"
    )
    bot.reply_to(message, text, parse_mode="Markdown")

# --- ДОНАТ ---
@bot.message_handler(commands=['donate'])
def donate_cmd(message):
    kb = InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("⭐ 25 Звезд (12 500)", callback_data="pay_25"),
        InlineKeyboardButton("⭐ 50 Звезд (25 000)", callback_data="pay_50"),
        InlineKeyboardButton("⭐ 100 Звезд (50 000)", callback_data="pay_100"),
        InlineKeyboardButton("📝 Выбрать количество", callback_data="donate_custom")
    )
    bot.send_message(message.chat.id, "💖 **Донат**\nВыберите пакет:", reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_"))
def pay(call):
    s = int(call.data.split("_")[1]); c = s * 500
    bot.answer_callback_query(call.id)
    bot.send_invoice(call.message.chat.id, "Донат", f"+{c} Mon1Coin", f"don_{s}_{c}", "", "XTR", [LabeledPrice("Донат", s)])

@bot.callback_query_handler(func=lambda call: call.data == "donate_custom")
def donate_custom(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "Введите количество звезд (от 1 до 5000):")
    bot.register_next_step_handler(msg, process_custom_donate)

def process_custom_donate(message):
    try:
        s = int(message.text.strip())
        if s < 1 or s > 5000: return bot.reply_to(message, "❌ Введите число от 1 до 5000.")
        c = s * 500
        bot.send_invoice(message.chat.id, "Донат", f"+{c} Mon1Coin", f"don_{s}_{c}", "", "XTR", [LabeledPrice("Донат", s)])
    except: bot.reply_to(message, "❌ Неверный формат. Введите число.")

@bot.pre_checkout_query_handler(func=lambda q: True)
def pre_chk(q): bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def success(m):
    p = m.successful_payment.invoice_payload
    if p.startswith("don_"):
        c = int(p.split("_")[2]); add_balance(m.from_user.id, c); bot.send_message(m.chat.id, f"🎉 +{c} 🪙")

# --- АДМИН И БАЗА ---
@bot.message_handler(func=lambda m: m.text.lower().strip() in ["б", "баланс"])
def bal_cmd(message): bot.reply_to(message, f"🪙 Баланс: {get_balance(message.from_user.id)} Mon1Coin")

@bot.message_handler(func=lambda m: m.text.lower().strip() == "профиль")
def profile_cmd(message):
    uid = message.from_user.id; p = data["players"].get(str(uid), {}); c_info = "Нет"
    if p.get("clan_id"): c_info = f"{data['clans'].get(str(p['clan_id']), {}).get('name', '?')} ({p.get('role', 'игрок')})"
    bot.reply_to(message, f"👤 **Профиль**\n🆔 ID: `{p.get('short_id')}`\n📛 Ник: {get_nick(uid)}\n🪙 Баланс: {get_balance(uid)}\n🛡 Клан: {c_info}", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text.lower().strip() == "бонус")
def bonus_cmd(message):
    uid = str(message.from_user.id); now = int(time.time()); last = data["players"].get(uid, {}).get("last_bonus", 0)
    if now - last < 86400: return bot.reply_to(message, f"⏳ Ждать: {(86400-(now-last))//3600} ч.")
    amt = random.randint(1000, 2000); add_balance(uid, amt); data["players"][uid]["last_bonus"] = now; save_data()
    bot.reply_to(message, f"🎁 **БОНУС!** +{amt} 🪙", parse_mode="Markdown")

@bot.message_handler(commands=['give'])
def give(m):
    if m.from_user.id not in ADMIN_IDS: return
    try:
        a = m.text.split()[1:]; sid, amt = a[0], int(a[1]); real_uid = get_user_by_short_id(sid)
        if not real_uid: return bot.reply_to(m, "❌ Игрок не найден.")
        add_balance(real_uid, amt); bot.reply_to(m, f"✅ Выдано {amt} 🪙 игроку {sid}.")
    except: bot.reply_to(m, "❌ `/give ID СУММА`", parse_mode="Markdown")

@bot.message_handler(commands=['reset'])
def rst(m):
    if m.from_user.id not in ADMIN_IDS: return
    try:
        sid = m.text.split()[1]; real_uid = get_user_by_short_id(sid)
        if real_uid: data["players"][real_uid]["balance"] = 0; save_data(); bot.reply_to(m, "♻️ Сброшено.")
    except: pass

@bot.message_handler(commands=['wipe'])
def wipe(m):
    if m.from_user.id not in ADMIN_IDS: return
    for u in data["players"]: data["players"][u]["balance"] = 1000
    save_data(); bot.reply_to(m, "♻️ Все по 1000.")

@bot.message_handler(commands=['createpromo'])
def promo(m):
    if m.from_user.id not in ADMIN_IDS: return
    try:
        a = m.text.split()[1:]; data["promos"][a[0].upper()] = {"amount": int(a[1]), "uses_left": int(a[2])}
        save_data(); bot.reply_to(m, "✅ Создан.")
    except: bot.reply_to(m, "❌ `/createpromo КОД СУММА ЮЗЫ`", parse_mode="Markdown")

@bot.message_handler(content_types=['text'])
def handle_text(m):
    if m.text.startswith('/'): return
    t = m.text.lower().strip(); u = str(m.from_user.id)
    if t.startswith("сменить ник"):
        new_nick = m.text[11:].strip()[:15]
        if new_nick: data["players"][u]["username"] = new_nick; save_data(); return bot.reply_to(m, "✅ Ник изменен.")

    if len(t.split()) == 1 and len(t) > 3 and t.isalnum():
        code = t.upper()
        if code in data["promos"]:
            pr = data["promos"][code]
            if pr["uses_left"] <= 0: return bot.reply_to(m, "❌ Не работает.")
            if [u, code] in data["activations"]: return bot.reply_to(m, "❌ Уже активировали!")
            add_balance(u, pr["amount"]); pr["uses_left"] -= 1; data["activations"].append([u, code]); save_data()
            return bot.reply_to(m, f"🎉 +{pr['amount']} 🪙")

@bot.callback_query_handler(func=lambda call: call.data == "ignore")
def ignore(call): bot.answer_callback_query(call.id)

print("BOT STARTED")
bot.infinity_polling(skip_pending=True)
