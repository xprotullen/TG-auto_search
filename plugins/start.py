import time
import asyncio
from pyrogram import Client, filters, enums
from utils.database import collection
from redis.exceptions import ConnectionError as RedisConnectionError
from motor.motor_asyncio import AsyncIOMotorClient
from .search import rdb  
from info import AUTHORIZED_USERS

@Client.on_message(filters.command("start") & filters.private)
async def start_command(client, message):
    user_id = message.from_user.id
    if user_id not in AUTHORIZED_USERS:
        return
        
    await message.reply_text(
        "👋 <b>Welcome!</b>\n\n"
        "This bot helps you search and manage movie data from indexed groups.\n\n"
        "🎬 <b>How to Use:</b>\n"
        "1️⃣ Add me to your movie group as admin.\n"
        "2️⃣ Use /index to link source and target chats.\n"
        "3️⃣ Send any movie name in the group to search instantly.\n\n"
        "💡 Works only for authorized users.\n\n"
        "<i>Enjoy your private movie search experience!</i>",
        parse_mode=enums.ParseMode.HTML
    )


@Client.on_message(filters.command("checkbot") & filters.private)
async def checkbot_handler(client, message):
    """Self-diagnostic command to check bot health."""
    user_id = message.from_user.id
    if user_id not in AUTHORIZED_USERS:
        return
        
    start_time = time.time()
    status_lines = []

    try:
        await collection.estimated_document_count()
        status_lines.append("🟢 MongoDB: Connected")
    except Exception as e:
        status_lines.append(f"🔴 MongoDB: Failed ({e})")

    try:
        await rdb.ping()
        status_lines.append("🟢 Redis: Connected")
    except RedisConnectionError:
        status_lines.append("🔴 Redis: Failed (Connection error)")
    except Exception as e:
        status_lines.append(f"🔴 Redis: Failed ({e})")

    try:
        indexes = await collection.index_information()
        if "movie_text_index" in indexes:
            status_lines.append("🟢 Mongo Index: OK ✅")
        else:
            status_lines.append("🟡 Mongo Index: Missing (Run ensure_indexes())")
    except Exception as e:
        status_lines.append(f"🔴 Index Check Failed: {e}")

    response_time = round((time.time() - start_time) * 1000, 2)
    status_lines.append(f"⚙️ Response Time: {response_time} ms")

    report = "<b>🤖 wroxen Health Report</b>\n\n" + "\n".join(status_lines)
    await message.reply_text(report, parse_mode=enums.ParseMode.HTML)
