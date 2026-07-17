import sys
import subprocess
import os

# === АВТОУСТАНОВКА ===
try:
    import telegram
    import libsql_client
except ImportError:
    print("📦 Устанавливаю python-telegram-bot и libsql-client...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "python-telegram-bot", "libsql-client"])
    print("✅ Готово!")
    import telegram
    import libsql_client

# === ОСНОВНОЙ КОД ===
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters

# ========== НАСТРОЙКИ ==========
TELEGRAM_TOKEN = "8878655390:AAEwYv0NSRQRu4rV-j2Q-2JMhPba2fJxi60"  # ВСТАВЬ СВОЙ ТОКЕН!
ADMIN_ID = 1076312001

TURSO_URL = "libsql://vk-bot-cursedd.aws-eu-west-1.turso.io"
TURSO_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3ODQyOTA1NDAsImlkIjoiMDE5ZjcwMDAtOTcwMS03NDJjLWIwM2EtNzA0MTQ2MDk4ZWI2Iiwia2lkIjoicWpYbEhLbElGQmJNX29uRDlaWEkyWFVfazVBT3h3X3JIMF9TcUZ6MmU0ZyIsInJpZCI6ImM3OTFiYzM5LTg3YjktNDgwZC1iZjRkLTEwMDdiNTI1YTg2NCJ9.rvnr8-mOPA7ydTmVKb1C4QDIxA_se-HSIiGQX5OaJ9vnj89C4xJ5PZnHn5ldw4eQMf-5pRXztvisg-chcKj4Dw"

logging.basicConfig(level=logging.INFO)

NAME, ADMIN_NICK, TARIFF = range(3)

# ========== ПОДКЛЮЧЕНИЕ К БАЗЕ ==========
def get_db():
    return libsql_client.connect(TURSO_URL, auth_token=TURSO_TOKEN)

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS server_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER,
            username TEXT,
            server_name TEXT,
            admin_nick TEXT,
            map_size INTEGER,
            wipe_days INTEGER,
            tariff TEXT,
            max_players INTEGER DEFAULT 5,
            status TEXT DEFAULT 'pending',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS servers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            admin TEXT,
            size INTEGER,
            wipe_days INTEGER,
            tariff TEXT DEFAULT 'free',
            max_players INTEGER DEFAULT 5,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def create_free_server(name, admin_nick):
    conn = get_db()
    conn.execute("""
        INSERT INTO servers (name, admin, size, wipe_days, tariff, max_players)
        VALUES (?, ?, 40, 7, 'free', 5)
    """, (name, admin_nick))
    server_id = conn.last_insert_rowid()
    conn.commit()
    conn.close()
    return server_id

def create_premium_order(tg_id, username, server_name, admin_nick):
    conn = get_db()
    conn.execute("""
        INSERT INTO server_orders (tg_id, username, server_name, admin_nick, map_size, wipe_days, tariff, max_players)
        VALUES (?, ?, ?, ?, 150, 30, 'premium', 100)
    """, (tg_id, username, server_name, admin_nick))
    order_id = conn.last_insert_rowid()
    conn.commit()
    conn.close()
    return order_id

def approve_order(order_id):
    conn = get_db()
    conn.execute("UPDATE server_orders SET status='approved' WHERE id=?", (order_id,))
    row = conn.execute("SELECT tg_id, server_name, admin_nick FROM server_orders WHERE id=?", (order_id,)).fetchone()
    conn.execute("""
        INSERT INTO servers (name, admin, size, wipe_days, tariff, max_players)
        VALUES (?, ?, 150, 30, 'premium', 100)
    """, (row[1], row[2]))
    server_id = conn.last_insert_rowid()
    conn.commit()
    conn.close()
    return server_id, row[0], row[1]

def get_pending_orders():
    conn = get_db()
    rows = conn.execute("SELECT id, tg_id, username, server_name, admin_nick, created_at FROM server_orders WHERE status='pending' ORDER BY created_at DESC").fetchall()
    conn.close()
    return rows

def get_user_servers(tg_id):
    conn = get_db()
    rows = conn.execute("SELECT name, admin, size, tariff FROM servers WHERE admin IN (SELECT admin_nick FROM server_orders WHERE tg_id=?)", (tg_id,)).fetchall()
    conn.close()
    return rows

# ========== КОМАНДЫ ==========
async def start(update, context):
    await update.message.reply_text(
        "🏗️ <b>York — Создание серверов</b>\n\n"
        "Выберите действие:\n"
        "/create — создать сервер\n"
        "/my — мои сервера\n"
        "/help — справка\n\n"
        "📌 Бесплатный сервер: 40x40, вайп 7 дней\n"
        "⭐ Премиум сервер: 150x150, вайп 30 дней — 100 ₽/мес",
        parse_mode="HTML"
    )

async def help_command(update, context):
    await update.message.reply_text(
        "📖 <b>Команды:</b>\n"
        "/create — начать создание сервера\n"
        "/my — список моих серверов\n"
        "/pending — список заявок (только для админа)\n"
        "/approve [ID] — одобрить заявку (только для админа)",
        parse_mode="HTML"
    )

async def create_start(update, context):
    await update.message.reply_text("🏗️ Введите <b>название сервера</b>:", parse_mode="HTML")
    return NAME

async def get_server_name(update, context):
    context.user_data['server_name'] = update.message.text
    await update.message.reply_text("👤 Введите ваш <b>ник в игре</b> (администратор сервера):", parse_mode="HTML")
    return ADMIN_NICK

async def get_admin_nick(update, context):
    context.user_data['admin_nick'] = update.message.text
    keyboard = [
        [InlineKeyboardButton("🆓 Бесплатный (40x40)", callback_data="tariff_free")],
        [InlineKeyboardButton("⭐ Премиум (150x150) — 100 ₽/мес", callback_data="tariff_premium")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📌 <b>Выберите тариф:</b>", parse_mode="HTML", reply_markup=reply_markup)
    return TARIFF

async def tariff_selection(update, context):
    query = update.callback_query
    await query.answer()
    tariff = query.data.replace("tariff_", "")
    tg_id = update.effective_user.id
    username = update.effective_user.username or "Без ника"
    server_name = context.user_data.get('server_name')
    admin_nick = context.user_data.get('admin_nick')

    if tariff == "free":
        server_id = create_free_server(server_name, admin_nick)
        await query.edit_message_text(
            f"✅ <b>Бесплатный сервер создан!</b>\n\n"
            f"📛 Название: {server_name}\n"
            f"👤 Администратор: {admin_nick}\n"
            f"📐 Размер: 40x40\n"
            f"🔄 Вайп: каждые 7 дней\n"
            f"👥 Игроков: до 5\n\n"
            f"🎮 Играй: https://york-game.onrender.com/play?server={server_id}",
            parse_mode="HTML"
        )
        return ConversationHandler.END

    elif tariff == "premium":
        order_id = create_premium_order(tg_id, username, server_name, admin_nick)
        await query.edit_message_text(
            f"⏳ <b>Заявка на премиум сервер создана!</b>\n\n"
            f"📛 Название: {server_name}\n"
            f"👤 Администратор: {admin_nick}\n"
            f"📐 Размер: 150x150\n"
            f"🔄 Вайп: 30 дней\n"
            f"💰 Стоимость: 100 ₽/мес\n\n"
            f"📋 После оплаты админ активирует сервер.",
            parse_mode="HTML"
        )
        # Уведомление админу
        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"⭐ <b>Новая заявка на Premium сервер!</b>\n\n"
                f"ID: {order_id}\n"
                f"Игрок: @{username} (TG ID: {tg_id})\n"
                f"Название: {server_name}\n"
                f"Админ: {admin_nick}\n"
                f"Размер: 150x150\n"
                f"Вайп: 30 дней\n"
                f"Стоимость: 100 ₽\n\n"
                f"Для активации: /approve {order_id}",
                parse_mode="HTML"
            )
        except:
            pass
        return ConversationHandler.END

async def cancel(update, context):
    await update.message.reply_text("❌ Создание сервера отменено.")
    return ConversationHandler.END

async def my_servers(update, context):
    tg_id = update.effective_user.id
    servers = get_user_servers(tg_id)
    if not servers:
        await update.message.reply_text("📭 У тебя пока нет серверов. Создай новый командой /create")
        return
    msg = "📋 <b>Твои сервера:</b>\n\n"
    for s in servers:
        emoji = "🆓" if s[3] == "free" else "⭐"
        msg += f"{emoji} <b>{s[0]}</b>\n"
        msg += f"   👤 Админ: {s[1]}\n"
        msg += f"   📐 Размер: {s[2]}x{s[2]}\n"
        msg += f"   📋 Тариф: {s[3]}\n\n"
    await update.message.reply_text(msg, parse_mode="HTML")

# ========== АДМИН КОМАНДЫ ==========
async def pending_orders(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ У вас нет прав на эту команду.")
        return
    rows = get_pending_orders()
    if not rows:
        await update.message.reply_text("📭 Нет ожидающих заявок.")
        return
    msg = "📋 <b>Ожидающие заявки:</b>\n\n"
    for row in rows:
        msg += f"ID: <b>{row[0]}</b> | @{row[2]} | {row[3]} (админ: {row[4]}) | {row[5]}\n"
    msg += "\nДля активации: /approve [ID]"
    await update.message.reply_text(msg, parse_mode="HTML")

async def approve_order(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ У вас нет прав на эту команду.")
        return
    if not context.args:
        await update.message.reply_text("❌ Укажите ID заявки: /approve 123")
        return
    try:
        order_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Укажите числовой ID: /approve 123")
        return
    try:
        server_id, tg_id, server_name = approve_order(order_id)
        await update.message.reply_text(f"✅ Заявка #{order_id} одобрена! Сервер создан.")
        try:
            await context.bot.send_message(
                tg_id,
                f"✅ <b>Ваш премиум сервер создан!</b>\n\n"
                f"📛 Название: {server_name}\n"
                f"🎮 Играй: https://york-game.onrender.com/play?server={server_id}\n\n"
                f"Приятной игры! 🎮",
                parse_mode="HTML"
            )
        except:
            pass
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ========== ЗАПУСК ==========
def main():
    init_db()
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("create", create_start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_server_name)],
            ADMIN_NICK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_admin_nick)],
            TARIFF: [CallbackQueryHandler(tariff_selection, pattern="^tariff_")]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("my", my_servers))
    app.add_handler(CommandHandler("pending", pending_orders))
    app.add_handler(CommandHandler("approve", approve_order))

    print("🤖 Бот запущен!")
    app.run_polling()

if __name__ == "__main__":
    main()
