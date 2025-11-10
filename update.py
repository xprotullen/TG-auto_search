import os
from os import path as opath, getenv, rename
from subprocess import run as srun
from dotenv import load_dotenv
import logging
import sys

# ── Setup logger ─────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AutoUpdater")

# ── Load environment variables ───────────────
load_dotenv("config.env", override=True)

UPSTREAM_REPO = getenv("UPSTREAM_REPO", "https://github.com/xprotullen/TG-auto_search")
UPSTREAM_BRANCH = getenv("UPSTREAM_BRANCH", "master")

if not UPSTREAM_REPO:
    logger.warning("⚠️ UPSTREAM_REPO is not defined — skipping auto update.")
    sys.exit(0)

logger.info(f"🔄 Updating from repo: {UPSTREAM_REPO} ({UPSTREAM_BRANCH})")

config_backup = "../config.env.tmp"

try:
    if opath.exists("config.env"):
        rename("config.env", config_backup)

    # Clean old git data
    if opath.exists(".git"):
        srun(["rm", "-rf", ".git"])

    # Run update commands
    git_commands = (
        f"git init -q && "
        f"git config --global user.email 'autoupdate@bot.local' && "
        f"git config --global user.name 'AutoUpdater' && "
        f"git add . && git commit -sm update -q && "
        f"git remote add origin {UPSTREAM_REPO} && "
        f"git fetch origin -q && "
        f"git reset --hard origin/{UPSTREAM_BRANCH} -q"
    )

    result = srun(git_commands, shell=True)

    if result.returncode == 0:
        logger.info("✅ Updated to latest commit.")
    else:
        logger.error("❌ Update failed — check repo URL/branch.")

finally:
    if opath.exists(config_backup):
        rename(config_backup, "config.env")

# ── Restart services ─────────────────────────
logger.info("🚀 Restarting services...")

# Start Gunicorn for web app
srun("nohup gunicorn app:app &", shell=True)
logger.info("✅ Gunicorn started in background.")

# Start bot
os.execv(sys.executable, [sys.executable, "main.py"])
