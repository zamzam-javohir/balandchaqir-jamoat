"""Balandchaqir Jamoat — FastAPI backend + aiogram bot (bitta jarayonda)."""
import asyncio, contextlib, html, json, logging, os, re, time
from datetime import datetime, timedelta
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from aiogram.types import Update

import bot_logic as bl
import config, db, prayer
from auth import validate_init_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("app")
BASE = os.path.dirname(os.path.abspath(__file__))
PRAYER_KEYS = ["bomdod", "peshin", "asr", "shom", "xufton"]
PRAYER_NAMES = {"bomdod": "Bomdod", "quyosh": "Quyosh", "peshin": "Peshin", "asr": "Asr", "shom": "Shom", "xufton": "Xufton"}
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


# ------------------------------------------------------------------ yordamchilar
_bg: set = set()


def bg(coro):
    """Fon vazifasi (broadcast): tugamaguncha havola saqlanadi."""
    t = asyncio.create_task(coro)
    _bg.add(t)
    t.add_done_callback(_bg.discard)
    return t


def jamoat_dt(key: str, d) -> datetime:
    """Namozning jamoat vaqti (admin kiritgan iqomat vaqti; yo'q bo'lsa hisoblangan vaqt + 15 daq)."""
    t = ((db.get_setting("jamoat_times") or {}).get(key) or "").strip()
    if t and HHMM.match(t):
        return prayer.to_dt(d, t)
    pt = prayer.day_times(d, config.LAT, config.LNG, db.get_setting("prayer_offsets"))[key]
    return prayer.to_dt(d, pt) + timedelta(minutes=15)


def next_jamoat():
    """Eng yaqin jamoat namozi: (kalit, 'today'|'tomorrow'). Xuftondan keyin — ertangi Bomdod."""
    now = db.now()
    for key in PRAYER_KEYS:
        if jamoat_dt(key, now.date()) > now:
            return key, "today"
    return "bomdod", "tomorrow"


def day_label(d: str) -> str:
    today = db.now().date()
    if d == today.isoformat():
        return "bugun"
    if d == (today + timedelta(days=1)).isoformat():
        return "ertaga"
    y, mo, dd = d.split("-")
    return f"{dd}.{mo}.{y}"


def map_link(lat, lon) -> str:
    return f"https://maps.google.com/?q={lat},{lon}"
async def current_user(x_init_data: str = Header(default="")) -> dict:
    u = validate_init_data(x_init_data, config.BOT_TOKEN, config.INITDATA_MAX_AGE)
    if not u:
        raise HTTPException(401, "Telegram orqali kiring (initData noto'g'ri)")
    return db.upsert_tg_user(u)


async def member(user: dict = Depends(current_user)) -> dict:
    if user["status"] != "approved":
        raise HTTPException(403, "Avval ro'yxatdan o'tib, admin tasdiqlashini kuting")
    return user


async def admin(user: dict = Depends(member)) -> dict:
    if not db.is_admin(user):
        raise HTTPException(403, "Faqat adminlar uchun")
    return user


def me_json(u: dict) -> dict:
    return {"id": u["tg_id"], "name": u.get("name") or "", "first_name": u.get("first_name") or "",
            "username": u.get("username"), "phone": u.get("phone") or "", "phone_verified": bool(u.get("phone_verified")),
            "status": u["status"], "is_admin": db.is_admin(u)}


def norm_phone(p: str) -> str | None:
    d = re.sub(r"[^\d+]", "", p or "")
    digits = d.replace("+", "")
    if len(digits) == 9:
        digits = "998" + digits
    if not (10 <= len(digits) <= 15):
        return None
    return "+" + digits


def contact_of(u: dict, share_phone=True) -> dict:
    return {"id": u["tg_id"], "name": db.display_name(u), "username": u.get("username"),
            "phone": (u.get("phone") or "") if share_phone else ""}


# ------------------------------------------------------------------ modellar
class RegisterIn(BaseModel):
    name: str
    phone: str = ""

class JamoatIn(BaseModel):
    times: dict[str, str] = {}
    juma_time: str = ""
    note: str = ""
    offsets: dict[str, int] = {}

class RideIn(BaseModel):
    kind: str
    prayer: str = "bomdod"
    day: str = "today"          # today | tomorrow
    depart_time: str
    seats: int = 0
    note: str = ""
    share_phone: bool = False
    lat: float | None = None
    lon: float | None = None

class VoteIn(BaseModel):
    answer: str

class FootballIn(BaseModel):
    min_players: int = 10
    game_time: str = ""
    game_place: str = ""
    daily_poll_enabled: bool = False
    daily_poll_time: str = "08:00"

class StatusIn(BaseModel):
    status: str

class AdminIn(BaseModel):
    is_admin: bool


# ------------------------------------------------------------------ ilova
@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    tasks = []
    if config.BOT_TOKEN and not os.getenv("DISABLE_BOT"):
        bl.bot = bl.make_bot()
        dp = bl.make_dispatcher()
        app.state.dp = dp
        try:
            await bl.setup_menu()
        except Exception as e:
            log.warning("menu button: %s", e)
        if config.MODE == "polling":
            await bl.bot.delete_webhook(drop_pending_updates=False)
            tasks.append(asyncio.create_task(dp.start_polling(bl.bot, handle_signals=False, allowed_updates=["message", "callback_query"])))
            log.info("Bot: polling rejimi")
        else:
            if config.WEBAPP_URL:
                await bl.bot.set_webhook(f"{config.WEBAPP_URL}/webhook/{config.WEBHOOK_SECRET}",
                                         secret_token=config.WEBHOOK_SECRET, allowed_updates=["message", "callback_query"])
                log.info("Bot: webhook o'rnatildi")
            else:
                log.warning("WEBAPP_URL yo'q — webhook o'rnatilmadi")
        tasks.append(asyncio.create_task(scheduler()))
        tasks.append(asyncio.create_task(expiry_loop()))
    else:
        log.warning("BOT_TOKEN topilmadi — faqat API ishlaydi")
    yield
    for t in tasks:
        t.cancel()
    if bl.bot:
        await bl.bot.session.close()


app = FastAPI(title="Balandchaqir Jamoat", lifespan=lifespan, docs_url=None, redoc_url=None)


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/webhook/{secret}")
async def webhook(secret: str, request: Request):
    if secret != config.WEBHOOK_SECRET or request.headers.get("x-telegram-bot-api-secret-token") != config.WEBHOOK_SECRET:
        raise HTTPException(403)
    upd = Update.model_validate(await request.json(), context={"bot": bl.bot})
    await app.state.dp.feed_update(bl.bot, upd)
    return {"ok": True}


@app.get("/")
async def index():
    return FileResponse(os.path.join(BASE, "static", "index.html"), headers={"Cache-Control": "no-cache"})


# ------------------------------------------------------------------ profil / a'zolik
@app.get("/api/me")
async def api_me(user: dict = Depends(current_user)):
    return me_json(user)


@app.post("/api/register")
async def api_register(body: RegisterIn, user: dict = Depends(current_user)):
    name = " ".join(body.name.split())[:60]
    if len(name) < 2:
        raise HTTPException(400, "Ism-familiyani kiriting")
    phone = norm_phone(body.phone) if body.phone else user.get("phone")
    if not phone:
        raise HTTPException(400, "Telefon raqamni kiriting (masalan: +998 90 123 45 67)")
    if user.get("phone_verified") and user.get("phone") and body.phone and norm_phone(body.phone) != user["phone"]:
        phone = user["phone"]  # tasdiqlangan raqamni almashtirmaymiz
    was = user["status"]
    new_status = "pending" if was in ("new", "rejected") else was
    db.x("UPDATE users SET name=?, phone=?, status=?, updated_at=? WHERE tg_id=?",
         (name, phone, new_status, db.now_str(), user["tg_id"]))
    u = db.get_user(user["tg_id"])
    if was in ("new", "rejected") and new_status == "pending":
        await bl.notify_admins_new_user(u)
    return me_json(u)


# ------------------------------------------------------------------ 1. namoz vaqtlari
@app.get("/api/prayer")
async def api_prayer(date: str | None = None, user: dict = Depends(current_user)):
    now = db.now()
    try:
        d = datetime.strptime(date, "%Y-%m-%d").date() if date else now.date()
    except ValueError:
        raise HTTPException(400, "Sana noto'g'ri")
    offsets = db.get_setting("prayer_offsets")
    times = prayer.day_times(d, config.LAT, config.LNG, offsets)
    k, name, dt = prayer.next_prayer(now, config.LAT, config.LNG, offsets)
    return {"date": d.isoformat(), "place": config.PLACE_NAME, "now": now.isoformat(),
            "times": [{"key": kk, "name": nn, "time": times[kk]} for kk, nn in prayer.PRAYERS],
            "next": {"key": k, "name": name, "at": dt.isoformat(), "seconds": int((dt - now).total_seconds())},
            "qibla": round(prayer.qibla(config.LAT, config.LNG), 1),
            "method": "Muslim World League, Asr: Hanafiy"}


# ------------------------------------------------------------------ 2. jamoat vaqtlari
@app.get("/api/jamoat")
async def api_jamoat(user: dict = Depends(member)):
    nk, nd = next_jamoat()
    now = db.now()
    passed = {k: jamoat_dt(k, now.date()) <= now for k in PRAYER_KEYS}
    return {"times": db.get_setting("jamoat_times"), "juma_time": db.get_setting("juma_time"),
            "note": db.get_setting("jamoat_note"), "offsets": db.get_setting("prayer_offsets"),
            "is_admin": db.is_admin(user), "next_prayer": nk, "next_day": nd, "passed": passed}


@app.put("/api/admin/jamoat")
async def api_jamoat_put(body: JamoatIn, user: dict = Depends(admin)):
    times = {}
    for k in PRAYER_KEYS:
        v = (body.times.get(k) or "").strip()
        if v and not HHMM.match(v):
            raise HTTPException(400, f"{PRAYER_NAMES[k]} vaqti noto'g'ri (HH:MM)")
        times[k] = v
    juma = body.juma_time.strip()
    if juma and not HHMM.match(juma):
        raise HTTPException(400, "Juma vaqti noto'g'ri (HH:MM)")
    offs = db.get_setting("prayer_offsets")
    for k in prayer.PRAYERS:
        if k[0] in body.offsets:
            offs[k[0]] = max(-30, min(30, int(body.offsets[k[0]])))
    old_times = db.get_setting("jamoat_times")
    old_juma = db.get_setting("juma_time")
    db.set_setting("jamoat_times", times)
    db.set_setting("juma_time", juma)
    db.set_setting("jamoat_note", body.note.strip()[:300])
    db.set_setting("prayer_offsets", offs)
    # e'lonlar muddatini yangi iqomat vaqtiga moslash
    for r in db.q("SELECT id, prayer, date FROM rides WHERE expires_at > ?", (db.now_str(),)):
        db.x("UPDATE rides SET expires_at=? WHERE id=?",
             (jamoat_dt(r["prayer"], datetime.strptime(r["date"], "%Y-%m-%d").date()).strftime("%Y-%m-%d %H:%M"), r["id"]))
    lines = []
    for k in PRAYER_KEYS:
        if times[k] and times[k] != (old_times.get(k) or ""):
            lines.append(f"🕌 {PRAYER_NAMES[k]} jamoati endi <b>{times[k]}</b> da")
    if juma and juma != (old_juma or ""):
        lines.append(f"🕌 Juma namozi endi <b>{juma}</b> da")
    if lines:
        bg(bl.broadcast("🔔 <b>Jamoat vaqti o'zgardi</b>\n" + "\n".join(lines)))
    return await api_jamoat(user)


# ------------------------------------------------------------------ 3. birga borish (rides)
def ride_json(r: dict, me: dict, joins: list[dict]) -> dict:
    author = db.get_user(r["author_id"])
    mine = r["author_id"] == me["tg_id"]
    my_join = any(j["user_id"] == me["tg_id"] for j in joins)
    out = {"id": r["id"], "kind": r["kind"], "prayer": r["prayer"], "prayer_name": PRAYER_NAMES.get(r["prayer"], r["prayer"]),
           "date": r["date"], "depart_time": r["depart_time"], "seats": r["seats"], "note": r["note"] or "",
           "author": {"id": author["tg_id"], "name": db.display_name(author), "username": author.get("username"),
                      "phone": (author.get("phone") or "") if r["share_phone"] else ""},
           "mine": mine, "joined": my_join, "join_count": len(joins),
           "free": max(0, r["seats"] - len(joins)) if r["kind"] == "driver" else None,
           "lat": r.get("lat"), "lon": r.get("lon"), "has_location": r.get("lat") is not None and r.get("lon") is not None,
           "joiners": []}
    if mine:
        for j in joins:
            ju = db.get_user(j["user_id"])
            out["joiners"].append(contact_of(ju))
    return out


@app.get("/api/rides")
async def api_rides(prayer: str = "bomdod", user: dict = Depends(member)):
    if prayer not in PRAYER_KEYS:
        raise HTTPException(400, "Namoz noto'g'ri")
    rows = db.q("SELECT * FROM rides WHERE prayer=? AND expires_at > ? ORDER BY date, depart_time", (prayer, db.now_str()))
    res = []
    for r in rows:
        joins = db.q("SELECT * FROM ride_joins WHERE ride_id=? ORDER BY id", (r["id"],))
        res.append(ride_json(r, user, joins))
    return {"prayer": prayer, "rides": res}


@app.post("/api/rides")
async def api_ride_create(body: RideIn, user: dict = Depends(member)):
    if body.kind not in ("driver", "request"):
        raise HTTPException(400, "Tur noto'g'ri")
    if body.prayer not in PRAYER_KEYS:
        raise HTTPException(400, "Namoz noto'g'ri")
    if not HHMM.match(body.depart_time):
        raise HTTPException(400, "Chiqish vaqti noto'g'ri (HH:MM)")
    if body.day not in ("today", "tomorrow"):
        raise HTTPException(400, "Kun noto'g'ri")
    seats = body.seats if body.kind == "driver" else 0
    if body.kind == "driver" and not (1 <= seats <= 8):
        raise HTTPException(400, "Bo'sh joylar soni 1 dan 8 gacha bo'lsin")
    if body.share_phone and not user.get("phone"):
        raise HTTPException(400, "Telefon raqamingiz saqlanmagan")
    lat, lon = body.lat, body.lon
    if (lat is None) != (lon is None):
        raise HTTPException(400, "Joylashuv to'liq emas")
    if lat is not None and not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise HTTPException(400, "Joylashuv noto'g'ri")
    d = db.now().date() + (timedelta(days=1) if body.day == "tomorrow" else timedelta())
    exp = jamoat_dt(body.prayer, d)   # e'lon shu namozning jamoat vaqtigacha amal qiladi
    if exp <= db.now():
        raise HTTPException(400, "Bu namozning jamoat vaqti allaqachon o'tib ketgan. «Ertaga»ni tanlang yoki boshqa namozni tanlang")
    rid = db.x("INSERT INTO rides(author_id,kind,prayer,date,depart_time,seats,note,share_phone,lat,lon,expires_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
               (user["tg_id"], body.kind, body.prayer, d.isoformat(), body.depart_time, seats,
                body.note.strip()[:200], 1 if body.share_phone else 0, lat, lon, exp.strftime("%Y-%m-%d %H:%M"), db.now_str()))
    drv = body.kind == "driver"
    pn = PRAYER_NAMES[body.prayer]
    lines = [f"🚗 <b>Mashinada chiqaman</b> — {pn}" if drv else f"🙋 <b>Mashinam yo'q, olib keting</b> — {pn}",
             f"👤 {bl.user_link(user)}", f"📅 {day_label(d.isoformat()).capitalize()}, 🕒 chiqish: <b>{body.depart_time}</b>"]
    if drv:
        lines.append(f"💺 Bo'sh joy: {seats}")
    if body.note.strip():
        lines.append(f"💬 {html.escape(body.note.strip()[:200])}")
    if lat is not None:
        lines.append(f'📍 <a href="{map_link(lat, lon)}">Joylashuv</a>')
    lines.append("Qo'shilish uchun ilovani oching 👇")
    bg(bl.broadcast("\n".join(lines), track=("ride", rid), exclude=[user["tg_id"]]))
    return {"id": rid}


def _get_ride(rid: int) -> dict:
    r = db.q("SELECT * FROM rides WHERE id=?", (rid,), one=True)
    if not r or r["expires_at"] <= db.now_str():
        raise HTTPException(404, "E'lon topilmadi yoki muddati o'tgan")
    return r


@app.delete("/api/rides/{rid}")
async def api_ride_delete(rid: int, user: dict = Depends(member)):
    r = db.q("SELECT * FROM rides WHERE id=?", (rid,), one=True)
    if not r:
        raise HTTPException(404, "E'lon topilmadi")
    if r["author_id"] != user["tg_id"] and not db.is_admin(user):
        raise HTTPException(403, "Faqat e'lon egasi o'chira oladi")
    db.x("DELETE FROM ride_joins WHERE ride_id=?", (rid,))
    db.x("DELETE FROM rides WHERE id=?", (rid,))
    bg(bl.retire_broadcasts("ride", rid, "🗑 E'lon o'chirildi"))
    return {"ok": True}


@app.post("/api/rides/{rid}/join")
async def api_ride_join(rid: int, user: dict = Depends(member)):
    r = _get_ride(rid)
    if r["author_id"] == user["tg_id"]:
        raise HTTPException(400, "O'z e'loningizga qo'shila olmaysiz")
    joins = db.q("SELECT * FROM ride_joins WHERE ride_id=?", (rid,))
    if any(j["user_id"] == user["tg_id"] for j in joins):
        raise HTTPException(409, "Siz allaqachon qo'shilgansiz")
    if r["kind"] == "driver" and len(joins) >= r["seats"]:
        raise HTTPException(409, "Afsuski, bo'sh joy qolmadi")
    db.x("INSERT INTO ride_joins(ride_id,user_id,created_at) VALUES(?,?,?)", (rid, user["tg_id"], db.now_str()))
    author = db.get_user(r["author_id"])
    pn = PRAYER_NAMES.get(r["prayer"], r["prayer"])
    when = f"{'bugun' if r['date'] == db.now().date().isoformat() else r['date']} {r['depart_time']}"
    if r["kind"] == "driver":
        head = f"🚗 <b>{html.escape(db.display_name(user))}</b> sizning {pn} e'loningizga qo'shildi: «Men ham boraman»."
    else:
        head = f"🙋 <b>{html.escape(db.display_name(user))}</b> sizni {pn}ga olib ketishga rozi: «Men olib ketaman»."
    lines = [head, f"🕒 {when}", f"👤 {bl.user_link(user)}" + (f" (@{user['username']})" if user.get("username") else "")]
    if user.get("phone"):
        lines.append(f"📞 {html.escape(user['phone'])}")
    if r.get("lat") is not None and r.get("lon") is not None:
        lines.append("📍 E'londagi joylashuv pastda yuborildi.")
    await bl.safe_send(author["tg_id"], "\n".join(lines))
    if r.get("lat") is not None and r.get("lon") is not None:
        await bl.safe_location(author["tg_id"], r["lat"], r["lon"])
        await bl.safe_send(user["tg_id"], "📍 E'londagi joylashuv (navigatsiya uchun):")
        await bl.safe_location(user["tg_id"], r["lat"], r["lon"])
    return {"ok": True, "contact": contact_of(author, bool(r["share_phone"]))}


@app.delete("/api/rides/{rid}/join")
async def api_ride_leave(rid: int, user: dict = Depends(member)):
    db.x("DELETE FROM ride_joins WHERE ride_id=? AND user_id=?", (rid, user["tg_id"]))
    return {"ok": True}


# ------------------------------------------------------------------ 4. futbol
def current_poll():
    return db.q("SELECT * FROM polls WHERE status='open' ORDER BY id DESC LIMIT 1", one=True)


def football_state(user: dict) -> dict:
    p = current_poll()
    mn = int(db.get_setting("min_players"))
    out = {"poll": None, "min": mn, "game": {"time": db.get_setting("game_time"), "place": db.get_setting("game_place")},
           "is_admin": db.is_admin(user)}
    if p:
        votes = db.q("SELECT * FROM votes WHERE poll_id=? ORDER BY updated_at", (p["id"],))
        yes = [db.public_user(db.get_user(v["user_id"])) for v in votes if v["answer"] == "yes"]
        no = [db.public_user(db.get_user(v["user_id"])) for v in votes if v["answer"] == "no"]
        my = next((v["answer"] for v in votes if v["user_id"] == user["tg_id"]), None)
        out["poll"] = {"id": p["id"], "date": p["date"], "created_at": p["created_at"]}
        out.update({"yes": yes, "no": no, "yes_count": len(yes), "no_count": len(no), "my": my, "enough": len(yes) >= mn})
    if db.is_admin(user):
        out["settings"] = {"min_players": mn, "game_time": db.get_setting("game_time"), "game_place": db.get_setting("game_place"),
                           "daily_poll_enabled": db.get_setting("daily_poll_enabled"), "daily_poll_time": db.get_setting("daily_poll_time")}
    return out


@app.get("/api/football")
async def api_football(user: dict = Depends(member)):
    return football_state(user)


@app.post("/api/football/vote")
async def api_vote(body: VoteIn, user: dict = Depends(member)):
    if body.answer not in ("yes", "no"):
        raise HTTPException(400, "Javob noto'g'ri")
    p = current_poll()
    if not p:
        raise HTTPException(409, "Hozir ochiq so'rovnoma yo'q")
    db.x("INSERT INTO votes(poll_id,user_id,answer,updated_at) VALUES(?,?,?,?) ON CONFLICT(poll_id,user_id) DO UPDATE SET answer=excluded.answer, updated_at=excluded.updated_at",
         (p["id"], user["tg_id"], body.answer, db.now_str()))
    await check_game_on(p["id"])
    return football_state(user)


async def check_game_on(poll_id: int):
    p = db.q("SELECT * FROM polls WHERE id=?", (poll_id,), one=True)
    if not p or p["notified"]:
        return
    mn = int(db.get_setting("min_players"))
    yes = db.q("SELECT user_id FROM votes WHERE poll_id=? AND answer='yes'", (poll_id,))
    if len(yes) < mn:
        return
    db.x("UPDATE polls SET notified=1 WHERE id=?", (poll_id,))
    t, place = db.get_setting("game_time"), db.get_setting("game_place")
    txt = f"⚽ <b>O'yin bo'ladi!</b>\n\n✅ Kelishini tasdiqlaganlar: <b>{len(yes)}</b> kishi"
    t = html.escape(t) if t else "admin e'lon qiladi"
    place = html.escape(place) if place else "admin e'lon qiladi"
    txt += f"\n🕒 Vaqt: <b>{t}</b>\n📍 Joy: <b>{place}</b>"
    bg(bl.broadcast(txt))


async def open_new_poll(auto=False, notify=True) -> int:
    db.x("UPDATE polls SET status='closed' WHERE status='open'")
    pid = db.x("INSERT INTO polls(date,status,auto,created_at) VALUES(?,?,?,?)",
               (db.now().date().isoformat(), "open", 1 if auto else 0, db.now_str()))
    if notify:
        t, place = db.get_setting("game_time"), db.get_setting("game_place")
        txt = f"⚽ <b>Bugun futbolga kim keladi?</b>\nIlovani ochib «Ha» yoki «Yo'q» ni tanlang.\nKamida {db.get_setting('min_players')} kishi kerak."
        if t or place:
            txt += f"\n🕒 {html.escape(t or '—')}  📍 {html.escape(place or '—')}"
        bg(bl.broadcast(txt))
    return pid


@app.put("/api/admin/football")
async def api_football_put(body: FootballIn, user: dict = Depends(admin)):
    if body.daily_poll_time and not HHMM.match(body.daily_poll_time):
        raise HTTPException(400, "So'rovnoma vaqti noto'g'ri (HH:MM)")
    if body.game_time and len(body.game_time) > 60:
        raise HTTPException(400, "O'yin vaqti juda uzun")
    old_t, old_p = db.get_setting("game_time"), db.get_setting("game_place")
    new_t, new_p = body.game_time.strip()[:60], body.game_place.strip()[:100]
    db.set_setting("min_players", max(2, min(40, body.min_players)))
    db.set_setting("game_time", new_t)
    db.set_setting("game_place", new_p)
    if (new_t, new_p) != (old_t, old_p):
        e = html.escape
        if not (new_t or new_p):
            bg(bl.broadcast("❌ <b>Futbol o'yini bekor qilindi</b>"))
        elif not (old_t or old_p):
            bg(bl.broadcast(f"⚽ <b>Futbol o'yini e'lon qilindi</b>\n🕒 Vaqt: <b>{e(new_t or '—')}</b>\n📍 Joy: <b>{e(new_p or '—')}</b>"))
        else:
            ch = []
            if new_t != old_t:
                ch.append(f"🕒 Vaqt: {e(old_t or '—')} → <b>{e(new_t or '—')}</b>")
            if new_p != old_p:
                ch.append(f"📍 Joy: {e(old_p or '—')} → <b>{e(new_p or '—')}</b>")
            bg(bl.broadcast("⚽ <b>Futbol o'yini o'zgardi</b>\n" + "\n".join(ch)))
    db.set_setting("daily_poll_enabled", bool(body.daily_poll_enabled))
    db.set_setting("daily_poll_time", body.daily_poll_time or "08:00")
    p = current_poll()
    if p:
        await check_game_on(p["id"])
    return football_state(user)


@app.post("/api/admin/football/cancel")
async def api_football_cancel(user: dict = Depends(admin)):
    p = current_poll()
    if not p and not db.get_setting("game_time"):
        raise HTTPException(409, "Bekor qilinadigan o'yin yo'q")
    if p:
        db.x("UPDATE polls SET status='cancelled' WHERE id=?", (p["id"],))
    place = db.get_setting("game_place")
    db.set_setting("game_time", "")
    bg(bl.broadcast("❌ <b>Futbol o'yini bekor qilindi</b>" + (f"\n📍 {html.escape(place)}" if place else "")))
    return football_state(user)


@app.post("/api/admin/football/new-poll")
async def api_new_poll(user: dict = Depends(admin)):
    await open_new_poll(auto=False, notify=True)
    return football_state(user)


# ------------------------------------------------------------------ 5. a'zolar (admin)
@app.get("/api/admin/users")
async def api_users(status: str = "pending", user: dict = Depends(admin)):
    if status == "all":
        rows = db.q("SELECT * FROM users WHERE status!='new' ORDER BY created_at DESC")
    elif status == "admins":
        rows = [r for r in db.q("SELECT * FROM users ORDER BY created_at DESC") if db.is_admin(r)]
    else:
        rows = db.q("SELECT * FROM users WHERE status=? ORDER BY created_at DESC", (status,))
    counts = {r["status"]: r["n"] for r in db.q("SELECT status, count(*) n FROM users GROUP BY status")}
    counts["admins"] = len(db.admin_ids())
    return {"users": [{"id": r["tg_id"], "name": db.display_name(r), "username": r.get("username"), "phone": r.get("phone") or "",
                       "status": r["status"], "is_admin": db.is_admin(r), "is_super": r["tg_id"] in config.ADMIN_IDS,
                       "is_self": r["tg_id"] == user["tg_id"], "created_at": r["created_at"]} for r in rows],
            "counts": counts}


@app.post("/api/admin/users/{uid}/admin")
async def api_user_admin(uid: int, body: AdminIn, user: dict = Depends(admin)):
    t = db.get_user(uid)
    if not t:
        raise HTTPException(404, "Foydalanuvchi topilmadi")
    if uid == user["tg_id"]:
        raise HTTPException(400, "O'zingizning admin huquqingizni o'zgartirib bo'lmaydi")
    if not body.is_admin and uid in config.ADMIN_IDS:
        raise HTTPException(400, "Bosh adminni adminlikdan olib bo'lmaydi")
    if body.is_admin and t["status"] != "approved":
        raise HTTPException(400, "Avval a'zoni tasdiqlang")
    await bl.set_admin(uid, body.is_admin, by=user)
    return {"ok": True}


@app.post("/api/admin/users/{uid}/status")
async def api_user_status(uid: int, body: StatusIn, user: dict = Depends(admin)):
    if body.status not in ("approved", "rejected", "pending"):
        raise HTTPException(400, "Holat noto'g'ri")
    t = db.get_user(uid)
    if not t:
        raise HTTPException(404, "Foydalanuvchi topilmadi")
    if db.is_admin(t) and body.status != "approved":
        raise HTTPException(400, "Adminni rad etib bo'lmaydi")
    await bl.set_status(uid, body.status)
    return {"ok": True}


# ------------------------------------------------------------------ 6. hashar
WHEN_LABELS = {"bomdod_after": "Bomdoddan keyin", "xufton_after": "Xuftondan keyin"}


class HasharIn(BaseModel):
    when_kind: str = "bomdod_after"
    when_time: str = ""
    date: str
    place: str
    description: str = ""
    lat: float | None = None
    lon: float | None = None


def hashar_when(h: dict) -> str:
    return WHEN_LABELS.get(h["when_kind"]) or (h.get("when_time") or "—")


def hashar_json(h: dict, me: dict) -> dict:
    joins = db.q("SELECT user_id FROM hashar_joins WHERE hashar_id=? ORDER BY rowid", (h["id"],))
    going = [db.public_user(u) for u in (db.get_user(j["user_id"]) for j in joins) if u]
    author = db.get_user(h["author_id"])
    return {"id": h["id"], "when_kind": h["when_kind"], "when_time": h.get("when_time") or "", "when_label": hashar_when(h),
            "date": h["date"], "date_label": day_label(h["date"]), "place": h["place"], "description": h["description"] or "",
            "lat": h.get("lat"), "lon": h.get("lon"), "has_location": h.get("lat") is not None and h.get("lon") is not None,
            "author": db.display_name(author) if author else "?", "going": going, "going_count": len(going),
            "joined": any(g["id"] == me["tg_id"] for g in going), "can_edit": db.is_admin(me)}


def hashar_text(h: dict, head: str) -> str:
    e = html.escape
    lines = [head, f"📅 <b>{e(day_label(h['date']).capitalize())}</b> ({h['date']}), 🕒 <b>{e(hashar_when(h))}</b>",
             f"📍 Joy: <b>{e(h['place'])}</b>"]
    if h.get("description"):
        lines.append(f"📝 {e(h['description'])}")
    if h.get("lat") is not None and h.get("lon") is not None:
        lines.append(f'🗺 <a href="{map_link(h["lat"], h["lon"])}">Joylashuv (xarita)</a>')
    return "\n".join(lines)


def validate_hashar(body: HasharIn) -> dict:
    if body.when_kind not in ("bomdod_after", "xufton_after", "custom"):
        raise HTTPException(400, "Vaqt turi noto'g'ri")
    wt = body.when_time.strip()
    if body.when_kind == "custom" and not HHMM.match(wt):
        raise HTTPException(400, "Vaqtni HH:MM ko'rinishida kiriting")
    try:
        d = datetime.strptime(body.date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "Sana noto'g'ri")
    if d < db.now().date():
        raise HTTPException(400, "Sana o'tib ketgan")
    place = body.place.strip()[:100]
    if not place:
        raise HTTPException(400, "Joyni kiriting")
    if (body.lat is None) != (body.lon is None):
        raise HTTPException(400, "Joylashuv to'liq emas")
    if body.lat is not None and not (-90 <= body.lat <= 90 and -180 <= body.lon <= 180):
        raise HTTPException(400, "Joylashuv noto'g'ri")
    return {"when_kind": body.when_kind, "when_time": wt if body.when_kind == "custom" else "", "date": d.isoformat(),
            "place": place, "description": body.description.strip()[:500], "lat": body.lat, "lon": body.lon}


def _get_hashar(hid: int) -> dict:
    h = db.q("SELECT * FROM hashars WHERE id=?", (hid,), one=True)
    if not h or h["status"] != "active":
        raise HTTPException(404, "Hashar topilmadi yoki bekor qilingan")
    return h


@app.get("/api/hashars")
async def api_hashars(user: dict = Depends(member)):
    rows = db.q("SELECT * FROM hashars WHERE status='active' AND date>=? ORDER BY date, id", (db.now().date().isoformat(),))
    return {"hashars": [hashar_json(h, user) for h in rows], "can_create": db.is_admin(user)}


@app.post("/api/admin/hashars")
async def api_hashar_create(body: HasharIn, user: dict = Depends(admin)):
    v = validate_hashar(body)
    hid = db.x("INSERT INTO hashars(author_id,when_kind,when_time,date,place,description,lat,lon,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,'active',?,?)",
               (user["tg_id"], v["when_kind"], v["when_time"], v["date"], v["place"], v["description"], v["lat"], v["lon"], db.now_str(), db.now_str()))
    h = _get_hashar(hid)
    bg(bl.broadcast(hashar_text(h, "🤝 <b>Hashar e'lon qilindi!</b>") + "\n\nBorishingizni ilovada tasdiqlang 👇", exclude=[user["tg_id"]]))
    return {"id": hid}


@app.put("/api/admin/hashars/{hid}")
async def api_hashar_edit(hid: int, body: HasharIn, user: dict = Depends(admin)):
    old = _get_hashar(hid)
    v = validate_hashar(body)
    changed = any(old.get(k) != v[k] for k in v)
    db.x("UPDATE hashars SET when_kind=?, when_time=?, date=?, place=?, description=?, lat=?, lon=?, updated_at=? WHERE id=?",
         (v["when_kind"], v["when_time"], v["date"], v["place"], v["description"], v["lat"], v["lon"], db.now_str(), hid))
    if changed:
        h = _get_hashar(hid)
        bg(bl.broadcast(hashar_text(h, "✏️ <b>Hashar ma'lumotlari o'zgardi</b>") + "\n\nIlovada borishingizni tekshiring 👇"))
    return {"ok": True, "changed": changed}


@app.delete("/api/admin/hashars/{hid}")
async def api_hashar_cancel(hid: int, user: dict = Depends(admin)):
    h = _get_hashar(hid)
    db.x("UPDATE hashars SET status='cancelled', updated_at=? WHERE id=?", (db.now_str(), hid))
    bg(bl.broadcast(hashar_text(h, "❌ <b>Hashar bekor qilindi</b>"), with_button=False))
    return {"ok": True}


@app.post("/api/hashars/{hid}/join")
async def api_hashar_join(hid: int, user: dict = Depends(member)):
    _get_hashar(hid)
    db.x("INSERT OR IGNORE INTO hashar_joins(hashar_id,user_id,created_at) VALUES(?,?,?)", (hid, user["tg_id"], db.now_str()))
    return {"ok": True}


@app.delete("/api/hashars/{hid}/join")
async def api_hashar_leave(hid: int, user: dict = Depends(member)):
    db.x("DELETE FROM hashar_joins WHERE hashar_id=? AND user_id=?", (hid, user["tg_id"]))
    return {"ok": True}


# ------------------------------------------------------------------ rejalashtiruvchi
async def expire_rides():
    """Muddati o'tgan (yoki o'chirilgan) e'lonlarning bot xabarlarini o'chiradi / «Muddati o'tdi» qiladi."""
    rows = db.q("SELECT DISTINCT b.ref_id FROM bcasts b LEFT JOIN rides r ON r.id=b.ref_id "
                "WHERE b.kind='ride' AND (r.id IS NULL OR r.expires_at <= ?)", (db.now_str(),))
    for r in rows:
        await bl.retire_broadcasts("ride", r["ref_id"])


async def expiry_loop():
    await asyncio.sleep(10)
    while True:
        try:
            await expire_rides()
        except Exception:
            log.exception("expire_rides")
        await asyncio.sleep(60)

BOOT_TS = time.time()
BACKUP_HOUR = 23                 # avtomatik zaxira: har kuni 23:00–23:59 (Asia/Tashkent) oralig'ida, kuniga ko'pi bilan 1 marta
BACKUP_MIN_UPTIME = 600          # ishga tushgandan/uyg'ongandan keyin kamida 10 daqiqa o'tmaguncha yubormaydi
_poll_state = {"date": None}
_backup_state = {"date": None, "fp": None}   # jarayon xotirasi (Render uyquga ketsa tozalanadi — shuning uchun qo'shimcha himoyalar bor)


async def maybe_auto_backup(uptime: float | None = None) -> bool:
    """Avtomatik zaxira. Yuborilmaydigan holatlar: (1) belgilangan soat emas, (2) bugun yuborilgan, (3) endigina ishga tushgan/uyg'ongan,
    (4) bazada oddiy a'zo yo'q (reset bo'lgan, deyarli bo'sh baza), (5) oxirgi zaxiradan beri ma'lumot o'zgarmagan."""
    now = db.now()
    if now.hour != BACKUP_HOUR or not bl.bot:
        return False
    today = now.date().isoformat()
    if db.get_setting("last_backup") == today or _backup_state["date"] == today:
        return False
    if (time.time() - BOOT_TS if uptime is None else uptime) < BACKUP_MIN_UPTIME:
        return False
    if db.member_count() == 0:
        log.info("Avto-zaxira o'tkazib yuborildi: bazada oddiy a'zo yo'q")
        return False
    fp = db.fingerprint()
    if fp == _backup_state["fp"]:
        return False
    db.set_setting("last_backup", today)
    _backup_state.update(date=today, fp=fp)
    for a in db.admin_ids()[:3]:
        try:
            await bl.send_backup(a)
        except Exception as e:
            log.warning("backup: %s", e)
    return True


async def scheduler():
    await asyncio.sleep(3)
    while True:
        try:
            db.cleanup()
            now = db.now()
            if db.get_setting("daily_poll_enabled"):
                hhmm = db.get_setting("daily_poll_time") or "08:00"
                # faqat belgilangan vaqtdan keyingi 60 daqiqa ichida (Render uyg'onganda kun bo'yi qayta-qayta ochmaslik uchun)
                h, mi = (int(x) for x in hhmm.split(":"))
                start = now.replace(hour=h, minute=mi, second=0, microsecond=0)
                today = now.date().isoformat()
                if (start <= now < start + timedelta(minutes=60) and _poll_state["date"] != today
                        and not db.q("SELECT 1 FROM polls WHERE date=? AND auto=1", (today,), one=True)):
                    _poll_state["date"] = today
                    await open_new_poll(auto=True, notify=True)
                    log.info("Kunlik futbol so'rovnomasi ochildi")
            await maybe_auto_backup()
        except Exception:
            log.exception("scheduler")
        await asyncio.sleep(30)


app.mount("/static", StaticFiles(directory=os.path.join(BASE, "static")), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=config.PORT)
