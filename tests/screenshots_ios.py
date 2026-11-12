"""Mobil o'lchamda skrinshotlar (playwright + chrome). Server o'zi ishga tushiriladi, test ma'lumotlari bilan."""
import os, subprocess, sys, tempfile, time, json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import httpx
from auth import make_init_data
from playwright.sync_api import sync_playwright

TOKEN = "123456:TEST_TOKEN_FOR_LOCAL_TESTS"; PORT = 8766; BASE = f"http://127.0.0.1:{PORT}"
OUT = os.path.join(ROOT, "screens_ios"); os.makedirs(OUT, exist_ok=True)
tmp = tempfile.mkdtemp()
env = dict(os.environ, BOT_TOKEN=TOKEN, DISABLE_BOT="1", DB_PATH=os.path.join(tmp, "s.db"), ADMIN_IDS="1001", PORT=str(PORT), MODE="polling")
srv = subprocess.Popen([sys.executable, "main.py"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(50):
        try:
            if httpx.get(BASE + "/health").status_code == 200: break
        except Exception: time.sleep(0.2)
    def init(uid, name, un=None):
        u = {"id": uid, "first_name": name}; 
        if un: u["username"] = un
        return make_init_data(u, TOKEN)
    I = {3000: init(3000, "Yangi", "yangi_user"), 1001: init(1001, "Javohir", "javohir"), 2001: init(2001, "Alisher", "alisher_k"), 2002: init(2002, "Vali"), 2003: init(2003, "Sardor", "sardor"), 2004: init(2004, "Bobur"), 2005: init(2005, "Aziz")}
    def call(uid, method, path, body=None):
        r = httpx.request(method, BASE + path, headers={"X-Init-Data": I[uid]}, json=body); r.raise_for_status(); return r.json()
    call(1001, "GET", "/api/me")
    for uid, nm in [(2001, "Alisher Karimov"), (2002, "Vali Aliyev"), (2003, "Sardor Rahimov"), (2004, "Bobur Ergashev")]:
        call(uid, "POST", "/api/register", {"name": nm, "phone": f"+99890123{uid}"})
        if uid != 2004: call(1001, "POST", f"/api/admin/users/{uid}/status", {"status": "approved"})
    call(1001, "PUT", "/api/admin/jamoat", {"times": {"bomdod": "05:50", "peshin": "13:00", "asr": "15:40", "shom": "17:12", "xufton": "19:00"}, "juma_time": "13:15", "note": "Juma xutbasi 12:50 da boshlanadi", "offsets": {}})
    call(2001, "POST", "/api/rides", {"kind": "driver", "prayer": "bomdod", "day": "tomorrow", "depart_time": "05:20", "seats": 3, "note": "Markaz ko'chasidan olaman", "share_phone": True})
    call(2002, "POST", "/api/rides", {"kind": "request", "prayer": "bomdod", "day": "tomorrow", "depart_time": "05:25", "note": "Maktab oldida turaman"})
    rid = call(2003, "POST", "/api/rides", {"kind": "driver", "prayer": "bomdod", "day": "tomorrow", "depart_time": "05:30", "seats": 4})["id"]
    call(2002, "POST", f"/api/rides/{rid}/join")
    import datetime as _d
    _tm = (_d.datetime.utcnow() + _d.timedelta(hours=5, days=1)).date().isoformat()
    h1 = call(1001, "POST", "/api/admin/hashars", {"when_kind": "bomdod_after", "date": _tm, "place": "Masjid oldi, maktab yo'li", "description": "Ariq va yo'l bo'yini tozalash. Belkurak va qo'lqop olib keling.", "lat": 39.96, "lon": 68.78})["id"]
    call(1001, "POST", "/api/admin/hashars", {"when_kind": "custom", "when_time": "15:30", "date": _tm, "place": "Qabriston atrofi", "description": "To'siqni ta'mirlash"})
    for uid in (2001, 2002, 2003): call(uid, "POST", f"/api/hashars/{h1}/join")
    call(1001, "PUT", "/api/admin/football", {"min_players": 10, "game_time": "Bugun 20:30", "game_place": "Markaziy minifutzal maydon", "daily_poll_enabled": False, "daily_poll_time": "08:00"})
    call(1001, "POST", "/api/admin/football/new-poll")
    for uid, a in [(1001, "yes"), (2001, "yes"), (2002, "no"), (2003, "yes")]: call(uid, "POST", "/api/football/vote", {"answer": a})

    STUB = "window.Telegram={WebApp:{initData:%s,ready(){},expand(){},setHeaderColor(){},setBackgroundColor(){},HapticFeedback:{impactOccurred(){},selectionChanged(){}}}};"
    with sync_playwright() as p:
        br = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        def page_for(uid, dark=False):
            ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, locale="uz", color_scheme="dark" if dark else "light")
            pg = ctx.new_page()
            pg.route("**/telegram-web-app.js", lambda r: r.fulfill(content_type="application/javascript", body=STUB % json.dumps(I[uid])))
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
            return pg, errs
        def shot(pg, name, full=False, wait=900):
            pg.wait_for_timeout(wait); path = os.path.join(OUT, name + ".png")
            if full:
                h = pg.evaluate("document.documentElement.scrollHeight"); pg.set_viewport_size({"width": 390, "height": max(844, min(h, 2400))}); pg.wait_for_timeout(300)
            pg.screenshot(path=path); print("saved", path)
            if full: pg.set_viewport_size({"width": 390, "height": 844})
        allerrs = []
        pg, e = page_for(2003); allerrs += e
        pg.goto(BASE + "/"); pg.evaluate("localStorage.clear()"); pg.reload()
        shot(pg, "01_namoz")
        pg.click('.seg button[data-s=qibla]'); shot(pg, "13_qibla")
        pg.click('.seg button[data-s=tasbeh]'); shot(pg, "14_tasbeh")
        pg.click('.seg button[data-s=dua]'); shot(pg, "15_duolar")
        pg.click('#tabs button[data-tab=jamoat]'); shot(pg, "02_jamoat")
        pg.click('#tabs button[data-tab=birga]'); shot(pg, "03_birga_royxat", full=True)
        pg.click('#bDrv'); shot(pg, "04_birga_forma")
        pg.click('#sheetBox .btn.ghost:has-text("Bekor")'); pg.click('#tabs button[data-tab=hashar]'); shot(pg, "05_hashar", full=True)
        pg.click('#tabs button[data-tab=futbol]'); shot(pg, "06_futbol", full=True)
        pga, e = page_for(1001); allerrs += e
        pga.goto(BASE + "/"); pga.evaluate("localStorage.setItem('tab','profil')"); pga.reload()
        shot(pga, "07_profil_admin", full=True)
        pga.click('#tabs button[data-tab=futbol]'); shot(pga, "08_futbol_admin", full=True)
        pga.click('#tabs button[data-tab=jamoat]'); pga.click('#editJ'); shot(pga, "09_jamoat_forma_admin")
        pgd, e = page_for(2003, dark=True); allerrs += e
        pgd.goto(BASE + "/"); pgd.evaluate("localStorage.setItem('tab','namoz')"); pgd.reload()
        shot(pgd, "10_dark_namoz")
        pgd.click('#tabs button[data-tab=birga]'); shot(pgd, "11_dark_birga", full=True)
        pgd.click('#tabs button[data-tab=futbol]'); shot(pgd, "12_dark_futbol", full=True)
        br.close()
    print("JS xatolari:", allerrs or "yo'q")
finally:
    srv.terminate()
