from telegram_bot import build_telegram_app

if __name__ == "__main__":
    app = build_telegram_app()
    print("Starting NEXARA Telegram Bot...")
    app.run_polling()
