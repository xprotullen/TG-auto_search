import time
import asyncio
from pyrogram import Client, filters
from utils.database import collection
from redis.exceptions import ConnectionError as RedisConnectionError
from motor.motor_asyncio import AsyncIOMotorClient

from main import rdb  # if Redis instance defined in main file; else import accordingly


@Client.on_message(filters.command("checkbot") & filters.private)
async def checkbot_handler(client, message):
    """Self-diagnostic command to check bot health."""
    start_time = time.time()
    status_lines = []

    # ---- MongoDB Check ----
    try:
        await collection.estimated_document_count()
        status_lines.append("🟢 MongoDB: Connected")
    except Exception as e:
        status_lines.append(f"🔴 MongoDB: Failed ({e})")

    # ---- Redis Check ----
    try:
        await rdb.ping()
        status_lines.append("🟢 Redis: Connected")
    except RedisConnectionError:
        status_lines.append("🔴 Redis: Failed (Connection error)")
    except Exception as e:
        status_lines.append(f"🔴 Redis: Failed ({e})")

    # ---- Index Check ----
    try:
        indexes = await collection.index_information()
        if "movie_text_index" in indexes:
            status_lines.append("🟢 Mongo Index: OK ✅")
        else:
            status_lines.append("🟡 Mongo Index: Missing (Run ensure_indexes())")
    except Exception as e:
        status_lines.append(f"🔴 Index Check Failed: {e}")

    # ---- Response Time ----
    response_time = round((time.time() - start_time) * 1000, 2)
    status_lines.append(f"⚙️ Response Time: {response_time} ms")

    # ---- Final Report ----
    report = "<b>🤖 wroxen Health Report</b>\n\n" + "\n".join(status_lines)
    await message.reply_text(report, parse_mode="html")
