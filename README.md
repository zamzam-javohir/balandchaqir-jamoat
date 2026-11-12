# 🕌 Balandchaqir Jamoat — Telegram Mini App + bot

Balandchaqir qishlog'i (Yangiobod tumani, Jizzax viloyati) jamoasi uchun Telegram ichida ishlaydigan ilova. Hamma matnlar o'zbek tilida (lotin).

## Imkoniyatlar

| Bo'lim | Nima qiladi |
|---|---|
| 🕌 **Namoz** | Bugungi namoz vaqtlari (mahalliy hisoblanadi), keyingi namozgacha sanoq, **qibla** kompasi (qurilma datchigi bilan, bo'lmasa gradus), **tasbeh**, qisqa **duolar** |
| 🕋 **Jamoat** | Masjidda jamoat (iqomat) vaqtlari va Juma vaqti. **Adminlar** ilovaning o'zida tahrirlaydi |
| 🚗 **Birga** | «Bomdodga kim boradi?» (istalgan namozni tanlash mumkin). «Mashinada chiqaman, N joy bor» va «Mashinam yo'q, olib keting» e'lonlari; «Men ham boraman» / «Men olib ketaman» tugmalari e'lon egasiga bot orqali xabar yuboradi. E'lonlar chiqish vaqtidan 30 daqiqa o'tgach o'zi yo'qoladi, muallif o'chira oladi |
| ⚽ **Futbol** | «Bugun futbolga kim keladi?» — Ha/Yo'q, ismlar va hisob. Minimum (standart 10) to'lganda hammaga «O'yin bo'ladi!» xabari ketadi. Admin vaqt/joy/minimumni belgilaydi, yangi so'rovnoma ochadi yoki har kuni avtomatik ochilishini yoqadi |
| 👤 **Profil** | A'zolik: ism + telefon (Telegram kontakti orqali) → admin tasdiqlaydi. Tasdiqlanmaganlar jamoat bo'limlaridan foydalana olmaydi |

Texnik tomoni: Python 3.12 · aiogram 3 · FastAPI · SQLite · oddiy HTML/CSS/JS. Telegram `initData` har bir API so'rovda HMAC-SHA256 bilan tekshiriladi.

## Fayllar

```
main.py          FastAPI backend + bot ishga tushirish + rejalashtiruvchi
bot_logic.py     Telegram bot (/start, kontakt, tasdiqlash tugmalari, zaxira nusxa)
auth.py          initData HMAC tekshiruvi
prayer.py        namoz vaqtlari va qibla hisobi
db.py, config.py SQLite va sozlamalar
static/          index.html, app.css, app.js, duolar.js (Mini App)
tests/           test_api.py (API testi), screenshots.py (skrinshotlar)
render.yaml      Render.com uchun (bepul reja)
```

## 1-qadam. Botni yaratish (@BotFather)

1. Telegramda **@BotFather** → `/newbot` → nom (masalan, *Balandchaqir Jamoat*) va username (masalan, `balandchaqirjamoatbot`) bering.
2. BotFather bergan **tokenni** saqlang (hech kimga bermang!).
3. Adminlarning **Telegram ID** sini bilib oling: har bir admin **@userinfobot** ga `/start` yozsa, raqamli ID chiqadi.

## 2-qadam. Lokal ishga tushirish (sinov uchun)

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export BOT_TOKEN="123456:ABC..."     # Windows: set BOT_TOKEN=...
export ADMIN_IDS="123456789"
export MODE=polling
python main.py                       # http://localhost:8000
```

Mini App faqat **HTTPS** manzildan ochiladi, shuning uchun lokal sinov uchun tunnel kerak (masalan, `cloudflared tunnel --url http://localhost:8000`) va chiqqan `https://...` manzilni `WEBAPP_URL` ga yozing.

Testlar (internet va token shart emas):
```bash
python tests/test_api.py             # API testi — 58 ta tekshiruv
pip install playwright && python tests/screenshots.py   # mobil skrinshotlar -> screens/
```

## 3-qadam. Render.com ga joylash (bepul)

1. Loyihani GitHub ga yuklang (yoki Render'da *New → Web Service → Public/Private Git repo*). Fayllar repo ildizida bo'lsin (`render.yaml` bor).
2. Render'da **New → Blueprint** (yoki Web Service) → repo'ni tanlang. `render.yaml` hamma narsani o'zi sozlaydi.
3. **Environment** bo'limida kiriting:
   - `BOT_TOKEN` — BotFather tokeni
   - `ADMIN_IDS` — adminlar ID si, vergul bilan (`111111111,222222222`)
   - `WEBAPP_URL` — xizmat manzili, masalan `https://balandchaqir-jamoat.onrender.com` (oxirida `/` bo'lmasin). Bo'sh qoldirsangiz, Render'ning `RENDER_EXTERNAL_URL` i ishlatiladi.
4. **Deploy**. Birinchi ishga tushishda bot webhook'ni o'zi o'rnatadi va chat menyusidagi **«Jamoat»** tugmasini Mini App'ga bog'laydi.
5. Botga `/start` yozing — «🕌 Ilovani ochish» tugmasi chiqadi.

### Mini App ni BotFather'da ham ro'yxatdan o'tkazish (ixtiyoriy, tavsiya)
- `/newapp` → botni tanlang → nom, tavsif, rasm (640×360) → **Web App URL** = `WEBAPP_URL` → qisqa nom (masalan `jamoat`). Shunda `t.me/<bot>/jamoat` havolasi bilan ham ochiladi.
- Yoki `/setmenubutton` → botni tanlang → URL va tugma nomi («Jamoat»). (Bot buni o'zi ham qiladi.)
- `/setcommands` → `start - Ilovani ochish`, `help - Yordam`.

### ⚠️ Bepul Render'ning cheklovlari
- **Uxlab qoladi:** 15 daqiqa so'rov bo'lmasa xizmat uxlaydi, birinchi ochilish ~30–50 soniya oladi. Oldini olish: bepul **UptimeRobot** da `https://<manzil>/health` ni har 5 daqiqada tekshiradigan monitor qo'shing.
- **Baza o'chib ketadi:** bepul rejada fayl tizimi doimiy emas (qayta deploy/restartda `jamoat.db` yo'qoladi). Himoya: bot har kuni ~03:00 dan keyin **adminlarga baza nusxasini Telegramga yuboradi** (yoki admin `/backup` yozadi). Tiklash: nusxa faylni botga yuboring va izohiga `/restore` yozing. Mutlaqo xavfsiz yechim — pullik Render *Disk* ulab, `DB_PATH=/var/data/jamoat.db` qo'yish yoki kichik VPS ishlatish.

## Admin bo'lish
- `ADMIN_IDS` dagilar avtomatik admin va tasdiqlangan a'zo.
- Qo'shimcha: `ADMIN_SETUP_CODE=maxfiy` o'rnatilsa, ishonchli odam botga `/admin maxfiy` yozib admin bo'ladi (ishlatib bo'lgach kodni o'chiring).
- Yangi a'zo ro'yxatdan o'tganda adminlarga **✅ Tasdiqlash / ❌ Rad etish** tugmali xabar keladi (yoki Profil → «A'zolarni boshqarish»).

## Sozlamalar (env)

| O'zgaruvchi | Izoh |
|---|---|
| `BOT_TOKEN` | Bot tokeni (zaxira nomi: `BALANDCHAQIR_BOT_TOKEN`) |
| `WEBAPP_URL` | Mini App'ning https manzili |
| `ADMIN_IDS` | Admin Telegram ID lari |
| `MODE` | `webhook` (Render, standart) yoki `polling` (lokal) |
| `DB_PATH` | SQLite fayl yo'li |
| `LAT`, `LNG`, `PLACE_NAME` | Namoz vaqti koordinatalari (standart 39.96, 68.78 — Balandchaqir/Yangiobod) |
| `ADMIN_SETUP_CODE` | `/admin <kod>` uchun (ixtiyoriy) |

## Namoz vaqtlari haqida
Vaqtlar server ichida astronomik formulalar bilan hisoblanadi (Muslim World League: bomdod 18°, xufton 17°; **Asr — hanafiy**, UTC+5). Internet yoki tashqi API kerak emas. O'zbekiston Musulmonlar idorasi taqvimidan 1–3 daqiqa farq bo'lishi mumkin — **Jamoat → Tahrirlash → «Namoz vaqtlarini tuzatish»** orqali admin har bir namoz uchun daqiqalarni (−30…+30) to'g'rilaydi. Masjidning amaldagi jamoat vaqtlari esa alohida kiritiladi.

## Xavfsizlik
- Har bir API chaqiruv `X-Init-Data` (Telegram imzosi) bilan tekshiriladi, eskirgan (3 kundan oshgan) yoki o'zgartirilgan ma'lumot rad etiladi.
- Jamoat bo'limlari faqat admin tasdiqlagan a'zolarga ochiq; admin amallari serverda alohida tekshiriladi.
- Telefon raqam faqat tasdiqlangan a'zolarga, e'lon egasi ruxsat bergandagina ko'rinadi.
- Duolar matni faqat mashhur, ishonchli manbalardan; baribir diniy matnlarni imom/ustoz bilan solishtirib turing.
