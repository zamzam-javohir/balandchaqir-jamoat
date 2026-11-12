"""Telegram bot: /start, kontakt, admin tugmalari, xabarnomalar."""
import asyncio, html, logging, os, sqlite3, tempfile
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.types import (CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup,
                           KeyboardButton, Message, ReplyKeyboardMarkup, ReplyKeyboardRemove,
                           WebAppInfo, MenuButtonWebApp, MenuButtonDefault)
import config, db

log = logging.getLogger("bot")
router = Router()
bot: Bot | None = None


def make_bot() -> Bot:
    return Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


def app_kb(text="🕌 Ilovani ochish") -> InlineKeyboardMarkup | None:
    if not config.WEBAPP_URL.startswith("https://"):
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, web_app=WebAppInfo(url=config.WEBAPP_URL))]])


def contact_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True)


def user_link(row) -> str:
    return f'<a href="tg://user?id={row["tg_id"]}">{html.escape(db.display_name(row))}</a>'


async def safe_send(chat_id: int, text: str, **kw) -> bool:
    if bot is None:
        return False
    try:
        await bot.send_message(chat_id, text, **kw)
        return True
    except Exception as e:  # bloklagan, topilmadi va h.k.
        log.warning("send to %s failed: %s", chat_id, e)
        return False


async def broadcast(text: str, ids: list[int] | None = None, with_button=True) -> int:
    ids = db.approved_ids() if ids is None else ids
    ok = 0
    kb = app_kb() if with_button else None
    for uid in ids:
        if await safe_send(uid, text, reply_markup=kb):
            ok += 1
        await asyncio.sleep(0.05)
    return ok


async def notify_admins_new_user(row):
    txt = (f"🆕 <b>Yangi a'zo so'rovi</b>\n👤 {user_link(row)}"
           f"{' (@' + row['username'] + ')' if row.get('username') else ''}\n"
           f"📞 {html.escape(row.get('phone') or '—')}")
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"ap:{row['tg_id']}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"rj:{row['tg_id']}")]])
    for a in db.admin_ids():
        await safe_send(a, txt, reply_markup=kb)


async def set_status(uid: int, status: str):
    db.x("UPDATE users SET status=?, updated_at=? WHERE tg_id=?", (status, db.now_str(), uid))
    if status == "approved":
        await safe_send(uid, "✅ Arizangiz tasdiqlandi! Endi ilovadan to'liq foydalanishingiz mumkin.", reply_markup=app_kb())
    elif status == "rejected":
        await safe_send(uid, "❌ Afsuski, arizangiz rad etildi. Savol bo'lsa jamoat adminiga murojaat qiling.")


@router.message(Command("start"))
async def cmd_start(m: Message):
    row = db.upsert_tg_user({"id": m.from_user.id, "first_name": m.from_user.first_name, "username": m.from_user.username})
    st = row["status"]
    if st == "approved":
        txt = ("Assalomu alaykum! 🕌 <b>Balandchaqir Jamoat</b> ilovasiga xush kelibsiz.\n\n"
               "Namoz vaqtlari, jamoat vaqtlari, masjidga birga borish va jamoat futboli — hammasi bitta joyda.")
        await m.answer(txt, reply_markup=app_kb() or ReplyKeyboardRemove())
    elif st == "pending":
        await m.answer("⏳ Arizangiz ko'rib chiqilmoqda. Admin tasdiqlagach, xabar beramiz.", reply_markup=app_kb())
    elif st == "rejected":
        await m.answer("❌ Arizangiz rad etilgan. Jamoat adminiga murojaat qiling.")
    else:
        await m.answer("Assalomu alaykum! 🕌 <b>Balandchaqir Jamoat</b> — qishloq jamoasi uchun ilova.\n\n"
                       "Ro'yxatdan o'tish uchun pastdagi tugma orqali telefon raqamingizni yuboring, "
                       "yoki ilovani ochib ma'lumotlarni kiriting. Admin tasdiqlagach, to'liq foydalanasiz.",
                       reply_markup=contact_kb())
        kb = app_kb()
        if kb:
            await m.answer("Yoki ilovani ochib ro'yxatdan o'ting:", reply_markup=kb)


@router.message(F.contact)
async def on_contact(m: Message):
    c = m.contact
    row = db.upsert_tg_user({"id": m.from_user.id, "first_name": m.from_user.first_name, "username": m.from_user.username})
    verified = 1 if c.user_id == m.from_user.id else 0
    if not verified:
        await m.answer("Iltimos, o'zingizning raqamingizni yuboring.")
        return
    phone = c.phone_number if c.phone_number.startswith("+") else "+" + c.phone_number
    name = row.get("name") or " ".join(x for x in [c.first_name, c.last_name] if x)
    db.x("UPDATE users SET phone=?, phone_verified=1, name=?, updated_at=? WHERE tg_id=?",
         (phone, name, db.now_str(), m.from_user.id))
    row = db.get_user(m.from_user.id)
    if row["status"] == "new":
        db.x("UPDATE users SET status='pending' WHERE tg_id=?", (row["tg_id"],))
        row = db.get_user(row["tg_id"])
        await m.answer("Rahmat! Arizangiz adminga yuborildi. Tasdiqlangach xabar beramiz. ⏳", reply_markup=ReplyKeyboardRemove())
        await notify_admins_new_user(row)
    else:
        await m.answer("Telefon raqamingiz saqlandi. ✅", reply_markup=ReplyKeyboardRemove())


@router.callback_query(F.data.regexp(r"^(ap|rj):\d+$"))
async def on_admin_cb(cb: CallbackQuery):
    me = db.get_user(cb.from_user.id)
    if not db.is_admin(me):
        await cb.answer("Faqat adminlar uchun", show_alert=True)
        return
    act, uid = cb.data.split(":")
    uid = int(uid)
    await set_status(uid, "approved" if act == "ap" else "rejected")
    u = db.get_user(uid)
    mark = "✅ Tasdiqlandi" if act == "ap" else "❌ Rad etildi"
    try:
        await cb.message.edit_text(cb.message.html_text + f"\n\n<b>{mark}</b> — {html.escape(db.display_name(me))}")
    except Exception:
        pass
    await cb.answer(mark)


@router.message(Command("admin"))
async def cmd_admin(m: Message, command: CommandObject):
    if not config.ADMIN_SETUP_CODE or (command.args or "").strip() != config.ADMIN_SETUP_CODE:
        await m.answer("Kod noto'g'ri yoki admin kodi sozlanmagan.")
        return
    db.upsert_tg_user({"id": m.from_user.id, "first_name": m.from_user.first_name, "username": m.from_user.username})
    db.x("UPDATE users SET is_admin=1, status='approved' WHERE tg_id=?", (m.from_user.id,))
    await m.answer("✅ Siz endi adminsiz. Ilovani oching.", reply_markup=app_kb())


@router.message(Command("backup"))
async def cmd_backup(m: Message):
    if not db.is_admin(db.get_user(m.from_user.id)):
        return
    await send_backup(m.from_user.id)


async def send_backup(chat_id: int):
    path = os.path.join(tempfile.gettempdir(), f"jamoat_{db.now().strftime('%Y%m%d_%H%M')}.db")
    src = db.connect()
    dst = sqlite3.connect(path)
    src.backup(dst)
    dst.close(); src.close()
    try:
        await bot.send_document(chat_id, FSInputFile(path), caption="🗄 Ma'lumotlar bazasi nusxasi. Tiklash uchun shu faylni qaytarib yuboring va izohga /restore yozing.")
    finally:
        os.remove(path)


@router.message(F.document, F.caption.startswith("/restore"))
async def cmd_restore(m: Message):
    if not db.is_admin(db.get_user(m.from_user.id)):
        return
    tmp = os.path.join(tempfile.gettempdir(), "restore.db")
    await bot.download(m.document, destination=tmp)
    try:
        t = sqlite3.connect(tmp)
        t.execute("SELECT count(*) FROM users"); t.execute("SELECT count(*) FROM rides")
        with db._lock:
            dst = db.connect()
            t.backup(dst)
            dst.close()
        t.close()
        db.init()
        await m.answer("✅ Baza tiklandi.")
    except Exception as e:
        await m.answer(f"❌ Tiklab bo'lmadi: {html.escape(str(e))}")


@router.message(Command("help"))
async def cmd_help(m: Message):
    await m.answer("/start — ilovani ochish\n/help — yordam\n\nAdminlar uchun: /backup — baza nusxasi")


@router.message()
async def fallback(m: Message):
    await m.answer("Ilovani ochish uchun /start bosing.", reply_markup=app_kb())


def make_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(router)
    return dp


async def setup_menu():
    if config.WEBAPP_URL.startswith("https://"):
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Jamoat", web_app=WebAppInfo(url=config.WEBAPP_URL)))
    else:  # WEBAPP_URL (https) yo'q bo'lsa, menyu tugmasini standart holatga qaytaramiz
        await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
