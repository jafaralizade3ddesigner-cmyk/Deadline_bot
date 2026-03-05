import os
import json
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
SUPER_ADMIN_ID = int(os.environ.get("MANAGER_ID", "0"))
DATA_FILE = "data.json"

WAITING_NEW_DEADLINE = 1
WAITING_DEADLINE_TITLE = 2
WAITING_DEADLINE_MINUTES = 3
WAITING_ADD_MANAGER_ID = 4

# ─── Data ─────────────────────────────────────────────────
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"deadlines": {}, "pending_delays": {}, "users": {}, "managers": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def is_manager(user_id):
    if user_id == SUPER_ADMIN_ID:
        return True
    data = load_data()
    return str(user_id) in data.get("managers", {})

def is_super_admin(user_id):
    return user_id == SUPER_ADMIN_ID

def register_user(user):
    data = load_data()
    if "users" not in data:
        data["users"] = {}
    uid = str(user.id)
    is_new = uid not in data["users"]
    data["users"][uid] = {
        "id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name or "",
        "username": user.username or "",
        "joined_at": datetime.now().isoformat()
    }
    # Update manager record too if they're a manager
    if uid in data.get("managers", {}):
        data["managers"][uid].update({
            "first_name": user.first_name,
            "last_name": user.last_name or "",
            "username": user.username or "",
        })
    save_data(data)
    return is_new

def get_all_users():
    """All registered users INCLUDING managers (everyone can receive deadlines)"""
    data = load_data()
    users = data.get("users", {})
    # Exclude only the super admin from receiving deadlines
    return {k: v for k, v in users.items() if int(k) != SUPER_ADMIN_ID}

def get_deadline(deadline_id):
    return load_data()["deadlines"].get(str(deadline_id))

def persian_time_left(seconds):
    if seconds <= 0:
        return "⛔ منقضی شده"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    parts = []
    if h: parts.append(f"{h} ساعت")
    if m: parts.append(f"{m} دقیقه")
    if s and not h: parts.append(f"{s} ثانیه")
    return " و ".join(parts)

# ─── Keyboards ────────────────────────────────────────────
def manager_menu(is_super=False):
    rows = [
        [KeyboardButton("➕ ددلاین جدید"), KeyboardButton("👥 لیست کاربران")],
        [KeyboardButton("📋 ددلاین‌های فعال"), KeyboardButton("❓ راهنما")],
    ]
    if is_super:
        rows.append([KeyboardButton("👔 مدیران"), KeyboardButton("➕ افزودن مدیر")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def member_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🆔 آیدی من"), KeyboardButton("⏱ ددلاین‌های من")],
        [KeyboardButton("❓ راهنما")]
    ], resize_keyboard=True)

def cancel_keyboard():
    return ReplyKeyboardMarkup([[KeyboardButton("🚫 لغو")]], resize_keyboard=True)

# ─── Cancel ───────────────────────────────────────────────
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    context.user_data.clear()
    await update.message.reply_text(
        "❌ عملیات لغو شد.",
        reply_markup=manager_menu(is_super=is_super_admin(user.id))
    )
    return ConversationHandler.END

# ─── /start ───────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_new = register_user(user)
    context.user_data.clear()  # Reset any stuck conversation

    if is_manager(user.id):
        await update.message.reply_text(
            f"👋 *سلام {user.first_name}!*\n\n"
            f"{'👑 مدیر اصلی' if is_super_admin(user.id) else '👔 مدیر'}\n\n"
            f"از منوی پایین استفاده کن 👇",
            parse_mode="Markdown",
            reply_markup=manager_menu(is_super=is_super_admin(user.id))
        )
    else:
        if is_new:
            data = load_data()
            all_manager_ids = [SUPER_ADMIN_ID] + [int(k) for k in data.get("managers", {}).keys()]
            for mid in all_manager_ids:
                try:
                    await context.bot.send_message(
                        chat_id=mid,
                        text=f"🆕 *کاربر جدید ثبت شد!*\n\n👤 {user.first_name} {user.last_name or ''}\n🔗 @{user.username or '—'}\n🆔 `{user.id}`",
                        parse_mode="Markdown"
                    )
                except:
                    pass
        await update.message.reply_text(
            f"👋 *سلام {user.first_name}!*\n\n"
            f"🆔 آیدی عددی تو:\n`{user.id}`\n\n"
            f"این عدد رو به مدیرت بفرست.\nاز منوی پایین استفاده کن 👇",
            parse_mode="Markdown",
            reply_markup=member_menu()
        )

# ─── Menu handler ─────────────────────────────────────────
async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user

    if text == "🆔 آیدی من":
        await update.message.reply_text(f"🆔 آیدی عددی تو:\n\n`{user.id}`\n\nکپی کن و به مدیرت بفرست.", parse_mode="Markdown")
    elif text == "⏱ ددلاین‌های من":
        await my_deadlines(update, context)
    elif text == "❓ راهنما":
        await help_cmd(update, context)
    elif is_manager(user.id):
        if text == "➕ ددلاین جدید":
            await show_user_list_for_deadline(update, context)
        elif text == "👥 لیست کاربران":
            await list_users(update, context)
        elif text == "📋 ددلاین‌های فعال":
            await active_deadlines(update, context)
        elif text == "👔 مدیران" and is_super_admin(user.id):
            await list_managers(update, context)

# ─── Add manager conversation ─────────────────────────────
async def add_manager_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_super_admin(update.effective_user.id):
        return ConversationHandler.END
    await update.message.reply_text(
        "👔 *افزودن مدیر جدید*\n\n"
        "آیدی عددی مدیر جدید رو بنویس:\n\n"
        "💡 ازش بخواه توی ربات /myid یا 🆔 بزنه تا آیدیش رو بگیره.\n\n"
        "برای لغو 🚫 بزن.",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )
    return WAITING_ADD_MANAGER_ID

async def add_manager_receive_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_super_admin(update.effective_user.id):
        return ConversationHandler.END

    text = update.message.text.strip()

    try:
        new_manager_id = int(text)
    except ValueError:
        await update.message.reply_text(
            "❌ آیدی باید عدد باشه.\n\nدوباره وارد کن یا 🚫 بزن برای لغو:",
            reply_markup=cancel_keyboard()
        )
        return WAITING_ADD_MANAGER_ID

    if new_manager_id == SUPER_ADMIN_ID:
        await update.message.reply_text("⚠️ این آیدی مدیر اصلیه!", reply_markup=manager_menu(is_super=True))
        return ConversationHandler.END

    data = load_data()
    if "managers" not in data:
        data["managers"] = {}

    user_info = data.get("users", {}).get(str(new_manager_id), {})
    data["managers"][str(new_manager_id)] = {
        "id": new_manager_id,
        "first_name": user_info.get("first_name", f"مدیر {new_manager_id}"),
        "last_name": user_info.get("last_name", ""),
        "username": user_info.get("username", ""),
        "added_at": datetime.now().isoformat(),
        "added_by": update.effective_user.id
    }
    save_data(data)

    name = user_info.get("first_name", str(new_manager_id))
    await update.message.reply_text(
        f"✅ *{name}* به عنوان مدیر اضافه شد!\n\nبهش بگو /start بزنه تا منوی مدیر ببینه.",
        parse_mode="Markdown",
        reply_markup=manager_menu(is_super=True)
    )
    try:
        await context.bot.send_message(
            chat_id=new_manager_id,
            text="🎉 *تبریک!*\n\nتو به عنوان *مدیر* تعیین شدی.\n\n/start بزن تا منوی مدیر ببینی.",
            parse_mode="Markdown"
        )
    except:
        pass
    return ConversationHandler.END

# ─── List managers ────────────────────────────────────────
async def list_managers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_super_admin(update.effective_user.id):
        return
    data = load_data()
    managers = data.get("managers", {})
    if not managers:
        await update.message.reply_text("📭 هنوز مدیری اضافه نشده.\nاز '➕ افزودن مدیر' مدیر جدید اضافه کن.")
        return
    text = f"👔 *مدیران ({len(managers)} نفر):*\n\n"
    keyboard = []
    for mid, m in managers.items():
        name = f"{m.get('first_name','')} {m.get('last_name','')}".strip()
        un = f"@{m['username']}" if m.get('username') else "—"
        text += f"👤 {name} | {un}\n🆔 `{m['id']}`\n\n"
        keyboard.append([InlineKeyboardButton(f"🗑 حذف {name}", callback_data=f"remove_manager_{mid}")])
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def remove_manager_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_super_admin(update.effective_user.id):
        return
    mid = query.data.replace("remove_manager_", "")
    data = load_data()
    if mid in data.get("managers", {}):
        name = data["managers"][mid].get("first_name", mid)
        del data["managers"][mid]
        save_data(data)
        await query.edit_message_text(f"✅ {name} از لیست مدیران حذف شد.")
    else:
        await query.edit_message_text("❌ مدیر پیدا نشد.")

# ─── Users ────────────────────────────────────────────────
async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_manager(update.effective_user.id):
        return
    users = get_all_users()
    if not users:
        await update.message.reply_text("📭 هنوز کاربری ثبت نشده.\nاز اعضا بخواه ربات رو /start کنن.")
        return
    text = f"👥 *کاربران ({len(users)} نفر):*\n\n"
    for uid, u in users.items():
        name = f"{u['first_name']} {u.get('last_name','')}".strip()
        un = f"@{u['username']}" if u.get('username') else "—"
        role = " 👔" if is_manager(int(uid)) else ""
        text += f"👤 {name}{role} | {un}\n🆔 `{u['id']}`\n\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def my_deadlines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = load_data()
    my = [(k, v) for k, v in data["deadlines"].items()
          if str(v["user_id"]) == str(user.id) and v["status"] == "active"]
    if not my:
        await update.message.reply_text("📭 ددلاین فعالی نداری.")
        return
    text = "⏱ *ددلاین‌های فعال تو:*\n\n"
    for did, d in my:
        end = datetime.fromisoformat(d["end_time"])
        remaining = int((end - datetime.now()).total_seconds())
        manager_name = d.get("manager_name", "مدیر")
        text += f"📌 {d['title']}\n👔 از طرف: {manager_name}\n⏳ {persian_time_left(remaining)}\n\n"
    await update.message.reply_text(text, parse_mode="Markdown")

# ─── New deadline conversation ────────────────────────────
async def show_user_list_for_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_manager(update.effective_user.id):
        return
    users = get_all_users()
    if not users:
        await update.message.reply_text("📭 هنوز کاربری ثبت نشده.")
        return
    keyboard = []
    for uid, u in users.items():
        name = f"{u['first_name']} {u.get('last_name','')}".strip()
        un = f" (@{u['username']})" if u.get('username') else ""
        role = " 👔" if is_manager(int(uid)) else ""
        keyboard.append([InlineKeyboardButton(f"👤 {name}{role}{un}", callback_data=f"select_user_{uid}")])
    await update.message.reply_text(
        "👥 *برای کدوم عضو ددلاین بفرستم؟*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def select_user_for_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_manager(update.effective_user.id):
        return
    uid = query.data.replace("select_user_", "")
    users = get_all_users()
    user = users.get(uid)
    if not user:
        await query.edit_message_text("❌ کاربر پیدا نشد.")
        return
    context.user_data["selected_user_id"] = uid
    context.user_data["selected_user_name"] = user["first_name"]
    await query.edit_message_text(
        f"📌 *ددلاین برای {user['first_name']}*\n\nعنوان ددلاین رو بنویس:\n\n/cancel برای لغو",
        parse_mode="Markdown"
    )
    return WAITING_DEADLINE_TITLE

async def receive_deadline_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_manager(update.effective_user.id):
        return ConversationHandler.END
    context.user_data["deadline_title"] = update.message.text.strip()
    name = context.user_data.get("selected_user_name", "")
    await update.message.reply_text(
        f"⏱ چند دقیقه مهلت برای *{name}*؟\n\nمثال: `30`\n\n/cancel برای لغو",
        parse_mode="Markdown"
    )
    return WAITING_DEADLINE_MINUTES

async def receive_deadline_minutes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_manager(update.effective_user.id):
        return ConversationHandler.END
    try:
        minutes = int(update.message.text.strip())
        if minutes <= 0 or minutes > 1440:
            await update.message.reply_text("❌ عدد بین ۱ تا ۱۴۴۰ وارد کن.")
            return WAITING_DEADLINE_MINUTES
    except ValueError:
        await update.message.reply_text("❌ فقط عدد وارد کن.")
        return WAITING_DEADLINE_MINUTES
    target_id = int(context.user_data["selected_user_id"])
    title = context.user_data["deadline_title"]
    name = context.user_data["selected_user_name"]
    manager = update.effective_user
    context.user_data.clear()
    await send_deadline_to_user(update, context, target_id, minutes, title, manager)
    await update.message.reply_text(
        f"✅ ددلاین برای *{name}* ارسال شد!",
        parse_mode="Markdown",
        reply_markup=manager_menu(is_super=is_super_admin(manager.id))
    )
    return ConversationHandler.END

async def send_deadline_to_user(update, context, target_id, minutes, title, manager_user=None):
    deadline_id = f"{target_id}_{int(datetime.now().timestamp())}"
    end_time = datetime.now() + timedelta(minutes=minutes)
    manager_name = manager_user.first_name if manager_user else "مدیر"
    manager_id = manager_user.id if manager_user else SUPER_ADMIN_ID

    data = load_data()
    data["deadlines"][deadline_id] = {
        "user_id": target_id, "title": title, "minutes": minutes,
        "end_time": end_time.isoformat(), "created_at": datetime.now().isoformat(),
        "status": "active", "manager_id": manager_id, "manager_name": manager_name
    }
    save_data(data)

    keyboard = [[InlineKeyboardButton("⏸ درخواست تمدید", callback_data=f"delay_request_{deadline_id}")]]
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=(f"⏰ *ددلاین جدید!*\n\n"
                  f"📌 *عنوان:* {title}\n"
                  f"👔 *از طرف:* {manager_name}\n"
                  f"⏱ *زمان:* {minutes} دقیقه\n"
                  f"🕐 *مهلت تا:* {end_time.strftime('%H:%M:%S')}\n\n"
                  f"یادآوری‌های خودکار دریافت می‌کنی 👇"),
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
        )
        for pct, label in [(0.5, 50), (0.75, 75), (0.9, 90)]:
            context.job_queue.run_once(remind_user, when=timedelta(minutes=minutes * pct),
                data={"deadline_id": deadline_id, "user_id": target_id, "title": title,
                      "percent": label, "manager_name": manager_name},
                name=f"remind_{label}_{deadline_id}")
        context.job_queue.run_once(deadline_expired, when=timedelta(minutes=minutes),
            data={"deadline_id": deadline_id, "user_id": target_id, "title": title, "manager_id": manager_id},
            name=f"expire_{deadline_id}")
    except Exception as e:
        if update:
            await update.message.reply_text(f"❌ خطا: {e}\nمطمئن شو کاربر ربات رو /start کرده.")

async def send_deadline_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_manager(update.effective_user.id):
        return
    args = context.args
    if len(args) < 3:
        await update.message.reply_text("`/send [user_id] [دقیقه] [عنوان]`", parse_mode="Markdown")
        return
    try:
        target_id = int(args[0])
        minutes = int(args[1])
        title = " ".join(args[2:])
    except ValueError:
        await update.message.reply_text("❌ user_id و دقیقه باید عدد باشن.")
        return
    await send_deadline_to_user(update, context, target_id, minutes, title, update.effective_user)
    await update.message.reply_text("✅ ددلاین ارسال شد!")

# ─── Reminders & expiry ───────────────────────────────────
async def remind_user(context: ContextTypes.DEFAULT_TYPE):
    d = context.job.data
    deadline = get_deadline(d["deadline_id"])
    if not deadline or deadline["status"] != "active":
        return
    end_time = datetime.fromisoformat(deadline["end_time"])
    remaining = int((end_time - datetime.now()).total_seconds())
    pct = d["percent"]
    emoji = "🟡" if pct == 50 else ("🟠" if pct == 75 else "🔴")
    keyboard = [[InlineKeyboardButton("⏸ درخواست تمدید", callback_data=f"delay_request_{d['deadline_id']}")]]
    await context.bot.send_message(
        chat_id=d["user_id"],
        text=f"{emoji} *یادآوری*\n\n📌 {d['title']}\n👔 از طرف: {d.get('manager_name','مدیر')}\n⏱ {persian_time_left(remaining)} مانده!\n📊 {pct}% از زمان گذشته",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def deadline_expired(context: ContextTypes.DEFAULT_TYPE):
    d = context.job.data
    deadline = get_deadline(d["deadline_id"])
    if not deadline or deadline["status"] != "active":
        return
    data = load_data()
    data["deadlines"][d["deadline_id"]]["status"] = "expired"
    save_data(data)
    manager_name = deadline.get("manager_name", "مدیر")
    await context.bot.send_message(chat_id=d["user_id"],
        text=f"🚨 *ددلاین منقضی شد!*\n\n📌 {d['title']}\n👔 از طرف: {manager_name}\n⛔ زمان تموم شد.",
        parse_mode="Markdown")
    manager_id = d.get("manager_id", SUPER_ADMIN_ID)
    await context.bot.send_message(chat_id=manager_id,
        text=f"⚠️ *ددلاین منقضی شد*\n\n📌 {d['title']}\n👤 کاربر: `{d['user_id']}`\n🕐 {datetime.now().strftime('%H:%M:%S')}",
        parse_mode="Markdown")

# ─── Delay request ────────────────────────────────────────
async def delay_request_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    deadline_id = query.data.replace("delay_request_", "")
    deadline = get_deadline(deadline_id)
    if not deadline or deadline["status"] != "active":
        await query.edit_message_text("⛔ این ددلاین دیگه فعال نیست.")
        return ConversationHandler.END
    context.user_data["pending_deadline_id"] = deadline_id
    await query.edit_message_text(
        f"📝 *درخواست تمدید*\n\n📌 {deadline['title']}\n\nچند دقیقه اضافه نیاز داری؟\nمثال: `15`\n\n/cancel برای لغو",
        parse_mode="Markdown"
    )
    return WAITING_NEW_DEADLINE

async def delay_receive_minutes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        extra = int(update.message.text.strip())
        if extra <= 0 or extra > 480:
            await update.message.reply_text("❌ عدد بین ۱ تا ۴۸۰ وارد کن.")
            return WAITING_NEW_DEADLINE
    except ValueError:
        await update.message.reply_text("❌ فقط عدد وارد کن.")
        return WAITING_NEW_DEADLINE
    deadline_id = context.user_data.get("pending_deadline_id")
    deadline = get_deadline(deadline_id)
    user = update.effective_user
    data = load_data()
    data["pending_delays"][deadline_id] = {
        "user_id": user.id, "user_name": user.first_name,
        "extra_minutes": extra, "requested_at": datetime.now().isoformat()
    }
    save_data(data)
    keyboard = [[
        InlineKeyboardButton(f"✅ تأیید +{extra} دقیقه", callback_data=f"approve_{deadline_id}"),
        InlineKeyboardButton("❌ رد", callback_data=f"reject_{deadline_id}")
    ]]
    manager_id = deadline.get("manager_id", SUPER_ADMIN_ID)
    await context.bot.send_message(chat_id=manager_id,
        text=f"🔔 *درخواست تمدید*\n\n👤 {user.first_name} (`{user.id}`)\n📌 {deadline['title']}\n⏱ +{extra} دقیقه",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data.clear()
    await update.message.reply_text("✅ درخواستت ارسال شد! منتظر تأیید مدیر باش... 🕐")
    return ConversationHandler.END

async def approve_delay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_manager(update.effective_user.id):
        return
    deadline_id = query.data.replace("approve_", "")
    data = load_data()
    deadline = data["deadlines"].get(deadline_id)
    delay_req = data["pending_delays"].get(deadline_id)
    if not deadline or not delay_req:
        await query.edit_message_text("❌ ددلاین یافت نشد.")
        return
    extra = delay_req["extra_minutes"]
    new_end = datetime.fromisoformat(deadline["end_time"]) + timedelta(minutes=extra)
    data["deadlines"][deadline_id]["end_time"] = new_end.isoformat()
    data["deadlines"][deadline_id]["status"] = "active"
    del data["pending_delays"][deadline_id]
    save_data(data)
    for j in context.job_queue.get_jobs_by_name(f"expire_{deadline_id}"):
        j.schedule_removal()
    context.job_queue.run_once(deadline_expired, when=new_end - datetime.now(),
        data={"deadline_id": deadline_id, "user_id": deadline["user_id"],
              "title": deadline["title"], "manager_id": deadline.get("manager_id", SUPER_ADMIN_ID)},
        name=f"expire_{deadline_id}")
    await query.edit_message_text(f"✅ تمدید تأیید شد\n📌 {deadline['title']}\n+{extra} دقیقه | مهلت جدید: {new_end.strftime('%H:%M:%S')}")
    keyboard = [[InlineKeyboardButton("⏸ درخواست تمدید", callback_data=f"delay_request_{deadline_id}")]]
    await context.bot.send_message(chat_id=delay_req["user_id"],
        text=f"🎉 *تمدید تأیید شد!*\n\n📌 {deadline['title']}\n👔 از طرف: {deadline.get('manager_name','مدیر')}\n+{extra} دقیقه\n🕐 {new_end.strftime('%H:%M:%S')}",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def reject_delay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_manager(update.effective_user.id):
        return
    deadline_id = query.data.replace("reject_", "")
    data = load_data()
    deadline = data["deadlines"].get(deadline_id)
    delay_req = data["pending_delays"].get(deadline_id)
    if delay_req:
        del data["pending_delays"][deadline_id]
        save_data(data)
        await context.bot.send_message(chat_id=delay_req["user_id"],
            text=f"❌ *درخواست تمدید رد شد*\n\n📌 {deadline['title'] if deadline else ''}\nبه ددلاین پایبند باش! 💪",
            parse_mode="Markdown")
    await query.edit_message_text("❌ درخواست تمدید رد شد.")

# ─── Active deadlines ─────────────────────────────────────
async def active_deadlines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_manager(update.effective_user.id):
        return
    data = load_data()
    manager_id = update.effective_user.id
    if is_super_admin(manager_id):
        actives = {k: v for k, v in data["deadlines"].items() if v["status"] == "active"}
    else:
        actives = {k: v for k, v in data["deadlines"].items()
                   if v["status"] == "active" and v.get("manager_id") == manager_id}
    if not actives:
        await update.message.reply_text("📭 هیچ ددلاین فعالی وجود نداره.")
        return
    users = data.get("users", {})
    text = "📋 *ددلاین‌های فعال:*\n\n"
    for did, d in actives.items():
        end = datetime.fromisoformat(d["end_time"])
        remaining = int((end - datetime.now()).total_seconds())
        u = users.get(str(d["user_id"]), {})
        name = u.get("first_name", str(d["user_id"]))
        text += f"📌 {d['title']}\n👤 {name}\n⏱ {persian_time_left(remaining)}\n\n"
    await update.message.reply_text(text, parse_mode="Markdown")

# ─── Help ─────────────────────────────────────────────────
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_super_admin(user.id):
        text = ("📖 *راهنمای مدیر اصلی:*\n\n"
                "➕ *ددلاین جدید* — ارسال ددلاین\n"
                "👥 *لیست کاربران* — اعضای ثبت‌شده\n"
                "📋 *ددلاین‌های فعال* — همه ددلاین‌ها\n"
                "👔 *مدیران* — لیست و حذف مدیران\n"
                "➕ *افزودن مدیر* — مدیر جدید\n\n"
                "💡 برای لغو هر عملیات /cancel بزن.")
    elif is_manager(user.id):
        text = ("📖 *راهنمای مدیر:*\n\n"
                "➕ *ددلاین جدید* — ارسال ددلاین\n"
                "👥 *لیست کاربران* — اعضا\n"
                "📋 *ددلاین‌های فعال* — ددلاین‌های من\n\n"
                "💡 برای لغو هر عملیات /cancel بزن.")
    else:
        text = ("📖 *راهنما:*\n\n"
                "🆔 *آیدی من* — نمایش آیدی برای مدیر\n"
                "⏱ *ددلاین‌های من* — ددلاین‌های فعال")
    await update.message.reply_text(text, parse_mode="Markdown")

# ─── /myid command ────────────────────────────────────────
async def myid_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(f"🆔 آیدی عددی تو:\n\n`{user.id}`", parse_mode="Markdown")

# ─── Main ─────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    cancel_filter = filters.Regex("^🚫 لغو$") | filters.COMMAND

    delay_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(delay_request_start, pattern="^delay_request_")],
        states={WAITING_NEW_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, delay_receive_minutes)]},
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex("^🚫 لغو$"), cancel)]
    )
    deadline_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(select_user_for_deadline, pattern="^select_user_")],
        states={
            WAITING_DEADLINE_TITLE: [MessageHandler(filters.TEXT & ~cancel_filter, receive_deadline_title)],
            WAITING_DEADLINE_MINUTES: [MessageHandler(filters.TEXT & ~cancel_filter, receive_deadline_minutes)],
        },
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex("^🚫 لغو$"), cancel)]
    )
    add_manager_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^➕ افزودن مدیر$"), add_manager_start)],
        states={WAITING_ADD_MANAGER_ID: [MessageHandler(filters.TEXT & ~cancel_filter, add_manager_receive_id)]},
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex("^🚫 لغو$"), cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("myid", myid_cmd))
    app.add_handler(CommandHandler("send", send_deadline_cmd))
    app.add_handler(CommandHandler("active", active_deadlines))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(delay_conv)
    app.add_handler(deadline_conv)
    app.add_handler(add_manager_conv)
    app.add_handler(CallbackQueryHandler(approve_delay, pattern="^approve_"))
    app.add_handler(CallbackQueryHandler(reject_delay, pattern="^reject_"))
    app.add_handler(CallbackQueryHandler(remove_manager_callback, pattern="^remove_manager_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu))

    print("🤖 ربات در حال اجراست...")
    app.run_polling()

if __name__ == "__main__":
    main()
