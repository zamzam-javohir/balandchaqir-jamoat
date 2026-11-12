"""Telegram WebApp initData tekshiruvi (HMAC-SHA256)."""
import hashlib, hmac, json, time
from urllib.parse import parse_qsl


def validate_init_data(init_data: str, bot_token: str, max_age: int = 86400) -> dict | None:
    """To'g'ri bo'lsa user dict qaytaradi, aks holda None."""
    if not init_data or not bot_token:
        return None
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError:
        return None
    recv_hash = pairs.pop("hash", None)
    if not recv_hash:
        return None
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, recv_hash):
        return None
    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        return None
    if max_age and time.time() - auth_date > max_age:
        return None
    try:
        user = json.loads(pairs.get("user", ""))
    except (ValueError, TypeError):
        return None
    if not isinstance(user, dict) or "id" not in user:
        return None
    return user


def make_init_data(user: dict, bot_token: str, auth_date: int | None = None) -> str:
    """Faqat testlar uchun: soxta imzolangan initData yasaydi."""
    from urllib.parse import urlencode
    pairs = {"auth_date": str(auth_date or int(time.time())), "query_id": "AAtest",
             "user": json.dumps(user, separators=(",", ":"), ensure_ascii=False)}
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)
