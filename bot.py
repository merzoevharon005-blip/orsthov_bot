import os, random, math, time, telebot, threading, json, pathlib
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN: raise ValueError("Не задан BOT_TOKEN")

ADMIN_IDS = [8211650013, 6940877915] 
DATA_DIR = pathlib.Path("/app/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = DATA_DIR / "database.json"

data = {"players": {}, "promos": {}, "activations": [], "history": [], "transfers": [], "clans": {}, "clan_bosses": {}}

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
bot = telebot.TeleBot(TOKEN)
mines_games, crash_games = {}, {}

def get_balance(user_id):
    uid = str(user_id)
    return data["players"].get(uid, {}).get("balance", 0)

def get_nick(user_id):
    uid = str(user_id)
    return data["players"].get(uid, {}).get("username", "Player")

def get_user_short_id(user_id):
    uid = str(user_id)
    return data["players"].get(uid, {}).get("short_id", "0")

def add_balance(user_id, amount):
    uid = str(user_id)
    if uid not in data["players"]: register_user_by_id(uid)
    data["players"][uid]["balance"] += amount
    save_data()

def register_user(user):
    uid = str(user.id)
    if uid not in data["players"]:
        data["players"][uid] = {"username": user.username or user.first_name, "balance": 1000, "last_bonus": 0, "short_id": random.randint(1000, 9999), "clan_id": None, "weapon": 1, "armor": 1}
        save_data()

def register_user_by_id(uid):
    if uid not in data["players"]:
        data["players"][uid] = {"username": "Player", "balance": 1000, "last_bonus": 0, "short_id": random.randint(1000, 9999), "clan_id": None, "weapon": 1, "armor": 1}
        save_data()

def get_history_roulette():
    if not data["history"]: return "История пуста."
    res = []
    for item in data["history"][-15:]:
        sym = "🟢" if item["color"] == "green" else ("🔴" if item["color"] == "red" else "⚫️")
        res.append(f"{sym}{item['number']}")
    return " ".join(res)

def main_menu():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("💣 MINES", callback_data="game_mines"), InlineKeyboardButton("🚀 CRASH", callback_data="game_crash"), InlineKeyboardButton("🎰 РУЛЕТКА", callback_data="game_roulette"), InlineKeyboardButton("👤 ПРОФИЛЬ", callback_data="profile"), InlineKeyboardButton("🎁 БОНУС", callback_data="bonus_menu"), InlineKeyboardButton("🏆 ТОП", callback_data="top_menu"), InlineKeyboardButton("🛡 КЛАНЫ", callback_data="clan_menu"), InlineKeyboardButton("⚔️ МАГАЗИН", callback_data="shop_menu"), InlineKeyboardButton("❓ ПОМОЩЬ", callback_data="help_menu"), InlineKeyboardButton("⭐ ДОНАТ", callback_data="donate_menu"))
    return kb

@bot.message_handler(commands=["start"])
def start(message):
    register_user(message.from_user)
    bot.send_message(message.chat.id, f"🎰 MON1 CASINO RPG!\n\n🪙 Баланс: {get_balance(message.from_user.id)} Mon1Coin\nВыбирай действие:", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda call: call.data == "profile")
def profile_callback(call):
    bot.answer_callback_query(call.id)
    p = data["players"].get(str(call.from_user.id), {})
    clan_name = "Нет" if not p.get("clan_id") else data["clans"].get(str(p["clan_id"]), {}).get("name", "Нет")
    text = f"👤 **Профиль**\n\n🆔 ID: `{p.get('short_id')}`\n📛 Ник: {get_nick(call.from_user.id)}\n🪙 Баланс: {get_balance(call.from_user.id)} Mon1Coin\n🛡 Клан: {clan_name}\n⚔️ Оружие ур.{p.get('weapon', 1)}\n🥋 Броня ур.{p.get('armor', 1)}"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=main_menu(), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "bonus_menu")
def bonus_callback(call):
    bot.answer_callback_query(call.id)
    process_bonus(call.from_user.id, call.message.chat.id, call.message.message_id)

def process_bonus(user_id, chat_id, msg_id=None):
    uid = str(user_id)
    now, last, cd = int(time.time()), data["players"].get(uid, {}).get("last_bonus", 0), 86400
    if now - last < cd:
        rem = cd - (now - last)
        msg = f"⏳ Бонус через: **{rem // 3600} ч. {(rem % 3600) // 60} мин.**"
    else:
        amt = random.randint(1000, 2000)
        add_balance(user_id, amt)
        data["players"][uid]["last_bonus"] = now
        save_data()
        msg = f"🎁 **БОНУС!**\nВы получили: **+{amt} Mon1Coin** 🪙"
    if msg_id: bot.edit_message_text(msg, chat_id, msg_id, reply_markup=main_menu(), parse_mode="Markdown")
    else: bot.send_message(chat_id, msg, reply_markup=main_menu(), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "top_menu")
def top_callback(call):
    bot.answer_callback_query(call.id)
    s_players = sorted(data["players"].items(), key=lambda x: x[1].get("balance", 0), reverse=True)
    text = "🏆 **ТОП-10**\n\n"
    for i, (uid, pdata) in enumerate(s_players[:10], 1):
        text += f"{i}. {pdata.get('username', '?')} — {pdata.get('balance', 0)} 🪙\n"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=main_menu(), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "help_menu")
def help_callback(call):
    bot.answer_callback_query(call.id)
    text = "📖 **ИНСТРУКЦИЯ**\n\n`б` - баланс\n`профиль` - статы\n`сменить ник ИМЯ`\n`бонус` - раз в 24ч\n\n**ИГРЫ**\n`мины 1000`\n`краш 1000`\n`1000 на 1 на 5`\n\n**КЛАНЫ**\nСоздать: 5000\nВступить: по ID\n\n**МАГАЗИН**\nОружие/Броня: 2000\n\n**АДМИН**\n`/give`, `/reset`, `/wipe`, `/createpromo`"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=main_menu(), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "back")
def back(call):
    bot.edit_message_text("🎰 ГЛАВНОЕ МЕНЮ", call.message.chat.id, call.message.message_id, reply_markup=main_menu())

@bot.callback_query_handler(func=lambda call: call.data == "clan_menu")
def clan_menu(call):
    bot.answer_callback_query(call.id)
    uid = call.from_user.id
    p = data["players"].get(str(uid), {})
    if p.get("clan_id"):
        c_id = p["clan_id"]
        clan = data["clans"].get(str(c_id), {})
        boss = data["clan_bosses"].get(str(c_id), {"level": 1, "hp": 1000, "max_hp": 1000})
        kb = InlineKeyboardMarkup(row_width=2).add(InlineKeyboardButton("⚔️ Атаковать Босса", callback_data="attack_boss"), InlineKeyboardButton("⬅️ Назад", callback_data="back"))
        text = f"🛡 **Клан: {clan.get('name', '?')}**\n\n👑 Владелец: {clan.get('owner_name', '?')}\n👥 Игроков: {len([m for m in data['players'].values() if m.get('clan_id') == c_id])}/15\n🆔 ID Клана: `{c_id}`\n\n🐉 **БОСС (Ур. {boss['level']})**\n❤️ HP: {boss['hp']} / {boss['max_hp']}"
    else:
        kb = InlineKeyboardMarkup(row_width=1).add(InlineKeyboardButton("➕ Создать (5000 🪙)", callback_data="create_clan"), InlineKeyboardButton("🔍 Вступить по ID", callback_data="join_clan_prompt"), InlineKeyboardButton("⬅️ Назад", callback_data="back"))
        text = "🛡 **Кланы**\n\nТы не в клане."
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "create_clan")
def c_clan(call):
    bot.answer_callback_query(call.id)
    if get_balance(call.from_user.id) < 5000: return bot.answer_callback_query(call.id, "❌ Нужно 5000!", show_alert=True)
    msg = bot.send_message(call.message.chat.id, "Введите имя клана (до 15 символов):")
    bot.register_next_step_handler(msg, save_clan)

def save_clan(m):
    uid = str(m.from_user.id)
    name = m.text.strip()[:15]
    if not name or get_balance(uid) < 5000: return bot.reply_to(m, "❌ Ошибка.")
    cid = str(random.randint(1000, 9999))
    while cid in data["clans"]: cid = str(random.randint(1000, 9999))
    add_balance(uid, -5000)
    data["clans"][cid] = {"name": name, "owner_id": uid, "owner_name": get_nick(uid)}
    data["players"][uid]["clan_id"] = cid
    data["clan_bosses"][cid] = {"level": 1, "hp": 1000, "max_hp": 1000}
    save_data()
    bot.reply_to(m, f"✅ Клан **{name}** создан!\nID: `{cid}`", parse_mode="Markdown", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda call: call.data == "join_clan_prompt")
def j_clan(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.message.chat.id, "Введите ID клана:")
    bot.register_next_step_handler(msg, do_join)

def do_join(m):
    uid, cid = str(m.from_user.id), m.text.strip()
    if cid not in data["clans"]: return bot.reply_to(m, "❌ Не найден.")
    if len([x for x in data["players"].values() if x.get("clan_id") == cid]) >= 15: return bot.reply_to(m, "❌ Полон (15).")
    data["players"][uid]["clan_id"] = cid
    save_data()
    bot.reply_to(m, f"✅ Вступил в **{data['clans'][cid]['name']}**!", parse_mode="Markdown", reply_markup=main_menu())

@bot.callback_query_handler(func=lambda call: call.data == "shop_menu")
def shop_menu(call):
    bot.answer_callback_query(call.id)
    p = data["players"].get(str(call.from_user.id), {})
    kb = InlineKeyboardMarkup(row_width=1).add(InlineKeyboardButton("🗡 Купить Оружие (2000)", callback_data="buy_weapon"), InlineKeyboardButton("🛡 Купить Броню (2000)", callback_data="buy_armor"), InlineKeyboardButton("⬅️ Назад", callback_data="back"))
    text = f"⚔️ **Магазин**\n🗡 Оружие: Ур. {p.get('weapon', 1)}\n🛡 Броня: Ур. {p.get('armor', 1)}\n\n🪙 Баланс: {get_balance(call.from_user.id)}\nУлучшение: 2000"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data in ["buy_weapon", "buy_armor"])
def buy(call):
    bot.answer_callback_query(call.id)
    uid = str(call.from_user.id)
    if get_balance(uid) < 2000: return bot.answer_callback_query(call.id, "❌ Мало денег!", show_alert=True)
    add_balance(uid, -2000)
    if call.data == "buy_weapon": data["players"][uid]["weapon"] += 1
    else: data["players"][uid]["armor"] += 1
    save_data()
    shop_menu(call)

@bot.callback_query_handler(func=lambda call: call.data == "attack_boss")
def boss(call):
    bot.answer_callback_query(call.id)
    uid = str(call.from_user.id)
    cid = data["players"].get(uid, {}).get("clan_id")
    if not cid: return
    b = data["clan_bosses"].get(str(cid))
    w = data["players"][uid].get("weapon", 1)
    a = data["players"][uid].get("armor", 1)
    dmg = w * random.randint(10, 20)
    b["hp"] -= dmg
    if b["hp"] <= 0:
        rw = 500 * b["level"]
        add_balance(uid, rw)
        b["level"] += 1; b["max_hp"] += 1000; b["hp"] = b["max_hp"]
        msg = f"🎉 **БОСС УБИТ!**\nПоследний удар твой. +{rw} 🪙"
    else:
        cd = max(1, random.randint(10, 20) - (a * 5))
        data["players"][uid]["balance"] = max(0, get_balance(uid) - cd)
        msg = f"⚔️ Урон: {dmg}\nБосс бьет: {cd}"
    save_data()
    bot.send_message(call.message.chat.id, msg, parse_mode="Markdown", reply_markup=main_menu())
    @bot.callback_query_handler(func=lambda call: call.data == "game_crash")
def crash_menu(call):
    bot.answer_callback_query(call.id)
    bot.edit_message_text("🚀 Введите: `краш 1000`", call.message.chat.id, call.message.message_id, reply_markup=main_menu(), parse_mode="Markdown")

def start_crash(uid, cid, bet):
    if get_balance(uid) < bet: return bot.send_message(cid, "❌ Мало.")
    add_balance(uid, -bet)
    crash_games[uid] = {"bet": bet, "cp": round(random.uniform(1.1, 100.0), 2), "cur": 1.0, "act": True}
    kb = InlineKeyboardMarkup().add(InlineKeyboardButton("💰 ЗАБРАТЬ", callback_data="crash_cashout"))
    msg = bot.send_message(cid, f"🚀 CRASH\nСтавка: {bet}\nКоэф: x1.00", reply_markup=kb)
    threading.Thread(target=crash_loop, args=(uid, cid, msg.message_id)).start()

def crash_loop(uid, cid, mid):
    time.sleep(1)
    while True:
        g = crash_games.get(uid)
        if not g or not g["act"]: break
        g["cur"] += 0.1 if g["cur"] < 10 else (0.5 if g["cur"] < 50 else 1.0)
        g["cur"] = round(g["cur"], 2)
        if g["cur"] >= g["cp"]:
            g["act"] = False
            bot.edit_message_text(f"💥 КРАШ на x{g['cp']:.2f}!\nПотеряно {g['bet']} 🪙.", cid, mid)
            break
        try: bot.edit_message_text(f"🚀 CRASH\nСтавка: {g['bet']}\nКоэф: x{g['cur']:.2f}", cid, mid, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("💰 ЗАБРАТЬ", callback_data="crash_cashout")))
        except: pass
        time.sleep(1)

@bot.callback_query_handler(func=lambda call: call.data == "crash_cashout")
def crash_out(call):
    g = crash_games.get(call.from_user.id)
    if not g or not g["act"]: return
    g["act"] = False
    rw = math.floor(g["bet"] * g["cur"])
    add_balance(call.from_user.id, rw)
    bot.edit_message_text(f"🏆 Забрано: +{rw} 🪙", call.message.chat.id, call.message.message_id, reply_markup=main_menu())

MULT = {2: 1.10, 3: 1.15, 5: 1.25, 9: 1.45}
@bot.callback_query_handler(func=lambda call: call.data == "game_mines")
def mines_menu(call):
    bot.answer_callback_query(call.id)
    bot.edit_message_text("💣 Введите: `мины 1000 3`", call.message.chat.id, call.message.message_id, reply_markup=main_menu(), parse_mode="Markdown")

def start_mines(uid, cid, bet, bmb):
    if get_balance(uid) < bet: return bot.send_message(cid, "❌ Мало.")
    if bmb not in MULT: return bot.send_message(cid, "❌ Мины: 2, 3, 5, 9")
    add_balance(uid, -bet)
    mines_games[uid] = {"bet": bet, "b": bmb, "m": set(random.sample(range(25), bmb)), "o": set(), "f": False}
    bot.send_message(cid, mines_txt(uid), reply_markup=mines_kb(uid), parse_mode="Markdown")

def mines_txt(uid):
    g = mines_games[uid]
    o = len(g["o"])
    m = MULT[g["b"]] ** o if o > 0 else 1.0
    rw = math.floor(g["bet"] * m)
    return f"💣 MINES\nСтавка: {g['bet']}\nМин: {g['b']}\nОткрыто: {o}\nМнож: x{m:.2f}\nЗабрать: {rw}"

def mines_kb(uid):
    g = mines_games[uid]
    kb = InlineKeyboardMarkup(row_width=5)
    for r in range(5):
        row = []
        for c in range(5):
            i = r*5 + c
            s = "💎" if i in g["o"] else ("💣" if g["f"] and i in g["m"] else ("▫️" if g["f"] else "❔"))
            row.append(InlineKeyboardButton(s, callback_data=f"mc_{i}"))
        kb.row(*row)
    if not g["f"] and g["o"]: kb.row(InlineKeyboardButton("⭐ ЗАБРАТЬ", callback_data="m_out"))
    return kb

@bot.callback_query_handler(func=lambda call: call.data.startswith("mc_") or call.data == "m_out")
def mines_play(call):
    uid = call.from_user.id
    g = mines_games.get(uid)
    if not g or g["f"]: return
    if call.data == "m_out":
        rw = math.floor(g["bet"] * (MULT[g["b"]] ** len(g["o"])))
        add_balance(uid, rw)
        g["f"] = True
        bot.edit_message_text(f"🏆 Забрано: {rw} 🪙", call.message.chat.id, call.message.message_id, reply_markup=main_menu())
        return
    i = int(call.data.split("_")[1])
    if i in g["m"]:
        g["f"] = True
        bot.edit_message_text(f"💥 МИНА! Потеряно {g['bet']} 🪙.", call.message.chat.id, call.message.message_id, reply_markup=main_menu())
    else:
        g["o"].add(i)
        bot.edit_message_text(mines_txt(uid), call.message.chat.id, call.message.message_id, reply_markup=mines_kb(uid), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "game_roulette")
def roul_menu(call):
    bot.answer_callback_query(call.id)
    bot.edit_message_text(f"🎰 **РУЛЕТКА**\n\n📜 {get_history_roulette()}\n\n`1000 на 1 на 5`\n`500 на red`", call.message.chat.id, call.message.message_id, reply_markup=main_menu(), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "donate_menu")
def donate_menu(call):
    bot.answer_callback_query(call.id)
    kb = InlineKeyboardMarkup(row_width=1).add(InlineKeyboardButton("⭐ 50 Звезд (5000)", callback_data="pay_50"), InlineKeyboardButton("⭐ 100 Звезд (12000)", callback_data="pay_100"))
    bot.edit_message_text("💖 Выберите пакет:", call.message.chat.id, call.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_"))
def send_donate_invoice(call):
    s = int(call.data.split("_")[1])
    c = {50: 5000, 100: 12000}[s]
    bot.answer_callback_query(call.id)
    bot.send_invoice(call.message.chat.id, "Донат", f"+{c} Mon1Coin", f"don_{s}_{c}", "", "XTR", [LabeledPrice("Донат", s)])

@bot.pre_checkout_query_handler(func=lambda q: True)
def pre_chk(q): bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def success(m):
    p = m.successful_payment.invoice_payload
    if p.startswith("don_"):
        c = int(p.split("_")[2])
        add_balance(m.from_user.id, c)
        bot.send_message(m.chat.id, f"🎉 +{c} 🪙")

@bot.message_handler(commands=['give'])
def admin_give(m):
    if m.from_user.id not in ADMIN_IDS: return
    try:
        a = m.text.split()[1:]
        t, amt = str(int(a[0])), int(a[1])
        register_user_by_id(t)
        add_balance(t, amt)
        bot.reply_to(m, f"✅ Выдано {amt} 🪙 игроку {t}.")
    except: bot.reply_to(m, "❌ `/give ID СУММА`", parse_mode="Markdown")

@bot.message_handler(commands=['reset'])
def admin_reset(m):
    if m.from_user.id not in ADMIN_IDS: return
    try:
        t = str(int(m.text.split()[1]))
        if t in data["players"]: data["players"][t]["balance"] = 0; save_data(); bot.reply_to(m, "♻️ Сброшено.")
    except: bot.reply_to(m, "❌ `/reset ID`", parse_mode="Markdown")

@bot.message_handler(commands=['wipe'])
def admin_wipe(m):
    if m.from_user.id not in ADMIN_IDS: return
    for u in data["players"]: data["players"][u]["balance"] = 1000
    save_data()
    bot.reply_to(m, "♻️ Все балансы по 1000.")

@bot.message_handler(commands=['createpromo'])
def create_promo(m):
    if m.from_user.id not in ADMIN_IDS: return
    try:
        a = m.text.split()[1:]
        data["promos"][a[0].upper()] = {"amount": int(a[1]), "uses_left": int(a[2])}
        save_data()
        bot.reply_to(m, "✅ Промокод создан.")
    except: bot.reply_to(m, "❌ `/createpromo КОД СУММА ЮЗЫ`", parse_mode="Markdown")

@bot.message_handler(content_types=['text'])
def handle_all_text(message):
    if message.text.startswith('/'): return
    text = message.text.lower().strip()
    parts = text.split()
    user_id = message.from_user.id

    if text in ["б", "баланс"]: return bot.reply_to(message, f"🪙 Баланс: {get_balance(user_id)} Mon1Coin")
    if text in ["профиль", "п"]: return bot.reply_to(message, f"👤 ID: `{get_user_short_id(user_id)}`\nНик: {get_nick(user_id)}", parse_mode="Markdown")
    if text in ["помощь", "help"]: return help_callback(type('obj', (object,), {'id': None, 'message': message, 'from_user': message.from_user, 'answer_callback_query': lambda *a: None})())
    if text in ["топ", "top"]: return top_callback(type('obj', (object,), {'id': None, 'message': message, 'from_user': message.from_user, 'answer_callback_query': lambda *a: None})())
    if text in ["бонус", "bonus"]: return process_bonus(user_id, message.chat.id)

    if parts[0] in ["сменить", "ник"] and len(parts) >= 2:
        new_nick = " ".join(parts[1:])[:15]
        data["players"][str(user_id)]["username"] = new_nick
        save_data()
        return bot.reply_to(message, f"✅ Твой новый ник: **{new_nick}**", parse_mode="Markdown")

    if parts[0] in ["мины", "mines"] and len(parts) >= 2:
        try: start_mines(user_id, message.chat.id, int(parts[1]), int(parts[2]) if len(parts) > 2 else 3)
        except: bot.reply_to(message, "❌ `мины 1000 3`", parse_mode="Markdown")
        return

    if parts[0] in ["краш", "crash"] and len(parts) >= 2:
        try: start_crash(user_id, message.chat.id, int(parts[1]))
        except: bot.reply_to(message, "❌ `краш 1000`", parse_mode="Markdown")
        return

    if " на " in text and len(parts) >= 3:
        try:
            bet = int(parts[0])
            tg = [parts[i] for i in range(2, len(parts)) if parts[i] != "на"]
            cost = bet * len(tg)
            if get_balance(user_id) < cost: return bot.reply_to(message, f"❌ Нужно {cost} 🪙")
            add_balance(user_id, -cost)
            wn = random.randint(0, 36)
            wc = "green" if wn == 0 else ("red" if 1 <= wn <= 18 else "black")
            sym = {"green": "🟢", "red": "🔴", "black": "⚫️"}[wc]
            data["history"].append({"number": wn, "color": wc})
            save_data()
            tw, res = 0, []
            for x in tg:
                win, mlt = False, 0
                if "-" in x:
                    try:
                        s, e = map(int, x.split("-"))
                        if s <= wn <= e: mlt = max(1, math.floor(37 / (e - s + 1))); win = True
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
            add_balance(user_id, tw)
            bot.reply_to(message, f"🎰 {sym} **{wn}**\n" + "\n".join(res) + f"\n💰 Итог: {tw} 🪙", parse_mode="Markdown")
            return
        except ValueError: bot.reply_to(message, "❌ `1000 на 5`", parse_mode="Markdown")
        return

    if len(parts) == 1 and len(text) > 3 and text.isalnum():
        code = text.upper()
        if code in data["promos"]:
            promo = data["promos"][code]
            if promo["uses_left"] <= 0: return bot.reply_to(message, "❌ Не работает.")
            if [str(user_id), code] in data["activations"]: return bot.reply_to(message, "❌ Уже активировали!")
            add_balance(user_id, promo["amount"])
            promo["uses_left"] -= 1
            data["activations"].append([str(user_id), code])
            save_data()
            return bot.reply_to(message, f"🎉 Промокод активирован! +{promo['amount']} 🪙")

print("BOT STARTED")
bot.infinity_polling(skip_pending=True)
