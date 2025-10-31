import re
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from search_info import extract_movie_details
from database import database
from info import ADMINS

# Setup logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@Client.on_message(filters.command("index") & filters.group)
async def index_command(client: Client, message: Message):
    """Command to index all movies from a source chat."""

    # Check if user is admin or owner
    user = await client.get_chat_member(message.chat.id, message.from_user.id)
    if user.status not in ["creator", "administrator"]:
        await message.reply_text("❌ Only group admins or owner can use this command!")
        return

    # Check if chat ID is provided
    if len(message.command) < 2:
        await message.reply_text("❌ Please provide chat ID!\nUsage: `/index -10083829927`")
        return

    # Validate chat ID
    try:
        source_chat_id = int(message.command[1])
    except ValueError:
        await message.reply_text("❌ Invalid chat ID format!")
        return

    processing_msg = await message.reply_text("🔄 Indexing movies from source chat...")

    try:
        # Add group to database
        success = await database.add_group(
            group_id=message.chat.id,
            source_chat_id=source_chat_id,
            added_by=message.from_user.id
        )

        if not success:
            await processing_msg.edit_text("❌ Failed to add group to database!")
            return

        # Index movies from source chat
        indexed_count = 0
        async for msg in client.USER.search_messages(
            source_chat_id,
            filter="video"
        ):
            if msg.caption:
                movie_name, year, quality = extract_movie_details(msg.caption)
                movie_data = {
                    "movie_name": movie_name,
                    "year": year,
                    "quality": quality,
                    "caption": msg.caption,
                    "message_link": msg.link,
                    "file_id": getattr(msg.video, "file_id", None) if msg.video else None,
                    "file_size": getattr(msg.video, "file_size", 0) if msg.video else 0
                }

                success = await database.add_movie(message.chat.id, movie_data)
                if success:
                    indexed_count += 1

        await processing_msg.edit_text(
            f"✅ Successfully indexed {indexed_count} movies!\n"
            f"📁 Group: {message.chat.title}\n"
            f"🔗 Source: {source_chat_id}"
        )

    except Exception as e:
        logger.error(f"Indexing error: {e}")
        await processing_msg.edit_text(f"❌ Error during indexing: {str(e)}")


@Client.on_message(filters.command("delete") & filters.group)
async def delete_command(client: Client, message: Message):
    """Command to delete a group's data from the database."""

    # Check if user is admin or owner
    user = await client.get_chat_member(message.chat.id, message.from_user.id)
    if user.status not in ["creator", "administrator"]:
        await message.reply_text("❌ Only group admins or owner can use this command!")
        return

    # Check if group ID is provided
    if len(message.command) < 2:
        await message.reply_text("❌ Please provide group ID!\nUsage: `/delete -10073883874`")
        return

    # Validate group ID
    try:
        group_id = int(message.command[1])
    except ValueError:
        await message.reply_text("❌ Invalid group ID format!")
        return

    processing_msg = await message.reply_text("🔄 Deleting group data...")

    try:
        success = await database.remove_group(group_id)
        if success:
            await processing_msg.edit_text("✅ Group data deleted successfully!")
        else:
            await processing_msg.edit_text("❌ Group not found in database!")
    except Exception as e:
        logger.error(f"Deletion error: {e}")
        await processing_msg.edit_text(f"❌ Error during deletion: {str(e)}")
