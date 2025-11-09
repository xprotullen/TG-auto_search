import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus, MessagesFilter, MessageMediaType
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import RPCError, FloodWait
from .search import clear_redis_for_chat
from utils.database import (
    save_movie_async,
    delete_chat_data_async,
    mark_indexed_chat_async,
    unmark_indexed_chat_async,
    is_source_linked_to_target
)
from utils import extract_details
from info import AUTHORIZED_USERS

INDEXING = {}
BATCH_SIZE = 50
logger = logging.getLogger(__name__)


@Client.on_message(filters.command("index"))
async def index_chat(client, message):
    """
    /index <target_chat_id> <source_chat_id>
    Example: /index -1001234 -1005678
    """
    user_id = message.from_user.id
    if user_id not in AUTHORIZED_USERS:
        return

    parts = message.text.split()
    if len(parts) < 3:
        return await message.reply_text("Usage: `/index target_chat_id source_chat_id`")

    target_chat_id = int(parts[1])
    source_chat_id = int(parts[2])

    if INDEXING.get(user_id):
        return await message.reply_text("⚠️ Indexing already in progress! Please wait or cancel it first.")

    async def check_admin(chat_id, who):
        try:
            member = await client.get_chat_member(chat_id, who)
            return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
        except Exception:
            return False

    if not await check_admin(target_chat_id, "me"):
        return await message.reply_text("❌ Bot must be admin in target chat!")

    if not await check_admin(target_chat_id, user_id):
        return await message.reply_text("❌ You must be admin in target chat!")

    if not await check_admin(source_chat_id, "me"):
        return await message.reply_text("❌ Bot must be admin in source chat!")

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
        
    if await is_source_linked_to_target(target_chat_id, source_chat_id):
    return await message.reply_text(
        f"⚠️ `{target_chat_id}` is already indexed from `{source_chat_id}`.\n"
        f"To reindex, run `/delete {target_chat_id} {source_chat_id}` first."
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_index_{user_id}")]
    ])
    progress = await message.reply_text(
        f"📦 Indexing started...\nFrom `{source_chat_id}` → `{target_chat_id}`",
        reply_markup=keyboard
    )

    INDEXING[user_id] = True
    indexed = 0
    errors = 0
    unsupported = 0
    skipped_uid = 0
    duplicates = 0

    try:
        async for msg in client.USER.search_messages(
            source_chat_id,
            filter=MessagesFilter.EMPTY,
            offset=0
        ):
            try:
                if not INDEXING.get(user_id):
                    await progress.edit_text("🚫 Indexing cancelled.")
                    return

                if not msg.media:
                    unsupported += 1
                    continue

                if msg.media not in [MessageMediaType.VIDEO, MessageMediaType.DOCUMENT]:
                    unsupported += 1
                    continue

                caption = (
                    msg.caption
                    or getattr(msg.video, "file_name", None)
                    or getattr(msg.document, "file_name", None)
                )
                if not caption:
                    unsupported += 1
                    continue

                file_uid = (
                    getattr(msg.video, "file_unique_id", None)
                    or getattr(msg.document, "file_unique_id", None)
                )

                if not file_uid:
                    skipped_uid += 1
                    continue

                try:
                    details = extract_details(caption)
                    result = await save_movie_async(
                        chat_id=target_chat_id,
                        title=details.get("title"),
                        year=details.get("year"),
                        quality=details.get("quality"),
                        lang=details.get("lang"),
                        print_type=details.get("print"),
                        season=details.get("season"),
                        episode=details.get("episode"),
                        codec=details.get("codec"),
                        caption=caption,
                        link=msg.link,
                        file_unique_id=file_uid
                    )

                    if result == "saved":
                        indexed += 1
                    elif result == "duplicate":
                        duplicates += 1
                    else:
                        errors += 1

                    total = indexed + duplicates + errors + unsupported
                    if total % BATCH_SIZE == 0:
                        await asyncio.sleep(2)
                        await progress.edit_text(
                            f"📈 Indexing Progress\n"
                            f"✅ Indexed: {indexed}\n"
                            f"⏩ Duplicates: {duplicates}\n"
                            f"❎ Skipped (no UID): {skipped_uid}\n"
                            f"⚠️ Unsupported: {unsupported}\n"
                            f"❌ Failed: {errors}\n"
                            f"From `{source_chat_id}` → `{target_chat_id}`",
                            reply_markup=keyboard
                        )

                except FloodWait as fw:
                    await asyncio.sleep(fw.value)
                except Exception as inner_e:
                    errors += 1
                    logger.warning(f"⚠️ Skipped message due to error: {inner_e}")

        await mark_indexed_chat_async(target_chat_id, source_chat_id)
        await progress.edit_text(
            f"✅ Completed!\n\n📂 Indexed: <b>{indexed}</b>\n⏩ Duplicates: <b>{duplicates}</b>\n"
            f"❎ Skipped (no UID): <b>{skipped_uid}</b>\nUnsupported: {unsupported}\n⚠️ Failed: <b>{errors}</b>\n"
            f"Linked `{source_chat_id}` → `{target_chat_id}`"
        )

    except Exception as e:
        await progress.edit_text(f"❌ Error during indexing: {e}")
        logger.exception(e)
    finally:
        INDEXING.pop(user_id, None)


@Client.on_callback_query(filters.regex(r"cancel_index_(\d+)"))
async def cancel_index_callback(client, callback_query):
    user_id = int(callback_query.matches[0].group(1))
    INDEXING[user_id] = False
    await callback_query.answer("Cancelled!", show_alert=True)
    await callback_query.message.edit_text("🚫 Indexing cancelled.")


@Client.on_message(filters.command("delete"))
async def delete_indexed_pair(client, message):
    """
    /delete <target_chat_id> <source_chat_id>
    Removes mapping & deletes records for that target.
    """
    user_id = message.from_user.id
    if user_id not in AUTHORIZED_USERS:
        return

    parts = message.text.split()
    if len(parts) < 3:
        return await message.reply_text("Usage: `/delete target_chat_id source_chat_id`")

    target_chat_id = int(parts[1])
    source_chat_id = int(parts[2])

    try:
        mongo_deleted = await delete_chat_data_async(target_chat_id)
        redis_deleted = await clear_redis_for_chat(target_chat_id)
        await unmark_indexed_chat_async(target_chat_id, source_chat_id)
        await message.reply_text(
            f"🗑 MongoDB: Deleted <b>{mongo_deleted} records</b>\n"
            f"🧹 Redis: Deleted {redis_deleted} keys\n"
            f"🔗 Unlinked `{source_chat_id}` → `{target_chat_id}`"
        )
    except Exception as e:
        await message.reply_text(f"❌ Error: `{e}`")
