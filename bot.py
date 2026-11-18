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
    kb.add(InlineKeyboardButton("👑 Выдать статус", callback_data="adm_setstatus"), InlineKeyboardButton("🗑 Обнулить игрока", callback_data="adm_reset"))
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
        msg = bot.send_message(call.message.chat.id, "Введите `ID` игрока для обнуления баланса (например: `3`):")
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
        if not target_uid: return bot.reply_to(message, f"❌ Игрок {target_sid} не найден.")
        add_balance(target_uid, amount)
        bot.reply_to(message, f"✅ Выдано {amount} 🪙 игроку {get_nick(target_uid)}.", parse_mode="Markdown")
    except: bot.reply_to(message, "❌ `/give ID СУММА`", parse_mode="Markdown")

@bot.message_handler(commands=['reset'])
def reset_user_command(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        target_sid = message.text.split()[1]; target_uid = get_user_by_short_id(target_sid)
        if not target_uid: return bot.reply_to(message, f"❌ Игрок {target_sid} не найден.")
        data["players"][target_uid]["balance"] = 0
        data["players"][target_uid]["bank"] = 0
        data["players"][target_uid]["deposit"] = 0
        data["players"][target_uid]["deposit_start"] = 0
        save_data()
        bot.reply_to(message, f"✅ Баланс игрока {target_sid} обнулен.")
    except: bot.reply_to(message, "❌ `/reset ID`", parse_mode="Markdown")

@bot.message_handler(commands=['get_profile'])
def get_profile_command(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        target_sid = message.text.split()[1]; target_uid = get_user_by_short_id(target_sid)
        if not target_uid: return bot.reply_to(message, f"❌ Игрок {target_sid} не найден.")
        p = data["players"][target_uid]
        bot.reply_to(message, f"👤 **Профиль (Админ)**\n🆔 ID: `{p.get('short_id')}`\nНик: {p.get('username')}\nСтатус: {p.get('donate_status')}\nБаланс: {p.get('balance')} 🪙", parse_mode="Markdown")
    except: bot.reply_to(message, "❌ `/get_profile ID`", parse_mode="Markdown")

# ==================== ПРОМОКОДЫ ====================

@bot.message_handler(commands=['createpromo'])
def create_promo(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        parts = message.text.split(); code = parts[1].upper(); amount = int(parts[2])
        if code in data["promos"]: return bot.reply_to(message, "❌ Такой промокод уже существует.")
        data["promos"][code] = amount; save_data()
        bot.reply_to(message, f"✅ Промокод **{code}** на {amount} 🪙 создан!", parse_mode="Markdown")
    except: bot.reply_to(message, "❌ `/createpromo КОД СУММА`", parse_mode="Markdown")

@bot.message_handler(commands=['deletepromo'])
def delete_promo(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        code = message.text.split()[1].upper()
        if code in data["promos"]:
            del data["promos"][code]; save_data()
            bot.reply_to(message, f"✅ Промокод **{code}** удален.", parse_mode="Markdown")
        else: bot.reply_to(message, "❌ Такого промокода нет.")
    except: bot.reply_to(message, "❌ `/deletepromo КОД`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("промо"))
def activate_promo(message):
    uid = str(message.from_user.id)
    try:
        code = message.text.split()[1].upper()
        if code not in data["promos"]: return bot.reply_to(message, "❌ Неверный или несуществующий промокод.")
        activation_key = f"{uid}_{code}"
        if activation_key in data["activations"]: return bot.reply_to(message, "❌ Вы уже активировали этот промокод.")
        amount = data["promos"][code]
        add_balance(uid, amount)
        data["activations"].append(activation_key); save_data()
        bot.reply_to(message, f"🎉 Промокод **{code}** активирован! Вы получили {amount} 🪙.", parse_mode="Markdown")
    except: bot.reply_to(message, "❌ Использование: `промо КОД`")

# ==================== КЛАНЫ ====================

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("создать клан"))
def create_clan(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]: register_user(message.from_user)
    p = data["players"][uid]
    if p.get("clan_id"): return bot.reply_to(message, "❌ Вы уже состоите в клане.")
    cost = 10000
    if get_balance(uid) < cost: return bot.reply_to(message, f"❌ Недостаточно средств. Нужно {cost} 🪙.")
    try:
        clan_name = message.text[12:].strip()
        if len(clan_name) < 3 or len(clan_name) > 20: return bot.reply_to(message, "❌ Название от 3 до 20 символов.")
    except: return bot.reply_to(message, "❌ `создать клан НАЗВАНИЕ`")
    for c in data["clans"].values():
        if c.get("name", "").lower() == clan_name.lower(): return bot.reply_to(message, "❌ Клан с таким названием уже есть.")
    add_balance(uid, -cost)
    clan_id = str(len(data["clans"]) + 1)
    while clan_id in data["clans"]: clan_id = str(int(clan_id) + 1)
    data["clans"][clan_id] = {"name": clan_name, "owner_id": uid, "owner_name": p.get("username", "?"), "treasury": 0, "members": [uid]}
    p["clan_id"] = clan_id; p["role"] = "создатель"; save_data()
    bot.reply_to(message, f"✅ Клан **{clan_name}** создан!\n🆔 ID клана: `{clan_id}`\n👑 Вы — создатель.\n💰 Списано: {cost} 🪙", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("вступить клан"))
def join_clan(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]: register_user(message.from_user)
    p = data["players"][uid]
    if p.get("clan_id"): return bot.reply_to(message, "❌ Вы уже в клане.")
    try: clan_id = message.text.split()[2]
    except: return bot.reply_to(message, "❌ `вступить клан ID`")
    clan = data["clans"].get(clan_id)
    if not clan: return bot.reply_to(message, "❌ Клан не найден.")
    members = [m for m in data["players"].values() if m.get("clan_id") == clan_id]
    if len(members) >= 15: return bot.reply_to(message, "❌ Клан переполнен (макс 15).")
    p["clan_id"] = clan_id; p["role"] = "игрок"; save_data()
    bot.reply_to(message, f"✅ Вы вступили в клан **{clan['name']}**!", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "выйти из клана")
def leave_clan(message):
    uid = str(message.from_user.id); p = data["players"].get(uid, {})
    if not p.get("clan_id"): return bot.reply_to(message, "❌ Вы не в клане.")
    if p.get("role") == "создатель": return bot.reply_to(message, "❌ Создатель не может выйти.")
    p["clan_id"] = None; p["role"] = "none"; save_data()
    bot.reply_to(message, "✅ Вы вышли из клана.")

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "мой клан")
def my_clan_info(message):
    uid = str(message.from_user.id); p = data["players"].get(uid, {})
    if not p.get("clan_id"): return bot.reply_to(message, "🛡 У вас нет клана.\n`создать клан ИМЯ` (10000)\n`вступить клан ID`", parse_mode="Markdown")
    cid = str(p["clan_id"]); clan = data["clans"].get(cid)
    if not clan: return bot.reply_to(message, "❌ Клан удален.")
    members = [m for m in data["players"].values() if m.get("clan_id") == cid]
    text = f"🛡 **Клан: {clan['name']}**\n🆔 ID: `{cid}`\n👑 Создатель: {clan['owner_name']}\n👥 Участники: {len(members)}/15\n💰 Казна: {clan.get('treasury', 0)} 🪙\n\nВаша роль: **{p.get('role', 'игрок').upper()}**"
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("👥 Участники", callback_data=f"clan_members_{cid}"))
    bot.reply_to(message, text, reply_markup=kb, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "топ кланов")
def top_clans(message):
    clans = sorted(data["clans"].items(), key=lambda x: x[1].get("treasury", 0), reverse=True)[:10]
    if not clans: return bot.reply_to(message, "❌ Нет кланов.")
    text = "🏆 **ТОП КЛАНОВ**\n━━━━━━━━━━━━━━━━━━━━\n" + "".join([f"{i}. {c.get('name')} — {c.get('treasury', 0)} 🪙\n" for i, (cid, c) in enumerate(clans, 1)])
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("клан казна"))
def clan_treasury(message):
    uid = str(message.from_user.id); p = data["players"].get(uid, {})
    if not p.get("clan_id"): return bot.reply_to(message, "❌ Вы не в клане.")
    cid = str(p["clan_id"]); clan = data["clans"].get(cid)
    if not clan: return bot.reply_to(message, "❌ Клан не найден.")
    try:
        parts = message.text.split(); action = parts[2].lower(); amount = int(parts[3])
        if amount <= 0: return bot.reply_to(message, "❌ Сумма > 0.")
        if action == "снять":
            if p.get("role") != "создатель": return bot.reply_to(message, "❌ Только создатель может снимать.")
            if clan.get("treasury", 0) < amount: return bot.reply_to(message, "❌ В казне мало денег.")
            clan["treasury"] -= amount; add_balance(uid, amount); save_data()
            bot.reply_to(message, f"✅ Вы сняли {amount} 🪙 из казны.")
        else:
            if get_balance(uid) < amount: return bot.reply_to(message, "❌ Недостаточно средств.")
            add_balance(uid, -amount); clan["treasury"] = clan.get("treasury", 0) + amount; save_data()
            bot.reply_to(message, f"✅ Вы положили {amount} 🪙 в казну.")
    except: bot.reply_to(message, "❌ `клан казна положить 1000`\n`клан казна снять 1000`", parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("clan_members_"))
def clan_members(call):
    cid = call.data.split("_")[2]; clan = data["clans"].get(cid)
    if not clan: return bot.answer_callback_query(call.id, "❌ Клан не найден.")
    members = [(m.get('username', '?'), m.get('short_id', '?'), m.get('role', 'игрок')) for m in data["players"].values() if m.get("clan_id") == cid]
    text = f"👥 **Участники клана {clan['name']}**\n\n"
    for name, sid, role in members: text += f"• {name} (ID: `{sid}`) — {role}\n"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("⬅️ Назад", callback_data=f"clan_back_{cid}")), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("clan_back_"))
def clan_back(call):
    uid = str(call.from_user.id); p = data["players"].get(uid, {}); cid = str(p.get("clan_id"))
    if not cid: return
    clan = data["clans"].get(cid)
    if not clan: return
    members = [m for m in data["players"].values() if m.get("clan_id") == cid]
    text = f"🛡 **Клан: {clan['name']}**\n🆔 ID: `{cid}`\n👑 Создатель: {clan['owner_name']}\n👥 Участники: {len(members)}/15\n💰 Казна: {clan.get('treasury', 0)} 🪙\n\nВаша роль: **{p.get('role', 'игрок').upper()}**"
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("👥 Участники", callback_data=f"clan_members_{cid}"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode="Markdown")

def has_perm(uid, act):
    role = data["players"][uid].get("role", "none")
    if role == "создатель": return True
    if role == "заместитель" and act in ["rename", "appoint", "kick"]: return True
    if role == "модер" and act == "rename": return True
    return False

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("клан исключить"))
def clan_kick(message):
    uid = str(message.from_user.id)
    if not has_perm(uid, "kick"): return bot.reply_to(message, "❌ Нет прав.")
    try:
        target_sid = message.text.split()[2]; target_uid = get_user_by_short_id(target_sid)
        if not target_uid: return bot.reply_to(message, "❌ Игрок не найден.")
        cid = data["players"][uid].get("clan_id")
        if data["players"].get(target_uid, {}).get("clan_id") != cid: return bot.reply_to(message, "❌ Не в вашем клане.")
        if data["players"].get(target_uid, {}).get("role") == "создатель": return bot.reply_to(message, "❌ Нельзя исключить создателя.")
        data["players"][target_uid]["clan_id"] = None; data["players"][target_uid]["role"] = "none"; save_data()
        bot.reply_to(message, f"✅ Игрок `{target_sid}` исключен.")
    except: bot.reply_to(message, "❌ `клан исключить ID`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("клан повысить"))
def clan_promote(message):
    uid = str(message.from_user.id)
    if not has_perm(uid, "appoint"): return bot.reply_to(message, "❌ Нет прав.")
    try:
        target_sid = message.text.split()[2]; target_uid = get_user_by_short_id(target_sid)
        if not target_uid: return bot.reply_to(message, "❌ Игрок не найден.")
        cid = data["players"][uid].get("clan_id")
        if data["players"].get(target_uid, {}).get("clan_id") != cid: return bot.reply_to(message, "❌ Не в вашем клане.")
        current_role = data["players"][target_uid].get("role", "игрок")
        if current_role == "создатель": return bot.reply_to(message, "❌ Это создатель.")
        elif current_role == "заместитель": return bot.reply_to(message, "❌ Уже заместитель.")
        elif current_role == "модер": data["players"][target_uid]["role"] = "заместитель"; new_role = "заместитель"
        else: data["players"][target_uid]["role"] = "модер"; new_role = "модер"
        save_data()
        bot.reply_to(message, f"✅ Игрок `{target_sid}` повышен до **{new_role}**.", parse_mode="Markdown")
    except: bot.reply_to(message, "❌ `клан повысить ID`", parse_mode="Markdown")

# ==================== ИГРЫ ====================

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("слот"))
def slot_machine(message):
    uid = str(message.from_user.id)
    try:
        bet = int(message.text.split()[1])
        if bet <= 0 or get_balance(uid) < bet: return bot.reply_to(message, "❌ Недостаточно средств.")
        add_balance(uid, -bet)
        s = [random.choice(["🍒", "🍋", "💎", "🎰"]) for _ in range(3)]
        win = 0
        if s[0] == s[1] == s[2]:
            if s[0] == "🎰": win = bet * 50
            elif s[0] == "💎": win = bet * 10
            elif s[0] == "🍋": win = bet * 5
            elif s[0] == "🍒": win = bet * 3
        elif s[0] == s[1] or s[1] == s[2] or s[0] == s[2]: win = bet
        
        if win > 0:
            win = int(win * get_win_multiplier(uid))
            add_balance(uid, win)
            msg = f"🎰 **СЛОТ**\n[ {s[0]} | {s[1]} | {s[2]} ]\n🎉 **ВЫИГРЫШ!** +{win} 🪙\nБаланс: {get_balance(uid)}"
        else:
            msg = f"🎰 **СЛОТ**\n[ {s[0]} | {s[1]} | {s[2]} ]\n😢 Проигрыш.\nБаланс: {get_balance(uid)}"
        bot.reply_to(message, msg, parse_mode="Markdown")
        complete_quest(uid, "Сделать ставку в слот")
    except: bot.reply_to(message, "❌ `слот 1000`")

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("мины"))
def start_mines(message):
    uid = str(message.from_user.id)
    try:
        p = message.text.split(); bet = int(p[1]); bmb = int(p[2]) if len(p) > 2 else 5
        if bet <= 0 or get_balance(uid) < bet: return bot.reply_to(message, "❌ Мало.")
        if bmb not in MULT: return bot.reply_to(message, "❌ Мины: 3, 5 или 9.")
        add_balance(uid, -bet); gid = str(random.randint(10000, 99999))
        data["active_games"][gid] = {"type": "mines", "user": uid, "bet": bet, "mines": random.sample(range(25), bmb), "opened": [], "bombs": bmb}; save_data()
        bot.reply_to(message, f"💣 **МИНЫ** #{gid}\nСтавка: {bet} 🪙\nМин: {bmb}", reply_markup=mines_kb(gid), parse_mode="Markdown")
    except: bot.reply_to(message, "❌ `мины 1000 5`")

def mines_kb(gid):
    g = data["active_games"].get(gid)
    if not g: return None
    kb = InlineKeyboardMarkup(row_width=5)
    for r in range(5): kb.row(*[InlineKeyboardButton("💎" if (r*5+c) in g["opened"] else "❔", callback_data=f"m_{gid}_{r*5+c}") for c in range(5)])
    kb.row(InlineKeyboardButton("⭐ ЗАБРАТЬ", callback_data=f"mcash_{gid}"))
    return kb

@bot.callback_query_handler(func=lambda call: call.data.startswith("m_"))
def mines_play(call):
    _, gid, c = call.data.split("_"); c = int(c); uid = str(call.from_user.id); g = data["active_games"].get(gid)
    if not g or g["user"] != uid or c in g["opened"]: return bot.answer_callback_query(call.id, "❌ Ошибка.")
    if c in g["mines"]:
        del data["active_games"][gid]; save_data()
        kb = InlineKeyboardMarkup(row_width=5)
        for r in range(5): kb.row(*[InlineKeyboardButton("💣" if (r*5+x) in g["mines"] else "💎", callback_data="ignore") for x in range(5)])
        bot.edit_message_text(f"💥 **МИНА!** Потеряно {g['bet']} 🪙.", call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode="Markdown"); return
    g["opened"].append(c); mult = MULT[g["bombs"]] ** len(g["opened"]); rw = math.floor(g["bet"] * mult); save_data()
    bot.edit_message_text(f"💣 **МИНЫ**\nСтавка: {g['bet']} 🪙\nОткрыто: {len(g['opened'])}\nМнож: x{mult:.2f}\nЗабрать: {rw} 🪙", call.message.chat.id, call.message.message_id, reply_markup=mines_kb(gid), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("mcash_"))
def mines_out(call):
    gid = call.data.split("_")[1]; uid = str(call.from_user.id); g = data["active_games"].get(gid)
    if not g or g["user"] != uid or not g["opened"]: return
    rw = math.floor(g["bet"] * (MULT[g["bombs"]] ** len(g["opened"])))
    rw = int(rw * get_win_multiplier(uid))
    add_balance(uid, rw); del data["active_games"][gid]; save_data()
    bot.edit_message_text(f"🏆 **Забрано!** +{rw} 🪙", call.message.chat.id, call.message.message_id, reply_markup=None, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("краш"))
def start_crash(message):
    uid = str(message.from_user.id)
    try:
        bet = int(message.text.split()[1])
        if bet <= 0 or get_balance(uid) < bet: return bot.reply_to(message, "❌ Мало.")
        add_balance(uid, -bet); gid = str(random.randint(10000, 99999))
        data["active_games"][gid] = {"type": "crash", "user": uid, "bet": bet, "crash_point": round(random.uniform(1.1, 10.0), 2), "current": 1.0, "active": True}; save_data()
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("💰 ЗАБРАТЬ", callback_data=f"ccash_{gid}"))
        msg = bot.reply_to(message, f"🚀 **CRASH**\nСтавка: {bet}\nКоэф: x1.00", reply_markup=kb)
        threading.Thread(target=crash_loop, args=(gid, uid, msg.chat.id, msg.message_id)).start()
    except: bot.reply_to(message, "❌ `краш 1000`")

def crash_loop(gid, uid, cid, mid):
    time.sleep(1)
    while True:
        g = data["active_games"].get(gid)
        if not g or not g["active"]: break
        g["current"] = round(g["current"] + 0.10, 2); save_data()
        if g["current"] >= g["crash_point"] or random.random() < 0.06:
            g["active"] = False; save_data()
            try: bot.edit_message_text(f"💥 **КРАШ на x{g['current']:.2f}!**\nПотеряно {g['bet']} 🪙.", cid, mid, reply_markup=None, parse_mode="Markdown")
            except: pass
            del data["active_games"][gid]; save_data(); break
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("💰 ЗАБРАТЬ", callback_data=f"ccash_{gid}"))
        try: bot.edit_message_text(f"🚀 **CRASH**\nСтавка: {g['bet']}\nКоэф: x{g['current']:.2f}", cid, mid, reply_markup=kb, parse_mode="Markdown")
        except: pass
        time.sleep(1)

@bot.callback_query_handler(func=lambda call: call.data.startswith("ccash_"))
def crash_out(call):
    gid = call.data.split("_")[1]; uid = str(call.from_user.id); g = data["active_games"].get(gid)
    if not g or g["user"] != uid or not g["active"]: return
    g["active"] = False
    rw = math.floor(g["bet"] * g["current"])
    rw = int(rw * get_win_multiplier(uid))
    add_balance(uid, rw); del data["active_games"][gid]; save_data()
    bot.edit_message_text(f"🏆 **Забрано на x{g['current']:.2f}!** +{rw} 🪙", call.message.chat.id, call.message.message_id, reply_markup=None, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("джокер"))
def start_joker(message):
    uid = str(message.from_user.id)
    try:
        bet = int(message.text.split()[1])
        if bet <= 0 or get_balance(uid) < bet: return bot.reply_to(message, "❌ Недостаточно средств.")
        add_balance(uid, -bet); gid = str(random.randint(10000, 99999))
        data["active_games"][gid] = {"type": "joker", "user": uid, "bet": bet, "step": 0, "mult": 1.0, "active": True}
        save_data()
        show_joker_menu(message.chat.id, gid, uid, None)
    except: bot.reply_to(message, "❌ `джокер 1000`")

def show_joker_menu(cid, gid, uid, msg_id):
    g = data["active_games"].get(gid)
    if not g: return
    mult = g["mult"]
    text = f"🃏 **ДЖОКЕР**\nСтавка: {g['bet']} 🪙\nШаг: {g['step']} / 12\nТекущий множитель: x{mult:.2f}\nЗабрать: {math.floor(g['bet'] * mult)} 🪙\n\nВыберите ячейку:"
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(InlineKeyboardButton("🎴 1", callback_data=f"j_{gid}_0"), InlineKeyboardButton("🎴 2", callback_data=f"j_{gid}_1"), InlineKeyboardButton("🎴 3", callback_data=f"j_{gid}_2"))
    if g["step"] > 0: kb.row(InlineKeyboardButton("💰 ЗАБРАТЬ", callback_data=f"jcash_{gid}"))
    if msg_id: bot.edit_message_text(text, cid, msg_id, reply_markup=kb, parse_mode="Markdown")
    else: bot.send_message(cid, text, reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("j_"))
def joker_play(call):
    _, gid, choice = call.data.split("_"); uid = str(call.from_user.id); g = data["active_games"].get(gid)
    if not g or g["user"] != uid or not g["active"]: return bot.answer_callback_query(call.id, "❌ Ошибка.")
    if g["step"] >= 12: return bot.answer_callback_query(call.id, "❌ Максимум!")
    
    lose_idx = random.randint(0, 2)
    if int(choice) == lose_idx:
        g["active"] = False
        bot.edit_message_text(f"🃏 **ПРОИГРЫШ!**\nВы попали в проигрышную ячейку.\nПотеряно: {g['bet']} 🪙", call.message.chat.id, call.message.message_id, reply_markup=None, parse_mode="Markdown")
        del data["active_games"][gid]; save_data(); return
    
    g["step"] += 1
    mult_table = [1.2, 1.4, 1.6, 1.9, 2.2, 2.5, 2.9, 3.3, 3.8, 4.2, 4.6, 5.0]
    g["mult"] = mult_table[g["step"] - 1]
    save_data()
    
    if g["step"] >= 12:
        rw = math.floor(g["bet"] * g["mult"])
        add_balance(uid, rw); g["active"] = False
        bot.edit_message_text(f"🏆 **ДЖОКЕР ПРОЙДЕН!**\nМаксимальный множитель x{g['mult']:.2f}!\nВыигрыш: {rw} 🪙", call.message.chat.id, call.message.message_id, reply_markup=None, parse_mode="Markdown")
        del data["active_games"][gid]; save_data(); return
    
    bot.answer_callback_query(call.id, f"✅ Шаг {g['step']}! Множитель x{g['mult']:.2f}")
    show_joker_menu(call.message.chat.id, gid, uid, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("jcash_"))
def joker_cash(call):
    gid = call.data.split("_")[1]; uid = str(call.from_user.id); g = data["active_games"].get(gid)
    if not g or g["user"] != uid or not g["active"]: return
    rw = math.floor(g["bet"] * g["mult"])
    add_balance(uid, rw); g["active"] = False
    bot.edit_message_text(f"🏆 **Забрано!** +{rw} 🪙", call.message.chat.id, call.message.message_id, reply_markup=None, parse_mode="Markdown")
    del data["active_games"][gid]; save_data()

@bot.message_handler(func=lambda m: m.text and len(m.text.split()) >= 2 and m.text.split()[0].isdigit())
def roulette_bet(message):
    uid = str(message.from_user.id); parts = message.text.split()
    try: bet = int(parts[0])
    except: return
    targets = parts[1:]
    valid_targets = []
    for t in targets:
        t_clean = t.lower().strip()
        if t_clean in ["red", "к", "кр", "красное", "black", "ч", "черное", "green", "з", "зеленое", "even", "чет", "odd", "нечет"]:
            valid_targets.append(t_clean)
        elif t_clean.isdigit():
            num = int(t_clean)
            if 0 <= num <= 36: valid_targets.append(str(num))
            else: return
        elif "-" in t_clean:
            try:
                s, e = map(int, t_clean.split("-"))
                if 0 <= s <= 36 and 0 <= e <= 36 and s <= e: valid_targets.append(t_clean)
                else: return
            except: return
        else: return
    if not valid_targets: return
    if bet <= 0 or get_balance(uid) < bet * len(valid_targets): return bot.reply_to(message, f"❌ Недостаточно средств (нужно {bet * len(valid_targets)} 🪙).")
    if "bets" not in data["roulette_bets"]: data["roulette_bets"] = {}
    if str(message.chat.id) not in data["roulette_bets"]: data["roulette_bets"][str(message.chat.id)] = []
    data["roulette_bets"][str(message.chat.id)].append({"user": uid, "bet": bet, "targets": valid_targets})
    add_balance(uid, -bet * len(valid_targets)); save_data()
    bot.reply_to(message, f"✅ Ставка {bet} на {', '.join(valid_targets)} принята!\nНапишите `го` для запуска.")

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "го")
def roulette_go(message):
    chat_id = str(message.chat.id)
    if chat_id not in data["roulette_bets"] or not data["roulette_bets"][chat_id]: return bot.reply_to(message, "❌ Нет ставок.")
    bets = data["roulette_bets"][chat_id]; data["roulette_bets"][chat_id] = []; save_data()
    win_num = random.randint(0, 36)
    wc = "green" if win_num == 0 else ("red" if 1 <= win_num <= 18 else "black")
    sym = {"green": "🟢", "red": "🔴", "black": "⚫️"}[wc]
    total_win = 0; results = []
    for b in bets:
        u_win = 0
        for x in b["targets"]:
            win, mlt = False, 0
            if "-" in x:
                try: s, e = map(int, x.split("-")); mlt = max(1, math.floor(37 / (e - s + 1))) if s <= win_num <= e else 0
                except: pass
            elif x.isdigit():
                if int(x) == win_num: win, mlt = True, 36
            elif x in ["red", "к", "кр", "красное"]:
                if wc == "red": win, mlt = True, 2
            elif x in ["black", "ч", "черное"]:
                if wc == "black": win, mlt = True, 2
            elif x in ["green", "з", "зеленое"]:
                if wc == "green": win, mlt = True, 36
            elif x in ["even", "чет"]:
                if win_num != 0 and win_num % 2 == 0: win, mlt = True, 2
            elif x in ["odd", "нечет"]:
                if win_num % 2 != 0: win, mlt = True, 2
            if win: u_win += b["bet"] * mlt
        if u_win > 0: 
            u_win = int(u_win * get_win_multiplier(b["user"])); add_balance(b["user"], u_win); results.append(f"✅ {get_nick(b['user'])} +{u_win}")
        else: results.append(f"❌ {get_nick(b['user'])} -{b['bet'] * len(b['targets'])}")
        total_win += u_win
    res_text = "\n".join(results)
    bot.reply_to(message, f"🎰 Выпало: {sym} **{win_num}**\n\n{res_text}\n\n💰 Общий выигрыш: {total_win} 🪙", parse_mode="Markdown")

# ==================== БИЗНЕС, БАНК, КВЕСТЫ ====================

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "мой бизнес")
def my_business(message):
    uid = str(message.from_user.id); p = data["players"].get(uid, {}); t = p.get("biz_territory", 0)
    if t == 0:
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🏗 Построить бизнес", callback_data="biz_build"))
        return bot.reply_to(message, f"🏢 У вас нет бизнеса.\nНажмите кнопку ниже, чтобы купить первый уровень за {BIZ_TERRITORY_COST[0]} 🪙.", reply_markup=kb)
    show_biz_menu(message.chat.id, uid, None)

def show_biz_menu(chat_id, uid, msg_id):
    p = data["players"].get(uid, {}); t = p.get("biz_territory", 0); b = p.get("biz_building", 1); tax = p.get("biz_tax", 0)
    inc = (t * 100) * (1 + (b - 1) * 0.5)
    earned = int((min(int(time.time()) - p.get("biz_last_collect", int(time.time())), 86400) / 3600) * inc)
    text = f"🏢 **Бизнес**\n🧱 Территория: {t} м² (⬆️ {BIZ_TERRITORY_COST.get(t, 'MAX')} 🪙)\n🏢 Здание: ур. {b} (⬆️ {BIZ_BUILDING_COST.get(b, 'MAX')} 🪙)\n📈 Доход: {int(inc)} 🪙/час\n💸 Налоги: {tax} 🪙\n💰 Накоплено: **{earned} 🪙**"
    kb = InlineKeyboardMarkup(row_width=2).add(InlineKeyboardButton("💰 Собрать", callback_data="biz_collect"), InlineKeyboardButton("🧱 Терр.", callback_data="biz_terr"), InlineKeyboardButton("🏢 Здание", callback_data="biz_build_up"), InlineKeyboardButton("💸 Налоги", callback_data="biz_tax"))
    if msg_id: bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb, parse_mode="Markdown")
    else: bot.send_message(chat_id, text, reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("biz_"))
def biz_callback(call):
    uid = str(call.from_user.id); act = call.data.split("_")[1]
    if act == "build":
        if get_balance(uid) < BIZ_TERRITORY_COST[0]: return bot.answer_callback_query(call.id, "❌ Мало денег!", show_alert=True)
        add_balance(uid, -BIZ_TERRITORY_COST[0]); data["players"][uid]["biz_territory"] = 1; save_data()
        bot.answer_callback_query(call.id, "✅ Построено!"); show_biz_menu(call.message.chat.id, uid, call.message.message_id)
    elif act == "collect":
        p = data["players"].get(uid, {}); t = p.get("biz_territory", 0); b = p.get("biz_building", 1); tax = p.get("biz_tax", 0)
        if tax > 0: return bot.answer_callback_query(call.id, f"❌ Оплатите налоги ({tax} 🪙)!", show_alert=True)
        inc = (t * 100) * (1 + (b - 1) * 0.5)
        earned = int((min(int(time.time()) - p.get("biz_last_collect", int(time.time())), 86400) / 3600) * inc)
        if earned <= 0: return bot.answer_callback_query(call.id, "⏳ Пусто.", show_alert=True)
        tax_o = int(inc * 0.1)
        data["players"][uid]["biz_tax"] = tax_o; add_balance(uid, earned); data["players"][uid]["biz_last_collect"] = int(time.time()); save_data()
        bot.answer_callback_query(call.id, f"💰 +{earned} 🪙! Налог: {tax_o} 🪙", show_alert=True); show_biz_menu(call.message.chat.id, uid, call.message.message_id)
    elif act == "terr":
        p = data["players"].get(uid, {}); t = p.get("biz_territory", 0)
        if t >= 5: return bot.answer_callback_query(call.id, "🧱 MAX!", show_alert=True)
        c = BIZ_TERRITORY_COST.get(t, 0)
        if get_balance(uid) < c: return bot.answer_callback_query(call.id, f"❌ {c} 🪙!", show_alert=True)
        add_balance(uid, -c); data["players"][uid]["biz_territory"] += 1; save_data()
        bot.answer_callback_query(call.id, "✅ Территория +!"); show_biz_menu(call.message.chat.id, uid, call.message.message_id)
    elif act == "build_up":
        p = data["players"].get(uid, {}); b = p.get("biz_building", 1)
        if b >= 5: return bot.answer_callback_query(call.id, "🏢 MAX!", show_alert=True)
        c = BIZ_BUILDING_COST.get(b, 0)
        if get_balance(uid) < c: return bot.answer_callback_query(call.id, f"❌ {c} 🪙!", show_alert=True)
        add_balance(uid, -c); data["players"][uid]["biz_building"] += 1; save_data()
        bot.answer_callback_query(call.id, "✅ Здание +!"); show_biz_menu(call.message.chat.id, uid, call.message.message_id)
    elif act == "tax":
        p = data["players"].get(uid, {}); tax = p.get("biz_tax", 0)
        if tax <= 0: return bot.answer_callback_query(call.id, "✅ Долгов нет.", show_alert=True)
        if get_balance(uid) < tax: return bot.answer_callback_query(call.id, f"❌ {tax} 🪙!", show_alert=True)
        add_balance(uid, -tax); data["players"][uid]["biz_tax"] = 0; save_data()
        bot.answer_callback_query(call.id, "✅ Оплачено!"); show_biz_menu(call.message.chat.id, uid, call.message.message_id)

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "банк")
def bank_info(message):
    uid = str(message.from_user.id); p = data["players"].get(uid, {}); b = p.get("bank", 0); d = p.get("deposit", 0); ds = p.get("deposit_start", 0); now = int(time.time()); cd = 3 * 86400
    st = "Нет" if d == 0 else (f"✅ {d} 🪙 (Можно снять)" if now - ds >= cd else f"⏳ {d} 🪙 ({(cd - (now - ds))//3600} ч.)")
    msg = f"🏦 **БАНК**\n💰 Счет: {b} 🪙\n💎 Депозит: {st}\n📈 10% (раз в 3 дня)\n\n`банк положить СУММА` / `банк снять СУММА`\n`депозит положить СУММА` / `депозит снять`"
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("банк положить"))
def bank_dep(message):
    uid = str(message.from_user.id)
    try:
        a = int(message.text.split()[2])
        if a <= 0 or get_balance(uid) < a: return bot.reply_to(message, "❌ Мало.")
        add_balance(uid, -a); data["players"][uid]["bank"] += a; save_data(); bot.reply_to(message, f"✅ +{a} 🪙 в банк.")
    except: bot.reply_to(message, "❌ `банк положить 1000`")

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("банк снять"))
def bank_wd(message):
    uid = str(message.from_user.id)
    try:
        a = int(message.text.split()[2])
        if a <= 0 or data["players"][uid].get("bank", 0) < a: return bot.reply_to(message, "❌ Мало в банке.")
        data["players"][uid]["bank"] -= a; add_balance(uid, a); save_data(); bot.reply_to(message, f"✅ -{a} 🪙 из банка.")
    except: bot.reply_to(message, "❌ `банк снять 1000`")

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("депозит положить"))
def dep_make(message):
    uid = str(message.from_user.id); p = data["players"].get(uid, {})
    try:
        a = int(message.text.split()[2])
        if a <= 0 or get_balance(uid) < a: return bot.reply_to(message, "❌ Мало.")
        if p.get("deposit", 0) > 0 and (int(time.time()) - p.get("deposit_start", 0) < 3 * 86400): return bot.reply_to(message, "❌ Уже есть депозит.")
        add_balance(uid, -a); data["players"][uid]["deposit"] = a; data["players"][uid]["deposit_start"] = int(time.time()); save_data()
        bot.reply_to(message, f"✅ Депозит {a} 🪙 открыт."); complete_quest(uid, "Открыть депозит")
    except: bot.reply_to(message, "❌ `депозит положить 1000`")

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "депозит снять")
def dep_wd(message):
    uid = str(message.from_user.id); p = data["players"].get(uid, {}); d = p.get("deposit", 0); ds = p.get("deposit_start", 0)
    if d <= 0: return bot.reply_to(message, "❌ Нет депозита.")
    if int(time.time()) - ds < 3 * 86400: return bot.reply_to(message, f"⏳ Ждать {(3 * 86400 - (int(time.time()) - ds))//3600} ч.")
    i = int(d * 0.1); add_balance(uid, d + i); data["players"][uid]["deposit"] = 0; data["players"][uid]["deposit_start"] = 0; save_data()
    bot.reply_to(message, f"🏦 **Депозит закрыт!**\nВклад: {d} 🪙\nПроценты: +{i} 🪙\nИтого: **{d + i} 🪙**", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("перевод"))
def transfer(message):
    uid = str(message.from_user.id)
    if message.reply_to_message:
        t_uid = str(message.reply_to_message.from_user.id)
        try: a = int(message.text.split()[1])
        except: return bot.reply_to(message, "❌ `перевод 1000` (в ответ)")
        if a <= 0 or get_balance(uid) < a: return bot.reply_to(message, "❌ Мало.")
        if a > 10000: return bot.reply_to(message, "❌ Лимит перевода — 10000 🪙.")
        if t_uid == uid: return bot.reply_to(message, "❌ Себе нельзя.")
        if t_uid not in data["players"]: register_user(message.reply_to_message.from_user)
        add_balance(uid, -a); add_balance(t_uid, a)
        return bot.reply_to(message, f"✅ {a} 🪙 переведено {get_nick(t_uid)}.")
    else:
        try:
            a = int(message.text.split()[1]); t_name = message.text.split()[2]
            if a <= 0 or get_balance(uid) < a: return bot.reply_to(message, "❌ Мало.")
            if a > 10000: return bot.reply_to(message, "❌ Лимит перевода — 10000 🪙.")
            t_uid = get_user_by_username(t_name)
            if not t_uid or t_uid == uid: return bot.reply_to(message, "❌ Не найден.")
            add_balance(uid, -a); add_balance(t_uid, a)
            bot.reply_to(message, f"✅ {a} 🪙 переведено {get_nick(t_uid)}.")
        except: bot.reply_to(message, "❌ `перевод 1000 ник`")

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "квесты")
def quests_menu(message):
    uid = str(message.from_user.id); p = data["players"].get(uid, {}); now = int(time.time())
    if "quest_date" not in p or now - p.get("quest_date", 0) >= 86400:
        data["players"][uid]["quests"] = {
            "Сделать ставку в слот": {"done": False, "reward": 500, "claimed": False}, 
            "Сыграть в краш": {"done": False, "reward": 500, "claimed": False}, 
            "Открыть депозит": {"done": False, "reward": 500, "claimed": False}
        }
        data["players"][uid]["quest_date"] = now; save_data()
    q = p.get("quests", {}); text = "📜 **Ежедневные квесты**\n\n"
    for name, info in q.items(): 
        status = "✅" if info.get("done") else "❌"
        text += f"{status} {name} (+{info['reward']} 🪙)\n"
    text += "\nНапишите `забрать квест` после выполнения."
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "забрать квест")
def claim_quests(message):
    uid = str(message.from_user.id); q = data["players"].get(uid, {}).get("quests", {}); total = 0
    for name, info in q.items():
        if info.get("done") and not info.get("claimed", False): total += info["reward"]; info["claimed"] = True
    if total > 0: 
        add_balance(uid, total); save_data()
        bot.reply_to(message, f"🎉 Вы получили {total} 🪙 за квесты!", parse_mode="Markdown")
    else: bot.reply_to(message, "❌ Нет выполненных или незабранных квестов.")

def complete_quest(uid, quest_name):
    uid = str(uid); p = data["players"].get(uid, {})
    if "quests" in p and quest_name in p["quests"]:
        if not p["quests"][quest_name]["done"]: p["quests"][quest_name]["done"] = True; save_data()

print("BOT STARTED")
bot.infinity_polling(skip_pending=True)
