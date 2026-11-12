"""Mobil o'lchamda skrinshotlar (playwright + chrome). Server o'zi ishga tushiriladi, test ma'lumotlari bilan."""
import os, subprocess, sys, tempfile, time, json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import httpx
from auth import make_init_data
from playwright.sync_api import sync_playwright

TOKEN = "123456:TEST_TOKEN_FOR_LOCAL_TESTS"; PORT = 8765; BASE = f"http://127.0.0.1:{PORT}"
OUT = os.path.join(ROOT, "screens"); os.makedirs(OUT, exist_ok=True)
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
    call(1001, "PUT", "/api/admin/football", {"min_players": 10, "game_time": "Bugun 20:30", "game_place": "Markaziy minifutzal maydon", "daily_poll_enabled": False, "daily_poll_time": "08:00"})
    call(1001, "POST", "/api/admin/football/new-poll")
    for uid, a in [(1001, "yes"), (2001, "yes"), (2002, "no"), (2003, "yes")]: call(uid, "POST", "/api/football/vote", {"answer": a})

    STUB = "window.Telegram={WebApp:{initData:%s,ready(){},expand(){},setHeaderColor(){},setBackgroundColor(){},HapticFeedback:{impactOccurred(){}}}};"
    with sync_playwright() as p:
        br = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        def page_for(uid):
            ctx = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, locale="uz")
            pg = ctx.new_page()
            pg.route("**/telegram-web-app.js", lambda r: r.fulfill(content_type="application/javascript", body=STUB % json.dumps(I[uid])))
            errs = []; pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
            return pg, errs
        def shot(pg, name, full=False, wait=700):
            pg.wait_for_timeout(wait); path = os.path.join(OUT, name + ".png"); pg.screenshot(path=path, full_page=full); print("saved", path)
        allerrs = []
        pg, errs = page_for(2003); allerrs += errs
        pg.goto(BASE + "/"); pg.evaluate("localStorage.clear()"); pg.reload()
        shot(pg, "01_namoz_vaqtlari")
        pg.click('.seg button[data-s=qibla]'); shot(pg, "02_qibla")
        pg.click('.seg button[data-s=tasbeh]'); pg.wait_for_timeout(200)
        for _ in range(7): pg.click('#tb')
        shot(pg, "03_tasbeh")
        pg.click('.seg button[data-s=dua]'); pg.click('.dua summary >> nth=1'); shot(pg, "04_duolar", full=False)
        pg.click('#tabs button[data-tab=jamoat]'); shot(pg, "05_jamoat_vaqtlari")
        pg.click('#tabs button[data-tab=birga]'); shot(pg, "06_bomdodga_kim_boradi", full=True)
        pg.click('#bDrv'); shot(pg, "07_birga_forma")
        pg.click('#sheetBox .btn.ghost'); pg.click('#tabs button[data-tab=futbol]'); shot(pg, "08_futbol", full=True)
        # admin
        pga, e2 = page_for(1001); allerrs += e2
        pga.goto(BASE + "/"); pga.evaluate("localStorage.setItem('tab','futbol')"); pga.reload()
        shot(pga, "09_futbol_admin", full=True)
        pga.click('#tabs button[data-tab=jamoat]'); pga.click('#editJ'); shot(pga, "10_jamoat_admin_forma")
        pga.click('#sheetBox .btn.ghost'); pga.click('#tabs button[data-tab=profil]'); shot(pga, "11_profil_admin_azolar", full=True)
        # ro'yxatdan o'tmagan
        I[3000] = init(3000, "Yangi", "yangi_user"); 
        pgn, e3 = page_for(3000); allerrs += e3
        pgn.goto(BASE + "/"); pgn.evaluate("localStorage.setItem('tab','birga')"); pgn.reload()
        shot(pgn, "12_royxatdan_otish", full=True)
        br.close()
    print("JS xatolari:", allerrs or "yo'q")
finally:
    srv.terminate()
