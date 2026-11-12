"""Namoz vaqtlarini mahalliy hisoblash (praytimes.org algoritmi asosida).

Usul: Muslim World League (Fajr 18°, Isha 17°), Asr — Hanafiy (soya 2 barobar).
Vaqt mintaqasi: Asia/Tashkent (UTC+5, yozgi vaqt yo'q).
"""
from __future__ import annotations
import math
from datetime import date, datetime, timedelta, timezone

UZT = timezone(timedelta(hours=5))
KAABA = (21.4225, 39.8262)

PRAYERS = [  # (kalit, nomi)
    ("bomdod", "Bomdod"),
    ("quyosh", "Quyosh"),
    ("peshin", "Peshin"),
    ("asr", "Asr"),
    ("shom", "Shom"),
    ("xufton", "Xufton"),
]


def _d2r(x): return math.radians(x)
def _r2d(x): return math.degrees(x)
def _sin(x): return math.sin(_d2r(x))
def _cos(x): return math.cos(_d2r(x))
def _tan(x): return math.tan(_d2r(x))
def _arcsin(x): return _r2d(math.asin(x))
def _arccos(x): return _r2d(math.acos(x))
def _arctan2(y, x): return _r2d(math.atan2(y, x))
def _arccot(x): return _r2d(math.atan(1.0 / x))
def _fix(a, m):
    a = a - m * math.floor(a / m)
    return a


def _julian(y, m, d):
    if m <= 2:
        y -= 1
        m += 12
    A = math.floor(y / 100)
    B = 2 - A + math.floor(A / 4)
    return math.floor(365.25 * (y + 4716)) + math.floor(30.6001 * (m + 1)) + d + B - 1524.5


def _sun_position(jd):
    D = jd - 2451545.0
    g = _fix(357.529 + 0.98560028 * D, 360)
    q = _fix(280.459 + 0.98564736 * D, 360)
    L = _fix(q + 1.915 * _sin(g) + 0.020 * _sin(2 * g), 360)
    e = 23.439 - 0.00000036 * D
    RA = _arctan2(_cos(e) * _sin(L), _cos(L)) / 15.0
    eqt = q / 15.0 - _fix(RA, 24)
    decl = _arcsin(_sin(e) * _sin(L))
    return decl, eqt


def calc_times(day: date, lat: float, lng: float, tz: float = 5.0,
               fajr_angle: float = 18.0, isha_angle: float = 17.0,
               asr_factor: int = 2, elevation: float = 0.0) -> dict[str, float]:
    """Soatlarda (kasr) vaqtlar: {'bomdod': 5.4, ...}"""
    jd = _julian(day.year, day.month, day.day) - lng / (15.0 * 24.0)

    def noon():
        _, eqt = _sun_position(jd + 0.5)
        return _fix(12 - eqt, 24)

    def angle_time(angle, t, ccw=False):
        decl, _ = _sun_position(jd + t / 24.0)
        nm = noon()
        v = (-_sin(angle) - _sin(lat) * _sin(decl)) / (_cos(lat) * _cos(decl))
        v = max(-1.0, min(1.0, v))
        return nm + (-1 if ccw else 1) * _arccos(v) / 15.0

    def asr_time(t):
        decl, _ = _sun_position(jd + t / 24.0)
        ang = -_arccot(asr_factor + _tan(abs(lat - decl)))
        return angle_time(ang, t)

    horizon = 0.833 + 0.0347 * math.sqrt(max(elevation, 0))
    t = {"bomdod": 5.0, "quyosh": 6.0, "peshin": 12.0, "asr": 13.0, "shom": 18.0, "xufton": 18.0}
    for _ in range(2):  # iteratsiya
        t = {
            "bomdod": angle_time(fajr_angle, t["bomdod"], ccw=True),
            "quyosh": angle_time(horizon, t["quyosh"], ccw=True),
            "peshin": noon(),
            "asr": asr_time(t["asr"]),
            "shom": angle_time(horizon, t["shom"]),
            "xufton": angle_time(isha_angle, t["xufton"]),
        }
    adj = tz - lng / 15.0
    return {k: v + adj for k, v in t.items()}


def fmt(h: float) -> str:
    h = _fix(h + 0.5 / 60, 24)  # daqiqaga yaxlitlash
    return f"{int(h):02d}:{int((h - int(h)) * 60):02d}"


def day_times(day: date, lat: float, lng: float, offsets: dict | None = None) -> dict[str, str]:
    raw = calc_times(day, lat, lng)
    offsets = offsets or {}
    out = {}
    for k, _ in PRAYERS:
        h = raw[k] + float(offsets.get(k, 0)) / 60.0
        out[k] = fmt(h)
    return out


def qibla(lat: float, lng: float) -> float:
    """Qibla yo'nalishi (shimoldan soat yo'nalishi bo'yicha, gradus)."""
    p1, l1 = math.radians(lat), math.radians(lng)
    p2, l2 = math.radians(KAABA[0]), math.radians(KAABA[1])
    dl = l2 - l1
    y = math.sin(dl)
    x = math.cos(p1) * math.tan(p2) - math.sin(p1) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def to_dt(day: date, hhmm: str) -> datetime:
    h, m = hhmm.split(":")
    return datetime(day.year, day.month, day.day, int(h), int(m), tzinfo=UZT)


def next_prayer(now: datetime, lat: float, lng: float, offsets: dict | None = None):
    """Keyingi namoz: (kalit, nomi, datetime)."""
    for add in (0, 1):
        d = (now + timedelta(days=add)).date()
        times = day_times(d, lat, lng, offsets)
        for k, name in PRAYERS:
            dt = to_dt(d, times[k])
            if dt > now:
                return k, name, dt
    raise RuntimeError("unreachable")
