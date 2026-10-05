#!/bin/bash
# QWYTHOS Telegram Bot Launcher
# Sets environment and runs the bot

export TELEGRAM_BOT_TOKEN="REMOVED_BOT_TOKEN"
# Activate virtualenv (required under launchd, which has no shell profile)
VENV="/Users/ahmedabushama/venv"
source "$VENV/bin/activate"

export GROQ_API_KEY="$("$VENV/bin/python" -c "import yaml;print(yaml.safe_load(open('/Users/ahmedabushama/.dsh/.credentials.yaml'))['refs']['GROQ_API_KEY'])")"

cd /Users/ahmedabushama/qwythos-telegram-bot
# Keep the Mac from idle-sleeping so the bot keeps polling Telegram.
# NOTE: -i works on battery too; -s adds AC-power protection.
# Lid-close sleep CANNOT be defeated by caffeinate — see README for that.
exec /usr/bin/caffeinate -is "$VENV/bin/python" app.py
