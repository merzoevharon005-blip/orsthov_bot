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
                cid, mid, reply_markup=kb, parse_mode="Mark
