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
    if changed: save_data()

migrate_data()
bot = telebot.TeleBot(TOKEN)
MULT = {2: 1.10, 3: 1.15, 5: 1.25, 9: 1.45}

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

def add_balance(user_id, amount):
    uid = str(user_id)
    if uid not in data["players"]: register_user_by_id(uid)
    data["players"][uid]["balance"] += amount
    save_data()

def register_user(user):
    uid = str(user.id)
    if uid not in data["players"]:
        sid = data["next_id"]; data["next_id"] += 1
        data["players"][uid] = {"username": user.username or user.first_name, "balance": 1000, "last_bonus": 0, "short_id": sid, "clan_id": None, "role": "none"}
        save_data()

def register_user_by_id(uid):
    if uid not in data["players"]:
        sid = data["next_id"]; data["next_id"] += 1
        data["players"][uid] = {"username": "Player", "balance": 1000, "last_bonus": 0, "short_id": sid, "clan_id": None, "role": "none"}
        save_data()

# --- СТАРТ ---
@bot.message_handler(commands=["start"])
def start(message):
    register_user(message.from_user)
    bot.send_message(message.chat.id, 
        f"🎰 **MON1 CASINO RPG**\n\n🪙 Баланс: {get_balance(message.from_user.id)}\n\n"
        "**Игры:**\n"
        "`мины 1000 3`\n"
        "`краш 1000`\n"
        "`1000 на 5` (рулетка)\n\n"
        "**Кланы:** `мой клан`, `топ кланов`\n"
        "**База:** `б`, `профиль`, `бонус`\n"
        "**Инфо:** `помощь`", parse_mode="Markdown")

# --- ИГРА МИНЫ ---
@bot.message_handler(func=lambda m: m.text.lower().startswith("мины"))
def start_mines(message):
    uid = str(message.from_user.id)
    try:
        parts = message.text.split()
        bet = int(parts[1])
        bmb = int(parts[2]) if len(parts) > 2 else 3
        
        if bet <= 0 or get_balance(uid) < bet: return bot.reply_to(message, "❌ Недостаточно средств.")
        if bmb not in MULT: return bot.reply_to(message, "❌ Доступно мин: 2, 3, 5, 9.")
        
        add_balance(uid, -bet)
        gid = str(random.randint(10000, 99999))
        data["active_games"][gid] = {"type": "mines", "user": uid, "bet": bet, "mines": random.sample(range(25), bmb), "opened": [], "bombs": bmb}
        save_data()
        
        bot.reply_to(message, f"💣 **МИНЫ** (Игра #{gid})\nСтавка: {bet} 🪙\nМин: {bmb}\n\nНажмите на клетки.", reply_markup=mines_kb(gid), parse_mode="Markdown")
    except: bot.reply_to(message, "❌ `мины 1000 3`")

def mines_kb(gid):
    g = data["active_games"].get(gid)
    if not g: return None
    kb = InlineKeyboardMarkup(row_width=5)
    for r in range(5):
        row = [InlineKeyboardButton("💎" if (r*5+c) in g["opened"] else "❔", callback_data=f"m_{gid}_{r*5+c}") for c in range(5)]
        kb.row(*row)
    kb.row(InlineKeyboardButton("⭐ ЗАБРАТЬ", callback_data=f"mcash_{gid}"))
    return kb

@bot.callback_query_handler(func=lambda call: call.data.startswith("m_"))
def mines_play(call):
    _, gid, cell = call.data.split("_"); cell = int(cell)
    uid = str(call.from_user.id); g = data["active_games"].get(gid)
    
    if not g or g["user"] != uid: return bot.answer_callback_query(call.id, "❌ Игра не найдена.")
    if cell in g["opened"]: return bot.answer_callback_query(call.id, "❌ Уже открыто.")
    
    if cell in g["mines"]:
        del data["active_games"][gid]; save_data()
        kb = InlineKeyboardMarkup(row_width=5)
        for r in range(5):
            kb.row(*[InlineKeyboardButton("💣" if (r*5+c) in g["mines"] else "💎", callback_data="ignore") for c in range(5)])
        bot.edit_message_text(f"💥 **МИНА!** Потеряно {g['bet']} 🪙.", call.message.chat.id, call.message.message_id, reply_markup=kb, parse_mode="Markdown")
        return
        
    g["opened"].append(cell)
    mult = MULT[g["bombs"]] ** len(g["opened"]); reward = math.floor(g["bet"] * mult)
    save_data()
    bot.edit_message_text(f"💣 **МИНЫ**\nСтавка: {g['bet']} 🪙\nОткрыто: {len(g['opened'])}\nМнож: x{mult:.2f}\nЗабрать: {reward} 🪙", call.message.chat.id, call.message.message_id, reply_markup=mines_kb(gid), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("mcash_"))
def mines_cashout(call):
    gid = call.data.split("_")[1]; uid = str(call.from_user.id); g = data["active_games"].get(gid)
    if not g or g["user"] != uid or not g["opened"]: return
    reward = math.floor(g["bet"] * (MULT[g["bombs"]] ** len(g["opened"])))
    add_balance(uid, reward); del data["active_games"][gid]; save_data()
    bot.edit_message_text(f"🏆 **Забрано!** +{reward} 🪙", call.message.chat.id, call.message.message_id, reply_markup=None, parse_mode="Markdown")

# --- ИГРА КРАШ (x10 и частые краши) ---
@bot.message_handler(func=lambda m: m.text.lower().startswith("краш"))
def start_crash(message):
    uid = str(message.from_user.id)
    try:
        bet = int(message.text.split()[1])
        if bet <= 0 or get_balance(uid) < bet: return bot.reply_to(message, "❌ Недостаточно средств.")
        
        add_balance(uid, -bet)
        gid = str(random.randint(10000, 99999))
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
        
        g["current"] = round(g["current"] + 0.1, 2)
        save_data()
        
        # Добавлен шанс краша на каждом шаге (делает игру сложнее)
        if g["current"] >= g["crash_point"] or random.random() < 0.1: # 10% шанс на краш каждый тик
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
    g["active"] = False; reward = math.floor(g["bet"] * g["current"]); add_balance(uid, reward)
    del data["active_games"][gid]; save_data()
    bot.edit_message_text(f"🏆 **Забрано на x{g['current']:.2f}!** +{reward} 🪙", call.message.chat.id, call.message.message_id, reply_markup=None, parse_mode="Markdown")

# --- РУЛЕТКА ---
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
    members = [f"@{m.get('username')} ({m.get('role')})" for m in data["players"].values() if m.get("clan_id") == cid]
    text = f"🛡 **Клан: {clan['name']}**\n🆔 ID: `{cid}`\n👑 Создатель: @{clan['owner_name']}\n👥 Участники: {len(members)}/15\n💰 Казна: {clan.get('treasury', 0)} 🪙\n\nВаша роль: **{p.get('role', 'игрок').upper()}**\n\n" + "\n".join(members)
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
        bot.reply_to(message, f"✅ @{target} назначен {role}.")
    except: bot.reply_to(message, "❌ `назначить РОЛЬ @username`")

@bot.message_handler(func=lambda m: m.text.lower().startswith("кикнуть"))
def kick(message):
    uid = str(message.from_user.id)
    if not has_perm(uid, "kick"): return bot.reply_to(message, "❌ Нет прав.")
    try:
        target = message.text.split()[1].replace("@", ""); cid = data["players"][uid]["clan_id"]
        t_uid = next((u for u, p in data["players"].items() if p.get("username", "").lower() == target.lower() and p.get("clan_id") == cid), None)
        if not t_uid: return bot.reply_to(message, "❌ Игрок не найден.")
        data["players"][t_uid]["clan_id"] = None; data["players"][t_uid]["role"] = "none"; save_data()
        bot.reply_to(message, f"✅ @{target} кикнут.")
    except: bot.reply_to(message, "❌ `кикнуть @username`")

# --- ПОМОЩЬ ---
@bot.message_handler(func=lambda m: m.text.lower().strip() == "помощь")
def help_cmd(message):
    text = (
        "📖 **ПОЛНАЯ ИНСТРУКЦИЯ**\n\n"
        "**👤 БАЗОВЫЕ**\n`б` — баланс\n`профиль` — ID\n`бонус` — 24ч\n`сменить ник ИМЯ`\n\n"
        "**🎮 ИГРЫ**\n`мины СУММА МИНЫ`\n`краш СУММА`\n`СУММА на ЦИФРА`\n\n"
        "**🛡 КЛАНЫ**\n`создать клан ИМЯ` (5000)\n`вступить клан ID`\n`мой клан`\n`топ кланов`\n`пополнить казну СУММА`\n`выйти из клана`\n\n"
        "**👑 УПРАВЛЕНИЕ**\n`переименовать клан ИМЯ`\n`назначить РОЛЬ @username`\n`кикнуть @username`\n\n"
        "**💳 ДОНАТ**\n1 ⭐ = 500 Mon1Coin\n`/donate`\n\n"
        "**⚙️ АДМИН**\n`/give ИГРОВОЙ_ID СУММА`\n`/reset ИГРОВОЙ_ID`\n`/wipe`\n`/createpromo КОД СУММА ЮЗЫ`"
    )
    bot.reply_to(message, text, parse_mode="Markdown")

# --- ДОНАТ ---
@bot.message_handler(commands=['donate'])
def donate_cmd(message):
    kb = InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("⭐ 50 Звезд (25 000)", callback_data="pay_50"),
        InlineKeyboardButton("⭐ 100 Звезд (50 000)", callback_data="pay_100"),
        InlineKeyboardButton("⭐ 250 Звезд (125 000)", callback_data="pay_250")
    )
    bot.send_message(message.chat.id, "💖 **Донат**\nВыберите пакет:", reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_"))
def pay(call):
    s = int(call.data.split("_")[1]); c = s * 500
    bot.answer_callback_query(call.id)
    bot.send_invoice(call.message.chat.id, "Донат", f"+{c} Mon1Coin", f"don_{s}_{c}", "", "XTR", [LabeledPrice("Донат", s)])

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
