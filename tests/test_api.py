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
    c.put("/api/admin/football", json={"min_players": 3, "daily_poll_enabled": True, "daily_poll_time": "00:00"}, headers=admin)
    import asyncio
    n0 = db.q("SELECT count(*) n FROM polls", one=True)["n"]
    async def one_tick():
        t = asyncio.create_task(main.scheduler()); await asyncio.sleep(3.5); t.cancel()
    asyncio.run(one_tick())
    check("rejalashtiruvchi kunlik so'rovnoma ochdi", db.q("SELECT count(*) n FROM polls", one=True)["n"] == n0 + 1)

    print("[sahifa]")
    r = c.get("/")
    check("index.html beriladi", r.status_code == 200 and "Balandchaqir" in r.text)
    check("statik fayllar", c.get("/static/app.js").status_code == 200 and c.get("/static/app.css").status_code == 200)
    check("/health", c.get("/health").json() == {"ok": True})
    check("webhook noto'g'ri sir -> 403", c.post("/webhook/xxx", json={}).status_code == 403)

print(f"\nNatija: {ok} o'tdi, {fail} xato")
sys.exit(1 if fail else 0)
