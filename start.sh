#!/bin/bash
echo "🔁 Updating and launching bot..."
cd /opt/render/project/src || exit 1

# Run updater
python3 update.py

# Start Flask keep-alive in background
gunicorn app:app --bind 0.0.0.0:$PORT &

# Launch main bot (foreground)
exec python3 main.py
