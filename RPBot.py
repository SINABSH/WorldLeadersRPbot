import json
import os
import logging
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- تنظیمات اولیه ---
BOT_TOKEN = "توکن_ربات_خود_را_اینجا_قرار_دهید" # <--- توکن ربات خود را از BotFather بگیرید و اینجا بگذارید
DATA_FILE = "rp_data.json"

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- سیستم دیتابیس (ذخیره در فایل JSON) ---
default_db = {
    "users": {},      # user_id (str) -> {"name": str, "country": str, "money": int, "army": int, "last_tax": str}
    "countries": {},  # country_name (str) -> user_id (str)
    "alliances": [],  # list of lists [[user1, user2], ...]
    "wars": [],       # list of lists [[attacker, defender], ...]
    "requests": {}    # target_user_id -> {"ally": [requester_ids], "peace": [requester_ids]}
}

def load_db():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return default_db.copy()

def save_db():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=4)

db = load_db()

# --- توابع کمکی ---
def get_user_id_by_country(country_name):
    for c, uid in db["countries"].items():
        if c.lower() == country_name.lower():
            return uid
    return None

def get_country_by_user_id(user_id):
    user_id = str(user_id)
    if user_id in db["users"]:
        return db["users"][user_id]["country"]
    return None

def is_allied(uid1, uid2):
    return [uid1, uid2] in db["alliances"] or [uid2, uid1] in db["alliances"]

def is_at_war(uid1, uid2):
    return [uid1, uid2] in db["wars"] or [uid2, uid1] in db["wars"]

# --- دستورات ربات ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🌍 *به ربات مدیریت رول‌پلی ژئوپلیتیک خوش آمدید!*\n\n"
        "این ربات به شما کمک می‌کند تا کشور خود را رهبری کنید، اقتصاد بسازید، "
        "با دیگر کشورها متحد شوید یا به آن‌ها اعلان جنگ دهید.\n\n"
        "برای شروع، با دستور زیر یک کشور را برای خود انتخاب کنید:\n"
        "`/claim [نام کشور]`\n\n"
        "برای دیدن لیست کامل دستورات، `/help` را ارسال کنید."
    )
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📜 *لیست دستورات ربات:*\n\n"
        "🌍 `/claim [نام کشور]` - تصاحب و رهبری یک کشور\n"
        "👤 `/profile` - مشاهده وضعیت کشور، بودجه، ارتش و دیپلماسی شما\n"
        "🗺 `/world` - مشاهده لیست تمام کشورهای جهان\n"
        "💰 `/tax` - جمع‌آوری مالیات (هر 30 دقیقه)\n"
        "🪖 `/military [تعداد]` - خرید نیروی نظامی (هر نیرو 10 سکه)\n"
        "💸 `/send [نام کشور] [مبلغ]` - ارسال پول به کشور دیگر\n\n"
        "🤝 `/ally [نام کشور]` - پیشنهاد اتحاد\n"
        "✅ `/accept [نام کشور]` - پذیرش پیشنهاد اتحاد\n"
        "⚔️ `/war [نام کشور]` - اعلان جنگ به یک کشور\n"
        "🕊 `/peace [نام کشور]` - پیشنهاد صلح\n"
        "✅ `/acceptpeace [نام کشور]` - پذیرش صلح\n"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    user_name = update.message.from_user.first_name

    if len(context.args) == 0:
        await update.message.reply_text("❌ لطفاً نام کشور را وارد کنید. مثال: `/claim Iran`")
        return

    country_name = " ".join(context.args)

    if user_id in db["users"]:
        current_country = db["users"][user_id]["country"]
        await update.message.reply_text(f"❌ شما در حال حاضر رهبر کشور **{current_country}** هستید!", parse_mode='Markdown')
        return

    for existing_country in db["countries"]:
        if existing_country.lower() == country_name.lower():
            await update.message.reply_text(f"❌ کشور **{existing_country}** قبلاً توسط شخص دیگری انتخاب شده است.", parse_mode='Markdown')
            return

    # ثبت نام بازیکن
    db["users"][user_id] = {
        "name": user_name,
        "country": country_name,
        "money": 5000,
        "army": 100,
        "last_tax": "2000-01-01T00:00:00"
    }
    db["countries"][country_name] = user_id
    save_db()

    await update.message.reply_text(f"🎉 تبریک! شما با موفقیت رهبری کشور **{country_name}** را بر عهده گرفتید.\n\n"
                                    f"💰 بودجه اولیه: 5000\n"
                                    f"🪖 ارتش اولیه: 100\n\n"
                                    f"برای مشاهده وضعیت خود `/profile` را بزنید.", parse_mode='Markdown')

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    
    if user_id not in db["users"]:
        await update.message.reply_text("❌ شما هنوز کشوری ندارید! ابتدا با `/claim` یک کشور انتخاب کنید.")
        return

    user_data = db["users"][user_id]
    country = user_data["country"]
    
    # پیدا کردن متحدین و دشمنان
    allies = []
    enemies = []
    
    for pair in db["alliances"]:
        if user_id in pair:
            other_id = pair[0] if pair[1] == user_id else pair[1]
            allies.append(get_country_by_user_id(other_id))
            
    for pair in db["wars"]:
        if user_id in pair:
            other_id = pair[0] if pair[1] == user_id else pair[1]
            enemies.append(get_country_by_user_id(other_id))

    allies_str = "، ".join(allies) if allies else "ندارد"
    enemies_str = "، ".join(enemies) if enemies else "ندارد"

    profile_text = (
        f"🏛 **دولت {country}**\n"
        f"👤 رهبر: {user_data['name']}\n\n"
        f"💰 خزانه: {user_data['money']} سکه\n"
        f"🪖 قدرت نظامی: {user_data['army']} سرباز\n\n"
        f"🤝 متحدین: {allies_str}\n"
        f"⚔️ در جنگ با: {enemies_str}"
    )
    await update.message.reply_text(profile_text, parse_mode='Markdown')

async def world(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not db["countries"]:
        await update.message.reply_text("🌍 جهان هنوز خالی از سکنه است!")
        return

    text = "🌍 **نقشه سیاسی جهان:**\n\n"
    for country, uid in db["countries"].items():
        user = db["users"][uid]
        text += f"🏳️ **{country}** (رهبر: {user['name']}) - 🪖 {user['army']}\n"

    await update.message.reply_text(text, parse_mode='Markdown')

async def tax(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    if user_id not in db["users"]:
        await update.message.reply_text("❌ شما هنوز کشوری ندارید!")
        return

    user_data = db["users"][user_id]
    last_tax = datetime.fromisoformat(user_data["last_tax"])
    now = datetime.now()

    if now < last_tax + timedelta(minutes=30):
        remaining = (last_tax + timedelta(minutes=30)) - now
        minutes = int(remaining.total_seconds() // 60)
        await update.message.reply_text(f"⏳ خزانه‌دار در حال استراحت است. لطفاً {minutes} دقیقه دیگر برای جمع‌آوری مالیات مراجعه کنید.")
        return

    tax_amount = 1500 # مبلغ ثابت (می‌توانید فرمول‌های پیچیده‌تری بر اساس تعداد ارتش یا غیره بنویسید)
    user_data["money"] += tax_amount
    user_data["last_tax"] = now.isoformat()
    save_db()

    await update.message.reply_text(f"💰 مالیات با موفقیت جمع‌آوری شد!\nمبلغ **{tax_amount}** سکه به خزانه کشور **{user_data['country']}** واریز شد.", parse_mode='Markdown')

async def military(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    if user_id not in db["users"]:
        return await update.message.reply_text("❌ شما هنوز کشوری ندارید!")

    if len(context.args) != 1 or not context.args[0].isdigit():
        return await update.message.reply_text("❌ فرمت اشتباه است. مثال خرید 50 سرباز: `/military 50`")

    amount = int(context.args[0])
    cost = amount * 10 # هر سرباز 10 سکه

    user_data = db["users"][user_id]
    
    if user_data["money"] < cost:
        return await update.message.reply_text(f"❌ بودجه کافی نیست! شما به {cost} سکه نیاز دارید اما فقط {user_data['money']} سکه دارید.")

    user_data["money"] -= cost
    user_data["army"] += amount
    save_db()

    await update.message.reply_text(f"🪖 ارتش شما تجهیز شد! **{amount}** نیروی جدید به ارتش **{user_data['country']}** پیوستند.\nهزینه: {cost} سکه.", parse_mode='Markdown')

async def send_money(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    if user_id not in db["users"]:
        return await update.message.reply_text("❌ شما کشوری ندارید.")

    if len(context.args) < 2:
        return await update.message.reply_text("❌ فرمت اشتباه است. مثال: `/send Russia 1000`")

    target_country = " ".join(context.args[:-1])
    amount_str = context.args[-1]

    if not amount_str.isdigit():
        return await update.message.reply_text("❌ مبلغ باید عدد باشد.")
    
    amount = int(amount_str)
    target_id = get_user_id_by_country(target_country)

    if not target_id:
        return await update.message.reply_text(f"❌ کشوری با نام **{target_country}** یافت نشد.", parse_mode='Markdown')
    
    if target_id == user_id:
        return await update.message.reply_text("❌ شما نمی‌توانید به خودتان پول بفرستید!")

    user_data = db["users"][user_id]
    target_data = db["users"][target_id]

    if user_data["money"] < amount:
        return await update.message.reply_text("❌ خزانه شما برای این انتقال کافی نیست!")

    user_data["money"] -= amount
    target_data["money"] += amount
    save_db()

    await update.message.reply_text(f"💸 مبلغ **{amount}** سکه با موفقیت از **{user_data['country']}** به **{target_country}** منتقل شد.", parse_mode='Markdown')

async def war(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    if user_id not in db["users"]: return await update.message.reply_text("❌ شما کشوری ندارید.")

    if len(context.args) == 0: return await update.message.reply_text("❌ نام کشور هدف را بنویسید. مثال: `/war Germany`")
    
    target_country = " ".join(context.args)
    target_id = get_user_id_by_country(target_country)

    if not target_id: return await update.message.reply_text("❌ کشور پیدا نشد.")
    if target_id == user_id: return await update.message.reply_text("❌ نمی‌توانید به خودتان اعلان جنگ بدهید!")
    if is_at_war(user_id, target_id): return await update.message.reply_text("❌ شما در حال حاضر با این کشور در جنگ هستید!")
    if is_allied(user_id, target_id):
        # حذف اتحاد قبل از جنگ
        db["alliances"] = [a for a in db["alliances"] if set(a) != {user_id, target_id}]

    db["wars"].append([user_id, target_id])
    save_db()

    my_country = db["users"][user_id]["country"]
    await update.message.reply_text(f"🚨 **اعلان جنگ!** 🚨\n\nکشور **{my_country}** رسماً به **{target_country}** اعلان جنگ داد! طبل‌های جنگ به صدا درآمدند...", parse_mode='Markdown')

async def ally(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    if user_id not in db["users"]: return await update.message.reply_text("❌ شما کشوری ندارید.")

    if len(context.args) == 0: return await update.message.reply_text("❌ نام کشور هدف را بنویسید. مثال: `/ally Italy`")
    
    target_country = " ".join(context.args)
    target_id = get_user_id_by_country(target_country)

    if not target_id: return await update.message.reply_text("❌ کشور پیدا نشد.")
    if target_id == user_id: return await update.message.reply_text("❌ نمی‌توانید با خودتان متحد شوید!")
    if is_allied(user_id, target_id): return await update.message.reply_text("❌ شما در حال حاضر متحد هستید!")
    if is_at_war(user_id, target_id): return await update.message.reply_text("❌ شما در حال جنگ با این کشور هستید! ابتدا صلح کنید.")

    if target_id not in db["requests"]: db["requests"][target_id] = {"ally": [], "peace": []}
    if user_id not in db["requests"][target_id]["ally"]:
        db["requests"][target_id]["ally"].append(user_id)
        save_db()

    my_country = db["users"][user_id]["country"]
    await update.message.reply_text(f"✉️ درخواست اتحاد برای **{target_country}** ارسال شد. رهبر این کشور باید با دستور `/accept {my_country}` آن را بپذیرد.", parse_mode='Markdown')

async def accept_ally(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    if user_id not in db["users"]: return

    if len(context.args) == 0: return await update.message.reply_text("❌ نام کشوری که به شما پیشنهاد داده را وارد کنید. مثال `/accept Japan`")
    
    target_country = " ".join(context.args)
    requester_id = get_user_id_by_country(target_country)

    if not requester_id: return await update.message.reply_text("❌ کشور پیدا نشد.")

    if user_id in db["requests"] and requester_id in db["requests"][user_id]["ally"]:
        db["requests"][user_id]["ally"].remove(requester_id)
        db["alliances"].append([user_id, requester_id])
        save_db()
        my_country = db["users"][user_id]["country"]
        await update.message.reply_text(f"🤝 پیمان اتحاد بسته شد! **{my_country}** و **{target_country}** اکنون متحد هستند.", parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ هیچ پیشنهاد اتحادی از سمت این کشور برای شما ثبت نشده است.")

async def peace(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    if user_id not in db["users"]: return
    if len(context.args) == 0: return await update.message.reply_text("❌ مثال: `/peace France`")
    
    target_country = " ".join(context.args)
    target_id = get_user_id_by_country(target_country)

    if not target_id: return await update.message.reply_text("❌ کشور پیدا نشد.")
    if not is_at_war(user_id, target_id): return await update.message.reply_text("❌ شما با این کشور در جنگ نیستید.")

    if target_id not in db["requests"]: db["requests"][target_id] = {"ally": [], "peace": []}
    if user_id not in db["requests"][target_id]["peace"]:
        db["requests"][target_id]["peace"].append(user_id)
        save_db()

    my_country = db["users"][user_id]["country"]
    await update.message.reply_text(f"🕊 درخواست صلح برای **{target_country}** ارسال شد. (پذیرش با `/acceptpeace {my_country}`)", parse_mode='Markdown')

async def accept_peace(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    if user_id not in db["users"]: return

    if len(context.args) == 0: return await update.message.reply_text("❌ مثال `/acceptpeace England`")
    
    target_country = " ".join(context.args)
    requester_id = get_user_id_by_country(target_country)

    if user_id in db["requests"] and requester_id in db["requests"][user_id]["peace"]:
        db["requests"][user_id]["peace"].remove(requester_id)
        
        # پایان دادن به جنگ
        db["wars"] = [w for w in db["wars"] if set(w) != {user_id, requester_id}]
        save_db()
        
        my_country = db["users"][user_id]["country"]
        await update.message.reply_text(f"🕊 معاهده صلح امضا شد! جنگ بین **{my_country}** و **{target_country}** به پایان رسید.", parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ هیچ پیشنهاد صلحی از سمت این کشور برای شما ثبت نشده است.")

# --- اجرای ربات ---
if __name__ == '__main__':
    if BOT_TOKEN == "توکن_ربات_خود_را_اینجا_قرار_دهید":
        print("لطفاً ابتدا BOT_TOKEN را در داخل فایل ویرایش کنید!")
        exit()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # ثبت دستورات
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("claim", claim))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("world", world))
    app.add_handler(CommandHandler("tax", tax))
    app.add_handler(CommandHandler("military", military))
    app.add_handler(CommandHandler("send", send_money))
    app.add_handler(CommandHandler("war", war))
    app.add_handler(CommandHandler("ally", ally))
    app.add_handler(CommandHandler("accept", accept_ally))
    app.add_handler(CommandHandler("peace", peace))
    app.add_handler(CommandHandler("acceptpeace", accept_peace))

    print("ربات در حال اجرا است...")
    app.run_polling()


