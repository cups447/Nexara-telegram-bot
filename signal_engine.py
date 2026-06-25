from typing import Any, Dict, List

from market_scanner_pro import run_scan_json

def convert_scan_result(item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Hindura result iva muri market_scanner_pro.py
    ibe format yoroshye bot ishobora gukoresha.
    """
    signal = item.get("signal", "NONE")
    price = item.get("last_price")
    atr = item.get("atr", 0.0)
    symbol = item.get("symbol")

    # Simple SL/TP heuristic kuri V1
    stop_loss = None
    take_profit = None

    if price and atr:
        if signal == "BUY":
            stop_loss = round(price - (atr * 1.5), 8)
            take_profit = round(price + (atr * 2.5), 8)
        elif signal == "SELL":
            stop_loss = round(price + (atr * 1.5), 8)
            take_profit = round(price - (atr * 2.5), 8)

    return {
        "symbol": symbol,
        "signal": signal,
        "entry": price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "reason": ", ".join(item.get("reasons", [])),
        "score": item.get("score", 0),
        "trend": item.get("trend"),
        "timeframe": item.get("timeframe"),
        "candle_time": item.get("candle_time"),
        "raw": item
    }

def get_all_signals() -> List[Dict[str, Any]]:
    """
    Iscaninga pairs zose ikagarura actionable signals gusa.
    """
    raw_results = run_scan_json(only_actionable=True, dedupe=True)
    signals = []

    for item in raw_results:
        converted = convert_scan_result(item)
        if converted["signal"] in ("BUY", "SELL"):
            signals.append(converted)

    # strongest first
    signals.sort(key=lambda x: x.get("score", 0), reverse=True)
    return signals
