"""Bot handlerlarini Telegram'siz sinash (so'rovlar yozib olinadi). python tests/test_bot.py"""
import asyncio, os, sys, tempfile, datetime
os.environ.update(BOT_TOKEN="123456:TEST_TOKEN_FOR_LOCAL_TESTS", DB_PATH=os.path.join(tempfile.mkdtemp(), "b.db"),
                  ADMIN_IDS="1001", WEBAPP_URL="https://example.com", ADMIN_SETUP_CODE="kod123")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import TelegramMethod
from aiogram.types import Update
import bot_logic as bl, db

sent = []
class Fake(BaseSession):
    async def close(self): pass
    async def stream_content(self, *a, **k): yield b""
    async def make_request(self, bot, method: TelegramMethod, timeout=None):
        sent.append((type(method).__name__, method.model_dump(exclude_none=True)))
        return method.__returns__.model_validate({}) if False else True
ok = fail = 0
def check(n, c):
    global ok, fail
    if c: ok += 1; print("  OK  ", n)
    else: fail += 1; print("  FAIL", n)

def upd(i, **kw): return Update.model_validate({"update_id": i, **kw})
def msg(uid, text=None, **kw):
    return {"message": {"message_id": 1, "date": 0, "chat": {"id": uid, "type": "private"}, "from": {"id": uid, "is_bot": False, "first_name": "Ali", "username": "ali"}, **({"text": text, "entities": [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]} if text else {}), **kw}}

async def main():
    db.init()
    bl.bot = Bot(bl.config.BOT_TOKEN, session=Fake())
    dp = bl.make_dispatcher()
    await dp.feed_update(bl.bot, upd(1, **msg(2001, "/start")))
    check("/start (yangi) -> kontakt tugmasi + app tugmasi", any(m == "SendMessage" and "reply_markup" in p for m, p in sent) and len(sent) == 2)
    sent.clear()
    await dp.feed_update(bl.bot, upd(2, **msg(2001, contact={"phone_number": "998901112233", "first_name": "Ali", "user_id": 2001})))
    u = db.get_user(2001)
    check("kontakt -> pending + telefon", u["status"] == "pending" and u["phone"] == "+998901112233" and u["phone_verified"] == 1)
    check("adminga xabar tugmalar bilan", any(p.get("chat_id") == 1001 and "inline_keyboard" in str(p.get("reply_markup")) for m, p in sent))
    sent.clear()
    await dp.feed_update(bl.bot, upd(3, **msg(2001, contact={"phone_number": "998900000000", "first_name": "X", "user_id": 9999})))
    check("boshqaning kontaktini rad etadi", db.get_user(2001)["phone"] == "+998901112233")
    sent.clear()
    cb = {"callback_query": {"id": "1", "chat_instance": "x", "from": {"id": 2001, "is_bot": False, "first_name": "Ali"}, "data": "ap:2001",
          "message": {"message_id": 5, "date": 0, "chat": {"id": 2001, "type": "private"}, "text": "x"}}}
    await dp.feed_update(bl.bot, upd(4, **cb))
    check("oddiy a'zo tasdiqlay olmaydi", db.get_user(2001)["status"] == "pending")
    cb["callback_query"]["from"]["id"] = 1001; db.upsert_tg_user({"id": 1001, "first_name": "Adm"})
    cb["callback_query"]["message"]["chat"]["id"] = 1001
    await dp.feed_update(bl.bot, upd(5, **cb))
    check("admin tasdiqlaydi", db.get_user(2001)["status"] == "approved")
    check("a'zoga tasdiq xabari ketdi", any(p.get("chat_id") == 2001 and "tasdiqlandi" in p.get("text", "") for m, p in sent))
    sent.clear()
    await dp.feed_update(bl.bot, upd(6, **msg(3001, "/admin xato")))
    check("noto'g'ri admin kodi", not db.get_user(3001) or not db.get_user(3001)["is_admin"])
    await dp.feed_update(bl.bot, upd(7, **msg(3001, "/admin kod123")))
    check("to'g'ri admin kodi -> admin", db.get_user(3001)["is_admin"] == 1)
    sent.clear()
    await dp.feed_update(bl.bot, upd(8, **msg(2001, "/start")))
    check("/start (tasdiqlangan) -> app tugmasi", any("web_app" in str(p.get("reply_markup")) for m, p in sent))
    print("[admin buyruqlari]")
    sent.clear()
    await dp.feed_update(bl.bot, upd(9, **msg(2001, "/addadmin 2001")))
    check("oddiy a'zo /addadmin ishlata olmaydi", not db.get_user(2001)["is_admin"] and not sent)
    await dp.feed_update(bl.bot, upd(10, **msg(3001, "/addadmin 2001")))
    check("/addadmin <id> -> admin", db.get_user(2001)["is_admin"] == 1)
    check("yangi adminga xabar ketdi", any(p.get("chat_id") == 2001 and "admin" in p.get("text", "") for m, p in sent))
    sent.clear()
    db.x("UPDATE users SET is_admin=0 WHERE tg_id=2001"); db.x("UPDATE users SET username='ali_x' WHERE tg_id=2001")
    await dp.feed_update(bl.bot, upd(11, **msg(3001, "/addadmin @Ali_X")))
    check("/addadmin @username (katta-kichik harf farqsiz)", db.get_user(2001)["is_admin"] == 1)
    sent.clear()
    await dp.feed_update(bl.bot, upd(12, **msg(3001, "/addadmin @yoq_odam")))
    check("topilmasa tushuntirish", any("topilmadi" in p.get("text", "") for m, p in sent))
    sent.clear()
    await dp.feed_update(bl.bot, upd(13, **msg(3001, "/deladmin 1001")))
    check("super-adminni olib bo'lmaydi", db.is_admin(db.get_user(1001)) and any("Bosh admin" in p.get("text", "") for m, p in sent))
    await dp.feed_update(bl.bot, upd(14, **msg(3001, "/deladmin 3001")))
    check("o'zini olib bo'lmaydi", db.get_user(3001)["is_admin"] == 1)
    sent.clear()
    await dp.feed_update(bl.bot, upd(15, **msg(3001, "/deladmin 2001")))
    check("/deladmin -> oddiy a'zo", db.get_user(2001)["is_admin"] == 0)
    check("olinganga xabar ketdi", any(p.get("chat_id") == 2001 and "olib tashlandi" in p.get("text", "") for m, p in sent))
    print("[tiklash (restore) himoyasi]")
    import sqlite3, shutil
    # joriy bazada 3 ta tasdiqlangan a'zo bo'lsin (2001 va 3001 oldin yaratilgan)
    for uid in (4001, 4002):
        db.x("INSERT OR REPLACE INTO users(tg_id,first_name,status,is_admin,created_at,updated_at) VALUES(?,?,?,?,?,?)", (uid, "M", "approved", 0, "x", "x"))
    cur = db.current_summary()
    def mk(path, approved):
        c = sqlite3.connect(path); c.executescript(db.SCHEMA)
        for i in range(approved):
            c.execute("INSERT INTO users(tg_id,first_name,status) VALUES(?,?,'approved')", (7000 + i, "B"))
        c.commit(); c.close()
    small, big, bad = (os.path.join(tempfile.mkdtemp(), n) for n in ("small.db", "big.db", "bad.db"))
    mk(small, 1); mk(big, cur["approved"] + 5); open(bad, "wb").write(b"not a database")
    check("inspect: a'zolar soni", bl.inspect_backup(big)["approved"] == cur["approved"] + 5)
    try: bl.inspect_backup(bad); okbad = False
    except ValueError: okbad = True
    check("buzuq fayl rad etiladi", okbad)
    ns = bl.inspect_backup(small)
    check("kam a'zoli zaxira force'siz rad etiladi", bl.restore_decision(cur, ns, False)[0] is False and "yo'qoladi" in bl.restore_decision(cur, ns, False)[1])
    ok_f, w = bl.restore_decision(cur, ns, True)
    check("force bilan ogohlantirib ruxsat", ok_f and "yo'qoladi" in w)
    check("ko'p a'zoli zaxira ogohlantirishsiz", bl.restore_decision(cur, bl.inspect_backup(big), False) == (True, ""))
    # callback orqali tasdiq
    def cbq(data, uid):
        return {"callback_query": {"id": "9", "chat_instance": "x", "from": {"id": uid, "is_bot": False, "first_name": "A"}, "data": data,
                "message": {"message_id": 7, "date": 0, "chat": {"id": uid, "type": "private"}, "text": "x"}}}
    import time as _t
    before = db.current_summary()
    shutil.copy(small, small + ".p"); bl._pending_restore[3001] = {"path": small + ".p", "ts": _t.time()}
    await dp.feed_update(bl.bot, upd(20, **cbq("rs:no", 3001)))
    check("«Bekor» bazani o'zgartirmaydi", db.current_summary() == before and 3001 not in bl._pending_restore)
    bl._pending_restore[3001] = {"path": small + ".p", "ts": _t.time()}
    shutil.copy(small, small + ".p")
    await dp.feed_update(bl.bot, upd(21, **cbq("rs:ok", 2001)))    # oddiy a'zo bosdi (admin emas)
    check("admin bo'lmaganning tasdig'i ishlamaydi", db.current_summary() == before)
    await dp.feed_update(bl.bot, upd(22, **cbq("rs:ok", 3001)))
    after = db.current_summary()
    check("tasdiqlansa baza almashtiriladi", after["approved"] >= 1 and after["approved"] != before["approved"])
    check("bosh admin (ADMIN_IDS) tiklashdan keyin ham saqlanadi", (lambda r: r and r["status"] == "approved" and r["is_admin"] == 1)(db.get_user(1001)))
    check("tiklashdan oldingi nusxa saqlandi", os.path.exists(os.path.join(tempfile.gettempdir(), "pre_restore.db")))
    await dp.feed_update(bl.bot, upd(23, **cbq("rs:ok", 3001)))
    check("so'rovsiz/eskirgan tasdiq hech narsa qilmaydi", db.current_summary() == after)
asyncio.run(main())
print(f"\nNatija: {ok} o'tdi, {fail} xato"); sys.exit(1 if fail else 0)
