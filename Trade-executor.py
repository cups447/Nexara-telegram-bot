from config import DEFAULT_ORDER_USDT, BINANCE_TESTNET

class TradeExecutor:
    def __init__(self):
        self.testnet = BINANCE_TESTNET

    def calculate_qty_from_usdt(self, price: float):
        if price <= 0:
            return 0.0
        return round(DEFAULT_ORDER_USDT / price, 6)

    def place_market_order(self, symbol: str, side: str, qty: float):
        """
        V1 = paper/mock execution
        V2 tuzashyiramo ccxt Binance real orders
        """
        return {
            "success": True,
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "mode": "paper" if self.testnet else "live",
            "message": "Mock order executed"
        }
