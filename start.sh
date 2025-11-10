cd /opt/render/project/src || exit 1

# Create venv if missing
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi

# Activate venv
source .venv/bin/activate

# Install requirements
pip install --upgrade pip
pip install -r requirements.txt

# Run updater + bot
python3 update.py
exec python3 main.py
