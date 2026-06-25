from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import json
from pathlib import Path
from datetime import datetime

from config import (
    FRONTEND_ORIGIN,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    MAX_AUTO_TRADES_PER_SCAN,
)
from signal_engine import get_all_signals
from trade_executor import TradeExecutor
from telegram import Bot
from telegram_bot import build_telegram_app

STATE_FILE = Path("bot_state.json")

# --- Telegram Bot Background Setup ---
tg_app = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global tg_app
    # Startup: Start Telegram Bot in background
    if TELEGRAM_BOT_TOKEN:
        tg_app = build_telegram_app()
        await tg_app.initialize()
        await tg_app.start()
        await tg_app.updater.start_polling()
        print("✅ Telegram Bot started in background...")
    yield
    # Shutdown: Stop Telegram Bot
    if tg_app:
        await tg_app.updater.stop()
        await tg_app.stop()
        await tg_app.shutdown()

app = FastAPI(title="NEXARA Telegram Crypto Bot V1", lifespan=lifespan)
executor = TradeExecutor()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN] if FRONTEND_ORIGIN != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

async def send_telegram_message(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)
    except Exception as e:
        print(f"Telegram send error: {e}")

@app.get("/")
def root():
    return {"message": "NEXARA Telegram Crypto Bot V1 is running"}

@app.get("/api/bot/status")
def bot_status():
    return load_state()

@app.post("/api/bot/auto_on")
def auto_on():
    state = load_state()
    state["auto_enabled"] = True
    save_state(state)
    return {"success": True, "auto_enabled": True}

@app.post("/api/bot/auto_off")
def auto_off():
    state = load_state()
    state["auto_enabled"] = False
    save_state(state)
    return {"success": True, "auto_enabled": False}

@app.get("/api/scan")
async def scan_now():
    state = load_state()
    state["scan_running"] = True
    save_state(state)

    signals = get_all_signals()

    state["scan_running"] = False
    state["last_scan_count"] = len(signals)
    state["last_scan_time"] = datetime.utcnow().isoformat()
    state["last_signals"] = signals[:20]
    save_state(state)

    return {
        "success": True,
        "count": len(signals),
        "signals": signals
    }

@app.post("/api/trade/run")
async def trade_run():
    state = load_state()
    state["scan_running"] = True
    save_state(state)

    signals = get_all_signals()

    state["scan_running"] = False
    state["last_scan_count"] = len(signals)
    state["last_scan_time"] = datetime.utcnow().isoformat()
    state["last_signals"] = signals[:20]

    executed_orders = []

    if signals:
        top_for_alert = signals[:10]
        msg_lines = [f"📡 NEXARA Signals ({len(signals)})"]
        for s in top_for_alert:
            msg_lines.append(
                f"{s['symbol']} | {s['signal']} | entry={s['entry']} | TP={s['take_profit']} | SL={s['stop_loss']} | score={s['score']}"
            )
        await send_telegram_message("\n".join(msg_lines))
    else:
        await send_telegram_message("NEXARA: nta actionable signals zabonetse muri iyi scan.")

    if state.get("auto_enabled") and signals:
        auto_candidates = signals[:MAX_AUTO_TRADES_PER_SCAN]

        for s in auto_candidates:
            action = s.get("signal")
            if action not in ("BUY", "SELL"):
                continue

            price = s.get("entry") or 0
            qty = executor.calculate_qty_from_usdt(price)
            if qty <= 0:
                continue

            order = executor.place_market_order(
                symbol=s["symbol"],
                side=action,
                qty=qty
            )
            executed_orders.append(order)

        state["last_trades"] = executed_orders

        if executed_orders:
            trade_lines = ["💼 NEXARA Auto Trades"]
            for t in executed_orders:
                trade_lines.append(
                    f"{t['symbol']} | {t['side']} | qty={t['qty']} | mode={t['mode']}"
                )
            await send_telegram_message("\n".join(trade_lines))

    save_state(state)

    return {
        "success": True,
        "signals_count": len(signals),
        "signals": signals,
        "auto_enabled": state.get("auto_enabled"),
        "executed_orders": executed_orders
    }            "scan_running": False,
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

async def send_telegram_message(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text)
    except Exception as e:
        print(f"Telegram send error: {e}")

@app.get("/")
def root():
    return {"message": "NEXARA Telegram Crypto Bot V1 is running"}

@app.get("/api/bot/status")
def bot_status():
    return load_state()

@app.post("/api/bot/auto_on")
def auto_on():
    state = load_state()
    state["auto_enabled"] = True
    save_state(state)
    return {"success": True, "auto_enabled": True}

@app.post("/api/bot/auto_off")
def auto_off():
    state = load_state()
    state["auto_enabled"] = False
    save_state(state)
    return {"success": True, "auto_enabled": False}

@app.get("/api/scan")
def scan_now():
    state = load_state()
    state["scan_running"] = True
    save_state(state)

    signals = get_all_signals()

    state["scan_running"] = False
    state["last_scan_count"] = len(signals)
    state["last_scan_time"] = datetime.utcnow().isoformat()
    state["last_signals"] = signals[:20]
    save_state(state)

    return {
        "success": True,
        "count": len(signals),
        "signals": signals
    }

@app.post("/api/trade/run")
def trade_run():
    """
    1. Scan all pairs
    2. Save signals
    3. Send Telegram alerts
    4. If auto_enabled = True -> mock execute top signals
    """
    state = load_state()
    state["scan_running"] = True
    save_state(state)

    signals = get_all_signals()

    state["scan_running"] = False
    state["last_scan_count"] = len(signals)
    state["last_scan_time"] = datetime.utcnow().isoformat()
    state["last_signals"] = signals[:20]

    executed_orders = []

    # Always alert signals to Telegram
    if signals:
        top_for_alert = signals[:10]
        msg_lines = [f"📡 NEXARA Signals ({len(signals)})"]
        for s in top_for_alert:
            msg_lines.append(
                f"{s['symbol']} | {s['signal']} | entry={s['entry']} | TP={s['take_profit']} | SL={s['stop_loss']} | score={s['score']}"
            )
        asyncio.run(send_telegram_message("\n".join(msg_lines)))
    else:
        asyncio.run(send_telegram_message("NEXARA: nta actionable signals zabonetse muri iyi scan."))

    # AUTO TRADING
    if state.get("auto_enabled") and signals:
        auto_candidates = signals[:MAX_AUTO_TRADES_PER_SCAN]

        for s in auto_candidates:
            action = s.get("signal")
            if action not in ("BUY", "SELL"):
                continue

            price = s.get("entry") or 0
            qty = executor.calculate_qty_from_usdt(price)
            if qty <= 0:
                continue

            order = executor.place_market_order(
                symbol=s["symbol"],
                side=action,
                qty=qty
            )
            executed_orders.append(order)

        state["last_trades"] = executed_orders

        if executed_orders:
            trade_lines = ["💼 NEXARA Auto Trades"]
            for t in executed_orders:
                trade_lines.append(
                    f"{t['symbol']} | {t['side']} | qty={t['qty']} | mode={t['mode']}"
                )
            asyncio.run(send_telegram_message("\n".join(trade_lines)))

    save_state(state)

    return {
        "success": True,
        "signals_count": len(signals),
        "signals": signals,
        "auto_enabled": state.get("auto_enabled"),
        "executed_orders": executed_orders
              }
