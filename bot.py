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
bot.infinity_polling(skip_pending=True)
