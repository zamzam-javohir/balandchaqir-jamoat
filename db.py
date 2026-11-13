import json, os, re, sqlite3, threading
from datetime import datetime, timedelta
from prayer import UZT
import config

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:          # SQLite rejimida kerak emas
    psycopg = None

_lock = threading.RLock()


def use_pg() -> bool:
    """DATABASE_URL berilsa Postgres (Neon), aks holda SQLite (test / lokal)."""
    return bool(config.DATABASE_URL)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  tg_id INTEGER PRIMARY KEY, first_name TEXT, username TEXT,
  name TEXT, phone TEXT, phone_verified INTEGER DEFAULT 0,
  status TEXT DEFAULT 'new',            -- new | pending | approved | rejected
  is_admin INTEGER DEFAULT 0, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS rides(
  id INTEGER PRIMARY KEY AUTOINCREMENT, author_id INTEGER NOT NULL,
  kind TEXT NOT NULL,                   -- driver | request
  prayer TEXT NOT NULL, date TEXT NOT NULL, depart_time TEXT NOT NULL,
  seats INTEGER DEFAULT 0, note TEXT, share_phone INTEGER DEFAULT 0, lat REAL, lon REAL,
  expires_at TEXT NOT NULL, created_at TEXT);
CREATE TABLE IF NOT EXISTS ride_joins(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ride_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
  created_at TEXT, UNIQUE(ride_id, user_id));
CREATE TABLE IF NOT EXISTS polls(
  id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT, status TEXT DEFAULT 'open',
  notified INTEGER DEFAULT 0, auto INTEGER DEFAULT 0, created_at TEXT);
CREATE TABLE IF NOT EXISTS votes(
  poll_id INTEGER, user_id INTEGER, answer TEXT, updated_at TEXT, PRIMARY KEY(poll_id, user_id));
CREATE TABLE IF NOT EXISTS hashars(
  id INTEGER PRIMARY KEY AUTOINCREMENT, author_id INTEGER NOT NULL,
  when_kind TEXT NOT NULL,              -- bomdod_after | xufton_after | custom
  when_time TEXT DEFAULT '', date TEXT NOT NULL, place TEXT DEFAULT '', description TEXT DEFAULT '',
  lat REAL, lon REAL, status TEXT DEFAULT 'active',   -- active | cancelled
  created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS hashar_joins(
  hashar_id INTEGER NOT NULL, user_id INTEGER NOT NULL, created_at TEXT, PRIMARY KEY(hashar_id, user_id));
CREATE TABLE IF NOT EXISTS bcasts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, ref_id INTEGER NOT NULL,
  chat_id INTEGER NOT NULL, message_id INTEGER NOT NULL, created_at TEXT);
CREATE INDEX IF NOT EXISTS ix_bcasts_ref ON bcasts(kind, ref_id);
CREATE INDEX IF NOT EXISTS ix_rides_exp ON rides(expires_at);
"""

# Postgres: Telegram ID lar 2^31 dan katta -> BIGINT; avto-ID lar -> BIGSERIAL.
PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  tg_id BIGINT PRIMARY KEY, first_name TEXT, username TEXT,
  name TEXT, phone TEXT, phone_verified INTEGER DEFAULT 0,
  status TEXT DEFAULT 'new', is_admin INTEGER DEFAULT 0, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS rides(
  id BIGSERIAL PRIMARY KEY, author_id BIGINT NOT NULL, kind TEXT NOT NULL,
  prayer TEXT NOT NULL, date TEXT NOT NULL, depart_time TEXT NOT NULL,
  seats INTEGER DEFAULT 0, note TEXT, share_phone INTEGER DEFAULT 0, lat DOUBLE PRECISION, lon DOUBLE PRECISION,
  expires_at TEXT NOT NULL, created_at TEXT);
CREATE TABLE IF NOT EXISTS ride_joins(
  id BIGSERIAL PRIMARY KEY, ride_id BIGINT NOT NULL, user_id BIGINT NOT NULL,
  created_at TEXT, UNIQUE(ride_id, user_id));
CREATE TABLE IF NOT EXISTS polls(
  id BIGSERIAL PRIMARY KEY, date TEXT, status TEXT DEFAULT 'open',
  notified INTEGER DEFAULT 0, auto INTEGER DEFAULT 0, created_at TEXT);
CREATE TABLE IF NOT EXISTS votes(
  poll_id BIGINT, user_id BIGINT, answer TEXT, updated_at TEXT, PRIMARY KEY(poll_id, user_id));
CREATE TABLE IF NOT EXISTS hashars(
  id BIGSERIAL PRIMARY KEY, author_id BIGINT NOT NULL, when_kind TEXT NOT NULL,
  when_time TEXT DEFAULT '', date TEXT NOT NULL, place TEXT DEFAULT '', description TEXT DEFAULT '',
  lat DOUBLE PRECISION, lon DOUBLE PRECISION, status TEXT DEFAULT 'active',
  created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS hashar_joins(
  hashar_id BIGINT NOT NULL, user_id BIGINT NOT NULL, created_at TEXT, PRIMARY KEY(hashar_id, user_id));
CREATE TABLE IF NOT EXISTS bcasts(
  id BIGSERIAL PRIMARY KEY, kind TEXT NOT NULL, ref_id BIGINT NOT NULL,
  chat_id BIGINT NOT NULL, message_id BIGINT NOT NULL, created_at TEXT);
CREATE INDEX IF NOT EXISTS ix_bcasts_ref ON bcasts(kind, ref_id);
CREATE INDEX IF NOT EXISTS ix_rides_exp ON rides(expires_at);
"""

TABLES = ["users", "settings", "rides", "ride_joins", "polls", "votes", "hashars", "hashar_joins", "bcasts"]
ID_TABLES = {"rides", "ride_joins", "polls", "hashars", "bcasts"}   # `id` ustuni bor (avto-ID)
REQUIRED_TABLES = {"users", "rides", "settings"}


DEFAULTS = {
    "jamoat_times": {"bomdod": "", "peshin": "", "asr": "", "shom": "", "xufton": ""},
    "juma_time": "",
    "jamoat_note": "",
    "prayer_offsets": {"bomdod": 0, "quyosh": 0, "peshin": 0, "asr": 0, "shom": 0, "xufton": 0},
    "min_players": 10,
    "game_time": "",
    "game_place": "",
    "daily_poll_enabled": False,
    "daily_poll_time": "08:00",
    "last_backup": "",
}


def now() -> datetime:
    return datetime.now(UZT)


def now_str() -> str:
    return now().strftime("%Y-%m-%d %H:%M")


def connect() -> sqlite3.Connection:
    c = sqlite3.connect(config.DB_PATH, timeout=30, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


# ---- Postgres: bitta doimiy ulanish (_lock ostida), uzilsa qayta ulanadi ----
_pg_conn = None


def _pg():
    global _pg_conn
    if _pg_conn is None or _pg_conn.closed:
        if psycopg is None:
            raise RuntimeError("DATABASE_URL berilgan, lekin psycopg o'rnatilmagan")
        _pg_conn = psycopg.connect(config.DATABASE_URL, autocommit=True, row_factory=dict_row, connect_timeout=30,
                                   prepare_threshold=None,       # pgbouncer (Neon pooler) bilan mos
                                   keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=3)
    return _pg_conn


def pg_close():
    global _pg_conn
    if _pg_conn is not None:
        try:
            _pg_conn.close()
        except Exception:
            pass
        _pg_conn = None


def _tr(sql: str) -> str:
    """SQLite uslubidagi SQL ni Postgres ga o'giradi: ? -> %s, INSERT OR IGNORE."""
    sql = sql.replace("%", "%%").replace("?", "%s")
    if re.match(r"\s*INSERT\s+OR\s+IGNORE\s+INTO", sql, re.I):
        sql = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", sql, count=1, flags=re.I) + " ON CONFLICT DO NOTHING"
    return sql


def _pg_exec(sql, args=(), fetch="none"):
    """fetch: none | all | id (RETURNING id). Ulanish uzilgan bo'lsa bir marta qayta urinadi."""
    sql = _tr(sql)
    m = re.match(r"\s*INSERT\s+INTO\s+(\w+)", sql, re.I)
    if fetch == "none" and m and m.group(1).lower() in ID_TABLES:
        sql += " RETURNING id"; fetch = "id"
    for attempt in (0, 1):
        try:
            cur = _pg().execute(sql, tuple(args))
            if fetch == "all":
                return cur.fetchall()
            if fetch == "id":
                r = cur.fetchone()
                return r["id"] if r else None
            return None
        except (psycopg.OperationalError, psycopg.InterfaceError):
            pg_close()
            if attempt:
                raise


def init():
    with _lock:
        if use_pg():
            c = _pg()
            with c.transaction():
                c.execute("SELECT pg_advisory_xact_lock(7203451)")     # bir vaqtda ikki nusxa ishga tushsa
                c.execute(PG_SCHEMA)
            return
        os.makedirs(os.path.dirname(config.DB_PATH) or ".", exist_ok=True)
        with connect() as c:
            c.executescript(SCHEMA)
            cols = {r[1] for r in c.execute("PRAGMA table_info(rides)")}
            for col in ("lat", "lon"):
                if col not in cols:
                    c.execute(f"ALTER TABLE rides ADD COLUMN {col} REAL")


def reset_for_tests():
    """Faqat testlar uchun: Postgres dagi jadvallarni tozalaydi (lokal bazada yoki TEST_ALLOW_RESET=1 bo'lsa)."""
    u = config.DATABASE_URL
    if not use_pg() or not (os.getenv("TEST_ALLOW_RESET") == "1" or "/workspace/pgdata" in u or "localhost" in u or "127.0.0.1" in u):
        return
    with _lock:
        _pg().execute("DROP TABLE IF EXISTS " + ",".join(TABLES) + " CASCADE")


def q(sql, args=(), one=False):
    with _lock:
        if use_pg():
            rows = [dict(r) for r in _pg_exec(sql, args, "all")]
        else:
            with connect() as c:
                cur = c.execute(sql, args)
                rows = [dict(r) for r in cur.fetchall()]
    return (rows[0] if rows else None) if one else rows


def x(sql, args=()):
    """INSERT/UPDATE/DELETE; INSERT bo'lsa yangi id qaytaradi."""
    with _lock:
        if use_pg():
            return _pg_exec(sql, args, "none")
        with connect() as c:
            cur = c.execute(sql, args)
            return cur.lastrowid


def get_setting(key):
    r = q("SELECT value FROM settings WHERE key=?", (key,), one=True)
    if r is None:
        return DEFAULTS[key]
    try:
        v = json.loads(r["value"])
    except ValueError:
        return DEFAULTS[key]
    if isinstance(DEFAULTS[key], dict) and isinstance(v, dict):
        return {**DEFAULTS[key], **v}
    return v


def set_setting(key, value):
    x("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
      (key, json.dumps(value, ensure_ascii=False)))


# ---- foydalanuvchilar ----
def upsert_tg_user(u: dict) -> dict:
    uid = int(u["id"])
    ts = now_str()
    row = q("SELECT * FROM users WHERE tg_id=?", (uid,), one=True)
    if row is None:
        x("INSERT INTO users(tg_id,first_name,username,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
          (uid, u.get("first_name", ""), u.get("username"), "new", ts, ts))
    else:
        x("UPDATE users SET first_name=?, username=?, updated_at=? WHERE tg_id=?",
          (u.get("first_name", ""), u.get("username"), ts, uid))
    row = q("SELECT * FROM users WHERE tg_id=?", (uid,), one=True)
    if uid in config.ADMIN_IDS:
        if row["status"] != "approved" or not row["is_admin"]:
            x("UPDATE users SET status='approved', is_admin=1 WHERE tg_id=?", (uid,))
            row = q("SELECT * FROM users WHERE tg_id=?", (uid,), one=True)
    return row


def get_user(uid):
    return q("SELECT * FROM users WHERE tg_id=?", (uid,), one=True)


def is_admin(row) -> bool:
    return bool(row and (row["is_admin"] or row["tg_id"] in config.ADMIN_IDS))


def admin_ids() -> list[int]:
    ids = {r["tg_id"] for r in q("SELECT tg_id FROM users WHERE is_admin=1")}
    return sorted(ids | config.ADMIN_IDS)


def summary_of(t: dict) -> dict:
    """Jadvallar lug'ati ({jadval: [qatorlar]}) bo'yicha qisqa hisobot."""
    users = t.get("users", [])
    return {"users": sum(1 for u in users if u.get("status") != "new"),
            "approved": sum(1 for u in users if u.get("status") == "approved"),
            "pending": sum(1 for u in users if u.get("status") == "pending"),
            "admins": sum(1 for u in users if u.get("is_admin") == 1),
            "rides": len(t.get("rides", [])),
            "hashars": sum(1 for h in t.get("hashars", []) if h.get("status") == "active")}


def dump_all() -> dict:
    """Butun bazani {jadval: [qatorlar]} ko'rinishida qaytaradi (Postgres va SQLite uchun bir xil)."""
    with _lock:
        return {t: q(f"SELECT * FROM {t}") for t in TABLES}


def current_summary() -> dict:
    return summary_of(dump_all())


def read_backup(path: str) -> dict:
    """Zaxira faylini (JSON yoki eski SQLite .db) o'qib, {jadval: [qatorlar]} qaytaradi. Yaroqsiz bo'lsa ValueError."""
    with open(path, "rb") as f:
        head = f.read(16)
    if head.startswith(b"SQLite format 3"):
        try:
            t = sqlite3.connect(path)
            t.row_factory = sqlite3.Row
            try:
                if t.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("fayl buzilgan")
                have = {r[0] for r in t.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not REQUIRED_TABLES <= have:
                    raise ValueError("bu bizning bazaning nusxasi emas")
                return {n: [dict(r) for r in t.execute(f"SELECT * FROM {n}")] if n in have else [] for n in TABLES}
            finally:
                t.close()
        except sqlite3.Error as e:
            raise ValueError(f"fayl o'qilmadi ({e})")
    try:
        data = json.loads(open(path, "rb").read().decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise ValueError("fayl o'qilmadi (JSON ham, SQLite ham emas)")
    tabs = data.get("tables") if isinstance(data, dict) and data.get("format") == "balandchaqir-jamoat" else None
    if not isinstance(tabs, dict) or not REQUIRED_TABLES <= set(tabs):
        raise ValueError("bu bizning bazaning nusxasi emas")
    return {n: list(tabs.get(n) or []) for n in TABLES}


def write_backup_json(path: str):
    data = {"format": "balandchaqir-jamoat", "version": 1, "created_at": now_str(), "tables": dump_all()}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def _columns(table: str) -> list[str]:
    if use_pg():
        return [r["column_name"] for r in _pg_exec(
            "SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=? "
            "ORDER BY ordinal_position", (table,), "all")]
    with connect() as c:
        return [r[1] for r in c.execute(f"PRAGMA table_info({table})")]


def load_all(t: dict):
    """Butun bazani berilgan jadvallar bilan almashtiradi (bitta tranzaksiyada: xato bo'lsa hech narsa o'zgarmaydi)."""
    with _lock:
        plan = []
        for n in TABLES:
            cols = _columns(n)
            plan.append((n, cols, [r for r in t.get(n, [])]))
        if use_pg():
            c = _pg()
            with c.transaction():
                for n, cols, rows in plan:
                    c.execute(f"DELETE FROM {n}")
                    for r in rows:
                        use = [k for k in cols if k in r]
                        if use:
                            c.execute(f"INSERT INTO {n}({','.join(use)}) VALUES ({','.join(['%s'] * len(use))})",
                                      tuple(r[k] for k in use))
                    if n in ID_TABLES:
                        c.execute(f"SELECT setval(pg_get_serial_sequence('{n}','id'), coalesce((SELECT max(id) FROM {n}), 0) + 1, false)")
            return
        with connect() as c:
            for n, cols, rows in plan:
                c.execute(f"DELETE FROM {n}")
                for r in rows:
                    use = [k for k in cols if k in r]
                    if use:
                        c.execute(f"INSERT INTO {n}({','.join(use)}) VALUES ({','.join('?' * len(use))})", tuple(r[k] for k in use))
            c.execute("DELETE FROM sqlite_sequence")
            for n in ID_TABLES:
                c.execute("INSERT INTO sqlite_sequence(name, seq) VALUES(?, coalesce((SELECT max(id) FROM " + n + "), 0))", (n,))


def member_count() -> int:
    """Tasdiqlangan a'zolar soni (env adminlarsiz) — bo'sh baza zaxirasini aniqlash uchun."""
    ids = list(config.ADMIN_IDS) or [0]
    ph = ",".join("?" * len(ids))
    r = q(f"SELECT count(*) n FROM users WHERE status='approved' AND tg_id NOT IN ({ph})", ids, one=True)
    return r["n"] if r else 0


def fingerprint() -> str:
    """Ma'lumot o'zgarganini bilish uchun barmoq izi."""
    r = q("SELECT (SELECT count(*) FROM users) u, (SELECT count(*) FROM users WHERE status='approved') a, "
          "(SELECT coalesce(max(updated_at),'') FROM users) uu, (SELECT count(*) FROM rides) r, "
          "(SELECT count(*) FROM hashars) h, (SELECT count(*) FROM votes) v", one=True)
    return "|".join(str(v) for v in r.values())


def ensure_env_admins():
    """ADMIN_IDS dagi bosh adminlar har doim bazada, tasdiqlangan va admin bo'lsin (tiklashdan keyin ham)."""
    ts = now_str()
    for uid in config.ADMIN_IDS:
        if not q("SELECT 1 FROM users WHERE tg_id=?", (uid,), one=True):
            x("INSERT INTO users(tg_id,first_name,status,is_admin,created_at,updated_at) VALUES(?,?,?,?,?,?)",
              (uid, "", "approved", 1, ts, ts))
        else:
            x("UPDATE users SET status='approved', is_admin=1 WHERE tg_id=?", (uid,))


def approved_ids() -> list[int]:
    return [r["tg_id"] for r in q("SELECT tg_id FROM users WHERE status='approved'")]


def display_name(row) -> str:
    return (row.get("name") or row.get("first_name") or str(row["tg_id"])) if row else "?"


def public_user(row) -> dict:
    return {"id": row["tg_id"], "name": display_name(row)}


def cleanup():
    cutoff = (now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    ids = [r["id"] for r in q("SELECT id FROM rides WHERE expires_at < ?", (cutoff,))]
    for i in ids:
        x("DELETE FROM ride_joins WHERE ride_id=?", (i,))
        x("DELETE FROM rides WHERE id=?", (i,))
