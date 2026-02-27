import json
import os
import logging
import random
from datetime import datetime, timedelta
from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ==================== تنظیمات ====================
BOT_TOKEN = "xxxxxxxxxx"
DATA_FILE = "rp_data.json"
ADMIN_ID = "xxxxxxx"
MAX_COUNTRY_NAME_LEN = 20

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ==================== دیتابیس ====================
def load_db():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_db():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=4)

db = load_db()

# ==================== توابع کمکی ====================

def get_group_db(chat_id):
    chat_id = str(chat_id)
    if chat_id not in db:
        db[chat_id] = {
            "users": {},
            "countries": {},
            "alliances": [],
            "requests": {},
            "market": {},
            "factory_market": {},
            "votes": {}
        }
    # اطمینان از وجود کلیدهای جدید در دیتابیس‌های قدیمی
    db[chat_id].setdefault("votes", {})
    db[chat_id].setdefault("factory_market", {})
    return db[chat_id]

def get_user_id_by_country(group_db, country_name):
    for name, uid in group_db["countries"].items():
        if name.lower() == country_name.lower():
            return uid
    return None

def get_country_by_user_id(group_db, user_id):
    user_id = str(user_id)
    user = group_db["users"].get(user_id)
    return user["country"] if user else None

def is_allied(group_db, uid1, uid2):
    return [uid1, uid2] in group_db["alliances"] or [uid2, uid1] in group_db["alliances"]

def process_factories(user_data):
    """تولید خودکار سرباز توسط کارخانه‌ها"""
    user_data.setdefault("factories", 0)
    user_data.setdefault("last_factory_update", datetime.now().isoformat())

    if user_data["factories"] <= 0:
        return 0

    last_update = datetime.fromisoformat(user_data["last_factory_update"])
    hours_passed = (datetime.now() - last_update).total_seconds() / 3600.0

    if hours_passed < 1:
        return 0

    whole_hours = int(hours_passed)
    produced = whole_hours * user_data["factories"] * 10
    user_data["army"] = user_data.get("army", 0) + produced
    user_data["last_factory_update"] = (last_update + timedelta(hours=whole_hours)).isoformat()
    return produced

async def check_bankruptcy(update, group_db, user_id, kicked=False):
    """
    بررسی ورشکستگی. اگر kicked=True باشد، پیام سقوط نمایش داده نمی‌شود
    (چون پیام اخراج قبلاً فرستاده شده).
    """
    user_id = str(user_id)
    if user_id not in group_db["users"]:
        return False
    if group_db["users"][user_id]["cities"] > 0:
        return False

    country_name = group_db["users"][user_id]["country"]

    # پاکسازی کامل داده‌های کشور
    del group_db["users"][user_id]
    group_db["countries"].pop(country_name, None)
    group_db["alliances"] = [a for a in group_db["alliances"] if user_id not in a]
    group_db["requests"].pop(user_id, None)
    group_db["votes"].pop(user_id, None)
    group_db["market"].pop(user_id, None)
    group_db["factory_market"].pop(user_id, None)

    # پاک کردن رای‌های این کاربر از vote_kick دیگران
    for votes in group_db["votes"].values():
        if user_id in votes:
            votes.remove(user_id)

    save_db()

    if not kicked:
        await update.message.reply_text(
            f"💀 *سقوط یک امپراتوری!*\n"
            f"کشور *{country_name}* تمام شهرهای خود را از دست داد و از نقشه محو شد!",
            parse_mode='Markdown'
        )
    return True

# ==================== منوی دستورات ====================

async def post_init(application):
    commands = [
        BotCommand("claim",         "تصاحب یک کشور"),
        BotCommand("profile",       "مشاهده وضعیت کشور"),
        BotCommand("world",         "نقشه سیاسی جهان"),
        BotCommand("tax",           "جمع‌آوری مالیات (هر ۳۰ دقیقه)"),
        BotCommand("military",      "خرید نیروی نظامی"),
        BotCommand("buyfactory",    "خرید کارخانه ارتش‌سازی"),
        BotCommand("rename",        "تغییر نام کشور"),
        BotCommand("color",         "تغییر رنگ/ایموجی کشور"),
        BotCommand("send",          "ارسال سکه"),
        BotCommand("sendcity",      "واگذاری رایگان شهر"),
        BotCommand("sellcity",      "فروش شهر"),
        BotCommand("acceptcity",    "تایید خرید شهر"),
        BotCommand("sendfactory",   "واگذاری رایگان کارخانه"),
        BotCommand("sellfactory",   "فروش کارخانه"),
        BotCommand("acceptfactory", "تایید خرید کارخانه"),
        BotCommand("attack",        "حمله و شرط‌بندی روی شهرها"),
        BotCommand("ally",          "پیشنهاد اتحاد"),
        BotCommand("accept",        "پذیرش اتحاد"),
        BotCommand("breakally",     "شکستن پیمان اتحاد"),
        BotCommand("votekick",      "رای به اخراج یک کشور متخلف"),
        BotCommand("help",          "راهنما"),
    ]
    await application.bot.set_my_commands(commands)

# ==================== دستورات پایه ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌍 *به ربات رول‌پلی ژئوپلیتیک خوش آمدید!*\n\n"
        "برای شروع، کشور خود را انتخاب کنید:\n"
        "`/claim [نام کشور]`\n\n"
        "برای دیدن راهنما `/help` را بزنید.",
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📜 *راهنمای دستورات:*\n\n"
        "🌍 *پایه:*\n"
        "`/claim [نام]` — تأسیس کشور\n"
        "`/profile` یا `/profile @username` — مشاهده پروفایل\n"
        "`/world` — نقشه سیاسی جهان\n"
        "`/rename [نام جدید]` — تغییر نام کشور\n"
        "`/color [ایموجی]` — تغییر رنگ روی نقشه\n\n"
        "💰 *اقتصاد:*\n"
        "`/tax` — جمع مالیات (هر ۳۰ دقیقه، ۷۰ سکه به ازای هر شهر)\n"
        "`/military [تعداد]` — خرید سرباز (۱۰ سکه هر سرباز)\n"
        "`/buyfactory [تعداد]` — خرید کارخانه (ساعتی ۱۰ سرباز خودکار)\n"
        "`/send [کشور] [مبلغ]` — ارسال سکه\n\n"
        "🏙 *شهرها:*\n"
        "`/sendcity [کشور] [تعداد]` — واگذاری رایگان\n"
        "`/sellcity [کشور] [تعداد] [قیمت]` — فروش\n"
        "`/acceptcity [فروشنده]` — تأیید خرید\n\n"
        "🏭 *کارخانه‌ها:*\n"
        "`/sendfactory [کشور] [تعداد]` — واگذاری رایگان\n"
        "`/sellfactory [کشور] [تعداد] [قیمت]` — فروش\n"
        "`/acceptfactory [فروشنده]` — تأیید خرید\n\n"
        "⚔️ *نظامی:*\n"
        "`/attack [کشور] [شهر شرط‌بندی]` — حمله (ارتش بزرگتر شانس بیشتری دارد)\n\n"
        "🤝 *دیپلماسی:*\n"
        "`/ally [کشور]` — پیشنهاد اتحاد\n"
        "`/accept [کشور]` — پذیرش اتحاد\n"
        "`/breakally [کشور]` — شکستن پیمان اتحاد\n\n"
        "🚷 `/votekick [کشور]` — رای اخراج متخلف",
        parse_mode='Markdown'
    )

# ==================== مدیریت کشور ====================

async def claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)

    if not context.args:
        return await update.message.reply_text("❌ فرمت: `/claim [نام کشور]`", parse_mode='Markdown')

    country_name = " ".join(context.args)

    if len(country_name) > MAX_COUNTRY_NAME_LEN:
        return await update.message.reply_text(f"❌ نام کشور نمی‌تواند بیشتر از {MAX_COUNTRY_NAME_LEN} کاراکتر باشد.")
    if user_id in group_db["users"]:
        return await update.message.reply_text("❌ شما قبلاً کشوری دارید!")
    if any(c.lower() == country_name.lower() for c in group_db["countries"]):
        return await update.message.reply_text("❌ این نام قبلاً ثبت شده است.")

    username = update.message.from_user.username
    group_db["users"][user_id] = {
        "name": update.message.from_user.first_name,
        "username": username.lower() if username else "",
        "country": country_name,
        "color": "⚪️",
        "money": 5000,
        "army": 100,
        "cities": 21,
        "factories": 0,
        "last_tax": "2000-01-01T00:00:00",
        "last_factory_update": datetime.now().isoformat()
    }
    group_db["countries"][country_name] = user_id
    save_db()
    await update.message.reply_text(f"🎉 تبریک! شما رهبری *{country_name}* را بر عهده گرفتید.", parse_mode='Markdown')

async def rename_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)

    if user_id not in group_db["users"]:
        return await update.message.reply_text("❌ شما کشوری ندارید.")
    if not context.args:
        return await update.message.reply_text("❌ فرمت: `/rename [نام جدید]`", parse_mode='Markdown')

    new_name = " ".join(context.args)
    if len(new_name) > MAX_COUNTRY_NAME_LEN:
        return await update.message.reply_text(f"❌ نام نمی‌تواند بیشتر از {MAX_COUNTRY_NAME_LEN} کاراکتر باشد.")
    if any(c.lower() == new_name.lower() for c in group_db["countries"]):
        return await update.message.reply_text("❌ این نام قبلاً ثبت شده است.")

    old_name = group_db["users"][user_id]["country"]
    del group_db["countries"][old_name]
    group_db["countries"][new_name] = user_id
    group_db["users"][user_id]["country"] = new_name
    save_db()
    await update.message.reply_text(f"🔄 نام کشور از *{old_name}* به *{new_name}* تغییر یافت.", parse_mode='Markdown')

async def set_color(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)

    if user_id not in group_db["users"]:
        return await update.message.reply_text("❌ کشوری ندارید.")
    if not context.args:
        return await update.message.reply_text("❌ مثال: `/color 🔴`", parse_mode='Markdown')

    group_db["users"][user_id]["color"] = context.args[0]
    save_db()
    await update.message.reply_text(f"🎨 رنگ کشور شما به {context.args[0]} تغییر یافت.")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)
    target_id = user_id

    if context.args and context.args[0].startswith('@'):
        target_username = context.args[0].replace('@', '').lower()
        target_id = next(
            (uid for uid, data in group_db["users"].items()
             if data.get("username", "") == target_username),
            None
        )
        if not target_id:
            return await update.message.reply_text("❌ کاربری با این یوزرنیم یافت نشد.")

    if target_id not in group_db["users"]:
        return await update.message.reply_text("❌ شما هنوز کشوری ندارید.")

    user_data = group_db["users"][target_id]
    new_soldiers = process_factories(user_data)
    save_db()

    allies = [
        get_country_by_user_id(group_db, a[1] if a[0] == target_id else a[0])
        for a in group_db["alliances"] if target_id in a
    ]
    ally_text = "، ".join(allies) if allies else "ندارد"

    text = (
        f"🏛 *دولت {user_data['country']}* {user_data.get('color', '⚪️')}\n"
        f"👤 رهبر: {user_data['name']}\n\n"
        f"🏙 شهرها: {user_data.get('cities', 21)}\n"
        f"🏭 کارخانه‌ها: {user_data.get('factories', 0)}\n"
        f"💰 خزانه: {user_data['money']} سکه\n"
        f"🪖 ارتش: {user_data['army']} سرباز\n"
        f"🤝 متحدین: {ally_text}"
    )
    if new_soldiers > 0:
        text += f"\n\n_➕ {new_soldiers} سرباز جدید توسط کارخانه‌ها ساخته شد_"

    await update.message.reply_text(text, parse_mode='Markdown')

async def world(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)

    if not group_db["countries"]:
        return await update.message.reply_text("🌍 جهان هنوز خالی از سکنه است!")

    # مرتب‌سازی بر اساس تعداد شهر (نزولی)
    sorted_countries = sorted(
        group_db["countries"].items(),
        key=lambda x: group_db["users"][x[1]].get("cities", 0),
        reverse=True
    )

    text = "🌍 *نقشه سیاسی جهان:*\n\n"
    for i, (country, uid) in enumerate(sorted_countries, 1):
        user = group_db["users"][uid]
        color = user.get("color", "⚪️")
        text += f"{i}. {color} *{country}* | 🏙 {user.get('cities', 21)} | 🪖 {user['army']}\n"

    if group_db["alliances"]:
        text += "\n🤝 *اتحادها:*\n"
        for a in group_db["alliances"]:
            c1 = get_country_by_user_id(group_db, a[0])
            c2 = get_country_by_user_id(group_db, a[1])
            if c1 and c2:
                text += f"▪️ {c1} 🤝 {c2}\n"

    await update.message.reply_text(text, parse_mode='Markdown')

# ==================== اقتصاد ====================

async def tax(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)

    if user_id not in group_db["users"]:
        return await update.message.reply_text("❌ هنوز کشوری ندارید!")

    user_data = group_db["users"][user_id]
    last_tax = datetime.fromisoformat(user_data["last_tax"])
    now = datetime.now()
    cooldown = timedelta(minutes=30)

    if now < last_tax + cooldown:
        remaining = (last_tax + cooldown) - now
        m, s = divmod(int(remaining.total_seconds()), 60)
        return await update.message.reply_text(f"⏳ {m} دقیقه و {s} ثانیه دیگر مراجعه کنید.")

    process_factories(user_data)
    cities = user_data.get("cities", 21)
    tax_amount = cities * 70
    user_data["money"] += tax_amount
    user_data["last_tax"] = now.isoformat()
    save_db()
    await update.message.reply_text(
        f"💰 *{tax_amount}* سکه مالیات جمع‌آوری شد! (به ازای {cities} شهر)",
        parse_mode='Markdown'
    )

async def military(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)

    if user_id not in group_db["users"]:
        return await update.message.reply_text("❌ کشوری ندارید!")
    if len(context.args) != 1 or not context.args[0].isdigit():
        return await update.message.reply_text("❌ فرمت: `/military 50`", parse_mode='Markdown')

    amount = int(context.args[0])
    if amount <= 0:
        return await update.message.reply_text("❌ تعداد باید بیشتر از صفر باشد.")

    cost = amount * 10
    user_data = group_db["users"][user_id]

    if user_data["money"] < cost:
        return await update.message.reply_text(f"❌ بودجه کافی نیست! نیاز: {cost} سکه.")

    user_data["money"] -= cost
    user_data["army"] += amount
    save_db()
    await update.message.reply_text(
        f"🪖 *{amount}* نیروی جدید جذب شد. (هزینه: {cost} سکه)",
        parse_mode='Markdown'
    )

async def send_money(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)

    if user_id not in group_db["users"]:
        return await update.message.reply_text("❌ کشوری ندارید.")
    if len(context.args) < 2:
        return await update.message.reply_text("❌ فرمت: `/send [کشور] [مبلغ]`", parse_mode='Markdown')

    amount_str = context.args[-1]
    target_country = " ".join(context.args[:-1])

    if not amount_str.isdigit():
        return await update.message.reply_text("❌ مبلغ باید عدد صحیح باشد.")

    amount = int(amount_str)
    if amount <= 0:
        return await update.message.reply_text("❌ مبلغ باید بیشتر از صفر باشد.")

    target_id = get_user_id_by_country(group_db, target_country)
    if not target_id:
        return await update.message.reply_text("❌ کشور مقصد پیدا نشد.")
    if target_id == user_id:
        return await update.message.reply_text("❌ نمی‌توانید به خودتان سکه بفرستید.")

    user_data = group_db["users"][user_id]
    if user_data["money"] < amount:
        return await update.message.reply_text("❌ خزانه کافی نیست!")

    user_data["money"] -= amount
    group_db["users"][target_id]["money"] += amount
    save_db()
    await update.message.reply_text(
        f"💸 *{amount}* سکه به *{target_country}* منتقل شد.",
        parse_mode='Markdown'
    )

# ==================== شهرها ====================

async def send_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)

    if user_id not in group_db["users"]:
        return await update.message.reply_text("❌ کشوری ندارید.")
    if len(context.args) < 2:
        return await update.message.reply_text("❌ فرمت: `/sendcity [کشور] [تعداد]`", parse_mode='Markdown')

    amount_str = context.args[-1]
    target_country = " ".join(context.args[:-1])

    if not amount_str.isdigit() or int(amount_str) <= 0:
        return await update.message.reply_text("❌ تعداد شهر نامعتبر است.")

    amount = int(amount_str)
    target_id = get_user_id_by_country(group_db, target_country)

    if not target_id:
        return await update.message.reply_text("❌ کشور مقصد پیدا نشد.")
    if target_id == user_id:
        return await update.message.reply_text("❌ نمی‌توانید به خودتان شهر بفرستید.")

    user_data = group_db["users"][user_id]
    if user_data.get("cities", 0) < amount:
        return await update.message.reply_text("❌ شما این تعداد شهر ندارید!")

    user_data["cities"] -= amount
    group_db["users"][target_id]["cities"] = group_db["users"][target_id].get("cities", 0) + amount
    save_db()

    await update.message.reply_text(
        f"🏙 *{amount}* شهر از *{user_data['country']}* به *{target_country}* واگذار شد.",
        parse_mode='Markdown'
    )
    await check_bankruptcy(update, group_db, user_id)

async def sell_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)

    if user_id not in group_db["users"]:
        return await update.message.reply_text("❌ کشوری ندارید.")
    if len(context.args) < 3:
        return await update.message.reply_text("❌ فرمت: `/sellcity [کشور] [تعداد] [قیمت]`", parse_mode='Markdown')

    price_str = context.args[-1]
    amount_str = context.args[-2]
    target_country = " ".join(context.args[:-2])

    if not price_str.isdigit() or not amount_str.isdigit():
        return await update.message.reply_text("❌ تعداد و قیمت باید عدد صحیح باشند.")

    price = int(price_str)
    amount = int(amount_str)

    if amount <= 0 or price < 0:
        return await update.message.reply_text("❌ مقادیر نامعتبر.")

    target_id = get_user_id_by_country(group_db, target_country)
    if not target_id:
        return await update.message.reply_text("❌ خریدار پیدا نشد.")
    if target_id == user_id:
        return await update.message.reply_text("❌ نمی‌توانید به خودتان بفروشید.")

    if group_db["users"][user_id].get("cities", 0) < amount:
        return await update.message.reply_text("❌ شهر کافی ندارید.")

    group_db["market"][user_id] = {"target_id": target_id, "cities": amount, "price": price}
    save_db()

    seller_country = group_db["users"][user_id]["country"]
    await update.message.reply_text(
        f"📜 پیشنهاد فروش *{amount}* شهر به قیمت *{price}* سکه برای *{target_country}* ارسال شد.\n"
        f"برای تأیید: `/acceptcity {seller_country}`",
        parse_mode='Markdown'
    )

async def accept_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    buyer_id = str(update.message.from_user.id)

    if buyer_id not in group_db["users"]:
        return await update.message.reply_text("❌ کشوری ندارید.")
    if not context.args:
        return await update.message.reply_text("❌ فرمت: `/acceptcity [نام فروشنده]`", parse_mode='Markdown')

    seller_country = " ".join(context.args)
    seller_id = get_user_id_by_country(group_db, seller_country)

    if not seller_id or seller_id not in group_db["market"]:
        return await update.message.reply_text("❌ پیشنهادی از این کشور یافت نشد.")

    offer = group_db["market"][seller_id]
    if offer["target_id"] != buyer_id:
        return await update.message.reply_text("❌ این پیشنهاد برای شما نیست.")

    buyer_data = group_db["users"][buyer_id]
    seller_data = group_db["users"][seller_id]

    # اطمینان از اینکه فروشنده هنوز شهر کافی دارد
    if seller_data.get("cities", 0) < offer["cities"]:
        del group_db["market"][seller_id]
        save_db()
        return await update.message.reply_text("❌ فروشنده دیگر شهر کافی ندارد. معامله لغو شد.")

    if buyer_data["money"] < offer["price"]:
        return await update.message.reply_text("❌ بودجه کافی ندارید.")

    buyer_data["money"] -= offer["price"]
    seller_data["money"] += offer["price"]
    seller_data["cities"] -= offer["cities"]
    buyer_data["cities"] = buyer_data.get("cities", 0) + offer["cities"]

    del group_db["market"][seller_id]
    save_db()

    await update.message.reply_text(
        f"🏙 معامله تکمیل شد! *{offer['cities']}* شهر جدید به کشور شما افزوده شد.",
        parse_mode='Markdown'
    )
    await check_bankruptcy(update, group_db, seller_id)

# ==================== کارخانه‌ها ====================

async def buy_factory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)

    if user_id not in group_db["users"]:
        return await update.message.reply_text("❌ کشوری ندارید!")

    amount = 1
    if context.args and context.args[0].isdigit():
        amount = int(context.args[0])
    if amount <= 0:
        return await update.message.reply_text("❌ تعداد نامعتبر.")

    user_data = group_db["users"][user_id]
    current = user_data.get("factories", 0)

    total_cost = sum(int(1300 * (1 + (current + i) * 0.10)) for i in range(amount))

    if user_data["money"] < total_cost:
        return await update.message.reply_text(
            f"❌ بودجه کافی نیست! خرید {amount} کارخانه نیازمند {total_cost} سکه است."
        )

    user_data["money"] -= total_cost
    user_data["factories"] = current + amount
    process_factories(user_data)
    save_db()

    await update.message.reply_text(
        f"🏭 *{amount}* کارخانه جدید ساخته شد! (هزینه کل: {total_cost} سکه)\n"
        f"هر کارخانه ۱۰ سرباز در ساعت تولید می‌کند.",
        parse_mode='Markdown'
    )

async def sell_factory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)

    if user_id not in group_db["users"]:
        return await update.message.reply_text("❌ کشوری ندارید.")
    if len(context.args) < 3:
        return await update.message.reply_text("❌ فرمت: `/sellfactory [کشور] [تعداد] [قیمت]`", parse_mode='Markdown')

    if not context.args[-1].isdigit() or not context.args[-2].isdigit():
        return await update.message.reply_text("❌ تعداد و قیمت باید عدد صحیح باشند.")

    price = int(context.args[-1])
    amount = int(context.args[-2])
    target_country = " ".join(context.args[:-2])

    if amount <= 0 or price < 0:
        return await update.message.reply_text("❌ مقادیر نامعتبر.")

    target_id = get_user_id_by_country(group_db, target_country)
    if not target_id:
        return await update.message.reply_text("❌ خریدار پیدا نشد.")
    if target_id == user_id:
        return await update.message.reply_text("❌ نمی‌توانید به خودتان بفروشید.")

    if group_db["users"][user_id].get("factories", 0) < amount:
        return await update.message.reply_text("❌ کارخانه کافی ندارید.")

    group_db["factory_market"][user_id] = {"target_id": target_id, "amount": amount, "price": price}
    save_db()

    seller_country = group_db["users"][user_id]["country"]
    await update.message.reply_text(
        f"📜 پیشنهاد فروش *{amount}* کارخانه به قیمت *{price}* سکه به *{target_country}* ارسال شد.\n"
        f"برای تأیید: `/acceptfactory {seller_country}`",
        parse_mode='Markdown'
    )

async def accept_factory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    buyer_id = str(update.message.from_user.id)

    if buyer_id not in group_db["users"]:
        return await update.message.reply_text("❌ کشوری ندارید.")
    if not context.args:
        return await update.message.reply_text("❌ فرمت: `/acceptfactory [نام فروشنده]`", parse_mode='Markdown')

    seller_country = " ".join(context.args)
    seller_id = get_user_id_by_country(group_db, seller_country)

    if not seller_id or seller_id not in group_db["factory_market"]:
        return await update.message.reply_text("❌ پیشنهادی از این کشور یافت نشد.")

    offer = group_db["factory_market"][seller_id]
    if offer["target_id"] != buyer_id:
        return await update.message.reply_text("❌ این پیشنهاد برای شما نیست.")

    buyer_data = group_db["users"][buyer_id]
    seller_data = group_db["users"][seller_id]

    if seller_data.get("factories", 0) < offer["amount"]:
        del group_db["factory_market"][seller_id]
        save_db()
        return await update.message.reply_text("❌ فروشنده دیگر کارخانه کافی ندارد. معامله لغو شد.")

    if buyer_data["money"] < offer["price"]:
        return await update.message.reply_text("❌ بودجه کافی ندارید.")

    process_factories(buyer_data)
    process_factories(seller_data)

    buyer_data["money"] -= offer["price"]
    seller_data["money"] += offer["price"]
    seller_data["factories"] -= offer["amount"]
    buyer_data["factories"] = buyer_data.get("factories", 0) + offer["amount"]

    del group_db["factory_market"][seller_id]
    save_db()

    await update.message.reply_text(
        f"🏭 معامله تکمیل شد! *{offer['amount']}* کارخانه منتقل گردید.",
        parse_mode='Markdown'
    )

async def send_factory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)

    if user_id not in group_db["users"]:
        return await update.message.reply_text("❌ کشوری ندارید.")
    if len(context.args) < 2:
        return await update.message.reply_text("❌ فرمت: `/sendfactory [کشور] [تعداد]`", parse_mode='Markdown')
    if not context.args[-1].isdigit():
        return await update.message.reply_text("❌ تعداد باید عدد صحیح باشد.")

    amount = int(context.args[-1])
    target_country = " ".join(context.args[:-1])

    if amount <= 0:
        return await update.message.reply_text("❌ تعداد نامعتبر.")

    target_id = get_user_id_by_country(group_db, target_country)
    if not target_id:
        return await update.message.reply_text("❌ کشور مقصد پیدا نشد.")
    if target_id == user_id:
        return await update.message.reply_text("❌ نمی‌توانید به خودتان کارخانه بفرستید.")

    user_data = group_db["users"][user_id]
    if user_data.get("factories", 0) < amount:
        return await update.message.reply_text("❌ کارخانه کافی ندارید.")

    process_factories(user_data)
    process_factories(group_db["users"][target_id])

    user_data["factories"] -= amount
    group_db["users"][target_id]["factories"] = group_db["users"][target_id].get("factories", 0) + amount
    save_db()

    await update.message.reply_text(
        f"🏭 *{amount}* کارخانه به *{target_country}* واگذار شد.",
        parse_mode='Markdown'
    )

# ==================== دیپلماسی ====================

async def ally(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)

    if user_id not in group_db["users"]:
        return await update.message.reply_text("❌ کشوری ندارید.")
    if not context.args:
        return await update.message.reply_text("❌ فرمت: `/ally [نام کشور]`", parse_mode='Markdown')

    target_country = " ".join(context.args)
    target_id = get_user_id_by_country(group_db, target_country)

    if not target_id:
        return await update.message.reply_text("❌ کشور پیدا نشد.")
    if target_id == user_id:
        return await update.message.reply_text("❌ نمی‌توانید با خودتان متحد شوید.")
    if is_allied(group_db, user_id, target_id):
        return await update.message.reply_text("❌ شما قبلاً با این کشور متحد هستید!")

    # ایجاد ساختار درخواست در صورت نبود
    if target_id not in group_db["requests"]:
        group_db["requests"][target_id] = {"ally": []}
    if "ally" not in group_db["requests"][target_id]:
        group_db["requests"][target_id]["ally"] = []

    if user_id in group_db["requests"][target_id]["ally"]:
        return await update.message.reply_text("❌ شما قبلاً درخواست اتحاد فرستاده‌اید.")

    group_db["requests"][target_id]["ally"].append(user_id)
    save_db()

    my_country = group_db["users"][user_id]["country"]
    await update.message.reply_text(
        f"✉️ درخواست اتحاد به *{target_country}* ارسال شد.\n"
        f"برای پذیرش: `/accept {my_country}`",
        parse_mode='Markdown'
    )

async def accept_ally(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)

    if user_id not in group_db["users"]:
        return await update.message.reply_text("❌ کشوری ندارید.")
    if not context.args:
        return await update.message.reply_text("❌ فرمت: `/accept [نام کشور]`", parse_mode='Markdown')

    target_country = " ".join(context.args)
    requester_id = get_user_id_by_country(group_db, target_country)

    # بررسی وجود درخواست (FIX: کد قدیمی بدون بررسی کلید KeyError می‌داد)
    requests = group_db["requests"].get(user_id, {})
    ally_requests = requests.get("ally", [])

    if not requester_id or requester_id not in ally_requests:
        return await update.message.reply_text("❌ هیچ درخواست اتحادی از این کشور یافت نشد.")

    group_db["requests"][user_id]["ally"].remove(requester_id)
    group_db["alliances"].append([user_id, requester_id])
    save_db()

    await update.message.reply_text(
        f"🤝 پیمان اتحاد با *{target_country}* بسته شد!",
        parse_mode='Markdown'
    )

async def break_ally(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)

    if user_id not in group_db["users"]:
        return await update.message.reply_text("❌ کشوری ندارید.")
    if not context.args:
        return await update.message.reply_text("❌ فرمت: `/breakally [نام کشور]`", parse_mode='Markdown')

    target_country = " ".join(context.args)
    target_id = get_user_id_by_country(group_db, target_country)

    if not target_id or not is_allied(group_db, user_id, target_id):
        return await update.message.reply_text("❌ شما با این کشور متحد نیستید.")

    group_db["alliances"] = [
        a for a in group_db["alliances"]
        if not (user_id in a and target_id in a)
    ]
    save_db()

    my_country = group_db["users"][user_id]["country"]
    await update.message.reply_text(
        f"💔 پیمان اتحاد بین *{my_country}* و *{target_country}* شکسته شد.",
        parse_mode='Markdown'
    )

# ==================== جنگ ====================

async def attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    سیستم جنگ بهبود‌یافته:
    - ارتش بزرگتر احتمال برد بالاتری دارد (اثرگذاری ۵۰٪ شانس و ۵۰٪ نظامی)
    - پیروزی با رسیدن به ۵ امتیاز (مانند تنیس، نیاز به ۲ امتیاز اختلاف در صورت تساوی ۴-۴)
    - هر دو طرف سربازانی را در جنگ از دست می‌دهند
    """
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)

    if user_id not in group_db["users"]:
        return await update.message.reply_text("❌ کشوری ندارید.")
    if len(context.args) < 2:
        return await update.message.reply_text(
            "❌ فرمت: `/attack [نام کشور] [تعداد شهر شرط‌بندی]`",
            parse_mode='Markdown'
        )

    bet_str = context.args[-1]
    target_country = " ".join(context.args[:-1])

    if not bet_str.isdigit() or int(bet_str) <= 0:
        return await update.message.reply_text("❌ تعداد شهر شرط‌بندی نامعتبر است.")

    bet = int(bet_str)
    target_id = get_user_id_by_country(group_db, target_country)

    if not target_id:
        return await update.message.reply_text("❌ کشور هدف پیدا نشد.")
    if target_id == user_id:
        return await update.message.reply_text("❌ نمی‌توانید به خودتان حمله کنید!")

    attacker = group_db["users"][user_id]
    defender = group_db["users"][target_id]

    process_factories(attacker)
    process_factories(defender)

    if attacker.get("cities", 0) < bet:
        return await update.message.reply_text(f"❌ شما {bet} شهر برای شرط‌بندی ندارید!")
    if defender.get("cities", 0) < bet:
        return await update.message.reply_text(f"❌ کشور هدف {bet} شهر برای باختن ندارد!")
    if attacker.get("army", 0) <= 0:
        return await update.message.reply_text("❌ شما ارتشی برای جنگ ندارید!")

    # محاسبه احتمال برد هر راند بر اساس نسبت ارتش
    atk_army = attacker.get("army", 1)
    def_army = defender.get("army", 1)
    total_army = atk_army + def_army
    # ۵۰٪ شانس خالص + ۵۰٪ وزن ارتش
    atk_win_prob = 0.5 * (atk_army / total_army) + 0.25

    # سیستم امتیازدهی: اول به ۵ برسد برنده است؛ اگر ۴-۴ شد باید ۲ امتیاز اختلاف بگیرد
    WIN_TARGET = 5
    score_a, score_d = 0, 0
    rounds = 0

    while True:
        rounds += 1
        if rounds > 200:  # جلوگیری از حلقه بی‌نهایت در موارد استثنایی
            break

        if random.random() < atk_win_prob:
            score_a += 1
        else:
            score_d += 1

        # شرط پیروزی: رسیدن به WIN_TARGET با حداقل ۲ امتیاز اختلاف
        if score_a >= WIN_TARGET or score_d >= WIN_TARGET:
            if abs(score_a - score_d) >= 2:
                break

    # تلفات ارتش (هر دو طرف متناسب با تعداد راندها ضرر می‌کنند)
    casualty_rate = min(0.05 * rounds, 0.60)  # حداکثر ۶۰٪ تلفات
    atk_losses = int(atk_army * casualty_rate * random.uniform(0.5, 1.0))
    def_losses = int(def_army * casualty_rate * random.uniform(0.5, 1.0))
    attacker["army"] = max(0, atk_army - atk_losses)
    defender["army"] = max(0, def_army - def_losses)

    log = (
        f"⚔️ *جنگ: {attacker['country']} vs {target_country}*\n"
        f"🎯 شرط: *{bet} شهر*\n"
        f"🪖 ارتش مهاجم: {atk_army:,} | مدافع: {def_army:,}\n"
        f"📊 نتیجه: مهاجم {score_a} — {score_d} مدافع\n"
        f"💀 تلفات: مهاجم -{atk_losses:,} | مدافع -{def_losses:,}\n\n"
    )

    attacker_won = score_a > score_d
    if attacker_won:
        attacker["cities"] += bet
        defender["cities"] -= bet
        log += f"🏆 *{attacker['country']}* پیروز شد و {bet} شهر را فتح کرد!"
    else:
        defender["cities"] += bet
        attacker["cities"] -= bet
        log += f"🛡 *{target_country}* پیروز شد و {bet} شهر از مهاجم گرفت!"

    save_db()
    await update.message.reply_text(log, parse_mode='Markdown')

    if attacker_won:
        await check_bankruptcy(update, group_db, target_id)
    else:
        await check_bankruptcy(update, group_db, user_id)

# ==================== Vote Kick و ادمین ====================

async def votekick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)

    if user_id not in group_db["users"]:
        return await update.message.reply_text("❌ شما در بازی نیستید و نمی‌توانید رای دهید.")
    if not context.args:
        return await update.message.reply_text("❌ فرمت: `/votekick [نام کشور]`", parse_mode='Markdown')

    target_country = " ".join(context.args)
    target_id = get_user_id_by_country(group_db, target_country)

    if not target_id:
        return await update.message.reply_text("❌ کشور پیدا نشد.")
    if target_id == user_id:
        return await update.message.reply_text("❌ نمی‌توانید به خودتان رای دهید!")

    group_db["votes"].setdefault(target_id, [])

    if user_id in group_db["votes"][target_id]:
        return await update.message.reply_text("❌ شما قبلاً رای داده‌اید.")

    group_db["votes"][target_id].append(user_id)
    save_db()

    total_players = len(group_db["users"])
    required = max(3, (total_players // 2) + 1)
    current = len(group_db["votes"][target_id])

    if current < required:
        await update.message.reply_text(
            f"🚷 یک رای برای اخراج *{target_country}* ثبت شد.\n"
            f"(آرای فعلی: {current} / حد نصاب: {required})",
            parse_mode='Markdown'
        )
        return

    # FIX: پیام اخراج را قبل از check_bankruptcy بفرست، و kicked=True بده تا پیام تکراری نباشد
    await update.message.reply_text(
        f"⛔️ رأی‌گیری به حد نصاب رسید!\n"
        f"کشور *{target_country}* به دلیل تخلف از بازی اخراج شد.",
        parse_mode='Markdown'
    )
    group_db["users"][target_id]["cities"] = 0
    await check_bankruptcy(update, group_db, target_id, kicked=True)

async def admin_wipe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    if user_id != ADMIN_ID:
        return await update.message.reply_text("❌ دسترسی ادمین لازم است.")

    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)

    if not context.args:
        return await update.message.reply_text("❌ فرمت: `/adminwipe [نام کشور]`", parse_mode='Markdown')

    target_country = " ".join(context.args)
    target_id = get_user_id_by_country(group_db, target_country)

    if not target_id:
        return await update.message.reply_text("❌ کشور پیدا نشد.")

    await update.message.reply_text(
        f"⚡️ *ادمین وارد عمل شد!*\n"
        f"کشور *{target_country}* به دلیل تخلف فوراً از نقشه حذف شد.",
        parse_mode='Markdown'
    )
    group_db["users"][target_id]["cities"] = 0
    await check_bankruptcy(update, group_db, target_id, kicked=True)

# ==================== اجرا ====================

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start",         start))
    app.add_handler(CommandHandler("help",          help_command))
    app.add_handler(CommandHandler("claim",         claim))
    app.add_handler(CommandHandler("rename",        rename_country))
    app.add_handler(CommandHandler("color",         set_color))
    app.add_handler(CommandHandler("profile",       profile))
    app.add_handler(CommandHandler("world",         world))
    app.add_handler(CommandHandler("tax",           tax))
    app.add_handler(CommandHandler("military",      military))
    app.add_handler(CommandHandler("buyfactory",    buy_factory))
    app.add_handler(CommandHandler("sellfactory",   sell_factory))
    app.add_handler(CommandHandler("acceptfactory", accept_factory))
    app.add_handler(CommandHandler("sendfactory",   send_factory))
    app.add_handler(CommandHandler("send",          send_money))
    app.add_handler(CommandHandler("sendcity",      send_city))
    app.add_handler(CommandHandler("sellcity",      sell_city))
    app.add_handler(CommandHandler("acceptcity",    accept_city))
    app.add_handler(CommandHandler("attack",        attack))
    app.add_handler(CommandHandler("ally",          ally))
    app.add_handler(CommandHandler("accept",        accept_ally))
    app.add_handler(CommandHandler("breakally",     break_ally))
    app.add_handler(CommandHandler("votekick",      votekick))
    app.add_handler(CommandHandler("adminwipe",     admin_wipe))

    print("✅ ربات ژئوپلیتیک راه‌اندازی شد...")
    app.run_polling()