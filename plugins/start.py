from pyrogram import Client, filters
from pyrogram import Client, filters
from pyrogram.enums import MessagesFilter
from utils.database import save_movie, delete_chat_data
from utils import extract_details
import asyncio
import re

@Client.on_message(filters.command("index"))
async def index_chat(client, message):
    """
    Index all movies from a given chat/channel ID into MongoDB.
    Usage: /index -1001234567890
    """
    parts = message.text.split()
    if len(parts) < 2:
        return await message.reply_text("Usage: `/index chat_id`", quote=True)

    chat_id = parts[1]
    indexed_count = 0

    try:
        await message.reply_text(f"📦 Indexing started for `{chat_id}`...")

        async for msg in client.USER.search_messages(int(chat_id), filter=MessagesFilter.VIDEO):
            if msg.caption and msg.link:
                # Extract structured details
                details = extract_details(msg.caption)

                # Save movie entry
                save_movie(
                    chat_id=int(chat_id),
                    title=details.get("title"),
                    year=details.get("year"),
                    quality=details.get("quality"),
                    language=details.get("language"),
                    print_type=details.get("print"),
                    season=details.get("season"),
                    episode=details.get("episode"),
                    caption=msg.caption,
                    link=msg.link
                )

                indexed_count += 1

                # Slow down a little to avoid floodwaits
                if indexed_count % 50 == 0:
                    await asyncio.sleep(2)

        await message.reply_text(f"✅ Indexing completed!\nTotal: **{indexed_count}** messages indexed.")

    except Exception as e:
        await message.reply_text(f"❌ Error: `{e}`", quote=True)


@Client.on_message(filters.command("delete"))
async def delete_chat(client, message):
    """
    Delete all indexed data for a specific chat_id.
    Usage: /delete -1001234567890
    """
    parts = message.text.split()
    if len(parts) < 2:
        return await message.reply_text("Usage: `/delete chat_id`", quote=True)

    chat_id = int(parts[1])
    deleted = delete_chat_data(chat_id)

    if deleted:
        await message.reply_text(f"🗑 Deleted **{deleted}** records from `{chat_id}`.")
    else:
        await message.reply_text(f"No data found for `{chat_id}`.")
