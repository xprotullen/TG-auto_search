import time
import humanize
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import RPCError
from utils.database import collection, ensure_indexes, INDEXED_COLL
from redis.exceptions import ConnectionError as RedisConnectionError
from motor.motor_asyncio import AsyncIOMotorClient
from .search import rdb, clear_redis_for_chat
from info import AUTHORIZED_USERS
import logging

logger = logging.getLogger(__name__)

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
        "/resetdb - clean database\n\n"
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


@Client.on_message(filters.command("clearcache"))
async def clear_cache_cmd(client, message):
    user_id = message.from_user.id
    if user_id not in AUTHORIZED_USERS:
        return await message.reply_text("🚫 You are not authorized to use this command.")

    parts = message.text.split()
    if len(parts) < 2:
        return await message.reply_text("Usage: `/clearcache <chat_id>`", quote=True)

    try:
        chat_id = int(parts[1])
    except ValueError:
        return await message.reply_text("❌ Invalid chat ID!", quote=True)

    msg = await message.reply_text("🧹 Clearing Redis cache, please wait...")

    try:
        deleted = await clear_redis_for_chat(chat_id)
        if deleted == 0:
            await msg.edit_text(f"ℹ️ No Redis keys found for `{chat_id}`.")
        else:
            await msg.edit_text(f"✅ Cleared `{deleted}` Redis cache keys for chat `{chat_id}`.")
    except RPCError as e:
        await msg.edit_text(f"⚠️ Telegram RPC Error: {e}")
    except Exception as e:
        await msg.edit_text(f"❌ Unexpected error: {e}")    
        
@Client.on_message(filters.command("resetdb") & filters.private)
async def resetdb_handler(client, message):
    """Drop full movie database only after confirmation."""
    user_id = message.from_user.id
    if user_id not in AUTHORIZED_USERS:
        return 
        
    s = await message.reply("This will permanently delete all movie data and indexes\n\nType `<code>confirm</code>` to delete")
    skip_msg = await client.listen(chat_id=message.chat.id, user_id=message.from_user.id)
    await s.delete()

    try:
        if skip_msg.text.strip().lower() != "confirm":
            return await message.reply("❌ Reset cancelled.")
        msg = await message.reply("🧹 Resetting database... please wait.")
        await collection.drop()            
        await INDEXED_COLL.drop_indexes()  
        await ensure_indexes()            
        await msg.edit_text("✅ Database reset successfully!\nAll data wiped and indexes rebuilt.")

        logger.info("✅ Database reset by user %s", user_id)
    except Exception as e:
        logger.exception("❌ Database reset failed")
        await message.reply_text(f"❌ Reset failed: {e}")
        
@Client.on_message(filters.command("checkbot") & filters.private)
async def checkbot_handler(client, message):
    """Self-diagnostic command to check bot health and resource usage."""
    user_id = message.from_user.id
    if user_id not in AUTHORIZED_USERS:
        return 
        
    start_time = time.time()
    status_lines = []

    # ========== MongoDB ==========
    try:
        await collection.estimated_document_count()
        stats = await collection.database.command("dbStats")

        mongo_storage_raw = stats.get("storageSize", 0)
        mongo_data_raw = stats.get("dataSize", 0)
        mongo_index_raw = stats.get("indexSize", 0)
        coll_count = stats.get("collections", 0)
        obj_count = stats.get("objects", 0)

        mongo_storage = humanize.naturalsize(mongo_storage_raw, binary=True)
        mongo_data = humanize.naturalsize(mongo_data_raw, binary=True)
        mongo_index = humanize.naturalsize(mongo_index_raw, binary=True)

        # ✅ Accurate Atlas free-tier (512 MiB)
        atlas_limit = 512 * 1024 * 1024  # 512 MiB
        total_used = mongo_data_raw + mongo_index_raw
        used_percent = (total_used / atlas_limit) * 100
        free_space = max(atlas_limit - total_used, 0)
        free_space_h = humanize.naturalsize(free_space, binary=True)

        status_lines.append("🟢 MongoDB: Connected")
        status_lines.append(f"   ├─ Collections: {coll_count}")
        status_lines.append(f"   ├─ Documents: {obj_count}")
        status_lines.append(f"   ├─ Data Size: {mongo_data}")
        status_lines.append(f"   ├─ Storage: {mongo_storage}")
        status_lines.append(f"   ├─ Index: {mongo_index}")
        status_lines.append(f"   ├─ Used: {humanize.naturalsize(total_used, binary=True)} / 512 MiB ({used_percent:.2f}% used)")
        status_lines.append(f"   └─ Free Space: {free_space_h}")
    except Exception as e:
        status_lines.append(f"🔴 MongoDB: Failed ({e})")

    # ========== Redis ==========
    try:
        info = await rdb.info()
        used_memory_raw = info.get("used_memory", 0)
        maxmemory_raw = info.get("maxmemory", 0)
        total_keys = await rdb.dbsize()

        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)
        total_access = hits + misses
        hit_ratio = (hits / total_access * 100) if total_access > 0 else 0

        # Assume 100 MiB for free plan if not defined
        if not maxmemory_raw:
            maxmemory_raw = 100 * 1024 * 1024
            plan_note = " (estimated free plan)"
        else:
            plan_note = ""

        used_percent = (used_memory_raw / maxmemory_raw) * 100
        free_mem = max(maxmemory_raw - used_memory_raw, 0)

        used_memory = humanize.naturalsize(used_memory_raw, binary=True)
        max_mem_h = humanize.naturalsize(maxmemory_raw, binary=True)
        free_mem_h = humanize.naturalsize(free_mem, binary=True)

        status_lines.append(f"🟢 Redis: Connected{plan_note}")
        status_lines.append(f"   ├─ Used: {used_memory} / {max_mem_h} ({used_percent:.2f}% used)")
        status_lines.append(f"   ├─ Free: {free_mem_h}")
        status_lines.append(f"   ├─ Cached Keys: {total_keys}")
        status_lines.append(f"   └─ Cache Hit Ratio: {hit_ratio:.2f}%")
    except RedisConnectionError:
        status_lines.append("🔴 Redis: Failed (Connection error)")
    except Exception as e:
        status_lines.append(f"🔴 Redis: Failed ({e})")

    # ========== Mongo Index Check ==========
    try:
        indexes = await collection.index_information()
        if "movie_text_index" in indexes:
            status_lines.append("🟢 Mongo Index: OK ✅")
        else:
            status_lines.append("🟡 Mongo Index: Missing (Run ensure_indexes())")
    except Exception as e:
        status_lines.append(f"🔴 Index Check Failed: {e}")

    # ========== Final Report ==========
    response_time = round((time.time() - start_time) * 1000, 2)
    status_lines.append(f"⚙️ Response Time: {response_time} ms")

    report = "<b>🤖 Wroxen System Health Report</b>\n\n" + "\n".join(status_lines)
    await message.reply_text(report, parse_mode=enums.ParseMode.HTML)
