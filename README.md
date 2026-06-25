# NEXARA Telegram Crypto Bot V1

Production-grade automated crypto trading bot with multi-asset scanning, Telegram alerts, and mock trading execution.

## 🚀 Features

- **Multi-asset scanning**: Scans all USDT pairs on Binance
- **Smart signals**: Uses RSI, MACD, EMA, ATR, and Volume analysis
- **Telegram integration**: Real-time alerts and bot control
- **Auto trading**: Optional mock/paper trading (V2: live trading)
- **Deduplication**: Prevents duplicate alerts on same candle
- **Production-ready**: Error handling, retries, logging

## 📋 Prerequisites

- Python 3.9+
- Telegram Bot Token
- Binance API keys (optional for V1)

## 🛠️ Installation

```bash
# Clone repository
git clone <your-repo-url>
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## ⚙️ Configuration

1. Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

2. Edit `.env` and add your credentials:
```bash
TELEGRAM_BOT_TOKEN=your_actual_token
TELEGRAM_CHAT_ID=your_chat_id
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret
```

## 🚀 Running Locally

### Option 1: Run API Server only
```bash
uvicorn api_server:app --reload --host 0.0.0.0 --port 8000
```

### Option 2: Run Telegram Bot only
```bash
python run_telegram.py
```

### Option 3: Run both (separate terminals)
```bash
# Terminal 1
uvicorn api_server:app --reload

# Terminal 2
python run_telegram.py
```

## 📱 Telegram Commands

- `/start` - Welcome message
- `/status` - Check bot status
- `/auto_on` - Enable auto trading
- `/auto_off` - Disable auto trading
- `/lastsignals` - View recent signals
- `/lasttrades` - View recent trades

## 🌐 API Endpoints

- `GET /` - Health check
- `GET /api/bot/status` - Bot status
- `POST /api/bot/auto_on` - Enable auto trading
- `POST /api/bot/auto_off` - Disable auto trading
- `GET /api/scan` - Run manual scan
- `POST /api/trade/run` - Scan + alert + auto trade

## 🚢 Deploy to Render

### 1. Web Service (API Server)
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn api_server:app --host 0.0.0.0 --port $PORT`
- **Environment Variables**: Add all from `.env`

### 2. Background Worker (Telegram Bot)
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `python run_telegram.py`
- **Environment Variables**: Add all from `.env`

## 📊 Signal Strategy

The bot uses multiple indicators to generate signals:

- **EMA Trend Filter**: 50/200 EMA crossover
- **MACD Crossover**: 12/26/9 MACD
- **RSI Momentum**: 14-period RSI
- **Volume Confirmation**: Current vs average volume
- **ATR Volatility**: Minimum 0.3% volatility required

## ⚠️ Important Notes

### V1 (Current)
- ✅ Scans all USDT pairs
- ✅ Sends Telegram alerts
- ✅ Mock/paper trading only
- ❌ No live Binance orders

### V2 (Next)
- 🔄 Live Binance execution
- 🔄 Stop-loss / Take-profit
- 🔄 Position management

## 🔒 Security

- Never commit `.env` to Git
- Use environment variables for all secrets
- Enable `BINANCE_TESTNET=true` for testing
- Use `MASTER_ENCRYPTION_KEY` for V2 live trading

## 📝 License

MIT License

## 🤝 Support

For issues or questions, please open an issue on GitHub.
