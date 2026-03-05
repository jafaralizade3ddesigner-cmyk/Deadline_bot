import os
import json
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

# ─── Config ───────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
MANAGER_ID = int(os.environ.get("MANAGER_ID", "0"))  # Your Telegram user ID
DATA_FILE = "data.json"

# Conversation states
WAITING_DELAY_REASON = 1
WAITING_NEW_DEADLINE = 2

# ─── Data helpers ─────────────────────────────────────────
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"deadlines": {}, "pending_delays": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_deadline(deadline_id):
    data = load_data()
    return data["deadlines"].get(str(deadline_id))

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

# ─── /start ───────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id == MANAGER_ID:
        await update.message.reply_text(
            "👋 سلام مدیر!\n\n"
            "📋 *دستورات:*\n"
            "/newdeadline — ایجاد ددلاین جدید\n"
            "/active — مشاهده ددلاین‌های فعال\n"
            "/help — راهنما",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"👋 سلام {user.first_name}!\n\n"
            "⏱ این ربات برای مدیریت ددلاین‌های تیمی استفاده می‌شه.\n"
            "وقتی مدیرت ددلاینی برات تنظیم کنه، اینجا اطلاع می‌گیری.",
            parse_mode="Markdown"
        )

# ─── /newdeadline ──────────────────────────────────────────
async def new_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MANAGER_ID:
        await update.message.reply_text("⛔ فقط مدیر می‌تونه ددلاین بسازه.")
        return

    await update.message.reply_text(
        "📝 *ددلاین جدید*\n\n"
        "فرمت را به این شکل ارسال کن:\n\n"
        "`/send [user_id] [دقیقه] [عنوان]`\n\n"
        "مثال:\n"
        "`/send 123456789 30 تحویل گزارش فروش`\n\n"
        "💡 برای گرفتن ID کاربران، از /getid استفاده کن یا از اونا بخواه /myid رو بزنن.",
        parse_mode="Markdown"
    )

# ─── /send ────────────────────────────────────────────────
async def send_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MANAGER_ID:
        await update.message.reply_text("⛔ دسترسی ندارید.")
        return

    args = context.args
    if len(args) < 3:
        await update.message.reply_text(
            "❌ فرمت اشتباه!\n\n`/send [user_id] [دقیقه] [عنوان]`",
            parse_mode="Markdown"
        )
        return

    try:
        target_id = int(args[0])
        minutes = int(args[1])
        title = " ".join(args[2:])
    except ValueError:
        await update.message.reply_text("❌ user_id و دقیقه باید عدد باشن.")
        return

    deadline_id = f"{target_id}_{int(datetime.now().timestamp())}"
    end_time = datetime.now() + timedelta(minutes=minutes)

    data = load_data()
    data["deadlines"][deadline_id] = {
        "user_id": target_id,
        "title": title,
        "minutes": minutes,
        "end_time": end_time.isoformat(),
        "created_at": datetime.now().isoformat(),
        "status": "active"
    }
    save_data(data)

    # Send to user
    keyboard = [[InlineKeyboardButton("⏸ درخواست تمدید", callback_data=f"delay_request_{deadline_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                f"⏰ *ددلاین جدید دریافت کردی!*\n\n"
                f"📌 *عنوان:* {title}\n"
                f"⏱ *زمان:* {minutes} دقیقه\n"
                f"🕐 *مهلت تا:* {end_time.strftime('%H:%M:%S')}\n\n"
                f"هر {max(1, minutes//4)} دقیقه یادآوری می‌گیری.\n"
                f"اگه به زمان بیشتری نیاز داری، درخواست تمدید بده 👇"
            ),
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

        # Schedule reminders
        context.job_queue.run_once(
            remind_user,
            when=timedelta(minutes=minutes * 0.5),
            data={"deadline_id": deadline_id, "user_id": target_id, "title": title, "percent": 50},
            name=f"remind_50_{deadline_id}"
        )
        context.job_queue.run_once(
            remind_user,
            when=timedelta(minutes=minutes * 0.75),
            data={"deadline_id": deadline_id, "user_id": target_id, "title": title, "percent": 75},
            name=f"remind_75_{deadline_id}"
        )
        context.job_queue.run_once(
            remind_user,
            when=timedelta(minutes=minutes * 0.9),
            data={"deadline_id": deadline_id, "user_id": target_id, "title": title, "percent": 90},
            name=f"remind_90_{deadline_id}"
        )
        context.job_queue.run_once(
            deadline_expired,
            when=timedelta(minutes=minutes),
            data={"deadline_id": deadline_id, "user_id": target_id, "title": title},
            name=f"expire_{deadline_id}"
        )

        await update.message.reply_text(
            f"✅ ددلاین برای کاربر `{target_id}` ارسال شد!\n"
            f"📌 {title}\n⏱ {minutes} دقیقه",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در ارسال: {e}\n\nمطمئن شو کاربر ربات رو start کرده.")

# ─── Reminders ────────────────────────────────────────────
async def remind_user(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    d = job.data
    deadline = get_deadline(d["deadline_id"])
    if not deadline or deadline["status"] != "active":
        return

    end_time = datetime.fromisoformat(deadline["end_time"])
    remaining = int((end_time - datetime.now()).total_seconds())
    percent = d["percent"]

    emoji = "🟡" if percent == 50 else ("🟠" if percent == 75 else "🔴")

    keyboard = [[InlineKeyboardButton("⏸ درخواست تمدید", callback_data=f"delay_request_{d['deadline_id']}")]]

    await context.bot.send_message(
        chat_id=d["user_id"],
        text=(
            f"{emoji} *یادآوری ددلاین*\n\n"
            f"📌 {d['title']}\n"
            f"⏱ {persian_time_left(remaining)} مانده!\n"
            f"📊 {percent}% از زمان گذشته"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def deadline_expired(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    d = job.data
    deadline = get_deadline(d["deadline_id"])
    if not deadline or deadline["status"] != "active":
        return

    data = load_data()
    data["deadlines"][d["deadline_id"]]["status"] = "expired"
    save_data(data)

    # Notify user
    await context.bot.send_message(
        chat_id=d["user_id"],
        text=(
            f"🚨 *ددلاین منقضی شد!*\n\n"
            f"📌 {d['title']}\n\n"
            f"⛔ زمان شما به پایان رسید."
        ),
        parse_mode="Markdown"
    )

    # Notify manager
    await context.bot.send_message(
        chat_id=MANAGER_ID,
        text=(
            f"⚠️ *ددلاین منقضی شد*\n\n"
            f"📌 {d['title']}\n"
            f"👤 کاربر: `{d['user_id']}`\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}"
        ),
        parse_mode="Markdown"
    )

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
        f"📝 *درخواست تمدید*\n\n"
        f"📌 ددلاین: {deadline['title']}\n\n"
        f"چند دقیقه اضافه نیاز داری؟ (عدد بنویس)\n"
        f"مثال: `15`",
        parse_mode="Markdown"
    )
    return WAITING_NEW_DEADLINE

async def delay_receive_minutes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        extra_minutes = int(update.message.text.strip())
        if extra_minutes <= 0 or extra_minutes > 480:
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
        "user_id": user.id,
        "user_name": user.first_name,
        "extra_minutes": extra_minutes,
        "requested_at": datetime.now().isoformat()
    }
    save_data(data)

    # Notify manager
    keyboard = [
        [
            InlineKeyboardButton(f"✅ تأیید +{extra_minutes} دقیقه", callback_data=f"approve_{deadline_id}"),
            InlineKeyboardButton("❌ رد", callback_data=f"reject_{deadline_id}")
        ]
    ]
    await context.bot.send_message(
        chat_id=MANAGER_ID,
        text=(
            f"🔔 *درخواست تمدید ددلاین*\n\n"
            f"👤 کاربر: {user.first_name} (`{user.id}`)\n"
            f"📌 ددلاین: {deadline['title']}\n"
            f"⏱ درخواست: +{extra_minutes} دقیقه\n\n"
            f"تأیید می‌کنی؟"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    await update.message.reply_text(
        f"✅ درخواستت ارسال شد!\n"
        f"منتظر تأیید مدیر باش... 🕐"
    )
    return ConversationHandler.END

# ─── Manager approve/reject ────────────────────────────────
async def approve_delay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if update.effective_user.id != MANAGER_ID:
        await query.answer("⛔ فقط مدیر می‌تونه تأیید کنه.", show_alert=True)
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

    await query.edit_message_text(
        f"✅ *تمدید تأیید شد*\n\n"
        f"📌 {deadline['title']}\n"
        f"⏱ +{extra} دقیقه اضافه شد\n"
        f"🕐 مهلت جدید: {new_end.strftime('%H:%M:%S')}",
        parse_mode="Markdown"
    )

    # Reschedule expiry
    old_job = context.job_queue.get_jobs_by_name(f"expire_{deadline_id}")
    for j in old_job:
        j.schedule_removal()

    context.job_queue.run_once(
        deadline_expired,
        when=new_end - datetime.now(),
        data={"deadline_id": deadline_id, "user_id": deadline["user_id"], "title": deadline["title"]},
        name=f"expire_{deadline_id}"
    )

    keyboard = [[InlineKeyboardButton("⏸ درخواست تمدید", callback_data=f"delay_request_{deadline_id}")]]
    await context.bot.send_message(
        chat_id=delay_req["user_id"],
        text=(
            f"🎉 *تمدید تأیید شد!*\n\n"
            f"📌 {deadline['title']}\n"
            f"⏱ +{extra} دقیقه اضافه شد\n"
            f"🕐 مهلت جدید: {new_end.strftime('%H:%M:%S')}"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def reject_delay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if update.effective_user.id != MANAGER_ID:
        await query.answer("⛔ فقط مدیر می‌تونه رد کنه.", show_alert=True)
        return

    deadline_id = query.data.replace("reject_", "")
    data = load_data()
    deadline = data["deadlines"].get(deadline_id)
    delay_req = data["pending_delays"].get(deadline_id)

    if delay_req:
        user_id = delay_req["user_id"]
        del data["pending_delays"][deadline_id]
        save_data(data)

        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"❌ *درخواست تمدید رد شد*\n\n"
                f"📌 {deadline['title']}\n"
                f"مدیر تمدید رو تأیید نکرد. به ددلاین اصلی پایبند باش! 💪"
            ),
            parse_mode="Markdown"
        )

    await query.edit_message_text(
        f"❌ درخواست تمدید رد شد.\n📌 {deadline['title'] if deadline else ''}",
        parse_mode="Markdown"
    )

# ─── /myid ────────────────────────────────────────────────
async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"🆔 *اطلاعات شما:*\n\n"
        f"نام: {user.first_name}\n"
        f"ID: `{user.id}`\n\n"
        f"این ID رو به مدیرت بده.",
        parse_mode="Markdown"
    )

# ─── /active ──────────────────────────────────────────────
async def active_deadlines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != MANAGER_ID:
        await update.message.reply_text("⛔ دسترسی ندارید.")
        return

    data = load_data()
    actives = {k: v for k, v in data["deadlines"].items() if v["status"] == "active"}

    if not actives:
        await update.message.reply_text("📭 هیچ ددلاین فعالی وجود نداره.")
        return

    text = "📋 *ددلاین‌های فعال:*\n\n"
    for did, d in actives.items():
        end = datetime.fromisoformat(d["end_time"])
        remaining = int((end - datetime.now()).total_seconds())
        text += f"📌 {d['title']}\n"
        text += f"👤 کاربر: `{d['user_id']}`\n"
        text += f"⏱ مانده: {persian_time_left(remaining)}\n\n"

    await update.message.reply_text(text, parse_mode="Markdown")

# ─── Main ─────────────────────────────────────────────────
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(delay_request_start, pattern="^delay_request_")],
        states={
            WAITING_NEW_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, delay_receive_minutes)],
        },
        fallbacks=[]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newdeadline", new_deadline))
    app.add_handler(CommandHandler("send", send_deadline))
    app.add_handler(CommandHandler("active", active_deadlines))
    app.add_handler(CommandHandler("myid", my_id))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(approve_delay, pattern="^approve_"))
    app.add_handler(CallbackQueryHandler(reject_delay, pattern="^reject_"))

    print("🤖 ربات در حال اجراست...")
    app.run_polling()

if __name__ == "__main__":
    main()
