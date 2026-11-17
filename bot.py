import os, random, math, time, telebot, threading, json, pathlib
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("Не задан BOT_TOKEN")

ADMIN_IDS = [8211650013, 6940877915]

DATA_DIR = pathlib.Path(os.getenv("DATA_DIR", "/app/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = DATA_DIR / "database.json"

data = {
    "players": {}, "promos": {}, "activations": [], "history": [],
    "clans": {}, "next_id": 1, "active_games": {},
}

# ---------- ЗАГРУЗКА / СОХРАНЕНИЕ ----------
_dirty = False
_save_lock = threading.Lock()

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
    global _dirty
    _dirty = True

def _real_save():
    global _dirty
    with _save_lock:
        if not _dirty:
            return
        tmp = DATA_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(DATA_FILE)
        _dirty = False

def _saver_loop():
    while True:
        time.sleep(3)
        try:
            _real_save()
        except Exception as e:
            print("save err:", e)

threading.Thread(target=_saver_loop, daemon=True).start()

load_data()

def migrate_data():
    global data
    changed = False
    current_max = max(
        [p.get("short_id", 0) for p in data["players"].values() if isinstance(p.get("short_id"), int)],
        default=0,
    )
    if data.get("next_id", 1) <= current_max:
        data["next_id"] = current_max + 1
    for uid, pdata in data["players"].items():
        if "short_id" not in pdata or pdata["short_id"] == 0:
            pdata["short_id"] = data["next_id"]; data["next_id"] += 1; changed = True
        if "bank" not in pdata:
            pdata["bank"] = 0; pdata["deposit"] = 0; pdata["deposit_start"] = 0; changed = True
        if "biz_territory" not in pdata:
            pdata["biz_territory"] = 0; pdata["biz_building"] = 1
            pdata["biz_tax"] = 0; pdata["biz_last_collect"] = int(time.time()); changed = True
        if "clan_id" not in pdata:
            pdata["clan_id"] = None; pdata["role"] = "none"; changed = True
    if changed:
        save_data()

migrate_data()

# ---------- ВОССТАНОВЛЕНИЕ ЗАВИСШИХ ИГР ----------
def recover_games():
    changed = False
    for gid, g in list(data["active_games"].items()):
        try:
            add_balance(g["user"], g["bet"])
        except Exception:
            pass
        data["active_games"].pop(gid, None)
        changed = True
    if changed:
        save_data()

# ---------- БОТ ----------
bot = telebot.TeleBot(TOKEN)

# ---------- БИЗНЕС ----------
BIZ_TERRITORY_COST = {0: 10000, 1: 50000, 2: 250000, 3: 1000000, 4: 5000000, 5: 25000000}
BIZ_BUILDING_COST  = {1: 20000, 2: 100000, 3: 500000, 4: 2000000, 5: 10000000}
BIZ_BASE_INCOME    = 1000
BIZ_BUILDING_BONUS = 0.5
BIZ_TAX_PERCENT    = 0.05

def biz_income_per_hour(p):
    t = p.get("biz_territory", 0)
    b = p.get("biz_building", 1)
    if t <= 0:
        return 0
    return int(t * BIZ_BASE_INCOME * (1 + (b - 1) * BIZ_BUILDING_BONUS))

# ---------- ХЕЛПЕРЫ ----------
def get_balance(uid):        return data["players"].get(str(uid), {}).get("balance", 0)
def get_nick(uid):           return data["players"].get(str(uid), {}).get("username", "Player")
def get_user_short_id(uid):  return data["players"].get(str(uid), {}).get("short_id", "0")

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

def add_balance(uid, amt):
    uid = str(uid)
    if uid not in data["players"]:
        register_user_by_id(uid)
    data["players"][uid]["balance"] += amt
    save_data()

def register_user(user):
    uid = str(user.id)
    if uid not in data["players"]:
        sid = data["next_id"]; data["next_id"] += 1
        data["players"][uid] = {
            "username": user.username or user.first_name or "Player",
            "balance": 1000, "last_bonus": 0, "short_id": sid,
            "clan_id": None, "role": "none",
            "bank": 0, "deposit": 0, "deposit_start": 0,
            "biz_territory": 0, "biz_building": 1, "biz_tax": 0,
            "biz_last_collect": int(time.time()),
        }
        save_data()

def register_user_by_id(uid, username="Player"):
    if uid not in data["players"]:
        sid = data["next_id"]; data["next_id"] += 1
        data["players"][uid] = {
            "username": username, "balance": 1000, "last_bonus": 0,
            "short_id": sid, "clan_id": None, "role": "none",
            "bank": 0, "deposit": 0, "deposit_start": 0,
            "biz_territory": 0, "biz_building": 1, "biz_tax": 0,
            "biz_last_collect": int(time.time()),
        }
        save_data()

# ---------- START ----------
@bot.message_handler(commands=["start"])
def start(message):
    register_user(message.from_user)
    bot.send_message(
        message.chat.id,
        f"🎰 **MON1 CASINO RPG**\n\n🪙 Баланс: {get_balance(message.from_user.id)}\n\n"
        f"Игры: `слот 1000`, `мины 1000 5`, `краш 1000`, `1000 на 5`\n"
        f"Инфо: `помощь`",
        parse_mode="Markdown",
    )

# ---------- СЛОТ ----------
@bot.message_handler(func=lambda m: m.text.lower().startswith("слот"))
def slot_machine(message):
    uid = str(message.from_user.id)
    try:
        bet = int(message.text.split()[1])
        if bet <= 0 or get_balance(uid) < bet:
            return bot.reply_to(message, "❌ Недостаточно средств.")
        add_balance(uid, -bet)
        s = [random.choice(["🍒", "🍋", "💎", "🎰"]) for _ in range(3)]
        win = 0
        if s[0] == s[1] == s[2]:
            if s[0] == "🎰":   win = bet * 50
            elif s[0] == "💎": win = bet * 10
            elif s[0] == "🍋": win = bet * 5
            elif s[0] == "🍒": win = bet * 3
        elif s[0] == s[1] or s[1] == s[2] or s[0] == s[2]:
            win = bet
        if win > 0:
            add_balance(uid, win)
            msg = f"🎰 **СЛОТ**\n[ {s[0]} | {s[1]} | {s[2]} ]\n🎉 **ВЫИГРЫШ!** +{win} 🪙\nБаланс: {get_balance(uid)}"
        else:
            msg = f"🎰 **СЛОТ**\n[ {s[0]} | {s[1]} | {s[2]} ]\n😢 Проигрыш.\nБаланс: {get_balance(uid)}"
        bot.reply_to(message, msg, parse_mode="Markdown")
    except Exception:
        bot.reply_to(message, "❌ `слот 1000`")

# ---------- ТОП ----------
@bot.message_handler(func=lambda m: m.text.lower().strip() in ["топ", "топ игроков"])
def top_cmd(message):
    sp = sorted(data["players"].items(), key=lambda x: x[1].get("balance", 0), reverse=True)[:10]
    text = "🏆 **ТОП-10**\n\n" + "".join(
        [f"{i}. {p.get('username','?')} — {p.get('balance',0)} 🪙\n" for i, (u, p) in enumerate(sp, 1)]
    )
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text.lower().strip() == "чаты")
def chats_cmd(message):
    bot.reply_to(message, "💬 **Наши чаты**\n📢 Канал: https://t.me/mon1bots\n💬 Чат: https://t.me/mon1not", parse_mode="Markdown")

# ---------- БИЗНЕС ----------
@bot.message_handler(func=lambda m: m.text.lower().strip() == "мой бизнес")
def my_business(message):
    uid = str(message.from_user.id)
    p = data["players"].get(uid, {})
    t = p.get("biz_territory", 0)
    if t == 0:
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🏗 Построить бизнес", callback_data="biz_build"))
        return bot.reply_to(
            message,
            f"🏢 У вас нет бизнеса.\nНажмите кнопку ниже, чтобы купить первый уровень за {BIZ_TERRITORY_COST[0]} 🪙.",
            reply_markup=kb,
        )
    show_biz_menu(message.chat.id, uid, None)

def show_biz_menu(chat_id, uid, msg_id):
    p = data["players"].get(uid, {})
    t = p.get("biz_territory", 0)
    b = p.get("biz_building", 1)
    tax = p.get("biz_tax", 0)
    inc = biz_income_per_hour(p)
    elapsed = min(int(time.time()) - p.get("biz_last_collect", int(time.time())), 86400)
    earned = int((elapsed / 3600) * inc)
    next_t = BIZ_TERRITORY_COST.get(t, "MAX")
    next_b = BIZ_BUILDING_COST.get(b, "MAX")
    text = (
        f"🏢 **Бизнес**\n"
        f"🧱 Территория: {t} м² (⬆️ {next_t} 🪙)\n"
        f"🏢 Здание: ур. {b} (⬆️ {next_b} 🪙)\n"
        f"📈 Доход: **{inc} 🪙/час**\n"
        f"💸 Налог к оплате: {tax} 🪙\n"
        f"💰 Накоплено: **{earned} 🪙**"
    )
    kb = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("💰 Собрать", callback_data="biz_collect"),
        InlineKeyboardButton("🧱 Терр.", callback_data="biz_terr"),
        InlineKeyboardButton("🏢 Здание", callback_data="biz_build_up"),
        InlineKeyboardButton("💸 Налоги", callback_data="biz_tax"),
    )
    if msg_id:
        try:
            bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb, parse_mode="Markdown")
        except Exception:
            pass
    else:
        bot.send_message(chat_id, text, reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("biz_"))
def biz_callback(call):
    uid = str(call.from_user.id)
    action = call.data

    if action == "biz_build":
        if get_balance(uid) < BIZ_TERRITORY_COST[0]:
            return bot.answer_callback_query(call.id, "❌ Мало денег!", show_alert=True)
        add_balance(uid, -BIZ_TERRITORY_COST[0])
        data["players"][uid]["biz_territory"] = 1
        data["players"][uid]["biz_last_collect"] = int(time.time())
        save_data()
        bot.answer_callback_query(call.id, "✅ Построено!")
        show_biz_menu(call.message.chat.id, uid, call.message.message_id)

    elif action == "biz_collect":
        p = data["players"].get(uid, {})
        tax = p.get("biz_tax", 0)
        if tax > 0:
            return bot.answer_callback_query(call.id, f"❌ Оплатите налог ({tax} 🪙)!", show_alert=True)
        inc = biz_income_per_hour(p)
        elapsed = min(int(time.time()) - p.get("biz_last_collect", int(time.time())), 86400)
        earned = int((elapsed / 3600) * inc)
        if earned <= 0:
            return bot.answer_callback_query(call.id, "⏳ Пусто.", show_alert=True)
        tax_o = int(earned * BIZ_TAX_PERCENT)
        data["players"][uid]["biz_tax"] = tax_o
        add_balance(uid, earned)
        data["players"][uid]["biz_last_collect"] = int(time.time())
        save_data()
        bot.answer_callback_query(call.id, f"💰 +{earned} 🪙! Налог: {tax_o} 🪙", show_alert=True)
        show_biz_menu(call.message.chat.id, uid, call.message.message_id)

    elif action == "biz_terr":
        p = data["players"].get(uid, {})
        t = p.get("biz_territory", 0)
        if t >= 5:
            return bot.answer_callback_query(call.id, "🧱 MAX!", show_alert=True)
        c = BIZ_TERRITORY_COST.get(t, 0)
        if get_balance(uid) < c:
            return bot.answer_callback_query(call.id, f"❌ {c} 🪙!", show_alert=True)
        add_balance(uid, -c)
        data["players"][uid]["biz_territory"] += 1
        save_data()
        bot.answer_callback_query(call.id, "✅ Территория +!")
        show_biz_menu(call.message.chat.id, uid, call.message.message_id)

    elif action == "biz_build_up":
        p = data["players"].get(uid, {})
        b = p.get("biz_building", 1)
        if b >= 5:
            return bot.answer_callback_query(call.id, "🏢 MAX!", show_alert=True)
        c = BIZ_BUILDING_COST.get(b, 0)
        if get_balance(uid) < c:
            return bot.answer_callback_query(call.id, f"❌ {c} 🪙!", show_alert=True)
        add_balance(uid, -c)
        data["players"][uid]["biz_building"] += 1
        save_data()
        bot.answer_callback_query(call.id, "✅ Здание +!")
        show_biz_menu(call.message.chat.id, uid, call.message.message_id)

    elif action == "biz_tax":
        p = data["players"].get(uid, {})
        tax = p.get("biz_tax", 0)
        if tax <= 0:
            return bot.answer_callback_query(call.id, "✅ Долгов нет.", show_alert=True)
        if get_balance(uid) < tax:
            return bot.answer_callback_query(call.id, f"❌ {tax} 🪙!", show_alert=True)
        add_balance(uid, -tax)
        data["players"][uid]["biz_tax"] = 0
        save_data()
        bot.answer_callback_query(call.id, "✅ Оплачено!")
        show_biz_menu(call.message.chat.id, uid, call.message.message_id)

# ---------- БАНК ----------
@bot.message_handler(func=lambda m: m.text.lower().strip() == "банк")
def bank_info(message):
    uid = str(message.from_user.id)
    p = data["players"].get(uid, {})
    b = p.get("bank", 0)
    d = p.get("deposit", 0)
    ds = p.get("deposit_start", 0)
    now = int(time.time())
    cd = 3 * 86400
    st = "Нет" if d == 0 else (
        f"✅ {d} 🪙 (Можно снять)" if now - ds >= cd else f"⏳ {d} 🪙 ({(cd - (now - ds)) // 3600} ч.)"
    )
    msg = (
        f"🏦 **БАНК**\n💰 Счет: {b} 🪙\n💎 Депозит: {st}\n📈 10% (раз в 3 дня)\n\n"
        f"`банк положить СУММА` / `банк снять СУММА`\n`депозит положить СУММА` / `депозит снять`"
    )
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text.lower().startswith("банк положить"))
def bank_dep(message):
    uid = str(message.from_user.id)
    try:
        a = int(message.text.split()[2])
        if a <= 0 or get_balance(uid) < a:
            return bot.reply_to(message, "❌ Мало.")
        add_balance(uid, -a)
        data["players"][uid]["bank"] += a
        save_data()
        bot.reply_to(message, f"✅ +{a} 🪙 в банк.")
    except Exception:
        bot.reply_to(message, "❌ `банк положить 1000`")

@bot.message_handler(func=lambda m: m.text.lower().startswith("банк снять"))
def bank_wd(message):
    uid = str(message.from_user.id)
    try:
        a = int(message.text.split()[2])
        if a <= 0 or data["players"][uid].get("bank", 0) < a:
            return bot.reply_to(message, "❌ Мало в банке.")
        data["players"][uid]["bank"] -= a
        add_balance(uid, a)
        save_data()
        bot.reply_to(message, f"✅ -{a} 🪙 из банка.")
    except Exception:
        bot.reply_to(message, "❌ `банк снять 1000`")

@bot.message_handler(func=lambda m: m.text.lower().startswith("депозит положить"))
def dep_make(message):
    uid = str(message.from_user.id)
    p = data["players"].get(uid, {})
    try:
        a = int(message.text.split()[2])
        if a <= 0 or get_balance(uid) < a:
            return bot.reply_to(message, "❌ Мало.")
        if p.get("deposit", 0) > 0 and (int(time.time()) - p.get("deposit_start", 0) < 3 * 86400):
            return bot.reply_to(message, "❌ Уже есть депозит.")
        add_balance(uid, -a)
        data["players"][uid]["deposit"] = a
        data["players"][uid]["deposit_start"] = int(time.time())
        save_data()
        bot.reply_to(message, f"✅ Депозит {a} 🪙 открыт.")
    except Exception:
        bot.reply_to(message, "❌ `депозит положить 1000`")

@bot.message_handler(func=lambda m: m.text.lower().strip() == "депозит снять")
def dep_wd(message):
    uid = str(message.from_user.id)
    p = data["players"].get(uid, {})
    d = p.get("deposit", 0)
    ds = p.get("deposit_start", 0)
    if d <= 0:
        return bot.reply_to(message, "❌ Нет депозита.")
    if int(time.time()) - ds < 3 * 86400:
        return bot.reply_to(message, f"⏳ Ждать {(3 * 86400 - (int(time.time()) - ds)) // 3600} ч.")
    i = int(d * 0.1)
    add_balance(uid, d + i)
    data["players"][uid]["deposit"] = 0
    data["players"][uid]["deposit_start"] = 0
    save_data()
    bot.reply_to(message, f"🏦 **Депозит закрыт!**\nВклад: {d} 🪙\nПроценты: +{i} 🪙\nИтого: **{d + i} 🪙**", parse_mode="Markdown")

# ---------- ПЕРЕВОД ----------
@bot.message_handler(func=lambda m: m.text.lower().startswith("перевод"))
def transfer(message):
    uid = str(message.from_user.id)
    if message.reply_to_message:
        if message.reply_to_message.from_user.is_bot:
            return bot.reply_to(message, "❌ Нельзя переводить боту.")
        t_uid = str(message.reply_to_message.from_user.id)
        try:
            a = int(message.text.split()[1])
        except Exception:
            return bot.reply_to(message, "❌ `перевод 1000` (в ответ)")
        if a <= 0 or get_balance(uid) < a:
            return bot.reply_to(message, "❌ Мало.")
        if a > 10000:
            return bot.reply_to(message, "❌ Лимит перевода — 10 000 🪙.")
        if t_uid == uid:
            return bot.reply_to(message, "❌ Себе нельзя.")
        if t_uid not in data["players"]:
            register_user(message.reply_to_message.from_user)
        add_balance(uid, -a)
        add_balance(t_uid, a)
        return bot.reply_to(message, f"✅ {a} 🪙 переведено {get_nick(t_uid)}.")
    try:
        a = int(message.text.split()[1])
        t_name = message.text.split()[2]
        if a <= 0 or get_balance(uid) < a:
            return bot.reply_to(message, "❌ Мало.")
        if a > 10000:
            return bot.reply_to(message, "❌ Лимит перевода — 10 000 🪙.")
        t_uid = get_user_by_username(t_name)
        if not t_uid or t_uid == uid:
            return bot.reply_to(message, "❌ Не найден.")
        add_balance(uid, -a)
        add_balance(t_uid, a)
        bot.reply_to(message, f"✅ {a} 🪙 переведено {get_nick(t_uid)}.")
    except Exception:
        bot.reply_to(message, "❌ `перевод 1000 ник`")

# ---------- МИНЫ ----------
MULT = {5: 1.25, 9: 1.45}

@bot.message_handler(func=lambda m: m.text.lower().startswith("мины"))
def start_mines(message):
    uid = str(message.from_user.id)
    try:
        p = message.text.split()
        bet = int(p[1])
        bmb = int(p[2]) if len(p) > 2 else 5
        if bet <= 0 or get_balance(uid) < bet:
            return bot.reply_to(message, "❌ Мало.")
        if bmb not in MULT:
            return bot.reply_to(message, "❌ Мины: 5 или 9.")
        add_balance(uid, -bet)
        gid = str(random.randint(10000, 99999))
        data["active_games"][gid] = {
            "type": "mines", "user": uid, "bet": bet,
            "mines": random.sample(range(25), bmb),
            "opened": [], "bombs": bmb,
        }
        save_data()
        bot.reply_to(message, f"💣 **МИНЫ** #{gid}\nСтавка: {bet} 🪙\nМин: {bmb}", reply_markup=mines_kb(gid), parse_mode="Markdown")
    except Exception:
        bot.reply_to(message, "❌ `мины 1000 5`")

def mines_kb(gid):
    g = data["active_games"].get(gid)
    if not g:
        return None
    kb = InlineKeyboardMarkup(row_width=5)
    for r in range(5):
        kb.row(*[InlineKeyboardButton(
            "💎" if (r * 5 + c) in g["opened"] else "❔",
            callback_data=f"m_{gid}_{r * 5 + c}"
        ) for c in range(5)])
    kb.row(InlineKeyboardButton("⭐ ЗАБРАТЬ", callback_data=f"mcash_{gid}"))
    return kb

@bot.callback_query_handler(func=lambda call: call.data.startswith("m_"))
def mines_play(call):
    _, gid, c = call.data.split("_")
    c = int(c)
    uid = str(call.from_user.id)
    g = data["active_games"].get(gid)
    if not g or g["user"] != uid or c in g["opened"]:
        return bot.answer_callback_query(call.id, "❌ Ошибка.")
    if c in g["mines"]:
        data["active_games"].pop(gid, None)
        save_data()
        kb = InlineKeyboardMarkup(row_width=5)
        for r in range(5):
            kb.row(*[InlineKeyboardButton(
                "💣" if (r * 5 + x) in g["mines"] else "💎",
                callback_data="ignore"
            ) for x in range(5)])
        bot.edit_message_text(
            f"💥 **МИНА!** Потеряно {g['bet']} 🪙.",
            call.message.chat.id, call.message.message_id,
            reply_markup=kb, parse_mode="Markdown",
        )
        return
    g["opened"].append(c)
    mult = MULT[g["bombs"]] ** len(g["opened"])
    rw = math.floor(g["bet"] * mult)
    save_data()
    bot.edit_message_text(
        f"💣 **МИНЫ**\nСтавка: {g['bet']} 🪙\nОткрыто: {len(g['opened'])}\nМнож: x{mult:.2f}\nЗабрать: {rw} 🪙",
        call.message.chat.id, call.message.message_id,
        reply_markup=mines_kb(gid), parse_mode="Markdown",
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("mcash_"))
def mines_out(call):
    gid = call.data.split("_")[1]
    uid = str(call.from_user.id)
    g = data["active_games"].get(gid)
    if not g or g["user"] != uid or not g["opened"]:
        return bot.answer_callback_query(call.id)
    rw = math.floor(g["bet"] * (MULT[g["bombs"]] ** len(g["opened"])))
    add_balance(uid, rw)
    data["active_games"].pop(gid, None)
    save_data()
    bot.edit_message_text(
        f"🏆 **Забрано!** +{rw} 🪙",
        call.message.chat.id, call.message.message_id,
        reply_markup=None, parse_mode="Markdown",
    )

# ---------- КРАШ ----------
@bot.message_handler(func=lambda m: m.text.lower().startswith("краш"))
def start_crash(message):
    uid = str(message.from_user.id)
    try:
        bet = int(message.text.split()[1])
        if bet <= 0 or get_balance(uid) < bet:
            return bot.reply_to(message, "❌ Мало.")
        add_balance(uid, -bet)
        gid = str(random.randint(10000, 99999))
        data["active_games"][gid] = {
            "type": "crash", "user": uid, "bet": bet,
            "crash_point": round(random.uniform(1.5, 10.0), 2),
            "current": 1.0, "active": True,
        }
        save_data()
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("💰 ЗАБРАТЬ", callback_data=f"ccash_{gid}"))
        msg = bot.reply_to(message, f"🚀 **CRASH**\nСтавка: {bet}\nКоэф: x1.00", reply_markup=kb, parse_mode="Markdown")
        threading.Thread(target=crash_loop, args=(gid, uid, msg.chat.id, msg.message_id), daemon=True).start()
    except Exception:
        bot.reply_to(message, "❌ `краш 1000`")

def crash_loop(gid, uid, cid, mid):
    time.sleep(0.7)
    while True:
        g = data["active_games"].get(gid)
        if not g or not g.get("active"):
            break
        g["current"] = round(g["current"] + 0.5, 2)
        save_data()
        if g["current"] >= g["crash_point"]:
            g["active"] = False
            save_data()
            try:
                bot.edit_message_text(
                    f"💥 **КРАШ на x{g['current']:.2f}!**\nПотеряно {g['bet']} 🪙.",
                    cid, mid, reply_markup=None, parse_mode="Markdown",
                )
            except Exception:
                pass
            data["active_games"].pop(gid, None)
            save_data()
            break
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("💰 ЗАБРАТЬ", callback_data=f"ccash_{gid}"))
        try:
            bot.edit_message_text(
                f"🚀 **CRASH**\nСтавка: {g['bet']}\nКоэф: x{g['current']:.2f}",
                cid, mid, reply_markup=kb, parse_mode="Markdown",
            )
        except Exception:
            pass
        time.sleep(0.7)

@bot.callback_query_handler(func=lambda call: call.data.startswith("ccash_"))
def crash_out(call):
    gid = call.data.split("_")[1]
    uid = str(call.from_user.id)
    g = data["active_games"].get(gid)
    if not g or g["user"] != uid or not g["active"]:
        return bot.answer_callback_query(call.id)
    g["active"] = False
    rw = math.floor(g["bet"] * g["current"])
    add_balance(uid, rw)
    data["active_games"].pop(gid, None)
    save_data()
    bot.edit_message_text(
        f"🏆 **Забрано на x{g['current']:.2f}!** +{rw} 🪙",
        call.message.chat.id, call.message.message_id,
        reply_markup=None, parse_mode="Markdown",
    )

# ---------- РУЛЕТКА ----------
@bot.message_handler(func=lambda m: " на " in m.text.lower() and m.text.lower().split()[0].isdigit())
def roulette(message):
    uid = str(message.from_user.id)
    t = message.text.lower().strip()
    p = t.split()
    try:
        bet = int(p[0])
        tg = [p[i] for i in range(2, len(p)) if p[i] != "на"]
        cost = bet * len(tg)
        if cost <= 0 or get_balance(uid) < cost:
            return bot.reply_to(message, f"❌ Нужно {cost} 🪙.")
        add_balance(uid, -cost)
        wn = random.randint(0, 36)
        wc = "green" if wn == 0 else ("red" if 1 <= wn <= 18 else "black")
        sym = {"green": "🟢", "red": "🔴", "black": "⚫️"}[wc]
        tw = 0
        res = []
        for x in tg:
            win, mlt = False, 0
            if "-" in x:
                try:
                    s, e = map(int, x.split("-"))
                    mlt = max(1, math.floor(37 / (e - s + 1))) if s <= wn <= e else 0
                except Exception:
                    pass
            elif x.isdigit():
                if int(x) == wn:
                    win, mlt = True, 36
            elif x in ["red", "к", "кр", "красное", "красный"]:
                if wc == "red":
                    win, mlt = True, 2
            elif x in ["black", "ч", "чёрное", "черное", "чёрный", "черный"]:
                if wc == "black":
                    win, mlt = True, 2
            elif x in ["green", "з", "зелёное", "зеленое", "зеро"]:
                if wc == "green":
                    win, mlt = True, 36
            elif x in ["even", "чет", "чёт", "четное"]:
                if wn != 0 and wn % 2 == 0:
                    win, mlt = True, 2
            elif x in ["odd", "нечет", "нечёт", "нечетное"]:
                if wn % 2 != 0:
                    win, mlt = True, 2
            if win:
                r = bet * mlt
                tw += r
                res.append(f"✅ {bet} на {x} (+{r})")
            else:
                res.append(f"❌ {bet} на {x}")
        add_balance(uid, tw)
        bot.reply_to(message, f"🎰 {sym} **{wn}**\n" + "\n".join(res) + f"\n💰 Итог: {tw} 🪙", parse_mode="Markdown")
    except Exception:
        bot.reply_to(message, "❌ `1000 на 5`")

# ---------- ПОМОЩЬ ----------
@bot.message_handler(func=lambda m: m.text.lower().strip() == "помощь")
def help_cmd(message):
    text = (
        "📖 **ИНСТРУКЦИЯ**\n\n"
        "**ИГРЫ**\n`слот 1000`\n`мины 1000 5`\n`краш 1000`\n`1000 на 5`\n\n"
        "**БАНК**\n`банк`, `депозит`\n\n"
        "**БИЗНЕС**\n`мой бизнес`\n\n"
        "**КЛАНЫ**\n`создать клан ИМЯ` (10 000)\n`вступить клан ID`\n`мой клан`\n`выйти из клана`\n\n"
        "**ПЕРЕВОД**\n`перевод 1000 ник` (лимит 10 000)\n\n"
        "**АДМИН**\n`/give ID СУММА`\n`/wipe`"
    )
    bot.reply_to(message, text, parse_mode="Markdown")

# ---------- ДОНАТ ----------
@bot.message_handler(commands=['donate'])
def donate_cmd(message):
    kb = InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("⭐ 25 Звезд (12 500)", callback_data="pay_25"),
        InlineKeyboardButton("⭐ 50 Звезд (25 000)", callback_data="pay_50"),
        InlineKeyboardButton("⭐ 100 Звезд (50 000)", callback_data="pay_100"),
        InlineKeyboardButton("📝 Выбрать количество", callback_data="donate_custom"),
    )
    bot.send_message(message.chat.id, "💖 **Донат**\nВыберите пакет:", reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_"))
def pay(call):
    s = int(call.data.split("_")[1])
    c = s * 500
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
        if s < 1 or s > 5000:
            return bot.reply_to(message, "❌ Введите число от 1 до 5000.")
        c = s * 500
        bot.send_invoice(message.chat.id, "Донат", f"+{c} Mon1Coin", f"don_{s}_{c}", "", "XTR", [LabeledPrice("Донат", s)])
    except Exception:
        bot.reply_to(message, "❌ Неверный формат. Введите число.")

@bot.pre_checkout_query_handler(func=lambda q: True)
def pre_chk(q):
    bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def success(m):
    p = m.successful_payment.invoice_payload
    if p.startswith("don_"):
        c = int(p.split("_")[2])
        add_balance(m.from_user.id, c)
        bot.send_message(m.chat.id, f"🎉 +{c} 🪙")

# ---------- БАЛАНС / ПРОФИЛЬ / БОНУС ----------
@bot.message_handler(func=lambda m: m.text.lower().strip() in ["б", "баланс"])
def bal_cmd(message):
    bot.reply_to(message, f"🪙 Баланс: {get_balance(message.from_user.id)} Mon1Coin")

@bot.message_handler(func=lambda m: m.text.lower().strip() == "профиль")
def profile_cmd(message):
    uid = message.from_user.id
    p = data["players"].get(str(uid), {})
    c_info = "Нет"
    if p.get("clan_id"):
        c_info = f"{data['clans'].get(str(p['clan_id']), {}).get('name', '?')} ({p.get('role', 'игрок')})"
    bot.reply_to(message, f"👤 **Профиль**\n🆔 ID: `{p.get('short_id')}`\n📛 Ник: {get_nick(uid)}\n🪙 Баланс: {get_balance(uid)}\n🛡 Клан: {c_info}", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text.lower().strip() == "бонус")
def bonus_cmd(message):
    uid = str(message.from_user.id)
    now = int(time.time())
    last = data["players"].get(uid, {}).get("last_bonus", 0)
    if now - last < 86400:
        return bot.reply_to(message, f"⏳ Ждать: {(86400 - (now - last)) // 3600} ч.")
    amt = random.randint(1000, 2000)
    add_balance(uid, amt)
    data["players"][uid]["last_bonus"] = now
    save_data()
    bot.reply_to(message, f"🎁 **БОНУС!** +{amt} 🪙", parse_mode="Markdown")

# ---------- КЛАНЫ ----------
@bot.message_handler(func=lambda m: m.text.lower().strip().startswith("создать клан"))
def clan_create(message):
    uid = str(message.from_user.id)
    try:
        name = message.text.split(maxsplit=2)[2].strip()[:20]
        if not name:
            raise ValueError
    except Exception:
        return bot.reply_to(message, "❌ `создать клан НАЗВАНИЕ`", parse_mode="Markdown")

    p = data["players"].get(uid, {})
    if p.get("clan_id"):
        return bot.reply_to(message, "❌ Вы уже в клане.")
    cost = 10000
    if get_balance(uid) < cost:
        return bot.reply_to(message, f"❌ Создание клана стоит {cost} 🪙.")
    if any(c.get("name", "").lower() == name.lower() for c in data["clans"].values()):
        return bot.reply_to(message, "❌ Клан с таким названием уже есть.")

    cid = str(data["next_id"])
    data["next_id"] += 1
    data["clans"][cid] = {
        "name": name,
        "leader": uid,
        "members": [uid],
        "created": int(time.time()),
    }
    data["players"][uid]["clan_id"] = cid
    data["players"][uid]["role"] = "лидер"
    add_balance(uid, -cost)
    save_data()
    bot.reply_to(
        message,
        f"🛡 **Клан создан!**\nНазвание: **{name}**\nID клана: `{cid}`\nЛидер: {get_nick(uid)}",
        parse_mode="Markdown",
    )

@bot.message_handler(func=lambda m: m.text.lower().strip().startswith("вступить клан"))
def clan_join(message):
    uid = str(message.from_user.id)
    try:
        cid = message.text.split()[2].strip()
    except Exception:
        return bot.reply_to(message, "❌ `вступить клан ID`", parse_mode="Markdown")

    clan = data["clans"].get(cid)
    if not clan:
        return bot.reply_to(message, "❌ Клан не найден.")
    p = data["players"].get(uid, {})
    if p.get("clan_id"):
        return bot.reply_to(message, "❌ Вы уже в клане.")
    if len(clan["members"]) >= 50:
        return bot.reply_to(message, "❌ Клан заполнен (макс. 50).")

    clan["members"].append(uid)
    data["players"][uid]["clan_id"] = cid
    data["players"][uid]["role"] = "игрок"
    save_data()
    bot.reply_to(message, f"✅ Вы вступили в клан **{clan['name']}**!", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text.lower().strip() == "мой клан")
def clan_info(message):
    uid = str(message.from_user.id)
    p = data["players"].get(uid, {})
    cid = p.get("clan_id")
    if not cid:
        return bot.reply_to(
            message,
            "🛡 Вы не в клане.\n`создать клан НАЗВАНИЕ` (10 000 🪙)\n`вступить клан ID`",
            parse_mode="Markdown",
        )
    clan = data["clans"].get(str(cid))
    if not clan:
        return bot.reply_to(message, "❌ Клан не найден.")

    members_lines = []
    for i, muid in enumerate(clan["members"], 1):
        mp = data["players"].get(muid, {})
        nick = mp.get("username", "Player")
        sid = mp.get("short_id", "0")
        role = mp.get("role", "игрок")
        mark = "👑" if muid == clan["leader"] else "•"
        members_lines.append(f"{mark} `{sid}` — {nick} ({role})")

    leader_nick = get_nick(clan["leader"])
    text = (
        f"🛡 **КЛАН: {clan['name']}**\n"
        f"🆔 ID клана: `{cid}`\n"
        f"👑 Лидер: {leader_nick} (`{get_user_short_id(clan['leader'])}`)\n"
        f"👥 Участников: **{len(clan['members'])}/50**\n\n"
        f"**Участники:**\n" + "\n".join(members_lines)
    )
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text.lower().strip() == "выйти из клана")
def clan_leave(message):
    uid = str(message.from_user.id)
    p = data["players"].get(uid, {})
    cid = p.get("clan_id")
    if not cid:
        return bot.reply_to(message, "❌ Вы не в клане.")
    clan = data["clans"].get(str(cid))
    if not clan:
        data["players"][uid]["clan_id"] = None
        data["players"][uid]["role"] = "none"
        save_data()
        return bot.reply_to(message, "✅ Вы вышли из клана.")
    if clan["leader"] == uid:
        if len(clan["members"]) > 1:
            return bot.reply_to(message, "❌ Сначала передайте лидерство или распустите клан.")
        del data["clans"][str(cid)]
    else:
        clan["members"].remove(uid)
    data["players"][uid]["clan_id"] = None
    data["players"][uid]["role"] = "none"
    save_data()
    bot.reply_to(message, "✅ Вы вышли из клана.")

# ---------- АДМИН ----------
@bot.message_handler(commands=['give'])
def give(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    try:
        a = m.text.split()[1:]
        sid, amt = a[0], int(a[1])
        real_uid = get_user_by_short_id(sid)
        if not real_uid:
            return bot.reply_to(m, "❌ Игрок не найден.")
        add_balance(real_uid, amt)
        bot.reply_to(m, f"✅ Выдано {amt} 🪙 игроку {sid}.")
    except Exception:
        bot.reply_to(m, "❌ `/give ID СУММА`", parse_mode="Markdown")

@bot.message_handler(commands=['reset'])
def rst(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    try:
        sid = m.text.split()[1]
        real_uid = get_user_by_short_id(sid)
        if real_uid:
            data["players"][real_uid]["balance"] = 0
            save_data()
            bot.reply_to(m, "♻️ Сброшено.")
    except Exception:
        pass

@bot.message_handler(commands=['wipe'])
def wipe(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    for u in data["players"]:
        data["players"][u]["balance"] = 1000
    save_data()
    bot.reply_to(m, "♻️ Все по 1000.")

@bot.message_handler(commands=['createpromo'])
def promo(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    try:
        a = m.text.split()[1:]
        data["promos"][a[0].upper()] = {"amount": int(a[1]), "uses_left": int(a[2])}
        save_data()
        bot.reply_to(m, "✅ Создан.")
    except Exception:
        bot.reply_to(m, "❌ `/createpromo КОД СУММА ЮЗЫ`", parse_mode="Markdown")

# ---------- ОБЩИЙ ТЕКСТ ----------
@bot.message_handler(content_types=['text'])
def handle_text(m):
    if m.text.startswith('/'):
        return
    t = m.text.lower().strip()
    u = str(m.from_user.id)

    if t.startswith("сменить ник"):
        parts = m.text.split(maxsplit=2)
        if len(parts) >= 3:
            new_nick = parts[2].strip()[:15]
            if new_nick:
                if u not in data["players"]:
                    register_user(m.from_user)
                data["players"][u]["username"] = new_nick
                save_data()
                return bot.reply_to(m, "✅ Ник изменен.")

    if len(t.split()) == 1 and len(t) > 3 and t.isalnum():
        code = t.upper()
        if code in data["promos"]:
            pr = data["promos"][code]
            if pr["uses_left"] <= 0:
                return bot.reply_to(m, "❌ Не работает.")
            if [u, code] in data["activations"]:
                return bot.reply_to(m, "❌ Уже активировали!")
            add_balance(u, pr["amount"])
            pr["uses_left"] -= 1
            data["activations"].append([u, code])
            save_data()
            return bot.reply_to(m, f"🎉 +{pr['amount']} 🪙")

@bot.callback_query_handler(func=lambda call: call.data == "ignore")
def ignore(call):
    bot.answer_callback_query(call.id)

# ---------- ЗАПУСК ----------
try:
    bot.remove_webhook()
except Exception:
    pass

recover_games()
_real_save()

print("BOT STARTED")
bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=25)
