
# --- БОСС ---
@bot.callback_query_handler(func=lambda call: call.data == "attack_boss")
def attack_boss(call):
    bot.answer_callback_query(call.id)
    uid = str(call.from_user.id)
    clan_id = data["players"].get(uid, {}).get("clan_id")
    if not clan_id: return bot.answer_callback_query(call.id, "❌ Ты не в клане!")
    boss = data["clan_bosses"].get(str(clan_id))
    if not boss: return
    weapon_lvl = data["players"][uid].get("weapon", 1)
    armor_lvl = data["players"][uid].get("armor", 1)
    damage = weapon_lvl * random.randint(10, 20)
    boss["hp"] -= damage
    if boss["hp"] <= 0:
        reward = 500 * boss["level"]
        add_balance(uid, reward)
        boss["level"] += 1
        boss["max_hp"] += 1000
        boss["hp"] = boss["max_hp"]
        msg = f"🎉 **БОСС УБИТ!**\nПоследний удар твой. Награда: **+{reward} 🪙**"
    else:
        counter = max(1, random.randint(10, 20) - (armor_lvl * 5))
        data["players"][uid]["balance"] = max(0, get_balance(uid) - counter)
        msg = f"⚔️ Урон: {damage}\nБосс бьет: {counter}"
    save_data()
    bot.send_message(call.message.chat.id, msg, parse_mode="Markdown", reply_markup=main_menu())

# --- ИГРОВЫЕ РЕЖИМЫ ---
# Режимы со ставками и платными игровыми пакетами отключены.
@bot.callback_query_handler(func=lambda call: call.data in ("game_crash", "game_mines", "game_roulette"))
def disabled_game(call):
    bot.answer_callback_query(call.id, "Этот режим отключён.")
    bot.send_message(call.message.chat.id, "🎮 Этот игровой режим пока недоступен.")

@bot.callback_query_handler(func=lambda call: call.data == "donate_menu")
def donate_menu(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "⭐ Покупка игровой валюты отключена. Используй бонусы и промокоды.")


# --- АДМИНКА ---
@bot.message_handler(commands=['give'])
def admin_give(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        args = message.text.split()[1:]
        target_id = str(int(args[0]))
        amount = int(args[1])
        register_user_by_id(target_id)
        add_balance(target_id, amount)
        bot.reply_to(message, f"✅ Выдано {amount} 🪙 игроку {target_id}.")
    except: bot.reply_to(message, "❌ `/give ID СУММА`", parse_mode="Markdown")

@bot.message_handler(commands=['reset'])
def admin_reset(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        target_id = str(int(message.text.split()[1]))
        if target_id in data["players"]:
            data["players"][target_id]["balance"] = 0
            save_data()
            bot.reply_to(message, "♻️ Сброшено.")
    except: bot.reply_to(message, "❌ `/reset ID`", parse_mode="Markdown")

@bot.message_handler(commands=['createpromo'])
def create_promo(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        args = message.text.split()[1:]
        code = args[0].upper()
        data["promos"][code] = {"amount": int(args[1]), "uses_left": int(args[2])}
        save_data()
        bot.reply_to(message, "✅ Промокод создан.")
    except: bot.reply_to(message, "❌ `/createpromo КОД СУММА ЮЗЫ`", parse_mode="Markdown")

@bot.message_handler(commands=['wipe'])
def admin_wipe(message):
    if message.from_user.id not in ADMIN_IDS: return
    for uid, pdata in data["players"].items():
        pdata["balance"] = 1000
    save_data()
    bot.reply_to(message, "♻️ Все балансы по 1000.")

# --- ТЕКСТОВЫЕ КОМАНДЫ ---
@bot.message_handler(content_types=['text'])
def handle_all_text(message):
    if message.text.startswith('/'): return
    text = message.text.lower().strip()
    parts = text.split()
    user_id = message.from_user.id
    register_user(message.from_user)

    if text in ["б", "баланс"]:
        return bot.reply_to(message, f"🪙 Баланс: {get_balance(user_id)} Mon1Coin")
    if text in ["профиль", "п"]:
        return bot.reply_to(message, f"👤 ID: `{get_user_short_id(user_id)}`\nНик: {get_nick(user_id)}", parse_mode="Markdown")
    if text in ["помощь", "help"]:
        return help_callback(type('obj', (object,), {'id': None, 'message': message, 'from_user': message.from_user, 'answer_callback_query': lambda *a: None})())
    if text in ["топ", "top"]:
        return top_callback(type('obj', (object,), {'id': None, 'message': message, 'from_user': message.from_user, 'answer_callback_query': lambda *a: None})())
    if text in ["бонус", "bonus"]:
        return process_bonus(user_id, message.chat.id)

    if parts[0] in ["сменить", "ник"] and len(parts) >= 2:
        new_nick = " ".join(parts[1:])[:15]
        data["players"][str(user_id)]["username"] = new_nick
        save_data()
        return bot.reply_to(message, f"✅ Твой новый ник: **{new_nick}**", parse_mode="Markdown")

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
            bot.reply_to(
                message,
                f"🎁 Промокод активирован! Начислено +{promo['amount']} Mon1Coin."
            )
            return

# --- ЗАПУСК ---
if __name__ == "__main__":
