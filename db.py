import json, os, sqlite3, threading
from datetime import datetime, timedelta
from prayer import UZT
import config

_lock = threading.RLock()

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


def init():
    os.makedirs(os.path.dirname(config.DB_PATH) or ".", exist_ok=True)
    with _lock, connect() as c:
        c.executescript(SCHEMA)
        cols = {r[1] for r in c.execute("PRAGMA table_info(rides)")}
        for col in ("lat", "lon"):
            if col not in cols:
                c.execute(f"ALTER TABLE rides ADD COLUMN {col} REAL")


def q(sql, args=(), one=False):
    with _lock, connect() as c:
        cur = c.execute(sql, args)
        rows = cur.fetchall()
    rows = [dict(r) for r in rows]
    return (rows[0] if rows else None) if one else rows


def x(sql, args=()):
    """INSERT/UPDATE/DELETE; lastrowid qaytaradi."""
    with _lock, connect() as c:
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
