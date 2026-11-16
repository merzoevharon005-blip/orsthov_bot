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

# --- СПИСОК АДМИНОВ ---
ADMIN_IDS = [8211650013, 6940877915] 

# --- НАСТРОЙКА ХРАНЕНИЯ ДАННЫХ ---
DATA_DIR = pathlib.Path("/app/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = DATA_DIR / "database.json"

data = {
    "players": {}, "promos": {}, "activations": [], "history": [], "transfers": [],
    "clans": {}, "clan_bosses": {}
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
    if uid not in data["players"]: register_user_by_id(uid)
    data["players"][uid]["balance"] += amount
    save_data()

def register_user(user):
    uid = str(user.id)
    if uid not in data["players"]:
        data["players"][uid] = {
            "username": user.username or user.first_name,
            "balance": 1000, "last_bonus": 0, "short_id": random.randint(1000, 9999),
            "clan_id": None, "weapon": 1, "armor": 1
        }
        save_data()

def register_user_by_id(uid):
    if uid not in data["players"]:
        data["players"][uid] = {
            "username": "Player", "balance": 1000, "last_bonus": 0, 
            "short_id": random.randint(1000, 9999), "clan_id": None, "weapon": 1, "armor": 1
        }
        save_data()

def get_history_roulette():
    if not data["history"]: return "История пуста."
    res = []
    for item in data["history"][-15:]:
        num, color = item["number"], item["color"]
        sym = "🟢" if color == "green" else ("🔴" if color == "red" else "⚫️")
        res.append(f"{sym}{num}")
