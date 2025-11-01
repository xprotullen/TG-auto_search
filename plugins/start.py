import asyncio
from pyrogram import Client, filters
from pyrogram.enums import MessagesFilter
from utils.database import save_movie_async, delete_chat_data_async
from utils import extract_details

BATCH_SIZE = 50  # batch sleep after every 50 inserts


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
    errors = 0

    await message.reply_text(f"📦 Indexing started for `{chat_id}`...")

    try:
        # iterate over videos in the chat
        async for msg in client.USER.search_messages(
            int(chat_id),
            filter=MessagesFilter.VIDEO
        ):
            try:
                if not msg.caption:
                    continue

                # extract structured data
                details = extract_details(msg.caption)

                # save entry in Mongo
                await save_movie_async(
                    chat_id=int(chat_id),
                    title=details.get("title"),
                    year=details.get("year"),
                    quality=details.get("quality"),
                    lang=details.get("lang"),
                    print_type=details.get("print"),
                    season=details.get("season"),
                    episode=details.get("episode"),
                    caption=msg.caption,
                    link=msg.link
                )
                indexed_count += 1

                # avoid hitting floodwaits
                if indexed_count % BATCH_SIZE == 0:
                    await asyncio.sleep(2)

            except Exception as inner_e:
                errors += 1
                print(f"⚠️ Skipped one message: {inner_e}")

        await message.reply_text(
            f"✅ Indexing completed!\n"
            f"📂 Total Indexed: **{indexed_count}**\n"
            f"⚠️ Failed: **{errors}**"
        )

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
    try:
        deleted = await delete_chat_data_async(chat_id)
        if deleted:
            await message.reply_text(f"🗑 Deleted **{deleted}** records from `{chat_id}`.")
        else:
            await message.reply_text(f"No data found for `{chat_id}`.")
    except Exception as e:
        await message.reply_text(f"❌ Error: `{e}`", quote=True)
