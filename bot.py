import os, random, math, time, telebot, threading, json, pathlib
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN: raise ValueError("Не задан BOT_TOKEN")

ADMIN_IDS = [8211650013, 6940877915]
DATA_DIR = pathlib.Path("/app/data"); DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = DATA_DIR / "database.json"

data = {"players": {}, "promos": {}, "activations": [], "history": [], "clans": {}, "next_id": 1, "active_games": {}, "roulette_bets": {}}
db_lock = threading.Lock()

def load_data():
    global data
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                for key in loaded: data[key] = loaded[key]
        except Exception as e: print(f"⚠️ Ошибка загрузки: {e}")

def save_data():
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f: 
            json.dump(data, f, ensure_ascii=False, indent=4)

load_data()

def migrate_data():
    global data
    changed = False
    current_max = max([p.get("short_id", 0) for p in data["players"].values() if isinstance(p.get("short_id"), int)], default=0)
    if data.get("next_id", 1) <= current_max: data["next_id"] = current_max + 1
    for uid, pdata in data["players"].items():
        if "short_id" not in pdata or pdata["short_id"] == 0:
            pdata["short_id"] = data["next_id"]; data["next_id"] += 1; changed = True
        if "bank" not in pdata: pdata["bank"] = 0; pdata["deposit"] = 0; pdata["deposit_start"] = 0; changed = True
        if "biz_territory" not in pdata: pdata["biz_territory"] = 0; pdata["biz_building"] = 1; pdata["biz_tax"] = 0; pdata["biz_last_collect"] = int(time.time()); changed = True
        if "title" not in pdata: pdata["title"] = "Нет"; changed = True
        if "quests" not in pdata: pdata["quests"] = {}; changed = True
        if "donate_status" not in pdata: pdata["donate_status"] = "Нет"; changed = True
        if "last_bonus" not in pdata: pdata["last_bonus"] = 0; changed = True
    if "roulette_bets" not in data: data["roulette_bets"] = {}
    if "promos" not in data: data["promos"] = {}
    if "activations" not in data: data["activations"] = []
    if changed: save_data()

migrate_data()
bot = telebot.TeleBot(TOKEN)

# Коэффициенты для мин (3, 5, 9 бомб)
MULT = {3: 1.15, 5: 1.25, 9: 1.45}

BIZ_TERRITORY_COST = {0: 10000, 1: 50000, 2: 250000, 3: 1000000, 4: 5000000, 5: 25000000}
BIZ_BUILDING_COST = {1: 20000, 2: 100000, 3: 500000, 4: 2000000, 5: 10000000}

def get_balance(uid): return data["players"].get(str(uid), {}).get("balance", 0)
def get_nick(uid): return data["players"].get(str(uid), {}).get("username", "Player")
def get_user_short_id(uid): return data["players"].get(str(uid), {}).get("short_id", "0")

def get_user_by_short_id(sid):
    for uid, pdata in data["players"].items():
        if str(pdata.get("short_id")) == str(sid): return uid
    return None

def get_user_by_username(uname):
    uname = uname.replace("@", "").lower()
    for uid, pdata in data["players"].items():
        if pdata.get("username", "").lower() == uname: return uid
    return None

def get_win_multiplier(uid):
    status = data["players"].get(str(uid), {}).get("donate_status", "Нет")
    if status == "VIP": return 1.05
    if status == "Premium": return 1.15
    if status == "Ultra": return 1.25
    return 1.0

def add_balance(uid, amt):
    uid = str(uid)
    if uid not in data["players"]: register_user_by_id(uid)
    data["players"][uid]["balance"] += amt; save_data()

def register_user(user):
    uid = str(user.id)
    if uid not in data["players"]:
        sid = data["next_id"]; data["next_id"] += 1
        data["players"][uid] = {"username": user.username or user.first_name, "balance": 1000, "last_bonus": 0, "short_id": sid, "clan_id": None, "role": "none", "bank": 0, "deposit": 0, "deposit_start": 0, "biz_territory": 0, "biz_building": 1, "biz_tax": 0, "biz_last_collect": int(time.time()), "title": "Нет", "quests": {}, "donate_status": "Нет"}
        save_data()

def register_user_by_id(uid):
    if uid not in data["players"]:
        sid = data["next_id"]; data["next_id"] += 1
        data["players"][uid] = {"username": "Player", "balance": 1000, "last_bonus": 0, "short_id": sid, "clan_id": None, "role": "none", "bank": 0, "deposit": 0, "deposit_start": 0, "biz_territory": 0, "biz_building": 1, "biz_tax": 0, "biz_last_collect": int(time.time()), "title": "Нет", "quests": {}, "donate_status": "Нет"}
        save_data()

# ==================== СТАРТ И ПОМОЩЬ ====================

@bot.message_handler(commands=["start"])
def start(message):
    register_user(message.from_user)
    bot.send_message(message.chat.id, 
        f"🎰 **MON1 CASINO RPG** 🎰\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Добро пожаловать, **{get_nick(message.from_user.id)}**!\n\n"
        f"💰 Ваш баланс: **{get_balance(message.from_user.id)} 🪙**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎮 **Игры:** `слот 1000`, `мины 1000 5`, `краш 1000`, `джокер 1000`, `1000 5 12`\n"
        f"🎁 **Бонус:** `бонус`\n"
        f"🛡 **Кланы:** `мой клан`\n"
        f"📖 **Помощь:** `помощь`", 
        parse_mode="Markdown")

@bot.message_handler(commands=['help'])
@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() in ['помощь', 'help'])
def help_command(message):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("🎮 Игры", callback_data="help_games"), InlineKeyboardButton("💼 Экономика", callback_data="help_eco"))
    kb.add(InlineKeyboardButton("🛡 Кланы", callback_data="help_clans"), InlineKeyboardButton("💎 Донат", callback_data="help_donate"))
    bot.reply_to(message, "📖 **МЕНЮ ПОМОЩИ**\n━━━━━━━━━━━━━━━━━━━━\nВыберите раздел кнопками ниже:", reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("help_"))
def help_callbacks(call):
    section = call.data.split("_")[1]
    if section == "games": text = "🎮 **ИГРЫ**\n━━━━━━━━━━━━━━━━━━━━\n• `слот 1000` — автомат\n• `мины 1000 5` — поле (3, 5, 9 бомб)\n• `краш 1000` — растущий коэф.\n• `джокер 1000` — лесенка удачи\n• `1000 5 красное` — рулетка (запуск `го`)"
    elif section == "eco": text = "💼 **ЭКОНОМИКА**\n━━━━━━━━━━━━━━━━━━━━\n• `б` — баланс\n• `бонус` — ежедневный бонус\n• `профиль` — профиль\n• `узнать ид` — ID игрока\n• `топ` — топ-10\n• `банк` — банк\n• `мой бизнес` — бизнес\n• `квесты` — задания\n• `перевод 1000 ник`\n• `промо КОД`\n• `сменить ник НОВЫЙ_НИК`"
    elif section == "clans": text = "🛡 **КЛАНЫ**\n━━━━━━━━━━━━━━━━━━━━\n• `создать клан ИМЯ` (10000)\n• `вступить клан ID`\n• `мой клан`\n• `выйти из клана`\n• `топ кланов`\n• `клан казна положить/снять СУММА`"
    elif section == "donate": text = "💎 **ДОНАТ**\n━━━━━━━━━━━━━━━━━━━━\n• `донат` — пополнить\n• `донат статус` — купить статус\n• `мой статус` — узнать статус"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=call.message.reply_markup, parse_mode="Markdown")
    bot.answer_callback_query(call.id)

# ==================== БОНУС ====================

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == 'бонус')
def daily_bonus(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]: register_user(message.from_user)
    p = data["players"][uid]
    now = int(time.time())
    last = p.get("last_bonus", 0)
    if now - last < 86400:
        left = 86400 - (now - last)
        return bot.reply_to(message, f"⏳ **Подождите!**\nСледующий бонус через **{left // 3600} ч. {(left % 3600) // 60} мин.**", parse_mode="Markdown")
    reward = random.randint(1000, 3000)
    add_balance(uid, reward)
    data["players"][uid]["last_bonus"] = now; save_data()
    bot.reply_to(message, f"🎁 **ЕЖЕДНЕВНЫЙ БОНУС**\n━━━━━━━━━━━━━━━━━━━━\nВы получили: **{reward} 🪙**\n━━━━━━━━━━━━━━━━━━━━\nПриходите завтра!", parse_mode="Markdown")

# ==================== ДОНАТ И СТАТУСЫ ====================

@bot.message_handler(commands=['donate'])
@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == 'донат')
def donate_menu(message):
    text = "💎 **ПОПОЛНЕНИЕ БАЛАНСА**\n━━━━━━━━━━━━━━━━━━━━\n1 ⭐ = 1000 🪙\n\nВыберите пакет:"
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("25 ⭐ = 25000 🪙", callback_data="donate_pack_25"))
    kb.add(InlineKeyboardButton("50 ⭐ = 50000 🪙", callback_data="donate_pack_50"))
    kb.add(InlineKeyboardButton("100 ⭐ = 100000 🪙", callback_data="donate_pack_100"))
    kb.add(InlineKeyboardButton("✏️ Ввести свою сумму", callback_data="donate_custom"))
    bot.reply_to(message, text, reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("donate_"))
def donate_process(call):
    if call.data == "donate_custom":
        msg = bot.send_message(call.message.chat.id, "✏️ Введите количество звезд (от 1 до 10000):")
        bot.register_next_step_handler(msg, process_custom_stars)
        return
    stars = int(call.data.split("_")[2])
    coins = stars * 1000
    prices = [LabeledPrice(label=f"{coins} монет", amount=stars)]
    try:
        bot.send_invoice(chat_id=call.message.chat.id, title=f"Покупка {coins} монет", description=f"Вы получите {coins} монет на баланс.", invoice_payload=f"pay_{stars}", provider_token="", currency="XTR", prices=prices)
        bot.answer_callback_query(call.id, "✅ Счет выставлен!")
    except Exception as e: bot.answer_callback_query(call.id, f"Ошибка: {e}", show_alert=True)

def process_custom_stars(message):
    try:
        stars = int(message.text)
        if stars < 1 or stars > 10000: return bot.reply_to(message, "❌ От 1 до 10000 звезд.")
        coins = stars * 1000
        prices = [LabeledPrice(label=f"{coins} монет", amount=stars)]
        bot.send_invoice(chat_id=message.chat.id, title=f"Покупка {coins} монет", description=f"Вы получите {coins} монет на баланс.", invoice_payload=f"pay_{stars}", provider_token="", currency="XTR", prices=prices)
    except: bot.reply_to(message, "❌ Введите число.")

@bot.pre_checkout_query_handler(func=lambda query: True)
def process_pre_checkout_query(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def got_payment(message):
    payload = message.successful_payment.invoice_payload
    if payload.startswith("status_"):
        status = payload.split("_")[1]
        uid = str(message.from_user.id)
        if uid not in data["players"]: register_user(message.from_user)
        data["players"][uid]["donate_status"] = status
        save_data()
        bot.send_message(message.chat.id, f"🎉 **ОПЛАТА УСПЕШНА!**\n━━━━━━━━━━━━━━━━━━━━\nВы получили статус **{status}**!", parse_mode="Markdown")
        return

    stars = int(payload.split("_")[1])
    coins = stars * 1000
    uid = str(message.from_user.id)
    if uid not in data["players"]: register_user(message.from_user)
    add_balance(uid, coins)
    
    current_status = data["players"][uid].get("donate_status", "Нет")
    if stars >= 750 and current_status != "Ultra": data["players"][uid]["donate_status"] = "Ultra"; bot.send_message(message.chat.id, f"🎉 **ОПЛАТА УСПЕШНА!**\n━━━━━━━━━━━━━━━━━━━━\nВы получили **{coins} 🪙** и статус **Ultra**!", parse_mode="Markdown")
    elif stars >= 450 and current_status not in ["Premium", "Ultra"]: data["players"][uid]["donate_status"] = "Premium"; bot.send_message(message.chat.id, f"🎉 **ОПЛАТА УСПЕШНА!**\n━━━━━━━━━━━━━━━━━━━━\nВы получили **{coins} 🪙** и статус **Premium**!", parse_mode="Markdown")
    elif stars >= 200 and current_status not in ["VIP", "Premium", "Ultra"]: data["players"][uid]["donate_status"] = "VIP"; bot.send_message(message.chat.id, f"🎉 **ОПЛАТА УСПЕШНА!**\n━━━━━━━━━━━━━━━━━━━━\nВы получили **{coins} 🪙** и статус **VIP**!", parse_mode="Markdown")
    else: bot.send_message(message.chat.id, f"🎉 **ОПЛАТА УСПЕШНА!**\n━━━━━━━━━━━━━━━━━━━━\nВы получили **{coins} 🪙**.", parse_mode="Markdown")
    save_data()

@bot.message_handler(commands=['donate_status'])
@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == 'донат статус')
def donate_status_menu(message):
    text = "💎 **ДОНАТ-СТАТУСЫ**\n━━━━━━━━━━━━━━━━━━━━\n👑 **VIP** (200 ⭐) — +5% к выигрышу\n💎 **Premium** (450 ⭐) — +15% к выигрышу\n⚡ **Ultra** (750 ⭐) — +25% к выигрышу + просмотр профилей"
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("👑 VIP (200 ⭐)", callback_data="buy_status_VIP"))
    kb.add(InlineKeyboardButton("💎 Premium (450 ⭐)", callback_data="buy_status_Premium"))
    kb.add(InlineKeyboardButton("⚡ Ultra (750 ⭐)", callback_data="buy_status_Ultra"))
    bot.reply_to(message, text, reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_status_"))
def buy_status(call):
    status = call.data.split("_")[2]
    stars = {"VIP": 200, "Premium": 450, "Ultra": 750}[status]
    prices = [LabeledPrice(label=f"Статус {status}", amount=stars)]
    try:
        bot.send_invoice(chat_id=call.message.chat.id, title=f"Покупка статуса {status}", description=f"Вы получите статус {status}.", invoice_payload=f"status_{status}", provider_token="", currency="XTR", prices=prices)
        bot.answer_callback_query(call.id, "✅ Счет выставлен!")
    except Exception as e: bot.answer_callback_query(call.id, f"Ошибка: {e}", show_alert=True)

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "мой статус")
def my_status(message):
    uid = str(message.from_user.id)
    status = data["players"].get(uid, {}).get("donate_status", "Нет")
    bot.reply_to(message, f"💎 **ВАШ СТАТУС**\n━━━━━━━━━━━━━━━━━━━━\nТекущий статус: **{status}**", parse_mode="Markdown")

# ==================== БАЗОВЫЕ КОМАНДЫ ====================

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == 'б')
def balance_command(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]: register_user(message.from_user)
    bot.reply_to(message, f"💰 **БАЛАНС**\n━━━━━━━━━━━━━━━━━━━━\nВаш баланс: **{get_balance(uid)} 🪙**", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() in ['узнать ид', 'мой ид', 'мой id'])
def get_id_command(message):
    uid = str(message.from_user.id)
    target_uid = uid
    if message.reply_to_message:
        target_uid = str(message.reply_to_message.from_user.id)
        caller_status = data["players"].get(uid, {}).get("donate_status", "Нет")
        if uid not in [str(a) for a in ADMIN_IDS] and caller_status != "Ultra":
            return bot.reply_to(message, "❌ **ДОСТУП ЗАПРЕЩЕН**\nСмотреть чужой ID могут только админы и Ultra.", parse_mode="Markdown")
    if target_uid not in data["players"]: register_user_by_id(target_uid)
    sid = get_user_short_id(target_uid)
    bot.reply_to(message, f"🆔 **ID ИГРОКА**\n━━━━━━━━━━━━━━━━━━━━\n`{sid}`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("сменить ник"))
def change_nick(message):
    uid = str(message.from_user.id)
    try:
        new_nick = message.text[12:].strip()
        if len(new_nick) < 3 or len(new_nick) > 15: return bot.reply_to(message, "❌ Ник от 3 до 15 символов.")
        data["players"][uid]["username"] = new_nick
        save_data()
        bot.reply_to(message, f"✅ **НИК ИЗМЕНЕН**\n━━━━━━━━━━━━━━━━━━━━\nНовый ник: **{new_nick}**", parse_mode="Markdown")
    except: bot.reply_to(message, "❌ `сменить ник НОВЫЙ_НИК`")

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == 'профиль')
def profile_command(message):
    uid = str(message.from_user.id)
    target_uid = uid
    if message.reply_to_message:
        target_uid = str(message.reply_to_message.from_user.id)
        caller_status = data["players"].get(uid, {}).get("donate_status", "Нет")
        if uid not in [str(a) for a in ADMIN_IDS] and caller_status != "Ultra":
            return bot.reply_to(message, "❌ **ДОСТУП ЗАПРЕЩЕН**\nСмотреть чужой профиль могут только админы и Ultra.", parse_mode="Markdown")
    if target_uid not in data["players"]: register_user_by_id(target_uid)
    p = data["players"][target_uid]
    clan_name = "Нет"
    if p.get("clan_id"):
        clan = data["clans"].get(str(p["clan_id"]))
        if clan: clan_name = clan.get("name", "Нет")
    text = (f"👤 **ПРОФИЛЬ ИГРОКА**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 ID: `{p.get('short_id', '?')}`\n"
            f"👤 Ник: {p.get('username', '?')}\n"
            f"💎 Статус: {p.get('donate_status', 'Нет')}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 Баланс: {p.get('balance', 0)} 🪙\n"
            f"🏦 Банк: {p.get('bank', 0)} 🪙\n"
            f"💎 Депозит: {p.get('deposit', 0)} 🪙\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🛡 Клан: {clan_name}\n"
            f"🏢 Бизнес: {p.get('biz_territory', 0)} м²")
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() in ["топ", "топ игроков"])
def top_cmd(message):
    sp = sorted(data["players"].items(), key=lambda x: x[1].get("balance", 0), reverse=True)[:10]
    text = "🏆 **ТОП-10 ИГРОКОВ**\n━━━━━━━━━━━━━━━━━━━━\n" + "".join([f"{i}. {p.get('username', '?')} — {p.get('balance', 0)} 🪙\n" for i, (u, p) in enumerate(sp, 1)])
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "чаты")
def chats_cmd(message):
    bot.reply_to(message, "💬 **НАШИ ЧАТЫ**\n━━━━━━━━━━━━━━━━━━━━\n📢 Канал: https://t.me/mon1bots\n💬 Чат: https://t.me/mon1not", parse_mode="Markdown")

# ==================== АДМИН-ПАНЕЛЬ ====================

@bot.message_handler(commands=['admin'])
@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() in ['админ', 'админка'])
def admin_panel(message):
    if message.from_user.id not in ADMIN_IDS: return
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("📊 Статистика", callback_data="adm_stats"), InlineKeyboardButton("💰 Выдать деньги", callback_data="adm_give"))
    kb.add(InlineKeyboardButton("👑 Выдать статус", callback_data="adm_setstatus"), InlineKeyboardButton("🗑 Удалить игрока", callback_data="adm_reset"))
    kb.add(InlineKeyboardButton("🎁 Создать промо", callback_data="adm_promo"), InlineKeyboardButton("❌ Удалить промо", callback_data="adm_delpromo"))
    kb.add(InlineKeyboardButton("📢 Рассылка", callback_data="adm_broadcast"))
    bot.reply_to(message, "⚙️ **АДМИН-ПАНЕЛЬ**\n━━━━━━━━━━━━━━━━━━━━\nВыберите действие:", reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_"))
def admin_callbacks(call):
    if call.from_user.id not in ADMIN_IDS: return bot.answer_callback_query(call.id, "❌ Нет прав.")
    act = call.data.split("_")[1]
    if act == "stats":
        total_players = len(data["players"])
        total_money = sum(p.get("balance", 0) for p in data["players"].values())
        total_clans = len(data["clans"])
        text = f"📊 **СТАТИСТИКА**\n━━━━━━━━━━━━━━━━━━━━\n👥 Игроков: {total_players}\n💰 Общий баланс: {total_money} 🪙\n🛡 Кланов: {total_clans}"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("⬅️ Назад", callback_data="adm_back")), parse_mode="Markdown")
    elif act == "give":
        msg = bot.send_message(call.message.chat.id, "Введите `ID СУММА` (например: `3 5000`):")
        bot.register_next_step_handler(msg, admin_give_step)
        bot.answer_callback_query(call.id)
    elif act == "setstatus":
        msg = bot.send_message(call.message.chat.id, "Введите `ID СТАТУС` (например: `3 Ultra`).\nДоступные статусы: `VIP`, `Premium`, `Ultra`, `Нет`:")
        bot.register_next_step_handler(msg, admin_setstatus_step)
        bot.answer_callback_query(call.id)
    elif act == "reset":
        msg = bot.send_message(call.message.chat.id, "Введите `ID` игрока для сброса баланса (например: `3`):")
        bot.register_next_step_handler(msg, admin_reset_step)
        bot.answer_callback_query(call.id)
    elif act == "promo":
        msg = bot.send_message(call.message.chat.id, "Введите `КОД СУММА` (например: `NEWYEAR 1000`):")
        bot.register_next_step_handler(msg, admin_promo_step)
        bot.answer_callback_query(call.id)
    elif act == "delpromo":
        msg = bot.send_message(call.message.chat.id, "Введите `КОД` промокода для удаления:")
        bot.register_next_step_handler(msg, admin_delpromo_step)
        bot.answer_callback_query(call.id)
    elif act == "broadcast":
        msg = bot.send_message(call.message.chat.id, "Введите текст для рассылки всем игрокам:")
        bot.register_next_step_handler(msg, admin_broadcast_step)
        bot.answer_callback_query(call.id)
    elif act == "back":
        admin_panel(call.message)

def admin_give_step(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        sid, amount = message.text.split(); amount = int(amount)
        target_uid = get_user_by_short_id(sid)
        if not target_uid: return bot.reply_to(message, "❌ Игрок не найден.")
        add_balance(target_uid, amount)
        bot.reply_to(message, f"✅ Выдано {amount} 🪙 игроку с ID {sid}.")
    except: bot.reply_to(message, "❌ Ошибка формата.")

def admin_setstatus_step(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        sid, status = message.text.split()
        status = status.capitalize()
        if status not in ["VIP", "Premium", "Ultra", "Нет"]:
            return bot.reply_to(message, "❌ Неверный статус. Доступно: VIP, Premium, Ultra, Нет.")
        target_uid = get_user_by_short_id(sid)
        if not target_uid: return bot.reply_to(message, "❌ Игрок не найден.")
        data["players"][target_uid]["donate_status"] = status
        save_data()
        bot.reply_to(message, f"✅ Игроку с ID {sid} выдан статус **{status}**.", parse_mode="Markdown")
    except: bot.reply_to(message, "❌ Ошибка формата. Введите `ID Статус`")

def admin_reset_step(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        sid = message.text.strip()
        target_uid = get_user_by_short_id(sid)
        if not target_uid: return bot.reply_to(message, "❌ Игрок не найден.")
        # ОБНУЛЯЕМ ТОЛЬКО БАЛАНС И БАНК, НЕ УДАЛЯЕМ ИГРОКА
        data["players"][target_uid]["balance"] = 0
        data["players"][target_uid]["bank"] = 0
        data["players"][target_uid]["deposit"] = 0
        data["players"][target_uid]["deposit_start"] = 0
        save_data()
        bot.reply_to(message, f"✅ Баланс и банк игрока с ID {sid} обнулены.")
    except: bot.reply_to(message, "❌ Ошибка.")

def admin_promo_step(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        code, amount = message.text.upper().split(); amount = int(amount)
        data["promos"][code] = amount; save_data()
        bot.reply_to(message, f"✅ Промокод {code} на {amount} 🪙 создан.")
    except: bot.reply_to(message, "❌ Ошибка формата.")

def admin_delpromo_step(message):
    if message.from_user.id not in ADMIN_IDS: return
    code = message.text.upper().strip()
    if code in data["promos"]: del data["promos"][code]; save_data(); bot.reply_to(message, f"✅ Промокод {code} удален.")
    else: bot.reply_to(message, "❌ Не найден.")

def admin_broadcast_step(message):
    if message.from_user.id not in ADMIN_IDS: return
    text = message.text
    success = 0
    for uid in list(data["players"].keys()):
        try: bot.send_message(uid, text); success += 1
        except: pass
    bot.reply_to(message, f"✅ Рассылка отправлена {success} игрокам.")

# ==================== СТАРЫЕ АДМИН-КОМАНДЫ ====================

@bot.message_handler(commands=['wipe'])
def wipe_command(message):
    if message.from_user.id not in ADMIN_IDS: return
    global data
    data = {"players": {}, "promos": {}, "activations": [], "history": [], "clans": {}, "next_id": 1, "active_games": {}, "roulette_bets": {}}
    save_data()
    bot.reply_to(message, "💥 **База данных очищена!**", parse_mode="Markdown")

@bot.message_handler(commands=['give'])
def give_command(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        parts = message.text.split(); target_sid = parts[1]; amount = int(parts[2])
        target_uid = get_user_by_short_id(target_sid)
        if not target_uid: return bot.reply_to(message, f"❌ Игрок {target_s
