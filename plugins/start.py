from pyrogram import Client, filters
from utils.database import save_movie, delete_chat_data
from pyrogram.enums import MessagesFilter
import re

@Client.on_message(filters.command("index"))
async def index_chat(client, message):
    parts = message.text.split()
    if len(parts) < 2:
        return await message.reply_text("Usage: `/index chat_id`", quote=True)
    
    chat_id = parts[1]

    try:
        await message.reply_text(f"📦 Indexing started for `{chat_id}`...")
        async for msg in client.USER.search_messages(int(chat_id), filter=MessagesFilter.VIDEO):
            if msg.caption and msg.link:
                save_movie(chat_id, msg.link, msg.caption)
        await message.reply_text("✅ Indexing completed successfully!")
    except Exception as e:
        await message.reply_text(f"❌ Error: `{e}`")

@Client.on_message(filters.command("delete"))
async def delete_chat(client, message):
    parts = message.text.split()
    if len(parts) < 2:
        return await message.reply_text("Usage: `/delete chat_id`", quote=True)
    
    chat_id = parts[1]
    deleted = delete_chat_data(chat_id)
    await message.reply_text(f"🗑 Deleted {deleted} records from `{chat_id}`")
