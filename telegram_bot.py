import json
from pathlib import Path
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from config import TELEGRAM_BOT_TOKEN

STATE_FILE = Path("bot_state.json")

def load_state():
    if not STATE_FILE.exists():
        return {
            "auto_enabled": False,
            "scan_running": False,
            "last_scan_count": 0,
            "last_scan_time": None,
            "last_signals": [],
            "last_trades": []
        }
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Murakaza neza muri NEXARA Crypto Bot 🚀\n\n"
        "Commands:\n"
        "/status - kureba uko bot ihagaze\n"
        "/auto_on - gufungura auto trading\n"
        "/auto_off - guhagarika auto trading\n"
        "/lastsignals - kureba signals ziheruka\n"
        "/lasttrades - kureba trades ziheruka"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = load_state()
    msg = (
        "📊 NEXARA STATUS\n"
        f"Auto Trading: {'ON' if state.get('auto_enabled') else 'OFF'}\n"
        f"Scan Running: {'YES' if state.get('scan_running') else 'NO'}\n"
        f"Last Scan Count: {state.get('last_scan_count', 0)}\n"
        f"Last Scan Time: {state.get('last_scan_time')}\n"
        f"Last Trades Count: {len(state.get('last_trades', []))}"
    )
    await update.message.reply_text(msg)

async def auto_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = load_state()
    state["auto_enabled"] = True
    save_state(state)
    await update.message.reply_text("🤖 Auto trading yafunguwe.")

async def auto_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = load_state()
    state["auto_enabled"] = False
    save_state(state)
    await update.message.reply_text("🛑 Auto trading ihagaritswe.")

async def lastsignals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = load_state()
    signals = state.get("last_signals", [])
    if not signals:
        await update.message.reply_text("Nta signals ziraboneka.")
        return

    lines = ["📡 Last Signals:"]
    for s in signals[:10]:
        lines.append(
            f"{s.get('symbol')} | {s.get('signal')} | price={s.get('entry')} | score={s.get('score')}"
        )
    await update.message.reply_text("\n".join(lines))

async def lasttrades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    state = load_state()
    trades = state.get("last_trades", [])
    if not trades:
        await update.message.reply_text("Nta trades ziraboneka.")
        return

    lines = ["💼 Last Trades:"]
    for t in trades[:10]:
        lines.append(
            f"{t.get('symbol')} | {t.get('side')} | qty={t.get('qty')} | mode={t.get('mode')}"
        )
    await update.message.reply_text("\n".join(lines))

def build_telegram_app():
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN ntabwo yashyizwe muri environment variables.")
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("auto_on", auto_on))
    app.add_handler(CommandHandler("auto_off", auto_off))
    app.add_handler(CommandHandler("lastsignals", lastsignals))
    app.add_handler(CommandHandler("lasttrades", lasttrades))

    return app
