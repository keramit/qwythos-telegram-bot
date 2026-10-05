#!/usr/bin/env python3
"""
QWYTHOS Telegram Bot — Webhook server for cloud deployment.

Cloud platforms (Render, Railway, HF) sleep a service when there is no
INBOUND traffic. Long polling is outbound-only, so the service would sleep
and the bot would go deaf. Webhook mode makes Telegram push each update to
this server's public URL — an inbound request — which keeps the service
awake exactly when it matters.

Run locally:      python webhook_server.py
Production:       uvicorn webhook_server:fastapi_app --host 0.0.0.0 --port $PORT

Env vars:
  TELEGRAM_BOT_TOKEN  (required) — from BotFather
  GROQ_API_KEY        (required) — read from DSH credentials by start script
  WEBHOOK_BASE_URL    (required) — public https URL, e.g. https://x.onrender.com
  WEBHOOK_SECRET      (optional) — random string; Telegram signs each request with it
  PORT                (optional) — default 8080
"""

import os
import logging

from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

# Import handlers and config from the existing bot module (no side effects:
# app.py only runs main() under __main__).
import app as bot

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

WEBHOOK_BASE_URL = os.environ.get("WEBHOOK_BASE_URL", "").rstrip("/")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
PORT = int(os.environ.get("PORT", "8080"))

if not WEBHOOK_BASE_URL:
    raise ValueError("❌ Set WEBHOOK_BASE_URL (public https URL of this service)")

WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}" if WEBHOOK_SECRET else "/webhook"
WEBHOOK_URL = f"{WEBHOOK_BASE_URL}{WEBHOOK_PATH}"

# ---- Build the PTB application (handlers mirror app.py's main()) ----
ptb_app = ApplicationBuilder().token(bot.TELEGRAM_BOT_TOKEN).build()
ptb_app.add_handler(CommandHandler("start", bot.start))
ptb_app.add_handler(CommandHandler("help", bot.start))
ptb_app.add_handler(CommandHandler("status", bot.status_cmd))
ptb_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
ptb_app.add_handler(MessageHandler(filters.Document.ALL, bot.handle_document))
ptb_app.add_handler(MessageHandler(filters.PHOTO, bot.handle_photo))

# ---- FastAPI wrapper: health endpoint + webhook receiver ----
fastapi_app = FastAPI(title="QWYTHOS Bot", version="1.0")


@fastapi_app.on_event("startup")
async def on_startup():
    await ptb_app.initialize()
    await ptb_app.start()
    await ptb_app.bot.set_webhook(
        url=WEBHOOK_URL,
        secret_token=WEBHOOK_SECRET or None,
        drop_pending_updates=True,
        allowed_updates=["message", "edited_message"],
    )
    logger.info(f"✅ Webhook registered: {WEBHOOK_URL}")


@fastapi_app.on_event("shutdown")
async def on_shutdown():
    await ptb_app.bot.delete_webhook()
    await ptb_app.stop()
    await ptb_app.shutdown()
    logger.info("👋 Webhook removed, app stopped")


@fastapi_app.get("/")
async def health():
    """Health check — Render/Railway hit this to decide if the service is up."""
    return {"status": "ok", "service": "qwythos-bot", "mode": "webhook"}


@fastapi_app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@fastapi_app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    """Receive one Telegram update and hand it to the PTB application."""
    # Verify Telegram's secret header so random POSTs can't drive the bot.
    if WEBHOOK_SECRET:
        got = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if got != WEBHOOK_SECRET:
            logger.warning("Rejected webhook POST with bad secret token")
            return Response(status_code=403)

    try:
        data = await request.json()
        update = Update.de_json(data, ptb_app.bot)
        await ptb_app.process_update(update)
    except Exception as e:
        # Always 200: a non-200 makes Telegram retry the same update forever.
        logger.error(f"Error processing update: {e}")
    return Response(status_code=200)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(fastapi_app, host="0.0.0.0", port=PORT)
