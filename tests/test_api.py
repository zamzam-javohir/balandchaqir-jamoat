"""Lokal API testi: soxta imzolangan initData bilan (bot o'chirilgan, internet kerak emas).
Ishga tushirish:  python tests/test_api.py
"""
import os, sys, tempfile, time
tmp = tempfile.mkdtemp()
os.environ.update(BOT_TOKEN="123456:TEST_TOKEN_FOR_LOCAL_TESTS", DISABLE_BOT="1", DB_PATH=os.path.join(tmp, "t.db"),
                  ADMIN_IDS="1001", MODE="polling")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi.testclient import TestClient
from auth import make_init_data
import config, main, db

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond: ok += 1; print("  OK  ", name)
    else: fail += 1; print("  FAIL", name, extra)

def H(uid, name="User", username=None, token=None, age=0):
    u = {"id": uid, "first_name": name}
    if username: u["username"] = username
    return {"X-Init-Data": make_init_data(u, token or config.BOT_TOKEN, int(time.time()) - age)}

with TestClient(main.app) as c:
    admin, a, b, d = H(1001, "Admin", "admin_u"), H(2001, "Ali", "ali_u"), H(2002, "Vali"), H(2003, "Sami")
    print("[auth]")
    check("initData yo'q -> 401", c.get("/api/me").status_code == 401)
    check("soxta token -> 401", c.get("/api/me", headers=H(5, token="1:WRONG")).status_code == 401)
    check("eskirgan initData -> 401", c.get("/api/me", headers=H(5, age=10 * 86400)).status_code == 401)
    bad = dict(a); bad["X-Init-Data"] = bad["X-Init-Data"].replace("Ali", "Alx")
    check("o'zgartirilgan initData -> 401", c.get("/api/me", headers=bad).status_code == 401)
    r = c.get("/api/me", headers=admin).json()
    check("env admin avtomatik tasdiqlanadi", r["is_admin"] and r["status"] == "approved", r)
    r = c.get("/api/me", headers=a).json()
    check("yangi foydalanuvchi status=new", r["status"] == "new", r)

    print("[a'zolik]")
    check("tasdiqlanmagan -> /api/rides 403", c.get("/api/rides", headers=a).status_code == 403)
    check("ismsiz ro'yxat 400", c.post("/api/register", json={"name": "A", "phone": "901234567"}, headers=a).status_code == 400)
    check("telefonsiz 400", c.post("/api/register", json={"name": "Ali Karimov"}, headers=a).status_code == 400)
    r = c.post("/api/register", json={"name": "Ali Karimov", "phone": "90 123 45 67"}, headers=a).json()
    check("ro'yxat -> pending, +998", r["status"] == "pending" and r["phone"] == "+998901234567", r)
    check("pending -> football 403", c.get("/api/football", headers=a).status_code == 403)
    check("oddiy a'zo admin API 403", c.get("/api/admin/users", headers=a).status_code == 403)
    r = c.get("/api/admin/users?status=pending", headers=admin).json()
    check("admin kutayotganlarni ko'radi", any(u["id"] == 2001 for u in r["users"]), r)
    for uid, h, nm in [(2001, a, None), (2002, b, "Vali Aliyev"), (2003, d, "Sami Karimov")]:
        if nm: c.post("/api/register", json={"name": nm, "phone": f"+99890000{uid}"}, headers=h)
        r = c.post(f"/api/admin/users/{uid}/status", json={"status": "approved"}, headers=admin)
        check(f"admin {uid} ni tasdiqladi", r.status_code == 200)
    check("tasdiqlangach me.status=approved", c.get("/api/me", headers=a).json()["status"] == "approved")

    print("[admin boshqaruvi]")
    check("oddiy a'zo admin qila olmaydi", c.post("/api/admin/users/2002/admin", json={"is_admin": True}, headers=a).status_code == 403)
    check("o'zini o'zgartira olmaydi", c.post("/api/admin/users/1001/admin", json={"is_admin": False}, headers=admin).status_code == 400)
    check("yo'q foydalanuvchi 404", c.post("/api/admin/users/9999/admin", json={"is_admin": True}, headers=admin).status_code == 404)
    r = c.post("/api/admin/users/2001/admin", json={"is_admin": True}, headers=admin)
    check("admin qilindi", r.status_code == 200 and c.get("/api/me", headers=a).json()["is_admin"])
    r = c.get("/api/admin/users?status=admins", headers=admin).json()
    ids = {u["id"] for u in r["users"]}
    check("Adminlar tabi: 1001 va 2001", ids == {1001, 2001} and r["counts"]["admins"] == 2, r)
    su = next(u for u in r["users"] if u["id"] == 1001)
    check("super-admin belgilangan", su["is_super"] and not next(u for u in r["users"] if u["id"] == 2001)["is_super"])
    check("yangi admin boshqani admin qila oladi", c.post("/api/admin/users/2002/admin", json={"is_admin": True}, headers=a).status_code == 200)
    check("super-adminni olib bo'lmaydi", c.post("/api/admin/users/1001/admin", json={"is_admin": False}, headers=a).status_code == 400)
    check("tasdiqlanmagan odamni admin qilib bo'lmaydi", c.post("/api/admin/users/3001/admin", json={"is_admin": True}, headers=admin).status_code in (400, 404))
    check("adminlikdan olish", c.post("/api/admin/users/2002/admin", json={"is_admin": False}, headers=admin).status_code == 200
          and not c.get("/api/me", headers=b).json()["is_admin"])
    c.post("/api/admin/users/2001/admin", json={"is_admin": False}, headers=admin)
    check("2001 oddiy a'zoga qaytdi", not c.get("/api/me", headers=a).json()["is_admin"])
    check("endi admin API 403", c.get("/api/admin/users", headers=a).status_code == 403)

    print("[namoz]")
    r = c.get("/api/prayer", headers=a).json()
    keys = [t["key"] for t in r["times"]]
    tm = [t["time"] for t in r["times"]]
    check("6 ta vaqt, o'sish tartibida", keys == ["bomdod", "quyosh", "peshin", "asr", "shom", "xufton"] and tm == sorted(tm), tm)
    check("keyingi namoz bor", r["next"]["seconds"] > 0, r["next"])
    check("qibla ~241°", 238 < r["qibla"] < 245, r["qibla"])
    r2 = c.get("/api/prayer?date=2026-12-21", headers=a).json()
    check("sana bo'yicha so'rov", r2["date"] == "2026-12-21")

    bom0 = c.get("/api/prayer", headers=a).json()["times"][0]["time"]
    print("[jamoat vaqtlari]")
    check("oddiy a'zo tahrirlay olmaydi", c.put("/api/admin/jamoat", json={"times": {}}, headers=a).status_code == 403)
    check("noto'g'ri vaqt 400", c.put("/api/admin/jamoat", json={"times": {"bomdod": "25:99"}}, headers=admin).status_code == 400)
    r = c.put("/api/admin/jamoat", json={"times": {"bomdod": "05:45", "peshin": "13:00", "asr": "15:30", "shom": "17:10", "xufton": "19:00"}, "juma_time": "13:15", "note": "Test", "offsets": {"bomdod": 2}}, headers=admin)
    check("admin saqlaydi", r.status_code == 200 and r.json()["juma_time"] == "13:15", r.text)
    r = c.get("/api/jamoat", headers=a).json()
    check("a'zo ko'radi", r["times"]["bomdod"] == "05:45" and r["note"] == "Test" and not r["is_admin"], r)
    p1 = c.get("/api/prayer", headers=a).json()["times"][0]["time"]
    h0, m0 = map(int, bom0.split(":")); h1, m1 = map(int, p1.split(":"))
    check("offset ta'siri (bomdod +2 daq)", (h1 * 60 + m1) - (h0 * 60 + m0) == 2, (bom0, p1))

    print("[birga borish]")
    check("o'tgan vaqt rad", c.post("/api/rides", json={"kind": "driver", "prayer": "bomdod", "day": "today", "depart_time": "00:01", "seats": 2}, headers=a).status_code == 400 or db.now().hour == 0)
    r = c.post("/api/rides", json={"kind": "driver", "prayer": "bomdod", "day": "tomorrow", "depart_time": "05:00", "seats": 1, "share_phone": True, "note": "Markazdan"}, headers=a)
    check("haydovchi e'loni", r.status_code == 200, r.text); rid = r.json()["id"]
    r = c.post("/api/rides", json={"kind": "request", "prayer": "bomdod", "day": "tomorrow", "depart_time": "05:10"}, headers=b)
    check("so'rov e'loni", r.status_code == 200); rid2 = r.json()["id"]
    check("0 joy 400", c.post("/api/rides", json={"kind": "driver", "prayer": "bomdod", "day": "tomorrow", "depart_time": "05:00", "seats": 0}, headers=a).status_code == 400)
    r = c.get("/api/rides?prayer=bomdod", headers=b).json()["rides"]
    ra = next(x for x in r if x["id"] == rid)
    check("ro'yxatda 2 ta e'lon", len(r) == 2)
    check("haydovchi telefoni ulashilgan", ra["author"]["phone"] == "+998901234567" and ra["free"] == 1, ra)
    check("boshqa namozda e'lon yo'q", c.get("/api/rides?prayer=asr", headers=b).json()["rides"] == [])
    r = c.post("/api/rides", json={"kind": "driver", "prayer": "bomdod", "day": "tomorrow", "depart_time": "05:05", "seats": 2, "lat": 39.96, "lon": 68.78}, headers=a)
    lid = r.json()["id"]
    check("joylashuvli e'lon yaratildi", r.status_code == 200)
    ride = next(x for x in c.get("/api/rides?prayer=bomdod", headers=b).json()["rides"] if x["id"] == lid)
    check("e'londa lat/lon qaytadi", ride["has_location"] and ride["lat"] == 39.96 and ride["lon"] == 68.78, ride)
    nl = next(x for x in c.get("/api/rides?prayer=bomdod", headers=b).json()["rides"] if x["id"] == rid)
    check("joylashuvsiz e'lon: has_location=False", nl["has_location"] is False and nl["lat"] is None)
    check("faqat lat -> 400", c.post("/api/rides", json={"kind": "request", "prayer": "bomdod", "day": "tomorrow", "depart_time": "05:10", "lat": 39.9}, headers=b).status_code == 400)
    check("noto'g'ri lat -> 400", c.post("/api/rides", json={"kind": "request", "prayer": "bomdod", "day": "tomorrow", "depart_time": "05:10", "lat": 99, "lon": 10}, headers=b).status_code == 400)
    locs = []
    async def _loc(chat_id, lat, lon): locs.append((chat_id, lat, lon)); return True
    _orig = main.bl.safe_location; main.bl.safe_location = _loc
    check("joylashuvli e'longa qo'shilish", c.post(f"/api/rides/{lid}/join", headers=b).status_code == 200)
    main.bl.safe_location = _orig
    check("joiner va muallifga sendLocation chaqirildi", {x[0] for x in locs} == {2001, 2002} and all(x[1:] == (39.96, 68.78) for x in locs), locs)
    c.delete(f"/api/rides/{lid}", headers=a)
    check("o'z e'loniga qo'shila olmaydi", c.post(f"/api/rides/{rid}/join", headers=a).status_code == 400)
    r = c.post(f"/api/rides/{rid}/join", headers=b)
    check("«Men ham boraman» ishladi", r.status_code == 200 and r.json()["contact"]["username"] == "ali_u", r.text)
    check("ikkinchi marta 409", c.post(f"/api/rides/{rid}/join", headers=b).status_code == 409)
    check("joy qolmadi 409", c.post(f"/api/rides/{rid}/join", headers=d).status_code == 409)
    mine = next(x for x in c.get("/api/rides?prayer=bomdod", headers=a).json()["rides"] if x["id"] == rid)
    check("muallif qo'shilganlarni ko'radi", len(mine["joiners"]) == 1 and mine["joiners"][0]["name"] == "Vali Aliyev", mine["joiners"])
    check("«Men olib ketaman»", c.post(f"/api/rides/{rid2}/join", headers=a).status_code == 200)
    check("begona o'chira olmaydi", c.delete(f"/api/rides/{rid}", headers=d).status_code == 403)
    check("muallif o'chiradi", c.delete(f"/api/rides/{rid2}", headers=b).status_code == 200)
    # muddati o'tish
    db.x("UPDATE rides SET expires_at='2000-01-01 00:00' WHERE id=?", (rid,))
    check("muddati o'tgan e'lon ko'rinmaydi", c.get("/api/rides?prayer=bomdod", headers=b).json()["rides"] == [])
    check("muddati o'tganga qo'shilib bo'lmaydi 404", c.post(f"/api/rides/{rid}/join", headers=d).status_code == 404)

    print("[futbol]")
    check("so'rovnomasiz ovoz 409", c.post("/api/football/vote", json={"answer": "yes"}, headers=a).status_code == 409)
    check("oddiy a'zo so'rovnoma och olmaydi", c.post("/api/admin/football/new-poll", headers=a).status_code == 403)
    r = c.put("/api/admin/football", json={"min_players": 3, "game_time": "20:00", "game_place": "Minifutzal", "daily_poll_enabled": False, "daily_poll_time": "08:00"}, headers=admin)
    check("admin sozlamalari", r.status_code == 200 and r.json()["min"] == 3, r.text)
    r = c.post("/api/admin/football/new-poll", headers=admin).json()
    check("yangi so'rovnoma", r["poll"] is not None and r["yes_count"] == 0, r)
    check("noto'g'ri javob 400", c.post("/api/football/vote", json={"answer": "maybe"}, headers=a).status_code == 400)
    c.post("/api/football/vote", json={"answer": "yes"}, headers=a); c.post("/api/football/vote", json={"answer": "no"}, headers=b)
    r = c.post("/api/football/vote", json={"answer": "yes"}, headers=d).json()
    check("hisob: 2 ha, 1 yo'q, yetmaydi", r["yes_count"] == 2 and r["no_count"] == 1 and not r["enough"], r)
    check("hali e'lon qilinmagan", db.q("SELECT notified FROM polls ORDER BY id DESC LIMIT 1", one=True)["notified"] == 0)
    r = c.post("/api/football/vote", json={"answer": "yes"}, headers=b).json()   # b fikrini o'zgartirdi
    check("fikr o'zgartirish -> 3 ha, yetarli", r["yes_count"] == 3 and r["enough"] and r["no_count"] == 0, r)
    check("«O'yin bo'ladi» bir marta belgilandi", db.q("SELECT notified FROM polls ORDER BY id DESC LIMIT 1", one=True)["notified"] == 1)
    check("a'zo sozlamani ko'rmaydi", "settings" not in c.get("/api/football", headers=a).json())
    # kunlik so'rovnoma
    from datetime import timedelta as _td
    _pt = (db.now() - _td(minutes=5)).strftime("%H:%M")
    c.put("/api/admin/football", json={"min_players": 3, "daily_poll_enabled": True, "daily_poll_time": _pt}, headers=admin)
    import asyncio
    n0 = db.q("SELECT count(*) n FROM polls", one=True)["n"]
    async def one_tick():
        t = asyncio.create_task(main.scheduler()); await asyncio.sleep(3.5); t.cancel()
    asyncio.run(one_tick())
    check("rejalashtiruvchi kunlik so'rovnoma ochdi", db.q("SELECT count(*) n FROM polls", one=True)["n"] == n0 + 1)

    print("[yangi: xabarnomalar, hashar, e'lon muddati]")
    import asyncio, types, datetime as _dt
    class FakeBot:
        def __init__(self): self.sent = []; self.deleted = []; self.edited = []; self.fail_delete = set(); self.blocked = set(); self._id = 100
        async def send_message(self, chat_id, text, reply_markup=None, **kw):
            if chat_id in self.blocked: raise RuntimeError("Forbidden: bot was blocked by the user")
            self._id += 1; self.sent.append((chat_id, text, self._id)); return types.SimpleNamespace(message_id=self._id)
        async def send_location(self, *a, **k): return True
        async def delete_message(self, chat_id, message_id):
            if chat_id in self.fail_delete: raise RuntimeError("can't delete")
            self.deleted.append((chat_id, message_id))
        async def edit_message_text(self, text, chat_id, message_id, reply_markup=None): self.edited.append((chat_id, message_id, text))
    fb = FakeBot(); main.bl.bot = fb
    def settle():
        for _ in range(200):
            if not main._bg: break
            time.sleep(0.05)
    def msgs(sub): return [x for x in fb.sent if sub in x[1]]
    approved = set(db.approved_ids())
    real_now = db.now
    def fake_now(h, mi=0):
        base = real_now().replace(hour=h, minute=mi, second=0, microsecond=0)
        db.now = lambda: base
    c.put("/api/admin/jamoat", json={"times": {"bomdod": "05:45", "peshin": "13:00", "asr": "15:30", "shom": "17:10", "xufton": "19:00"}, "juma_time": "13:15", "note": "Test", "offsets": {}}, headers=admin)
    settle(); fb.sent.clear()

    # --- jamoat vaqti o'zgarishi
    c.put("/api/admin/jamoat", json={"times": {"bomdod": "06:10", "peshin": "13:00", "asr": "15:30", "shom": "17:10", "xufton": "19:00"}, "juma_time": "13:30", "note": "", "offsets": {}}, headers=admin)
    settle()
    jm = msgs("jamoati endi")
    check("Bomdod o'zgarishi hammaga xabar", len(jm) == len(approved) and "Bomdod jamoati endi <b>06:10</b> da" in jm[0][1] and {x[0] for x in jm} == approved, [x[0] for x in jm])
    check("Juma o'zgarishi xabari", "Juma namozi endi <b>13:30</b> da" in jm[0][1] and "Peshin" not in jm[0][1])
    fb.sent.clear()
    c.put("/api/admin/jamoat", json={"times": {"bomdod": "06:10", "peshin": "13:00", "asr": "15:30", "shom": "17:10", "xufton": "19:00"}, "juma_time": "13:30", "note": "x", "offsets": {}}, headers=admin)
    settle()
    check("o'zgarmasa xabar yo'q", not fb.sent)

    # --- keyingi jamoat namozi
    fake_now(20, 0)
    j = c.get("/api/jamoat", headers=a).json()
    check("Xuftondan keyin -> ertangi Bomdod", j["next_prayer"] == "bomdod" and j["next_day"] == "tomorrow", j)
    fake_now(14, 0)
    j = c.get("/api/jamoat", headers=a).json()
    check("14:00 -> Asr bugun", j["next_prayer"] == "asr" and j["next_day"] == "today" and j["passed"]["peshin"] and not j["passed"]["asr"], j)
    fake_now(5, 0)
    check("05:00 -> Bomdod bugun", c.get("/api/jamoat", headers=a).json()["next_prayer"] == "bomdod")

    # --- e'lon: muddat = jamoat vaqti, broadcast
    fake_now(14, 0)
    check("jamoat vaqti o'tgan namozga e'lon 400", c.post("/api/rides", json={"kind": "driver", "prayer": "peshin", "day": "today", "depart_time": "12:40", "seats": 2}, headers=a).status_code == 400)
    fb.sent.clear(); fb.blocked.add(2003)
    r = c.post("/api/rides", json={"kind": "driver", "prayer": "asr", "day": "today", "depart_time": "15:10", "seats": 2, "note": "Markazdan <b>"}, headers=a)
    settle()
    nid = r.json()["id"]
    row = db.q("SELECT * FROM rides WHERE id=?", (nid,), one=True)
    check("muddat = Asr jamoat vaqti (15:30)", row["expires_at"].endswith("15:30"), row["expires_at"])
    rm = msgs("Mashinada chiqaman")
    check("e'lon muallifdan boshqa a'zolarga yuborildi (bloklagan e'tiborsiz)", {x[0] for x in rm} == approved - {2001, 2003}, sorted(x[0] for x in rm))
    check("e'lon matni HTML-xavfsiz", "&lt;b&gt;" in rm[0][1] and "Asr" in rm[0][1])
    check("chat_id/message_id saqlandi", db.q("SELECT count(*) n FROM bcasts WHERE kind='ride' AND ref_id=?", (nid,), one=True)["n"] == len(rm))
    fb.blocked.clear()
    # --- muddati o'tgach: yashirin, xabarlar o'chiriladi, o'chmasa edit
    one = fb.sent[-1][0]; fb.fail_delete.add(one); fb.sent.clear()
    fake_now(15, 29)
    check("15:29 da ko'rinadi", any(x["id"] == nid for x in c.get("/api/rides?prayer=asr", headers=b).json()["rides"]))
    asyncio.run(main.expire_rides())
    check("muddatdan oldin xabarlar tegilmaydi", not fb.deleted and not fb.edited)
    fake_now(15, 31)
    check("15:31 da API'da yashirin", not any(x["id"] == nid for x in c.get("/api/rides?prayer=asr", headers=b).json()["rides"]))
    asyncio.run(main.expire_rides())
    check("xabarlar o'chirildi", len(fb.deleted) == len(rm) - 1, (len(fb.deleted), len(rm)))
    check("o'chmaganiga «Muddati o'tdi» edit", len(fb.edited) == 1 and fb.edited[0][0] == one and "Muddati o'tdi" in fb.edited[0][2], fb.edited)
    check("saqlangan yozuvlar tozalandi", db.q("SELECT count(*) n FROM bcasts WHERE ref_id=?", (nid,), one=True)["n"] == 0)
    n_del = len(fb.deleted); asyncio.run(main.expire_rides())
    check("qayta ishga tushirsa takrorlanmaydi", len(fb.deleted) == n_del)
    db.now = real_now; fb.fail_delete.clear(); fb.deleted.clear(); fb.edited.clear()

    # --- futbol xabarlari
    c.put("/api/admin/football", json={"min_players": 3, "game_time": "", "game_place": "", "daily_poll_enabled": False, "daily_poll_time": "08:00"}, headers=admin); settle(); fb.sent.clear()
    c.put("/api/admin/football", json={"min_players": 3, "game_time": "20:00", "game_place": "Maydon", "daily_poll_enabled": False, "daily_poll_time": "08:00"}, headers=admin); settle()
    check("o'yin e'lon qilindi xabari", len(msgs("Futbol o'yini e'lon qilindi")) == len(approved) and "20:00" in msgs("e'lon qilindi")[0][1])
    fb.sent.clear()
    c.put("/api/admin/football", json={"min_players": 3, "game_time": "21:00", "game_place": "Maydon", "daily_poll_enabled": False, "daily_poll_time": "08:00"}, headers=admin); settle()
    ch = msgs("Futbol o'yini o'zgardi")
    check("vaqt o'zgarishi xabari", len(ch) == len(approved) and "20:00 → <b>21:00</b>" in ch[0][1] and "Joy" not in ch[0][1], ch[:1])
    fb.sent.clear()
    c.put("/api/admin/football", json={"min_players": 4, "game_time": "21:00", "game_place": "Maydon", "daily_poll_enabled": False, "daily_poll_time": "08:00"}, headers=admin); settle()
    check("faqat min_players o'zgarsa xabar yo'q", not fb.sent)
    check("a'zo bekor qila olmaydi", c.post("/api/admin/football/cancel", headers=a).status_code == 403)
    c.post("/api/admin/football/new-poll", headers=admin); settle(); fb.sent.clear()
    r = c.post("/api/admin/football/cancel", headers=admin); settle()
    check("o'yin bekor qilindi xabari", r.status_code == 200 and len(msgs("Futbol o'yini bekor qilindi")) == len(approved))
    check("bekor qilgach so'rovnoma yopildi, vaqt tozalandi", r.json()["poll"] is None and r.json()["game"]["time"] == "")
    check("bekor qilinadigan o'yin yo'q 409", c.post("/api/admin/football/cancel", headers=admin).status_code == 409)

    # --- hashar
    def hz(**kw):
        body = {"when_kind": "bomdod_after", "date": real_now().date().isoformat(), "place": "Masjid oldi", "description": "Ariq tozalash"}; body.update(kw); return body
    check("a'zo hashar yarata olmaydi", c.post("/api/admin/hashars", json=hz(), headers=a).status_code == 403)
    check("a'zo hashar ro'yxatini ko'radi", c.get("/api/hashars", headers=a).json()["hashars"] == [])
    check("joysiz 400", c.post("/api/admin/hashars", json=hz(place=" "), headers=admin).status_code == 400)
    check("boshqa vaqtda HH:MM shart", c.post("/api/admin/hashars", json=hz(when_kind="custom"), headers=admin).status_code == 400)
    check("o'tgan sana 400", c.post("/api/admin/hashars", json=hz(date="2020-01-01"), headers=admin).status_code == 400)
    check("noto'g'ri tur 400", c.post("/api/admin/hashars", json=hz(when_kind="x"), headers=admin).status_code == 400)
    fb.sent.clear()
    r = c.post("/api/admin/hashars", json=hz(lat=39.9, lon=68.7), headers=admin); settle()
    hid = r.json()["id"]
    hm = msgs("Hashar e'lon qilindi")
    check("hashar e'loni a'zolarga (muallifdan boshqa) yuborildi", r.status_code == 200 and {x[0] for x in hm} == approved - {1001}, sorted(x[0] for x in hm))
    check("xabarda vaqt, joy, tavsif, xarita", all(s in hm[0][1] for s in ["Bomdoddan keyin", "Masjid oldi", "Ariq tozalash", "maps.google.com/?q=39.9,68.7"]), hm[0][1])
    check("a'zo ro'yxatda ko'radi", [x["id"] for x in c.get("/api/hashars", headers=a).json()["hashars"]] == [hid])
    check("Men boraman", c.post(f"/api/hashars/{hid}/join", headers=a).status_code == 200 and c.post(f"/api/hashars/{hid}/join", headers=b).status_code == 200)
    c.post(f"/api/hashars/{hid}/join", headers=b)
    hj = c.get("/api/hashars", headers=a).json()["hashars"][0]
    check("boradiganlar ro'yxati ko'rinadi, takror yo'q", hj["going_count"] == 2 and hj["joined"] and not hj["can_edit"], hj["going"])
    c.delete(f"/api/hashars/{hid}/join", headers=b)
    check("bekor qilish (borishni)", c.get("/api/hashars", headers=a).json()["hashars"][0]["going_count"] == 1)
    fb.sent.clear()
    check("a'zo tahrirlay olmaydi", c.put(f"/api/admin/hashars/{hid}", json=hz(), headers=a).status_code == 403)
    r = c.put(f"/api/admin/hashars/{hid}", json=hz(when_kind="custom", when_time="07:30", lat=39.9, lon=68.7), headers=admin); settle()
    em = msgs("Hashar ma'lumotlari o'zgardi")
    check("tahrir hammaga xabar", r.json()["changed"] and len(em) == len(approved) and "07:30" in em[0][1], len(em))
    fb.sent.clear()
    r = c.put(f"/api/admin/hashars/{hid}", json=hz(when_kind="custom", when_time="07:30", lat=39.9, lon=68.7), headers=admin); settle()
    check("o'zgarishsiz tahrir -> xabar yo'q", not r.json()["changed"] and not fb.sent)
    check("a'zo bekor qila olmaydi", c.delete(f"/api/admin/hashars/{hid}", headers=a).status_code == 403)
    r = c.delete(f"/api/admin/hashars/{hid}", headers=admin); settle()
    check("bekor qilish hammaga xabar", r.status_code == 200 and len(msgs("Hashar bekor qilindi")) == len(approved))
    check("bekor qilingan hashar ko'rinmaydi", c.get("/api/hashars", headers=a).json()["hashars"] == [])
    check("bekor qilinganga yozilib bo'lmaydi 404", c.post(f"/api/hashars/{hid}/join", headers=a).status_code == 404)
    check("tasdiqlanmagan hashar ko'rmaydi", c.get("/api/hashars", headers=H(9999)).status_code == 403)

    # --- avtomatik zaxira: kuniga 1 marta, ishga tushganda yubormaydi, bo'sh bazada yubormaydi
    docs = []
    async def _send_document(chat_id, f, caption=None, **k): docs.append((chat_id, caption)); return types.SimpleNamespace(message_id=1)
    fb.send_document = _send_document
    def auto(uptime):
        return asyncio.run(main.maybe_auto_backup(uptime=uptime))
    main._backup_state.update(date=None, fp=None); db.set_setting("last_backup", "")
    fake_now(23, 30)
    check("ishga tushgandan keyin (uptime 5s) yubormaydi", auto(5) is False and not docs)
    fake_now(10, 0)
    check("soat 23 emas -> yubormaydi", auto(5000) is False and not docs)
    fake_now(3, 5)
    check("eski qoida (03:00 dan keyin) endi ishlamaydi", auto(5000) is False and not docs)
    fake_now(23, 30)
    _mc = db.member_count; db.member_count = lambda: 0
    check("oddiy a'zo yo'q (reset) -> yubormaydi", auto(5000) is False and not docs)
    db.member_count = _mc
    check("23:30, uptime yetarli, a'zolar bor -> yuboradi", auto(5000) is True and docs and {d[0] for d in docs} <= set(db.admin_ids()), docs)
    check("izohda a'zolar soni ko'rsatilgan", "A'zolar:" in docs[0][1] and "tasdiq so'raladi" in docs[0][1], docs[0][1])
    n0 = len(docs)
    check("shu kuni qayta yubormaydi", auto(5000) is False and len(docs) == n0)
    main._backup_state["date"] = None; db.set_setting("last_backup", "")      # uyquga ketib uyg'ongandek: xotira/baza tozalandi
    check("o'zgarish bo'lmasa (xuddi shu ma'lumot) qayta yubormaydi", auto(5000) is False and len(docs) == n0)
    db.x("UPDATE users SET updated_at='2099-01-01 00:00' WHERE tg_id=2001")
    check("ma'lumot o'zgarsa yuboradi", auto(5000) is True and len(docs) > n0)
    db.now = real_now

    main.bl.bot = None

    print("[sahifa]")
    r = c.get("/")
    check("index.html beriladi", r.status_code == 200 and "Balandchaqir" in r.text)
    check("statik fayllar", c.get("/static/app.js").status_code == 200 and c.get("/static/app.css").status_code == 200)
    check("/health", c.get("/health").json() == {"ok": True})
    check("webhook noto'g'ri sir -> 403", c.post("/webhook/xxx", json={}).status_code == 403)

print(f"\nNatija: {ok} o'tdi, {fail} xato")
sys.exit(1 if fail else 0)
