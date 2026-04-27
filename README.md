# 🦌 Deer Books Bot

بوت Telegram لمكتبة رقمية متخصصة في كتب الأعمال والاستثمار والتداول.

## المميزات
- 📚 عرض وتصفح الكتب بالتصنيفات
- ⭐ نظام النجوم والمكافآت
- 💰 عرض طرق الدفع (USDT / ETH / BTC)
- 🎨 إنشاء إعلانات تسويقية بـ 15 ستايل
- 📢 إشعارات جماعية لجميع المستخدمين
- ⚙️ لوحة تحكم كاملة للمدير
- 🌐 دعم العربية والإنجليزية
- 🔗 **Webhook Mode** — سريع ومستقر

## متطلبات التشغيل
```bash
pip install -r requirements.txt
```

## متغيرات البيئة المطلوبة

| المتغير | الوصف |
|---------|-------|
| `BOT_TOKEN` | توكن البوت من @BotFather |
| `ADMIN_ID` | معرف حساب المدير |
| `WEBHOOK_URL` | رابط الاستضافة (مثال: https://my-bot.koyeb.app) |
| `PORT` | المنفذ (افتراضي: 5000) |

## النشر على Koyeb

1. ارفع الكود على GitHub
2. أنشئ تطبيقاً جديداً على [koyeb.com](https://koyeb.com)
3. اربطه بـ GitHub Repository
4. أضف متغيرات البيئة:
   - `BOT_TOKEN` = توكنك
   - `ADMIN_ID` = معرفك
   - `WEBHOOK_URL` = `https://<app-name>.koyeb.app`
5. Start Command: `python main.py`
6. Port: `5000`

## تشغيل محلي
```bash
cp .env.example .env
# عدّل .env بقيمك الحقيقية
python main.py
```
