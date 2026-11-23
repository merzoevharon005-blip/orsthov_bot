import os, random, math, time, telebot, threading, json, pathlib
import hmac, hashlib, secrets
from urllib.parse import parse_qsl
from flask import Flask, jsonify, request, send_from_directory
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, WebAppInfo

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN: raise ValueError("Не задан BOT_TOKEN")

ADMIN_IDS = [8211650013, 6940877915]
DATA_DIR = pathlib.Path("/app/data"); DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = DATA_DIR / "database.json"

data = {"players": {}, "promos": {}, "activations": [], "history": [], "clans": {}, "next_id": 1, "active_games": {}, "roulette_bets": {}, "duels": {}, "banned": {}, "muted": {}, "blacklist": {}, "reports": [], "admin_logs": []}
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
    if "duels" not in data: data["duels"] = {}
    if "promos" not in data: data["promos"] = {}
    if "activations" not in data: data["activations"] = []
    if "banned" not in data: data["banned"] = {}
    if "muted" not in data: data["muted"] = {}
    if "blacklist" not in data: data["blacklist"] = {}
    if "reports" not in data: data["reports"] = []
    if "admin_logs" not in data: data["admin_logs"] = []
    if changed: save_data()

migrate_data()
data.setdefault("mini_sessions", {})
bot = telebot.TeleBot(TOKEN)

# ==================== TELEGRAM MINI APP ====================

WEBAPP_URL = "https://bot-1794808232-3061-mon1x.bothost.tech"
WEBAPP_DIR = pathlib.Path(__file__).parent / "webapp"
web_app = Flask(__name__, static_folder=None)


def validate_telegram_init_data(init_data: str):
    """Проверяет подпись initData от Telegram. Не доверяем данным из браузера."""
    if not init_data or len(init_data) > 10000:
        return None

    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None

        data_check_string = "\n".join(
            f"{key}={parsed[key]}" for key in sorted(parsed)
        )
        secret_key = hmac.new(
            b"WebAppData", TOKEN.encode("utf-8"), hashlib.sha256
        ).digest()
        calculated_hash = hmac.new(
            secret_key, data_check_string.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(calculated_hash, received_hash):
            return None

        auth_date = int(parsed.get("auth_date", "0"))
        if auth_date <= 0 or time.time() - auth_date > 86400:
            return None

        user = json.loads(parsed.get("user", "{}"))
        if not user.get("id"):
            return None
        return user
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


@web_app.route("/")
def mini_app_index():
    return send_from_directory(WEBAPP_DIR, "index.html")


@web_app.route("/api/me", methods=["POST"])
def mini_app_me():
    payload = request.get_json(silent=True) or {}
    tg_user = validate_telegram_init_data(payload.get("initData", ""))
    if not tg_user:
        return jsonify({"ok": False, "error": "Не удалось подтвердить Telegram-пользователя"}), 401

    uid = str(tg_user["id"])
    if is_blocked(uid):
        return jsonify({"ok": False, "error": "Доступ к игре ограничен"}), 403

    with db_lock:
        player = data.get("players", {}).get(uid)
        if not player:
            return jsonify({"ok": False, "error": "Сначала запусти бота командой /start"}), 404
        result = {
            "ok": True,
            "name": player.get("username") or tg_user.get("first_name") or "Игрок",
            "balance": int(player.get("balance", 0)),
            "short_id": player.get("short_id", 0),
            "status": player.get("donate_status", "Нет"),
            "bonus_ready": int(time.time()) - int(player.get("last_bonus", 0)) >= 86400,
            "bonus_seconds_left": max(0, 86400 - (int(time.time()) - int(player.get("last_bonus", 0)))),
            "promo_count": len(data.get("promos", {}))
        }
    return jsonify(result)


def mini_auth_user():
    payload = request.get_json(silent=True) or {}
    tg_user = validate_telegram_init_data(payload.get("initData", ""))
    if not tg_user:
        return None, (jsonify({"ok": False, "error": "Не удалось подтвердить Telegram-пользователя"}), 401)
    uid = str(tg_user["id"])
    if is_blocked(uid):
        return None, (jsonify({"ok": False, "error": "Доступ к игре ограничен"}), 403)
    if uid not in data.get("players", {}):
        return None, (jsonify({"ok": False, "error": "Сначала запусти бота командой /start"}), 404)
    return uid, None


@web_app.route("/api/bonus", methods=["POST"])
def mini_app_bonus():
    uid, error = mini_auth_user()
    if error:
        return error
    player = data["players"][uid]
    now = int(time.time())
    last = int(player.get("last_bonus", 0))
    left = 86400 - (now - last)
    if left > 0:
        return jsonify({"ok": False, "error": "Бонус уже получен", "seconds_left": left}), 429
    reward = random.randint(1000, 3000)
    player["balance"] = int(player.get("balance", 0)) + reward
    player["last_bonus"] = now
    save_data()
    try:
        complete_quest(uid, "bonus")
    except Exception as e:
        print(f"Mini App bonus quest warning: {e}")
    return jsonify({"ok": True, "reward": reward, "balance": int(player["balance"]), "bonus_ready": False, "bonus_seconds_left": 86400})


@web_app.route("/api/promo", methods=["POST"])
def mini_app_promo():
    uid, error = mini_auth_user()
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    code = str(payload.get("code", "")).strip().upper()
    if not code or len(code) > 40:
        return jsonify({"ok": False, "error": "Введи корректный промокод"}), 400
    if code not in data.get("promos", {}):
        return jsonify({"ok": False, "error": "Промокод не найден или уже не действует"}), 404
    activation_key = f"{uid}_{code}"
    if activation_key in data.setdefault("activations", []):
        return jsonify({"ok": False, "error": "Ты уже активировал этот промокод"}), 409
    amount = int(data["promos"][code])
    if amount <= 0:
        return jsonify({"ok": False, "error": "У этого промокода некорректная награда"}), 400
    data["players"][uid]["balance"] = int(data["players"][uid].get("balance", 0)) + amount
    data["activations"].append(activation_key)
    save_data()
    return jsonify({"ok": True, "code": code, "reward": amount, "balance": int(data["players"][uid]["balance"])})


# Мини-игры в Mini App — тренировочные режимы без ставок и списания/начисления валюты.
@web_app.route("/api/mines/start", methods=["POST"])
def mini_mines_start():
    uid, error = mini_auth_user()
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    try:
        bombs = int(payload.get("bombs", 5))
    except (TypeError, ValueError):
        bombs = 5
    if bombs not in (3, 5, 9):
        return jsonify({"ok": False, "error": "Выбери 3, 5 или 9 мин"}), 400
    sessions = data.setdefault("mini_sessions", {})
    for old_id, old in list(sessions.items()):
        if old.get("user") == uid and old.get("type") == "mines":
            sessions.pop(old_id, None)
    sid = secrets.token_urlsafe(12)
    mines = random.sample(range(25), bombs)
    sessions[sid] = {"type": "mines", "user": uid, "mines": mines, "opened": [], "active": True, "created": int(time.time())}
    save_data()
    return jsonify({"ok": True, "session": sid, "bombs": bombs, "opened": [], "active": True})


@web_app.route("/api/mines/open", methods=["POST"])
def mini_mines_open():
    uid, error = mini_auth_user()
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    sid = str(payload.get("session", ""))
    try:
        cell = int(payload.get("cell", -1))
    except (TypeError, ValueError):
        cell = -1
    session = data.setdefault("mini_sessions", {}).get(sid)
    if not session or session.get("type") != "mines" or session.get("user") != uid or not session.get("active"):
        return jsonify({"ok": False, "error": "Раунд уже завершён. Начни новый."}), 404
    if not 0 <= cell < 25 or cell in session["opened"]:
        return jsonify({"ok": False, "error": "Эта клетка недоступна"}), 400
    if cell in session["mines"]:
        session["active"] = False
        save_data()
        return jsonify({"ok": True, "hit": True, "active": False, "opened": session["opened"], "mines": session["mines"], "score": len(session["opened"])})
    session["opened"].append(cell)
    if len(session["opened"]) >= 25 - len(session["mines"]):
        session["active"] = False
    save_data()
    return jsonify({"ok": True, "hit": False, "active": session["active"], "opened": session["opened"], "score": len(session["opened"])})


@web_app.route("/api/crash/start", methods=["POST"])
def mini_crash_start():
    uid, error = mini_auth_user()
    if error:
        return error
    sessions = data.setdefault("mini_sessions", {})
    for old_id, old in list(sessions.items()):
        if old.get("user") == uid and old.get("type") == "crash":
            sessions.pop(old_id, None)
    sid = secrets.token_urlsafe(12)
    sessions[sid] = {"type": "crash", "user": uid, "crash_point": round(random.uniform(1.5, 8.0), 2), "started": time.time(), "active": True}
    save_data()
    return jsonify({"ok": True, "session": sid, "multiplier": 1.0, "active": True})


@web_app.route("/api/crash/state", methods=["POST"])
def mini_crash_state():
    uid, error = mini_auth_user()
    if error:
        return error
    payload = request.get_json(silent=True) or {}
    sid = str(payload.get("session", ""))
    session = data.setdefault("mini_sessions", {}).get(sid)
    if not session or session.get("type") != "crash" or session.get("user") != uid:
        return jsonify({"ok": False, "error": "Раунд не найден"}), 404
    if session.get("active"):
        elapsed = max(0.0, time.time() - float(session["started"]))
        current = 1.0 + elapsed * 0.35
        crashed = current >= float(session["crash_point"])
        if crashed:
            current = float(session["crash_point"])
            session["active"] = False
            save_data()
    else:
        current = float(session.get("crash_point", 1.0))
        crashed = True
    return jsonify({"ok": True, "multiplier": round(current, 2), "active": bool(session.get("active")), "crashed": crashed})


@web_app.route("/health")
def mini_app_health():
    return jsonify({"ok": True, "service": "MON1 GAME Mini App"})


def run_mini_app_server():
    port = int(os.getenv("PORT", "3000"))
    web_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)



def is_blocked(uid):
    """ЧС / бан / мут — полная блокировка взаимодействия"""
    uid = str(uid)
    if uid in data.get("blacklist", {}):
        return "chs"
    if uid in data.get("banned", {}):
        return "ban"
    mute = data.get("muted", {}).get(uid)
    if mute:
        until = mute.get("until", 0)
        if until == 0 or until > int(time.time()):
            return "mute"
        data["muted"].pop(uid, None)
        save_data()
    return None

def add_admin_log(action, admin_id, target=None, detail=""):
    entry = {
        "time": int(time.time()),
        "action": action,
        "admin": str(admin_id),
        "target": str(target) if target else None,
        "detail": detail
    }
    data.setdefault("admin_logs", []).append(entry)
    # храним последние 300 логов
    if len(data["admin_logs"]) > 300:
        data["admin_logs"] = data["admin_logs"][-300:]
    save_data()

# Блокировка ЧС / бан / мут — раньше всех команд
@bot.message_handler(func=lambda m: is_blocked(m.from_user.id) is not None, content_types=["text"])
def block_restricted(message):
    status = is_blocked(message.from_user.id)
    if status in ("chs", "ban"):
        return  # полный игнор
    if status == "mute":
        try:
            bot.reply_to(message, "🔇 Вы в муте и не можете писать.")
        except:
            pass

@bot.callback_query_handler(func=lambda call: is_blocked(call.from_user.id) is not None)
def block_restricted_cb(call):
    status = is_blocked(call.from_user.id)
    if status in ("chs", "ban"):
        try:
            bot.answer_callback_query(call.id, "⛔ Доступ запрещён.", show_alert=True)
        except:
            pass
        return
    if status == "mute":
        try:
            bot.answer_callback_query(call.id, "🔇 Вы в муте.", show_alert=True)
        except:
            pass

MULT = {3: 1.15, 5: 1.25, 9: 1.45}
# Дешёвая прокачка бизнеса (в разумных рамках)
BIZ_TERRITORY_COST = {0: 3000, 1: 8000, 2: 20000, 3: 50000, 4: 120000, 5: 300000}
BIZ_BUILDING_COST = {1: 5000, 2: 15000, 3: 40000, 4: 100000, 5: 250000}

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
    """Бонус к игровому выигрышу по статусу: VIP +3%, Premium +6%, Ultra +10%."""
    status = data["players"].get(str(uid), {}).get("donate_status", "Нет")
    return {"VIP": 1.03, "Premium": 1.06, "Ultra": 1.10}.get(status, 1.0)

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

    bot_username = bot.get_me().username
    add_to_group_url = f"https://t.me/{bot_username}?startgroup=true"

    kb = InlineKeyboardMarkup(row_width=2)
    if message.chat.type == "private":
        kb.add(InlineKeyboardButton("🎮 Открыть MON1 GAME", web_app=WebAppInfo(url=WEBAPP_URL)))
    kb.add(
        InlineKeyboardButton("➕ Добавить бота в свой чат", url=add_to_group_url),
        InlineKeyboardButton("📖 Помощь", callback_data="start_help")
    )

    bot.send_message(
        message.chat.id,
        f"🎮 **MON1 GAME RPG**\n"
        f"👋 Добро пожаловать, **{get_nick(message.from_user.id)}**!\n\n"
        f"🚀 Играй, развивайся, выполняй задания, открывай бизнес и создавай кланы.\n\n"
        f"🌐 **Наши сообщества**\n"
        f"📢 [Канал новостей](https://t.me/mon1bots)\n"
        f"💬 [Общий чат](https://t.me/mon1not)\n\n"
        f"👇 Выбери действие:",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data == "start_help")
def start_help_callback(call):
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "📚 **ПОМОЩЬ MON1 GAME RPG**\n"
        "Выбери нужный раздел, чтобы посмотреть команды и узнать, как ими пользоваться.",
        reply_markup=help_keyboard(),
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("home_"))
def home_callbacks(call):
    action = call.data[5:]
    uid = str(call.from_user.id)
    if uid not in data["players"]:
        register_user(call.from_user)
    if action == "balance":
        bot.answer_callback_query(call.id, f"Баланс: {get_balance(uid):,} 🪙", show_alert=True)
    elif action == "business":
        bot.answer_callback_query(call.id)
        if data["players"].get(uid, {}).get("biz_territory", 0) == 0:
            kb = InlineKeyboardMarkup().add(InlineKeyboardButton(
                "🏗 Открыть свой бизнес · 3 000 🪙", callback_data="biz_build"))
            bot.send_message(call.message.chat.id,
                f"🏢 **ТВОЙ БИЗНЕС**\n"
                f"У тебя пока нет предприятия.\n\n"
                f"🏗 Построй первый уровень территории за **{BIZ_TERRITORY_COST[0]:,} 🪙**, "
                f"чтобы начать получать доход.", reply_markup=kb, parse_mode="Markdown")
        else:
            show_biz_menu(call.message.chat.id, uid, None)
    elif action == "quests":
        bot.answer_callback_query(call.id, "Открой задания командой «квесты».", show_alert=True)
    elif action == "help":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id,
            "📚 **ЦЕНТР ПОМОЩИ**\nВыбери раздел:", reply_markup=help_keyboard(), parse_mode="Markdown")
    elif action == "profile":
        bot.answer_callback_query(call.id, "Открой профиль командой «профиль».", show_alert=True)
    elif action == "clan":
        bot.answer_callback_query(call.id, "Открой раздел командой «мой клан».", show_alert=True)

def help_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("🎮 Игры", callback_data="help_games"),
           InlineKeyboardButton("💰 Экономика", callback_data="help_eco"))
    kb.add(InlineKeyboardButton("🏢 Бизнес", callback_data="help_business"),
           InlineKeyboardButton("🛡 Кланы", callback_data="help_clans"))
    kb.add(InlineKeyboardButton("💎 Статусы и донат", callback_data="help_donate"))
    return kb

@bot.message_handler(commands=['help'])
@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() in ['помощь', 'help'])
def help_command(message):
    bot.reply_to(message,
        "📚 **ПУТЕВОДИТЕЛЬ MON1 GAME**\n"
        ""
        "Новичок? Начни с раздела «Экономика» и узнай, как получать монеты.\n\n"
        "🎮 Игры — игровые режимы и команды.\n"
        "💰 Экономика — баланс, бонусы, банк и переводы.\n"
        "🏢 Бизнес — управление предприятием.\n"
        "🛡 Кланы — создание и развитие команды.\n"
        "💎 Статусы — Stars и дополнительные возможности.\n\n"
        "👇 **Выбери интересующий раздел:**",
        reply_markup=help_keyboard(), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("help_"))
def help_callbacks(call):
    section = call.data.split("_", 1)[1]
    pages = {
        "games": "🎮 **ИГРОВАЯ ПЛОЩАДКА**\n"
                 "Здесь собраны игровые команды. Напиши команду в чат,\n"
                 "укажи ставку и следуй подсказкам бота.\n\n"
                 "🎰 `слот 1000` — сыграть в слоты со ставкой 1 000 монет.\n"
                 "💣 `мины 1000 5` — открыть поле с 5 минами.\n"
                 "🚀 `краш 1000` — следить за ростом коэффициента.\n"
                 "🃏 `джокер 1000` — пройти раунд с выбором карт.\n"
                 "🎡 `1000 5 12` — подготовить ставку на колесо, затем `го`.\n\n"
                 "💡 Перед началом проверь условия раунда и размер ставки.",
        "eco": "💰 **ЭКОНОМИКА И ПЕРСОНАЖ**\n"
               "Управляй монетами, получай награды и развивай профиль.\n\n"
               "💳 `б` — посмотреть свой баланс.\n"
               "🎁 `бонус` — получить ежедневную награду.\n"
               "👤 `профиль` — открыть информацию о персонаже.\n"
               "🆔 `узнать ид` — узнать игровой ID.\n"
               "🏆 `топ` — посмотреть рейтинг игроков.\n"
               "🏦 `банк` — открыть банковский раздел.\n"
               "📜 `квесты` — посмотреть задания.\n"
               "🎁 `забрать квест` — забрать доступную награду за задание.\n"
               "🔁 `перевод 1000 ник` — отправить монеты игроку.\n"
               "🎟 `промо КОД` — активировать промокод.\n"
               "✏️ `сменить ник НОВЫЙ_НИК` — изменить игровой ник.\n\n"
               "💡 Внимательно проверяй сумму и имя получателя перед переводом.",
        "business": "🏢 **БИЗНЕС — УПРАВЛЕНИЕ**\n"
                    "Открой своё дело и получай игровой доход со временем.\n\n"
                    "🏗 `мой бизнес` — открыть панель бизнеса.\n"
                    "🧱 `Построить бизнес` — купить первый уровень территории за 3 000 🪙.\n"
                    "📍 `Терр.` — расширить территорию и увеличить доход.\n"
                    "🏢 `Здание` — улучшить здание и увеличить доход.\n"
                    "💰 `Собрать` — забрать накопленный доход на баланс.\n"
                    "🧾 После сбора появляется налог — его можно оплатить кнопкой `Налоги`.\n"
                    "⏳ Доход накапливается максимум за 24 часа.\n\n"
                    "💡 Следи за налогами: пока они не оплачены, собрать следующий доход нельзя.",
        "clans": "🛡 **КЛАНЫ И КОМАНДА**\n"
                 "Объединяйся с другими игроками и развивай свой клан.\n\n"
                 "🏰 `создать клан ИМЯ` — создать клан за 10 000 🪙.\n"
                 "🤝 `вступить клан ID` — вступить в существующий клан.\n"
                 "📋 `мой клан` — посмотреть информацию о своём клане.\n"
                 "🚪 `выйти из клана` — покинуть клан.\n"
                 "🏆 `топ кланов` — открыть рейтинг кланов.\n"
                 "🏦 `клан казна положить СУММА` — внести монеты в казну.\n"
                 "💸 `клан казна снять СУММА` — запросить снятие монет (если разрешено).",
        "donate": "💎 **ЗВЁЗДЫ И СТАТУСЫ**\n"
                  "Здесь можно посмотреть дополнительные варианты поддержки проекта.\n\n"
                  "⭐ `донат` — открыть меню пополнения валюты и покупки статусов.\n"
                  "💠 `статусы` — посмотреть информацию и привилегии статусов.\n"
                  "👑 `мой статус` — проверить свой текущий статус.\n\n"
                  "ℹ️ Покупки необязательны: основные игровые разделы доступны всем игрокам."
    }
    text = pages.get(section, "📚 Выбери нужный раздел в меню помощи.")
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                          reply_markup=help_keyboard(), parse_mode="Markdown")
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
    complete_quest(uid, "bonus")
    bot.reply_to(message, f"🎁 **ЕЖЕДНЕВНЫЙ БОНУС**\nВы получили: **{reward} 🪙**\nПриходите завтра!", parse_mode="Markdown")

# ==================== ДОНАТ И СТАТУСЫ ====================

@bot.message_handler(commands=['donate'])
@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == 'донат')
def donate_menu(message):
    text = (
        "💎 **ЦЕНТР ПОПОЛНЕНИЯ MON1 GAME**\n\n"
        "Выбери, что тебя интересует:\n\n"
        "🪙 Пополнение игрового баланса за Telegram Stars.\n"
        "👑 Покупка VIP, Premium или Ultra."
    )
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("🪙 Пополнить игровую валюту", callback_data="donate_currency"))
    kb.add(InlineKeyboardButton("💎 Купить статус", callback_data="donate_status_shop"))
    bot.reply_to(message, text, reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data in ("donate_currency", "donate_status_shop"))
def donate_sections_callback(call):
    if call.data == "donate_currency":
        text = (
            "🪙 **ПОПОЛНЕНИЕ ИГРОВОГО БАЛАНСА**\n\n"
            "⭐ 1 звезда = 1 000 🪙\n\n"
            "Выбери пакет:"
        )
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton("25 ⭐ = 25 000 🪙", callback_data="donate_pack_25"))
        kb.add(InlineKeyboardButton("50 ⭐ = 50 000 🪙", callback_data="donate_pack_50"))
        kb.add(InlineKeyboardButton("100 ⭐ = 100 000 🪙", callback_data="donate_pack_100"))
        kb.add(InlineKeyboardButton("✏️ Ввести свою сумму", callback_data="donate_custom"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                              reply_markup=kb, parse_mode="Markdown")
    else:
        text = (
            "💎 **ВЫБЕРИ СТАТУС**\n\n"
            "👑 VIP — 100 ⭐\n"
            "💠 Premium — 200 ⭐\n"
            "⚡ Ultra — 300 ⭐\n\n"
            "Нажми на нужный статус для покупки."
        )
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton("👑 Купить VIP · 100 ⭐", callback_data="buy_status_VIP"))
        kb.add(InlineKeyboardButton("💠 Купить Premium · 200 ⭐", callback_data="buy_status_Premium"))
        kb.add(InlineKeyboardButton("⚡ Купить Ultra · 300 ⭐", callback_data="buy_status_Ultra"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                              reply_markup=kb, parse_mode="Markdown")
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("donate_"))
def donate_process(call):
    if call.data == "donate_custom":
        msg = bot.send_message(call.message.chat.id, "✏️ Введите количество звёзд (от 1 до 10000):")
        bot.register_next_step_handler(msg, process_custom_stars)
        return
    try:
        stars = int(call.data.split("_")[2])
    except (ValueError, IndexError):
        return bot.answer_callback_query(call.id, "Неизвестный вариант пополнения.", show_alert=True)
    coins = stars * 1000
    prices = [LabeledPrice(label=f"{coins} монет", amount=stars)]
    try:
        bot.send_invoice(
            chat_id=call.message.chat.id,
            title=f"Покупка {coins} монет",
            description=f"Вы получите {coins} монет на баланс.",
            invoice_payload=f"pay_{stars}",
            provider_token="",
            currency="XTR",
            prices=prices
        )
        bot.answer_callback_query(call.id, "✅ Счёт выставлен!")
    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {e}", show_alert=True)

def process_custom_stars(message):
    try:
        stars = int(message.text)
        if stars < 1 or stars > 10000: return bot.reply_to(message, "❌ От 1 до 10000 звезд.")
        coins = stars * 1000
        prices = [LabeledPrice(label=f"{coins} монет", amount=stars)]
        bot.send_invoice(chat_id=message.chat.id, title=f"Покупка {coins} монет", description=f"Вы получите {coins} монет на баланс.", invoice_payload=f"pay_{stars}", provider_token="", currency="XTR", prices=prices)
    except (ValueError, TypeError): bot.reply_to(message, "❌ Введите число.")

@bot.pre_checkout_query_handler(func=lambda query: True)
def process_pre_checkout_query(pre_checkout_query):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def got_payment(message):
    payload = message.successful_payment.invoice_payload
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)

    if payload.startswith("status_"):
        status = payload.split("_", 1)[1]
        if status not in ("VIP", "Premium", "Ultra"):
            return bot.send_message(message.chat.id, "❌ Неизвестный статус.")
        data["players"][uid]["donate_status"] = status
        save_data()
        return bot.send_message(
            message.chat.id,
            f"🎉 **ПОКУПКА УСПЕШНА!**\n"
            f"💎 Получен статус: **{status}**\n"
            f"Открой команду `статусы`, чтобы посмотреть привилегии.",
            parse_mode="Markdown"
        )

    if payload.startswith("pay_"):
        try:
            stars = int(payload.split("_", 1)[1])
        except (ValueError, IndexError):
            return bot.send_message(message.chat.id, "❌ Не удалось обработать платёж.")
        coins = stars * 1000
        add_balance(uid, coins)
        bot.send_message(
            message.chat.id,
            f"🎉 **ОПЛАТА УСПЕШНА!**\n"
            f"💰 На баланс зачислено: **{coins:,} 🪙**",
            parse_mode="Markdown"
        )

@bot.message_handler(commands=['donate_status'])
@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() in ('донат статус', 'статусы', 'статус'))
def donate_status_menu(message):
    text = (
        "💎 **СТАТУСЫ MON1 GAME**\n\n"
        "👑 **VIP — 100 ⭐**\n"
        "🏦 Банковский депозит: **12% в день**\n"
        "🎮 Бонус к игровому выигрышу: **+3%**\n\n"
        "💠 **PREMIUM — 200 ⭐**\n"
        "🏦 Банковский депозит: **15% в день**\n"
        "🎮 Бонус к игровому выигрышу: **+6%**\n\n"
        "⚡ **ULTRA — 300 ⭐**\n"
        "🏦 Банковский депозит: **20% в день**\n"
        "🎮 Бонус к игровому выигрышу: **+10%**\n"
        "🆔 Команда `узнать ид` — посмотреть ID игрока.\n"
        "👤 Команда `профиль ID` — посмотреть профиль по ID.\n\n"
        "ℹ️ Проценты 12%, 15% и 20% начисляются ежедневно на сумму, помещённую в банковский депозит.\n"
        "ℹ️ Бонусы +3%, +6% и +10% применяются отдельно к игровому выигрышу."
    )
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_status_"))
def buy_status(call):
    status = call.data.split("_", 2)[2]
    prices_by_status = {"VIP": 100, "Premium": 200, "Ultra": 300}
    stars = prices_by_status.get(status)
    if not stars:
        return bot.answer_callback_query(call.id, "Неизвестный статус.", show_alert=True)
    prices = [LabeledPrice(label=f"Статус {status}", amount=stars)]
    try:
        bot.send_invoice(
            chat_id=call.message.chat.id,
            title=f"Статус {status}",
            description=f"Покупка статуса {status} в MON1 GAME RPG.",
            invoice_payload=f"status_{status}",
            provider_token="",
            currency="XTR",
            prices=prices
        )
        bot.answer_callback_query(call.id, "⭐ Счёт на оплату выставлен!")
    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка выставления счёта: {e}", show_alert=True)

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "мой статус")
def my_status(message):
    uid = str(message.from_user.id)
    status = data["players"].get(uid, {}).get("donate_status", "Нет")
    bot.reply_to(message, f"💎 **ВАШ СТАТУС**\nТекущий статус: **{status}**", parse_mode="Markdown")

# ==================== БАЗОВЫЕ КОМАНДЫ ====================

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == 'б')
def balance_command(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]: register_user(message.from_user)
    bot.reply_to(message, f"💰 **БАЛАНС**\nВаш баланс: **{get_balance(uid)} 🪙**", parse_mode="Markdown")

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
    bot.reply_to(message, f"🆔 **ID ИГРОКА**\n`{sid}`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("сменить ник"))
def change_nick(message):
    uid = str(message.from_user.id)
    try:
        new_nick = message.text[12:].strip()
        if len(new_nick) < 3 or len(new_nick) > 15: return bot.reply_to(message, "❌ Ник от 3 до 15 символов.")
        data["players"][uid]["username"] = new_nick
        save_data()
        bot.reply_to(message, f"✅ **НИК ИЗМЕНЕН**\nНовый ник: **{new_nick}**", parse_mode="Markdown")
    except: bot.reply_to(message, "❌ `сменить ник НОВЫЙ_НИК`")

@bot.message_handler(func=lambda m: m.text and (m.text.lower().strip() == "профиль" or m.text.lower().strip().startswith("профиль ")))
def profile_command(message):
    uid = str(message.from_user.id)
    target_uid = uid
    parts = message.text.strip().split(maxsplit=1)

    if len(parts) > 1:
        caller_status = data["players"].get(uid, {}).get("donate_status", "Нет")
        if uid not in [str(a) for a in ADMIN_IDS] and caller_status != "Ultra":
            return bot.reply_to(message, "❌ Смотреть чужие профили могут только администраторы и Ultra.", parse_mode="Markdown")
        target_uid = get_user_by_short_id(parts[1].strip())
        if not target_uid:
            return bot.reply_to(message, "❌ Игрок с таким ID не найден.")
    elif message.reply_to_message:
        caller_status = data["players"].get(uid, {}).get("donate_status", "Нет")
        if uid not in [str(a) for a in ADMIN_IDS] and caller_status != "Ultra":
            return bot.reply_to(message, "❌ Смотреть чужие профили могут только администраторы и Ultra.", parse_mode="Markdown")
        target_uid = str(message.reply_to_message.from_user.id)

    if target_uid not in data["players"]:
        return bot.reply_to(message, "❌ Игрок не найден.")
    p = data["players"][target_uid]
    clan_name = "Нет"
    if p.get("clan_id"):
        clan = data["clans"].get(str(p["clan_id"]))
        if clan:
            clan_name = clan.get("name", "Нет")
    text = (
        "👤 **ПРОФИЛЬ ИГРОКА**\n"
        ""
        f"🆔 ID: `{p.get('short_id', '?')}`\n"
        f"👤 Ник: {p.get('username', '?')}\n"
        f"💎 Статус: {p.get('donate_status', 'Нет')}\n"
        ""
        f"💰 Баланс: {money_fmt(p.get('balance', 0))} 🪙\n"
        f"🏦 Банк: {money_fmt(p.get('bank', 0))} 🪙\n"
        f"💎 Депозит: {money_fmt(p.get('deposit', 0))} 🪙\n"
        ""
        f"🛡 Клан: {clan_name}\n"
        f"🏢 Бизнес: {p.get('biz_territory', 0)} м²"
    )
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() in ["топ", "топ игроков", "/top"])
def top_cmd(message):
    try:
        players = list(data.get("players", {}).items())
        if not players:
            return bot.reply_to(message, "🏆 ТОП-10 ИГРОКОВ\nПока никого нет.")
        sp = sorted(players, key=lambda x: int(x[1].get("balance", 0) or 0), reverse=True)[:10]
        lines = []
        for i, (u, p) in enumerate(sp, 1):
            name = str(p.get("username") or "Player")
            for ch in ["*", "_", "`", "[", "]", "(", ")"]:
                name = name.replace(ch, "")
            if not name.strip():
                name = "Player"
            bal = int(p.get("balance", 0) or 0)
            lines.append(f"{i}. {name} — {bal} 🪙")
        text = "🏆 ТОП-10 ИГРОКОВ\n" + "\n".join(lines)
        bot.reply_to(message, text)
    except Exception as e:
        bot.reply_to(message, f"Ошибка топа: {e}")

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "чаты")
def chats_cmd(message):
    bot.reply_to(message, "💬 **НАШИ ЧАТЫ**\n📢 Канал: https://t.me/mon1bots\n💬 Чат: https://t.me/mon1not", parse_mode="Markdown")

# ==================== ДУЭЛИ (Камень-Ножницы-Бумага) ====================

RPS_MAP = {
    "камень": "🪨", "ножницы": "✂️", "бумага": "📄",
    "к": "🪨", "н": "✂️",
    "rock": "🪨", "scissors": "✂️", "paper": "📄"
}
RPS_CHOICES = {"камень": "камень", "ножницы": "ножницы", "бумага": "бумага",
               "к": "камень", "н": "ножницы",
               "rock": "камень", "scissors": "ножницы", "paper": "бумага"}

def rps_winner(c1, c2):
    if c1 == c2: return 0
    wins = {"камень": "ножницы", "ножницы": "бумага", "бумага": "камень"}
    if wins[c1] == c2: return 1
    return 2

def find_pending_duel_for(uid):
    uid = str(uid)
    for duel_id, duel in data["duels"].items():
        if duel["status"] == "pending" and duel["opponent"] == uid:
            return duel_id, duel
    return None, None

def find_active_duel_for(uid):
    uid = str(uid)
    for duel_id, duel in data["duels"].items():
        if duel["status"] == "choosing" and uid in (duel["challenger"], duel["opponent"]):
            return duel_id, duel
    return None, None

def resolve_rps_duel(duel_id, duel):
    c1 = duel.get("choice1")
    c2 = duel.get("choice2")
    if not c1 or not c2: return

    amount = duel["amount"]
    pot = amount * 2
    ch = duel["challenger"]
    op = duel["opponent"]

    result = rps_winner(c1, c2)
    emoji1 = RPS_MAP.get(c1, c1)
    emoji2 = RPS_MAP.get(c2, c2)

    if result == 0:
        add_balance(ch, amount); add_balance(op, amount)
        duel["status"] = "draw"; save_data()
        text = (f"⚔️ **ДУЭЛЬ — НИЧЬЯ**\n"
                f"👤 {get_nick(ch)}: {emoji1} **{c1}**\n"
                f"👤 {get_nick(op)}: {emoji2} **{c2}**\n"
                f""
                f"🤝 Ставки возвращены ({amount} 🪙 каждому)")
    else:
        if result == 1: winner, loser = ch, op; w_choice, l_choice = c1, c2; w_emoji, l_emoji = emoji1, emoji2
        else: winner, loser = op, ch; w_choice, l_choice = c2, c1; w_emoji, l_emoji = emoji2, emoji1
        add_balance(winner, pot)
        duel["status"] = "finished"; duel["winner"] = winner; save_data()
        pot_str = f"{pot:,}".replace(",", " ")
        text = (f"⚔️ **РЕЗУЛЬТАТ ДУЭЛИ**\n"
                f"🏆 **{get_nick(winner)}**: {w_emoji} **{w_choice}**\n"
                f"💀 **{get_nick(loser)}**: {l_emoji} **{l_choice}**\n"
                f""
                f"💰 Банк: **{pot_str} 🪙**")
    try:
        bot.send_message(int(ch), text, parse_mode="Markdown")
        bot.send_message(int(op), text, parse_mode="Markdown")
    except: pass

def send_choice_buttons(uid, duel_id):
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton("🪨 Камень", callback_data=f"rps_{duel_id}_камень"),
        InlineKeyboardButton("✂️ Ножницы", callback_data=f"rps_{duel_id}_ножницы"),
        InlineKeyboardButton("📄 Бумага", callback_data=f"rps_{duel_id}_бумага")
    )
    try:
        bot.send_message(int(uid), "🎮 **Выбери ход:**\nНажми кнопку или напиши: `камень` / `ножницы` / `бумага`", reply_markup=kb, parse_mode="Markdown")
    except: pass

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("дуэль "))
def duel_challenge(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]: register_user(message.from_user)

    parts = message.text.split()
    target_uid = None; amount = None

    if len(parts) == 2:
        try: amount = int(parts[1].replace(" ", "").replace(",", ""))
        except: return bot.reply_to(message, "❌ Формат: `дуэль сумма` (в ответ) или `дуэль ID/@ник сумма`", parse_mode="Markdown")
        if message.reply_to_message: target_uid = str(message.reply_to_message.from_user.id)
        else: return bot.reply_to(message, "❌ Укажи игрока: `дуэль ID сумма` или ответь на его сообщение командой `дуэль сумма`", parse_mode="Markdown")
    elif len(parts) >= 3:
        target_raw = parts[1]
        try: amount = int(parts[2].replace(" ", "").replace(",", ""))
        except: return bot.reply_to(message, "❌ Сумма должна быть числом.")
        if target_raw.startswith("@"): target_uid = get_user_by_username(target_raw)
        else:
            try: target_uid = get_user_by_short_id(int(target_raw))
            except: pass
    else:
        return bot.reply_to(message, "❌ Формат:\n`дуэль ID сумма`\n`дуэль @ник сумма`\n`дуэль сумма` (в ответ на сообщение)\n\nПример: `дуэль 15 5000`", parse_mode="Markdown")

    if amount is None or amount < 100: return bot.reply_to(message, "❌ Минимальная ставка — 100 🪙")
    if amount > 10_000_000: return bot.reply_to(message, "❌ Максимальная ставка — 10 000 000 🪙")
    if not target_uid: return bot.reply_to(message, "❌ Игрок не найден.")

    target_uid = str(target_uid)
    if target_uid == uid: return bot.reply_to(message, "❌ Нельзя вызвать самого себя.")
    if get_balance(uid) < amount: return bot.reply_to(message, "❌ У тебя недостаточно средств.")
    if get_balance(target_uid) < amount: return bot.reply_to(message, "❌ У соперника недостаточно средств.")

    for d in data["duels"].values():
        if d["status"] in ("pending", "choosing"):
            if uid in (d["challenger"], d["opponent"]) or target_uid in (d["challenger"], d["opponent"]):
                return bot.reply_to(message, "❌ У одного из вас уже есть активный вызов.")

    duel_id = str(int(time.time() * 1000))
    data["duels"][duel_id] = {"challenger": uid, "opponent": target_uid, "amount": amount, "status": "pending", "choice1": None, "choice2": None, "created": int(time.time())}
    save_data()

    amount_str = f"{amount:,}".replace(",", " ")
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("✅ Принять", callback_data=f"duel_accept_{duel_id}"), InlineKeyboardButton("❌ Отклонить", callback_data=f"duel_reject_{duel_id}"))

    try:
        bot.send_message(int(target_uid),
            f"⚔️ **ВЫЗОВ НА ДУЭЛЬ (КНБ)**\n"
            f"👤 **{get_nick(uid)}** вызывает тебя!\n"
            f"💰 Ставка: **{amount_str} 🪙**\n"
            f"🎮 Камень · Ножницы · Бумага\n"
            f"Напиши `принять` или нажми кнопку.\nУ тебя **2 минуты**.",
            reply_markup=kb, parse_mode="Markdown")
    except Exception:
        del data["duels"][duel_id]; save_data()
        return bot.reply_to(message, "❌ Не удалось отправить вызов.\nСоперник, скорее всего, ещё не запускал бота.")

    bot.reply_to(message, f"⚔️ Вызов (КНБ) отправлен **{get_nick(target_uid)}**\nСтавка: **{amount_str} 🪙**\nОжидай ответа...", parse_mode="Markdown")

    def auto_cancel(duel_id=duel_id, uid=uid, target_uid=target_uid):
        time.sleep(120)
        if duel_id in data["duels"] and data["duels"][duel_id]["status"] == "pending":
            data["duels"][duel_id]["status"] = "expired"; save_data()
            try:
                bot.send_message(int(uid), "⌛️ Твой вызов на дуэль истёк.")
                bot.send_message(int(target_uid), "⌛️ Вызов на дуэль истёк.")
            except: pass
    threading.Thread(target=auto_cancel, daemon=True).start()

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() in ["принять", "accept", "да"])
def duel_accept_text(message):
    uid = str(message.from_user.id)
    duel_id, duel = find_pending_duel_for(uid)
    if not duel: return bot.reply_to(message, "❌ У тебя нет входящих вызовов на дуэль.")

    challenger = duel["challenger"]; opponent = duel["opponent"]; amount = duel["amount"]
    if get_balance(challenger) < amount or get_balance(opponent) < amount:
        duel["status"] = "cancelled"; save_data()
        return bot.reply_to(message, "❌ Недостаточно средств у одного из игроков. Дуэль отменена.")

    add_balance(challenger, -amount); add_balance(opponent, -amount)
    duel["status"] = "choosing"; duel["choice1"] = None; duel["choice2"] = None; save_data()

    bot.reply_to(message, "⚔️ Дуэль принята! Выбирайте ход.")
    try: bot.send_message(int(challenger), f"⚔️ **{get_nick(opponent)}** принял вызов! Выбирайте ход.")
    except: pass
    send_choice_buttons(challenger, duel_id); send_choice_buttons(opponent, duel_id)

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() in ["отклонить", "no"])
def duel_reject_text(message):
    uid = str(message.from_user.id)
    duel_id, duel = find_pending_duel_for(uid)
    if not duel: return
    duel["status"] = "rejected"; save_data()
    bot.reply_to(message, "❌ Ты отклонил вызов.")
    try: bot.send_message(int(duel["challenger"]), f"❌ **{get_nick(uid)}** отклонил твой вызов.")
    except: pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("duel_"))
def duel_callback(call):
    try: parts = call.data.split("_"); action = parts[1]; duel_id = parts[2]
    except: return bot.answer_callback_query(call.id, "Ошибка.", show_alert=True)

    duel = data["duels"].get(duel_id)
    if not duel or duel["status"] != "pending":
        return bot.answer_callback_query(call.id, "❌ Вызов уже недействителен.", show_alert=True)

    uid = str(call.from_user.id)
    if uid != duel["opponent"]: return bot.answer_callback_query(call.id, "❌ Это не твой вызов.", show_alert=True)

    challenger = duel["challenger"]; opponent = duel["opponent"]; amount = duel["amount"]

    if action == "reject":
        duel["status"] = "rejected"; save_data()
        bot.edit_message_text("❌ Ты отклонил вызов.", call.message.chat.id, call.message.message_id)
        try: bot.send_message(int(challenger), f"❌ **{get_nick(opponent)}** отклонил твой вызов.")
        except: pass
        return bot.answer_callback_query(call.id)

    if get_balance(challenger) < amount or get_balance(opponent) < amount:
        duel["status"] = "cancelled"; save_data()
        bot.edit_message_text("❌ Недостаточно средств.", call.message.chat.id, call.message.message_id)
        return bot.answer_callback_query(call.id, "Недостаточно средств.", show_alert=True)

    add_balance(challenger, -amount); add_balance(opponent, -amount)
    duel["status"] = "choosing"; duel["choice1"] = None; duel["choice2"] = None; save_data()

    bot.edit_message_text("⚔️ Дуэль принята! Выбирайте ход.", call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id, "Дуэль началась!")
    try: bot.send_message(int(challenger), f"⚔️ **{get_nick(opponent)}** принял вызов! Выбирайте ход.")
    except: pass
    send_choice_buttons(challenger, duel_id); send_choice_buttons(opponent, duel_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("rps_"))
def rps_choice_callback(call):
    try: _, duel_id, choice = call.data.split("_", 2)
    except: return bot.answer_callback_query(call.id, "Ошибка.", show_alert=True)

    duel = data["duels"].get(duel_id)
    if not duel or duel["status"] != "choosing": return bot.answer_callback_query(call.id, "❌ Дуэль уже закончена.", show_alert=True)

    uid = str(call.from_user.id)
    if uid not in (duel["challenger"], duel["opponent"]): return bot.answer_callback_query(call.id, "❌ Это не твоя дуэль.", show_alert=True)

    choice = RPS_CHOICES.get(choice.lower())
    if not choice: return bot.answer_callback_query(call.id, "Неверный выбор.")

    if uid == duel["challenger"]:
        if duel.get("choice1"): return bot.answer_callback_query(call.id, "Ты уже выбрал!", show_alert=True)
        duel["choice1"] = choice
    else:
        if duel.get("choice2"): return bot.answer_callback_query(call.id, "Ты уже выбрал!", show_alert=True)
        duel["choice2"] = choice

    save_data()
    bot.answer_callback_query(call.id, f"Выбрано: {choice}")
    bot.edit_message_text(f"✅ Ты выбрал: **{RPS_MAP.get(choice, choice)} {choice}**\nЖдём соперника...", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    if duel.get("choice1") and duel.get("choice2"): resolve_rps_duel(duel_id, duel)

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() in ["камень", "ножницы", "бумага", "к", "н", "rock", "scissors", "paper"])
def rps_choice_text(message):
    uid = str(message.from_user.id)
    duel_id, duel = find_active_duel_for(uid)
    if not duel: return
    choice = RPS_CHOICES.get(message.text.lower().strip())
    if not choice: return
    if uid == duel["challenger"]:
        if duel.get("choice1"): return bot.reply_to(message, "❌ Ты уже выбрал ход.")
        duel["choice1"] = choice
    else:
        if duel.get("choice2"): return bot.reply_to(message, "❌ Ты уже выбрал ход.")
        duel["choice2"] = choice
    save_data()
    bot.reply_to(message, f"✅ Ты выбрал: **{RPS_MAP.get(choice, choice)} {choice}**\nЖдём соперника...", parse_mode="Markdown")
    if duel.get("choice1") and duel.get("choice2"): resolve_rps_duel(duel_id, duel)

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
    bot.reply_to(message, "⚙️ **АДМИН-ПАНЕЛЬ**\nВыберите действие:", reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_"))
def admin_callbacks(call):
    if call.from_user.id not in ADMIN_IDS: return bot.answer_callback_query(call.id, "❌ Нет прав.")
    act = call.data.split("_")[1]
    if act == "stats":
        total_players = len(data["players"]); total_money = sum(p.get("balance", 0) for p in data["players"].values()); total_clans = len(data["clans"])
        text = f"📊 **СТАТИСТИКА**\n👥 Игроков: {total_players}\n💰 Общий баланс: {total_money} 🪙\n🛡 Кланов: {total_clans}"
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("⬅️ Назад", callback_data="adm_back")), parse_mode="Markdown")
    elif act == "give":
        msg = bot.send_message(call.message.chat.id, "Введите `ID СУММА` (например: `3 5000`):"); bot.register_next_step_handler(msg, admin_give_step); bot.answer_callback_query(call.id)
    elif act == "setstatus":
        msg = bot.send_message(call.message.chat.id, "Введите `ID СТАТУС` (например: `3 Ultra`).\nДоступные статусы: `VIP`, `Premium`, `Ultra`, `Нет`:"); bot.register_next_step_handler(msg, admin_setstatus_step); bot.answer_callback_query(call.id)
    elif act == "reset":
        msg = bot.send_message(call.message.chat.id, "Введите `ID` игрока для обнуления баланса (например: `3`):"); bot.register_next_step_handler(msg, admin_reset_step); bot.answer_callback_query(call.id)
    elif act == "promo":
        msg = bot.send_message(call.message.chat.id, "Введите `КОД СУММА` (например: `NEWYEAR 1000`):"); bot.register_next_step_handler(msg, admin_promo_step); bot.answer_callback_query(call.id)
    elif act == "delpromo":
        msg = bot.send_message(call.message.chat.id, "Введите `КОД` промокода для удаления:"); bot.register_next_step_handler(msg, admin_delpromo_step); bot.answer_callback_query(call.id)
    elif act == "broadcast":
        msg = bot.send_message(call.message.chat.id, "Введите текст для рассылки всем игрокам:"); bot.register_next_step_handler(msg, admin_broadcast_step); bot.answer_callback_query(call.id)
    elif act == "back": admin_panel(call.message)

def admin_give_step(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        sid, amount = message.text.split(); amount = int(amount)
        target_uid = get_user_by_short_id(sid)
        if not target_uid: return bot.reply_to(message, "❌ Игрок не найден.")
        add_balance(target_uid, amount); bot.reply_to(message, f"✅ Выдано {amount} 🪙 игроку с ID {sid}.")
    except: bot.reply_to(message, "❌ Ошибка формата.")

def admin_setstatus_step(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        sid, status = message.text.split(maxsplit=1); status = status.strip()
        status_map = {"vip": "VIP", "premium": "Premium", "ultra": "Ultra", "нет": "Нет"}
        status = status_map.get(status.lower(), status)
        if status not in ["VIP", "Premium", "Ultra", "Нет"]: return bot.reply_to(message, "❌ Неверный статус. Доступно: VIP, Premium, Ultra, Нет.")
        target_uid = get_user_by_short_id(sid)
        if not target_uid: return bot.reply_to(message, "❌ Игрок не найден.")
        data["players"][target_uid]["donate_status"] = status; save_data()
        bot.reply_to(message, f"✅ Игроку с ID {sid} выдан статус **{status}**.", parse_mode="Markdown")
    except: bot.reply_to(message, "❌ Ошибка формата. Введите `ID Статус`")

def admin_reset_step(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        sid = message.text.strip(); target_uid = get_user_by_short_id(sid)
        if not target_uid: return bot.reply_to(message, "❌ Игрок не найден.")
        data["players"][target_uid]["balance"] = 0; data["players"][target_uid]["bank"] = 0
        data["players"][target_uid]["deposit"] = 0; data["players"][target_uid]["deposit_start"] = 0; save_data()
        bot.reply_to(message, f"✅ Баланс и банк игрока с ID {sid} обнулены.")
    except: bot.reply_to(message, "❌ Ошибка.")

def admin_promo_step(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        code, amount = message.text.upper().split(); amount = int(amount)
        data["promos"][code] = amount; save_data(); bot.reply_to(message, f"✅ Промокод {code} на {amount} 🪙 создан.")
    except: bot.reply_to(message, "❌ Ошибка формата.")

def admin_delpromo_step(message):
    if message.from_user.id not in ADMIN_IDS: return
    code = message.text.upper().strip()
    if code in data["promos"]: del data["promos"][code]; save_data(); bot.reply_to(message, f"✅ Промокод {code} удален.")
    else: bot.reply_to(message, "❌ Не найден.")

def admin_broadcast_step(message):
    if message.from_user.id not in ADMIN_IDS: return
    text = message.text; success = 0
    for uid in list(data["players"].keys()):
        try: bot.send_message(uid, text); success += 1
        except: pass
    bot.reply_to(message, f"✅ Рассылка отправлена {success} игрокам.")

# ==================== СТАРЫЕ АДМИН-КОМАНДЫ ====================

@bot.message_handler(commands=['wipe'])
def wipe_command(message):
    if message.from_user.id not in ADMIN_IDS: return
    global data
    data = {"players": {}, "promos": {}, "activations": [], "history": [], "clans": {}, "next_id": 1, "active_games": {}, "roulette_bets": {}, "duels": {}}
    save_data(); bot.reply_to(message, "💥 **База данных очищена!**", parse_mode="Markdown")

@bot.message_handler(commands=['give'])
def give_command(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        parts = message.text.split(); target_sid = parts[1]; amount = int(parts[2])
        target_uid = get_user_by_short_id(target_sid)
        if not target_uid: return bot.reply_to(message, f"❌ Игрок {target_sid} не найден.")
        add_balance(target_uid, amount); bot.reply_to(message, f"✅ Выдано {amount} 🪙 игроку {get_nick(target_uid)}.", parse_mode="Markdown")
    except: bot.reply_to(message, "❌ `/give ID СУММА`", parse_mode="Markdown")

@bot.message_handler(commands=['reset'])
def reset_user_command(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        target_sid = message.text.split()[1]; target_uid = get_user_by_short_id(target_sid)
        if not target_uid: return bot.reply_to(message, f"❌ Игрок {target_sid} не найден.")
        data["players"][target_uid]["balance"] = 0; data["players"][target_uid]["bank"] = 0
        data["players"][target_uid]["deposit"] = 0; data["players"][target_uid]["deposit_start"] = 0; save_data()
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
        if code in data["promos"]: del data["promos"][code]; save_data(); bot.reply_to(message, f"✅ Промокод **{code}** удален.", parse_mode="Markdown")
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
        amount = data["promos"][code]; add_balance(uid, amount)
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
    p["clan_id"] = None; p["role"] = "none"; save_data(); bot.reply_to(message, "✅ Вы вышли из клана.")

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
    text = "🏆 **ТОП КЛАНОВ**\n" + "".join([f"{i}. {c.get('name')} — {c.get('treasury', 0)} 🪙\n" for i, (cid, c) in enumerate(clans, 1)])
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
            clan["treasury"] -= amount; add_balance(uid, amount); save_data(); bot.reply_to(message, f"✅ Вы сняли {amount} 🪙 из казны.")
        else:
            if get_balance(uid) < amount: return bot.reply_to(message, "❌ Недостаточно средств.")
            add_balance(uid, -amount); clan["treasury"] = clan.get("treasury", 0) + amount; save_data(); bot.reply_to(message, f"✅ Вы положили {amount} 🪙 в казну.")
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
        save_data(); bot.reply_to(message, f"✅ Игрок `{target_sid}` повышен до **{new_role}**.", parse_mode="Markdown")
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
            win = int(win * get_win_multiplier(uid)); add_balance(uid, win)
            msg = f"🎰 **СЛОТ**\n[ {s[0]} | {s[1]} | {s[2]} ]\n🎉 **ВЫИГРЫШ!** +{win} 🪙\nБаланс: {get_balance(uid)}"
        else:
            msg = f"🎰 **СЛОТ**\n[ {s[0]} | {s[1]} | {s[2]} ]\n😢 Проигрыш.\nБаланс: {get_balance(uid)}"
        bot.reply_to(message, msg, parse_mode="Markdown")
        complete_quest(uid, "slot")
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
        complete_quest(uid, "mines")
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
    rw = int(rw * get_win_multiplier(uid)); add_balance(uid, rw)
    data["active_games"].pop(gid, None); save_data()
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
        complete_quest(uid, "crash")
        threading.Thread(target=crash_loop, args=(gid, uid, msg.chat.id, msg.message_id)).start()
    except: bot.reply_to(message, "❌ `краш 1000`")

def crash_loop(gid, uid, cid, mid):
    time.sleep(1)
    while True:
        g = data["active_games"].get(gid)
        if not g or not g.get("active"): break
        g["current"] = round(g["current"] + 0.10, 2); save_data()
        if g["current"] >= g["crash_point"] or random.random() < 0.06:
            g["active"] = False; save_data()
            try: bot.edit_message_text(f"💥 **КРАШ на x{g['current']:.2f}!**\nПотеряно {g['bet']} 🪙.", cid, mid, reply_markup=None, parse_mode="Markdown")
            except: pass
            data["active_games"].pop(gid, None); save_data(); break
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("💰 ЗАБРАТЬ", callback_data=f"ccash_{gid}"))
        try: bot.edit_message_text(f"🚀 **CRASH**\nСтавка: {g['bet']}\nКоэф: x{g['current']:.2f}", cid, mid, reply_markup=kb, parse_mode="Markdown")
        except: pass
        time.sleep(1)

@bot.callback_query_handler(func=lambda call: call.data.startswith("ccash_"))
def crash_out(call):
    gid = call.data.split("_")[1]; uid = str(call.from_user.id); g = data["active_games"].get(gid)
    if not g or g["user"] != uid or not g.get("active"): return
    g["active"] = False
    rw = math.floor(g["bet"] * g["current"]); rw = int(rw * get_win_multiplier(uid))
    add_balance(uid, rw); data["active_games"].pop(gid, None); save_data()
    bot.edit_message_text(f"🏆 **Забрано на x{g['current']:.2f}!** +{rw} 🪙", call.message.chat.id, call.message.message_id, reply_markup=None, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("джокер"))
def start_joker(message):
    uid = str(message.from_user.id)
    try:
        bet = int(message.text.split()[1])
        if bet <= 0 or get_balance(uid) < bet: return bot.reply_to(message, "❌ Недостаточно средств.")
        add_balance(uid, -bet); gid = str(random.randint(10000, 99999))
        data["active_games"][gid] = {"type": "joker", "user": uid, "bet": bet, "step": 0, "mult": 1.0, "active": True}; save_data()
        show_joker_menu(message.chat.id, gid, uid, None)
        complete_quest(uid, "joker")
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
    if not g or g["user"] != uid or not g.get("active"): return bot.answer_callback_query(call.id, "❌ Ошибка.")
    if g["step"] >= 12: return bot.answer_callback_query(call.id, "❌ Максимум!")
    lose_idx = random.randint(0, 2)
    if int(choice) == lose_idx:
        g["active"] = False
        bot.edit_message_text(f"🃏 **ПРОИГРЫШ!**\nВы попали в проигрышную ячейку.\nПотеряно: {g['bet']} 🪙", call.message.chat.id, call.message.message_id, reply_markup=None, parse_mode="Markdown")
        data["active_games"].pop(gid, None); save_data(); return
    g["step"] += 1
    mult_table = [1.2, 1.4, 1.6, 1.9, 2.2, 2.5, 2.9, 3.3, 3.8, 4.2, 4.6, 5.0]
    g["mult"] = mult_table[g["step"] - 1]; save_data()
    if g["step"] >= 12:
        rw = math.floor(g["bet"] * g["mult"]); add_balance(uid, rw); g["active"] = False
        bot.edit_message_text(f"🏆 **ДЖОКЕР ПРОЙДЕН!**\nМаксимальный множитель x{g['mult']:.2f}!\nВыигрыш: {rw} 🪙", call.message.chat.id, call.message.message_id, reply_markup=None, parse_mode="Markdown")
        data["active_games"].pop(gid, None); save_data(); return
    bot.answer_callback_query(call.id, f"✅ Шаг {g['step']}! Множитель x{g['mult']:.2f}")
    show_joker_menu(call.message.chat.id, gid, uid, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("jcash_"))
def joker_cash(call):
    gid = call.data.split("_")[1]; uid = str(call.from_user.id); g = data["active_games"].get(gid)
    if not g or g["user"] != uid or not g.get("active"): return
    rw = math.floor(g["bet"] * g["mult"]); add_balance(uid, rw); g["active"] = False
    bot.edit_message_text(f"🏆 **Забрано!** +{rw} 🪙", call.message.chat.id, call.message.message_id, reply_markup=None, parse_mode="Markdown")
    data["active_games"].pop(gid, None); save_data()

@bot.message_handler(func=lambda m: m.text and len(m.text.split()) >= 2 and m.text.split()[0].isdigit())
def roulette_bet(message):
    uid = str(message.from_user.id); parts = message.text.split()
    try: bet = int(parts[0])
    except: return
    targets = parts[1:]; valid_targets = []
    for t in targets:
        t_clean = t.lower().strip()
        if t_clean in ["red", "к", "кр", "красное", "black", "ч", "черное", "green", "з", "зеленое", "even", "чет", "odd", "нечет"]: valid_targets.append(t_clean)
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

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "отмена")
def roulette_cancel(message):
    uid = str(message.from_user.id)
    chat_id = str(message.chat.id)
    bets = data.get("roulette_bets", {}).get(chat_id, [])
    user_bets = [b for b in bets if str(b.get("user")) == uid]
    if not user_bets:
        return bot.reply_to(message, "❌ У тебя нет подготовленных ставок на рулетку.")

    refund = sum(int(b["bet"]) * len(b["targets"]) for b in user_bets)
    data["roulette_bets"][chat_id] = [b for b in bets if str(b.get("user")) != uid]
    add_balance(uid, refund)
    save_data()
    bot.reply_to(message, f"↩️ Ставки отменены. Возвращено: **{refund:,} 🪙**", parse_mode="Markdown")


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
    bot.reply_to(message, f"🎰 Результат: {sym} **{win_num}**\n\n{res_text}\n\n💰 Общий выигрыш: {total_win} 🪙", parse_mode="Markdown")

# ==================== БИЗНЕС, БАНК, КВЕСТЫ ====================

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "мой бизнес")
def my_business(message):
    uid = str(message.from_user.id); p = data["players"].get(uid, {}); t = p.get("biz_territory", 0)
    if t == 0:
        kb = InlineKeyboardMarkup().add(InlineKeyboardButton("🏗 Открыть свой бизнес · 3 000 🪙", callback_data="biz_build"))
        return bot.reply_to(message, f"🏢 **ТВОЙ БИЗНЕС**\nУ тебя пока нет предприятия.\n\n🏗 Построй первый уровень территории за **{BIZ_TERRITORY_COST[0]:,} 🪙**, чтобы начать получать доход.", reply_markup=kb, parse_mode="Markdown")
    show_biz_menu(message.chat.id, uid, None)

def calc_biz_income(t, b):
    """Доход в час: на 1 уровне ~1000, растёт с прокачкой"""
    t = max(1, int(t or 1))
    b = max(1, int(b or 1))
    return int(1000 * t * (1 + (b - 1) * 0.6))

def show_biz_menu(chat_id, uid, msg_id):
    p = data["players"].get(uid, {}); t = p.get("biz_territory", 0); b = p.get("biz_building", 1); tax = p.get("biz_tax", 0)
    inc = calc_biz_income(t, b)
    earned = int((min(int(time.time()) - p.get("biz_last_collect", int(time.time())), 86400) / 3600) * inc)
    next_terr = BIZ_TERRITORY_COST.get(t, "MAX")
    next_build = BIZ_BUILDING_COST.get(b, "MAX")
    text = (f"🏢 **МОЙ БИЗНЕС**\n"
            f""
            f"📍 **Территория:** {t} ур.  ·  Следующее: **{next_terr} 🪙**\n"
            f"🏗 **Здание:** {b} ур.  ·  Следующее: **{next_build} 🪙**\n"
            f""
            f"📈 Доход: **{inc:,} 🪙 / час**\n"
            f"💰 Накоплено: **{earned:,} 🪙**\n"
            f"🧾 Налог при снятии: **25%**\n"
            f"🧾 Налог к оплате: **{tax:,} 🪙**\n"
            f""
            f"💡 Собирай доход и своевременно оплачивай налоги.")
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("💰 Собрать доход", callback_data="biz_collect"),
           InlineKeyboardButton("🧾 Оплатить налог", callback_data="biz_tax"))
    kb.add(InlineKeyboardButton("📍 Расширить территорию", callback_data="biz_terr"),
           InlineKeyboardButton("🏗 Улучшить здание", callback_data="biz_build_up"))
    if msg_id: bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb, parse_mode="Markdown")
    else: bot.send_message(chat_id, text, reply_markup=kb, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("biz_"))
def biz_callback(call):
    uid = str(call.from_user.id); act = call.data[4:]
    if act == "build":
        if get_balance(uid) < BIZ_TERRITORY_COST[0]: return bot.answer_callback_query(call.id, "❌ Мало денег!", show_alert=True)
        add_balance(uid, -BIZ_TERRITORY_COST[0])
        data["players"][uid]["biz_territory"] = 1
        data["players"][uid]["biz_building"] = 1
        data["players"][uid]["biz_tax"] = 0
        data["players"][uid]["biz_last_collect"] = int(time.time())  # с нуля, без прошлого дохода
        save_data()
        bot.answer_callback_query(call.id, "✅ Построено!")
        show_biz_menu(call.message.chat.id, uid, call.message.message_id)
    elif act == "collect":
        p = data["players"].get(uid, {}); t = p.get("biz_territory", 0); b = p.get("biz_building", 1); tax = p.get("biz_tax", 0)
        if tax > 0: return bot.answer_callback_query(call.id, f"❌ Оплатите налоги ({tax} 🪙)!", show_alert=True)
        inc = calc_biz_income(t, b)
        earned = int((min(int(time.time()) - p.get("biz_last_collect", int(time.time())), 86400) / 3600) * inc)
        if earned <= 0: return bot.answer_callback_query(call.id, "⏳ Пусто.", show_alert=True)
        tax_o = int(earned * 0.25)
        received = earned - tax_o
        add_balance(uid, received)
        data["players"][uid]["biz_last_collect"] = int(time.time())
        save_data()
        bot.answer_callback_query(call.id, f"💰 Получено: {received} 🪙. Налог 25%: {tax_o} 🪙", show_alert=True)
        show_biz_menu(call.message.chat.id, uid, call.message.message_id)
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

BANK_TERM_SECONDS = 3 * 86400
BANK_WITHDRAW_TAX = 0.025
BANK_DAILY_RATES = {"VIP": 0.12, "Premium": 0.15, "Ultra": 0.20}

def bank_daily_rate(player):
    status = player.get("donate_status", "Нет")
    if status in BANK_DAILY_RATES:
        return BANK_DAILY_RATES[status]
    return 0.10

def money_fmt(value):
    return f"{int(value):,}".replace(",", " ")

def bank_deposit_snapshot(player, now=None):
    now = int(now or time.time())
    principal = int(player.get("deposit", 0) or 0)
    started = int(player.get("deposit_start", 0) or 0)
    if principal <= 0 or started <= 0:
        return 0, 0, 0
    rate = float(player.get("deposit_rate", bank_daily_rate(player)))
    elapsed_days = max(0, (now - started) // 86400)
    interest = int(principal * rate * elapsed_days)
    total = principal + interest
    available_at = started + BANK_TERM_SECONDS
    return interest, total, available_at

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "банк")
def bank_info(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    p = data["players"][uid]
    now = int(time.time())
    bank_money = int(p.get("bank", 0) or 0)
    deposit = int(p.get("deposit", 0) or 0)
    rate = float(p.get("deposit_rate", bank_daily_rate(p)))
    interest, projected_total, available_at = bank_deposit_snapshot(p, now)

    if uid in [str(x) for x in ADMIN_IDS]:
        status_label = "Администратор"
    else:
        status_label = p.get("donate_status", "Нет статуса")
        if status_label == "Нет":
            status_label = "Обычный игрок"

    owner = p.get("username") or message.from_user.first_name or "Игрок"
    if deposit > 0:
        withdraw_date = time.strftime("%d.%m.%y в %H:%M:%S", time.localtime(available_at))
        deposit_line = (
            f"💎 **Под депозитом:** {money_fmt(projected_total)} 🪙\n"
            f"📈 Начислено процентов: +{money_fmt(interest)} 🪙\n"
            f"📅 **Можно снять:** {withdraw_date}"
        )
    else:
        deposit_line = "💎 **Под депозитом:** 0 🪙\n📅 Действующий депозит отсутствует."

    text = (
        "🏦 **ВАШ БАНКОВСКИЙ СЧЁТ**\n"
        ""
        f"👤 **Владелец:** {owner}\n"
        f"🪪 **Статус:** {status_label}\n"
        ""
        f"💰 **Деньги в банке:** {money_fmt(bank_money)} 🪙\n"
        f"📊 **Процент по депозиту:** {rate * 100:.0f}% в день\n"
        f"🧾 **Налог на снятие:** {BANK_WITHDRAW_TAX * 100:.1f}%\n"
        ""
        f"{deposit_line}\n"
        ""
        "📌 **Команды банка**\n"
        "➕ `банк положить СУММА` — внести деньги на счёт.\n"
        "➖ `банк снять СУММА` — снять деньги со счёта.\n"
        "💎 `депозит положить СУММА` — открыть депозит на 3 дня.\n"
        "💸 `депозит снять` — забрать депозит с процентами."
    )
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("банк положить"))
def bank_dep(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    try:
        parts = message.text.split()
        amount = int(parts[2])
        if amount <= 0 or get_balance(uid) < amount:
            return bot.reply_to(message, "❌ Недостаточно средств или неверная сумма.")
        data["players"][uid]["bank"] = int(data["players"][uid].get("bank", 0)) + amount
        add_balance(uid, -amount)
        save_data()
        bot.reply_to(message, f"🏦 На банковский счёт внесено **{money_fmt(amount)} 🪙**.", parse_mode="Markdown")
    except (ValueError, IndexError):
        bot.reply_to(message, "ℹ️ Использование: `банк положить 1000`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("банк снять"))
def bank_wd(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    try:
        parts = message.text.split()
        amount = int(parts[2])
        p = data["players"][uid]
        if amount <= 0 or int(p.get("bank", 0)) < amount:
            return bot.reply_to(message, "❌ Недостаточно денег на банковском счёте.")
        tax = int(amount * BANK_WITHDRAW_TAX)
        received = amount - tax
        p["bank"] = int(p.get("bank", 0)) - amount
        add_balance(uid, received)
        save_data()
        bot.reply_to(
            message,
            f"💸 **СНЯТИЕ СО СЧЁТА**\n"
            f"🏦 Снято: {money_fmt(amount)} 🪙\n"
            f"🧾 Налог (2.5%): {money_fmt(tax)} 🪙\n"
            f"💰 Получено: **{money_fmt(received)} 🪙**",
            parse_mode="Markdown"
        )
    except (ValueError, IndexError):
        bot.reply_to(message, "ℹ️ Использование: `банк снять 1000`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().startswith("депозит положить"))
def dep_make(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    p = data["players"][uid]
    try:
        amount = int(message.text.split()[2])
        if amount <= 0 or get_balance(uid) < amount:
            return bot.reply_to(message, "❌ Недостаточно средств или неверная сумма.")
        if int(p.get("deposit", 0)) > 0:
            return bot.reply_to(message, "⏳ У вас уже открыт депозит. Сначала дождитесь даты снятия.")
        rate = bank_daily_rate(p)
        add_balance(uid, -amount)
        p["deposit"] = amount
        p["deposit_start"] = int(time.time())
        p["deposit_rate"] = rate
        save_data()
        complete_quest(uid, "Открыть депозит")
        bot.reply_to(
            message,
            f"💎 **ДЕПОЗИТ ОТКРЫТ**\n"
            f"💰 Вклад: {money_fmt(amount)} 🪙\n"
            f"📈 Ставка: {rate * 100:.0f}% в день\n"
            f"📅 Срок: 3 дня\n"
            f"🏦 Откройте `банк`, чтобы увидеть дату снятия.",
            parse_mode="Markdown"
        )
    except (ValueError, IndexError):
        bot.reply_to(message, "ℹ️ Использование: `депозит положить 1000`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "депозит снять")
def dep_wd(message):
    uid = str(message.from_user.id)
    p = data["players"].get(uid, {})
    principal = int(p.get("deposit", 0) or 0)
    started = int(p.get("deposit_start", 0) or 0)
    now = int(time.time())
    if principal <= 0 or started <= 0:
        return bot.reply_to(message, "❌ У вас нет активного депозита.")
    available_at = started + BANK_TERM_SECONDS
    if now < available_at:
        remaining = available_at - now
        return bot.reply_to(
            message,
            f"⏳ **ДЕПОЗИТ ЕЩЁ ЗАКРЫТ**\n"
            f"📅 Снять можно: {time.strftime('%d.%m.%y в %H:%M:%S', time.localtime(available_at))}\n"
            f"⌛ Осталось: {remaining // 86400} дн. {(remaining % 86400) // 3600} ч.",
            parse_mode="Markdown"
        )
    rate = float(p.get("deposit_rate", bank_daily_rate(p)))
    elapsed_days = max(3, (now - started) // 86400)
    interest = int(principal * rate * elapsed_days)
    gross = principal + interest
    tax = int(gross * BANK_WITHDRAW_TAX)
    received = gross - tax
    p["deposit"] = 0
    p["deposit_start"] = 0
    p.pop("deposit_rate", None)
    add_balance(uid, received)
    save_data()
    bot.reply_to(
        message,
        f"🏦 **ДЕПОЗИТ ЗАКРЫТ**\n"
        f"💰 Первоначальный вклад: {money_fmt(principal)} 🪙\n"
        f"📈 Проценты ({rate * 100:.0f}% × {elapsed_days} дн.): +{money_fmt(interest)} 🪙\n"
        f"🧾 Налог на снятие (2.5%): −{money_fmt(tax)} 🪙\n"
        f""
        f"💎 **Зачислено на баланс: {money_fmt(received)} 🪙**",
        parse_mode="Markdown"
    )

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
            add_balance(uid, -a); add_balance(t_uid, a); bot.reply_to(message, f"✅ {a} 🪙 переведено {get_nick(t_uid)}.")
        except: bot.reply_to(message, "❌ `перевод 1000 ник`")

DAILY_QUESTS_TEMPLATE = {
    "slot": {"name": "Сделать 3 ставки в слот", "need": 3, "reward": 800},
    "crash": {"name": "Сыграть в краш 2 раза", "need": 2, "reward": 800},
    "mines": {"name": "Сыграть в мины", "need": 1, "reward": 600},
    "joker": {"name": "Сыграть в джокер", "need": 1, "reward": 600},
    "bonus": {"name": "Забрать ежедневный бонус", "need": 1, "reward": 500},
}

def ensure_daily_quests(uid):
    uid = str(uid)
    if uid not in data["players"]:
        return
    p = data["players"][uid]
    now = int(time.time())
    if "quest_date" not in p or now - p.get("quest_date", 0) >= 86400:
        quests = {}
        for key, tpl in DAILY_QUESTS_TEMPLATE.items():
            quests[key] = {
                "name": tpl["name"],
                "need": tpl["need"],
                "progress": 0,
                "reward": tpl["reward"],
                "done": False,
                "claimed": False
            }
        data["players"][uid]["quests"] = quests
        data["players"][uid]["quest_date"] = now
        save_data()

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() in ["квесты", "задания", "квест"])
def quests_menu(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    ensure_daily_quests(uid)
    q = data["players"][uid].get("quests", {})
    text = "📜 Ежедневные задания\n"
    for key, info in q.items():
        if info.get("done"):
            mark = "✅" if not info.get("claimed") else "🎁"
        else:
            mark = "❌"
        prog = f"{info.get('progress', 0)}/{info.get('need', 1)}"
        text += f"{mark} {info.get('name', key)} [{prog}] +{info.get('reward', 0)} 🪙\n"
    text += "\nНапишите: забрать квест"
    bot.reply_to(message, text)

@bot.message_handler(func=lambda m: m.text and m.text.lower().strip() == "забрать квест")
def claim_quests(message):
    uid = str(message.from_user.id)
    ensure_daily_quests(uid)
    q = data["players"].get(uid, {}).get("quests", {})
    total = 0
    claimed_names = []
    for key, info in q.items():
        if info.get("done") and not info.get("claimed", False):
            total += info.get("reward", 0)
            info["claimed"] = True
            claimed_names.append(info.get("name", key))
    if total > 0:
        add_balance(uid, total)
        save_data()
        bot.reply_to(message, f"🎉 Получено {total} 🪙\n" + "\n".join(f"• {n}" for n in claimed_names))
    else:
        bot.reply_to(message, "❌ Нет выполненных незабранных заданий.\nСмотри: квесты")

def complete_quest(uid, quest_key, amount=1):
    """quest_key: slot / crash / mines / joker / bonus"""
    uid = str(uid)
    if uid not in data["players"]:
        return
    ensure_daily_quests(uid)
    q = data["players"][uid].get("quests", {})
    if quest_key not in q:
        return
    info = q[quest_key]
    if info.get("done"):
        return
    info["progress"] = info.get("progress", 0) + amount
    if info["progress"] >= info.get("need", 1):
        info["progress"] = info.get("need", 1)
        info["done"] = True
    save_data()


# ==================== РЕПОРТ / БАН / МУТ / ЧС ====================

def resolve_target(raw):
    """Найти uid по ID, short_id или @нику"""
    raw = str(raw).strip().replace("@", "")
    # short_id
    try:
        sid = int(raw)
        uid = get_user_by_short_id(sid)
        if uid:
            return str(uid)
    except:
        pass
    # telegram id
    if raw.isdigit() and raw in data["players"]:
        return raw
    # username
    uid = get_user_by_username(raw)
    if uid:
        return str(uid)
    return None

@bot.message_handler(commands=["репорт", "report"])
def report_cmd(message):
    uid = str(message.from_user.id)
    if uid not in data["players"]:
        register_user(message.from_user)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return bot.reply_to(message, "❌ Формат:\n`/репорт текст жалобы`\nили ответом на сообщение: `/репорт причина`", parse_mode="Markdown")
    reason = parts[1].strip()
    target_uid = None
    target_name = None
    target_info = ""
    if message.reply_to_message:
        t = message.reply_to_message.from_user
        target_uid = str(t.id)
        target_name = t.first_name or str(t.id)
        target_info = f"\n👤 На кого: {target_name} (@{t.username or '—'})\n🆔 TG ID: `{t.id}`"
    # сохраняем репорт
    report = {
        "id": len(data.get("reports", [])) + 1,
        "time": int(time.time()),
        "from_uid": uid,
        "from_nick": get_nick(uid),
        "from_sid": get_user_short_id(uid),
        "target_uid": target_uid,
        "target_name": target_name,
        "reason": reason
    }
    data.setdefault("reports", []).append(report)
    if len(data["reports"]) > 200:
        data["reports"] = data["reports"][-200:]
    save_data()
    text = (
        f"🚨 ЖАЛОБА #{report['id']}\n"
        f""
        f"От: {get_nick(uid)} ({get_user_short_id(uid)})\n"
        f"TG ID: {uid}"
        f"{target_info}\n"
        f""
        f"📝 {reason}"
    )
    sent = 0
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(admin_id, text)
            sent += 1
        except:
            pass
    if sent:
        bot.reply_to(message, f"✅ Жалоба #{report['id']} отправлена администраторам.")
    else:
        bot.reply_to(message, "❌ Не удалось отправить жалобу. Попробуйте позже.")

@bot.message_handler(commands=["ban"])
def ban_cmd(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    parts = message.text.split()
    if len(parts) < 2:
        return bot.reply_to(message, "❌ Формат: `/ban ID/@ник [причина]`", parse_mode="Markdown")
    target = resolve_target(parts[1])
    if not target:
        return bot.reply_to(message, "❌ Игрок не найден.")
    reason = " ".join(parts[2:]) if len(parts) > 2 else "Без причины"
    data["banned"][target] = {"reason": reason, "by": message.from_user.id, "time": int(time.time())}
    data["blacklist"][target] = True
    save_data()
    add_admin_log("ban", message.from_user.id, target, reason)
    bot.reply_to(message, f"🚫 Игрок {get_nick(target)} ({get_user_short_id(target)}) забанен.\nПричина: {reason}")
    try:
        bot.send_message(int(target), f"🚫 Вы забанены.\nПричина: {reason}")
    except:
        pass

@bot.message_handler(commands=["unban"])
def unban_cmd(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    parts = message.text.split()
    if len(parts) < 2:
        return bot.reply_to(message, "❌ Формат: `/unban ID/@ник`", parse_mode="Markdown")
    target = resolve_target(parts[1])
    if not target:
        return bot.reply_to(message, "❌ Игрок не найден.")
    data["banned"].pop(target, None)
    data["blacklist"].pop(target, None)
    save_data()
    add_admin_log("unban", message.from_user.id, target)
    bot.reply_to(message, f"✅ Игрок {get_nick(target)} разбанен.")

@bot.message_handler(commands=["mute"])
def mute_cmd(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    parts = message.text.split()
    if len(parts) < 2:
        return bot.reply_to(message, "❌ Формат: `/mute ID/@ник [минуты]`\nБез минут — навсегда.", parse_mode="Markdown")
    target = resolve_target(parts[1])
    if not target:
        return bot.reply_to(message, "❌ Игрок не найден.")
    minutes = None
    if len(parts) >= 3:
        try:
            minutes = int(parts[2])
        except:
            pass
    until = int(time.time()) + minutes * 60 if minutes else 0
    data["muted"][target] = {"until": until, "by": message.from_user.id}
    save_data()
    add_admin_log("mute", message.from_user.id, target, f"{minutes or 'perm'} min")
    if minutes:
        bot.reply_to(message, f"🔇 Игрок {get_nick(target)} в муте на {minutes} мин.")
    else:
        bot.reply_to(message, f"🔇 Игрок {get_nick(target)} в муте навсегда.")
    try:
        bot.send_message(int(target), "🔇 Вы получили мут.")
    except:
        pass

@bot.message_handler(commands=["unmute"])
def unmute_cmd(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    parts = message.text.split()
    if len(parts) < 2:
        return bot.reply_to(message, "❌ Формат: `/unmute ID/@ник`", parse_mode="Markdown")
    target = resolve_target(parts[1])
    if not target:
        return bot.reply_to(message, "❌ Игрок не найден.")
    data["muted"].pop(target, None)
    save_data()
    add_admin_log("unmute", message.from_user.id, target)
    bot.reply_to(message, f"✅ Мут снят с {get_nick(target)}.")

@bot.message_handler(commands=["чс", "blacklist", "bl"])
def blacklist_cmd(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    parts = message.text.split()
    if len(parts) < 2:
        return bot.reply_to(message, "❌ Формат:\n/чс ID/@ник — добавить\n/чс del ID/@ник — убрать\n/чс list — список")
    if parts[1].lower() in ["list", "список"]:
        bl = data.get("blacklist", {})
        if not bl:
            return bot.reply_to(message, "ЧС пуст.")
        lines = []
        for i, uid in enumerate(list(bl.keys())[:30], 1):
            lines.append(f"{i}. {get_nick(uid)} ({get_user_short_id(uid)}) — {uid}")
        return bot.reply_to(message, "⛔ Чёрный список:\n" + "\n".join(lines))
    if parts[1].lower() in ["del", "удалить", "remove"]:
        if len(parts) < 3:
            return bot.reply_to(message, "❌ Укажите игрока.")
        target = resolve_target(parts[2])
        if not target:
            return bot.reply_to(message, "❌ Игрок не найден.")
        data["blacklist"].pop(target, None)
        save_data()
        add_admin_log("chs_del", message.from_user.id, target)
        return bot.reply_to(message, f"✅ {get_nick(target)} убран из ЧС.")
    target = resolve_target(parts[1])
    if not target:
        # если не в базе — можно добавить по сырому TG ID
        raw = parts[1].replace("@", "")
        if raw.isdigit():
            target = raw
        else:
            return bot.reply_to(message, "❌ Игрок не найден.")
    data["blacklist"][str(target)] = True
    save_data()
    add_admin_log("chs_add", message.from_user.id, target)
    bot.reply_to(message, f"⛔ {get_nick(target) if target in data['players'] else target} добавлен в ЧС.\nБот больше не отвечает этому пользователю.")

@bot.message_handler(commands=["репорты", "reports"])
def reports_list(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    reports = data.get("reports", [])
    if not reports:
        return bot.reply_to(message, "📭 Репортов пока нет.")
    # последние 15
    last = reports[-15:]
    lines = []
    for r in reversed(last):
        t = time.strftime("%d.%m %H:%M", time.localtime(r.get("time", 0)))
        target = r.get("target_name") or "—"
        lines.append(
            f"#{r.get('id')} [{t}]\n"
            f"От: {r.get('from_nick')} ({r.get('from_sid')})\n"
            f"На: {target}\n"
            f"📝 {r.get('reason', '')[:120]}\n"
        )
    bot.reply_to(message, "🚨 Последние репорты:\n\n" + "\n".join(lines))

@bot.message_handler(commands=["логи", "logs"])
def admin_logs_cmd(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    logs = data.get("admin_logs", [])
    if not logs:
        return bot.reply_to(message, "📭 Логов пока нет.")
    last = logs[-20:]
    lines = []
    for e in reversed(last):
        t = time.strftime("%d.%m %H:%M", time.localtime(e.get("time", 0)))
        target = e.get("target") or "—"
        detail = e.get("detail") or ""
        lines.append(f"[{t}] {e.get('action')} | admin:{e.get('admin')} | target:{target} {detail}")
    bot.reply_to(message, "📋 Админ-логи:\n\n" + "\n".join(lines))

print("BOT STARTED")
threading.Thread(target=run_mini_app_server, daemon=True).start()
bot.infinity_polling(skip_pending=True)
