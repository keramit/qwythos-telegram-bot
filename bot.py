#!/usr/bin/env python3
"""
QWYTHOS Telegram Bot — with embedded token loading
"""

import os
import logging
import httpx
from telegram import Update, ForceReply
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, ContextTypes, filters
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load credentials from DSH config directly
import yaml
CREDENTIALS_PATH = "/Users/ahmedabushama/.dsh/.credentials.yaml"
d = yaml.safe_load(open(CREDENTIALS_PATH))
GROQ_API_KEY = d["refs"]["GROQ_API_KEY"]
TELEGRAM_BOT_TOKEN = "REMOVED_BOT_TOKEN"

SYSTEM_PROMPT = """أنت مساعد تقني ذكي شخصي للمهندس أحمد.
تجيب بالعربية والإنجليزية حسب لغة السؤال.
متخصص في: البرمجة، البنية التحتية، الأمن السيبراني، الذكاء الاصطناعي.
قدّم أجوبة دقيقة وعملية مع أمثلة. استخدم Markdown للتنسيق."""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 QWYTHOS Assistant جاهز!\n"
        "النموذج: openai/gpt-oss-120b (Groq Free Tier)\n"
        "اسألني أي شيء تقني!",
        parse_mode="Markdown"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_msg = update.message.text
    await update.message.reply_chat_action(__import__("telegram").ChatAction.TYPING)

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                json={
                    "model": "openai/gpt-oss-120b",
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg}
                    ],
                    "max_tokens": 65536,
                    "temperature": 0.7,
                    "top_p": 0.9,
                }
            )

        if resp.status_code == 200:
            reply = resp.json()["choices"][0]["message"]["content"]
            await update.message.reply_text(reply, parse_mode="Markdown")
        elif resp.status_code == 429:
            # Fallback to qwen3.8-27b
            async with httpx.AsyncClient(timeout=45.0) as client:
                resp2 = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                    json={
                        "model": "qwen/qwen3.8-27b",
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_msg}
                        ],
                        "max_tokens": 16384,
                        "temperature": 0.7,
                    }
                )
            fallback_reply = resp2.json()["choices"][0]["message"]["content"] if resp2.status_code == 200 else "Fallback failed"
            await update.message.reply_text(
                "[Rate limited — using fallback qwen3.8-27b]\n\n" + fallback_reply,
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"Error: {resp.status_code}\n{resp.text[:300]}"
            )
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(f"Error: {str(e)[:300]}")


def main():
    print("Starting QWYTHOS Telegram Bot...")
    print(f"Model: openai/gpt-oss-120b (primary)")
    print(f"Fallback: qwen/qwen3.8-27b")
    print("Bot is active!")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()


if __name__ == "__main__":
    main()
