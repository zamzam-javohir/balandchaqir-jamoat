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
asyncio.run(main())
print(f"\nNatija: {ok} o'tdi, {fail} xato"); sys.exit(1 if fail else 0)
