import time
import asyncio
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
        "👋 **Welcome to Wroxen Bot!**\n\n"
        "Here’s how to use me:\n"
        "━━━━━━━━━━━━━━━\n"
        "🧩 **1. Index Source Chats:**\n"
        "Use `/index <target_chat_id> <source_chat_id>`\n"
        "to link a group with a source channel.\n\n"
        "🗑 **2. Delete Indexed Data:**\n"
        "Use `/delete <target_chat_id> <source_chat_id>` to unlink.\n\n"
        "🔍 **3. Search:**\n"
        "Simply send a movie name in your group to search.\n\n"
        "⚙️ **Notes:**\n"
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
