"""Baza qatlami testi (SQLite yoki Postgres: TEST_DATABASE_URL berilsa). python tests/test_db.py"""
import json, os, sqlite3, sys, tempfile
os.environ.pop("DATABASE_URL", None)
if os.getenv("TEST_DATABASE_URL"): os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ.update(BOT_TOKEN="123456:T", DB_PATH=os.path.join(tempfile.mkdtemp(), "d.db"), ADMIN_IDS="5280407495")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config, db

ok = fail = 0
def check(n, c, extra=None):
    global ok, fail
    if c: ok += 1; print("  OK  ", n)
    else: fail += 1; print("  FAIL", n)

print("backend:", "postgres" if db.use_pg() else "sqlite")
db.reset_for_tests(); db.init(); db.init()
check("init ikki marta (idempotent)", True)
db.ensure_env_admins(); db.ensure_env_admins()
a = db.get_user(5280407495)
check("env admin (katta Telegram ID) bazada", a and a["status"] == "approved" and a["is_admin"] == 1, a)
check("admin_ids env adminni o'z ichiga oladi", 5280407495 in db.admin_ids())
for uid in (2001, 2002):
    db.x("INSERT INTO users(tg_id,first_name,status,created_at,updated_at) VALUES(?,?,?,?,?)", (uid, "A", "approved", "t", "t"))
rid = db.x("INSERT INTO rides(author_id,kind,prayer,date,depart_time,expires_at) VALUES(?,?,?,?,?,?)", (2001, "driver", "asr", "2026-01-01", "16:00", "2099-01-01 00:00"))
check("INSERT id qaytaradi", isinstance(rid, int) and rid > 0)
db.x("INSERT OR IGNORE INTO hashar_joins(hashar_id,user_id,created_at) VALUES(?,?,?)", (1, 2001, "t"))
db.x("INSERT OR IGNORE INTO hashar_joins(hashar_id,user_id,created_at) VALUES(?,?,?)", (1, 2001, "t"))
check("INSERT OR IGNORE takrorni o'tkazib yuboradi", len(db.q("SELECT * FROM hashar_joins")) == 1)
db.set_setting("min_players", 7); db.set_setting("min_players", 8)
check("settings upsert", db.get_setting("min_players") == 8)
check("LIKE / % belgisi xavfsiz", db.q("SELECT count(*) n FROM users WHERE first_name LIKE 'A%'", one=True)["n"] == 2)
check("member_count env adminsiz", db.member_count() == 2)

tabs = db.dump_all()
check("dump_all: jadvallar", set(tabs) == set(db.TABLES) and len(tabs["users"]) == 3)
p = os.path.join(tempfile.mkdtemp(), "b.json"); db.write_backup_json(p)
data = db.read_backup(p)
check("JSON zaxira o'qiladi", db.summary_of(data) == db.current_summary())
# o'zgartirib, keyin tiklaymiz
db.x("DELETE FROM users WHERE tg_id=2002"); db.x("DELETE FROM rides")
check("o'zgarish bo'ldi", db.member_count() == 1)
db.load_all(data)
check("load_all: a'zolar qaytdi", db.member_count() == 2 and len(db.q("SELECT * FROM rides")) == 1)
new_id = db.x("INSERT INTO rides(author_id,kind,prayer,date,depart_time,expires_at) VALUES(?,?,?,?,?,?)", (2001, "driver", "asr", "2026-01-01", "16:00", "2099-01-01 00:00"))
check("tiklagandan keyin yangi ID to'qnashmaydi", new_id > rid, (new_id, rid))
# xato JSON
bad = os.path.join(tempfile.mkdtemp(), "x.json"); open(bad, "w").write(json.dumps({"hello": 1}))
try: db.read_backup(bad); good = False
except ValueError: good = True
check("begona JSON rad etiladi", good)
# eski SQLite .db zaxirasi
sp = os.path.join(tempfile.mkdtemp(), "old.db")
c = sqlite3.connect(sp); c.executescript(db.SCHEMA)
c.execute("INSERT INTO users(tg_id,first_name,status) VALUES(7001,'Old','approved')")
c.execute("INSERT INTO users(tg_id,first_name,status) VALUES(7002,'Old2','pending')"); c.commit(); c.close()
s = db.summary_of(db.read_backup(sp))
check("eski .db zaxira o'qiladi", s["approved"] == 1 and s["pending"] == 1)
db.load_all(db.read_backup(sp)); db.ensure_env_admins()
check("eski .db dan tiklash + env admin saqlanadi", db.get_user(7001) and db.get_user(5280407495)["is_admin"] == 1 and db.get_user(2001) is None)
if db.use_pg():
    db.pg_close()
    check("ulanish uzilsa qayta ulanadi", db.q("SELECT count(*) n FROM users", one=True)["n"] >= 1)
    db._pg().close()
    check("yopilgan ulanishdan keyin ham ishlaydi", db.get_user(7001) is not None)
print(f"Natija: {ok} o'tdi, {fail} xato"); sys.exit(1 if fail else 0)
