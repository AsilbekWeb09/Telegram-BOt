import os
import sqlite3
import time
from dotenv import load_dotenv

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    filters
)

# =========================
# LOAD ENV
# =========================
load_dotenv()

# =========================
# SETTINGS
# =========================
TOKEN = os.getenv("TOKEN")
DB_FILE = "bot.db"

PAGE_SIZE = 5
SPAM_LIMIT_SECONDS = 0.2
last_message_time = {}

if not TOKEN:
    raise ValueError("❌ TOKEN topilmadi! .env faylga TOKEN yoz yoki Koyeb ENV ga qo'y!")

# =========================
# DATABASE
# =========================
def db():
    return sqlite3.connect(DB_FILE)

def init_db():
    con = db()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        folder_id INTEGER,
        folder_name TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        folder_id INTEGER,
        type TEXT,
        text TEXT,
        file_id TEXT,
        file_name TEXT,
        caption TEXT
    )
    """)

    con.commit()
    con.close()

# =========================
# SPAM CHECK
# =========================
def is_spam(uid):
    now = time.time()
    if uid in last_message_time and now - last_message_time[uid] < SPAM_LIMIT_SECONDS:
        return True
    last_message_time[uid] = now
    return False

# =========================
# MENUS
# =========================
def user_menu(folder_id, folder_name, save_mode=False):
    save_text = "🟢 Saqlash rejimi ON" if save_mode else "🔴 Saqlash rejimi OFF"

    return ReplyKeyboardMarkup(
        [
            [f"📁 Papka #{folder_id} ({folder_name})"],
            ["📂 Saqlanganlar"],
            [save_text],
            ["🗑 Papkani tozalash"],
            ["ℹ️ Info"]
        ],
        resize_keyboard=True
    )

# =========================
# DB HELPERS
# =========================
def get_user(uid):
    con = db()
    cur = con.cursor()
    cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    r = cur.fetchone()
    con.close()
    return r

def create_user(uid):
    con = db()
    cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO users VALUES (?,?,?)", (uid, int(uid), "Shaxsiy"))
    con.commit()
    con.close()

def save_item(folder_id, msg):
    con = db()
    cur = con.cursor()

    t = None
    text = None
    file_id = None
    file_name = None
    caption = msg.caption

    if msg.text:
        t = "text"
        text = msg.text
    elif msg.photo:
        t = "photo"
        file_id = msg.photo[-1].file_id
    elif msg.video:
        t = "video"
        file_id = msg.video.file_id
        file_name = msg.video.file_name
    elif msg.audio:
        t = "audio"
        file_id = msg.audio.file_id
        file_name = msg.audio.file_name
    elif msg.document:
        t = "document"
        file_id = msg.document.file_id
        file_name = msg.document.file_name
    elif msg.voice:
        t = "voice"
        file_id = msg.voice.file_id
    else:
        return False

    cur.execute("""
    INSERT INTO items(folder_id,type,text,file_id,file_name,caption)
    VALUES(?,?,?,?,?,?)
    """, (folder_id, t, text, file_id, file_name, caption))

    con.commit()
    con.close()
    return True

def get_items(folder_id, offset=0):
    con = db()
    cur = con.cursor()
    cur.execute("""
    SELECT id,type,text,file_id,file_name,caption
    FROM items
    WHERE folder_id=?
    ORDER BY id DESC
    LIMIT ? OFFSET ?
    """, (folder_id, PAGE_SIZE, offset))
    r = cur.fetchall()
    con.close()
    return r

def count_items(folder_id):
    con = db()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM items WHERE folder_id=?", (folder_id,))
    c = cur.fetchone()[0]
    con.close()
    return c

def get_item_by_id(folder_id, item_id):
    con = db()
    cur = con.cursor()
    cur.execute("""
    SELECT type,text,file_id,file_name,caption
    FROM items
    WHERE folder_id=? AND id=?
    """, (folder_id, item_id))
    r = cur.fetchone()
    con.close()
    return r

def clear_folder(folder_id):
    con = db()
    cur = con.cursor()
    cur.execute("DELETE FROM items WHERE folder_id=?", (folder_id,))
    con.commit()
    con.close()

# =========================
# SEND ITEM
# =========================
async def send_item(update, folder_id, item_id):
    item = get_item_by_id(folder_id, item_id)
    msg_obj = update.message if update.message else update.callback_query.message

    if not item:
        await msg_obj.reply_text("❌ Bunday ID yo‘q")
        return

    t, text, fid, fname, cap = item

    if t == "text":
        await msg_obj.reply_text(text)
    elif t == "photo":
        await msg_obj.reply_photo(fid, caption=cap)
    elif t == "video":
        await msg_obj.reply_video(fid, caption=cap)
    elif t == "audio":
        await msg_obj.reply_audio(fid, caption=cap)
    elif t == "document":
        await msg_obj.reply_document(fid, caption=cap)
    elif t == "voice":
        await msg_obj.reply_voice(fid)

# =========================
# SHOW PAGE
# =========================
async def show_page(update, folder_id, page=0):
    total = count_items(folder_id)
    msg_obj = update.message if update.message else update.callback_query.message

    if total == 0:
        await msg_obj.reply_text("📂 Papka bo‘sh")
        return

    offset = page * PAGE_SIZE
    items = get_items(folder_id, offset)

    msg = f"📂 Saqlanganlar (Page {page+1}):\n\n"
    for i in items:
        msg += f"🆔 {i[0]} | {i[1]}\n"

    msg += "\n📌 ID yozsangiz – shu fayl chiqadi"

    buttons = []
    if page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"page_{page-1}"))
    if offset + PAGE_SIZE < total:
        buttons.append(InlineKeyboardButton("➡️ Keyingi", callback_data=f"page_{page+1}"))

    markup = InlineKeyboardMarkup([buttons]) if buttons else None
    await msg_obj.reply_text(msg, reply_markup=markup)

# =========================
# CALLBACK
# =========================
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    uid = str(query.from_user.id)
    user = get_user(uid)
    if not user:
        create_user(uid)
        user = get_user(uid)

    folder_id = user[1]

    data = query.data
    if data.startswith("page_"):
        page = int(data.split("_")[1])

        total = count_items(folder_id)
        offset = page * PAGE_SIZE
        items = get_items(folder_id, offset)

        msg = f"📂 Saqlanganlar (Page {page+1}):\n\n"
        for i in items:
            msg += f"🆔 {i[0]} | {i[1]}\n"

        msg += "\n📌 ID yozsangiz – shu fayl chiqadi"

        buttons = []
        if page > 0:
            buttons.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"page_{page-1}"))
        if offset + PAGE_SIZE < total:
            buttons.append(InlineKeyboardButton("➡️ Keyingi", callback_data=f"page_{page+1}"))

        markup = InlineKeyboardMarkup([buttons]) if buttons else None
        await query.message.edit_text(msg, reply_markup=markup)

# =========================
# START
# =========================
async def start(update, context):
    uid = str(update.message.from_user.id)

    if not get_user(uid):
        create_user(uid)

    user = get_user(uid)
    save_mode = context.user_data.get("save", False)

    await update.message.reply_text(
        "✅ Xush kelibsiz!\n\n📌 Saqlash rejimini yoqib fayl yuborsangiz saqlanadi.",
        reply_markup=user_menu(user[1], user[2], save_mode)
    )

# =========================
# INFO
# =========================
async def info(update, context):
    await update.message.reply_text(
        "ℹ️ Bot imkoniyatlari:\n\n"
        "✅ Saqlash rejimi ON/OFF\n"
        "✅ Matn, rasm, video, audio, dokument saqlaydi\n"
        "✅ ID orqali qayta chiqaradi\n"
        "✅ Papkani tozalash bor\n"
        "✅ Pagination bor\n"
    )

# =========================
# MAIN HANDLER
# =========================
async def handle_all(update, context):
    uid = str(update.message.from_user.id)

    if is_spam(uid):
        return

    if not get_user(uid):
        create_user(uid)

    user = get_user(uid)
    folder_id = user[1]

    if update.message and update.message.text:
        t = update.message.text.strip()

        if t == "📂 Saqlanganlar":
            await show_page(update, folder_id, 0)
            return

        if "Saqlash rejimi" in t:
            current = context.user_data.get("save", False)
            context.user_data["save"] = not current
            save_mode = context.user_data["save"]

            await update.message.reply_text(
                f"✅ Saqlash rejimi {'ON' if save_mode else 'OFF'}",
                reply_markup=user_menu(folder_id, user[2], save_mode)
            )
            return

        if t == "🗑 Papkani tozalash":
            clear_folder(folder_id)
            await update.message.reply_text("🗑 Papka tozalandi!")
            return

        if t == "ℹ️ Info":
            await info(update, context)
            return

        if t.isdigit():
            await send_item(update, folder_id, int(t))
            return

    if context.user_data.get("save", False):
        if save_item(folder_id, update.message):
            await update.message.reply_text("✅ Saqlandi!")
        return

# =========================
# MAIN
# =========================
def main():
    init_db()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_all))

    print("Bot ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()
