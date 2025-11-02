import time
import humanize
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
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
        
    text = (
        "👋 <b>Welcome to Wroxen Bot!</b>\n\n"
        "Here’s how to use me:\n"
        "━━━━━━━━━━━━━━━\n"
        "🧩 <b>1. Index Source Chats:</b>\n"
        "Use `/index <target_chat_id> <source_chat_id>`\n"
        "to link a group with a source channel.\n\n"
        "🗑 <b>2. Delete Indexed Data:</b>\n"
        "Use `/delete <target_chat_id> <source_chat_id>` to unlink.\n\n"
        "🔍 <b>3. Search:</b>\n"
        "Simply send a movie name in your group to search.\n\n"
        "⚙️ <b>Notes:</b>\n"
        "• Bot only works in authorized and linked chats.\n"
        "• Use `/checkbot` to check MongoDB & Redis status.\n"
        "• Avoid rapid button clicks to prevent FloodWaits."
    )

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/thelx0980")]
    ])
    await message.reply_text(
        text,
        reply_markup=buttons,
        disable_web_page_preview=True
    )

@Client.on_message(filters.command("checkbot") & filters.private)
async def checkbot_handler(client, message):
    """Self-diagnostic command to check bot health and resource usage."""
    user_id = message.from_user.id
    if user_id not in AUTHORIZED_USERS:
        return 
        
    start_time = time.time()
    status_lines = []

    try:
        await collection.estimated_document_count()
        stats = await collection.database.command("dbStats")
        mongo_storage = humanize.naturalsize(stats["storageSize"])
        mongo_data = humanize.naturalsize(stats["dataSize"])
        mongo_index = humanize.naturalsize(stats["indexSize"])
        coll_count = stats.get("collections", 0)
        obj_count = stats.get("objects", 0)

        status_lines.append("🟢 MongoDB: Connected")
        status_lines.append(f"   ├─ Collections: {coll_count}")
        status_lines.append(f"   ├─ Documents: {obj_count}")
        status_lines.append(f"   ├─ Data Size: {mongo_data}")
        status_lines.append(f"   ├─ Storage: {mongo_storage}")
        status_lines.append(f"   └─ Index: {mongo_index}")
    except Exception as e:
        status_lines.append(f"🔴 MongoDB: Failed ({e})")

    try:
        info = await rdb.info()
        used_memory = humanize.naturalsize(info.get("used_memory", 0))
        maxmemory = info.get("maxmemory", 0)
        total_keys = await rdb.dbsize()

        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)
        total_access = hits + misses
        hit_ratio = (hits / total_access * 100) if total_access > 0 else 0

        if maxmemory:
            used_percent = (info["used_memory"] / maxmemory) * 100
            max_mem_h = humanize.naturalsize(maxmemory)
            status_lines.append(f"🟢 Redis: Connected ({used_percent:.1f}% used)")
            status_lines.append(f"   ├─ Used: {used_memory} / {max_mem_h}")
        else:
            status_lines.append("🟢 Redis: Connected")
            status_lines.append(f"   ├─ Used Memory: {used_memory}")

        status_lines.append(f"   ├─ Cached Keys: {total_keys}")
        status_lines.append(f"   └─ Cache Hit Ratio: {hit_ratio:.2f}%")
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

    report = "<b>🤖 Wroxen System Health Report</b>\n\n" + "\n".join(status_lines)
    await message.reply_text(report, parse_mode=enums.ParseMode.HTML)
