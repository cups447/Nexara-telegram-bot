import os

# =========================
# TELEGRAM
# =========================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# =========================
# BINANCE
# =========================
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
BINANCE_TESTNET = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

# =========================
# BOT SETTINGS
# =========================
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", "900"))
DEFAULT_ORDER_USDT = float(os.getenv("DEFAULT_ORDER_USDT", "20"))
MAX_AUTO_TRADES_PER_SCAN = int(os.getenv("MAX_AUTO_TRADES_PER_SCAN", "3"))

# =========================
# APP
# =========================
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "*")
