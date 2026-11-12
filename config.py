import os, hashlib

BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("BALANDCHAQIR_BOT_TOKEN") or ""
WEBAPP_URL = (os.getenv("WEBAPP_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").rstrip("/")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x.strip().isdigit()}
ADMIN_SETUP_CODE = os.getenv("ADMIN_SETUP_CODE", "")  # /admin <kod> orqali admin bo'lish uchun (ixtiyoriy)
DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "jamoat.db"))
MODE = os.getenv("MODE", "webhook").lower()  # webhook | polling
PORT = int(os.getenv("PORT", "8000"))

# Yangiobod tumani (Balandchaqir) taxminiy koordinatalari
LAT = float(os.getenv("LAT", "39.96"))
LNG = float(os.getenv("LNG", "68.78"))
PLACE_NAME = os.getenv("PLACE_NAME", "Balandchaqir, Yangiobod tumani")

INITDATA_MAX_AGE = int(os.getenv("INITDATA_MAX_AGE", str(3 * 86400)))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET") or hashlib.sha256(("wh:" + BOT_TOKEN).encode()).hexdigest()[:40]
