import json
import os
import logging
from datetime import datetime, timedelta
from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- تنظیمات اولیه ---
BOT_TOKEN = "xxxxxxx" # توکن ربات خود را اینجا بگذارید
DATA_FILE = "rp_data.json"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- سیستم دیتابیس (تفکیک شده بر اساس گروه) ---
# ساختار جدید: db[chat_id] = {"users": {}, "countries": {}, "alliances": [], "wars": [], "requests": {}, "market": {}}

def load_db():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_db():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=4)

db = load_db()

# --- توابع کمکی ---
def get_group_db(chat_id):
    chat_id = str(chat_id)
    if chat_id not in db:
        db[chat_id] = {
            "users": {},
            "countries": {},
            "alliances": [],
            "wars": [],
            "requests": {},
            "market": {} # برای فروش شهرها: seller_id -> {"target_id": id, "cities": count, "price": price}
        }
    return db[chat_id]

def get_user_id_by_country(group_db, country_name):
    for c, uid in group_db["countries"].items():
        if c.lower() == country_name.lower():
            return uid
    return None

def get_country_by_user_id(group_db, user_id):
    user_id = str(user_id)
    if user_id in group_db["users"]:
        return group_db["users"][user_id]["country"]
    return None

def is_allied(group_db, uid1, uid2):
    return [uid1, uid2] in group_db["alliances"] or [uid2, uid1] in group_db["alliances"]

def is_at_war(group_db, uid1, uid2):
    return [uid1, uid2] in group_db["wars"] or [uid2, uid1] in group_db["wars"]

async def check_bankruptcy(update, group_db, user_id):
    """بررسی ورشکستگی در صورت از دست دادن تمام شهرها"""
    user_id = str(user_id)
    if user_id in group_db["users"] and group_db["users"][user_id]["cities"] <= 0:
        country_name = group_db["users"][user_id]["country"]
        
        # حذف اطلاعات کاربر از همه جا
        del group_db["users"][user_id]
        if country_name in group_db["countries"]:
            del group_db["countries"][country_name]
            
        group_db["alliances"] = [a for a in group_db["alliances"] if user_id not in a]
        group_db["wars"] = [w for w in group_db["wars"] if user_id not in w]
        
        if user_id in group_db["requests"]:
            del group_db["requests"][user_id]
        
        save_db()
        await update.message.reply_text(f"💀 **سقوط یک امپراتوری!**\nکشور **{country_name}** تمام شهرهای خود را از دست داد و به طور کامل از نقشه جهان محو شد!", parse_mode='Markdown')
        return True
    return False

# --- تنظیم منوی کامندها ---
async def post_init(application):
    commands = [
        BotCommand("claim", "تصاحب و رهبری یک کشور"),
        BotCommand("profile", "مشاهده پروفایل (یا پروفایل دیگران با منشن)"),
        BotCommand("world", "مشاهده نقشه سیاسی جهان"),
        BotCommand("tax", "جمع‌آوری مالیات (هر ۳۰ دقیقه)"),
        BotCommand("military", "خرید نیروی نظامی"),
        BotCommand("rename", "تغییر نام کشور"),
        BotCommand("color", "تغییر رنگ/ایموجی کشور در نقشه"),
        BotCommand("send", "ارسال سکه به کشور دیگر"),
        BotCommand("sendcity", "انتقال رایگان شهر به کشور دیگر"),
        BotCommand("sellcity", "فروش شهر با قیمت دلخواه"),
        BotCommand("acceptcity", "تایید خرید شهر"),
        BotCommand("ally", "پیشنهاد اتحاد"),
        BotCommand("accept", "پذیرش اتحاد"),
        BotCommand("war", "اعلان جنگ"),
        BotCommand("peace", "پیشنهاد صلح"),
        BotCommand("acceptpeace", "پذیرش صلح"),
        BotCommand("help", "لیست کامل راهنما")
    ]
    await application.bot.set_my_commands(commands)

# --- دستورات ربات ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🌍 *به ربات مدیریت رول‌پلی ژئوپلیتیک خوش آمدید!*\n\n"
        "برای شروع در این گروه، یک کشور را با دستور زیر انتخاب کنید:\n"
        "`/claim [نام کشور]`\n\n"
        "برای دیدن راهنما `/help` را بزنید."
    )
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📜 *راهنمای کامل دستورات:*\n\n"
        "🌍 `/claim [نام]` - تاسیس کشور\n"
        "👤 `/profile` یا `/profile @user` - وضعیت کشور\n"
        "🗺 `/world` - نقشه جهان\n"
        "🔄 `/rename [نام جدید]` - تغییر نام کشور\n"
        "🎨 `/color [ایموجی]` - تعیین رنگ کشور در نقشه\n\n"
        "💰 `/tax` - مالیات (هر شهر ۷۰ سکه در نیم ساعت)\n"
        "🪖 `/military [تعداد]` - خرید ارتش (هر نیرو ۱۰ سکه)\n"
        "💸 `/send [کشور] [مبلغ]` - کمک مالی\n\n"
        "🏙 `/sendcity [کشور] [تعداد]` - واگذاری شهر\n"
        "🤝 `/sellcity [کشور] [تعداد] [مبلغ]` - پیشنهاد فروش شهر\n"
        "✅ `/acceptcity [کشور فروشنده]` - خرید شهر پیشنهاد شده\n\n"
        "🤝 `/ally [کشور]` | ✅ `/accept [کشور]` - دیپلماسی\n"
        "⚔️ `/war [کشور]` - اعلان جنگ\n"
        "🕊 `/peace [کشور]` | ✅ `/acceptpeace [کشور]` - صلح"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)
    user_name = update.message.from_user.first_name
    username = update.message.from_user.username

    if len(context.args) == 0:
        return await update.message.reply_text("❌ لطفاً نام کشور را وارد کنید. مثال: `/claim Iran`")

    country_name = " ".join(context.args)

    if user_id in group_db["users"]:
        current_country = group_db["users"][user_id]["country"]
        return await update.message.reply_text(f"❌ شما در این گروه رهبر **{current_country}** هستید!", parse_mode='Markdown')

    for existing_country in group_db["countries"]:
        if existing_country.lower() == country_name.lower():
            return await update.message.reply_text(f"❌ کشور **{existing_country}** قبلاً انتخاب شده است.", parse_mode='Markdown')

    group_db["users"][user_id] = {
        "name": user_name,
        "username": username.lower() if username else "",
        "country": country_name,
        "color": "⚪️", # رنگ پیش‌فرض
        "money": 5000,
        "army": 100,
        "cities": 21, # تعداد شهرهای اولیه
        "last_tax": "2000-01-01T00:00:00"
    }
    group_db["countries"][country_name] = user_id
    save_db()

    await update.message.reply_text(
        f"🎉 تبریک! شما رهبری **{country_name}** را بر عهده گرفتید.\n\n"
        f"🏙 شهرها: 21\n💰 بودجه: 5000\n🪖 ارتش: 100", parse_mode='Markdown'
    )

async def rename_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)

    if user_id not in group_db["users"]:
        return await update.message.reply_text("❌ شما کشوری ندارید.")
    if len(context.args) == 0:
        return await update.message.reply_text("❌ نام جدید را وارد کنید: `/rename NewName`")

    new_name = " ".join(context.args)
    old_name = group_db["users"][user_id]["country"]

    for existing_country in group_db["countries"]:
        if existing_country.lower() == new_name.lower():
            return await update.message.reply_text("❌ این نام قبلاً ثبت شده است.")

    del group_db["countries"][old_name]
    group_db["countries"][new_name] = user_id
    group_db["users"][user_id]["country"] = new_name
    save_db()

    await update.message.reply_text(f"🔄 نام کشور شما از **{old_name}** به **{new_name}** تغییر یافت.", parse_mode='Markdown')

async def set_color(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)

    if user_id not in group_db["users"]:
        return await update.message.reply_text("❌ کشوری ندارید.")
    if len(context.args) == 0:
        return await update.message.reply_text("❌ یک ایموجی یا رنگ وارد کنید. مثال: `/color 🔴`")

    color = context.args[0]
    group_db["users"][user_id]["color"] = color
    save_db()
    await update.message.reply_text(f"🎨 رنگ کشور شما در نقشه به {color} تغییر یافت.")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)
    target_id = user_id

    # بررسی منشن
    if len(context.args) > 0 and context.args[0].startswith('@'):
        target_username = context.args[0].replace('@', '').lower()
        found = False
        for uid, data in group_db["users"].items():
            if data.get("username", "") == target_username:
                target_id = uid
                found = True
                break
        if not found:
            return await update.message.reply_text("❌ کاربری با این آیدی در سیستم ثبت نشده است.")
    
    if target_id not in group_db["users"]:
        if target_id == user_id:
            return await update.message.reply_text("❌ شما کشوری ندارید! `/claim` کنید.")
        else:
            return await update.message.reply_text("❌ این کاربر کشوری ندارد.")

    user_data = group_db["users"][target_id]
    country = user_data["country"]
    color = user_data.get("color", "⚪️")
    
    allies = []
    enemies = []
    for pair in group_db["alliances"]:
        if target_id in pair:
            other_id = pair[0] if pair[1] == target_id else pair[1]
            allies.append(get_country_by_user_id(group_db, other_id))
            
    for pair in group_db["wars"]:
        if target_id in pair:
            other_id = pair[0] if pair[1] == target_id else pair[1]
            enemies.append(get_country_by_user_id(group_db, other_id))

    profile_text = (
        f"🏛 **دولت {country}** {color}\n"
        f"👤 رهبر: {user_data['name']}\n\n"
        f"🏙 تعداد شهرها: {user_data.get('cities', 21)}\n"
        f"💰 خزانه: {user_data['money']} سکه\n"
        f"🪖 ارتش: {user_data['army']} سرباز\n\n"
        f"🤝 متحدین: {('، '.join(allies)) if allies else 'ندارد'}\n"
        f"⚔️ در جنگ با: {('، '.join(enemies)) if enemies else 'ندارد'}"
    )
    await update.message.reply_text(profile_text, parse_mode='Markdown')

async def world(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)

    if not group_db["countries"]:
        return await update.message.reply_text("🌍 جهان هنوز خالی از سکنه است!")

    text = "🌍 **نقشه سیاسی جهان:**\n\n"
    for country, uid in group_db["countries"].items():
        user = group_db["users"][uid]
        color = user.get("color", "⚪️")
        text += f"{color} **{country}** | 🏙 {user.get('cities', 21)} | 🪖 {user['army']}\n"

    # اضافه کردن بخش جنگ‌ها و اتحادها به پایین نقشه
    if group_db["wars"]:
        text += "\n⚔️ **جنگ‌های فعال:**\n"
        for w in group_db["wars"]:
            c1 = get_country_by_user_id(group_db, w[0])
            c2 = get_country_by_user_id(group_db, w[1])
            text += f"▪️ {c1} ⚔️ {c2}\n"
            
    if group_db["alliances"]:
        text += "\n🤝 **اتحادهای بزرگ:**\n"
        for a in group_db["alliances"]:
            c1 = get_country_by_user_id(group_db, a[0])
            c2 = get_country_by_user_id(group_db, a[1])
            text += f"▪️ {c1} 🤝 {c2}\n"

    await update.message.reply_text(text, parse_mode='Markdown')

async def tax(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)

    if user_id not in group_db["users"]:
        return await update.message.reply_text("❌ شما هنوز کشوری ندارید!")

    user_data = group_db["users"][user_id]
    last_tax = datetime.fromisoformat(user_data["last_tax"])
    now = datetime.now()

    if now < last_tax + timedelta(minutes=30):
        remaining = (last_tax + timedelta(minutes=30)) - now
        minutes, seconds = divmod(int(remaining.total_seconds()), 60)
        return await update.message.reply_text(f"⏳ لطفاً {minutes} دقیقه و {seconds} ثانیه دیگر برای جمع‌آوری مالیات مراجعه کنید.")

    cities = user_data.get("cities", 21)
    tax_amount = cities * 70  # هر شهر 70 سکه
    
    user_data["money"] += tax_amount
    user_data["last_tax"] = now.isoformat()
    save_db()

    await update.message.reply_text(f"💰 مالیات جمع‌آوری شد!\nمبلغ **{tax_amount}** سکه (به ازای {cities} شهر) به خزانه **{user_data['country']}** واریز شد.", parse_mode='Markdown')

# --- بخش شهرسازی و انتقال ---

async def send_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)

    if user_id not in group_db["users"]: return await update.message.reply_text("❌ کشوری ندارید.")
    if len(context.args) < 2: return await update.message.reply_text("❌ فرمت اشتباه. مثال: `/sendcity Italy 3`")

    target_country = " ".join(context.args[:-1])
    amount_str = context.args[-1]

    if not amount_str.isdigit() or int(amount_str) <= 0: return await update.message.reply_text("❌ تعداد شهر نامعتبر است.")
    amount = int(amount_str)
    
    target_id = get_user_id_by_country(group_db, target_country)
    if not target_id: return await update.message.reply_text("❌ کشور پیدا نشد.")
    if target_id == user_id: return await update.message.reply_text("❌ به خودتان؟")

    user_data = group_db["users"][user_id]
    target_data = group_db["users"][target_id]

    if user_data.get("cities", 21) < amount:
        return await update.message.reply_text("❌ شما این تعداد شهر برای واگذاری ندارید!")

    user_data["cities"] -= amount
    target_data["cities"] = target_data.get("cities", 21) + amount
    save_db()

    await update.message.reply_text(f"🏙 تعداد **{amount}** شهر از **{user_data['country']}** به **{target_country}** واگذار شد.", parse_mode='Markdown')
    await check_bankruptcy(update, group_db, user_id)

async def sell_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)

    if user_id not in group_db["users"]: return await update.message.reply_text("❌ کشوری ندارید.")
    if len(context.args) < 3: return await update.message.reply_text("❌ فرمت: `/sellcity [کشور] [تعداد شهر] [قیمت]`")

    price_str = context.args[-1]
    amount_str = context.args[-2]
    target_country = " ".join(context.args[:-2])

    if not (price_str.isdigit() and amount_str.isdigit()): return await update.message.reply_text("❌ قیمت و تعداد باید عدد باشند.")
    
    price = int(price_str)
    amount = int(amount_str)
    target_id = get_user_id_by_country(group_db, target_country)

    if not target_id: return await update.message.reply_text("❌ کشور خریدار پیدا نشد.")
    if group_db["users"][user_id].get("cities", 21) < amount: return await update.message.reply_text("❌ شهر کافی ندارید.")

    group_db["market"][user_id] = {"target_id": target_id, "cities": amount, "price": price}
    save_db()
    
    seller_name = group_db["users"][user_id]["country"]
    await update.message.reply_text(f"📜 قرارداد فروش **{amount}** شهر به قیمت **{price}** سکه برای **{target_country}** ارسال شد.\nکشور خریدار باید با `/acceptcity {seller_name}` آن را تایید کند.", parse_mode='Markdown')

async def accept_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    buyer_id = str(update.message.from_user.id)

    if buyer_id not in group_db["users"]: return await update.message.reply_text("❌ کشوری ندارید.")
    if len(context.args) == 0: return await update.message.reply_text("❌ فرمت: `/acceptcity [نام کشور فروشنده]`")

    seller_country = " ".join(context.args)
    seller_id = get_user_id_by_country(group_db, seller_country)

    if not seller_id or seller_id not in group_db["market"]:
        return await update.message.reply_text("❌ پیشنهاد فروشی از این کشور یافت نشد.")

    offer = group_db["market"][seller_id]
    if offer["target_id"] != buyer_id:
        return await update.message.reply_text("❌ این پیشنهاد برای شما نیست.")

    buyer_data = group_db["users"][buyer_id]
    seller_data = group_db["users"][seller_id]

    if buyer_data["money"] < offer["price"]:
        return await update.message.reply_text("❌ بودجه کافی برای خرید ندارید.")

    # انتقال
    buyer_data["money"] -= offer["price"]
    seller_data["money"] += offer["price"]
    seller_data["cities"] -= offer["cities"]
    buyer_data["cities"] = buyer_data.get("cities", 21) + offer["cities"]
    
    del group_db["market"][seller_id]
    save_db()

    await update.message.reply_text(f"🏙 معامله انجام شد! **{offer['cities']}** شهر به نقشه **{buyer_data['country']}** اضافه شد و {offer['price']} سکه پرداخت شد.", parse_mode='Markdown')
    await check_bankruptcy(update, group_db, seller_id)

# --- دستورات قبلی (اصلاح شده برای گروه‌ها) ---

async def military(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)
    
    if user_id not in group_db["users"]: return await update.message.reply_text("❌ کشوری ندارید!")
    if len(context.args) != 1 or not context.args[0].isdigit(): return await update.message.reply_text("❌ فرمت: `/military 50`")

    amount = int(context.args[0])
    cost = amount * 10
    user_data = group_db["users"][user_id]
    
    if user_data["money"] < cost: return await update.message.reply_text(f"❌ بودجه کافی نیست! نیاز: {cost}")

    user_data["money"] -= cost
    user_data["army"] += amount
    save_db()
    await update.message.reply_text(f"🪖 **{amount}** نیروی جدید افزوده شد.\nهزینه: {cost} سکه.", parse_mode='Markdown')

async def send_money(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)
    
    if user_id not in group_db["users"]: return
    if len(context.args) < 2: return await update.message.reply_text("❌ فرمت: `/send Russia 1000`")

    target_country = " ".join(context.args[:-1])
    amount_str = context.args[-1]

    if not amount_str.isdigit(): return await update.message.reply_text("❌ مبلغ باید عدد باشد.")
    amount = int(amount_str)
    target_id = get_user_id_by_country(group_db, target_country)

    if not target_id: return await update.message.reply_text(f"❌ کشوری یافت نشد.")
    if target_id == user_id: return await update.message.reply_text("❌ به خودتان؟")

    user_data = group_db["users"][user_id]
    if user_data["money"] < amount: return await update.message.reply_text("❌ خزانه کافی نیست!")

    user_data["money"] -= amount
    group_db["users"][target_id]["money"] += amount
    save_db()
    await update.message.reply_text(f"💸 مبلغ **{amount}** سکه به **{target_country}** منتقل شد.", parse_mode='Markdown')

async def war(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)
    
    if user_id not in group_db["users"]: return
    if len(context.args) == 0: return await update.message.reply_text("❌ مثال: `/war Germany`")
    
    target_country = " ".join(context.args)
    target_id = get_user_id_by_country(group_db, target_country)

    if not target_id: return await update.message.reply_text("❌ کشور پیدا نشد.")
    if target_id == user_id: return
    if is_at_war(group_db, user_id, target_id): return await update.message.reply_text("❌ در حال جنگ هستید!")
    
    if is_allied(group_db, user_id, target_id):
        group_db["alliances"] = [a for a in group_db["alliances"] if set(a) != {user_id, target_id}]

    group_db["wars"].append([user_id, target_id])
    save_db()
    await update.message.reply_text(f"🚨 **اعلان جنگ!**\nکشور **{group_db['users'][user_id]['country']}** به **{target_country}** اعلان جنگ داد!", parse_mode='Markdown')

async def ally(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)
    
    if user_id not in group_db["users"]: return
    if len(context.args) == 0: return await update.message.reply_text("❌ مثال: `/ally Italy`")
    
    target_country = " ".join(context.args)
    target_id = get_user_id_by_country(group_db, target_country)

    if not target_id: return await update.message.reply_text("❌ کشور پیدا نشد.")
    if target_id == user_id: return
    if is_allied(group_db, user_id, target_id): return await update.message.reply_text("❌ متحد هستید!")
    if is_at_war(group_db, user_id, target_id): return await update.message.reply_text("❌ در حال جنگ هستید!")

    if target_id not in group_db["requests"]: group_db["requests"][target_id] = {"ally": [], "peace": []}
    if user_id not in group_db["requests"][target_id]["ally"]:
        group_db["requests"][target_id]["ally"].append(user_id)
        save_db()

    my_country = group_db["users"][user_id]["country"]
    await update.message.reply_text(f"✉️ درخواست اتحاد برای **{target_country}** ارسال شد. (پذیرش با `/accept {my_country}`)", parse_mode='Markdown')

async def accept_ally(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)
    
    if user_id not in group_db["users"] or len(context.args) == 0: return
    
    target_country = " ".join(context.args)
    requester_id = get_user_id_by_country(group_db, target_country)

    if user_id in group_db["requests"] and requester_id in group_db["requests"][user_id]["ally"]:
        group_db["requests"][user_id]["ally"].remove(requester_id)
        group_db["alliances"].append([user_id, requester_id])
        save_db()
        await update.message.reply_text(f"🤝 پیمان اتحاد با **{target_country}** بسته شد.", parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ هیچ پیشنهاد اتحادی یافت نشد.")

async def peace(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)
    
    if user_id not in group_db["users"] or len(context.args) == 0: return
    
    target_country = " ".join(context.args)
    target_id = get_user_id_by_country(group_db, target_country)

    if not target_id or not is_at_war(group_db, user_id, target_id): return await update.message.reply_text("❌ با این کشور در جنگ نیستید.")

    if target_id not in group_db["requests"]: group_db["requests"][target_id] = {"ally": [], "peace": []}
    if user_id not in group_db["requests"][target_id]["peace"]:
        group_db["requests"][target_id]["peace"].append(user_id)
        save_db()

    my_country = group_db["users"][user_id]["country"]
    await update.message.reply_text(f"🕊 درخواست صلح به **{target_country}** ارسال شد. (پذیرش با `/acceptpeace {my_country}`)", parse_mode='Markdown')

async def accept_peace(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)
    
    if user_id not in group_db["users"] or len(context.args) == 0: return
    
    target_country = " ".join(context.args)
    requester_id = get_user_id_by_country(group_db, target_country)

    if user_id in group_db["requests"] and requester_id in group_db["requests"][user_id]["peace"]:
        group_db["requests"][user_id]["peace"].remove(requester_id)
        group_db["wars"] = [w for w in group_db["wars"] if set(w) != {user_id, requester_id}]
        save_db()
        await update.message.reply_text(f"🕊 جنگ با **{target_country}** به پایان رسید.", parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ پیشنهادی یافت نشد.")

# --- اجرای ربات ---
if __name__ == '__main__':
    if BOT_TOKEN == "توکن_ربات_خود_را_اینجا_قرار_دهید" or len(BOT_TOKEN) < 30:
        print("❌ لطفاً ابتدا BOT_TOKEN را در داخل فایل ویرایش کنید!")
        exit()

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    # ثبت دستورات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("claim", claim))
    app.add_handler(CommandHandler("rename", rename_country))
    app.add_handler(CommandHandler("color", set_color))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("world", world))
    app.add_handler(CommandHandler("tax", tax))
    app.add_handler(CommandHandler("military", military))
    app.add_handler(CommandHandler("send", send_money))
    app.add_handler(CommandHandler("sendcity", send_city))
    app.add_handler(CommandHandler("sellcity", sell_city))
    app.add_handler(CommandHandler("acceptcity", accept_city))
    app.add_handler(CommandHandler("war", war))
    app.add_handler(CommandHandler("ally", ally))
    app.add_handler(CommandHandler("accept", accept_ally))
    app.add_handler(CommandHandler("peace", peace))
    app.add_handler(CommandHandler("acceptpeace", accept_peace))

    print("✅ ربات ژئوپلیتیک روشن شد...")
    app.run_polling()