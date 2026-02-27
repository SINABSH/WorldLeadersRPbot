import json
import os
import logging
import asyncio
import math
from datetime import datetime, timedelta
from telegram import Update, User
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode

# --- Configuration ---
BOT_TOKEN = "" # توکن خود را اینجا قرار دهید
DATA_FILE = "rp_master_data.json"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- Database Setup ---
def load_db():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

db = load_db()

def save_db():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=4)

def init_group(chat_id):
    gid = str(chat_id)
    if gid not in db:
        db[gid] = {
            "users": {},
            "countries": {},
            "alliances": [],
            "wars": [],
            "market": [] # {seller_id, item_type, amount, price, id}
        }
    return db[gid]

# --- Calculation Helpers ---
def get_factory_price(count):
    # قیمت پایه ۱۳۰۰، افزایش ۱۰٪ به ازای هر سطح قبلی بصورت تصاعدی
    # کارخانه اول: ۱۳۰۰، دوم: ۱۳۰۰ + ۱۰٪، سوم: قبلی + ۲۰٪ و ...
    base = 1300
    total_price = base
    for i in range(1, count + 1):
        total_price += total_price * (0.1 * i)
    return int(total_price)

def get_time_diff(target_time_iso):
    now = datetime.now()
    target = datetime.fromisoformat(target_time_iso)
    diff = target - now
    if diff.total_seconds() <= 0:
        return None
    minutes, seconds = divmod(int(diff.total_seconds()), 60)
    return f"{minutes:02d}:{seconds:02d}"

# --- Commands ---

async def set_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # این تابع برای ست کردن لیست کامندها در منوی تلگرام است
    commands = [
        ("start", "شروع ربات"),
        ("help", "راهنمای کامل"),
        ("claim", "ثبت کشور [نام]"),
        ("profile", "مشاهده پروفایل خود یا دیگران"),
        ("world", "نقشه جهانی و آمار"),
        ("tax", "دریافت مالیات"),
        ("build", "خرید شهر یا کارخانه"),
        ("rename", "تغییر نام کشور"),
        ("sell", "فروش ملک در بازار"),
        ("market", "لیست بازار فروش"),
        ("buy", "خرید از بازار [کد]"),
        ("give", "انتقال مستقیم به دیگران"),
        ("war", "اعلان جنگ"),
        ("ally", "پیشنهاد اتحاد")
    ]
    await context.bot.set_my_commands(commands)
    await update.message.reply_text("✅ لیست دستورات در منوی تلگرام بروزرسانی شد.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🇮🇷 به ربات رول‌پلی پیشرفته خوش آمدید!\nبرای شروع از `/claim [نام کشور]` استفاده کنید.")

async def claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gid = str(update.effective_chat.id)
    uid = str(update.effective_user.id)
    g_db = init_group(gid)

    if uid in g_db["users"]:
        return await update.message.reply_text("❌ شما در این گروه قبلاً کشور ثبت کرده‌اید.")
    
    if not context.args:
        return await update.message.reply_text("❌ نام کشور را وارد کنید.")
    
    c_name = " ".join(context.args)
    if c_name in g_db["countries"]:
        return await update.message.reply_text("❌ این نام کشور رزرو شده است.")

    g_db["users"][uid] = {
        "name": update.effective_user.first_name,
        "country": c_name,
        "color": "⚪️",
        "money": 5000,
        "army": 100,
        "cities": 21,
        "factories": 0,
        "last_tax": (datetime.now() - timedelta(minutes=30)).isoformat(),
        "last_factory_prod": datetime.now().isoformat()
    }
    g_db["countries"][c_name] = uid
    save_db()
    await update.message.reply_text(f"✅ کشور **{c_name}** با ۲۱ شهر تاسیس شد!", parse_mode=ParseMode.MARKDOWN)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gid = str(update.effective_chat.id)
    g_db = init_group(gid)
    
    target_uid = str(update.effective_user.id)
    
    # Check for mention or reply
    if update.message.reply_to_message:
        target_uid = str(update.message.reply_to_message.from_user.id)
    elif context.args and update.message.entities:
        for ent in update.message.entities:
            if ent.type == "mention":
                # Note: Mentions need complex resolving, for simplicity we check if the user is in db
                mention_text = update.message.text[ent.offset:ent.offset+ent.length]
                # Filter through users to find name match if possible or just use mention logic
                pass

    if target_uid not in g_db["users"]:
        return await update.message.reply_text("❌ این کاربر در این گروه کشوری ندارد.")

    u = g_db["users"][target_uid]
    tax_timer = get_time_diff((datetime.fromisoformat(u["last_tax"]) + timedelta(minutes=30)).isoformat())
    tax_status = "✅ آماده دریافت" if not tax_timer else f"⏳ {tax_timer}"

    msg = (
        f"{u['color']} **کشور: {u['country']}**\n"
        f"👤 رهبر: {u['name']}\n"
        f"➖➖➖➖➖➖\n"
        f"💰 خزانه: {u['money']:,} سکه\n"
        f"🏙 شهرها: {u['cities']}\n"
        f"🏭 کارخانه‌ها: {u['factories']}\n"
        f"🪖 ارتش: {u['army']:,} نیرو\n"
        f"➖➖➖➖➖➖\n"
        f"💵 مالیات بعدی: {tax_status}\n"
        f"🛠 قیمت کارخانه بعدی: {get_factory_price(u['factories']):,}"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

async def tax(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gid = str(update.effective_chat.id)
    uid = str(update.effective_user.id)
    g_db = init_group(gid)

    if uid not in g_db["users"]: return
    u = g_db["users"][uid]
    
    now = datetime.now()
    last_tax = datetime.fromisoformat(u["last_tax"])
    
    if now < last_tax + timedelta(minutes=30):
        timer = get_time_diff((last_tax + timedelta(minutes=30)).isoformat())
        return await update.message.reply_text(f"⏳ زمان باقی‌مانده: {timer}")

    # هر شهر ۷۰ سکه مالیات
    income = u["cities"] * 70
    u["money"] += income
    u["last_tax"] = now.isoformat()
    
    # تولید نیروی کارخانه (هر کارخانه ۱۰ نیرو در ساعت)
    # اینجا ساده‌سازی شده: موقع مالیات، تولید کارخانه هم چک می‌شود
    last_prod = datetime.fromisoformat(u["last_factory_prod"])
    hours = (now - last_prod).total_seconds() / 3600
    new_army = int(hours * u["factories"] * 10)
    u["army"] += new_army
    u["last_factory_prod"] = now.isoformat()

    save_db()
    await update.message.reply_text(f"💰 مالیات دریافت شد!\n💵 سود بانکی: {income:,}\n🪖 نیروهای جدید کارخانه: {new_army}")

async def rename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gid = str(update.effective_chat.id)
    uid = str(update.effective_user.id)
    g_db = init_group(gid)

    if uid not in g_db["users"] or not context.args: return
    new_name = " ".join(context.args)
    
    if new_name in g_db["countries"]:
        return await update.message.reply_text("❌ این نام قبلاً انتخاب شده است.")
    
    old_name = g_db["users"][uid]["country"]
    del g_db["countries"][old_name]
    g_db["users"][uid]["country"] = new_name
    g_db["countries"][new_name] = uid
    save_db()
    await update.message.reply_text(f"✅ نام کشور به {new_name} تغییر یافت.")

async def world(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gid = str(update.effective_chat.id)
    g_db = init_group(gid)
    if not g_db["users"]: return await update.message.reply_text("نقشه خالی است.")

    text = "🌍 **آمار جهانی این گروه:**\n\n"
    for uid, u in g_db["users"].items():
        text += f"{u['color']} **{u['country']}**: 🏙 {u['cities']} | 🏭 {u['factories']} | 🪖 {u['army']}\n"
    
    # نمایش اتحادها و جنگ‌ها
    if g_db["alliances"]:
        text += "\n🤝 **اتحادها:**\n"
        for a in g_db["alliances"]:
            text += f"- {g_db['users'][a[0]]['country']} 🤝 {g_db['users'][a[1]]['country']}\n"
            
    if g_db["wars"]:
        text += "\n⚔️ **جنگ‌های جاری:**\n"
        for w in g_db["wars"]:
            text += f"- {g_db['users'][w[0]]['country']} 🔥 {g_db['users'][w[1]]['country']}\n"

    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

async def build(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gid = str(update.effective_chat.id)
    uid = str(update.effective_user.id)
    g_db = init_group(gid)
    if uid not in g_db["users"]: return

    if not context.args:
        return await update.message.reply_text("💡 مثال: `/build factory` یا `/build city` (قیمت شهر: ۵۰۰۰)")

    u = g_db["users"][uid]
    item = context.args[0].lower()

    if item == "factory":
        price = get_factory_price(u["factories"])
        if u["money"] >= price:
            u["money"] -= price
            u["factories"] += 1
            save_db()
            await update.message.reply_text(f"🏭 کارخانه شماره {u['factories']} ساخته شد!")
        else:
            await update.message.reply_text(f"❌ موجودی کافی نیست. نیاز به {price:,} دارید.")
    
    elif item == "city":
        if u["money"] >= 5000:
            u["money"] -= 5000
            u["cities"] += 1
            save_db()
            await update.message.reply_text("🏙 یک شهر جدید به قلمرو اضافه شد!")
        else:
            await update.message.reply_text("❌ پول کافی برای خرید شهر ندارید (۵۰۰۰ سکه).")

async def sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gid = str(update.effective_chat.id)
    uid = str(update.effective_user.id)
    g_db = init_group(gid)
    if uid not in g_db["users"]: return

    # /sell city 1 1000
    if len(context.args) < 3:
        return await update.message.reply_text("💡 دستور: `/sell [نوع] [تعداد] [قیمت_کل]`\nمثال: `/sell factory 1 2000`")

    itype = context.args[0].lower() # city / factory
    amount = int(context.args[1])
    price = int(context.args[2])
    u = g_db["users"][uid]

    if itype == "city" and u["cities"] > amount:
        u["cities"] -= amount
    elif itype == "factory" and u["factories"] >= amount:
        u["factories"] -= amount
    else:
        return await update.message.reply_text("❌ موجودی ملک شما کافی نیست.")

    listing = {
        "id": len(g_db["market"]) + 1,
        "seller_id": uid,
        "type": itype,
        "amount": amount,
        "price": price
    }
    g_db["market"].append(listing)
    save_db()
    await update.message.reply_text(f"✅ آگهی فروش ثبت شد. کد کالا: {listing['id']}")

async def market(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gid = str(update.effective_chat.id)
    g_db = init_group(gid)
    if not g_db["market"]: return await update.message.reply_text("بازار خالی است.")

    text = "🏪 **بازار جهانی:**\n\n"
    for item in g_db["market"]:
        seller = g_db["users"][item['seller_id']]['country']
        text += f"📦 کد {item['id']} | {item['amount']} عدد {item['type']} | قیمت: {item['price']:,} | فروشنده: {seller}\n"
    
    text += "\nبرای خرید: `/buy [کد]`"
    await update.message.reply_text(text)

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gid = str(update.effective_chat.id)
    uid = str(update.effective_user.id)
    g_db = init_group(gid)
    if uid not in g_db["users"] or not context.args: return

    item_id = int(context.args[0])
    listing = next((x for x in g_db["market"] if x["id"] == item_id), None)

    if not listing: return await update.message.reply_text("❌ کد کالا یافت نشد.")
    u = g_db["users"][uid]

    if u["money"] < listing["price"]:
        return await update.message.reply_text("❌ پول شما کافی نیست.")

    u["money"] -= listing["price"]
    # واریز پول به فروشنده
    if listing["seller_id"] in g_db["users"]:
        g_db["users"][listing["seller_id"]]["money"] += listing["price"]

    if listing["type"] == "city": u["cities"] += listing["amount"]
    else: u["factories"] += listing["amount"]

    g_db["market"].remove(listing)
    save_db()
    await update.message.reply_text("✅ معامله با موفقیت انجام شد!")

async def attack_logic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # سیستم تخریب شهر در جنگ
    gid = str(update.effective_chat.id)
    uid = str(update.effective_user.id)
    g_db = init_group(gid)
    if uid not in g_db["users"] or not context.args: return

    target_name = " ".join(context.args)
    tid = None
    for n, i in g_db["countries"].items():
        if n.lower() == target_name.lower(): tid = i
    
    if not tid: return await update.message.reply_text("❌ کشور یافت نشد.")
    
    u = g_db["users"][uid]
    t = g_db["users"][tid]

    # جنگ ساده: اگر قدرت ۲ برابر باشد یک شهر تسخیر می‌شود
    if u["army"] > t["army"] * 1.5:
        t["cities"] -= 1
        u["army"] -= int(t["army"] * 0.5)
        t["army"] = 0
        await update.message.reply_text(f"🔥 پیروزی! یک شهر از {target_name} تسخیر شد.")
        
        # چک کردن ورشکستگی
        if t["cities"] <= 0:
            await update.message.reply_text(f"🏴 کشور {target_name} به دلیل از دست دادن تمام شهرها ورشکست و نابود شد!")
            del g_db["countries"][target_name]
            del g_db["users"][tid]
    else:
        u["army"] -= int(u["army"] * 0.4)
        await update.message.reply_text("💀 شکست خوردید! تلفات سنگینی به ارتش شما وارد شد.")
    
    save_db()

# --- Main ---
if __name__ == '__main__':
    if not BOT_TOKEN:
        print("لطفا توکن را وارد کنید")
    else:
        app = ApplicationBuilder().token(BOT_TOKEN).build()
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_cmd)) # مشابه کد قبل
        app.add_handler(CommandHandler("claim", claim))
        app.add_handler(CommandHandler("profile", profile))
        app.add_handler(CommandHandler("world", world))
        app.add_handler(CommandHandler("tax", tax))
        app.add_handler(CommandHandler("build", build))
        app.add_handler(CommandHandler("rename", rename))
        app.add_handler(CommandHandler("sell", sell))
        app.add_handler(CommandHandler("market", market))
        app.add_handler(CommandHandler("buy", buy))
        app.add_handler(CommandHandler("set_menu", set_commands))
        
        print("Bot is running...")
        app.run_polling()


