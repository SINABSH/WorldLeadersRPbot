import json
import os
import logging
import random
from datetime import datetime, timedelta
from telegram import Update, BotCommand
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- تنظیمات اولیه ---
BOT_TOKEN = "xxxxxxx" # توکن ربات
DATA_FILE = "rp_data.json"
ADMIN_ID = "xxxxxxx" # آیدی عددی ادمین اصلی 
MAX_COUNTRY_NAME_LEN = 20 # حداکثر طول مجاز برای نام کشور

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- سیستم دیتابیس ---
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
            "requests": {},
            "market": {},
            "factory_market": {},
            "votes": {} # برای ذخیره رای‌گیری‌های اخراج
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

async def check_bankruptcy(update, group_db, user_id):
    """بررسی ورشکستگی در صورت از دست دادن تمام شهرها"""
    user_id = str(user_id)
    if user_id in group_db["users"] and group_db["users"][user_id]["cities"] <= 0:
        country_name = group_db["users"][user_id]["country"]
        
        del group_db["users"][user_id]
        if country_name in group_db["countries"]:
            del group_db["countries"][country_name]
            
        group_db["alliances"] = [a for a in group_db["alliances"] if user_id not in a]
        if user_id in group_db["requests"]:
            del group_db["requests"][user_id]
            
        # پاک کردن آرای مربوط به این شخص
        if user_id in group_db["votes"]:
            del group_db["votes"][user_id]
        
        save_db()
        await update.message.reply_text(f"💀 **سقوط یک امپراتوری!**\nکشور **{country_name}** تمام شهرهای خود را از دست داد و به طور کامل از نقشه جهان محو شد!", parse_mode='Markdown')
        return True
    return False

def process_factories(user_data):
    """تابع تولید خودکار سرباز توسط کارخانه‌ها"""
    if "factories" not in user_data:
        user_data["factories"] = 0
        user_data["last_factory_update"] = datetime.now().isoformat()
        return 0
    
    factories = user_data["factories"]
    if factories > 0:
        last_update = datetime.fromisoformat(user_data["last_factory_update"])
        now = datetime.now()
        hours_passed = (now - last_update).total_seconds() / 3600.0
        
        if hours_passed >= 1:
            whole_hours = int(hours_passed)
            produced_soldiers = whole_hours * factories * 10
            user_data["army"] = user_data.get("army", 0) + produced_soldiers
            user_data["last_factory_update"] = (last_update + timedelta(hours=whole_hours)).isoformat()
            return produced_soldiers
    return 0

# --- تنظیم منوی کامندها ---
async def post_init(application):
    commands = [
        BotCommand("claim", "تصاحب یک کشور"),
        BotCommand("profile", "مشاهده وضعیت کشور"),
        BotCommand("world", "نقشه سیاسی جهان"),
        BotCommand("tax", "جمع‌آوری مالیات (هر ۳۰ دقیقه)"),
        BotCommand("military", "خرید نیروی نظامی"),
        BotCommand("buyfactory", "خرید کارخانه ارتش‌سازی"),
        BotCommand("rename", "تغییر نام کشور"),
        BotCommand("color", "تغییر رنگ/ایموجی کشور"),
        BotCommand("send", "ارسال سکه"),
        BotCommand("sendcity", "واگذاری شهر"),
        BotCommand("sellcity", "فروش شهر"),
        BotCommand("acceptcity", "تایید خرید شهر"),
        BotCommand("sendfactory", "واگذاری کارخانه"),
        BotCommand("sellfactory", "فروش کارخانه"),
        BotCommand("acceptfactory", "تایید خرید کارخانه"),
        BotCommand("attack", "حمله و شرط‌بندی روی شهرها"),
        BotCommand("ally", "پیشنهاد اتحاد"),
        BotCommand("accept", "پذیرش اتحاد"),
        BotCommand("votekick", "رای به اخراج یک کشور"),
        BotCommand("help", "راهنما")
    ]
    await application.bot.set_my_commands(commands)

# --- دستورات اصلی و پایه ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🌍 *به ربات مدیریت رول‌پلی ژئوپلیتیک خوش آمدید!*\n\n"
        "برای شروع، کشور خود را انتخاب کنید:\n"
        "`/claim [نام کشور]`\n\n"
        "برای دیدن راهنما `/help` را بزنید."
    )
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📜 *راهنمای دستورات:*\n\n"
        "🌍 `/claim` | 👤 `/profile` | 🗺 `/world` | 🔄 `/rename` | 🎨 `/color`\n"
        "💰 `/tax` - مالیات (۳۰ دقیقه)\n"
        "🪖 `/military [تعداد]` - خرید ارتش مستقیم\n"
        "🏭 `/buyfactory [تعداد]` - خرید کارخانه (ساعتی 10 سرباز خودکار)\n"
        "💸 `/send [کشور] [مبلغ]` - کمک مالی\n\n"
        "🏙 *شهرها:* `/sendcity`, `/sellcity`, `/acceptcity`\n"
        "🏭 *کارخانه‌ها:* `/sendfactory`, `/sellfactory`, `/acceptfactory`\n\n"
        "⚔️ `/attack [کشور] [تعداد شهر]` - حمله و شرط‌بندی روی شهرها\n"
        "🤝 `/ally [کشور]` | ✅ `/accept [کشور]` - دیپلماسی\n"
        "🚷 `/votekick [کشور]` - رای‌گیری برای اخراج یک کشور متخلف"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)
    user_name = update.message.from_user.first_name
    username = update.message.from_user.username

    if len(context.args) == 0: return await update.message.reply_text("❌ لطفاً نام کشور را وارد کنید.")
    country_name = " ".join(context.args)

    if len(country_name) > MAX_COUNTRY_NAME_LEN:
        return await update.message.reply_text(f"❌ نام کشور نمی‌تواند بیشتر از {MAX_COUNTRY_NAME_LEN} کاراکتر باشد.")

    if user_id in group_db["users"]: return await update.message.reply_text("❌ شما در این گروه قبلاً کشوری ساخته‌اید!")
    for existing_country in group_db["countries"]:
        if existing_country.lower() == country_name.lower(): return await update.message.reply_text("❌ این نام تکراری است.")

    group_db["users"][user_id] = {
        "name": user_name,
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
    await update.message.reply_text(f"🎉 تبریک! شما رهبری **{country_name}** را بر عهده گرفتید.", parse_mode='Markdown')

async def rename_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)

    if user_id not in group_db["users"]: return await update.message.reply_text("❌ شما کشوری ندارید.")
    if len(context.args) == 0: return await update.message.reply_text("❌ نام جدید را وارد کنید: `/rename NewName`")

    new_name = " ".join(context.args)
    if len(new_name) > MAX_COUNTRY_NAME_LEN:
        return await update.message.reply_text(f"❌ نام کشور نمی‌تواند بیشتر از {MAX_COUNTRY_NAME_LEN} کاراکتر باشد.")

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

    if user_id not in group_db["users"]: return await update.message.reply_text("❌ کشوری ندارید.")
    if len(context.args) == 0: return await update.message.reply_text("❌ یک ایموجی یا رنگ وارد کنید. مثال: `/color 🔴`")

    color = context.args[0]
    group_db["users"][user_id]["color"] = color
    save_db()
    await update.message.reply_text(f"🎨 رنگ کشور شما در نقشه به {color} تغییر یافت.")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)
    target_id = user_id

    if len(context.args) > 0 and context.args[0].startswith('@'):
        target_username = context.args[0].replace('@', '').lower()
        found = False
        for uid, data in group_db["users"].items():
            if data.get("username", "") == target_username:
                target_id = uid
                found = True; break
        if not found: return await update.message.reply_text("❌ کاربری یافت نشد.")
    
    if target_id not in group_db["users"]: return await update.message.reply_text("❌ کشور پیدا نشد.")

    user_data = group_db["users"][target_id]
    new_soldiers = process_factories(user_data)
    save_db()

    profile_text = (
        f"🏛 **دولت {user_data['country']}** {user_data.get('color', '⚪️')}\n"
        f"👤 رهبر: {user_data['name']}\n\n"
        f"🏙 شهرها: {user_data.get('cities', 21)}\n"
        f"🏭 کارخانه‌ها: {user_data.get('factories', 0)}\n"
        f"💰 خزانه: {user_data['money']} سکه\n"
        f"🪖 ارتش: {user_data['army']} سرباز"
    )
    if new_soldiers > 0:
        profile_text += f"\n\n*(➕ {new_soldiers} سرباز جدید توسط کارخانه‌ها ساخته شد)*"

    await update.message.reply_text(profile_text, parse_mode='Markdown')

async def world(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)

    if not group_db["countries"]: return await update.message.reply_text("🌍 جهان هنوز خالی از سکنه است!")

    text = "🌍 **نقشه سیاسی جهان:**\n\n"
    for country, uid in group_db["countries"].items():
        user = group_db["users"][uid]
        color = user.get("color", "⚪️")
        text += f"{color} **{country}** | 🏙 {user.get('cities', 21)} | 🪖 {user['army']}\n"
            
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

    if user_id not in group_db["users"]: return await update.message.reply_text("❌ هنوز کشوری ندارید!")
    user_data = group_db["users"][user_id]
    
    last_tax = datetime.fromisoformat(user_data["last_tax"])
    now = datetime.now()
    if now < last_tax + timedelta(minutes=30): 
        remaining = (last_tax + timedelta(minutes=30)) - now
        minutes, seconds = divmod(int(remaining.total_seconds()), 60)
        return await update.message.reply_text(f"⏳ لطفاً {minutes} دقیقه و {seconds} ثانیه دیگر مراجعه کنید.")
    
    process_factories(user_data) 
    cities = user_data.get("cities", 21)
    tax_amount = cities * 70
    user_data["money"] += tax_amount
    user_data["last_tax"] = now.isoformat()
    save_db()
    await update.message.reply_text(f"💰 مالیات جمع‌آوری شد! مبلغ **{tax_amount}** سکه (به ازای {cities} شهر) واریز شد.", parse_mode='Markdown')

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

    amount_str = context.args[-1]
    target_country = " ".join(context.args[:-1])

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

# --- بخش شهرها و کارخانه‌ها ---

async def send_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)

    if user_id not in group_db["users"]: return await update.message.reply_text("❌ کشوری ندارید.")
    if len(context.args) < 2: return await update.message.reply_text("❌ فرمت: `/sendcity Italy 3`")

    amount_str = context.args[-1]
    target_country = " ".join(context.args[:-1])

    if not amount_str.isdigit() or int(amount_str) <= 0: return await update.message.reply_text("❌ تعداد شهر نامعتبر است.")
    amount = int(amount_str)
    
    target_id = get_user_id_by_country(group_db, target_country)
    if not target_id: return await update.message.reply_text("❌ کشور پیدا نشد.")
    if target_id == user_id: return await update.message.reply_text("❌ به خودتان؟")

    user_data = group_db["users"][user_id]
    if user_data.get("cities", 21) < amount: return await update.message.reply_text("❌ شما این تعداد شهر ندارید!")

    user_data["cities"] -= amount
    group_db["users"][target_id]["cities"] = group_db["users"][target_id].get("cities", 21) + amount
    save_db()

    await update.message.reply_text(f"🏙 تعداد **{amount}** شهر از **{user_data['country']}** به **{target_country}** واگذار شد.", parse_mode='Markdown')
    await check_bankruptcy(update, group_db, user_id)

async def sell_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)

    if user_id not in group_db["users"]: return
    if len(context.args) < 3: return await update.message.reply_text("❌ فرمت: `/sellcity [کشور] [تعداد] [قیمت]`")

    price_str = context.args[-1]
    amount_str = context.args[-2]
    target_country = " ".join(context.args[:-2])

    if not (price_str.isdigit() and amount_str.isdigit()): return await update.message.reply_text("❌ قیمت و تعداد باید عدد باشند.")
    
    price = int(price_str)
    amount = int(amount_str)
    target_id = get_user_id_by_country(group_db, target_country)

    if not target_id: return await update.message.reply_text("❌ خریدار پیدا نشد.")
    if group_db["users"][user_id].get("cities", 21) < amount: return await update.message.reply_text("❌ شهر کافی ندارید.")

    group_db["market"][user_id] = {"target_id": target_id, "cities": amount, "price": price}
    save_db()
    
    seller_name = group_db["users"][user_id]["country"]
    await update.message.reply_text(f"📜 قرارداد فروش **{amount}** شهر به قیمت **{price}** برای **{target_country}** ارسال شد.\nتایید با `/acceptcity {seller_name}`", parse_mode='Markdown')

async def accept_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    buyer_id = str(update.message.from_user.id)

    if buyer_id not in group_db["users"]: return
    if len(context.args) == 0: return await update.message.reply_text("❌ فرمت: `/acceptcity [فروشنده]`")

    seller_country = " ".join(context.args)
    seller_id = get_user_id_by_country(group_db, seller_country)

    if not seller_id or seller_id not in group_db["market"]: return await update.message.reply_text("❌ پیشنهادی یافت نشد.")
    offer = group_db["market"][seller_id]
    if offer["target_id"] != buyer_id: return await update.message.reply_text("❌ پیشنهاد برای شما نیست.")

    buyer_data = group_db["users"][buyer_id]
    seller_data = group_db["users"][seller_id]

    if buyer_data["money"] < offer["price"]: return await update.message.reply_text("❌ بودجه کافی نیست.")

    buyer_data["money"] -= offer["price"]
    seller_data["money"] += offer["price"]
    seller_data["cities"] -= offer["cities"]
    buyer_data["cities"] = buyer_data.get("cities", 21) + offer["cities"]
    
    del group_db["market"][seller_id]
    save_db()

    await update.message.reply_text(f"🏙 معامله انجام شد! **{offer['cities']}** شهر به نقشه شما اضافه شد.", parse_mode='Markdown')
    await check_bankruptcy(update, group_db, seller_id)

async def buy_factory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)
    
    if user_id not in group_db["users"]: return await update.message.reply_text("❌ کشوری ندارید!")
    
    amount = 1
    if len(context.args) == 1 and context.args[0].isdigit():
        amount = int(context.args[0])

    user_data = group_db["users"][user_id]
    current_factories = user_data.get("factories", 0)
    
    total_cost = 0
    for i in range(amount):
        price = 1300 * (1 + (current_factories + i) * 0.10)
        total_cost += int(price)

    if user_data["money"] < total_cost:
        return await update.message.reply_text(f"❌ بودجه کافی نیست! خرید {amount} کارخانه نیازمند {total_cost} سکه است.")

    user_data["money"] -= total_cost
    user_data["factories"] = current_factories + amount
    process_factories(user_data)
    save_db()
    
    await update.message.reply_text(f"🏭 **{amount}** کارخانه جدید با قیمت کل {total_cost} سکه ساخته شد!", parse_mode='Markdown')

async def sell_factory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)

    if user_id not in group_db["users"]: return
    if len(context.args) < 3: return await update.message.reply_text("❌ فرمت: `/sellfactory [کشور] [تعداد] [قیمت]`")

    price = int(context.args[-1])
    amount = int(context.args[-2])
    target_country = " ".join(context.args[:-2])

    target_id = get_user_id_by_country(group_db, target_country)
    if not target_id: return await update.message.reply_text("❌ خریدار پیدا نشد.")
    
    user_data = group_db["users"][user_id]
    if user_data.get("factories", 0) < amount: return await update.message.reply_text("❌ کارخانه کافی ندارید.")

    group_db["factory_market"][user_id] = {"target_id": target_id, "amount": amount, "price": price}
    save_db()
    
    await update.message.reply_text(f"📜 پیشنهاد فروش **{amount}** کارخانه به قیمت **{price}** به **{target_country}** ارسال شد.", parse_mode='Markdown')

async def accept_factory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    buyer_id = str(update.message.from_user.id)

    if buyer_id not in group_db["users"] or len(context.args) == 0: return

    seller_country = " ".join(context.args)
    seller_id = get_user_id_by_country(group_db, seller_country)

    if not seller_id or seller_id not in group_db["factory_market"]: return await update.message.reply_text("❌ پیشنهادی یافت نشد.")
    offer = group_db["factory_market"][seller_id]
    
    if offer["target_id"] != buyer_id: return await update.message.reply_text("❌ پیشنهاد برای شما نیست.")
    
    buyer_data = group_db["users"][buyer_id]
    seller_data = group_db["users"][seller_id]

    if buyer_data["money"] < offer["price"]: return await update.message.reply_text("❌ بودجه کافی ندارید.")

    process_factories(buyer_data)
    process_factories(seller_data)

    buyer_data["money"] -= offer["price"]
    seller_data["money"] += offer["price"]
    seller_data["factories"] -= offer["amount"]
    buyer_data["factories"] = buyer_data.get("factories", 0) + offer["amount"]
    
    del group_db["factory_market"][seller_id]
    save_db()

    await update.message.reply_text(f"🏭 معامله انجام شد! {offer['amount']} کارخانه منتقل گردید.", parse_mode='Markdown')

async def send_factory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)

    if user_id not in group_db["users"] or len(context.args) < 2: return
    
    amount = int(context.args[-1])
    target_country = " ".join(context.args[:-1])
    target_id = get_user_id_by_country(group_db, target_country)

    if not target_id or target_id == user_id: return await update.message.reply_text("❌ کشور نامعتبر.")
    
    user_data = group_db["users"][user_id]
    if user_data.get("factories", 0) < amount: return await update.message.reply_text("❌ کارخانه کافی ندارید.")

    process_factories(user_data)
    process_factories(group_db["users"][target_id])

    user_data["factories"] -= amount
    group_db["users"][target_id]["factories"] = group_db["users"][target_id].get("factories", 0) + amount
    save_db()

    await update.message.reply_text(f"🏭 تعداد {amount} کارخانه به {target_country} واگذار شد.", parse_mode='Markdown')

# --- دیپلماسی ---
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

    if target_id not in group_db["requests"]: group_db["requests"][target_id] = {"ally": []}
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

# --- بخش جنگ شرطی (Attack) ---
async def attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)
    
    if user_id not in group_db["users"]: return await update.message.reply_text("❌ کشوری ندارید.")
    if len(context.args) < 2: return await update.message.reply_text("❌ فرمت صحیح: `/attack [نام کشور] [تعداد شهر برای شرط‌بندی]`")
    
    bet_amount_str = context.args[-1]
    target_country = " ".join(context.args[:-1])
    
    if not bet_amount_str.isdigit() or int(bet_amount_str) <= 0:
        return await update.message.reply_text("❌ تعداد شهر شرط‌بندی شده نامعتبر است.")
    bet_amount = int(bet_amount_str)
    
    target_id = get_user_id_by_country(group_db, target_country)
    if not target_id: return await update.message.reply_text("❌ کشور هدف پیدا نشد.")
    if target_id == user_id: return await update.message.reply_text("❌ به خودتان حمله می‌کنید؟!")
    
    user_data = group_db["users"][user_id]
    target_data = group_db["users"][target_id]
    
    land1 = user_data.get("cities", 21)
    land2 = target_data.get("cities", 21)
    
    if land1 < bet_amount: return await update.message.reply_text(f"❌ شما {bet_amount} شهر برای شرط‌بندی ندارید!")
    if land2 < bet_amount: return await update.message.reply_text(f"❌ کشور مدافع {bet_amount} شهر برای باختن ندارد!")
    
    score1, score2 = 0, 0
    if land1 > land2: score2 += (land1 - land2 - 1)
    elif land1 < land2: score1 += (land2 - land1 - 1)
        
    win_score = max(score1, score2) + 3 
    
    log_text = f"⚔️ **جنگ بین {user_data['country']} و {target_data['country']} آغاز شد!**\n"
    log_text += f"⚠️ شرط‌بندی روی: **{bet_amount} شهر**\n"
    log_text += f"🎯 امتیاز هدف اولیه برای پیروزی: {win_score}\n\n"
    
    round_count = 0
    while score1 < win_score and score2 < win_score and round_count < 100:
        round_count += 1
        percent1 = random.randint(1, 100)
        percent2 = random.randint(1, 100)
        
        if percent1 > percent2: score1 += 1
        elif percent1 < percent2: score2 += 1
            
        if score1 == win_score - 1 or score2 == win_score - 1:
            win_score += 1

    log_text += f"📊 **نتیجه نهایی:** مهاجم {score1} | مدافع {score2} (هدف: {win_score})\n\n"

    # اعمال نتایج شرط‌بندی
    if score1 >= win_score:
        log_text += f"🏆 مهاجم (**{user_data['country']}**) پیروز شد و **{bet_amount} شهر** را فتح کرد!"
        user_data["cities"] += bet_amount
        target_data["cities"] -= bet_amount
        await update.message.reply_text(log_text, parse_mode='Markdown')
        await check_bankruptcy(update, group_db, target_id)
        
    elif score2 >= win_score:
        log_text += f"🛡 مدافع (**{target_data['country']}**) پیروز شد و **{bet_amount} شهر** از خاک مهاجم را تصرف کرد!"
        target_data["cities"] += bet_amount
        user_data["cities"] -= bet_amount
        await update.message.reply_text(log_text, parse_mode='Markdown')
        await check_bankruptcy(update, group_db, user_id)
    save_db()

# --- سیستم Vote Kick و ادمین ---
async def votekick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    user_id = str(update.message.from_user.id)
    
    if user_id not in group_db["users"]: return await update.message.reply_text("❌ شما کشوری در بازی ندارید و نمی‌توانید رای دهید.")
    if len(context.args) == 0: return await update.message.reply_text("❌ نام کشور متخلف را وارد کنید: `/votekick [نام]`")
    
    target_country = " ".join(context.args)
    target_id = get_user_id_by_country(group_db, target_country)
    
    if not target_id: return await update.message.reply_text("❌ کشور پیدا نشد.")
    if target_id == user_id: return await update.message.reply_text("❌ نمی‌توانید به خودتان رای دهید!")

    if target_id not in group_db["votes"]:
        group_db["votes"][target_id] = []
        
    if user_id in group_db["votes"][target_id]:
        return await update.message.reply_text("❌ شما قبلاً به اخراج این کشور رای داده‌اید.")
        
    group_db["votes"][target_id].append(user_id)
    save_db()
    
    total_players = len(group_db["users"])
    # حداقل ۳ رای برای گروه‌های کوچک، در غیر اینصورت نصف بازیکنان + ۱
    required_votes = max(3, (total_players // 2) + 1)
    current_votes = len(group_db["votes"][target_id])
    
    await update.message.reply_text(f"🚷 یک رای برای اخراج **{target_country}** ثبت شد.\n(آرای فعلی: {current_votes} / حد نصاب: {required_votes})", parse_mode='Markdown')
    
    if current_votes >= required_votes:
        # شبیه‌سازی از دست دادن تمام شهرها برای اجرای تابع ورشکستگی
        group_db["users"][target_id]["cities"] = 0
        await update.message.reply_text(f"⛔️ رای‌گیری به حد نصاب رسید! کشور متخلف **{target_country}** از بازی اخراج شد.", parse_mode='Markdown')
        await check_bankruptcy(update, group_db, target_id)

async def admin_wipe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    if user_id != ADMIN_ID:
        return await update.message.reply_text("❌ شما دسترسی ادمین ندارید.")
        
    chat_id = update.effective_chat.id
    group_db = get_group_db(chat_id)
    
    if len(context.args) == 0: return await update.message.reply_text("❌ نام کشور را وارد کنید.")
    target_country = " ".join(context.args)
    target_id = get_user_id_by_country(group_db, target_country)
    
    if not target_id: return await update.message.reply_text("❌ کشور پیدا نشد.")
    
    group_db["users"][target_id]["cities"] = 0
    await update.message.reply_text(f"⚡️ **ادمین (SINA) وارد عمل شد!**\nکشور **{target_country}** به دلیل تخلف فوراً از نقشه پاک شد.", parse_mode='Markdown')
    await check_bankruptcy(update, group_db, target_id)


# --- اجرای ربات ---
if __name__ == '__main__':
    if BOT_TOKEN == "توکن_شما" or len(BOT_TOKEN) < 30:
        print("⚠️ توکن را در سورس کد قرار دهید.")

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    # ثبت تمامی دستورات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("claim", claim))
    app.add_handler(CommandHandler("rename", rename_country))
    app.add_handler(CommandHandler("color", set_color))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("world", world))
    app.add_handler(CommandHandler("tax", tax))
    app.add_handler(CommandHandler("military", military))
    app.add_handler(CommandHandler("buyfactory", buy_factory))
    app.add_handler(CommandHandler("sellfactory", sell_factory))
    app.add_handler(CommandHandler("acceptfactory", accept_factory))
    app.add_handler(CommandHandler("sendfactory", send_factory))
    app.add_handler(CommandHandler("send", send_money))
    app.add_handler(CommandHandler("sendcity", send_city))
    app.add_handler(CommandHandler("sellcity", sell_city))
    app.add_handler(CommandHandler("acceptcity", accept_city))
    app.add_handler(CommandHandler("attack", attack))
    app.add_handler(CommandHandler("ally", ally))
    app.add_handler(CommandHandler("accept", accept_ally))
    app.add_handler(CommandHandler("votekick", votekick))
    app.add_handler(CommandHandler("adminwipe", admin_wipe))

    print("✅ ربات ژئوپلیتیک با تمامی ویژگی‌ها به صورت کامل روشن شد...")
    app.run_polling()