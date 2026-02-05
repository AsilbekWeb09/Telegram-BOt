import sqlite3
import time
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
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
# SETTINGS
# =========================
TOKEN = "8516700367:AAHW1TP5-sKGkfKdGsVg2e7kK1y8L3U6QMA"
ADMIN_ID = 7424095511
DB_FILE = "bot.db"

PAGE_SIZE = 5
SPAM_LIMIT_SECONDS = 0.1
last_message_time = {}

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
        phone TEXT,
        folder_id INTEGER,
        folder_name TEXT,
        pin TEXT
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
def phone_menu():
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Telefon raqamni yuborish", request_contact=True)]],
        resize_keyboard=True
    )

def user_menu(folder_id, folder_name):
    return ReplyKeyboardMarkup(
        [
            [f"📁 Papka #{folder_id} ({folder_name})"],
            ["📂 Saqlanganlar"],
            ["📥 Saqlash rejimi"],
            ["🔍 Qidirish", "🗑 Papkani tozalash"],
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

def create_user(uid, phone):
    con = db()
    cur = con.cursor()
    cur.execute("INSERT INTO users VALUES (?,?,?,?,?)",
                (uid, phone, uid, "Shaxsiy", None))
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
# SEND ITEM (ID orqali)
# =========================
async def send_item(update, folder_id, item_id):
    item = get_item_by_id(folder_id, item_id)
    if not item:
        await update.message.reply_text("❌ Bunday ID yo‘q")
        return

    t, text, fid, fname, cap = item

    if t == "text":
        await update.message.reply_text(text)
    elif t == "photo":
        await update.message.reply_photo(fid, caption=cap)
    elif t == "video":
        await update.message.reply_video(fid, caption=cap)
    elif t == "audio":
        await update.message.reply_audio(fid, caption=cap)
    elif t == "document":
        await update.message.reply_document(fid, caption=cap)
    elif t == "voice":
        await update.message.reply_voice(fid)

# =========================
# SHOW PAGE
# =========================
async def show_page(update, folder_id, page=0):
    total = count_items(folder_id)
    if total == 0:
        await update.message.reply_text("📂 Papka bo‘sh")
        return

    items = get_items(folder_id, page * PAGE_SIZE)
    msg = "📂 Saqlanganlar:\n\n"

    for i in items:
        msg += f"🆔 {i[0]} | {i[1]}\n"

    msg += "\n📌 ID yozsangiz – shu fayl chiqadi"
    await update.message.reply_text(msg)

# =========================
# START
# =========================
async def start(update, context):
    uid = str(update.message.from_user.id)
    user = get_user(uid)

    if not user:
        await update.message.reply_text(
            "📱 Telefon raqamingizni yuboring",
            reply_markup=phone_menu()
        )
        return

    await update.message.reply_text(
        "✅ Xush kelibsiz",
        reply_markup=user_menu(user[2], user[3])
    )

# =========================
# CONTACT
# =========================
async def handle_contact(update, context):
    uid = str(update.message.from_user.id)
    if get_user(uid):
        return
    create_user(uid, update.message.contact.phone_number)
    await update.message.reply_text("✅ Ro‘yxatdan o‘tdingiz")

# =========================
# MAIN HANDLER
# =========================
async def handle_all(update, context):
    uid = str(update.message.from_user.id)
    if is_spam(uid):
        return

    user = get_user(uid)
    if not user:
        await update.message.reply_text("Avval /start")
        return

    folder_id = user[2]

    if update.message.text:
        t = update.message.text.strip()

        if t == "📂 Saqlanganlar":
            await show_page(update, folder_id)
            return

        if t == "📥 Saqlash rejimi":
            context.user_data["save"] = True
            await update.message.reply_text("📥 Endi fayl yuboring")
            return

        if t == "🗑 Papkani tozalash":
            clear_folder(folder_id)
            await update.message.reply_text("🗑 Tozalandi")
            return

        # 🔥 FAOL TALAB: faqat ID yozsa chiqadi
        if t.isdigit():
            await send_item(update, folder_id, int(t))
            return

    if context.user_data.get("save"):
        if save_item(folder_id, update.message):
            await update.message.reply_text("✅ Saqlandi")
        return

# =========================
# MAIN
# =========================
def main():
    init_db()
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_all))

    print("Bot ishga tushdi")
    app.run_polling()

if __name__ == "__main__":
    main()
