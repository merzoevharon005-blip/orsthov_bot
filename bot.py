import os, random, math, time, telebot, threading, json, pathlib
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN: raise ValueError("Не задан BOT_TOKEN")

ADMIN_IDS = [8211650013, 6940877915]
DATA_DIR = pathlib.Path("/app/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = DATA_DIR / "database.json"

data = {
    "players": {},
    "promos": {},
    "activations": [],
    "history": [],
    "clans": {},
    "next_id": 1,
    "active_games": {},
    "roulette_bets": {},
    "duels": {}
}
db_lock = threading.Lock()

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
    with db_lock:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

load_data()

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
            pdata["bank"] = 0
            pdata["deposit"] = 0
            pdata["deposit_start"] = 0
            changed = True
        if "biz_territory" not in pdata:
            pdata["biz_territory"] = 0
            pdata["biz_building"] = 1
            pdata["biz_tax"] = 0
            pdata["biz_last_collect"] = int(time.time())
            changed = True
        if "title" not in pdata:
            pdata["title"] = "Нет"
            changed = True
        if "quests" not in pdata:
            pdata["quests"] = {}
            changed = True
        if "donate_status" not in pdata:
            pdata["donate_status"] = "Нет"
            changed = True
        if "last_bonus" not in pdata:
            pdata["last_bonus"] = 0
            changed = True

    if "roulette_bets" not in data:
        data["roulette_bets"] = {}
    if "promos" not in data:
        data["promos"] = {}
    if "activations" not in data:
        data["activations"] = []
    if "duels" not in data:
        data["duels"] = {}
    if "clans" not in data:
        data["clans"] = {}

    if changed:
        save_data()

migrate_data()
bot = telebot.TeleBot(TOKEN)

MULT = {3: 1.15, 5: 1.25, 9: 1.45}
BIZ_TERRITORY_COST = {0: 10000, 1: 50000, 2: 250000, 3: 1000000, 4: 5000000, 5: 25000000}
BIZ_BUILDING_COST = {1: 20000, 2: 100000, 3: 500000, 4: 2000000, 5: 10000000}

def get_balance(uid):
    return data["players"].get(str(uid), {}).get("balance", 0)

def get_nick(uid):
    return data["players"].get(str(uid), {}).get("username", "Player")

def get_user_short_id(uid):
    return data["players"].get(str(uid), {}).get("short_id", "0")

def get_user_by_short_id(sid):
    for uid, pdata in data["players"].items():
        if str(pdata.get("short_id")) == str(sid):
            return uid
    return None

def get_user_by_username(uname):
    uname = uname.replace("@", "").lower()
    for uid, pdata in data["players"].items():
        if pdata.get("username", "").lower() == uname:
            return uid
    return None

def get_win_multiplier(uid):
    status = data["players"].get(str(uid), {}).get("donate_status", "Нет")
    if status == "VIP":
        return 1.05
    if status == "Premium":
        return 1.15
    if status == "Ultra":
        return 1.25
    return 1.0

def add_balance(uid, amt):
    uid = str(uid)
    if uid not in data["players"]:
        register_user_by_id(uid)
    data["players"][uid]["balance"] += amt
    save_data()

def register_user(user):
    uid = str(user.id)
    if uid not in data["players"]:
        sid = data["next_id"]
        data["next_id"] += 1
        data["players"][uid] = {
            "username": user.username or user.first_name,
            "balance": 1000,
            "last_bonus": 0,
            "short_id": sid,
            "clan_id": None,
            "role": "none",
            "bank": 0,
            "deposit": 0,
            "deposit_start": 0,
            "biz_territory": 0,
            "biz_building": 1,
            "biz_tax": 0,
            "biz_last_collect": int(time.time()),
            "title": "Нет",
            "quests": {},
            "donate_status": "Нет"
        }
        save_data()

def register_user_by_id(uid):
    uid = str(uid)
    if uid not in data["players"]:
        sid = data["next_id"]
        data["next_id"] += 1
        data["players"][uid] = {
            "username": "Player",
            "balance": 1000,
            "last_bonus": 0,
            "short_id": sid,
            "clan_id": None,
            "role": "none",
            "bank": 0,
            "deposit": 0,
            "deposit_start": 0,
            "biz_territory": 0,
            "biz_building": 1,
            "biz_tax": 0,
            "biz_last_collect": int(time.time()),
            "title": "Нет",
            "quests": {},
            "donate_status": "Нет"
        }
        save_data()

def find_pending_duel_for(uid):
    uid = str(uid)
    for duel_id, duel in data["duels"].items():
        if duel["status"] == "pending" and duel["opponent"] == uid:
            return duel_id, duel
    return None, None

def resolve_duel(duel_id, duel, winner, loser):
    amount = duel["amount"]
    pot = amount * 2
    add_balance(winner, pot)

    duel["status"] = "finished"
    duel["winner"] = winner
    save_data()

    winner_name = get_nick(winner)
    loser_name = get_nick(loser)
    pot_str = f"{pot:,}".replace(",", " ")

    result = (
        f"⚔️ **РЕЗУЛЬТАТ ДУЭЛИ**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏆 Победитель: **{winner_name}**\n"
        f"💀 Проигравший: **{loser_name}**\n"
        f"💰 Банк: **{pot_str} 🪙**\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )

    try:
        bot.send_message(int(duel["challenger"]), result, parse_mode="Markdown")
        bot.send_message(int(duel["opponent"]), result, parse_mode="Markdown")
    except:
        pass

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
        f"🎮 **Игры:** `слот 1000`, `мины 1000 5`, `краш 1000`, `джокер 1000`\n"
        f"⚔️ **Дуэли:** `дуэль ID сумма` или `дуэль @ник сумма`\n"
        f"🎁 **Бонус:** `бонус`\n"
        f"🛡 **Кланы:** `мой клан`\n"
        f"📖 **Помощь:** `помощь`",
        parse_mode="Markdown")

@bot.message_handler(commands=['help'])
@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() in ['помощь', 'help'])
def help_command(message):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("🎮 Игры", callback_data="help_games"),
           InlineKeyboardButton("💼 Экономика", callback_data="help_eco"))
    kb.add(InlineKeyboardButton("🛡 Кланы", callback_data="help_clans"),
           InlineKeyboardButton("💎 Донат", callback_data="help_donate"))
    bot.reply_to(message, "📖 **МЕНЮ ПОМОЩИ**\n━━━━━━━━━━━━━━━━━━━━\nВыберите раздел кнопками ниже:", reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("help_"))
def help_callbacks(call):
    section = call.data.split("_")[1]
    if section == "games":
        text = ("🎮 **ИГРЫ**\n━━━━━━━━━━━━━━━━━━━━\n"
                "• `слот 1000` — автомат\n"
                "• `мины 1000 5` — поле (3, 5, 9 бомб)\n"
                "• `краш 1000` — растущий коэф.\n"
                "• `джокер 1000` — лесенка удачи\n"
                "• `дуэль ID/@ник сумма` — вызвать на дуэль\n"
                "• `принять` / `го` — принять дуэль\n"
                "• `отклонить` — отклонить дуэль")
    elif section == "eco":
        text = ("💼 **ЭКОНОМИКА**\n━━━━━━━━━━━━━━━━━━━━\n"
                "• `б` — баланс\n"
                "• `бонус` — ежедневный бонус\n"
                "• `профиль` — профиль\n"
                "• `узнать ид` — ID игрока\n"
                "• `топ` — топ-10\n"
                "• `банк` — банк\n"
                "• `мой бизнес` — бизнес\n"
                "• `квесты` — задания\n"
                "• `перевод 1000 ник`\n"
                "• `промо КОД`\n"
                "• `сменить ник НОВЫЙ_НИК`")
    elif section == "clans":
        text = ("🛡 **КЛАНЫ**\n━━━━━━━━━━━━━━━━━━━━\n"
                "• `создать клан ИМЯ` (10000)\n"
                "• `вступить клан ID`\n"
                "• `мой клан`\n"
                "• `выйти из клана`\n"
                "• `топ кланов`\n"
                "• `клан казна положить/снять СУММА`")
    elif section == "donate":
        text = ("💎 **ДОНАТ**\n━━━━━━━━━━━━━━━━━━━━\n"
                "• `донат` — пополнить\n"
                "• `донат статус` — купить статус\n"
                "• `мой статус` — узнать статус")
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=call.message.reply_markup, parse_mode="Markdown")
    bot.answer_callback_query(call.id)

# ==================== БОНУС ====================

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == 'бонус')
def daily_bonus(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    p = data["players"][uid]
    now = int(time.time())
    last = p.get("last_bonus", 0)
    if now - last < 86400:
        left = 86400 - (now - last)
        return bot.reply_to(message, f"⏳ **Подождите!**\nСледующий бонус через **{left // 3600} ч. {(left % 3600) // 60} мин.**", parse_mode="Markdown")
    reward = random.randint(1000, 3000)
    add_balance(uid, reward)
    data["players"][uid]["last_bonus"] = now
    save_data()
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
        bot.send_invoice(chat_id=call.message.chat.id, title=f"Покупка {coins} монет",
                         description=f"Вы получите {coins} монет на баланс.",
                         invoice_payload=f"pay_{stars}", provider_token="", currency="XTR", prices=prices)
        bot.answer_callback_query(call.id, "✅ Счет выставлен!")
    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {e}", show_alert=True)

def process_custom_stars(message):
    try:
        stars = int(message.text)
        if stars < 1 or stars > 10000:
            return bot.reply_to(message, "❌ От 1 до 10000 звезд.")
        coins = stars * 1000
        prices = [LabeledPrice(label=f"{coins} монет", amount=stars)]
        bot.send_invoice(chat_id=message.chat.id, title=f"Покупка {coins} монет",
                         description=f"Вы получите {coins} монет на баланс.",
                         invoice_payload=f"pay_{stars}", provider_token="", currency="XTR", prices=prices)
    except:
        bot.reply_to(message, "❌ Введите число.")

@bot.pre_checkout_query_handler(func=lambda query: True)
def process_pre_checkout_query(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def got_payment(message):
    payload = message.successful_payment.invoice_payload
    if payload.startswith("status_"):
        status = payload.split("_")[1]
        uid = str(message.from_user.id)
        if uid not in data["players"]:
            register_user(message.from_user)
        data["players"][uid]["donate_status"] = status
        save_data()
        bot.send_message(message.chat.id, f"🎉 **ОПЛАТА УСПЕШНА!**\n━━━━━━━━━━━━━━━━━━━━\nВы получили статус **{status}**!", parse_mode="Markdown")
        return

    stars = int(payload.split("_")[1])
    coins = stars * 1000
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    add_balance(uid, coins)

    current_status = data["players"][uid].get("donate_status", "Нет")
    if stars >= 750 and current_status != "Ultra":
        data["players"][uid]["donate_status"] = "Ultra"
        bot.send_message(message.chat.id, f"🎉 **ОПЛАТА УСПЕШНА!**\n━━━━━━━━━━━━━━━━━━━━\nВы получили **{coins} 🪙** и статус **Ultra**!", parse_mode="Markdown")
    elif stars >= 450 and current_status not in ["Premium", "Ultra"]:
        data["players"][uid]["donate_status"] = "Premium"
        bot.send_message(message.chat.id, f"🎉 **ОПЛАТА УСПЕШНА!**\n━━━━━━━━━━━━━━━━━━━━\nВы получили **{coins} 🪙** и статус **Premium**!", parse_mode="Markdown")
    elif stars >= 200 and current_status not in ["VIP", "Premium", "Ultra"]:
        data["players"][uid]["donate_status"] = "VIP"
        bot.send_message(message.chat.id, f"🎉 **ОПЛАТА УСПЕШНА!**\n━━━━━━━━━━━━━━━━━━━━\nВы получили **{coins} 🪙** и статус **VIP**!", parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, f"🎉 **ОПЛАТА УСПЕШНА!**\n━━━━━━━━━━━━━━━━━━━━\nВы получили **{coins} 🪙**.", parse_mode="Markdown")
    save_data()

@bot.message_handler(commands=['donate_status'])
@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == 'донат статус')
def donate_status_menu(message):
    text = ("💎 **ДОНАТ-СТАТУСЫ**\n━━━━━━━━━━━━━━━━━━━━\n"
            "👑 **VIP** (200 ⭐) — +5% к выигрышу\n"
            "💎 **Premium** (450 ⭐) — +15% к выигрышу\n"
            "⚡ **Ultra** (750 ⭐) — +25% к выигрышу + просмотр профилей")
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
        bot.send_invoice(chat_id=call.message.chat.id, title=f"Покупка статуса {status}",
                         description=f"Вы получите статус {status}.",
                         invoice_payload=f"status_{status}", provider_token="", currency="XTR", prices=prices)
        bot.answer_callback_query(call.id, "✅ Счет выставлен!")
    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {e}", show_alert=True)

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "мой статус")
def my_status(message):
    uid = str(message.from_user.id)
    status = data["players"].get(uid, {}).get("donate_status", "Нет")
    bot.reply_to(message, f"💎 **ВАШ СТАТУС**\n━━━━━━━━━━━━━━━━━━━━\nТекущий статус: **{status}**", parse_mode="Markdown")

# ==================== БАЗОВЫЕ КОМАНДЫ ====================

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == 'б')
def balance_command(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
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
    if target_uid not in data["players"]:
        register_user_by_id(target_uid)
    sid = get_user_short_id(target_uid)
    bot.reply_to(message, f"🆔 **ID ИГРОКА**\n━━━━━━━━━━━━━━━━━━━━\n`{sid}`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("сменить ник"))
def change_nick(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            return bot.reply_to(message, "❌ Формат: `сменить ник НОВЫЙ_НИК`", parse_mode="Markdown")
        new_nick = parts[2].strip()
        if len(new_nick) < 3 or len(new_nick) > 15:
            return bot.reply_to(message, "❌ Ник должен быть от 3 до 15 символов.")
        data["players"][uid]["username"] = new_nick
        save_data()
        bot.reply_to(message, f"✅ **НИК ИЗМЕНЁН**\n━━━━━━━━━━━━━━━━━━━━\nНовый ник: **{new_nick}**", parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Формат: `сменить ник НОВЫЙ_НИК`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == 'профиль')
def profile_command(message):
    uid = str(message.from_user.id)
    target_uid = uid
    if message.reply_to_message:
        target_uid = str(message.reply_to_message.from_user.id)
        caller_status = data["players"].get(uid, {}).get("donate_status", "Нет")
        if uid not in [str(a) for a in ADMIN_IDS] and caller_status != "Ultra":
            return bot.reply_to(message, "❌ **ДОСТУП ЗАПРЕЩЕН**\nСмотреть чужой профиль могут только админы и Ultra.", parse_mode="Markdown")
    if target_uid not in data["players"]:
        register_user_by_id(target_uid)
    p = data["players"][target_uid]
    clan_name = "Нет"
    if p.get("clan_id"):
        clan = data["clans"].get(str(p["clan_id"]))
        if clan:
            clan_name = clan.get("name", "Нет")
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

# ==================== ИГРЫ ====================

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("слот "))
def slot_game(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    try:
        amount = int(message.text.split()[1].replace(" ", "").replace(",", ""))
    except:
        return bot.reply_to(message, "❌ Формат: `слот 1000`", parse_mode="Markdown")
    if amount < 100:
        return bot.reply_to(message, "❌ Минимум 100 🪙")
    if get_balance(uid) < amount:
        return bot.reply_to(message, "❌ Недостаточно средств.")

    add_balance(uid, -amount)
    symbols = ["🍒", "🍋", "🍇", "🍉", "⭐", "💎", "7️⃣"]
    reels = [random.choice(symbols) for _ in range(3)]
    result_str = " | ".join(reels)

    mult = get_win_multiplier(uid)
    win = 0
    if reels[0] == reels[1] == reels[2]:
        if reels[0] == "7️⃣":
            win = int(amount * 10 * mult)
        elif reels[0] == "💎":
            win = int(amount * 7 * mult)
        elif reels[0] == "⭐":
            win = int(amount * 5 * mult)
        else:
            win = int(amount * 3 * mult)
    elif reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
        win = int(amount * 1.5 * mult)

    if win > 0:
        add_balance(uid, win)
        bot.reply_to(message,
            f"🎰 **СЛОТ**\n━━━━━━━━━━━━━━━━━━━━\n"
            f"{result_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎉 Выигрыш: **{win} 🪙**\n"
            f"💰 Баланс: **{get_balance(uid)} 🪙**",
            parse_mode="Markdown")
    else:
        bot.reply_to(message,
            f"🎰 **СЛОТ**\n━━━━━━━━━━━━━━━━━━━━\n"
            f"{result_str}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"😢 Проигрыш: **-{amount} 🪙**\n"
            f"💰 Баланс: **{get_balance(uid)} 🪙**",
            parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("мины "))
def mines_game(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    parts = message.text.split()
    if len(parts) < 3:
        return bot.reply_to(message, "❌ Формат: `мины 1000 5`\nБомбы: 3, 5 или 9", parse_mode="Markdown")
    try:
        amount = int(parts[1].replace(" ", "").replace(",", ""))
        bombs = int(parts[2])
    except:
        return bot.reply_to(message, "❌ Формат: `мины 1000 5`", parse_mode="Markdown")
    if bombs not in [3, 5, 9]:
        return bot.reply_to(message, "❌ Количество бомб: 3, 5 или 9")
    if amount < 100:
        return bot.reply_to(message, "❌ Минимум 100 🪙")
    if get_balance(uid) < amount:
        return bot.reply_to(message, "❌ Недостаточно средств.")

    add_balance(uid, -amount)
    mult = MULT[bombs] * get_win_multiplier(uid)
    # 25 клеток, bombs мин, остальное безопасные
    safe = 25 - bombs
    # Простая симуляция: шанс пройти = safe/25 * небольшой множитель
    success_chance = (safe / 25) * 0.85
    if random.random() < success_chance:
        win = int(amount * mult)
        add_balance(uid, win)
        bot.reply_to(message,
            f"💣 **МИНЫ** ({bombs} бомб)\n━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ Успешно!\n"
            f"🎉 Выигрыш: **{win} 🪙** (x{mult:.2f})\n"
            f"💰 Баланс: **{get_balance(uid)} 🪙**",
            parse_mode="Markdown")
    else:
        bot.reply_to(message,
            f"💣 **МИНЫ** ({bombs} бомб)\n━━━━━━━━━━━━━━━━━━━━\n"
            f"💥 БУМ! Вы попали на мину.\n"
            f"😢 Проигрыш: **-{amount} 🪙**\n"
            f"💰 Баланс: **{get_balance(uid)} 🪙**",
            parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("краш "))
def crash_game(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    try:
        amount = int(message.text.split()[1].replace(" ", "").replace(",", ""))
    except:
        return bot.reply_to(message, "❌ Формат: `краш 1000`", parse_mode="Markdown")
    if amount < 100:
        return bot.reply_to(message, "❌ Минимум 100 🪙")
    if get_balance(uid) < amount:
        return bot.reply_to(message, "❌ Недостаточно средств.")

    add_balance(uid, -amount)
    # Генерируем коэффициент краша
    r = random.random()
    if r < 0.03:
        crash_point = 1.00
    else:
        crash_point = max(1.00, round(0.97 / (1 - r), 2))

    # Игрок "кэшится" случайно или по формуле (для простоты — рандомный кэш)
    player_cash = round(random.uniform(1.1, min(crash_point + 0.5, 8.0)), 2)
    mult = get_win_multiplier(uid)

    if player_cash < crash_point:
        win = int(amount * player_cash * mult)
        add_balance(uid, win)
        bot.reply_to(message,
            f"📈 **КРАШ**\n━━━━━━━━━━━━━━━━━━━━\n"
            f"🚀 Улетел до: **x{crash_point}**\n"
            f"✅ Вы вышли на: **x{player_cash}**\n"
            f"🎉 Выигрыш: **{win} 🪙**\n"
            f"💰 Баланс: **{get_balance(uid)} 🪙**",
            parse_mode="Markdown")
    else:
        bot.reply_to(message,
            f"📈 **КРАШ**\n━━━━━━━━━━━━━━━━━━━━\n"
            f"💥 Краш на: **x{crash_point}**\n"
            f"😢 Вы не успели выйти\n"
            f"Проигрыш: **-{amount} 🪙**\n"
            f"💰 Баланс: **{get_balance(uid)} 🪙**",
            parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("джокер "))
def joker_game(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    try:
        amount = int(message.text.split()[1].replace(" ", "").replace(",", ""))
    except:
        return bot.reply_to(message, "❌ Формат: `джокер 1000`", parse_mode="Markdown")
    if amount < 100:
        return bot.reply_to(message, "❌ Минимум 100 🪙")
    if get_balance(uid) < amount:
        return bot.reply_to(message, "❌ Недостаточно средств.")

    add_balance(uid, -amount)
    mult = get_win_multiplier(uid)
    # Лесенка: 5 ступеней, шанс пройти каждую ~70%
    steps = 0
    for i in range(5):
        if random.random() < 0.68:
            steps += 1
        else:
            break

    multipliers = [1.3, 1.8, 2.5, 4.0, 7.0]
    if steps == 0:
        bot.reply_to(message,
            f"🃏 **ДЖОКЕР**\n━━━━━━━━━━━━━━━━━━━━\n"
            f"💀 Сорвались на первой ступени\n"
            f"😢 Проигрыш: **-{amount} 🪙**\n"
            f"💰 Баланс: **{get_balance(uid)} 🪙**",
            parse_mode="Markdown")
    else:
        win_mult = multipliers[steps - 1] * mult
        win = int(amount * win_mult)
        add_balance(uid, win)
        bot.reply_to(message,
            f"🃏 **ДЖОКЕР**\n━━━━━━━━━━━━━━━━━━━━\n"
            f"🪜 Пройдено ступеней: **{steps}/5**\n"
            f"🎉 Выигрыш: **{win} 🪙** (x{win_mult:.2f})\n"
            f"💰 Баланс: **{get_balance(uid)} 🪙**",
            parse_mode="Markdown")

# ==================== ПРОМО ====================

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("промо "))
def promo_activate(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    code = message.text.split(maxsplit=1)[1].strip().upper()
    if code not in data["promos"]:
        return bot.reply_to(message, "❌ Промокод не найден или уже закончился.")
    promo = data["promos"][code]
    if uid in promo.get("activated", []):
        return bot.reply_to(message, "❌ Вы уже активировали этот промокод.")
    if len(promo.get("activated", [])) >= promo.get("uses", 0):
        return bot.reply_to(message, "❌ Промокод больше недоступен.")
    amount = promo["amount"]
    add_balance(uid, amount)
    if "activated" not in promo:
        promo["activated"] = []
    promo["activated"].append(uid)
    save_data()
    bot.reply_to(message, f"🎁 **ПРОМОКОД АКТИВИРОВАН**\n━━━━━━━━━━━━━━━━━━━━\nВы получили: **{amount} 🪙**", parse_mode="Markdown")

# ==================== ПЕРЕВОД ====================

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("перевод "))
def transfer_cmd(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    parts = message.text.split()
    if len(parts) < 3:
        return bot.reply_to(message, "❌ Формат: `перевод 1000 ник` или `перевод 1000 ID`", parse_mode="Markdown")
    try:
        amount = int(parts[1].replace(" ", "").replace(",", ""))
    except:
        return bot.reply_to(message, "❌ Сумма должна быть числом.")
    if amount < 100:
        return bot.reply_to(message, "❌ Минимум 100 🪙")
    if get_balance(uid) < amount:
        return bot.reply_to(message, "❌ Недостаточно средств.")

    target_raw = parts[2]
    target_uid = None
    if target_raw.startswith("@"):
        target_uid = get_user_by_username(target_raw)
    else:
        try:
            sid = int(target_raw)
            target_uid = get_user_by_short_id(sid)
        except:
            target_uid = get_user_by_username(target_raw)

    if not target_uid:
        return bot.reply_to(message, "❌ Игрок не найден.")
    target_uid = str(target_uid)
    if target_uid == uid:
        return bot.reply_to(message, "❌ Нельзя перевести себе.")

    add_balance(uid, -amount)
    add_balance(target_uid, amount)
    bot.reply_to(message, f"✅ Переведено **{amount} 🪙** игроку **{get_nick(target_uid)}**", parse_mode="Markdown")
    try:
        bot.send_message(int(target_uid), f"💸 Вам перевели **{amount} 🪙** от **{get_nick(uid)}**", parse_mode="Markdown")
    except:
        pass

# ==================== БАНК ====================

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "банк")
def bank_menu(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    p = data["players"][uid]
    text = (f"🏦 **БАНК**\n━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 На руках: **{p.get('balance', 0)} 🪙**\n"
            f"🏦 В банке: **{p.get('bank', 0)} 🪙**\n"
            f"💎 Депозит: **{p.get('deposit', 0)} 🪙**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"`банк положить СУММА`\n"
            f"`банк снять СУММА`\n"
            f"`депозит положить СУММА`\n"
            f"`депозит снять`")
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("банк положить "))
def bank_put(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    try:
        amount = int(message.text.split()[2].replace(" ", "").replace(",", ""))
    except:
        return bot.reply_to(message, "❌ Формат: `банк положить 5000`")
    if amount < 1:
        return bot.reply_to(message, "❌ Сумма должна быть больше 0")
    if get_balance(uid) < amount:
        return bot.reply_to(message, "❌ Недостаточно средств.")
    add_balance(uid, -amount)
    data["players"][uid]["bank"] += amount
    save_data()
    bot.reply_to(message, f"✅ Положено **{amount} 🪙** в банк.\n🏦 В банке: **{data['players'][uid]['bank']} 🪙**", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("банк снять "))
def bank_take(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    try:
        amount = int(message.text.split()[2].replace(" ", "").replace(",", ""))
    except:
        return bot.reply_to(message, "❌ Формат: `банк снять 5000`")
    if amount < 1:
        return bot.reply_to(message, "❌ Сумма должна быть больше 0")
    if data["players"][uid].get("bank", 0) < amount:
        return bot.reply_to(message, "❌ Недостаточно средств в банке.")
    data["players"][uid]["bank"] -= amount
    add_balance(uid, amount)
    save_data()
    bot.reply_to(message, f"✅ Снято **{amount} 🪙** из банка.\n🏦 В банке: **{data['players'][uid]['bank']} 🪙**", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("депозит положить "))
def deposit_put(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    try:
        amount = int(message.text.split()[2].replace(" ", "").replace(",", ""))
    except:
        return bot.reply_to(message, "❌ Формат: `депозит положить 5000`")
    if amount < 1000:
        return bot.reply_to(message, "❌ Минимум 1000 🪙 на депозит")
    if get_balance(uid) < amount:
        return bot.reply_to(message, "❌ Недостаточно средств.")
    add_balance(uid, -amount)
    data["players"][uid]["deposit"] += amount
    data["players"][uid]["deposit_start"] = int(time.time())
    save_data()
    bot.reply_to(message, f"✅ Депозит пополнен на **{amount} 🪙**.\n💎 На депозите: **{data['players'][uid]['deposit']} 🪙**", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "депозит снять")
def deposit_take(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    dep = data["players"][uid].get("deposit", 0)
    if dep <= 0:
        return bot.reply_to(message, "❌ Депозит пуст.")
    # Простой процент: +0.5% в сутки
    start = data["players"][uid].get("deposit_start", int(time.time()))
    days = max(0, (int(time.time()) - start) // 86400)
    interest = int(dep * 0.005 * days)
    total = dep + interest
    data["players"][uid]["deposit"] = 0
    data["players"][uid]["deposit_start"] = 0
    add_balance(uid, total)
    save_data()
    bot.reply_to(message, f"✅ Депозит снят.\n💎 Сумма: **{dep} 🪙**\n📈 Проценты: **{interest} 🪙**\n💰 Итого: **{total} 🪙**", parse_mode="Markdown")

# ==================== БИЗНЕС ====================

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "мой бизнес")
def my_business(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    p = data["players"][uid]
    territory = p.get("biz_territory", 0)
    building = p.get("biz_building", 1)
    last = p.get("biz_last_collect", int(time.time()))
    hours = max(0, (int(time.time()) - last) // 3600)
    income_per_hour = (territory + 1) * building * 50
    pending = income_per_hour * hours

    text = (f"🏢 **МОЙ БИЗНЕС**\n━━━━━━━━━━━━━━━━━━━━\n"
            f"📐 Территория: **{territory}**\n"
            f"🏗 Здание: **ур. {building}**\n"
            f"💵 Доход: **{income_per_hour} 🪙/час**\n"
            f"📦 Можно собрать: **{pending} 🪙**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"`бизнес собрать`\n"
            f"`бизнес территория` — улучшить\n"
            f"`бизнес здание` — улучшить")
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "бизнес собрать")
def biz_collect(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    p = data["players"][uid]
    last = p.get("biz_last_collect", int(time.time()))
    hours = max(0, (int(time.time()) - last) // 3600)
    if hours < 1:
        return bot.reply_to(message, "⏳ Собирать можно раз в час.")
    income_per_hour = (p.get("biz_territory", 0) + 1) * p.get("biz_building", 1) * 50
    pending = income_per_hour * min(hours, 24)  # максимум 24 часа
    data["players"][uid]["biz_last_collect"] = int(time.time())
    add_balance(uid, pending)
    save_data()
    bot.reply_to(message, f"✅ Собрано **{pending} 🪙** с бизнеса!", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "бизнес территория")
def biz_territory_up(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    p = data["players"][uid]
    level = p.get("biz_territory", 0)
    if level >= 5:
        return bot.reply_to(message, "❌ Максимальный уровень территории.")
    cost = BIZ_TERRITORY_COST.get(level, 999999999)
    if get_balance(uid) < cost:
        return bot.reply_to(message, f"❌ Нужно **{cost} 🪙**")
    add_balance(uid, -cost)
    data["players"][uid]["biz_territory"] = level + 1
    save_data()
    bot.reply_to(message, f"✅ Территория улучшена до **{level + 1}**!", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "бизнес здание")
def biz_building_up(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    p = data["players"][uid]
    level = p.get("biz_building", 1)
    if level >= 5:
        return bot.reply_to(message, "❌ Максимальный уровень здания.")
    cost = BIZ_BUILDING_COST.get(level, 999999999)
    if get_balance(uid) < cost:
        return bot.reply_to(message, f"❌ Нужно **{cost} 🪙**")
    add_balance(uid, -cost)
    data["players"][uid]["biz_building"] = level + 1
    save_data()
    bot.reply_to(message, f"✅ Здание улучшено до **ур. {level + 1}**!", parse_mode="Markdown")

# ==================== КВЕСТЫ ====================

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "квесты")
def quests_cmd(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    text = ("📜 **КВЕСТЫ**\n━━━━━━━━━━━━━━━━━━━━\n"
            "1. Сыграть 5 игр — награда 2000 🪙\n"
            "2. Выиграть 3 раза — награда 3500 🪙\n"
            "3. Пополнить депозит — награда 1500 🪙\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "Квесты пока в разработке. Скоро появятся!")
    bot.reply_to(message, text, parse_mode="Markdown")

# ==================== КЛАНЫ ====================

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("создать клан "))
def create_clan(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    if data["players"][uid].get("clan_id"):
        return bot.reply_to(message, "❌ Вы уже в клане.")
    name = message.text.split(maxsplit=2)[2].strip()
    if len(name) < 3 or len(name) > 20:
        return bot.reply_to(message, "❌ Название от 3 до 20 символов.")
    if get_balance(uid) < 10000:
        return bot.reply_to(message, "❌ Нужно 10000 🪙 для создания клана.")
    add_balance(uid, -10000)
    clan_id = str(data.get("next_id", 1000))
    data["next_id"] = data.get("next_id", 1000) + 1
    data["clans"][clan_id] = {
        "name": name,
        "leader": uid,
        "members": [uid],
        "treasury": 0,
        "created": int(time.time())
    }
    data["players"][uid]["clan_id"] = clan_id
    data["players"][uid]["role"] = "leader"
    save_data()
    bot.reply_to(message, f"✅ Клан **{name}** создан!\n🆔 ID клана: `{clan_id}`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("вступить клан "))
def join_clan(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    if data["players"][uid].get("clan_id"):
        return bot.reply_to(message, "❌ Вы уже в клане.")
    try:
        clan_id = message.text.split()[2].strip()
    except:
        return bot.reply_to(message, "❌ Формат: `вступить клан ID`")
    if clan_id not in data["clans"]:
        return bot.reply_to(message, "❌ Клан не найден.")
    data["clans"][clan_id]["members"].append(uid)
    data["players"][uid]["clan_id"] = clan_id
    data["players"][uid]["role"] = "member"
    save_data()
    bot.reply_to(message, f"✅ Вы вступили в клан **{data['clans'][clan_id]['name']}**!", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "мой клан")
def my_clan(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    clan_id = data["players"][uid].get("clan_id")
    if not clan_id or clan_id not in data["clans"]:
        return bot.reply_to(message, "❌ Вы не состоите в клане.\nСоздайте: `создать клан ИМЯ`")
    clan = data["clans"][clan_id]
    members = len(clan.get("members", []))
    text = (f"🛡 **КЛАН {clan['name']}**\n━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 ID: `{clan_id}`\n"
            f"👑 Лидер: {get_nick(clan['leader'])}\n"
            f"👥 Участников: {members}\n"
            f"💰 Казна: {clan.get('treasury', 0)} 🪙")
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "выйти из клана")
def leave_clan(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    clan_id = data["players"][uid].get("clan_id")
    if not clan_id or clan_id not in data["clans"]:
        return bot.reply_to(message, "❌ Вы не в клане.")
    clan = data["clans"][clan_id]
    if clan["leader"] == uid:
        return bot.reply_to(message, "❌ Лидер не может выйти. Передайте лидерство или распустите клан.")
    if uid in clan["members"]:
        clan["members"].remove(uid)
    data["players"][uid]["clan_id"] = None
    data["players"][uid]["role"] = "none"
    save_data()
    bot.reply_to(message, "✅ Вы вышли из клана.")

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "топ кланов")
def top_clans(message):
    clans = sorted(data["clans"].items(), key=lambda x: len(x[1].get("members", [])), reverse=True)[:10]
    if not clans:
        return bot.reply_to(message, "Пока нет кланов.")
    text = "🏆 **ТОП КЛАНОВ**\n━━━━━━━━━━━━━━━━━━━━\n"
    for i, (cid, c) in enumerate(clans, 1):
        text += f"{i}. {c['name']} — {len(c.get('members', []))} чел.\n"
    bot.reply_to(message, text, parse_mode="Markdown")

# ==================== ДУЭЛИ ====================

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("дуэль "))
def duel_challenge(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)

    parts = message.text.split()
    if len(parts) < 3:
        return bot.reply_to(message,
            "❌ Формат:\n`дуэль ID сумма`\n`дуэль @ник сумма`\n\nПример: `дуэль 15 5000`",
            parse_mode="Markdown")

    target_raw = parts[1]
    try:
        amount = int(parts[2].replace(" ", "").replace(",", ""))
    except:
        return bot.reply_to(message, "❌ Сумма должна быть числом.")

    if amount < 100:
        return bot.reply_to(message, "❌ Минимальная ставка — 100 🪙")
    if amount > 10_000_000:
        return bot.reply_to(message, "❌ Максимальная ставка — 10 000 000 🪙")

    target_uid = None
    if target_raw.startswith("@"):
        target_uid = get_user_by_username(target_raw)
    else:
        try:
            sid = int(target_raw)
            target_uid = get_user_by_short_id(sid)
        except:
            pass

    if not target_uid:
        return bot.reply_to(message, "❌ Игрок не найден.")

    target_uid = str(target_uid)

    if target_uid == uid:
        return bot.reply_to(message, "❌ Нельзя вызвать самого себя.")

    if get_balance(uid) < amount:
        return bot.reply_to(message, "❌ У тебя недостаточно средств.")
    if get_balance(target_uid) < amount:
        return bot.reply_to(message, "❌ У соперника недостаточно средств.")

    for d in data["duels"].values():
        if d["status"] == "pending":
            participants = [d["challenger"], d["opponent"]]
            if uid in participants or target_uid in participants:
                return bot.reply_to(message, "❌ У одного из вас уже есть активный вызов.")

    duel_id = str(int(time.time() * 1000))
    data["duels"][duel_id] = {
        "challenger": uid,
        "opponent": target_uid,
        "amount": amount,
        "status": "pending",
        "created": int(time.time())
    }
    save_data()

    amount_str = f"{amount:,}".replace(",", " ")
    challenger_name = get_nick(uid)

    try:
        bot.send_message(
            int(target_uid),
            f"⚔️ **ВЫЗОВ НА ДУЭЛЬ**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 **{challenger_name}** вызывает тебя!\n"
            f"💰 Ставка: **{amount_str} 🪙**\n"
            f"🏆 Победитель забирает всё\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Чтобы принять — напиши: `принять` или `го`\n"
            f"Чтобы отклонить — напиши: `отклонить`\n\n"
            f"У тебя **2 минуты**.",
            parse_mode="Markdown"
        )
    except Exception:
        del data["duels"][duel_id]
        save_data()
        return bot.reply_to(message, "❌ Не удалось отправить вызов.\nСоперник, скорее всего, ещё не запускал бота.")

    bot.reply_to(message,
        f"⚔️ Вызов отправлен **{get_nick(target_uid)}**\n"
        f"Ставка: **{amount_str} 🪙**\n"
        f"Ожидай ответа...",
        parse_mode="Markdown")

    def auto_cancel(duel_id=duel_id, uid=uid, target_uid=target_uid):
        time.sleep(120)
        if duel_id in data["duels"] and data["duels"][duel_id]["status"] == "pending":
            data["duels"][duel_id]["status"] = "expired"
            save_data()
            try:
                bot.send_message(int(uid), "⌛️ Твой вызов на дуэль истёк (соперник не ответил).")
                bot.send_message(int(target_uid), "⌛️ Вызов на дуэль истёк.")
            except:
                pass

    threading.Thread(target=auto_cancel, daemon=True).start()

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() in ["принять", "го", "accept", "да", "yes", "ок", "ok"])
def duel_accept_text(message):
    uid = str(message.from_user.id)
    duel_id, duel = find_pending_duel_for(uid)

    if not duel:
        return bot.reply_to(message, "❌ У тебя нет входящих вызовов на дуэль.")

    challenger = duel["challenger"]
    opponent = duel["opponent"]
    amount = duel["amount"]

    if get_balance(challenger) < amount or get_balance(opponent) < amount:
        duel["status"] = "cancelled"
        save_data()
        return bot.reply_to(message, "❌ Недостаточно средств у одного из игроков. Дуэль отменена.")

    add_balance(challenger, -amount)
    add_balance(opponent, -amount)

    duel["status"] = "active"
    save_data()

    bot.reply_to(message, "⚔️ Дуэль принята! Идёт бой...")
    try:
        bot.send_message(int(challenger), f"⚔️ **{get_nick(opponent)}** принял твой вызов! Идёт бой...")
    except:
        pass

    time.sleep(1.5)

    mult_ch = get_win_multiplier(challenger)
    mult_op = get_win_multiplier(opponent)

    weight_ch = 50 * mult_ch
    weight_op = 50 * mult_op
    total = weight_ch + weight_op
    roll = random.uniform(0, total)

    if roll < weight_ch:
        winner = challenger
        loser = opponent
    else:
        winner = opponent
        loser = challenger

    resolve_duel(duel_id, duel, winner, loser)

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() in ["отклонить", "нет", "no", "отмена", "cancel"])
def duel_reject_text(message):
    uid = str(message.from_user.id)
    duel_id, duel = find_pending_duel_for(uid)

    if not duel:
        return bot.reply_to(message, "❌ У тебя нет входящих вызовов на дуэль.")

    duel["status"] = "rejected"
    save_data()

    bot.reply_to(message, "❌ Ты отклонил вызов.")
    try:
        bot.send_message(int(duel["challenger"]), f"❌ **{get_nick(uid)}** отклонил твой вызов на дуэль.")
    except:
        pass

# ==================== АДМИН-ПАНЕЛЬ ====================

@bot.message_handler(commands=['admin'])
@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() in ['админ', 'админка'])
def admin_panel(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("📊 Статистика", callback_data="adm_stats"),
           InlineKeyboardButton("💰 Выдать деньги", callback_data="adm_give"))
    kb.add(InlineKeyboardButton("👑 Выдать статус", callback_data="adm_setstatus"),
           InlineKeyboardButton("🗑 Обнулить игрока", callback_data="adm_reset"))
    kb.add(InlineKeyboardButton("🎁 Создать промо", callback_data="adm_promo"),
           InlineKeyboardButton("❌ Удалить промо", callback_data="adm_delpromo"))
    kb.add(InlineKeyboardButton("📢 Рассылка", callback_data="adm_broadcast"))
    bot.reply_to(message, "⚙️ **АДМИН-ПАНЕЛЬ**\n━━━━━━━━━━━━━━━━━━━━\nВыберите действие:", reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_"))
def admin_callbacks(call):
    if call.from_user.id not in ADMIN_IDS:
        return bot.answer_callback_query(call.id, "❌ Нет прав.")
    
    act = call.data.split("_")[1]

    if act == "stats":
        total_players = len(data["players"])
        total_money = sum(p.get("balance", 0) for p in data["players"].values())
        total_clans = len(data["clans"])
        text = f"📊 **СТАТИСТИКА**\n━━━━━━━━━━━━━━━━━━━━\n👥 Игроков: {total_players}\n💰 Общий баланс: {total_money} 🪙\n🛡 Кланов: {total_clans}"
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("⬅️ Назад", callback_data="adm_back"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode="Markdown")
        bot.answer_callback_query(call.id)

    elif act == "give":
        msg = bot.send_message(call.message.chat.id, "Введите `ID СУММА`\nПример: `3 5000`")
        bot.register_next_step_handler(msg, admin_give_step)
        bot.answer_callback_query(call.id)

    elif act == "setstatus":
        msg = bot.send_message(call.message.chat.id, "Введите `ID СТАТУС`\nПример: `3 Ultra`\nДоступные: VIP, Premium, Ultra, Нет")
        bot.register_next_step_handler(msg, admin_setstatus_step)
        bot.answer_callback_query(call.id)

    elif act == "reset":
        msg = bot.send_message(call.message.chat.id, "Введите ID игрока для обнуления:")
        bot.register_next_step_handler(msg, admin_reset_step)
        bot.answer_callback_query(call.id)

    elif act == "promo":
        msg = bot.send_message(call.message.chat.id, "Введите `КОД СУММА КОЛИЧЕСТВО`\nПример: `SUMMER 5000 100`")
        bot.register_next_step_handler(msg, admin_promo_step)
        bot.answer_callback_query(call.id)

    elif act == "delpromo":
        msg = bot.send_message(call.message.chat.id, "Введите код промо для удаления:")
        bot.register_next_step_handler(msg, admin_delpromo_step)
        bot.answer_callback_query(call.id)

    elif act == "broadcast":
        msg = bot.send_message(call.message.chat.id, "Введите текст рассылки:")
        bot.register_next_step_handler(msg, admin_broadcast_step)
        bot.answer_callback_query(call.id)

    elif act == "back":
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(InlineKeyboardButton("📊 Статистика", callback_data="adm_stats"),
               InlineKeyboardButton("💰 Выдать деньги", callback_data="adm_give"))
        kb.add(InlineKeyboardButton("👑 Выдать статус", callback_data="adm_setstatus"),
               InlineKeyboardButton("🗑 Обнулить игрока", callback_data="adm_reset"))
        kb.add(InlineKeyboardButton("🎁 Создать промо", callback_data="adm_promo"),
               InlineKeyboardButton("❌ Удалить промо", callback_data="adm_delpromo"))
        kb.add(InlineKeyboardButton("📢 Рассылка", callback_data="adm_broadcast"))
        bot.edit_message_text("⚙️ **АДМИН-ПАНЕЛЬ**\n━━━━━━━━━━━━━━━━━━━━\nВыберите действие:",
                              call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode="Markdown")
        bot.answer_callback_query(call.id)

def admin_give_step(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        parts = message.text.split()
        sid = int(parts[0])
        amount = int(parts[1])
        target = get_user_by_short_id(sid)
        if not target:
            return bot.reply_to(message, "❌ Игрок не найден.")
        add_balance(target, amount)
        bot.reply_to(message, f"✅ Выдано **{amount} 🪙** игроку `{sid}`", parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Формат: `ID СУММА`")

def admin_setstatus_step(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        parts = message.text.split()
        sid = int(parts[0])
        status = parts[1]
        if status not in ["VIP", "Premium", "Ultra", "Нет"]:
            return bot.reply_to(message, "❌ Статус: VIP / Premium / Ultra / Нет")
        target = get_user_by_short_id(sid)
        if not target:
            return bot.reply_to(message, "❌ Игрок не найден.")
        data["players"][str(target)]["donate_status"] = status
        save_data()
        bot.reply_to(message, f"✅ Игроку `{sid}` выдан статус **{status}**", parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Формат: `ID СТАТУС`")

def admin_reset_step(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        sid = int(message.text.strip())
        target = get_user_by_short_id(sid)
        if not target:
            return bot.reply_to(message, "❌ Игрок не найден.")
        data["players"][str(target)]["balance"] = 0
        data["players"][str(target)]["bank"] = 0
        data["players"][str(target)]["deposit"] = 0
        save_data()
        bot.reply_to(message, f"✅ Игрок `{sid}` обнулён.", parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Введите ID.")

def admin_promo_step(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        parts = message.text.split()
        code = parts[0].upper()
        amount = int(parts[1])
        uses = int(parts[2])
        data["promos"][code] = {"amount": amount, "uses": uses, "activated": []}
        save_data()
        bot.reply_to(message, f"✅ Промо `{code}` создан.\nСумма: {amount} 🪙\nАктиваций: {uses}", parse_mode="Markdown")
    except:
        bot.reply_to(message, "❌ Формат: `КОД СУММА КОЛИЧЕСТВО`")

def admin_delpromo_step(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    code = message.text.strip().upper()
    if code in data["promos"]:
        del data["promos"][code]
        save_data()
        bot.reply_to(message, f"✅ Промо `{code}` удалён.", parse_mode="Markdown")
    else:
        bot.reply_to(message, "❌ Промо не найден.")

def admin_broadcast_step(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    text = message.text
    count = 0
    for uid in list(data["players"].keys()):
        try:
            bot.send_message(int(uid), text)
            count += 1
            time.sleep(0.05)
        except:
            pass
    bot.reply_to(message, f"✅ Рассылка отправлена {count} игрокам.")


# ==================== АДМИН-КОМАНДЫ /give и /reset ====================

@bot.message_handler(commands=['give'])
def admin_give_cmd(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        parts = message.text.split()
        if len(parts) < 3:
            return bot.reply_to(message, "❌ Формат: `/give ID сумма`\nПример: `/give 15 50000`", parse_mode="Markdown")
        sid = int(parts[1])
        amount = int(parts[2].replace(" ", "").replace(",", ""))
        target = get_user_by_short_id(sid)
        if not target:
            return bot.reply_to(message, "❌ Игрок не найден.")
        add_balance(target, amount)
        amount_str = f"{amount:,}".replace(",", " ")
        bot.reply_to(message, f"✅ Выдано **{amount_str} 🪙** игроку `{sid}`", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}\nФормат: `/give ID сумма`", parse_mode="Markdown")


@bot.message_handler(commands=['reset'])
def admin_reset_cmd(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        parts = message.text.split()
        if len(parts) < 2:
            return bot.reply_to(message, "❌ Формат: `/reset ID`\nПример: `/reset 15`", parse_mode="Markdown")
        sid = int(parts[1])
        target = get_user_by_short_id(sid)
        if not target:
            return bot.reply_to(message, "❌ Игрок не найден.")
        uid = str(target)
        data["players"][uid]["balance"] = 0
        data["players"][uid]["bank"] = 0
        data["players"][uid]["deposit"] = 0
        data["players"][uid]["deposit_start"] = 0
        save_data()
        bot.reply_to(message, f"✅ Игрок `{sid}` полностью обнулён (баланс + банк + депозит).", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}\nФормат: `/reset ID`", parse_mode="Markdown")


# ==================== ЗАПУСК ====================

print("Бот запущен...")
bot.infinity_polling()
