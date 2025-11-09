from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus, MessageMediaType, MessagesFilter
from pyrogram.errors import RPCError, FloodWait
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncio
import logging
from .search import clear_redis_for_chat
from info import AUTHORIZED_USERS
from utils.database import (
    delete_chat_data_async,
    mark_indexed_chat_async,
    save_movie_async,
    rebuild_indexes
)
from utils import extract_details

logger = logging.getLogger(__name__)

REINDEXING = {}
BATCH_SIZE = 50


@Client.on_message(filters.command("reindex"))
async def reindex_chat(client, message):
    user_id = message.from_user.id
    if user_id not in AUTHORIZED_USERS:
        return

    parts = message.text.split()
    if len(parts) < 3:
        return await message.reply_text("Usage: `/reindex target_chat_id source_chat_id`")

    target_chat_id = int(parts[1])
    source_chat_id = int(parts[2])

    if REINDEXING.get(user_id):
        return await message.reply_text("⚠️ Reindexing already running! Please wait or cancel it first.")

    try:
        bot_member = await client.get_chat_member(target_chat_id, "me")
        if bot_member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            return await message.reply_text("❌ Bot must be admin in target chat!")
    except Exception as e:
        return await message.reply_text(f"⚠️ Error accessing target chat: {e}")

    try:
        user_member = await client.get_chat_member(target_chat_id, user_id)
        if user_member.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            return await message.reply_text("❌ You must be admin in target chat to start reindexing!")
    except Exception as e:
        return await message.reply_text(f"⚠️ Error verifying user permissions: {e}")

    try:
        bot_member_source = await client.get_chat_member(source_chat_id, "me")
        if bot_member_source.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            return await message.reply_text("❌ Bot must be admin in source chat!")
    except Exception as e:
        return await message.reply_text(f"⚠️ Error accessing source chat: {e}")

    try:
        userbot_member = await client.USER.get_chat_member(source_chat_id, "me")
        if userbot_member.status not in [
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.OWNER,
            ChatMemberStatus.MEMBER
        ]:
            return await message.reply_text("❌ Userbot must be at least a member in source chat!")
    except Exception as e:
        return await message.reply_text(f"⚠️ Userbot can't access source chat: {e}")

    await message.reply_text(f"🗑️ Deleting old MongoDB and Redis data for `{target_chat_id}`...")
    deleted_mongo = await delete_chat_data_async(chat_id=target_chat_id)
    deleted_redis = await clear_redis_for_chat(target_chat_id)
    await message.reply_text(f"✅ Deleted {deleted_mongo} Mongo docs and {deleted_redis} Redis keys.")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_reindex_{user_id}")]
    ])
    progress = await message.reply_text(
        f"♻️ Reindexing started...\nFrom `{source_chat_id}` → `{target_chat_id}`",
        reply_markup=keyboard
    )

    REINDEXING[user_id] = True

    indexed = 0
    errors = 0
    unsupported = 0

    try:
        async for msg in client.USER.search_messages(
            source_chat_id,
            filter=MessagesFilter.EMPTY,
            offset=0
        ):
            if not REINDEXING.get(user_id):
                await progress.edit_text("🚫 Indexing cancelled.")
                return

            if not msg.media:
                unsupported += 1
                continue

            if msg.media not in [MessageMediaType.VIDEO, MessageMediaType.DOCUMENT]:
                unsupported += 1
                continue

            msg_caption = (
                msg.caption
                or getattr(msg.video, "file_name", None)
                or getattr(msg.document, "file_name", None)
            )
            if not msg_caption:
                unsupported += 1
                continue

            try:
                details = extract_details(msg_caption)
                await save_movie_async(
                    chat_id=target_chat_id,
                    title=details.get("title"),
                    year=details.get("year"),
                    quality=details.get("quality"),
                    lang=details.get("lang"),
                    print_type=details.get("print"),
                    season=details.get("season"),
                    episode=details.get("episode"),
                    codec=details.get("codec"),
                    caption=msg_caption,
                    link=msg.link
                )
                indexed += 1

                if indexed % BATCH_SIZE == 0:
                    await asyncio.sleep(2)
                    await progress.edit_text(
                        f"📈 Reindexing...\nIndexed: {indexed}\nUnsupported: {unsupported}\n⚠️ Failed: {errors}\n"
                        f"From `{source_chat_id}` → `{target_chat_id}`",
                        reply_markup=keyboard
                    )
            except Exception as inner_e:
                errors += 1
                logger.warning(f"⚠️ Skipped message due to error: {inner_e}")

        await rebuild_indexes()
        await mark_indexed_chat_async(target_chat_id, source_chat_id)

        await progress.edit_text(
            f"✅ Reindex Completed!\n\n"
            f"📂 Indexed: {indexed}\n⚠️ Unsupported: {unsupported}\n❌ Failed: {errors}\n"
            f"🔗 `{source_chat_id}` → `{target_chat_id}`"
        )

    except Exception as e:
        await progress.edit_text(f"❌ Error during reindex: {e}")
        logger.exception(e)

    finally:
        REINDEXING.pop(user_id, None)


@Client.on_callback_query(filters.regex(r"cancel_reindex_(\d+)"))
async def cancel_reindex_callback(client, callback_query):
    user_id = int(callback_query.matches[0].group(1))
    REINDEXING[user_id] = False
    await callback_query.answer("Cancelled!", show_alert=True)
    await callback_query.message.edit_text("🚫 Indexing cancelled.")
