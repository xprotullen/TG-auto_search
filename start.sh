#!/bin/bash
echo "🔁 Updating and restarting bot..."
cd /opt/render/project/src   # make sure you are in repo root

# Activate venv if it exists
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Run updater
python3 update.py

# Launch main bot (replaces shell)
exec python3 main.py
