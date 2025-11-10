#!/bin/bash
echo "🔁 Starting update and restart process..."

cd /opt/render/project/src

# Run updater
./.venv/bin/python update.py

echo "🚀 Launching bot..."
# Launch main bot
./.venv/bin/python main.py
