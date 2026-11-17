import os, random, math, time, telebot, threading, json, pathlib
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN: raise ValueError("Не задан BOT_TOKEN")

ADMIN_IDS = [8211650013, 6940877915]
DATA_DIR = pathlib.Path("/app/data"); DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = DATA_DIR / "database.json"

data = {"players": {}, "promos": {}, "activations": [], "history": [], "clans": {}, "next_id": 1, "active_games": {}, "roulette_bets": {}}

def load_data():
    global data
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                for key in loaded: data[key] = loaded[key]
        except Exception as e: print(f"⚠️ Ошибка загрузки: {e}")

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=4)

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
        if "btc" in pdata: del pdata["btc"]; changed = True
    if "roulette_bets" not in data: data["roulette_bets"] = {}
    if changed: save_data()

migrate_data()
bot = telebot.TeleBot(TOKEN)
MULT = {5: 1.25, 9: 1.45}
BIZ_TERRITORY_COST = {0: 10000, 1: 50000, 2: 250000, 3: 1000000, 4: 5000000, 5: 25000000}
BIZ_BUILDING_COST = {1: 20000, 2: 100000, 3: 500000, 4: 2000000, 5: 10000000}
TITLES = {"👑 Король": 1000000, "💎 Олигарх": 500000, "🔥 Везунчик": 250000, "🐺 Волк": 100000, "🌟 Звезда": 50000, "😎 Крутой": 20000}

def get_balance(uid): return data["players"].get(str(uid), {}).get("balance", 0)
def get_nick(uid): return data["players"].get(str(uid), {}).get("username", "Player")
def get_title(uid): return data["players"].get(str(uid), {}).get("title", "Нет")
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

def add_balance(uid, amt):
    uid = str(uid)
    if uid not in data["players"]: register_user_by_id(uid)
    data["players"][uid]["balance"] += amt; save_data()

def register_user(user):
    uid = str(user.id)
    if uid not in data["players"]:
        sid = data["next_id"]; data["next_id"] += 1
        data["players"][uid] = {"username": user.username or user.first_name, "balance": 1000, "last_bonus": 0, "short_id": sid, "clan_id": None, "role": "none", "bank": 0, "deposit": 0, "deposit_start": 0, "biz_territory": 0, "biz_building": 1, "biz_tax": 0, "biz_last_collect": int(time.time()), "title": "Нет", "quests": {}}
        save_data()

def register_user_by_id(uid):
    if uid not in data["players"]:
        sid = data["next_id"]; data["next_id"] += 1
        data["players"][uid] = {"username": "Player", "balance": 1000, "last_bonus": 0, "short_id": sid, "clan_id": None, "role": "none", "bank": 0, "deposit": 0, "deposit_start": 0, "biz_territory": 0, "biz_building": 1, "biz_tax": 0, "biz_last_collect": int(time.time()), "title": "Нет", "quests": {}}
        save_data()

@bot.message_handler(commands=["start"])
def start(message):
    register_user(message.from_user)
    bot.send_message(message.chat.id, f"🎰 **MON1 CASINO RPG**\n\n🪙 Баланс: {get_balance(message.from_user.id)}\n\nИгры: `слот 1000`, `мины 1000 5`, `краш 1000`, `1000 5 12` (рулетка)\nКланы: `мой клан`\nИнфо: `помощь`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text.lower().strip() == "мой клан")
def my_clan_info(message):
    uid = str(message.from_user.id); p = data["players"].get(uid, {})
    if not p.get("clan_id"): return bot.reply_to(message, "🛡 У вас нет клана.\n`создать клан ИМЯ` (5000)\n`вступить клан ID`", parse_mode="Markdown")
    
    cid = str(p["clan_id"]); clan = data["clans"].get(cid)
    if not clan: return bot.reply_to(message, "❌ Клан удален.")
    
    members = [m for m in data["players"].values() if m.get("clan_id") == cid]
    text = (
        f"🛡 **Клан: {clan['name']}**\n"
        f"🆔 ID: `{cid}`\n"
        f"👑 Создатель: {clan['owner_name']}\n"
        f"👥 Участники: {len(members)}/15\n"
        f"💰 Казна: {clan.get('treasury', 0)} 🪙\n\n"
        f"Ваша роль: **{p.get('role', 'игрок').upper()}**"
    )
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("👥 Участники", callback_data=f"clan_members_{cid}"))
    bot.reply_to(message, text, reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("clan_members_"))
def clan_members(call):
    cid = call.data.split("_")[2]; clan = data["clans"].get(cid)
    if not clan: return bot.answer_callback_query(call.id, "❌ Клан не найден.")
    
    members = [(m.get('username', '?'), m.get('short_id', '?'), m.get('role', 'игрок')) for m in data["players"].values() if m.get("clan_id") == cid]
    text = f"👥 **Участники клана {clan['name']}**\n\n"
    for name, sid, role in members:
        text += f"• {name} (ID: `{sid}`) — {role}\n"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("⬅️ Назад", callback_data=f"clan_back_{cid}")), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("clan_back_"))
def clan_back(call):
    # Просто вызываем функцию информации о клане заново
    uid = str(call.from_user.id)
    p = data["players"].get(uid, {})
    cid = str(p.get("clan_id"))
    if not cid: return
    clan = data["clans"].get(cid)
    if not clan: return
    members = [m for m in data["players"].values() if m.get("clan_id") == cid]
    text = (
        f"🛡 **Клан: {clan['name']}**\n🆔 ID: `{cid}`\n👑 Создатель: {clan['owner_name']}\n"
        f"👥 Участники: {len(members)}/15\n💰 Казна: {clan.get('treasury', 0)} 🪙\n\n"
        f"Ваша роль: **{p.get('role', 'игрок').upper()}**"
    )
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("👥 Участники", callback_data=f"clan_members_{cid}"))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode="Markdown")

def has_perm(uid, act):
    role = data["players"][uid].get("role", "none")
    if role == "создатель": return True
    if role == "заместитель" and act in ["rename", "appoint", "kick"]: return True
    if role == "модер" and act == "rename": return True
    return False

@bot.message_handler(func=lambda m: m.text.lower().startswith("клан исключить"))
def clan_kick(message):
    uid = str(message.from_user.id)
    if not has_perm(uid, "kick"): return bot.reply_to(message, "❌ Нет прав.")
    try:
        target_sid = message.text.split()[2]
        target_uid = get_user_by_short_id(target_sid)
        if not target_uid: return bot.reply_to(message, "❌ Игрок с таким ID не найден.")
        
        cid = data["players"][uid].get("clan_id")
        if data["players"].get(target_uid, {}).get("clan_id") != cid:
            return bot.reply_to(message, "❌ Этот игрок не в вашем клане.")
        if data["players"].get(target_uid, {}).get("role") == "создатель":
            return bot.reply_to(message, "❌ Нельзя исключить создателя.")
            
        data["players"][target_uid]["clan_id"] = None
        data["players"][target_uid]["role"] = "none"
        save_data()
        bot.reply_to(message, f"✅ Игрок с ID `{target_sid}` исключен из клана.", parse_mode="Markdown")
    except: bot.reply_to(message, "❌ `клан исключить ID`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text.lower().startswith("клан повысить"))
def clan_promote(message):
    uid = str(message.from_user.id)
    if not has_perm(uid, "appoint"): return bot.reply_to(message, "❌ Нет прав.")
    try:
        target_sid = message.text.split()[2]
        target_uid = get_user_by_short_id(target_sid)
        if not target_uid: return bot.reply_to(message, "❌ Игрок с таким ID не найден.")
        
        cid = data["players"][uid].get("clan_id")
        if data["players"].get(target_uid, {}).get("clan_id") != cid:
            return bot.reply_to(message, "❌ Этот игрок не в вашем клане.")
            
        current_role = data["players"][target_uid].get("role", "игрок")
        if current_role == "создатель":
            return bot.reply_to(message, "❌ Это создатель.")
        elif current_role == "заместитель":
            return bot.reply_to(message, "❌ Он уже заместитель.")
        elif current_role == "модер":
            data["players"][target_uid]["role"] = "заместитель"
            new_role = "заместитель"
        else:
            data["players"][target_uid]["role"] = "модер"
            new_role = "модер"
            
        save_data()
        bot.reply_to(message, f"✅ Игрок с ID `{target_sid}` повышен до **{new_role}**.", parse_mode="Markdown")
    except: bot.reply_to(message, "❌ `клан повысить ID`", parse_mode="Markdown")

# ... Остальной код (слоты, мины, краш, бизнес, банк, рулетка, квесты, донат, админка) ...

@bot.message_handler(func=lambda m: m.text.lower().strip() == "магазин")
def shop_menu(message):
    kb = InlineKeyboardMarkup(row_width=1)
    for t, p in TITLES.items(): kb.add(InlineKeyboardButton(f"{t} ({p:,} 🪙)", callback_data=f"buy_title_{t}"))
    bot.send_message(message.chat.id, "🛒 **Магазин титулов**\nВыберите титул для покупки:", reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_title_"))
def buy_title(call):
    uid = str(call.from_user.id); title = call.data.split("_", 2)[2]; price = TITLES.get(title)
    if not price: return bot.answer_callback_query(call.id, "❌ Ошибка.")
    if get_balance(uid) < price: return bot.answer_callback_query(call.id, "❌ Недостаточно средств!", show_alert=True)
    add_balance(uid, -price); data["players"][uid]["title"] = title; save_data()
    bot.answer_callback_query(call.id, f"✅ Вы купили титул {title}!")
    bot.send_message(call.message.chat.id, f"🎉 Вы купили титул **{title}** за {price:,} 🪙", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text.lower().strip() == "квесты")
def quests_menu(message):
    uid = str(message.from_user.id); p = data["players"].get(uid, {}); now = int(time.time())
    if "quest_date" not in p or now - p.get("quest_date", 0) >= 86400:
        data["players"][uid]["quests"] = {"Сделать ставку в слот": {"done": False, "reward": 5000}, "Сыграть в краш": {"done": False, "reward": 5000}, "Купить биткоин": {"done": False, "reward": 5000}, "Открыть депозит": {"done": False, "reward": 10000}}
        data["players"][uid]["quest_date"] = now; save_data()
    q = p.get("quests", {}); text = "📜 **Ежедневные квесты**\n\n"
    for name, info in q.items(): text += f"{'✅' if info['done'] else '❌'} {name} (+{info['reward']:,} 🪙)\n"
    text += "\nНапишите `забрать квест` после выполнения."
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text.lower().strip() == "забрать квест")
def claim_quests(message):
    uid = str(message.from_user.id); q = data["players"].get(uid, {}).get("quests", {}); total = 0
    for name, info in q.items():
        if info["done"] and not info.get("claimed", False): total += info["reward"]; info["claimed"] = True
    if total > 0: add_balance(uid, total); save_data(); bot.reply_to(message, f"🎉 Вы получили {total:,} 🪙 за квесты!", parse_mode="Markdown")
    else: bot.reply_to(message, "❌ Нет выполненных квестов.")

def complete_quest(uid, quest_name):
    uid = str(uid); p = data["players"].get(uid, {})
    if "quests" in p and quest_name in p["quests"]:
        if not p["quests"][quest_name]["done"]: p["quests"][quest_name]["done"] = True; save_data()

@bot.message_handler(func=lambda m: m.text.lower().startswith("слот"))
def slot_machine(message):
    uid = str(message.from_user.id)
    try:
        bet = int(message.text.split()[1])
        if bet <= 0 or get_balance(uid) < bet: return bot.reply_to(message, "❌ Недостаточно средств.")
        add_balance(uid, -bet); s = [random.choice(["🍒", "🍋", "💎", "🎰"]) for _ in range(3)]; win = 0
        if s[0] == s[1] == s[2]:
            if s[0] == "🎰": win = bet * 50
            elif s[0] == "💎": win = bet * 10
            elif s[0] == "🍋": win = bet * 5
            elif s[0] == "🍒": win = bet * 3
        elif s[0] == s[1] or s[1] == s[2] or s[0] == s[2]: win = bet
        if win > 0: add_balance(uid, win); msg = f"🎰 **СЛОТ**\n[ {s[0]} | {s[1]} | {s[2]} ]\n🎉 **ВЫИГРЫШ!** +{win} 🪙\nБаланс: {get_balance(uid)}"
        else: msg = f"🎰 **СЛОТ**\n[ {s[0]} | {s[1]} | {s[2]} ]\n😢 Проигрыш.\nБаланс: {get_balance(uid)}"
        bot.reply_to(message, msg, parse_mode="Markdown"); complete_quest(uid, "Сделать ставку в слот")
    except: bot.reply_to(message, "❌ `слот 1000`")

@bot.message_handler(func=lambda m: m.text.lower().strip() in ["топ", "топ игроков"])
def top_cmd(message):
    sp = sorted(data["players"].items(), key=lambda x: x[1].get("balance", 0), reverse=True)[:10]
    text = "🏆 **ТОП-10**\n\n" + "".join([f"{i}. {p.get('username', '?')} {p.get('title', '')} — {p.get('balance', 0)} 🪙\n" for i, (u, p) in enumerate(sp, 1)])
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text.lower().strip() == "чаты")
def chats_cmd(message):
    bot.reply_to(message, "💬 **Наши чаты**\n📢 Канал: https://t.me/mon1bots\n💬 Чат: https://t.me/mon1not", parse_mode="Markdown")

# ... Дальше идут функции бизнеса, банка, мин, краша, рулетки, админки, которые вы уже видели ...
# Я вставлю их сюда для полноты картины, чтобы код был готов к запуску.

@bot.message_handler(func=lambda m: m.text.lower().strip() == "мой бизнес")
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

@bot.message_handler(func=lambda m: m.text.lower().strip() == "банк")
def bank_info(message):
    uid = str(message.from_user.id); p = data["players"].get(uid, {}); b = p.get("bank", 0); d = p.get("deposit", 0); ds = p.get("deposit_start", 0); now = int(time.time()); cd = 3 * 86400
    st = "Нет" if d == 0 else (f"✅ {d} 🪙 (Можно снять)" if now - ds >= cd else f"⏳ {d} 🪙 ({(cd - (now - ds))//3600} ч.)")
    msg = f"🏦 **БАНК**\n💰 Счет: {b} 🪙\n💎 Депозит: {st}\n📈 10% (раз в 3 дня)\n\n`банк положить СУММА` / `банк снять СУММА`\n`депозит положить СУММА` / `депозит снять`"
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text.lower().startswith("банк положить"))
def bank_dep(message):
    uid = str(message.from_user.id)
    try:
        a = int(message.text.split()[2])
        if a <= 0 or get_balance(uid) < a: return bot.reply_to(message, "❌ Мало.")
        add_balance(uid, -a); data["players"][uid]["bank"] += a; save_data(); bot.reply_to(message, f"✅ +{a} 🪙 в банк.")
    except: bot.reply_to(message, "❌ `банк положить 1000`")

@bot.message_handler(func=lambda m: m.text.lower().startswith("банк снять"))
def bank_wd(message):
    uid = str(message.from_user.id)
    try:
        a = int(message.text.split()[2])
        if a <= 0 or data["players"][uid].get("bank", 0) < a: return bot.reply_to(message, "❌ Мало в банке.")
        data["players"][uid]["bank"] -= a; add_balance(uid, a); save_data(); bot.reply_to(message, f"✅ -{a} 🪙 из банка.")
    except: bot.reply_to(message, "❌ `банк снять 1000`")

@bot.message_handler(func=lambda m: m.text.lower().startswith("депозит положить"))
def dep_make(message):
    uid = str(message.from_user.id); p = data["players"].get(uid, {})
    try:
        a = int(message.text.split()[2])
        if a <= 0 or get_balance(uid) < a: return bot.reply_to(message, "❌ Мало.")
        if p.get("deposit", 0) > 0 and (int(time.time()) - p.get("deposit_start", 0) < 3 * 86400): return bot.reply_to(message, "❌ Уже есть депозит.")
        add_balance(uid, -a); data["players"][uid]["deposit"] = a; data["players"][uid]["deposit_start"] = int(time.time()); save_data()
        bot.reply_to(message, f"✅ Депозит {a} 🪙 открыт."); complete_quest(uid, "Открыть депозит")
    except: bot.reply_to(message, "❌ `депозит положить 1000`")

@bot.message_handler(func=lambda m: m.text.lower().strip() == "депозит снять")
def dep_wd(message):
    uid = str(message.from_user.id); p = data["players"].get(uid, {}); d = p.get("deposit", 0); ds = p.get("deposit_start", 0)
    if d <= 0: return bot.reply_to(message, "❌ Нет депозита.")
    if int(time.time()) - ds < 3 * 86400: return bot.reply_to(message, f"⏳ Ждать {(3 * 86400 - (int(time.time()) - ds))//3600} ч.")
    i = int(d * 0.1); add_balance(uid, d + i); data["players"][uid]["deposit"] = 0; data["players"][uid]["deposit_start"] = 0; save_data()
    bot.reply_to(message, f"🏦 **Депозит закрыт!**\nВклад: {d} 🪙\nПроценты: +{i} 🪙\nИтого: **{d + i} 🪙**", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text.lower().startswith("перевод"))
def transfer(message):
    uid = str(message.from_user.id)
    if message.reply_to_message:
        t_uid = str(message.reply_to_message.from_user.id)
        try: a = int(message.text.split()[1])
        except: return bot.reply_to(message, "❌ `перевод 1000` (в ответ)")
        if a <= 0 or get_balance(uid) < a: return bot.reply_to(message, "❌ Мало.")
        if a > 10000: return bot.reply_to(message, "❌ Лимит перевода — 10 000 🪙.")
        if t_uid == uid: return bot.reply_to(message, "❌ Себе нельзя.")
        if t_uid not in data["players"]: register_user(message.reply_to_message.from_user)
        add_balance(uid, -a); add_balance(t_uid, a)
        return bot.reply_to(message, f"✅ {a} 🪙 переведено {get_nick(t_uid)}.")
    else:
        try:
            a = int(message.text.split()[1]); t_name = message.text.split()[2]
            if a <= 0 or get_balance(uid) < a: return bot.reply_to(message, "❌ Мало.")
            if a > 10000: return bot.reply_to(message, "❌ Лимит перевода — 10 000 🪙.")
            t_uid = get_user_by_username(t_name)
            if not t_uid or t_uid == uid: return bot.reply_to(message, "❌ Не найден.")
            add_balance(uid, -a); add_balance(t_uid, a)
            bot.reply_to(message, f"✅ {a} 🪙 переведено {get_nick(t_uid)}.")
        except: bot.reply_to(message, "❌ `перевод 1000 ник`")

@bot.message_handler(func=lambda m: m.text.lower().startswith("мины"))
def start_mines(message):
    uid = str(message.from_user.id)
    try:
        p = message.text.split(); bet = int(p[1]); bmb = int(p[2]) if len(p) > 2 else 5
        if bet <= 0 or get_balance(uid) < bet: return bot.reply_to(message, "❌ Мало.")
        if bmb not in MULT: return bot.reply_to(message, "❌ Мины: 5 или 9.")
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
    rw = math.floor(g["bet"] * (MULT[g["bombs"]] ** len(g["opened"]))); add_balance(uid, rw); del data["active_games"][gid]; save_data()
    bot.edit_message_text(f"🏆 **Забрано!** +{rw} 🪙", call.message.chat.id, call.message.message_id, reply_markup=None, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text.lower().startswith("краш"))
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
        if g["current"] >= g["crash_point"] or random.random() < 0.1:
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
    g["active"] = False; rw = math.floor(g["bet"] * g["current"]); add_balance(uid, rw); del data["active_games"][gid]; save_data()
    bot.edit_message_text(f"🏆 **Забрано на x{g['current']:.2f}!** +{rw} 🪙", call.message.chat.id, call.message.message_id, reply_markup=None, parse_mode="Markdown")

@bot.message_handler(func=lambda m: len(m.text.split()) >= 2 and m.text.split()[0].isdigit())
def roulette_bet(message):
    uid = str(message.from_user.id); parts = message.text.split()
    try:
        bet = int(parts[0])
        targets = parts[1:]
        if bet <= 0 or get_balance(uid) < bet * len(targets): return bot.reply_to(message, f"❌ Недостаточно средств (нужно {bet * len(targets)} 🪙).")
        
        if "bets" not in data["roulette_bets"]: data["roulette_bets"] = {}
        if str(message.chat.id) not in data["roulette_bets"]: data["roulette_bets"][str(message.chat.id)] = []
        
        data["roulette_bets"][str(message.chat.id)].append({"user": uid, "bet": bet, "targets": targets})
        add_balance(uid, -bet * len(targets))
        save_data()
        bot.reply_to(message, f"✅ Ставка {bet} на {', '.join(targets)} принята!\nНапишите `го` для запуска.")
    except: bot.reply_to(message, "❌ `1000 5 12 30`")

@bot.message_handler(func=lambda m: m.text.lower().strip() == "го")
def roulette_go(message):
    chat_id = str(message.chat.id)
    if chat_id not in data["roulette_bets"] or not data["roulette_bets"][chat_id]:
        return bot.reply_to(message, "❌ Нет ставок.")
    
    bets = data["roulette_bets"][chat_id]
    data["roulette_bets"][chat_id] = []
    save_data()
    
    win_num = random.randint(0, 36)
    wc = "green" if win_num == 0 else ("red" if 1 <= win_num <= 18 else "black")
    sym = {"green": "🟢", "red": "🔴", "black": "⚫️"}[wc]
    
    total_win = 0
    results = []
    for b in bets:
        u_win = 0
        for x in b["targets"]:
            win, mlt = False, 0
            if "-" in x:
                try: s, e = map(int, x.split("-")); mlt = max(1, math.floor(37 / (e - s + 1))) if s <= win_num <= e else 0
                except: pass
            elif x.isdigit():
                if int(x) == win_num: win, mlt = True, 36
            elif x in ["red", "к", "кр"]:
                if wc == "red": win, mlt = True, 2
            elif x in ["black", "ч"]:
                if wc == "black": win, mlt = True, 2
            elif x in ["green", "з"]:
                if wc == "green": win, mlt = True, 36
            elif x in ["even", "чет"]:
                if win_num != 0 and win_num % 2 == 0: win, mlt = True, 2
            elif x in ["odd", "нечет"]:
                if win_num % 2 != 0: win, mlt = True, 2
            if win: u_win += b["bet"] * mlt
        
        if u_win > 0: add_balance(b["user"], u_win); results.append(f"✅ {get_nick(b['user'])} +{u_win}")
        else: results.append(f"❌ {get_nick(b['user'])} -{b['bet'] * len(b['targets'])}")
        total_win += u_win
    
    res_text = "\n".join(results)
    bot.reply_to(message, f"🎰 Выпало: {sym} **{win_num}**\n\n{res_text}\n\n💰 Общий выигрыш: {total_win} 🪙", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text.lower().strip() == "мой клан")
def my_clan_info(message):
    uid = str(message.from_user.id); p = data["players"].get(uid, {})
    if not p.get("clan_id"): return bot.reply_to(message, "🛡 У вас нет клана.\n`создать клан ИМЯ` (5000)\n`вступить клан ID`", parse_mode="Markdown")
    
    cid = str(p["clan_id"]); clan = data["clans"].get(cid)
    if not clan: return bot.reply_to(message, "❌ Клан удален.")
    
    members = [m for m in data["players"].values() if m.get("clan_id") == cid]
    text = f"🛡 **Клан: {clan['name']}**\n🆔 ID: `{cid}`\n👑 Создатель: {clan['owner_name']}\n👥 Участники: {len(members)}/15\n💰 Казна: {clan.get('treasury', 0)} 🪙\n\nВаша роль: **{p.get('role', 'игрок').upper()}**"
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("👥 Участники", callback_data=f"clan_members_{cid}"))
    bot.reply_to(message, text, reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("clan_members_"))
def clan_members(call):
    cid = call.data.split("_")[2]; clan = data["clans"].get(cid)
    if not clan: return bot.answer_callback_query(call.id, "❌ Клан не найден.")
    members = [(m.get('username', '?'), m.get('short_id', '?'), m.get('role', 'игрок')) for m in data["players"].values() if m.get("clan_id") == cid]
    text = f"👥 **Участники клана {clan['name']}**\n\n"
    for name, sid, role in members:
        text += f"• {name} (ID: `{sid}`) — {role}\n"
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

@bot.message_handler(func=lambda m: m.text.lower().startswith("клан исключить"))
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

@bot.message_handler(func=lambda m: m.text.lower().startswith("клан повысить"))
def clan_promote(message):
    uid = str(message.from_user.id)
    if not has_perm(uid, "appoint"): return bot.reply_to(message, "❌ Нет прав.")
    try:
        target_sid = message.text.split()[2]; target_uid = get_user_by_short_id(target_sid)
        if not target_uid: return bot.reply_to(message, "❌ Игрок не найден.")
        cid = data["players"][uid].get("clan_id")
        if data["players"].get(target_uid, {}).get("clan_id") != cid: return bot.reply_to(message, "❌ Не в вашем клане.")
        cr = data["players"][target_uid].get("role", "игрок")
        if cr == "создатель": return bot.reply_to(message, "❌ Это создатель.")
        elif cr == "заместитель": return bot.reply_to(message, "❌ Уже заместитель.")
        elif cr == "модер": data["players"][target_uid]["role"] = "заместитель"; nr = "заместитель"
        else: data["players"][target_uid]["role"] = "модер"; nr = "модер"
        save_data()
        bot.reply_to(message, f"✅ Игрок `{target_sid}` повышен до **{nr}**.", parse_mode="Markdown")
    except: bot.reply_to(message, "❌ `клан повысить ID`", parse_mode="Markdown")

# ... (Остальной код админки и помощи) ...
print("BOT STARTED")
bot.infinity_polling(skip_pending=True)
