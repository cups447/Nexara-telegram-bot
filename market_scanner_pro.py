"""
market_scanner_pro.py

Production-grade multi-asset market scanner for spot USDT markets.

What this version improves over the original:
- Avoids duplicate `fetch_ticker()` calls by carrying 24h quote volume forward
- Safer RSI implementation (proper 0/100 edge handling)
- Stronger signal model:
    * EMA trend filter
    * MACD crossover
    * RSI momentum confirmation
    * volume confirmation
    * ATR-based volatility context
- Structured JSON-ready output
- State store to prevent duplicate alerts on the same candle
- Data validation / cleaning for OHLCV
- Optional async-ready architecture later (current version remains sync for simplicity)
- Dry, scan-only by default. Live execution helpers remain opt-in only.

Dependencies:
    pip install ccxt pandas cryptography --break-system-packages
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

import ccxt
import pandas as pd
from cryptography.fernet import Fernet, InvalidToken


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

class Config:
    EXCHANGE_ID = "binance"
    QUOTE_CURRENCY = "USDT"
    MARKET_TYPE = "spot"

    # Liquidity / market filters
    MIN_24H_QUOTE_VOLUME = 1_000_000
    ONLY_ACTIVE_MARKETS = True

    # Timeframe / history
    TIMEFRAME = "1h"
    OHLCV_LIMIT = 300

    # Indicators
    RSI_PERIOD = 14
    MACD_FAST = 12
    MACD_SLOW = 26
    MACD_SIGNAL = 9
    EMA_FAST = 50
    EMA_SLOW = 200
    ATR_PERIOD = 14
    VOL_MA_PERIOD = 20

    # Signal thresholds
    RSI_BULLISH_MIN = 35          # RSI should be recovering above this
    RSI_BEARISH_MAX = 65          # RSI should be falling below this
    RSI_OVERSOLD = 30
    RSI_OVERBOUGHT = 70
    MIN_VOLUME_RATIO = 1.10       # current candle volume / avg volume
    MIN_ATR_PCT = 0.003           # 0.3% of price minimum volatility

    # Request pacing / retries
    REQUEST_DELAY_SECONDS = 0.12
    MAX_RETRIES = 3
    RETRY_BACKOFF_SECONDS = 2.0

    # Output / dedupe
    SIGNAL_STATE_FILE = "scanner_state.json"
    MAX_RESULTS = 50


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("market_scanner_pro")


# -----------------------------------------------------------------------------
# Enums / data structures
# -----------------------------------------------------------------------------

class Signal(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    NONE = "NONE"


@dataclass
class MarketCandidate:
    symbol: str
    quote_volume_24h: float


@dataclass
class ScanResult:
    symbol: str
    timeframe: str
    candle_time: str
    last_price: float
    quote_volume_24h: float

    rsi: float
    macd: float
    macd_signal: float
    macd_prev: float
    macd_signal_prev: float
    ema_fast: float
    ema_slow: float
    atr: float
    atr_pct: float
    candle_volume: float
    avg_volume: float
    volume_ratio: float

    trend: str
    score: int
    reasons: list[str] = field(default_factory=list)
    signal: Signal = Signal.NONE

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["signal"] = self.signal.value
        return d


# -----------------------------------------------------------------------------
# State store (dedupe signals per symbol + candle)
# -----------------------------------------------------------------------------

class SignalStateStore:
    def __init__(self, path: str = Config.SIGNAL_STATE_FILE):
        self.path = path
        self.state = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            logger.warning("Could not load signal state file; starting fresh.")
            return {}

    def save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def already_sent(self, symbol: str, candle_time: str, signal: Signal) -> bool:
        item = self.state.get(symbol)
        if not item:
            return False
        return item.get("candle_time") == candle_time and item.get("signal") == signal.value

    def mark_sent(self, symbol: str, candle_time: str, signal: Signal) -> None:
        self.state[symbol] = {"candle_time": candle_time, "signal": signal.value}


# -----------------------------------------------------------------------------
# Exchange helpers
# -----------------------------------------------------------------------------

def build_exchange(exchange_id: str = Config.EXCHANGE_ID) -> ccxt.Exchange:
    exchange_class = getattr(ccxt, exchange_id)
    exchange = exchange_class({
        "enableRateLimit": True,
        "options": {
            "defaultType": Config.MARKET_TYPE
        }
    })
    exchange.load_markets()
    return exchange


def with_retries(fn: Callable, *args, **kwargs):
    last_err: Optional[Exception] = None
    for attempt in range(1, Config.MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except (ccxt.NetworkError, ccxt.ExchangeNotAvailable, ccxt.RequestTimeout) as err:
            last_err = err
            wait = Config.RETRY_BACKOFF_SECONDS * attempt
            logger.warning("Transient error on attempt %d/%d (%s). Retrying in %.1fs…",
                           attempt, Config.MAX_RETRIES, err, wait)
            time.sleep(wait)
        except ccxt.RateLimitExceeded as err:
            last_err = err
            wait = Config.RETRY_BACKOFF_SECONDS * attempt * 2
            logger.warning("Rate limit hit. Backing off %.1fs…", wait)
            time.sleep(wait)
    raise last_err  # type: ignore[misc]


# -----------------------------------------------------------------------------
# Market universe selection
# -----------------------------------------------------------------------------

def get_liquid_usdt_pairs(exchange: ccxt.Exchange) -> list[MarketCandidate]:
    logger.info("Fetching all tickers from %s…", exchange.id)
    tickers = with_retries(exchange.fetch_tickers)

    candidates: list[MarketCandidate] = []

    for symbol, ticker in tickers.items():
        market = exchange.markets.get(symbol)
        if not market:
            continue

        if market.get("quote") != Config.QUOTE_CURRENCY:
            continue
        if Config.ONLY_ACTIVE_MARKETS and not market.get("active", True):
            continue

        market_type = market.get("type")
        if market_type not in (Config.MARKET_TYPE, None):
            continue

        quote_volume = ticker.get("quoteVolume")
        if quote_volume is None:
            base_volume = ticker.get("baseVolume") or 0
            last_price = ticker.get("last") or 0
            quote_volume = base_volume * last_price

        if quote_volume and quote_volume >= Config.MIN_24H_QUOTE_VOLUME:
            candidates.append(MarketCandidate(symbol=symbol, quote_volume_24h=float(quote_volume)))

    candidates.sort(key=lambda x: x.quote_volume_24h, reverse=True)
    logger.info("Found %d liquid %s pairs.", len(candidates), Config.QUOTE_CURRENCY)
    return candidates


# -----------------------------------------------------------------------------
# Indicators
# -----------------------------------------------------------------------------

def fetch_ohlcv_df(exchange: ccxt.Exchange, symbol: str) -> pd.DataFrame:
    raw = with_retries(
        exchange.fetch_ohlcv,
        symbol,
        timeframe=Config.TIMEFRAME,
        limit=Config.OHLCV_LIMIT,
    )

    if not raw:
        raise ValueError(f"No OHLCV returned for {symbol}")

    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
    df = df.dropna(subset=["open", "high", "low", "close", "volume"])
    if df.empty:
        raise ValueError(f"OHLCV empty after cleaning for {symbol}")

    df.set_index("timestamp", inplace=True)
    return df


def calculate_rsi(close: pd.Series, period: int = Config.RSI_PERIOD) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))

    # Proper edge cases
    rsi = rsi.where(~((avg_gain == 0) & (avg_loss > 0)), 0)
    rsi = rsi.where(~((avg_loss == 0) & (avg_gain > 0)), 100)

    return rsi.ffill()


def calculate_macd(
    close: pd.Series,
    fast: int = Config.MACD_FAST,
    slow: int = Config.MACD_SLOW,
    signal: int = Config.MACD_SIGNAL,
) -> tuple[pd.Series, pd.Series]:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line


def calculate_atr(df: pd.DataFrame, period: int = Config.ATR_PERIOD) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        (df["high"] - df["low"]),
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs()
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    return atr


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["rsi"] = calculate_rsi(df["close"])
    df["macd"], df["macd_signal"] = calculate_macd(df["close"])
    df["ema_fast"] = df["close"].ewm(span=Config.EMA_FAST, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=Config.EMA_SLOW, adjust=False).mean()
    df["atr"] = calculate_atr(df)
    df["avg_volume"] = df["volume"].rolling(Config.VOL_MA_PERIOD).mean()
    df["atr_pct"] = df["atr"] / df["close"]
    df["volume_ratio"] = df["volume"] / df["avg_volume"]
    return df


# -----------------------------------------------------------------------------
# Signal engine
# -----------------------------------------------------------------------------

def classify_signal(df: pd.DataFrame) -> tuple[Signal, int, list[str], str]:
    latest = df.iloc[-1]
    prev = df.iloc[-2]

    reasons: list[str] = []
    score = 0

    trend_up = latest["close"] > latest["ema_slow"] and latest["ema_fast"] > latest["ema_slow"]
    trend_down = latest["close"] < latest["ema_slow"] and latest["ema_fast"] < latest["ema_slow"]

    macd_cross_up = (prev["macd"] <= prev["macd_signal"]) and (latest["macd"] > latest["macd_signal"])
    macd_cross_down = (prev["macd"] >= prev["macd_signal"]) and (latest["macd"] < latest["macd_signal"])

    rsi_bullish = latest["rsi"] >= Config.RSI_BULLISH_MIN and latest["rsi"] > prev["rsi"]
    rsi_bearish = latest["rsi"] <= Config.RSI_BEARISH_MAX and latest["rsi"] < prev["rsi"]

    volume_ok = pd.notna(latest["volume_ratio"]) and latest["volume_ratio"] >= Config.MIN_VOLUME_RATIO
    atr_ok = pd.notna(latest["atr_pct"]) and latest["atr_pct"] >= Config.MIN_ATR_PCT

    if trend_up:
        score += 2
        reasons.append("trend_up")
    if trend_down:
        score += 2
        reasons.append("trend_down")

    if macd_cross_up:
        score += 3
        reasons.append("macd_cross_up")
    if macd_cross_down:
        score += 3
        reasons.append("macd_cross_down")

    if rsi_bullish:
        score += 2
        reasons.append("rsi_rising")
    if rsi_bearish:
        score += 2
        reasons.append("rsi_falling")

    if volume_ok:
        score += 1
        reasons.append("volume_confirmed")
    if atr_ok:
        score += 1
        reasons.append("atr_ok")

    if trend_up and macd_cross_up and rsi_bullish and volume_ok:
        return Signal.BUY, score, reasons, "UPTREND"
    if trend_down and macd_cross_down and rsi_bearish and volume_ok:
        return Signal.SELL, score, reasons, "DOWNTREND"

    trend = "UPTREND" if trend_up else "DOWNTREND" if trend_down else "SIDEWAYS"
    return Signal.NONE, score, reasons, trend


def analyze_symbol(exchange: ccxt.Exchange, candidate: MarketCandidate) -> Optional[ScanResult]:
    df = fetch_ohlcv_df(exchange, candidate.symbol)

    min_required = max(Config.EMA_SLOW, Config.MACD_SLOW + Config.MACD_SIGNAL, Config.VOL_MA_PERIOD) + 5
    if len(df) < min_required:
        logger.debug("Skipping %s: insufficient candle history.", candidate.symbol)
        return None

    df = add_indicators(df)
    latest = df.iloc[-1]
    prev = df.iloc[-2]

    signal, score, reasons, trend = classify_signal(df)

    return ScanResult(
        symbol=candidate.symbol,
        timeframe=Config.TIMEFRAME,
        candle_time=df.index[-1].isoformat(),
        last_price=float(latest["close"]),
        quote_volume_24h=float(candidate.quote_volume_24h),
        rsi=float(latest["rsi"]),
        macd=float(latest["macd"]),
        macd_signal=float(latest["macd_signal"]),
        macd_prev=float(prev["macd"]),
        macd_signal_prev=float(prev["macd_signal"]),
        ema_fast=float(latest["ema_fast"]),
        ema_slow=float(latest["ema_slow"]),
        atr=float(latest["atr"]),
        atr_pct=float(latest["atr_pct"]),
        candle_volume=float(latest["volume"]),
        avg_volume=float(latest["avg_volume"]) if pd.notna(latest["avg_volume"]) else 0.0,
        volume_ratio=float(latest["volume_ratio"]) if pd.notna(latest["volume_ratio"]) else 0.0,
        trend=trend,
        score=score,
        reasons=reasons,
        signal=signal,
    )


# -----------------------------------------------------------------------------
# Scanner orchestration
# -----------------------------------------------------------------------------

def run_scan(
    exchange_id: str = Config.EXCHANGE_ID,
    only_actionable: bool = True,
    dedupe: bool = True,
) -> list[ScanResult]:
    exchange = build_exchange(exchange_id)
    candidates = get_liquid_usdt_pairs(exchange)
    state = SignalStateStore()

    results: list[ScanResult] = []

    for i, candidate in enumerate(candidates, start=1):
        try:
            result = analyze_symbol(exchange, candidate)
            if result is None:
                continue

            logger.info("[%d/%d] %s %s score=%s price=%s",
                        i, len(candidates), result.symbol, result.signal.value, result.score, result.last_price)

            if only_actionable and result.signal == Signal.NONE:
                pass
            else:
                if dedupe and result.signal != Signal.NONE and state.already_sent(result.symbol, result.candle_time, result.signal):
                    logger.info("Skipping duplicate signal for %s on %s", result.symbol, result.candle_time)
                else:
                    results.append(result)
                    if dedupe and result.signal != Signal.NONE:
                        state.mark_sent(result.symbol, result.candle_time, result.signal)

        except ccxt.BaseError as err:
            logger.error("Exchange error on %s: %s", candidate.symbol, err)
        except Exception as err:
            logger.error("Failed to analyze %s: %s", candidate.symbol, err)

        time.sleep(Config.REQUEST_DELAY_SECONDS)

    if dedupe:
        state.save()

    results.sort(key=lambda r: (r.signal != Signal.NONE, r.score, r.quote_volume_24h), reverse=True)
    return results[:Config.MAX_RESULTS]


def run_scan_json(**kwargs) -> list[dict[str, Any]]:
    return [r.to_dict() for r in run_scan(**kwargs)]


# -----------------------------------------------------------------------------
# Secure execution blueprint (still opt-in only)
# -----------------------------------------------------------------------------

def get_master_key() -> bytes:
    key = os.environ.get("MASTER_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("MASTER_ENCRYPTION_KEY is not set.")
    return key.encode()


def encrypt_credentials(api_key: str, api_secret: str) -> tuple[bytes, bytes]:
    f = Fernet(get_master_key())
    return f.encrypt(api_key.encode()), f.encrypt(api_secret.encode())


def decrypt_credentials(encrypted_api_key: bytes, encrypted_api_secret: bytes) -> tuple[str, str]:
    f = Fernet(get_master_key())
    try:
        api_key = f.decrypt(encrypted_api_key).decode()
        api_secret = f.decrypt(encrypted_api_secret).decode()
    except InvalidToken as err:
        raise RuntimeError("Failed to decrypt exchange credentials.") from err
    return api_key, api_secret


def build_authenticated_exchange(
    exchange_id: str,
    encrypted_api_key: bytes,
    encrypted_api_secret: bytes
) -> ccxt.Exchange:
    api_key, api_secret = decrypt_credentials(encrypted_api_key, encrypted_api_secret)
    exchange_class = getattr(ccxt, exchange_id)
    exchange = exchange_class({
        "apiKey": api_key,
        "secret": api_secret,
        "enableRateLimit": True,
        "options": {"defaultType": Config.MARKET_TYPE},
    })
    exchange.load_markets()
    return exchange


def normalize_order_amount(exchange: ccxt.Exchange, symbol: str, amount: float) -> float:
    """
    Normalizes amount to exchange precision. Raises if result is invalid.
    """
    normalized = float(exchange.amount_to_precision(symbol, amount))
    if normalized <= 0:
        raise ValueError("Normalized amount is <= 0.")
    return normalized


def place_market_order(
    exchange_id: str,
    encrypted_api_key: bytes,
    encrypted_api_secret: bytes,
    symbol: str,
    side: str,
    amount: float,
    confirm: bool = False,
) -> dict[str, Any]:
    if not confirm:
        raise RuntimeError("Refusing to place a live order without confirm=True.")
    if side not in ("buy", "sell"):
        raise ValueError("side must be 'buy' or 'sell'.")
    if amount <= 0:
        raise ValueError("amount must be positive.")

    exchange = build_authenticated_exchange(exchange_id, encrypted_api_key, encrypted_api_secret)
    amount = normalize_order_amount(exchange, symbol, amount)

    logger.info("Placing %s market order %s amount=%s", side.upper(), symbol, amount)
    order = with_retries(
        exchange.create_order,
        symbol=symbol,
        type="market",
        side=side,
        amount=amount,
    )
    logger.info("Order placed: id=%s status=%s", order.get("id"), order.get("status"))
    return order


# -----------------------------------------------------------------------------
# CLI entrypoint
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    signals = run_scan(only_actionable=True, dedupe=True)

    print("\n" + "=" * 90)
    print(f"ACTIONABLE SIGNALS ({len(signals)})")
    print("=" * 90)
    for result in signals:
        print(json.dumps(result.to_dict(), ensure_ascii=False))
