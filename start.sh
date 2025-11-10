#!/bin/bash
echo "🔁 Starting update and restart process..."

# Update codebase
python3 update.py

# Start bot (main.py)
echo "🚀 Launching bot..."
python3 main.py
