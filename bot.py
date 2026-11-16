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

# Начальная структура БД
data = {
    "players": {}, "promos": {}, "activations": [], "history": [], "transfers": [],
    "clans": {}, "clan_members": {}, "clan_bosses": {}
}

def load_data():
    global data
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                for key in loaded:
                    data[key] = loaded[key]
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

def get_nick(user_id):
    uid = str(user_id)
    if uid not in data["players"]: return "Player"
    return data["players"][uid].get("username", "Player")

def get_user_short_id(user_id):
    uid = str(user_id)
    if uid not in data["players"]: return "0"
    return data["players"][uid].get("short_id", "0")

def add_balance(user_id, amount):
    uid = str(user_id)
    if uid not in data["players"]:
        data["players"][uid] = {"username": "Player", "balance": 0, "last_bonus": 0, "short_id": random.randint(1000, 9999), "clan_id": None, "weapon": 1, "armor": 1}
    data["players"][uid]["balance"] += amount
    save_data()

def register_user(user):
    uid = str(user.id)
    if uid not in data["players"]:
        data["players"][uid] = {
            "username": user.username or user.first_name,
            "balance": 1000,
            "last_bonus": 0,
            "short_id": random.randint(1000, 9999),
            "clan_id": None,
            "weapon": 1, # 1 - кулаки
            "armor": 1   # 1 - рваная одежда
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
        InlineKeyboardButton("👤 ПРОФИЛЬ", callback_data="profile"),
        InlineKeyboardButton("🎁 БОНУС", callback_data="bonus_menu"),
        InlineKeyboardButton("🏆 ТОП", callback_data="top_menu"),
        InlineKeyboardButton("🛡 КЛАНЫ", callback_data="clan_menu"),
        InlineKeyboardButton("⚔️ МАГАЗИН", callback_data="shop_menu"),
        InlineKeyboardButton("❓ ПОМОЩЬ", callback_data="help_menu"),
        InlineKeyboardButton("⭐ ДОНАТ", callback_data="donate_menu")
    )
    return kb

# --- СТАРТ ---
@bot.message_handler(commands=["start"])
def start(message):
    register_user(message.from_user)
    bot.send_message(message.chat.id, f"🎰 ДОБРО ПОЖАЛОВАТЬ В MON1 CASINO RPG!\n\n🪙 Твой баланс: {get_balance(message.from_user.id)} Mon1Coin\n\nВыбирай действие:", reply_markup=main_menu())

# --- ПРОФИЛЬ ---
@bot.callback_query_handler(func=lambda call: call.data == "profile")
def profile_callback(call):
    bot.answer_callback_query(call.id)
    uid = call.from_user.id
    p = data["players"].get(str(uid), {})
    clan_name = "Нет" if not p.get("clan_id") else data["clans"].get(str(p["clan_id"]), {}).get("name", "Нет")
    
    text = (
        f"👤 **Профиль**\n\n"
        f"🆔 ID: `{p.get('short_id')}`\n"
        f"📛 Ник: {get_nick(uid)}\n"
        f"🪙 Баланс: {get_balance(uid)} Mon1Coin\n"
        f"🛡 Клан: {clan_name}\n"
        f"⚔️ Оружие ур.{p.get('weapon', 1)}\n"
        f"🥋 Броня ур.{p.get('armor', 1)}"
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=main_menu(), parse_mode="Markdown")

# --- БОНУС (Упрощен) ---
@bot.callback_query_handler(func=lambda call: call.data == "bonus_menu")
def bonus_callback(call):
    bot.answer_callback_query(call.id)
    process_bonus(call.from_user.id, call.message.chat.id, call.message.message_id)

def process_bonus(user_id, chat_id, msg_id=None):
    uid = str(user_id)
    current_time = int(time.time())
    last_bonus = data["players"].get(uid, {}).get("last_bonus", 0)
    cooldown = 24 * 60 * 60

    if current_time - last_bonus < cooldown:
        remaining = cooldown - (current_time - last_bonus)
        msg = f"⏳ Бонус через: **{remaining // 3600} ч. {(remaining % 3600) // 60} мин.**"
    else:
        bonus_amount = random.randint(1000, 2000)
        add_balance(user_id, bonus_amount)
        data["players"][uid]["last_bonus"] = current_time
        save_data()
        msg = f"🎁 **БОНУС!**\n\nВы получили: **+{bonus_amount} Mon1Coin** 🪙"

    if msg_id: bot.edit_message_text(msg, chat_id, msg_id, reply_markup=main_menu(), parse_mode="Markdown")
    else: bot.send_message(chat_id, msg, reply_markup=main_menu(), parse_mode="Markdown")

# --- КЛАНЫ (Меню) ---
@bot.callback_query_handler(func=lambda call: call.data == "clan_menu")
def clan_menu(call):
    bot.answer_callback_query(call.id)
    uid = call.from_user.id
    p = data["players"].get(str(uid), {})
    
    if p.get("clan_id"):
        # Игрок уже в клане
        clan_id = p["clan_id"]
        clan = data["clans"].get(str(clan_id), {})
        boss = data["clan_bosses"].get(str(clan_id), {"level": 1, "hp": 1000, "max_hp": 1000})
        
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("⚔️ Атаковать Босса", callback_data="attack_boss"),
            InlineKeyboardButton("ℹ️ Инфо о Клане", callback_data="clan_info")
        )
        text = (
            f"🛡 **Твой Клан: {clan.get('name', 'Unknown')}**\n\n"
            f"👑 Владелец: {clan.get('owner_name', 'Unknown')}\n"
            f"👥 Игроков: {len([m for m in data['players'].values() if m.get('clan_id') == clan_id])}/15\n"
            f"🆔 ID Клана: `{clan_id}`\n\n"
            f"🐉 **БОСС КЛАНА (Ур. {boss['level']})**\n"
            f"❤️ HP: {boss['hp']} / {boss['max_hp']}"
        )
    else:
        # Игрок без клана
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton("➕ Создать Клан (5000 🪙)", callback_data="create_clan"),
            InlineKeyboardButton("🔍 Вступить по ID", callback_data="join_clan_prompt")
        )
        text = "🛡 **Кланы**\n\nТы не состоишь в клане.\nСоздай свой за 5000 или вступи по ID."
        
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "create_clan")
def create_clan_prompt(call):
    bot.answer_callback_query(call.id)
    uid = call.from_user.id
    if get_balance(uid) < 5000:
        return bot.answer_callback_query(call.id, "❌ Недостаточно средств! Нужно 5000.", show_alert=True)
    
    msg = bot.send_message(call.message.chat.id, "Введите название для вашего клана (до 15 символов):")
    bot.register_next_step_handler(msg, process_create_clan)

def process_create_clan(message):
    uid = str(message.from_user.id)
    clan_name = message.text.strip()[:15]
    if not clan_name:
        return bot.reply_to(message, "❌ Название не может быть пустым.")
        
    if get_balance(uid) < 5000:
        return bot.reply_to(message, "❌ У вас нет 5000 монет.")
        
    clan_id = str(random.randint(1000, 9999))
    while clan_id in data["clans"]:
        clan_id = str(random.randint(1000, 9999))
        
    add_balance(uid, -5000)
    data["clans"][clan_id] = {"name": clan_name, "owner_id": uid, "owner_name": get_nick(uid)}
    data["players"][uid]["clan_id"] = clan_id
    data["clan_bosses"][clan_id] = {"level": 1, "hp": 1000, "max_hp": 1000}
    save_data()
    
    bot.reply_to(message, f"✅ Клан **{clan_name}** создан!\nID вашего клана: `{clan_id}`\nПередайте этот ID друзьям.", parse_mode="Markdown", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda call: call.data == "join_clan_prompt")
def join_clan_prompt(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "Введите ID клана, в который хотите вступить:")
    bot.register_next_step_handler(msg, process_join_clan)

def process_join_clan(message):
    uid = str(message.from_user.id)
    clan_id = message.text.strip()
    
    if clan_id not in data["clans"]:
        return bot.reply_to(message, "❌ Клан с таким ID не найден.")
        
    members_count = len([m for m in data["players"].values() if m.get("clan_id") == clan_id])
    if members_count >= 15:
        return bot.reply_to(message, "❌ В клане уже максимум игроков (15).")
        
    data["players"][uid]["clan_id"] = clan_id
    save_data()
    bot.reply_to(message, f"✅ Вы вступили в клан **{data['clans'][clan_id]['name']}**!", parse_mode="Markdown", reply_markup=main_menu())

# --- МАГАЗИН ЭКИПИРОВКИ ---
@bot.callback_query_handler(func=lambda call: call.data == "shop_menu")
def shop_menu(call):
    bot.answer_callback_query(call.id)
    uid = call.from_user.id
    p = data["players"].get(str(uid), {})
    
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🗡 Купить Оружие (2000)", callback_data="buy_weapon"),
        InlineKeyboardButton("🛡 Купить Броню (2000)", callback_data="buy_armor")
    )
    text = (
        f"⚔️ **Магазин Экипировки**\n\n"
        f"Твои характеристики:\n"
        f"🗡 Оружие: Ур. {p.get('weapon', 1)} (Урон +{p.get('weapon', 1)*10})\n"
        f"🛡 Броня: Ур. {p.get('armor', 1)} (Защита -{p.get('armor', 1)*5} урона по боссу)\n\n"
        f"🪙 Баланс: {get_balance(uid)}\n\n"
        f"Улучшение стоит 2000 монет. Уровень повышается на 1."
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "buy_weapon")
def buy_weapon(call):
    bot.answer_callback_query(call.id)
    uid = str(call.from_user.id)
    if get_balance(uid) < 2000:
        return bot.answer_callback_query(call.id, "❌ Недостаточно средств!", show_alert=True)
    
    add_balance(uid, -2000)
    data["players"][uid]["weapon"] += 1
    save_data()
    bot.answer_callback_query(call.id, f"✅ Оружие улучшено до ур. {data['players'][uid]['weapon']}!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "buy_armor")
def buy_armor(call):
    bot.answer_callback_query(call.id)
    uid = str(call.from_user.id)
    if get_balance(uid) < 2000:
        return bot.answer_callback_query(call.id, "❌ Недостаточно средств!", show_alert=True)
    
    add_balance(uid, -2000)
    data["players"][uid]["armor"] += 1
    save_data()
    bot.answer_callback_query(call.id, f"✅ Броня улучшена до ур. {data['players'][uid]['armor']}!", show_alert=True)

# --- БИТВА С БОССОМ ---
@bot.callback_query_handler(func=lambda call: call.data == "attack_boss")
def attack_boss(call):
    bot.answer_callback_query(call.id)
    uid = str(call.from_user.id)
    clan_id = data["players"].get(uid, {}).get("clan_id")
    if not clan_id:
        return bot.answer_callback_query(call.id, "❌ Вы не в клане!")
        
    boss = data["clan_bosses"].get(str(clan_id))
    if not boss:
        return bot.answer_callback_query(call.id, "❌ Босс не найден.")
        
    weapon_lvl = data["players"][uid].get("weapon", 1)
    armor_lvl = data["players"][uid].get("armor", 1)
    
    damage = weapon_lvl * random.randint(10, 20)
    boss["hp"] -= damage
    
    msg = ""
    if boss["hp"] <= 0:
        # Босс убит
        reward_pool = 500 * boss["level"]
        data["players"][uid]["balance"] += reward_pool
        msg = f"🎉 **БОСС ПОВЕРЖЕН!**\nВы нанесли последний удар и получили **{reward_pool} Mon1Coin**!"
        
        # Апаем следующего босса
        boss["level"] += 1
        boss["max_hp"] += 1000
        boss["hp"] = boss["max_hp"]
    else:
        # Босс жив, бьет в ответ (урон пробивает броню)
        counter_damage = max(1, random.randint(10, 20) - (armor_lvl * 5))
        data["players"][uid]["balance"] = max(0, data["players"][uid]["balance"] - counter_damage)
        msg = f"⚔️ Вы ударили Босса на **{damage}** урона.\nБосс ударил вас на **{counter_damage}** урона (Броня спасла)."
        
    save_data()
    bot.send_message(call.message.chat.id, msg, parse_mode="Markdown", reply_markup=main_menu())
    # --- ТОП ---
@bot.callback_query_handler(func=lambda call: call.data == "top_menu")
def top_callback(call):
    bot.answer_callback_query(call.id)
    sorted_players = sorted(data["players"].items(), key=lambda x: x[1].get("balance", 0), reverse=True)
    text = "🏆 **ТОП-10 БОГАЧЕЙ**\n\n"
    for i, (uid, pdata) in enumerate(sorted_players[:10], 1):
        name = pdata.get("username", "Unknown")
        bal = pdata.get("balance", 0)
        text += f"{i}. {name} — {bal} 🪙\n"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=main_menu(), parse_mode="Markdown")

# --- ПОМОЩЬ ---
@bot.callback_query_handler(func=lambda call: call.data == "help_menu")
def help_callback(call):
    bot.answer_callback_query(call.id)
    text = (
        "📖 **ИНСТРУКЦИЯ**\n\n"
        "🪙 `б` - баланс\n`профиль` - ваш ID и статы\n"
        "`сменить ник ИМЯ` - сменить ник\n`бонус` - раз в 24 часа\n\n"
        "**🎮 ИГРЫ**\n`мины 1000` / `краш 500`\n`1000 на 1 на 5` (рулетка)\n\n"
        "**🛡 КЛАНЫ**\nСоздать: 5000 монет\nВступить: по ID\nЛимит: 15 чел.\n\n"
        "**⚔️ МАГАЗИН**\nОружие/Броня: 2000 монет\n\n"
        "**👑 АДМИН**\n`/give ID СУММА`\n`/reset ID`\n`/wipe`\n`/createpromo КОД СУММА ЮЗЫ`"
    )
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=main_menu(), parse_mode="Markdown")

# --- CRASH ---
@bot.callback_query_handler(func=lambda call: call.data == "game_crash")
def crash_menu(call):
    bot.answer_callback_query(call.id)
    bot.edit_message_text("🚀 Введите: `краш 1000`", call.message.chat.id, call.message.message_id, reply_markup=main_menu(), parse_mode="Markdown")

def start_crash_game(user_id, chat_id, bet):
    if get_balance(user_id) < bet: return bot.send_message(chat_id, "❌ Недостаточно Mon1Coin!")
    add_balance(user_id, -bet)
    crash_point = round(random.uniform(1.1, 100.0), 2)
    crash_games[user_id] = {"bet": bet, "crash_point": crash_point, "current": 1.0, "active": True}
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("💰 ЗАБРАТЬ", callback_data="crash_cashout"))
    msg = bot.send_message(chat_id, f"🚀 CRASH\nСтавка: {bet} 🪙\nКоэф: x1.00", reply_markup=kb)
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
            bot.edit_message_text(f"🚀 CRASH\nСтавка: {g['bet']} 🪙\nКоэф: x{g['current']:.2f}\n\nУспей забрать!", chat_id, msg_id, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("💰 ЗАБРАТЬ", callback_data="crash_cashout")))
        except Exception: pass
        time.sleep(1)

@bot.callback_query_handler(func=lambda call: call.data == "crash_cashout")
def crash_cashout(call):
    g = crash_games.get(call.from_user.id)
    if not g or not g["active"]: return
    g["active"] = False
    reward = math.floor(g["bet"] * g["current"])
    add_balance(call.from_user.id, reward)
    bot.edit_message_text(f"🏆 Ты забрал на x{g['current']:.2f}!\n+{reward} 🪙", call.message.chat.id, call.message.message_id, reply_markup=main_menu())

# --- MINES ---
MULTIPLIERS = {2: 1.10, 3: 1.15, 5: 1.25, 9: 1.45}

@bot.callback_query_handler(func=lambda call: call.data == "game_mines")
def mines_menu(call):
    bot.answer_callback_query(call.id)
    bot.edit_message_text("💣 Введите: `мины 1000 3`", call.message.chat.id, call.message.message_id, reply_markup=main_menu(), parse_mode="Markdown")

def start_mines_game(user_id, chat_id, bet, bombs):
    if get_balance(user_id) < bet: return bot.send_message(chat_id, "❌ Недостаточно Mon1Coin!")
    if bombs not in MULTIPLIERS: return bot.send_message(chat_id, "❌ Доступно мин: 2, 3, 5 или 9.")
    add_balance(user_id, -bet)
    mines_games[user_id] = {"bet": bet, "bombs": bombs, "mines": set(random.sample(range(25), bombs)), "opened": set(), "finished": False}
    bot.send_message(chat_id, mines_text(user_id), reply_markup=mines_kb(user_id), parse_mode="Markdown")

def mines_text(user_id):
    g = mines_games[user_id]; opened = len(g["opened"]); mult = MULTIPLIERS[g["bombs"]] ** opened if opened > 0 else 1.0; reward = math.floor(g["bet"] * mult)
    return f"💣 MINES\nСтавка: {g['bet']} 🪙\nМин: {g['bombs']}\nОткрыто: {opened}\n📈 Множитель: x{mult:.2f}\n🎁 Забрать: {reward} 🪙"

def mines_kb(user_id):
    g = mines_games[user_id]; kb = InlineKeyboardMarkup(row_width=5)
    for r in range(5):
        row = []
        for c in range(5):
            i = r * 5 + c
            sym = "💎" if i in g["opened"] else ("💣" if g["finished"] and i in g["mines"] else ("▫️" if g["finished"] else "❔"))
            row.append(InlineKeyboardButton(sym, callback_data=f"mcell_{i}"))
        kb.row(*row)
    if not g["finished"] and g["opened"]: kb.row(InlineKeyboardButton("⭐ ЗАБРАТЬ", callback_data="mcashout"))
    return kb

@bot.callback_query_handler(func=lambda call: call.data.startswith("mcell_") or call.data == "mcashout")
def mines_play(call):
    user_id = call.from_user.id; g = mines_games.get(user_id)
    if not g or g["finished"]: return
    if call.data == "mcashout":
        reward = math.floor(g["bet"] * (MULTIPLIERS[g["bombs"]] ** len(g["opened"])))
        add_balance(user_id, reward); g["finished"] = True
        bot.edit_message_text(f"🏆 Ты забрал {reward} 🪙!", call.message.chat.id, call.message.message_id, reply_markup=main_menu(), parse_mode="Markdown")
        return
    idx = int(call.data.split("_")[1])
    if idx in g["mines"]:
        g["finished"] = True
        bot.edit_message_text(f"💥 МИНА!\nТы потерял {g['bet']} 🪙.", call.message.chat.id, call.message.message_id, reply_markup=main_menu(), parse_mode="Markdown")
    else:
        g["opened"].add(idx)
        bot.edit_message_text(mines_text(user_id), call.message.chat.id, call.message.message_id, reply_markup=mines_kb(user_id), parse_mode="Markdown")

# --- РУЛЕТКА ---
@bot.callback_query_handler(func=lambda call: call.data == "game_roulette")
def roul_menu(call):
    bot.answer_callback_query(call.id)
    bot.edit_message_text(f"🎰 **РУЛЕТКА**\n\n📜 История: {get_history_roulette()}\n\nФормат: `1000 на 1 на 5`\nЦвет: `500 на red`", call.message.chat.id, call.message.message_id, reply_markup=main_menu(), parse_mode="Markdown")

# --- ДОНАТ ---
@bot.callback_query_handler(func=lambda call: call.data == "donate_menu")
def donate_menu(call):
    bot.answer_callback_query(call.id)
    kb = InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("⭐ 50 Звезд (5000)", callback_data="pay_50"),
        InlineKeyboardButton("⭐ 100 Звезд (12000)", callback_data="pay_100"),
        InlineKeyboardButton("⭐ 250 Звезд (35000)", callback_data="pay_250")
    )
    bot.edit_message_text("💖 Выберите пакет:", call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_"))
def send_donate_invoice(call):
    stars = int(call.data.split("_")[1]); coins = {50: 5000, 100: 12000, 250: 35000}[stars]
    bot.answer_callback_query(call.id)
    bot.send_invoice(call.message.chat.id, "Донат", f"Вы получите {coins} Mon1Coin", f"donate_{stars}_{coins}", "", "XTR", [LabeledPrice("Донат", stars)])

@bot.pre_checkout_query_handler(func=lambda query: True)
def process_pre_checkout(query): bot.answer_pre_checkout_query(query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def process_successful_payment(message):
    payload = message.successful_payment.invoice_payload
    if payload.startswith("donate_"):
        coins = int(payload.split("_")[2]); add_balance(message.from_user.id, coins)
        bot.send_message(message.chat.id, f"🎉 +{coins} Mon1Coin 🪙", parse_mode="Markdown")

# --- АДМИНКА ---
@bot.message_handler(commands=['give'])
def admin_give(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        args = message.text.split()[1:]; target_id, amount = str(int(args[0])), int(args[1])
        if target_id not in data["players"]: register_user(message.from_user)
        add_balance(target_id, amount)
        bot.reply_to(message, f"✅ Выдано {amount} 🪙 игроку {target_id}.")
    except: bot.reply_to(message, "❌ Формат: `/give ID СУММА`", parse_mode="Markdown")

@bot.message_handler(commands=['reset'])
def admin_reset(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        target_id = str(int(message.text.split()[1]))
        if target_id in data["players"]:
            data["players"][target_id]["balance"] = 0; save_data()
            bot.reply_to(message, f"♻️ Баланс игрока {target_id} обнулен.")
    except: bot.reply_to(message, "❌ Формат: `/reset ID`", parse_mode="Markdown")

@bot.message_handler(commands=['createpromo'])
def create_promo(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        args = message.text.split()[1:]; code, amount, uses = args[0].upper(), int(args[1]), int(args[2])
        data["promos"][code] = {"amount": amount, "uses_left": uses}; save_data()
        bot.reply_to(message, f"✅ Промокод `{code}` создан!", parse_mode="Markdown")
    except: bot.reply_to(message, "❌ Формат: `/createpromo КОД СУММА ЮЗЫ`", parse_mode="Markdown")

@bot.message_handler(commands=['wipe'])
def admin_wipe(message):
    if message.from_user.id not in ADMIN_IDS: return
    for uid, pdata in data["players"].items(): pdata["balance"] = 1000
    save_data()
    bot.reply_to(message, "♻️ Балансы всех игроков сброшены до 1000.")

# --- ТЕКСТОВЫЕ КОМАНДЫ ---
@bot.message_handler(content_types=['text'])
def handle_all_text(message):
    if message.text.startswith('/'): return
    text = message.text.lower().strip(); parts = text.split(); user_id = message.from_user.id

    if text in ["б", "баланс"]: return bot.reply_to(message, f"🪙 Твой баланс: {get_balance(user_id)} Mon1Coin")
    if text in ["профиль", "п"]: return bot.reply_to(message, f"👤 ID: `{get_user_short_id(user_id)}`\nНик: {get_nick(user_id)}", parse_mode="Markdown")
    if text in ["помощь", "help"]: return send_help_text(message.chat.id)
    if text in ["топ", "top"]: return send_top_text(message.chat.id)
    if text in ["бонус", "bonus"]: return process_bonus(user_id, message.chat.id)

    if parts[0] in ["сменить", "ник"] and len(parts) >= 2:
        new_nick = " ".join(parts[1:])[:15]
        data["players"][str(user_id)]["username"] = new_nick; save_data()
        return bot.reply_to(message, f"✅ Твой новый ник: **{new_nick}**", parse_mode="Markdown")

   
