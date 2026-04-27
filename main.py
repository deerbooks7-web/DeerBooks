import os
import json
import random
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional
from io import BytesIO
from flask import Flask, request
from threading import Thread
import aiohttp
from PIL import Image, ImageDraw, ImageFont
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

# ==================== إعدادات التسجيل ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== إعدادات البوت ====================
TOKEN    = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = os.environ.get("ADMIN_ID",  "")

if not TOKEN:
    raise RuntimeError("❌ يجب تعيين متغير BOT_TOKEN")
if not ADMIN_ID:
    raise RuntimeError("❌ يجب تعيين متغير ADMIN_ID")

# محافظ الدفع
WALLETS = {
    "USDT_TRC20": "TUG6Uk4HdhEWwAnFDqQrxBrbCiSS1AZT1q",
    "ETH_BSC":    "0xD21cbA838fB5671d05e7362D93Ff76Ff5B3BdEB6",
    "BTC":        "bc1qdrr6up7ytx3vm2j9ymuw28dnzgkcu67fp94nm3",
}

# ==================== إدارة البيانات ====================
class DataManager:
    def __init__(self):
        self.users_file      = "users_data.json"
        self.books_file      = "books_data.json"
        self.categories_file = "categories_data.json"
        self.load_data()

    def load_data(self):
        self.users      = self._load_json(self.users_file, {})
        self.books      = self._load_json(self.books_file, {})
        self.categories = self._load_json(self.categories_file, [
            {"id": 1, "name": "التجارة الإلكترونية",  "name_en": "E-commerce"},
            {"id": 2, "name": "الاستثمار العقاري",    "name_en": "Real Estate"},
            {"id": 3, "name": "الأسهم والتداول",      "name_en": "Stocks & Trading"},
            {"id": 4, "name": "ريادة الأعمال",        "name_en": "Entrepreneurship"},
            {"id": 5, "name": "التسويق الرقمي",       "name_en": "Digital Marketing"},
        ])
        self.user_languages = {uid: d.get("language", "ar") for uid, d in self.users.items()}

    def _load_json(self, filename, default):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            self._save_json(filename, default)
            return default

    def _save_json(self, filename, data):
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"خطأ في حفظ {filename}: {e}")

    def save_all(self):
        self._save_json(self.users_file,      self.users)
        self._save_json(self.books_file,      self.books)
        self._save_json(self.categories_file, self.categories)

    def get_user(self, user_id):
        uid = str(user_id)
        if uid not in self.users:
            self.users[uid] = {
                "id": uid, "stars": 0,
                "books_purchased": [], "language": "ar",
                "join_date": datetime.now().isoformat(),
            }
            self.user_languages[uid] = "ar"
            self.save_all()
        return self.users[uid]

    def add_book(self, book_id, title, author, price, category_id, description=""):
        self.books[book_id] = {
            "id": book_id, "title": title, "author": author,
            "price": price, "category_id": category_id, "description": description,
        }
        self.save_all()

    def delete_book(self, book_id):
        if book_id in self.books:
            del self.books[book_id]
            self.save_all()
            return True
        return False

    def update_book(self, book_id, **kwargs):
        if book_id in self.books:
            self.books[book_id].update(kwargs)
            self.save_all()
            return True
        return False

    def add_category(self, cat_id, name, name_en):
        self.categories.append({"id": cat_id, "name": name, "name_en": name_en})
        self.save_all()

    def delete_category(self, cat_id):
        self.categories = [c for c in self.categories if c["id"] != cat_id]
        self.save_all()

    def update_category(self, cat_id, **kwargs):
        for cat in self.categories:
            if cat["id"] == cat_id:
                cat.update(kwargs)
                self.save_all()
                return True
        return False


data_manager = DataManager()

# ==================== نظام الترجمة ====================
TRANSLATIONS = {
    "welcome": {
        "ar": "📚 *أهلاً بك في Deer Books*\n\nمكتبتك الرقمية المتخصصة في كتب إدارة الأعمال والاستثمار والتداول.",
        "en": "📚 *Welcome to Deer Books*\n\nYour digital library specialized in business, investment, and trading books.",
    },
    "btn_create_own_book":  {"ar": "👍 أنشئ كتابك الخاص",    "en": "👍 Create Your Own Book"},
    "btn_all_books":        {"ar": "💬 جميع الكتب",           "en": "💬 All Books"},
    "btn_categories":       {"ar": "📘 التصنيفات",            "en": "📘 Categories"},
    "btn_stars_system":     {"ar": "⭐ نظام النجوم",          "en": "⭐ Stars System"},
    "btn_payment_methods":  {"ar": "💰 طرق الدفع",            "en": "💰 Payment Methods"},
    "btn_special_offers":   {"ar": "🎁 عروض خاصة",           "en": "🎁 Special Offers"},
    "btn_about":            {"ar": "🔗 عن المكتبة",           "en": "🔗 About Library"},
    "btn_language":         {"ar": "🌐 اللغة / Language",     "en": "🌐 اللغة / Language"},
    "btn_control":          {"ar": "⚙️ التحكم",               "en": "⚙️ Control"},
    "btn_share":            {"ar": "📢 شارك البوت",           "en": "📢 Share Bot"},
    "back_button":          {"ar": "🔙 رجوع",                 "en": "🔙 Back"},
    "error_occurred":       {"ar": "❌ حدث خطأ، حاول مرة أخرى","en": "❌ An error occurred, please try again"},
}

def get_lang(user_id):
    return data_manager.user_languages.get(str(user_id), "ar")

def set_lang(user_id, lang):
    data_manager.user_languages[str(user_id)] = lang
    data_manager.get_user(user_id)["language"] = lang
    data_manager.save_all()

def t(key, user_id):
    lang = get_lang(user_id)
    entry = TRANSLATIONS.get(key, key)
    if isinstance(entry, dict):
        return entry.get(lang, entry.get("ar", key))
    return entry

# ==================== الـ 15 ستايل للإعلانات ====================
AD_STYLES = {
    1:  {"name": "🎨 كلاسيكي ذهبي",      "description": "تصميم فخم ذهبي داكن",       "bg": (10,8,15),     "accent": (218,165,32),  "fc": (255,215,0)},
    2:  {"name": "🎨 حديث أزرق",          "description": "ألوان زرقاء عصرية",         "bg": (25,35,60),    "accent": (52,152,219),  "fc": (255,255,255)},
    3:  {"name": "🎨 استثماري أخضر",      "description": "ألوان النمو المالي",         "bg": (20,40,25),    "accent": (46,204,113),  "fc": (255,255,255)},
    4:  {"name": "🎨 ملون جذاب",           "description": "ألوان زاهية للشباب",        "bg": (45,25,55),    "accent": (231,76,60),   "fc": (255,255,255)},
    5:  {"name": "🎨 فضائي إبداعي",       "description": "لمسات كونية خيالية",        "bg": (15,10,35),    "accent": (155,89,182),  "fc": (200,200,255)},
    6:  {"name": "🎨 تقني",               "description": "مظهر تكنولوجي",             "bg": (20,20,35),    "accent": (0,255,255),   "fc": (0,255,255)},
    7:  {"name": "🎨 ريادي",              "description": "القيادة والنجاح",            "bg": (30,25,45),    "accent": (243,156,18),  "fc": (255,255,255)},
    8:  {"name": "🎨 بسيط نظيف",          "description": "minimalist هادئ",           "bg": (245,245,245), "accent": (52,73,94),    "fc": (44,62,80)},
    9:  {"name": "🎨 أكاديمي",            "description": "مظهر كتابي كلاسيكي",       "bg": (40,35,30),    "accent": (192,57,43),   "fc": (220,200,180)},
    10: {"name": "🎨 طبيعي",              "description": "مستوحى من الطبيعة",         "bg": (30,50,30),    "accent": (39,174,96),   "fc": (255,255,255)},
    11: {"name": "🎨 سحابي",              "description": "خلفية سحابية ناعمة",        "bg": (100,120,140), "accent": (236,240,241), "fc": (44,62,80)},
    12: {"name": "🎨 ثلاثي الأبعاد",      "description": "تأثيرات عمق وإضاءة",       "bg": (40,35,50),    "accent": (241,196,15),  "fc": (255,255,255)},
    13: {"name": "🎨 ورق عتيق",           "description": "كتب قديمة تاريخية",         "bg": (210,180,140), "accent": (139,69,19),   "fc": (60,40,20)},
    14: {"name": "🎨 عصري متدرج",         "description": "تدرجات لونية جذابة",        "bg": (75,25,95),    "accent": (155,89,182),  "fc": (255,255,255)},
    15: {"name": "🎨 AI مخصص",            "description": "تصميم بالذكاء الاصطناعي",  "bg": None,          "accent": None,          "fc": (255,255,255)},
}

POLLINATIONS_URL = "https://image.pollinations.ai/prompt/"

async def generate_ai_image(prompt: str, W=1080, H=1350) -> BytesIO:
    try:
        enc = prompt.replace(" ", "%20").replace("\n", "%20")
        url = f"{POLLINATIONS_URL}{enc}?width={W}&height={H}&model=flux"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=60)) as r:
                if r.status == 200:
                    buf = BytesIO(await r.read()); buf.seek(0); return buf
    except Exception as e:
        logger.error(f"Pollinations error: {e}")
    return _fallback_image(prompt)

def _fallback_image(text: str) -> BytesIO:
    img  = Image.new("RGB", (1080, 1350), (30, 30, 60))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    for i, chunk in enumerate([text[j:j+35] for j in range(0, len(text), 35)][:14]):
        draw.text((50, 380 + i * 44), chunk, fill=(255, 255, 255), font=font)
    buf = BytesIO(); img.save(buf, "PNG"); buf.seek(0); return buf

async def create_marketing_image(style_id: int, title: str, author: str, ad_text: str, variation=1) -> BytesIO:
    s = AD_STYLES.get(style_id, AD_STYLES[1])
    W, H = 1080, 1350
    if style_id == 15:
        return await generate_ai_image(
            f'Professional Arabic book ad. Book: "{title}" by {author}. Copy: "{ad_text}". Elegant social media.', W, H)
    bg     = s["bg"]     or (30, 30, 60)
    accent = s["accent"] or (218, 165, 32)
    fc     = s["fc"]
    img    = Image.new("RGB", (W, H), bg)
    draw   = ImageDraw.Draw(img)
    font   = ImageFont.load_default()
    draw.rectangle([10, 10, W-10, H-10], outline=accent, width=12)
    draw.rectangle([25, 25, W-25, H-25], outline=accent, width=3)
    logo = "🦌 Deer Books"
    bb = draw.textbbox((0,0), logo, font=font)
    draw.text(((W-(bb[2]-bb[0]))//2, 55), logo, fill=accent, font=font)
    draw.line([(60,88),(W-60,88)], fill=accent, width=2)
    draw.rectangle([120,200,W-120,580], outline=accent, width=3)
    bb  = draw.textbbox((0,0), title, font=font)
    tw  = bb[2]-bb[0]; tx = (W-tw)//2
    draw.rectangle([tx-15,490,tx+tw+15,530], fill=accent)
    draw.text((tx, 493), title, fill=(255,255,255) if sum(accent)<400 else (0,0,0), font=font)
    bb = draw.textbbox((0,0), f"✍  {author}", font=font)
    draw.text(((W-(bb[2]-bb[0]))//2, 545), f"✍  {author}", fill=(180,180,180), font=font)
    draw.line([(60,622),(W-60,622)], fill=accent, width=2)
    y = 655
    for line in (ad_text.split('\n') or ["اكتشف هذا الكتاب!"])[:6]:
        if y > H-160: break
        bb = draw.textbbox((0,0), line, font=font)
        draw.text(((W-(bb[2]-bb[0]))//2, y), line, fill=fc, font=font)
        y += 44
    draw.line([(60,H-120),(W-60,H-120)], fill=accent, width=2)
    ver = f"#{variation} | {datetime.now().strftime('%Y-%m-%d')}"
    bb  = draw.textbbox((0,0), ver, font=font)
    draw.text(((W-(bb[2]-bb[0]))//2, H-98), ver, fill=(130,130,130), font=font)
    buf = BytesIO(); img.save(buf, "PNG"); buf.seek(0); return buf

# ==================== لوحات المفاتيح ====================
def get_main_keyboard(user_id):
    kb = [
        [InlineKeyboardButton(t("btn_create_own_book", user_id),  callback_data="create_book")],
        [InlineKeyboardButton(t("btn_all_books", user_id),        callback_data="all_books"),
         InlineKeyboardButton(t("btn_categories", user_id),       callback_data="categories")],
        [InlineKeyboardButton(t("btn_stars_system", user_id),     callback_data="stars_system"),
         InlineKeyboardButton(t("btn_payment_methods", user_id),  callback_data="payment_methods")],
        [InlineKeyboardButton(t("btn_special_offers", user_id),   callback_data="special_offers"),
         InlineKeyboardButton(t("btn_about", user_id),            callback_data="about")],
        [InlineKeyboardButton(t("btn_language", user_id),         callback_data="language_menu"),
         InlineKeyboardButton(t("btn_share", user_id),            callback_data="share_bot")],
    ]
    if str(user_id) == ADMIN_ID:
        kb.append([InlineKeyboardButton(t("btn_control", user_id), callback_data="control_panel")])
    return InlineKeyboardMarkup(kb)

def get_control_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 إدارة الكتب",          callback_data="admin_books_mgmt")],
        [InlineKeyboardButton("🏷️ إدارة التصنيفات",      callback_data="admin_categories_mgmt")],
        [InlineKeyboardButton("✨ إنشاء كتاب (مجاني)",   callback_data="admin_create_free_book")],
        [InlineKeyboardButton("🎨 إعلان تسويقي",         callback_data="admin_create_ad")],
        [InlineKeyboardButton("📊 الإحصائيات",           callback_data="admin_stats")],
        [InlineKeyboardButton("📢 إشعار جماعي",          callback_data="admin_broadcast")],
        [InlineKeyboardButton("💰 إدارة المحافظ",        callback_data="admin_wallets")],
        [InlineKeyboardButton("💾 نسخ احتياطي",          callback_data="admin_backup")],
        [InlineKeyboardButton("🏠 القائمة الرئيسية",    callback_data="back_to_main")],
    ])

def get_books_mgmt_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة كتاب",   callback_data="admin_add_book")],
        [InlineKeyboardButton("✏️ تعديل كتاب",  callback_data="admin_edit_book")],
        [InlineKeyboardButton("❌ حذف كتاب",    callback_data="admin_delete_book")],
        [InlineKeyboardButton("📋 عرض الكتب",   callback_data="admin_list_books")],
        [InlineKeyboardButton("🔙 رجوع",        callback_data="control_panel")],
    ])

def get_cats_mgmt_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة تصنيف",  callback_data="admin_add_category")],
        [InlineKeyboardButton("✏️ تعديل تصنيف", callback_data="admin_edit_category")],
        [InlineKeyboardButton("❌ حذف تصنيف",   callback_data="admin_delete_category")],
        [InlineKeyboardButton("📋 عرض التصنيفات",callback_data="admin_list_categories")],
        [InlineKeyboardButton("🔙 رجوع",         callback_data="control_panel")],
    ])

def back_btn(user_id, dest="back_to_main"):
    return InlineKeyboardMarkup([[InlineKeyboardButton(t("back_button", user_id), callback_data=dest)]])

# ==================== الأوامر ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    data_manager.get_user(user_id)
    if user_id != ADMIN_ID:
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"👤 *مستخدم جديد:* {update.effective_user.first_name}\n🆔 ID: `{user_id}`",
                parse_mode="Markdown",
            )
        except Exception:
            pass
    await update.message.reply_text(t("welcome", user_id), reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")

# ==================== معالج الأزرار ====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    user_id = str(update.effective_user.id)
    await query.answer()
    d = query.data

    try:
        # ── القائمة الرئيسية ──
        if d == "back_to_main":
            await query.edit_message_text(t("welcome", user_id), reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")

        elif d == "language_menu":
            await query.edit_message_text(
                "🌐 *اختر لغتك / Choose your language:*",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🇸🇦 العربية", callback_data="set_lang_ar")],
                    [InlineKeyboardButton("🇬🇧 English", callback_data="set_lang_en")],
                    [InlineKeyboardButton(t("back_button", user_id), callback_data="back_to_main")],
                ]), parse_mode="Markdown")

        elif d.startswith("set_lang_"):
            set_lang(user_id, d.split("_")[-1])
            await query.edit_message_text(t("welcome", user_id), reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")

        elif d == "share_bot":
            info = await context.bot.get_me()
            await query.edit_message_text(
                f"📚 *شارك بوت Deer Books!*\n\n🔗 https://t.me/{info.username}\n\n🎁 كل من ينضم عبرك يمنحك نجوم إضافية!",
                reply_markup=back_btn(user_id), parse_mode="Markdown")

        # ── الكتب ──
        elif d == "all_books":
            if not data_manager.books:
                await query.edit_message_text("📚 لا توجد كتب متاحة حالياً.", reply_markup=back_btn(user_id), parse_mode="Markdown")
                return
            text = "📚 *جميع الكتب:*\n\n"
            kb = []
            for bid, book in data_manager.books.items():
                p = book.get("price", 5)
                text += f"📖 *{book['title']}* — {book.get('author','')} {'🆓' if p==0 else f'⭐{p}'}\n"
                kb.append([InlineKeyboardButton(f"📖 {book['title']}", callback_data=f"book_{bid}")])
            kb.append([InlineKeyboardButton(t("back_button", user_id), callback_data="back_to_main")])
            await query.edit_message_text(text[:4000], reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

        elif d.startswith("book_"):
            bid  = d[5:]
            book = data_manager.books.get(bid)
            if not book:
                await query.answer("❌ الكتاب غير موجود"); return
            user  = data_manager.get_user(user_id)
            stars = user.get("stars", 0)
            price = book.get("price", 5)
            text  = (f"📖 *{book['title']}*\n\n👤 *المؤلف:* {book.get('author','—')}\n"
                     f"📝 *الوصف:* {book.get('description','—')}\n"
                     f"{'🆓 *مجاني*' if price==0 else f'⭐ *السعر:* {price} نجوم'}\n\n💫 *رصيدك:* {stars} نجمة")
            kb = []
            if price == 0 or stars >= price:
                kb.append([InlineKeyboardButton("📥 طلب الكتاب", callback_data=f"req_{bid}")])
            else:
                kb.append([InlineKeyboardButton(f"💳 شراء ({price} نجوم)", callback_data="payment_methods")])
            kb.append([InlineKeyboardButton(t("back_button", user_id), callback_data="all_books")])
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

        elif d.startswith("req_"):
            bid  = d[4:]
            book = data_manager.books.get(bid, {})
            await query.edit_message_text(
                f"✅ تم تسجيل طلبك!\n📖 {book.get('title', bid)}\n\nستصلك الكتاب من الإدارة قريباً.",
                reply_markup=back_btn(user_id, "all_books"), parse_mode="Markdown")
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"📥 *طلب كتاب*\n👤 {update.effective_user.first_name} (`{user_id}`)\n📖 {book.get('title',bid)}",
                    parse_mode="Markdown")
            except Exception:
                pass

        # ── التصنيفات ──
        elif d == "categories":
            kb = [[InlineKeyboardButton(f"📂 {c['name']}", callback_data=f"cat_{c['id']}")] for c in data_manager.categories]
            kb.append([InlineKeyboardButton(t("back_button", user_id), callback_data="back_to_main")])
            await query.edit_message_text("📘 *التصنيفات:*", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

        elif d.startswith("cat_"):
            try:    cat_id = int(d[4:])
            except: cat_id = d[4:]
            cat      = next((c for c in data_manager.categories if c["id"] == cat_id), None)
            cat_name = cat["name"] if cat else str(cat_id)
            cat_books= {bid:b for bid,b in data_manager.books.items() if b.get("category_id")==cat_id}
            text = f"📂 *{cat_name}*\n\n" + ("لا توجد كتب في هذا التصنيف." if not cat_books else
                                               "\n".join(f"• {b['title']}" for b in cat_books.values()))
            kb = [[InlineKeyboardButton(f"📖 {b['title']}", callback_data=f"book_{bid}")] for bid,b in cat_books.items()]
            kb.append([InlineKeyboardButton(t("back_button", user_id), callback_data="categories")])
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

        # ── نجوم / دفع / عروض ──
        elif d == "stars_system":
            user  = data_manager.get_user(user_id)
            stars = user.get("stars", 0)
            await query.edit_message_text(
                f"⭐ *نظام النجوم*\n\n💫 *رصيدك:* {stars} نجمة\n\n"
                f"• قيمة النجمة = $1.2\n• شراء نجمة = $1\n• الكتاب = 5 نجوم\n\n"
                f"🌟 *كيف تكسب نجوم؟*\n• إكمال قراءة: +1\n• دعوة 5 أصدقاء: +1\n• تقييم كتاب: +1",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 شراء نجوم", callback_data="payment_methods")],
                    [InlineKeyboardButton(t("back_button", user_id), callback_data="back_to_main")],
                ]), parse_mode="Markdown")

        elif d == "payment_methods":
            await query.edit_message_text(
                f"💰 *طرق الدفع*\n\n"
                f"💎 *USDT (TRC20):*\n`{WALLETS['USDT_TRC20']}`\n\n"
                f"💎 *ETH / BSC:*\n`{WALLETS['ETH_BSC']}`\n\n"
                f"💎 *Bitcoin (BTC):*\n`{WALLETS['BTC']}`\n\n"
                f"🛡️ *بعد التحويل أرسل لقطة شاشة للإدارة*\n\n"
                f"📊 *الأسعار:*\n5⭐=$5 | 10⭐=$9 | 25⭐=$20 | 50⭐=$35",
                reply_markup=back_btn(user_id), parse_mode="Markdown")

        elif d == "special_offers":
            await query.edit_message_text(
                f"🎁 *العروض الخاصة*\n\n"
                f"1️⃣ اشتري 2 كتب واحصل على الثالث مجاناً\n"
                f"2️⃣ خصم 30% على أول كتاب: كود WELCOME30\n"
                f"3️⃣ اشترِ 10 نجوم واحصل على نجمتين مجاناً",
                reply_markup=back_btn(user_id), parse_mode="Markdown")

        elif d == "about":
            await query.edit_message_text(
                f"🔗 *عن Deer Books*\n\n"
                f"مكتبتك الرقمية للكتب المالية والاستثمارية.\n\n"
                f"📚 {len(data_manager.books)} كتاب متاح\n"
                f"⭐ نظام نجوم ومكافآت\n"
                f"🌐 عروض خاصة يومية\n\n🦌 *Deer Books*",
                reply_markup=back_btn(user_id), parse_mode="Markdown")

        elif d == "create_book":
            context.user_data["admin_action"] = "create_book_user"
            await query.edit_message_text(
                "📝 *أرسل لي فكرة كتابك*\n\n• العنوان المقترح\n• الموضوع الرئيسي\n• عدد الصفحات التقريبي",
                reply_markup=back_btn(user_id), parse_mode="Markdown")

        # ── لوحة التحكم ──
        elif d == "control_panel" and user_id == ADMIN_ID:
            await query.edit_message_text("📋 *لوحة التحكم*\n\nاختر القسم:", reply_markup=get_control_keyboard(), parse_mode="Markdown")

        elif d == "admin_books_mgmt" and user_id == ADMIN_ID:
            await query.edit_message_text("📚 *إدارة الكتب*:", reply_markup=get_books_mgmt_keyboard(), parse_mode="Markdown")

        elif d == "admin_add_book" and user_id == ADMIN_ID:
            context.user_data["admin_action"] = "add_book"
            await query.edit_message_text(
                "➕ *إضافة كتاب*\n\nأرسل بالتنسيق:\n`id|عنوان|مؤلف|سعر|تصنيف_id|وصف`\n\n"
                "مثال:\n`book_001|فكر كرجل أعمال|أحمد|6|1|كتاب رائع`",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 إلغاء", callback_data="admin_books_mgmt")]]),
                parse_mode="Markdown")

        elif d == "admin_edit_book" and user_id == ADMIN_ID:
            context.user_data["admin_action"] = "edit_book"
            await query.edit_message_text(
                "✏️ *تعديل كتاب*\n\nأرسل: `id|حقل|قيمة`\n\nالحقول: title, author, price, category_id, description\n\nمثال: `book_001|price|7`",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 إلغاء", callback_data="admin_books_mgmt")]]),
                parse_mode="Markdown")

        elif d == "admin_delete_book" and user_id == ADMIN_ID:
            context.user_data["admin_action"] = "delete_book"
            await query.edit_message_text("❌ *حذف كتاب*\n\nأرسل معرف الكتاب:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 إلغاء", callback_data="admin_books_mgmt")]]),
                parse_mode="Markdown")

        elif d == "admin_list_books" and user_id == ADMIN_ID:
            if not data_manager.books:
                await query.edit_message_text("📚 لا توجد كتب.", reply_markup=get_books_mgmt_keyboard(), parse_mode="Markdown")
            else:
                text = "📚 *الكتب:*\n\n" + "\n".join(f"📖 `{bid}`: {b['title']} — ${b.get('price',0)}" for bid,b in data_manager.books.items())
                await query.edit_message_text(text[:4000], reply_markup=get_books_mgmt_keyboard(), parse_mode="Markdown")

        elif d == "admin_categories_mgmt" and user_id == ADMIN_ID:
            await query.edit_message_text("🏷️ *إدارة التصنيفات*:", reply_markup=get_cats_mgmt_keyboard(), parse_mode="Markdown")

        elif d == "admin_add_category" and user_id == ADMIN_ID:
            context.user_data["admin_action"] = "add_category"
            await query.edit_message_text(
                "➕ *إضافة تصنيف*\n\nأرسل: `id|عربي|english`\n\nمثال: `6|الذكاء الاصطناعي|AI`",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 إلغاء", callback_data="admin_categories_mgmt")]]),
                parse_mode="Markdown")

        elif d == "admin_delete_category" and user_id == ADMIN_ID:
            context.user_data["admin_action"] = "delete_category"
            await query.edit_message_text("❌ *حذف تصنيف*\n\nأرسل رقم معرف التصنيف:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 إلغاء", callback_data="admin_categories_mgmt")]]),
                parse_mode="Markdown")

        elif d == "admin_list_categories" and user_id == ADMIN_ID:
            text = "🏷️ *التصنيفات:*\n\n" + "\n".join(f"📂 `{c['id']}`: {c['name']} / {c['name_en']}" for c in data_manager.categories)
            await query.edit_message_text(text, reply_markup=get_cats_mgmt_keyboard(), parse_mode="Markdown")

        elif d == "admin_broadcast" and user_id == ADMIN_ID:
            context.user_data["admin_action"] = "broadcast"
            await query.edit_message_text(
                "📢 *إشعار جماعي*\n\nأرسل الرسالة التي تريد إرسالها لجميع المستخدمين:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 إلغاء", callback_data="control_panel")]]),
                parse_mode="Markdown")

        elif d == "admin_stats" and user_id == ADMIN_ID:
            users_ar = sum(1 for u in data_manager.users.values() if u.get("language") == "ar")
            users_en = len(data_manager.users) - users_ar
            await query.edit_message_text(
                f"📊 *إحصائيات البوت*\n\n"
                f"👥 المستخدمون: {len(data_manager.users)}\n   🇸🇦 عربي: {users_ar} | 🇬🇧 EN: {users_en}\n\n"
                f"📚 الكتب: {len(data_manager.books)}\n"
                f"🏷️ التصنيفات: {len(data_manager.categories)}\n"
                f"⭐ إجمالي النجوم: {sum(u.get('stars',0) for u in data_manager.users.values())}\n\n"
                f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                reply_markup=back_btn(user_id, "control_panel"), parse_mode="Markdown")

        elif d == "admin_backup" and user_id == ADMIN_ID:
            backup = {"users": data_manager.users, "books": data_manager.books,
                      "categories": data_manager.categories, "wallets": WALLETS,
                      "timestamp": datetime.now().isoformat()}
            buf = BytesIO(json.dumps(backup, ensure_ascii=False, indent=2).encode("utf-8"))
            await context.bot.send_document(chat_id=user_id, document=buf, filename="deer_books_backup.json",
                                            caption="💾 نسخة احتياطية كاملة")
            await query.edit_message_text("✅ تم إرسال النسخة الاحتياطية!", reply_markup=back_btn(user_id, "control_panel"), parse_mode="Markdown")

        elif d == "admin_wallets" and user_id == ADMIN_ID:
            await query.edit_message_text(
                f"💰 *المحافظ:*\n\n💎 USDT TRC20:\n`{WALLETS['USDT_TRC20']}`\n\n"
                f"💎 ETH/BSC:\n`{WALLETS['ETH_BSC']}`\n\n💎 BTC:\n`{WALLETS['BTC']}`",
                reply_markup=back_btn(user_id, "control_panel"), parse_mode="Markdown")

        elif d == "admin_create_free_book" and user_id == ADMIN_ID:
            context.user_data["admin_action"] = "free_book"
            await query.edit_message_text("✨ *إنشاء كتاب مجاني*\n\nأرسل عنوان وموضوع الكتاب:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 إلغاء", callback_data="control_panel")]]),
                parse_mode="Markdown")

        elif d == "admin_create_ad" and user_id == ADMIN_ID:
            styles_list = "\n".join(f"*{i}* — {AD_STYLES[i]['name']}" for i in range(1, 16))
            kb, row = [], []
            for i in range(1, 16):
                row.append(InlineKeyboardButton(f"#{i}", callback_data=f"ad_style_{i}"))
                if len(row) == 5: kb.append(row); row = []
            if row: kb.append(row)
            kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="control_panel")])
            await query.edit_message_text(f"🎨 *اختر ستايل الإعلان:*\n\n{styles_list}",
                reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

        elif d.startswith("ad_style_") and user_id == ADMIN_ID:
            sid = int(d.split("_")[-1])
            context.user_data["ad_style_id"]  = sid
            context.user_data["admin_action"] = "ad_info"
            style = AD_STYLES[sid]
            await query.edit_message_text(
                f"✨ *ستايل {sid}: {style['name']}*\n📝 {style['description']}\n\n"
                f"أرسل (كل سطر منفصل):\n1️⃣ عنوان الكتاب\n2️⃣ اسم المؤلف\n3️⃣ النص التسويقي\n4️⃣ عدد الصور (1-20)",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 إلغاء", callback_data="control_panel")]]),
                parse_mode="Markdown")

    except Exception as e:
        logger.error(f"button_handler error: {e}", exc_info=True)
        try:
            await query.edit_message_text(t("error_occurred", user_id),
                reply_markup=back_btn(user_id), parse_mode="Markdown")
        except Exception:
            pass

# ==================== معالج الرسائل ====================
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    text    = update.message.text.strip()
    action  = context.user_data.get("admin_action")

    if action == "broadcast" and user_id == ADMIN_ID:
        context.user_data.pop("admin_action", None)
        sent = failed = 0
        await update.message.reply_text(f"📢 جاري الإرسال لـ {len(data_manager.users)} مستخدم...")
        for uid in data_manager.users:
            try:
                await context.bot.send_message(int(uid), f"📢 *Deer Books:*\n\n{text}", parse_mode="Markdown")
                sent += 1; await asyncio.sleep(0.08)
            except Exception: failed += 1
        await update.message.reply_text(f"✅ أُرسلت: {sent} | ❌ فشل: {failed}")

    elif action == "add_book" and user_id == ADMIN_ID:
        context.user_data.pop("admin_action", None)
        parts = [p.strip() for p in text.split("|")]
        if len(parts) < 4:
            await update.message.reply_text("❌ التنسيق: `id|عنوان|مؤلف|سعر|تصنيف|وصف`", parse_mode="Markdown"); return
        bid, title, author, price = parts[0], parts[1], parts[2], parts[3]
        cat_id = int(parts[4]) if len(parts) > 4 else 1
        desc   = parts[5] if len(parts) > 5 else ""
        data_manager.add_book(bid, title, author, float(price), cat_id, desc)
        await update.message.reply_text(f"✅ تمت إضافة: *{title}*", parse_mode="Markdown")

    elif action == "delete_book" and user_id == ADMIN_ID:
        context.user_data.pop("admin_action", None)
        msg = f"✅ تم حذف: `{text}`" if data_manager.delete_book(text) else "❌ لم يُعثر على الكتاب."
        await update.message.reply_text(msg, parse_mode="Markdown")

    elif action == "edit_book" and user_id == ADMIN_ID:
        context.user_data.pop("admin_action", None)
        parts = [p.strip() for p in text.split("|")]
        if len(parts) < 3:
            await update.message.reply_text("❌ التنسيق: `id|حقل|قيمة`", parse_mode="Markdown"); return
        bid, field, val = parts[0], parts[1], parts[2]
        if field == "price":    val = float(val)
        elif field == "category_id": val = int(val)
        msg = f"✅ تم تعديل `{field}`" if data_manager.update_book(bid, **{field: val}) else "❌ لم يُعثر على الكتاب."
        await update.message.reply_text(msg, parse_mode="Markdown")

    elif action == "add_category" and user_id == ADMIN_ID:
        context.user_data.pop("admin_action", None)
        parts = [p.strip() for p in text.split("|")]
        if len(parts) < 3:
            await update.message.reply_text("❌ التنسيق: `id|عربي|english`", parse_mode="Markdown"); return
        data_manager.add_category(int(parts[0]), parts[1], parts[2])
        await update.message.reply_text(f"✅ تمت إضافة التصنيف: *{parts[1]}*", parse_mode="Markdown")

    elif action == "delete_category" and user_id == ADMIN_ID:
        context.user_data.pop("admin_action", None)
        msg = "✅ تم حذف التصنيف." if data_manager.delete_category(int(text)) else "❌ لم يُعثر على التصنيف."
        await update.message.reply_text(msg)

    elif action == "ad_info" and user_id == ADMIN_ID:
        context.user_data.pop("admin_action", None)
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if len(lines) < 4:
            await update.message.reply_text("❌ أرسل 4 أسطر: عنوان / مؤلف / نص / عدد الصور"); return
        title, author = lines[0], lines[1]
        ad_text = "\n".join(lines[2:-1]) or lines[2]
        try:    num = max(1, min(int(lines[-1]), 20))
        except: num = 1
        sid = context.user_data.get("ad_style_id", 1)
        await update.message.reply_text(f"⏳ جاري إنشاء {num} صورة بالستايل #{sid}...")
        sent = 0
        for i in range(num):
            try:
                img = await create_marketing_image(sid, title, author, ad_text, i+1)
                img.seek(0)
                await context.bot.send_photo(user_id, img, caption=f"🎨 {i+1}/{num} | {title}")
                sent += 1; await asyncio.sleep(0.4)
            except Exception as e:
                logger.error(f"Ad image {i+1}: {e}")
        await update.message.reply_text(f"✅ تم إرسال {sent}/{num} صورة!")

    elif action == "free_book" and user_id == ADMIN_ID:
        context.user_data.pop("admin_action", None)
        bid = f"free_{int(datetime.now().timestamp())}"
        data_manager.add_book(bid, f"دليل {text}", "Deer Books", 0, 1, f"كتاب مجاني عن {text}")
        await update.message.reply_text(f"✅ تمت إضافة: *دليل {text}*", parse_mode="Markdown")

    elif action == "create_book_user":
        context.user_data.pop("admin_action", None)
        await update.message.reply_text("✅ *شكراً!*\n\nتم استلام فكرتك وسيتواصل معك فريقنا قريباً.\n🦌 Deer Books", parse_mode="Markdown")
        try:
            await context.bot.send_message(ADMIN_ID, f"📝 *طلب كتاب جديد*\n👤 {update.effective_user.first_name} (`{user_id}`)\n\n{text}", parse_mode="Markdown")
        except Exception:
            pass

    else:
        await update.message.reply_text(t("welcome", user_id), reply_markup=get_main_keyboard(user_id), parse_mode="Markdown")

# ==================== معالج الأخطاء ====================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"خطأ: {context.error}", exc_info=context.error)

# ==================== الدالة الرئيسية (Webhook) ====================

# المتغير العالمي للـ Application
_application: Optional[Application] = None

# حلقة asyncio تعمل في خيط خلفي
_loop = asyncio.new_event_loop()

def _start_loop():
    asyncio.set_event_loop(_loop)
    _loop.run_forever()

Thread(target=_start_loop, daemon=True).start()

# ==================== Flask + Webhook ====================
flask_app = Flask(__name__)

@flask_app.route("/", methods=["GET"])
def index():
    return "🦌 Deer Books Bot — Webhook Mode ✅"

@flask_app.route(f"/{TOKEN}", methods=["POST"])
def telegram_webhook():
    """نقطة استقبال التحديثات من Telegram"""
    if _application is None:
        return "not ready", 503
    data   = request.get_json(force=True)
    update = Update.de_json(data, _application.bot)
    future = asyncio.run_coroutine_threadsafe(
        _application.process_update(update), _loop)
    try:
        future.result(timeout=30)
    except Exception as e:
        logger.error(f"process_update error: {e}")
    return "OK", 200

async def _init_application():
    """تهيئة البوت وضبط الـ Webhook"""
    global _application

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_error_handler(error_handler)

    await app.initialize()
    await app.start()
    _application = app

    # ضبط الـ Webhook تلقائياً
    domains = os.environ.get("REPLIT_DOMAINS", "")
    domain  = domains.split(",")[0].strip() if domains else ""

    # يمكن أيضاً تحديده يدوياً
    webhook_url_env = os.environ.get("WEBHOOK_URL", "")

    if webhook_url_env:
        wh_url = f"{webhook_url_env.rstrip('/')}/{TOKEN}"
    elif domain:
        wh_url = f"https://{domain}/{TOKEN}"
    else:
        wh_url = None

    if wh_url:
        await app.bot.set_webhook(
            url=wh_url,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )
        logger.info(f"✅ Webhook تم ضبطه على: {wh_url}")
    else:
        logger.warning("⚠️  لم يُعثر على WEBHOOK_URL — البوت في وضع الانتظار فقط.")

    logger.info("🦌 Deer Books Bot جاهز!")

def main():
    # تهيئة البوت في الحلقة الخلفية
    asyncio.run_coroutine_threadsafe(_init_application(), _loop).result(timeout=30)

    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🌐 Flask يعمل على المنفذ {port}")
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    main()
