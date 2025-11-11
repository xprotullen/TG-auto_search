import os
import re
import time
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

load_dotenv("config.env")

id_pattern = re.compile(r"^\\d+$")

BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_ID = int(os.getenv("APP_ID", "0"))
API_HASH = os.getenv("API_HASH")
USER_SESSION = os.getenv("USER_SESSION")
AUTHORIZED_USERS = [
    int(x) for x in os.getenv("AUTHORIZED_USERS", "").split(",") if x.strip().isdigit()
]
MONGO_URL = os.getenv("MONGO_URL")
DB_NAME = os.getenv("DB_NAME", "wroxen-moviesbotdb")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "wroxen-movies")
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_USERNAME = os.getenv("REDIS_USERNAME", None)
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
    datefmt="%d-%b-%y %H:%M:%S",
    handlers=[
        RotatingFileHandler("bot.log", maxBytes=50_000_000, backupCount=10),
        logging.StreamHandler(),
    ],
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

start_uptime = time.time()

def LOGGER(name: str) -> logging.Logger:
    return logging.getLogger(name)
