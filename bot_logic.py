"""Telegram bot: /start, kontakt, admin tugmalari, xabarnomalar."""
import asyncio, html, logging, os, sqlite3, tempfile, time
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramRetryAfter
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


async def safe_location(chat_id: int, lat: float, lon: float) -> bool:
    if bot is None:
        return False
    try:
        await bot.send_location(chat_id, lat, lon)
        return True
    except Exception as e:
        log.warning("location to %s failed: %s", chat_id, e)
        return False


async def _send_retry(chat_id: int, text: str, kb=None):
    """Xabar yuboradi; message_id qaytaradi. Bloklagan/xato bo'lsa None (e'tiborsiz)."""
    if bot is None:
        return None
    for attempt in (1, 2):
        try:
            m = await bot.send_message(chat_id, text, reply_markup=kb)
            return m.message_id
        except TelegramRetryAfter as e:
            if attempt == 2:
                return None
            await asyncio.sleep(min(float(e.retry_after), 30))
        except Exception as e:  # bloklagan, topilmadi va h.k.
            log.debug("send to %s failed: %s", chat_id, e)
            return None
    return None


BROADCAST_DELAY = 0.04  # ~25 xabar/soniya


async def broadcast(text: str, ids: list[int] | None = None, with_button=True, track=None, exclude=()) -> int:
    """Tasdiqlangan a'zolarga xabar. track=(tur, id) bo'lsa chat_id/message_id saqlanadi (keyin o'chirish uchun)."""
    skip = set(exclude)
    ids = [i for i in (db.approved_ids() if ids is None else ids) if i not in skip]
    ok = 0
    kb = app_kb() if with_button else None
    for uid in ids:
        mid = await _send_retry(uid, text, kb)
        if mid is not None:
            ok += 1
            if track:
                db.x("INSERT INTO bcasts(kind,ref_id,chat_id,message_id,created_at) VALUES(?,?,?,?,?)",
                     (track[0], track[1], uid, mid, db.now_str()))
        await asyncio.sleep(BROADCAST_DELAY)
    return ok


async def retire_broadcasts(kind: str, ref_id: int, text: str = "⌛ Muddati o'tdi") -> int:
    """Saqlangan xabarlarni o'chiradi; o'chirib bo'lmasa matnini «Muddati o'tdi»ga o'zgartiradi."""
    rows = db.q("SELECT * FROM bcasts WHERE kind=? AND ref_id=?", (kind, ref_id))
    if bot is None:
        return 0
    n = 0
    for r in rows:
        try:
            await bot.delete_message(r["chat_id"], r["message_id"])
            n += 1
        except Exception:
            try:
                await bot.edit_message_text(text=text, chat_id=r["chat_id"], message_id=r["message_id"], reply_markup=None)
                n += 1
            except Exception as e:
                log.debug("retire %s/%s: %s", r["chat_id"], r["message_id"], e)
        db.x("DELETE FROM bcasts WHERE id=?", (r["id"],))
        await asyncio.sleep(BROADCAST_DELAY)
    return n


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


async def set_admin(uid: int, flag: bool, by=None):
    t = db.get_user(uid)
    if flag:
        db.x("UPDATE users SET is_admin=1, status='approved', updated_at=? WHERE tg_id=?", (db.now_str(), uid))
        if not (t and t["is_admin"]):
            who = f" ({html.escape(db.display_name(by))} tomonidan)" if by else ""
            await safe_send(uid, f"🛡 Siz Balandchaqir Jamoat <b>admini</b> qilindingiz{who}. Ilovada admin imkoniyatlari ochildi.", reply_markup=app_kb())
    else:
        db.x("UPDATE users SET is_admin=0, updated_at=? WHERE tg_id=?", (db.now_str(), uid))
        if t and t["is_admin"]:
            await safe_send(uid, "ℹ️ Sizning adminlik huquqingiz olib tashlandi.")


def find_user(arg: str):
    arg = (arg or "").strip()
    if arg.lstrip("@").isdigit():
        return db.get_user(int(arg.lstrip("@")))
    if arg.startswith("@") and len(arg) > 1:
        return db.q("SELECT * FROM users WHERE lower(username)=lower(?)", (arg[1:],), one=True)
    return None


@router.message(Command("addadmin"))
async def cmd_addadmin(m: Message, command: CommandObject):
    me = db.get_user(m.from_user.id)
    if not db.is_admin(me):
        return
    t = find_user(command.args)
    if not t:
        await m.answer("Foydalanuvchi topilmadi. Format: <code>/addadmin 123456789</code> yoki <code>/addadmin @username</code>.\n"
                       "U avval botga /start bosgan bo'lishi kerak.")
        return
    if t["tg_id"] == m.from_user.id or db.is_admin(t):
        await m.answer("Bu foydalanuvchi allaqachon admin.")
        return
    await set_admin(t["tg_id"], True, by=me)
    await m.answer(f"✅ {user_link(t)} admin qilindi.")


@router.message(Command("deladmin"))
async def cmd_deladmin(m: Message, command: CommandObject):
    me = db.get_user(m.from_user.id)
    if not db.is_admin(me):
        return
    t = find_user(command.args)
    if not t:
        await m.answer("Foydalanuvchi topilmadi. Format: <code>/deladmin 123456789</code> yoki <code>/deladmin @username</code>.")
        return
    if t["tg_id"] == m.from_user.id:
        await m.answer("O'zingizni adminlikdan ola olmaysiz.")
        return
    if t["tg_id"] in config.ADMIN_IDS:
        await m.answer("Bosh adminni adminlikdan olib bo'lmaydi.")
        return
    if not t["is_admin"]:
        await m.answer("Bu foydalanuvchi admin emas.")
        return
    await set_admin(t["tg_id"], False)
    await m.answer(f"✅ {user_link(t)} adminlikdan olindi.")


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


def _fmt_summary(s: dict) -> str:
    return (f"👥 A'zolar (tasdiqlangan): <b>{s['approved']}</b>\n⏳ Kutayotganlar: {s['pending']}\n🛡 Adminlar: {s['admins']}\n"
            f"🚗 E'lonlar: {s['rides']}\n🤝 Hasharlar: {s['hashars']}")


async def send_backup(chat_id: int):
    ext = "json" if db.use_pg() else "db"
    path = os.path.join(tempfile.gettempdir(), f"jamoat_{db.now().strftime('%Y%m%d_%H%M')}.{ext}")
    summ = db.current_summary()
    if db.use_pg():
        db.write_backup_json(path)
    else:
        src = db.connect()
        dst = sqlite3.connect(path)
        src.backup(dst)
        dst.close(); src.close()
    cap = (f"🗄 Ma'lumotlar bazasi nusxasi.\nA'zolar: {summ['approved']}, kutayotgan: {summ['pending']}, adminlar: {summ['admins']}.\n"
           "Tiklash uchun shu faylni qaytarib yuboring va izohga /restore yozing (tiklashdan oldin tasdiq so'raladi).")
    if db.member_count() == 0:
        cap += "\n⚠️ Diqqat: bazada oddiy a'zo yo'q, bu nusxani tiklamang."
    try:
        await bot.send_document(chat_id, FSInputFile(path), caption=cap)
    finally:
        os.remove(path)


# ---- tiklash (restore): xulosa + tasdiq + himoya ----
_pending_restore: dict[int, dict] = {}   # admin_id -> {"path", "ts", "new", "cur"}
RESTORE_TTL = 15 * 60


def inspect_backup(path: str) -> dict:
    """Zaxira faylini tekshiradi (JSON yoki SQLite) va xulosa qaytaradi. Xato bo'lsa ValueError."""
    return db.summary_of(db.read_backup(path))


def restore_decision(cur: dict, new: dict, force: bool) -> tuple[bool, str]:
    """(ruxsat, ogohlantirish). A'zolari kam zaxira `force`siz rad etiladi."""
    if new["approved"] < cur["approved"]:
        lost = cur["approved"] - new["approved"]
        msg = (f"⚠️ Zaxirada tasdiqlangan a'zolar <b>{new['approved']}</b> ta, hozir esa <b>{cur['approved']}</b> ta. "
               f"Tiklasangiz <b>{lost}</b> ta a'zo yo'qoladi.")
        if not force:
            return False, msg + ("\n\n❌ Shuning uchun tiklash rad etildi. Baribir tiklash kerak bo'lsa, faylni izoh "
                                 "<code>/restore force</code> bilan qayta yuboring.")
        return True, msg
    return True, ""


def apply_restore(path: str):
    """Joriy bazani zaxira bilan almashtiradi. Oldin joriy bazaning nusxasi saqlanadi; bosh adminlar saqlanadi."""
    data = db.read_backup(path)                       # avval to'liq tekshiramiz
    db.write_backup_json(os.path.join(tempfile.gettempdir(), "pre_restore.json"))
    db.load_all(data)
    db.init()
    db.ensure_env_admins()


@router.message(F.document, F.caption.startswith("/restore"))
async def cmd_restore(m: Message):
    if not db.is_admin(db.get_user(m.from_user.id)):
        return
    force = "force" in (m.caption or "").lower().split()
    path = os.path.join(tempfile.gettempdir(), f"restore_{m.from_user.id}.bak")
    try:
        await bot.download(m.document, destination=path)
        new = inspect_backup(path)
    except Exception as e:
        await m.answer(f"❌ Fayl yaroqsiz: {html.escape(str(e))}")
        return
    cur = db.current_summary()
    ok, warn = restore_decision(cur, new, force)
    txt = (f"🗄 <b>Zaxira ichida:</b>\n{_fmt_summary(new)}\n\n📊 <b>Hozirgi baza:</b>\n{_fmt_summary(cur)}\n\n"
           "Tiklasangiz hozirgi ma'lumotlar zaxiradagi bilan <b>almashtiriladi</b>.")
    if warn:
        txt += "\n\n" + warn
    if not ok:
        os.remove(path)
        await m.answer(txt)
        return
    _pending_restore[m.from_user.id] = {"path": path, "ts": time.time()}
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⚠️ Baribir tiklash" if warn else "✅ Tiklash", callback_data="rs:ok"),
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data="rs:no")]])
    await m.answer(txt, reply_markup=kb)


@router.callback_query(F.data.in_({"rs:ok", "rs:no"}))
async def on_restore_cb(cb: CallbackQuery):
    if not db.is_admin(db.get_user(cb.from_user.id)):
        await cb.answer("Faqat adminlar uchun", show_alert=True)
        return
    p = _pending_restore.pop(cb.from_user.id, None)
    if cb.data == "rs:no" or not p:
        if p and os.path.exists(p["path"]):
            os.remove(p["path"])
        await cb.answer("Bekor qilindi" if p else "So'rov topilmadi yoki eskirgan. Faylni qaytadan yuboring", show_alert=not p)
        try:
            await cb.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return
    if time.time() - p["ts"] > RESTORE_TTL or not os.path.exists(p["path"]):
        await cb.answer("Tasdiq muddati o'tdi. Faylni qaytadan yuboring", show_alert=True)
        return
    try:
        apply_restore(p["path"])
        await cb.message.answer("✅ Baza tiklandi.\n\n" + _fmt_summary(db.current_summary()) +
                                "\n\nTiklashdan oldingi baza nusxasi serverda vaqtincha saqlandi.")
    except Exception as e:
        await cb.message.answer(f"❌ Tiklab bo'lmadi: {html.escape(str(e))}")
    finally:
        if os.path.exists(p["path"]):
            os.remove(p["path"])
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await cb.answer()


@router.message(Command("help"))
async def cmd_help(m: Message):
    await m.answer("/start — ilovani ochish\n/help — yordam\n\nAdminlar uchun:\n/backup — baza nusxasi\n/addadmin &lt;id yoki @username&gt; — admin qo'shish\n/deladmin &lt;id yoki @username&gt; — adminlikdan olish")


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
